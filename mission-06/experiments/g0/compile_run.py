"""G0-K1: Z3 lemmas (compile_lemmas.py) plus the premise checker (compile_check.py) on every network compiled from the
plans of Mission 05 (G3, G4: every route; round 8: A routes) and of G0-C1 (oracle_free.json), at N = 5, 6, 7, 9, 12, 15.

  python -I compile_run.py        # writes compile_run.json
"""

from __future__ import annotations

import json
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
import compile_lemmas  # noqa: E402
from cir_dsl import emit_dsl  # noqa: E402
from compile_check import check  # noqa: E402
from compile_cir import compile_cir  # noqa: E402
from run_pa3 import goals  # noqa: E402

D = aud.load()
BY = D["by_id"]
G = goals()
NS = (5, 6, 7, 9, 12, 15)


def plans():
    out = {}
    for f in (EXP / "g3" / "heldout_run.json", EXP / "g4" / "heldout_run.json"):
        for route, res in json.loads(f.read_text())["constructions"].items():
            for gid, r in res.items():
                if r["status"] == "CONSTRUCTED":
                    out.setdefault((gid, json.dumps(r["plan"])), []).append(f"{f.parent.name}:{route}")
    for route, res in json.loads((EXP / "r8" / "r8.json").read_text())["constructions"].items():
        for gid, r in res.items():
            if r["status"] == "CONSTRUCTED":
                out.setdefault((gid, json.dumps(r["plan"])), []).append(f"r8:{route}")
    of = HERE / "oracle_free.json"
    if of.exists():
        for route, res in json.loads(of.read_text())["constructions"].items():
            for gid, r in res.items():
                if r["status"] == "CONSTRUCTED":
                    out.setdefault((gid, json.dumps(r["plan"])), []).append(f"G0:{route}")
    return out


def one(x):
    gid, plan = x
    pl = [(a, BY[i]) for a, i in json.loads(plan)]
    res = {}
    for N in NS:
        prog = emit_dsl(pl, G[gid], N)
        net, info = compile_cir(prog)
        pr = check(prog, net, info)
        res[N] = {"problems": pr[:5], "D": info["D"], "neurons": info["neurons"], "max_comb_depth": info["max_comb_depth"]}
    return gid + "|" + plan, res


def main():
    t0 = time.perf_counter()
    lem = compile_lemmas.lemmas()
    P = plans()
    with Pool(8) as p:
        res = dict(p.map(one, sorted(P), chunksize=1))
    bad = {k: {N: r["problems"] for N, r in v.items() if r["problems"]} for k, v in res.items()}
    bad = {k: v for k, v in bad.items() if v}
    out = {"label": "G0-K1 (Mission 06): compile_cir lemmas and per-network premises", "lemmas": lem,
           "plans": len(P), "networks": len(P) * len(NS), "networks_with_problems": sum(len(v) for v in bad.values()),
           "problems": bad, "sources": {f"{g}|{p}": s for (g, p), s in P.items()},
           "results": res, "time_s": round(time.perf_counter() - t0, 1)}
    (HERE / "compile_run.json").write_text(json.dumps(out, indent=1, default=str))
    print("lemmas", [(r["lemma"], r["status"]) for r in lem])
    print("plans", len(P), "networks", out["networks"], "with problems", out["networks_with_problems"], "time", out["time_s"])


if __name__ == "__main__":
    main()
