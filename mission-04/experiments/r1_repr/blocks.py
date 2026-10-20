"""Mission 04 pilot P-R1: where does a block representation come from, and how is it selected?
(protocol: mission-04/PROTOCOL.md section 2, locked before this file was written)

Partition grammar: adjacency atom (A4, A8, AH, AV) AND predicate (SAME, NONBG), transitive closure over non-background
cells; plus COLOUR (all non-background cells of one colour). The block mechanism layer (KEEP, RECOLOUR, CROP) and
the block attributes are shared by every route, so routes differ only in where the partitions come from and how
they are selected.
"""

from __future__ import annotations

import numpy as np

BG = 0
ATOMS = {"A4": ((1, 0), (-1, 0), (0, 1), (0, -1)),
         "A8": ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)),
         "AH": ((0, 1), (0, -1)), "AV": ((1, 0), (-1, 0))}
GRAMMAR = [f"{a}-{p}" for a in ATOMS for p in ("SAME", "NONBG")] + ["COLOUR"]
F1_LIST = ["A4-SAME", "A8-NONBG"]
FEATURES = ["size", "size_rank", "colour", "bbox_h", "bbox_w", "shape", "is_largest", "is_smallest", "touches_border",
            "n_colours"]
NUMERIC = {"size", "size_rank", "bbox_h", "bbox_w", "n_colours"}


def partition(g, rule):
    H, W = g.shape
    cells = [(r, c) for r in range(H) for c in range(W) if g[r, c] != BG]
    if rule == "COLOUR":
        groups = {}
        for cell in cells:
            groups.setdefault(int(g[cell]), set()).add(cell)
        return [frozenset(v) for v in groups.values()]
    atom, pred = rule.split("-")
    seen, blocks = set(), []
    for start in cells:
        if start in seen:
            continue
        stack, comp = [start], set()
        seen.add(start)
        while stack:
            a = stack.pop()
            comp.add(a)
            for dr, dc in ATOMS[atom]:
                b = (a[0] + dr, a[1] + dc)
                if 0 <= b[0] < H and 0 <= b[1] < W and b not in seen and g[b] != BG:
                    if pred == "NONBG" or g[b] == g[a]:
                        seen.add(b)
                        stack.append(b)
        blocks.append(frozenset(comp))
    return blocks


def features(blocks, g):
    H, W = g.shape
    sizes = sorted({len(b) for b in blocks}, reverse=True)
    out = []
    for b in blocks:
        rs, cs = [r for r, _ in b], [c for _, c in b]
        cols = {int(g[x]) for x in b}
        r0, c0 = min(rs), min(cs)
        out.append({"size": len(b), "size_rank": sizes.index(len(b)), "colour": cols.pop() if len(cols) == 1 else -1,
                    "bbox_h": max(rs) - r0 + 1, "bbox_w": max(cs) - c0 + 1,
                    "shape": frozenset((r - r0, c - c0) for r, c in b),
                    "is_largest": len(b) == sizes[0], "is_smallest": len(b) == sizes[-1],
                    "touches_border": any(r in (0, H - 1) or c in (0, W - 1) for r, c in b),
                    "n_colours": len({int(g[x]) for x in b})})
    return out


def phi_holds(phi, f, allf):
    feat, op, val = phi
    if op == "eq":
        return f[feat] == val
    vals = [x[feat] for x in allf]
    return f[feat] == (max(vals) if op == "max" else min(vals))


def candidate_phis(train_feats):
    phis = []
    for feat in FEATURES:
        vals = {f[feat] for fs in train_feats for f in fs}
        phis += [(feat, "eq", v) for v in vals]
        if feat in NUMERIC:
            phis += [(feat, "max", None), (feat, "min", None)]
    return phis


# ------------------------------------------------------------------ mechanisms: fit on training, predict on a test
def keep_apply(g, blocks, fs, phi):
    out = np.full_like(g, BG)
    for b, f in zip(blocks, fs):
        if phi_holds(phi, f, fs):
            for x in b:
                out[x] = g[x]
    return out


def crop_apply(g, blocks, fs, phi, variant):
    sel = [b for b, f in zip(blocks, fs) if phi_holds(phi, f, fs)]
    if len(sel) != 1:
        return None
    b = sel[0]
    rs, cs = [r for r, _ in b], [c for _, c in b]
    r0, r1, c0, c1 = min(rs), max(rs), min(cs), max(cs)
    if variant == "box":
        return g[r0:r1 + 1, c0:c1 + 1].copy()
    out = np.full((r1 - r0 + 1, c1 - c0 + 1), BG, dtype=g.dtype)
    for r, c in b:
        out[r - r0, c - c0] = g[r, c]
    return out


def recolour_fit(train_parts, feat):
    """train_parts: list of (I, O, blocks, fs). Returns the lookup g or None."""
    lut = {}
    for I, O, blocks, fs in train_parts:
        if I.shape != O.shape:
            return None
        covered = np.zeros(I.shape, bool)
        for b, f in zip(blocks, fs):
            cols = {int(O[x]) for x in b}
            if len(cols) != 1:
                return None
            c = cols.pop()
            if lut.setdefault(f[feat] if feat != "shape" else f["shape"], c) != c:
                return None
            for x in b:
                covered[x] = True
        if (O[~covered] != BG).any():
            return None
    return lut


def recolour_apply(g, blocks, fs, feat, lut):
    out = np.full_like(g, BG)
    for b, f in zip(blocks, fs):
        key = f[feat]
        if key not in lut:
            return None            # attribute value never seen in training: not determined by the data
        for x in b:
            out[x] = lut[key]
    return out


def explanations(train, rule, mechs=("KEEP", "RECOLOUR", "CROP")):
    """All (rule, mechanism, params) consistent with every training pair under one partition rule."""
    parts = []
    for I, O in train:
        blocks = partition(I, rule)
        parts.append((I, O, blocks, features(blocks, I)))
    phis = candidate_phis([p[3] for p in parts])
    found = []
    same = all(I.shape == O.shape for I, O in train)
    if "KEEP" in mechs and same:
        for phi in phis:
            if all(np.array_equal(keep_apply(I, b, f, phi), O) for I, O, b, f in parts):
                found.append((rule, "KEEP", phi))
    if "RECOLOUR" in mechs and same:
        for feat in FEATURES:
            lut = recolour_fit(parts, feat)
            if lut is not None:
                found.append((rule, "RECOLOUR", (feat, tuple(sorted(lut.items(), key=repr)))))
    if "CROP" in mechs:
        for variant in ("block", "box"):
            for phi in phis:
                ok = True
                for I, O, b, f in parts:
                    out = crop_apply(I, b, f, phi, variant)
                    if out is None or not np.array_equal(out, O):
                        ok = False
                        break
                if ok:
                    found.append((rule, f"CROP-{variant}", phi))
    return found


def predict(expl, g):
    rule, mech, params = expl
    blocks = partition(g, rule)
    fs = features(blocks, g)
    if mech == "KEEP":
        return keep_apply(g, blocks, fs, params)
    if mech == "RECOLOUR":
        feat, items = params
        return recolour_apply(g, blocks, fs, feat, dict(items))
    return crop_apply(g, blocks, fs, params, mech.split("-")[1])


# ------------------------------------------------------------------ selection laws
def law_K(train, rule):
    """Every output block (same rule applied to the output) has an input block with exactly the same cells."""
    for I, O in train:
        if I.shape != O.shape:
            return False
        ins = set(partition(I, rule))
        if any(b not in ins for b in partition(O, rule)):
            return False
    return True


def law_C(train, rule):
    """Each output, translated, equals one input block (cells and colours)."""
    for I, O in train:
        ys, xs = np.nonzero(O != BG)
        if not len(ys):
            return False
        pat = {(int(r) - ys.min(), int(c) - xs.min()): int(O[r, c]) for r, c in zip(ys, xs)}
        ok = False
        for b in partition(I, rule):
            r0, c0 = min(r for r, _ in b), min(c for _, c in b)
            if {(r - r0, c - c0): int(I[r, c]) for r, c in b} == pat:
                ok = True
                break
        if not ok:
            return False
    return True


def law_residual(train, rule):
    """Same-size pairs; the cells changed by the identity explanation are exactly a union of input blocks."""
    for I, O in train:
        if I.shape != O.shape:
            return False
        changed = {(int(r), int(c)) for r, c in zip(*np.nonzero(I != O))}
        if not changed:
            continue
        blocks = partition(I, rule)
        union = set()
        for b in blocks:
            if b & changed:
                if not b <= changed:
                    return False
                union |= b
        if union != changed:
            return False
    return True
