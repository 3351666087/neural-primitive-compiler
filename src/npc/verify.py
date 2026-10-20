"""Independent verification engines.

  bmc         Z3 bounded model checking: all input traces of length T.
  exhaustive  brute-force enumeration of all 2^(m*T) traces (numpy); shares no
              code with the SMT path, so it cross-checks the encoding.
  reach       explicit-state breadth-first reachability over the product of the
              network state and the specification monitors. Because the
              semantics is finite-state, a completed search is a proof for
              input traces of *every* length (VERIFIED_UNBOUNDED) - relative to
              the formal semantics in network.py, nothing more.

Every counterexample from every engine is replayed through the reference
interpreter (simulator.simulate) and the batch spec evaluator before it is
reported; a disagreement raises EngineBug instead of being reported.
"""

from __future__ import annotations

import itertools
import math
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

import numpy as np
import z3

from .network import Network
from .simulator import BatchSim, CompiledNet, simulate
from .smt import unroll, violation_terms
from .spec import Monitor, Spec


class Status(str, Enum):
    VERIFIED_BOUNDED = "VERIFIED_BOUNDED"
    VERIFIED_UNBOUNDED = "VERIFIED_UNBOUNDED"
    COUNTEREXAMPLE = "COUNTEREXAMPLE"
    UNKNOWN = "UNKNOWN"
    TIMEOUT = "TIMEOUT"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"


class EngineBug(RuntimeError):
    pass


@dataclass
class Result:
    status: Status
    engine: str
    scope: str
    time_s: float
    horizon: int | None = None
    counterexample: dict[str, list[int]] | None = None
    violation_time: int | None = None
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def verified(self) -> bool:
        return self.status in (Status.VERIFIED_BOUNDED, Status.VERIFIED_UNBOUNDED)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    def summary(self) -> str:
        if self.status == Status.COUNTEREXAMPLE:
            s = f"[{self.engine}] {self.status.value} ({self.time_s:.3f}s) - spec refuted by a concrete input trace"
        elif self.verified:
            s = f"[{self.engine}] {self.status.value} ({self.time_s:.3f}s) - holds for {self.scope}"
        else:
            s = f"[{self.engine}] {self.status.value} ({self.time_s:.3f}s) - NO CONCLUSION {self.stats}"
        if self.counterexample is not None:
            s += f"\n    counterexample (violation at t={self.violation_time}): " + ", ".join(
                f"{k}={''.join(map(str, v))}" for k, v in self.counterexample.items())
        return s


def _check_interface(net: Network, spec: Spec) -> None:
    if set(spec.inputs) != set(net.inputs):
        raise ValueError(f"spec inputs {spec.inputs} != network inputs {net.inputs}")
    missing = set(spec.outputs) - set(net.output_names)
    if missing:
        raise ValueError(f"network lacks outputs {sorted(missing)}")


def _scope(spec: Spec, horizon: int | None) -> str:
    dom = f"all binary input traces over {list(spec.inputs)}"
    if spec.assume.op != "const":
        dom += " satisfying the assumption"
    if horizon is None:
        return f"{dom}, every length (finite-state proof)"
    return f"{dom} of length {horizon} (steps 0..{horizon - 1}); says nothing about later steps"


def replay(net: Network, spec: Spec, cex: Mapping[str, Sequence[int]]) -> int | None:
    """Re-run a counterexample on the reference interpreter. Returns violation time or None."""
    tr = simulate(net, {k: cex[k] for k in net.inputs})
    signals = dict(tr.inputs)
    for p in spec.outputs:
        signals[p] = tr.outputs[p]
    return spec.first_violation(signals)


def _confirm(net: Network, spec: Spec, cex: dict[str, list[int]], engine: str) -> int:
    t = replay(net, spec, cex)
    if t is None:
        raise EngineBug(f"{engine} produced a counterexample that does not replay: {cex}")
    return t


# ------------------------------------------------------------------------- BMC
def bmc(net: Network, spec: Spec, T: int, timeout_s: float = 60.0) -> Result:
    _check_interface(net, spec)
    t0 = time.perf_counter()
    solver = z3.Solver()
    solver.set("timeout", max(1, int(timeout_s * 1000)))
    x = {k: [z3.Bool(f"x_{k}_{t}") for t in range(T)] for k in net.inputs}
    cons: list = []
    spikes = unroll(net, T, x, cons, prefix="v_")
    env: dict[str, Any] = dict(x)
    for p, n in net.outputs:
        env[p] = spikes[n]
    viol = violation_terms(spec, env, T)
    solver.add(*cons)
    solver.add(z3.Or(*[v for _, v in viol]) if viol else z3.BoolVal(False))
    r = solver.check()
    dt = time.perf_counter() - t0
    stats = {"neuron_steps": len(net.neurons) * T, "constraints": len(cons)}
    if r == z3.unsat:
        return Result(Status.VERIFIED_BOUNDED, "bmc", _scope(spec, T), dt, T, stats=stats)
    if r == z3.sat:
        mdl = solver.model()
        first = min(t for t, v in viol if z3.is_true(mdl.eval(v, model_completion=True)))
        cex = {k: [int(z3.is_true(mdl.eval(x[k][t], model_completion=True))) for t in range(first + 1)]
               for k in net.inputs}
        vt = _confirm(net, spec, cex, "bmc")
        return Result(Status.COUNTEREXAMPLE, "bmc", _scope(spec, T), dt, T, cex, vt, stats)
    reason = solver.reason_unknown()
    st = Status.TIMEOUT if ("timeout" in reason or "canceled" in reason) else Status.UNKNOWN
    stats["reason"] = reason
    return Result(st, "bmc", _scope(spec, T), dt, T, stats=stats)


# ------------------------------------------------------------------ exhaustive
def all_traces(m: int, T: int, start: int, stop: int) -> np.ndarray:
    idx = np.arange(start, stop, dtype=np.int64)
    bits = (idx[:, None] >> np.arange(m * T, dtype=np.int64)) & 1
    return bits.reshape(-1, m, T)


def exhaustive(net: Network, spec: Spec, T: int, max_traces: int = 1 << 20, chunk: int = 1 << 14) -> Result:
    _check_interface(net, spec)
    t0 = time.perf_counter()
    m = len(net.inputs)
    total = 1 << (m * T)
    if total > max_traces:
        return Result(Status.RESOURCE_LIMIT, "exhaustive", _scope(spec, T), time.perf_counter() - t0, T,
                      stats={"traces_needed": total, "max_traces": max_traces})
    sim = BatchSim(net)
    out_rows = {p: sim.m + net.neuron_names.index(n) for p, n in net.outputs}
    for start in range(0, total, chunk):
        X = all_traces(m, T, start, min(total, start + chunk))
        S = sim.run(X)
        env = {k: X[:, i, :] for i, k in enumerate(net.inputs)}
        for p in spec.outputs:
            env[p] = S[:, out_rows[p], :]
        mask = spec.violation_mask(env)
        hit = mask.any(axis=1)
        if hit.any():
            rows = np.flatnonzero(hit)
            firsts = mask[rows].argmax(axis=1)
            j = int(np.argmin(firsts))
            b, tv = int(rows[j]), int(firsts[j])
            cex = {k: [int(v) for v in X[b, i, : tv + 1]] for i, k in enumerate(net.inputs)}
            vt = _confirm(net, spec, cex, "exhaustive")
            return Result(Status.COUNTEREXAMPLE, "exhaustive", _scope(spec, T), time.perf_counter() - t0, T,
                          cex, vt, {"traces": total})
    return Result(Status.VERIFIED_BOUNDED, "exhaustive", _scope(spec, T), time.perf_counter() - t0, T,
                  stats={"traces": total})


# ----------------------------------------------------------------------- reach
class NetSystem:
    """Adapter exposing a network through the generic explorer interface."""

    def __init__(self, net: Network):
        self.cn = CompiledNet(net)
        self.inputs = tuple(net.inputs)
        self.signals = tuple(net.output_names)

    def initial_state(self):
        return self.cn.initial_state()

    def fire(self, state):
        spikes, pots = self.cn.fire(state)
        return dict(zip(self.signals, self.cn.outputs(spikes))), (spikes, pots)

    def advance(self, state, aux, x):
        return self.cn.advance(state, aux[0], aux[1], x)


def reach(net: Network, spec: Spec, max_states: int = 2_000_000, timeout_s: float = 120.0) -> Result:
    """Breadth-first exploration of (network state, assume monitor, guarantee monitor, warm-up counter)."""
    _check_interface(net, spec)
    return explore(NetSystem(net), spec, max_states=max_states, timeout_s=timeout_s, replay_net=net)


def explore(system, spec: Spec, obligations: Sequence[tuple[str, Monitor]] = (), max_states: int = 2_000_000,
            timeout_s: float = 120.0, replay_net: Network | None = None, engine: str = "reach") -> Result:
    """Generic explicit-state check of ``spec`` (and of extra ``obligations``, formulas that must hold
    whenever the spec's assumption has held) over any finite system with the interface
    initial_state() / fire(state) -> (signal values, aux) / advance(state, aux, x)."""
    t0 = time.perf_counter()
    A, G = Monitor(spec.assume), Monitor(spec.guarantee)
    ins = list(system.inputs)
    letters = list(itertools.product((0, 1), repeat=len(ins)))
    strict = spec.assume_mode == "strict"
    w_max = spec.warmup
    obs = list(obligations)
    init = (system.initial_state(), A.init, G.init, tuple(m.init for _, m in obs), 0)
    parent: dict[tuple, tuple | None] = {init: None}
    depth = {init: 0}
    frontier = deque([init])
    sys_states: set = set()
    max_depth = 0
    steps = 0

    def trace_to(st, x):
        path = [x]
        cur = st
        while parent[cur] is not None:
            prev, px = parent[cur]
            path.append(px)
            cur = prev
        path.reverse()
        return {k: [p[i] for p in path] for i, k in enumerate(ins)}

    while frontier:
        st = frontier.popleft()
        sst, ast, gst, ost, w = st
        sys_states.add(sst)
        sval, aux = system.fire(sst)
        for x in letters:
            val = dict(zip(ins, x))
            val.update(sval)
            ast2, aok = A.step(ast, val)
            gst2, gok = G.step(gst, val)
            ost2 = []
            for j, (label, mon) in enumerate(obs):
                o2, ook = mon.step(ost[j], val)
                ost2.append(o2)
                if not ook and (aok or strict):
                    cex = trace_to(st, x)
                    return Result(Status.UNKNOWN, engine, _scope(spec, None), time.perf_counter() - t0, None, cex,
                                  depth[st], {"reason": f"obligation not discharged: {label}", "states": len(parent)})
            if w >= w_max and not gok and (aok or strict):
                cex = trace_to(st, x)
                vt = _confirm(replay_net, spec, cex, engine) if replay_net is not None else depth[st]
                return Result(Status.COUNTEREXAMPLE, engine, _scope(spec, None), time.perf_counter() - t0, None,
                              cex, vt, {"states": len(parent)})
            if not aok:
                continue
            nxt = (system.advance(sst, aux, x), ast2, gst2, tuple(ost2), min(w + 1, w_max))
            if nxt not in parent:
                parent[nxt] = (st, x)
                d = depth[st] + 1
                depth[nxt] = d
                max_depth = max(max_depth, d)
                frontier.append(nxt)
                if len(parent) > max_states:
                    return Result(Status.RESOURCE_LIMIT, engine, _scope(spec, None), time.perf_counter() - t0,
                                  None, stats={"states": len(parent), "max_states": max_states})
        steps += 1
        if steps % 2048 == 0 and time.perf_counter() - t0 > timeout_s:
            return Result(Status.TIMEOUT, engine, _scope(spec, None), time.perf_counter() - t0, None,
                          stats={"states": len(parent)})
    stats = {
        "product_states": len(parent),
        "system_states": len(sys_states),
        "effective_state_bits": round(math.log2(max(1, len(sys_states))), 3),
        "bfs_depth": max_depth,
    }
    return Result(Status.VERIFIED_UNBOUNDED, engine, _scope(spec, None), time.perf_counter() - t0, None, stats=stats)


# ------------------------------------------------------------------ orchestration
def verify_all(net: Network, spec: Spec, T: int, engines: Sequence[str] = ("bmc", "exhaustive", "reach"),
               timeout_s: float = 60.0, max_states: int = 2_000_000, max_traces: int = 1 << 20) -> list[Result]:
    res = []
    for e in engines:
        if e == "bmc":
            res.append(bmc(net, spec, T, timeout_s))
        elif e == "exhaustive":
            res.append(exhaustive(net, spec, T, max_traces=max_traces))
        elif e == "reach":
            res.append(reach(net, spec, max_states=max_states, timeout_s=timeout_s))
        else:
            raise ValueError(f"unknown engine {e}")
    check_consistency(res)
    return res


def check_consistency(results: Sequence[Result]) -> None:
    """Engines must never contradict each other on overlapping scopes."""
    bounded = [r for r in results if r.horizon is not None and r.status in (Status.VERIFIED_BOUNDED, Status.COUNTEREXAMPLE)]
    unb = [r for r in results if r.horizon is None and r.status in (Status.VERIFIED_UNBOUNDED, Status.COUNTEREXAMPLE)]
    for r in bounded:
        for q in bounded:
            if r.horizon == q.horizon and r.status != q.status:
                raise EngineBug(f"{r.engine}={r.status} but {q.engine}={q.status} at horizon {r.horizon}")
        for u in unb:
            if u.status == Status.VERIFIED_UNBOUNDED and r.status == Status.COUNTEREXAMPLE:
                raise EngineBug(f"reach proved the spec but {r.engine} found a counterexample")
            if (u.status == Status.COUNTEREXAMPLE and u.violation_time is not None
                    and u.violation_time < r.horizon and r.status == Status.VERIFIED_BOUNDED):
                raise EngineBug(f"reach found a violation at t={u.violation_time} < {r.horizon} "
                                f"but {r.engine} verified the bounded spec")
