"""Judge side: the 12-game B2 subset of the Gate 3 evaluation games (2 per task type, seed 69, as G2 did with seed 66)
and its 4 batch files under experiments/b2/run/ (gitignored: game paths name the task).
  mission-06/env/venv-alf/bin/python -I mission-06/experiments/g3/g3_b2_subset.py"""

import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import games as G  # noqa: E402

games = G.evaluation()
rng = random.Random(69)
sel = []
for t in sorted({t for _, t in games}):
    idx = [i for i, (_, tt) in enumerate(games) if tt == t]
    sel += [{"idx": i, "game": games[i][0], "type": t} for i in sorted(rng.sample(idx, 2))]
rng.shuffle(sel)
run = HERE.parent / "b2" / "run"
run.mkdir(exist_ok=True)
(run / "g3_subset.json").write_text(json.dumps(sel))
for k in range(4):
    (run / f"g3_batch{k}.json").write_text(json.dumps(sel[3 * k:3 * k + 3]))
print("subset indices (Gate 3 evaluation game numbers):", sorted(x["idx"] for x in sel))
