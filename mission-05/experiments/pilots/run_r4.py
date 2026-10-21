"""Round 4 (amendment 4, DEV). Needs lib/tzp_table.json (z3_preserve.py) and lib/n8_check.json (libval8.py); written
before either was run.

  1  TZ-P0 / TZ-P1 against G2 and T7 (E1-E3 inputs)
  2  A-P with TZ-P0 and TZ-P1 (evidence "TZ", TZ progress); the entries each certificate uses
  3  B-EXCH fits: (disc, n) for n in {50, 200, 1000} at N = 5, 6, 7 and (five, 1000) at N = 5; S-given supports;
     S-obs and S-given bound tables; law check against the exchange formula; hold-out at N = 8
  4  every B table against T7 and TZ ("dangerous" as in rounds 2-3), split by template type
  5  A-P' (L-tmpl) with B-EXCH tables (evidence "BX"): S-obs n = 1000, S-given n = 50, 200, 1000, and the B-EXCH-5
     tables; every certificate re-checked under TZ
  6  every constructed plan not judged before: J1-sym and J2 (as in rounds 2-3)

  python -I mission-05/experiments/pilots/run_r4.py      # writes r4.json
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
from run_cr import plan_key  # noqa: E402
from run_pa3 import goals, judge_plan  # noqa: E402

INF = float("inf")


def num(b):
    return INF if b in (None, "inf") else b


def ttype(k):
    return "KD" if k.startswith("KD") else k.split("(")[0]


def compare(learned, ref):
    out = {"entries": 0, "equal": 0, "dangerous": 0, "conservative": 0, "dangerous_by_type": {}, "dangerous_list": []}
    for a, row in ref.items():
        for k, e in row["entries"].items():
            g, l = num(e["bound"]), num(learned[a]["entries"][k]["bound"])
            out["entries"] += 1
            if g == l:
                out["equal"] += 1
            elif l < g:
                out["dangerous"] += 1
                out["dangerous_by_type"][ttype(k)] = out["dangerous_by_type"].get(ttype(k), 0) + 1
                out["dangerous_list"].append(f"{a} / {k}: learned {l}, reference {g}")
            else:
                out["conservative"] += 1
    out["agreement"] = out["equal"] / out["entries"]
    out["dangerous_fraction"] = out["dangerous"] / out["entries"]
    return out


def used_pairwise(plan, spec):
    fixed = {s[1] for s in spec["safety"] if s[0] == "NO_PICK"}
    u = []
    for j in range(len(plan)):
        aj, vj = plan[j]
        for i in range(j):
            u.append((ap.achiever_key(aj, vj), ap.pattern_key(plan[i][0], aj, fixed)))
    return u


def main():
    t0 = time.perf_counter()
    G = goals()
    t7 = json.loads((LIB / "t7_tables.json").read_text())
    tz = json.loads((LIB / "tz_table.json").read_text())
    tzp = json.loads((LIB / "tzp_table.json").read_text())
    n8 = json.loads((LIB / "n8_check.json").read_text())
    cr = json.loads((HERE / "cr.json").read_text())
    cache = cr["judged"]
    n_cached = len(cache)
    out = {"label": "round 4 (amendment 4, DEV)"}

    # 1 TZ-P against G2 / T7
    tp = {}
    for var, tab in tzp["tables"].items():
        rows = [(a, g, e) for a, r in tab.items() for g, e in r.items()]
        tp[var] = {"proved": sum(e["proved"] for _, _, e in rows),
                   "proved_with_real_cex": [f"{a} / {g}" for a, g, e in rows if e["proved"] and not e["ok_N7"]],
                   "nonvacuous_held": sum(1 for _, _, e in rows if e["ok_N7"] and e["states_N5"] > 0),
                   "nonvacuous_held_proved": sum(1 for _, _, e in rows if e["ok_N7"] and e["states_N5"] > 0 and e["proved"]),
                   "nonvacuous_held_not_proved": [f"{a} / {g}" for a, g, e in rows if e["ok_N7"] and e["states_N5"] > 0 and not e["proved"]],
                   "vacuous_held_proved": [f"{a} / {g}" for a, g, e in rows if e["ok_N7"] and e["states_N5"] == 0 and e["proved"]],
                   "vacuous_held_not_proved": [f"{a} / {g}" for a, g, e in rows if e["ok_N7"] and e["states_N5"] == 0 and not e["proved"]],
                   "status": {s: sum(e["status"] == s for _, _, e in rows) for s in ("PROVED", "NOT_PROVED", "UNKNOWN")}}
    out["TZ-P"] = tp
    out["N8"] = {"checked": n8["checked"], "refuted": n8["refuted"], "cpu_s": n8["cpu_s"]}

    # 2 A-P with TZ-P
    out["A-P"] = {}
    for var, tab in tzp["tables"].items():
        table = {"progress": tz["progress"],
                 "preserves": {a: {g: {"ok": e["proved"], "states": e["states_N5"], "proved": e["proved"],
                                       "evidence": e["evidence"]} for g, e in r.items()} for a, r in tab.items()}}
        res = {}
        for gid, spec in G.items():
            c0 = time.process_time()
            r = ap.construct(spec, table, evidence="TZ")
            row = {"status": r["status"], "cpu": time.process_time() - c0, "reasons": r.get("reasons", {})}
            if r["status"] == "CONSTRUCTED":
                plan = [tuple(x) for x in r["plan"]]
                row["plan"] = plan
                row["used"] = [{"entry": f"{a} / {g}", "status": tab[a][g]["status"], "states_N5": tab[a][g]["states_N5"]}
                               for a, g in used_pairwise(plan, spec)]
                row["failures"] = judge_plan(spec, plan, cache, plan_key(gid, plan))["failures"]
            res[gid] = row
        out["A-P"][var] = res
        print("A-P", var, "constructed", sum(v["status"] == "CONSTRUCTED" for v in res.values()),
              "wrong", sum(v.get("failures", 0) > 0 for v in res.values()), round(time.perf_counter() - t0, 1), "s", flush=True)

    # 3 B-EXCH
    variants = {"disc-50": (50, (5, 6, 7)), "disc-200": (200, (5, 6, 7)), "disc-1000": (1000, (5, 6, 7)),
                "five-1000": (1000, (5,))}
    fits, B = {}, {}
    for name, (n, sizes) in variants.items():
        f, cost, hold = bexch.learn(n, sizes)
        fits[name] = f
        laws = {}
        for row in f.values():
            for k, x in row.items():
                laws[f"{ttype(k)}:{x['law']}"] = laws.get(f"{ttype(k)}:{x['law']}", 0) + 1
        B[name] = {"cost": cost, "holdout_N8": hold, "laws": laws}
        print("B-EXCH", name, laws, "L0 failures", cost["L0_failures"], "hold-out errors", hold["errors"],
              "cpu", round(cost["cpu"], 1), flush=True)
    need = frozenset((a, k) for f in fits.values() for a, row in f.items() for k, x in row.items()
                     if x["law"] == "LOC" and not k.startswith("KD"))
    given, gcpu = bexch.given_all(need)
    out["S_given_cpu_s"] = gcpu
    tabs = {}
    for name, f in fits.items():
        B[name]["law_check"] = bexch.law_check(f, given)
        for sup in ("obs", "given"):
            dmg, prog = bexch.tables(f, None if sup == "obs" else given)
            tabs[(name, sup)] = (dmg, prog)
            B[name][sup] = {"vs_T7": compare(dmg, t7["damage"]), "vs_TZ": compare(dmg, tz["table"]),
                            "progress_ok": sum(p["ok"] for p in prog.values()),
                            "reasons": {}}
            for row in dmg.values():
                for e in row["entries"].values():
                    B[name][sup]["reasons"][e["reason"]] = B[name][sup]["reasons"].get(e["reason"], 0) + 1
            B[name][sup]["tables"] = {a: {k: [e["law"], e["bound"], e["reason"]] for k, e in row["entries"].items()}
                                      for a, row in dmg.items()}
        print("B-EXCH", name, "S-obs dangerous vs T7", B[name]["obs"]["vs_T7"]["dangerous"],
              "S-given dangerous vs T7", B[name]["given"]["vs_T7"]["dangerous"],
              "S-given agreement with TZ", round(B[name]["given"]["vs_TZ"]["agreement"], 3), flush=True)
    out["B-EXCH"] = B
    out["B-DISC_reference"] = {"vs_TZ_dangerous_fraction": cr["B_vs_TZ"]["disc"]["vs_TZ"]["dangerous_fraction"],
                               "vs_T7_dangerous": cr["B_vs_TZ"]["disc"]["vs_T7"]["dangerous"]}

    # 5 A-P' with B-EXCH tables
    out["A-P'"] = {}
    runs = [("disc-1000", "obs"), ("disc-1000", "given"), ("disc-200", "given"), ("disc-50", "given"),
            ("five-1000", "obs"), ("five-1000", "given")]
    for name, sup in runs:
        dmg, prog = tabs[(name, sup)]
        res = {}
        for gid, spec in G.items():
            c0 = time.process_time()
            r = ap2.construct(spec, "tmpl", dmg, prog, evidence="BX")
            row = {"status": r["status"], "cpu": time.process_time() - c0, "reasons": r.get("reasons", {})}
            if r["status"] == "CONSTRUCTED":
                plan = [tuple(x) for x in r["plan"]]
                row.update(plan=plan, weights=r["weights"])
                vs = [p[1] for p in r["plan"]]
                row["accepted_under_TZ"] = ap2.check_certificate(spec, vs, r["weights"], "tmpl", tz["table"],
                                                                 tz["progress"], "TZ")["accepted"]
                row["failures"] = judge_plan(spec, plan, cache, plan_key(gid, plan))["failures"]
            res[gid] = row
        out["A-P'"][f"{name}/{sup}"] = res
        print("A-P'", name, sup, "constructed", sum(v["status"] == "CONSTRUCTED" for v in res.values()),
              "wrong", sum(v.get("failures", 0) > 0 for v in res.values()),
              "rejected under TZ", sum(v["status"] == "CONSTRUCTED" and not v["accepted_under_TZ"] for v in res.values()),
              round(time.perf_counter() - t0, 1), "s", flush=True)
    out["TZ_A-P'_reference"] = sum(r["status"] == "CONSTRUCTED" for r in cr["A-P'"]["TZ"].values())
    out["newly_judged_plans"] = len(cache) - n_cached
    out["judged"] = cache
    out["costs"] = {"TZ-P_z3_s": tzp["z3_time_s"], "N8_cpu_s": n8["cpu_s"], "S_given_cpu_s": gcpu,
                    "B-EXCH_cpu_s": {k: v["cost"]["cpu"] for k, v in B.items()},
                    "A-P_median_cpu_s": {k: statistics.median(r["cpu"] for r in v.values()) for k, v in out["A-P"].items()}}
    out["time_s"] = round(time.perf_counter() - t0, 1)
    (HERE / "r4.json").write_text(json.dumps(out, indent=1, default=str))
    print("done", out["time_s"], "s; newly judged plans", out["newly_judged_plans"])


if __name__ == "__main__":
    main()
