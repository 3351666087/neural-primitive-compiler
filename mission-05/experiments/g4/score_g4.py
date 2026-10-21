"""Score a G4 run against the locked predictions (G4_DESIGN.md section 6). Written and frozen before the held-out
specs exist; thresholds set from the DEV evidence of rounds 7-8 and the POST-HOC G3 re-checks.

  P1  A++ soundness on the held-out achievers: (a) no controller built from A++'s tables (A-P, A-P', specs only and
      library + specs) fails J1-sym or J2; (b) no PROVED damage bound below a delta observed at N <= 7; (c) no PROVED
      preservation entry with an N <= 7 counterexample; (d) no progress certification contradicted by the N <= 7
      truth; (e) J1-net: 0 mismatching episodes and 0 failures
  P2  A++ calibration: among the instances that truly make progress at N <= 7, A++ certifies >= 0.90
      (INCONCLUSIVE if fewer than 20 such instances)
  P3  monotone: every instance A (G3 encoding) certifies, A+ certifies; every instance A+ certifies, A++ certifies
  P4  residual gap: every truly progressing instance A++ does not certify uses a window region on a non-GROUP atom, or
      a source region relative to d (LEFT_OF_DEST, RIGHT_OF_DEST, within), possibly inside "and"
      (INCONCLUSIVE if A++ certifies every truly progressing instance)
  P5  B: no controller built from B's tables (n = 1000, 200) fails J1-sym or J2; every instance of a spec inside B's
      grammar has, at n = 1000, a non-empty version space (<= 64 pairs), 0 H1 disagreements and no bound below an
      observed N <= 7 delta (INCONCLUSIVE for the second part if no such spec)
  P6  cost: the run <= 2.5 h wall clock; the truth tables <= 45 min CPU

  python -I score_g4.py RUN.json SPECS.json SCORES.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def V(ok):
    return "HOLDS" if ok else "FALSIFIED"


def _gap_construct(r, atom_type, is_source):
    if isinstance(r, dict):
        if "and" in r:
            return any(_gap_construct(x, atom_type, is_source) for x in r["and"])
        return is_source                                      # within k of DEST
    if "WINDOW" in r and atom_type != "GROUP":
        return True
    return is_source and r in ("LEFT_OF_DEST", "RIGHT_OF_DEST")


def gap_shape(spec):
    return (_gap_construct(spec["dest"]["region"], spec["atom_type"], False)
            or _gap_construct(spec["source"]["region"], spec["atom_type"], True))


def main():
    d = json.loads(Path(sys.argv[1]).read_text())
    raw = json.loads(Path(sys.argv[2]).read_text())
    specs = {s["id"]: s for s in (raw["specs"] if isinstance(raw, dict) else raw) if isinstance(s, dict) and "id" in s}
    S = {}
    wrongA = {name: sorted(g for g, r in res.items() if r.get("failures", 0) > 0) for name, res in d["constructions"].items()}
    snd = d["A"]["soundness"]
    net_m = sum(v["mismatch_episodes"] for r in d["J1_net"].values() for v in r.values())
    net_f = sum(v["failures"] for r in d["J1_net"].values() for v in r.values())
    S["P1"] = {"verdict": V(not any(wrongA.values()) and not snd["damage_below_truth"] and not snd["preservation_proved_with_cex"]
                            and not snd["progress_certified_but_false"] and net_m == 0 and net_f == 0),
               "wrong_constructions": wrongA, "damage_below_truth": snd["damage_below_truth"],
               "preservation_proved_with_cex": snd["preservation_proved_with_cex"],
               "progress_certified_but_false": snd["progress_certified_but_false"],
               "J1_net": {"plans": len(d["J1_net"]), "mismatch_episodes": net_m, "failures": net_f}}
    good = sorted(k for k, v in d["truth_progress"].items() if v["good"])
    certA2 = {k for k, p in d["A"]["progress"].items() if p["ok"]}
    rate = sum(k in certA2 for k in good) / len(good) if good else None
    S["P2"] = {"verdict": "INCONCLUSIVE" if len(good) < 20 else V(rate >= 0.90), "truly_good": len(good),
               "certified": sum(k in certA2 for k in good), "rate": rate,
               "by_table": {"A(G3)": d["comparison"]["A(G3)"]["soundness"]["certified_among_truth_good"],
                            "A+": d["comparison"]["A+"]["soundness"]["certified_among_truth_good"],
                            "A++": sum(k in certA2 for k in good)}}
    cA, cP = set(d["comparison"]["A(G3)"]["certified"]), set(d["comparison"]["A+"]["certified"])
    S["P3"] = {"verdict": V(cA <= cP <= certA2), "A_not_A+": sorted(cA - cP), "A+_not_A++": sorted(cP - certA2)}
    missed = [k for k in good if k not in certA2]
    off = [k for k in missed if not gap_shape(specs[k.split("|")[0]])]
    S["P4"] = {"verdict": "INCONCLUSIVE" if not missed else V(not off), "uncertified_truly_good": missed,
               "outside_the_predicted_shape": off}
    wrongB = {bn: sorted(g for g, r in b["A-P'"].items() if r.get("failures", 0) > 0) for bn, b in d["B"].items()}
    b1 = d["B"]["five-1000"]
    ing = [k for k in b1["H1"] if d["in_B_grammar"][k.split("|")[0]]]
    bad_in = {"no_rules": [k for k in ing if k in b1["no_rules"]],
              "disagreements": {k: b1["H1"][k]["disagree"] for k in ing if b1["H1"][k]["disagree"]},
              "below_observed": [x for x in b1["violations"]["below_observed"] if x.split(" / ")[0] in ing]}
    ok5 = not any(wrongB.values()) and (not ing or not (bad_in["no_rules"] or bad_in["disagreements"] or bad_in["below_observed"]))
    S["P5"] = {"verdict": V(ok5), "wrong_B_constructions": wrongB, "in_grammar_instances": len(ing), **bad_in,
               "in_grammar_part": "INCONCLUSIVE" if not ing else "evaluated"}
    S["P6"] = {"verdict": V(d["time_s"] <= 9000 and d["truth_cpu_s"] <= 2700), "time_s": d["time_s"], "truth_cpu_s": d["truth_cpu_s"]}
    S["descriptive"] = {"validation": d["validation"],
                        "coverage": {n: sum(r["status"] == "CONSTRUCTED" and r.get("failures", 1) == 0 for r in res.values())
                                     for n, res in d["constructions"].items()},
                        "B_constructed": {bn: sum(r["status"] == "CONSTRUCTED" for r in b["A-P'"].values()) for bn, b in d["B"].items()},
                        "B_misses_outside_grammar": {k: h["miss"] for k, h in b1["H1"].items()
                                                     if not d["in_B_grammar"][k.split("|")[0]] and k not in b1["no_rules"] and h["miss"]},
                        "in_B_grammar": sum(d["in_B_grammar"].values())}
    Path(sys.argv[3]).write_text(json.dumps(S, indent=1, default=str))
    print(json.dumps({k: v["verdict"] for k, v in S.items() if "verdict" in v}, indent=1))


if __name__ == "__main__":
    main()
