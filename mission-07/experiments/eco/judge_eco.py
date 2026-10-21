"""JUDGE SIDE for ECO (Mission 07): goal-class taxonomy, grounding test, witness pairs for restricted inexpressibility,
and goal-log checks. Nothing here is visible to an actor.

Goal classes are derived mechanically from a family specification before any experiment:
  OBS:<kind>          a visible object of the kind is in view / adjacent / carried (S0-expressible)
  NEED:<need>         a need variable above a level (S0-expressible)
  LATENT:<kind>.<var> an object of the kind has a latent value in a set (hidden state)
  PLACE:<kind>        the agent is adjacent to an object of the kind while that object is not visible (hidden place)
A class is S0-inexpressible (restricted to S0's language: predicates of the current observation and needs) iff a
witness pair exists: two histories from the same start state whose final observations (and needs) are identical but
which disagree on the class condition. `witness_*` constructs candidate pairs; `verify_witness` checks them by
simulation, so the [P]-level statement "no S0 goal identifies this class" rests on an exhibited, re-checkable pair.
"""

from __future__ import annotations

import itertools
import json

from eco_env import ACTIONS, EcoWorld

A = {a: i for i, a in enumerate(ACTIONS)}


# ---------------------------------------------------------------- taxonomy
def classes(fam):
    out = []
    for k, spec in fam["kinds"].items():
        out.append(("OBS", k))
        for v, d in spec.get("latent", {}).items():
            out.append(("LATENT", f"{k}.{v}"))
        if spec.get("visibility", "always") != "always":
            out.append(("PLACE", k))
    out += [("NEED", "food"), ("NEED", "water")]
    return out


def condition(world: EcoWorld, cls, arg=None):
    """Judge-side truth of a class condition in the current world state (arg selects the value set for LATENT)."""
    typ, name = cls
    if typ == "LATENT":
        kind, var = name.split(".")
        vals = arg if arg is not None else None
        for o in world.objs:
            if o.kind == kind and not o.carried:
                v = o.latent.get(var)
                if (vals is None and v not in (0, None)) or (vals is not None and v in vals):
                    return True
        return False
    if typ == "PLACE":
        for o in world.objs:
            if o.kind == name and not world.is_visible(o) and max(abs(o.x - world.ax), abs(o.y - world.ay)) <= 1:
                return True
        return False
    if typ == "OBS":
        if world.carried is not None and world.carried.kind == name:
            return True
        return any(o.kind == name and world.is_visible(o) and max(abs(o.x - world.ax), abs(o.y - world.ay)) <= 1
                   for o in world.objs if not o.carried)
    if typ == "NEED":
        return (world.food if name == "food" else world.water) >= (arg or 80)
    raise ValueError(cls)


def obs_key(obs):
    return json.dumps(obs, sort_keys=True)


# ---------------------------------------------------------------- witness pairs (restricted inexpressibility)
def run(world, actions):
    w = world.clone()
    obs = None
    for a in actions:
        obs = w.step(A[a])
    return w, obs


def face_toward(world, target):
    """Actions that walk the agent to a free cell next to `target` and turn to face it (BFS over free cells).
    Only for solid targets: the final move toward the target bumps and sets the facing. None if unreachable."""
    from collections import deque
    N = world.N
    occupied = {(o.x, o.y) for o in world.objs if not o.carried and world.fam["kinds"][o.kind].get("solid")}
    moves = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
    adjacent = {}
    for a, (dx, dy) in moves.items():               # standing at target - (dx, dy), action a faces the target
        adjacent[(target.x - dx, target.y - dy)] = a
    start = (world.ax, world.ay)
    prev = {start: None}
    q = deque([start])
    while q:
        c = q.popleft()
        if c in adjacent:
            path = []
            while prev[c] is not None:
                c, a = prev[c]
                path.append(a)
            end_cell = start
            for a in reversed(path):
                end_cell = (end_cell[0] + moves[a][0], end_cell[1] + moves[a][1])
            return path[::-1] + [adjacent[end_cell]]
        for a, (dx, dy) in moves.items():
            nx, ny = c[0] + dx, c[1] + dy
            if 0 <= nx < N and 0 <= ny < N and not world.wall[ny][nx] and (nx, ny) not in occupied and (nx, ny) not in prev:
                prev[(nx, ny)] = (c, a)
                q.append((nx, ny))
    return None


def witness_latent(world, kind, var, prefix_steps):
    """Pair: (approach object, POKE x prefix_steps, WAIT) vs (approach object, WAIT x prefix_steps, WAIT)."""
    for o in world.objs:
        if o.kind != kind or o.carried:
            continue
        path = face_toward(world, o)
        if path is None:
            continue
        h1 = path + ["POKE"] * prefix_steps + ["WAIT"]
        h2 = path + ["WAIT"] * prefix_steps + ["WAIT"]
        yield o.oid, h1, h2


def verify_witness(world, h1, h2, cls, arg=None):
    w1, o1 = run(world, h1)
    w2, o2 = run(world, h2)
    same_obs = obs_key(o1) == obs_key(o2)
    c1, c2 = condition(w1, cls, arg), condition(w2, cls, arg)
    return {"same_observation": same_obs, "condition": [c1, c2], "witness": same_obs and c1 != c2}


def witness_place(world, kind):
    """Pair of free cells with identical (visible) local views and needs, one adjacent to a hidden object of the kind."""
    N = world.N
    cells = [(x, y) for y in range(N) for x in range(N) if not world.wall[y][x] and not world.objs_at(x, y)]
    views = {}
    for (x, y) in cells:
        w = world.clone()
        w.ax, w.ay, w.feedback = x, y, 0
        key = obs_key(w.observe())
        views.setdefault(key, []).append((x, y, condition(w, ("PLACE", kind))))
    for key, lst in views.items():
        pos = [c for c in lst if c[2]]
        neg = [c for c in lst if not c[2]]
        if pos and neg:
            return {"witness": True, "cells": [pos[0][:2], neg[0][:2]]}
    return {"witness": False}


# ---------------------------------------------------------------- grounding test
def grounding(agent_values, judge_values):
    """Precision and recall of an agent predicate (list of bools) against a judge condition on the same probe states."""
    tp = sum(1 for a, j in zip(agent_values, judge_values) if a and j)
    fp = sum(1 for a, j in zip(agent_values, judge_values) if a and not j)
    fn = sum(1 for a, j in zip(agent_values, judge_values) if not a and j)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": prec, "recall": rec, "grounded": prec >= 0.9 and rec >= 0.9, "n": len(agent_values)}


# ---------------------------------------------------------------- goal-log checks
def check_goal_log(goal_log, action_log):
    """Each goal record must be written at a step <= the step of the first action that cites it."""
    first_act = {}
    for rec in action_log:
        g = rec.get("goal_id")
        if g is not None and g not in first_act:
            first_act[g] = rec["t"]
    bad = [g["goal_id"] for g in goal_log if g["goal_id"] in first_act and g["t_logged"] > first_act[g["goal_id"]]]
    return {"goals": len(goal_log), "late_records": bad, "ok": not bad}


# ---------------------------------------------------------------- bounded inexpressibility (exhaustive, [M])
def view_literals(obs):
    """Literals of S0's language for one observation: per view cell its (wall, kind, features) value; carried; needs bands."""
    lits = set()
    for i, row in enumerate(obs["view"]):
        for j, cell in enumerate(row):
            lits.add(("cell", i, j, json.dumps(cell)))
    lits.add(("carried", obs["carried"]))
    lits.add(("facing", obs["facing"]))
    return lits


def bounded_inexpressible(rows, k=3, thr=0.9):
    """rows: list of (literal set, condition bool). Search every conjunction of at most k literals; return the best
    (precision, recall) found and whether any reaches thr on both (then the class is expressible within the bound)."""
    pos = sum(1 for _, c in rows if c)
    if pos == 0:
        return {"positives": 0, "expressible_within_bound": None}
    lits = sorted({l for ls, _ in rows for l in ls})
    masks = {}
    for idx, (ls, _) in enumerate(rows):
        for l in ls:
            masks[l] = masks.get(l, 0) | (1 << idx)
    target = sum(1 << i for i, (_, c) in enumerate(rows) if c)
    # literals that cover no positive cannot help a conjunction with recall >= thr
    useful = [l for l in lits if bin(masks[l] & target).count("1") >= thr * pos]
    best = (0.0, 0.0)
    for r in range(1, k + 1):
        for combo in itertools.combinations(useful, r):
            m = masks[combo[0]]
            for l in combo[1:]:
                m &= masks[l]
            tp = bin(m & target).count("1")
            cov = bin(m).count("1")
            if cov == 0:
                continue
            prec, rec = tp / cov, tp / pos
            if (prec, rec) > best:
                best = (prec, rec)
            if prec >= thr and rec >= thr:
                return {"positives": pos, "rows": len(rows), "expressible_within_bound": True, "witness_conjunction": list(combo)}
    return {"positives": pos, "rows": len(rows), "expressible_within_bound": False, "best_precision_recall": best,
            "literals_searched": len(useful), "k": k}


def place_rows(world, kind):
    """One row per (free cell, facing): S0 literals at that pose and whether the agent is next to a hidden `kind`."""
    rows = []
    N = world.N
    for y in range(N):
        for x in range(N):
            if world.wall[y][x] or world.objs_at(x, y):
                continue
            for f in range(4):
                w = world.clone()
                w.ax, w.ay, w.facing, w.feedback = x, y, f, 0
                rows.append((view_literals(w.observe()), condition(w, ("PLACE", kind))))
    return rows
