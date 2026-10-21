"""JUDGE SIDE: composite goals on real ALFWorld rooms (EXPERIMENT_PRE_REGISTRATION.md section G4b).

A composite goal is a conjunction of atoms over two objects of different types, built from the six atom kinds the frozen
library already has: IN(T, R), CLEAN / HEAT / COOL(T), HOLDING(T), LIT(lamp type). The goal sentence replaces the game's
own "Your task is to: ..." in the first observation. Success is judged from the environment's state facts
(inreceptacle, isclean, ishot, iscool, holds, istoggled, atlocation): there must be two distinct objects, one per goal
type, that satisfy every atom at the end of the episode.

Goal object types must have an instance inside a receptacle at the start (findable from observations); the lamp type
must be one that official training tasks use. The game's own goal is excluded from generation (no atom on its target object type). If it is nevertheless satisfied
during an episode, TextWorld stops updating the state; the judge then answers "Nothing happens." to every later command
(like the other judges after a win), flags the episode `orig_won` and judges the frozen state.
"""

import json
import random
import re
from pathlib import Path

TREAT_DEV = {"CLEAN": "sinkbasin", "HEAT": "microwave", "COOL": "fridge"}
TREAT_ADJ = {"CLEAN": "clean", "HEAT": "hot", "COOL": "cool"}
FAMILIES = ("F2", "F3", "F3L", "F4")


def _t(name):
    return name.strip()[:-4] if name.strip().endswith("type") else name.strip()


def initial_world(game_file):
    """Facts of the initial state, reduced to what the generator needs."""
    import textworld
    import textworld.gym
    from alfworld.agents.environment.alfred_tw_env import AlfredDemangler, AlfredInfos
    env = textworld.gym.make(textworld.gym.register_games(
        [game_file], textworld.EnvInfos(facts=True), batch_size=1, asynchronous=False, max_episode_steps=5,
        wrappers=[AlfredDemangler, AlfredInfos]))
    _obs, info = env.reset()
    f = info["facts"][0]
    env.close()
    w = {"otype": {}, "rtype": {}, "inrec": {}, "pick": set(), "toggle": set(), "can": set()}
    for x in f:
        a = [y.name for y in x.arguments]
        if x.name == "objecttype":
            w["otype"][a[0]] = _t(a[1])
        elif x.name == "receptacletype":
            w["rtype"][a[0]] = _t(a[1])
        elif x.name == "inreceptacle":
            w["inrec"][a[0]] = a[1]
        elif x.name == "pickupable":
            w["pick"].add(a[0])
        elif x.name == "toggleable":
            w["toggle"].add(a[0])
        elif x.name == "cancontain":
            w["can"].add((_t(a[0]), _t(a[1])))
    return w


def whitelists(train_games):
    """Object types that official training tasks use per task type (pddl_params.object_target)."""
    wl, tog = {}, set()
    for g, t in train_games:
        pp = json.loads((Path(g).parent / "traj_data.json").read_text())["pddl_params"]
        wl.setdefault(t, set()).add(pp["object_target"].lower())
        if pp.get("toggle_target"):
            tog.add(pp["toggle_target"].lower())
    return {"place": wl["pick_and_place_simple"] | wl["pick_two_obj_and_place"], "CLEAN": wl["pick_clean_then_place_in_recep"],
            "HEAT": wl["pick_heat_then_place_in_recep"], "COOL": wl["pick_cool_then_place_in_recep"],
            "look": wl["look_at_obj_in_light"], "toggle": tog}


def make_goal(game_file, family, rng, wl):
    """A feasible composite goal of the family in this room, or None. Returns {"atoms": [...], "sentence": str}."""
    w = initial_world(game_file)
    orig = json.loads((Path(game_file).parent / "traj_data.json").read_text())["pddl_params"]["object_target"].lower()
    types = sorted({w["otype"][o] for o in w["pick"] if o in w["otype"] and o in w["inrec"]} - {orig})   # findable
    rtypes = sorted(set(w["rtype"].values()))
    present = lambda rt: rt in rtypes

    def place_options(T):
        held_in = {w["rtype"].get(w["inrec"].get(o)) for o in w["pick"] if w["otype"].get(o) == T}
        return [R for R in rtypes if (R, T) in w["can"] and R not in held_in]

    def treat_options(T):
        return [k for k in ("CLEAN", "HEAT", "COOL") if T in wl[k] and present(TREAT_DEV[k])]
    lamps = sorted({w["otype"][o] for o in w["toggle"] if o in w["otype"]} & wl["toggle"])   # official toggle targets
    for _ in range(200):
        if family in ("F2", "F3"):
            pool1 = [T for T in types if place_options(T) and (family == "F2" and T in wl["place"] or family == "F3" and treat_options(T))]
            pool2 = [T for T in types if place_options(T) and T in wl["place"]]
        elif family == "F3L":
            if not lamps:
                return None
            pool1 = [T for T in types if place_options(T) and T in wl["place"]]
            pool2 = [T for T in types if T in wl["look"]]
        else:
            pool1 = pool2 = [T for T in types if place_options(T) and treat_options(T)]
        if not pool1 or not pool2:
            return None
        T1, T2 = rng.choice(pool1), rng.choice(pool2)
        if T1 == T2:
            continue
        g1 = [("IN", T1, rng.choice(place_options(T1)))]
        if family in ("F3", "F4"):
            g1 = [(rng.choice(treat_options(T1)), T1, None)] + g1
        if family == "F3L":
            g2 = [("HOLDING", T2, None), ("LIT", rng.choice(lamps), None)]
        else:
            g2 = [("IN", T2, rng.choice(place_options(T2)))]
            if family == "F4":
                g2 = [(rng.choice(treat_options(T2)), T2, None)] + g2
        groups = [g1, g2]
        rng.shuffle(groups)
        atoms = [a for g in groups for a in g]
        rng.shuffle(atoms)                                  # the constructor gets the atoms in a random order
        return {"atoms": [list(a) for a in atoms], "sentence": sentence(groups)}
    return None


def clause(group):
    kinds = {a[0]: a for a in group}
    if "HOLDING" in kinds:
        return f"look at a {kinds['HOLDING'][1]} under the {kinds['LIT'][1]}"
    T, R = kinds["IN"][1], kinds["IN"][2]
    adj = next((TREAT_ADJ[k] + " " for k in TREAT_ADJ if k in kinds), "")
    return f"put a {adj}{T} in/on the {R}"


def sentence(groups):
    return " and ".join(clause(g) for g in groups)


def satisfied(facts, atoms):
    """Two distinct objects (one per goal type) satisfy every atom in the final state."""
    F = {(x.name, tuple(y.name for y in x.arguments)) for x in facts}
    otype = {a[0]: _t(a[1]) for n, a in F if n == "objecttype"}
    rtype = {a[0]: _t(a[1]) for n, a in F if n == "receptacletype"}
    inrec = {}
    for n, a in F:
        if n == "inreceptacle":
            inrec.setdefault(a[0], set()).add(a[1])
    held = {a[1] for n, a in F if n == "holds"}
    flag = {k: {a[0] for n, a in F if n == p} for k, p in (("CLEAN", "isclean"), ("HEAT", "ishot"), ("COOL", "iscool"))}
    toggled = {a[0] for n, a in F if n == "istoggled"}
    oloc = {a[0]: a[1] for n, a in F if n == "objectatlocation"}
    aloc = {a[1] for n, a in F if n == "atlocation"}

    def ok(o, atom):
        k, T, X = atom
        if otype.get(o) != T:
            return False
        if k == "IN":
            return any(rtype.get(r) == X for r in inrec.get(o, ()))
        if k in flag:
            return o in flag[k]
        if k == "HOLDING":
            return o in held
        return False
    types = sorted({a[1] for a in atoms if a[0] != "LIT"})
    cand = {T: [o for o, t in otype.items() if t == T] for T in types}
    lit = [a for a in atoms if a[0] == "LIT"]
    if lit and not any(otype.get(l) == lit[0][1] and l in toggled and oloc.get(l) in aloc for l in otype):
        return False

    def assign(i, used):
        if i == len(types):
            return True
        T = types[i]
        for o in cand[T]:
            if o not in used and all(ok(o, a) for a in atoms if a[1] == T and a[0] != "LIT"):
                if assign(i + 1, used | {o}):
                    return True
        return False
    return assign(0, frozenset())


class CompositeGame:
    def __init__(self, game_file, spec, max_steps):
        import textworld
        import textworld.gym
        from alfworld.agents.environment.alfred_tw_env import AlfredDemangler, AlfredInfos
        self.spec, self.atoms = spec, [tuple(a) for a in spec["atoms"]]
        self.env = textworld.gym.make(textworld.gym.register_games(
            [game_file], textworld.EnvInfos(won=True, facts=True), batch_size=1, asynchronous=False,
            max_episode_steps=max_steps + 5, wrappers=[AlfredDemangler, AlfredInfos]))
        self.orig_won, self.facts = False, None

    def reset(self):
        obs, info = self.env.reset()
        self.facts = info["facts"][0]
        o = obs[0]
        return re.sub(r"Your task is to: .*$", f"Your task is to: {self.spec['sentence']}.", o.strip(), flags=re.S)

    def step(self, cmd):
        if self.orig_won:
            return "Nothing happens."
        obs, _s, _d, info = self.env.step([cmd])
        self.facts = info["facts"][0]
        if info["won"][0]:
            self.orig_won = True
        return obs[0]

    def success(self):
        return satisfied(self.facts, self.atoms)

    def close(self):
        self.env.close()
