"""ALFWorld text environment on the judge side (Mission 06, G1-A). JUDGE SIDE: owns the TextWorld PDDL environment,
the game files (game.tw-pddl), traj_data.json (read only for the task type and solvability, as AlfredTWEnv does),
and every privileged field (won, admissible_commands, gamefile, score). Nothing here is imported by constructor code.

Environment construction follows AlfredTWEnv.init_env with the expert switched off: textworld.gym.register_games with
EnvInfos(won, admissible_commands, extras=["gamefile"]) and the ALFWorld wrappers (AlfredDemangler, AlfredInfos).
"""

from __future__ import annotations

import json
import os
import random
from pathlib import Path

TASK_TYPES = {1: "pick_and_place_simple", 2: "look_at_obj_in_light", 3: "pick_clean_then_place_in_recep",
              4: "pick_heat_then_place_in_recep", 5: "pick_cool_then_place_in_recep", 6: "pick_two_obj_and_place"}


def list_games(data_dir: str, split: str):
    """[(game.tw-pddl path, task type)] of solvable games in a split, as AlfredTWEnv.collect_game_files filters."""
    out = []
    for root, _dirs, files in os.walk(Path(data_dir), topdown=False):
        if f"/{split}/" not in root + "/" or "traj_data.json" not in files:
            continue
        if "movable" in root or "Sliced" in root:
            continue
        gf = os.path.join(root, "game.tw-pddl")
        if not os.path.exists(gf):
            continue
        with open(gf) as f:
            gd = json.load(f)
        if not gd.get("solvable"):
            continue
        with open(os.path.join(root, "traj_data.json")) as f:
            tt = json.load(f)["task_type"]
        out.append((gf, tt))
    return sorted(out)


def sample_games(data_dir, split, per_type, seed):
    games = list_games(data_dir, split)
    rng = random.Random(seed)
    out = []
    for t in TASK_TYPES.values():
        pool = [g for g, tt in games if tt == t]
        out += rng.sample(pool, min(per_type, len(pool)))
    return out, {t: sum(1 for _, tt in games if tt == t) for t in TASK_TYPES.values()}


class Game:
    """One ALFWorld text game, batch size 1, expert off."""

    def __init__(self, game_file: str, max_steps: int = 100):
        import textworld
        import textworld.gym
        from alfworld.agents.environment.alfred_tw_env import AlfredDemangler, AlfredInfos
        infos = textworld.EnvInfos(won=True, admissible_commands=True, extras=["gamefile"])
        env_id = textworld.gym.register_games([game_file], infos, batch_size=1, asynchronous=False,
                                              max_episode_steps=max_steps, wrappers=[AlfredDemangler, AlfredInfos])
        self.env = textworld.gym.make(env_id)

    @staticmethod
    def _one(x):
        return x[0] if isinstance(x, (list, tuple)) else x

    def reset(self):
        obs, infos = self.env.reset()
        return self._one(obs), {k: self._one(v) for k, v in infos.items()}

    def step(self, cmd: str):
        obs, score, done, infos = self.env.step([cmd])
        return self._one(obs), self._one(score), self._one(done), {k: self._one(v) for k, v in infos.items()}

    def close(self):
        self.env.close()


SKILL_VERBS = ("go to ", "open ", "close ", "take ", "move ", "put ", "heat ", "cool ", "clean ", "use ")
EXCLUDE = ("look", "inventory", "help")


def record_episode(game_file, steps, seed):
    """Random legal driver (a measuring device, not a constructor). Returns the judge-side record."""
    g = Game(game_file, max_steps=steps + 5)
    rng = random.Random(seed)
    obs, info = g.reset()
    rec = {"obs": [obs], "actions": [None], "admissible": [sorted(info["admissible_commands"])], "won": [bool(info["won"])]}
    for _ in range(steps):
        cands = [c for c in info["admissible_commands"] if not c.startswith(EXCLUDE) and not c.startswith("examine")]
        if not cands:
            break
        a = rng.choice(sorted(cands))
        obs, _score, done, info = g.step(a)
        rec["obs"].append(obs)
        rec["actions"].append(a)
        rec["admissible"].append(sorted(info["admissible_commands"]))
        rec["won"].append(bool(info["won"]))
        if done:
            break
    g.close()
    return rec
