"""Mission 04 pilot P-R1 runner (ARC-AGI-1 training split, DEV). Protocol: mission-04/PROTOCOL.md section 2.

Prints only task ids and outcome labels; never grid contents.

  python -I mission-04/experiments/r1_repr/run_r1.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "mission-04" / "experiments" / "a0_uniqueness"))
import blocks as B  # noqa: E402
import uniqueness as U  # noqa: E402

M = U.M
DATA = REPO / "mission-03" / "external" / "arc-agi-1" / "data" / "training"
ROUTES = ["F1", "F3", "F3-noselect", "F4"]


def load(path):
    d = json.loads(Path(path).read_bytes())
    return ([(np.array(p["input"]), np.array(p["output"])) for p in d["train"]],
            [(np.array(p["input"]), np.array(p["output"])) for p in d["test"]])


def plan(route, train):
    """Partition rules to search and the mechanisms allowed on each (route-specific selection)."""
    allm = ("KEEP", "RECOLOUR", "CROP")
    if route == "F1":
        return {r: allm for r in B.F1_LIST}
    if route == "F3-noselect":
        return {r: allm for r in B.GRAMMAR}
    if route == "F3":
        out = {}
        for r in B.GRAMMAR:
            mechs = (("KEEP", "RECOLOUR") if B.law_K(train, r) else ()) + (("CROP",) if B.law_C(train, r) else ())
            if mechs:
                out[r] = mechs
        return out
    if route == "F4":
        return {r: ("KEEP", "RECOLOUR") for r in B.GRAMMAR if B.law_residual(train, r)}
    raise ValueError(route)


def route_solve(route, train, test_inputs):
    p = plan(route, train)
    expls = []
    for rule, mechs in p.items():
        expls += B.explanations(train, rule, mechs)
    outs = []
    for I in test_inputs:
        preds = set()
        last = None
        for e in expls:
            o = B.predict(e, I)
            preds.add(None if o is None else (o.shape, o.tobytes()))
            last = o
        outs.append(last if expls and len(preds) == 1 and None not in preds else None)
    return outs, {"rules_tried": len(p), "explanations": len(expls), "rules_used": sorted({e[0] for e in expls}),
                  "mechanisms": sorted({e[1] for e in expls})}


def status(outs, tests):
    labels = ["abstain" if o is None else "correct" if o.shape == T.shape and (o == T).all() else "wrong"
              for o, (_, T) in zip(outs, tests)]
    return "correct" if all(l == "correct" for l in labels) else "wrong" if "wrong" in labels else "abstain"


def loo(route, train):
    if len(train) < 3:
        return None
    ok = 0
    for j in range(len(train)):
        rest = train[:j] + train[j + 1:]
        outs, _ = route_solve(route, rest, [train[j][0]])
        ok += int(outs[0] is not None and outs[0].shape == train[j][1].shape and (outs[0] == train[j][1]).all())
    return ok / len(train)


def specificity(train):
    if len(train) < 2:
        return None
    k = len(train)
    shuffled = [(train[i][0], train[(i + 1) % k][1]) for i in range(k)]
    holds = lambda pairs: any(B.law_K(pairs, r) or B.law_C(pairs, r) for r in B.GRAMMAR)
    return {"true": holds(train), "shuffled": holds(shuffled)}


# ------------------------------------------------------------------ F2a: macros from solved M-DISC explanations
def mdisc_cover(train):
    mats = [tuple(tuple(k * v for v in row) for row in Mx) for k in (1, 2, 3) for Mx in M.D4M]
    pieces = M.admissible_pieces(train, mats, M.translations())
    need = M.requirement(train)
    groups = {}
    for p in pieces:
        groups.setdefault(M.coverage(p, train), []).append(p)
    gl = list(groups.items())
    return pieces, gl, need


def f2a(tasks, answered_by_mdisc):
    ids = sorted(tasks)
    folds = {0: [t for i, t in enumerate(ids) if i % 2 == 0], 1: [t for i, t in enumerate(ids) if i % 2 == 1]}
    result = {}
    for a, b in ((0, 1), (1, 0)):
        counts = {}
        for tid in folds[a]:
            if tid not in answered_by_mdisc:
                continue
            train, _ = tasks[tid]
            pieces, gl, need = mdisc_cover(train)
            covers = M.min_covers(gl, need)
            if covers and len(covers[0]) >= 2:
                key = frozenset((gl[i][1][0][0], gl[i][1][0][1]) for i in covers[0])
                counts[key] = counts.get(key, 0) + 1
        macros = [m for m, c in counts.items() if c >= 2]
        gained = []
        for tid in folds[b]:
            if tid in answered_by_mdisc:
                continue
            train, tests = tasks[tid]
            pieces, gl, need = mdisc_cover(train)
            by_me = {(p[0], p[1]): p for p in pieces}
            extra = []
            for mac in macros:
                if all(x in by_me for x in mac):
                    members = [by_me[x] for x in mac]
                    cov = 0
                    for p in members:
                        cov |= M.coverage(p, train)
                    extra.append((cov, members))
            if not extra:
                continue
            groups = [(g[0], g[1]) for g in gl] + [(cov, [tuple(members)]) for cov, members in extra]
            covers = M.min_covers(groups, need)
            if not covers:
                continue
            rules = M.size_rules(train)
            ok = True
            for I, T in tests:
                shape = M.apply_size(rules, I) if rules else None
                cv = covers[0]
                flat = []
                for i in cv:
                    item = groups[i][1][0]
                    flat += list(item) if isinstance(item, tuple) and item and isinstance(item[0], tuple) and len(item[0]) == 3 else [item]
                pred = M.predict(flat, I, shape) if shape else None
                ok = ok and pred is not None and pred.shape == T.shape and (pred == T).all()
            if ok:
                gained.append(tid)
        result[f"fold{a}->fold{b}"] = {"macros": len(macros), "macro_sizes": sorted(len(m) for m in macros),
                                       "fold_b_tasks_gained_upper_bound": gained}
    return result


def main():
    t0 = time.perf_counter()
    tasks = {f.stem: load(f) for f in sorted(DATA.glob("*.json"))}
    rows = {}
    for tid, (train, tests) in tasks.items():
        row = {}
        for route in ROUTES:
            t1 = time.perf_counter()
            outs, info = route_solve(route, train, [I for I, _ in tests])
            st = status(outs, tests)
            row[route] = dict(info, status=st, time_s=round(time.perf_counter() - t1, 3),
                              loo=loo(route, train) if st != "abstain" else None)
        row["specificity"] = specificity(train)
        rows[tid] = row
        print(tid, {r: row[r]["status"] for r in ROUTES}, flush=True)
    out = {"label": "ARC-AGI-1 training split, DEV", "rows": rows, "f2a": "run separately: run_r1.py f2a",
           "time_s": round(time.perf_counter() - t0, 1)}
    (HERE / "r1.json").write_text(json.dumps(out, indent=1, default=str))
    print("time", out["time_s"])


def main_f2a():
    """F2a needs M-DISC-fixed's training results (mission-04/experiments/a0_uniqueness/rerun_training.json)."""
    tasks = {f.stem: load(f) for f in sorted(DATA.glob("*.json"))}
    rr = json.loads((REPO / "mission-04" / "experiments" / "a0_uniqueness" / "rerun_training.json").read_text())["rows"]
    answered = {t for t, r in rr.items() if r["M-DISC-fixed"]["status"] in ("correct", "wrong")}
    out = json.loads((HERE / "r1.json").read_text())
    out["f2a"] = f2a(tasks, answered)
    out["mdisc_fixed_answered"] = sorted(answered)
    (HERE / "r1.json").write_text(json.dumps(out, indent=1, default=str))
    print("f2a:", out["f2a"])


if __name__ == "__main__":
    main_f2a() if sys.argv[1:] == ["f2a"] else main()
