"""G4b runner (EXPERIMENT_PRE_REGISTRATION.md section G4b): composite goals, three constructors on one executor.
CONSTRUCTOR SIDE orchestrator (import guard first); the judge process (judge4b.py) holds the rooms and the facts.

  venv-alf/bin/python -I g4b_run.py --set dev|heldout      writes g4b_<set>_judge.jsonl, g4b_<set>_constructor.jsonl
"""

import argparse
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
for d in (HERE, HERE.parent / "g1", HERE.parent / "g2", HERE.parent / "g3", HERE.parent / "g4"):
    sys.path.insert(0, str(d))
import alf_core as C  # noqa: E402
import cmp_core as K  # noqa: E402
import g3_core as G3  # noqa: E402
import g4_core as G4  # noqa: E402
import harness  # noqa: E402

MAX_STEPS = 100
ARMS = {"CMP-0": K.construct_frozen, "CMP-1": K.construct_upgraded, "SEQ": K.seq_method}


def _judge(conn, set_name, max_steps, out_path, lit_rule):
    sys.path.insert(0, str(HERE))
    import judge4b
    judge4b.judge_proc(conn, set_name, max_steps, out_path, lit_rule)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=("dev", "heldout"), required=True)
    ap.add_argument("--official-lit", action="store_true", help="POST-HOC: judge LIT with the official ALFWorld condition")
    a = ap.parse_args()
    t0 = time.perf_counter()
    harness.guard_imports()
    harness.FORBIDDEN_MODULES = harness.FORBIDDEN_MODULES + ("alfworld", "textworld", "alf_judge", "cmp_env", "sets4b",
                                                             "judge4b", "games", "games4", "judge", "judge4")
    disc = json.loads((HERE.parent / "g3" / "g3_discovery.json").read_text())
    sfx = "_officiallit" if a.official_lit else ""
    judge_out, cons_out = HERE / f"g4b_{a.set}{sfx}_judge.jsonl", HERE / f"g4b_{a.set}{sfx}_constructor.jsonl"
    for f in (judge_out, cons_out):
        if f.exists():
            f.unlink()
    ctx = mp.get_context("spawn")
    pa, pb = ctx.Pipe()
    p = ctx.Process(target=_judge, args=(pb, a.set, MAX_STEPS, str(judge_out), "official" if a.official_lit else "objloc"))
    p.start()

    def ask(msg):
        pa.send(msg)
        return pa.recv()[1]
    n = ask(("count", None))
    print(a.set, "goals", n, flush=True)
    cons = open(cons_out, "a")
    for arm, build in ARMS.items():
        for i in range(n):
            first, atoms = ask(("start", (arm, i)))
            order, why = build(atoms)
            rec = {"variant": arm, "game": i, "atoms": atoms, "order": order, "constructed": order is not None, "reason": why}
            agent = G4.Agent4(lambda cmd: ask(("act", cmd)), first, MAX_STEPS, law=disc["L_co_adopted"], monitor="literal",
                              prior=disc["P_loc"], recover=2)
            if order is None:
                rec["outcome"] = "not constructed"
            else:
                try:
                    rec["outcome"] = G3.run_priority3(agent, [tuple(x) for x in order])
                except C.Abstain as e:
                    rec["outcome"] = f"abstain: {e}"
            rec.update({"steps": agent.steps, "violations": agent.violations, "retries": agent.retries})
            ask(("end", None))
            cons.write(json.dumps(rec) + "\n")
            cons.flush()
        print(a.set, arm, "done", round(time.perf_counter() - t0, 1), "s", flush=True)
    ask(("stop", None))
    p.join(timeout=60)


if __name__ == "__main__":
    main()
