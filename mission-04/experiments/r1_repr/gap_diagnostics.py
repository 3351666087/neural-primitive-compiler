"""Descriptive diagnostics of the P-R1c gap tasks that remain unexplained (no grid contents are printed).

For each task: which conservation laws hold; whether, under a rule where law K holds, every input block is
recoloured uniformly in the output (else a within-block mechanism is needed); whether blocks are deleted.

  python -I mission-04/experiments/r1_repr/gap_diagnostics.py
"""
import json, sys
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import blocks as B, run_r1 as R

r1c = json.loads((HERE / "r1c.json").read_text())
left = [t for t in r1c["gap_tasks"] if r1c["rows"][t]["+ALL"]["S2"] != "correct"]
cats = {}
rows = {}
for t in left:
    train, _ = R.load(R.DATA / f"{t}.json")
    K = [r for r in B.GRAMMAR if B.law_K(train, r)]
    C = [r for r in B.GRAMMAR if B.law_C(train, r)]
    info = {"law_K_rules": K, "law_C_rules": C, "same_size": all(I.shape == O.shape for I, O in train)}
    if K:
        r = K[0]
        uniform, deleted, recoloured, added = True, False, False, False
        for I, O in train:
            blocks = B.partition(I, r)
            covered = np.zeros(I.shape, bool)
            for b in blocks:
                cols = {int(O[x]) for x in b}
                if len(cols) > 1:
                    uniform = False
                if cols == {0}:
                    deleted = True
                elif any(int(O[x]) != int(I[x]) for x in b):
                    recoloured = True
                for x in b:
                    covered[x] = True
            if (O[~covered] != 0).any():
                added = True
        info.update(rule=r, uniform_per_block=uniform, blocks_deleted=deleted, blocks_recoloured=recoloured,
                    cells_added_outside_blocks=added)
        cat = ("K: non-uniform recolouring inside blocks" if not uniform else
               "K: new cells outside input blocks" if added else
               "K: uniform per block, not a function of any attribute")
    else:
        cat = "C only: crop target not selectable by any attribute"
    info["category"] = cat
    cats[cat] = cats.get(cat, 0) + 1
    rows[t] = info
out = {"label": "ARC-AGI-1 training split, DEV; descriptive only", "unexplained_gap_tasks": len(left), "categories": cats, "rows": rows}
(HERE / "gap_diagnostics.json").write_text(json.dumps(out, indent=1, default=str))
print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=1))
