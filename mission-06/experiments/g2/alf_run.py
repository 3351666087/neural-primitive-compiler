"""G2-ALF runner (EXPERIMENT_PRE_REGISTRATION.md section G2-ALF): strict frozen core (G2A-0), axiom contracts with
monitors (G2A-1) and the HTN baseline (B1) on 60 ALFWorld training games, 50 steps each.

Process layout as in the G1 pilots: this process is the constructor side (import guard first); one spawned judge
process holds the game files and the environment and serves text observations for a game index. Success (`won`) is
written by the judge to a judge-only file and merged by the scorer afterwards; the constructor never receives it.

  mission-06/env/venv-alf/bin/python -I mission-06/experiments/g2/alf_run.py     # writes g2alf_*.json(l)
"""

from __future__ import annotations

import json
import multiprocessing as mp
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
G1 = HERE.parent / "g1"
B2 = HERE.parent / "b2"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(G1))
import alf_core as C  # noqa: E402
import harness  # noqa: E402

DATA = str(HERE.parents[1] / "env" / "alfworld-data")
MAX_STEPS = 50
JUDGE_OUT = HERE / "g2alf_judge.jsonl"
CONS_OUT = HERE / "g2alf_constructor.jsonl"


def pick_games():
    """Judge side: 10 train games per task type (seed 65), excluding the games of P-ALF-1, B2P0 and the server test."""
    sys.path.insert(0, str(B2))
    import alf_judge as J
    import alf_server as S
    used = set(J.sample_games(DATA, "train", 10, 61)[0])
    used |= set(S.pick_games(2, False)[0]) | set(S.pick_games(1, True)[0])
    games = [(g, t) for g, t in J.list_games(DATA, "train") if g not in used]
    rng = random.Random(65)
    out = []
    for t in J.TASK_TYPES.values():
        out += [(g, t) for g in rng.sample(sorted(g for g, tt in games if tt == t), 10)]
    return out


def judge_proc(conn):
    """JUDGE SIDE: serves text observations; records won / steps per (variant, game index) in a judge-only file."""
    import alf_judge as J
    games = pick_games()
    log = open(JUDGE_OUT, "a")
    g, cur, steps, won = None, None, 0, False

    def finish():
        nonlocal g
        if g is not None:
            log.write(json.dumps({"variant": cur[0], "game": cur[1], "task_type": games[cur[1]][1], "won": won,
                                  "steps": steps}) + "\n")
            log.flush()
            g.close()
            g = None
    while True:
        kind, payload = conn.recv()
        if kind == "count":
            conn.send(("n", len(games)))
        elif kind == "start":
            finish()
            cur, steps = payload, 0
            g = J.Game(games[payload[1]][0], max_steps=MAX_STEPS + 5)
            obs, info = g.reset()
            won = bool(info["won"])
            conn.send(("obs", obs))
        elif kind == "act":
            if steps >= MAX_STEPS:
                conn.send(("obs", "[step limit]"))
                continue
            steps += 1
            if won:
                obs = "Nothing happens."
            else:
                obs, _s, _d, info = g.step(payload)
                won = bool(info["won"])
            conn.send(("obs", obs))
        elif kind == "end":
            finish()
            conn.send(("ok", None))
        elif kind == "stop":
            finish()
            conn.send(("ok", None))
            break


def main():
    t0 = time.perf_counter()
    harness.guard_imports()
    harness.FORBIDDEN_MODULES = harness.FORBIDDEN_MODULES + ("alfworld", "textworld", "alf_judge", "alf_server")
    for f in (JUDGE_OUT, CONS_OUT):
        if f.exists():
            f.unlink()
    ctx = mp.get_context("spawn")
    a, b = ctx.Pipe()
    p = ctx.Process(target=judge_proc, args=(b,))
    p.start()

    def ask(msg):
        a.send(msg)
        return a.recv()[1]
    n = ask(("count", None))
    cons = open(CONS_OUT, "a")
    for variant in ("G2A-0", "G2A-1", "B1"):
        for i in range(n):
            first = ask(("start", (variant, i)))
            atoms = C.parse_goal(BL_goal(first))
            rec = {"variant": variant, "game": i, "atoms": atoms}
            if variant == "G2A-0":
                order, why = C.construct(atoms, accept=("P", "M"))
                rec.update({"constructed": order is not None, "reason": why, "outcome": "not constructed", "steps": 0})
            else:
                order, why = C.construct(atoms)
                rec.update({"constructed": order is not None, "reason": why})
                agent = C.Agent(lambda cmd: ask(("act", cmd)), first, MAX_STEPS, monitors=(variant == "G2A-1"))
                if order is None:
                    rec["outcome"] = "not constructed"
                else:
                    try:
                        rec["outcome"] = C.run_priority(agent, order) if variant == "G2A-1" else C.run_htn(agent, atoms)
                    except C.Abstain as e:
                        rec["outcome"] = f"abstain: {e}"
                rec.update({"steps": agent.steps, "violations": agent.violations})
            ask(("end", None))
            cons.write(json.dumps(rec) + "\n")
            cons.flush()
        print(variant, "done", round(time.perf_counter() - t0, 1), "s", flush=True)
    ask(("stop", None))
    p.join(timeout=60)
    print("total", round(time.perf_counter() - t0, 1), "s")


def BL_goal(first_obs):
    import belief as BL
    return BL.belief_after([(None, first_obs)]).goal


if __name__ == "__main__":
    main()
