"""Gate 4 confirmation runs in ECO (JUDGE SIDE; PROTOCOL.md sections 1, 7, 9; amendments A2-A5).

Families and seeds: alpha confirmation 200-209, beta 300-309, gamma 400-409. A held-out family file is used only
if its SHA-256 equals the value in CUSTODY.md (checked before every read). Outputs that already exist are never
rerun (confirmation runs are run once).
  python3 -I g4_jobs.py jobs FAMILY ARMS            # FAMILY in alpha, beta, gamma; ARMS comma separated
  python3 -I g4_jobs.py run FAMILY INDEX
Main runs carry a checkpoint at step 20,000 (history-swap L1); learning arms also get an S0 twin (learn_off).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
CUSTODIAN = Path("/Users/null3351/Code/m07-custodian")
CUSTODY = {"family_beta.json": "41c050373310a512c13d33f10ff84d9f5e8a509ffe6a85cc3bc2863d00ca5bfb",
           "demos_beta.json": "abbe165d84a5c81bd0d9ef171aabaa4aa27ac3596c224f798f8fc8e82169b50e",
           "family_gamma.json": "2a43a5dfc5537d06307a4f4bca2b91fd78c16d294b59e120a5eabc0608faa911",
           "demos_gamma.json": "c09fd24b5f43582123b71ed2bee1f6486525d2ad9b9af8438727ace5e77d9995"}
SEEDS = {"alpha": range(200, 210), "beta": range(300, 310), "gamma": range(400, 410)}
NO_TWIN = {"B1"}
STEPS = 60000


def family_path(name):
    if name == "alpha":
        return HERE / "family_alpha.json"
    p = CUSTODIAN / f"family_{name}.json"
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    if h != CUSTODY[p.name]:
        raise SystemExit(f"hash mismatch for {p.name}: {h}")
    return p


def out_dir(name):
    return HERE / "run" / f"g4_{name}"


def jobs(name, arms):
    fam = str(family_path(name))
    out = out_dir(name)
    out.mkdir(parents=True, exist_ok=True)
    lines = []
    for arm in arms.split(","):
        for seed in SEEDS[name]:
            lines.append({"arm": arm, "family": fam, "seed": seed, "steps": STEPS, "out": str(out), "checkpoint": 20000})
            if arm not in NO_TWIN:
                lines.append({"arm": arm, "family": fam, "seed": seed, "steps": STEPS, "out": str(out), "tag": ".twin",
                              "opts": {"learn_off": True}})
    with open(out / "jobs.jsonl", "a") as f:
        for l in lines:
            f.write(json.dumps(l) + "\n")
    print(len(lines), "jobs appended to", out / "jobs.jsonl")


def run(name, idx):
    import run_eco as R
    from eco_env import load_family
    spec = json.loads((out_dir(name) / "jobs.jsonl").read_text().splitlines()[idx])
    fam = load_family(family_path(name))                    # hash check before every read
    stem = f"{spec['arm']}_{fam['name']}_{spec['seed']}{spec.get('tag', '')}"
    if (Path(spec["out"]) / f"{stem}.judge.json.gz").exists():
        print(json.dumps({"exists": stem}), flush=True)
        return
    try:
        print(json.dumps(R.run_job(spec)), flush=True)
    except Exception as e:
        print(json.dumps({"job": idx, "stem": stem, "error": f"{type(e).__name__}: {e}"}), flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "jobs":
        jobs(sys.argv[2], sys.argv[3])
    else:
        run(sys.argv[2], int(sys.argv[3]))
