"""Score B2 on the 12-game Gate 3 subset from the judge logs (aggregates only; no observation text or actions are
printed). The subagents' reported token and tool-call counts are read from run/g3_reported.json
({"0": {"tokens": .., "tool_uses": ..}, ...}). Appends the cost ledger, writes ../g3/g3_b2.json.

  python3 -I score_g3_b2.py
"""

import json
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = HERE / "run"


def main():
    reported = {int(k): v for k, v in json.loads((RUN / "g3_reported.json").read_text()).items()}
    games, batches = [], {}
    for k in sorted(reported):
        batch = json.loads((RUN / f"g3_batch{k}.json").read_text())
        ev = [json.loads(l) for l in (RUN / f"judge_log_g3b{k}.jsonl").read_text().splitlines()]
        acts = sum(1 for e in ev if e["event"] == "act")
        resets = sum(1 for e in ev if e["event"] == "reset")
        dones = sum(1 for e in ev if e["event"] == "end" and e["reason"] == "agent done")
        protocol_calls = acts + resets + dones + 1
        batches[k] = {"acts": acts, "games": resets, "protocol_calls": protocol_calls, **reported[k],
                      "extra_tool_calls": reported[k]["tool_uses"] - protocol_calls}
        for e in ev:
            if e["event"] == "end":
                x = batch[e["game"]]
                games.append({"idx": x["idx"], "type": x["type"], "won": e["won"], "steps": e["steps"], "end": e["reason"]})
    out = {"label": "Gate 3 B2 (Opus 5.5 subagent) on the 12-game subset", "games": len(games),
           "games_idx": [g["idx"] for g in games], "won": sum(g["won"] for g in games),
           "success": sum(g["won"] for g in games) / len(games),
           "per_type": {t: f"{sum(g['won'] for g in games if g['type'] == t)}/{sum(1 for g in games if g['type'] == t)}"
                        for t in sorted({g["type"] for g in games})},
           "mean_steps": sum(g["steps"] for g in games) / len(games), "ends": [g["end"] for g in games],
           "batches": batches, "tokens_total": sum(v["tokens"] for v in reported.values())}
    (HERE.parent / "g3" / "g3_b2.json").write_text(json.dumps(out, indent=1))
    with open(HERE / "cost_ledger.jsonl", "a") as f:
        for k, v in reported.items():
            f.write(json.dumps({"run": f"G3-B2-batch{k}", "date": time.strftime("%Y-%m-%d"), "route": "Claude Code subagent",
                                "model": "Opus 5.5 (inherited)", "subagent_tokens": v["tokens"], "tool_uses": v["tool_uses"],
                                "acts": batches[k]["acts"]}) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
