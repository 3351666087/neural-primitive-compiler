"""Why does the fixed checker answer tasks that Mission 03's M-DISC abstained on? For each such task, report whether
Mission 03's own loop hit its 256-variant limit ("too many behaviourally distinct variants: treat as ambiguous"),
saw an undefined prediction (conflict / unseen colour), or neither. Also counts "conflict" abstentions of the fixed
solver. Prints only ids and booleans.

  python -I mission-04/experiments/a0_uniqueness/why_gains.py
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rerun_arc as RA  # noqa: E402
import uniqueness as U  # noqa: E402

M = U.M
GAINS = {"training": ["3af2c5a8", "62c24649", "67e8384a", "7fe24cdd"],
         "evaluation": ["0c786b71", "2072aba6", "59341089", "7953d61e", "ed98d772"]}


def m03_loop(train, I):
    rules = M.size_rules(train)
    shape = M.apply_size(rules, I)
    mats = [tuple(tuple(k * v for v in r) for r in Mx) for k in (1, 2, 3) for Mx in M.D4M]
    pieces = M.admissible_pieces(train, mats, M.translations())
    groups = {}
    for p in pieces:
        groups.setdefault(M.coverage(p, train), []).append(p)
    gl = list(groups.items())
    covers = M.min_covers(gl, M.requirement(train))
    limit_hit, undefined, preds = False, False, set()
    for cv in covers:
        sets = [gl[i][1] for i in cv]
        if np.prod([len(c) for c in sets]) > 256:
            limit_hit = True
            break
        for combo in itertools.product(*sets):
            p = M.predict(combo, I, shape)
            if p is None:
                undefined = True
            else:
                preds.add(p.tobytes())
    return {"limit_256_hit": limit_hit, "undefined_prediction": undefined, "distinct_before_stop": len(preds)}


def main():
    out = {}
    for split, ids in GAINS.items():
        for tid in ids:
            train, tests = RA.load(RA.DATA / split / f"{tid}.json")
            out[f"{split}|{tid}"] = [m03_loop(train, I) for I, _ in tests]
            print(split, tid, out[f"{split}|{tid}"], flush=True)
    conflicts = {}
    for split in GAINS:
        rows = json.loads((HERE / f"rerun_{split}.json").read_text())["rows"]
        conflicts[split] = {name: sorted(t for t, r in rows.items() if isinstance(r[name], dict)
                                         and any(s and s.startswith("conflict") for s in (r[name].get("uniqueness") or [])))
                            for name in RA.VARIANTS}
    out["fixed_solver_conflict_abstentions"] = conflicts
    print(json.dumps(conflicts))
    (HERE / "why_gains.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
