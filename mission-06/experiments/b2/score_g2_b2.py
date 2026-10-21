"""Score B2 on the 12-game G2-ALF subset from the judge logs (aggregates only; no observation text or actions are
printed). Compares with G2A-1 and B1 on the same games, checks each batch's tool calls against the protocol calls the
server recorded, appends the cost ledger, writes ../g2/g2alf_b2.json.

  python -I score_g2_b2.py
"""

from __future__ import annotations

import json
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = HERE / "run"
REPORTED = {0: {"tokens": 67780, "tool_uses": 33}, 1: {"tokens": 76179, "tool_uses": 71},
            2: {"tokens": 67955, "tool_uses": 36}, 3: {"tokens": 64885, "tool_uses": 22}}


def main():
    sel = json.loads((RUN / "g2_subset.json").read_text())
    g2 = {(r["variant"], r["game"]): r for r in map(json.loads, (HERE.parent / "g2" / "g2alf_judge.jsonl").read_text().splitlines())}
    games, batches = [], {}
    for k in range(4):
        batch = json.loads((RUN / f"g2_batch{k}.json").read_text())
        ev = [json.loads(l) for l in (RUN / f"judge_log_g2b{k}.jsonl").read_text().splitlines()]
        acts = sum(1 for e in ev if e["event"] == "act")
        resets = sum(1 for e in ev if e["event"] == "reset")
        dones = sum(1 for e in ev if e["event"] == "end" and e["reason"] == "agent done")
        protocol_calls = acts + resets + dones + 1                 # + the final reset answered "[no more games]"
        batches[k] = {"acts": acts, "games": resets, "protocol_calls": protocol_calls, **REPORTED[k],
                      "extra_tool_calls": REPORTED[k]["tool_uses"] - protocol_calls}
        for e in ev:
            if e["event"] == "end":
                x = batch[e["game"]]
                games.append({"g2_game": x["idx"], "type": x["type"], "won": e["won"], "steps": e["steps"],
                              "end": e["reason"]})
    idx = [g["g2_game"] for g in games]
    b2 = sum(g["won"] for g in games) / len(games)
    a1 = sum(g2[("G2A-1", i)]["won"] for i in idx) / len(idx)
    b1 = sum(g2[("B1", i)]["won"] for i in idx) / len(idx)
    out = {"label": "G2-ALF B2 (Opus 5.5 subagent) on the 12-game subset", "games": len(games), "success": b2,
           "won": sum(g["won"] for g in games), "same_games": {"G2A-1": a1, "B1": b1},
           "per_type": {t: f"{sum(g['won'] for g in games if g['type'] == t)}/{sum(1 for g in games if g['type'] == t)}"
                        for t in sorted({g["type"] for g in games})},
           "mean_steps": sum(g["steps"] for g in games) / len(games), "ends": [g["end"] for g in games],
           "batches": batches, "tokens_total": sum(v["tokens"] for v in REPORTED.values()),
           "prediction_G2A-d (B2 >= G2A-1 on the same games)": "HOLDS" if b2 >= a1 else "FALSIFIED"}
    (HERE.parent / "g2" / "g2alf_b2.json").write_text(json.dumps(out, indent=1))
    with open(HERE / "cost_ledger.jsonl", "a") as f:
        for k, v in REPORTED.items():
            f.write(json.dumps({"run": f"G2-ALF-B2-batch{k}", "date": time.strftime("%Y-%m-%d"), "route": "Claude Code subagent",
                                "model": "Opus 5.5 (inherited)", "subagent_tokens": v["tokens"], "tool_uses": v["tool_uses"],
                                "acts": batches[k]["acts"]}) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
