"""Score round 5 against F1-F6 and G1-G2 (amendment 5). Written before the round ran.

  F1  B-GRAM, all four variants: (a) 0 L1 failures (and 0 L0); (b) no H_glob, every OUT/OOW entry in class "t only";
      (c) 0 mismatches with the exchange formula on identified S-given combinations; (d) 0 hold-out errors, and
      0 unpredicted hold-out cases for disc-1000
  F2  B-GRAM S-given: 0 dangerous vs T7 and vs TZ in all four variants; agreement with TZ >= 0.99 (disc-1000) and
      >= 0.90 (disc-50)
  F3  B-R1 S-given: 0 dangerous vs T7 and vs TZ in all four variants; agreement with TZ >= 0.95 at disc-1000;
      B-GRAM agreement >= B-R1 agreement at disc-50 and disc-1000
  F4  B-GRAM S-fact: disc-1000 0 dangerous vs T7 and agreement with TZ >= 0.95; five-1000 >= 1 dangerous vs T7
  F5  A-P' with B-GRAM S-given (n = 50, 200, 1000) and B-GRAM S-fact (disc-1000): 0 failures, the constructed goals
      equal TZ's 30, every certificate accepted under TZ
  F6  B-GRAM fitting <= 60 s CPU per variant; B-R1 <= 10 s; TZ-P2 Z3 <= 60 s
  G1  TZ-P2 proves all 94 non-vacuous T7-held entries and none of the entries with a real counterexample
  G2  A-P with TZ-P2: 0 failures, >= 36 constructions, every used entry PROVED

  python -I score_r5.py      # writes r5_scores.json
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
VARS = ("disc-50", "disc-200", "disc-1000", "five-1000")


def V(ok):
    return "HOLDS" if ok else "FALSIFIED"


def main():
    d = json.loads((HERE / "r5.json").read_text())
    B = d["B"]
    S = {}
    f1 = {}
    ok1 = True
    for v in VARS:
        b = B[v]
        cls = b["gram_classes"]
        bad_cls = [c for c in cls if c.endswith(":GLOB") or (c.split(":")[0] in ("OUT", "OOW") and c.split(":")[1] != "t")]
        h = b["diag"]["holdout"]
        o = (b["diag"]["L1_failures"] == 0 and b["diag"]["L0_failures"] == 0 and not bad_cls
             and b["gram_law_check"]["mismatches"] == 0 and h["errors"] == 0 and (v != "disc-1000" or h["unpredicted"] == 0))
        ok1 &= o
        f1[v] = {"L0": b["diag"]["L0_failures"], "L1": b["diag"]["L1_failures"], "classes": cls,
                 "law_mismatches": b["gram_law_check"]["mismatches"], "holdout": h}
    S["F1"] = {"verdict": V(ok1), **f1}
    tb = lambda v, c: B[v]["tables"][c]
    dang = {v: (tb(v, "gram/given")["vs_T7"]["dangerous"], tb(v, "gram/given")["vs_TZ"]["dangerous"]) for v in VARS}
    agr = {v: tb(v, "gram/given")["vs_TZ"]["agreement"] for v in VARS}
    S["F2"] = {"verdict": V(all(x == (0, 0) for x in dang.values()) and agr["disc-1000"] >= 0.99 and agr["disc-50"] >= 0.90),
               "dangerous_T7_TZ": dang, "agreement_with_TZ": agr,
               "B-EXCH_given_agreement": {v: tb(v, "exch/given")["vs_TZ"]["agreement"] for v in VARS}}
    dr1 = {v: (tb(v, "r1/given")["vs_T7"]["dangerous"], tb(v, "r1/given")["vs_TZ"]["dangerous"]) for v in VARS}
    ar1 = {v: tb(v, "r1/given")["vs_TZ"]["agreement"] for v in VARS}
    S["F3"] = {"verdict": V(all(x == (0, 0) for x in dr1.values()) and ar1["disc-1000"] >= 0.95
                            and agr["disc-50"] >= ar1["disc-50"] and agr["disc-1000"] >= ar1["disc-1000"]),
               "dangerous_T7_TZ": dr1, "agreement_with_TZ": ar1, "r1_contradictions": {v: B[v]["r1_contradictions"] for v in VARS}}
    fd = tb("disc-1000", "gram/fact")
    f5 = tb("five-1000", "gram/fact")
    S["F4"] = {"verdict": V(fd["vs_T7"]["dangerous"] == 0 and fd["vs_TZ"]["agreement"] >= 0.95 and f5["vs_T7"]["dangerous"] >= 1),
               "disc-1000": {"dangerous_vs_T7": fd["vs_T7"]["dangerous"], "agreement_with_TZ": fd["vs_TZ"]["agreement"],
                             "list": fd["vs_T7"]["dangerous_list"]},
               "five-1000": {"dangerous_vs_T7": f5["vs_T7"]["dangerous"], "by_type": f5["vs_T7"]["dangerous_by_type"],
                             "list": f5["vs_T7"]["dangerous_list"]},
               "S-obs_dangerous_vs_T7": {v: tb(v, "gram/obs")["vs_T7"]["dangerous"] for v in VARS}}
    tzset = set(d["TZ_A-P'_constructed"])
    f5r = {}
    ok5 = True
    for run in ("disc-50/gram/given", "disc-200/gram/given", "disc-1000/gram/given", "disc-1000/gram/fact"):
        r = d["A-P'"][run]
        built = {g for g, x in r.items() if x["status"] == "CONSTRUCTED"}
        wrong = [g for g in built if r[g].get("failures", 0) > 0]
        rej = [g for g in built if not r[g]["accepted_under_TZ"]]
        ok5 &= built == tzset and not wrong and not rej
        f5r[run] = {"constructed": len(built), "same_as_TZ": built == tzset, "wrong": wrong, "rejected_under_TZ": rej}
    S["F5"] = {"verdict": V(ok5), **f5r}
    k = d["costs"]
    S["F6"] = {"verdict": V(all(k["B_cpu_s"][v]["gram_fit"] <= 60 and k["B_cpu_s"][v]["r1"] <= 10 for v in VARS)
                            and k["TZ-P2_z3_s"] <= 60), **k}
    t = d["TZ-P2"]
    S["G1"] = {"verdict": V(t["nonvacuous_held"] == 94 and t["nonvacuous_held_proved"] == 94 and not t["proved_with_real_cex"]),
               **{x: t[x] for x in ("proved", "nonvacuous_held_proved", "nonvacuous_held_not_proved", "proved_with_real_cex",
                                    "vacuous_held_proved")}}
    A = d["A-P"]
    built = {g: r for g, r in A.items() if r["status"] == "CONSTRUCTED"}
    S["G2"] = {"verdict": V(len(built) >= 36 and not any(r.get("failures", 0) > 0 for r in built.values())
                            and all(u["status"] == "PROVED" for r in built.values() for u in r["used"])),
               "constructed": len(built), "wrong": [g for g, r in built.items() if r.get("failures", 0) > 0]}
    S["A-P'_other"] = {run: sum(x["status"] == "CONSTRUCTED" for x in d["A-P'"][run].values())
                       for run in d["A-P'"]}
    (HERE / "r5_scores.json").write_text(json.dumps(S, indent=1))
    print(json.dumps({k: v["verdict"] for k, v in S.items() if isinstance(v, dict) and "verdict" in v}, indent=1))


if __name__ == "__main__":
    main()
