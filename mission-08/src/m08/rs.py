"""Independent re-implementation of the Richter & Schneidman (PNAS 2025) developmental generative model, written from
the paper and its preprint methods only (their code has no licence and was not read; FAILURE_TAXONOMY.md C8).

Model (single epoch). Time runs from 0 to the target age in steps of dt = 10 min (hatching at 800 min). A neuron
exists from its birth time on. For every ordered pair (i, j) that exists, in every step an absent synapse forms with
probability f_t = min(1, S+[type_i, type_j] * exp(-beta_t * d_ij)), then an existing synapse is pruned with
probability S-. beta_t = beta0 * L(t) / L(0), L(t) the worm length interpolated from Byerly et al. 1976 (constants as
given by the authors: 50 um at fertilisation, 250 um at hatching, 370 / 500 / 635 um at hatching + 12 / 20 / 28 h,
800 um in the adult at 3500 min); positions are fixed adult coordinates divided by 800 um. Each S+ is set by
bisection so that the expected number of synapses of its type pair equals the training data; (beta0, S-) by maximum
likelihood on a grid. Within a step this single-pair model forms, then prunes; the paper's recursion (an image in
the Methods, read at Gate 4) applies both to the previous state. The two differ only by S+ -> S+ (1 - S-), which the
bisection absorbs (amendment A4.2; the reciprocity model below follows the paper's order).

Multiple epochs: S+ may differ between epochs [0, e1), [e1, e2), ...; epoch m's S+ is fitted (with the earlier
epochs fixed) so that expected counts per type pair at the end of epoch m match the data set given for that epoch.

Reciprocity (paper, Methods "Reciprocity-dependent models"; PRE_REGISTRATION.md amendment A4.1): every unordered pair
{a, b} is a four-state chain (E none, U a->b only, L b->a only, R both). Within a step formation and pruning act on
the previous state: an absent synapse forms with min{S+ e^{-beta_t d}, 1}, or min{gamma S+ e^{-beta_t d}, 1} when the
reverse synapse exists; an existing one survives with 1 - S-. gamma = 1 gives independent pairs with the marginal
recursion p' = p (1 - S-) + (1 - p) f, which is the single-pair model above with S+ replaced by S+ (1 - S-) (the
step order of amendment A4.2; tests/test_rs.py checks the identity).
"""

from __future__ import annotations

import numpy as np

HATCH = 800.0
DT = 10.0
LENGTH_KNOTS = ((0.0, 50.0), (800.0, 250.0), (800.0 + 12 * 60, 370.0), (800.0 + 20 * 60, 500.0),
                (800.0 + 28 * 60, 635.0), (3500.0, 800.0))


def length(t):
    xs, ys = zip(*LENGTH_KNOTS)
    return np.interp(t, xs, ys)


def minutes(age_h):
    """Model time (minutes since fertilisation) of a data set aged `age_h` hours after hatching; adult capped at 3500."""
    return min(HATCH + 60.0 * age_h, 3500.0)


class Setup:
    """Pairs, distances and birth times for an ordered neuron list. `pos` in um (n x 3), `birth` in minutes."""

    def __init__(self, pos, birth, types, t_end):
        n = len(birth)
        self.n = n
        I, J = np.where(~np.eye(n, dtype=bool))
        self.I, self.J = I, J
        d = np.linalg.norm(pos[:, None, :] - pos[None, :, :], axis=-1) / 800.0
        self.d = d[I, J]
        self.tb = np.maximum(birth[I], birth[J])
        self.set_types(types)
        self.steps = np.arange(0.0, t_end, DT)               # step k covers [steps[k], steps[k] + DT)
        self.growth = length(self.steps) / LENGTH_KNOTS[0][1]
        self.u = np.where(I < J)[0]                           # dyads: the pair (a, b), a < b ...
        self.r = J[self.u] * (n - 1) + I[self.u]              # ... and the index of its reverse pair (b, a)

    def set_types(self, types):
        types = np.asarray(types)
        self.k = int(types.max()) + 1
        self.tp = types[self.I] * self.k + types[self.J]       # type-pair index per ordered pair

    def final_prob(self, splus_pair, beta0, sminus, epochs=None):
        """P(synapse exists at the end) for every pair. splus_pair: (pairs,) or (epochs, pairs)."""
        sp = np.atleast_2d(splus_pair)
        p = np.zeros(sp.shape[1])
        alive_from = self.tb
        for k, t in enumerate(self.steps):
            e = 0 if epochs is None else int(np.searchsorted(epochs, t, side="right"))
            on = alive_from <= t
            f = np.minimum(1.0, sp[min(e, len(sp) - 1)] * np.exp(-beta0 * self.growth[k] * self.d))
            p = np.where(on, (p + (1.0 - p) * f) * (1.0 - sminus), p)
        return p

    def final_states(self, splus_pair, beta0, sminus, gamma, epochs=None):
        """Dyad state probabilities (E, U, L, R) at the end, over dyads self.u (U: the pair self.u exists alone)."""
        sp = np.atleast_2d(splus_pair)
        u, r = self.u, self.r
        d, tb = self.d[u], self.tb[u]
        E, U, L, R = np.ones(len(u)), np.zeros(len(u)), np.zeros(len(u)), np.zeros(len(u))
        s, q = sminus, 1.0 - sminus
        for k, t in enumerate(self.steps):
            e = 0 if epochs is None else int(np.searchsorted(epochs, t, side="right"))
            on = tb <= t
            if not on.any():
                continue
            row = sp[min(e, len(sp) - 1)]
            base = np.exp(-beta0 * self.growth[k] * d)
            a, b = row[u] * base, row[r] * base
            fa, fb = np.minimum(1.0, a), np.minimum(1.0, b)
            ga, gb = np.minimum(1.0, gamma * a), np.minimum(1.0, gamma * b)
            nE = E * (1 - fa) * (1 - fb) + U * s * (1 - gb) + L * s * (1 - ga) + R * s * s
            nU = E * fa * (1 - fb) + U * q * (1 - gb) + L * s * ga + R * q * s
            nL = E * (1 - fa) * fb + U * s * gb + L * q * (1 - ga) + R * s * q
            nR = E * fa * fb + U * q * gb + L * q * ga + R * q * q
            E, U, L, R = (np.where(on, x, y) for x, y in ((nE, E), (nU, U), (nL, L), (nR, R)))
        return E, U, L, R

    def marginals(self, states):
        E, U, L, R = states
        p = np.zeros(len(self.I))
        p[self.u], p[self.r] = U + R, L + R
        return p

    def final_prob_dyad(self, splus_pair, beta0, sminus, gamma, epochs=None):
        return self.marginals(self.final_states(splus_pair, beta0, sminus, gamma, epochs))


def expected_counts(setup, p):
    return np.bincount(setup.tp, weights=p, minlength=setup.k * setup.k)


def fit_splus(setup, target_counts, beta0, sminus, iters=40, epochs=None, fixed=None):
    """Bisection on log S+ per type pair so that expected counts match `target_counts` (k*k). With `epochs`, the
    last epoch's S+ is fitted and earlier epochs are taken from `fixed` (list of (k*k,) arrays)."""
    kk = setup.k * setup.k
    lo = np.full(kk, -30.0)
    hi = np.zeros(kk)
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        s = np.exp(mid)
        rows = [] if fixed is None else [f[setup.tp] for f in fixed]
        sp = np.vstack(rows + [s[setup.tp]])
        c = expected_counts(setup, setup.final_prob(sp, beta0, sminus, epochs))
        up = c < target_counts
        lo = np.where(up, mid, lo)
        hi = np.where(up, hi, mid)
    s = np.exp(0.5 * (lo + hi))
    s[target_counts <= 0] = 0.0
    return s


def expected_counts_masked(setup, p, mask):
    return np.bincount(setup.tp[mask], weights=p[mask], minlength=setup.k * setup.k)


def fit_splus_masked(setup, target, beta0, sminus, masks, iters=40):
    """As fit_splus, but the model's expected counts are averaged over the pair masks of several training data sets
    (each data set contains only the neurons present in it)."""
    kk = setup.k * setup.k
    lo, hi = np.full(kk, -30.0), np.zeros(kk)
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        p = setup.final_prob(np.exp(mid)[setup.tp], beta0, sminus)
        c = sum(expected_counts_masked(setup, p, m) for m in masks) / len(masks)
        up = c < target
        lo, hi = np.where(up, mid, lo), np.where(up, hi, mid)
    s = np.exp(0.5 * (lo + hi))
    s[target <= 0] = 0.0
    return s


def fit_splus_dyad(setup, target, beta0, sminus, gamma, masks, iters=40, epochs=None, fixed=None, refine=40,
                   tol=1e-3):
    """S+ for every type pair of the reciprocity model. The two directions of a dyad are coupled, so all type pairs
    are first bisected together (each against its own expected count), then refined by damped log-ratio steps
    log S+ += 0.8 log(target / count) (counts are close to proportional to S+ at these rates) until every count is
    within `tol` (relative). Returns (S+ (k*k,), max relative count error)."""
    kk = setup.k * setup.k
    lo, hi = np.full(kk, -30.0), np.zeros(kk)
    pos = target > 0

    def counts(logs):
        rows = [] if fixed is None else [f[setup.tp] for f in fixed]
        sp = np.vstack(rows + [np.exp(logs)[setup.tp]])
        p = setup.final_prob_dyad(sp, beta0, sminus, gamma, epochs)
        return sum(expected_counts_masked(setup, p, m) for m in masks) / len(masks)

    def rel_err(c):
        return float(np.max(np.abs(c - target)[pos] / target[pos])) if pos.any() else 0.0

    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        up = counts(mid) < target
        lo, hi = np.where(up, mid, lo), np.where(up, hi, mid)
    est = np.where(pos, 0.5 * (lo + hi), -30.0)
    c = counts(est)
    for _ in range(refine):
        if rel_err(c) < tol:
            break
        step = np.where(pos, 0.8 * np.log(np.maximum(target, 1e-12) / np.maximum(c, 1e-12)), 0.0)
        est = np.minimum(0.0, est + np.clip(step, -2.0, 2.0))
        c = counts(est)
    s = np.exp(est)
    s[~pos] = 0.0
    return s, rel_err(c)


def dyad_loglik(setup, states, y, mask, eps=1e-12):
    """Log-likelihood of the observed dyad states (both directions of every dyad whose neurons are present)."""
    E, U, L, R = (np.clip(x, eps, 1.0) for x in states)
    m = mask[setup.u]
    a, b = y[setup.u][m] > 0, y[setup.r][m] > 0
    ll = np.where(a & b, np.log(R[m]), np.where(a, np.log(U[m]), np.where(b, np.log(L[m]), np.log(E[m]))))
    return float(ll.sum())


def loglik(p, y, eps=1e-12):
    p = np.clip(p, eps, 1 - eps)
    return float(np.sum(y * np.log(p) + (1 - y) * np.log(1 - p)))


def fit(setup, y, beta0_grid, sminus_grid, iters=40):
    """Single-epoch fit to the binary pair vector y. Returns (best dict, table of (beta0, sminus, ll))."""
    target = expected_counts(setup, y.astype(float))
    best, table = None, []
    for b in beta0_grid:
        for s in sminus_grid:
            sp = fit_splus(setup, target, b, s, iters)
            p = setup.final_prob(sp[setup.tp], b, s)
            ll = loglik(p, y)
            table.append((b, s, ll))
            if best is None or ll > best["ll"]:
                best = {"beta0": b, "sminus": s, "splus": sp, "ll": ll, "p": p}
    return best, table


def hit_rate(E, s):
    """sum_tu E_tu^2 / N_tu with N_tu = s_t s_u - [t = u] s_t (no autapses); 0/0 counts as 0."""
    N = np.outer(s, s) - np.diag(s)
    return float(np.sum(np.where(N > 0, E * E / np.where(N > 0, N, 1), 0.0)))


def hit_rate_types(adj, k):
    """Greedy agglomeration of neurons into k types maximising the 'hit rate' sum_tu E_tu^2 / N_tu (the expected
    agreement when E_tu synapses are placed uniformly among the N_tu possible ones), merging at each step the pair
    of types whose merge loses least (Richter & Schneidman methods). adj: binary n x n, diagonal ignored. The loss of
    every candidate merge is computed at once from M = E diag(1/s) E^T and its transpose analogue."""
    A = adj.astype(float).copy()
    np.fill_diagonal(A, 0)
    E, s = A.copy(), np.ones(A.shape[0])
    members = [[i] for i in range(A.shape[0])]
    while len(s) > k:
        N = np.outer(s, s) - np.diag(s)
        R = np.where(N > 0, E * E / np.where(N > 0, N, 1), 0.0)
        rs_, cs_ = R.sum(1), R.sum(0)
        old = rs_[:, None] + rs_[None, :] + cs_[:, None] + cs_[None, :] - np.diag(R)[:, None] - np.diag(R)[None, :] - R - R.T
        Mr = (E / s[None, :]) @ E.T                       # sum_u E_au E_bu / s_u
        Mc = (E.T / s[None, :]) @ E                       # sum_u E_ua E_ub / s_u
        dr, dc = np.diag(Mr), np.diag(Mc)
        sc = s[:, None] + s[None, :]
        Ed = np.diag(E)
        # merged row / column sums over u not in {a, b}: remove the u = a and u = b terms
        rows = dr[:, None] + 2 * Mr + dr[None, :] - (Ed[:, None] + E.T) ** 2 / s[:, None] - (E + Ed[None, :]) ** 2 / s[None, :]
        cols = dc[:, None] + 2 * Mc + dc[None, :] - (Ed[:, None] + E) ** 2 / s[:, None] - (E.T + Ed[None, :]) ** 2 / s[None, :]
        ecc = Ed[:, None] + E + E.T + Ed[None, :]
        new = (rows + cols) / sc + np.where(sc > 1, ecc ** 2 / (sc * (sc - 1)), 0.0)
        loss = old - new
        np.fill_diagonal(loss, np.inf)
        a, b = np.unravel_index(np.argmin(loss), loss.shape)
        a, b = min(a, b), max(a, b)
        E[a, :] += E[b, :]
        E[:, a] += E[:, b]
        E = np.delete(np.delete(E, b, 0), b, 1)
        s[a] += s[b]
        s = np.delete(s, b)
        members[a] += members.pop(b)
    label = np.empty(A.shape[0], dtype=int)
    for t, m in enumerate(members):
        label[m] = t
    return label
