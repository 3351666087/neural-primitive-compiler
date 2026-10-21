"""Score PA-1 against the locked predictions P1.1-P1.6 (A05_PROTOCOL.md section 9). Written before PA-1 ran.

Interpretations fixed in advance:
  cost            = cpu_total (search + emit/compile of the final controller at N = 7); library validation excluded
  P1.1            per target: A-P constructed, 0 global verifications, J1-sym 0 failures (train and unseen),
                  J1-net 0 mismatching episodes and 0 failures, J2 model checking (N = 6) 0 failures
  P1.2            on T3, M3, M4: ratio = cost(A-SAME) / cost(A-P); HOLDS if every ratio >= 5; supports A-H0 if any
                  ratio <= 2; otherwise INCONCLUSIVE (if A-SAME failed to construct, its cost up to failure is used)
  P1.3            cost(M4)/cost(M2): A-P <= 3 and A-SAME >= 10
  P1.4            HOLDS iff A-FLAT does not construct on T2, T3, M3, M4 (any non-construction status, reported as is);
                  A-H2 refuted iff A-FLAT constructs on one of them at cost <= 2 x A-SAME's
  P1.5            HOLDS iff every A-SAME construction has 0 J1-sym failures on V_unseen
  P1.6            per A-P construction: neurons(15) / neurons(5) <= 3 (linear with a non-negative intercept);
                  A-FSM states grow >= 5x from N = 5 to 6 and from 6 to 7

  python -I score_pa1.py      # writes pa1_scores.json
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    d = json.loads((HERE / "pa1.json").read_text())["targets"]
    S = {}
    p11 = {}
    for t, r in d.items():
        a = r["A-P"]
        ok = a["status"] == "CONSTRUCTED"
        if ok:
            j1 = a["J1_sym"]["total_failures"] == 0
            jn = all(v["mismatch_episodes"] == 0 and v["failures"] == 0 for v in a["J1_net"].values())
            j2 = a["J2_mc6"]["failures"] == 0
            ok = j1 and jn and j2 and a["global_verifications"] == 0
            p11[t] = {"J1_sym_failures": a["J1_sym"]["total_failures"], "J1_net_ok": jn, "J2_failures": a["J2_mc6"]["failures"],
                      "holds": ok}
        else:
            p11[t] = {"status": a["status"], "holds": False}
    S["P1.1"] = {"verdict": "HOLDS" if all(v["holds"] for v in p11.values()) else "FALSIFIED", "per_target": p11}
    cost = lambda t, route: d[t][route].get("cpu_total")
    ratios = {t: (cost(t, "A-SAME") / cost(t, "A-P")) if d[t]["A-P"]["status"] == "CONSTRUCTED" else None
              for t in ("T3", "M3", "M4")}
    vals = [v for v in ratios.values() if v is not None]
    if len(vals) < 3:
        v12 = "INCONCLUSIVE"
    elif all(v >= 5 for v in vals):
        v12 = "HOLDS"
    elif any(v <= 2 for v in vals):
        v12 = "FALSIFIED (supports A-H0)"
    else:
        v12 = "INCONCLUSIVE"
    S["P1.2"] = {"verdict": v12, "ratios": ratios}
    g = lambda route: cost("M4", route) / cost("M2", route)
    gp, gs = g("A-P"), g("A-SAME")
    S["P1.3"] = {"verdict": "HOLDS" if gp <= 3 and gs >= 10 else "FALSIFIED", "A-P_growth": gp, "A-SAME_growth": gs}
    fl = {t: d[t]["A-FLAT"]["status"] for t in ("T2", "T3", "M3", "M4")}
    refuted = [t for t in fl if fl[t] == "CONSTRUCTED" and cost(t, "A-FLAT") <= 2 * cost(t, "A-SAME")]
    S["P1.4"] = {"verdict": "HOLDS" if all(v != "CONSTRUCTED" for v in fl.values()) else "FALSIFIED", "A-FLAT_status": fl,
                 "A-H2_refuted_on": refuted}
    unseen_fail = {t: sum(v["failures"] for k, v in d[t]["A-SAME"]["J1_sym"].items() if k.startswith("unseen"))
                   for t in d if d[t]["A-SAME"]["status"] == "CONSTRUCTED"}
    S["P1.5"] = {"verdict": "HOLDS" if all(v == 0 for v in unseen_fail.values()) else "FALSIFIED",
                 "A-SAME_unseen_failures": unseen_fail}
    lin = {t: d[t]["A-P"]["structure"]["15"]["neurons"] / d[t]["A-P"]["structure"]["5"]["neurons"]
           for t in d if d[t]["A-P"]["status"] == "CONSTRUCTED"}
    fsm = {t: [d[t]["A-FSM_states"]["6"] / d[t]["A-FSM_states"]["5"], d[t]["A-FSM_states"]["7"] / d[t]["A-FSM_states"]["6"]]
           for t in d}
    S["P1.6"] = {"verdict": "HOLDS" if all(v <= 3 for v in lin.values()) and all(min(x) >= 5 for x in fsm.values())
                 else "FALSIFIED", "A-P_neurons_15_over_5": lin, "A-FSM_growth": fsm}
    (HERE / "pa1_scores.json").write_text(json.dumps(S, indent=1, default=str))
    print(json.dumps({k: v["verdict"] for k, v in S.items()}, indent=1))


if __name__ == "__main__":
    main()
