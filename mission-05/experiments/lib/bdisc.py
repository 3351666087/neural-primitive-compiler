"""B-1' (amendment 2): learn the damage table from observed relocations instead of exhaustive checking.

For each achiever instance, states are drawn at random (rejection sampling from the libval.py distribution: objects
of colours 1..4, K <= N-1, hazard subsets of size <= 2 of the empty cells, NO_PICK on X2 or on nothing) until the
achiever's atom is violated, satisfiable on its own, and a spare cell exists; one relocation is observed and the
change of every template is recorded.
  B-DISC   n states at each of N = 5, 6, 7; bounded with value max over all observations iff the observed maximum
           at N = 7 does not exceed the one at N = 5, else growing
  B-NULL   n states at N = 5 only; bound = observed maximum (no growth check)
Output has the same layout as damage_table.json, so ap2.construct can use it directly.
"""

from __future__ import annotations

import random

from libval import ROLE, achiever_instances
from libval2 import deltas, eligible
from potentials import patterns


def sample_state(N, rng):
    K = rng.randint(1, N - 1)
    pos = rng.sample(range(N), K)
    cells = [0] * N
    for p in pos:
        cells[p] = rng.randint(1, 4)
    free = [p for p in range(N) if cells[p] == 0]
    hz = set(rng.sample(free, rng.randint(0, min(2, len(free)))))
    haz = tuple(1 if p in hz else 0 for p in range(N))
    fixed = rng.choice(((), (4,)))
    return tuple(cells), haz, fixed


def observe(a, v, keys, N, n, rng, max_tries=200_000):
    mx = {k: None for k in keys}
    got = tries = 0
    while got < n and tries < max_tries:
        tries += 1
        cells, haz, fixed = sample_state(N, rng)
        if not eligible(a, cells, haz, fixed):
            continue
        d = deltas(a, v, cells, haz, fixed, keys)
        if d is None:
            continue
        got += 1
        for k, x in d.items():
            if mx[k] is None or x > mx[k]:
                mx[k] = x
    return mx, got, tries


def learn(n, mode, seed=0):
    rng = random.Random(seed)
    table = {}
    cost = {"observations": 0, "draws": 0}
    for key, a, v in achiever_instances():
        keys = patterns(a[0])
        sizes = (5, 6, 7) if mode == "disc" else (5,)
        per = {}
        for N in sizes:
            mx, got, tries = observe(a, v, keys, N, n, rng)
            per[N] = mx
            cost["observations"] += got
            cost["draws"] += tries
        ent = {}
        for k in keys:
            vals = {N: per[N][k] for N in sizes}
            seen = [x for x in vals.values() if x is not None]
            if not seen:
                bound = None
            elif mode == "disc":
                bound = max(seen) if (vals[7] is not None and vals[5] is not None and vals[7] <= vals[5]) else "inf"
            else:
                bound = max(seen)
            ent[k] = {"max_by_N": vals, "bound": bound}
        table[key] = {"entries": ent}
    return table, cost
