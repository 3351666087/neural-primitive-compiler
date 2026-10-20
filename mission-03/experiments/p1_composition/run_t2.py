"""P1 T2 (`same`) on its own: the original run_p1.py run was stopped at the T1 budget before reaching T2.
Protocol section 3 unchanged for T2.

  python mission-03/experiments/p1_composition/run_t2.py
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from run_p1 import UNSEEN, explain_same, generate

HERE = Path(__file__).resolve().parent

if __name__ == "__main__":
    seed = json.loads((UNSEEN / "tasks.json").read_text())["seed"]
    units = {u.uid: u for u in generate(seed)}
    rows = []
    t0 = time.perf_counter()
    for uid in ("UB0", "UB1"):
        r = explain_same(units[uid])
        print(r, flush=True)
        rows.append(r)
    (HERE / "p1_t2.json").write_text(json.dumps({"T2": rows, "time_s": round(time.perf_counter() - t0, 1)}, indent=1, default=str))
