"""Round 5 (amendment 5, DEV). Needs lib/tzp2_table.json (z3_preserve.py --p2); written before it was run.

  1  TZ-P2 against G2 / T7 (G1 inputs); A-P with TZ-P2 (evidence "TZ", TZ progress) and the entries it uses
  2  for (disc, n) n in {50, 200, 1000} at N = 5, 6, 7 and (five, 1000) at N = 5 (the round-4 draws): B-EXCH
     (reference), B-GRAM and B-R1 fits; L0 / L1; hold-out at N = 8; law check against the exchange formula
  3  bound tables: B-EXCH x {S-obs, S-given}, B-R1 x S-given, B-GRAM x {S-obs, S-given, S-fact}; each against T7
     and TZ ("dangerous" as before)
  4  A-P' (L-tmpl, evidence "BX"): B-GRAM S-given (n = 50, 200, 1000), B-GRAM S-fact (disc-1000, five-1000),
     B-R1 S-given (disc-1000); certificates re-checked under TZ
  5  every constructed plan not judged before: J1-sym and J2

  python -I mission-05/experiments/pilots/run_r5.py      # writes r5.json
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
LIB = EXP / "lib"
sys.path.insert(0, str(EXP / "judge"))
sys.path.insert(0, str(LIB))
sys.path.insert(0, str(HERE))
import ap  # noqa: E402
import ap2  # noqa: E402
import bexch  # noqa: E402
import bgram  # noqa: E402
from run_cr import plan_key  # noqa: E402
from run_pa3 import goals, judge_plan  # noqa: E402
from run_r4 import compare, ttype, used_pairwise  # noqa: E402


def main():
    t0 = time.perf_counter()
    G = goals()
    t7 = json.loads((LIB / "t7_tables.json").read_text())
    tz = json.loads((LIB / "tz_table.json").read_text())
    tzp2 = json.loads((LIB / "tzp2_table.json").read_text())
    cr = json.loads((HERE / "cr.json").read_text())
    r4 = json.loads((HERE / "r4.json").read_text())
    cache = r4["judged"]
    n_cached = len(cache)
    out = {"label": "round 5 (amendment 5, DEV)"}

    # 1 TZ-P2
    tab = tzp2["table"]
    rows = [(a, g, e) for a, r in tab.items() for g, e in r.items()]
    out["TZ-P2"] = {"proved": sum(e["proved"] for _, _, e in rows),
                    "proved_with_real_cex": [f"{a} / {g}" for a, g, e in rows if e["proved"] and not e["ok_N7"]],
                    "nonvacuous_held": sum(1 for _, _, e in rows if e["ok_N7"] and e["states_N5"] > 0),
                    "nonvacuous_held_proved": sum(1 for _, _, e in rows if e["ok_N7"] and e["states_N5"] > 0 and e["proved"]),
                    "nonvacuous_held_not_proved": [f"{a} / {g}" for a, g, e in rows if e["ok_N7"] and e["states_N5"] > 0 and not e["proved"]],
                    "vacuous_held_proved": [f"{a} / {g}" for a, g, e in rows if e["ok_N7"] and e["states_N5"] == 0 and e["proved"]],
                    "z3_time_s": tzp2["z3_time_s"]}
    table = {"progress": tz["progress"],
             "preserves": {a: {g: {"ok": e["proved"], "states": e["states_N5"], "proved": e["proved"],
                                   "evidence": e["evidence"]} for g, e in r.items()} for a, r in tab.items()}}
    res = {}
    for gid, spec in G.items():
        c0 = time.process_time()
        r = ap.construct(spec, table, evidence="TZ")
        row = {"status": r["status"], "cpu": time.process_time() - c0}
        if r["status"] == "CONSTRUCTED":
            plan = [tuple(x) for x in r["plan"]]
            row["plan"] = plan
            row["used"] = [{"entry": f"{a} / {g}", "status": tab[a][g]["status"]} for a, g in used_pairwise(plan, spec)]
            row["failures"] = judge_plan(spec, plan, cache, plan_key(gid, plan))["failures"]
        res[gid] = row
    out["A-P"] = res
    print("A-P TZ-P2 constructed", sum(v["status"] == "CONSTRUCTED" for v in res.values()),
          "wrong", sum(v.get("failures", 0) > 0 for v in res.values()), flush=True)

    # 2 fits
    hold = bgram.holdout()
    variants = {"disc-50": (50, (5, 6, 7)), "disc-200": (200, (5, 6, 7)), "disc-1000": (1000, (5, 6, 7)),
                "five-1000": (1000, (5,))}
    recs, B = {}, {}
    for name, (n, sizes) in variants.items():
        rec, diag = bgram.run_variant(n, sizes, hold)
        recs[name] = rec
        classes = {}
        for row in rec.values():
            for k, r in row.items():
                key = f"{ttype(k)}:{r['gram'].law}"
                classes[key] = classes.get(key, 0) + 1
        B[name] = {"diag": diag, "gram_classes": classes,
                   "r1_contradictions": sum(1 for row in rec.values() for r in row.values() if r["r1"] and r["r1"]["contradiction"])}
        print("B", name, classes, "L0", diag["L0_failures"], "L1", diag["L1_failures"], "hold-out", diag["holdout"],
              "cpu", {k: round(x, 1) for k, x in diag["cpu"].items()}, flush=True)
    need = frozenset((a, k) for rec in recs.values() for a, row in rec.items() for k, r in row.items()
                     if not k.startswith("KD") and (r["exch"]["law"] == "LOC" or r["gram"].law in ("k", "tk")))
    given, gcpu = bexch.given_all(need)
    out["S_given_cpu_s"] = gcpu

    # 3 tables
    tabs = {}
    combos = [("exch", "obs"), ("exch", "given"), ("r1", "given"), ("gram", "obs"), ("gram", "given"), ("gram", "fact")]
    for name, rec in recs.items():
        B[name]["gram_law_check"] = bgram.gram_law_check(rec, given)
        B[name]["tables"] = {}
        for law, sup in combos:
            dmg, prog = bgram.tables(rec, law, sup, given)
            tabs[(name, law, sup)] = (dmg, prog)
            reasons = {}
            for row in dmg.values():
                for e in row["entries"].values():
                    reasons[e["reason"]] = reasons.get(e["reason"], 0) + 1
            B[name]["tables"][f"{law}/{sup}"] = {"vs_T7": compare(dmg, t7["damage"]), "vs_TZ": compare(dmg, tz["table"]),
                                                 "reasons": reasons, "progress_ok": sum(p["ok"] for p in prog.values())}
        print("B", name, {c: (B[name]["tables"][c]["vs_T7"]["dangerous"], round(B[name]["tables"][c]["vs_TZ"]["agreement"], 3))
                          for c in B[name]["tables"]}, flush=True)
    out["B"] = B

    # 4 A-P'
    tzset = sorted(g for g, r in cr["A-P'"]["TZ"].items() if r["status"] == "CONSTRUCTED")
    out["TZ_A-P'_constructed"] = tzset
    out["A-P'"] = {}
    runs = [("disc-50", "gram", "given"), ("disc-200", "gram", "given"), ("disc-1000", "gram", "given"),
            ("disc-1000", "gram", "fact"), ("five-1000", "gram", "fact"), ("disc-1000", "r1", "given")]
    for name, law, sup in runs:
        dmg, prog = tabs[(name, law, sup)]
        res = {}
        for gid, spec in G.items():
            c0 = time.process_time()
            r = ap2.construct(spec, "tmpl", dmg, prog, evidence="BX")
            row = {"status": r["status"], "cpu": time.process_time() - c0}
            if r["status"] == "CONSTRUCTED":
                plan = [tuple(x) for x in r["plan"]]
                row.update(plan=plan, weights=r["weights"])
                row["accepted_under_TZ"] = ap2.check_certificate(spec, [p[1] for p in r["plan"]], r["weights"], "tmpl",
                                                                 tz["table"], tz["progress"], "TZ")["accepted"]
                row["failures"] = judge_plan(spec, plan, cache, plan_key(gid, plan))["failures"]
            res[gid] = row
        out["A-P'"][f"{name}/{law}/{sup}"] = res
        print("A-P'", name, law, sup, "constructed", sum(v["status"] == "CONSTRUCTED" for v in res.values()),
              "wrong", sum(v.get("failures", 0) > 0 for v in res.values()),
              "rejected under TZ", sum(v["status"] == "CONSTRUCTED" and not v["accepted_under_TZ"] for v in res.values()),
              round(time.perf_counter() - t0, 1), "s", flush=True)
    out["newly_judged_plans"] = len(cache) - n_cached
    out["judged"] = cache
    out["costs"] = {"TZ-P2_z3_s": tzp2["z3_time_s"], "S_given_cpu_s": gcpu,
                    "B_cpu_s": {k: v["diag"]["cpu"] for k, v in B.items()},
                    "A-P_median_cpu_s": statistics.median(r["cpu"] for r in out["A-P"].values())}
    out["time_s"] = round(time.perf_counter() - t0, 1)
    (HERE / "r5.json").write_text(json.dumps(out, indent=1, default=str))
    print("done", out["time_s"], "s; newly judged plans", out["newly_judged_plans"])


if __name__ == "__main__":
    main()
