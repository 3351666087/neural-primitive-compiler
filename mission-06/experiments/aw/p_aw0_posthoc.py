"""POST-HOC recount of P-AW-0 (after the locked run; does not change its verdicts). Treats every supervisor.* call
(including POST supervisor/message, the completion protocol) as protocol rather than a write, and recomputes the write
count, the write binding depth and the gap profile. Judge-side measurement; outputs numbers only.

  mission-06/env/venv-aw/bin/python -I mission-06/experiments/aw/p_aw0_posthoc.py   # writes p_aw0_posthoc.json
"""

import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import p_aw0 as P  # noqa: E402


def main():
    d = json.loads((HERE / "p_aw0.json").read_text())
    M = P.methods()
    out = {}
    for t, v in d["tasks"].items():
        gt = P.DATA / "tasks" / t / "ground_truth"
        calls = json.loads((gt / "api_calls.json").read_text())
        writes = [c for c in calls if c["method"].upper() != "GET" and c["url"].strip("/").split("/")[0] != "supervisor"
                  and "auth" not in c["url"].strip("/").split("/")]
        fl = P.Flow()
        fl.run(P.ast.parse((gt / "solution.py").read_text()).body)
        wdepth = max([lv for app, api, lv in fl.calls if app != "supervisor" and api not in P.AUTH
                      and M.get((app, api), "GET") != "GET"] or [0])
        gaps = {"information_goal": v["answer_required"],
                "runtime_query_binding": wdepth >= 1 or (v["answer_required"] and v["bind_depth_answer"] >= 1),
                "iteration": v["loops"] > 0, "global_no_collateral_damage": len(writes) >= 1}
        out[t] = {"n_write": len(writes), "bind_depth": wdepth, "gaps": [k for k, x in gaps.items() if x],
                  "answer_required": v["answer_required"]}
    n = len(out)
    fr = lambda f: round(sum(1 for v in out.values() if f(v)) / n, 3)
    agg = {"state_change_tasks": fr(lambda v: v["n_write"] >= 1),
           "answer_only_tasks": fr(lambda v: v["answer_required"] and v["n_write"] == 0),
           "answer_and_state_change": fr(lambda v: v["answer_required"] and v["n_write"] >= 1),
           "bind_depth_ge1_writes": fr(lambda v: v["bind_depth"] >= 1),
           "bind_depth_ge1_among_state_change": round(sum(1 for v in out.values() if v["n_write"] >= 1 and v["bind_depth"] >= 1)
                                                      / max(1, sum(1 for v in out.values() if v["n_write"] >= 1)), 3),
           "two_or_more_gaps": fr(lambda v: len(v["gaps"]) >= 2),
           "gap_counts": {g: sum(g in v["gaps"] for v in out.values()) for g in
                          ("information_goal", "runtime_query_binding", "iteration", "global_no_collateral_damage")},
           "write_depth_distribution": {k: sum(1 for v in out.values() if v["bind_depth"] == k) for k in sorted({v["bind_depth"] for v in out.values()})}}
    (HERE / "p_aw0_posthoc.json").write_text(json.dumps({"label": "POST-HOC recount of P-AW-0", "aggregate": agg, "tasks": out}, indent=1))
    print(json.dumps(agg, indent=1))


if __name__ == "__main__":
    main()
