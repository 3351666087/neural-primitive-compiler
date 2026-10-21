"""JUDGE SIDE process for G4b: serves a composite-goal room by index (rewritten first observation and the goal atoms,
the goal-level logical specification), then text observations; judges success from the state facts at "end" and writes
it to a judge-only file."""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def judge_proc(conn, set_name, max_steps, out_path, lit_rule="objloc"):
    sys.path.insert(0, str(HERE))
    import cmp_env as E
    import sets4b as S
    goals = getattr(S, set_name)()
    log = open(out_path, "a")
    g, cur, steps = None, None, 0

    def finish():
        nonlocal g
        if g is not None:
            log.write(json.dumps({"variant": cur[0], "game": cur[1], "family": goals[cur[1]][1], "won": g.success(),
                                  "orig_won": g.orig_won, "steps": steps, "depth": len(g.atoms)}) + "\n")
            log.flush()
            g.close()
            g = None
    while True:
        kind, payload = conn.recv()
        if kind == "count":
            conn.send(("n", len(goals)))
        elif kind == "start":
            finish()
            cur, steps = payload, 0
            game_file, _fam, spec = goals[payload[1]]
            g = E.CompositeGame(game_file, spec, max_steps, lit_rule)
            conn.send(("obs", (g.reset(), spec["atoms"])))
        elif kind == "act":
            if steps >= max_steps:
                conn.send(("obs", "[step limit]"))
                continue
            steps += 1
            conn.send(("obs", g.step(payload)))
        elif kind in ("end", "stop"):
            finish()
            conn.send(("ok", None))
            if kind == "stop":
                break
