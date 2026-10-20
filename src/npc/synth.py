"""Synthesis: counterexample-guided search for networks that meet a spec.

No gradients anywhere. Four searchers, all ending in the same independent
verifier (verify.py):

  cegis            parametric templates (integer holes) solved with Z3; each
                   verifier counterexample becomes a new constraint (CEGIS,
                   Solar-Lezama et al. 2006). UNSAT on the example set is a
                   *proof* that no assignment of the holes works.
  enumerate_params same templates, plain enumeration of hole values, filtered
                   on the example set (baseline without a solver).
  compose_dag      bottom-up enumeration of primitive compositions with
                   observational-equivalence pruning on the example set.
  compose_cyclic   bounded enumeration of compositions with feedback.
  sketch           finite choice holes (e.g. proposed by an LLM) enumerated,
                   integer holes solved by cegis.

Statuses: SOLVED (unbounded proof), SOLVED_BOUNDED (only BMC to horizon T
succeeded; the unbounded check hit a resource limit), UNREALIZABLE (proof that
the searched space has no solution), EXHAUSTED (finite space searched, nothing
found - also a proof for that space), TIMEOUT, UNKNOWN.
"""

from __future__ import annotations

import itertools
import random
import time
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import z3

from .dsl import Choice, DSLError, InstDecl, Library, NetworkDef, flatten
from .network import Network, Neuron, Synapse, full_leak
from .simulator import BatchSim
from .smt import Hole, encode_formula, hole_vars, template_holes, unroll, violation_terms
from .spec import Spec, evaluate
from .verify import Result, Status, bmc, reach

SOLVED, SOLVED_BOUNDED, UNREALIZABLE, EXHAUSTED, TIMEOUT, UNKNOWN = (
    "SOLVED", "SOLVED_BOUNDED", "UNREALIZABLE", "EXHAUSTED", "TIMEOUT", "UNKNOWN")


@dataclass
class SynthResult:
    status: str
    method: str
    network: Network | None = None
    iterations: int = 0
    candidates: int = 0
    examples: list[dict[str, list[int]]] = field(default_factory=list)
    synth_time_s: float = 0.0
    verify_time_s: float = 0.0
    total_time_s: float = 0.0
    verification: list[Result] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)
    log: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "method": self.method,
            "network": self.network.to_dict() if self.network else None,
            "stats": self.network.stats() if self.network else None,
            "iterations": self.iterations,
            "candidates": self.candidates,
            "n_examples": len(self.examples),
            "examples": self.examples,
            "synth_time_s": round(self.synth_time_s, 4),
            "verify_time_s": round(self.verify_time_s, 4),
            "total_time_s": round(self.total_time_s, 4),
            "verification": [r.to_dict() for r in self.verification],
            "detail": self.detail,
            "log": self.log,
        }


# ------------------------------------------------------------------- templates
def fully_connected(spec: Spec, n: int, in_delays: Sequence[int] = (1, 2, 3), rec_delays: Sequence[int] = (1,),
                    wmax: int = 3, vmin: int = 0, vmax: int = 7, bias: tuple[int, int] = (0, 1),
                    leak: tuple[int, int] | None = None, name: str | None = None) -> Network:
    """n neurons; every (source, neuron, delay) gets a weight hole in [-wmax, wmax] (0 = absent).

    The first len(spec.outputs) neurons drive the outputs. Thresholds in [1, vmax], leak in
    [0, full], bias in the given range, reset = init = 0.
    """
    ins = tuple(spec.inputs)
    names = [f"n{i}" for i in range(n)]
    lk = leak or (0, full_leak(vmin, vmax))
    neurons = tuple(Neuron(nm, Hole(f"{nm}.threshold", 1, vmax), Hole(f"{nm}.leak", *lk),
                           Hole(f"{nm}.bias", *bias) if bias[0] != bias[1] else bias[0], 0, 0, vmin, vmax)
                    for nm in names)
    syns = []
    for dst in names:
        for src in ins:
            for d in in_delays:
                syns.append(Synapse(src, dst, Hole(f"w[{src}->{dst}@{d}]", -wmax, wmax), d))
        for src in names:
            for d in rec_delays:
                syns.append(Synapse(src, dst, Hole(f"w[{src}->{dst}@{d}]", -wmax, wmax), d))
    outs = tuple((o, names[i]) for i, o in enumerate(spec.outputs))
    md = max([*in_delays, *rec_delays])
    return Network(name or f"fc{n}", ins, neurons, tuple(syns), outs, max_delay=md)


def instantiate(template: Network, values: Mapping[str, int]) -> Network:
    def v(x: Any) -> Any:
        return values[x.name] if isinstance(x, Hole) else x

    neurons = tuple(Neuron(n.name, v(n.threshold), v(n.leak), v(n.bias), v(n.reset), v(n.init), v(n.vmin), v(n.vmax))
                    for n in template.neurons)
    syns = tuple(Synapse(s.src, s.dst, v(s.weight), s.delay) for s in template.synapses if v(s.weight) != 0)
    # drop neurons that cannot influence any output (keeps reported architecture honest and small)
    needed = {n for _, n in template.outputs}
    changed = True
    while changed:
        changed = False
        for s in syns:
            if s.dst in needed and s.src not in needed and s.src in {x.name for x in neurons}:
                needed.add(s.src)
                changed = True
    neurons = tuple(n for n in neurons if n.name in needed)
    syns = tuple(s for s in syns if s.dst in needed)
    return Network(template.name, template.inputs, neurons, syns, template.outputs, template.max_delay,
                   meta=dict(template.meta)).validate()


# ----------------------------------------------------------------- examples
def _random_examples(spec: Spec, T: int, k: int, rng: random.Random) -> list[dict[str, list[int]]]:
    out = []
    tries = 0
    while len(out) < k and tries < 50 * max(1, k):
        tries += 1
        tr = {x: [rng.randint(0, 1) for _ in range(T)] for x in spec.inputs}
        if spec.assume.op != "const":
            env = {x: np.array([v]) for x, v in tr.items()}
            if not evaluate(spec.assume, env)[0].all():
                continue
        out.append(tr)
    return out


def _example_constraint(template: Network, spec: Spec, ex: Mapping[str, Sequence[int]], hv, tag: str) -> list:
    L = len(next(iter(ex.values()))) if ex else 1
    cons: list = []
    spikes = unroll(template, L, {k: [bool(b) for b in ex[k]] for k in template.inputs}, cons, prefix=tag, hvars=hv)
    env: dict[str, Any] = {k: [bool(b) for b in ex[k]] for k in template.inputs}
    for p, n in template.outputs:
        env[p] = spikes[n]
    viol = violation_terms(spec, env, L)
    if viol:
        cons.append(z3.Not(z3.Or(*[v for _, v in viol])))
    return cons


# ---------------------------------------------------------------------- CEGIS
def final_check(net: Network, spec: Spec, T: int, deadline: float, max_states: int) -> tuple[str, list[Result], dict | None]:
    """BMC to horizon T, then unbounded reachability. Returns (status, results, counterexample)."""
    res = []
    b = bmc(net, spec, T, timeout_s=max(1.0, deadline - time.perf_counter()))
    res.append(b)
    if b.status == Status.COUNTEREXAMPLE:
        return "CEX", res, b.counterexample
    if b.status != Status.VERIFIED_BOUNDED:
        return TIMEOUT, res, None
    r = reach(net, spec, max_states=max_states, timeout_s=max(1.0, deadline - time.perf_counter()))
    res.append(r)
    if r.status == Status.COUNTEREXAMPLE:
        return "CEX", res, r.counterexample
    if r.status == Status.VERIFIED_UNBOUNDED:
        return SOLVED, res, None
    return SOLVED_BOUNDED, res, None


def cegis(template: Network, spec: Spec, T: int = 8, timeout_s: float = 60.0, n_random: int = 2, seed: int = 0,
          max_iters: int = 200, max_states: int = 500_000, extra_constraints: Iterable = (),
          examples: Sequence[Mapping[str, Sequence[int]]] = (), unbounded: bool = True) -> SynthResult:
    t_start = time.perf_counter()
    deadline = t_start + timeout_s
    rng = random.Random(seed)
    holes = template_holes(template)
    hv, dom = hole_vars(holes)
    solver = z3.Solver()
    solver.add(*dom)
    solver.add(*extra_constraints)
    E = [dict(e) for e in examples] or [{x: [0] * T for x in spec.inputs}]
    if not examples:
        E += _random_examples(spec, T, n_random, rng)
    for i, e in enumerate(E):
        solver.add(*_example_constraint(template, spec, e, hv, f"e{i}_"))
    res = SynthResult(UNKNOWN, "cegis", detail={"holes": len(holes), "template": template.name})
    t_syn = t_ver = 0.0
    for it in range(1, max_iters + 1):
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            res.status = TIMEOUT
            break
        solver.set("timeout", max(1, int(remaining * 1000)))
        t0 = time.perf_counter()
        r = solver.check()
        t_syn += time.perf_counter() - t0
        res.iterations = it
        if r == z3.unsat:
            res.status = UNREALIZABLE
            res.log.append(f"iter {it}: UNSAT on {len(E)} examples -> no hole assignment in this template works")
            break
        if r == z3.unknown:
            reason = solver.reason_unknown()
            res.status = TIMEOUT if ("timeout" in reason or "canceled" in reason) else UNKNOWN
            res.log.append(f"iter {it}: solver unknown ({reason})")
            break
        mdl = solver.model()
        values = {h: mdl.eval(hv[h], model_completion=True).as_long() for h in holes}
        cand = instantiate(template, values)
        t0 = time.perf_counter()
        if unbounded:
            status, vres, cex = final_check(cand, spec, T, deadline, max_states)
        else:
            b = bmc(cand, spec, T, timeout_s=max(1.0, deadline - time.perf_counter()))
            vres = [b]
            status, cex = ("CEX", b.counterexample) if b.status == Status.COUNTEREXAMPLE else \
                ((SOLVED_BOUNDED, None) if b.verified else (TIMEOUT, None))
        t_ver += time.perf_counter() - t0
        if status == "CEX":
            E.append(cex)
            L = len(next(iter(cex.values())))
            res.log.append(f"iter {it}: candidate refuted by {vres[-1].engine} (len {L}); added counterexample")
            solver.add(*_example_constraint(template, spec, cex, hv, f"e{len(E) - 1}_"))
            continue
        res.status = status
        res.network = cand
        res.verification = vres
        res.log.append(f"iter {it}: candidate accepted ({status})")
        break
    else:
        res.status = UNKNOWN
        res.log.append("iteration limit")
    res.examples = E
    res.synth_time_s, res.verify_time_s = t_syn, t_ver
    res.total_time_s = time.perf_counter() - t_start
    return res


def minimize_synapses(template: Network, spec: Spec, first: SynthResult, T: int = 8, timeout_s: float = 60.0,
                      **kw) -> SynthResult:
    """Repeatedly ask CEGIS for a solution with strictly fewer synapses. UNSAT proves minimality
    (for this template and parameter ranges)."""
    if first.network is None:
        return first
    best = first
    t0 = time.perf_counter()
    holes = template_holes(template)
    hv, _ = hole_vars(holes)
    weight_holes = [h for h in holes if h.startswith("w[")]
    proven = False
    while time.perf_counter() - t0 < timeout_s:
        k = len(best.network.synapses)
        bound = z3.Sum([z3.If(hv[h] != 0, 1, 0) for h in weight_holes]) < k
        r = cegis(template, spec, T, timeout_s=timeout_s - (time.perf_counter() - t0), extra_constraints=[bound],
                  examples=best.examples, **kw)
        if r.status in (SOLVED, SOLVED_BOUNDED) and len(r.network.synapses) < k:
            r.method = "cegis+min"
            best = r
            continue
        proven = r.status == UNREALIZABLE
        break
    best.detail["synapse_minimality_proven"] = proven
    best.detail["minimization_time_s"] = round(time.perf_counter() - t0, 3)
    return best


def search_neurons(spec: Spec, n_max: int = 4, T: int = 8, timeout_s: float = 120.0, **template_kw) -> tuple[SynthResult, list[dict]]:
    """Grow the fully-connected template until CEGIS succeeds. UNREALIZABLE at n means *no*
    n-neuron network within the template's parameter ranges meets the spec."""
    t0 = time.perf_counter()
    trail = []
    last = SynthResult(UNKNOWN, "cegis")
    for n in range(1, n_max + 1):
        remaining = timeout_s - (time.perf_counter() - t0)
        if remaining <= 0:
            trail.append({"n": n, "status": TIMEOUT})
            break
        tpl = fully_connected(spec, n, **template_kw)
        r = cegis(tpl, spec, T, timeout_s=remaining)
        trail.append({"n": n, "status": r.status, "iterations": r.iterations, "time_s": round(r.total_time_s, 3),
                      "holes": r.detail.get("holes")})
        last = r
        if r.status in (SOLVED, SOLVED_BOUNDED, TIMEOUT, UNKNOWN):
            break
    last.detail["neuron_search"] = trail
    last.total_time_s = time.perf_counter() - t0
    return last, trail


# ----------------------------------------------------- enumeration baseline
def _passes(net: Network, spec: Spec, E: Sequence[Mapping[str, Sequence[int]]]) -> bool:
    for e in E:  # examples may differ in length
        L = len(next(iter(e.values())))
        X = np.array([[e[k] for k in net.inputs]])
        sim = BatchSim(net)
        S = sim.run(X.reshape(1, len(net.inputs), L)) if net.inputs else sim.run(np.zeros((1, 0, L), dtype=np.int64))
        env = {k: X[:, i, :] for i, k in enumerate(net.inputs)}
        for p, n in net.outputs:
            env[p] = S[:, sim.m + net.neuron_names.index(n), :]
        if spec.violation_mask(env).any():
            return False
    return True


def enumerate_params(template: Network, spec: Spec, T: int = 8, timeout_s: float = 60.0, n_random: int = 2,
                     seed: int = 0, max_states: int = 500_000) -> SynthResult:
    """Brute-force baseline: try every hole assignment in lexicographic order."""
    t_start = time.perf_counter()
    deadline = t_start + timeout_s
    holes = template_holes(template)
    names = sorted(holes)
    space = 1
    for h in names:
        space *= holes[h].hi - holes[h].lo + 1
    rng = random.Random(seed)
    E = [{x: [0] * T for x in spec.inputs}] + _random_examples(spec, T, n_random, rng)
    res = SynthResult(UNKNOWN, "enumerate", detail={"holes": len(holes), "space": space})
    t_ver = 0.0
    for vals in itertools.product(*[range(holes[h].lo, holes[h].hi + 1) for h in names]):
        res.candidates += 1
        if res.candidates % 512 == 0 and time.perf_counter() > deadline:
            res.status = TIMEOUT
            break
        try:
            cand = instantiate(template, dict(zip(names, vals)))
        except Exception:
            continue
        if not _passes(cand, spec, E):
            continue
        t0 = time.perf_counter()
        status, vres, cex = final_check(cand, spec, T, deadline, max_states)
        t_ver += time.perf_counter() - t0
        res.iterations += 1
        if status == "CEX":
            E.append(cex)
            continue
        res.status, res.network, res.verification = status, cand, vres
        break
    else:
        res.status = EXHAUSTED
    res.examples = E
    res.verify_time_s = t_ver
    res.total_time_s = time.perf_counter() - t_start
    res.synth_time_s = res.total_time_s - t_ver
    return res


# ------------------------------------------------------- primitive compositions
DEFAULT_GRID: dict[str, list[dict[str, int]]] = {
    "relay": [{"d": 1}, {"d": 2}, {"d": 3}],
    "and2": [{}], "or2": [{}], "gate": [{}], "inv": [{}], "rise": [{}],
    "window": [{"k": k, "w": w} for w in (2, 3) for k in range(1, w + 1)],
    "compare": [{"w": 1, "k": 1}, {"w": 2, "k": 1}, {"w": 2, "k": 2}],
    "counter": [{"k": k} for k in (2, 3, 4)],
    "latch": [{}], "latch_lite": [{}],
    "clock": [{"p": 2}, {"p": 3}],
    "pairdet": [{}],
}


@dataclass(frozen=True)
class Expr:
    """A DAG node: an input name, the silent signal, or a primitive applied to child expressions."""
    kind: str  # "input" | "silent" | "prim"
    name: str = ""
    args: tuple = ()
    children: tuple = ()

    def size(self) -> int:
        return (1 if self.kind == "prim" else 0) + sum(c.size() for c in self.children)

    def show(self) -> str:
        if self.kind == "input":
            return self.name
        if self.kind == "silent":
            return "_"
        a = ",".join(f"{k}={v}" for k, v in self.args)
        return f"{self.name}({a})[" + ", ".join(c.show() for c in self.children) + "]"


def expr_to_networkdef(lib: Library, e: Expr, spec: Spec, max_delay: int = 4) -> NetworkDef:
    nd = NetworkDef(f"synth_{spec.name}", max_delay=max_delay, inputs=list(spec.inputs))
    memo: dict[Expr, str] = {}

    def go(x: Expr) -> str:
        if x.kind == "input":
            return x.name
        if x.kind == "silent":
            return "_"
        if x in memo:
            return memo[x]
        pd = lib.primitives[x.name]
        refs = [go(c) for c in x.children]
        iname = f"i{len(nd.instances)}"
        nd.instances.append(InstDecl(iname, x.name, dict(x.args), dict(zip(pd.ports, refs))))
        out = f"{iname}.{pd.outputs[0][0]}"
        memo[x] = out
        return out

    nd.outputs.append((spec.outputs[0], go(e)))
    return nd


def networkdef_text(nd: NetworkDef) -> str:
    lines = [f"network {nd.name} {{", f"  maxdelay {nd.max_delay}", f"  inputs {', '.join(nd.inputs)}"]
    for i in nd.instances:
        a = ", ".join(f"{k}={v}" for k, v in i.args.items())
        b = " ".join(f"{k}={v}" for k, v in i.bindings.items())
        lines.append(f"  inst {i.name} = {i.prim}({a}) {b}")
    for o, r in nd.outputs:
        lines.append(f"  output {o} = {r}")
    lines.append("}")
    return "\n".join(lines)


class _PrimRunner:
    """Simulates a primitive variant on a batch of input signals (all through the neural substrate)."""

    def __init__(self, lib: Library, grid: Mapping[str, list[dict[str, int]]]):
        self.variants = []
        for prim, arglist in grid.items():
            if prim not in lib.primitives:
                continue
            pd = lib.primitives[prim]
            if len(pd.outputs) != 1:
                continue
            for args in arglist:
                net, _ = pd.instantiate(args)
                self.variants.append((prim, tuple(sorted(args.items())), len(pd.ports), BatchSim(net)))

    @staticmethod
    def run(sim: BatchSim, children: Sequence[np.ndarray], B: int, L: int) -> np.ndarray:
        X = np.stack(children, axis=1) if children else np.zeros((B, 0, L), dtype=np.int64)
        S = sim.run(X)
        return S[:, sim.m + sim.out_idx[0], :]


def _example_batch(spec: Spec, E: Sequence[Mapping[str, Sequence[int]]]) -> tuple[dict[str, np.ndarray], int, int]:
    L = max(len(next(iter(e.values()))) for e in E)
    B = len(E)
    env = {}
    for k in spec.inputs:
        arr = np.zeros((B, L), dtype=np.int64)
        for b, e in enumerate(E):
            arr[b, : len(e[k])] = e[k]
        env[k] = arr
    return env, B, L


def _spec_ok_on(spec: Spec, env: dict[str, np.ndarray], y: np.ndarray, lengths: np.ndarray) -> bool:
    env2 = dict(env)
    env2[spec.outputs[0]] = y
    mask = spec.violation_mask(env2)
    T = mask.shape[1]
    mask &= np.arange(T)[None, :] < lengths[:, None]  # padded steps are not part of the example
    return not mask.any()


def compose_dag(lib: Library, spec: Spec, T: int = 8, max_size: int = 4, timeout_s: float = 60.0,
                grid: Mapping[str, list[dict[str, int]]] | None = None, n_random: int = 4, seed: int = 0,
                max_states: int = 500_000, max_delay: int = 4) -> SynthResult:
    if len(spec.outputs) != 1:
        raise ValueError("compose_dag handles single-output specs")
    t_start = time.perf_counter()
    deadline = t_start + timeout_s
    runner = _PrimRunner(lib, grid or DEFAULT_GRID)
    rng = random.Random(seed)
    E = [{x: [0] * T for x in spec.inputs}] + _random_examples(spec, T, n_random, rng)
    res = SynthResult(UNKNOWN, "compose_dag", detail={"variants": len(runner.variants), "max_size": max_size})
    t_ver = 0.0
    restarts = 0
    while True:
        env, B, L = _example_batch(spec, E)
        lengths = np.array([len(next(iter(e.values()))) for e in E])
        pool: dict[int, list[tuple[Expr, np.ndarray]]] = {0: []}
        seen: set[bytes] = set()
        checked: set[bytes] = set()

        def add(size: int, e: Expr, sig: np.ndarray) -> bool:
            key = sig.astype(np.int8).tobytes()
            if key in seen:
                return False
            seen.add(key)
            pool.setdefault(size, []).append((e, sig))
            return True

        add(0, Expr("silent"), np.zeros((B, L), dtype=np.int64))
        for x in spec.inputs:
            add(0, Expr("input", x), env[x])
        found = None
        timed_out = False
        for size in range(1, max_size + 1):
            for prim, args, arity, sim in runner.variants:
                child_sizes = [c for c in itertools.product(range(size), repeat=arity) if sum(c) == size - 1]
                for cs in child_sizes:
                    for kids in itertools.product(*[pool.get(c, []) for c in cs]):
                        res.candidates += 1
                        if res.candidates % 256 == 0 and time.perf_counter() > deadline:
                            timed_out = True
                            break
                        if arity and all(k[0].kind == "silent" for k in kids):
                            continue
                        sig = _PrimRunner.run(sim, [k[1] for k in kids], B, L)
                        e = Expr("prim", prim, args, tuple(k[0] for k in kids))
                        key = sig.astype(np.int8).tobytes()
                        add(size, e, sig)
                        # Observational equivalence prunes the pool, but a signal that first appeared as an
                        # input or as the silent signal was never checked as an output: check it once here.
                        if key not in checked and _spec_ok_on(spec, env, sig, lengths):
                            checked.add(key)
                            nd = expr_to_networkdef(lib, e, spec, max_delay)
                            net = flatten(lib, nd).network
                            t0 = time.perf_counter()
                            status, vres, cex = final_check(net, spec, T, deadline, max_states)
                            t_ver += time.perf_counter() - t0
                            res.iterations += 1
                            if status == "CEX":
                                E.append(cex)
                                found = "restart"
                            elif status in (SOLVED, SOLVED_BOUNDED):
                                found = (status, net, vres, nd, e)
                            else:
                                timed_out = True
                            break
                    if found or timed_out:
                        break
                if found or timed_out:
                    break
            if found or timed_out:
                break
        if found == "restart":
            restarts += 1
            continue
        if found:
            res.status, res.network, res.verification = found[0], found[1], found[2]
            res.detail["program"] = networkdef_text(found[3])
            res.detail["expr"] = found[4].show()
        else:
            res.status = TIMEOUT if timed_out else EXHAUSTED
        break
    res.detail["restarts"] = restarts
    res.examples = E
    res.verify_time_s = t_ver
    res.total_time_s = time.perf_counter() - t_start
    res.synth_time_s = res.total_time_s - t_ver
    return res


def _eval_network_on(net: Network, spec: Spec, E) -> bool:
    return _passes(net, spec, E)


def compose_cyclic(lib: Library, spec: Spec, k: int = 2, T: int = 8, timeout_s: float = 60.0,
                   grid: Mapping[str, list[dict[str, int]]] | None = None, n_random: int = 4, seed: int = 0,
                   max_states: int = 500_000, max_delay: int = 4) -> SynthResult:
    """Exactly k instances, ports may read inputs, any instance output (cycles allowed) or nothing.
    Instance 0 drives the output. Symmetry breaking: variants of instances 1..k-1 non-decreasing."""
    t_start = time.perf_counter()
    deadline = t_start + timeout_s
    runner = _PrimRunner(lib, grid or DEFAULT_GRID)
    variants = [(p, a, ar) for p, a, ar, _ in runner.variants]
    rng = random.Random(seed)
    E = [{x: [0] * T for x in spec.inputs}] + _random_examples(spec, T, n_random, rng)
    res = SynthResult(UNKNOWN, "compose_cyclic", detail={"k": k, "variants": len(variants)})
    t_ver = 0.0
    srcs = list(spec.inputs) + [f"i{j}.out" for j in range(k)] + ["_"]
    timed_out = False
    found = None
    for v0 in range(len(variants)):
        for rest in itertools.combinations_with_replacement(range(len(variants)), k - 1):
            combo = (v0, *rest)
            ports = []
            for j, vi in enumerate(combo):
                pd = lib.primitives[variants[vi][0]]
                ports += [(j, p) for p in pd.ports]
            for binding in itertools.product(srcs, repeat=len(ports)):
                res.candidates += 1
                if res.candidates % 256 == 0 and time.perf_counter() > deadline:
                    timed_out = True
                    break
                used = {int(b[1:].split(".")[0]) for b in binding if b.startswith("i")}
                if any(j not in used for j in range(1, k)):
                    continue  # every non-output instance must be read by someone
                nd = NetworkDef(f"synth_{spec.name}", max_delay=max_delay, inputs=list(spec.inputs))
                for j, vi in enumerate(combo):
                    prim, args, _ = variants[vi]
                    pd = lib.primitives[prim]
                    b = {p: binding[ports.index((j, p))] for p in pd.ports}
                    nd.instances.append(InstDecl(f"i{j}", prim, dict(args), b))
                nd.outputs.append((spec.outputs[0], "i0.out"))
                try:
                    net = flatten(lib, nd).network
                except DSLError:
                    continue
                if not _eval_network_on(net, spec, E):
                    continue
                t0 = time.perf_counter()
                status, vres, cex = final_check(net, spec, T, deadline, max_states)
                t_ver += time.perf_counter() - t0
                res.iterations += 1
                if status == "CEX":
                    E.append(cex)
                    continue
                if status in (SOLVED, SOLVED_BOUNDED):
                    found = (status, net, vres, nd)
                    break
                timed_out = True
                break
            if found or timed_out:
                break
        if found or timed_out:
            break
    if found:
        res.status, res.network, res.verification = found[0], found[1], found[2]
        res.detail["program"] = networkdef_text(found[3])
    else:
        res.status = TIMEOUT if timed_out else EXHAUSTED
    res.examples = E
    res.verify_time_s = t_ver
    res.total_time_s = time.perf_counter() - t_start
    res.synth_time_s = res.total_time_s - t_ver
    return res


# ------------------------------------------------------------------- sketches
def sketch(lib: Library, nd: NetworkDef, spec: Spec, T: int = 8, timeout_s: float = 60.0,
           max_states: int = 500_000, n_random: int = 2, seed: int = 0) -> SynthResult:
    """Enumerate choice holes; solve integer holes with CEGIS. Returns the first fully verified network."""
    t_start = time.perf_counter()
    deadline = t_start + timeout_s
    choices = nd.choices()
    rng = random.Random(seed)
    E = [{x: [0] * T for x in spec.inputs}] + _random_examples(spec, T, n_random, rng)
    res = SynthResult(UNKNOWN, "sketch", detail={"choice_holes": len(choices),
                                                 "choice_space": int(np.prod([len(c.options) for c in choices])) if choices else 1})
    t_ver = 0.0
    attempts = []
    timed_out = False
    for combo in itertools.product(*[c.options for c in choices]):
        if time.perf_counter() > deadline:
            timed_out = True
            break
        assign = {c.name: v for c, v in zip(choices, combo)}
        res.candidates += 1
        try:
            flat = flatten(lib, nd, assign, allow_holes=True)
        except DSLError as e:
            attempts.append({"assignment": assign, "status": "ILLEGAL", "why": str(e)})
            continue
        net = flat.network
        if template_holes(net):
            r = cegis(net, spec, T, timeout_s=max(1.0, deadline - time.perf_counter()), max_states=max_states,
                      examples=E)
            res.iterations += r.iterations
            attempts.append({"assignment": assign, "status": r.status, "iterations": r.iterations})
            E = r.examples
            if r.status in (SOLVED, SOLVED_BOUNDED):
                res.status, res.network, res.verification = r.status, r.network, r.verification
                res.detail["assignment"] = assign
                break
            if r.status == TIMEOUT:
                timed_out = True
                break
            continue
        net.validate()
        if not _passes(net, spec, E):
            attempts.append({"assignment": assign, "status": "REJECTED_BY_EXAMPLES"})
            continue
        t0 = time.perf_counter()
        status, vres, cex = final_check(net, spec, T, deadline, max_states)
        t_ver += time.perf_counter() - t0
        res.iterations += 1
        if status == "CEX":
            E.append(cex)
            attempts.append({"assignment": assign, "status": "COUNTEREXAMPLE", "counterexample": cex})
            continue
        attempts.append({"assignment": assign, "status": status})
        if status in (SOLVED, SOLVED_BOUNDED):
            res.status, res.network, res.verification = status, net, vres
            res.detail["assignment"] = assign
            break
        timed_out = True
        break
    else:
        res.status = EXHAUSTED
    if res.status == UNKNOWN:
        res.status = TIMEOUT if timed_out else EXHAUSTED
    res.detail["attempts"] = attempts[-50:]
    res.examples = E
    res.verify_time_s = t_ver
    res.total_time_s = time.perf_counter() - t_start
    res.synth_time_s = res.total_time_s - t_ver
    return res
