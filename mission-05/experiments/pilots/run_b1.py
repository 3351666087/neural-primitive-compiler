"""B-1' (amendment 2, DEV): learn the damage table from observed relocations and feed it to A-P' (L-tmpl).

  B-DISC  n in {50, 200, 1000} states per achiever at each of N = 5, 6, 7 (growth check)
  B-NULL  n in {50, 200, 1000} states per achiever at N = 5 only (no growth check)
Each learned table is compared entry by entry with B-GIVEN (damage_table.json, exhaustive at N <= 5): equal,
dangerous (learned bound below the given one, or finite where the given one grows) or conservative (the reverse).
A-P' (L-tmpl) is run with the n = 1000 tables on the same 98 goals; plans not judged in PA-3 are judged now.

  python -I mission-05/experiments/pilots/run_b1.py       # writes b1.json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(EXP / "judge"))
sys.path.insert(0, str(EXP / "lib"))
sys.path.insert(0, str(HERE))
import ap2  # noqa: E402
import bdisc  # noqa: E402
from run_pa3 import goals, judge_plan  # noqa: E402

INF = float("inf")


def num(b):
    return INF if b in (None, "inf") else b


def compare(learned, given):
    eq = dang = cons = 0
    dangerous = []
    for a, row in given.items():
        for k, e in row["entries"].items():
            g, l = num(e["bound"]), num(learned[a]["entries"][k]["bound"])
            if g == l:
                eq += 1
            elif l < g:
                dang += 1
                dangerous.append(f"{a} / {k}: learned {l}, given {g}")
            else:
                cons += 1
    tot = eq + dang + cons
    return {"entries": tot, "equal": eq, "dangerous": dang, "conservative": cons, "agreement": eq / tot,
            "dangerous_examples": dangerous[:10]}


def main():
    t0 = time.perf_counter()
    given = ap2.load_damage()
    progress = ap2.load_progress()
    out = {"label": "B-1' (DEV): learned damage tables", "tables": {}}
    learned = {}
    for mode in ("disc", "null"):
        for n in (50, 200, 1000):
            c0 = time.process_time()
            tab, cost = bdisc.learn(n, mode, seed=11)
            cost["cpu"] = time.process_time() - c0
            learned[(mode, n)] = tab
            out["tables"][f"{mode}-{n}"] = {"cost": cost, "vs_given": compare(tab, given)}
            print(mode, n, out["tables"][f"{mode}-{n}"]["vs_given"]["agreement"],
                  out["tables"][f"{mode}-{n}"]["vs_given"]["dangerous"], round(cost["cpu"], 1), "s", flush=True)
    pa3 = json.loads((HERE / "pa3.json").read_text())
    cache = pa3["judged"]
    G = goals()
    out["A"] = {}
    for mode in ("disc", "null"):
        res = {}
        for gid, spec in G.items():
            r = ap2.construct(spec, "tmpl", learned[(mode, 1000)], progress)
            row = {"status": r["status"]}
            if r["status"] == "CONSTRUCTED":
                plan = [tuple(x) for x in r["plan"]]
                key = gid + "|" + json.dumps(plan)
                row["failures"] = judge_plan(spec, plan, cache, key)["failures"]
            res[gid] = row
        out["A"][f"{mode}-1000"] = res
        print("A-P' with", mode, "constructed", sum(v["status"] == "CONSTRUCTED" for v in res.values()),
              "wrong", sum(v.get("failures", 0) > 0 for v in res.values()), flush=True)
    out["time_s"] = round(time.perf_counter() - t0, 1)
    (HERE / "b1.json").write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
