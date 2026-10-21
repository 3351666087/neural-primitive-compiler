"""Judge / constructor process separation for BrowserGym environments (Mission 06, G1-P3). Two sides:

JUDGE SIDE (judge_main, run in its own process): owns the BrowserGym environment and, for benchmark tasks, the task
object (its oracle `cheat`, its validator), the reward, the terminated / truncated flags and `info`. It records them in
a judge-only log and forwards to the constructor only the observation keys in OBS_ALLOW.

CONSTRUCTOR SIDE (Client, used inside the constructor process): sends actions as BrowserGym action strings and receives
filtered observations. guard_imports() installs an import hook in the constructor process that refuses benchmark task
modules (FORBIDDEN_MODULES) and records every attempt.

Protocol over a multiprocessing Pipe: ("reset", {"seed": s}) -> ("obs", obs); ("step", action) -> ("obs", obs);
("close", None) -> ("closed", None). The constructor decides when to stop; it never learns whether the task succeeded.
"""

from __future__ import annotations

import importlib.abc
import json
import sys
import time

OBS_ALLOW = ("goal", "goal_object", "chat_messages", "url", "open_pages_urls", "open_pages_titles", "active_page_index",
             "axtree_object", "dom_object", "extra_element_properties", "screenshot", "focused_element_bid",
             "last_action", "last_action_error", "elapsed_time")
FORBIDDEN_MODULES = ("browsergym.workarena", "browsergym.webarena", "browsergym.experiments", "alfworld")


# ------------------------------------------------------------------ constructor side
class _Guard(importlib.abc.MetaPathFinder):
    def __init__(self):
        self.attempts = []

    def find_spec(self, name, path=None, target=None):
        if any(name == m or name.startswith(m + ".") for m in FORBIDDEN_MODULES):
            self.attempts.append(name)
            raise ImportError(f"constructor side may not import {name}")
        return None


def guard_imports():
    """Install the import hook in the current (constructor) process; returns the guard (its .attempts lists refusals)."""
    leaked = [m for m in sys.modules if any(m == f or m.startswith(f + ".") for f in FORBIDDEN_MODULES)]
    if leaked:
        raise RuntimeError(f"forbidden modules already loaded in the constructor process: {leaked[:5]}")
    g = _Guard()
    sys.meta_path.insert(0, g)
    return g


class Client:
    def __init__(self, conn):
        self.conn = conn

    def _ask(self, msg):
        self.conn.send(msg)
        kind, payload = self.conn.recv()
        if kind == "error":
            raise RuntimeError(payload)
        return payload

    def reset(self, seed=None):
        return self._ask(("reset", {"seed": seed}))

    def step(self, action: str):
        return self._ask(("step", action))

    def close(self):
        return self._ask(("close", None))


# ------------------------------------------------------------------ judge side
def filter_obs(obs: dict) -> dict:
    return {k: obs[k] for k in OBS_ALLOW if k in obs}


def make_env(env_spec: dict):
    """env_spec: {"kind": "local", "url": "file:///..."} uses BrowserGym's open-ended task on a local page (no external
    site); {"kind": "workarena", "task": <registered id>, ...} is refused unless env_spec["allow_instance"] is True."""
    import gymnasium as gym
    import browsergym.core  # noqa: F401  (registers browsergym/openended)
    if env_spec["kind"] == "local":
        return gym.make("browsergym/openended", task_kwargs={"start_url": env_spec["url"]},
                        wait_for_user_message=False, headless=True)
    if env_spec["kind"] == "workarena":
        if not env_spec.get("allow_instance"):
            raise PermissionError("WorkArena instances are not to be touched in this pilot step")
        import browsergym.workarena  # noqa: F401  (judge side only)
        return gym.make(f"browsergym/{env_spec['task']}", headless=True)
    raise ValueError(env_spec["kind"])


def judge_main(conn, env_spec: dict, log_path: str):
    """Runs in the judge process. Everything the environment returns besides the filtered observation stays here."""
    log = open(log_path, "a")
    env = None
    try:
        env = make_env(env_spec)
        while True:
            kind, payload = conn.recv()
            t0 = time.perf_counter()
            if kind == "reset":
                obs, info = env.reset(seed=payload["seed"])
                rec = {"event": "reset", "seed": payload["seed"], "info_keys": sorted(info), "obs_keys": sorted(obs)}
                conn.send(("obs", filter_obs(obs)))
            elif kind == "step":
                obs, reward, terminated, truncated, info = env.step(payload)
                rec = {"event": "step", "action": payload, "reward": float(reward), "terminated": bool(terminated),
                       "truncated": bool(truncated), "info_keys": sorted(info),
                       "last_action_error": obs.get("last_action_error", "")}
                conn.send(("obs", filter_obs(obs)))
            elif kind == "close":
                rec = {"event": "close"}
                conn.send(("closed", None))
                log.write(json.dumps(rec) + "\n")
                break
            else:
                conn.send(("error", f"unknown message {kind}"))
                continue
            rec["judge_s"] = round(time.perf_counter() - t0, 3)
            log.write(json.dumps(rec, default=str) + "\n")
            log.flush()
    except Exception as e:                                     # noqa: BLE001
        conn.send(("error", f"{type(e).__name__}: {e}"))
    finally:
        if env is not None:
            env.close()
        log.close()
