"""Mission 04 pilot P-R1b (protocol amendment 1): can a preference among representations be learned from
other tasks instead of being supplied by the designer's list? ARC-AGI-1 training split, DEV.

Base: every explanation consistent with the training pairs under any of the 9 partition rules (F3-noselect).
An explanation's type is (rule, mechanism, attribute[, operator]). Tasks are split by index parity; each half is
scored with preferences learned on the other half.
  S0 strict      abstain if any consistent explanation is undetermined on the test input or predictions differ
  S1 designer    F1 (from r1.json)
  S2 permissive  drop undetermined explanations; answer if the remaining ones agree
  S3 consistency preference: type frequency among consistent explanations of the other half (no test outputs)
  S4 experience  preference: type frequency among explanations of the other half whose test prediction was correct

  python -I mission-04/experiments/r1_repr/run_r1b.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import blocks as B  # noqa: E402
import run_r1 as R  # noqa: E402


def etype(e):
    rule, mech, params = e
    if mech == "RECOLOUR":
        return (rule, mech, params[0])
    return (rule, mech, params[0], params[1])


def task_explanations(train, tests):
    expl = []
    for rule in B.GRAMMAR:
        expl += B.explanations(train, rule)
    rows = []
    for e in expl:
        preds = [B.predict(e, I) for I, _ in tests]
        determined = all(p is not None for p in preds)
        correct = determined and all(p.shape == T.shape and (p == T).all() for p, (_, T) in zip(preds, tests))
        rows.append({"type": etype(e), "preds": [None if p is None else (p.shape, p.tobytes()) for p in preds],
                     "determined": determined, "correct": correct})
    return rows


def decide(rows):
    if not rows:
        return "abstain"
    if any(not r["determined"] for r in rows):
        return "abstain"
    if len({tuple(map(repr, r["preds"])) for r in rows}) != 1:
        return "abstain"
    return "correct" if rows[0]["correct"] else "wrong"


def main():
    t0 = time.perf_counter()
    tasks = {f.stem: R.load(f) for f in sorted(R.DATA.glob("*.json"))}
    ids = sorted(tasks)
    fold = {t: i % 2 for i, t in enumerate(ids)}
    ex = {t: task_explanations(*tasks[t]) for t in ids}
    score = {0: {"S3": {}, "S4": {}}, 1: {"S3": {}, "S4": {}}}
    for t in ids:
        f = fold[t]
        for ty in {r["type"] for r in ex[t]}:
            score[f]["S3"][ty] = score[f]["S3"].get(ty, 0) + 1
        for ty in {r["type"] for r in ex[t] if r["correct"]}:
            score[f]["S4"][ty] = score[f]["S4"].get(ty, 0) + 1
    r1 = json.loads((HERE / "r1.json").read_text())["rows"]
    out = {}
    for t in ids:
        rows = ex[t]
        other = score[1 - fold[t]]
        res = {"S0": decide(rows), "S1": r1[t]["F1"]["status"], "S2": decide([r for r in rows if r["determined"]])}
        for pol in ("S3", "S4"):
            sc = [other[pol].get(r["type"], 0) for r in rows]
            if not rows or max(sc) == 0:
                res[pol] = "abstain"
            else:
                top = max(sc)
                res[pol] = decide([r for r, s in zip(rows, sc) if s == top])
        out[t] = res
    summary = {}
    for pol in ("S0", "S1", "S2", "S3", "S4"):
        st = [r[pol] for r in out.values()]
        c, w = st.count("correct"), st.count("wrong")
        summary[pol] = {"correct": c, "wrong": w, "abstain": st.count("abstain"), "precision": round(c / (c + w), 3) if c + w else None}
    diag = {t: out[t] for t in ["25d8a9c8", "b1948b0a", "c8f0f002", "0b148d64", "a87f7484"]}
    sol = lambda pol: {t for t, r in out.items() if r[pol] == "correct"}
    res = {"label": "ARC-AGI-1 training split, DEV; S4 uses the other half's test outputs as feedback",
           "summary": summary, "diagnostic_tasks": diag,
           "S4_minus_S1": sorted(sol("S4") - sol("S1")), "S1_minus_S4": sorted(sol("S1") - sol("S4")),
           "S2_minus_S0": sorted(sol("S2") - sol("S0")),
           "wrong": {pol: sorted(t for t, r in out.items() if r[pol] == "wrong") for pol in summary},
           "top_types_S4": {f"fold{f}": sorted(score[f]["S4"].items(), key=lambda kv: -kv[1])[:8] for f in (0, 1)},
           "rows": out, "time_s": round(time.perf_counter() - t0, 1)}
    (HERE / "r1b.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1, default=str))


if __name__ == "__main__":
    main()
