"""F2a, second implementation (POST-HOC correction, written after the first run returned 0 macros).

The first run (run_r1.py f2a) compared whole minimum covers by the FIRST representative piece of each coverage group,
and used M-DISC-fixed's answers before the UNKNOWN cases were resolved. Both choices are narrower than the locked
definition in PROTOCOL.md §2.4 ("a set of 2 or more pieces that recurs in the explanations of at least 2 solved tasks").
This version implements the locked definition more faithfully:
  - answered set = M-DISC-fixed after resolution (a0_uniqueness/final_numbers.json);
  - every minimum cover returned by min_covers, every piece of every group, every PAIR of pieces from two different
    groups of one cover counts as a candidate 2-piece set; a piece is identified by (matrix, size-generic translation);
  - a macro is a pair that occurs in at least 2 solved tasks of the learning fold.
Detection is still a lower bound (min_covers prunes dominated groups). Gains on the other fold are an upper bound
(first minimum cover, no uniqueness check), as in the first run. ARC-AGI-1 training split, DEV. Prints ids only.

  python -I mission-04/experiments/r1_repr/run_f2a_v2.py
"""

from __future__ import annotations

import itertools
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_r1 as R  # noqa: E402

M = R.M
REPO = HERE.parents[2]


def sig(p):
    return (p[0], p[1])


def pairs_of(train):
    pieces, gl, need = R.mdisc_cover(train)
    covers = M.min_covers(gl, need)
    out = set()
    for cv in covers:
        for i, j in itertools.combinations(cv, 2):
            si = {sig(p) for p in gl[i][1]}
            sj = {sig(p) for p in gl[j][1]}
            out |= {frozenset((a, b)) for a in si for b in sj if a != b}
    return out


def main():
    t0 = time.perf_counter()
    tasks = {f.stem: R.load(f) for f in sorted(R.DATA.glob("*.json"))}
    fn = json.loads((REPO / "mission-04/experiments/a0_uniqueness/final_numbers.json").read_text())["rows_training"]
    answered = {t for t, r in fn.items() if r["M-DISC-fixed"] in ("correct", "wrong")}
    ids = sorted(tasks)
    folds = {0: [t for i, t in enumerate(ids) if i % 2 == 0], 1: [t for i, t in enumerate(ids) if i % 2 == 1]}
    result = {}
    for a, b in ((0, 1), (1, 0)):
        occ = {}
        multi = 0
        for tid in folds[a]:
            if tid not in answered:
                continue
            ps = pairs_of(tasks[tid][0])
            multi += bool(ps)
            for pr in ps:
                occ.setdefault(pr, set()).add(tid)
        macros = [pr for pr, ts in occ.items() if len(ts) >= 2]
        gained = []
        for tid in folds[b]:
            if tid in answered or not macros:
                continue
            train, tests = tasks[tid]
            pieces, gl, need = R.mdisc_cover(train)
            by = {sig(p): p for p in pieces}
            extra = []
            for mac in macros:
                if all(x in by for x in mac):
                    members = [by[x] for x in mac]
                    cov = 0
                    for p in members:
                        cov |= M.coverage(p, train)
                    extra.append((cov, members))
            if not extra:
                continue
            groups = [(g[0], [[p] for p in g[1]]) for g in gl] + [(cov, [members]) for cov, members in extra]
            covers = M.min_covers(groups, need)
            if not covers:
                continue
            rules = M.size_rules(train)
            ok = True
            for I, T in tests:
                shape = M.apply_size(rules, I) if rules else None
                flat = [p for i in covers[0] for p in groups[i][1][0]]
                pred = M.predict(flat, I, shape) if shape else None
                ok = ok and pred is not None and pred.shape == T.shape and (pred == T).all()
            if ok:
                gained.append(tid)
        result[f"fold{a}->fold{b}"] = {"solved_tasks_in_fold": sum(t in answered for t in folds[a]),
                                       "solved_tasks_with_multi_piece_cover": multi,
                                       "candidate_pairs": len(occ), "macros": len(macros),
                                       "macro_task_sets": sorted(sorted(occ[m]) for m in macros),
                                       "fold_b_tasks_gained_upper_bound": gained}
        print(f"fold{a}->fold{b}", result[f"fold{a}->fold{b}"], flush=True)
    out = {"label": "ARC-AGI-1 training split, DEV; POST-HOC correction of the F2a implementation",
           "f2a_v2": result, "time_s": round(time.perf_counter() - t0, 1)}
    (HERE / "f2a_v2.json").write_text(json.dumps(out, indent=1, default=str))
    print("time", out["time_s"])


if __name__ == "__main__":
    main()
