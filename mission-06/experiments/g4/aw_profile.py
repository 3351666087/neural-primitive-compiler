"""Gate 4, AppWorld part (EXPERIMENT_PRE_REGISTRATION.md section G4): JUDGE-SIDE structure profile of a dataset split
from the released ground-truth files that exist for every split (answer.json, metadata.json). Prints aggregates only:
no task IDs, no text, no answers.
  answer_required   answer.json is neither null nor an empty string (an information goal)
  multi_app         metadata num_apps >= 2 (num_apps as AppWorld counts it)
  api_calls         metadata num_api_calls (median, quartiles)
  python3 -I aw_profile.py train dev | test_normal test_challenge     (writes aw_profile_<splits>.json)
"""

import json
import statistics
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "env" / "appworld" / "data"


def profile(split):
    ids = (DATA / "datasets" / f"{split}.txt").read_text().split()
    ans, apps, calls, diff = [], [], [], []
    for t in ids:
        gt = DATA / "tasks" / t / "ground_truth"
        a = json.loads((gt / "answer.json").read_text())
        m = json.loads((gt / "metadata.json").read_text())
        ans.append(a is not None and a != "")
        apps.append(m["num_apps"])
        calls.append(m["num_api_calls"])
        diff.append(m["difficulty"])
    q = statistics.quantiles(calls, n=4)
    return {"tasks": len(ids), "answer_required": sum(ans) / len(ids), "multi_app (num_apps>=2)": sum(x >= 2 for x in apps) / len(ids),
            "num_apps_mean": statistics.mean(apps), "api_calls_median": statistics.median(calls), "api_calls_q1_q3": [q[0], q[2]],
            "difficulty": {str(d): diff.count(d) for d in sorted(set(diff))}}


if __name__ == "__main__":
    out = {s: profile(s) for s in sys.argv[1:]}
    (Path(__file__).resolve().parent / f"aw_profile_{'_'.join(sys.argv[1:])}.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
