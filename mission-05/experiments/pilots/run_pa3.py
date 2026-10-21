"""PA-3 (amendment 2, DEV): shared-potential certificates (A-P', L-tmpl and L-lin) on the PA-1 targets and the PA-2
pool. A-SAME and A-P results are taken from G2 (pa1.json, pa2.json), not re-run. Every distinct constructed plan
is judged with J1-sym (V_train, V_unseen) and J2 (all N = 6 instances).

  python -I mission-05/experiments/pilots/run_pa3.py        # writes pa3.json (updated after every goal)
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(EXP / "judge"))
sys.path.insert(0, str(EXP / "lib"))
sys.path.insert(0, str(HERE))
import cir_interp as CI  # noqa: E402
import instances as INS  # noqa: E402
import ap2  # noqa: E402
import cirgen  # noqa: E402
from run_pa1 import judge_all  # noqa: E402

OUT = HERE / "pa3.json"


def goals():
    pool = json.loads((EXP / "judge" / "pool.json").read_text())
    g = {k: v for k, v in pool["PA1"].items()}
    g.update(pool["PA2"])
    return g


def judge_plan(spec, plan, cache, key):
    if key in cache:
        return cache[key]
    train, unseen = INS.v_train(spec), INS.v_unseen(spec)
    mk = lambda N: cirgen.emit(plan, spec, N)
    res = {"J1_sym": judge_all(mk, spec, train, unseen), "J2_mc6": CI.judge_set(mk(6), spec, INS.v_mc6(spec))}
    res["failures"] = res["J1_sym"]["total_failures"] + res["J2_mc6"]["failures"]
    cache[key] = res
    return res


def main():
    G = goals()
    out = json.loads(OUT.read_text()) if OUT.exists() else {"goals": {}, "judged": {}}
    out["label"] = "PA-3 (DEV): shared-potential certificates"
    damage, progress = ap2.load_damage(), ap2.load_progress()
    for gid, spec in G.items():
        if gid in out["goals"]:
            continue
        t0 = time.perf_counter()
        rec = {"name": spec["name"]}
        for mode in ("tmpl", "lin"):
            c0 = time.process_time()
            r = ap2.construct(spec, mode, damage, progress)
            r["cpu"] = time.process_time() - c0
            if r["status"] == "CONSTRUCTED":
                plan = [tuple(x) for x in r["plan"]]
                key = gid + "|" + json.dumps(plan)
                j = judge_plan(spec, plan, out["judged"], key)
                r["judge_key"] = key
                r["failures"] = j["failures"]
            rec[mode] = r
        rec["wall_s"] = round(time.perf_counter() - t0, 1)
        out["goals"][gid] = rec
        OUT.write_text(json.dumps(out, indent=1, default=str))
        print(gid, spec["name"], "| tmpl", rec["tmpl"]["status"], rec["tmpl"].get("failures"), rec["tmpl"].get("reasons"),
              "| lin", rec["lin"]["status"], rec["lin"].get("failures"), rec["wall_s"], "s", flush=True)


if __name__ == "__main__":
    main()
