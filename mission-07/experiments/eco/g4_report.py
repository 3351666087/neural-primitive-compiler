"""Gate 4 tables (JUDGE SIDE): reads run/g4_FAMILY/arm_*.json, state_*.json, interv_scores_CAND.json and writes a
compact, committable g4_results_FAMILY.json plus markdown tables on stdout.
  python3 -I g4_report.py FAMILY"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from g4_jobs import out_dir  # noqa: E402


def main(name):
    out = out_dir(name)
    arms = {}
    for f in sorted(out.glob("arm_*.json")):
        d = json.loads(f.read_text())
        runs = {s: r for s, r in d["runs"].items() if "missing" not in r}
        arms[d["arm"]] = {
            "C2": d["C2"], "C3": d["C3"],
            "L1": d["summary"]["L1"]["passes"], "L2": d["summary"]["L2"]["passes"], "L3": d["summary"]["L3"]["passes"],
            "wilson": {k: d["summary"][k]["wilson95"] for k in ("L1", "L2", "L3")},
            "runs": len(runs),
            "mean_lives": round(sum(r["lives"] for r in runs.values()) / max(1, len(runs)), 1),
            "seeds_grounded_any": sum(1 for r in runs.values() if r["grounded"]),
            "seeds_s1": sum(1 for r in runs.values() if r["L3"].get("s1")),
            "seeds_s2": sum(1 for r in runs.values() if r["L3"].get("s2")),
            "L2_events": {s: sorted(k for k, v in r["L2"].items() if v["event"]) for s, r in runs.items()
                          if any(v["event"] for v in r["L2"].values())},
            "L3_posthoc": sum(1 for r in runs.values() if (r.get("L3_posthoc") or {}).get("L3")),
            "per_seed": {s: {"L1": [r["L1"].get("tv_swap"), r["L1"].get("tv_noise"), r["L1"].get("L1_pass")],
                             "grounded": r["grounded"], "s1": r["L3"].get("s1"), "s2": r["L3"].get("s2"),
                             "C2_goals": r["L3"].get("C2_goals"), "L2": {k: [v["top_after_structure"], v["top_achieved"],
                                                                            v["achieved_per_10k"], v["twin_incidental_per_10k"],
                                                                            v["event"]] for k, v in r["L2"].items()}}
                         for s, r in runs.items()}}
    state = {}
    for f in sorted(out.glob("state_*.json")):
        d = json.loads(f.read_text())
        state[d["arm"]] = {"passes": d["passes"], "runs": {s: v for s, v in d["runs"].items()}}
    interv = None
    p = out / "interv_scores_CAND.json"
    if p.exists():
        d = json.loads(p.read_text())
        interv = {k: ({"missing": v["missing"]} if "missing" in v else
                      {"L3": v["L3"], "L2": {c: [x["top_after_structure"], x["top_achieved"], x["achieved_per_10k"],
                                                 x["twin_incidental_per_10k"], x["event"]] for c, x in v["L2"].items()}})
                  for k, v in d.items()}
    res = {"family": name, "arms": arms, "state_intervention": state, "interventions": interv}
    (HERE / f"g4_results_{name}.json").write_text(json.dumps(res, indent=1, default=str))
    print(f"| arm | runs | lives | seeds with a grounded predicate | s1 | s2 | L1 | L2 | L3 | L3 post-hoc |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for a, v in arms.items():
        print(f"| {a} | {v['runs']} | {v['mean_lives']} | {v['seeds_grounded_any']} | {v['seeds_s1']} | {v['seeds_s2']} | "
              f"{v['L1']}/10 | {v['L2']}/10 | {v['L3']}/10 | {v['L3_posthoc']} |")
    for a, v in arms.items():
        if v["L2_events"]:
            print("L2 events", a, v["L2_events"])
    for a, v in state.items():
        print("state intervention", a, v["passes"])


if __name__ == "__main__":
    main(sys.argv[1])
