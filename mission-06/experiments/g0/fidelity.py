"""G0-M1: does the constructor's macro model (select_dsl + relocation as an exchange) agree with the environment driven
by the compiled selection (emit_dsl CIR, judge's BatchEnv)? AUDIT: uses both sides.

For every AUD instance that is applicable in the N <= 7 truth (aud_truth.json): the single-atom goal with role colours
(A1 = 1, A2 = 2) and the one-step plan [(atom, spec)], under two safety variants (the judge's palette holds only goal
and safety colours plus distractor 4): "fixed" = NO_DROP_HAZARD and NO_PICK 4 (colour 4 objects are NO_PICK), and
"movable" = NO_DROP_HAZARD only (colour 4 objects are OTHER). Instances: every feasible instance at N = 5 with K <= 3 (instances.enumerate_all) and 100 feasible
random instances at N = 9 (instances.random_instance, Kmax 7; seed f"M1|{key}").
Environment trace: the cells after every step in which an object was dropped (hand empty again).
Model trace: from the initial cells, while the atom is violated: (d, s) = select_dsl; one relocation if d is empty
(cells after moving s -> d); else three (d -> spare, s -> d, spare -> s; spare = leftmost non-hazard empty cell).
Agreement: identical traces, and (environment outcome SUCCESS) == (the model ends with the atom holding).

  python -I fidelity.py        # writes fidelity.json
"""

from __future__ import annotations

import json
import random
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import aud  # noqa: E402

EXP = aud.EXP
for p in ("lib", "judge", "g3"):
    sys.path.insert(0, str(EXP / p))
import dsl  # noqa: E402
import instances as INS  # noqa: E402
from cir_dsl import emit_dsl  # noqa: E402
from cir_interp import Interp  # noqa: E402
from env import BatchEnv  # noqa: E402
from libval import ROLE  # noqa: E402
from model import allowed_free, holds  # noqa: E402

D = aud.load()
BY = D["by_id"]


def concrete(atom):
    return [atom[0], 1, 2] if atom[0] == "ORDER" else ([atom[0], 1] + list(atom[2:]))


def model_trace(spec, atom, cells, haz, fixed=(4,), limit=200):
    cells = tuple(cells)
    tr = []
    for _ in range(limit):
        if holds(atom, cells, ROLE):
            return tr, True
        sel = dsl.select_dsl(spec, atom, cells, haz, True, fixed, ROLE)
        if sel is None:
            return tr, False
        x, y = sel
        c = list(cells)
        if c[x] == 0:
            c[x], c[y] = c[y], 0
            tr.append(tuple(c))
        else:
            free = allowed_free(c, haz, True)
            if not free:
                return tr, False
            s = free[0]
            c[s], c[x] = c[x], 0
            tr.append(tuple(c))
            c[x], c[y] = c[y], 0
            tr.append(tuple(c))
            c[y], c[s] = c[s], 0
            tr.append(tuple(c))
        cells = tuple(c)
    return tr, False


def env_traces(goal, prog, insts):
    env = BatchEnv(goal, insts)
    it = Interp(prog, env.B)
    traces = [[] for _ in insts]
    while not env.done.all():
        acts, conflict = it.step(env.observation())
        env._finish(conflict, "REG_CONFLICT")
        before = env.cells.copy()
        live = ~env.done
        env.act(acts)
        dropped = live & (env.hand == 0) & (env.cells != before).any(1)
        for b in np.flatnonzero(dropped):
            traces[b].append(tuple(int(v) for v in env.cells[b]))
    return traces, env.outcome.tolist()


def one(x):
    k, atom = x
    spec = BY[k.split("|")[0]]
    out = {}
    for var, safety, fixed in (("fixed", [["NO_DROP_HAZARD"], ["NO_PICK", 4]], (4,)), ("movable", [["NO_DROP_HAZARD"]], ())):
      goal = {"atoms": [concrete(atom)], "safety": safety, "cue": [], "name": f"M1 {k} {var}"}
      plan = [(goal["atoms"][0], spec)]
      for N, insts in ((5, INS.enumerate_all(goal, 5, 3)),
                       (9, [INS.random_instance(goal, 9, 7, random.Random(f"M1|{k}|{var}")) for _ in range(100)])):
        prog = emit_dsl(plan, goal, N)
        traces, outcomes = env_traces(goal, prog, insts)
        bad = []
        for inst, et, o in zip(insts, traces, outcomes):
            mt, ok = model_trace(spec, atom, inst["cells"], inst["hazards"], fixed)
            if et != mt or (o == "SUCCESS") != ok:
                bad.append({"cells": list(inst["cells"]), "haz": list(inst["hazards"]), "agent": inst["agent"],
                            "env_outcome": o, "env_trace": et[:6], "model_trace": mt[:6], "model_success": ok})
        out[f"{var}_N{N}"] = {"episodes": len(insts), "disagreements": len(bad), "examples": bad[:3],
                              "outcomes": {o: outcomes.count(o) for o in set(outcomes)}}
    return k, out


def main():
    t0 = time.perf_counter()
    tr = json.loads((HERE / "aud_truth.json").read_text())["truth"]
    allinst = [(k, a) for v in D["inst"].values() for k, a in v if tr[k]["applicability_cex"] is None]
    with Pool(8) as p:
        res = dict(p.map(one, allinst, chunksize=1))
    tot = {g: {"episodes": sum(r[g]["episodes"] for r in res.values()),
               "disagreements": sum(r[g]["disagreements"] for r in res.values()),
               "instances_disagreeing": sorted(k for k, r in res.items() if r[g]["disagreements"])}
           for g in ("fixed_N5", "fixed_N9", "movable_N5", "movable_N9")}
    out = {"label": "G0-M1 (Mission 06): macro model vs environment + compiled selection", "instances": len(allinst),
           "total": tot, "results": res, "time_s": round(time.perf_counter() - t0, 1)}
    (HERE / "fidelity.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(tot, indent=1), "time", out["time_s"])


if __name__ == "__main__":
    main()
