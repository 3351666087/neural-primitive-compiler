"""Score Gate 4 runs (EXPERIMENT_PRE_REGISTRATION.md section G4).
  python3 -I g4_score.py dev60_clean dev60_pert ...       descriptive summaries of runs (development)
  python3 -I g4_score.py --heldout                          the locked predictions on heldout_clean / heldout_pert,
                                                            with B2 from g4_b2_clean.json / g4_b2_pert.json if present
Writes g4_scores_<tag>.json per run and, with --heldout, g4_heldout_verdicts.json.
"""

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import stats as S  # noqa: E402

SIL = "silent_failures"


def load_run(tag):
    J = {(r["variant"], r["game"]): r for r in map(json.loads, (HERE / f"g4_{tag}_judge.jsonl").read_text().splitlines())}
    Cn = {(r["variant"], r["game"]): r for r in map(json.loads, (HERE / f"g4_{tag}_constructor.jsonl").read_text().splitlines())}
    return J, Cn


def summarize(tag, J, Cn):
    order = ["G2A-1", "B1", "G3-L", "G3-S", "G3-LP", "G3-LPR", "B1-LPR"]
    arms = sorted({k[0] for k in Cn}, key=lambda v: (order.index(v) if v in order else len(order), v))
    out = {}
    for v in arms:
        keys = sorted(k for k in Cn if k[0] == v)
        won = [J[k]["won"] for k in keys]
        fails = [k for k in keys if not J[k]["won"]]
        oc = Counter()
        for k in keys:
            o = Cn[k]["outcome"]
            oc["won" if J[k]["won"] else ("abstain: " + o.split(": ", 1)[1].split(":")[0] if o.startswith("abstain") else o)] += 1
        n, w = len(keys), sum(won)
        claims = [k for k in keys if Cn[k]["outcome"] == "claims done"]
        abst = [k for k in keys if Cn[k]["outcome"].startswith("abstain")]
        out[v] = {"games": n, "won": w, "success": w / n, "wilson95": S.wilson(w, n),
                  SIL: sum(1 for k in fails if Cn[k]["outcome"] == "claims done"),
                  "abstain_failed": sum(1 for k in fails if Cn[k]["outcome"].startswith("abstain")),
                  "abstain_but_won": sum(1 for k in abst if J[k]["won"]),
                  "claims_done": len(claims),
                  "precision_of_claims_done": (sum(J[k]["won"] for k in claims) / len(claims)) if claims else None,
                  "L_co_contradictions_in_lost_games": sum(1 for k in fails if "monitor: 'examine'" in Cn[k]["outcome"]),
                  "mean_steps": sum(Cn[k]["steps"] for k in keys) / n,
                  "retries": sum(Cn[k].get("retries") or 0 for k in keys),
                  "colocated_hits": sum(Cn[k].get("colocated_hits") or 0 for k in keys),
                  "perturbed_actions": sum(J[k].get("perturbed_actions", 0) for k in keys),
                  "outcomes": dict(oc.most_common()),
                  "by_task_type": {t: f"{sum(J[k]['won'] for k in keys if J[k]['task_type'] == t)}/"
                                      f"{sum(1 for k in keys if J[k]['task_type'] == t)}"
                                   for t in sorted({J[k]['task_type'] for k in keys})}}
    return out


def paired(J, Cn, a, b, n):
    wa = [int(J[(a, i)]["won"]) for i in range(n)]
    wb = [int(J[(b, i)]["won"]) for i in range(n)]
    d, ci = S.paired_diff(wa, wb)
    p, n10, n01 = S.mcnemar_exact(wa, wb)
    sa = [Cn[(a, i)]["steps"] for i in range(n)]
    sb = [Cn[(b, i)]["steps"] for i in range(n)]
    ds, cis = S.paired_diff(sa, sb)
    return {"success_diff": d, "success_diff_ci95": ci, "mcnemar_p": p, f"{a}_only": n10, f"{b}_only": n01,
            "steps_diff": ds, "steps_diff_ci95": cis, "steps_ratio": (sum(sa) / max(1, sum(sb)))}


PAIRS = [("G3-L", "G2A-1"), ("G3-L", "B1"), ("G3-LP", "G3-L"), ("G3-LPR", "B1-LPR"), ("G3-LPR", "G3-LP"), ("B1-LPR", "B1")]


def score(tag):
    J, Cn = load_run(tag)
    n = 1 + max(k[1] for k in Cn)
    out = {"run": tag, "arms": summarize(tag, J, Cn), "paired": {}}
    arms = {k[0] for k in Cn}
    for a, b in PAIRS:
        if a in arms and b in arms:
            out["paired"][f"{a} vs {b}"] = paired(J, Cn, a, b, n)
    (HERE / f"g4_scores_{tag}.json").write_text(json.dumps(out, indent=1))
    return out, J, Cn


def main():
    if "--heldout" in sys.argv:
        import g4_verdicts
        g4_verdicts.main(score)
        return
    for tag in sys.argv[1:]:
        out, _, _ = score(tag)
        print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
