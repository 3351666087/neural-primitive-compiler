"""E4 (amendment 4): exhaustive counterexample search at N = 8 for the pairwise-preservation entries that hold at
N <= 7 (T7) but that TZ-P1 does not prove. Conditions as in libval.py; the satisfiability checks run only when the
pattern breaks (same result as checking every state).

  python -I libval8.py        # needs tzp_table.json; writes n8_check.json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from libval import ROLE, _parse, achiever_instances, states  # noqa: E402
from model import holds, reloc, satisfiable, select  # noqa: E402


def main():
    t0, c0 = time.perf_counter(), time.process_time()
    tzp = json.loads((HERE / "tzp_table.json").read_text())["tables"]["TZ-P1"]
    todo = {akey: [(gk, _parse(gk)) for gk, e in row.items() if e["ok_N7"] and not e["proved"]] for akey, row in tzp.items()}
    todo = {k: v for k, v in todo.items() if v}
    ach = [(k, a, v) for k, a, v in achiever_instances() if k in todo]
    cex = {k: {gk: None for gk, _ in todo[k]} for k in todo}
    N = 8
    sat_calls = 0
    for cells, haz, fixed in states(N):
        if not any(cells[p] == 0 and not haz[p] for p in range(N)):
            continue
        sc = {}
        for akey, a, v in ach:
            if holds(a, cells, ROLE):
                continue
            sel = select(a, v, cells, haz, True, fixed, ROLE)
            r = reloc(cells, 0, sel[0], sel[1], haz, True) if sel else None
            if r is None:
                continue
            for gk, gp in todo[akey]:
                if cex[akey][gk] is not None:
                    continue
                if holds(gp, cells, ROLE) and not holds(gp, r[0], ROLE):
                    if akey not in sc:
                        sat_calls += 1
                        sc[akey] = satisfiable([a], cells, haz, True, fixed, ROLE)
                    if sc[akey]:
                        sat_calls += 1
                        if satisfiable([a, gp], cells, haz, True, fixed, ROLE):
                            cex[akey][gk] = {"cells": cells, "haz": haz, "fixed": fixed, "after": r[0]}
    out = {"label": "E4: exhaustive counterexample search at N = 8 (amendment 4)", "entries": cex,
           "checked": sum(len(v) for v in todo.values()), "refuted": sum(c is not None for v in cex.values() for c in v.values()),
           "sat_calls": sat_calls, "time_s": round(time.perf_counter() - t0, 1), "cpu_s": round(time.process_time() - c0, 1)}
    (HERE / "n8_check.json").write_text(json.dumps(out, indent=1, default=str))
    print("checked", out["checked"], "refuted", out["refuted"], "cpu", out["cpu_s"])


if __name__ == "__main__":
    main()
