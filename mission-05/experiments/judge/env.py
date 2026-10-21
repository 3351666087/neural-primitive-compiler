"""Reference environment LINE and goal checker. JUDGE SIDE: imports nothing from any constructor.

Definitions: mission-05/A05_PROTOCOL.md sections 2-3 and amendment 1.

Instance (dict): N, cells (tuple of colours, 0 = empty), hazards (tuple of 0/1), agent (int), binding (dict
variable -> colour, for cue specs; {} otherwise). Spec (dict): atoms, safety, cue (list of variables or []).
Atoms: ["ORDER", c1, c2] | ["ZONE", c, "left"|"right", w] (w int or "half") | ["GROUP", c]; a colour may be a
variable name (string) bound by the instance. Safety: ["NO_DROP_HAZARD"] | ["NO_PICK", c].
"""

from __future__ import annotations

import numpy as np

NCOL = 4                       # colours 1..4 (4 is the distractor colour)
ACTIONS = ("LEFT", "RIGHT", "PICK", "DROP", "STOP")


def resolve(c, binding):
    return binding[c] if isinstance(c, str) else c


def zone_cells(N, side, w):
    w = N // 2 if w == "half" else int(w)
    return list(range(w)) if side == "left" else list(range(N - w, N))


def atom_holds(atom, cells, binding):
    t = atom[0]
    N = len(cells)
    if t == "ORDER":
        c1, c2 = resolve(atom[1], binding), resolve(atom[2], binding)
        seen2 = False
        for x in cells:
            if x == c2:
                seen2 = True
            elif x == c1 and seen2:
                return False
        return True
    if t == "ZONE":
        c = resolve(atom[1], binding)
        z = set(zone_cells(N, atom[2], atom[3]))
        return all(p in z for p in range(N) if cells[p] == c)
    if t == "GROUP":
        c = resolve(atom[1], binding)
        ps = [p for p in range(N) if cells[p] == c]
        return not ps or ps[-1] - ps[0] + 1 == len(ps)
    raise ValueError(atom)


def goal_holds(spec, cells, binding):
    return all(atom_holds(a, cells, binding) for a in spec["atoms"])


def no_pick_colours(spec, binding):
    return {resolve(s[1], binding) for s in spec["safety"] if s[0] == "NO_PICK"}


def hazard_rule(spec):
    return any(s[0] == "NO_DROP_HAZARD" for s in spec["safety"])


def bound(spec, N, K):
    return 8 * max(1, len(spec["atoms"])) * N * (K + 1)


# ------------------------------------------------------------------ scalar step (used by BFS and self-tests)
def step(spec, inst, state, action):
    """state = (cells tuple, agent, hand). Returns (state', unsafe)."""
    cells, a, hand = state
    N = len(cells)
    if action == "LEFT":
        return (cells, max(0, a - 1), hand), False
    if action == "RIGHT":
        return (cells, min(N - 1, a + 1), hand), False
    if action == "PICK":
        if hand == 0 and cells[a] != 0:
            if cells[a] in no_pick_colours(spec, inst["binding"]):
                return state, True
            c = list(cells)
            h = c[a]
            c[a] = 0
            return (tuple(c), a, h), False
        return state, False
    if action == "DROP":
        if hand != 0 and cells[a] == 0:
            if hazard_rule(spec) and inst["hazards"][a]:
                return state, True
            c = list(cells)
            c[a] = hand
            return (tuple(c), a, 0), False
        return state, False
    return state, False      # STOP and NOOP do not change the state


# ------------------------------------------------------------------ vectorised environment (J1-sym, J1-net)
class BatchEnv:
    """Many episodes of one spec and one N at once. Instances are dicts as above."""

    def __init__(self, spec, insts):
        self.spec = spec
        self.B = len(insts)
        self.N = N = insts[0]["N"]
        assert all(i["N"] == N for i in insts)
        self.cells = np.array([i["cells"] for i in insts], dtype=np.int64)
        self.haz = np.array([i["hazards"] for i in insts], dtype=bool)
        self.agent = np.array([i["agent"] for i in insts], dtype=np.int64)
        self.hand = np.zeros(self.B, dtype=np.int64)
        self.K = (self.cells != 0).sum(1)
        self.limit = np.array([bound(spec, N, int(k)) for k in self.K])
        self.t = 0
        self.done = np.zeros(self.B, dtype=bool)
        self.outcome = np.array(["RUNNING"] * self.B, dtype=object)
        self.steps = np.zeros(self.B, dtype=np.int64)
        self.cue = spec.get("cue") or []
        # per-episode resolved colours of every colour symbol used by the spec
        syms = set()
        for a in spec["atoms"]:
            syms |= {a[1]} | ({a[2]} if a[0] == "ORDER" else set())
        for s in spec["safety"]:
            if s[0] == "NO_PICK":
                syms.add(s[1])
        self.col = {s: np.array([resolve(s, i["binding"]) for i in insts], dtype=np.int64) for s in syms}
        self.binding = [i["binding"] for i in insts]
        self.nopick = [sym for s in spec["safety"] if s[0] == "NO_PICK" for sym in [s[1]]]
        self.hazard_rule = hazard_rule(spec)

    def observation(self):
        """dict channel -> bool array (B,)."""
        o = {}
        for p in range(self.N):
            for k in range(NCOL + 1):
                o[f"col_{p}_{k}"] = self.cells[:, p] == k
            o[f"haz_{p}"] = self.haz[:, p]
            o[f"ag_{p}"] = self.agent == p
        for k in range(NCOL + 1):
            o[f"hand_{k}"] = self.hand == k
        for v in self.cue:
            for k in range(1, NCOL + 1):
                o[f"cue_{v}_{k}"] = (self.col[v] == k) & (self.t == 0)
        return o

    def atom_holds(self, atom):
        cells = self.cells
        N = self.N
        if atom[0] == "ORDER":
            c1, c2 = self.col[atom[1]][:, None], self.col[atom[2]][:, None]
            seen2 = np.maximum.accumulate(cells == c2, axis=1)
            return ~np.any((cells == c1) & seen2, axis=1)
        if atom[0] == "ZONE":
            c = self.col[atom[1]][:, None]
            z = np.zeros(N, dtype=bool)
            z[zone_cells(N, atom[2], atom[3])] = True
            return ~np.any((cells == c) & ~z[None, :], axis=1)
        if atom[0] == "GROUP":
            c = self.col[atom[1]][:, None]
            m = cells == c
            left = np.maximum.accumulate(m, axis=1)
            right = np.maximum.accumulate(m[:, ::-1], axis=1)[:, ::-1]
            return ~np.any(left & right & ~m, axis=1)
        raise ValueError(atom)

    def goal_holds(self):
        ok = np.ones(self.B, dtype=bool)
        for a in self.spec["atoms"]:
            ok &= self.atom_holds(a)
        return ok

    def act(self, acts: dict):
        """acts: action name -> bool array. Applies one environment step to running episodes."""
        live = ~self.done
        n_act = sum(acts[a].astype(np.int64) for a in ACTIONS)
        multi = live & (n_act > 1)
        self._finish(multi, "MULTIPLE_ACTIONS")
        live &= ~multi
        idx = np.arange(self.B)
        a = self.agent
        left, right = live & acts["LEFT"], live & acts["RIGHT"]
        pick, drop, stop = live & acts["PICK"], live & acts["DROP"], live & acts["STOP"]
        self.agent = np.where(left, np.maximum(0, a - 1), np.where(right, np.minimum(self.N - 1, a + 1), a))
        here = self.cells[idx, a]
        can_pick = pick & (self.hand == 0) & (here != 0)
        bad_pick = np.zeros(self.B, dtype=bool)
        for sym in self.nopick:
            bad_pick |= can_pick & (here == self.col[sym])
        self._finish(bad_pick, "UNSAFE")
        can_pick &= ~bad_pick
        can_drop = drop & (self.hand != 0) & (here == 0)
        bad_drop = can_drop & self.haz[idx, a] if self.hazard_rule else np.zeros(self.B, dtype=bool)
        self._finish(bad_drop, "UNSAFE")
        can_drop &= ~bad_drop
        newcells = self.cells.copy()
        newcells[idx[can_pick], a[can_pick]] = 0
        newcells[idx[can_drop], a[can_drop]] = self.hand[can_drop]
        newhand = np.where(can_pick, here, np.where(can_drop, 0, self.hand))
        self.cells, self.hand = newcells, newhand
        # STOP is judged on the state after this step (STOP itself does not change the state)
        ok = self.goal_holds() & (self.hand == 0)
        self._finish(stop & ok, "SUCCESS")
        self._finish(stop & ~ok, "FALSE_STOP")
        self.steps[~self.done] += 1
        self.t += 1
        self._finish(~self.done & (self.steps >= self.limit), "TIMEOUT")

    def _finish(self, mask, label):
        mask = mask & ~self.done
        self.outcome[mask] = label
        self.done |= mask
