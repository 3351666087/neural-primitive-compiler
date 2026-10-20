"""Mission 03 pilot P3 (H-B; protocol section 5, predictions locked before this script existed).

When can a set-valued ("draw any X such that ...") goal be met by local construction, without search?

Families on N x N grids (N = 5..8), random instances:
  shape     connected shape of exactly k cells containing cell c
  path      4-connected path from A to B avoiding random obstacles (density 0.25)
  perm      exactly one cell in every row and every column
  queens    N queens, no two sharing a row, column or diagonal
  symshape  left-right symmetric, connected shape of exactly k cells
  loop      closed loop (the boundary of a hole-free region) enclosing exactly k cells

Constructors (no constructor sees a solution; choices are random among the allowed moves):
  B1 grow     keep an invariant with local moves only; dead end = no allowed move before the goal
  B2 prop     first propagate (a fixpoint: reachability field, forward checking, or the maximal region the
              growth rule can still reach), refuse if propagation shows the goal impossible, then choose greedily
              (for `loop` the propagation runs only once, at the start: per-step propagation was too slow)
  B3 search   depth-first backtracking with the same propagation (baseline and ground truth for feasibility),
              node budget 200,000

  python mission-03/experiments/p3_generative/run_gen.py
"""

from __future__ import annotations

import json
import random
import time
from collections import deque
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUDGET = 200_000


def nb(c, N):
    x, y = c
    return [(x + dx, y + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)) if 0 <= x + dx < N and 0 <= y + dy < N]


def connected(S, N):
    if not S:
        return True
    S = set(S)
    start = next(iter(S))
    seen, q = {start}, [start]
    while q:
        c = q.pop()
        for d in nb(c, N):
            if d in S and d not in seen:
                seen.add(d)
                q.append(d)
    return len(seen) == len(S)


def hole_free(S, N):
    """No empty cell is enclosed by S (empty cells all reach the border through empty cells)."""
    S = set(S)
    empty = {(x, y) for x in range(N) for y in range(N)} - S
    seen = {c for c in empty if c[0] in (0, N - 1) or c[1] in (0, N - 1)}
    q = list(seen)
    while q:
        c = q.pop()
        for d in nb(c, N):
            if d in empty and d not in seen:
                seen.add(d)
                q.append(d)
    return seen == empty


# ------------------------------------------------------------------ growth-type families
class Growth:
    """A family defined by a seed, a move generator that preserves the invariant, and a goal size."""

    def __init__(self, N, rng, kind):
        self.N, self.kind, self.rng = N, kind, rng
        cells = [(x, y) for x in range(N) for y in range(N)]
        if kind == "shape":
            self.c = rng.choice(cells)
            self.k = rng.randint(2, N * N // 2)
        elif kind == "symshape":
            self.k = rng.randint(2, N * N // 2)
        elif kind == "loop":
            self.k = rng.randint(1, (N - 2) ** 2)

    def seeds(self):
        N = self.N
        if self.kind == "shape":
            return [frozenset({self.c})]
        if self.kind == "symshape":
            out = []
            for y in range(N):
                if N % 2:
                    out.append(frozenset({(N // 2, y)}))
                out.append(frozenset({(N // 2 - 1, y), (N - N // 2, y)}) if N % 2 == 0 else frozenset({(N // 2 - 1, y), (N // 2, y), (N // 2 + 1, y)}))
            return [s for s in out if len(s) <= self.k]
        if self.kind == "loop":
            return [frozenset({(x, y)}) for x in range(1, N - 1) for y in range(1, N - 1)]

    def moves(self, S):
        N = self.N
        front = {d for c in S for d in nb(c, N)} - set(S)
        if self.kind == "shape":
            return [S | {d} for d in front]
        if self.kind == "symshape":
            out = []
            for d in front:
                m = (N - 1 - d[0], d[1])
                T = S | {d, m}
                if connected(T, N):
                    out.append(frozenset(T))
            return list(set(out))
        if self.kind == "loop":
            return [S | {d} for d in front if 0 < d[0] < N - 1 and 0 < d[1] < N - 1 and hole_free(S | {d}, N)]

    def done(self, S):
        return len(S) == self.k

    def over(self, S):
        return len(S) > self.k


def grow(fam, rng, lookahead=False):
    seeds = fam.seeds()
    if not seeds:
        return "no seed"
    S = frozenset(rng.choice(seeds))
    if lookahead and max_reach(fam, S) < fam.k:
        return "refused"
    while not fam.done(S):
        ms = [T for T in fam.moves(S) if not fam.over(T)]
        if lookahead and fam.kind != "loop":   # loop: propagation only at the start (per-step cost is prohibitive)
            ms = [T for T in ms if max_reach(fam, T) >= fam.k]
        if not ms:
            return "dead end"
        S = frozenset(rng.choice(ms))
    return "ok"


def max_reach(fam, S):
    """Propagation for growth families: size of the largest set the growth rule can still reach from S
    (the fixpoint of 'add every allowed cell'); parity of symmetric pairs is ignored on purpose."""
    T = set(S)
    while True:
        add = set()
        for M in fam.moves(frozenset(T)):
            add |= set(M) - T
        if not add:
            return len(T)
        if fam.kind == "loop":   # adding all cells at once can close holes; add one at a time
            T |= {next(iter(add))}
        else:
            T |= add


def search_growth(fam, nodes):
    seen = set()
    stack = list(fam.seeds())
    while stack:
        S = stack.pop()
        if S in seen:
            continue
        seen.add(S)
        nodes[0] += 1
        if nodes[0] > BUDGET:
            return None
        if fam.done(S):
            return True
        stack += [T for T in fam.moves(S) if not fam.over(T) and T not in seen]
    return False


# ------------------------------------------------------------------ path
def path_instance(N, rng):
    cells = [(x, y) for x in range(N) for y in range(N)]
    A, B = rng.sample(cells, 2)
    obst = {c for c in cells if c not in (A, B) and rng.random() < 0.25}
    return A, B, obst


def path_grow(N, inst, rng):
    A, B, obst = inst
    path, cur = {A}, A
    while cur != B:
        ms = [d for d in nb(cur, N) if d not in obst and d not in path]
        if not ms:
            return "dead end"
        cur = rng.choice(ms)
        path.add(cur)
    return "ok"


def dist_field(N, B, obst):
    D, q = {B: 0}, deque([B])
    while q:
        c = q.popleft()
        for d in nb(c, N):
            if d not in obst and d not in D:
                D[d] = D[c] + 1
                q.append(d)
    return D


def path_prop(N, inst, rng):
    A, B, obst = inst
    D = dist_field(N, B, obst)
    if A not in D:
        return "refused"
    cur = A
    while cur != B:
        ms = [d for d in nb(cur, N) if D.get(d, 10 ** 9) == D[cur] - 1]
        if not ms:
            return "dead end"
        cur = rng.choice(ms)
    return "ok"


def path_search(N, inst, nodes):
    A, B, obst = inst
    nodes[0] += len(dist_field(N, B, obst))
    return A in dist_field(N, B, obst)


# ------------------------------------------------------------------ perm / queens (row by row)
def attacks(kind, r1, c1, r2, c2):
    return c1 == c2 or (kind == "queens" and abs(r1 - r2) == abs(c1 - c2))


def rows_grow(N, kind, rng, forward=False):
    placed = []
    dom = [set(range(N)) for _ in range(N)]
    for r in range(N):
        opts = [c for c in range(N) if all(not attacks(kind, r, c, r2, c2) for r2, c2 in placed)]
        if forward:
            opts = [c for c in opts if all(any(not attacks(kind, r, c, r3, c3) and all(not attacks(kind, r3, c3, r2, c2) for r2, c2 in placed)
                                               for c3 in range(N)) for r3 in range(r + 1, N))]
        if not opts:
            return "dead end"
        placed.append((r, rng.choice(opts)))
    return "ok"


def rows_search(N, kind, nodes):
    def rec(placed):
        nodes[0] += 1
        if nodes[0] > BUDGET:
            return None
        r = len(placed)
        if r == N:
            return True
        for c in range(N):
            if all(not attacks(kind, r, c, r2, c2) for r2, c2 in placed):
                res = rec(placed + [(r, c)])
                if res is not False:
                    return res
        return False
    return rec([])


# ------------------------------------------------------------------ experiment
def main():
    rng = random.Random(0)
    t0 = time.perf_counter()
    rows = []
    for N in (5, 6, 7, 8):
        for kind in ("shape", "symshape", "loop", "path", "perm", "queens"):
            n_inst = 100 if kind in ("shape", "symshape", "loop", "path") else 50
            stats = {k: {"ok": 0, "dead end": 0, "refused": 0, "no seed": 0} for k in ("B1", "B2")}
            feas = {"feasible": 0, "infeasible": 0, "budget": 0}
            b2_judgement = {"refused_feasible": 0, "refused_infeasible": 0, "accepted_infeasible": 0}
            nodes_total = 0
            for _ in range(n_inst):
                nodes = [0]
                if kind in ("shape", "symshape", "loop"):
                    fam = Growth(N, rng, kind)
                    truth = search_growth(fam, nodes)
                    r1, r2 = grow(fam, rng), grow(fam, rng, lookahead=True)
                elif kind == "path":
                    inst = path_instance(N, rng)
                    truth = path_search(N, inst, nodes)
                    r1, r2 = path_grow(N, inst, rng), path_prop(N, inst, rng)
                else:
                    truth = rows_search(N, kind, nodes)
                    r1, r2 = rows_grow(N, kind, rng), rows_grow(N, kind, rng, forward=True)
                nodes_total += nodes[0]
                feas["budget" if truth is None else "feasible" if truth else "infeasible"] += 1
                stats["B1"][r1] += 1
                stats["B2"][r2] += 1
                if r2 == "refused":
                    b2_judgement["refused_feasible" if truth else "refused_infeasible"] += 1
                elif truth is False:
                    b2_judgement["accepted_infeasible"] += 1
            row = {"N": N, "family": kind, "instances": n_inst, "ground_truth": feas, "B1": stats["B1"], "B2": stats["B2"],
                   "B2_feasibility_judgement": b2_judgement, "B3_mean_nodes": round(nodes_total / n_inst, 1)}
            print(row, flush=True)
            rows.append(row)
    (HERE / "generative.json").write_text(json.dumps({"rows": rows, "time_s": round(time.perf_counter() - t0, 1)}, indent=1))


if __name__ == "__main__":
    main()
