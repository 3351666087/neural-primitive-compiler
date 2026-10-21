"""Score Gate 3 against the locked predictions G3-a..G3-f (EXPERIMENT_PRE_REGISTRATION.md section G3-M2).
Reads g3_discovery.json, g3_judge.jsonl + g3_constructor.jsonl and, once B2 has run, g3_b2.json.

  python3 -I g3_score.py        # writes g3_scores.json
"""

import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARMS = ("G2A-1", "B1", "G3-L", "G3-S", "G3-LS", "G3-LP")


def load(name):
    return [json.loads(l) for l in (HERE / name).read_text().splitlines()]


def main():
    disc = json.loads((HERE / "g3_discovery.json").read_text())
    J = {(r["variant"], r["game"]): r for r in load("g3_judge.jsonl")}
    Cn = {(r["variant"], r["game"]): r for r in load("g3_constructor.jsonl")}
    out = {"discovery": {k: v for k, v in disc.items() if k != "P_loc"}, "arms": {}}
    for v in ARMS:
        keys = sorted(k for k in Cn if k[0] == v)
        won = [J[k]["won"] for k in keys]
        fails = [k for k in keys if not J[k]["won"]]
        outcomes = Counter()
        for k in keys:
            o = Cn[k]["outcome"]
            outcomes["won" if J[k]["won"] else ("abstain: " + o.split(": ", 1)[1].split(":")[0] if o.startswith("abstain") else o)] += 1
        by_type = {}
        for k in keys:
            t = J[k]["task_type"]
            by_type.setdefault(t, [0, 0])
            by_type[t][0] += J[k]["won"]
            by_type[t][1] += 1
        out["arms"][v] = {
            "games": len(keys), "constructed": sum(Cn[k]["constructed"] for k in keys), "won": sum(won),
            "success": sum(won) / len(keys), "failures": len(fails),
            "failures_abstain": sum(1 for k in fails if Cn[k]["outcome"].startswith("abstain")),
            "silent_failures (claims done but lost)": sum(1 for k in fails if Cn[k]["outcome"] == "claims done"),
            "abstained_but_won": sum(1 for k in keys if J[k]["won"] and Cn[k]["outcome"].startswith("abstain")),
            "mean_steps": sum(Cn[k]["steps"] for k in keys) / len(keys),
            "mean_steps_won": (sum(Cn[k]["steps"] for k in keys if J[k]["won"]) / max(1, sum(won))),
            "colocated_hits": sum(Cn[k].get("colocated_hits") or 0 for k in keys),
            "violations_by_command": dict(Counter(x for k in keys for x in Cn[k].get("violations", []))),
            "outcomes": dict(outcomes.most_common()), "by_task_type": {t: f"{a}/{b}" for t, (a, b) in sorted(by_type.items())}}
    A = out["arms"]
    sil = "silent_failures (claims done but lost)"
    ev = disc["evidence"]
    pred = {
        "G3-a (discrimination tests all support H_co; symmetry consistent; L_co adopted)":
            disc["contradictions_of_H_co"] == 0 and ev["sym_tests"] > 0 and disc["L_co_adopted"],
        "G3-b (G3-L >= B1 - 0.03 and >= G2A-1 + 0.10)":
            A["G3-L"]["success"] >= A["B1"]["success"] - 0.03 and A["G3-L"]["success"] >= A["G2A-1"]["success"] + 0.10,
        "G3-c (G3-L: no silent failures)": A["G3-L"][sil] == 0,
        "G3-d (G3-S >= B1 - 0.03)": A["G3-S"]["success"] >= A["B1"]["success"] - 0.03,
        "G3-e (G3-LP mean steps <= 0.75 x G3-L, success not lower)":
            A["G3-LP"]["mean_steps"] <= 0.75 * A["G3-L"]["mean_steps"] and A["G3-LP"]["success"] >= A["G3-L"]["success"]}
    b2 = HERE / "g3_b2.json"
    if b2.exists():
        B = json.loads(b2.read_text())
        idx = B["games_idx"]
        same = {v: sum(J[(v, i)]["won"] for i in idx) / len(idx) for v in ARMS}
        B["same_games"] = same
        out["B2"] = B
        pred["G3-f (B2 >= G3-LP on the 12-game subset)"] = B["success"] >= same["G3-LP"]
    out["silent_failures_G3-S_vs_G3-L"] = [A["G3-S"][sil], A["G3-L"][sil]]
    out["predictions"] = {k: "HOLDS" if v else "FALSIFIED" for k, v in pred.items()}
    (HERE / "g3_scores.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
