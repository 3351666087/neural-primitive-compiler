"""Worm function test (PRE_REGISTRATION.md section 3): one frozen propagation operator applied to different structure
conditions. Structures are pre -> post matrices A[pre, post] over the Randi-usable neurons; the predicted response of
neuron i to stimulation of j is the resolvent entry R[j, i], R = (I - g A / rho(A))^-1 - I (all paths j -> i, weighted
by g^length). g and a two-parameter logistic calibration are fitted on development columns only.
"""

from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression

from . import metrics as M

G_GRID = np.round(np.arange(0.1, 1.0, 0.1), 2)


def resolvent(A, g):
    A = np.asarray(A, dtype=float).copy()
    np.fill_diagonal(A, 0)
    rho = np.max(np.abs(np.linalg.eigvals(A))) if A.any() else 1.0
    Ah = A / (rho if rho > 0 else 1.0)
    R = np.linalg.inv(np.eye(len(A)) - g * Ah) - np.eye(len(A))
    return R


def scores(A, g, I, J):
    """Predicted propagation j -> i for the labelled pairs (I responder, J stimulated)."""
    return resolvent(A, g)[J, I]


def fit_condition(A, dev_pairs, groups=None):
    """Choose g on development pairs by AUPRC; then calibrate by logistic regression on log score."""
    I, J, y = dev_pairs
    best = None
    for g in G_GRID:
        s = scores(A, g, I, J)
        ap = M.auprc(s, y)
        if best is None or ap > best[0]:
            best = (ap, g)
    g = best[1]
    s = scores(A, g, I, J)
    x = np.log(np.maximum(s, 0) + 1e-6)[:, None]
    lr = LogisticRegression(C=1e3, max_iter=2000).fit(x, y)
    return {"g": float(g), "dev_auprc": float(best[0]), "lr": lr}


def predict(A, fit, pairs):
    I, J, _ = pairs
    s = scores(A, fit["g"], I, J)
    return fit["lr"].predict_proba(np.log(np.maximum(s, 0) + 1e-6)[:, None])[:, 1]


def fit_support(S, F_obs, obs, l2=1.0, maxiter=500):
    """Support-constrained linear propagation fitted to mean responses (a Creamer-style model on the aggregated
    atlas). W[pre, post] is free only where S[pre, post] is true; R = (I - W)^-1 - I; predicted response of i to j is
    R[j, i] + b_i (responder bias). Squared error over observed pairs `obs` (bool n x n, [i, j] = i responds to j),
    plus l2 * |W|^2. Returns (W, b)."""
    from scipy.optimize import minimize
    n = S.shape[0]
    S = S.astype(bool).copy()
    np.fill_diagonal(S, False)
    idx = np.where(S)
    nw = len(idx[0])
    Fz = np.where(obs, F_obs, 0.0)
    cnt = obs.sum()

    def unpack(x):
        W = np.zeros((n, n))
        W[idx] = x[:nw]
        return W, x[nw:]

    def f(x):
        W, b = unpack(x)
        Mi = np.linalg.inv(np.eye(n) - W)
        P = (Mi - np.eye(n)).T + b[:, None]
        E = np.where(obs, P - Fz, 0.0)
        loss = np.sum(E * E) / cnt + l2 * np.sum(x[:nw] ** 2) / cnt
        gR = 2 * E.T / cnt
        gW = Mi.T @ gR @ Mi.T
        g = np.concatenate([gW[idx] + 2 * l2 * x[:nw] / cnt, 2 * E.sum(1) / cnt])
        return loss, g

    x0 = np.zeros(nw + n)
    r = minimize(f, x0, jac=True, method="L-BFGS-B", options={"maxiter": maxiter, "ftol": 1e-15, "gtol": 1e-12})
    W, b = unpack(r.x)
    fit_support.last = {"nit": int(r.nit), "loss": float(r.fun), "message": str(r.message)}
    return W, b


def predict_support(W, b):
    n = W.shape[0]
    return (np.linalg.inv(np.eye(n) - W) - np.eye(n)).T + b[:, None]


def rewire(A, rng, n_swaps=None):
    """Degree-preserving double-edge-swap rewiring of a directed binary graph."""
    A = (np.asarray(A) > 0).copy()
    np.fill_diagonal(A, False)
    E = np.argwhere(A)
    n_swaps = n_swaps or 10 * len(E)
    for _ in range(n_swaps):
        a, b = rng.integers(0, len(E), 2)
        (i, j), (k, l) = E[a], E[b]
        if len({i, j, k, l}) < 4 or A[i, l] or A[k, j]:
            continue
        A[i, j] = A[k, l] = False
        A[i, l] = A[k, j] = True
        E[a], E[b] = (i, l), (k, j)
    return A.astype(float)
