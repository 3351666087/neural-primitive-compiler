"""Gate 3, phases B and C (EXPERIMENT_PRE_REGISTRATION.md section G3-M2): the arms on the 60 evaluation games (seed 68),
50 steps each. CONSTRUCTOR SIDE orchestrator (import guard first); one spawned judge process (judge.py) serves text
observations and writes `won` to a judge-only file that only the scorer reads.

Arms
  G2A-1  the G2 controller as it ran (alf_core.Agent, literal monitors, priority controller)
  B1     the G2 HTN baseline as it ran (alf_core.Agent, no monitors)
  G3-L   G2A-1 + the co-location law L_co (only if phase A adopted it)
  G3-S   state-level monitors: only each achiever's postcondition is checked; no L_co
  G3-LS  both
  G3-LP  G3-L + the location prior P_loc from phase A (search order)
Inputs from phase A: g3_discovery.json (L_co_adopted, P_loc). Nothing else from the discovery games is used.

  mission-06/env/venv-alf/bin/python -I mission-06/experiments/g3/g3_run.py    # writes g3_judge.jsonl, g3_constructor.jsonl
"""

import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "g1"))
sys.path.insert(0, str(HERE.parent / "g2"))
import alf_core as C  # noqa: E402
import g3_core as G3  # noqa: E402
import harness  # noqa: E402

MAX_STEPS = 50
JUDGE_OUT = HERE / "g3_judge.jsonl"
CONS_OUT = HERE / "g3_constructor.jsonl"
ARMS = ("G2A-1", "B1", "G3-L", "G3-S", "G3-LS", "G3-LP")


def _judge(conn, set_name, max_steps, out_path):
    sys.path.insert(0, str(HERE))
    import judge
    judge.judge_proc(conn, set_name, max_steps, out_path)


def make_agent(arm, act, first, disc):
    law = disc["L_co_adopted"]
    if arm == "G2A-1":
        return C.Agent(act, first, MAX_STEPS, monitors=True)
    if arm == "B1":
        return C.Agent(act, first, MAX_STEPS, monitors=False)
    if arm == "G3-L":
        return G3.Agent3(act, first, MAX_STEPS, law=law, monitor="literal")
    if arm == "G3-S":
        return G3.Agent3(act, first, MAX_STEPS, law=False, monitor="post")
    if arm == "G3-LS":
        return G3.Agent3(act, first, MAX_STEPS, law=law, monitor="post")
    if arm == "G3-LP":
        return G3.Agent3(act, first, MAX_STEPS, law=law, monitor="literal", prior=disc["P_loc"])
    raise ValueError(arm)


def run(agent, arm, atoms, order):
    if arm == "G2A-1":
        return C.run_priority(agent, order)
    if arm == "B1":
        return C.run_htn(agent, atoms)
    return G3.run_priority3(agent, order)


def main():
    t0 = time.perf_counter()
    harness.guard_imports()
    harness.FORBIDDEN_MODULES = harness.FORBIDDEN_MODULES + ("alfworld", "textworld", "alf_judge", "games", "judge",
                                                             "alf_run", "alf_server")
    smoke = "--smoke" in sys.argv                 # code check on already-used games; outputs go to $TMPDIR
    tmp = Path(__import__("os").environ.get("TMPDIR", "/tmp"))
    judge_out, cons_out = (tmp / JUDGE_OUT.name, tmp / CONS_OUT.name) if smoke else (JUDGE_OUT, CONS_OUT)
    disc = json.loads(((tmp if smoke else HERE) / "g3_discovery.json").read_text())
    for f in (judge_out, cons_out):
        if f.exists():
            f.unlink()
    ctx = mp.get_context("spawn")
    a, b = ctx.Pipe()
    p = ctx.Process(target=_judge, args=(b, "smoke" if smoke else "evaluation", MAX_STEPS, str(judge_out)))
    p.start()

    def ask(msg):
        a.send(msg)
        return a.recv()[1]
    n = ask(("count", None))
    cons = open(cons_out, "a")
    import belief as BL
    for arm in ARMS:
        for i in range(n):
            first = ask(("start", (arm, i)))
            atoms = C.parse_goal(BL.belief_after([(None, first)]).goal)
            order, why = C.construct(atoms)
            rec = {"variant": arm, "game": i, "atoms": atoms, "constructed": order is not None, "reason": why}
            agent = make_agent(arm, lambda cmd: ask(("act", cmd)), first, disc)
            if order is None:
                rec["outcome"] = "not constructed"
            else:
                try:
                    rec["outcome"] = run(agent, arm, atoms, order)
                except C.Abstain as e:
                    rec["outcome"] = f"abstain: {e}"
            rec.update({"steps": agent.steps, "violations": agent.violations,
                        "colocated_hits": getattr(agent, "colocated_hits", None)})
            ask(("end", None))
            cons.write(json.dumps(rec) + "\n")
            cons.flush()
        print(arm, "done", round(time.perf_counter() - t0, 1), "s", flush=True)
    ask(("stop", None))
    p.join(timeout=60)
    print("total", round(time.perf_counter() - t0, 1), "s")


if __name__ == "__main__":
    main()
