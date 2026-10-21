"""Score the contract reliability round against C1-C7 (amendment 3). Written before the round ran.

  C1  T7 refutes (counterexample at N = 6 or 7) >= 1 of the 120 pairwise-preservation entries certified in G2
  C2  (a) no damage entry has an N <= 7 exhaustive maximum above its TZ bound (TZ PROVED entries), and
      (b) every round-2 witness entry (b1_witness.json, entries with a witness) has a TZ bound above its T5 bound
          (TZ infinite counts as above). Erratum: the protocol text says 12 such entries; the file holds 11.
  C3  A-P' with TZ: 0 constructions with J1/J2 failures, >= 30 constructions, and every certificate uses only TZ
      evidence (PROVED damage entries and TZ progress)
  C4  none of the 6 round-2 certificates B-DISC refused is accepted under T7 or under TZ
  C5  T7/TZ bounded-vs-infinite agreement >= 0.90 and >= 1 entry bounded in T7 but infinite in TZ
  C6  TZ (Z3 time) <= 600 s; T7 <= 7200 s CPU; A-P' median CPU per goal <= 1 ms under both T7 and TZ
  C7  against TZ: B-DISC (round 2, n = 1000) dangerous fraction <= 0.05 and B-NULL >= 0.20

  python -I score_cr.py      # writes cr_scores.json
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIB = HERE.parent / "lib"


def main():
    d = json.loads((HERE / "cr.json").read_text())
    t7 = json.loads((LIB / "t7_tables.json").read_text())
    S = {}
    refuted = [f"{a} / {g}" for a, row in t7["preserves"].items() for g, e in row.items() if e["ok_N5"] and e["cex_N67"]]
    S["C1"] = {"verdict": "HOLDS" if refuted else "FALSIFIED", "checked": t7["summary"]["pairwise_checked"],
               "refuted": refuted}
    above = d["T7_vs_TZ"]["T7_max_above_TZ"]
    notabove = [w["entry"] for w in d["witness_entries"] if not w["TZ_above_T5"]]
    S["C2"] = {"verdict": "HOLDS" if not above and not notabove else "FALSIFIED", "T7_max_above_TZ": above,
               "witness_entries": len(d["witness_entries"]), "witness_TZ_not_above_T5": notabove}
    A = d["A-P'"]["TZ"]
    built = {g: r for g, r in A.items() if r["status"] == "CONSTRUCTED"}
    wrong = [g for g, r in built.items() if r.get("failures", 0) > 0]
    non_tz = [g for g, r in built.items() if any(u["progress_evidence"] != "TZ" or any(e["evidence"] != "TZ" for e in u["entries"])
                                                 for u in r["used"])]
    S["C3"] = {"verdict": "HOLDS" if not wrong and len(built) >= 30 and not non_tz else "FALSIFIED",
               "constructed": len(built), "wrong": wrong, "certificates_with_non_TZ_entries": non_tz}
    acc = {g: [s for s in ("T7", "TZ") if r[s]["accepted"]] for g, r in d["C4_certificates"].items()}
    S["C4"] = {"verdict": "HOLDS" if len(acc) == 6 and not any(acc.values()) else "FALSIFIED",
               "certificates": len(acc), "accepted_under": acc}
    c = d["T7_vs_TZ"]
    S["C5"] = {"verdict": "HOLDS" if c["agreement"] >= 0.90 and len(c["T7_bounded_TZ_inf"]) >= 1 else "FALSIFIED",
               "agreement": c["agreement"], "T7_bounded_TZ_inf": len(c["T7_bounded_TZ_inf"]),
               "TZ_bounded_T7_inf": len(c["TZ_bounded_T7_inf"])}
    k = d["costs"]
    med = k["A-P'_median_cpu_s"]
    S["C6"] = {"verdict": "HOLDS" if k["TZ_z3_s"] <= 600 and k["T7_cpu_s"] <= 7200 and med["T7"] <= 0.001
               and med["TZ"] <= 0.001 else "FALSIFIED", **k}
    b = d["B_vs_TZ"]
    S["C7"] = {"verdict": "HOLDS" if b["disc"]["vs_TZ"]["dangerous_fraction"] <= 0.05
               and b["null"]["vs_TZ"]["dangerous_fraction"] >= 0.20 else "FALSIFIED",
               "disc_dangerous_fraction": b["disc"]["vs_TZ"]["dangerous_fraction"],
               "null_dangerous_fraction": b["null"]["vs_TZ"]["dangerous_fraction"]}
    ok = lambda r: r["status"] == "CONSTRUCTED" and r.get("failures", 1) == 0
    S["coverage"] = {"A-P'": {s: sum(ok(r) for r in d["A-P'"][s].values()) for s in d["A-P'"]},
                     "A-P": {s: sum(ok(r) for r in d["A-P"][s].values()) for s in d["A-P"]}}
    lost = [g for g, r in d["A-P"]["G2"].items() if r["status"] == "CONSTRUCTED" and d["A-P"]["T7"][g]["status"] != "CONSTRUCTED"]
    S["A-P_lost_with_T7"] = lost
    (HERE / "cr_scores.json").write_text(json.dumps(S, indent=1))
    print(json.dumps({k: v["verdict"] for k, v in S.items() if isinstance(v, dict) and "verdict" in v}, indent=1))


if __name__ == "__main__":
    main()
