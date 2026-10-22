"""JUDGE SIDE scoring of ECO runs (PROTOCOL.md sections 6-7; AGENCY_DEFINITION.md sections 2-8).

score_run(stem, run_dir, probes, classes, twin_stem=None) returns, for one run:
  goal-log validity   records written after the first action that cites them (late records)
  structures          grounding (ground_eco), the novelty criteria that can be checked from logs, and a provenance
                      audit: a structure's evidence steps must coincide (within W + 2 steps) with judge-logged effect
                      events, at least 3 times; structures created without evidence are 'not from interaction'
  goals by class      each goal's literals mapped to S0 / a grounded judge class / ungrounded; top-level (parent None,
                      reason not 'need' or 'external'), instrumental (parent set), external
  achievement         a goal is achieved if its grounded class condition holds (judge intervals) at some step between
                      its logging and the last action citing it
  L2 events           per R-level class (LATENT, PLACE): >= 5 top-level goals logged after the structure's creation,
                      >= 3 achieved, achieved rate >= 3 x the twin run's incidental onset rate, structure passes the
                      provenance audit
L1 is computed separately by swap_test (history swap at a checkpoint vs. the reseeded noise floor).
"""

from __future__ import annotations

import gzip
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ground_eco as G  # noqa: E402

W = 6
EFFECT_EVENTS = {"spawn", "reveal"}


def load(run_dir, stem):
    with gzip.open(Path(run_dir) / f"{stem}.judge.json.gz", "rt") as f:
        j = json.load(f)
    with gzip.open(Path(run_dir) / f"{stem}.agent.json.gz", "rt") as f:
        a = json.load(f)
    return j, a


def class_key(c):
    return f"{c[0]}:{c[1]}:{tuple(c[2]) if c[2] else None}"


def provenance_audit(s, judge_events):
    ev_t = [e[0] for e in judge_events if e[1] in EFFECT_EVENTS]
    evid = s.get("data_provenance") or []
    hits = sum(1 for t in evid if any(-2 <= tj - t <= W + 2 for tj in ev_t)) if s["form"] in ("M1", "M2", "M4") else len(evid)
    from_interaction = s.get("t_created", 0) > 0 and s.get("trigger") not in ("hardcoded", "transplant") and len(evid) > 0
    return {"evidence": len(evid), "matched_judge_effects": hits, "ok": from_interaction and hits >= 3}


def score_run(stem, run_dir, probes, classes, twin_stem=None):
    j, a = load(run_dir, stem)
    T = j["steps"]
    structs = a["export"]["structures"]
    logs_by_sid = {s["struct_id"]: s for s in a["structures"]}
    evaluable = [s for s in structs if s["form"] in ("M1", "M2", "M3", "M4")]
    gr = G.ground(evaluable, probes, classes) if evaluable else {}
    pred_info = {}
    for s in structs:
        info = logs_by_sid.get(s["struct_id"], s)
        audit = provenance_audit({**s, **{k: info.get(k) for k in ("trigger",)}}, j["events"])
        for p in s.get("predicates", []):
            g = gr.get(p)
            pred_info[p] = {"struct": s["struct_id"], "t_created": s.get("t_created", 0), "audit": audit,
                            "grounded": bool(g and g["grounded"]), "class": class_key(g["class"]) if g and g["grounded"] else None,
                            "precision": g and round(g["precision"], 3), "recall": g and round(g["recall"], 3)}
    # goal intervals
    first_act, last_act = {}, {}
    for rec in a["actions"]:
        gid = rec.get("goal_id")
        if gid is not None:
            first_act.setdefault(gid, rec["t"])
            last_act[gid] = rec["t"]
    late = [g["goal_id"] for g in a["goals"] if g["goal_id"] in first_act and g["t_logged"] > first_act[g["goal_id"]]]
    cls_idx = {class_key(c): i for i, c in enumerate(j["classes"])}
    intervals = {int(k): v for k, v in j["intervals"].items()}

    def holds_between(ci, t0, t1):
        for s0, s1 in intervals.get(ci, []):
            if s0 <= t1 + 1 and (s1 is None or s1 >= t0):
                return True
        return False
    per_class = defaultdict(lambda: Counter())
    for g in a["goals"]:
        kinds = []
        for p in g["formula"]:
            if "[" not in p:
                kinds.append("S0")
            else:
                info = pred_info.get(p)
                kinds.append(info["class"] if info and info["grounded"] else "ungrounded")
        cls = kinds[0] if len(set(kinds)) == 1 else "mixed"
        role = "external" if g["reason"] == "external" else "need" if g["reason"] == "need" else \
            "instrumental" if g["parent_goal"] is not None else "top"
        per_class[cls][role] += 1
        if cls in cls_idx and role == "top":
            info = pred_info[g["formula"][0]]
            if g["t_logged"] >= info["t_created"]:
                per_class[cls]["top_after_structure"] += 1
                if holds_between(cls_idx[cls], g["t_logged"], last_act.get(g["goal_id"], g["t_logged"])):
                    per_class[cls]["top_achieved"] += 1
        if cls in cls_idx and role == "instrumental":
            if holds_between(cls_idx[cls], g["t_logged"], last_act.get(g["goal_id"], g["t_logged"])):
                per_class[cls]["instrumental_achieved"] += 1
    twin_rate = {}
    if twin_stem:
        jt, _ = load(run_dir, twin_stem)
        for ck, ci in cls_idx.items():
            twin_rate[ck] = len(jt["intervals"].get(str(ci), [])) / (jt["steps"] / 10000)
    l2 = {}
    for ck, cnt in per_class.items():
        if ck not in cls_idx or not ck.startswith(("LATENT", "PLACE")):
            continue
        audit_ok = any(info["audit"]["ok"] for info in pred_info.values() if info["class"] == ck)
        rate = cnt["top_achieved"] / (T / 10000)
        inc = twin_rate.get(ck)
        l2[ck] = {"top_after_structure": cnt["top_after_structure"], "top_achieved": cnt["top_achieved"],
                  "achieved_per_10k": round(rate, 2), "twin_incidental_per_10k": None if inc is None else round(inc, 2),
                  "provenance_ok": audit_ok,
                  "event": bool(cnt["top_after_structure"] >= 5 and cnt["top_achieved"] >= 3 and audit_ok
                                and inc is not None and rate >= 3 * inc and len(late) == 0)}
    return {"stem": stem, "arm": j["arm"], "seed": j["seed"], "steps": T, "lives": j["lives"], "secs": j["secs"],
            "goals": len(a["goals"]), "late_goal_records": len(late), "goal_log_valid": len(late) == 0,
            "structures": [{"struct_id": s["struct_id"], "form": s["form"], "params": s.get("params"), "t_created": s.get("t_created"),
                            "trigger": logs_by_sid.get(s["struct_id"], {}).get("trigger"), "predicates": s.get("predicates")} for s in structs],
            "predicates": pred_info, "goals_by_class": {k: dict(v) for k, v in per_class.items()}, "L2": l2,
            "L2_any": any(v["event"] for v in l2.values()), "self_report_ignored": "self_report" in a["export"]}


def goal_dist(agent_out, t0, t1):
    c = Counter(g["formula"][0] for g in agent_out["goals"] if t0 <= g["t_logged"] < t1 and g["reason"] != "need")
    n = sum(c.values())
    return {k: v / n for k, v in c.items()} if n else {}


def tv(p, q):
    keys = set(p) | set(q)
    return 0.5 * sum(abs(p.get(k, 0) - q.get(k, 0)) for k in keys)
