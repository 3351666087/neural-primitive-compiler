"""A's contract tables for ACH-DSL achiever instances (G3): Z3 damage bounds and preservation proofs (z3_dsl), and
progress = decrease PROVED for an own measure and no applicability counterexample in the truth tables at N <= 7 [M].
Evidence tag "TZ". Also the soundness and calibration checks of these tables against the truth tables.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))
sys.path.insert(0, str(HERE))
import dsl  # noqa: E402
import z3_dsl  # noqa: E402
from potentials import patterns  # noqa: E402

INF = float("inf")


def num(b):
    return INF if b in (None, "inf") else b


def a_tables(specs, inst, tr):
    damage, progress, preserves, raw = {}, {}, {}, {}
    sp_of = {k: sp for sp in specs for k, _ in dsl.instances(sp)}
    for k, a in inst:
        sp = sp_of[k]
        b = {x: z3_dsl.bound(sp, a, x) for x in patterns(a[0])}
        raw[k] = b
        damage[k] = {"entries": {x: {"bound": e["bound"], "evidence": "TZ" if e["status"] == "PROVED" else None,
                                     "status": e["status"]} for x, e in b.items()}}
        m = z3_dsl.progress(sp, a, b)
        ok = m is not None and tr[k]["applicability_cex"] is None
        progress[k] = {"ok": ok, "evidence": "TZ" if ok else None, "measure": m,
                       "decrease_proved": m is not None, "applicability_N7": tr[k]["applicability_cex"] is None}
        preserves[k] = {}
        for gk in tr[k]["preserves"]:
            st = z3_dsl.prove(sp, a, gk)["status"]
            preserves[k][gk] = {"ok": st == "PROVED", "evidence": "TZ" if st == "PROVED" else None, "status": st}
    return {"damage": damage, "progress": progress, "preserves": preserves}


def truth_damage(tr):
    return {k: {"entries": {x: {"bound": e["bound"]} for x, e in r["damage"].items()}} for k, r in tr.items()}


def truth_progress(tr, atom_of):
    """An instance truly makes progress at N <= 7 iff it always applies and some own measure always decreases."""
    out = {}
    for k, r in tr.items():
        ms = [x for x in z3_dsl.own_measures(atom_of[k])
              if any(v is not None for v in r["damage"][x]["max_by_N"].values())
              and all(v is None or v <= -1 for v in r["damage"][x]["max_by_N"].values())]
        out[k] = {"applies": r["applicability_cex"] is None, "decreasing_measures": ms,
                  "good": r["applicability_cex"] is None and bool(ms)}
    return out


def soundness(A, tr, atom_of):
    below, finite_growing, pres_bad, prog_bad = [], [], [], []
    for k, row in A["damage"].items():
        for x, e in row["entries"].items():
            if e["status"] != "PROVED":
                continue
            per = tr[k]["damage"][x]["max_by_N"]
            m7 = max((v for v in per.values() if v is not None), default=None)
            if m7 is not None and e["bound"] < m7:
                below.append(f"{k} / {x}: bound {e['bound']}, observed {m7}")
            if tr[k]["damage"][x]["bound"] == "inf":
                finite_growing.append(f"{k} / {x}")
    for k, row in A["preserves"].items():
        for gk, e in row.items():
            if e["ok"] and tr[k]["preserves"][gk]["cex"] is not None:
                pres_bad.append(f"{k} / {gk}")
    tp = truth_progress(tr, atom_of)
    for k, p in A["progress"].items():
        if p["ok"] and (not tp[k]["applies"] or p["measure"] not in tp[k]["decreasing_measures"]):
            prog_bad.append(k)
    good = [k for k, t in tp.items() if t["good"]]
    return {"damage_below_truth": below, "damage_finite_where_truth_grows": finite_growing,
            "preservation_proved_with_cex": pres_bad, "progress_certified_but_false": prog_bad,
            "truth_good_instances": len(good), "certified_among_truth_good": sum(A["progress"][k]["ok"] for k in good),
            "certified_total": sum(p["ok"] for p in A["progress"].values()), "instances": len(A["progress"])}


def observed_violations(tables, tr):
    """Entries of a bound table (A or B) whose finite bound lies below a delta observed at N <= 7 (a real state
    exceeds the bound), and entries that are finite where the truth's growth rule (max N=7 > max N=6) says infinite."""
    below, growing = [], []
    for k, row in tables.items():
        for x, e in row["entries"].items():
            b = e["bound"]
            if b in (None, "inf"):
                continue
            per = tr[k]["damage"][x]["max_by_N"]
            m7 = max((v for v in per.values() if v is not None), default=None)
            if m7 is not None and b < m7:
                below.append(f"{k} / {x}: bound {b}, observed {m7}")
            if tr[k]["damage"][x]["bound"] == "inf":
                growing.append(f"{k} / {x}")
    return {"below_observed": below, "finite_where_truth_grows": growing}
