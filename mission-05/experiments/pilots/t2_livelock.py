"""Minimal counterexample for T2 = GROUP(1) & ORDER(1,2) & NO_DROP_HAZARD (POST-HOC diagnosis after PA-1).

Instance: N = 5, cells (1, 0, 1, 2, 0), hazard on cell 1, agent at 0. The goal is feasible (the judge's BFS finds a
plan). Every priority plan over the library achievers (both orders x both variants), emitted as a controller and
run by the judge (J1-sym), fails on it; the macro trace shows the two-cycle between GROUP's window choice and
ORDER's swap.

  python -I mission-05/experiments/pilots/t2_livelock.py      # writes t2_livelock.json
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "judge"))
sys.path.insert(0, str(HERE.parent / "lib"))
import cir_interp as CI  # noqa: E402
from feasibility import bfs_feasible, feasible  # noqa: E402
import cirgen  # noqa: E402
from model import holds, reloc, select  # noqa: E402

INST = {"N": 5, "cells": (1, 0, 1, 2, 0), "hazards": (0, 1, 0, 0, 0), "agent": 0, "binding": {}}


def main():
    spec = json.loads((HERE.parent / "judge" / "pool.json").read_text())["PA1"]["T2"]
    out = {"instance": INST, "feasible_exact": feasible(spec, INST), "feasible_bfs": bfs_feasible(spec, INST), "plans": {}}
    V = {"ORDER": ("O1", "O2"), "GROUP": ("G1", "G2")}
    for perm in itertools.permutations(spec["atoms"]):
        for vs in itertools.product(*[V[a[0]] for a in perm]):
            plan = list(zip(perm, vs))
            o, s, _ = CI.run_closed_loop(cirgen.emit(plan, spec, 5), spec, [INST])
            out["plans"][" > ".join(f"{a[0]}:{v}" for a, v in plan)] = {"outcome": o[0], "steps": s[0]}
    # macro trace for GROUP:G1 > ORDER:O1
    cells, trace = INST["cells"], []
    plan = [(spec["atoms"][0], "G1"), (spec["atoms"][1], "O1")]
    for _ in range(6):
        first = next(((a, v) for a, v in plan if not holds(a, cells, {})), None)
        if first is None:
            break
        x, y = select(first[0], first[1], cells, INST["hazards"], True, set(), {})
        cells = reloc(cells, 0, x, y, INST["hazards"], True)[0]
        trace.append({"achiever": f"{first[0][0]}:{first[1]}", "x": x, "y": y, "cells_after": cells})
    out["macro_trace_GROUP_G1_then_ORDER_O1"] = trace
    (HERE / "t2_livelock.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
