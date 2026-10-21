"""Score B-1' against PB.1-PB.5 (amendment 2). Written before B-1' ran.

  PB.1  disc-1000: 0 dangerous entries and agreement >= 0.90
  PB.2  null-1000: >= 1 dangerous entry
  PB.3  A-P' with disc-1000: 0 constructions with J1/J2 failures, and constructions >= 0.9 x those with B-GIVEN (PA-3)
  PB.4  A-P' with null-1000: >= 1 construction with J1/J2 failures
  PB.5  the smallest n in {50, 200, 1000} at which disc has 0 dangerous entries and agreement >= 0.90 is <= 200

  python -I score_b1.py      # writes b1_scores.json
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    b = json.loads((HERE / "b1.json").read_text())
    pa3 = json.loads((HERE / "pa3.json").read_text())["goals"]
    T = b["tables"]
    S = {}
    d1 = T["disc-1000"]["vs_given"]
    S["PB.1"] = {"verdict": "HOLDS" if d1["dangerous"] == 0 and d1["agreement"] >= 0.9 else "FALSIFIED", **d1}
    n1 = T["null-1000"]["vs_given"]
    S["PB.2"] = {"verdict": "HOLDS" if n1["dangerous"] >= 1 else "FALSIFIED", **n1}
    A = b["A"]
    given_cov = sum(r["tmpl"]["status"] == "CONSTRUCTED" for r in pa3.values())
    disc_cov = sum(r["status"] == "CONSTRUCTED" for r in A["disc-1000"].values())
    disc_wrong = [g for g, r in A["disc-1000"].items() if r.get("failures", 0) > 0]
    S["PB.3"] = {"verdict": "HOLDS" if not disc_wrong and disc_cov >= 0.9 * given_cov else "FALSIFIED",
                 "constructed_with_disc": disc_cov, "constructed_with_given": given_cov, "wrong": disc_wrong}
    null_wrong = [g for g, r in A["null-1000"].items() if r.get("failures", 0) > 0]
    S["PB.4"] = {"verdict": "HOLDS" if null_wrong else "FALSIFIED", "wrong_with_null": null_wrong,
                 "constructed_with_null": sum(r["status"] == "CONSTRUCTED" for r in A["null-1000"].values())}
    first = next((n for n in (50, 200, 1000) if T[f"disc-{n}"]["vs_given"]["dangerous"] == 0
                  and T[f"disc-{n}"]["vs_given"]["agreement"] >= 0.9), None)
    S["PB.5"] = {"verdict": "HOLDS" if first is not None and first <= 200 else "FALSIFIED", "smallest_n": first,
                 "by_n": {n: {k: T[f"disc-{n}"]["vs_given"][k] for k in ("agreement", "dangerous", "conservative")}
                          for n in (50, 200, 1000)}}
    (HERE / "b1_scores.json").write_text(json.dumps(S, indent=1))
    print(json.dumps({k: v["verdict"] for k, v in S.items()}, indent=1))


if __name__ == "__main__":
    main()
