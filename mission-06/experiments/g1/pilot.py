"""WorkArena deployment pilot, steps P2 and P3 (EXPERIMENT_PRE_REGISTRATION.md, section G1-P). No ServiceNow instance
and no external site is contacted: the environment is BrowserGym's open-ended task on local_page.html (file://).

This process is the CONSTRUCTOR side: it installs the import guard first, then starts the judge process
(harness.judge_main, spawned, so the guard does not apply there) and talks to it only through harness.Client.

  P2  Chromium starts headless; reset gives an observation; the constructor finds the text box and the button in the
      AXTree, fills the box, clicks the button, and sees "saved: <text>" in the next AXTree
  P3  every key the constructor received is in OBS_ALLOW; no reward / terminated / info crossed the boundary; importing
      browsergym.workarena on the constructor side is refused by the import guard itself (not merely missing); a static
      scan finds no forbidden import in mission-06 modules carrying the constructor-side marker

  PLAYWRIGHT_BROWSERS_PATH=mission-06/env/ms-playwright mission-06/env/venv-wa/bin/python -I \
      mission-06/experiments/g1/pilot.py        # writes pilot_p2p3.json and judge_log.jsonl
"""

from __future__ import annotations

import ast
import json
import multiprocessing as mp
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import harness  # noqa: E402

M06 = HERE.parents[1]


def find(axtree, role, text=None):
    for n in axtree.get("nodes", []):
        r = (n.get("role") or {}).get("value")
        nm = (n.get("name") or {}).get("value", "")
        if r == role and (text is None or text in str(nm)):
            return n.get("browsergym_id"), nm
    return None, None


def all_names(axtree):
    return [str((n.get("name") or {}).get("value", "")) for n in axtree.get("nodes", [])]


def static_scan():
    bad = []
    for f in sorted((M06 / "experiments").rglob("*.py")):
        tree = ast.parse(f.read_text())
        doc = ast.get_docstring(tree) or ""
        if "CONSTRUCTOR SIDE" not in doc or "JUDGE SIDE" in doc:   # mixed modules (harness.py) are split by process
            continue
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for nm in names:
                if any(nm == m or nm.startswith(m + ".") for m in harness.FORBIDDEN_MODULES) or nm in ("truth",):
                    bad.append(f"{f.relative_to(M06)}: {nm}")
    return bad


def main():
    t0 = time.perf_counter()
    guard = harness.guard_imports()
    out = {"label": "G1-P2/P3 (Mission 06): BrowserGym local smoke test and judge/constructor isolation"}
    url = (HERE / "local_page.html").resolve().as_uri()
    log_path = str(HERE / "judge_log.jsonl")
    ctx = mp.get_context("spawn")
    a, b = ctx.Pipe()
    judge = ctx.Process(target=harness.judge_main, args=(b, {"kind": "local", "url": url}, log_path))
    judge.start()
    cl = harness.Client(a)
    received = set()
    p2 = {}
    try:
        obs = cl.reset(seed=0)
        received |= set(obs)
        p2["reset_s"] = round(time.perf_counter() - t0, 2)
        box, _ = find(obs["axtree_object"], "textbox")
        btn, _ = find(obs["axtree_object"], "button", "Save")
        p2["found_bids"] = {"textbox": box, "button": btn}
        obs = cl.step(f'fill("{box}", "pilot record")')
        received |= set(obs)
        p2["fill_error"] = obs.get("last_action_error", "")
        obs = cl.step(f'click("{btn}")')
        received |= set(obs)
        p2["click_error"] = obs.get("last_action_error", "")
        p2["saved_visible"] = any("saved: pilot record" in s for s in all_names(obs["axtree_object"]))
        p2["screenshot_shape"] = list(getattr(obs.get("screenshot"), "shape", []))
        cl.close()
    except Exception as e:                                     # noqa: BLE001
        p2["error"] = f"{type(e).__name__}: {e}"
    judge.join(timeout=60)
    out["P2"] = {**p2, "verdict": "HOLDS" if p2.get("saved_visible") and not p2.get("error") else "FALSIFIED"}
    try:
        import browsergym.workarena  # noqa: F401
    except ImportError:
        pass
    refused = "browsergym.workarena" in guard.attempts                 # refused by the guard, not merely absent
    judge_log = [json.loads(x) for x in Path(log_path).read_text().splitlines()]
    leaked = sorted(received - set(harness.OBS_ALLOW))
    scan = static_scan()
    out["P3"] = {"received_keys": sorted(received), "outside_allowlist": leaked,
                 "judge_side_obs_keys": judge_log[0].get("obs_keys") if judge_log else None,
                 "judge_side_info_keys": judge_log[0].get("info_keys") if judge_log else None,
                 "workarena_import_refused": refused, "guard_attempts": guard.attempts, "static_scan_violations": scan,
                 "verdict": "HOLDS" if (not leaked and refused and not scan) else "FALSIFIED"}
    freeze = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True).stdout.split()
    out["pip_freeze"] = freeze
    out["python"] = sys.version
    out["time_s"] = round(time.perf_counter() - t0, 1)
    (HERE / "pilot_p2p3.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: (v["verdict"] if isinstance(v, dict) and "verdict" in v else None) for k, v in out.items()
                      if k in ("P2", "P3")}), out["time_s"], "s")


if __name__ == "__main__":
    main()
