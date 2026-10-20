"""Score the locked predictions CP1-CP9 and the decision rules of CONFIRMATION_ARC2.md against confirm_arc2.json.

Written while the confirmation run was in progress and before any of its results were read. Edge cases fixed in
advance: a tie for the largest unexplained gap category makes that sub-claim INCONCLUSIVE; count claims of CP8 are
scored only for methods with at least 3 answers. Verdicts: HOLDS, FALSIFIED, INCONCLUSIVE (condition not met).
Prints only counts, ids and verdicts.

  python -I mission-04/experiments/c1_arc2/score_cp.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROUTES = ["F1", "F3", "F3-noselect", "F4"]
POLICIES = ["S0", "S1", "S2", "S3", "S4"]
NONUNIFORM = "K: non-uniform recolouring inside blocks"


def verdict(cond, ok):
    return "INCONCLUSIVE" if not cond else "HOLDS" if ok else "FALSIFIED"


def answers(c):
    return c["correct"] + c["wrong"]


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "confirm_arc2.json"   # another path: only to test the scorer
    d = json.loads(src.read_text())
    s, rows = d["summary"], d["rows"]
    n = s["tasks"]
    out = {"label": d["label"], "tasks": n, "time_s": d["time_s"], "cp": {}}

    sp = s["specificity"]
    nt, ns = sp["law_holds_true_pairs"], sp["law_holds_shuffled_pairs"]
    frac = nt / n
    ok1 = (ns == 0 or nt >= 3 * ns) and frac <= 0.1975
    out["cp"]["CP1"] = {"verdict": verdict(nt >= 6, ok1), "true": nt, "shuffled": ns, "ratio": sp["ratio"],
                        "fraction_true": round(frac, 4)}

    law = s["law_holding_tasks"]
    share = s["law_holding_with_an_F1_rule"] / law if law else None
    out["cp"]["CP2"] = {"verdict": verdict(law >= 6, share is not None and share >= 0.75),
                        "law_holding": law, "with_F1_rule": s["law_holding_with_an_F1_rule"],
                        "share": round(share, 3) if share is not None else None}
    m3 = s["F3_rules_tried_mean_on_law_tasks"]
    out["cp"]["CP3"] = {"verdict": verdict(law >= 6, m3 is not None and m3 <= 6.0), "F3_rules_tried_mean": m3}

    ia = s["identifiability_abstentions"]
    out["cp"]["CP4"] = {"verdict": verdict(ia["tasks"] >= 3, ia["tasks"] and ia["S2_correct_among_them"] / ia["tasks"] >= 2 / 3),
                        **ia}

    g = s["gap"]
    cats = g["unexplained_categories"]
    share5 = g["explained_by_attributes_or_parts_S2"] / g["tasks"] if g["tasks"] else None
    part_a = share5 is not None and share5 <= 0.25
    if not cats:
        part_b, tie = None, False
    else:
        top = max(cats.values())
        leaders = [k for k, v in cats.items() if v == top]
        tie = len(leaders) > 1 and NONUNIFORM in leaders
        part_b = None if tie else leaders == [NONUNIFORM]
    if g["tasks"] < 5:
        v5 = "INCONCLUSIVE"
    elif not part_a or part_b is False:
        v5 = "FALSIFIED"
    elif part_b is None:
        v5 = "INCONCLUSIVE"         # first part holds; the category claim is undecided (tie or no unexplained task)
    else:
        v5 = "HOLDS"
    out["cp"]["CP5"] = {"verdict": v5, "gap_tasks": g["tasks"], "explained": g["explained_by_attributes_or_parts_S2"],
                        "explained_share": round(share5, 3) if share5 is not None else None, "categories": cats,
                        "category_tie": tie}

    lo = s["loo_pairs"]
    f1, f3, fn = lo["F1"], lo["F3"], lo["F3-noselect"]
    cond6 = all(answers(x) >= 10 for x in (f1, f3, fn))
    ok6 = cond6 and (f3["correct"] >= f1["correct"] - 3 and f3["precision"] >= f1["precision"] - 0.10
                     and fn["precision"] <= f3["precision"] and min(f1["precision"], f3["precision"], fn["precision"]) < 1)
    out["cp"]["CP6"] = {"verdict": verdict(cond6, ok6), "F1": f1, "F3": f3, "F3-noselect": fn}

    md = s["M-DISC-fixed"]
    rc = s["z3_unique_rechecked"]
    recheck_ok = rc["agree"] == rc["n"] and not rc["other"]
    count7 = "FALSIFIED" if md["correct"] > 4 or md["wrong"] > 2 else "INCONCLUSIVE" if answers(md) < 3 else "HOLDS"
    out["cp"]["CP7"] = {"verdict": "FALSIFIED" if not recheck_ok else count7,
                        "recheck": "HOLDS" if recheck_ok else "FALSIFIED", "count_part": count7,
                        "M-DISC-fixed": md, "M-DISC-fixed-strict": s["M-DISC-fixed-strict"],
                        "M-DISC-MDL-fixed": s["M-DISC-MDL-fixed"], "z3_unique_rechecked": rc}

    wrong_ok = s["S0"]["wrong"] == 0 and s["F1"]["wrong"] == 0 and s["F3"]["wrong"] == 0 and s["S2"]["wrong"] <= 1
    evaluated = {m: s[m]["correct"] <= 4 for m in ROUTES + POLICIES if answers(s[m]) >= 3}
    count8 = "INCONCLUSIVE" if not evaluated else "HOLDS" if all(evaluated.values()) else "FALSIFIED"
    out["cp"]["CP8"] = {"verdict": "FALSIFIED" if not wrong_ok or count8 == "FALSIFIED" else count8,
                        "wrong_part": "HOLDS" if wrong_ok else "FALSIFIED", "count_part": count8,
                        "count_part_methods": evaluated, **{m: s[m] for m in ROUTES + POLICIES}}

    s1, s4 = s["S1"], s["S4"]
    out["cp"]["CP9"] = {"verdict": verdict(answers(s1) >= 3 or answers(s4) >= 3,
                                           s4["wrong"] == 0 and s4["correct"] >= s1["correct"] - 1), "S1": s1, "S4": s4}

    # decision rules (CONFIRMATION_ARC2.md section 5)
    def solved_by_block(r):
        b = r["blocks"]
        if not isinstance(b, dict):
            return False
        return any(b[x]["status"] == "correct" for x in ROUTES) or b["policies"]["S0"] == "correct" or b["policies"]["S4"] == "correct"
    beyond = sorted(t for t, r in rows.items() if solved_by_block(r)
                    and not (isinstance(r.get("mdisc"), dict) and r["mdisc"]["M-DISC-fixed"]["status"] == "correct"))
    rule1 = (out["cp"]["CP1"]["verdict"] == "HOLDS" and len(beyond) >= 2 and s["S0"]["wrong"] == 0
             and s["F3"]["correct"] >= s["F1"]["correct"] - 1)
    out["decision"] = {
        "rule1_block_representation_enters_formal_system": rule1,
        "rule1_block_correct_beyond_mdisc_fixed": beyond,
        "rule2_retract_conservation_law_selection": out["cp"]["CP1"]["verdict"] == "FALSIFIED",
        "rule3_composition_supported_outside_DEV": out["cp"]["CP5"]["verdict"] == "HOLDS" and out["cp"]["CP6"]["verdict"] == "HOLDS",
        "rule4_rediscovery_confirmed": out["cp"]["CP2"]["verdict"] == "HOLDS",
    }
    out["correct_tasks"] = {m: sorted(t for t, r in rows.items() if isinstance(r["blocks"], dict) and (
        r["blocks"][m]["status"] if m in ROUTES else r["blocks"]["policies"][m]) == "correct") for m in ROUTES + POLICIES}
    out["correct_tasks"].update({v: sorted(t for t, r in rows.items() if isinstance(r.get("mdisc"), dict)
                                           and r["mdisc"][v]["status"] == "correct")
                                 for v in ("M-DISC-fixed", "M-DISC-fixed-strict", "M-DISC-MDL-fixed")})
    out["wrong_tasks"] = {m: sorted(t for t, r in rows.items() if isinstance(r["blocks"], dict) and (
        r["blocks"][m]["status"] if m in ROUTES else r["blocks"]["policies"][m]) == "wrong") for m in ROUTES + POLICIES}
    out["wrong_tasks"].update({v: sorted(t for t, r in rows.items() if isinstance(r.get("mdisc"), dict)
                                         and r["mdisc"][v]["status"] == "wrong")
                               for v in ("M-DISC-fixed", "M-DISC-fixed-strict", "M-DISC-MDL-fixed")})
    out["resource_limits"] = {"blocks": s["block_layer_RESOURCE_LIMIT"], "loo": s["loo_pairs"]["RESOURCE_LIMIT"],
                              "mdisc": sorted(t for t, r in rows.items() if r.get("mdisc") == "RESOURCE_LIMIT")}
    dst = HERE / ("cp_scores.json" if src.name == "confirm_arc2.json" else f"cp_scores_test_{src.stem}.json")
    dst.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
