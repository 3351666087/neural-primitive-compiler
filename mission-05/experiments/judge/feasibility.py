"""Exact feasibility of a goal on an instance (amendment 1, item 2). JUDGE SIDE.

Reachability lemma: the agent walks over every cell, PICK empties a cell, DROP needs an empty allowed cell. If the
number of allowed cells (not a hazard under NO_DROP_HAZARD, not holding a NO_PICK object) exceeds the number of
movable objects, every placement of the movable objects on allowed cells is reachable (move objects one at a time
through the spare cell); otherwise no object can ever change cell. So:
  feasible  <=>  goal holds initially  or  (a spare allowed cell exists and some placement satisfies the goal).
The placement search is an exact backtracking over cells left to right. `bfs_feasible` is the brute-force
cross-check (used in self-tests only).
"""

from __future__ import annotations

from collections import deque
from functools import lru_cache

from env import ACTIONS, goal_holds, hazard_rule, no_pick_colours, resolve, step, zone_cells


def _layout(spec, inst):
    N, cells, b = inst["N"], inst["cells"], inst["binding"]
    fixed_cols = no_pick_colours(spec, b)
    fixed = {p: c for p, c in enumerate(cells) if c in fixed_cols}
    haz = inst["hazards"] if hazard_rule(spec) else (0,) * N
    allowed = [p for p in range(N) if p not in fixed and not haz[p]]
    movable = [c for p, c in enumerate(cells) if c != 0 and p not in fixed]
    return N, fixed, allowed, movable


def satisfiable(spec, inst):
    """Does some placement of the movable objects on allowed cells (fixed objects in place) satisfy every atom?"""
    N, fixed, allowed, movable = _layout(spec, inst)
    b = inst["binding"]
    atoms = [[a[0]] + [resolve(x, b) if i in (1, 2) and not (a[0] == "ZONE" and i == 2) else x
                       for i, x in enumerate(a[1:], start=1)] for a in spec["atoms"]]
    zones = {i: set(zone_cells(N, a[2], a[3])) for i, a in enumerate(atoms) if a[0] == "ZONE"}
    colours = sorted(set(movable))
    allowed_set = set(allowed)
    init_counts = tuple(movable.count(c) for c in colours)

    def place_ok(flags, p, c):
        """c = colour placed at p (0 = empty). Returns new flags or None."""
        new = list(flags)
        for i, a in enumerate(atoms):
            if a[0] == "ORDER":
                if c == a[2]:
                    new[i] = 1
                elif c == a[1] and flags[i]:
                    return None
            elif a[0] == "ZONE":
                if c == a[1] and p not in zones[i]:
                    return None
            elif a[0] == "GROUP":
                if c == a[1]:
                    if flags[i] == 2:
                        return None
                    new[i] = 1
                elif flags[i] == 1:
                    new[i] = 2
        return tuple(new)

    @lru_cache(maxsize=None)
    def go(p, counts, flags):
        if p == N:
            return all(x == 0 for x in counts)
        if sum(counts) > sum(1 for q in range(p, N) if q in allowed_set):
            return False
        if p in fixed:
            nf = place_ok(flags, p, fixed[p])
            return nf is not None and go(p + 1, counts, nf)
        options = [0] if p not in allowed_set else [0] + [c for c, n in zip(colours, counts) if n > 0]
        for c in options:
            nf = place_ok(flags, p, c)
            if nf is None:
                continue
            nc = counts if c == 0 else tuple(n - (1 if col == c else 0) for col, n in zip(colours, counts))
            if go(p + 1, nc, nf):
                return True
        return False

    return go(0, init_counts, tuple(0 for _ in atoms))


def feasible(spec, inst):
    if goal_holds(spec, inst["cells"], inst["binding"]):
        return True
    N, fixed, allowed, movable = _layout(spec, inst)
    return len(allowed) > len(movable) and satisfiable(spec, inst)


def bfs_feasible(spec, inst, max_states=2_000_000):
    """Brute force over (cells, agent, hand); success = goal holds with an empty hand. None = budget exhausted."""
    start = (tuple(inst["cells"]), inst["agent"], 0)
    seen = {start}
    q = deque([start])
    while q:
        s = q.popleft()
        if s[2] == 0 and goal_holds(spec, s[0], inst["binding"]):
            return True
        for a in ACTIONS[:4]:
            s2, unsafe = step(spec, inst, s, a)
            if unsafe or s2 in seen:
                continue
            seen.add(s2)
            if len(seen) > max_states:
                return None
            q.append(s2)
    return False
