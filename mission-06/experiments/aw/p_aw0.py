"""P-AW-0 (a)(b): structure profile of AppWorld development tasks (EXPERIMENT_PRE_REGISTRATION.md section G2-0).
JUDGE-SIDE MEASUREMENT: reads the released ground truth of train/dev tasks (solution.py, api_calls.json, answer.json,
metadata.json) and the environment's own API docs; outputs only task IDs and numbers (no task text, no code), so it is
not an input to any constructor.

Sample: 40 tasks from sorted(train + dev), random.Random(64).
Features per task:
  answer_required   answer.json is not null / empty
  n_read, n_write, n_auth   from api_calls.json by HTTP method (GET = read); auth = login / logout; the final
                    supervisor.complete_task is counted apart
  loops, paginated  For / While nodes in solution.py; a loop whose body mentions `page_index`
  bind_depth        data flow in solution.py: an API call's level = 1 + the highest level among values its arguments
                    use; variables take the level of what they are assigned from. Protocol sources are level 0: logins,
                    supervisor.* (profile, account passwords). bind_depth = highest argument level over write calls
                    (excluding complete_task and auth); bind_depth_answer = argument level of complete_task(answer=...)
Gap types of the frozen contract core (rule locked in G2-0 (b)): information goal (answer_required), runtime query
binding (bind_depth >= 1), iteration contract (loops or paginated), global no-collateral-damage contract (n_write >= 1).

  mission-06/env/venv-aw/bin/python -I mission-06/experiments/aw/p_aw0.py        # writes p_aw0.json
"""

from __future__ import annotations

import ast
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parents[1] / "env" / "appworld" / "data"
AUTH = {"login", "logout"}


def methods():
    m = {}
    for f in (DATA / "api_docs" / "standard").glob("*.json"):
        for api, e in json.loads(f.read_text()).items():
            m[(e["app_name"], e["api_name"])] = e["method"]
    return m


def api_of(node):
    f = node.func
    if (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Attribute) and isinstance(f.value.value, ast.Name)
            and f.value.value.id == "apis"):
        return f.value.attr, f.attr
    return None


class Flow:
    def __init__(self):
        self.level = {}
        self.calls = []                    # (app, api, argument level)

    def expr_level(self, node):
        lv = 0
        for n in ast.walk(node):
            if isinstance(n, ast.Name) and n.id in self.level:
                lv = max(lv, self.level[n.id])
            elif isinstance(n, ast.Call) and api_of(n):
                lv = max(lv, self.result_level(n))
        return lv

    def result_level(self, call):
        app, api = api_of(call)
        if app == "supervisor" or api in AUTH:
            return 0
        a = max([self.expr_level(x) for x in list(call.args) + [k.value for k in call.keywords]] or [0])
        return a + 1

    def record_calls(self, node):
        for n in ast.walk(node):
            if isinstance(n, ast.Call) and api_of(n):
                a = max([self.expr_level(x) for x in list(n.args) + [k.value for k in n.keywords]] or [0])
                self.calls.append((*api_of(n), a))

    def assign(self, target, lv):
        for n in ast.walk(target):
            if isinstance(n, ast.Name):
                self.level[n.id] = max(self.level.get(n.id, 0), lv)

    def run(self, stmts):
        for s in stmts:
            if isinstance(s, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                val = s.value
                if val is None:
                    continue
                self.record_calls(val)
                lv = self.expr_level(val)
                for t in (s.targets if isinstance(s, ast.Assign) else [s.target]):
                    self.assign(t, lv)
            elif isinstance(s, (ast.For, ast.AsyncFor)):
                self.record_calls(s.iter)
                self.assign(s.target, self.expr_level(s.iter))
                self.run(s.body)
                self.run(s.body)           # second pass: loop-carried values
                self.run(s.orelse)
            elif isinstance(s, ast.While):
                self.record_calls(s.test)
                self.run(s.body)
                self.run(s.body)
            elif isinstance(s, ast.If):
                self.record_calls(s.test)
                self.run(s.body)
                self.run(s.orelse)
            elif isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.run(s.body)
            elif isinstance(s, (ast.With, ast.AsyncWith, ast.Try)):
                for blk in ("body", "orelse", "finalbody"):
                    self.run(getattr(s, blk, []) or [])
                for h in getattr(s, "handlers", []) or []:
                    self.run(h.body)
            else:
                self.record_calls(s)


def analyse(task_id, M):
    gt = DATA / "tasks" / task_id / "ground_truth"
    meta = json.loads((gt / "metadata.json").read_text())
    calls = json.loads((gt / "api_calls.json").read_text())
    answer = json.loads((gt / "answer.json").read_text())
    src = (gt / "solution.py").read_text()
    tree = ast.parse(src)
    n_read = n_write = n_auth = n_complete = 0
    for c in calls:
        parts = c["url"].strip("/").split("/")
        app = parts[0] if parts else ""
        if "auth" in parts and ("token" in parts or "login" in c["url"]):
            n_auth += 1
        elif app == "supervisor" and "complete" in c["url"]:
            n_complete += 1
        elif c["method"].upper() == "GET":
            n_read += 1
        else:
            n_write += 1
    loops = sum(isinstance(n, (ast.For, ast.While, ast.AsyncFor)) for n in ast.walk(tree))
    paginated = any(isinstance(n, (ast.For, ast.While)) and any(isinstance(x, ast.Name) and x.id == "page_index"
                                                                   for x in ast.walk(n)) for n in ast.walk(tree))
    fl = Flow()
    fl.run(tree.body)
    wdepth = max([lv for app, api, lv in fl.calls if M.get((app, api), "GET") != "GET" and api not in AUTH
                  and not (app == "supervisor" and api == "complete_task")] or [0])
    adepth = max([lv for app, api, lv in fl.calls if app == "supervisor" and api == "complete_task"] or [0])
    ans = answer not in (None, "", [], {})
    feat = {"answer_required": ans, "n_read": n_read, "n_write": n_write, "n_auth": n_auth, "n_complete": n_complete,
            "loops": loops, "paginated": paginated, "bind_depth": wdepth, "bind_depth_answer": adepth,
            "num_apps": meta.get("num_apps"), "num_apis": meta.get("num_apis"), "num_api_calls": meta.get("num_api_calls"),
            "difficulty": meta.get("difficulty"), "solution_lines": meta.get("num_solution_code_lines")}
    gaps = {"information_goal": ans, "runtime_query_binding": wdepth >= 1 or (ans and adepth >= 1),
            "iteration": loops > 0 or paginated, "global_no_collateral_damage": n_write >= 1}
    feat["gaps"] = [k for k, v in gaps.items() if v]
    return feat


def main():
    ids = sorted(set((DATA / "datasets" / "train.txt").read_text().split()) | set((DATA / "datasets" / "dev.txt").read_text().split()))
    sample = sorted(random.Random(64).sample(ids, 40))
    M = methods()
    feats = {t: analyse(t, M) for t in sample}
    n = len(feats)
    frac = lambda f: sum(1 for v in feats.values() if f(v)) / n
    agg = {"tasks": n, "pool": len(ids),
           "answer_required": frac(lambda v: v["answer_required"]),
           "bind_depth_ge1_writes": frac(lambda v: v["bind_depth"] >= 1),
           "bind_depth_ge1_writes_or_answer": frac(lambda v: v["bind_depth"] >= 1 or (v["answer_required"] and v["bind_depth_answer"] >= 1)),
           "loops_or_paginated": frac(lambda v: v["loops"] > 0 or v["paginated"]),
           "paginated": frac(lambda v: v["paginated"]),
           "any_write": frac(lambda v: v["n_write"] >= 1),
           "two_or_more_gaps": frac(lambda v: len(v["gaps"]) >= 2),
           "gap_counts": {g: sum(g in v["gaps"] for v in feats.values()) for g in
                          ("information_goal", "runtime_query_binding", "iteration", "global_no_collateral_damage")},
           "median_api_calls": sorted(v["num_api_calls"] or 0 for v in feats.values())[n // 2],
           "max_bind_depth": max(max(v["bind_depth"], v["bind_depth_answer"]) for v in feats.values())}
    pred = {"answer >= 30%": agg["answer_required"] >= 0.30,
            "binding depth >= 1 (writes) >= 60%": agg["bind_depth_ge1_writes"] >= 0.60,
            "loops or pagination >= 30%": agg["loops_or_paginated"] >= 0.30,
            ">= 2 gap types >= 50%": agg["two_or_more_gaps"] >= 0.50}
    out = {"label": "P-AW-0 (a)(b) (Mission 06 G2-0): AppWorld dev task structure; judge-side measurement",
           "aggregate": agg, "predictions": {k: "HOLDS" if v else "FALSIFIED" for k, v in pred.items()}, "tasks": feats}
    (HERE / "p_aw0.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({"aggregate": agg, "predictions": out["predictions"]}, indent=1))


if __name__ == "__main__":
    main()
