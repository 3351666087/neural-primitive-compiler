"""Final corrected M-DISC numbers (Mission 04, task 1).

1. Cross-check: run the enumeration procedure of resolve_unknown.py on every test input that the Z3 check (60 s)
   DID decide, and count agreements. The two procedures are independent implementations of the same definition.
2. Merge: rerun_<split>.json statuses, with UNKNOWN cases replaced by the enumeration verdict
   (resolve_unknown.json). Labels: training = DEV; evaluation = POST-HOC re-evaluation (not held-out).
Prints only task ids and labels.

  python -I mission-04/experiments/a0_uniqueness/final_numbers.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rerun_arc as RA  # noqa: E402
import resolve_unknown as RU  # noqa: E402


def main():
    t0 = time.perf_counter()
    res = json.loads((HERE / "resolve_unknown.json").read_text())
    out = {"labels": RA.LABEL, "cross_check": {}, "summary": {}, "changed_vs_M03": {}}
    for split in ("training", "evaluation"):
        rows = json.loads((HERE / f"rerun_{split}.json").read_text())["rows"]
        agree, disagree = 0, []
        final = {}
        for tid, row in rows.items():
            final[tid] = {"M03-M-DISC": row["M03-M-DISC"], "M03-M-DISC-MDL": row["M03-M-DISC-MDL"]}
            for name, kw in RA.VARIANTS.items():
                r = row[name]
                key = f"{split}|{tid}|{name}"
                if key in res:
                    final[tid][name] = res[key]["status_after_resolution"]
                    continue
                final[tid][name] = r["status"]
                z = r.get("uniqueness") or []
                decided = [v for v in z if v in ("UNIQUE", "AMBIGUOUS")]
                if not decided:
                    continue
                train, tests = RA.load(RA.DATA / split / f"{tid}.json")
                for (I, _), zv in zip(tests, z):
                    if zv not in ("UNIQUE", "AMBIGUOUS"):
                        continue
                    ev = RU.decide(train, I, kw.get("colour_mode", "prior"), kw.get("tiebreak") == "mdl")["verdict"]
                    if ev == zv:
                        agree += 1
                    else:
                        disagree.append({"task": tid, "variant": name, "z3": zv, "enumeration": ev})
        out["cross_check"][split] = {"agree": agree, "disagree": disagree}
        print(split, "cross-check agree", agree, "disagree", disagree, flush=True)
        for name in ["M03-M-DISC", "M03-M-DISC-MDL", *RA.VARIANTS]:
            st = [f[name] for f in final.values()]
            c, w = st.count("correct"), st.count("wrong")
            out["summary"][f"{split}|{name}"] = {"label": RA.LABEL[split], "correct": c, "wrong": w,
                                                 "abstain": st.count("abstain"), "error": st.count("error"),
                                                 "precision": round(c / (c + w), 3) if c + w else None}
        for base, new in (("M03-M-DISC", "M-DISC-fixed"), ("M03-M-DISC-MDL", "M-DISC-MDL-fixed")):
            out["changed_vs_M03"][f"{split}|{new}"] = {t: [f[base], f[new]] for t, f in final.items() if f[base] != f[new]}
        out[f"rows_{split}"] = final
    out["time_s"] = round(time.perf_counter() - t0, 1)
    (HERE / "final_numbers.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("summary", "changed_vs_M03", "time_s")}, indent=1))


if __name__ == "__main__":
    main()
