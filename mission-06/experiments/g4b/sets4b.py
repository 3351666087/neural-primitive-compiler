"""JUDGE SIDE goal sets for G4b (EXPERIMENT_PRE_REGISTRATION.md section G4b). One composite goal per room.
  dev()       rooms of the 60 Gate 3 evaluation games (train split, development): 10 goals per family, seed 80
  heldout()   rooms of valid_unseen (official held-out): 15 goals per family, seed 81
  b2()        6 per family of heldout(), seed 82
Each returns [(game file, family, spec)]; specs are cached judge-side in run/ (gitignored)."""

import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "g1"))
sys.path.insert(0, str(HERE.parent / "g4"))
DATA = str(HERE.parents[1] / "env" / "alfworld-data")
RUN = HERE / "run"


def _build(games, per_family, seed):
    import alf_judge as J
    import cmp_env as E
    wl = E.whitelists(J.list_games(DATA, "train"))
    rng = random.Random(seed)
    order = list(range(len(games)))
    rng.shuffle(order)
    out, used = [], set()
    for fam in E.FAMILIES:
        n = 0
        for i in order:
            if n == per_family:
                break
            if i in used:
                continue
            spec = E.make_goal(games[i][0], fam, rng, wl)
            if spec:
                out.append((games[i][0], fam, spec))
                used.add(i)
                n += 1
    return out


def _cached(name, build):
    RUN.mkdir(exist_ok=True)
    f = RUN / f"{name}.json"
    if not f.exists():
        f.write_text(json.dumps(build()))
    return [tuple(x) for x in json.loads(f.read_text())]


def dev():
    import games4 as G
    return _cached("dev", lambda: _build(G.dev60(), 10, 80))


def heldout():
    import games4 as G
    return _cached("heldout", lambda: _build(G.heldout(), 15, 81))


def b2():
    h = heldout()
    rng = random.Random(82)
    sel = []
    for fam in ("F2", "F3", "F3L", "F4"):
        idx = [i for i, x in enumerate(h) if x[1] == fam]
        sel += sorted(rng.sample(idx, 6))
    return sel
