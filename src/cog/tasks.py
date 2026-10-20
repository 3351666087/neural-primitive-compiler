"""Cognitive micro-task families: interfaces and REFERENCE SEMANTICS (the specification oracle).

The reference semantics below is the *specification*. It is written as plain set manipulation in the
"forward" direction (where does each point go), and it is only ever executed as a black box:
constructors never import the lambdas in this file (tests enforce that `cog.prims`, `cog.ir`,
`cog.learn` do not import `cog.tasks`).

Time convention (shared by every task):
  S(t)            state after processing the frame at time t; S(-1) = empty set.
  frame at t      at most one letter channel is 1 (environment assumption), plus data/query bundles.
  img_j(t)        = [j in S(t - L_img)]                         (state image, L_img declared per task)
  any_R(t)        = [S(t - L_any) meets R]                       (region query)
  sel_b(t)        = exists a: q_a(t - L_q) and (a, b) in S(t - L_q - 1)    (selection query)
A conditional letter COND at tau takes effect at tau + D (declared), computed from S(tau - 1), and requires
no other letter in (tau, tau + D] (pacing assumption).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Iterable

Coord = tuple


def cname(bundle: str, coord: Coord) -> str:
    return bundle + "_" + "_".join(str(c) for c in coord) if coord else bundle


# ------------------------------------------------------------------ spaces
@dataclass(frozen=True)
class Space:
    name: str
    kind: str          # "grid" | "table" | "objgrid" | "vec"
    dims: tuple        # grid: (N,), table: (K, V), objgrid: (K, N), vec: (n,)

    @property
    def coords(self) -> tuple:
        if self.kind == "grid":
            (N,) = self.dims
            return tuple((x, y) for y in range(N) for x in range(N))
        if self.kind == "table":
            K, V = self.dims
            return tuple((k, v) for k in range(K) for v in range(V))
        if self.kind == "objgrid":
            K, N = self.dims
            return tuple((k, x, y) for k in range(K) for y in range(N) for x in range(N))
        if self.kind == "vec":
            (n,) = self.dims
            return tuple((i,) for i in range(n))
        raise ValueError(self.kind)


def grid(N: int) -> Space:
    return Space(f"grid{N}", "grid", (N,))


def table(K: int, V: int) -> Space:
    return Space(f"table{K}x{V}", "table", (K, V))


def objgrid(K: int, N: int) -> Space:
    return Space(f"objgrid{K}x{N}", "objgrid", (K, N))


def vec(n: int) -> Space:
    return Space(f"vec{n}", "vec", (n,))


# ------------------------------------------------------------------ task description
@dataclass
class Letter:
    name: str
    # forward semantics: (S, data_frame) -> new S. Specification only; never read by constructors.
    act: Callable[[frozenset, dict], frozenset]
    data: str | None = None          # name of the data bundle read together with this letter
    cond_delay: int | None = None    # for conditional letters: effect delay D


@dataclass
class Output:
    name: str
    kind: str                         # "img" | "any" | "sel" | "match"
    lag: int
    region: frozenset | None = None   # for "any": set of coords
    query: str | None = None          # for "sel"/"match": query bundle name(s)
    query2: str | None = None
    axis: int = 0                     # for "sel": which coordinate axis the query selects
    out_space: Space | None = None    # for "sel": space of the answer


@dataclass
class Task:
    name: str
    family: str
    space: Space
    letters: list[Letter]
    data: dict[str, Space]
    queries: dict[str, Space]
    outputs: list[Output]
    description: str
    pacing: int = 0                   # min idle steps after a conditional letter (= its delay)
    tags: dict = field(default_factory=dict)

    # -------------------------------------------------------------- interface (what constructors see)
    def interface(self) -> dict:
        """Everything a constructor may know without probing: channel names, spaces, lags."""
        return {
            "name": self.name,
            "state_space": {"kind": self.space.kind, "dims": list(self.space.dims)},
            "letters": [{"name": l.name, "data": l.data, "cond_delay": l.cond_delay} for l in self.letters],
            "data": {k: {"kind": s.kind, "dims": list(s.dims)} for k, s in self.data.items()},
            "queries": {k: {"kind": s.kind, "dims": list(s.dims)} for k, s in self.queries.items()},
            "outputs": [{"name": o.name, "kind": o.kind, "lag": o.lag,
                         "space": ({"kind": o.out_space.kind, "dims": list(o.out_space.dims)} if o.out_space else None)}
                        for o in self.outputs],
            "description": self.description,
        }

    def input_channels(self) -> list[str]:
        chans = [l.name for l in self.letters]
        for b, s in self.data.items():
            chans += [cname(b, c) for c in s.coords]
        for b, s in self.queries.items():
            chans += [cname(b, c) for c in s.coords]
        return chans

    def output_channels(self) -> list[str]:
        out = []
        for o in self.outputs:
            if o.kind == "img":
                out += [cname(o.name, c) for c in self.space.coords]
            elif o.kind in ("any", "match"):
                out.append(o.name)
            elif o.kind == "sel":
                out += [cname(o.name, c) for c in (o.out_space.coords if o.out_space else ((),))]
        return out


# ------------------------------------------------------------------ reference execution
def run_reference(task: Task, trace: dict[str, list[int]], T: int) -> dict[str, list[int]]:
    """Execute the specification on a valid input trace. Returns every output channel over [0, T)."""
    S_hist: list[frozenset] = []
    S = frozenset()
    pending: dict[int, Callable] = {}
    for t in range(T):
        frame = {k: v[t] for k, v in trace.items()}
        new = S
        for l in task.letters:
            if frame.get(l.name, 0):
                if l.cond_delay is None:
                    new = l.act(S, frame)
                else:  # conditional: decide now on S(t-1), apply at t + D
                    snapshot = S
                    pending[t + l.cond_delay] = (lambda snap=snapshot, f=frame, L=l: L.act(snap, f))
        if t in pending:
            new = pending.pop(t)()
        S = new
        S_hist.append(S)

    def state(tau: int) -> frozenset:
        return S_hist[tau] if tau >= 0 else frozenset()

    out: dict[str, list[int]] = {}
    for o in task.outputs:
        if o.kind == "img":
            for c in task.space.coords:
                out[cname(o.name, c)] = [int(c in state(t - o.lag)) for t in range(T)]
        elif o.kind == "any":
            out[o.name] = [int(bool(state(t - o.lag) & o.region)) for t in range(T)]
        elif o.kind == "sel":
            qs = task.queries[o.query]
            outs = o.out_space.coords if o.out_space else ((),)
            for b in outs:
                col = []
                for t in range(T):
                    tq = t - o.lag
                    val = 0
                    if tq >= 0:
                        for a in qs.coords:
                            if trace[cname(o.query, a)][tq]:
                                full = _join(a, b, o.axis)
                                val |= int(full in state(tq - 1))
                    col.append(val)
                out[cname(o.name, b)] = col
        elif o.kind == "match":
            qa, qb = task.queries[o.query], task.queries[o.query2]
            col = []
            for t in range(T):
                tq = t - o.lag
                val = 0
                if tq >= 0:
                    S0 = state(tq - 1)
                    ja = [a for a in qa.coords if trace[cname(o.query, a)][tq]]
                    jb = [b for b in qb.coords if trace[cname(o.query2, b)][tq]]
                    for (a,) in ja:
                        for (b,) in jb:
                            va = {p[1] for p in S0 if p[0] == a}
                            vb = {p[1] for p in S0 if p[0] == b}
                            val |= int(bool(va & vb))
                col.append(val)
            out[o.name] = col
    return out


def _join(a: Coord, b: Coord, axis: int) -> Coord:
    """Insert the selected coordinate a (1-tuple) at position `axis` into the answer coordinate b."""
    b = tuple(b)
    return b[:axis] + tuple(a) + b[axis:]


# ------------------------------------------------------------------ random valid traces
def random_trace(task: Task, T: int, rng: random.Random, p_letter: float = 0.6, p_query: float = 0.4) -> dict[str, list[int]]:
    """Valid traces: <= 1 letter per step; one-hot value data for table stores; one-hot queries;
    after a conditional letter, `pacing` idle steps."""
    tr = {c: [0] * T for c in task.input_channels()}
    quiet_until = -1
    for t in range(T):
        if t > quiet_until and rng.random() < p_letter:
            l = rng.choice(task.letters)
            tr[l.name][t] = 1
            if l.data:
                sp = task.data[l.data]
                if sp.kind == "vec":  # a value: exactly one channel
                    c = rng.choice(sp.coords)
                    tr[cname(l.data, c)][t] = 1
                else:
                    for c in sp.coords:
                        tr[cname(l.data, c)][t] = int(rng.random() < 0.35)
            if l.cond_delay is not None:
                quiet_until = t + l.cond_delay
        for b, sp in task.queries.items():
            if rng.random() < p_query:
                tr[cname(b, rng.choice(sp.coords))][t] = 1
    return tr


def valid(task: Task, trace: dict[str, list[int]], T: int) -> bool:
    quiet_until = -1
    for t in range(T):
        active = [l for l in task.letters if trace[l.name][t]]
        if len(active) > 1 or (active and t <= quiet_until):
            return False
        for l in active:
            if l.data and task.data[l.data].kind == "vec":
                if sum(trace[cname(l.data, c)][t] for c in task.data[l.data].coords) != 1:
                    return False
            if l.cond_delay is not None:
                quiet_until = t + l.cond_delay
        for b, sp in task.queries.items():
            if sum(trace[cname(b, c)][t] for c in sp.coords) > 1:
                return False
    return True


# ------------------------------------------------------------------ forward point maps (spec level)
def pmap(f: Callable[[Coord], Iterable[Coord] | Coord | None], coords: tuple) -> Callable[[frozenset, dict], frozenset]:
    """Letter semantics from a forward point map: every point goes to f(point) (None = vanishes)."""
    cs = set(coords)

    def act(S: frozenset, frame: dict) -> frozenset:
        out = set()
        for p in S:
            r = f(p)
            if r is None:
                continue
            for q in (r if isinstance(r, list) else [r]):
                if q in cs:
                    out.add(q)
        return frozenset(out)
    return act


def grid_point_maps(N: int) -> dict[str, Callable]:
    M = N - 1
    return {
        "ROT90": lambda p: (M - p[1], p[0]),            # clockwise, y grows downward
        "ROT180": lambda p: (M - p[0], M - p[1]),
        "ROT270": lambda p: (p[1], M - p[0]),
        "FLIPH": lambda p: (M - p[0], p[1]),             # mirror left-right
        "FLIPV": lambda p: (p[0], M - p[1]),             # mirror top-bottom
        "TRANSPOSE": lambda p: (p[1], p[0]),
        "RIGHT": lambda p: (p[0] + 1, p[1]) if p[0] + 1 <= M else None,   # clipping shifts
        "LEFT": lambda p: (p[0] - 1, p[1]) if p[0] >= 1 else None,
        "DOWN": lambda p: (p[0], p[1] + 1) if p[1] + 1 <= M else None,
        "UP": lambda p: (p[0], p[1] - 1) if p[1] >= 1 else None,
        "RIGHTWRAP": lambda p: ((p[0] + 1) % N, p[1]),
        "DILATE": lambda p: [q for q in [p, (p[0] + 1, p[1]), (p[0] - 1, p[1]), (p[0], p[1] + 1), (p[0], p[1] - 1)]
                             if 0 <= q[0] <= M and 0 <= q[1] <= M],
    }


DESCR = {
    "ROT90": "rotate the remembered shape 90 degrees clockwise about the grid centre",
    "ROT180": "rotate the shape 180 degrees", "ROT270": "rotate the shape 90 degrees counter-clockwise",
    "FLIPH": "mirror the shape left-right", "FLIPV": "mirror the shape top-bottom",
    "TRANSPOSE": "reflect the shape across the main diagonal (x <-> y)",
    "RIGHT": "move the shape one cell right; cells pushed past the border disappear",
    "LEFT": "move the shape one cell left; cells pushed past the border disappear",
    "DOWN": "move the shape one cell down; cells pushed past the border disappear",
    "UP": "move the shape one cell up; cells pushed past the border disappear",
    "RIGHTWRAP": "move the shape one cell right, wrapping around the right border",
    "DILATE": "thicken the shape: every on cell also turns on its 4 neighbours",
}


# ------------------------------------------------------------------ family A: spatial working memory
def family_a(N: int, cmds: list[str], name: str | None = None, queries: list[str] = (), cond: tuple | None = None) -> Task:
    """A shape is LOADed from `see`, transformed by commands, and continuously imagined on `img` (lag 2).
    queries: "top" (any cell in row 0, lag 3), "cell" (is the queried cell on, lag 3).
    cond: (name, region_name, then_cmd, else_cmd, delay) conditional command."""
    sp = grid(N)
    pm = grid_point_maps(N)
    letters = [Letter("LOAD", lambda S, f: frozenset(c for c in sp.coords if f.get(cname("see", c), 0)), data="see")]
    for c in cmds:
        letters.append(Letter(c, pmap(pm[c], sp.coords)))
    outputs = [Output("img", "img", 2)]
    queries_sp: dict[str, Space] = {}
    descr = [f"A {N}x{N} grid. LOAD stores the shape shown on `see` (one channel per cell, x left-to-right, "
             f"y top-to-bottom). Output `img` continuously shows the remembered shape 2 steps late."]
    descr += [f"Command {c}: {DESCR[c]}." for c in cmds]
    regions = {"top": frozenset(c for c in sp.coords if c[1] == 0), "left": frozenset(c for c in sp.coords if c[0] == 0),
               "bottom": frozenset(c for c in sp.coords if c[1] == N - 1), "all": frozenset(sp.coords)}
    for q in queries:
        if q in regions:
            outputs.append(Output(f"any_{q}", "any", 3, region=regions[q]))
            descr.append(f"Output any_{q}: 1 iff the remembered shape has a cell in region {q}, 3 steps late.")
        elif q == "cell":
            queries_sp["qcell"] = sp
            outputs.append(Output("cellon", "sel", 3, query="qcell", axis=0, out_space=None))
            descr.append("Query qcell (one cell): output cellon = whether that cell is on in the shape as it was just "
                         "before the query, 3 steps after the query.")
    pacing = 0
    if cond:
        cname_, reg, then_c, else_c, D = cond
        R = regions[reg]

        def act(S, f, R=R, a=pmap(pm[then_c], sp.coords), b=pmap(pm[else_c], sp.coords)):
            return a(S, f) if S & R else b(S, f)
        letters.append(Letter(cname_, act, cond_delay=D))
        pacing = D
        descr.append(f"Command {cname_}: if the shape has a cell in region {reg}, apply {then_c} ({DESCR[then_c]}), "
                     f"otherwise apply {else_c} ({DESCR[else_c]}); decided on the shape just before the command, "
                     f"takes effect {D} steps later; the environment sends no other command meanwhile.")
    return Task(name or f"A_{N}_{'_'.join(cmds)}", "A", sp, letters, {"see": sp}, queries_sp, outputs,
                " ".join(descr), pacing)


# ------------------------------------------------------------------ family B: object-value binding
def family_b(K: int, V: int, ops: list[str], name: str | None = None, queries: list[str] = ("value",)) -> Task:
    """K objects, each may hold one of V values. STOREk (with `val`), SWAPjk, COPYjk, CLEARk.
    queries: "value" (value of the queried object), "who" (which objects hold the queried value), "same"."""
    sp = table(K, V)
    letters: list[Letter] = []
    descr = [f"{K} objects (slots 0..{K - 1}), each holding at most one of {V} values. Output `img` shows the "
             f"object-value table 2 steps late."]
    for op in ops:
        if op == "STORE":
            for k in range(K):
                letters.append(Letter(f"STORE{k}", lambda S, f, k=k: frozenset(
                    {p for p in S if p[0] != k} | {(k, v) for v in range(V) if f.get(cname("val", (v,)), 0)}), data="val"))
            descr.append("STOREk: object k now holds the value shown on `val` (one-hot).")
        elif op == "SWAP":
            for j in range(K):
                for k in range(j + 1, K):
                    letters.append(Letter(f"SWAP{j}{k}", lambda S, f, j=j, k=k: frozenset(
                        ((k if p[0] == j else j if p[0] == k else p[0]), p[1]) for p in S)))
            descr.append("SWAPjk: objects j and k exchange their values.")
        elif op == "COPY":
            for j in range(K):
                for k in range(K):
                    if j != k:
                        letters.append(Letter(f"COPY{j}{k}", lambda S, f, j=j, k=k: frozenset(
                            {p for p in S if p[0] != k} | {(k, p[1]) for p in S if p[0] == j})))
            descr.append("COPYjk: object k gets a copy of object j's value (or becomes empty if j is empty).")
        elif op == "CLEAR":
            for k in range(K):
                letters.append(Letter(f"CLEAR{k}", lambda S, f, k=k: frozenset(p for p in S if p[0] != k)))
            descr.append("CLEARk: object k becomes empty.")
    outputs = [Output("img", "img", 2)]
    qsp: dict[str, Space] = {}
    for q in queries:
        if q == "value":
            qsp["qobj"] = vec(K)
            outputs.append(Output("valueof", "sel", 3, query="qobj", axis=0, out_space=vec(V)))
            descr.append("Query qobj (one object): output valueof shows that object's value (one-hot), 3 steps after "
                         "the query, as of just before the query.")
        elif q == "who":
            qsp["qval"] = vec(V)
            outputs.append(Output("who", "sel", 3, query="qval", axis=1, out_space=vec(K)))
            descr.append("Query qval (one value): output who marks every object holding that value, 3 steps after "
                         "the query, as of just before the query.")
        elif q == "same":
            qsp["qa"] = vec(K)
            qsp["qb"] = vec(K)
            outputs.append(Output("same", "match", 5, query="qa", query2="qb"))
            descr.append("Queries qa, qb (one object each, same step): output same = 1 iff both objects hold the same "
                         "value, 5 steps after the query, as of just before it.")
    data = {"val": vec(V)}
    return Task(name or f"B_{K}x{V}_{'_'.join(ops)}", "B", sp, letters, data, qsp, outputs, " ".join(descr))


# ------------------------------------------------------------------ family AB: several objects on one grid
def family_ab(K: int, N: int, cmds: list[str], name: str | None = None, queries: list[str] = ()) -> Task:
    """K objects, each a shape on the same N x N grid (objects may overlap). PLACEk loads object k's shape
    from `see`; command Ck (C in cmds) transforms object k only. Output img shows every object's cells
    (coordinate (k, x, y)), 2 steps late. queries: "toptouch" (object k has a cell in row 0, one output
    per object, lag 3); "occupant" (for the queried cell: which objects cover it, lag 3)."""
    sp = objgrid(K, N)
    pm = grid_point_maps(N)
    gcoords = grid(N).coords
    letters = []
    descr = [f"{K} objects on a {N}x{N} grid (x left-to-right, y top-to-bottom); objects may overlap. "
             f"Output img shows, for each object k and cell (x, y), whether object k covers it, 2 steps late."]
    for k in range(K):
        letters.append(Letter(f"PLACE{k}", lambda S, f, k=k: frozenset(
            {p for p in S if p[0] != k} | {(k,) + c for c in gcoords if f.get(cname("see", c), 0)}), data="see"))
    descr.append("PLACEk: object k's shape becomes the shape shown on `see`.")
    for c in cmds:
        for k in range(K):
            def act(S, f, k=k, g=pm[c]):
                out = {p for p in S if p[0] != k}
                for p in S:
                    if p[0] == k:
                        r = g(p[1:])
                        for q in (r if isinstance(r, list) else ([r] if r is not None else [])):
                            if 0 <= q[0] < N and 0 <= q[1] < N:
                                out.add((k,) + q)
                return frozenset(out)
            letters.append(Letter(f"{c}{k}", act))
        descr.append(f"{c}k: {DESCR[c]} -- applied to object k only.")
    outputs = [Output("img", "img", 2)]
    qsp: dict[str, Space] = {}
    for q in queries:
        if q == "toptouch":
            for k in range(K):
                outputs.append(Output(f"top{k}", "any", 3, region=frozenset((k, x, 0) for x in range(N))))
            descr.append("Outputs topk: 1 iff object k has a cell in the top row, 3 steps late.")
        elif q == "occupant":
            qsp["qcell"] = grid(N)
            outputs.append(Output("occ", "sel", 3, query="qcell", axis=1, out_space=vec(K)))
            descr.append("Query qcell (one cell): output occ marks every object covering that cell, 3 steps after the "
                         "query, as of just before it.")
    return Task(name or f"AB_{K}x{N}_{'_'.join(cmds)}", "AB", sp, letters, {"see": grid(N)}, qsp, outputs, " ".join(descr))
