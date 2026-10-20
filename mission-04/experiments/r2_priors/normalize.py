"""Mission 04 P-R2 (protocol amendment 5): representation priors as normalizations wrapped around the frozen solvers.

A representation is (bg, col, edge):
  bg    "zero" | "mode" | "border" | ("const", c)   background colour b of each grid, realised by swapping 0 <-> b
  col   "id" | "rank"                               rank: non-background colours renumbered by frequency (desc)
  edge  "grid" | "content"                          content: the reference frame is the input's content box
Training inputs and outputs of a pair use the colour map of that pair's input; a test prediction is mapped back
with the inverse map of its test input. The solvers never see the original colours or frame.
"""

from __future__ import annotations

import numpy as np

NC = 10


def background(I, bg):
    if bg == "zero":
        return 0
    if bg == "mode":
        return int(np.bincount(I.ravel(), minlength=NC).argmax())
    if bg == "border":
        edge = np.concatenate([I[0], I[-1], I[:, 0], I[:, -1]])
        return int(np.bincount(edge, minlength=NC).argmax())
    return int(bg[1])


def colour_map(I, bg, col):
    """lut with lut[original colour] = normalised colour (a bijection of 0..9)."""
    b = background(I, bg)
    swap = np.arange(NC)
    swap[0], swap[b] = b, 0
    if col == "id":
        return swap
    J = swap[I]
    counts = np.bincount(J.ravel(), minlength=NC)
    present = sorted((c for c in range(1, NC) if counts[c] > 0), key=lambda c: (-counts[c], c))
    absent = [c for c in range(1, NC) if counts[c] == 0]
    rank = np.zeros(NC, dtype=int)
    for i, c in enumerate(present + absent):
        rank[c] = i + 1
    return rank[swap]


def content_box(J):
    ys, xs = np.nonzero(J != 0)
    if not len(ys):
        return None
    return int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1


def apply_rep(train, test_inputs, rep):
    """Returns (train2, tests2, back) or None when the representation does not apply to this task.
    back(k, prediction) maps a prediction for test input k back to the original colours and frame (or None)."""
    bg, col, edge = rep
    luts = [colour_map(I, bg, col) for I, _ in train]
    train2 = [(lut[I], lut[O]) for lut, (I, O) in zip(luts, train)]
    tluts = [colour_map(I, bg, col) for I in test_inputs]
    tests2 = [lut[I] for lut, I in zip(tluts, test_inputs)]
    invs = [np.argsort(lut) for lut in tluts]
    if edge == "grid":
        return train2, tests2, lambda k, p: None if p is None else invs[k][p]
    same = all(I.shape == O.shape for I, O in train2)
    boxes = [content_box(I) for I, _ in train2]
    tboxes = [content_box(I) for I in tests2]
    if any(b is None for b in boxes):
        return None
    sub = []
    for (I, O), (r0, r1, c0, c1) in zip(train2, boxes):
        if same:
            outside = np.ones(I.shape, bool)
            outside[r0:r1, c0:c1] = False
            if not np.array_equal(I[outside], O[outside]):
                return None          # the outside of the content box is not invariant: the frame is not the content box
            sub.append((I[r0:r1, c0:c1], O[r0:r1, c0:c1]))
        else:
            sub.append((I[r0:r1, c0:c1], O))
    tsub = [None if b is None else I[b[0]:b[1], b[2]:b[3]] for I, b in zip(tests2, tboxes)]
    if any(t is None for t in tsub):
        return None

    def back(k, p):
        if p is None:
            return None
        if same:
            r0, r1, c0, c1 = tboxes[k]
            if p.shape != (r1 - r0, c1 - c0):
                return None
            full = tests2[k].copy()
            full[r0:r1, c0:c1] = p
            p = full
        return invs[k][p]

    return sub, tsub, back


def induced_backgrounds(train, test_inputs, bg):
    """Per-grid background colours a background rule induces; used to deduplicate candidates."""
    return tuple(background(I, bg) for I, _ in train) + tuple(background(I, bg) for I in test_inputs)


def candidates(train, test_inputs):
    """BG-pool candidates: zero, mode, border, and every colour present in every training input; deduplicated by the
    backgrounds they induce on all grids of the task."""
    common = set(range(NC))
    for I, _ in train:
        common &= set(np.unique(I).tolist())
    cands = ["zero", "mode", "border"] + [("const", c) for c in sorted(common) if c != 0]
    seen, out = set(), []
    for c in cands:
        key = induced_backgrounds(train, test_inputs, c)
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out
