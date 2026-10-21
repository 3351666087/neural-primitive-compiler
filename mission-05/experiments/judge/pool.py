"""PA-1 targets and the PA-2 goal pool (protocol section 9). JUDGE SIDE; written before any constructor.

PA-2 pool: every two-atom conjunction over the 12 atoms that is satisfiable on some small instance in which every
colour it mentions is present (N = 6, one or two objects of each mentioned colour); 20 three-atom conjunctions
drawn with seed 2026 under the same filter; 10 NO_PICK variants (seed 2027: a pool goal plus NO_PICK(c) for a
colour c it mentions). Cue variants are chosen AFTER A-P has run, by the fixed rule in `cue_variants`.

  python -I pool.py        # writes pool.json
"""

from __future__ import annotations

import itertools
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from feasibility import feasible  # noqa: E402

ATOMS = ([["ORDER", a, b] for a in (1, 2, 3) for b in (1, 2, 3) if a != b]
         + [["ZONE", c, side, "half"] for c in (1, 2) for side in ("left", "right")]
         + [["GROUP", c] for c in (1, 2)])

PA1 = {
    "T1": {"atoms": [["ORDER", 1, 2], ["ZONE", 3, "right", 2]], "safety": []},
    "T2": {"atoms": [["GROUP", 1], ["ORDER", 1, 2]], "safety": [["NO_DROP_HAZARD"]]},
    "T3": {"atoms": [["ORDER", 1, 2], ["ORDER", 2, 3], ["ZONE", 3, "right", 2]], "safety": []},
}
_M = [["ORDER", 1, 2], ["ORDER", 2, 3], ["ZONE", 3, "right", 2], ["GROUP", 1]]
for m in range(1, 5):
    PA1[f"M{m}"] = {"atoms": _M[:m], "safety": []}


def colours_mentioned(atoms, safety=()):
    cs = set()
    for a in atoms:
        cs.add(a[1])
        if a[0] == "ORDER":
            cs.add(a[2])
    for s in safety:
        if s[0] == "NO_PICK":
            cs.add(s[1])
    return sorted(cs)


def satisfiable_somewhere(atoms, safety=()):
    spec = {"atoms": atoms, "safety": list(safety), "cue": []}
    cols = colours_mentioned(atoms, safety)
    for counts in itertools.product((1, 2), repeat=len(cols)):
        objs = [c for c, n in zip(cols, counts) for _ in range(n)]
        if len(objs) >= 6:
            continue
        cells = objs + [0] * (6 - len(objs))
        inst = {"N": 6, "cells": tuple(cells), "hazards": (0,) * 6, "agent": 0, "binding": {}}
        if feasible(spec, inst):
            return True
    return False


def name(atoms, safety=()):
    f = lambda a: a[0] + "(" + ",".join(str(x) for x in a[1:]) + ")"
    return " & ".join([f(a) for a in atoms] + [f(s) for s in safety])


def build_pool():
    two = [list(p) for p in itertools.combinations(ATOMS, 2) if satisfiable_somewhere(list(p))]
    three_all = [list(p) for p in itertools.combinations(ATOMS, 3)]
    rng = random.Random(2026)
    rng.shuffle(three_all)
    three = []
    for p in three_all:
        if satisfiable_somewhere(p):
            three.append(p)
        if len(three) == 20:
            break
    rng2 = random.Random(2027)
    nopick = []
    for g in rng2.sample(two, 10):
        c = rng2.choice(colours_mentioned(g))
        nopick.append((g, [["NO_PICK", c]]))
    pool = {}
    for i, g in enumerate(two):
        pool[f"P2-{i:02d}"] = {"atoms": g, "safety": [], "cue": [], "name": name(g)}
    for i, g in enumerate(three):
        pool[f"P3-{i:02d}"] = {"atoms": g, "safety": [], "cue": [], "name": name(g)}
    for i, (g, s) in enumerate(nopick):
        pool[f"PN-{i:02d}"] = {"atoms": g, "safety": s, "cue": [], "name": name(g, s)}
    return pool


def cue_variants(pool, constructed_ids):
    """Fixed rule (seed 7): 10 two-atom goals without NO_PICK among those A-P constructed; every colour is
    replaced by a variable (distinct colours -> distinct variables X, Y, Z in order of first appearance)."""
    cand = sorted(i for i in constructed_ids if i.startswith("P2-"))
    rng = random.Random(7)
    chosen = rng.sample(cand, min(10, len(cand)))
    out = {}
    for i in chosen:
        g = pool[i]
        var = {}
        def v(c):
            if c not in var:
                var[c] = "XYZ"[len(var)]
            return var[c]
        atoms = [[a[0], v(a[1])] + ([v(a[2])] if a[0] == "ORDER" else a[2:]) for a in g["atoms"]]
        out["CUE-" + i] = {"atoms": atoms, "safety": [], "cue": sorted(set(var.values())), "name": "cue " + g["name"],
                           "from": i}
    return out


if __name__ == "__main__":
    pool = build_pool()
    pa1 = {k: dict(v, cue=[], name=name(v["atoms"], v["safety"])) for k, v in PA1.items()}
    (HERE / "pool.json").write_text(json.dumps({"PA1": pa1, "PA2": pool}, indent=1))
    print("PA-1 targets:", len(pa1), "| PA-2 two-atom:", sum(k.startswith("P2") for k in pool),
          "three-atom:", sum(k.startswith("P3") for k in pool), "NO_PICK:", sum(k.startswith("PN") for k in pool))
