"""G0-S1, G0-S2: certified controllers outside the judged range (Mission 06). AUDIT (uses the judge's environment).

Plans: every distinct plan of the Mission 05 G3 and G4 held-out runs on the "specs" routes (A-P', A-P), and every plan
of G0-C1 (oracle_free.json, variant A++r). Each plan is emitted as CIR (cir_dsl.emit_dsl) and run by J1-sym
(judge/cir_interp.judge_set) on feasible instances:
  S1  N = 20: 100 instances from the judge's own generator (instances.random_instance, Kmax = 7, hazards 0..2)
  S2  N = 9 and N = 12: 100 instances each from the same generator with K up to N - 1 and hazards 0..4 (legal LINE
      states outside the judged distribution; exploratory)
Seeds: random.Random(f"S1|{goal}|{plan}") etc.

  python -I stress.py        # writes stress.json
"""

from __future__ import annotations

import json
import random
import sys
import time
from multiprocessing import Pool
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import aud  # noqa: E402

EXP = aud.EXP
for p in ("lib", "judge", "pilots", "g3"):
    sys.path.insert(0, str(EXP / p))
import cir_interp as CI  # noqa: E402
import instances as INS  # noqa: E402
from cir_dsl import emit_dsl  # noqa: E402
from env import hazard_rule  # noqa: E402
from feasibility import feasible  # noqa: E402
from run_pa3 import goals  # noqa: E402

D = aud.load()
BY = D["by_id"]
G = goals()


def wide_instance(spec, N, rng, hmax=4):
    for _ in range(10_000):
        K = rng.randint(1, N - 1)
        pal = INS.goal_colours(spec)
        cols = [rng.choice(pal) for _ in range(K)]
        if rng.random() < 0.3:
            cols = [INS.DISTRACTOR if rng.random() < 0.3 else c for c in cols]
        pos = rng.sample(range(N), K)
        cells = [0] * N
        for p, c in zip(pos, cols):
            cells[p] = c
        haz = [0] * N
        if hazard_rule(spec):
            free = [p for p in range(N) if cells[p] == 0]
            for p in rng.sample(free, min(len(free), rng.randint(0, hmax))):
                haz[p] = 1
        inst = INS._inst(N, cells, haz, rng.randrange(N), rng.choice(INS.bindings(spec)))
        if feasible(spec, inst):
            return inst
    return None


def plans():
    out = {}
    for f in (EXP / "g3" / "heldout_run.json", EXP / "g4" / "heldout_run.json"):
        for route, res in json.loads(f.read_text())["constructions"].items():
            if not route.startswith("specs/"):
                continue
            for gid, r in res.items():
                if r["status"] == "CONSTRUCTED":
                    out.setdefault((gid, json.dumps(r["plan"])), []).append(f"{f.parent.name}:{route}")
    for route, res in json.loads((HERE / "oracle_free.json").read_text())["constructions"].items():
        if "/A++r/" not in route:
            continue
        for gid, r in res.items():
            if r["status"] == "CONSTRUCTED":
                out.setdefault((gid, json.dumps(r["plan"])), []).append(f"G0:{route}")
    return out


def one(x):
    gid, plan = x
    spec = G[gid]
    pl = [(a, BY[i]) for a, i in json.loads(plan)]
    res = {}
    rng = random.Random(f"S1|{gid}|{plan}")
    insts = [INS.random_instance(spec, 20, 7, rng) for _ in range(100)]
    res["S1_N20"] = CI.judge_set(emit_dsl(pl, spec, 20), spec, insts)
    for N in (9, 12):
        rng = random.Random(f"S2|{N}|{gid}|{plan}")
        insts = [i for i in (wide_instance(spec, N, rng) for _ in range(100)) if i is not None]
        r = CI.judge_set(emit_dsl(pl, spec, N), spec, insts)
        r["K_max"] = max(sum(1 for c in i["cells"] if c) for i in insts)
        r["H_max"] = max(sum(i["hazards"]) for i in insts)
        res[f"S2_N{N}"] = r
    return gid + "|" + plan, res


def main():
    t0 = time.perf_counter()
    P = plans()
    with Pool(8) as p:
        res = dict(p.map(one, sorted(P), chunksize=1))
    agg = {}
    for v in res.values():
        for grp, r in v.items():
            a = agg.setdefault(grp, {"plans": 0, "episodes": 0, "failures": 0, "plans_failing": 0, "outcomes": {}})
            a["plans"] += 1
            a["episodes"] += r["n"]
            a["failures"] += r["failures"]
            a["plans_failing"] += r["failures"] > 0
            for o, c in r["counts"].items():
                a["outcomes"][o] = a["outcomes"].get(o, 0) + c
    out = {"label": "G0-S1/S2 (Mission 06): certified controllers outside the judged range", "aggregate": agg,
           "sources": {f"{g}|{p}": s for (g, p), s in P.items()}, "results": res,
           "time_s": round(time.perf_counter() - t0, 1)}
    (HERE / "stress.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(agg, indent=1), "time", out["time_s"])


if __name__ == "__main__":
    main()
