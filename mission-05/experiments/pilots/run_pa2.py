"""Pilot PA-2 (protocol section 9, amendment 1): interference, limits and bound memory, over the goal pool.

Per pool goal (91 goals: P2-*, P3-*, PN-*):
  A-P (2 variants) -> status; if constructed: J1-sym on V_train and V_unseen, J2 model checking (N = 6)
  A-P (1 variant)  -> status only (P2.3)
  if A-P refuses:  A-SAME (600 s); if it constructs, J1-sym on V_train and V_unseen; if it does not construct, A-FLAT
                   (600 s) and J1-sym likewise. A route "establishes a general policy" iff its construction has
                   0 J1-sym failures on V_train and V_unseen.
J1-net: 10 A-P constructions sampled with seed 9, 200 V_train + 50 per unseen size each.
Cue variants: chosen by pool.cue_variants (seed 7) from the two-atom goals A-P constructed; A-P + J1-sym.

  python -I mission-05/experiments/pilots/run_pa2.py      # writes pa2.json (updated after every goal)
"""

from __future__ import annotations

import json
import random
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
import pool as POOL  # noqa: E402
import aflat  # noqa: E402
import ap  # noqa: E402
import asame  # noqa: E402
import cirgen  # noqa: E402
from run_pa1 import judge_all, net_check  # noqa: E402

OUT = HERE / "pa2.json"


def cpu():
    return time.process_time()


def main():
    pool = json.loads((EXP / "judge" / "pool.json").read_text())["PA2"]
    out = json.loads(OUT.read_text()) if OUT.exists() else {"goals": {}, "cue": {}}
    out["label"] = "PA-2 (DEV): goal pool from the grammar"
    for gid, spec in pool.items():
        if gid in out["goals"]:
            continue
        t0 = time.perf_counter()
        train, unseen = INS.v_train(spec), INS.v_unseen(spec)
        rec = {"name": spec["name"]}
        c0 = cpu()
        r2 = ap.construct(spec, max_variants=2)
        rec["A-P"] = {k: v for k, v in r2.items() if k != "plan"}
        rec["A-P"]["cpu"] = cpu() - c0
        rec["A-P1"] = {k: v for k, v in ap.construct(spec, max_variants=1).items() if k != "plan"}
        if r2["status"] == "CONSTRUCTED":
            plan = [tuple(x) for x in r2["plan"]]
            rec["A-P"]["plan"] = plan
            mk = lambda N, p=plan: cirgen.emit(p, spec, N)
            rec["A-P"]["J1_sym"] = judge_all(mk, spec, train, unseen)
            rec["A-P"]["J2_mc6"] = CI.judge_set(mk(6), spec, INS.v_mc6(spec))
        else:
            c0 = cpu()
            s = asame.construct(spec, train)
            rec["A-SAME"] = {k: v for k, v in s.items() if k != "plan"}
            rec["A-SAME"]["cpu"] = cpu() - c0
            if s["status"] == "CONSTRUCTED":
                plan = [tuple(x) for x in s["plan"]]
                rec["A-SAME"]["plan"] = plan
                rec["A-SAME"]["J1_sym"] = judge_all(lambda N, p=plan: cirgen.emit(p, spec, N), spec, train, unseen)
            if s["status"] != "CONSTRUCTED" or rec["A-SAME"]["J1_sym"]["total_failures"] > 0:
                c0 = cpu()
                f = aflat.construct(spec, train, budget_s=600.0)
                rec["A-FLAT"] = {k: v for k, v in f.items() if k != "rules"}
                rec["A-FLAT"]["cpu"] = cpu() - c0
                if f["status"] == "CONSTRUCTED":
                    rl = f["rules"]
                    rec["A-FLAT"]["J1_sym"] = judge_all(lambda N, x=rl: cirgen.emit_flat(x, spec, N), spec, train, unseen)
        rec["wall_s"] = round(time.perf_counter() - t0, 1)
        out["goals"][gid] = rec
        OUT.write_text(json.dumps(out, indent=1, default=str))
        print(gid, spec["name"], "A-P", r2["status"], "| A-P1", rec["A-P1"]["status"],
              "| A-SAME", rec.get("A-SAME", {}).get("status"), "| A-FLAT", rec.get("A-FLAT", {}).get("status"),
              rec["wall_s"], "s", flush=True)
    # J1-net on 10 sampled A-P constructions
    if "J1_net" not in out:
        built = sorted(g for g, r in out["goals"].items() if r["A-P"]["status"] == "CONSTRUCTED")
        rng = random.Random(9)
        res = {}
        for gid in rng.sample(built, min(10, len(built))):
            spec = pool[gid]
            plan = [tuple(x) for x in out["goals"][gid]["A-P"]["plan"]]
            res[gid] = net_check(plan, spec, INS.v_train(spec), INS.v_unseen(spec))
            print("J1-net", gid, res[gid], flush=True)
        out["J1_net"] = res
        OUT.write_text(json.dumps(out, indent=1, default=str))
    # cue variants
    built = [g for g, r in out["goals"].items() if r["A-P"]["status"] == "CONSTRUCTED"]
    cues = POOL.cue_variants(pool, built)
    for cid, spec in cues.items():
        if cid in out["cue"]:
            continue
        train, unseen = INS.v_train(spec), INS.v_unseen(spec)
        r = ap.construct(spec)
        rec = {"from": spec["from"], "name": spec["name"], "A-P": {k: v for k, v in r.items() if k != "plan"}}
        if r["status"] == "CONSTRUCTED":
            plan = [tuple(x) for x in r["plan"]]
            rec["A-P"]["plan"] = plan
            rec["A-P"]["global_verifications"] = 0
            rec["A-P"]["J1_sym"] = judge_all(lambda N, p=plan: cirgen.emit(p, spec, N), spec, train, unseen)
        out["cue"][cid] = rec
        OUT.write_text(json.dumps(out, indent=1, default=str))
        print(cid, r["status"], rec["A-P"].get("J1_sym", {}).get("total_failures"), flush=True)


if __name__ == "__main__":
    main()
