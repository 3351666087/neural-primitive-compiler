"""ALFWorld game server for the B2 feasibility pilot (EXPERIMENT_PRE_REGISTRATION.md section G1-B2P0). JUDGE SIDE.

Holds the TextWorld environment (expert off) and serves text observations only over a local Unix socket: no
admissible commands, no `won`, no score. Once a game is won, further actions get the neutral reply "Nothing happens."
so the agent does not learn success from the environment (the constructor does not either). Success, steps, commands
and observations go to a judge-only log.

Games: train split, seed 62, one game from each of N task types drawn at random, excluding the 60 P-ALF-1 games.
`--test` serves one different game for checking the server itself.

  mission-06/env/venv-alf/bin/python -I mission-06/experiments/b2/alf_server.py --sock $TMPDIR/m06b2.sock [--test]
Protocol (one JSON line per connection): {"cmd": "reset" | "act" | "done", "arg": "<command for act>"} -> {"obs": text}
"""

from __future__ import annotations

import argparse
import json
import os
import random
import socket
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "g1"))
import alf_judge as J  # noqa: E402

DATA = str(HERE.parents[1] / "env" / "alfworld-data")


def pick_games(n, test):
    games = J.list_games(DATA, "train")
    used, _ = J.sample_games(DATA, "train", 10, 61)
    pool = [(g, t) for g, t in games if g not in set(used)]
    rng = random.Random(63 if test else 62)
    types = rng.sample(sorted({t for _, t in pool}), 1 if test else n)
    return [rng.choice([g for g, t in pool if t == ty]) for ty in types], types


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sock", required=True)
    ap.add_argument("--n", type=int, default=2)
    ap.add_argument("--max-steps", type=int, default=40)
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--games-file", help="judge-side JSON list of {game, type} (overrides the default pick)")
    ap.add_argument("--tag", default="")
    ap.add_argument("--perturb-base", type=int, help="Gate 4: perturbation seed base (seed = base + the entry's idx)")
    a = ap.parse_args()
    PT = None
    if a.perturb_base is not None:
        sys.path.insert(0, str(HERE.parent / "g4"))
        import perturb as PT
    if a.games_file:
        sel = json.loads(Path(a.games_file).read_text())
        games, types = [x["game"] for x in sel], [x["type"] for x in sel]
        idxs = [x.get("idx", i) for i, x in enumerate(sel)]
    else:
        games, types = pick_games(a.n, a.test)
        idxs = list(range(len(games)))
    run = HERE / "run"
    run.mkdir(exist_ok=True)
    log = open(run / ("judge_log_test.jsonl" if a.test else f"judge_log{a.tag}.jsonl"), "a")
    rec = lambda **k: (log.write(json.dumps({"t": time.strftime("%H:%M:%S"), **k}) + "\n"), log.flush())
    rec(event="start", n_games=len(games), types=types, max_steps=a.max_steps)
    if os.path.exists(a.sock):
        os.unlink(a.sock)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(a.sock)
    srv.listen(1)
    gi, game, steps, won, active = -1, None, 0, False, False
    pt, n_pert = None, 0

    def end(reason):
        nonlocal active, game
        rec(event="end", game=gi, reason=reason, steps=steps, won=won, perturbed_actions=n_pert)
        if game is not None:
            game.close()
        game, active = None, False

    while True:
        conn, _ = srv.accept()
        with conn:
            msg = json.loads(conn.makefile().readline() or "{}")
            cmd, arg = msg.get("cmd"), msg.get("arg", "")
            if cmd == "reset":
                if active:
                    end("reset before done")
                if gi + 1 >= len(games):
                    out = "[no more games]"
                else:
                    gi += 1
                    game = J.Game(games[gi], max_steps=a.max_steps + 5)
                    obs, info = game.reset()
                    steps, won, active = 0, bool(info["won"]), True
                    pt, n_pert = (PT.Perturb(a.perturb_base + idxs[gi]) if PT else None), 0
                    rec(event="reset", game=gi, obs=obs)
                    out = obs
            elif cmd == "act" and active:
                steps += 1
                if won:
                    obs = "Nothing happens."
                elif pt is not None and pt.fails(arg):
                    n_pert += 1
                    obs = "Nothing happens."
                else:
                    obs, _s, _d, info = game.step(arg)
                    won = bool(info["won"])
                rec(event="act", game=gi, step=steps, cmd=arg, obs=obs, won=won)
                out = obs
                if steps >= a.max_steps:
                    end("step limit")
                    out += "\n[step limit reached; call reset for the next game]"
            elif cmd == "done" and active:
                end("agent done")
                out = "[game ended; call reset for the next game]"
            else:
                out = "[no active game; call reset]"
            conn.sendall((json.dumps({"obs": out}) + "\n").encode())
        if out == "[no more games]":                 # exit only after the agent has asked for a game past the last
            rec(event="all games finished")
            break
    srv.close()
    os.unlink(a.sock)


if __name__ == "__main__":
    main()
