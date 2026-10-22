"""Gate 2 scoring (JUDGE SIDE): every baseline and fake run on alpha's development seeds; history-swap L1 tests on the
seed pair (100, 101) at step 20,000 with a 2,000-step horizon; the fake-rejection check.
  python3 -I g2_score.py        # writes g2_scores.json"""

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ground_eco as G  # noqa: E402
import score_eco as S  # noqa: E402
import swap_eco as SW  # noqa: E402
from eco_env import load_family  # noqa: E402
from g2_jobs import BASE, FAKES, LEARNERS, OUT, RUN  # noqa: E402

FAM = HERE / "family_alpha.json"


def main():
    fam = load_family(FAM)
    probes, classes = G.make_probes(fam)
    runs = {}
    for arm in BASE + FAKES:
        seeds = range(100, 105) if arm in BASE else (100, 101)
        for seed in seeds:
            stem = f"{arm}_alpha_{seed}"
            twin = f"{stem}.twin" if arm in LEARNERS else stem
            try:
                runs[stem] = S.score_run(stem, OUT, probes, classes, twin_stem=twin)
            except FileNotFoundError as e:
                runs[stem] = {"missing": str(e)}
            print(stem, "L2_any", runs[stem].get("L2_any"), flush=True)
    swaps = {}
    for arm in BASE + FAKES:
        try:
            swaps[arm] = SW.swap_test(arm, str(FAM), 100, 101, 20000, 2000, OUT)
        except Exception as e:
            swaps[arm] = {"error": f"{type(e).__name__}: {e}"}
        print(arm, "L1", swaps[arm].get("L1_pass"), swaps[arm].get("tv_swap"), swaps[arm].get("tv_noise"), flush=True)
    summary = {}
    for arm in BASE + FAKES:
        rs = [r for k, r in runs.items() if k.startswith(arm + "_") and "missing" not in r]
        cls_events = Counter(ck for r in rs for ck, v in r["L2"].items() if v["event"])
        grounded = Counter(info["class"] for r in rs for p, info in r["predicates"].items() if info["grounded"])
        summary[arm] = {"runs": len(rs), "mean_lives": round(sum(r["lives"] for r in rs) / max(1, len(rs)), 1),
                        "goal_logs_valid": sum(r["goal_log_valid"] for r in rs), "L1_pass": swaps[arm].get("L1_pass"),
                        "L2_runs": sum(r["L2_any"] for r in rs), "L2_by_class": dict(cls_events),
                        "grounded_predicates_by_class": dict(grounded),
                        "structures_from_interaction": sum(1 for r in rs for p, info in r["predicates"].items() if info["audit"]["ok"]),
                        "structures_failing_audit": sum(1 for r in rs for p, info in r["predicates"].items() if not info["audit"]["ok"])}
    fake_check = {arm: {"labelled_negative": not (summary[arm]["L2_runs"] > 0 or summary[arm]["L1_pass"])
                        or summary[arm]["goal_logs_valid"] < summary[arm]["runs"],
                        "why": [w for w, c in (("late goal records", summary[arm]["goal_logs_valid"] < summary[arm]["runs"]),
                                               ("no L1", not summary[arm]["L1_pass"]), ("no L2", summary[arm]["L2_runs"] == 0)) if c]}
                  for arm in FAKES + ["B3"]}
    out = {"summary": summary, "fake_check": fake_check, "swaps": swaps, "runs": runs}
    (HERE / ("g2_scores.json" if RUN == "g2" else f"g2_scores_{RUN}.json")).write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({"summary": summary, "fake_check": fake_check}, indent=1, default=str))


if __name__ == "__main__":
    main()
