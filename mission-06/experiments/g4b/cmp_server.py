"""G4b: judge-side server for B2 on composite goals (same protocol and client as experiments/b2/alf_server.py). Holds
the room, rewrites the goal sentence, judges success from the state facts when the agent calls `done` or reaches the
step limit, and writes a judge-only log. B2 receives text observations only (no `won`, no facts).

  venv-alf/bin/python -I cmp_server.py --sock S --idx-file run/b2_batchK.json --max-steps 100 --tag _K
"""

import argparse
import json
import os
import socket
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cmp_env as E  # noqa: E402
import sets4b as S  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sock", required=True)
    ap.add_argument("--idx-file", required=True)
    ap.add_argument("--max-steps", type=int, default=100)
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    goals = S.heldout()
    idxs = json.loads(Path(a.idx_file).read_text())
    log = open(HERE / "run" / f"b2_judge_log{a.tag}.jsonl", "a")
    rec = lambda **k: (log.write(json.dumps({"t": time.strftime("%H:%M:%S"), **k}) + "\n"), log.flush())
    rec(event="start", idxs=idxs, max_steps=a.max_steps)
    if os.path.exists(a.sock):
        os.unlink(a.sock)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(a.sock)
    srv.listen(1)
    gi, game, steps, active = -1, None, 0, False

    def end(reason):
        nonlocal active, game
        rec(event="end", game=gi, idx=idxs[gi], family=goals[idxs[gi]][1], reason=reason, steps=steps,
            won=game.success(), orig_won=game.orig_won)
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
                if gi + 1 >= len(idxs):
                    out = "[no more games]"
                else:
                    gi += 1
                    gf, _fam, spec = goals[idxs[gi]]
                    game = E.CompositeGame(gf, spec, a.max_steps)
                    out = game.reset()
                    steps, active = 0, True
                    rec(event="reset", game=gi)
            elif cmd == "act" and active:
                steps += 1
                out = game.step(arg)
                rec(event="act", game=gi, step=steps)
                if steps >= a.max_steps:
                    end("step limit")
                    out += "\n[step limit reached; call reset for the next game]"
            elif cmd == "done" and active:
                end("agent done")
                out = "[game ended; call reset for the next game]"
            else:
                out = "[no active game; call reset]"
            conn.sendall((json.dumps({"obs": out}) + "\n").encode())
        if out == "[no more games]":
            rec(event="all games finished")
            break
    srv.close()
    os.unlink(a.sock)


if __name__ == "__main__":
    main()
