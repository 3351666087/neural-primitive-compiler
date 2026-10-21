"""Instance sets V_train, V_unseen and V_mc6 (protocol section 9, amendment 1 items 5, 8, 9). JUDGE SIDE.

Only feasible instances are kept. Objects take goal colours, plus the distractor colour 4: exhaustively in the
enumerated sets; in random instances, with probability 0.3 the instance has distractors and then each object is
colour 4 with probability 0.3. Hazards appear only under NO_DROP_HAZARD. Cue specs bind their variables to a
permutation of distinct colours from {1, 2, 3}.
"""

from __future__ import annotations

import itertools
import random

from env import hazard_rule, resolve
from feasibility import feasible

DISTRACTOR = 4


def goal_colours(spec):
    if spec.get("cue"):
        return [1, 2, 3]
    cols = set()
    for a in spec["atoms"]:
        cols.add(a[1])
        if a[0] == "ORDER":
            cols.add(a[2])
    for s in spec["safety"]:
        if s[0] == "NO_PICK":
            cols.add(s[1])
    return sorted(cols)


def bindings(spec):
    vs = spec.get("cue") or []
    if not vs:
        return [{}]
    return [dict(zip(vs, perm)) for perm in itertools.permutations([1, 2, 3], len(vs))]


def _inst(N, cells, haz, agent, binding):
    return {"N": N, "cells": tuple(cells), "hazards": tuple(haz), "agent": agent, "binding": binding}


def enumerate_all(spec, N, Kmax):
    """Every instance with N cells and 1..Kmax objects, colours from goal colours and 4, every agent position,
    hazard subsets of size <= 2 of the empty cells (only under NO_DROP_HAZARD), every cue binding."""
    pal = goal_colours(spec) + [DISTRACTOR]
    out = []
    for K in range(1, Kmax + 1):
        for pos in itertools.combinations(range(N), K):
            free = [p for p in range(N) if p not in pos]
            hz_sets = [()] if not hazard_rule(spec) else [h for r in range(3) for h in itertools.combinations(free, r)]
            for cols in itertools.product(pal, repeat=K):
                cells = [0] * N
                for p, c in zip(pos, cols):
                    cells[p] = c
                for hz in hz_sets:
                    haz = [1 if p in hz else 0 for p in range(N)]
                    for a in range(N):
                        for b in bindings(spec):
                            inst = _inst(N, cells, haz, a, b)
                            if feasible(spec, inst):
                                out.append(inst)
    return out


def random_instance(spec, N, Kmax, rng):
    for _ in range(10_000):
        K = rng.randint(1, min(Kmax, N - 1))
        pal = goal_colours(spec)
        cols = [rng.choice(pal) for _ in range(K)]
        if rng.random() < 0.3:
            cols = [DISTRACTOR if rng.random() < 0.3 else c for c in cols]
        pos = rng.sample(range(N), K)
        cells = [0] * N
        for p, c in zip(pos, cols):
            cells[p] = c
        haz = [0] * N
        if hazard_rule(spec):
            free = [p for p in range(N) if cells[p] == 0]
            for p in rng.sample(free, min(len(free), rng.randint(0, 2))):
                haz[p] = 1
        b = rng.choice(bindings(spec))
        inst = _inst(N, cells, haz, rng.randrange(N), b)
        if feasible(spec, inst):
            return inst
    raise RuntimeError("no feasible instance found")


def v_train(spec, seed=1):
    rng = random.Random(seed)
    out = enumerate_all(spec, 5, 3)
    for N in (6, 7):
        out += [random_instance(spec, N, 4, rng) for _ in range(1000)]
    return out


def v_unseen(spec, seed=2):
    rng = random.Random(seed)
    return {N: [random_instance(spec, N, 7, rng) for _ in range(1000)] for N in (9, 12, 15)}


def v_mc6(spec):
    return enumerate_all(spec, 6, 4)
