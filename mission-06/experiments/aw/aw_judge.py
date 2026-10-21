"""AppWorld on the judge side (Mission 06, EXPERIMENT_PRE_REGISTRATION.md section G1-AW). JUDGE SIDE.

judge_proc runs in its own process and holds the AppWorld world (with evaluate, ground truth, save/load_state,
expose_internals). Only development tasks (train, dev) can be opened. Across the pipe the constructor receives only:
the task instruction, the supervisor's public profile (first name, last name, email, phone number) and the string output
of each execute. The number of executes is capped per run (registered before the run) and every run is entered in the
interaction ledger (task IDs and counts only). Logs with task text stay under env/appworld (gitignored: the AppWorld
license forbids plaintext redistribution of the decrypted data).

Protocol: ("list_dev", None) -> ("ids", [...]); ("open", task_id) -> ("task", {instruction, supervisor});
("exec", code) -> ("out", str); ("close", None) -> ("closed", None); ("probe_test_refusal", None) -> ("refused", bool).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "env" / "appworld"
LOGDIR = ROOT / "m06_logs"
LEDGER = Path(__file__).resolve().parent / "interaction_ledger.jsonl"
PROFILE_KEYS = ("first_name", "last_name", "email", "phone_number")


def _profile(sup):
    get = (lambda k: sup.get(k)) if isinstance(sup, dict) else (lambda k: getattr(sup, k, None))
    return {k: get(k) for k in PROFILE_KEYS}


def judge_proc(conn, run_id: str, cap: int):
    os.environ["APPWORLD_ROOT"] = str(ROOT)
    LOGDIR.mkdir(parents=True, exist_ok=True)
    from appworld import AppWorld, load_task_ids
    dev = set(load_task_ids("train")) | set(load_task_ids("dev"))
    log = open(LOGDIR / f"{run_id}.jsonl", "a")
    w = lambda **k: (log.write(json.dumps({"t": time.strftime("%H:%M:%S"), **k}, default=str) + "\n"), log.flush())
    world, task_id, n = None, None, 0
    run = {"run_id": run_id, "cap": cap, "tasks": [], "executes": 0, "refused": [], "results": []}
    try:
        while True:
            kind, payload = conn.recv()
            if kind == "list_dev":
                conn.send(("ids", sorted(dev)))
            elif kind == "probe_test_refusal":
                tid = sorted(load_task_ids("test_normal"))[0]
                ok = tid not in dev
                run["refused"].append("test-split task requested (probe)")
                conn.send(("refused", ok))
            elif kind == "open":
                if payload not in dev:
                    run["refused"].append("non-development task requested")
                    conn.send(("error", "not a development task"))
                    continue
                if world is not None:
                    conn.send(("error", "close the current task first"))
                    continue
                t0 = time.perf_counter()
                world, task_id, n = AppWorld(task_id=payload, experiment_name=f"m06_{run_id}"), payload, 0
                run["tasks"].append(payload)
                info = {"instruction": world.task.instruction, "supervisor": _profile(world.task.supervisor)}
                w(event="open", task=payload, open_s=round(time.perf_counter() - t0, 2), **info)
                conn.send(("task", info))
            elif kind == "exec":
                if world is None:
                    conn.send(("error", "no open task"))
                    continue
                if n >= cap:
                    run["refused"].append("execute beyond cap")
                    conn.send(("error", "execute cap reached"))
                    continue
                n += 1
                run["executes"] += 1
                t0 = time.perf_counter()
                out = world.execute(payload)
                w(event="exec", task=task_id, n=n, code=payload, out=out, exec_s=round(time.perf_counter() - t0, 3),
                  completed=world.task_completed())
                conn.send(("out", out))
            elif kind == "close":
                if world is not None:
                    tracker = world.evaluate()
                    res = {"task": task_id, "executes": n, "completed_flag": world.task_completed()}
                    for attr in ("success", "pass_count", "fail_count", "num_tests"):
                        res[attr] = getattr(tracker, attr, None)
                    if hasattr(tracker, "to_dict"):
                        res["report"] = tracker.to_dict()
                    run["results"].append({k: v for k, v in res.items() if k != "report"})
                    w(event="evaluate", **res)
                    world.close()
                    world = None
                conn.send(("closed", None))
            elif kind == "stop":
                conn.send(("stopped", None))
                break
            else:
                conn.send(("error", f"unknown message {kind}"))
    except Exception as e:                                     # noqa: BLE001
        run["refused"].append(f"{type(e).__name__}: {str(e)[:200]}")
        conn.send(("error", f"{type(e).__name__}: {str(e)[:300]}"))
    finally:
        if world is not None:
            world.close()
        log.close()
        run["end"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        with open(LEDGER, "a") as f:
            f.write(json.dumps(run, default=str) + "\n")
