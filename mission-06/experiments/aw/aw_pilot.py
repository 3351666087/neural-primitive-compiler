"""AppWorld deployment pilot AW2/AW3 (EXPERIMENT_PRE_REGISTRATION.md section G1-AW). This process is the constructor
side: the import guard is installed first; the judge (aw_judge.judge_proc) runs in a spawned process.

Probes (task-agnostic, on the first train task in sorted order): the app list and the supervisor app's API list from
the environment's own documentation API, then two attempts to reach the file system (must be blocked), then close
without completing the task (the judge must score it as not completed).

  mission-06/env/venv-aw/bin/python -I mission-06/experiments/aw/aw_pilot.py      # writes aw_pilot.json
"""

from __future__ import annotations

import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "g1"))
import harness  # noqa: E402

RUN_ID, CAP = "G1-AW-pilot", 6
PROBES = {"app_list": "print(apis.api_docs.show_app_descriptions())",
          "supervisor_apis": "print(apis.api_docs.show_api_descriptions(app_name='supervisor'))",
          "import_os": "import os\nprint(os.listdir('/'))",
          "open_file": "print(open('/etc/hosts').read()[:20])"}


def _judge(conn, run_id, cap):
    """Runs in the spawned judge process only (no import guard there); the constructor process never imports aw_judge."""
    sys.path.insert(0, str(HERE))
    import aw_judge
    aw_judge.judge_proc(conn, run_id, cap)


def ask(conn, msg):
    conn.send(msg)
    kind, payload = conn.recv()
    if kind == "error":
        raise RuntimeError(payload)
    return kind, payload


def looks_blocked(out: str) -> bool:
    o = out.lower()
    return any(s in o for s in ("unsafe", "not allowed", "forbidden", "permission", "traceback", "error"))


def main():
    guard = harness.guard_imports()
    harness.FORBIDDEN_MODULES = harness.FORBIDDEN_MODULES + ("appworld", "aw_judge")
    ctx = mp.get_context("spawn")
    a, b = ctx.Pipe()
    p = ctx.Process(target=_judge, args=(b, RUN_ID, CAP))
    t0 = time.perf_counter()
    p.start()
    out = {"label": "G1-AW2/AW3 (Mission 06): AppWorld deployment pilot", "run_id": RUN_ID, "cap": CAP}
    crossed = set()
    try:
        _, refused = ask(a, ("probe_test_refusal", None))
        out["AW3-b_test_request_refused"] = refused
        _, ids = ask(a, ("list_dev", None))
        out["dev_ids"] = len(ids)
        t1 = time.perf_counter()
        _, task = ask(a, ("open", ids[0]))
        out["open_s"] = round(time.perf_counter() - t1, 2)
        crossed |= {f"task.{k}" for k in task} | {f"supervisor.{k}" for k in task["supervisor"]}
        out["instruction_chars"] = len(task["instruction"])
        probes = {}
        for name, code in PROBES.items():
            t2 = time.perf_counter()
            _, o = ask(a, ("exec", code))
            crossed.add(type(o).__name__)
            probes[name] = {"exec_s": round(time.perf_counter() - t2, 3), "chars": len(o), "tokens_est": len(o) // 4,
                            "blocked_or_error": looks_blocked(o)}
            if name in ("import_os", "open_file"):
                probes[name]["first_line"] = o.strip().splitlines()[-1][:160] if o.strip() else ""
        out["probes"] = probes
        ask(a, ("close", None))
        ask(a, ("stop", None))
    except Exception as e:                                     # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {e}"
    p.join(timeout=120)
    out["time_s"] = round(time.perf_counter() - t0, 1)
    try:
        import appworld  # noqa: F401
    except ImportError:
        pass
    sys.path.insert(0, str(HERE.parent / "g1"))
    import pilot
    out["crossed"] = sorted(crossed)
    out["guard_refused_appworld"] = "appworld" in guard.attempts
    out["static_scan_violations"] = pilot.static_scan()
    pr = out.get("probes", {})
    lat = sorted(v["exec_s"] for k, v in pr.items() if k in ("app_list", "supervisor_apis"))
    out["predictions"] = {
        "AW2-a": "HOLDS" if out.get("open_s", 1e9) <= 30 and lat and lat[len(lat) // 2] <= 2 else "FALSIFIED",
        "AW3-a": "HOLDS" if crossed and crossed <= {"task.instruction", "task.supervisor", "supervisor.first_name",
                                                    "supervisor.last_name", "supervisor.email",
                                                    "supervisor.phone_number", "str"} else "FALSIFIED",
        "AW3-b": "HOLDS" if out.get("AW3-b_test_request_refused") else "FALSIFIED",
        "AW3-c": "HOLDS" if pr and pr["import_os"]["blocked_or_error"] and pr["open_file"]["blocked_or_error"] else "FALSIFIED",
        "AW3-d": "HOLDS" if out["guard_refused_appworld"] and not out["static_scan_violations"] else "FALSIFIED",
        "AW2-b": "scored from the judge log"}
    (HERE / "aw_pilot.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: v for k, v in out.items() if k not in ("probes",)}, indent=1, default=str))
    print(json.dumps(out.get("probes"), indent=1))


if __name__ == "__main__":
    main()
