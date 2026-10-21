"""Damage tables (amendment 2): for every achiever instance and template pattern, the maximum one-step increase of
the template at N = 3, 4, 5 (exhaustive over the libval.py state distribution, restricted to states where the
achiever's atom is violated but satisfiable on its own and a spare cell exists). Classification: bounded with value
max_N5 if max_N5 <= max_N4, else growing (infinite). Also usable with sampled states (B-1', bdisc.py).

  python -I libval2.py        # writes damage_table.json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from libval import ROLE, achiever_instances, states  # noqa: E402
from model import holds, reloc, satisfiable, select  # noqa: E402
from potentials import evaluate, patterns  # noqa: E402


def eligible(a, cells, haz, fixed, b=ROLE):
    if holds(a, cells, b):
        return False
    if not any(cells[p] == 0 and not haz[p] for p in range(len(cells))):
        return False
    return satisfiable([a], cells, haz, True, fixed, b)


def deltas(a, v, cells, haz, fixed, keys, b=ROLE):
    sel = select(a, v, cells, haz, True, fixed, b)
    if sel is None:
        return None
    r = reloc(cells, 0, sel[0], sel[1], haz, True)
    if r is None:
        return None
    after = r[0]
    return {k: evaluate(k, after, haz, True, fixed, b) - evaluate(k, cells, haz, True, fixed, b) for k in keys}


def classify(per_n):
    """per_n: {N: max delta or None}. Bounded iff the value at the largest N does not exceed the one below it."""
    ns = sorted(n for n, v in per_n.items() if v is not None)
    if len(ns) < 2:
        return None
    hi, lo = per_n[ns[-1]], per_n[ns[-2]]
    return max(per_n[n] for n in ns) if hi <= lo else "inf"


def main():
    t0 = time.perf_counter()
    table = {}
    for key, a, v in achiever_instances():
        keys = patterns(a[0])
        per = {k: {} for k in keys}
        n_states = {}
        for N in (3, 4, 5):
            mx = {k: None for k in keys}
            cnt = 0
            for cells, haz, fixed in states(N):
                if not eligible(a, cells, haz, fixed):
                    continue
                d = deltas(a, v, cells, haz, fixed, keys)
                if d is None:
                    continue
                cnt += 1
                for k, x in d.items():
                    if mx[k] is None or x > mx[k]:
                        mx[k] = x
            n_states[N] = cnt
            for k in keys:
                per[k][N] = mx[k]
        table[key] = {"states": n_states, "entries": {k: {"max_by_N": per[k], "bound": classify(per[k])} for k in keys}}
        print(key, n_states, round(time.perf_counter() - t0, 1), flush=True)
    out = {"label": "damage table: max one-step template increase, exhaustive at N = 3..5; bounded iff max(N=5) <= max(N=4) [P]",
           "table": table, "time_s": round(time.perf_counter() - t0, 1)}
    (HERE / "damage_table.json").write_text(json.dumps(out, indent=1))
    print("time", out["time_s"])


if __name__ == "__main__":
    main()
