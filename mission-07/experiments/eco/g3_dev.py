"""Gate 3 development runs (JUDGE SIDE): candidate revisions and ablations on alpha's development seeds, each with its
S0 twin (structure acquisition off), scored with score_eco2 (amendment A2) including L3.
  python3 -I g3_dev.py jobs REV ARMS SEEDS     # e.g. jobs r0 CAND,OC1 100-104   -> run/g3_REV/jobs.jsonl
  python3 -I g3_dev.py run REV INDEX
  python3 -I g3_dev.py score REV               # -> run/g3_REV/scores.json (+ printed summary)
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ground_eco as G  # noqa: E402
import run_eco as R  # noqa: E402
import score_eco2 as S2  # noqa: E402
from eco_env import load_family  # noqa: E402

FAM = HERE / "family_alpha.json"
STEPS = 60000
C2, C3 = "LATENT:stone.charge", "LATENT:lamp.armed"


def out_dir(rev):
    return HERE / "run" / f"g3_{rev}"


def seeds_of(spec):
    if "-" in spec:
        a, b = spec.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in spec.split(",")]


def jobs(rev, arms, seeds):
    out = out_dir(rev)
    out.mkdir(parents=True, exist_ok=True)
    lines = []
    for arm in arms.split(","):
        for seed in seeds_of(seeds):
            lines.append({"arm": arm, "family": str(FAM), "seed": seed, "steps": STEPS, "out": str(out)})
            lines.append({"arm": arm, "family": str(FAM), "seed": seed, "steps": STEPS, "out": str(out),
                          "opts": {"learn_off": True}, "tag": ".twin"})
    with open(out / "jobs.jsonl", "a") as f:
        for l in lines:
            f.write(json.dumps(l) + "\n")
    print(len(lines), "jobs appended")


def run(rev, idx):
    spec = json.loads((out_dir(rev) / "jobs.jsonl").read_text().splitlines()[idx])
    stem = f"{spec['arm']}_alpha_{spec['seed']}{spec.get('tag', '')}"
    if (Path(spec["out"]) / f"{stem}.judge.json.gz").exists():
        print("exists", stem)
        return
    print(json.dumps(R.run_job(spec)), flush=True)


def score(rev):
    out = out_dir(rev)
    fam = load_family(FAM)
    probes, classes = G.make_probes(fam)
    specs = [json.loads(l) for l in (out / "jobs.jsonl").read_text().splitlines()]
    mains = sorted({(s["arm"], s["seed"]) for s in specs if not s.get("tag")})
    runs = {}
    for arm, seed in mains:
        stem = f"{arm}_alpha_{seed}"
        try:
            r = S2.score_run(stem, out, probes, classes, twin_stem=f"{stem}.twin")
        except FileNotFoundError as e:
            runs[stem] = {"missing": str(e)}
            continue
        r["L3"] = S2.l3(r, C2, C3)
        runs[stem] = S2.public(r)
        g = sorted({p["class"] for s in r["structures"].values() for p in s["predicates"].values() if p["grounded"]})
        print(stem, "lives", r["lives"], "L2", sorted(k for k, v in r["L2"].items() if v["event"]), "L3", r["L3"]["L3"],
              "grounded", g, flush=True)
    summary = {}
    for arm in sorted({a for a, _ in mains}):
        rs = [v for k, v in runs.items() if k.startswith(arm + "_") and "missing" not in v]
        summary[arm] = {"runs": len(rs), "mean_lives": round(sum(r["lives"] for r in rs) / max(1, len(rs)), 1),
                        "L2_runs_by_class": dict(Counter(k for r in rs for k, v in r["L2"].items() if v["event"])),
                        "C2_L2": sum(r["L3"]["C2_L2"] for r in rs), "C3_L2": sum(r["L3"]["C3_L2"] for r in rs),
                        "L3": sum(r["L3"]["L3"] for r in rs),
                        "s1_runs": sum(1 for r in rs if r["L3"]["s1"]), "s2_runs": sum(1 for r in rs if r["L3"]["s2"])}
    (out / "scores.json").write_text(json.dumps({"summary": summary, "runs": runs}, indent=1, default=str))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "jobs":
        jobs(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == "run":
        run(sys.argv[2], int(sys.argv[3]))
    elif cmd == "score":
        score(sys.argv[2])
