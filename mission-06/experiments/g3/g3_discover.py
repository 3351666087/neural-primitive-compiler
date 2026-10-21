"""Gate 3, phase A (EXPERIMENT_PRE_REGISTRATION.md section G3-M2): B's active discrimination experiments on 20
discovery games. CONSTRUCTOR SIDE orchestrator (import guard first); the judge process serves text only.

Exploration: visit the receptacles in the order of the first observation (open closed ones), at most 30 steps per game.
When `go to r` gives no arrival at r: (1) `examine r` (needs presence, no side effect); (2) retry `go to r`.
Symmetry: after the next successful arrival elsewhere, `go to r` (from elsewhere it should arrive; if it does not, r is
co-located with this place too and no test is counted) then `go to r0` (r0 = where the failure happened; under H_co it
is co-located with r, so it should give no arrival).
Hypotheses: H_co (already at r's place: examine succeeds, retry fails), H_un (unreachable: examine fails), H_noise
(retry succeeds). Also counts object type -> receptacle type from every listed content (location prior P_loc).

  mission-06/env/venv-alf/bin/python -I mission-06/experiments/g3/g3_discover.py    # writes g3_discovery.json
"""

import json
import multiprocessing as mp
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "g1"))
import belief as BL  # noqa: E402
import harness  # noqa: E402

LISTING = re.compile(r"(?:(?:On|In) the (\w+ \d+),|The (\w+ \d+) is open\. In it,) you see (.*?)\.(?:\s|$)")


def _judge(conn, set_name, max_steps, out_path):
    sys.path.insert(0, str(HERE))
    import judge
    judge.judge_proc(conn, set_name, max_steps, out_path)


def main():
    harness.guard_imports()
    harness.FORBIDDEN_MODULES = harness.FORBIDDEN_MODULES + ("alfworld", "textworld", "alf_judge", "games", "judge")
    smoke = "--smoke" in sys.argv                 # code check on already-used games; outputs go to $TMPDIR
    tmp = Path(__import__("os").environ.get("TMPDIR", "/tmp"))
    out_path = (tmp if smoke else HERE) / "g3_discovery_judge.jsonl"
    if out_path.exists():
        out_path.unlink()
    ctx = mp.get_context("spawn")
    a, b = ctx.Pipe()
    p = ctx.Process(target=_judge, args=(b, "smoke" if smoke else "discovery", 30, str(out_path)))
    p.start()

    def ask(msg):
        a.send(msg)
        return a.recv()[1]
    n = ask(("count", None))
    ev = {"failures": 0, "examine_ok": 0, "examine_fail": 0, "retry_arrived": 0, "retry_failed": 0,
          "sym_tests": 0, "sym_back_colocated": 0, "sym_r0_noarrival": 0, "steps": 0}
    prior = defaultdict(lambda: defaultdict(int))
    for i in range(n):
        first = ask(("start", ("A", i)))
        hist = [(None, first)]
        steps = [0]

        def act(cmd):
            steps[0] += 1
            o = ask(("act", cmd))
            hist.append((cmd, o))
            for r1, r2, lst in LISTING.findall(o.replace("\n", " ")):  # the receptacle is named in the listing text
                rec = r1 or r2
                for obj in BL._items(lst):
                    prior[obj.split(" ")[0]][rec.split(" ")[0]] += 1
            return o
        m = re.search(r"Looking quickly around you, you see (.*?)\.\s", first.replace("\n", " ") + " ")
        recs = BL._items(m.group(1)) if m else []
        pending_sym = None
        for r in recs:
            if steps[0] >= 26:
                break
            b = BL.belief_after(hist)
            r0 = b.location
            o = act(f"go to {r}")
            if f"You arrive at {r}" in o:
                if "is closed" in o:
                    act(f"open {r}")
                if pending_sym and steps[0] <= 27 and pending_sym[0] != r and pending_sym[1] != r:
                    rf, rprev = pending_sym
                    o2 = act(f"go to {rf}")
                    if f"You arrive at {rf}" in o2:               # arrived at rf from elsewhere: r0 must be co-located
                        ev["sym_tests"] += 1
                        o3 = act(f"go to {rprev}")
                        ev["sym_r0_noarrival"] += f"You arrive at {rprev}" not in o3
                    else:                                          # rf co-located with r as well: not a test
                        ev["sym_back_colocated"] += 1
                    pending_sym = None
                continue
            ev["failures"] += 1
            o = act(f"examine {r}")
            ok = r in o and "Nothing happens" not in o
            ev["examine_ok" if ok else "examine_fail"] += 1
            o = act(f"go to {r}")
            ev["retry_arrived" if f"You arrive at {r}" in o else "retry_failed"] += 1
            if pending_sym is None and r0:
                pending_sym = (r, r0)
        ev["steps"] += steps[0]
        ask(("end", None))
    ask(("stop", None))
    p.join(timeout=60)
    f = ev["failures"]
    contradictions = ev["examine_fail"] + ev["retry_arrived"] + (ev["sym_tests"] - ev["sym_r0_noarrival"])
    adopt = f > 0 and ev["sym_tests"] > 0 and contradictions == 0
    out = {"label": "Gate 3 phase A: discrimination experiments and location prior", "games": n, "evidence": ev,
           "hypotheses": {"H_co (already at r's place)": {"examine_ok": ev["examine_ok"], "retry_failed": ev["retry_failed"]},
                          "H_un (unreachable)": {"examine_fail": ev["examine_fail"]},
                          "H_noise (random)": {"retry_arrived": ev["retry_arrived"]}},
           "contradictions_of_H_co": contradictions, "L_co_adopted": adopt, "P_loc": {k: dict(v) for k, v in prior.items()}}
    ((tmp if smoke else HERE) / "g3_discovery.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "P_loc"}, indent=1))
    print("P_loc object types:", len(out["P_loc"]))


if __name__ == "__main__":
    main()
