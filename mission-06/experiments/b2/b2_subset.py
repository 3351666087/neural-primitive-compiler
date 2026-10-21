"""Judge side: the 12-game B2 subset of the G2-ALF games (2 per task type, seed 66) and its 4 batch files, written
under experiments/b2/run/ (gitignored: game paths name the task).  venv-alf python -I b2_subset.py"""

import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "g2"))
import alf_run  # noqa: E402

games = alf_run.pick_games()
rng = random.Random(66)
types = sorted({t for _, t in games})
sel = []
for t in types:
    idx = [i for i, (_, tt) in enumerate(games) if tt == t]
    sel += [{"idx": i, "game": games[i][0], "type": t} for i in sorted(rng.sample(idx, 2))]
rng.shuffle(sel)
run = HERE / "run"
run.mkdir(exist_ok=True)
(run / "g2_subset.json").write_text(json.dumps(sel))
for k in range(4):
    (run / f"g2_batch{k}.json").write_text(json.dumps(sel[3 * k:3 * k + 3]))
print("subset indices (G2-ALF game numbers):", sorted(x["idx"] for x in sel))
