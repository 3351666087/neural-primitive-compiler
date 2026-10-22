"""Learner positive control (JUDGE SIDE harness; amendment A3). Gate 2 checked that alpha's true structures ground
and that the executor can use them, but not that the shared learner can recover them from informative data. Here a
scripted teacher (designer knowledge: it navigates with the judge's object positions) performs varied experiments in
alpha; the observations go through the agent-side Memory exactly as for an agent, and the shared learner fits that
memory. The fitted structures are then grounded with the judge's probes.

The teacher stands on the side of the target whose view covers the most cells where effects can appear (designer
knowledge used only to make the data informative). Teacher schedule, cycling over all stones and lamps (world seed s, 12,000 steps; when food or water is below 50 it
first eats or drinks the nearest visible source, which also frees space for new fruit):
  stone: n in {2, 3, 4, 5} pokes at spacing in {1, 10, 20, 30, 40}, then 8 WAITs
  lamp : charge a stone within 1 of it with 1, 2 or 3 consecutive pokes (in turn), poke the lamp, 3 WAITs, poke the lamp, 8 WAITs
         (every second visit to each lamp skips the charging, as a contrast)
  python3 -I g3_learner_control.py SEED [SEED ...]       # prints JSON; writes g3_learner_control.json
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AGENTS = HERE.parent / "agents"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(AGENTS))
import ground_eco as G  # noqa: E402
import judge_eco as JE  # noqa: E402
from eco_env import EcoWorld, load_family  # noqa: E402
from structures import Learner  # noqa: E402
from substrate import Memory  # noqa: E402

FAM = HERE / "family_alpha.json"
STEPS = 12000


def walk_face(w, target):
    """Path to the free cell next to `target` whose 5x5 view covers the most cells where an effect can appear (free
    cells within 1 of a tree, spring cells) within distance 3 of the target, then the move that faces the target."""
    from collections import deque
    N = w.N
    occupied = {(o.x, o.y) for o in w.objs if not o.carried and w.fam["kinds"][o.kind].get("solid")}
    trees = [(o.x, o.y) for o in w.objs if o.kind == "tree"]
    hot = {(x, y) for y in range(N) for x in range(N) if not w.wall[y][x] and (x, y) not in occupied
           and max(abs(x - target.x), abs(y - target.y)) <= 3
           and (any(max(abs(x - a), abs(y - b)) <= 1 for a, b in trees) or any(o.kind == "spring" and (o.x, o.y) == (x, y) for o in w.objs))}
    moves = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}
    stands = {}
    for a, (dx, dy) in moves.items():
        c = (target.x - dx, target.y - dy)
        if 0 <= c[0] < N and 0 <= c[1] < N and not w.wall[c[1]][c[0]] and c not in occupied:
            stands[c] = (a, sum(1 for h in hot if max(abs(h[0] - c[0]), abs(h[1] - c[1])) <= 2))
    if not stands:
        return None
    start = (w.ax, w.ay)
    prev = {start: None}
    q = deque([start])
    while q:
        c = q.popleft()
        for a, (dx, dy) in moves.items():
            n = (c[0] + dx, c[1] + dy)
            if 0 <= n[0] < N and 0 <= n[1] < N and not w.wall[n[1]][n[0]] and n not in occupied and n not in prev:
                prev[n] = (c, a)
                q.append(n)
    reach = [c for c in stands if c in prev]
    if not reach:
        return None
    best = max(reach, key=lambda c: (stands[c][1], -sum(1 for _ in range(0))))
    path = []
    c = best
    while prev[c] is not None:
        c, a = prev[c]
        path.append(a)
    return path[::-1] + [stands[best][0]]


def face_any(w, target):
    """Shortest action list ending next to `target` and facing it (BFS over (cell, facing); works for non-solid
    targets, which can only be faced by stepping toward them from two cells away)."""
    from collections import deque
    N = w.N
    occupied = {(o.x, o.y) for o in w.objs if not o.carried and w.fam["kinds"][o.kind].get("solid")}
    dirs = [("N", (0, -1)), ("E", (1, 0)), ("S", (0, 1)), ("W", (-1, 0))]
    start = (w.ax, w.ay, w.facing)
    prev = {start: None}
    q = deque([start])
    while q:
        st = q.popleft()
        x, y, f = st
        if (x + dirs[f][1][0], y + dirs[f][1][1]) == (target.x, target.y):
            path = []
            while prev[st] is not None:
                st, a = prev[st]
                path.append(a)
            return path[::-1]
        for d, (a, (dx, dy)) in enumerate(dirs):
            nx, ny = x + dx, y + dy
            free = 0 <= nx < N and 0 <= ny < N and not w.wall[ny][nx] and (nx, ny) not in occupied
            ns = (nx, ny, d) if free and (nx, ny) != (target.x, target.y) else (x, y, d)
            if free and (nx, ny) == (target.x, target.y):
                continue                                   # stepping onto the target does not face it
            if ns not in prev:
                prev[ns] = (st, a)
                q.append(ns)
    return None


def teacher_memory(fam, seed, steps=STEPS):
    w = EcoWorld(fam, seed)
    mem = Memory()
    rng = random.Random(seed)
    obs = w.observe()
    mem.observe(obs, "WAIT")
    last = "WAIT"
    queue = []
    trial = 0
    visits = {}

    def plan_trial():
        nonlocal trial
        for need, kinds in ((w.food, ("fruit",)), (w.water, ("puddle", "spring"))):
            if need < 50:                                   # eat, so that consumed fruit frees space near the trees
                srcs = [o for o in w.objs if o.kind in kinds and not o.carried and w.is_visible(o) and o.cooldown <= 0]
                srcs.sort(key=lambda o: max(abs(o.x - w.ax), abs(o.y - w.ay)))
                for o in srcs[:3]:
                    path = face_any(w, o)
                    if path is not None:
                        return path + ["CONSUME"]
        trial += 1
        targets = [o for o in w.objs if o.kind in ("stone", "lamp") and not o.carried]
        o = targets[trial % len(targets)]
        path = walk_face(w, o)
        if path is None:
            return ["WAIT"]
        if o.kind == "stone":
            n, sp = rng.choice((2, 3, 4, 5)), rng.choice((1, 10, 20, 30, 40))
            acts = []
            for i in range(n):
                acts += ["POKE"] + ["WAIT"] * (sp - 1 if i < n - 1 else 0)
            return path + acts + ["WAIT"] * 8
        acts = []
        visits[o.oid] = visits.get(o.oid, 0) + 1
        if visits[o.oid] % 2 == 0:                          # alternate charged and uncharged visits per lamp
            for s in w.objs:
                if s.kind == "stone" and w.cheb(s, o) <= 1:
                    p2 = walk_face(w, s)
                    if p2 is not None:
                        n = 1 + (visits[o.oid] // 2) % 3            # charge levels 1, 2, 3 in turn
                        return p2 + ["POKE"] * n + ["@lamp", o.oid]
        return path + ["POKE", "WAIT", "WAIT", "WAIT", "POKE"] + ["WAIT"] * 8

    t = 0
    while t < steps:
        if not queue:
            queue = plan_trial()
        a = queue.pop(0)
        if a == "@lamp":                                   # re-plan the lamp approach from the current position
            oid = queue.pop(0)
            o = next(x for x in w.objs if x.oid == oid)
            path = walk_face(w, o) or []
            queue = path + ["POKE", "WAIT", "WAIT", "WAIT", "POKE"] + ["WAIT"] * 8
            continue
        obs = w.step(JE.A[a])
        mem.observe(obs, a)
        last = a
        t += 1
    return mem, w


def main(seeds):
    fam = load_family(FAM)
    probes, classes = G.make_probes(fam)
    out = {}
    for seed in seeds:
        mem, w = teacher_memory(fam, seed)
        lr = Learner()
        structs = {}
        for _ in range(3):                                  # M2 can use an M1 found in an earlier pass
            for s in lr.fit(mem, structs, mem.t):
                structs[s.sid] = s
        descs = [s.describe() for s in structs.values()]
        gr = {}
        for d in descs:
            dep = [d] + [x for x in descs if x["struct_id"] == d["params"].get("q_struct")]
            g = G.ground(dep, probes, classes)
            gr.update({f"{d['struct_id']}:{p}": {"class": g[p]["class"], "precision": round(g[p]["precision"], 3),
                                                 "recall": round(g[p]["recall"], 3), "grounded": g[p]["grounded"]}
                       for p in d["predicates"] if p in g})
        ev = {k: sum(1 for e in w.events if e[1] == k) for k in ("charged_fruit", "arm", "spring_reveal", "spont_fruit")}
        out[seed] = {"judge_events": ev, "structures": [{k: d[k] for k in ("struct_id", "form", "params", "stats")} for d in descs],
                     "grounding": gr}
        print(json.dumps({seed: out[seed]}, default=str), flush=True)
    return out


if __name__ == "__main__":
    res = main([int(x) for x in sys.argv[1:]])
    (HERE / "g3_learner_control.json").write_text(json.dumps(res, indent=1, default=str))
