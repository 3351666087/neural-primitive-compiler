"""JUDGE SIDE process for Gate 4: serves text observations of a game set (games4.py) by index, optionally with the
perturbation of perturb.py (seed = seed_base + game index), keeps `won` private (judge-only JSONL)."""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def judge_proc(conn, set_name, max_steps, out_path, seed_base=None):
    sys.path.insert(0, str(HERE))
    sys.path.insert(0, str(HERE.parent / "g1"))
    import alf_judge as J
    import games4 as G
    import perturb as PT
    games = getattr(G, set_name)()
    log = open(out_path, "a")
    g, cur, steps, won, pt, n_pert = None, None, 0, False, None, 0

    def finish():
        nonlocal g
        if g is not None:
            log.write(json.dumps({"variant": cur[0], "game": cur[1], "task_type": games[cur[1]][1], "won": won,
                                  "steps": steps, "perturbed_actions": n_pert}) + "\n")
            log.flush()
            g.close()
            g = None
    while True:
        kind, payload = conn.recv()
        if kind == "count":
            conn.send(("n", len(games)))
        elif kind == "start":
            finish()
            cur, steps, n_pert = payload, 0, 0
            pt = PT.Perturb(seed_base + payload[1]) if seed_base is not None else None
            g = J.Game(games[payload[1]][0], max_steps=max_steps + 5)
            obs, info = g.reset()
            won = bool(info["won"])
            conn.send(("obs", obs))
        elif kind == "act":
            if steps >= max_steps:
                conn.send(("obs", "[step limit]"))
                continue
            steps += 1
            if won:
                obs = "Nothing happens."
            elif pt is not None and pt.fails(payload):
                n_pert += 1
                obs = "Nothing happens."
            else:
                obs, _s, _d, info = g.step(payload)
                won = bool(info["won"])
            conn.send(("obs", obs))
        elif kind in ("end", "stop"):
            finish()
            conn.send(("ok", None))
            if kind == "stop":
                break
