"""Concrete applicability counterexamples (Mission 06, G0.2). CONSTRUCTOR SIDE: uses the library's own semantics
(mission-05 lib/model.py, lib/libval2.eligible, g3/dsl.select_dsl); imports no truth table and nothing from judge/.

  check(spec, atom, cells, haz, fixed)        -> True iff the state is eligible and the achiever cannot move
  from_model(spec, atom, m, rng, tries)       -> a concrete counterexample built from an APP-R model, or None
  random_search(spec, atom, N, n, rng, scope) -> the first counterexample among n random eligible states, or None
"""

from __future__ import annotations

import sys
from pathlib import Path

M05 = Path(__file__).resolve().parents[3] / "mission-05" / "experiments"
sys.path.insert(0, str(M05 / "lib"))
sys.path.insert(0, str(M05 / "g3"))
import dsl  # noqa: E402
from libval import ROLE  # noqa: E402
from libval2 import eligible  # noqa: E402
from model import reloc  # noqa: E402

E, H, O, P, X, F = range(6)


def check(spec, atom, cells, haz, fixed):
    if not eligible(atom, cells, haz, fixed, ROLE):
        return False
    sel = dsl.select_dsl(spec, atom, cells, haz, True, fixed, ROLE)
    if sel is None:
        return True
    return reloc(cells, 0, sel[0], sel[1], haz, True) is None


def describe(cells, haz, fixed):
    return {"N": len(cells), "K": sum(1 for x in cells if x), "H": sum(haz), "fixed": list(fixed),
            "cells": list(cells), "haz": list(haz)}


def _class_of(p, m, base):
    d = m["d"]
    part = "L" if p < d else ("D" if p == d else "R")
    bits = "".join("1" if m["intervals"][b][0] <= p < m["intervals"][b][1] else "0" for b in base)
    return part + "|" + bits


def _colours(atom, types, rng):
    has_f = F in types
    if atom[0] == "ORDER":
        xs = [3] if has_f else [3, 4]
    else:
        xs = [2, 3] if has_f else [2, 3, 4]
    cells, haz = [], []
    for t in types:
        if t in (E, H):
            cells.append(0)
            haz.append(1 if t == H else 0)
        else:
            cells.append({O: 1, P: 2, F: 4}.get(t) or rng.choice(xs))
            haz.append(0)
    return tuple(cells), tuple(haz), ((4,) if has_f else ())


def from_model(spec, atom, m, rng, tries=500):
    N = m["N"]
    base = list(m["intervals"])
    cls = {}
    for p in range(N):
        cls.setdefault(_class_of(p, m, base), []).append(p)
    need = {k: list(v) for k, v in m["counts"].items()}
    fixed_pos = {}
    for name, (p, t) in m["witnesses"].items():
        if p in fixed_pos:
            continue
        k = _class_of(p, m, base)
        if k not in need or need[k][t] <= 0:
            return None
        need[k][t] -= 1
        fixed_pos[p] = t
    for k, ps in cls.items():
        free = [p for p in ps if p not in fixed_pos]
        if sum(need.get(k, [0] * 6)) != len(free):
            return None
    for _ in range(tries):
        types = [None] * N
        for p, t in fixed_pos.items():
            types[p] = t
        for k, ps in cls.items():
            free = [p for p in ps if p not in fixed_pos]
            pool = [t for t in range(6) for _ in range(need.get(k, [0] * 6)[t])]
            rng.shuffle(pool)
            for p, t in zip(free, pool):
                types[p] = t
        cells, haz, fixed = _colours(atom, types, rng)
        if check(spec, atom, cells, haz, fixed):
            return describe(cells, haz, fixed)
    return None


def random_state(N, rng, scope):
    kmax = min(N - 1, 7) if scope == "S_D" else N - 1
    K = rng.randint(1, kmax)
    pos = rng.sample(range(N), K)
    cells = [0] * N
    for p in pos:
        cells[p] = rng.randint(1, 4)
    free = [p for p in range(N) if cells[p] == 0]
    hmax = len(free) if scope == "S_A" else min(2, len(free))
    haz = [0] * N
    for p in rng.sample(free, rng.randint(0, hmax)):
        haz[p] = 1
    fixed = (4,) if rng.random() < 0.5 else ()
    return tuple(cells), tuple(haz), fixed


def random_search(spec, atom, N, n, rng, scope="S_T", max_draws=None):
    """Draws states until n eligible ones were checked (at most max_draws draws)."""
    got = draws = 0
    max_draws = max_draws or 20 * n
    while got < n and draws < max_draws:
        draws += 1
        cells, haz, fixed = random_state(N, rng, scope)
        if not eligible(atom, cells, haz, fixed, ROLE):
            continue
        got += 1
        sel = dsl.select_dsl(spec, atom, cells, haz, True, fixed, ROLE)
        if sel is None or reloc(cells, 0, sel[0], sel[1], haz, True) is None:
            return describe(cells, haz, fixed), got, draws
    return None, got, draws
