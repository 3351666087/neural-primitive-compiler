"""Gate 4 scoring in ECO (JUDGE SIDE; PROTOCOL.md sections 7-8 with amendments A2-A5).
Per (arm, seed): L1 (history swap with the next seed of the family's set at step 20,000, 2,000-step horizon, against
the reseeded noise floor), L2 events per R-level class (score_eco2, the run's own twin), L3 (C2 / C3 of the family:
alpha fixed by PROTOCOL.md section 6.5; beta / gamma by heldout_classes.py). Per arm: passes with Wilson 95 %
intervals. Candidate vs. the strongest baseline (B1-B5) per layer: difference in passes and exact McNemar p.
  python3 -I g4_score.py FAMILY ARMS            # writes run/g4_FAMILY/g4_scores.json
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ground_eco as G  # noqa: E402
import score_eco2 as S2  # noqa: E402
import swap_eco as SW  # noqa: E402
from eco_env import load_family  # noqa: E402
from g4_jobs import CUSTODIAN, SEEDS, family_path, out_dir  # noqa: E402

BASELINES = ("B1", "B1+M", "B2", "B3", "B4", "B5")


def wilson(k, n, z=1.96):
    if n == 0:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 3), round(c + h, 3)]


def mcnemar(a, b):
    """Exact two-sided McNemar on paired booleans a (candidate), b (baseline)."""
    n10 = sum(1 for x, y in zip(a, b) if x and not y)
    n01 = sum(1 for x, y in zip(a, b) if y and not x)
    n = n10 + n01
    if n == 0:
        return {"n10": 0, "n01": 0, "p": 1.0}
    k = min(n10, n01)
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)
    return {"n10": n10, "n01": n01, "p": round(p, 4)}


def classes_for(name):
    if name == "alpha":
        return "LATENT:stone.charge", "LATENT:lamp.armed"
    import heldout_classes as HC
    family_path(name)                                         # hash check
    d = HC.main(str(CUSTODIAN / f"family_{name}.json"), str(CUSTODIAN / f"demos_{name}.json"))
    return d["C2"], d["C3"]


def main(name, arms):
    fam_p = family_path(name)
    fam = load_family(fam_p)
    out = out_dir(name)
    probes, classes = G.make_probes(fam)
    c2, c3 = classes_for(name)
    seeds = list(SEEDS[name])
    res = {"family": name, "C2": c2, "C3": c3, "arms": {}}
    for arm in arms.split(","):
        rows = {}
        for i, seed in enumerate(seeds):
            stem = f"{arm}_{fam['name']}_{seed}"
            twin = f"{stem}.twin" if (out / f"{stem}.twin.judge.json.gz").exists() else None
            try:
                r = S2.score_run(stem, out, probes, classes, twin_stem=twin)
            except FileNotFoundError as e:
                rows[seed] = {"missing": str(e)}
                continue
            l3 = S2.l3(r, c2, c3) if c2 and c3 else {"L3": False, "note": "C2 or C3 undefined"}
            try:
                sw = SW.swap_test(arm, str(fam_p), seed, seeds[(i + 1) % len(seeds)], 20000, 2000, str(out))
            except Exception as e:
                sw = {"error": f"{type(e).__name__}: {e}", "L1_pass": False}
            rows[seed] = {"lives": r["lives"], "goal_log_valid": r["goal_log_valid"], "L1": sw,
                          "L2": r["L2"], "L2_any": r["L2_any"], "L3": l3,
                          "grounded": sorted({p["class"] for s in r["structures"].values() for p in s["predicates"].values()
                                              if p["grounded"]})}
            print(arm, seed, "L1", sw.get("L1_pass"), "L2", sorted(k for k, v in r["L2"].items() if v["event"]),
                  "L3", l3.get("L3"), flush=True)
        ok = [s for s in seeds if "missing" not in rows.get(s, {"missing": 1})]
        summ = {}
        for layer, f in (("L1", lambda x: bool(x["L1"].get("L1_pass"))), ("L2", lambda x: bool(x["L2_any"])),
                         ("L3", lambda x: bool(x["L3"].get("L3")))):
            k = sum(1 for s in ok if f(rows[s]))
            summ[layer] = {"passes": k, "runs": len(ok), "wilson95": wilson(k, len(ok)),
                           "by_seed": {s: f(rows[s]) for s in ok}}
        res["arms"][arm] = {"summary": summ, "runs": rows}
    cmp = {}
    if "CAND" in res["arms"]:
        for layer in ("L1", "L2", "L3"):
            cand = res["arms"]["CAND"]["summary"][layer]
            base = [(a, res["arms"][a]["summary"][layer]) for a in BASELINES if a in res["arms"]]
            if not base:
                continue
            best_arm, best = max(base, key=lambda x: x[1]["passes"])
            a = [cand["by_seed"].get(s, False) for s in seeds]
            b = [best["by_seed"].get(s, False) for s in seeds]
            m = mcnemar(a, b)
            cmp[layer] = {"candidate": cand["passes"], "strongest_baseline": best_arm, "baseline": best["passes"],
                          "difference": cand["passes"] - best["passes"], "mcnemar": m,
                          "gain_over_known_mechanisms": cand["passes"] - best["passes"] >= 4 and m["p"] < 0.05}
    res["comparison"] = cmp
    (out / "g4_scores.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps({a: {l: v["summary"][l]["passes"] for l in ("L1", "L2", "L3")} for a, v in res["arms"].items()}))
    print(json.dumps(cmp, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
