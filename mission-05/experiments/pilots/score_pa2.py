"""Score PA-2 against the locked predictions P2.1-P2.4. Written before PA-2 ran.

  wrong construction   an A-P construction with any J1-sym failure (V_train or V_unseen) or any J2 (N = 6) failure
  general policy       a construction (A-P, A-SAME or A-FLAT) with 0 J1-sym failures on V_train and V_unseen
  P2.1  HOLDS iff A-P has 0 wrong constructions in the pool
  P2.2  price = goals refused by A-P that A-SAME or A-FLAT establish / goals for which some route establishes a
        general policy; HOLDS iff at least 1 such goal and price >= 0.05
  P2.3  refusal rate r1 (1 variant) and r2 (2 variants) over the pool; HOLDS iff (r1 - r2) / r1 >= 0.30
        (INCONCLUSIVE if r1 = 0)
  P2.4  HOLDS iff every cue variant is constructed by A-P with 0 global verifications and 0 J1-sym failures

  python -I score_pa2.py      # writes pa2_scores.json
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def established(r):
    return r is not None and r.get("status") == "CONSTRUCTED" and r.get("J1_sym", {}).get("total_failures", 1) == 0


def main():
    d = json.loads((HERE / "pa2.json").read_text())
    G = d["goals"]
    S = {}
    wrong = [g for g, r in G.items() if r["A-P"]["status"] == "CONSTRUCTED"
             and (r["A-P"]["J1_sym"]["total_failures"] > 0 or r["A-P"]["J2_mc6"]["failures"] > 0)]
    S["P2.1"] = {"verdict": "HOLDS" if not wrong else "FALSIFIED", "wrong_constructions": wrong,
                 "A-P_constructed": sum(r["A-P"]["status"] == "CONSTRUCTED" for r in G.values()), "pool": len(G)}
    exists = [g for g, r in G.items() if established(r["A-P"]) or established(r.get("A-SAME")) or established(r.get("A-FLAT"))]
    priced = [g for g, r in G.items() if r["A-P"]["status"] != "CONSTRUCTED"
              and (established(r.get("A-SAME")) or established(r.get("A-FLAT")))]
    price = len(priced) / len(exists) if exists else None
    S["P2.2"] = {"verdict": "HOLDS" if priced and price >= 0.05 else "FALSIFIED", "price": price,
                 "refused_but_established": priced, "goals_with_a_general_policy": len(exists),
                 "refused_unknown": [g for g, r in G.items() if g not in exists]}
    r1 = sum(r["A-P1"]["status"] != "CONSTRUCTED" for r in G.values()) / len(G)
    r2 = sum(r["A-P"]["status"] != "CONSTRUCTED" for r in G.values()) / len(G)
    S["P2.3"] = {"verdict": "INCONCLUSIVE" if r1 == 0 else ("HOLDS" if (r1 - r2) / r1 >= 0.30 else "FALSIFIED"),
                 "refusal_1_variant": r1, "refusal_2_variants": r2}
    C = d["cue"]
    ok = [c for c, r in C.items() if r["A-P"]["status"] == "CONSTRUCTED" and r["A-P"]["J1_sym"]["total_failures"] == 0]
    S["P2.4"] = {"verdict": "HOLDS" if C and len(ok) == len(C) else "FALSIFIED", "cue_variants": len(C), "ok": len(ok),
                 "not_ok": sorted(set(C) - set(ok))}
    S["refusal_reasons"] = {}
    for r in G.values():
        for k, v in r["A-P"].get("reasons", {}).items():
            S["refusal_reasons"][k] = S["refusal_reasons"].get(k, 0) + v
    S["J1_net"] = d.get("J1_net")
    (HERE / "pa2_scores.json").write_text(json.dumps(S, indent=1, default=str))
    print(json.dumps({k: v["verdict"] for k, v in S.items() if isinstance(v, dict) and "verdict" in v}, indent=1))


if __name__ == "__main__":
    main()
