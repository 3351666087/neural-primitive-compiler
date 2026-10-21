"""RAND-DEV (amendment 7): ACH-DSL specs sampled uniformly from the language with a fixed seed, so that the round-7
evaluation set is not designed around the known gap. 20 valid, distinct specs per atom type.

  dest   types: a uniformly chosen non-empty subset of {EMPTY, OTHER} (+ PARTNER for ORDER); region: one base region
         allowed for the atom type, or (probability 0.3) the "and" of two different ones; pick: uniform over 4
  source region: a base region, LEFT_OF_DEST, RIGHT_OF_DEST or {"within": k} (k uniform 1..3), or (probability 0.3)
         the "and" of two different ones; pick: uniform over 5
  ZONE side uniform over any / left / right

  python -I rand_specs.py      # writes specs_rand.json
"""

from __future__ import annotations

import itertools
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "g3"))
import dsl  # noqa: E402

WINDOWS = ["WINDOW_G1", "NOT_WINDOW_G1", "WINDOW_G2", "NOT_WINDOW_G2"]
BASE = {"ORDER": ["ALL"] + WINDOWS, "ZONE": ["ALL", "ZONE", "NOT_ZONE"] + WINDOWS, "GROUP": ["ALL"] + WINDOWS}


def region(rng, pool):
    if rng.random() < 0.3:
        a, b = rng.sample(pool, 2)
        return {"and": [a, b]}
    return rng.choice(pool)


def sample(rng, t):
    tys = ["EMPTY", "OTHER"] + (["PARTNER"] if t == "ORDER" else [])
    subsets = [list(c) for r in range(1, len(tys) + 1) for c in itertools.combinations(tys, r)]
    src_pool = BASE[t] + ["LEFT_OF_DEST", "RIGHT_OF_DEST"] + [{"within": k, "of": "DEST"} for k in (1, 2, 3)]
    sp = {"atom_type": t,
          "dest": {"types": rng.choice(subsets), "region": region(rng, BASE[t]), "pick": rng.choice(dsl.PICKS)},
          "source": {"types": ["OWN"], "region": region(rng, src_pool), "pick": rng.choice(dsl.PICKS + ("nearest_to_dest",))}}
    if t == "ZONE":
        sp["side"] = rng.choice(["any", "left", "right"])
    return sp


def main():
    rng = random.Random(7)
    out, seen = [], set()
    for t in ("ORDER", "ZONE", "GROUP"):
        n = 0
        while n < 20:
            sp = sample(rng, t)
            key = json.dumps(sp, sort_keys=True)
            if key in seen:
                continue
            sp = {"id": f"R-{t[:3]}-{n:02d}", **sp}
            if dsl.validate(sp):
                continue
            seen.add(key)
            out.append(sp)
            n += 1
    (HERE / "specs_rand.json").write_text(json.dumps({"label": "RAND-DEV: seeded uniform samples of ACH-DSL (seed 7)",
                                                      "specs": out}, indent=1))
    print(len(out), "specs;", sum(len(dsl.instances(s)) for s in out), "instances;",
          sum(dsl.in_b_grammar(s) for s in out), "inside B's grammar")


if __name__ == "__main__":
    main()
