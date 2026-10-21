"""G1-P4 step 2 (EXPERIMENT_PRE_REGISTRATION.md section G1-P4): open one development L1 task through the D2-guarded
judge process, read the first observation, take no action, close. This process is the constructor side (import guard
first). Records sizes and timings and the goal text of this development task; not the instance URL.

  PLAYWRIGHT_BROWSERS_PATH=mission-06/env/ms-playwright mission-06/env/venv-wa/bin/python -I mission-06/experiments/g1/p4.py
"""

from __future__ import annotations

import json
import multiprocessing as mp
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import harness  # noqa: E402

SPEC = {"kind": "workarena", "allow_instance": True, "task": "workarena.servicenow.all-menu", "step_cap": 1,
        "run_id": "G1-P4"}


def main():
    guard = harness.guard_imports()
    from browsergym.utils.obs import flatten_axtree_to_str, flatten_dom_to_str
    ctx = mp.get_context("spawn")
    a, b = ctx.Pipe()
    p = ctx.Process(target=harness.judge_main, args=(b, SPEC, str(HERE / "judge_log_p4.jsonl")))
    t0 = time.perf_counter()
    p.start()
    cl = harness.Client(a)
    out = {"label": "G1-P4 (Mission 06): first instance contact", "run_id": SPEC["run_id"], "task": SPEC["task"],
           "seed": 10}
    try:
        obs = cl.reset(seed=10)
        out["reset_s"] = round(time.perf_counter() - t0, 1)
        ax = flatten_axtree_to_str(obs["axtree_object"])
        dom = flatten_dom_to_str(obs["dom_object"])
        out.update({"received_keys": sorted(obs), "goal": obs.get("goal"), "url_path": urlparse(obs.get("url", "")).path,
                    "axtree_chars": len(ax), "axtree_tokens_est": len(ax) // 4, "axtree_nodes": len(obs["axtree_object"].get("nodes", [])),
                    "dom_chars": len(dom), "dom_tokens_est": len(dom) // 4,
                    "screenshot_shape": list(getattr(obs.get("screenshot"), "shape", []))})
        cl.close()
    except Exception as e:                                     # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {str(e)[:300]}"
    p.join(timeout=120)
    out["guard_attempts"] = guard.attempts
    out["predictions"] = {"P4-a": "HOLDS" if out.get("reset_s", 1e9) <= 120 and "error" not in out else "FALSIFIED",
                          "P4-b": "HOLDS" if out.get("axtree_tokens_est", 0) >= 3000 else "FALSIFIED"}
    (HERE / "p4.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: v for k, v in out.items() if k != "received_keys"}, indent=1, default=str))


if __name__ == "__main__":
    main()
