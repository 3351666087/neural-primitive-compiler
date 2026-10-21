"""JUDGE SIDE game sets for Gate 4 (EXPERIMENT_PRE_REGISTRATION.md section G4).
  heldout()   the official ALFWorld held-out split valid_unseen (unseen rooms), every solvable game, sorted by path
  dev60()     the 60 Gate 3 evaluation games (train split, development; used to set the Gate 4 predictions)
  b2_clean()  B2 subset of heldout(): 10 per task type, seed 71
  b2_pert()   4 per task type drawn (seed 72) from b2_clean(), for B2 under perturbation
Each returns [(game file, task type)]; b2_* return [{"idx", "game", "type"}].
"""

import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "g1"))
DATA = str(HERE.parents[1] / "env" / "alfworld-data")


def heldout():
    import alf_judge as J
    return sorted(J.list_games(DATA, "valid_unseen"))


def dev60():
    sys.path.insert(0, str(HERE.parent / "g3"))
    import games as G
    return G.evaluation()


def b2_clean():
    games = heldout()
    rng = random.Random(71)
    sel = []
    for t in sorted({t for _, t in games}):
        idx = [i for i, (_, tt) in enumerate(games) if tt == t]
        sel += [{"idx": i, "game": games[i][0], "type": t} for i in sorted(rng.sample(idx, 10))]
    return sel


def b2_pert():
    clean = b2_clean()
    rng = random.Random(72)
    sel = []
    for t in sorted({x["type"] for x in clean}):
        sel += sorted(rng.sample([x for x in clean if x["type"] == t], 4), key=lambda x: x["idx"])
    return sel
