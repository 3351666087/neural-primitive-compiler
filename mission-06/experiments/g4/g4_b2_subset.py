"""Judge side, after the held-out split is extracted: B2 batch files for Gate 4 under experiments/b2/run/ (gitignored).
  g4c_batch{0..19}.json   b2_clean(): 60 held-out games, 3 per batch (shuffled, seed 73)
  g4p_batch{0..7}.json    b2_pert(): 24 of them, 3 per batch (shuffled, seed 74), served with the perturbation
  mission-06/env/venv-alf/bin/python -I mission-06/experiments/g4/g4_b2_subset.py      (prints counts only)"""

import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import games4 as G  # noqa: E402

run = HERE.parent / "b2" / "run"
run.mkdir(exist_ok=True)
for name, sel, seed in (("g4c", G.b2_clean(), 73), ("g4p", G.b2_pert(), 74)):
    sel = list(sel)
    random.Random(seed).shuffle(sel)
    (run / f"{name}_subset.json").write_text(json.dumps(sel))
    for k in range(len(sel) // 3):
        (run / f"{name}_batch{k}.json").write_text(json.dumps(sel[3 * k:3 * k + 3]))
    print(name, len(sel), "games,", len(sel) // 3, "batches")
