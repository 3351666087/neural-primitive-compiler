"""Score round 7 against L1-L6 (amendment 7). Written before the round ran.

  L1  A+ on LIB, G3-DEV, RAND-DEV: no PROVED damage bound below an observed N <= 7 delta; no progress certification
      contradicted by the truth; no controller built from A+'s RAND-DEV tables (A-P', A-P) fails J1-sym or J2
  L2  LIB: A+ bounds equal A's on all 432 entries; the same progress certifications
  L3  RAND-DEV: A+ certifies >= 0.90 of the truly progressing instances and strictly more than A; G3-DEV: A+ >= A
  L4  every instance A certifies, A+ certifies; no entry where A+'s bound is higher than A's
  L5  RAND-DEV: A+'s constructed goals contain A's (A-P' and A-P separately)
  L6  A+ Z3 CPU <= 5 x A's (all sets together); the round <= 2 h

  python -I score_r7.py      # writes r7_scores.json
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def V(ok):
    return "HOLDS" if ok else "FALSIFIED"


def main():
    d = json.loads((HERE / "r7.json").read_text())
    S = {}
    Sx = d["sets"]
    bad = {n: {"below": s["Aplus_soundness"]["damage_below_truth"], "false_progress": s["Aplus_soundness"]["progress_certified_but_false"]}
           for n, s in Sx.items()}
    wrong = {r: sorted(g for g, x in res.items() if x.get("failures", 0) > 0) for r, res in d["constructions"].items() if r.startswith("A+")}
    S["L1"] = {"verdict": V(not any(v["below"] or v["false_progress"] for v in bad.values()) and not any(wrong.values())),
               "per_set": bad, "wrong_constructions": wrong}
    lib = Sx["LIB"]
    same_prog = all(p["A"] == p["A+"] for p in lib["progress"].values())
    S["L2"] = {"verdict": V(not lib["Aplus_looser_than_A"] and not lib["Aplus_tighter_than_A"] and same_prog),
               "looser": lib["Aplus_looser_than_A"], "tighter": lib["Aplus_tighter_than_A"], "same_progress": same_prog}
    cal = {n: {"A": (s["A_soundness"]["certified_among_truth_good"], s["A_soundness"]["truth_good_instances"]),
               "A+": (s["Aplus_soundness"]["certified_among_truth_good"], s["Aplus_soundness"]["truth_good_instances"])} for n, s in Sx.items()}
    r = cal["RAND-DEV"]
    g = cal["G3-DEV"]
    S["L3"] = {"verdict": V(r["A+"][1] > 0 and r["A+"][0] / r["A+"][1] >= 0.90 and r["A+"][0] > r["A"][0] and g["A+"][0] >= g["A"][0]),
               "calibration": cal}
    S["L4"] = {"verdict": V(not any(s["certified_by_A_not_Aplus"] or s["Aplus_looser_than_A"] for s in Sx.values())),
               "lost": {n: s["certified_by_A_not_Aplus"] for n, s in Sx.items()},
               "looser": {n: s["Aplus_looser_than_A"][:10] for n, s in Sx.items()},
               "tighter_count": {n: len(s["Aplus_tighter_than_A"]) for n, s in Sx.items()}}
    built = {r_: {g_ for g_, x in res.items() if x["status"] == "CONSTRUCTED"} for r_, res in d["constructions"].items()}
    S["L5"] = {"verdict": V(built["A/A-P'"] <= built["A+/A-P'"] and built["A/A-P"] <= built["A+/A-P"]),
               "counts": {k: len(v) for k, v in built.items()},
               "A+_extra": {"A-P'": sorted(built["A+/A-P'"] - built["A/A-P'"]), "A-P": sorted(built["A+/A-P"] - built["A/A-P"])}}
    za = sum(s["A_z3_cpu_s"] for s in Sx.values())
    zp = sum(s["Aplus_z3_cpu_s"] for s in Sx.values())
    S["L6"] = {"verdict": V(zp <= 5 * za and d["time_s"] <= 7200), "A_z3_cpu_s": za, "Aplus_z3_cpu_s": zp, "time_s": d["time_s"]}
    (HERE / "r7_scores.json").write_text(json.dumps(S, indent=1, default=str))
    print(json.dumps({k: v["verdict"] for k, v in S.items()}, indent=1))


if __name__ == "__main__":
    main()
