"""Gate 2 job list (development family alpha). JUDGE SIDE.
  python3 -I g2_jobs.py make        writes run/$G2_RUN/jobs.jsonl (default g2)
  python3 -I g2_jobs.py run I       runs job I (used with xargs -P)"""

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
RUN = os.environ.get("G2_RUN", "g2")              # amendment A3: Gate 2 rerun with the A3 learner in run/g2a3
OUT = HERE / "run" / RUN
FAM = str(HERE / "family_alpha.json")
BASE = ["B1", "B1+M", "B2", "B3", "B4", "B5"]
LEARNERS = ["B1+M", "B2", "B3", "B4", "B5"]
FAKES = ["F-random", "F-scripted", "F-list", "F-inflate", "F-hindsight", "F-scheduler", "F-unlock", "F-hardmap", "F-macro",
         "F-story", "F-rewardhack"]
STEPS = 60000


def jobs():
    js = []
    for arm in BASE:
        for seed in range(100, 105):
            js.append({"arm": arm, "family": FAM, "seed": seed, "steps": STEPS, "out": str(OUT), "checkpoint": 20000})
            if arm in LEARNERS:
                js.append({"arm": arm, "family": FAM, "seed": seed, "steps": STEPS, "out": str(OUT), "tag": ".twin",
                           "opts": {"learn_off": True}})
    for arm in FAKES:
        for seed in (100, 101):
            js.append({"arm": arm, "family": FAM, "seed": seed, "steps": STEPS, "out": str(OUT), "checkpoint": 20000})
    return js


if __name__ == "__main__":
    if sys.argv[1] == "make":
        OUT.mkdir(parents=True, exist_ok=True)
        with open(OUT / "jobs.jsonl", "w") as f:
            for j in jobs():
                f.write(json.dumps(j) + "\n")
        print(len(jobs()), "jobs")
    else:
        import run_eco as R
        spec = json.loads((OUT / "jobs.jsonl").read_text().splitlines()[int(sys.argv[2])])
        try:
            print(json.dumps(R.run_job(spec)), flush=True)
        except Exception as e:
            print(json.dumps({"job": int(sys.argv[2]), "error": f"{type(e).__name__}: {e}"}), flush=True)
