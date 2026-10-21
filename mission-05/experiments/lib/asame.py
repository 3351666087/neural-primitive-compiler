"""A-SAME: the same achievers, the same priority composition and the same candidate order as A-P, WITHOUT the
contract table. Each candidate is verified globally by macro-level simulation (model.simulate) on the training
verification set V_train, which every route shares (protocol section 9). CEGIS: a candidate is first run on the
counterexamples collected so far; only if it passes them is it run on the whole set, and its first failing
instance joins the counterexample set. The first candidate that succeeds on every training instance is accepted.
CONSTRUCTOR SIDE (the instances are plain data handed over by the runner).
"""

from __future__ import annotations

import itertools
import time

from model import simulate

VARS = {"ORDER": ("O1", "O2"), "ZONE": ("Z1", "Z2"), "GROUP": ("G1", "G2")}


def construct(spec, train, budget_s=600.0, max_variants=2, cegis=True):
    t0 = time.perf_counter()
    atoms = spec["atoms"]
    cex = []
    cand = sims = 0
    for perm in itertools.permutations(range(len(atoms))):
        order = [atoms[i] for i in perm]
        for vs in itertools.product(*[VARS[a[0]][:max_variants] for a in order]):
            if time.perf_counter() - t0 > budget_s:
                return {"status": "RESOURCE_LIMIT", "plan": None, "candidates": cand, "simulations": sims,
                        "counterexamples": len(cex), "time_s": time.perf_counter() - t0}
            cand += 1
            plan = list(zip(order, vs))
            ok = True
            if cegis:
                for inst in cex:
                    sims += 1
                    if simulate(plan, spec, inst)[0] != "SUCCESS":
                        ok = False
                        break
            if not ok:
                continue
            for inst in train:
                sims += 1
                if simulate(plan, spec, inst)[0] != "SUCCESS":
                    ok = False
                    if cegis:
                        cex.append(inst)
                    break
            if ok:
                return {"status": "CONSTRUCTED", "plan": plan, "candidates": cand, "simulations": sims,
                        "counterexamples": len(cex), "time_s": time.perf_counter() - t0}
    return {"status": "OUT_OF_CLASS", "plan": None, "candidates": cand, "simulations": sims,
            "counterexamples": len(cex), "time_s": time.perf_counter() - t0}
