"""JUDGE SIDE history-swap test for L1 (PROTOCOL.md section 6.6; amendment A1 defines the noise floor).
From the checkpoint of run A at step t: continue A's world for `horizon` steps (1) with A's own agent state, (2) with
A's agent state and a different agent random seed (noise floor), (3) with run B's agent state (history swap). The goal
distributions (first literal of each non-need goal) are compared by total-variation distance.
  python3 -I swap_eco.py ARM FAMILY.json SEED_A SEED_B T HORIZON RUN_DIR        # prints JSON
"""

from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_eco as R  # noqa: E402
import score_eco as S  # noqa: E402
from eco_env import load_family  # noqa: E402


def swap_test(arm, family, seed_a, seed_b, t, horizon, run_dir):
    fam = load_family(family)
    ck_a = pickle.loads((Path(run_dir) / f"{arm}_{fam['name']}_{seed_a}.ckpt_{t}.pkl").read_bytes())
    ck_b = pickle.loads((Path(run_dir) / f"{arm}_{fam['name']}_{seed_b}.ckpt_{t}.pkl").read_bytes())
    out = {}
    for name, agent_bytes, reseed in (("own", ck_a["agent"], 1), ("noise", ck_a["agent"], 2), ("swap", ck_b["agent"], 1)):
        w = pickle.loads(pickle.dumps(ck_a["world"]))
        R.run(arm, family, seed_a, horizon, run_dir, opts={"agent_pickle": agent_bytes, "reseed": reseed, "start_obs": ck_a["obs"]},
              tag=f".swap_{name}", world=w)
        _, a = S.load(run_dir, f"{arm}_{fam['name']}_{seed_a}.swap_{name}")
        t0 = min((g["t_logged"] for g in a["goals"] if g["t_logged"] > t), default=t)
        out[name] = S.goal_dist(a, t, 10 ** 9)
    tv_swap, tv_noise = S.tv(out["own"], out["swap"]), S.tv(out["own"], out["noise"])
    return {"arm": arm, "seed_a": seed_a, "seed_b": seed_b, "t": t, "horizon": horizon, "tv_swap": round(tv_swap, 3),
            "tv_noise": round(tv_noise, 3), "goals_own": round(sum(1 for _ in out["own"]), 1),
            "L1_pass": bool(out["own"]) and tv_swap >= 0.3 and tv_swap > tv_noise}


if __name__ == "__main__":
    a = sys.argv
    print(json.dumps(swap_test(a[1], a[2], int(a[3]), int(a[4]), int(a[5]), int(a[6]), a[7])))
