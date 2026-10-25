"""Gate 4 candidates (G4_CANDIDATE_LOG.md). At most three; each is developed on development data only.

K1 (route A, discovery inside an explicit search space): a logistic edge rule over features measured independently of
any connectome -- soma distance, birth times, lineage distance (Sulston), neurotransmitter identity (NemaNode),
sensory / inter / motor class, bilateral homology, age. Feature blocks are added greedily while they improve the
mean held-out log-likelihood of the development proxy tasks; the selected blocks and their coefficients are the
"discovered" rule, with its description length.

K2 (route A / C, memory with a compact prior): Beta-binomial shrinkage of the memorised edges towards a compact rule,
p_ij = (k_ij + kappa * q_ij) / (N + kappa), k_ij the (age-weighted) number of training data sets with the edge, N their
(effective) number, q_ij a rule's probability; kappa on the development proxies. It asks whether a rule adds
information to memory (criterion S-c) in the simplest probabilistic form.
"""

from __future__ import annotations

import json

import numpy as np
from sklearn.linear_model import LogisticRegression

from . import lineage as L
from . import metrics as M
from .models import Ctx, age_weights, logit
from .raw import path

NT_GROUP = {"a": "ach", "l": "glu", "g": "gaba", "d": "mono", "s": "mono", "o": "mono", "t": "mono"}


def nt_codes(cells):
    tab = {c["name"]: c["neurotransmitter"] for c in json.loads(path("nema_cells").read_text())}
    groups = ["ach", "glu", "gaba", "mono", "other"]
    out = []
    for c in cells:
        code = tab.get(c, "u")
        g = next((NT_GROUP[x] for x in code if x in NT_GROUP), "other")
        out.append(groups.index(g))
    return np.array(out), groups


class FeatureBank:
    """Feature blocks over the ordered pairs of a Ctx (independent of connectomes)."""

    def __init__(self, ctx: Ctx):
        I, J = ctx.I, ctx.J
        D, P = L.distance_matrix(ctx.cells)
        nt, _ = nt_codes(ctx.cells)
        oh5, oh3 = np.eye(5), np.eye(3)
        bi, bj = ctx.birth[I] / 1000.0, ctx.birth[J] / 1000.0
        self.static = {
            "dist": np.c_[ctx.d, np.log(ctx.d + 1e-3)],
            "birth": np.c_[bi, bj, np.maximum(bi, bj), np.abs(bi - bj)],
            "lineage": np.c_[np.log1p(D[I, J]), P[I, J] / 12.0],
            "coarse": (oh3[ctx.coarse[I]][:, :, None] * oh3[ctx.coarse[J]][:, None, :]).reshape(len(I), 9),
            "nt_pre_post": np.c_[oh5[nt[I]], oh5[nt[J]]],
            "nt_pair": (oh5[nt[I]][:, :, None] * oh5[nt[J]][:, None, :]).reshape(len(I), 25),
            "homolog": (ctx.lr[I] == ctx.lr[J]).astype(float)[:, None],
            "same_class_nt": np.c_[(ctx.coarse[I] == ctx.coarse[J]), (nt[I] == nt[J])].astype(float),
            "lineage_x_dist": (np.log1p(D[I, J]) * np.log(ctx.d + 1e-3))[:, None],
        }
        self.n_pairs = len(I)

    def matrix(self, blocks, age_h):
        cols = [self.static[b] for b in blocks if b != "age"]
        if "age" in blocks:
            cols.append(np.full((self.n_pairs, 1), age_h / 50.0))
        return np.hstack(cols) if cols else np.zeros((self.n_pairs, 0))


class K1:
    name = "K1-independent-rule"

    def __init__(self, blocks, C_reg=1.0):
        self.blocks, self.C_reg = list(blocks), C_reg

    def fit(self, ctx, train, bank=None):
        self.bank = bank or FeatureBank(ctx)
        X = np.vstack([self.bank.matrix(self.blocks, t.age_h)[ctx.pair_mask(t.present)] for t in train])
        y = np.concatenate([ctx.flat(t.A)[ctx.pair_mask(t.present)] for t in train])
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-9
        self.lr = LogisticRegression(C=self.C_reg, max_iter=5000).fit((X - self.mu) / self.sd, y)
        self.n_params = X.shape[1] + 1
        return self

    def predict(self, ctx, age_h):
        X = (self.bank.matrix(self.blocks, age_h) - self.mu) / self.sd
        return self.lr.predict_proba(X)[:, 1]


def forward_select(ctx, proxies, candidates_blocks, base_blocks=(), max_blocks=10, min_gain=1e-4, bank=None):
    """Greedy forward selection of feature blocks by mean held-out LL (bits / pair) over the proxy tasks.
    proxies: list of (train list of Conn, test Conn). Returns (selected blocks, trace)."""
    bank = bank or FeatureBank(ctx)

    def score(blocks):
        out = []
        for train, test in proxies:
            m = ctx.pair_mask(test.present)
            p = K1(blocks).fit(ctx, train, bank).predict(ctx, test.age_h)
            out.append(M.ll_bits(p[m], ctx.flat(test.A)[m]).mean())
        return float(np.mean(out))

    sel = list(base_blocks)
    best = score(sel) if sel else -np.inf
    trace = [(list(sel), best)]
    while len(sel) < max_blocks:
        trial = [(score(sel + [b]), b) for b in candidates_blocks if b not in sel]
        if not trial:
            break
        s, b = max(trial)
        if s - best < min_gain:
            break
        sel.append(b)
        best = s
        trace.append((list(sel), best))
    return sel, trace


class K2:
    """Shrinkage of memory towards a rule's probabilities."""

    def __init__(self, kappa, name="K2-shrink"):
        self.kappa, self.name = kappa, name

    def predict(self, ctx, train, age_h, q, interpolate):
        if interpolate:
            w = age_weights([t.age_h for t in train], age_h)
            k = sum(wi * ctx.flat(t.A) for wi, t in zip(w, train) if wi > 0)
            n = 1.0
        else:
            k = sum(ctx.flat(t.A) for t in train)
            n = float(len(train))
        return np.clip((k + self.kappa * q) / (n + self.kappa), 1e-6, 1 - 1e-6)


def fit_kappa(proxies, grid=(0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0)):
    """proxies: list of (k_ij, n, q_ij, y) over evaluated pairs. Returns the kappa with the best mean LL."""
    best = None
    for kap in grid:
        ll = np.mean([M.ll_bits(np.clip((k + kap * q) / (n + kap), 1e-6, 1 - 1e-6), y).mean() for k, n, q, y in proxies])
        if best is None or ll > best[0]:
            best = (ll, kap)
    return best[1], best[0]


__all__ = ["FeatureBank", "K1", "K2", "forward_select", "fit_kappa", "logit"]
