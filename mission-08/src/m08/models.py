"""Structural models of PRE_REGISTRATION.md section 2.2. Every model is fitted on a list of training data sets and then
asked for edge probabilities over the ordered pairs of a neuron list at a target age.

A training data set is a `Conn`: binary and count matrices over the reference neuron list `cells`, the mask of neurons
present in that data set, and the age in hours after hatching. Probabilities are returned for all ordered pairs
(i != j) of `cells`; evaluation restricts them to pairs whose neurons are present in the target.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.linear_model import LogisticRegression

from . import celegans as C
from . import rs

EPS = 1e-6


@dataclass
class Conn:
    name: str
    age_h: float
    counts: np.ndarray            # n x n synapse counts (chemical), 0 on the diagonal
    present: np.ndarray           # n booleans

    @property
    def A(self):
        return (self.counts > 0).astype(float)


@dataclass
class Ctx:
    """Reference neurons and their independent features."""
    cells: list
    pos: np.ndarray
    birth: np.ndarray
    cook: np.ndarray              # integer category codes
    coarse: np.ndarray            # 0 sensory, 1 inter, 2 motor
    lr: np.ndarray                # bilateral class codes
    I: np.ndarray = field(init=False)
    J: np.ndarray = field(init=False)

    def __post_init__(self):
        n = len(self.cells)
        self.I, self.J = np.where(~np.eye(n, dtype=bool))
        self.d = np.linalg.norm(self.pos[self.I] - self.pos[self.J], axis=1) / 800.0

    def flat(self, M):
        return M[self.I, self.J]

    def pair_mask(self, present):
        return present[self.I] & present[self.J]


def make_ctx(cells):
    cat, coarse = C.cook_categories(cells)
    cmap = {"sensory": 0, "interneuron": 1, "motorneuron": 2}
    return Ctx(list(cells), C.positions(cells), C.birth_times(cells), C.codes(cat)[0],
               np.array([cmap[x] for x in coarse]), C.codes(C.lr_class(cells))[0])


def logit(p):
    p = np.clip(p, EPS, 1 - EPS)
    return np.log(p / (1 - p))


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def age_weights(ages, a):
    """Linear interpolation weights over sorted distinct training ages; flat beyond the ends."""
    ages = np.asarray(ages, dtype=float)
    u = np.unique(ages)
    w = np.zeros(len(ages))
    if a <= u[0] or len(u) == 1:
        tgt = {u[0]: 1.0} if a <= u[0] else {u[-1]: 1.0}
    elif a >= u[-1]:
        tgt = {u[-1]: 1.0}
    else:
        k = np.searchsorted(u, a)
        lo, hi = u[k - 1], u[k]
        f = (a - lo) / (hi - lo)
        tgt = {lo: 1 - f, hi: f}
    for age, wt in tgt.items():
        idx = np.where(ages == age)[0]
        w[idx] = wt / len(idx)
    return w


# ---------------------------------------------------------------- baselines


class ER:
    name = "B0-ER"

    def fit(self, ctx, train):
        self.ages = [t.age_h for t in train]
        self.dens = [ctx.flat(t.A)[ctx.pair_mask(t.present)].mean() for t in train]
        self.n_params = len(train)
        return self

    def predict(self, ctx, age_h):
        w = age_weights(self.ages, age_h)
        return np.full(len(ctx.I), sigmoid(np.dot(w, logit(np.array(self.dens)))))


class Block:
    """Block model: one probability per (type_i, type_j), per training data set, interpolated in logit by age."""

    def __init__(self, types, name, label_bits=0.0):
        self.types = np.asarray(types)
        self.name = name
        self.label_bits = label_bits

    def fit(self, ctx, train):
        k = int(self.types.max()) + 1
        tp = self.types[ctx.I] * k + self.types[ctx.J]
        self.ages, self.logits = [], []
        for t in train:
            m = ctx.pair_mask(t.present)
            e = np.bincount(tp[m], weights=ctx.flat(t.A)[m], minlength=k * k)
            n = np.bincount(tp[m], minlength=k * k)
            self.logits.append(logit((e + 0.5) / (n + 1.0)))
            self.ages.append(t.age_h)
        self.tp, self.k = tp, k
        self.n_params = k * k * len(set(self.ages))
        return self

    def predict(self, ctx, age_h):
        w = age_weights(self.ages, age_h)
        return sigmoid(np.tensordot(w, np.array(self.logits), axes=1)[self.tp])


def feature_matrix(ctx, age_h, with_distance=True):
    """Independent features of B4 (and of A-none in the function test)."""
    bi, bj = ctx.birth[ctx.I] / 1000.0, ctx.birth[ctx.J] / 1000.0
    oh = np.eye(3)
    cp, cq = oh[ctx.coarse[ctx.I]], oh[ctx.coarse[ctx.J]]
    inter = (cp[:, :, None] * cq[:, None, :]).reshape(len(ctx.I), 9)
    same = (ctx.lr[ctx.I] == ctx.lr[ctx.J]).astype(float)[:, None]
    cols = [bi[:, None], bj[:, None], np.maximum(bi, bj)[:, None], inter, same,
            np.full((len(ctx.I), 1), age_h / 50.0)]
    if with_distance:
        d = ctx.d[:, None]
        cols = [d, d ** 2, np.log(d + 1e-3)] + cols
    return np.hstack(cols)


class Distance:
    name = "B1-distance"

    def fit(self, ctx, train):
        X, y = [], []
        for t in train:
            m = ctx.pair_mask(t.present)
            X.append(np.c_[ctx.d[m], np.log(ctx.d[m] + 1e-3), np.full(m.sum(), t.age_h / 50.0)])
            y.append(ctx.flat(t.A)[m])
        self.lr = LogisticRegression(C=1e3, max_iter=2000).fit(np.vstack(X), np.concatenate(y))
        self.n_params = 4
        return self

    def predict(self, ctx, age_h):
        X = np.c_[ctx.d, np.log(ctx.d + 1e-3), np.full(len(ctx.I), age_h / 50.0)]
        return self.lr.predict_proba(X)[:, 1]


class Features:
    name = "B4-features"

    def __init__(self, C_reg=1.0, with_distance=True):
        self.C_reg, self.with_distance = C_reg, with_distance

    def fit(self, ctx, train):
        X, y = [], []
        for t in train:
            m = ctx.pair_mask(t.present)
            X.append(feature_matrix(ctx, t.age_h, self.with_distance)[m])
            y.append(ctx.flat(t.A)[m])
        X = np.vstack(X)
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-9
        self.lr = LogisticRegression(C=self.C_reg, max_iter=5000).fit((X - self.mu) / self.sd, np.concatenate(y))
        self.n_params = X.shape[1] + 1
        return self

    def predict(self, ctx, age_h):
        X = (feature_matrix(ctx, age_h, self.with_distance) - self.mu) / self.sd
        return self.lr.predict_proba(X)[:, 1]


# ---------------------------------------------------------------- memorisation


class Copy:
    """M1 (nearest age, or the mean over all training sets of the target's age) and M2 (age interpolation)."""

    def __init__(self, alpha=0.05, interpolate=False):
        self.alpha, self.interpolate = alpha, interpolate
        self.name = "M2-copy-interp" if interpolate else "M1-copy"

    def fit(self, ctx, train):
        self.train = train
        self.ages = [t.age_h for t in train]
        return self

    def predict(self, ctx, age_h):
        if self.interpolate:
            w = age_weights(self.ages, age_h)
        else:
            u = np.unique(self.ages)
            near = u[np.argmin(np.abs(u - age_h))]
            w = np.array([1.0 if a == near else 0.0 for a in self.ages])
            w /= w.sum()
        a = sum(wi * ctx.flat(t.A) for wi, t in zip(w, self.train) if wi > 0)
        return (a + self.alpha) / (1 + 2 * self.alpha)

    def bits(self, ctx):
        """Stored adjacency: binary entropy of each stored training matrix over its present pairs."""
        out = 0.0
        for t in self.train:
            m = ctx.pair_mask(t.present)
            rho = ctx.flat(t.A)[m].mean()
            out += m.sum() * (-(rho * np.log2(rho) + (1 - rho) * np.log2(1 - rho)))
        return out


class CountCopy:
    """M3 (counts) and M4 (counts + reverse counts), calibrated by a logistic fit on the development proxy."""

    def __init__(self, reverse=False):
        self.reverse = reverse
        self.name = "M4-count-reverse" if reverse else "M3-count"

    def design(self, ctx, n):
        f = [np.log1p(ctx.flat(n))]
        if self.reverse:
            f.append(np.log1p(n[ctx.J, ctx.I]))
        return np.vstack(f).T

    def fit(self, ctx, train, calib):
        """calib: list of (source counts matrix, target Conn) pairs from development data."""
        X = np.vstack([self.design(ctx, s)[ctx.pair_mask(t.present)] for s, t in calib])
        y = np.concatenate([ctx.flat(t.A)[ctx.pair_mask(t.present)] for s, t in calib])
        self.lr = LogisticRegression(C=1e3, max_iter=2000).fit(X, y)
        self.n = sum(t.counts for t in train) / len(train)
        self.train = train
        return self

    def predict(self, ctx, age_h):
        return self.lr.predict_proba(self.design(ctx, self.n))[:, 1]

    def bits(self, ctx):
        """Elias-gamma code length of (count + 1) for every stored pair."""
        out = 0.0
        for t in self.train:
            c = ctx.flat(t.counts)[ctx.pair_mask(t.present)] + 1
            out += np.sum(2 * np.floor(np.log2(c)) + 1)
        return out


# ---------------------------------------------------------------- Richter & Schneidman (R1)


class RS:
    """Single-epoch R1 on adult training sets; types fixed (Cook codes) or inferred on the training adjacency."""

    def __init__(self, types=None, k_inferred=None, beta0_grid=None, sminus_grid=None, iters=30, name=None):
        self.types0, self.k_inferred = types, k_inferred
        self.beta0_grid = np.linspace(0, 0.05, 11)[:-1] if beta0_grid is None else beta0_grid
        self.sminus_grid = np.linspace(0, 0.05, 11)[:-1] if sminus_grid is None else sminus_grid
        self.iters = iters
        self.name = name or ("R1-inferred%d" % k_inferred if k_inferred else "R1-cook")

    def fit(self, ctx, train):
        if self.k_inferred:
            A = sum(t.A for t in train)
            self.types = rs.hit_rate_types(A > 0, self.k_inferred)
        else:
            self.types = np.asarray(self.types0)
        k = int(self.types.max()) + 1
        self.t_end = rs.minutes(max(t.age_h for t in train))
        S = rs.Setup(ctx.pos, ctx.birth, self.types, self.t_end)
        ys = [ctx.flat(t.A) for t in train]
        ms = [ctx.pair_mask(t.present) for t in train]
        target = sum(rs.expected_counts_masked(S, y, m) for y, m in zip(ys, ms)) / len(train)
        best = None
        for b in self.beta0_grid:
            for s in self.sminus_grid:
                sp = rs.fit_splus_masked(S, target, b, s, ms, self.iters)
                p = S.final_prob(sp[S.tp], b, s)
                ll = sum(rs.loglik(p[m], y[m]) for y, m in zip(ys, ms))
                if best is None or ll > best[0]:
                    best = (ll, b, s, sp, p)
        self.ll, self.beta0, self.sminus, self.splus, self.p = best
        self.k = k
        self.n_params = k * k + 2
        self.label_bits = len(self.types) * np.log2(k) if self.k_inferred else 0.0
        return self

    def predict(self, ctx, age_h):
        if rs.minutes(age_h) == self.t_end:
            return self.p
        S = rs.Setup(ctx.pos, ctx.birth, self.types, rs.minutes(age_h))
        return S.final_prob(self.splus[S.tp], self.beta0, self.sminus)


class RSDev:
    """Multi-epoch R1 (PRE_REGISTRATION.md section 2.2): S+ may change at the epoch boundaries; epoch m's S+ is fitted
    so that expected counts per type pair at the boundary time match the constraint data set(s) of that epoch, the
    earlier epochs fixed; (beta0, S-) by the summed log-likelihood of all constraint data sets. `constraints` is a list
    of lists of Conn, one list per epoch, in time order; their (common) age ends the epoch."""

    def __init__(self, types, beta0_grid, sminus_grid, iters=20, name="R1-dev"):
        self.types = np.asarray(types)
        self.beta0_grid, self.sminus_grid, self.iters, self.name = beta0_grid, sminus_grid, iters, name

    def fit(self, ctx, constraints):
        ends = [rs.minutes(c[0].age_h) for c in constraints]
        self.ends = ends
        bounds = np.array(ends[:-1])
        setups = [rs.Setup(ctx.pos, ctx.birth, self.types, e) for e in ends]
        k = int(self.types.max()) + 1
        best = None
        for b in self.beta0_grid:
            for s in self.sminus_grid:
                fixed, ll = [], 0.0
                for m, (S, cs) in enumerate(zip(setups, constraints)):
                    ys = [ctx.flat(c.A) for c in cs]
                    ms = [ctx.pair_mask(c.present) for c in cs]
                    target = sum(rs.expected_counts_masked(S, y, mk) for y, mk in zip(ys, ms)) / len(cs)
                    sp = self._fit_epoch(S, target, b, s, ms, fixed, bounds[:m])
                    fixed.append(sp)
                    p = S.final_prob(np.vstack([f[S.tp] for f in fixed]), b, s, bounds[:m] if m else None)
                    ll += sum(rs.loglik(p[mk], y[mk]) for y, mk in zip(ys, ms))
                if best is None or ll > best[0]:
                    best = (ll, b, s, [f.copy() for f in fixed])
        self.ll, self.beta0, self.sminus, self.splus = best
        self.bounds = bounds
        self.n_params = len(self.splus) * k * k + 2
        return self

    def _fit_epoch(self, S, target, b, s, masks, fixed, bounds):
        kk = S.k * S.k
        lo, hi = np.full(kk, -30.0), np.zeros(kk)
        for _ in range(self.iters):
            mid = 0.5 * (lo + hi)
            sp = np.vstack([f[S.tp] for f in fixed] + [np.exp(mid)[S.tp]])
            p = S.final_prob(sp, b, s, bounds if len(bounds) else None)
            c = sum(rs.expected_counts_masked(S, p, m) for m in masks) / len(masks)
            up = c < target
            lo, hi = np.where(up, mid, lo), np.where(up, hi, mid)
        out = np.exp(0.5 * (lo + hi))
        out[target <= 0] = 0.0
        return out

    def predict(self, ctx, age_h):
        t = rs.minutes(age_h)
        S = rs.Setup(ctx.pos, ctx.birth, self.types, t)
        m = int(np.searchsorted(self.bounds, t, side="right"))
        sp = np.vstack([f[S.tp] for f in self.splus[:m + 1]])
        return S.final_prob(sp, self.beta0, self.sminus, self.bounds[:m] if m else None)


# ---------------------------------------------------------------- combination


class Combine:
    """C(X): logit p = w0 + w1 logit p_M + w2 logit p_X, weights fitted on development proxy predictions."""

    def __init__(self, name):
        self.name = name

    def fit(self, proxies):
        """proxies: list of (p_M, p_X, y) arrays over evaluated pairs of development proxy targets."""
        X = np.vstack([np.c_[logit(a), logit(b)] for a, b, _ in proxies])
        y = np.concatenate([yy for _, _, yy in proxies])
        self.lr = LogisticRegression(C=1e3, max_iter=2000).fit(X, y)
        return self

    def predict(self, p_m, p_x):
        return self.lr.predict_proba(np.c_[logit(p_m), logit(p_x)])[:, 1]


def param_bits(n_params, label_bits=0.0, bits_per_param=32):
    return n_params * bits_per_param + label_bits
