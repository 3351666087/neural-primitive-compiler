"""Score the B2 feasibility pilot (EXPERIMENT_PRE_REGISTRATION.md section G1-B2P0) from the judge log, reporting
aggregates only: no observation text and no action strings are printed or written (the designer must not see B2's
trajectories).

  python -I score_b2p0.py SUBAGENT_TOKENS TOOL_USES DURATION_MS        # writes b2p0_scores.json, cost_ledger.jsonl
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    tokens, tool_uses, dur = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
    ev = [json.loads(l) for l in (HERE / "run" / "judge_log.jsonl").read_text().splitlines()]
    games = {}
    for e in ev:
        if e["event"] == "reset":
            games[e["game"]] = {"acts": 0, "verbs": Counter(), "won": False, "end": None}
        elif e["event"] == "act":
            g = games[e["game"]]
            g["acts"] += 1
            g["verbs"][e["cmd"].split(" ")[0] if e["cmd"] else "<empty>"] += 1
            g["won"] = g["won"] or e["won"]
            g.setdefault("first_win_step", None)
            if e["won"] and g["first_win_step"] is None:
                g["first_win_step"] = e["step"]
        elif e["event"] == "end":
            games[e["game"]]["end"] = e["reason"]
    acts = sum(g["acts"] for g in games.values())
    start = next(e for e in ev if e["event"] == "start")
    out = {"label": "G1-B2P0 (Mission 06): B2 via subagent, feasibility", "types": start["types"],
           "games": {i: {"acts": g["acts"], "won": g["won"], "first_win_step": g.get("first_win_step"), "end": g["end"],
                         "command_verbs": dict(g["verbs"])} for i, g in games.items()},
           "subagent_tokens": tokens, "tool_uses": tool_uses, "duration_s": round(dur / 1000, 1),
           "tokens_per_act": round(tokens / acts) if acts else None}
    pa = len(games) == 2 and all(g["acts"] >= 1 for g in games.values())
    pc = acts > 0 and tokens / acts <= 30000
    out["predictions"] = {"B2P0-a": "HOLDS" if pa else "FALSIFIED",
                          "B2P0-b": "scored by hand (subagent report and command verbs)",
                          "B2P0-c": "HOLDS" if pc else "FALSIFIED"}
    (HERE / "b2p0_scores.json").write_text(json.dumps(out, indent=1))
    with open(HERE / "cost_ledger.jsonl", "a") as f:
        f.write(json.dumps({"run": "G1-B2P0", "date": time.strftime("%Y-%m-%d"), "route": "Claude Code subagent",
                            "model": "Opus 5.5 (inherited)", "subagent_tokens": tokens, "tool_uses": tool_uses,
                            "acts": acts}) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
