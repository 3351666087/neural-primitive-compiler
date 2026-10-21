"""Score round 6 against H1-H7 (amendment 6). Written before the round ran. "Dangerous" is against T7.

  H1  disc-1000 and five-1000: every achiever's version space non-empty with <= 64 (d, s) rule pairs, and 0
      disagreements with the true selection on eligible N = 6, 7 states
  H2  B-RULE disc-1000 and five-1000: 0 dangerous entries; agreement with TZ >= 0.99
  H3  disc-1000 and five-1000: no entry's simulated support gains a combination at N = 7
  H4  B-SYM: disc-1000 0 dangerous; five-1000 >= 1 dangerous; 0 mirror inconsistencies of the B-GRAM laws (both)
  H5  A-P' with B-RULE disc-1000 and five-1000: 0 failures, the constructed goals equal TZ's 30, all accepted under TZ
  H6  B-RULE five-200 and five-50: 0 dangerous; A-P' with five-200 constructs exactly TZ's 30
  H7  per variant: rule learning <= 60 s CPU; simulation <= 1200 s CPU

  python -I score_r6.py      # writes r6_scores.json
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def V(ok):
    return "HOLDS" if ok else "FALSIFIED"


def main():
    d = json.loads((HERE / "r6.json").read_text())
    Vr = d["variants"]
    sim = lambda v: Vr[v]["simulation"] if "H1" in Vr[v]["simulation"] else Vr[Vr[v]["simulation"]["shared_with"]]["simulation"]
    S = {}
    h1 = {}
    ok = True
    for v in ("disc-1000", "five-1000"):
        vs = Vr[v]["version_spaces"]
        dis = sum(x["disagree"] for x in sim(v)["H1"].values())
        o = not Vr[v]["no_rules"] and all(x["pairs"] <= 64 and x["d"] > 0 and x["s"] > 0 for x in vs.values()) and dis == 0
        ok &= o
        h1[v] = {"pairs": {k: x["pairs"] for k, x in vs.items()}, "no_rules": Vr[v]["no_rules"], "disagreements": dis,
                 "examples": {k: x["example"] for k, x in sim(v)["H1"].items() if x["example"]}}
    S["H1"] = {"verdict": V(ok), **h1}
    h2 = {v: {"dangerous_vs_T7": Vr[v]["B-RULE"]["vs_T7"]["dangerous"], "agreement_with_TZ": Vr[v]["B-RULE"]["vs_TZ"]["agreement"],
              "dangerous_vs_TZ": Vr[v]["B-RULE"]["vs_TZ"]["dangerous"], "list": Vr[v]["B-RULE"]["vs_T7"]["dangerous_list"]}
          for v in ("disc-1000", "five-1000")}
    S["H2"] = {"verdict": V(all(x["dangerous_vs_T7"] == 0 and x["agreement_with_TZ"] >= 0.99 for x in h2.values())), **h2}
    late = {v: sim(v)["entries_with_new_combination_at_N7"] for v in ("disc-1000", "five-1000")}
    S["H3"] = {"verdict": V(not any(late.values())), "late": late}
    sd, sf = Vr["disc-1000"]["B-SYM"], Vr["five-1000"]["B-SYM"]
    mm = {v: Vr[v]["mirror_law_mismatches"]["count"] for v in ("disc-1000", "five-1000")}
    S["H4"] = {"verdict": V(sd["vs_T7"]["dangerous"] == 0 and sf["vs_T7"]["dangerous"] >= 1 and not any(mm.values())),
               "disc-1000_dangerous": sd["vs_T7"]["dangerous"], "five-1000_dangerous": sf["vs_T7"]["dangerous"],
               "mirror_law_mismatches": mm, "disc-1000_list": sd["vs_T7"]["dangerous_list"],
               "S-fact_reference_dangerous": {v: Vr[v]["B-FACT_reference"]["vs_T7"]["dangerous"] for v in ("disc-1000", "five-1000")}}
    tzset = set(d["TZ_A-P'_constructed"])
    h5, ok5 = {}, True
    for v in ("disc-1000", "five-1000", "five-200", "five-50"):
        r = d["A-P'"][v]
        built = {g for g, x in r.items() if x["status"] == "CONSTRUCTED"}
        wrong = [g for g in built if r[g].get("failures", 0) > 0]
        rej = [g for g in built if not r[g]["accepted_under_TZ"]]
        h5[v] = {"constructed": len(built), "same_as_TZ": built == tzset, "wrong": wrong, "rejected_under_TZ": rej}
        if v in ("disc-1000", "five-1000"):
            ok5 &= built == tzset and not wrong and not rej
    S["H5"] = {"verdict": V(ok5), **{v: h5[v] for v in ("disc-1000", "five-1000")}}
    S["H6"] = {"verdict": V(Vr["five-200"]["B-RULE"]["vs_T7"]["dangerous"] == 0 and Vr["five-50"]["B-RULE"]["vs_T7"]["dangerous"] == 0
                            and h5["five-200"]["same_as_TZ"]),
               "five-200": {"dangerous": Vr["five-200"]["B-RULE"]["vs_T7"]["dangerous"], **h5["five-200"],
                            "agreement_with_TZ": Vr["five-200"]["B-RULE"]["vs_TZ"]["agreement"], "no_rules": Vr["five-200"]["no_rules"]},
               "five-50": {"dangerous": Vr["five-50"]["B-RULE"]["vs_T7"]["dangerous"], **h5["five-50"],
                           "agreement_with_TZ": Vr["five-50"]["B-RULE"]["vs_TZ"]["agreement"], "no_rules": Vr["five-50"]["no_rules"]}}
    costs = {v: {"learn": Vr[v]["rule_learning_cpu_s"], "simulate": sim(v)["cpu_s"]} for v in Vr}
    S["H7"] = {"verdict": V(all(c["learn"] <= 60 and c["simulate"] <= 1200 for c in costs.values())), **costs}
    (HERE / "r6_scores.json").write_text(json.dumps(S, indent=1, default=str))
    print(json.dumps({k: v["verdict"] for k, v in S.items()}, indent=1))


if __name__ == "__main__":
    main()
