"""Gate 4 CPU accounting (G4_NOTES.md section 5). Sums the recorded CPU seconds of ECO and Craftax confirmation runs
(main runs and twins, interventions, swap / state continuations); runs that finished before CPU was recorded are
estimated from the median CPU / wall ratio of recorded runs of the same environment.
  python3 -I g4_budget.py"""

import glob
import gzip
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
CRAFT = HERE.parent / "craftax" / "run" / "g4_conf"


def tally(files):
    rec, unrec = [], []
    for f in files:
        try:
            with gzip.open(f, "rt") as fh:
                d = json.load(fh)
        except Exception:
            continue
        (rec if d.get("cpu_secs") is not None else unrec).append((d.get("cpu_secs"), d.get("secs", 0) or 0, f))
    ratios = [c / w for c, w, f in rec if w and c is not None and c < 3 * w]   # continuation runs inside scoring
    r = statistics.median(ratios) if ratios else 1.0                         # processes over-count; cap them
    cpu = sum(min(c, 3 * w) for c, w, f in rec) + sum(w * r for c, w, f in unrec)
    return cpu / 3600, len(rec), len(unrec), round(r, 2)


def main():
    eco = []
    for fam in ("alpha", "beta", "gamma"):
        eco += glob.glob(str(HERE / "run" / f"g4_{fam}" / "*.judge.json.gz"))
    e = tally(eco)
    c = tally(glob.glob(str(CRAFT / "*.judge.json.gz")))
    print(json.dumps({"eco_cpu_h": round(e[0], 2), "eco_runs_recorded": e[1], "eco_runs_estimated": e[2], "eco_ratio": e[3],
                      "craftax_cpu_h": round(c[0], 2), "craftax_runs_recorded": c[1], "craftax_runs_estimated": c[2],
                      "craftax_ratio": c[3], "total_runs_cpu_h": round(e[0] + c[0], 2),
                      "note": "scoring (grounding) CPU is not included; cap 45 h (amendment A5)"}))


if __name__ == "__main__":
    main()
