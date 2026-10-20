"""Re-run M-DISC on ARC-AGI-1 with the complete uniqueness check (Mission 04, task 1).

LABELS (stored in the output):
  training   : DEV split, as in Mission 03.
  evaluation : POST-HOC RE-EVALUATION. The split was used once in Mission 03 (outcome labels of the Mission 03
               methods are known; task contents were never viewed). These numbers are NOT a held-out result and
               must not be compared with Mission 03's held-out numbers as if they were.

Variants: M-DISC-fixed (identity colour extension as an explicit prior), M-DISC-fixed-strict (no extension:
undetermined colours -> UNKNOWN), M-DISC-MDL-fixed. Mission 03's historical results are read from its JSON files,
not recomputed. The runner prints only task ids and outcome labels.

  python -I mission-04/experiments/a0_uniqueness/rerun_arc.py training
  python -I mission-04/experiments/a0_uniqueness/rerun_arc.py evaluation
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))
import uniqueness as U  # noqa: E402

DATA = REPO / "mission-03" / "external" / "arc-agi-1" / "data"
M03 = REPO / "mission-03" / "experiments" / "arc"
LABEL = {"training": "DEV split (as in Mission 03)",
         "evaluation": "POST-HOC RE-EVALUATION on a split already used once in Mission 03; not a held-out result"}
VARIANTS = {"M-DISC-fixed": dict(colour_mode="prior"), "M-DISC-fixed-strict": dict(colour_mode="strict"),
            "M-DISC-MDL-fixed": dict(colour_mode="prior", tiebreak="mdl")}


def load(path):
    d = json.loads(Path(path).read_bytes())
    return ([(np.array(p["input"]), np.array(p["output"])) for p in d["train"]],
            [(np.array(p["input"]), np.array(p["output"])) for p in d["test"]])


def status(outs, tests):
    labels = []
    for o, (_, T) in zip(outs, tests):
        labels.append("abstain" if o is None else "correct" if o.shape == T.shape and (o == T).all() else "wrong")
    return "correct" if all(l == "correct" for l in labels) else "wrong" if "wrong" in labels else "abstain"


def main(split):
    hist = json.loads((M03 / f"arc_{split}.json").read_text())["rows"]
    rows = {}
    t0 = time.perf_counter()
    for f in sorted((DATA / split).glob("*.json")):
        tid = f.stem
        train, tests = load(f)
        row = {"M03-M-DISC": hist[tid]["M-DISC"]["status"], "M03-M-DISC-MDL": hist[tid]["M-DISC-MDL"]["status"]}
        for name, kw in VARIANTS.items():
            t1 = time.perf_counter()
            try:
                outs, info = U.solve_fixed(train, [I for I, _ in tests], **kw)
                row[name] = {"status": status(outs, tests), "reason": info.get("reason"), "uniqueness": info.get("uniqueness"),
                             "time_s": round(time.perf_counter() - t1, 3)}
            except Exception as e:
                row[name] = {"status": "error", "reason": f"{type(e).__name__}: {e}"}
        rows[tid] = row
        print(tid, {k: (v if isinstance(v, str) else v["status"]) for k, v in row.items()}, flush=True)
    summary = {}
    for name in ["M03-M-DISC", "M03-M-DISC-MDL", *VARIANTS]:
        st = [r[name] if isinstance(r[name], str) else r[name]["status"] for r in rows.values()]
        c, w = st.count("correct"), st.count("wrong")
        summary[name] = {"correct": c, "wrong": w, "abstain": st.count("abstain"), "error": st.count("error"),
                         "precision": round(c / (c + w), 3) if c + w else None}
    changed = {tid: {"M03": r["M03-M-DISC"], "fixed": r["M-DISC-fixed"]["status"], "why": r["M-DISC-fixed"]["reason"]}
               for tid, r in rows.items() if r["M03-M-DISC"] != r["M-DISC-fixed"]["status"]}
    out = {"label": LABEL[split], "split": split, "summary": summary, "changed_vs_M03": changed, "rows": rows,
           "time_s": round(time.perf_counter() - t0, 1)}
    (HERE / f"rerun_{split}.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({"label": LABEL[split], "summary": summary, "changed_vs_M03": changed}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
