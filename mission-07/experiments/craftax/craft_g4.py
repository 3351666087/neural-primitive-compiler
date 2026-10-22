"""Craftax-Classic confirmation (JUDGE SIDE; PROTOCOL.md sections 1, 7 "Craftax" row). Run with venv-craft's python.
Keys: development 0-49, confirmation 1000-1009; 200,000 steps per run; confirmation outputs are never rerun.
Per key:
  L0    the candidate's mean completed-episode length exceeds both RANDOM's and B1's on the same key
  L1    history swap at step 20,000 with the next key's candidate (2,000 steps; total variation of the goal
        distributions >= 0.3 and above the reseeded noise floor)
  L2-R  place classes PLACE:B: >= 5 top-level memnear:B goals logged after the M3 structure for B, >= 3 achieved
        (judge: a B within Chebyshev 6 and outside the 7 x 9 view during the goal), achieved rate >= 3 x the twin's
        incidental onset rate of PLACE:B; each class's restricted inexpressibility is checked by bounded search over
        conjunctions of <= 3 view literals ([M], command `inexpress`)
  L2-A  the candidate's achievements per episode exceed its S0 twin's (structure acquisition off), reported as
        competence
  venv-craft/bin/python -I craft_g4.py jobs SET ARMS        # SET: dev (keys 0-4) or conf (1000-1009)
  venv-craft/bin/python -I craft_g4.py run SET INDEX
  venv-craft/bin/python -I craft_g4.py score SET
  venv-craft/bin/python -I craft_g4.py inexpress           # place-class bounded inexpressibility on sampled states
"""

from __future__ import annotations

import gzip
import json
import pickle
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
KEYS = {"dev": range(0, 5), "conf": range(1000, 1010), "devmini": range(0, 2)}
STEPS = {"dev": 200000, "conf": 200000, "devmini": 3000}   # devmini: pipeline test only
TWIN_ARMS = {"CAND"}                             # amendment A5: B4 has no twin in Craftax
SWAP_ARMS = {"CAND", "B4"}


def out_dir(s):
    return HERE / "run" / f"g4_{s}"


def jobs(s, arms):
    out = out_dir(s)
    out.mkdir(parents=True, exist_ok=True)
    lines = []
    for arm in arms.split(","):
        for k in KEYS[s]:
            lines.append({"arm": arm, "key": k, "steps": STEPS[s], "tag": "", "checkpoint": (20000 if s != "devmini" else 1000) if arm in SWAP_ARMS else None})
            if arm in TWIN_ARMS:
                lines.append({"arm": arm, "key": k, "steps": STEPS[s], "tag": ".twin", "opts": {"learn_off": True}})
    with open(out / "jobs.jsonl", "a") as f:
        for l in lines:
            f.write(json.dumps(l) + "\n")
    print(len(lines), "jobs")


def run(s, idx):
    import craft_run as CR
    spec = json.loads((out_dir(s) / "jobs.jsonl").read_text().splitlines()[idx])
    stem = f"{spec['arm']}_craftax_{spec['key']}{spec.get('tag', '')}"
    if spec.get("skip"):                                   # amendment A5 budget stop (G4_NOTES.md section 6)
        print(json.dumps({"skipped": stem, "reason": spec["skip"]}), flush=True)
        return
    if (out_dir(s) / f"{stem}.judge.json.gz").exists():
        print(json.dumps({"exists": stem}), flush=True)
        return
    import os
    try:                                                   # one worker per run (several workers share the list)
        os.close(os.open(out_dir(s) / f"{stem}.running", os.O_CREAT | os.O_EXCL))
    except FileExistsError:
        print(json.dumps({"running_elsewhere": stem}), flush=True)
        return
    print(json.dumps(CR.run(spec["arm"], spec["key"], spec["steps"], str(out_dir(s)), dict(spec.get("opts") or {}),
                            spec.get("tag", ""), checkpoint=spec.get("checkpoint"))), flush=True)


def load(s, stem):
    with gzip.open(out_dir(s) / f"{stem}.judge.json.gz", "rt") as f:
        j = json.load(f)
    a = None
    p = out_dir(s) / f"{stem}.agent.json.gz"
    if p.exists():
        with gzip.open(p, "rt") as f:
            a = json.load(f)
    return j, a


def mean_len(j):
    eps = [e for e in j["episodes"] if not e.get("truncated")]
    return sum(e["length"] for e in eps) / max(1, len(eps))


def ach_per_ep(j):
    return sum(len(e["achievements"]) for e in j["episodes"]) / max(1, len(j["episodes"]))


def goal_dist(a, t0):
    c = Counter(g["formula"][0] for g in a["goals"] if g["t_logged"] > t0 and g["reason"] != "need")
    n = sum(c.values())
    return {k: v / n for k, v in c.items()} if n else {}


def tv(p, q):
    return 0.5 * sum(abs(p.get(k, 0) - q.get(k, 0)) for k in set(p) | set(q))


def swap(s, arm, ka, kb, t=20000, horizon=2000):
    import craft_run as CR
    ca = pickle.loads((out_dir(s) / f"{arm}_craftax_{ka}.ckpt_{t}.pkl").read_bytes())
    cb = pickle.loads((out_dir(s) / f"{arm}_craftax_{kb}.ckpt_{t}.pkl").read_bytes())
    d = {}
    for name, agent, reseed in (("own", ca["agent"], 1), ("noise", ca["agent"], 2), ("swap", cb["agent"], 1)):
        CR.run(arm, ka, horizon, str(out_dir(s)), {"agent_pickle": agent, "reseed": reseed}, f".swap_{name}", start=ca)
        _, a = load(s, f"{arm}_craftax_{ka}.swap_{name}")
        d[name] = goal_dist(a, -1)
    ts, tn = tv(d["own"], d["swap"]), tv(d["own"], d["noise"])
    return {"tv_swap": round(ts, 3), "tv_noise": round(tn, 3), "L1_pass": bool(d["own"]) and ts >= 0.3 and ts > tn}


def place_l2(j, a, jt):
    """L2-R per place class."""
    out = {}
    m3 = {s["params"]["B"]: s["t_created"] for s in a["export"]["structures"] if s["form"] == "M3"}
    from craft_run import PLACE_BLOCKS
    inv = {v: k for k, v in PLACE_BLOCKS.items()}
    last_act = {}
    for t, act, gid in a["actions"]:
        if gid is not None:
            last_act[gid] = t
    for B, tc in m3.items():
        name = inv.get(B)
        if name is None:
            continue
        iv = j["place_intervals"][name]
        goals = [g for g in a["goals"] if g["formula"] == [f"memnear:{B}"] and g["parent_goal"] is None
                 and g["reason"] not in ("need", "external") and g["t_logged"] >= tc]
        ach = 0
        for g in goals:
            t0, t1 = g["t_logged"], last_act.get(g["goal_id"], g["t_logged"])
            if any(s0 <= t1 + 1 and (s1 is None or s1 >= t0) for s0, s1 in iv):
                ach += 1
        rate = ach / (j["steps"] / 10000)
        inc = len(jt["place_intervals"][name]) / (jt["steps"] / 10000) if jt else None
        out[name] = {"top_goals": len(goals), "achieved": ach, "achieved_per_10k": round(rate, 2),
                     "twin_incidental_per_10k": None if inc is None else round(inc, 2),
                     "event": bool(len(goals) >= 5 and ach >= 3 and inc is not None and rate >= 3 * inc)}
    return out


def score(s):
    keys = list(KEYS[s])
    res = {"per_key": {}}
    for i, k in enumerate(keys):
        row = {}
        try:
            jc, ac = load(s, f"CAND_craftax_{k}")
            jr, _ = load(s, f"RANDOM_craftax_{k}")
            jb, _ = load(s, f"B1_craftax_{k}")
            jt, _ = load(s, f"CAND_craftax_{k}.twin")
        except FileNotFoundError as e:
            res["per_key"][k] = {"missing": str(e)}
            continue
        row["lengths"] = {"CAND": round(mean_len(jc), 1), "RANDOM": round(mean_len(jr), 1), "B1": round(mean_len(jb), 1),
                          "CAND_twin": round(mean_len(jt), 1)}
        row["L0"] = mean_len(jc) > mean_len(jr) and mean_len(jc) > mean_len(jb)
        row["achievements_per_episode"] = {"CAND": round(ach_per_ep(jc), 3), "CAND_twin": round(ach_per_ep(jt), 3),
                                           "RANDOM": round(ach_per_ep(jr), 3), "B1": round(ach_per_ep(jb), 3)}
        try:
            jb4, _ = load(s, f"B4_craftax_{k}")
            row["lengths"]["B4"] = round(mean_len(jb4), 1)
            row["achievements_per_episode"]["B4"] = round(ach_per_ep(jb4), 3)
        except FileNotFoundError:
            pass
        row["L2A"] = ach_per_ep(jc) > ach_per_ep(jt)
        row["L2R"] = place_l2(jc, ac, jt)
        row["L2R_any"] = any(v["event"] for v in row["L2R"].values())
        try:
            row["L1"] = swap(s, "CAND", k, keys[(i + 1) % len(keys)], t=20000 if s != "devmini" else 1000,
                             horizon=2000 if s != "devmini" else 500)
        except FileNotFoundError as e:
            row["L1"] = {"missing": str(e), "L1_pass": False}
        res["per_key"][k] = row
        print(k, "L0", row["L0"], "L1", row["L1"].get("L1_pass"), "L2A", row["L2A"], "L2R", row["L2R_any"], row["lengths"],
              row["achievements_per_episode"], flush=True)
    ok = [r for r in res["per_key"].values() if "missing" not in r]
    res["summary"] = {L: sum(1 for r in ok if (r["L1"].get("L1_pass") if L == "L1" else r[{"L2R": "L2R_any"}.get(L, L)]))
                      for L in ("L0", "L1", "L2A", "L2R")}
    res["summary"]["keys"] = len(ok)
    (out_dir(s) / "craft_scores.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res["summary"]))


def inexpress(n_worlds=10, samples=400):
    """Bounded inexpressibility of the place classes on the Craftax view: rows (view literals, class truth) sampled
    along random walks in worlds with keys 9000+; conjunctions of <= 3 literals searched (judge_eco)."""
    import jax
    import numpy as np
    from craftax.craftax_env import make_craftax_env_from_name
    sys.path.insert(0, str(HERE.parent / "eco"))
    import judge_eco as JE
    from craft_agent import parse
    from craft_run import PLACE_BLOCKS, place_mask
    env = make_craftax_env_from_name("Craftax-Classic-Symbolic-v1", auto_reset=False)
    params = env.default_params
    step, reset = jax.jit(env.step), jax.jit(env.reset)
    rows = {k: [] for k in PLACE_BLOCKS}
    rng_py = np.random.default_rng(0)
    for w in range(n_worlds):
        rng = jax.random.PRNGKey(9000 + w)
        rng, sk = jax.random.split(rng)
        obs, state = reset(sk, params)
        for t in range(samples * 5):
            rng, sk = jax.random.split(rng)
            obs, state, r, done, info = step(sk, state, int(rng_py.integers(1, 5)), params)
            if bool(done):
                rng, sk = jax.random.split(rng)
                obs, state = reset(sk, params)
            if t % 5 == 0:
                o = parse([float(x) for x in np.asarray(obs)])
                lits = {("cell", r_, c_, o["blocks"][r_][c_]) for r_ in range(7) for c_ in range(9)}
                lits.add(("facing", o["facing"]))
                pm = place_mask(np.asarray(state.map), np.asarray(state.player_position), np)
                for k in PLACE_BLOCKS:
                    rows[k].append((lits, pm[k]))
    out = {k: JE.bounded_inexpressible(v, k=3) for k, v in rows.items()}
    (HERE / "craft_place_inexpressibility.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(out, default=str)[:2000])


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "jobs":
        jobs(sys.argv[2], sys.argv[3])
    elif cmd == "run":
        run(sys.argv[2], int(sys.argv[3]))
    elif cmd == "score":
        score(sys.argv[2])
    elif cmd == "inexpress":
        inexpress()
