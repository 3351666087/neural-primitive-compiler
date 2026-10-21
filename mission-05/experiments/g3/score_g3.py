"""Score a G3 run against the locked predictions (G3_DESIGN.md section 9). Written and frozen before the held-out
specs exist; the thresholds were set after the DEV dry run (dev_dryrun.json) and the library self-check.

  Q1  A soundness on the held-out achievers: (a) no controller built from A's tables (A-P, A-P', specs only and
      library + specs) fails J1-sym or J2; (b) no PROVED damage bound lies below a delta observed at N <= 7; (c) no
      PROVED preservation entry has an N <= 7 counterexample; (d) no progress certification is contradicted by the
      N <= 7 truth; (e) J1-net: 0 mismatching episodes and 0 failures on the checked plans
  Q2  A calibration: among the instances that truly make progress at N <= 7, A certifies >= 0.75
      (INCONCLUSIVE if fewer than 5 such instances)
  Q3  B's certificates: no controller built from B's tables (five-1000, five-200) fails J1-sym or J2
  Q4  B inside its grammar: every instance of a held-out spec inside B's rule grammar has a non-empty version space
      (<= 64 pairs), 0 H1 disagreements and no bound below an observed N <= 7 delta, for five-1000 and five-200
      (INCONCLUSIVE if no such spec)
  Q5  B outside its grammar: at five-1000, at least one instance of a spec outside B's grammar has a non-empty
      version space that misses the true move on some eligible N = 6, 7 state (INCONCLUSIVE if no such spec)
  Q6  cost: the run takes <= 2 h wall clock; the truth tables <= 30 min CPU

  python -I score_g3.py RUN.json SCORES.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def V(ok):
    return "HOLDS" if ok else "FALSIFIED"


def main():
    d = json.loads(Path(sys.argv[1]).read_text())
    S = {}
    wrongA = {name: sorted(g for g, r in res.items() if r.get("failures", 0) > 0) for name, res in d["constructions"].items()}
    snd = d["A"]["soundness"]
    net_m = sum(v["mismatch_episodes"] for r in d["J1_net"].values() for v in r.values())
    net_f = sum(v["failures"] for r in d["J1_net"].values() for v in r.values())
    S["Q1"] = {"verdict": V(not any(wrongA.values()) and not snd["damage_below_truth"] and not snd["preservation_proved_with_cex"]
                            and not snd["progress_certified_but_false"] and net_m == 0 and net_f == 0),
               "wrong_constructions": wrongA, "damage_below_truth": snd["damage_below_truth"],
               "preservation_proved_with_cex": snd["preservation_proved_with_cex"],
               "progress_certified_but_false": snd["progress_certified_but_false"],
               "J1_net": {"plans": len(d["J1_net"]), "mismatch_episodes": net_m, "failures": net_f},
               "damage_finite_where_truth_grows": snd["damage_finite_where_truth_grows"]}
    good, cert = snd["truth_good_instances"], snd["certified_among_truth_good"]
    S["Q2"] = {"verdict": "INCONCLUSIVE" if good < 5 else V(cert / good >= 0.75), "truth_good": good, "certified": cert,
               "rate": cert / good if good else None, "certified_total": snd["certified_total"], "instances": snd["instances"]}
    wrongB = {bn: sorted(g for g, r in b["A-P'"].items() if r.get("failures", 0) > 0) for bn, b in d["B"].items()}
    S["Q3"] = {"verdict": V(not any(wrongB.values())), "wrong": wrongB,
               "constructed": {bn: sum(r["status"] == "CONSTRUCTED" for r in b["A-P'"].values()) for bn, b in d["B"].items()}}
    ing = lambda k: d["in_B_grammar"][k.split("|")[0]]
    q4, any_in = {}, False
    for bn, b in d["B"].items():
        ks = [k for k in b["H1"] if ing(k)]
        any_in |= bool(ks)
        below = [x for x in b["violations"]["below_observed"] if ing(x.split(" / ")[0])]
        q4[bn] = {"instances": len(ks), "no_rules": [k for k in ks if k in b["no_rules"]],
                  "disagreements": {k: b["H1"][k]["disagree"] for k in ks if b["H1"][k]["disagree"]}, "below_observed": below}
    S["Q4"] = {"verdict": "INCONCLUSIVE" if not any_in else V(not any(x["no_rules"] or x["disagreements"] or x["below_observed"]
                                                                       for x in q4.values())), **q4}
    b1 = d["B"]["five-1000"]
    outk = [k for k in b1["H1"] if not ing(k)]
    missed = {k: b1["H1"][k]["miss"] for k in outk if k not in b1["no_rules"] and b1["H1"][k]["miss"] > 0}
    S["Q5"] = {"verdict": "INCONCLUSIVE" if not outk else V(bool(missed)), "outside_grammar_instances": len(outk),
               "with_version_space": sum(k not in b1["no_rules"] for k in outk), "missing": missed,
               "below_observed_all": {bn: b["violations"]["below_observed"] for bn, b in d["B"].items()}}
    S["Q6"] = {"verdict": V(d["time_s"] <= 7200 and d["truth_cpu_s"] <= 1800), "time_s": d["time_s"], "truth_cpu_s": d["truth_cpu_s"]}
    S["descriptive"] = {
        "validation": d["validation"],
        "coverage": {name: sum(r["status"] == "CONSTRUCTED" and r.get("failures", 1) == 0 for r in res.values())
                     for name, res in d["constructions"].items()},
        "using_held_out_achievers": {name: sum(r.get("uses_spec", False) for r in res.values()) for name, res in d["constructions"].items()},
        "B_constructed": {bn: sum(r["status"] == "CONSTRUCTED" for r in b["A-P'"].values()) for bn, b in d["B"].items()},
        "B_no_rules": {bn: b["no_rules"] for bn, b in d["B"].items()},
        "in_B_grammar": d["in_B_grammar"],
        "B_vs_A": {bn: {x: b["vs_A"][x] for x in ("equal", "dangerous", "conservative")} for bn, b in d["B"].items()}}
    Path(sys.argv[2]).write_text(json.dumps(S, indent=1, default=str))
    print(json.dumps({k: v["verdict"] for k, v in S.items() if "verdict" in v}, indent=1))


if __name__ == "__main__":
    main()
