"""M-DISC: the Mission 03 discovery constructor, transferred to ARC grids (protocol amendment 9).

Hypothesis class: a union map over non-background cells. The output is the union of at most 4 size-generic
affine pieces; a piece sends input cell p to M p + t, where M is a D4 matrix scaled by 1, 2 or 3, and each
component of t is u*W + v*H + d (W, H = input width and height; u, v in {0, 1, 2}; d in -3..3); images that
fall outside the output are clipped. Each piece carries a colour function learned from the training pairs.
The output size follows a generic affine size rule. Background (colour 0) is "off".

Construction (no weights, no task-specific code):
  1. size rule: all simplest (a, b, c) with H' = aH + bW + c (same for W') consistent with every pair;
  2. pieces: every (M, t) whose images land only on non-background output cells of the right colour, with one
     colour function across all pairs (the elimination criterion of Mission 03);
  3. Occam: all minimum covers of the non-background output cells by at most 4 pieces;
  4. answer only if every minimum cover (and every behaviourally different piece with the same coverage)
     predicts the same test output; otherwise abstain.

Ablations: A1 translations anchored at 0 only (u = v = 0); A2 matrices restricted to scalings of the identity;
A3 the first minimum cover, without the uniqueness check. Ambiguity is a lower bound: pieces whose coverage is
strictly dominated by another piece are not searched (they can always be swapped for the dominating one).
"""

from __future__ import annotations

import itertools

import numpy as np

BG = 0
D4M = [((1, 0), (0, 1)), ((0, -1), (1, 0)), ((-1, 0), (0, -1)), ((0, 1), (-1, 0)),
       ((-1, 0), (0, 1)), ((1, 0), (0, -1)), ((0, 1), (1, 0)), ((0, -1), (-1, 0))]
UV = (0, 1, 2)
DD = tuple(range(-3, 4))
KMAX = 4


def size_rules(pairs):
    """Simplest affine size rules consistent with every pair, for rows and columns separately."""
    out = []
    for axis in (0, 1):
        cands = []
        for a in range(4):
            for b in range(4):
                cs = range(-2, 3) if a + b else range(1, 31)
                for c in cs:
                    if all(a * I.shape[0] + b * I.shape[1] + c == O.shape[axis] for I, O in pairs):
                        cands.append((a, b, c))
        if not cands:
            return None
        score = lambda r: (int(r[0] > 0) + int(r[1] > 0) + int(r[2] != 0), abs(r[2]))
        best = min(score(r) for r in cands)
        out.append([r for r in cands if score(r) == best])
    return out


def apply_size(rules, I):
    hs = {a * I.shape[0] + b * I.shape[1] + c for a, b, c in rules[0]}
    ws = {a * I.shape[0] + b * I.shape[1] + c for a, b, c in rules[1]}
    if len(hs) != 1 or len(ws) != 1:
        return None
    h, w = hs.pop(), ws.pop()
    return (h, w) if h > 0 and w > 0 else None


def translations(anchor_far=True):
    uv = UV if anchor_far else (0,)
    return [(ux, vx, dx, uy, vy, dy) for ux in uv for vx in uv for dx in DD for uy in uv for vy in uv for dy in DD]


def abs_t(E, I):
    H, W = I.shape
    ux, vx, dx, uy, vy, dy = E
    return ux * W + vx * H + dx, uy * W + vy * H + dy


def piece_image(M, t, I, out_shape, sigma=None):
    """Cells hit by the piece and their colours: dict (row, col) -> colour (None if sigma lacks a colour)."""
    ys, xs = np.nonzero(I != BG)
    cs = I[ys, xs]
    (a, b), (c, d) = M
    X = a * xs + b * ys + t[0]
    Y = c * xs + d * ys + t[1]
    inb = (X >= 0) & (X < out_shape[1]) & (Y >= 0) & (Y < out_shape[0])
    res = {}
    ident = sigma is not None and all(k == v for k, v in sigma.items())
    for x, y, col in zip(X[inb], Y[inb], cs[inb]):
        if sigma is None:
            res[(int(y), int(x))] = col
        else:   # Occam: a colour function that is the identity on every observed colour extends as the identity
            res[(int(y), int(x))] = sigma.get(int(col), int(col) if ident else None)
    return res


def admissible_pieces(pairs, mats, Es):
    """All (M, E, sigma) consistent with every training pair."""
    found = []
    for M in mats:
        (a, b), (c, d) = M
        per_pair = []
        for I, O in pairs:
            ys, xs = np.nonzero(I != BG)
            per_pair.append((xs, ys, I[ys, xs], a * xs + b * ys, c * xs + d * ys))
        cache = [dict() for _ in pairs]
        for E in Es:
            sigma, ok, hits = {}, True, 0
            for k, (I, O) in enumerate(pairs):
                t = abs_t(E, I)
                if t not in cache[k]:
                    xs, ys, cs, ax, ay = per_pair[k]
                    X, Y = ax + t[0], ay + t[1]
                    inb = (X >= 0) & (X < O.shape[1]) & (Y >= 0) & (Y < O.shape[0])
                    if not inb.any():
                        cache[k][t] = ("empty", None)
                    else:
                        tgt = O[Y[inb], X[inb]]
                        if (tgt == BG).any():
                            cache[k][t] = ("bad", None)
                        else:
                            cache[k][t] = ("ok", (cs[inb], tgt))
                status, data = cache[k][t]
                if status == "bad":
                    ok = False
                    break
                if status == "ok":
                    hits += 1
                    for s, g in zip(*data):
                        s, g = int(s), int(g)
                        if sigma.setdefault(s, g) != g:
                            ok = False
                            break
                    if not ok:
                        break
            if ok and hits:
                found.append((M, E, dict(sigma)))
    return found


def coverage(piece, pairs):
    M, E, sigma = piece
    bits, off = 0, 0
    for I, O in pairs:
        img = piece_image(M, abs_t(E, I), I, O.shape)
        for (y, x) in img:
            bits |= 1 << (off + y * O.shape[1] + x)
        off += O.size
    return bits


def requirement(pairs):
    bits, off = 0, 0
    for I, O in pairs:
        ys, xs = np.nonzero(O != BG)
        for y, x in zip(ys, xs):
            bits |= 1 << (off + int(y) * O.shape[1] + int(x))
        off += O.size
    return bits


def predict(cover, I, shape):
    out = np.full(shape, BG, dtype=int)
    owner = {}
    for M, E, sigma in cover:
        img = piece_image(M, abs_t(E, I), I, shape, sigma)
        for cell, col in img.items():
            if col is None:
                return None          # a source colour never seen in training
            if owner.setdefault(cell, col) != col:
                return None          # two pieces disagree on a cell
            out[cell] = col
    return out


def min_covers(groups, need, kmax=KMAX, cap=200):
    """groups: list of (coverage bits, [pieces with identical coverage]). Minimum covers of `need`."""
    keys = [g[0] for g in groups]
    maximal = [i for i, b in enumerate(keys) if not any((b | o) == o and o != b for o in keys)]
    best, found = None, []

    def rec(chosen, cov):
        nonlocal best
        if best is not None and len(chosen) > best:
            return
        miss = need & ~cov
        if not miss:
            if best is None or len(chosen) < best:
                best, found[:] = len(chosen), []
            if len(found) < cap:
                found.append(tuple(sorted(chosen)))
            return
        if len(chosen) == kmax:
            return
        low = miss & -miss
        for i in maximal:
            if keys[i] & low and i not in chosen:
                rec(chosen + [i], cov | keys[i])

    rec([], 0)
    return sorted(set(found))


def piece_dl(piece):
    """Description length of a piece: non-identity / scaled matrix, plus every non-zero anchor or offset term."""
    M, E, _ = piece
    k = abs(M[0][0]) + abs(M[0][1])
    base = tuple(tuple(v // k for v in row) for row in M)
    return int(base != ((1, 0), (0, 1))) + int(k > 1) + sum(1 for v in E if v != 0)


def solve(train, tests, anchor_far=True, mats_kind="full", unique=True, tiebreak=None):
    """train: list of (I, O) arrays; tests: list of input arrays. Returns list of outputs (None = abstain)."""
    rules = size_rules(train)
    if rules is None:
        return [None] * len(tests), {"reason": "no size rule"}
    mats = [tuple(tuple(k * v for v in row) for row in M) for k in (1, 2, 3) for M in D4M] if mats_kind == "full" \
        else [((k, 0), (0, k)) for k in (1, 2, 3)]
    pieces = admissible_pieces(train, mats, translations(anchor_far))
    need = requirement(train)
    if not need:
        return [None] * len(tests), {"reason": "empty outputs"}
    groups = {}
    for p in pieces:
        groups.setdefault(coverage(p, train), []).append(p)
    glist = list(groups.items())
    covers = min_covers(glist, need)
    info = {"pieces": len(pieces), "coverage_groups": len(glist), "min_covers": len(covers),
            "cover_size": len(covers[0]) if covers else None}
    if not covers:
        return [None] * len(tests), dict(info, reason="no cover")
    outs = []
    for I in tests:
        shape = apply_size(rules, I)
        if shape is None:
            outs.append(None)
            continue
        preds = set()
        options = covers[:1] if not unique else covers
        for cv in options:
            choice_sets = [glist[i][1] if unique else glist[i][1][:1] for i in cv]
            if np.prod([len(c) for c in choice_sets]) > 256:
                preds.add(None)      # too many behaviourally distinct variants to check: treat as ambiguous
                break
            for combo in itertools.product(*choice_sets):
                p = predict(combo, I, shape)
                preds.add(None if p is None else p.tobytes() + bytes(str(p.shape), "ascii"))
                if not unique:
                    break
            if not unique:
                break
        if len(preds) == 1 and None not in preds:
            outs.append(predict([glist[i][1][0] for i in options[0]], I, shape))
        elif tiebreak == "mdl":
            # amendment 10: among behaviourally different minimum explanations, keep the shortest description
            scored = {}
            for cv in covers:
                # description length is additive over pieces, so each group contributes only its shortest variants
                short = []
                for i in cv:
                    m = min(piece_dl(q) for q in glist[i][1])
                    short.append([q for q in glist[i][1] if piece_dl(q) == m])
                for combo in itertools.islice(itertools.product(*short), 256):
                    p = predict(combo, I, shape)
                    if p is not None:
                        dl = sum(piece_dl(q) for q in combo)
                        key = p.tobytes() + bytes(str(p.shape), "ascii")
                        scored[key] = min(scored.get(key, (10 ** 9, None))[0], dl), p
            if scored:
                best = min(v[0] for v in scored.values())
                top = [v[1] for v in scored.values() if v[0] == best]
                outs.append(top[0] if len(top) == 1 else None)
            else:
                outs.append(None)
        else:
            outs.append(None)
    info["reason"] = "answered" if all(o is not None for o in outs) else "ambiguous or unseen colour"
    return outs, info
