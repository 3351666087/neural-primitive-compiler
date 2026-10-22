"""JUDGE SIDE scoring with amendment A2 (PROTOCOL.md, amendment A2). Supersedes score_eco.score_run from Gate 3 on;
score_eco.py stays as the frozen Gate 2 scorer, and Gate 2's runs are rescored with this module as a check.

Differences from score_eco.score_run:
  - goal literals map to structures through the goal record's provenance (struct:<id>), not by predicate name;
  - every exported structure (including revised or deleted ones) is grounded separately, with the structures it
    references (a Bit's counter context);
  - a conjunction counts toward every R-level class among its grounded literals (none ungrounded);
  - a goal's pursuit period runs to the last action citing it or any descendant goal;
  - L3 (two-round cycle) per PROTOCOL.md section 6.5 with amendment A2 item 4.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ground_eco as G  # noqa: E402
from score_eco import class_key, load, provenance_audit  # noqa: E402

R_LEVEL = ("LATENT", "PLACE")
_GROUND_CACHE = {}


def _deps(s, by_sid):
    out = [s]
    q = s.get("params", {}).get("q_struct")
    seen = {s["struct_id"]}
    while q is not None and q in by_sid and q not in seen:
        seen.add(q)
        d = by_sid[q]
        out.append(d)
        q = d.get("params", {}).get("q_struct")
    return out


def ground_structures(structs, probes, classes):
    """{struct_id: {predicate: grounding}} with each structure evaluated together with the structures it references."""
    by_sid = {s["struct_id"]: s for s in structs}
    out = {}
    for s in structs:
        if s["form"] not in ("M1", "M2", "M3", "M4"):
            out[s["struct_id"]] = {}
            continue
        descs = _deps(s, by_sid)
        key = hashlib.sha256(json.dumps([[d["form"], d["struct_id"], d["params"]] for d in descs], sort_keys=True,
                                        default=str).encode()).hexdigest() + str(len(probes))
        if key not in _GROUND_CACHE:
            gr = G.ground(descs, probes, classes)
            _GROUND_CACHE[key] = {p: gr[p] for p in s.get("predicates", []) if p in gr}
        out[s["struct_id"]] = _GROUND_CACHE[key]
    return out


def _sid_of(prov):
    if isinstance(prov, str) and prov.startswith("struct:"):
        return int(prov.split(":")[1])
    return None


def score_run(stem, run_dir, probes, classes, twin_stem=None):
    j, a = load(run_dir, stem)
    T = j["steps"]
    structs = a["export"]["structures"]
    by_sid = {s["struct_id"]: s for s in structs}
    logs_by_sid = {}
    for s in a["structures"]:
        logs_by_sid.setdefault(s["struct_id"], s)
    gr = ground_structures(structs, probes, classes)
    sinfo = {}
    for s in structs:
        info = logs_by_sid.get(s["struct_id"], s)
        audit = provenance_audit({**s, "trigger": info.get("trigger")}, j["events"])
        preds = {}
        for p in s.get("predicates", []):
            g = gr.get(s["struct_id"], {}).get(p)
            preds[p] = {"grounded": bool(g and g["grounded"]), "class": class_key(g["class"]) if g and g["grounded"] else None,
                        "best_class": class_key(g["class"]) if g else None,
                        "precision": g and round(g["precision"], 3), "recall": g and round(g["recall"], 3),
                        "positives_judge": g and g.get("positives_judge")}
        sinfo[s["struct_id"]] = {"form": s["form"], "params": s.get("params"), "t_created": s.get("t_created", 0),
                                 "retired": s.get("retired"), "trigger": info.get("trigger"), "audit": audit,
                                 "evidence": s.get("data_provenance") or [], "predicates": preds}

    def lit_class(p, prov):
        if "[" not in p:
            return "S0", None
        sid = _sid_of(prov)
        if sid is None:                                   # external (gifted) literal: name lookup, latest structure
            cands = [x for x in structs if p in x.get("predicates", [])]
            sid = max(cands, key=lambda x: x.get("t_created", 0))["struct_id"] if cands else None
        if sid is None or sid not in sinfo or p not in sinfo[sid]["predicates"]:
            return "ungrounded", sid
        pi = sinfo[sid]["predicates"][p]
        return (pi["class"] if pi["grounded"] else "ungrounded"), sid

    # pursuit periods: last action citing the goal or any descendant
    children = defaultdict(list)
    for g in a["goals"]:
        if g["parent_goal"] is not None:
            children[g["parent_goal"]].append(g["goal_id"])
    first_act, last_own = {}, {}
    for rec in a["actions"]:
        gid = rec.get("goal_id")
        if gid is not None:
            first_act.setdefault(gid, rec["t"])
            last_own[gid] = rec["t"]
    last_desc = {}

    def last_of(gid, depth=0):
        if gid in last_desc:
            return last_desc[gid]
        v = last_own.get(gid)
        if depth < 50:
            for c in children.get(gid, ()):
                lc = last_of(c, depth + 1)
                if lc is not None and (v is None or lc > v):
                    v = lc
        last_desc[gid] = v
        return v
    late = [g["goal_id"] for g in a["goals"] if g["goal_id"] in first_act and g["t_logged"] > first_act[g["goal_id"]]]
    cls_idx = {class_key(c): i for i, c in enumerate(j["classes"])}
    intervals = {int(k): v for k, v in j["intervals"].items()}

    def holds_between(ci, t0, t1):
        for s0, s1 in intervals.get(ci, []):
            if s0 <= t1 + 1 and (s1 is None or s1 >= t0):
                return True
        return False
    per_class = defaultdict(Counter)
    goal_classes = {}
    for g in a["goals"]:
        prov = g.get("provenance") or ["S0"] * len(g["formula"])
        lits = [lit_class(p, prov[i] if i < len(prov) else None) for i, p in enumerate(g["formula"])]
        kinds = [k for k, _ in lits]
        role = "external" if g["reason"] == "external" else "need" if g["reason"] == "need" else \
            "instrumental" if g["parent_goal"] is not None else "top"
        if "ungrounded" in kinds:
            cls_list = ["ungrounded"]
        else:
            cls_list = sorted({k for k in kinds if k != "S0" and k.split(":")[0] in R_LEVEL})
            if not cls_list:
                nonr = sorted({k for k in kinds if k != "S0"})
                cls_list = nonr if len(nonr) == 1 else ["S0"]
        goal_classes[g["goal_id"]] = cls_list
        t_end = last_of(g["goal_id"])
        t_end = g["t_logged"] if t_end is None else t_end
        for cls in cls_list:
            per_class[cls][role] += 1
            if cls not in cls_idx:
                continue
            t_struct = max((sinfo[sid]["t_created"] for (k, sid) in lits if k == cls and sid in sinfo), default=0)
            ach = holds_between(cls_idx[cls], g["t_logged"], t_end)
            if role == "top" and g["t_logged"] >= t_struct:
                per_class[cls]["top_after_structure"] += 1
                per_class[cls]["top_achieved"] += ach
            if role == "instrumental":
                per_class[cls]["instrumental_achieved"] += ach
            if role == "external":
                per_class[cls]["external_achieved"] += ach
    twin_rate = {}
    if twin_stem:
        jt, _ = load(run_dir, twin_stem)
        for ck, ci in cls_idx.items():
            twin_rate[ck] = len(jt["intervals"].get(str(ci), [])) / (jt["steps"] / 10000)
    l2 = {}
    for ck, cnt in per_class.items():
        if ck not in cls_idx or not ck.startswith(R_LEVEL):
            continue
        audit_ok = any(si["audit"]["ok"] for si in sinfo.values() for p in si["predicates"].values() if p["class"] == ck)
        rate = cnt["top_achieved"] / (T / 10000)
        inc = twin_rate.get(ck)
        l2[ck] = {"top_after_structure": cnt["top_after_structure"], "top_achieved": cnt["top_achieved"],
                  "instrumental": cnt["instrumental"], "achieved_per_10k": round(rate, 2),
                  "twin_incidental_per_10k": None if inc is None else round(inc, 2), "provenance_ok": audit_ok,
                  "event": bool(cnt["top_after_structure"] >= 5 and cnt["top_achieved"] >= 3 and audit_ok
                                and inc is not None and rate >= 3 * inc and len(late) == 0)}
    res = {"stem": stem, "arm": j["arm"], "seed": j["seed"], "steps": T, "lives": j["lives"], "secs": j["secs"],
           "goals": len(a["goals"]), "late_goal_records": len(late), "goal_log_valid": len(late) == 0,
           "structures": {str(k): v for k, v in sinfo.items()}, "goals_by_class": {k: dict(v) for k, v in per_class.items()},
           "L2": l2, "L2_any": any(v["event"] for v in l2.values()), "self_report_ignored": "self_report" in a["export"]}
    res["_goal_classes"] = goal_classes
    res["_periods"] = {g["goal_id"]: (g["t_logged"], last_of(g["goal_id"]) or g["t_logged"]) for g in a["goals"]}
    res["_roles"] = {g["goal_id"]: ("external" if g["reason"] == "external" else "need" if g["reason"] == "need" else
                                    "instrumental" if g["parent_goal"] is not None else "top") for g in a["goals"]}
    res["_t_logged"] = {g["goal_id"]: g["t_logged"] for g in a["goals"]}
    return res


def l3(res, c2_prefix, c3_prefix):
    """Two-round cycle (PROTOCOL.md section 6.5, amendment A2 item 4) for one scored run. c2_prefix / c3_prefix: class-key
    prefixes, e.g. 'LATENT:stone.charge' and 'LATENT:lamp.armed'."""
    def grounded_to(prefix):
        out = []
        for sid, si in res["structures"].items():
            if any(p["class"] and p["class"].startswith(prefix) for p in si["predicates"].values()):
                out.append((si["t_created"], int(sid)))
        return sorted(out)
    s1 = grounded_to(c2_prefix)
    s2 = grounded_to(c3_prefix)
    c2_l2 = any(v["event"] for k, v in res["L2"].items() if k.startswith(c2_prefix))
    c3_l2 = any(v["event"] for k, v in res["L2"].items() if k.startswith(c3_prefix))
    c2_goals = [gid for gid, cl in res["_goal_classes"].items() if any(c.startswith(c2_prefix) for c in cl)]
    c2_top = sorted(res["_t_logged"][gid] for gid in c2_goals if res["_roles"][gid] == "top")
    periods = sorted(res["_periods"][gid] for gid in c2_goals)
    out = {"s1": s1[0] if s1 else None, "s2": s2[0] if s2 else None, "C2_L2": c2_l2, "C3_L2": c3_l2,
           "first_C2_top_goal": c2_top[0] if c2_top else None, "C2_goals": len(c2_goals)}
    if s2:
        si = res["structures"][str(s2[0][1])]
        ev = si["evidence"]

        def inside(t):
            for t0, t1 in periods:
                if t0 <= t <= t1:
                    return True
            return False
        frac = sum(1 for t in ev if inside(t)) / len(ev) if ev else 0.0
        out.update({"s2_evidence": len(ev), "s2_evidence_in_C2_pursuit": round(frac, 3),
                    "s2_after_first_C2_top": bool(c2_top and s2[0][0] > c2_top[0])})
    out["L3"] = bool(c2_l2 and c3_l2 and s2 and out.get("s2_after_first_C2_top") and out.get("s2_evidence_in_C2_pursuit", 0) >= 0.5)
    return out


def public(res):
    return {k: v for k, v in res.items() if not k.startswith("_")}
