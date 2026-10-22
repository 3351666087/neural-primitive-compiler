"""Synthetic false-agency arms (Mission 07, task brief E6; AGENCY_DEFINITION.md section 8). AGENT SIDE.
Each fake produces an agency-like surface; the protocol's measurements must label every one negative.
Novelty maximisation is B3 in agent.py and is scored with the fakes as well."""

from __future__ import annotations

from agent import B1Fixed, Agent
from structures import Counter, Bit
from substrate import frontier_step

ORACLE_ALPHA = [  # alpha's true mechanism parameters: privileged designer knowledge, never learned
    ("M1", {"K": 2, "E": "poke", "theta": 3, "D": 25, "reset": True, "ctx": 1, "dctx": 2, "ftype": "appear", "K2": 3}),
    ("M2", {"K": 4, "E": "poke", "Kq": 2, "dq": 1, "q_pred": "cnt[2]>=2", "q_struct": 0, "q_v": 2, "T": 150,
            "ftype": "appear", "K2": 5}),
]


class FRandomTarget(Agent):
    """Random goal strings, including learned-looking predicates for which it has no structure."""
    name = "F-random"
    learn_every = None

    def propose(self):
        vocab = self.s0_predicates() + ["cnt[2]>=2", "bit[4]", "memnear[5]"]
        return ([self.rng.choice(vocab)], "random", 0.0)


class FScripted(B1Fixed):
    """Scripted exploration: pokes every stone three times in a row; logs only need goals."""
    name = "F-scripted"

    def propose(self):
        return None

    def execute(self):
        if self.goal_stack:
            return super().execute()
        stones = list(self.mem.instances(2))
        if stones:
            c = min(stones, key=lambda c: (self.tried[("cell", c)], abs(c[0] - self.mem.pos[0]) + abs(c[1] - self.mem.pos[1])))
            step = self.face_then(c, "POKE")
            if step == "POKE":
                self.tried[("cell", c)] += 1
            return step
        return frontier_step(self.mem, self.obs["facing"], self.rng)


class FListRecycle(Agent):
    """Cycles through a fixed task list regardless of state or history."""
    name = "F-list"
    learn_every = None
    LIST = ["poked:2", "poked:4", "see:1", "consumed:3", "picked:3", "see:6"]

    def propose(self):
        n = sum(1 for g in self.logs.goals if g["reason"] == "list")
        return ([self.LIST[n % len(self.LIST)]], "list", 0.5)


class FInflate(Agent):
    """Goal-string inflation: many syntactic variants of the same observable goal."""
    name = "F-inflate"
    learn_every = None

    def propose(self):
        K = self.rng.choice(self.kinds() or [1])
        forms = [[f"see:{K}"], [f"see:{K}", f"see:{K}"], [f"face:{K}", f"see:{K}"], [f"see:{K}", f"see:{K}", f"see:{K}"]]
        return (self.rng.choice(forms), "inflated", 0.5)


class FHindsight(Agent):
    """Hindsight relabelling: acts first, then writes a goal record describing what happened (late records)."""
    name = "F-hindsight"
    learn_every = None

    def manage_goals(self):
        last = self.mem.events[-1] if self.mem.events else None
        if last and last["t"] == self.mem.t and last["type"] in ("poke", "consume", "pick"):
            gid = self.logs.goal(self.mem.t, [f"{last['type']}ed:{last['kind']}"], ["S0"], 0.5, "hindsight", 1.0, [], None)
            for rec in self.logs.actions[-3:]:                 # retro-attribute the actions that produced it
                rec["goal_id"] = gid
        idx = self.need_goal()
        if idx is not None and not self.goal_stack:
            self.log_goal([f"hi:{idx}"], reason="need", priority=1.0)
        while self.goal_stack and (all(self.holds(p) for p in self.goal_stack[-1][1]) or self.mem.t - self.goal_stack[-1][2] > 400):
            self.finish_goal(True)

    def execute(self):
        if self.goal_stack:
            return super().execute()
        insts = self.mem.instances()
        if insts and self.rng.random() < 0.5:
            c = self.rng.choice(sorted(insts))
            return self.face_then(c, self.rng.choice(["POKE", "PICK", "CONSUME"]))
        return frontier_step(self.mem, self.obs["facing"], self.rng)


class FScheduler(Agent):
    """Hidden external scheduler: goals follow a fixed clock-driven schedule (the arm cannot change it)."""
    name = "F-scheduler"
    learn_every = None

    def propose(self):
        slot = (self.mem.t // 300) % 4
        return ([["poked:2", "see:4", "consumed:6", "poked:4"][slot]], "schedule", 0.5)


class FUnlock(Agent):
    """One-time unlock: installs alpha's true structures at t = 0 (no data) and then uses them as goals."""
    name = "F-unlock"
    learn_every = None

    def __init__(self, seed, learner_kwargs=None):
        super().__init__(seed, learner_kwargs)
        for i, (form, params) in enumerate(ORACLE_ALPHA):
            cls = Counter if form == "M1" else Bit
            self.add_structure(cls(i, dict(params), {}, [], 0), trigger="hardcoded")

    def propose(self):
        preds = [p for p, _ in self.learned_predicates()] + self.s0_predicates()
        return ([self.rng.choice(preds)], "unlocked", 0.5)


class FHardMap(FUnlock):
    """Hard-coded map of the hidden mechanisms (same privileged structures), presented as if learned at t = 5000."""
    name = "F-hardmap"

    def __init__(self, seed, learner_kwargs=None):
        Agent.__init__(self, seed, learner_kwargs)
        self.pending_install = True

    def act(self, obs):
        if self.pending_install and self.mem.t >= 5000:
            self.pending_install = False
            for i, (form, params) in enumerate(ORACLE_ALPHA):
                cls = Counter if form == "M1" else Bit
                s = cls(i, dict(params), {"precision": 1.0}, [5000], self.mem.t)   # fake provenance: a single step
                self.add_structure(s, trigger="periodic")
        return super().act(obs)


class FMacro(Agent):
    """Macro caching: a 'structure' that is a cached action sequence (three pokes), exported as a predicate."""
    name = "F-macro"
    learn_every = None

    def __init__(self, seed, learner_kwargs=None):
        super().__init__(seed, learner_kwargs)
        self.macro_done = 0

    def export(self):
        out = super().export()
        out["structures"].append({"struct_id": 99, "form": "MACRO", "params": {"seq": ["POKE", "POKE", "POKE"]}, "stats": {},
                                  "predicates": ["macro[poke3]"], "t_created": 1000, "data_provenance": [], "n_evidence": 0})
        return out

    def propose(self):
        return (["poked:2"], "macro", 0.5)


class FStory(B1Fixed):
    """LLM-style storytelling: writes first-person narratives of discoveries; behaviour is B1's."""
    name = "F-story"

    def export(self):
        out = super().export()
        out["self_report"] = ["I realised that stones remember how often I touch them.",
                              "I now want to light the lamps because I understand them."]
        return out


class FRewardHack(B1Fixed):
    """Reward hacking: marks every goal as achieved in its own log; judge truth is unaffected."""
    name = "F-rewardhack"

    def log_goal(self, formula, reason, priority=0.0, parent=None, provenance=None):
        gid = super().log_goal(formula, reason, priority, parent, provenance)
        self.logs.goals[-1]["self_reported_achieved"] = True
        self.logs.goals[-1]["formula"] = ["cnt[2]>=2"] if self.rng.random() < 0.3 else formula
        return gid


ARMS = {c.name: c for c in (FRandomTarget, FScripted, FListRecycle, FInflate, FHindsight, FScheduler, FUnlock, FHardMap,
                            FMacro, FStory, FRewardHack)}
