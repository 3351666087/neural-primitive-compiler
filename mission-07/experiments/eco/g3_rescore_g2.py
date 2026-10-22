"""Amendment A2 check (JUDGE SIDE): rescore every Gate 2 run with score_eco2 and compare with g2_scores.json.
  python3 -I g3_rescore_g2.py        # writes g3_rescore_g2.json"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ground_eco as G  # noqa: E402
import score_eco2 as S2  # noqa: E402
from eco_env import load_family  # noqa: E402
from g2_jobs import BASE, FAKES, LEARNERS, OUT  # noqa: E402


def main():
    fam = load_family(HERE / "family_alpha.json")
    probes, classes = G.make_probes(fam)
    old = json.loads((HERE / "g2_scores.json").read_text())["runs"]
    rows, diffs = {}, []
    for arm in BASE + FAKES:
        for seed in (range(100, 105) if arm in BASE else (100, 101)):
            stem = f"{arm}_alpha_{seed}"
            twin = f"{stem}.twin" if arm in LEARNERS else stem
            r = S2.public(S2.score_run(stem, OUT, probes, classes, twin_stem=twin))
            o = old[stem]
            new_g = sorted({p["class"] for s in r["structures"].values() for p in s["predicates"].values() if p["grounded"]})
            old_g = sorted({i["class"] for i in o["predicates"].values() if i["grounded"]})
            row = {"L2_any": [o["L2_any"], r["L2_any"]], "grounded_classes": [old_g, new_g],
                   "goal_log_valid": [o["goal_log_valid"], r["goal_log_valid"]],
                   "top_by_class_old": {k: v.get("top", 0) for k, v in o["goals_by_class"].items()},
                   "top_by_class_new": {k: v.get("top", 0) for k, v in r["goals_by_class"].items()}}
            rows[stem] = row
            same = row["L2_any"][0] == row["L2_any"][1] and old_g == new_g and row["goal_log_valid"][0] == row["goal_log_valid"][1]
            if not same:
                diffs.append(stem)
            print(stem, "same" if same else "DIFF", row["L2_any"], old_g, new_g, flush=True)
    out = {"runs": rows, "differences": diffs, "verdicts_unchanged": not diffs}
    (HERE / "g3_rescore_g2.json").write_text(json.dumps(out, indent=1))
    print("differences:", diffs)


if __name__ == "__main__":
    main()
