"""G0 audit: exact (unbounded-integer) version of Mission 01's latency-1 realisability test.

Mission 01's `npc.fsm.latency1_weights(M, bound=64)` searches W, alpha, theta in [-64, 64]. Theorem 3
(theory.md) quantifies over all integers. Reduction (mission-02/G0-audit.md, Prop. G0.1): condition (*)
is feasible iff some integer W satisfies  W.(a1 - a0) >= 1  for every reachable state q and every pair
(a1 in T1(q), a0 in T0(q)); rows have entries in {-1,0,1}, so by Cramer's rule a solution exists with
|W_k| <= H(m) (max |det| of an m x m {-1,1} matrix: 1,2,4,16,48,160,...) and then alpha can be chosen with
|alpha| <= 1 + sum_k |W_k|. Hence bound=64 is complete for m <= 3 inputs, and not in general.

`latency1_exact` drops the bounds (Z3 decides linear integer arithmetic exactly).
"""

from __future__ import annotations

import z3

from npc.fsm import Latency1, Moore


def latency1_exact(M: Moore, timeout_s: float = 600.0) -> Latency1 | None:
    """Same constraints as npc.fsm.latency1_weights, no magnitude bound. None = solver gave up."""
    res = Latency1(True)
    letters = M.letters
    for j, o in enumerate(M.outputs):
        s = z3.Solver()
        s.set("timeout", int(timeout_s * 1000))
        W = [z3.Int(f"W{k}") for k in range(len(M.inputs))]
        al = [z3.Int(f"al{q}") for q in range(M.n)]
        th = z3.Int("theta")
        s.add(th >= 1)
        for q in range(M.n):
            for a in letters:
                if (q, a) not in M.delta:
                    continue
                target = M.out[M.delta[(q, a)]][j]
                if target is None:
                    continue
                lhs = al[q] + z3.Sum([W[k] * a[k] for k in range(len(a))]) if a else al[q]
                s.add((lhs >= th) if target else (lhs < th))
        r = s.check()
        if r == z3.unknown:
            return None
        if r == z3.unsat:
            return Latency1(False)
        m = s.model()
        res.W[o] = [m.eval(w, model_completion=True).as_long() for w in W]
        res.alpha[o] = [m.eval(x, model_completion=True).as_long() for x in al]
        res.theta[o] = m.eval(th, model_completion=True).as_long()
    return res


HADAMARD_PM1 = {1: 1, 2: 2, 3: 4, 4: 16, 5: 48, 6: 160, 7: 576, 8: 4096}  # max |det| of n x n {-1,1} matrices


def bound_is_provably_complete(m: int, bound: int = 64) -> bool:
    """Sufficient condition from Prop. G0.1: |W| <= H(m) and |alpha| <= 1 + m*H(m) fit inside the bound."""
    h = HADAMARD_PM1.get(m)
    return h is not None and h <= bound and 1 + m * h <= bound
