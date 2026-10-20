"""Unseen-task generator (frozen with the primitives; tasks are drawn only after the freeze).

Tasks are built from the same spec-level semantics as cog.tasks, but with things never present in the
design tasks: opaque command names (CMD0, CMD1, ...), commands that are compositions of two base
moves, base moves never used at design time (ROT180, ROT270, TRANSPOSE, LEFT, UP, DOWN, RIGHTWRAP),
larger sizes (design used N <= 4, K, V <= 3), the objects-on-grid family as a whole, and new
combinations of queries and conditional commands. Each task is evaluated at several sizes.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .tasks import (DESCR, Letter, Output, Space, Task, cname, family_ab, family_b, grid, grid_point_maps, pmap)

A_POOL = ["ROT90", "ROT180", "ROT270", "FLIPH", "FLIPV", "TRANSPOSE", "RIGHT", "LEFT", "UP", "DOWN", "RIGHTWRAP", "DILATE"]
DESIGN_A = {"ROT90", "FLIPH", "RIGHT", "DILATE", "FLIPV"}


@dataclass
class Unseen:
    uid: str
    family: str
    params: dict
    sizes: list

    def build(self, size) -> Task:
        p = self.params
        if self.family == "A":
            return build_a(self.uid, size, p["commands"], p["queries"], p.get("cond"))
        if self.family == "B":
            K, V = size
            return family_b(K, V, p["ops"], name=f"{self.uid}@{K}x{V}", queries=p["queries"])
        if self.family == "AB":
            K, N = size
            return family_ab(K, N, p["cmds"], name=f"{self.uid}@{K}x{N}", queries=p["queries"])
        raise ValueError(self.family)


def build_a(uid: str, N: int, commands: list, queries: list, cond) -> Task:
    """commands: list of (opaque name, [base moves applied in order])."""
    sp = grid(N)
    pm = grid_point_maps(N)
    letters = [Letter("LOAD", lambda S, f: frozenset(c for c in sp.coords if f.get(cname("see", c), 0)), data="see")]
    descr = [f"A {N}x{N} grid (x left-to-right, y top-to-bottom). LOAD stores the shape shown on `see`. Output img "
             f"continuously shows the remembered shape 2 steps late."]
    for name, seq in commands:
        fs = [pmap(pm[m], sp.coords) for m in seq]

        def act(S, f, fs=fs):
            for g in fs:
                S = g(S, f)
            return S
        letters.append(Letter(name, act))
        descr.append(f"Command {name}: " + ", then ".join(DESCR[m] for m in seq) + ".")
    regions = {"top": frozenset(c for c in sp.coords if c[1] == 0), "left": frozenset(c for c in sp.coords if c[0] == 0),
               "bottom": frozenset(c for c in sp.coords if c[1] == N - 1), "all": frozenset(sp.coords)}
    words = {"top": "the top row", "left": "the left column", "bottom": "the bottom row", "all": "anywhere"}
    outputs = [Output("img", "img", 2)]
    qsp = {}
    for q in queries:
        if q in regions:
            outputs.append(Output(f"any_{q}", "any", 3, region=regions[q]))
            descr.append(f"Output any_{q}: 1 iff the shape has a cell in {words[q]}, 3 steps late.")
        elif q == "cell":
            qsp["qcell"] = sp
            outputs.append(Output("cellon", "sel", 3, query="qcell", axis=0, out_space=None))
            descr.append("Query qcell (one cell): output cellon = whether that cell is on, 3 steps after the query, "
                         "as of just before the query.")
    pacing = 0
    if cond:
        cname_, reg, then_seq, else_seq, D = cond
        R = regions[reg]
        fa = [pmap(pm[m], sp.coords) for m in then_seq]
        fb = [pmap(pm[m], sp.coords) for m in else_seq]

        def cact(S, f, R=R, fa=fa, fb=fb):
            for g in (fa if S & R else fb):
                S = g(S, f)
            return S
        letters.append(Letter(cname_, cact, cond_delay=D))
        pacing = D
        descr.append(f"Command {cname_}: if the shape has a cell in {words[reg]}, then "
                     + ", then ".join(DESCR[m] for m in then_seq) + "; otherwise "
                     + ", then ".join(DESCR[m] for m in else_seq)
                     + f". Decided on the shape just before the command; the result appears as the state {D} steps "
                       f"later; the environment sends no other command in between.")
    return Task(f"{uid}@{N}", "A", sp, letters, {"see": sp}, qsp, outputs, " ".join(descr), pacing)


def generate(seed: int, n_a: int = 8, n_b: int = 4, n_ab: int = 4) -> list[Unseen]:
    rng = random.Random(seed)
    out = []
    for i in range(n_a):
        ncmd = rng.randint(2, 4)
        cmds = []
        for c in range(ncmd):
            if rng.random() < 0.4:
                seq = [rng.choice(A_POOL), rng.choice(A_POOL)]
            else:
                seq = [rng.choice(A_POOL)]
            cmds.append((f"CMD{c}", seq))
        queries = rng.sample(["top", "left", "bottom", "all", "cell"], rng.randint(0, 2))
        cond = None
        if rng.random() < 0.4:
            then_seq = [rng.choice(A_POOL)]
            else_seq = [rng.choice(A_POOL)]
            cond = (f"CMD{ncmd}", rng.choice(["top", "left", "bottom"]), then_seq, else_seq, rng.choice([3, 4]))
        out.append(Unseen(f"UA{i}", "A", {"commands": cmds, "queries": queries, "cond": cond}, [3, 5, 8]))
    for i in range(n_b):
        ops = ["STORE"] + rng.sample(["SWAP", "COPY", "CLEAR"], rng.randint(1, 3))
        queries = rng.sample(["value", "who", "same"], rng.randint(1, 2))
        K, V = rng.randint(2, 3), rng.randint(2, 3)
        out.append(Unseen(f"UB{i}", "B", {"ops": ops, "queries": queries}, [(K, V), (K + 2, V + 1)]))
    for i in range(n_ab):
        cmds = rng.sample(A_POOL, rng.randint(1, 2))
        queries = rng.sample(["toptouch", "occupant"], rng.randint(0, 2))
        out.append(Unseen(f"UAB{i}", "AB", {"cmds": cmds, "queries": queries}, [(2, 3), (3, 5)]))
    return out
