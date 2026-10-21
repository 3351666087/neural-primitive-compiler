"""JUDGE SIDE process for Gate 3: serves text observations of a named game set (games.py) by index, keeps `won`
private (judge-only JSONL), enforces the step limit. Protocol as in g2/alf_run.py."""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def judge_proc(conn, set_name, max_steps, out_path):
    sys.path.insert(0, str(HERE))
    import games as G
    import alf_judge as J
    games = getattr(G, set_name)()
    log = open(out_path, "a")
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
            else:
                obs, _s, _d, info = g.step(payload)
                won = bool(info["won"])
            conn.send(("obs", obs))
        elif kind in ("end", "stop"):
            finish()
            conn.send(("ok", None))
            if kind == "stop":
                break
