"""Checks of the Richter & Schneidman re-implementation (src/m08/rs.py) that need no data."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from m08 import rs  # noqa: E402


def brute_greedy(A, k):
    """Reference: try every merge, recompute the hit rate from scratch."""
    A = A.astype(float).copy()
    np.fill_diagonal(A, 0)
    groups = [[i] for i in range(len(A))]

    def total(gs):
        lab = np.empty(len(A), dtype=int)
        for t, g in enumerate(gs):
            lab[g] = t
        m = len(gs)
        E = np.zeros((m, m))
        np.add.at(E, (lab[:, None].repeat(len(A), 1), lab[None, :].repeat(len(A), 0)), A)
        s = np.array([len(g) for g in gs], dtype=float)
        return rs.hit_rate(E, s)

    while len(groups) > k:
        best = None
        for a in range(len(groups)):
            for b in range(a + 1, len(groups)):
                gs = [g for t, g in enumerate(groups) if t not in (a, b)] + [groups[a] + groups[b]]
                v = total(gs)
                if best is None or v > best[0] + 1e-12:
                    best = (v, a, b)
        _, a, b = best
        groups = [g for t, g in enumerate(groups) if t not in (a, b)] + [groups[a] + groups[b]]
    return sorted(sorted(g) for g in groups)


def test_hit_rate_greedy_matches_bruteforce():
    rng = np.random.default_rng(1)
    for _ in range(5):
        A = rng.random((9, 9)) < 0.3
        lab = rs.hit_rate_types(A, 3)
        got = sorted(sorted(np.where(lab == t)[0].tolist()) for t in set(lab))
        assert got == brute_greedy(A, 3)


def test_final_prob_closed_form_without_distance():
    """With beta0 = 0, a pair born at t_b sees n steps; p_n = q (1 - (a)^n) / (1 - a) with q = (1-S-) f, a = (1-f)(1-S-)."""
    pos = np.zeros((3, 3))
    birth = np.array([0.0, 100.0, 300.0])
    S = rs.Setup(pos, birth, [0, 0, 0], t_end=1000.0)
    f, sm = 0.01, 0.02
    p = S.final_prob(np.full(len(S.I), f), 0.0, sm)
    for idx, (i, j) in enumerate(zip(S.I, S.J)):
        n = int(np.sum(S.steps >= max(birth[i], birth[j])))
        q, a = (1 - sm) * f, (1 - f) * (1 - sm)
        assert abs(p[idx] - q * (1 - a ** n) / (1 - a)) < 1e-12


def test_fit_splus_matches_counts():
    rng = np.random.default_rng(2)
    n = 30
    pos = rng.random((n, 3)) * 100
    birth = rng.integers(0, 2000, n).astype(float)
    types = rng.integers(0, 3, n)
    S = rs.Setup(pos, birth, types, t_end=3500.0)
    y = (rng.random(len(S.I)) < 0.08).astype(float)
    target = rs.expected_counts(S, y)
    sp = rs.fit_splus(S, target, 0.5, 0.01)
    c = rs.expected_counts(S, S.final_prob(sp[S.tp], 0.5, 0.01))
    assert np.max(np.abs(c - target)) < 0.05


def _toy(n=25, seed=3):
    rng = np.random.default_rng(seed)
    pos = rng.random((n, 3)) * 200
    birth = rng.integers(0, 2500, n).astype(float)
    types = rng.integers(0, 3, n)
    return rng, rs.Setup(pos, birth, types, t_end=3500.0)


def test_dyad_gamma1_equals_single_pair_model():
    """Amendment A4.2: with gamma = 1 the dyad marginals equal the single-pair model with S+ -> S+ (1 - S-)."""
    rng, S = _toy()
    sp = rng.random(9) * 0.02
    for b0, sm in ((0.0, 0.0), (0.3, 0.01), (1.0, 0.04)):
        p1 = S.final_prob(sp[S.tp], b0, sm)
        p2 = S.final_prob_dyad(sp[S.tp] * (1 - sm), b0, sm, 1.0)
        assert np.max(np.abs(p1 - p2)) < 1e-12


def test_dyad_states_are_probabilities_and_gamma_raises_reciprocity():
    rng, S = _toy()
    sp = rng.random(9) * 0.01
    st1 = S.final_states(sp[S.tp], 0.3, 0.01, 1.0)
    st7 = S.final_states(sp[S.tp], 0.3, 0.01, 7.0)
    for st in (st1, st7):
        assert np.allclose(sum(st), 1.0) and min(x.min() for x in st) >= 0
    # independent dyads at gamma = 1: P(R) = p_ab p_ba
    p = S.marginals(st1)
    assert np.allclose(st1[3], p[S.u] * p[S.r])
    assert st7[3].sum() > st1[3].sum()


def test_fit_splus_dyad_matches_counts():
    rng, S = _toy(30, 4)
    y = (rng.random(len(S.I)) < 0.1).astype(float)
    y[S.r] = np.maximum(y[S.r], y[S.u] * (rng.random(len(S.u)) < 0.4))      # some reciprocity
    mask = np.ones(len(S.I), dtype=bool)
    target = rs.expected_counts(S, y)
    sp, err = rs.fit_splus_dyad(S, target, 0.3, 0.01, 5.0, [mask], iters=30)
    assert err < 0.01
