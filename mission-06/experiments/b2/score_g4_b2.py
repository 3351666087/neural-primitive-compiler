"""Score B2 on the Gate 4 held-out subsets from the judge logs (aggregates only). Reported subagent token and tool-call
counts are read from run/<prefix>_reported.json. Appends the cost ledger; writes ../g4/g4_b2_<clean|pert>.json.

  python3 -I score_g4_b2.py g4c      # clean subset (60 games)
  python3 -I score_g4_b2.py g4p      # perturbed subset (24 games)
"""

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = HERE / "run"


def main():
    prefix = sys.argv[1]
    reported = {int(k): v for k, v in json.loads((RUN / f"{prefix}_reported.json").read_text()).items()}
    games, batches = [], {}
    for k in sorted(reported):
        batch = json.loads((RUN / f"{prefix}_batch{k}.json").read_text())
        ev = [json.loads(l) for l in (RUN / f"judge_log_{prefix}{k}.jsonl").read_text().splitlines()]
        acts = sum(1 for e in ev if e["event"] == "act")
        resets = sum(1 for e in ev if e["event"] == "reset")
        dones = sum(1 for e in ev if e["event"] == "end" and e["reason"] == "agent done")
        protocol_calls = acts + resets + dones + 1
        batches[k] = {"acts": acts, "games": resets, "protocol_calls": protocol_calls, **reported[k],
                      "extra_tool_calls": reported[k]["tool_uses"] - protocol_calls}
        for e in ev:
            if e["event"] == "end":
                x = batch[e["game"]]
                games.append({"idx": x["idx"], "type": x["type"], "won": e["won"], "steps": e["steps"], "end": e["reason"],
                              "perturbed_actions": e.get("perturbed_actions", 0)})
    n = len(games)
    out = {"label": f"Gate 4 B2 (Opus 5.5 subagent), {prefix}", "games": n, "games_idx": [g["idx"] for g in games],
           "won_by_idx": {g["idx"]: g["won"] for g in games}, "steps_by_idx": {g["idx"]: g["steps"] for g in games},
           "won": sum(g["won"] for g in games), "success": sum(g["won"] for g in games) / n,
           "claims_done_but_lost": sum(1 for g in games if g["end"] == "agent done" and not g["won"]),
           "per_type": {t: f"{sum(g['won'] for g in games if g['type'] == t)}/{sum(1 for g in games if g['type'] == t)}"
                        for t in sorted({g["type"] for g in games})},
           "mean_steps": sum(g["steps"] for g in games) / n, "ends": dict((e, sum(1 for g in games if g["end"] == e))
                                                                          for e in {g["end"] for g in games}),
           "perturbed_actions": sum(g["perturbed_actions"] for g in games),
           "batches": batches, "tokens_total": sum(v["tokens"] for v in reported.values()),
           "extra_tool_calls_total": sum(b["extra_tool_calls"] for b in batches.values())}
    (HERE.parent / "g4" / f"g4_b2_{'clean' if prefix == 'g4c' else 'pert'}.json").write_text(json.dumps(out, indent=1))
    with open(HERE / "cost_ledger.jsonl", "a") as f:
        for k, v in reported.items():
            f.write(json.dumps({"run": f"G4-B2-{prefix}-batch{k}", "date": time.strftime("%Y-%m-%d"),
                                "route": "Claude Code subagent", "model": "Opus 5.5 (inherited)",
                                "subagent_tokens": v["tokens"], "tool_uses": v["tool_uses"], "acts": batches[k]["acts"]}) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k not in ("won_by_idx", "steps_by_idx", "games_idx")}, indent=1))


if __name__ == "__main__":
    main()
