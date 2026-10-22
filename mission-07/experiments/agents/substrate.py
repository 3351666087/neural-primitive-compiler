"""Shared agent substrate for Mission 07 (PROTOCOL.md section 3). CONSTRUCTOR / AGENT SIDE: imports nothing from
the judge or the environment; sees only legal observations.

Designer knowledge provided here to every arm (KNOWLEDGE_PROVENANCE.md section 2):
  - observation layout (5x5 view of (wall, kind id, visible features), facing, carried, needs, feedback code);
  - direct action semantics (moves change the cell only when free; a blocked move only turns; POKE / PICK / CONSUME act
    on the facing cell, CONSUME also on the carried object);
  - dead reckoning: the pose is integrated from 'moved' feedback; a jump of both needs to 100 without a consume is read
    as a life reset and starts a new frame (the pose is unknown after it);
  - objects are identified by (frame, cell) because objects do not move unless carried (an assumption, accounted);
  - a planner (BFS over (cell, facing)) and frontier exploration.
Nothing about mechanisms, latent variables or which kinds are food or water is given: those are learned.
"""

from __future__ import annotations

import json
import random
from collections import Counter, deque

ACTIONS = ("N", "E", "S", "W", "POKE", "PICK", "DROP", "CONSUME", "WAIT")
A = {a: i for i, a in enumerate(ACTIONS)}
DIRS = ((0, -1), (1, 0), (0, 1), (-1, 0))
FB = {0: "none", 1: "moved", 2: "bumped", 3: "poked", 4: "picked", 5: "dropped", 6: "consumed"}
R = 2


class Memory:
    """Per-life map and object instances, plus the agent's episodic event log (persists across lives)."""

    def __init__(self):
        self.frame = 0
        self.pos = (0, 0)
        self.cells = {}            # (frame, x, y) -> (wall, kind, feat, t_seen)
        self.events = []           # episodic memory: dicts
        self.t = 0
        self.prev_needs = (100, 100)
        self.prev_carried = 0
        self.poses = []            # (t, frame, x, y) per step, for testability of predictions
        self.solid = Counter()     # kind -> times a move into it was blocked (learned solidity)
        self.passed = Counter()    # kind -> times the agent stood on it

    def key(self, x, y):
        return (self.frame, x, y)

    def cell(self, x, y):
        return self.cells.get(self.key(x, y))

    def is_solid(self, kind):
        return self.solid[kind] > self.passed[kind]

    def observe(self, obs, last_action):
        """Update pose, map and events from one observation (called after every step)."""
        self.t += 1
        fb = FB[obs["feedback"]]
        needs = tuple(obs["needs"])
        reset = needs == (100, 100) and self.prev_needs != (100, 100) and fb != "consumed"
        if reset:
            self.frame += 1
            self.pos = (0, 0)
            self.events.append({"t": self.t, "type": "reset", "frame": self.frame})
        elif fb == "moved":
            dx, dy = DIRS[obs["facing"]]
            self.pos = (self.pos[0] + dx, self.pos[1] + dy)
        elif fb == "bumped" and last_action in ("N", "E", "S", "W"):
            dx, dy = DIRS[obs["facing"]]
            c = self.cell(self.pos[0] + dx, self.pos[1] + dy)
            if c and c[1]:
                self.solid[c[1]] += 1
        pre = self.cell(*self.facing_cell(obs["facing"])) if not reset else None     # facing cell before this update
        x0, y0 = self.pos
        for i, row in enumerate(obs["view"]):
            for j, (wall, kind, feat) in enumerate(row):
                x, y = x0 + j - R, y0 + i - R
                k = self.key(x, y)
                old = self.cells.get(k)
                if not reset and old is not None and old[1] != kind and (x, y) != self.pos:
                    if kind and not old[1] and not (fb == "dropped" and (x, y) == self.facing_cell(obs["facing"])):
                        self.events.append({"t": self.t, "type": "appear", "frame": self.frame, "cell": (x, y), "kind": kind,
                                            "gap": self.t - old[3]})
                    elif old[1] and not kind and not (fb in ("picked", "consumed") and (x, y) == self.facing_cell(obs["facing"])):
                        self.events.append({"t": self.t, "type": "vanish", "frame": self.frame, "cell": (x, y), "kind": old[1],
                                            "gap": self.t - old[3]})
                elif not reset and old is not None and old[1] == kind and kind and old[2] != feat:
                    self.events.append({"t": self.t, "type": "feat", "frame": self.frame, "cell": (x, y), "kind": kind,
                                        "old": list(old[2]), "new": list(feat), "gap": self.t - old[3]})
                self.cells[k] = (wall, kind, feat, self.t)
        self.poses.append((self.t, self.frame, self.pos[0], self.pos[1]))
        here = obs["view"][R][R]
        if here[1]:
            self.passed[here[1]] += 1
        if last_action in ("POKE", "PICK", "CONSUME", "DROP") and fb in ("poked", "picked", "consumed", "dropped"):
            fx, fy = self.facing_cell(obs["facing"])
            if fb == "consumed" and self.prev_carried:
                kind = self.prev_carried
            elif fb == "dropped":
                kind = self.prev_carried
            else:
                kind = pre[1] if pre else 0
            self.events.append({"t": self.t, "type": {"poked": "poke", "picked": "pick", "dropped": "drop", "consumed": "consume"}[fb],
                                "frame": self.frame,
                                "cell": (fx, fy), "kind": kind, "needs_before": self.prev_needs, "needs_after": needs})
        elif last_action in ("POKE", "PICK", "CONSUME") and fb == "none":
            fx, fy = self.facing_cell(obs["facing"])
            self.events.append({"t": self.t, "type": "fail_" + last_action.lower(), "frame": self.frame, "cell": (fx, fy),
                                "kind": pre[1] if pre else 0})
        self.prev_needs = needs
        self.prev_carried = obs["carried"]

    def facing_cell(self, facing):
        dx, dy = DIRS[facing]
        return self.pos[0] + dx, self.pos[1] + dy

    def instances(self, kind=None):
        """Known object instances in the current frame: (x, y) -> kind."""
        out = {}
        for (f, x, y), (wall, k, feat, ts) in self.cells.items():
            if f == self.frame and k and (kind is None or k == kind):
                out[(x, y)] = k
        return out

    def passable(self, x, y):
        c = self.cell(x, y)
        if c is None:
            return True                                    # unknown: optimistic
        wall, kind = c[0], c[1]
        return not wall and not (kind and self.is_solid(kind))


def plan_to_face(mem: Memory, facing: int, target, max_nodes=4000):
    """Shortest action list ending adjacent to `target` and facing it (BFS over (cell, facing))."""
    start = (mem.pos[0], mem.pos[1], facing)
    goal_cells = {(target[0] - dx, target[1] - dy): d for d, (dx, dy) in enumerate(DIRS)}
    if (start[0], start[1]) in goal_cells and goal_cells[(start[0], start[1])] == facing:
        return []
    prev = {start: None}
    q = deque([start])
    n = 0
    while q and n < max_nodes:
        s = q.popleft()
        n += 1
        x, y, f = s
        for d, (dx, dy) in enumerate(DIRS):
            nx, ny = x + dx, y + dy
            if (nx, ny) == tuple(target):
                ns = (x, y, d)                             # a move toward the target: turns (target solid) or enters it
                if mem.passable(nx, ny):
                    ns = (nx, ny, d)
            elif mem.passable(nx, ny):
                ns = (nx, ny, d)
            else:
                ns = (x, y, d)
            if ns in prev:
                continue
            prev[ns] = (s, ACTIONS[d])
            if (ns[0], ns[1]) in goal_cells and goal_cells[(ns[0], ns[1])] == ns[2]:
                path = []
                while prev[ns] is not None:
                    ns, a = prev[ns]
                    path.append(a)
                return path[::-1]
            q.append(ns)
    return None


def frontier_step(mem: Memory, facing: int, rng: random.Random):
    """One step toward the nearest unknown cell (frontier exploration); random move if none is reachable."""
    start = mem.pos
    prev = {start: None}
    q = deque([start])
    while q:
        c = q.popleft()
        if mem.cell(*c) is None:
            path = []
            while prev[c] is not None:
                c, a = prev[c]
                path.append(a)
            return path[-1] if path else rng.choice("NESW")
        for d, (dx, dy) in enumerate(DIRS):
            n = (c[0] + dx, c[1] + dy)
            if n not in prev and mem.passable(*n) and len(prev) < 3000:
                prev[n] = (c, ACTIONS[d])
                q.append(n)
    # everything known: wander toward the least recently seen cell
    cells = [(ts, (x, y)) for (f, x, y), (w, k, feat, ts) in mem.cells.items() if f == mem.frame and not w and not k]
    if cells:
        _, tgt = min(cells)
        p = plan_to_face(mem, facing, tgt)
        if p:
            return p[0]
    return rng.choice("NESW")


class Logs:
    """Agent-side logs (PROTOCOL.md section 5). Written to JSONL by the harness."""

    def __init__(self):
        self.goals, self.actions, self.structures, self.deletions = [], [], [], []

    def goal(self, t, formula, provenance, priority, reason, predicted, evidence, parent=None):
        gid = len(self.goals)
        self.goals.append({"goal_id": gid, "t_logged": t, "formula": formula, "provenance": provenance, "priority": priority,
                           "reason": reason, "predicted": predicted, "evidence": evidence, "parent_goal": parent})
        return gid

    def dump(self):
        return {"goals": self.goals, "actions": self.actions, "structures": self.structures, "deletions": self.deletions}


def obs_digest(obs):
    return json.dumps([obs["view"], obs["carried"]], separators=(",", ":"))
