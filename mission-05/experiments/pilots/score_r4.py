"""Score round 4 against E1-E6 and D1-D6 (amendment 4). Written before the round ran.

  E1  formula self-check 0 mismatches; TZ-P0 and TZ-P1 prove none of the 144 entries with a real counterexample
  E2  TZ-P0 proves all 94 non-vacuous entries that hold at N <= 7
  E3  TZ-P0 does not prove GROUP:G1 / ZONE(A1,left,half) nor GROUP:G2 / ZONE(A1,right,half); TZ-P1 proves both
  E4  the N = 8 search finds 0 counterexamples (entries T7-held, not proved by TZ-P1)
  E5  A-P with TZ-P1: 0 J1/J2 failures, >= 32 constructions, every used entry PROVED
  E6  TZ-P Z3 time <= 120 s; N = 8 search <= 3600 s CPU
  D1  (a) 0 L0 failures; (b) no H_glob entry; (c) 0 coefficient mismatches and no H_end KD entry whose formula has a
      nonzero between term on S-given; (d) 0 hold-out errors at N = 8         [disc-1000]
  D2  disc-1000 S-obs vs T7: 0 dangerous KD entries, total dangerous <= 10, all OUT/OOW; its dangerous fraction vs TZ
      below B-DISC's (round 3)
  D3  disc-1000 S-given: 0 dangerous vs T7 and vs TZ; agreement with TZ >= 0.90; A-P' with it: 0 failures, >= 28
      constructions, every certificate accepted under TZ
  D4  five-1000: D1 (b)(c) hold; S-obs dangerous vs T7 >= 10; S-given dangerous vs T7 = 0
  D5  smallest n in {50, 200, 1000} with A-P' (S-given) constructions >= 30 (TZ's count) and 0 failures is <= 200
  D6  B-EXCH CPU <= 120 s for disc-1000; S-given Z3 CPU <= 120 s

  python -I score_r4.py      # writes r4_scores.json
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIB = HERE.parent / "lib"


def V(ok):
    return "HOLDS" if ok else "FALSIFIED"


def main():
    d = json.loads((HERE / "r4.json").read_text())
    tzp = json.loads((LIB / "tzp_table.json").read_text())
    S = {}
    tp = d["TZ-P"]
    S["E1"] = {"verdict": V(tzp["self_check"]["mismatches"] == 0 and not tp["TZ-P0"]["proved_with_real_cex"]
                            and not tp["TZ-P1"]["proved_with_real_cex"]),
               "self_check": {k: tzp["self_check"][k] for k in ("checked", "mismatches")},
               "proved_with_real_cex": {v: tp[v]["proved_with_real_cex"] for v in tp}}
    S["E2"] = {"verdict": V(tp["TZ-P0"]["nonvacuous_held"] == 94 and tp["TZ-P0"]["nonvacuous_held_proved"] == 94),
               "nonvacuous_held": tp["TZ-P0"]["nonvacuous_held"], "proved": tp["TZ-P0"]["nonvacuous_held_proved"],
               "not_proved": tp["TZ-P0"]["nonvacuous_held_not_proved"]}
    two = ["GROUP:G1 / ZONE(A1,left,half)", "GROUP:G2 / ZONE(A1,right,half)"]
    t0, t1 = tzp["tables"]["TZ-P0"], tzp["tables"]["TZ-P1"]
    st = lambda t, e: t[e.split(" / ")[0]][e.split(" / ")[1]]["proved"]
    S["E3"] = {"verdict": V(not any(st(t0, e) for e in two) and all(st(t1, e) for e in two)),
               "TZ-P0": {e: st(t0, e) for e in two}, "TZ-P1": {e: st(t1, e) for e in two}}
    S["E4"] = {"verdict": V(d["N8"]["refuted"] == 0), **d["N8"]}
    A = d["A-P"]["TZ-P1"]
    built = {g: r for g, r in A.items() if r["status"] == "CONSTRUCTED"}
    wrong = [g for g, r in built.items() if r.get("failures", 0) > 0]
    unproved = [g for g, r in built.items() if any(u["status"] != "PROVED" for u in r["used"])]
    S["E5"] = {"verdict": V(not wrong and len(built) >= 32 and not unproved), "constructed": len(built), "wrong": wrong,
               "using_unproved": unproved,
               "using_entries_vacuous_at_N5": sorted({g for g, r in built.items() if any(u["states_N5"] == 0 for u in r["used"])})}
    k = d["costs"]
    S["E6"] = {"verdict": V(k["TZ-P_z3_s"] <= 120 and k["N8_cpu_s"] <= 3600), "TZ-P_z3_s": k["TZ-P_z3_s"],
               "N8_cpu_s": k["N8_cpu_s"]}
    B = d["B-EXCH"]
    b = B["disc-1000"]
    lc = b["law_check"]
    glob = [x for x in b["laws"] if x.endswith(":GLOB")]
    S["D1"] = {"verdict": V(b["cost"]["L0_failures"] == 0 and not glob and lc["coefficient_mismatches"] == 0
                            and not lc["end_selected_with_nonzero_between"] and b["holdout_N8"]["errors"] == 0),
               "L0_failures": b["cost"]["L0_failures"], "laws": b["laws"], "law_check": lc,
               "holdout_N8": {x: b["holdout_N8"][x] for x in ("predicted", "unpredicted", "errors")}}
    o = b["obs"]["vs_T7"]
    types = set(o["dangerous_by_type"])
    S["D2"] = {"verdict": V(o["dangerous_by_type"].get("KD", 0) == 0 and o["dangerous"] <= 10 and types <= {"OUT", "OOW"}
                            and b["obs"]["vs_TZ"]["dangerous_fraction"] < d["B-DISC_reference"]["vs_TZ_dangerous_fraction"]),
               "dangerous_vs_T7": o["dangerous"], "by_type": o["dangerous_by_type"],
               "dangerous_fraction_vs_TZ": b["obs"]["vs_TZ"]["dangerous_fraction"],
               "B-DISC_fraction_vs_TZ": d["B-DISC_reference"]["vs_TZ_dangerous_fraction"], "list": o["dangerous_list"]}
    g = b["given"]
    ap_ = d["A-P'"]["disc-1000/given"]
    bg = {x: r for x, r in ap_.items() if r["status"] == "CONSTRUCTED"}
    S["D3"] = {"verdict": V(g["vs_T7"]["dangerous"] == 0 and g["vs_TZ"]["dangerous"] == 0 and g["vs_TZ"]["agreement"] >= 0.9
                            and not any(r.get("failures", 0) > 0 for r in bg.values()) and len(bg) >= 28
                            and all(r["accepted_under_TZ"] for r in bg.values())),
               "dangerous_vs_T7": g["vs_T7"]["dangerous"], "dangerous_vs_TZ": g["vs_TZ"]["dangerous"],
               "agreement_with_TZ": g["vs_TZ"]["agreement"], "constructed": len(bg),
               "rejected_under_TZ": [x for x, r in bg.items() if not r["accepted_under_TZ"]],
               "wrong": [x for x, r in bg.items() if r.get("failures", 0) > 0]}
    f5 = B["five-1000"]
    S["D4"] = {"verdict": V(not [x for x in f5["laws"] if x.endswith(":GLOB")] and f5["law_check"]["coefficient_mismatches"] == 0
                            and not f5["law_check"]["end_selected_with_nonzero_between"]
                            and f5["obs"]["vs_T7"]["dangerous"] >= 10 and f5["given"]["vs_T7"]["dangerous"] == 0),
               "laws": f5["laws"], "coefficient_mismatches": f5["law_check"]["coefficient_mismatches"],
               "obs_dangerous_vs_T7": f5["obs"]["vs_T7"]["dangerous"], "given_dangerous_vs_T7": f5["given"]["vs_T7"]["dangerous"]}
    curve = {}
    for n in (50, 200, 1000):
        r = d["A-P'"][f"disc-{n}/given"]
        curve[n] = {"constructed": sum(x["status"] == "CONSTRUCTED" for x in r.values()),
                    "wrong": sum(x.get("failures", 0) > 0 for x in r.values())}
    first = next((n for n in (50, 200, 1000) if curve[n]["constructed"] >= d["TZ_A-P'_reference"] and curve[n]["wrong"] == 0), None)
    S["D5"] = {"verdict": V(first is not None and first <= 200), "smallest_n": first, "curve": curve,
               "TZ_reference": d["TZ_A-P'_reference"]}
    S["D6"] = {"verdict": V(k["B-EXCH_cpu_s"]["disc-1000"] <= 120 and k["S_given_cpu_s"] <= 120),
               "B-EXCH_cpu_s": k["B-EXCH_cpu_s"], "S_given_cpu_s": k["S_given_cpu_s"]}
    S["coverage"] = {"A-P": {v: sum(r["status"] == "CONSTRUCTED" and r.get("failures", 1) == 0 for r in x.values())
                             for v, x in d["A-P"].items()},
                     "A-P'": {v: sum(r["status"] == "CONSTRUCTED" and r.get("failures", 1) == 0 for r in x.values())
                              for v, x in d["A-P'"].items()}}
    (HERE / "r4_scores.json").write_text(json.dumps(S, indent=1))
    print(json.dumps({k: v["verdict"] for k, v in S.items() if isinstance(v, dict) and "verdict" in v}, indent=1))


if __name__ == "__main__":
    main()
