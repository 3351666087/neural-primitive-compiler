"""SMT (Z3, QF_LIA) encodings of network dynamics and of the specification logic.

Spikes are Booleans, so every synaptic term w * s is If(s, w, 0): linear even
when the weight w is itself an unknown (synthesis). Delays are structural
(fixed per synapse); a template expresses "unknown delay" by offering one
weight hole per candidate delay.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import z3

from .network import Network
from .spec import UNBOUNDED, F, Spec, SpecError


@dataclass(frozen=True)
class Hole:
    """An integer unknown in a network template."""

    name: str
    lo: int
    hi: int

    def __repr__(self) -> str:
        return f"?{self.name}[{self.lo},{self.hi}]"


def _is_hole(x: Any) -> bool:
    return isinstance(x, Hole)


def template_holes(net: Network) -> dict[str, Hole]:
    out: dict[str, Hole] = {}
    for n in net.neurons:
        for f in ("threshold", "leak", "bias", "reset", "init", "vmin", "vmax"):
            v = getattr(n, f)
            if _is_hole(v):
                out[v.name] = v
    for s in net.synapses:
        if _is_hole(s.weight):
            out[s.weight.name] = s.weight
    return out


def hole_vars(holes: Mapping[str, Hole]) -> tuple[dict[str, z3.ArithRef], list[z3.BoolRef]]:
    vars_ = {h: z3.Int(f"h_{h}") for h in holes}
    dom = [z3.And(vars_[h] >= holes[h].lo, vars_[h] <= holes[h].hi) for h in holes]
    return vars_, dom


def _lit(b: Any) -> Any:
    return z3.BoolVal(bool(b)) if isinstance(b, (bool, int)) else b


def unroll(
    net: Network,
    T: int,
    inputs: Mapping[str, Sequence[Any]],
    cons: list,
    prefix: str = "",
    hvars: Mapping[str, z3.ArithRef] | None = None,
) -> dict[str, list[Any]]:
    """Encode T steps. Returns {neuron: [spike_t ...]} as z3 Bool terms.

    ``inputs`` values may be z3 Bools (verification) or Python bools (synthesis
    on a concrete example). Field values may be ints or Holes (looked up in hvars).
    """
    hvars = hvars or {}

    def val(x: Any) -> Any:
        if _is_hole(x):
            return hvars[x.name]
        return x

    incoming: dict[str, list] = {n.name: [] for n in net.neurons}
    for s in net.synapses:
        incoming[s.dst].append(s)
    sig: dict[str, list[Any]] = {k: list(inputs[k]) for k in net.inputs}
    for n in net.neurons:
        sig[n.name] = []
    u: dict[str, Any] = {n.name: val(n.init) for n in net.neurons}
    for t in range(T):
        new_u = {}
        for n in net.neurons:
            th, lk, bias, rst = val(n.threshold), val(n.leak), val(n.bias), val(n.reset)
            lo, hi = val(n.vmin), val(n.vmax)
            terms: list[Any] = [bias]
            for syn in incoming[n.name]:
                tt = t - syn.delay
                if tt < 0:
                    continue
                src = sig[syn.src][tt]
                w = val(syn.weight)
                if isinstance(src, bool) or (isinstance(src, int) and not isinstance(src, z3.ExprRef)):
                    if src:
                        terms.append(w)
                else:
                    terms.append(z3.If(src, w, 0))
            raw = u[n.name] + z3.Sum([z3.IntVal(x) if isinstance(x, int) else x for x in terms])
            v = z3.If(raw > hi, hi, z3.If(raw < lo, lo, raw))
            s_var = z3.Bool(f"{prefix}s_{n.name}_{t}")
            cons.append(s_var == (v >= th))
            sig[n.name].append(s_var)
            concrete = not any(_is_hole(getattr(n, f)) for f in ("leak", "reset", "vmin", "vmax"))
            if concrete and n.memoryless:
                new_u[n.name] = 0
            else:
                u_var = z3.Int(f"{prefix}u_{n.name}_{t + 1}")
                leaked = z3.If(v > lk, v - lk, z3.If(v < -lk, v + lk, 0))
                cons.append(u_var == z3.If(s_var, rst, leaked))
                new_u[n.name] = u_var
        u = new_u
    return {n.name: sig[n.name] for n in net.neurons}


# ------------------------------------------------------------------- formulas
def encode_formula(f: F, env: Mapping[str, Sequence[Any]], T: int) -> list[Any]:
    """Encode f at every t in [0, T). env values: z3 Bool terms or Python bools."""
    memo: dict[int, list[Any]] = {}
    TRUE_, FALSE_ = z3.BoolVal(True), z3.BoolVal(False)

    def ev(g: F) -> list[Any]:
        key = id(g)
        if key in memo:
            return memo[key]
        op = g.op
        if op == "const":
            r = [z3.BoolVal(g.params[0])] * T
        elif op == "atom":
            name = g.params[0]
            if name not in env:
                raise SpecError(f"unknown signal {name!r}")
            r = [_lit(b) for b in env[name]]
        elif op == "not":
            r = [z3.Not(a) for a in ev(g.args[0])]
        elif op == "and":
            cols = [ev(a) for a in g.args]
            r = [z3.And(*[c[t] for c in cols]) for t in range(T)]
        elif op == "or":
            cols = [ev(a) for a in g.args]
            r = [z3.Or(*[c[t] for c in cols]) for t in range(T)]
        elif op == "xor":
            a, b = ev(g.args[0]), ev(g.args[1])
            r = [z3.Xor(a[t], b[t]) for t in range(T)]
        elif op == "implies":
            a, b = ev(g.args[0]), ev(g.args[1])
            r = [z3.Implies(a[t], b[t]) for t in range(T)]
        elif op == "iff":
            a, b = ev(g.args[0]), ev(g.args[1])
            r = [a[t] == b[t] for t in range(T)]
        elif op in ("prev", "wprev"):
            k = g.params[0]
            a = ev(g.args[0])
            fill = FALSE_ if op == "prev" else TRUE_
            r = [fill if t - k < 0 else a[t - k] for t in range(T)]
        elif op in ("once", "hist"):
            lo, hi = g.params
            a = ev(g.args[0])
            r = []
            for t in range(T):
                top = t if hi == UNBOUNDED else min(hi, t)
                items = [a[t - j] for j in range(lo, top + 1)]
                if op == "once":
                    r.append(z3.Or(*items) if items else FALSE_)
                else:
                    r.append(z3.And(*items) if items else TRUE_)
        elif op == "since":
            a, b = ev(g.args[0]), ev(g.args[1])
            r = []
            prev: Any = FALSE_
            for t in range(T):
                prev = z3.Or(b[t], z3.And(a[t], prev))
                r.append(prev)
        elif op == "atleast":
            cols = [ev(a) for a in g.args]
            r = [z3.Sum([z3.If(c[t], 1, 0) for c in cols]) >= g.params[0] for t in range(T)]
        elif op == "cmp":
            a, b = ev(g.args[0]), ev(g.args[1])
            c = g.params[0]
            ops = {">=": lambda x, y: x >= y, "<=": lambda x, y: x <= y, "==": lambda x, y: x == y,
                   "!=": lambda x, y: x != y, ">": lambda x, y: x > y, "<": lambda x, y: x < y}
            r = [ops[c](a[t], b[t]) for t in range(T)]
        elif op == "int":
            r = [z3.IntVal(g.params[0])] * T
        elif op == "count":
            a = ev(g.args[0])
            w = g.params[0]
            r = [z3.Sum([z3.If(a[t - j], 1, 0) for j in range(w) if t - j >= 0]) for t in range(T)]
        elif op == "modcount":
            k = g.params[0]
            a, rst = ev(g.args[0]), ev(g.args[1])
            r = []
            c: Any = z3.IntVal(0)
            for t in range(T):
                inc = z3.If(c + 1 == k, 0, c + 1)
                c = z3.If(rst[t], 0, z3.If(a[t], inc, c))
                r.append(c)
        elif op == "add":
            a, b = ev(g.args[0]), ev(g.args[1])
            r = [a[t] + b[t] for t in range(T)]
        elif op == "sub":
            a, b = ev(g.args[0]), ev(g.args[1])
            r = [a[t] - b[t] for t in range(T)]
        elif op == "mul":
            a = ev(g.args[0])
            r = [g.params[0] * a[t] for t in range(T)]
        else:
            raise SpecError(f"unknown op {op}")
        memo[key] = r
        return r

    return ev(f)


def violation_terms(spec: Spec, env: Mapping[str, Sequence[Any]], T: int) -> list[tuple[int, Any]]:
    """[(t, viol_t)] for t >= warmup, matching Spec.violation_mask."""
    A = encode_formula(spec.assume, env, T)
    G = encode_formula(spec.guarantee, env, T)
    out = []
    held: Any = z3.BoolVal(True)
    for t in range(T):
        held_incl = z3.And(held, A[t])
        cond = held_incl if spec.assume_mode == "inclusive" else held
        if t >= spec.warmup:
            out.append((t, z3.And(cond, z3.Not(G[t]))))
        held = held_incl
    return out
