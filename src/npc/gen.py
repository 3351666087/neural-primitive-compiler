"""Seeded random generators for networks and formulas (tests and the unseen-task protocol)."""

from __future__ import annotations

import random

from .network import Network, Neuron, Synapse, full_leak
from .spec import F, UNBOUNDED, atom


def random_network(rng: random.Random, n_neurons: int, inputs: tuple[str, ...], n_outputs: int = 1,
                   max_delay: int = 3, p_syn: float = 0.35, wmax: int = 3, vmax: int = 7,
                   allow_negative: bool = True, rest: bool = False) -> Network:
    """rest=True forces bias=0, init=0 (the all-zero state is then a fixed point under zero input)."""
    names = [f"n{i}" for i in range(n_neurons)]
    neurons = []
    for nm in names:
        vmin = rng.choice([0, 0, -4]) if allow_negative else 0
        leak = rng.choice([0, 1, 2, full_leak(vmin, vmax)])
        neurons.append(Neuron(
            name=nm,
            threshold=rng.randint(1, vmax),
            leak=leak,
            bias=0 if rest else rng.choice([0, 0, 0, 1, -1]),
            reset=0 if rest else rng.choice([0, 0, vmin]),
            init=0 if rest else rng.choice([0, 0, 1]),
            vmin=vmin,
            vmax=vmax,
        ))
    syns = []
    for dst in names:
        for src in (*inputs, *names):
            if rng.random() < p_syn:
                w = rng.choice([k for k in range(-wmax, wmax + 1) if k != 0])
                syns.append(Synapse(src, dst, w, rng.randint(1, max_delay)))
    outs = tuple((f"y{i}" if n_outputs > 1 else "y", names[i]) for i in range(n_outputs))
    return Network("rand", tuple(inputs), tuple(neurons), tuple(syns), outs, max_delay=max_delay).validate()


def random_formula(rng: random.Random, names: list[str], depth: int, counting: bool = True,
                   unbounded: bool = True) -> F:
    if depth <= 0 or rng.random() < 0.2:
        r = rng.random()
        if r < 0.08:
            return F("const", (), (rng.random() < 0.5,))
        return atom(rng.choice(names))
    ops = ["not", "and", "or", "xor", "implies", "iff", "prev", "wprev", "once_b", "hist_b", "atleast"]
    if unbounded:
        ops += ["since", "once_u", "hist_u"]
    if counting:
        ops += ["cmp_count", "cmp_mod"]
    op = rng.choice(ops)
    sub = lambda: random_formula(rng, names, depth - 1, counting, unbounded)
    if op == "not":
        return F("not", (sub(),))
    if op in ("and", "or"):
        return F(op, tuple(sub() for _ in range(rng.randint(2, 3))))
    if op in ("xor", "implies", "iff", "since"):
        return F(op, (sub(), sub()))
    if op in ("prev", "wprev"):
        return F(op, (sub(),), (rng.randint(1, 3),))
    if op in ("once_b", "hist_b"):
        lo = rng.randint(0, 2)
        return F(op[:4], (sub(),), (lo, lo + rng.randint(0, 2)))
    if op in ("once_u", "hist_u"):
        return F(op[:4], (sub(),), (0, UNBOUNDED))
    if op == "atleast":
        k = rng.randint(1, 3)
        return F("atleast", tuple(sub() for _ in range(3)), (k,))
    if op == "cmp_count":
        w = rng.randint(1, 4)
        return F("cmp", (F("count", (sub(),), (w,)), F("int", (), (rng.randint(0, w),))), (rng.choice([">=", "==", "<"]),))
    k = rng.randint(2, 4)
    reset = sub() if rng.random() < 0.4 else F("const", (), (False,))
    return F("cmp", (F("modcount", (sub(), reset), (k,)), F("int", (), (rng.randint(0, k - 1),))), ("==",))
