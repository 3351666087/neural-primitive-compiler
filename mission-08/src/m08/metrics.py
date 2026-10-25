"""Scores for edge-probability predictions (PRE_REGISTRATION.md section 2.3) and the block bootstrap by presynaptic
neuron (section 7). All functions take flat arrays over the evaluated ordered pairs."""

from __future__ import annotations

import numpy as np

LN2 = np.log(2.0)


def ll_bits(p, y, eps=1e-9):
    p = np.clip(p, eps, 1 - eps)
    return (y * np.log(p) + (1 - y) * np.log1p(-p)) / LN2


def auroc(score, y, w=None):
    """Mann-Whitney AUROC with average ranks for ties; optional integer weights (bootstrap multiplicities)."""
    w = np.ones_like(score) if w is None else w
    order = np.argsort(score, kind="mergesort")
    s, yy, ww = score[order], y[order], w[order]
    # average rank of each tie block, weighted
    cw = np.cumsum(ww)
    uniq, start = np.unique(s, return_index=True)
    end = np.r_[start[1:], len(s)] - 1
    lo = np.r_[0, cw[:-1]][start]
    rank_block = (lo + cw[end] + 1) / 2.0
    ranks = np.repeat(rank_block, end - start + 1)
    npos = np.sum(ww * yy)
    nneg = np.sum(ww * (1 - yy))
    if npos == 0 or nneg == 0:
        return np.nan
    return float((np.sum(ww * yy * ranks) - npos * (npos + 1) / 2) / (npos * nneg))


def auprc(score, y, w=None):
    """Average precision (step-wise, sklearn convention), with tied scores handled as one threshold."""
    w = np.ones_like(score) if w is None else w
    order = np.argsort(-score, kind="mergesort")
    s, yy, ww = score[order], y[order], w[order]
    tp = np.cumsum(ww * yy)
    fp = np.cumsum(ww * (1 - yy))
    last = np.r_[np.diff(s) != 0, True]                    # end of each tie block
    tp, fp = tp[last], fp[last]
    total = tp[-1]
    if total == 0:
        return np.nan
    prec = tp / (tp + fp)
    rec = tp / total
    return float(np.sum(np.diff(np.r_[0.0, rec]) * prec))


def brier(p, y, w=None):
    w = np.ones_like(p) if w is None else w
    return float(np.sum(w * (p - y) ** 2) / np.sum(w))


def ece(p, y, bins=10):
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    out = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            out += m.mean() * abs(p[m].mean() - y[m].mean())
    return float(out)


def summary(p, y, base_p=None):
    """Point estimates: mean per-pair LL (bits), LL gain over `base_p`, AUROC, AUPRC, Brier, ECE."""
    ll = ll_bits(p, y)
    out = {"ll_bits_per_pair": float(ll.mean()), "auroc": auroc(p, y), "auprc": auprc(p, y), "brier": brier(p, y),
           "ece": ece(p, y), "n_pairs": int(len(y)), "n_pos": int(y.sum())}
    if base_p is not None:
        out["ll_gain_bits_per_pair"] = float((ll - ll_bits(base_p, y)).mean())
    return out


def block_bootstrap(groups, n_boot=2000, seed=20261025):
    """Yield integer weight vectors over pairs: resample the unique `groups` (e.g. presynaptic neurons) with
    replacement; each pair gets the multiplicity of its group."""
    rng = np.random.default_rng(seed)
    u, inv = np.unique(groups, return_inverse=True)
    for _ in range(n_boot):
        mult = np.bincount(rng.integers(0, len(u), len(u)), minlength=len(u))
        yield mult[inv].astype(float)


def boot_diff(fun, a, b, y, groups, n_boot=2000, seed=20261025):
    """Point difference fun(a) - fun(b) and its 95 % percentile interval under the block bootstrap.
    fun(score, y, w) -> scalar."""
    point = fun(a, y, None) - fun(b, y, None)
    diffs = [fun(a, y, w) - fun(b, y, w) for w in block_bootstrap(groups, n_boot, seed)]
    lo, hi = np.nanpercentile(diffs, [2.5, 97.5])
    return {"diff": float(point), "lo": float(lo), "hi": float(hi)}


def wll(p, y, w=None):
    """Weighted mean per-pair LL in bits (for boot_diff)."""
    w = np.ones_like(p) if w is None else w
    return float(np.sum(w * ll_bits(p, y)) / np.sum(w))


def bern_entropy_bits(p):
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return float(np.sum(-(p * np.log2(p) + (1 - p) * np.log2(1 - p))))
