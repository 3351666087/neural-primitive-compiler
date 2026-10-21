"""Belief from ALFWorld text observations, and the applicability judgements of P-ALF-1 (Mission 06, G1-A.2).
CONSTRUCTOR SIDE: a pure function of the text observations the agent has seen; imports no environment package and
reads no data file.

Designer knowledge used here (KNOWLEDGE_PROVENANCE.md): the wording of ALFWorld observations ("You arrive at r.",
"On the r, you see ...", "The r is closed.", "You open the r. The r is open. In it, you see ...", "You pick up the o
from the r.", "You move the o to the r.", ...), the action semantics of the text game (go to any listed receptacle
other than the current one; open / close only at a closed / open receptacle; take only at the receptacle, with an empty
hand, from an open or non-openable receptacle that holds the object; move / heat / cool / clean only while holding the
object at the target receptacle; use a lamp only where it is visible), and the goal sentence patterns.
"""

from __future__ import annotations

import re

APPLICABLE, NOT_APPLICABLE, UNKNOWN = "A", "N", "U"
_LIST = re.compile(r"(?:you see|In it, you see) (.*?)\.(?:\s|$)")
_NAME = re.compile(r"^(?:a|an|some|the)\s+")


def _items(txt):
    txt = txt.strip()
    if txt.startswith("nothing"):
        return []
    parts = re.split(r",\s*(?:and\s+)?|\s+and\s+", txt)
    return [_NAME.sub("", p.strip()) for p in parts if p.strip()]


class Belief:
    def __init__(self):
        self.receptacles = set()
        self.location = None
        self.state = {}            # receptacle -> "open" | "closed" | "plain" (not openable)
        self.contents = {}         # receptacle -> set of objects (as last observed, updated by own actions)
        self.holding = None        # object name, None (empty hand: the game starts with an empty hand)
        self.goal = None

    def update(self, action, obs):
        """action: the command that produced obs (None for the first observation)."""
        o = obs.replace("\n", " ")
        if action is None:
            m = re.search(r"Looking quickly around you, you see (.*?)\.\s", o + " ")
            if m:
                self.receptacles |= set(_items(m.group(1)))
            g = re.search(r"Your task is to: (.*?)\.?\s*$", o.strip())
            self.goal = g.group(1).strip() if g else None
            return
        m = re.search(r"You arrive at (.*?)\.", o)
        if m:
            r = m.group(1)
            self.location = r
            self.receptacles.add(r)
            if re.search(rf"The {re.escape(r)} is closed\.", o):
                self.state[r] = "closed"
            elif re.search(rf"The {re.escape(r)} is open\.", o):
                self.state[r] = "open"
            else:
                self.state.setdefault(r, "plain")
        m = re.search(r"You open the (.*?)\.", o)
        if m:
            self.state[m.group(1)] = "open"
        m = re.search(r"You close the (.*?)\.", o)
        if m:
            self.state[m.group(1)] = "closed"
        if self.location and ("you see" in o) and ("Looking quickly" not in o):
            lm = _LIST.search(o)
            if lm:
                self.contents[self.location] = set(_items(lm.group(1)))
        m = re.search(r"You pick up the (.*?) from the (.*?)\.", o)
        if m:
            self.holding = m.group(1)
            self.contents.setdefault(m.group(2), set()).discard(m.group(1))
        m = re.search(r"You (?:move|put) the (.*?) (?:to|in|on) the (.*?)\.", o)
        if m:
            self.holding = None
            self.contents.setdefault(m.group(2), set()).add(m.group(1))


def belief_after(history):
    """history: [(None, first_obs), (action_1, obs_1), ...]"""
    b = Belief()
    for a, o in history:
        b.update(a, o)
    return b


def applicable(b: Belief, cmd: str) -> str:
    m = re.match(r"go to (.+)$", cmd)
    if m:
        r = m.group(1)
        if r == b.location:
            return NOT_APPLICABLE
        return APPLICABLE if r in b.receptacles else UNKNOWN
    m = re.match(r"(open|close) (.+)$", cmd)
    if m:
        r = m.group(2)
        if r != b.location:
            return NOT_APPLICABLE
        st = b.state.get(r)
        if st is None:
            return UNKNOWN
        want = "closed" if m.group(1) == "open" else "open"
        return APPLICABLE if st == want else NOT_APPLICABLE
    m = re.match(r"take (.+) from (.+)$", cmd)
    if m:
        o, r = m.group(1), m.group(2)
        if r != b.location or b.holding is not None:
            return NOT_APPLICABLE
        if b.state.get(r) == "closed":
            return NOT_APPLICABLE
        if r not in b.contents:
            return UNKNOWN
        return APPLICABLE if o in b.contents[r] else NOT_APPLICABLE
    m = re.match(r"(?:move|put) (.+) (?:to|in|on|in/on) (.+)$", cmd)
    if m:
        o, r = m.group(1), m.group(2)
        if r != b.location or b.holding != o or b.state.get(r) == "closed":
            return NOT_APPLICABLE
        return APPLICABLE
    m = re.match(r"(heat|cool|clean) (.+) with (.+)$", cmd)
    if m:
        o, r = m.group(2), m.group(3)
        return APPLICABLE if (r == b.location and b.holding == o) else NOT_APPLICABLE
    m = re.match(r"use (.+)$", cmd)
    if m:
        lamp = m.group(1)
        if b.location is None or b.location not in b.contents:
            return UNKNOWN
        return APPLICABLE if lamp in b.contents[b.location] else NOT_APPLICABLE
    return UNKNOWN


GOAL_PATTERNS = (r"put (?:a|an|some) (?:clean |hot |cool )?(\w+) (?:in|on|in/on) ",
                 r"(?:clean|heat|cool) (?:a|an|some) (\w+) and put it",
                 r"put two (\w+) (?:in|on|in/on) ", r"find two (\w+) and put them",
                 r"look at (?:a|an|some|the) (\w+) under", r"examine (?:a|an|some|the) (\w+) with")


def goal_object_type(goal):
    for p in GOAL_PATTERNS:
        m = re.search(p, goal or "")
        if m:
            return m.group(1)
    return None


def known_locations(b: Belief, otype: str):
    """[(object, receptacle)] for observed instances of the type ("apple" matches "apple 1")."""
    out = []
    for r, objs in b.contents.items():
        for o in objs:
            if o.split(" ")[0] == otype:
                out.append((o, r))
    if b.holding and b.holding.split(" ")[0] == otype:
        out.append((b.holding, "<hand>"))
    return out
