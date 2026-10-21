"""POST-HOC (after B-1'): exhaustive search at N = 6 for states where an entry that the N <= 5 damage table certified
as bounded is exceeded. Entries: those the B-DISC table (n = 1000) flagged as growing while the given table had a
finite bound. A witness is a state (same eligibility conditions as the table) where one relocation raises the
template by more than the given bound.

  python -I mission-05/experiments/pilots/b1_witness.py      # writes b1_witness.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))
import bdisc  # noqa: E402
from libval import achiever_instances, states  # noqa: E402
from libval2 import deltas, eligible  # noqa: E402


def main():
    given = json.loads((HERE.parent / "lib" / "damage_table.json").read_text())["table"]
    learned, _ = bdisc.learn(1000, "disc", seed=11)
    num = lambda b: float("inf") if b in (None, "inf") else b
    flagged = [(a, k) for a, row in given.items() for k, e in row["entries"].items()
               if num(learned[a]["entries"][k]["bound"]) > num(e["bound"])]
    ach = {key: (atom, v) for key, atom, v in achiever_instances()}
    out = {}
    for akey, k in flagged:
        atom, v = ach[akey]
        bound = given[akey]["entries"][k]["bound"]
        wit, worst = None, None
        for cells, haz, fixed in states(6):
            if not eligible(atom, cells, haz, fixed):
                continue
            d = deltas(atom, v, cells, haz, fixed, [k])
            if d is None:
                continue
            if worst is None or d[k] > worst:
                worst = d[k]
            if d[k] > bound and wit is None:
                wit = {"cells": cells, "hazards": haz, "fixed": fixed, "delta": d[k]}
        out[f"{akey} / {k}"] = {"given_bound": bound, "max_at_N6_exhaustive": worst, "witness": wit}
        print(akey, k, "given", bound, "N=6 max", worst, "witness" if wit else "-", flush=True)
    (HERE / "b1_witness.json").write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
