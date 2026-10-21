"""Score PA-3 against P3.1-P3.5 (amendment 2). Written before PA-3 ran.

  recovered      a goal constructed by the route with 0 J1-sym and 0 J2 failures
  the 38         PA-2 goals refused by A-P but established by A-SAME or A-FLAT (pa2_scores.json, G2)
  the 23         PA-2 goals no route constructed in G2
  P3.1  L-tmpl: 0 constructions with any J1 or J2 failure (over all 98 goals)
  P3.2  L-tmpl recovers >= 19 of the 38, and >= 2 of {T3, M2, M3, M4}
  P3.3  L-lin recovers <= half as many of the 38 as L-tmpl
  P3.4  L-tmpl constructs (status CONSTRUCTED) none of the 23 and not T2
  P3.5  L-tmpl CPU median <= 0.0165 s per goal and the damage table took <= 300 s

  python -I score_pa3.py      # writes pa3_scores.json
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIB = HERE.parent / "lib"


def main():
    d = json.loads((HERE / "pa3.json").read_text())["goals"]
    g2 = json.loads((HERE / "pa2_scores.json").read_text())
    the38, the23 = g2["P2.2"]["refused_but_established"], g2["P2.2"]["refused_unknown"]
    ok = lambda r: r["status"] == "CONSTRUCTED" and r.get("failures", 1) == 0
    S = {}
    wrong = [g for g, r in d.items() if r["tmpl"]["status"] == "CONSTRUCTED" and r["tmpl"]["failures"] > 0]
    S["P3.1"] = {"verdict": "HOLDS" if not wrong else "FALSIFIED", "wrong": wrong,
                 "constructed": sum(r["tmpl"]["status"] == "CONSTRUCTED" for r in d.values())}
    rec38 = [g for g in the38 if ok(d[g]["tmpl"])]
    recM = [g for g in ("T3", "M2", "M3", "M4") if ok(d[g]["tmpl"])]
    S["P3.2"] = {"verdict": "HOLDS" if len(rec38) >= 19 and len(recM) >= 2 else "FALSIFIED",
                 "recovered_of_38": len(rec38), "recovered_targets": recM}
    lin38 = [g for g in the38 if ok(d[g]["lin"])]
    S["P3.3"] = {"verdict": "HOLDS" if len(lin38) <= 0.5 * len(rec38) else "FALSIFIED", "L-lin_recovered_of_38": len(lin38),
                 "L-tmpl_recovered_of_38": len(rec38)}
    built23 = [g for g in the23 + ["T2"] if d[g]["tmpl"]["status"] == "CONSTRUCTED"]
    S["P3.4"] = {"verdict": "HOLDS" if not built23 else "FALSIFIED", "constructed_among_barrier_goals": built23,
                 "their_failures": {g: d[g]["tmpl"]["failures"] for g in built23}}
    med = statistics.median(r["tmpl"]["cpu"] for r in d.values())
    lib_t = json.loads((LIB / "damage_table.json").read_text())["time_s"]
    S["P3.5"] = {"verdict": "HOLDS" if med <= 0.0165 and lib_t <= 300 else "FALSIFIED", "median_cpu": med,
                 "damage_table_s": lib_t}
    reasons = {"tmpl": {}, "lin": {}}
    for r in d.values():
        for m in ("tmpl", "lin"):
            for k, v in r[m].get("reasons", {}).items():
                reasons[m][k] = reasons[m].get(k, 0) + v
    S["refusal_reasons_over_candidates"] = reasons
    S["coverage"] = {m: sum(ok(r[m]) for r in d.values()) for m in ("tmpl", "lin")}
    (HERE / "pa3_scores.json").write_text(json.dumps(S, indent=1))
    print(json.dumps({k: v["verdict"] for k, v in S.items() if isinstance(v, dict) and "verdict" in v}, indent=1))


if __name__ == "__main__":
    main()
