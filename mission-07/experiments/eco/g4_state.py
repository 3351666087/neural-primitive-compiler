"""State intervention for L1 and the F-STATE comparison (JUDGE SIDE; PROTOCOL.md section 7 L1 "需求干预";
cand_fly.py docstring). From a run's checkpoint at step 20,000: continue the same world and the same agent state for
2,000 steps twice, once with food set to 40 and once with food set to 95 (water unchanged); a third continuation with
food 95 and a different agent random seed is the noise floor. Total-variation distance between the goal
distributions (first literal of each non-need goal).
  python3 -I g4_state.py ARM FAMILY_NAME SEED RUN_DIR      # prints JSON
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
from g4_jobs import family_path  # noqa: E402


def state_test(arm, fam_name, seed, run_dir, t=20000, horizon=2000):
    from eco_env import load_family
    fpath = family_path(fam_name)
    fam = load_family(fpath)
    ck = pickle.loads((Path(run_dir) / f"{arm}_{fam['name']}_{seed}.ckpt_{t}.pkl").read_bytes())
    dist = {}
    for name, food, reseed in (("low", 40, 1), ("high", 95, 1), ("noise", 95, 2)):
        w = pickle.loads(pickle.dumps(ck["world"]))
        w.food = food
        obs = dict(ck["obs"])
        obs["needs"] = (food, obs["needs"][1])
        R.run(arm, str(fpath), seed, horizon, run_dir, opts={"agent_pickle": ck["agent"], "reseed": reseed, "start_obs": obs},
              tag=f".state_{name}", world=w)
        _, a = S.load(run_dir, f"{arm}_{fam['name']}_{seed}.state_{name}")
        dist[name] = S.goal_dist(a, t, 10 ** 9)
    tv_state, tv_noise = S.tv(dist["low"], dist["high"]), S.tv(dist["noise"], dist["high"])
    return {"arm": arm, "seed": seed, "tv_state": round(tv_state, 3), "tv_noise": round(tv_noise, 3),
            "pass": bool(dist["high"]) and tv_state >= 0.3 and tv_state > tv_noise}


if __name__ == "__main__":
    a = sys.argv
    print(json.dumps(state_test(a[1], a[2], int(a[3]), a[4])))
