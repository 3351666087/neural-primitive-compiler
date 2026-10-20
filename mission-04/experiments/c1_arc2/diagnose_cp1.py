"""POST-HOC diagnosis of the CP1 failure (written after the confirmation was scored; it does not change any verdict).

Hypothesis: the block layer takes colour 0 as background. Where training inputs have few or no 0 cells, a NONBG
partition puts (almost) the whole grid into one block, and law K then holds for any same-size task that keeps the
non-zero footprint, so it says little about the mechanism. Compares ARC-AGI-1 training (DEV) with the ARC-AGI-2
evaluation set (CONFIRMATION). Prints only counts, ids and booleans; never grid contents.

  python -I mission-04/experiments/c1_arc2/diagnose_cp1.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "mission-04" / "experiments" / "r1_repr"))
import blocks as B  # noqa: E402
import run_r1 as R  # noqa: E402

SETS = {"DEV ARC-AGI-1 training": REPO / "mission-03/external/arc-agi-1/data/training",
        "CONFIRMATION ARC-AGI-2 evaluation": REPO / "mission-04/external/arc-agi-2/data/evaluation"}


def task_facts(train):
    zero_free = any(not (I == 0).any() for I, _ in train)
    mode_not_zero = sum(int(np.bincount(I.ravel(), minlength=10).argmax() != 0) for I, _ in train) > len(train) / 2
    law_rules = [r for r in B.GRAMMAR if B.law_K(train, r) or B.law_C(train, r)]
    single = {}
    for r in law_rules:
        # does this rule put all non-background cells of every training input into one block?
        single[r] = all(len(B.partition(I, r)) == 1 for I, _ in train)
    return {"zero_free_input": zero_free, "background_not_zero": mode_not_zero, "law_rules": law_rules,
            "law_only_via_single_block": bool(law_rules) and all(single.values()),
            "law_via_some_single_block": any(single.values())}


def main():
    out = {"label": "POST-HOC diagnosis of CP1 (after scoring); does not change any verdict", "sets": {}}
    for name, d in SETS.items():
        rows = {}
        for f in sorted(d.glob("*.json")):
            if f.name == "MANIFEST.json":
                continue
            train, _ = R.load(f)
            rows[f.stem] = task_facts(train)
        law = {t: r for t, r in rows.items() if r["law_rules"]}
        agg = {"tasks": len(rows),
               "tasks_with_a_zero_free_training_input": sum(r["zero_free_input"] for r in rows.values()),
               "tasks_whose_most_frequent_input_colour_is_not_0": sum(r["background_not_zero"] for r in rows.values()),
               "law_holding_tasks": len(law),
               "law_holding_only_through_single_block_partitions": sum(r["law_only_via_single_block"] for r in law.values()),
               "law_holding_with_some_single_block_rule": sum(r["law_via_some_single_block"] for r in law.values()),
               "law_holding_and_background_not_0": sum(r["background_not_zero"] for r in law.values())}
        out["sets"][name] = {"summary": agg, "law_only_via_single_block_ids": sorted(
            t for t, r in law.items() if r["law_only_via_single_block"]), "rows": rows}
        print(name, json.dumps(agg))
    (HERE / "diagnose_cp1.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
