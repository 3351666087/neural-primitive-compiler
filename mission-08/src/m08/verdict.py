"""Mechanical verdict (PRE_REGISTRATION.md sections 2.4, 3.2, 4, 6, 8 with amendments A1-A4) computed from the Gate 5
result files; the verdict documents quote this output and do not re-judge.
  python3 -I -m m08.verdict            # reads results/g5/*.json, writes results/g5/verdict.json
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
G5 = ROOT / "results" / "g5"

PRIMARY_RULE = {"N2U": "R1-cook", "W2": "R1-dev", "W4": "R1-dev", "JSH": "R1-dev"}     # amendment A3.1
MEMORY = {"N2U": "M4", "W2": "M2", "W4": "M2", "JSH": "M2"}                            # amendment A1.4
TARGETS = ("W2", "W4", "JSH", "N2U")


def _load(name):
    p = G5 / f"{name}.json"
    return json.loads(p.read_text())["results"] if p.exists() else None


def structure(s, positive_control):
    """Sections 2.4 and 8 with amendments A2, A3 and A4.5: STRUCTURE_ONLY needs one rule to satisfy S-a and
    (S-b or S-c) - R1 (S-a(R1) and (S-b(R1) or S-c(R1))) or K2 (S-a(B3) and S-c(K2)); NOT_SUPPORTED when S-a fails on
    both; REPLICATION_ONLY otherwise, provided the development positive control holds."""
    out, per = {}, {}
    for t in TARGETS:
        r = s[t]
        sc, df = r["scores"], r["diffs"]
        rule, mem = PRIMARY_RULE[t], MEMORY[t]
        er = f"C({mem},ER)"
        crule, ck2 = f"C({mem},{rule})", f"C({mem},B3)"
        g_rule, g_mem = sc[rule]["ll_gain_bits_per_pair"], sc[mem]["ll_gain_bits_per_pair"]
        ap0 = sc["B0"]["auprc"]
        dl_rule, dl_mem = sc[rule].get("dl_bits"), sc[mem].get("dl_bits")
        per[t] = {
            "S-a(R1)": df[f"{rule}-vs-B1"]["lo"] > 0,
            "S-a(B3)": df["B3-vs-B1"]["lo"] > 0,
            "S-b(R1)": bool(g_rule >= 0.5 * g_mem and (sc[rule]["auprc"] - ap0) >= 0.5 * (sc[mem]["auprc"] - ap0)
                            and dl_rule is not None and dl_mem is not None and dl_rule <= 0.25 * dl_mem),
            "S-c(R1)": df[f"{crule}-vs-{er}"]["lo"] > 0,
            "S-c(K2)": df[f"{ck2}-vs-{er}"]["lo"] > 0,
            "rule_vs_memory_ll": df[f"{rule}-vs-{mem}"],
            "dl_bits": {"rule": dl_rule, "memory": dl_mem},
        }
    for k in ("S-a(R1)", "S-a(B3)", "S-b(R1)", "S-c(R1)", "S-c(K2)"):
        n = sum(per[t][k] for t in TARGETS)
        out[k] = {"passes": int(n), "of": len(TARGETS), "holds": n >= 3}
    out["S-d"] = {"W2": s["W2"]["diffs"]["R1-dev-vs-M2"]["lo"] > 0, "W4": s["W4"]["diffs"]["R1-dev-vs-M2"]["lo"] > 0}
    out["S-d"]["holds"] = out["S-d"]["W2"] and out["S-d"]["W4"]
    n2u = s["N2U"]
    ref = n2u["proxy_gain"]
    out["S-e"] = {"rule_retained": n2u["scores"]["R1-cook"]["ll_gain_bits_per_pair"] / ref["R1-cook"]["W7->W8"],
                  "memory_retained": n2u["scores"]["M4"]["ll_gain_bits_per_pair"] / ref["M4"]["W7->W8"],
                  "rule_retained_vs_W8W7": n2u["scores"]["R1-cook"]["ll_gain_bits_per_pair"] / ref["R1-cook"]["W8->W7"]}
    out["S-e"]["holds"] = out["S-e"]["rule_retained"] >= 0.5
    out["per_target"] = per
    h = {k: out[k]["holds"] for k in ("S-a(R1)", "S-a(B3)", "S-b(R1)", "S-c(R1)", "S-c(K2)")}
    out["paths"] = {"R1": h["S-a(R1)"] and (h["S-b(R1)"] or h["S-c(R1)"]), "K2": h["S-a(B3)"] and h["S-c(K2)"]}
    out["positive_control_dev"] = positive_control
    if out["paths"]["R1"] or out["paths"]["K2"]:
        layer = "STRUCTURE_ONLY"          # both rules are known model families (R1 / block model): amendment A2.3
    elif not (h["S-a(R1)"] or h["S-a(B3)"]):
        layer = "NOT_SUPPORTED"
    elif positive_control:
        layer = "REPLICATION_ONLY"
    else:
        layer = "INCONCLUSIVE"
    out["layer"] = layer
    return out


def function(f):
    if f is None:
        return {"layer": "INCONCLUSIVE", "note": "no result"}
    wt = f["wt"]
    out = {"F-a": wt["F-a"], "F-b": wt["F-b"], "F-c": wt["F-c"], "F-d": wt["F-d"], "F-e": f["F-e"]}
    if not (wt["F-a"] and wt["F-b"]):
        out["layer"] = "NOT_SUPPORTED"
        out["note"] = "F-c, F-d and C-a: dependency unmet; development evidence: insufficient power (amendment A1.5)"
    elif not wt["F-c"]:
        out["layer"] = "NOT_SUPPORTED"
        out["note"] = "H0-TOPO supported: rule-generated structure does not carry the real connectome's functional information"
    elif wt["F-d"] and all(wt["F-d"].values()):
        out["layer"] = "KNOWN_MECHANISM_EQUIVALENT"     # the rule is the published R1
    else:
        out["layer"] = "FUNCTIONAL_NOT_NOVEL"
    return out


def t4(t):
    if t is None:
        return {"layer": "INCONCLUSIVE", "note": "no result"}
    out = {k: t[k] for k in ("T-a", "T-b", "T-c", "T-d")}
    if not t["T-a"]:
        out["layer"] = "NOT_SUPPORTED"
    elif all(out.values()):
        out["layer"] = "KNOWN_MECHANISM_EQUIVALENT"
    elif not t["T-b"]:
        out["layer"] = "REPLICATION_ONLY"           # amendment A4.5 (v): the known direction result only
        out["note"] = "topology fixes the direction, not the magnitude (H0-TOPO in the fly)"
    else:
        out["layer"] = "FUNCTIONAL_NOT_NOVEL"
    return out


def main():
    s, f, t = _load("structure"), _load("function"), _load("t4")
    pc = json.loads((ROOT / "results" / "g3" / "structure_dev_grid10.json").read_text())["results"]["positive_control"]
    pc_ok = bool(pc["cook_ok"] and pc["inferred8_ok"])
    v = {"G-STRUCT": structure(s, pc_ok) if s else {"layer": "INCONCLUSIVE"}, "G-FUNCTION worm": function(f),
         "G-FUNCTION fly T4": t4(t)}
    fc = f is not None and f["wt"]["F-c"]
    v["G-CONSTRUCT"] = {"layer": "INCONCLUSIVE", "note": "C-a not run: dependency F-c unmet"} if not fc else \
        {"layer": "INCONCLUSIVE", "note": "C-a pending"}
    layers = [v["G-STRUCT"]["layer"], v["G-FUNCTION worm"]["layer"]]
    if "KNOWN_MECHANISM_EQUIVALENT" in layers:
        overall = "KNOWN_MECHANISM_EQUIVALENT"
    elif v["G-STRUCT"]["layer"] == "STRUCTURE_ONLY":
        overall = "STRUCTURE_ONLY"
    elif v["G-STRUCT"]["layer"] == "REPLICATION_ONLY":
        overall = "REPLICATION_ONLY"
    else:
        overall = "NOT_SUPPORTED"
    v["overall"] = overall
    (G5 / "verdict.json").write_text(json.dumps(v, indent=1, default=str))
    print(json.dumps(v, indent=1, default=str))


if __name__ == "__main__":
    main()
