"""Protocol amendment 5: confirmation on conditional-command tasks never seen before.

The seed is derived from the frozen fitting code (cond_fit.py, run_amend34.py, run_p1.py, run_concept.py), so
the tasks cannot be chosen after the code. Each task: LOAD, two plain one-move commands, one conditional command
(region in {top, left, bottom}, one-move branches, delay 3 or 4), drawn from the Mission 02 move pool.
Same pipeline, data budget and scoring as run_amend34.py; nothing is tuned here.

  python mission-03/experiments/p1_composition/run_confirm.py
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "src"))

from cog.unseen import A_POOL, build_a  # noqa: E402
import run_amend34  # noqa: E402

FROZEN = [HERE / "cond_fit.py", HERE / "run_amend34.py", HERE / "run_p1.py", HERE.parent / "p1b_concept" / "run_concept.py"]


@dataclass
class CondTask:
    uid: str
    params: dict

    def build(self, N):
        p = self.params
        return build_a(self.uid, N, p["commands"], [], p["cond"])


def make_tasks():
    h = hashlib.sha256(b"".join(p.read_bytes() for p in FROZEN)).hexdigest()
    rng = random.Random(int(h[:16], 16))
    tasks = {}
    for i in range(6):
        cmds = [(f"CMD{c}", [rng.choice(A_POOL)]) for c in range(2)]
        cond = ("CMD2", rng.choice(["top", "left", "bottom"]), [rng.choice(A_POOL)], [rng.choice(A_POOL)], rng.choice([3, 4]))
        tasks[f"C{i}"] = CondTask(f"C{i}", {"commands": cmds, "cond": cond})
    return h, tasks


def main():
    h, tasks = make_tasks()
    (HERE / "confirm_tasks.json").write_text(json.dumps({"frozen_code_sha256": h, "tasks": {k: t.params for k, t in tasks.items()}},
                                                         indent=1))
    print("frozen code sha256", h, flush=True)
    for k, t in tasks.items():
        print(k, t.params, flush=True)
    run_amend34.main(uids=tuple(tasks), units=tasks, out_name="confirm.json")


if __name__ == "__main__":
    main()
