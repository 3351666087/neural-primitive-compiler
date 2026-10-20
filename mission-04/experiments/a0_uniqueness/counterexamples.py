"""Minimal counterexamples for the Mission 03 uniqueness logic (audit items U1-U5).

C1 (U1, dominance pruning)   random search over small synthetic grid tasks (outputs = union of two random pieces
                              of the M-DISC class); report every task where Mission 03's solve(unique=True) answers
                              but the exact check finds a train-consistent minimum explanation with a different test
                              prediction; keep the smallest instance.
C2 (U2, cap = 200)            a 2-bit requirement with 15 x 15 single-bit groups: 225 minimum covers, 200 returned.
C3 (U3, islice 256)           3 groups with 7 equally short variants each: 343 combinations, 256 inspected.
C4 (U5, colour extension)     identity task, training colours {1}, test colour 2: the identity extension is a prior,
                              not forced by the data.
C5 (U6, size rule)            all training inputs 3x3: the constant rule H' = 3 is consistent but not simplest.

  python mission-04/experiments/a0_uniqueness/counterexamples.py
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import uniqueness as U  # noqa: E402

M = U.M


def apply_piece(Mx, t, I, shape):
    out = np.zeros(shape, int)
    ys, xs = np.nonzero(I != 0)
    (a, b), (c, d) = Mx
    for x, y in zip(xs, ys):
        X, Y = a * x + b * y + t[0], c * x + d * y + t[1]
        if 0 <= X < shape[1] and 0 <= Y < shape[0]:
            out[Y, X] = I[y, x]
    return out


def random_task(rng):
    """Output = union of two random pieces (D4 matrix, small size-generic translation); same-size output."""
    mats = M.D4M
    p = [(rng.choice(mats), (rng.choice((0, 1)), 0, rng.randint(-2, 2), 0, rng.choice((0, 1)), rng.randint(-2, 2)))
         for _ in range(2)]
    pairs = []
    for _ in range(4):
        h = rng.randint(3, 5)
        I = np.array([[rng.choice((1, 2)) if rng.random() < 0.3 else 0 for _ in range(h)] for _ in range(h)])
        O = np.zeros_like(I)
        conflict = False
        for Mx, E in p:
            img = apply_piece(Mx, M.abs_t(E, I), I, I.shape)
            if ((O != 0) & (img != 0) & (O != img)).any():
                conflict = True
            O = np.where(img != 0, img, O)
        if conflict or not (O != 0).any():
            return None
        pairs.append((I, O))
    return pairs[:3], pairs[3], p


def c1(n_trials=300, seed=0):
    rng = random.Random(seed)
    found, answered, tried = [], 0, 0
    t0 = time.perf_counter()
    while tried < n_trials:
        task = random_task(rng)
        if task is None:
            continue
        tried += 1
        train, (TI, TO), gen = task
        old, info = M.solve(train, [TI])
        if old[0] is None:
            continue
        answered += 1
        new, ninfo = U.solve_fixed(train, [TI])
        if new[0] is None and "AMBIGUOUS" in ninfo.get("reason", ""):
            # independent cross-check without Z3: every minimum cover over ALL groups (no pruning, no cap)
            groups = {}
            for pc in M.admissible_pieces(train, [tuple(tuple(k * v for v in r) for r in Mx) for k in (1, 2, 3) for Mx in M.D4M],
                                          M.translations()):
                groups.setdefault(M.coverage(pc, train), []).append(pc)
            gl = list(groups.items())
            covers, complete = U.all_min_covers_exhaustive(gl, M.requirement(train), limit=20000)
            shape = M.apply_size(M.size_rules(train), TI)
            preds = set()
            import itertools as _it
            for cv in covers:
                for combo in _it.islice(_it.product(*[gl[i][1] for i in cv]), 64):
                    pr = M.predict(combo, TI, shape)
                    preds.add(None if pr is None else pr.tobytes())
            found.append({"verified_by_exhaustive_enumeration": complete and len(preds) > 1,
                          "exhaustive_min_covers": len(covers), "distinct_predictions": len(preds),"train_sizes": [I.shape for I, _ in train], "test_size": TI.shape,
                          "old_answer_correct": bool((old[0] == TO).all()) if old[0].shape == TO.shape else False,
                          "generator": [[list(map(list, Mx)), list(E)] for Mx, E in gen],
                          "train": [[I.tolist(), O.tolist()] for I, O in train], "test": [TI.tolist(), TO.tolist()],
                          "old_min_covers": info["min_covers"]})
    found.sort(key=lambda f: sum(np.array(f["train"][k][0]).size for k in range(3)))
    return {"trials": tried, "old_answered": answered, "pruning_hid_ambiguity": len(found),
            "verified": sum(f["verified_by_exhaustive_enumeration"] for f in found),
            "cap_involved": sum(f["old_min_covers"] >= 200 for f in found),
            "old_answer_wrong_among_those": sum(not f["old_answer_correct"] for f in found),
            "smallest": found[:1], "time_s": round(time.perf_counter() - t0, 1)}


def c2():
    groups = [(1, [f"a{i}"]) for i in range(15)] + [(2, [f"b{i}"]) for i in range(15)]
    capped = M.min_covers(groups, 3)
    full, complete = U.all_min_covers_exhaustive(groups, 3)
    return {"minimum_covers_exist": len(full), "returned_by_m03": len(capped), "complete_reference": complete,
            "consequence": "uniqueness was checked on the first 200 covers only; a 201st cover with a different "
                           "prediction would not be seen"}


def c3():
    sets = [[f"v{g}{i}" for i in range(7)] for g in range(3)]
    import itertools
    inspected = sum(1 for _ in itertools.islice(itertools.product(*sets), 256))
    return {"combinations": 7 ** 3, "inspected_by_m03_mdl": inspected}


def c4():
    I1 = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 0]])
    I2 = np.array([[0, 0, 1], [1, 0, 0], [0, 0, 0]])
    I3 = np.array([[0, 1, 0], [0, 0, 0], [1, 0, 1]])
    train = [(I1, I1.copy()), (I2, I2.copy()), (I3, I3.copy())]
    T = np.array([[2, 0, 0], [0, 0, 1], [0, 0, 0]])
    old, _ = M.solve(train, [T])
    prior, pinfo = U.solve_fixed(train, [T], colour_mode="prior")
    strict, sinfo = U.solve_fixed(train, [T], colour_mode="strict")
    return {"m03_answer": None if old[0] is None else old[0].tolist(), "fixed_prior_mode": pinfo["reason"],
            "fixed_strict_mode": sinfo["reason"],
            "note": "a colour function with sigma(1)=1 and sigma(2)=c for any c is equally consistent with training"}


def c5():
    rng = np.random.default_rng(0)
    train = [(rng.integers(0, 3, (3, 3)), rng.integers(1, 3, (3, 3))) for _ in range(3)]
    rules = M.size_rules(train)
    test = np.zeros((5, 5), int)
    cands = [(a, b, c) for a in range(4) for b in range(4) for c in (range(-2, 3) if a + b else range(1, 31))
             if all(a * 3 + b * 3 + c == 3 for _ in train)]
    return {"simplest_rules_rows": rules[0], "all_consistent_row_rules": len(cands),
            "test_rows_by_consistent_rules": sorted({a * 5 + b * 5 + c for a, b, c in cands}),
            "m03_test_shape": M.apply_size(rules, test)}


def main():
    out = {"C2_cap": c2(), "C3_islice": c3(), "C4_colour_extension": c4(), "C5_size_rule": c5()}
    print(json.dumps(out, indent=1, default=str), flush=True)
    out["C1_dominance_pruning"] = c1()
    print(json.dumps({k: v for k, v in out["C1_dominance_pruning"].items() if k != "smallest"}, indent=1), flush=True)
    (HERE / "counterexamples.json").write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
