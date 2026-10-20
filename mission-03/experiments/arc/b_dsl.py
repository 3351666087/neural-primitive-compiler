"""Symbolic DSL baselines for ARC (protocol amendment 9). Whole-grid programs from a named vocabulary,
enumerated shortest first; the first program consistent with every training pair answers the test inputs.

B-SAME : the same expressive class as M-DISC (unions of D4 / scaled / tiled / mirrored copies) under a named
         vocabulary, composition depth <= 3, plus a colour function learned from the training pairs.
B-RICH : B-SAME plus non-union operations (crop to content, gravity, fill enclosed holes, largest object,
         delete background rows and columns, outline); programs containing a rich operation have depth <= 2.
B-TRIVIAL: identity; the first training output.

The vocabulary was written from generic image operations and from published descriptions of ARC DSLs
(icecuber, Hodel), not from viewing ARC tasks.
"""

from __future__ import annotations

import itertools

import numpy as np

BG = 0


def _tile(k, l):
    return lambda g: np.tile(g, (k, l))


SAME_OPS = {
    "rot90": lambda g: np.rot90(g, -1), "rot180": lambda g: np.rot90(g, 2), "rot270": lambda g: np.rot90(g, 1),
    "flipH": lambda g: g[:, ::-1], "flipV": lambda g: g[::-1, :], "transpose": lambda g: g.T,
    "antitranspose": lambda g: np.rot90(g, 2).T,
    "scale2": lambda g: np.kron(g, np.ones((2, 2), dtype=g.dtype)), "scale3": lambda g: np.kron(g, np.ones((3, 3), dtype=g.dtype)),
    **{f"tile{k}x{l}": _tile(k, l) for k in (1, 2, 3) for l in (1, 2, 3) if (k, l) != (1, 1)},
    "hmirror": lambda g: np.hstack([g, g[:, ::-1]]), "hmirror2": lambda g: np.hstack([g[:, ::-1], g]),
    "vmirror": lambda g: np.vstack([g, g[::-1, :]]), "vmirror2": lambda g: np.vstack([g[::-1, :], g]),
    "quad": lambda g: np.vstack([np.hstack([g, g[:, ::-1]]), np.hstack([g[::-1, :], np.rot90(g, 2)])]),
}


def crop(g):
    ys, xs = np.nonzero(g != BG)
    if not len(ys):
        return g
    return g[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def gravity(g, d):
    r = {"down": 0, "left": 1, "up": 2, "right": 3}[d]
    h = np.rot90(g, r).copy()
    out = np.full_like(h, BG)
    for x in range(h.shape[1]):
        col = [v for v in h[:, x] if v != BG]
        if col:
            out[h.shape[0] - len(col):, x] = col
    return np.rot90(out, -r)


def components(g):
    seen = np.zeros(g.shape, bool)
    comps = []
    for y in range(g.shape[0]):
        for x in range(g.shape[1]):
            if g[y, x] != BG and not seen[y, x]:
                stack, cells = [(y, x)], []
                seen[y, x] = True
                while stack:
                    a, b = stack.pop()
                    cells.append((a, b))
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        u, v = a + dy, b + dx
                        if 0 <= u < g.shape[0] and 0 <= v < g.shape[1] and not seen[u, v] and g[u, v] != BG:
                            seen[u, v] = True
                            stack.append((u, v))
                comps.append(cells)
    return comps


def largest(g):
    comps = components(g)
    if not comps:
        return g
    cells = max(comps, key=len)
    out = np.full_like(g, BG)
    for a, b in cells:
        out[a, b] = g[a, b]
    return crop(out)


def holes_mask(g):
    """Background cells not connected to the border through background cells."""
    H, W = g.shape
    reach = np.zeros(g.shape, bool)
    stack = [(y, x) for y in range(H) for x in range(W) if (y in (0, H - 1) or x in (0, W - 1)) and g[y, x] == BG]
    for c in stack:
        reach[c] = True
    while stack:
        a, b = stack.pop()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            u, v = a + dy, b + dx
            if 0 <= u < H and 0 <= v < W and not reach[u, v] and g[u, v] == BG:
                reach[u, v] = True
                stack.append((u, v))
    return (g == BG) & ~reach


def drop_bg_lines(g):
    rows = [i for i in range(g.shape[0]) if (g[i] != BG).any()]
    cols = [j for j in range(g.shape[1]) if (g[:, j] != BG).any()]
    if not rows or not cols:
        return g
    return g[np.ix_(rows, cols)]


def outline(g):
    out = np.full_like(g, BG)
    H, W = g.shape
    for y in range(H):
        for x in range(W):
            if g[y, x] != BG:
                nb = [(y + dy, x + dx) for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1))]
                if any(not (0 <= a < H and 0 <= b < W) or g[a, b] == BG for a, b in nb):
                    out[y, x] = g[y, x]
    return out


RICH_OPS = {
    "crop": crop, "gravity_down": lambda g: gravity(g, "down"), "gravity_up": lambda g: gravity(g, "up"),
    "gravity_left": lambda g: gravity(g, "left"), "gravity_right": lambda g: gravity(g, "right"),
    "largest": largest, "drop_bg_lines": drop_bg_lines, "outline": outline,
    "fill_holes": "FILL",   # colour learned from the training pairs
}


def colour_fn(outs, targets):
    """A colour function f with f(out) == target cell-wise on every pair; None if impossible."""
    f = {}
    for o, t in zip(outs, targets):
        if o.shape != t.shape:
            return None
        for a, b in zip(o.ravel(), t.ravel()):
            a, b = int(a), int(b)
            if f.setdefault(a, b) != b:
                return None
    return f


def run_prog(prog, g, fill=None):
    for name in prog:
        op = SAME_OPS.get(name) or RICH_OPS.get(name)
        if op == "FILL":
            g = g.copy()
            g[holes_mask(g)] = fill
        else:
            g = op(g)
        if g.size > 900 or g.size == 0:
            return None
    return g


def programs(rich):
    same = list(SAME_OPS)
    yield ("identity",)
    for d in (1, 2, 3):
        for p in itertools.product(same, repeat=d):
            yield p
    if rich:
        allops = same + list(RICH_OPS)
        for d in (1, 2):
            for p in itertools.product(allops, repeat=d):
                if any(o in RICH_OPS for o in p):
                    yield p


def solve(train, tests, rich=False, max_programs=None):
    """Returns (outputs, info). Abstains (None) when no program fits."""
    tried = 0
    for prog in programs(rich):
        tried += 1
        if max_programs and tried > max_programs:
            break
        prog = () if prog == ("identity",) else prog
        fills = range(1, 10) if "fill_holes" in prog else [None]
        for fill in fills:
            outs = [run_prog(prog, I, fill) for I, _ in train]
            if any(o is None for o in outs):
                continue
            targets = [O for _, O in train]
            if all(o.shape == t.shape and (o == t).all() for o, t in zip(outs, targets)):
                f = None
            else:
                f = colour_fn(outs, targets)
                if f is None:
                    continue
            res = []
            for I in tests:
                o = run_prog(prog, I, fill)
                if o is None:
                    res.append(None)
                    continue
                if f is not None:
                    ident = all(k == v for k, v in f.items())
                    if not ident and any(int(v) not in f for v in np.unique(o)):
                        res.append(None)
                        continue
                    o = np.vectorize(lambda v: f.get(int(v), int(v)))(o)
                res.append(o)
            return res, {"program": list(prog) or ["identity"], "colour_fn": f is not None, "fill": fill, "tried": tried}
    return [None] * len(tests), {"program": None, "tried": tried}


def trivial(train, tests, kind):
    if kind == "identity":
        return [I.copy() for I in tests], {}
    return [train[0][1].copy() for _ in tests], {}
