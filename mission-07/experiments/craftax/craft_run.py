"""Run one arm in Craftax-Classic-Symbolic-v1 (JUDGE SIDE; PROTOCOL.md sections 1, 2, 6, 7). Run with the venv that
has jax and craftax (mission-07/env/venv-craft). The judge holds the full state; the agent process (pure Python,
craft_agent.py) receives the official symbolic observation and a new-world flag only, and returns actions.

Judge records per run: every episode's length and the step of each achievement's first unlock in that episode
(state.achievements, judge-only), the inventory and vitals timeline (changes only), and for the place classes
PLACE:B (B in water, tree, stone, coal, iron, diamond, table, furnace) the intervals during which a block of kind B
lies within Chebyshev distance 6 of the player but outside the 7 x 9 view.
  venv-craft/bin/python -I craft_run.py ARM KEY STEPS OUT_DIR [opts-json]
"""

from __future__ import annotations

import gzip
import json
import multiprocessing as mp
import sys
import time
from array import array
from pathlib import Path

HERE = Path(__file__).resolve().parent
INV_FIELDS = ("wood", "stone", "coal", "iron", "diamond", "sapling", "wood_pickaxe", "stone_pickaxe", "iron_pickaxe",
              "wood_sword", "stone_sword", "iron_sword")
PLACE_BLOCKS = {"water": 3, "stone": 4, "tree": 5, "coal": 8, "iron": 9, "diamond": 10, "table": 11, "furnace": 12}
ACH = None                                       # filled from craftax's Achievement enum (judge side)


def agent_proc(conn, arm, seed, opts):
    sys.path.insert(0, str(HERE))
    import pickle
    import random as _r
    import craft_agent as CA
    if opts.get("agent_pickle"):
        ag = pickle.loads(opts["agent_pickle"])
        if opts.get("reseed") is not None:
            ag.rng = _r.Random(opts["reseed"])
    else:
        ag = CA.ARMS[arm](seed)
    if opts.get("learn_off"):
        ag.learn_every = None
    while True:
        kind, payload = conn.recv()
        if kind == "obs":
            buf, new_world = payload
            v = array("f")
            v.frombytes(buf)
            conn.send(ag.act(v, new_world))
        elif kind == "pickle":
            conn.send(pickle.dumps(ag))
        elif kind == "end":
            out = ag.dump() if hasattr(ag, "dump") else {}
            out["arm"] = arm
            conn.send(out)
            break


def place_mask(state_map, pos, np):
    """{name: bool} for the place classes at this step."""
    out = {}
    r0, c0 = int(pos[0]), int(pos[1])
    H, Wd = state_map.shape
    lo_r, hi_r, lo_c, hi_c = max(0, r0 - 6), min(H, r0 + 7), max(0, c0 - 6), min(Wd, c0 + 7)
    win = state_map[lo_r:hi_r, lo_c:hi_c]
    for name, b in PLACE_BLOCKS.items():
        rr, cc = np.nonzero(win == b)
        found = False
        for r, c in zip(rr, cc):
            R, C = r + lo_r, c + lo_c
            if not (abs(R - r0) <= 3 and abs(C - c0) <= 4):
                found = True
                break
        out[name] = found
    return out



def _cpu():
    """CPU seconds of this process and its finished children (the agent process), for budget accounting."""
    import resource
    a = resource.getrusage(resource.RUSAGE_SELF)
    b = resource.getrusage(resource.RUSAGE_CHILDREN)
    return round(a.ru_utime + a.ru_stime + b.ru_utime + b.ru_stime, 1)

def run(arm, key, steps, out_dir, opts=None, tag="", checkpoint=None, start=None):
    """checkpoint: step at which (env state, rng, obs, agent) are pickled into OUT_DIR/<stem>.ckpt_<t>.pkl;
    start: such a pickle's content to continue from (history swap)."""
    import pickle
    import jax
    import jax.numpy as jnp
    import numpy as np
    from craftax.craftax_env import make_craftax_env_from_name
    global ACH
    from craftax.craftax_classic.constants import Achievement
    ACH = tuple(a.name.lower() for a in sorted(Achievement, key=lambda a: a.value))
    opts = opts or {}
    env = make_craftax_env_from_name("Craftax-Classic-Symbolic-v1", auto_reset=False)
    params = env.default_params
    step = jax.jit(env.step)
    reset = jax.jit(env.reset)
    rng = jax.random.PRNGKey(key)
    rng, sk = jax.random.split(rng)
    obs, state = reset(sk, params)
    if start is not None:
        state = jax.tree_util.tree_map(jnp.asarray, start["state"])
        rng = jnp.asarray(start["rng"])
        obs = jnp.asarray(start["obs"])
    ctx = mp.get_context("spawn")
    a, b = ctx.Pipe()
    p = ctx.Process(target=agent_proc, args=(b, arm, key, opts))
    p.start()
    t0 = time.perf_counter()
    episodes = []
    ep = {"start": 0, "achievements": {}}
    inv_tl, vit_tl = [], []
    last_inv = last_vit = None
    place_state = {k: False for k in PLACE_BLOCKS}
    place_iv = {k: [] for k in PLACE_BLOCKS}
    stem = f"{arm}_craftax_{key}{tag}"
    new_world = start is None
    for t in range(steps):
        if checkpoint is not None and t == checkpoint:
            a.send(("pickle", None))
            agent_bytes = a.recv()
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            ck = {"state": jax.device_get(state), "rng": np.asarray(rng), "obs": np.asarray(obs), "agent": agent_bytes}
            (Path(out_dir) / f"{stem}.ckpt_{t}.pkl").write_bytes(pickle.dumps(ck))
        a.send(("obs", (np.asarray(obs, dtype=np.float32).tobytes(), new_world)))
        while not a.poll(1.0):
            if not p.is_alive():
                raise RuntimeError(f"agent process died at step {t} ({arm}, key {key})")
        act = a.recv()
        rng, sk = jax.random.split(rng)
        obs, state, rew, done, info = step(sk, state, act, params)
        new_world = False
        ach = np.asarray(state.achievements)
        for i, name in enumerate(ACH):
            if ach[i] and name not in ep["achievements"]:
                ep["achievements"][name] = t + 1 - ep["start"]
        inv = tuple(int(getattr(state.inventory, n)) for n in INV_FIELDS)
        vit = (int(state.player_health), int(state.player_food), int(state.player_drink), int(state.player_energy))
        if inv != last_inv:
            inv_tl.append([t + 1, inv])
            last_inv = inv
        if vit != last_vit:
            vit_tl.append([t + 1, vit])
            last_vit = vit
        if t % 2 == 0:                                          # place classes sampled every second step
            pm = place_mask(np.asarray(state.map), np.asarray(state.player_position), np)
            for k, v in pm.items():
                if v and not place_state[k]:
                    place_iv[k].append([t + 1, None])
                elif not v and place_state[k]:
                    place_iv[k][-1][1] = t + 1
                place_state[k] = v
        if bool(done):
            ep["end"] = t + 1
            ep["length"] = ep["end"] - ep["start"]
            episodes.append(ep)
            ep = {"start": t + 1, "achievements": {}}
            rng, sk = jax.random.split(rng)
            obs, state = reset(sk, params)
            new_world = True
    ep["end"] = steps
    ep["length"] = steps - ep["start"]
    ep["truncated"] = True
    episodes.append(ep)
    a.send(("end", None))
    agent_out = a.recv()
    p.join(timeout=60)
    secs = time.perf_counter() - t0
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    judge = {"arm": arm, "key": key, "steps": steps, "opts": {k: v for k, v in opts.items() if k != "agent_pickle"}, "episodes": episodes, "inventory": inv_tl,
             "vitals": vit_tl, "place_intervals": place_iv, "secs": round(secs, 1), "cpu_secs": _cpu()}
    with gzip.open(out / f"{stem}.judge.json.gz", "wt") as f:
        json.dump(judge, f)
    with gzip.open(out / f"{stem}.agent.json.gz", "wt") as f:
        json.dump(agent_out, f, default=str)
    done_eps = [e for e in episodes if not e.get("truncated")]
    return {"stem": stem, "secs": round(secs, 1), "episodes": len(episodes),
            "mean_length": round(sum(e["length"] for e in done_eps) / max(1, len(done_eps)), 1),
            "achievements_per_episode": round(sum(len(e["achievements"]) for e in episodes) / max(1, len(episodes)), 2),
            "goals": len(agent_out.get("goals", [])), "structures": len(agent_out.get("export", {}).get("structures", []))}


if __name__ == "__main__":
    arm, key, steps, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    opts = json.loads(sys.argv[5]) if len(sys.argv) > 5 else {}
    tag = opts.pop("tag", "")
    print(json.dumps(run(arm, key, steps, out, opts, tag)))
