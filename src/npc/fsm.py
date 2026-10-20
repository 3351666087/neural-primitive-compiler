"""Classical baselines: spec -> finite-state machine -> neural network, with no search.

1. ``machine_from_spec``: explores the specification monitor and builds the
   Moore machine that every implementation must realise (output at step t is
   a function of the state *before* step t, because the substrate is strictly
   causal). Outputs may be don't-care (warm-up, violated assumptions).
2. ``minimize``: partition refinement (don't-care treated as its own value, so
   the result is exact but not necessarily the smallest don't-care-exploiting
   machine - that problem is NP-hard).
3. ``latency1_weights``: decides exact realisability (theory.md, Theorem 3):
   a network output can only depend on the newest input frame x(t-1) through
   one shared integer weight vector W, so we need
        O(delta(q, a)) = [alpha(q) + W . a >= theta]   for all reachable q, a.
   If no (W, alpha, theta) exists, *no* network of any size meets the spec.
4. ``classical_network``: one-hot (state, letter) construction (Kleene 1956 /
   Minsky 1967 style, adapted to delays >= 1) that realises any realisable
   functional spec. Cost: 1 + #reachable(state, letter) + #outputs neurons.
"""

from __future__ import annotations

import itertools
import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import z3

from .network import Network, Neuron, Synapse, full_leak
from .spec import Monitor, Spec


class NotFunctional(ValueError):
    pass


class NotCausal(ValueError):
    def __init__(self, msg: str, witness: dict):
        super().__init__(msg)
        self.witness = witness


@dataclass
class Moore:
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    n: int
    q0: int
    delta: dict[tuple[int, tuple[int, ...]], int]  # missing entry: assumption violated, anything goes later
    out: list[tuple[Any, ...]]  # per state, per output: 0, 1 or None (don't care)
    paths: list[tuple] = field(default_factory=list)  # a shortest input path reaching each state

    @property
    def letters(self) -> list[tuple[int, ...]]:
        return list(itertools.product((0, 1), repeat=len(self.inputs)))

    def stats(self) -> dict[str, Any]:
        return {"states": self.n, "state_bits": math.ceil(math.log2(self.n)) if self.n > 1 else 0,
                "transitions": len(self.delta)}


def machine_from_spec(spec: Spec, max_states: int = 200_000) -> Moore:
    fo = spec.functional_outputs()
    if fo is None:
        raise NotFunctional("guarantee is not a conjunction of `out <-> phi` for every output")
    for o, phi in fo.items():
        from .spec import atoms
        if atoms(phi) & set(spec.outputs):
            raise NotFunctional(f"definition of {o} refers to outputs")
    outs = tuple(spec.outputs)
    mons = [Monitor(fo[o]) for o in outs]
    A = Monitor(spec.assume)
    letters = list(itertools.product((0, 1), repeat=len(spec.inputs)))
    strict = spec.assume_mode == "strict"
    init = (tuple(m.init for m in mons), A.init, 0)
    index = {init: 0}
    states = [init]
    paths = [()]
    out: list[tuple] = []
    delta: dict = {}
    queue = deque([0])
    pending_out: dict[int, tuple] = {}
    while queue:
        qi = queue.popleft()
        ms, ast, w = states[qi]
        vals_per_out: list[dict] = [dict() for _ in outs]
        for a in letters:
            val = dict(zip(spec.inputs, a))
            ast2, aok = A.step(ast, val)
            new_ms = []
            for j, m in enumerate(mons):
                st2, v = m.step(ms[j], val)
                new_ms.append(st2)
                constrained = w >= spec.warmup and (aok or strict)
                if constrained:
                    vals_per_out[j][a] = bool(v)
            if not aok:
                continue
            nxt = (tuple(new_ms), ast2, min(w + 1, spec.warmup))
            if nxt not in index:
                if len(states) >= max_states:
                    raise MemoryError(f"machine exceeds {max_states} states")
                index[nxt] = len(states)
                states.append(nxt)
                paths.append(paths[qi] + (a,))
                queue.append(index[nxt])
            delta[(qi, a)] = index[nxt]
        o_vals = []
        for j, o in enumerate(outs):
            vs = set(vals_per_out[j].values())
            if len(vs) > 1:
                a1 = next(a for a, v in vals_per_out[j].items() if v)
                a0 = next(a for a, v in vals_per_out[j].items() if not v)
                raise NotCausal(
                    f"output {o} at a step must react to the input of that same step; every network output "
                    f"is computed from strictly earlier inputs (all delays >= 1)",
                    {"history": [list(p) for p in paths[qi]], "letter_true": a1, "letter_false": a0})
            o_vals.append(int(vs.pop()) if vs else None)
        pending_out[qi] = tuple(o_vals)
    out = [pending_out[i] for i in range(len(states))]
    return Moore(tuple(spec.inputs), outs, len(states), 0, delta, out, paths)


def minimize(M: Moore) -> Moore:
    letters = M.letters
    block = {q: M.out[q] for q in range(M.n)}
    while True:
        sig = {q: (block[q], tuple(block.get(M.delta.get((q, a)), "_") if (q, a) in M.delta else "_" for a in letters))
               for q in range(M.n)}
        keys = {}
        new_block = {}
        for q in range(M.n):
            new_block[q] = keys.setdefault(sig[q], len(keys))
        if len(set(new_block.values())) == len(set(block.values())):
            block = new_block
            break
        block = new_block
    reps: dict[int, int] = {}
    for q in range(M.n):
        reps.setdefault(block[q], q)
    order = sorted(reps, key=lambda b: (b != block[M.q0], reps[b]))
    renum = {b: i for i, b in enumerate(order)}
    delta = {}
    for (q, a), r in M.delta.items():
        delta[(renum[block[q]], a)] = renum[block[r]]
    out = [M.out[reps[b]] for b in order]
    paths = [M.paths[reps[b]] for b in order]
    return Moore(M.inputs, M.outputs, len(order), renum[block[M.q0]], delta, out, paths)


@dataclass
class Latency1:
    realizable: bool
    W: dict[str, list[int]] = field(default_factory=dict)
    alpha: dict[str, list[int]] = field(default_factory=dict)
    theta: dict[str, int] = field(default_factory=dict)
    witness: dict | None = None


def latency1_weights(M: Moore, bound: int = 64) -> Latency1:
    """Decide whether some (W, alpha, theta) realises every output (Theorem 3)."""
    res = Latency1(True)
    letters = M.letters
    for j, o in enumerate(M.outputs):
        s = z3.Solver()
        W = [z3.Int(f"W{k}") for k in range(len(M.inputs))]
        al = [z3.Int(f"al{q}") for q in range(M.n)]
        th = z3.Int("theta")
        s.add(th >= 1)
        for v in (*W, *al, th):
            s.add(v >= -bound, v <= bound)
        rows = []
        for q in range(M.n):
            for a in letters:
                if (q, a) not in M.delta:
                    continue
                target = M.out[M.delta[(q, a)]][j]
                if target is None:
                    continue
                lhs = al[q] + z3.Sum([W[k] * a[k] for k in range(len(a))]) if a else al[q]
                c = (lhs >= th) if target else (lhs < th)
                s.assert_and_track(c, f"q{q}_a{''.join(map(str, a))}")
                rows.append((q, a, target))
        r = s.check()
        if r == z3.sat:
            m = s.model()
            res.W[o] = [m.eval(w, model_completion=True).as_long() for w in W]
            res.alpha[o] = [m.eval(x, model_completion=True).as_long() for x in al]
            res.theta[o] = m.eval(th, model_completion=True).as_long()
        else:
            res.realizable = False
            core = [str(c) for c in s.unsat_core()]
            wit = {"output": o, "conflicting_constraints": core, "histories": {}}
            for c in core:
                q = int(c.split("_")[0][1:])
                a = c.split("_a")[1]
                tgt = M.out[M.delta[(q, tuple(int(ch) for ch in a))]][j] if a or not M.inputs else None
                wit["histories"][c] = {"history": [list(p) for p in M.paths[q]], "next_letter": a, "required_output": tgt}
            res.witness = wit
            return res
    return res


def classical_network(spec: Spec, name: str | None = None) -> tuple[Network | None, dict[str, Any]]:
    """Compile a functional spec directly. Returns (network or None, info)."""
    info: dict[str, Any] = {}
    try:
        M = machine_from_spec(spec)
    except NotCausal as e:
        info.update(status="UNREALIZABLE", reason=str(e), witness=e.witness)
        return None, info
    except NotFunctional as e:
        info.update(status="NOT_APPLICABLE", reason=str(e))
        return None, info
    Mm = minimize(M)
    info["machine_states"] = M.n
    info["minimal_states"] = Mm.n
    info["minimal_state_bits"] = Mm.stats()["state_bits"]
    L1 = latency1_weights(Mm)
    if not L1.realizable:
        info.update(status="UNREALIZABLE",
                    reason="no shared weight vector W for the newest input frame (Theorem 3): no network of any size",
                    witness=L1.witness)
        return None, info
    m = len(spec.inputs)
    letters = Mm.letters
    pairs = sorted(Mm.delta)
    pname = {pa: f"N{pa[0]}_{''.join(map(str, pa[1]))}" for pa in pairs}
    neurons = [Neuron("S", threshold=1, leak=1, init=1, vmax=1)]
    syns = []
    for (q, a) in pairs:
        nm = pname[(q, a)]
        neurons.append(Neuron(nm, threshold=sum(a) + 1, leak=full_leak(0, m + 1), vmax=m + 1))
        for k, x in enumerate(spec.inputs):
            syns.append(Synapse(x, nm, 1 if a[k] else -1, 1))
        if q == Mm.q0:
            syns.append(Synapse("S", nm, 1, 1))
        for (p, b) in pairs:
            if Mm.delta[(p, b)] == q:
                syns.append(Synapse(pname[(p, b)], nm, 1, 1))
    outs = []
    for j, o in enumerate(spec.outputs):
        W, al, th = L1.W[o], L1.alpha[o], L1.theta[o]
        ynm = f"Y_{o}"
        ys = []
        if al[Mm.q0] != 0:
            ys.append(Synapse("S", ynm, al[Mm.q0], 1))
        for (p, b) in pairs:
            w = al[Mm.delta[(p, b)]]
            if w != 0:
                ys.append(Synapse(pname[(p, b)], ynm, w, 1))
        for k, x in enumerate(spec.inputs):
            if W[k] != 0:
                ys.append(Synapse(x, ynm, W[k], 1))
        lo = min(0, min(al) + sum(min(0, w) for w in W))
        hi = max(th, max(al) + sum(max(0, w) for w in W))
        o0 = Mm.out[Mm.q0][j]
        neurons.append(Neuron(ynm, threshold=th, leak=full_leak(lo, hi), init=th if o0 else 0, vmin=lo, vmax=hi))
        syns += ys
        outs.append((o, ynm))
    net = Network(name or f"classical_{spec.name}", tuple(spec.inputs), tuple(neurons), tuple(syns), tuple(outs),
                  max_delay=1).validate()
    info.update(status="COMPILED", neurons=len(neurons), W=L1.W, theta=L1.theta)
    return net, info
