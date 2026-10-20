"""Independent verification engines.

  bmc         Z3 bounded model checking: all input traces of length T.
  exhaustive  brute-force enumeration of all 2^(m*T) traces (numpy); shares no
              code with the SMT path, so it cross-checks the encoding.
  reach       explicit-state breadth-first reachability over the product of the
              network state and the specification monitors. Because the
              semantics is finite-state, a completed search is a proof for
              input traces of *every* length (VERIFIED_UNBOUNDED) - relative to
              the formal semantics in network.py, nothing more.
  kind        symbolic k-induction (Z3) over the same product state, encoded
              symbolically (SymNetSystem + SymMonitor). VERIFIED_UNBOUNDED only
              when the induction step or the forward (no loop-free path from the
              initial state) check closes; otherwise UNKNOWN / TIMEOUT.
  pdr         Z3 Spacer (IC3/PDR over constrained Horn clauses) on the same
              encoding. A "safe" answer counts only after the returned inductive
              invariant is re-checked by a plain solver.

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
from .spec import UNBOUNDED, F, Monitor, Spec


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


# ------------------------------------------------------------- symbolic (kind, pdr)
# A symbolic system exposes the explicit interface of NetSystem with Z3 terms:
#   components                 [(name, lo, hi)] - lo is None for a Bool component, else an Int in [lo, hi]
#   init_values()              initial state (Z3 values, one per component)
#   fire(state) -> (signals, aux)   signal values at the current step (independent of the current input)
#   advance(state, aux, x)     next state; x maps input name -> Z3 Bool
# State vectors are plain lists of Z3 terms, so a k-step path is k+1 copies of fresh constants.

class SymNetSystem:
    """Symbolic twin of CompiledNet: the same state (carried potentials u; bit j of source k's history
    = its value at t-1-j, max-outgoing-delay bits per source) and the same step, as pure Z3 terms.
    One exact simplification (as in smt.unroll): a memoryless neuron with init 0 carries u = 0 in every
    reachable state, so its u is the constant 0 rather than a state component."""

    def __init__(self, net: Network):
        net.validate()
        self.net = net
        self.inputs = tuple(net.inputs)
        self.signals = tuple(net.output_names)
        names = list(net.inputs) + list(net.neuron_names)
        idx = {k: i for i, k in enumerate(names)}
        depth = net.history_depth()
        self.n = len(net.neurons)
        self.depth = [depth[k] for k in names]
        self.components: list[tuple[str, int | None, int | None]] = []
        self.u_idx: list[int | None] = []  # neuron -> index of its u component (None: constant 0)
        for nr in net.neurons:
            if nr.memoryless and nr.init == 0:
                self.u_idx.append(None)
            else:
                self.u_idx.append(len(self.components))
                self.components.append((f"u_{nr.name}", nr.vmin, nr.vmax))
        self.n_u = len(self.components)
        self.hist_off = []
        for k, d in zip(names, self.depth):
            self.hist_off.append(len(self.components))
            self.components += [(f"h_{k}_{j}", None, None) for j in range(d)]
        self.incoming: list[list[tuple[int, int, int]]] = [[] for _ in range(self.n)]
        for s in net.synapses:
            self.incoming[idx[s.dst] - len(self.inputs)].append((idx[s.src], s.weight, s.delay - 1))
        self.out_idx = [(p, net.neuron_names.index(n)) for p, n in net.outputs]

    def init_values(self) -> list:
        return [z3.IntVal(nr.init) for nr, j in zip(self.net.neurons, self.u_idx) if j is not None] + \
               [z3.BoolVal(False)] * (len(self.components) - self.n_u)

    def _u(self, s: Sequence[Any], i: int) -> Any:
        j = self.u_idx[i]
        return z3.IntVal(0) if j is None else s[j]

    def _hist(self, s: Sequence[Any], k: int, j: int) -> Any:
        return s[self.hist_off[k] + j]

    def fire(self, s: Sequence[Any]):
        spikes, pots = [], []
        for i, nr in enumerate(self.net.neurons):
            terms = [z3.IntVal(nr.bias)] + [z3.If(self._hist(s, src, sh), w, 0) for src, w, sh in self.incoming[i]]
            raw = self._u(s, i) + z3.Sum(terms)
            v = z3.If(raw > nr.vmax, nr.vmax, z3.If(raw < nr.vmin, nr.vmin, raw))
            pots.append(v)
            spikes.append(v >= nr.threshold)
        return {p: spikes[i] for p, i in self.out_idx}, (spikes, pots)

    def advance(self, s: Sequence[Any], aux, x: Mapping[str, Any]) -> list:
        spikes, pots = aux
        nxt = []
        for i, nr in enumerate(self.net.neurons):
            if self.u_idx[i] is None:
                continue
            v, lk = pots[i], nr.leak
            nxt.append(z3.If(spikes[i], nr.reset, z3.If(v > lk, v - lk, z3.If(v < -lk, v + lk, 0))))
        vals = [x[k] for k in self.inputs] + spikes
        for k, d in enumerate(self.depth):
            if d:
                nxt += [vals[k]] + [self._hist(s, k, j) for j in range(d - 1)]
        return nxt


class SymMonitor:
    """Monitor.step over Z3 terms. Uses Monitor's own node list and slot layout (one component per
    Boolean in a buffer, one Int in [0, k-1] per modcount), so the state matches the explicit monitor."""

    def __init__(self, f: F, tag: str):
        self.mon = Monitor(f)
        self.components: list[tuple[str, int | None, int | None]] = []
        self.init: list = []
        self.layout: dict[int, tuple[int, int | None]] = {}  # slot -> (offset, length or None for a scalar)
        for g, _, slot in self.mon.nodes:
            if slot < 0:
                continue
            init = self.mon.init_slots[slot]
            off = len(self.components)
            if g.op == "modcount":
                self.components.append((f"{tag}{slot}", 0, g.params[0] - 1))
                self.init.append(z3.IntVal(init))
                self.layout[slot] = (off, None)
            elif isinstance(init, tuple):
                self.components += [(f"{tag}{slot}_{j}", None, None) for j in range(len(init))]
                self.init += [z3.BoolVal(bool(b)) for b in init]
                self.layout[slot] = (off, len(init))
            else:
                self.components.append((f"{tag}{slot}", None, None))
                self.init.append(z3.BoolVal(bool(init)))
                self.layout[slot] = (off, None)

    def step(self, st: Sequence[Any], val: Mapping[str, Any]) -> tuple[list, Any]:
        new = list(st)

        def get(slot):
            off, n = self.layout[slot]
            return st[off] if n is None else list(st[off:off + n])

        def put(slot, v):
            off, n = self.layout[slot]
            if n is None:
                new[off] = v
            else:
                new[off:off + n] = v

        vals: list[Any] = [None] * len(self.mon.nodes)
        for idx, (g, kids, slot) in enumerate(self.mon.nodes):
            op = g.op
            a = [vals[k] for k in kids]
            if op == "atom":
                v = val[g.params[0]]
                v = z3.BoolVal(bool(v)) if isinstance(v, (bool, int)) else v
            elif op == "const":
                v = z3.BoolVal(g.params[0])
            elif op == "not":
                v = z3.Not(a[0])
            elif op == "and":
                v = z3.And(*a)
            elif op == "or":
                v = z3.Or(*a)
            elif op == "xor":
                v = z3.Xor(a[0], a[1])
            elif op == "implies":
                v = z3.Implies(a[0], a[1])
            elif op == "iff":
                v = a[0] == a[1]
            elif op in ("prev", "wprev"):
                q = get(slot)
                v = q[0]
                put(slot, q[1:] + [a[0]])
            elif op in ("once", "hist"):
                lo, hi = g.params
                is_once = op == "once"
                if hi == UNBOUNDED:
                    v = z3.Or(get(slot), a[0]) if is_once else z3.And(get(slot), a[0])
                    put(slot, v)
                else:
                    q = get(slot) if hi > 0 else []
                    window = [q[hi - j] for j in range(max(lo, 1), hi + 1)]
                    if lo == 0:
                        window.append(a[0])
                    v = z3.Or(*window) if is_once else z3.And(*window)
                    if hi > 0:
                        put(slot, q[1:] + [a[0]])
            elif op == "since":
                v = z3.Or(a[1], z3.And(a[0], get(slot)))
                put(slot, v)
            elif op == "atleast":
                v = z3.Sum([z3.If(b, 1, 0) for b in a]) >= g.params[0]
            elif op == "cmp":
                l, r = a
                c = g.params[0]
                v = (l >= r) if c == ">=" else (l <= r) if c == "<=" else (l == r) if c == "==" else \
                    (l != r) if c == "!=" else (l > r) if c == ">" else (l < r)
            elif op == "int":
                v = z3.IntVal(g.params[0])
            elif op == "count":
                cur = z3.If(a[0], 1, 0)
                if g.params[0] > 1:
                    q = get(slot)
                    v = z3.Sum([cur] + [z3.If(b, 1, 0) for b in q])
                    put(slot, q[1:] + [a[0]])
                else:
                    v = cur
            elif op == "modcount":
                k = g.params[0]
                c = get(slot) + z3.If(a[0], 1, 0)
                v = z3.If(a[1], 0, z3.If(c >= k, c - k, c))  # == (c_prev + inc) % k for c_prev in [0, k-1]
                put(slot, v)
            elif op == "add":
                v = a[0] + a[1]
            elif op == "sub":
                v = a[0] - a[1]
            elif op == "mul":
                v = g.params[0] * a[0]
            else:
                raise ValueError(f"unknown op {op}")
            vals[idx] = v
        return new, vals[-1]


@dataclass
class _SymStep:
    aok: Any      # assumption holds at this step (the path may continue)
    bad: Any      # the spec is violated at this step (same condition as explore)
    obbad: Any    # an obligation (component assumption) fails at this step
    nxt: list


class SymProduct:
    """(system state, assume monitor, guarantee monitor, obligation monitors, warm-up counter) - the
    product explored by ``explore``, as a symbolic transition system."""

    def __init__(self, system, spec: Spec, obligations: Sequence[tuple[str, Monitor]] = ()):
        self.system = system
        self.inputs = tuple(system.inputs)
        self.A = SymMonitor(spec.assume, "A")
        self.G = SymMonitor(spec.guarantee, "G")
        self.obs = [(label, SymMonitor(m.root, f"O{j}_")) for j, (label, m) in enumerate(obligations)]
        self.strict = spec.assume_mode == "strict"
        self.W = spec.warmup
        parts = [list(system.components), self.A.components, self.G.components] + [m.components for _, m in self.obs]
        if self.W:
            parts.append([("warmup", 0, self.W)])
        self.cuts = [0]
        for p in parts:
            self.cuts.append(self.cuts[-1] + len(p))
        self.components = [c for p in parts for c in p]

    def _split(self, s: Sequence[Any]) -> list[list]:
        return [list(s[a:b]) for a, b in zip(self.cuts, self.cuts[1:])]

    def init_values(self) -> list:
        vals = list(self.system.init_values()) + self.A.init + self.G.init
        for _, m in self.obs:
            vals += m.init
        if self.W:
            vals.append(z3.IntVal(0))
        return vals

    def fresh(self, tag: str) -> list:
        return [z3.Bool(f"{tag}.{n}") if lo is None else z3.Int(f"{tag}.{n}") for n, lo, _ in self.components]

    def fresh_inputs(self, tag: str) -> dict[str, Any]:
        return {k: z3.Bool(f"{tag}.x_{k}") for k in self.inputs}

    def domain(self, s: Sequence[Any]) -> list:
        return [z3.And(v >= lo, v <= hi) for v, (_, lo, hi) in zip(s, self.components) if lo is not None]

    def step(self, s: Sequence[Any], x: Mapping[str, Any]) -> _SymStep:
        parts = self._split(s)
        sys_s, a_s, g_s = parts[0], parts[1], parts[2]
        sig, aux = self.system.fire(sys_s)
        val = dict(x)
        val.update(sig)
        a2, aok = self.A.step(a_s, val)
        g2, gok = self.G.step(g_s, val)
        nxt = list(self.system.advance(sys_s, aux, x)) + a2 + g2
        oks = []
        for j, (_, m) in enumerate(self.obs):
            o2, ook = m.step(parts[3 + j], val)
            oks.append(ook)
            nxt += o2
        gate = z3.BoolVal(True) if self.strict else aok
        warm = z3.BoolVal(True)
        if self.W:
            w = parts[-1][0]
            warm = w >= self.W
            nxt.append(z3.If(w + 1 > self.W, self.W, w + 1))
        bad = z3.And(warm, z3.Not(gok), gate)
        obbad = z3.And(z3.Or(*[z3.Not(o) for o in oks]), gate) if oks else z3.BoolVal(False)
        return _SymStep(aok, bad, obbad, nxt)

    def safe_for_all_inputs(self, st: _SymStep, x: Mapping[str, Any]) -> Any:
        """No violation and no failed obligation at this state, whatever the current input letter."""
        either = z3.Or(st.bad, st.obbad)
        out = []
        for letter in itertools.product((False, True), repeat=len(self.inputs)):
            sub = [(x[k], z3.BoolVal(b)) for k, b in zip(self.inputs, letter)]
            out.append(z3.Not(z3.substitute(either, *sub) if sub else either))
        return z3.And(*out)


def _eqs(a: Sequence[Any], b: Sequence[Any]) -> list:
    return [p == q for p, q in zip(a, b)]


def _value(e: Any) -> int:
    if z3.is_true(e):
        return 1
    if z3.is_false(e):
        return 0
    return e.as_long()


def _state_key(m: z3.ModelRef, s: Sequence[Any]) -> tuple:
    return tuple(_value(m.eval(v, model_completion=True)) for v in s)


class _Budget:
    def __init__(self, timeout_s: float):
        self.t0 = time.perf_counter()
        self.deadline = self.t0 + timeout_s
        self.checks = 0
        self.solver_s = 0.0  # time inside solver.check (the rest is encoding / model inspection)

    def elapsed(self) -> float:
        return time.perf_counter() - self.t0

    def stamp(self, stats: dict) -> dict:
        stats["solver_checks"] = self.checks
        stats["solver_time_s"] = round(self.solver_s, 4)
        return stats

    def check(self, solver: z3.Solver, *assumptions) -> tuple[Any, str]:
        rem = self.deadline - time.perf_counter()
        if rem <= 0:
            return z3.unknown, "timeout"
        solver.set("timeout", max(1, int(rem * 1000)))
        self.checks += 1
        t = time.perf_counter()
        r = solver.check(*assumptions)
        self.solver_s += time.perf_counter() - t
        return r, (solver.reason_unknown() if r == z3.unknown else "")

    def check_simple_path(self, solver: z3.Solver, states: Sequence[Sequence[Any]], stats: dict,
                          *assumptions) -> tuple[Any, str]:
        """Satisfiability restricted to loop-free paths, adding pairwise state disequalities lazily
        (only for pairs that a model actually repeats)."""
        while True:
            r, why = self.check(solver, *assumptions)
            if r != z3.sat:
                return r, why
            m = solver.model()
            seen: dict[tuple, int] = {}
            dup = None
            for i, s in enumerate(states):
                key = _state_key(m, s)
                if key in seen:
                    dup = (seen[key], i)
                    break
                seen[key] = i
            if dup is None:
                return r, ""
            solver.add(z3.Or(*[p != q for p, q in zip(states[dup[0]], states[dup[1]])]))
            stats["simple_path_constraints"] += 1


class _BaseUnroller:
    """BMC from the initial state, one time step per call: ``check_step`` asks for a violation at the
    next time step (sat = earliest counterexample, since all earlier steps were unsat)."""

    def __init__(self, P: SymProduct, budget: _Budget, tag: str = "b"):
        self.P, self.budget, self.tag = P, budget, tag
        self.solver = z3.Solver()
        self.states: list[list] = [P.init_values()]
        self.inputs: list[dict] = []
        self.steps: list[_SymStep] = []

    def check_step(self) -> tuple[Any, str]:
        k = len(self.inputs)
        x = self.P.fresh_inputs(f"{self.tag}{k}")
        st = self.P.step(self.states[k], x)
        self.inputs.append(x)
        self.steps.append(st)
        act = z3.Bool(f"{self.tag}.act{k}")
        self.solver.add(z3.Implies(act, z3.Or(st.bad, st.obbad)))
        return self.budget.check(self.solver, act)

    def close_step(self) -> None:
        """Called after check_step was UNSAT: record the lemma and extend the path by one transition."""
        k = len(self.inputs) - 1
        st = self.steps[k]
        nxt = self.P.fresh(f"{self.tag}{k + 1}")
        self.solver.add(self.P.safe_for_all_inputs(st, self.inputs[k]), st.aok, *_eqs(nxt, st.nxt))
        self.states.append(nxt)

    def trace(self, m: z3.ModelRef) -> dict[str, list[int]]:
        return {k: [_value(m.eval(x[k], model_completion=True)) for x in self.inputs] for k in self.P.inputs}


def _sym_violation(P: SymProduct, base: _BaseUnroller, spec: Spec, replay_net: Network | None, engine: str,
                   budget: _Budget, stats: dict) -> Result:
    budget.stamp(stats)
    m = base.solver.model()
    k = len(base.inputs) - 1
    cex = base.trace(m)
    if z3.is_true(m.eval(base.steps[k].obbad, model_completion=True)):
        stats["reason"] = "obligation not discharged"
        return Result(Status.UNKNOWN, engine, _scope(spec, None), budget.elapsed(), None, cex, k, stats)
    vt = _confirm(replay_net, spec, cex, engine) if replay_net is not None else k
    if vt != k:
        raise EngineBug(f"{engine}: earliest symbolic violation at t={k} but the replay violates at t={vt}")
    return Result(Status.COUNTEREXAMPLE, engine, _scope(spec, None), budget.elapsed(), None, cex, vt, stats)


def _inconclusive(spec: Spec, engine: str, budget: _Budget, stats: dict, why: str) -> Result:
    stats["reason"] = why
    budget.stamp(stats)
    timed_out = "timeout" in why or "canceled" in why or budget.elapsed() >= budget.deadline - budget.t0
    st = Status.TIMEOUT if timed_out else Status.UNKNOWN
    return Result(st, engine, _scope(spec, None), budget.elapsed(), None, stats=stats)


def kinduction(net: Network, spec: Spec, k_max: int = 200, timeout_s: float = 120.0, forward: bool = True) -> Result:
    """Unbounded check by k-induction over the symbolic network x monitor product (see kinduction_system)."""
    _check_interface(net, spec)
    return kinduction_system(SymNetSystem(net), spec, k_max=k_max, timeout_s=timeout_s, replay_net=net,
                             forward=forward)


def kinduction_system(system, spec: Spec, obligations: Sequence[tuple[str, Monitor]] = (), k_max: int = 200,
                      timeout_s: float = 120.0, replay_net: Network | None = None, engine: str = "kind",
                      forward: bool = True) -> Result:
    """k-induction with simple-path constraints (Sheeran-Singh-Stalmarck 2000; incremental form of
    Een-Sorensson 2003). For k = 0, 1, ...:

      base     no violation at time k on any path from the initial state (else: earliest counterexample);
      step     no path s_0..s_{k+1} that is loop-free, starts in the declared domain, has no violation
               (for any input letter) at s_0..s_k and has one at s_{k+1}            -> VERIFIED_UNBOUNDED;
      forward  no loop-free path s_0..s_{k+1} from the initial state (every reachable state is reached
               within k steps, and base covered times 0..k)                          -> VERIFIED_UNBOUNDED.

    Both closing checks are sound because a shortest violating path (and a shortest path to any
    state) never repeats a product state. If neither closes by k_max or the deadline, the result is
    UNKNOWN / TIMEOUT; ``stats['bounded_safe_upto']`` then records the bounded fact actually shown.
    """
    budget = _Budget(timeout_s)
    P = SymProduct(system, spec, obligations)
    stats: dict[str, Any] = {"state_components": len(P.components), "k": None, "closed_by": None,
                             "bounded_safe_upto": None, "simple_path_constraints": 0}
    base = _BaseUnroller(P, budget, "b")
    step = z3.Solver()
    ss = [P.fresh("s0")]
    step.add(*P.domain(ss[0]))
    sx = [P.fresh_inputs("s0")]
    sst = [P.step(ss[0], sx[0])]
    phase = {"base": 0.0, "step": 0.0, "forward": 0.0}  # wall time per check family, encoding included
    stats["phase_time_s"] = phase

    def done(status_closed: str) -> Result:
        stats["closed_by"] = status_closed
        stats["phase_time_s"] = {p: round(v, 4) for p, v in phase.items()}
        budget.stamp(stats)
        return Result(Status.VERIFIED_UNBOUNDED, engine, _scope(spec, None), budget.elapsed(), None, stats=stats)

    for k in range(k_max + 1):
        stats["k"] = k
        t = time.perf_counter()
        r, why = base.check_step()
        if r == z3.sat:
            return _sym_violation(P, base, spec, replay_net, engine, budget, stats)
        if r != z3.unsat:
            return _inconclusive(spec, engine, budget, stats, f"base case k={k}: {why}")
        base.close_step()
        stats["bounded_safe_upto"] = k
        phase["base"] += time.perf_counter() - t
        t = time.perf_counter()
        # induction step: hypothesis at s_k, then extend to s_{k+1} and ask for a violation there
        step.add(P.safe_for_all_inputs(sst[k], sx[k]), sst[k].aok)
        nxt = P.fresh(f"s{k + 1}")
        step.add(*_eqs(nxt, sst[k].nxt))
        ss.append(nxt)
        sx.append(P.fresh_inputs(f"s{k + 1}"))
        sst.append(P.step(nxt, sx[k + 1]))
        act = z3.Bool(f"s.act{k}")
        step.add(z3.Implies(act, z3.Or(sst[k + 1].bad, sst[k + 1].obbad)))
        r, why = budget.check_simple_path(step, ss, stats, act)
        phase["step"] += time.perf_counter() - t
        if r == z3.unsat:
            return done("induction")
        if r != z3.sat:
            return _inconclusive(spec, engine, budget, stats, f"induction step k={k}: {why}")
        if forward:
            t = time.perf_counter()
            r, why = budget.check_simple_path(base.solver, base.states, stats)
            phase["forward"] += time.perf_counter() - t
            if r == z3.unsat:
                return done("forward")
            if r != z3.sat:
                return _inconclusive(spec, engine, budget, stats, f"forward check k={k}: {why}")
    return _inconclusive(spec, engine, budget, stats, f"k_max={k_max} reached without closing")


def _interpretation(m: z3.ModelRef, f: z3.FuncDeclRef, args: Sequence[Any]) -> Any:
    """The model's interpretation of predicate f, applied to args (Spacer returns it over Var(i))."""
    fi = m[f]
    if fi is None:
        return z3.BoolVal(False)  # unconstrained: claim nothing, so the certificate check fails
    if isinstance(fi, z3.QuantifierRef):  # lambda: Var(0) is the last bound variable
        return z3.substitute_vars(fi.body(), *reversed(list(args)))
    if isinstance(fi, z3.ExprRef):  # zero-arity predicate (empty state vector): the model gives its value
        return z3.substitute_vars(fi, *reversed(list(args))) if args else fi
    out = z3.substitute_vars(fi.else_value(), *args)
    for i in range(fi.num_entries()):
        e = fi.entry(i)
        out = z3.If(z3.And(*[a == e.arg_value(j) for j, a in enumerate(args)]), e.value(), out)
    return out


def pdr(net: Network, spec: Spec, timeout_s: float = 120.0) -> Result:
    """Unbounded check with Z3's Spacer (IC3/PDR for constrained Horn clauses); see pdr_system."""
    _check_interface(net, spec)
    return pdr_system(SymNetSystem(net), spec, timeout_s=timeout_s, replay_net=net)


def pdr_system(system, spec: Spec, obligations: Sequence[tuple[str, Monitor]] = (), timeout_s: float = 120.0,
               replay_net: Network | None = None, engine: str = "pdr") -> Result:
    """Horn encoding: Inv(init); Inv(s) & aok & s' = next(s, x) -> Inv(s'); Inv(s) & bad(s, x) -> false.

    sat ("safe") is reported as VERIFIED_UNBOUNDED only after the invariant Spacer returns passes an
    independent check (initiation, consecution, safety) with a plain Z3 solver. unsat ("unsafe") is
    turned into a concrete trace by BMC from the initial state and replayed; if BMC does not reach it
    within the remaining budget the result is UNKNOWN, never a counterexample without a trace."""
    budget = _Budget(timeout_s)
    P = SymProduct(system, spec, obligations)
    stats: dict[str, Any] = {"state_components": len(P.components)}
    s, s2 = P.fresh("p"), P.fresh("q")
    x = P.fresh_inputs("p")
    st = P.step(s, x)
    xs = list(x.values())
    Inv = z3.Function("Inv", *[v.sort() for v in s], z3.BoolSort())
    h = z3.SolverFor("HORN")
    h.add(Inv(*P.init_values()))
    h.add(z3.ForAll(s + xs + s2, z3.Implies(z3.And(Inv(*s), st.aok, *_eqs(s2, st.nxt)), Inv(*s2))))
    bad_vars = s + xs
    h.add(z3.ForAll(bad_vars, z3.Implies(z3.And(Inv(*s), z3.Or(st.bad, st.obbad)), z3.BoolVal(False))))
    r, why = budget.check(h)
    stats["spacer_time_s"] = round(budget.elapsed(), 4)
    if r == z3.sat:
        m = h.model()
        inv_s = _interpretation(m, Inv, s)
        inv_s2 = _interpretation(m, Inv, s2)
        inv_0 = _interpretation(m, Inv, P.init_values())
        stats["invariant_size"] = len(str(inv_s))
        obligations_ = {"initiation": [z3.Not(inv_0)],
                        "consecution": [inv_s, st.aok, *_eqs(s2, st.nxt), z3.Not(inv_s2)],
                        "safety": [inv_s, z3.Or(st.bad, st.obbad)]}
        for name, fs in obligations_.items():
            c = z3.Solver()
            c.add(*fs)
            rc, why_c = budget.check(c)
            if rc != z3.unsat:
                stats["certificate"] = f"{name} check: {rc} {why_c}".strip()
                return _inconclusive(spec, engine, budget, stats, f"invariant not confirmed ({name}: {rc})")
        stats["certificate"] = "checked"
        budget.stamp(stats)
        return Result(Status.VERIFIED_UNBOUNDED, engine, _scope(spec, None), budget.elapsed(), None, stats=stats)
    if r == z3.unsat:
        base = _BaseUnroller(P, budget, "r")
        while True:
            rb, why_b = base.check_step()
            if rb == z3.sat:
                stats["reconstructed_by"] = "bmc"
                return _sym_violation(P, base, spec, replay_net, engine, budget, stats)
            if rb != z3.unsat:
                return _inconclusive(spec, engine, budget, stats,
                                     f"spacer reported a reachable violation; BMC did not rebuild it ({why_b})")
            base.close_step()
    return _inconclusive(spec, engine, budget, stats, f"spacer: {why}")


# ------------------------------------------------------------------ orchestration
def verify_all(net: Network, spec: Spec, T: int, engines: Sequence[str] = ("bmc", "exhaustive", "reach"),
               timeout_s: float = 60.0, max_states: int = 2_000_000, max_traces: int = 1 << 20,
               k_max: int = 200) -> list[Result]:
    res = []
    for e in engines:
        if e == "bmc":
            res.append(bmc(net, spec, T, timeout_s))
        elif e == "exhaustive":
            res.append(exhaustive(net, spec, T, max_traces=max_traces))
        elif e == "reach":
            res.append(reach(net, spec, max_states=max_states, timeout_s=timeout_s))
        elif e == "kind":
            res.append(kinduction(net, spec, k_max=k_max, timeout_s=timeout_s))
        elif e == "pdr":
            res.append(pdr(net, spec, timeout_s=timeout_s))
        else:
            raise ValueError(f"unknown engine {e}")
    check_consistency(res)
    return res


def check_consistency(results: Sequence[Result]) -> None:
    """Engines must never contradict each other on overlapping scopes."""
    bounded = [r for r in results if r.horizon is not None and r.status in (Status.VERIFIED_BOUNDED, Status.COUNTEREXAMPLE)]
    unb = [r for r in results if r.horizon is None and r.status in (Status.VERIFIED_UNBOUNDED, Status.COUNTEREXAMPLE)]
    for u in unb:
        for v in unb:
            if u.status != v.status:
                raise EngineBug(f"{u.engine}={u.status} but {v.engine}={v.status} (both unbounded)")
            if u.status == Status.COUNTEREXAMPLE and u.violation_time != v.violation_time:
                raise EngineBug(f"earliest violation: {u.engine} t={u.violation_time}, {v.engine} t={v.violation_time}")
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
