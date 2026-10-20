"""Mission 04, task 1: a complete uniqueness check for M-DISC (Mission 03), and a fixed solver.

Mission 03's `m_disc.solve(unique=True)` answered when every minimum cover it ENUMERATED predicted the same test
output. The enumeration was incomplete in three ways (audit, mission-04/AUDIT_M03_UNIQUENESS.md):
  U1  only coverage groups not strictly dominated by another group were searched;
  U2  at most 200 minimum covers were kept, without a flag;
  U3  the MDL tie-break looked at the first 256 variant combinations only.

`check_unique` decides the question exactly with Z3, over EVERY admissible piece: is there a set of exactly k*
pieces (k* = the minimum cover size) that covers every non-background training output cell and predicts a
different test output (or a conflicting / undetermined one)? SAT -> AMBIGUOUS (with a witness), UNSAT -> UNIQUE,
solver unknown or timeout -> UNKNOWN. Uniqueness is always relative to the stated priors: the hypothesis class
(<= 4 pieces, the matrices and translations of m_disc), the simplest size rule, minimum size (Occam), and either
the identity extension of colour functions to unseen colours ("prior" mode) or no extension ("strict" mode).

Mission 03 code is imported unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import z3

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "mission-03" / "experiments" / "arc"))
import m_disc as M  # noqa: E402

BG = M.BG
TIMEOUT_MS = 60_000


def test_image(piece, I, shape, colour_mode):
    """dict cell -> colour, or None if the piece maps a source colour that the data do not determine."""
    Mx, E, sigma = piece
    ys, xs = np.nonzero(I != BG)
    cs = I[ys, xs]
    (a, b), (c, d) = Mx
    t = M.abs_t(E, I)
    X, Y = a * xs + b * ys + t[0], c * xs + d * ys + t[1]
    inb = (X >= 0) & (X < shape[1]) & (Y >= 0) & (Y < shape[0])
    ident = all(k == v for k, v in sigma.items())
    out = {}
    for x, y, col in zip(X[inb], Y[inb], cs[inb]):
        col = int(col)
        if col in sigma:
            out[(int(y), int(x))] = sigma[col]
        elif colour_mode == "prior" and ident:
            out[(int(y), int(x))] = col
        else:
            return None
    return out


def all_min_covers_exhaustive(groups, need, kmax=M.KMAX, limit=None):
    """Reference enumerator for small cases: every minimum cover over ALL groups (no dominance pruning, no cap
    unless `limit`). Returns (covers, complete)."""
    keys = [g[0] for g in groups]
    best, found, complete = None, [], True

    def rec(chosen, cov):
        nonlocal best, complete
        if best is not None and len(chosen) > best:
            return
        miss = need & ~cov
        if not miss:
            if best is None or len(chosen) < best:
                best, found[:] = len(chosen), []
            if limit is None or len(found) < limit:
                found.append(tuple(sorted(chosen)))
            else:
                complete = False
            return
        if len(chosen) == kmax:
            return
        low = miss & -miss
        for i, b in enumerate(keys):
            if b & low and i not in chosen:
                rec(chosen + [i], cov | b)

    rec([], 0)
    return sorted(set(found)), complete


def check_unique(pieces, train, I, shape, k_star, ref, colour_mode="prior", dl=None, dl_star=None):
    """Exact check over every admissible piece. ref: reference prediction (array). Returns (status, witness).
    If dl/dl_star are given, only covers of size k_star AND description length dl_star are considered."""
    cov = [M.coverage(p, train) for p in pieces]
    need = M.requirement(train)
    imgs = [test_image(p, I, shape, colour_mode) for p in pieces]
    y = [z3.Bool(f"y{i}") for i in range(len(pieces))]
    s = z3.Solver()
    s.set("timeout", TIMEOUT_MS)
    bit = 0
    n = need
    while n:
        if n & 1:
            covering = [y[i] for i, c in enumerate(cov) if c >> bit & 1]
            s.add(z3.Or(covering) if covering else z3.BoolVal(False))
        n >>= 1
        bit += 1
    s.add(z3.PbEq([(v, 1) for v in y], k_star))
    if dl is not None:
        s.add(z3.Sum([z3.If(y[i], dl[i], 0) for i in range(len(pieces))]) == dl_star)
    diffs = []
    undetermined = [y[i] for i, im in enumerate(imgs) if im is None]
    diffs += undetermined
    hits = {}
    for i, im in enumerate(imgs):
        if im is None:
            continue
        for cell, col in im.items():
            hits.setdefault(cell, {}).setdefault(col, []).append(y[i])
    H, W = shape
    for r in range(H):
        for c in range(W):
            want = int(ref[r, c])
            h = hits.get((r, c), {})
            if want == BG:
                diffs += [v for vs in h.values() for v in vs]
            else:
                diffs.append(z3.Not(z3.Or(h[want])) if want in h else z3.BoolVal(True))
                diffs += [v for col, vs in h.items() if col != want for v in vs]
    s.add(z3.Or(diffs) if diffs else z3.BoolVal(False))
    res = s.check()
    if res == z3.unsat:
        return "UNIQUE", None
    if res == z3.sat:
        m = s.model()
        return "AMBIGUOUS", [i for i in range(len(pieces)) if z3.is_true(m.eval(y[i], model_completion=True))]
    return "UNKNOWN", None


def solve_fixed(train, tests, colour_mode="prior", tiebreak=None, anchor_far=True, mats_kind="full"):
    """M-DISC with a complete uniqueness decision. Returns (outputs, info); None = abstain / UNKNOWN."""
    rules = M.size_rules(train)
    if rules is None:
        return [None] * len(tests), {"reason": "no size rule"}
    mats = [tuple(tuple(k * v for v in row) for row in Mx) for k in (1, 2, 3) for Mx in M.D4M] if mats_kind == "full" \
        else [((k, 0), (0, k)) for k in (1, 2, 3)]
    pieces = M.admissible_pieces(train, mats, M.translations(anchor_far))
    need = M.requirement(train)
    if not need:
        return [None] * len(tests), {"reason": "empty outputs"}
    groups = {}
    for p in pieces:
        groups.setdefault(M.coverage(p, train), []).append(p)
    glist = list(groups.items())
    covers = M.min_covers(glist, need)          # the minimum SIZE is exact even with dominance pruning
    info = {"pieces": len(pieces), "coverage_groups": len(glist)}
    if not covers:
        return [None] * len(tests), dict(info, reason="no cover")
    k_star = len(covers[0])
    info["cover_size"] = k_star
    dl = [M.piece_dl(p) for p in pieces] if tiebreak == "mdl" else None
    outs, statuses = [], []
    for I in tests:
        shape = M.apply_size(rules, I)
        if shape is None:
            outs.append(None)
            statuses.append("size rule ambiguous")
            continue
        if tiebreak == "mdl":
            # minimum description length among covers of size k_star, found exactly with Z3 Optimize
            cov = [M.coverage(p, train) for p in pieces]
            y = [z3.Bool(f"y{i}") for i in range(len(pieces))]
            o = z3.Optimize()
            o.set("timeout", TIMEOUT_MS)
            bit, n = 0, need
            while n:
                if n & 1:
                    o.add(z3.Or([y[i] for i, c in enumerate(cov) if c >> bit & 1]))
                n >>= 1
                bit += 1
            o.add(z3.PbEq([(v, 1) for v in y], k_star))
            # only covers whose test prediction is defined can be the shortest answer
            imgs = [test_image(p, I, shape, colour_mode) for p in pieces]
            for i, im in enumerate(imgs):
                if im is None:
                    o.add(z3.Not(y[i]))
            h = o.minimize(z3.Sum([z3.If(y[i], dl[i], 0) for i in range(len(pieces))]))
            if o.check() != z3.sat:
                outs.append(None)
                statuses.append("UNKNOWN (no defined shortest cover)")
                continue
            m = o.model()
            chosen = [pieces[i] for i in range(len(pieces)) if z3.is_true(m.eval(y[i], model_completion=True))]
            dl_star = sum(M.piece_dl(p) for p in chosen)
            ref = M.predict(chosen, I, shape)
            if ref is None:
                outs.append(None)
                statuses.append("conflict in shortest cover")
                continue
            st, _ = check_unique(pieces, train, I, shape, k_star, ref, colour_mode, dl=dl, dl_star=dl_star)
        else:
            ref = None
            for cv in covers:
                ref = M.predict([glist[i][1][0] for i in cv], I, shape)
                if ref is not None:
                    break
            if ref is None:
                outs.append(None)
                statuses.append("conflict")
                continue
            if colour_mode == "strict" and any(test_image(glist[i][1][0], I, shape, "strict") is None for i in cv):
                outs.append(None)
                statuses.append("UNKNOWN (colour not determined by the data)")
                continue
            st, _ = check_unique(pieces, train, I, shape, k_star, ref, colour_mode)
        statuses.append(st)
        outs.append(ref if st == "UNIQUE" else None)
    info["uniqueness"] = statuses
    info["reason"] = "answered" if all(o is not None for o in outs) else "/".join(sorted(set(statuses)))
    return outs, info
