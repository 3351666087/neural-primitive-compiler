"""Score round 8 against M1-M6 (amendment 8). Written before the round ran.

  M1  A++ on STRAT-DEV, LIB, G3-DEV: no PROVED damage bound below an observed N <= 7 delta; no progress certification
      contradicted by the truth; no controller built from A++'s STRAT-DEV tables fails J1-sym or J2
  M2  LIB: A++ equals A on all 432 entries; the same progress certifications
  M3  every set: A++ keeps every A+ certification and no A++ bound is higher than A+'s
  M4  STRAT-DEV: A++ certifies >= 0.90 of the truly progressing instances and at least as many as A+ (INCONCLUSIVE if
      fewer than 20 such instances); G3-DEV: A++ certifies 8 of 8
  M5  STRAT-DEV constructions: A's goals within A+'s within A++'s (A-P' and A-P separately)
  M6  the round <= 3 h

  python -I score_r8.py      # writes r8_scores.json
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def V(ok):
    return "HOLDS" if ok else "FALSIFIED"


def main():
    d = json.loads((HERE / "r8.json").read_text())
    Sx = d["sets"]
    S = {}
    bad = {n: {"below": s["A++_soundness"]["damage_below_truth"], "false_progress": s["A++_soundness"]["progress_certified_but_false"]}
           for n, s in Sx.items()}
    wrong = {r: sorted(g for g, x in res.items() if x.get("failures", 0) > 0) for r, res in d["constructions"].items() if r.startswith("A++")}
    S["M1"] = {"verdict": V(not any(v["below"] or v["false_progress"] for v in bad.values()) and not any(wrong.values())),
               "per_set": bad, "wrong_constructions": wrong,
               "all_tables_wrong_constructions": {r: sorted(g for g, x in res.items() if x.get("failures", 0) > 0)
                                                  for r, res in d["constructions"].items()}}
    lib = Sx["LIB"]
    S["M2"] = {"verdict": V(not lib["App_vs_A_damage_differences"] and lib["App_vs_A_progress_same"]),
               "differences": lib["App_vs_A_damage_differences"][:20], "progress_same": lib["App_vs_A_progress_same"]}
    S["M3"] = {"verdict": V(not any(s["App_looser_than_Ap"] or s["lost_vs_Ap"] for s in Sx.values())),
               "looser": {n: s["App_looser_than_Ap"][:10] for n, s in Sx.items()},
               "lost": {n: s["lost_vs_Ap"] for n, s in Sx.items()}, "tighter": {n: s["App_tighter_than_Ap"] for n, s in Sx.items()}}
    st = Sx["STRAT-DEV"]
    good = st["A++_soundness"]["truth_good_instances"]
    cal = {t: st[f"{t}_soundness"]["certified_among_truth_good"] for t in ("A", "A+", "A++")}
    g3 = Sx["G3-DEV"]
    g3ok = g3["A++_soundness"]["certified_among_truth_good"] == 8 and g3["A++_soundness"]["truth_good_instances"] == 8
    if good < 20:
        verdict = "INCONCLUSIVE"
    else:
        verdict = V(cal["A++"] / good >= 0.90 and cal["A++"] >= cal["A+"] and g3ok)
    S["M4"] = {"verdict": verdict, "STRAT_truly_good": good, "certified": cal,
               "rate_A++": cal["A++"] / good if good else None, "G3-DEV_8_of_8": g3ok,
               "uncertified_truly_good": sorted(k for k in st["truly_good"] if not st["progress"][k]["A++"])}
    built = {r: {g for g, x in res.items() if x["status"] == "CONSTRUCTED"} for r, res in d["constructions"].items()}
    ok5 = all(built[f"A/{r}"] <= built[f"A+/{r}"] <= built[f"A++/{r}"] for r in ("A-P'", "A-P"))
    S["M5"] = {"verdict": V(ok5), "counts": {k: len(v) for k, v in built.items()}}
    S["M6"] = {"verdict": V(d["time_s"] <= 10800), "time_s": d["time_s"]}
    S["stratification"] = {"pool_instances": d["stage1"]["instances"], "passed_N5": len(d["stage1"]["passed"]),
                           "failed_sample": len(d["stage1"]["failed_sample"]), "strat_specs": len(d["strat_specs"]),
                           "truly_good_N7": good}
    (HERE / "r8_scores.json").write_text(json.dumps(S, indent=1, default=str))
    print(json.dumps({k: v["verdict"] for k, v in S.items() if "verdict" in v}, indent=1))


if __name__ == "__main__":
    main()
