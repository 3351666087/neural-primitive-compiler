"""G2-ALF: the frozen Mission 05 contract core applied to ALFWorld with accounted adapters
(EXPERIMENT_PRE_REGISTRATION.md section G2-ALF). CONSTRUCTOR SIDE: a pure function of the text observations; imports
no environment package and reads no data file.

Frozen core (method of Mission 05, re-implemented over abstract contract tables): goals are conjunctions of atoms;
achievers carry contracts (applicability, progress, pairwise preservation) with an evidence tag; A-P orders the atoms so
that every achiever preserves the atoms ordered before it; the priority controller runs the achiever of the first
violated atom. Evidence rule: strict mode (G2A-0) accepts only "P" (proved) or "M" (bounded exhaustive) contracts;
axiom mode (G2A-1) also accepts "AX" (environment axioms, trusted) and adds runtime monitors that stop (abstain) on the
first violated expectation. B1 (HTN): the same macros in a fixed hand-written order per goal form, no contracts, no
monitors (it carries on after an unexpected observation).

Adapters (designer knowledge, KNOWLEDGE_PROVENANCE.md): goal sentence forms; observation wording (belief.py, with the
one-receptacle-per-place prior); the achiever macros and their axioms.
"""

from __future__ import annotations

import itertools
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "g1"))
import belief as BL  # noqa: E402

# ------------------------------------------------------------------ goal parser (frozen once)
_T = r"(\w+)"
_R = r"(\w+)"
GOAL_FORMS = [
    (rf"^put (?:a|an|some) clean {_T} (?:in|on|in/on) {_R}$", "clean"),
    (rf"^clean (?:a|an|some) {_T} and put it (?:in|on|in/on) {_R}$", "clean"),
    (rf"^put (?:a|an|some) hot {_T} (?:in|on|in/on) {_R}$", "heat"),
    (rf"^heat (?:a|an|some) {_T} and put it (?:in|on|in/on) {_R}$", "heat"),
    (rf"^put (?:a|an|some) cool {_T} (?:in|on|in/on) {_R}$", "cool"),
    (rf"^cool (?:a|an|some) {_T} and put it (?:in|on|in/on) {_R}$", "cool"),
    (rf"^put two {_T} (?:in|on|in/on) {_R}$", "two"),
    (rf"^find two {_T} and put them (?:in|on|in/on) {_R}$", "two"),
    (rf"^(?:look at|examine) (?:a|an|some|the )?{_T} (?:under|with) the (\w+)$", "light"),
    (rf"^put (?:a|an|some) {_T} (?:in|on|in/on) {_R}$", "place"),
]


def parse_goal(goal: str):
    g = (goal or "").strip().rstrip(".").lower()
    for pat, form in GOAL_FORMS:
        m = re.match(pat, g)
        if m:
            T, X = m.group(1), m.group(2)
            if form == "place":
                return [("IN", T, X)]
            if form in ("clean", "heat", "cool"):
                return [(form.upper(), T, None), ("IN", T, X)]
            if form == "two":
                return [("IN2", T, X)]
            return [("HOLDING", T, None), ("LIT", X, None)]
    return None


# ------------------------------------------------------------------ contract table (axioms, tag "AX")
# achiever of each atom kind; preserves[a][b] = achiever of a keeps atom kind b true once it holds
ACHIEVER = {"IN": "fetch_place", "IN2": "fetch_place_twice", "CLEAN": "fetch_clean", "HEAT": "fetch_heat",
            "COOL": "fetch_cool", "HOLDING": "fetch", "LIT": "find_lamp_use"}
PRESERVES = {
    "IN": {"CLEAN": True, "HEAT": True, "COOL": True},                     # moving does not undo the treatment
    "CLEAN": {"IN": False}, "HEAT": {"IN": False}, "COOL": {"IN": False},    # treating needs the object in hand
    "HOLDING": {"LIT": False},                                               # walking away leaves the lamp's place
    "LIT": {"HOLDING": True},
}
EVIDENCE = {k: "AX" for k in ACHIEVER}                                       # no proof, no bounded check: axioms


def construct(atoms, accept=("P", "M", "AX")):
    """A-P over the abstract table: an atom order where each achiever preserves every earlier atom, and every
    achiever's contract carries an accepted evidence tag. Returns (order, reason)."""
    if atoms is None:
        return None, "goal not parsed"
    if any(EVIDENCE[a[0]] not in accept for a in atoms):
        return None, "no contract with accepted evidence"
    for perm in itertools.permutations(atoms):
        ok = all(PRESERVES.get(perm[j][0], {}).get(perm[i][0], True) for j in range(len(perm)) for i in range(j))
        if ok:
            return list(perm), None
    return None, "no order satisfies pairwise preservation"


# ------------------------------------------------------------------ controller
class Abstain(Exception):
    pass


class Agent:
    """Runs achiever macros through act(cmd) -> obs, keeping a belief from the observations only."""

    def __init__(self, act, first_obs, budget, monitors=True):
        self._act, self.budget, self.monitors = act, budget, monitors
        self.hist = [(None, first_obs)]
        self.steps = 0
        self.violations = []
        self.flags = {}                    # object -> {"clean", "hot", "cool"}
        self.placed = set()
        self.lamp_on_at = None

    @property
    def b(self):
        return BL.belief_after(self.hist)

    def act(self, cmd, expect):
        if self.steps >= self.budget:
            raise Abstain("budget exhausted")
        self.steps += 1
        obs = self._act(cmd)
        self.hist.append((cmd, obs))
        m = re.search(r"You (clean|heat|cool) the (.*?) using", obs)
        if m:
            self.flags.setdefault(m.group(2), set()).add({"clean": "clean", "heat": "hot", "cool": "cool"}[m.group(1)])
        if re.search(r"You turn on the", obs):
            self.lamp_on_at = self.b.location
        if expect not in obs:
            self.violations.append(cmd.split(" ")[0])
            if self.monitors:
                raise Abstain(f"monitor: '{cmd.split(' ')[0]}' did not give '{expect}'")
        return obs

    def goto(self, r):
        if self.b.location != r:
            self.act(f"go to {r}", f"You arrive at {r}")
        if self.b.state.get(r) == "closed":
            self.act(f"open {r}", f"You open the {r}")

    def receptacles(self):
        """Receptacles in the order the first observation lists them (no prior about where things are)."""
        if not hasattr(self, "_order"):
            m = re.search(r"Looking quickly around you, you see (.*?)\.\s", self.hist[0][1].replace("\n", " ") + " ")
            self._order = BL._items(m.group(1)) if m else []
        return self._order + sorted(set(self.b.receptacles) - set(self._order))

    def first_of_type(self, rtype):
        for r in self.receptacles():
            if r.split(" ")[0] == rtype:
                return r
        raise Abstain(f"no receptacle of type {rtype}")

    def fetch(self, T, exclude=()):
        held = self.b.holding
        if held and held.split(" ")[0] == T and held not in exclude:
            return held
        for r in self.receptacles():
            self.goto(r)
            cand = [o for o in sorted(self.b.contents.get(r, ())) if o.split(" ")[0] == T and o not in exclude]
            if cand:
                self.act(f"take {cand[0]} from {r}", "You pick up")
                return cand[0]
        raise Abstain("search exhausted")

    def place(self, o, R):
        r = self.first_of_type(R)
        self.goto(r)
        self.act(f"move {o} to {r}", "You move")
        self.placed.add(o)

    def treat(self, o, kind):
        dev = {"CLEAN": "sinkbasin", "HEAT": "microwave", "COOL": "fridge"}[kind]
        r = self.first_of_type(dev)
        self.goto(r)
        verb = kind.lower()
        self.act(f"{verb} {o} with {r}", f"You {verb} the {o}")

    def find_lamp_use(self, lamp_type):
        for r in self.receptacles():
            if self.b.location != r:
                self.act(f"go to {r}", f"You arrive at {r}")
            lamps = [o for o in sorted(self.b.contents.get(r, ())) if o.split(" ")[0] == lamp_type]
            if lamps:
                self.act(f"use {lamps[0]}", "You turn on")
                return
        raise Abstain("lamp not found")


def holds(agent, atom):
    kind, T, X = atom
    b = agent.b
    if kind == "IN":
        return any(o.split(" ")[0] == T for o in agent.placed)
    if kind == "IN2":
        return sum(1 for o in agent.placed if o.split(" ")[0] == T) >= 2
    if kind in ("CLEAN", "HEAT", "COOL"):
        need = {"CLEAN": "clean", "HEAT": "hot", "COOL": "cool"}[kind]
        return any(o.split(" ")[0] == T and need in f for o, f in agent.flags.items())
    if kind == "HOLDING":
        return bool(b.holding) and b.holding.split(" ")[0] == T
    if kind == "LIT":
        return agent.lamp_on_at is not None and agent.lamp_on_at == b.location
    raise ValueError(kind)


def achieve(agent, atom):
    kind, T, X = atom
    if kind == "IN":
        o = agent.fetch(T, exclude=tuple(agent.placed))
        agent.place(o, X)
    elif kind == "IN2":
        while not holds(agent, atom):
            o = agent.fetch(T, exclude=tuple(agent.placed))
            agent.place(o, X)
    elif kind in ("CLEAN", "HEAT", "COOL"):
        o = agent.fetch(T)
        agent.treat(o, kind)
    elif kind == "HOLDING":
        agent.fetch(T)
    elif kind == "LIT":
        agent.find_lamp_use(T)


def run_priority(agent, order, max_rounds=8):
    """Priority controller (Mission 05): achieve the first violated atom; stop when all hold."""
    for _ in range(max_rounds):
        first = next((a for a in order if not holds(agent, a)), None)
        if first is None:
            return "claims done"
        achieve(agent, first)
    raise Abstain("no progress across rounds")


HTN_ORDER = {"IN": ["IN"], "IN2": ["IN2"], "CLEAN": ["CLEAN", "IN"], "HEAT": ["HEAT", "IN"], "COOL": ["COOL", "IN"],
             "HOLDING": ["HOLDING", "LIT"]}


def run_htn(agent, atoms):
    """B1: fixed method per goal form, the same macros, no contract reasoning (order written by hand)."""
    key = atoms[0][0]
    for kind in HTN_ORDER[key]:
        atom = next(a for a in atoms if a[0] == kind)
        try:
            achieve(agent, atom)
        except Abstain as e:
            if str(e) in ("budget exhausted", "search exhausted", "lamp not found") or str(e).startswith("no receptacle"):
                raise
    return "claims done"
