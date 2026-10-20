"""Mission 03, exploration round 2: can the gating CONCEPT of a conditional command be invented from passive
data without a hand-listed concept family? (Predictions: CHALLENGE_PROTOCOL.md, amendment 1.)

Data: the same passive events as P1 (pre-state, post-state at the identified delay), N = 3 and N = 5.
Every hypothesis has two branches, each a union map (Src_c(j) = set of pre cells that turn target j on), and a
hidden branch label z_i per event. Concept priors, from weakest to strongest:

  G-free   z_i unconstrained: "some hidden binary variable selects the branch".
  G-region z_i = [pre_i meets R] for an arbitrary learned region R (any of the 2^(N*N) cell sets):
           "the concept is occupancy of some region". No list of candidate regions is given.

Each prior is solved exactly with Z3. Identifiability is measured by asking Z3 for a second solution that
differs in the branch labels of the observed events (G-free) or in R (G-region), with the class swap removed
by fixing z = 1 on the first event that the first solution labels 1. Size generalisation of R: fit R at N = 3
and N = 5 with the box-domain description used in L2 (rows/columns/blocks bounded 0-2 cells from the edges),
then compare its N = 8, 11 instance with the true region.

  python mission-03/experiments/p1b_concept/run_concept.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import z3

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "mission-03" / "experiments" / "p1_composition"))
from run_p1 import UNSEEN, at_delay, change_delays, generate, letter_events, observe  # noqa: E402

PROBES = (3, 5)
TIMEOUT_MS = 300_000


def encode(pairs, coords, prior):
    s = z3.Solver()
    s.set("timeout", TIMEOUT_MS)
    src = {(c, j, p): z3.Bool(f"s_{c}_{j}_{p}") for c in (0, 1) for j in coords for p in coords}
    z = [z3.Bool(f"z_{i}") for i in range(len(pairs))]
    r = {p: z3.Bool(f"r_{p}") for p in coords}
    for i, (pre, post) in enumerate(pairs):
        for c in (0, 1):
            lit = z[i] if c == 1 else z3.Not(z[i])
            for j in coords:
                if j in post:
                    s.add(z3.Implies(lit, z3.Or([src[(c, j, p)] for p in pre]) if pre else z3.BoolVal(False)))
                else:
                    for p in pre:
                        s.add(z3.Implies(lit, z3.Not(src[(c, j, p)])))
        if prior == "region":
            s.add(z[i] == (z3.Or([r[p] for p in pre]) if pre else z3.BoolVal(False)))
    return s, z, r


def solve(pairs, coords, prior):
    s, z, r = encode(pairs, coords, prior)
    t0 = time.perf_counter()
    res = s.check()
    out = {"status": str(res), "time_s": round(time.perf_counter() - t0, 1)}
    if res != z3.sat:
        return out, None
    m = s.model()
    labels = [z3.is_true(m.eval(zi, model_completion=True)) for zi in z]
    R = frozenset(p for p in coords if z3.is_true(m.eval(r[p], model_completion=True)))
    out["region"] = sorted(R) if prior == "region" else None
    out["label_counts"] = [labels.count(False), labels.count(True)]
    # identifiability: a second solution with different labels (G-free) or a different region (G-region)
    if True in labels:
        s.add(z[labels.index(True)])                        # removes the class swap
    if prior == "region":
        s.add(z3.Or([r[p] != (p in R) for p in coords]))
    else:
        s.add(z3.Or([zi != lab for zi, lab in zip(z, labels)]))
    t1 = time.perf_counter()
    res2 = s.check()
    out["second_solution"] = str(res2)
    out["second_time_s"] = round(time.perf_counter() - t1, 1)
    if res2 == z3.sat and prior == "region":
        m2 = s.model()
        out["second_region"] = sorted(p for p in coords if z3.is_true(m2.eval(r[p], model_completion=True)))
    return out, R


BOX = [(a, b, c, d) for a in (0, 1, 2) for b in (0, 1, 2) for c in (0, 1, 2) for d in (0, 1, 2)]


def box_cells(box, N):
    lx, hx, ly, hy = box
    return frozenset((x, y) for x in range(lx, N - hx) for y in range(ly, N - hy))


def generalise(regions, true_region_fn):
    fits = [b for b in BOX if all(box_cells(b, N) == R for N, R in regions.items())]
    res = {"box_fits": [list(b) for b in fits]}
    for N in (8, 11):
        preds = {box_cells(b, N) for b in fits}
        res[f"N{N}"] = ("no box description" if not fits else
                        "correct" if preds == {true_region_fn(N)} else
                        "ambiguous" if len(preds) > 1 else "wrong")
    return res


TRUE_REGION = {"top": lambda N: frozenset((x, 0) for x in range(N)),
               "bottom": lambda N: frozenset((x, N - 1) for x in range(N)),
               "left": lambda N: frozenset((0, y) for y in range(N))}


def main():
    seed = json.loads((UNSEEN / "tasks.json").read_text())["seed"]
    units = {u.uid: u for u in generate(seed)}
    rows = []
    for uid in ("UA0", "UA2", "UA3", "UA4"):
        u = units[uid]
        name, reg = u.params["cond"][0], u.params["cond"][1]
        row = {"uid": uid, "command": name, "true_region_for_scoring_only": reg}
        pairs, regions = {}, {}
        for N in PROBES:
            t = u.build(N)
            ev = letter_events(t, observe(t), name)
            ds, _ = change_delays(ev)
            d = min(ds)
            pairs[N] = at_delay(ev, d)
            for prior in ("free", "region"):
                res, R = solve(pairs[N], t.space.coords, prior)
                row[f"G-{prior}@N{N}"] = res
                if prior == "region" and R is not None:
                    regions[N] = R
            row[f"events@N{N}"] = len(pairs[N])
        if len(regions) == len(PROBES):
            row["region_generalisation"] = generalise(regions, TRUE_REGION[reg])
        print(json.dumps(row, default=str)[:1500], flush=True)
        rows.append(row)
    (HERE / "concept.json").write_text(json.dumps({"rows": rows}, indent=1, default=str))


if __name__ == "__main__":
    main()
