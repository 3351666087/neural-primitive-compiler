"""Gate 4 runner (EXPERIMENT_PRE_REGISTRATION.md section G4). CONSTRUCTOR SIDE orchestrator (import guard first); one
spawned judge process (judge4.py) per run serves text observations and writes `won` to a judge-only file.

Arms (all frozen; learned inputs only from ../g3/g3_discovery.json)
  G2A-1   G2 controller as it ran (axiom contracts, literal monitors)
  B1      G2 HTN baseline as it ran (no monitors)
  G3-L    G2A-1 + co-location law L_co
  G3-S    state-level (postcondition) monitors, no L_co
  G3-LP   G3-L + location prior P_loc
  G3-LPR  G3-LP + recovery (re-issue a manipulation whose feedback is unexpected, up to 2 times, then the monitor)
  B1-LPR  same-knowledge classical: HTN with L_co, P_loc and the same recovery, no monitors and no contracts

  venv-alf/bin/python -I g4_run.py --set dev60|heldout [--perturb]
writes g4_<set>_<clean|pert>_judge.jsonl and g4_<set>_<clean|pert>_constructor.jsonl
"""

import argparse
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "g1"))
sys.path.insert(0, str(HERE.parent / "g2"))
sys.path.insert(0, str(HERE.parent / "g3"))
import alf_core as C  # noqa: E402
import g3_core as G3  # noqa: E402
import g4_core as G4  # noqa: E402
import harness  # noqa: E402

MAX_STEPS = 50
ARMS = ("G2A-1", "B1", "G3-L", "G3-S", "G3-LP", "G3-LPR", "B1-LPR")
SEED_BASE = {"dev60": 7200, "heldout": 7300}


def _judge(conn, set_name, max_steps, out_path, seed_base):
    sys.path.insert(0, str(HERE))
    import judge4
    judge4.judge_proc(conn, set_name, max_steps, out_path, seed_base)


def make_agent(arm, act, first, disc):
    law, prior = disc["L_co_adopted"], disc["P_loc"]
    if arm == "G2A-1":
        return C.Agent(act, first, MAX_STEPS, monitors=True)
    if arm == "B1":
        return C.Agent(act, first, MAX_STEPS, monitors=False)
    if arm == "G3-L":
        return G3.Agent3(act, first, MAX_STEPS, law=law, monitor="literal")
    if arm == "G3-S":
        return G3.Agent3(act, first, MAX_STEPS, law=False, monitor="post")
    if arm == "G3-LP":
        return G3.Agent3(act, first, MAX_STEPS, law=law, monitor="literal", prior=prior)
    if arm == "G3-LPR":
        return G4.Agent4(act, first, MAX_STEPS, law=law, monitor="literal", prior=prior, recover=2)
    if arm == "B1-LPR":
        return G4.Agent4(act, first, MAX_STEPS, law=law, monitor="none", prior=prior, recover=2)
    raise ValueError(arm)


def run(agent, arm, atoms, order):
    if arm == "G2A-1":
        return C.run_priority(agent, order)
    if arm in ("B1", "B1-LPR"):
        return C.run_htn(agent, atoms)
    return G3.run_priority3(agent, order)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=("dev60", "heldout"), required=True)
    ap.add_argument("--perturb", action="store_true")
    ap.add_argument("--arms", default=",".join(ARMS))
    a = ap.parse_args()
    t0 = time.perf_counter()
    harness.guard_imports()
    harness.FORBIDDEN_MODULES = harness.FORBIDDEN_MODULES + ("alfworld", "textworld", "alf_judge", "games", "games4",
                                                             "judge", "judge4", "perturb", "alf_run", "alf_server")
    disc = json.loads((HERE.parent / "g3" / "g3_discovery.json").read_text())
    tag = f"{a.set}_{'pert' if a.perturb else 'clean'}"
    judge_out, cons_out = HERE / f"g4_{tag}_judge.jsonl", HERE / f"g4_{tag}_constructor.jsonl"
    for f in (judge_out, cons_out):
        if f.exists():
            f.unlink()
    ctx = mp.get_context("spawn")
    pa, pb = ctx.Pipe()
    p = ctx.Process(target=_judge, args=(pb, a.set, MAX_STEPS, str(judge_out), SEED_BASE[a.set] if a.perturb else None))
    p.start()

    def ask(msg):
        pa.send(msg)
        return pa.recv()[1]
    n = ask(("count", None))
    print(tag, "games", n, flush=True)
    cons = open(cons_out, "a")
    import belief as BL
    for arm in a.arms.split(","):
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
                        "colocated_hits": getattr(agent, "colocated_hits", None), "retries": getattr(agent, "retries", None)})
            ask(("end", None))
            cons.write(json.dumps(rec) + "\n")
            cons.flush()
        print(tag, arm, "done", round(time.perf_counter() - t0, 1), "s", flush=True)
    ask(("stop", None))
    p.join(timeout=60)
    print(tag, "total", round(time.perf_counter() - t0, 1), "s")


if __name__ == "__main__":
    main()
