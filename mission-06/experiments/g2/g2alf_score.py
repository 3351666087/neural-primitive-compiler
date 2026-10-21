"""Score G2-ALF against the locked predictions (EXPERIMENT_PRE_REGISTRATION.md section G2-ALF). B2 (G2A-d) is scored
once its run exists (g2alf_b2.json).

  python -I g2alf_score.py        # writes g2alf_scores.json
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name):
    return [json.loads(l) for l in (HERE / name).read_text().splitlines()]


def main():
    J = {(r["variant"], r["game"]): r for r in load("g2alf_judge.jsonl")}
    Cn = {(r["variant"], r["game"]): r for r in load("g2alf_constructor.jsonl")}
    out = {}
    for v in ("G2A-0", "G2A-1", "B1"):
        keys = sorted(k for k in Cn if k[0] == v)
        won = [J[k]["won"] for k in keys]
        outcomes = Counter()
        for k in keys:
            o = Cn[k]["outcome"]
            outcomes["won" if J[k]["won"] else ("abstain: " + o.split(": ", 1)[1].split(":")[0] if o.startswith("abstain") else o)] += 1
        fails = [k for k in keys if not J[k]["won"]]
        detected = [k for k in fails if Cn[k]["outcome"].startswith("abstain")]
        by_type = {}
        for k in keys:
            t = J[k]["task_type"]
            by_type.setdefault(t, [0, 0])
            by_type[t][0] += J[k]["won"]
            by_type[t][1] += 1
        viol = Counter(x for k in keys for x in Cn[k].get("violations", []))
        out[v] = {"games": len(keys), "constructed": sum(Cn[k]["constructed"] for k in keys),
                  "parsed": sum(Cn[k]["atoms"] is not None for k in keys), "success": sum(won) / len(keys),
                  "won": sum(won), "failures": len(fails), "failures_detected_abstain": len(detected),
                  "claims_done_but_lost": sum(1 for k in fails if Cn[k]["outcome"] == "claims done"),
                  "outcomes": dict(outcomes.most_common()), "by_task_type": {t: f"{a}/{b}" for t, (a, b) in by_type.items()},
                  "violations_by_command": dict(viol), "mean_steps": sum(Cn[k]["steps"] for k in keys) / len(keys)}
    a1, b1 = out["G2A-1"], out["B1"]
    pred = {"G2A-0 (strict: 0 constructions)": out["G2A-0"]["constructed"] == 0,
            "G2A-a (all parsed goals constructed)": a1["constructed"] == a1["parsed"],
            "G2A-b (success in [0.30, 0.75])": 0.30 <= a1["success"] <= 0.75,
            "G2A-c (>= 50% of failures detected)": a1["failures"] == 0 or a1["failures_detected_abstain"] / a1["failures"] >= 0.5,
            "G2A-e (|B1 - G2A-1| <= 0.05)": abs(b1["success"] - a1["success"]) <= 0.05}
    b2 = HERE / "g2alf_b2.json"
    if b2.exists():
        s = json.loads(b2.read_text())["success"]
        pred["G2A-d (B2 >= G2A-1)"] = s >= a1["success"]
        out["B2"] = json.loads(b2.read_text())
    out["predictions"] = {k: "HOLDS" if v else "FALSIFIED" for k, v in pred.items()}
    (HERE / "g2alf_scores.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
