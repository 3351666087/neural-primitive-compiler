"""Judge side: disjoint game sets for Gate 3 (EXPERIMENT_PRE_REGISTRATION.md section G3-M2), drawn from the train split
excluding every game used before (P-ALF-1 seed 61, B2P0 seed 62, server test seed 63, G2-ALF seed 65).
  discovery()   20 games, seed 67 (any task type)
  evaluation()  60 games, seed 68, 10 per task type, disjoint from discovery
  smoke()       code check only: 6 games of the G2-ALF set (already used and scored), one per task type
"""

import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "g1"))
sys.path.insert(0, str(HERE.parent / "b2"))
sys.path.insert(0, str(HERE.parent / "g2"))
DATA = str(HERE.parents[1] / "env" / "alfworld-data")


def _pool():
    import alf_judge as J
    import alf_run as R
    import alf_server as S
    used = set(J.sample_games(DATA, "train", 10, 61)[0])
    used |= set(S.pick_games(2, False)[0]) | set(S.pick_games(1, True)[0])
    used |= {g for g, _ in R.pick_games()}
    return [(g, t) for g, t in J.list_games(DATA, "train") if g not in used], J


def discovery():
    pool, _ = _pool()
    return random.Random(67).sample(sorted(pool), 20)


def evaluation():
    pool, J = _pool()
    disc = {g for g, _ in discovery()}
    pool = [(g, t) for g, t in pool if g not in disc]
    rng = random.Random(68)
    out = []
    for t in J.TASK_TYPES.values():
        out += [(g, t) for g in rng.sample(sorted(g for g, tt in pool if tt == t), 10)]
    return out


def smoke():
    sys.path.insert(0, str(HERE.parent / "g2"))
    import alf_run as R
    g = R.pick_games()
    return [g[10 * k] for k in range(6)]
