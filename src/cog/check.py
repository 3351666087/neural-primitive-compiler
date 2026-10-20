"""Judges for constructed networks (they never see how a network was built).

  differential   random valid traces, network (npc BatchSim) vs reference semantics       [E] statistical
  reach_equiv    explicit product of network state x reference stepper state, all valid
                 frames, breadth-first: equivalence for traces of EVERY length (one size)   [M]
  automorphism   structural check that a coordinate permutation maps the wiring onto itself
                 (equivariance then follows from the equivariance lemma, compositional-semantics.md)
"""

from __future__ import annotations

import itertools
import random
import re
import time
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from npc.network import Network
from npc.simulator import BatchSim, CompiledNet

from .tasks import Task, cname, random_trace, run_reference


@dataclass
class CheckResult:
    ok: bool | None          # None = no conclusion (resource limit)
    method: str
    detail: dict = field(default_factory=dict)
    counterexample: dict | None = None


def _sim(net: Network, task: Task, traces: list[dict], T: int) -> np.ndarray:
    X = np.zeros((len(traces), len(net.inputs), T), dtype=np.int64)
    for b, tr in enumerate(traces):
        for i, ch in enumerate(net.inputs):
            if ch in tr:
                X[b, i, :] = tr[ch]
    sim = BatchSim(net)
    S = sim.run(X)
    return S, sim


def differential(net: Network, task: Task, n: int = 300, T: int = 14, seed: int = 0) -> CheckResult:
    missing = set(task.input_channels()) - set(net.inputs)
    outs = task.output_channels()
    port = dict(net.outputs)
    miss_out = [o for o in outs if o not in port]
    if miss_out:
        return CheckResult(False, "differential", {"missing_outputs": miss_out[:5]})
    rng = random.Random(seed)
    traces = [random_trace(task, T, rng) for _ in range(n)]
    S, sim = _sim(net, task, traces, T)
    names = net.neuron_names
    bad = 0
    first = None
    for b, tr in enumerate(traces):
        ref = run_reference(task, tr, T)
        for o in outs:
            got = S[b, sim.m + names.index(port[o]), :]
            if list(got) != ref[o]:
                bad += 1
                if first is None:
                    t = next(i for i in range(T) if got[i] != ref[o][i])
                    first = {"output": o, "t": t, "trace": {k: v[: t + 1] for k, v in tr.items() if any(v[: t + 1])},
                             "got": int(got[t]), "want": ref[o][t]}
                break
    return CheckResult(bad == 0, "differential", {"traces": n, "T": T, "failing_traces": bad,
                                                   "unused_inputs": sorted(missing)[:5]}, first)


# ------------------------------------------------------------------ incremental reference (for reach)
class RefStepper:
    """Incremental form of run_reference (cross-tested against it). State is hashable."""

    def __init__(self, task: Task):
        self.task = task
        self.H = max(o.lag + (1 if o.kind in ("sel", "match") else 0) for o in task.outputs) + 1
        self.QH = max([o.lag for o in task.outputs if o.kind in ("sel", "match")] or [0]) + 1
        self.qnames = list(task.queries)

    def init(self):
        empty = frozenset()
        return ((empty,) * self.H, ((None,) * len(self.qnames),) * self.QH, (), -1)

    def step(self, st, frame: dict):
        hist, qhist, pending, quiet = st
        S = hist[0]
        new = S
        pend = list(pending)
        for l in self.task.letters:
            if frame.get(l.name, 0):
                if l.cond_delay is None:
                    new = l.act(S, frame)
                else:
                    pend.append((l.cond_delay, l.act(S, frame)))
                    quiet = l.cond_delay
        nxt = []
        for d, val in pend:
            if d == 0:
                new = val
            else:
                nxt.append((d - 1, val))
        # (delays count down: an action registered with delay D fires D steps later)
        qs = tuple(next((c for c in self.task.queries[q].coords if frame.get(cname(q, c), 0)), None) for q in self.qnames)
        hist = (new,) + hist[:-1]
        qhist = (qs,) + qhist[:-1]
        return (hist, qhist, tuple(sorted(nxt, key=repr)), max(-1, quiet - 1) if quiet >= 0 else -1)

    def outputs(self, st) -> dict:
        """Outputs at the current time t, given the state after processing frames up to t."""
        hist, qhist, _, _ = st
        out = {}
        for o in self.task.outputs:
            if o.kind == "img":
                S = hist[o.lag]
                for c in self.task.space.coords:
                    out[cname(o.name, c)] = int(c in S)
            elif o.kind == "any":
                out[o.name] = int(bool(hist[o.lag] & o.region))
            elif o.kind == "sel":
                qi = self.qnames.index(o.query)
                a = qhist[o.lag][qi]
                S = hist[o.lag + 1]
                for b in (o.out_space.coords if o.out_space else ((),)):
                    from .tasks import _join
                    out[cname(o.name, b)] = int(a is not None and _join(a, b, o.axis) in S)
            elif o.kind == "match":
                ia, ib = self.qnames.index(o.query), self.qnames.index(o.query2)
                a, bq = qhist[o.lag][ia], qhist[o.lag][ib]
                S = hist[o.lag + 1]
                v = 0
                if a is not None and bq is not None:
                    va = {p[1] for p in S if p[0] == a[0]}
                    vb = {p[1] for p in S if p[0] == bq[0]}
                    v = int(bool(va & vb))
                out[o.name] = v
        return out


def valid_frames(task: Task) -> list[tuple[dict, bool]]:
    """All valid single-step frames. Returns (frame, is_conditional_letter)."""
    letter_opts = [({}, False)]
    for l in task.letters:
        if l.data:
            sp = task.data[l.data]
            pats = [[(c,)] for c in sp.coords] if sp.kind == "vec" else \
                [list(s) for r in range(len(sp.coords) + 1) for s in itertools.combinations(sp.coords, r)]
            for p in pats:
                f = {l.name: 1}
                for c in p:
                    f[cname(l.data, c[0] if sp.kind == "vec" else c)] = 1
                letter_opts.append((f, l.cond_delay is not None))
        else:
            letter_opts.append(({l.name: 1}, l.cond_delay is not None))
    q_opts = [{}]
    for q, sp in task.queries.items():
        q_opts = [dict(base, **({cname(q, c): 1} if c is not None else {})) for base in q_opts for c in (None,) + sp.coords]
    return [(dict(lf, **qf), cond) for lf, cond in letter_opts for qf in q_opts]


def reach_equiv(net: Network, task: Task, max_states: int = 400_000, timeout_s: float = 300.0) -> CheckResult:
    """Unbounded (all trace lengths) equivalence of network and reference at this size."""
    t0 = time.perf_counter()
    cn = CompiledNet(net)
    ref = RefStepper(task)
    frames = valid_frames(task)
    port = dict(net.outputs)
    outs = task.output_channels()
    idx = {n: i for i, n in enumerate(net.neuron_names)}
    ins = list(net.inputs)
    init = (cn.initial_state(), ref.init())
    parent = {init: None}
    q = deque([init])
    while q:
        st = q.popleft()
        nst, rst = st
        spikes, pots = cn.fire(nst)
        for frame, is_cond in frames:
            if is_cond is False and any(frame.get(l.name, 0) for l in task.letters) and rst[3] >= 0:
                continue  # pacing: no letter while a conditional letter is being processed
            if is_cond and rst[3] >= 0:
                continue
            r2 = ref.step(rst, frame)
            want = ref.outputs(r2)
            for o in outs:
                if spikes[idx[port[o]]] != want[o]:
                    path = [frame]
                    cur = st
                    while parent[cur] is not None:
                        cur, f = parent[cur]
                        path.append(f)
                    path.reverse()
                    tr = {}
                    for t, f in enumerate(path):
                        for k, v in f.items():
                            tr.setdefault(k, [0] * len(path))[t] = v
                    return CheckResult(False, "reach_equiv", {"states": len(parent)},
                                       {"output": o, "t": len(path) - 1, "trace": tr,
                                        "got": spikes[idx[port[o]]], "want": want[o]})
            x = [frame.get(ch, 0) for ch in ins]
            nxt = (cn.advance(nst, spikes, pots, x), r2)
            if nxt not in parent:
                parent[nxt] = (st, frame)
                q.append(nxt)
                if len(parent) > max_states:
                    return CheckResult(None, "reach_equiv", {"states": len(parent), "reason": "max_states"})
        if time.perf_counter() - t0 > timeout_s:
            return CheckResult(None, "reach_equiv", {"states": len(parent), "reason": "timeout"})
    return CheckResult(True, "reach_equiv", {"states": len(parent), "frames": len(frames),
                                             "time_s": round(time.perf_counter() - t0, 2)})


# ------------------------------------------------------------------ equivariance (structural)
def automorphism(net: Network, rename) -> CheckResult:
    """rename: str -> str on signal names (inputs, neurons). Checks it is a bijection on signals that maps
    every synapse to a synapse with the same weight and delay, every neuron to one with identical
    parameters, and inputs to inputs. Output ports are checked by the caller via the same rename."""
    sigs = list(net.inputs) + list(net.neuron_names)
    img = {s: rename(s) for s in sigs}
    if sorted(img.values()) != sorted(sigs):
        return CheckResult(False, "automorphism", {"reason": "rename is not a bijection on signals"})
    if set(img[i] for i in net.inputs) != set(net.inputs):
        return CheckResult(False, "automorphism", {"reason": "inputs not mapped to inputs"})
    params = {n.name: (n.threshold, n.leak, n.bias, n.reset, n.init, n.vmin, n.vmax) for n in net.neurons}
    for n in net.neurons:
        if params[img[n.name]] != params[n.name]:
            return CheckResult(False, "automorphism", {"reason": f"parameters differ at {n.name}"})
    syn = sorted((s.src, s.dst, s.weight, s.delay) for s in net.synapses)
    mapped = sorted((img[s.src], img[s.dst], s.weight, s.delay) for s in net.synapses)
    ok = syn == mapped
    return CheckResult(ok, "automorphism", {"synapses": len(syn)})


def coord_renamer(perm: dict, letter_perm: dict):
    """Build a signal renamer from a coordinate permutation (coord tuple -> coord tuple) and a letter
    renaming. Coordinates appear in names as 'a,b' inside brackets and as '_a_b' suffixes."""
    br = {",".join(map(str, a)): ",".join(map(str, b)) for a, b in perm.items()}
    us = {"_" + "_".join(map(str, a)): "_" + "_".join(map(str, b)) for a, b in perm.items()}

    def rename(s: str) -> str:
        m = re.fullmatch(r"(.*)\[([0-9,]+)(\|(.*))?\]", s)
        if m:
            pre, c, _, l = m.group(1), m.group(2), m.group(3), m.group(4)
            c2 = br.get(c, c)
            if l is not None:
                return f"{pre}[{c2}|{br.get(l, letter_perm.get(l, l))}]"
            return f"{pre}[{c2}]"
        if s in letter_perm:
            return letter_perm[s]
        m = re.fullmatch(r"([A-Za-z]+)((_[0-9]+)+)", s)
        if m and m.group(2) in us:
            return m.group(1) + us[m.group(2)]
        return s
    return rename
