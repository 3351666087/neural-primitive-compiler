"""J2, formal view (protocol section 7, amendment 1 item 5). JUDGE SIDE.

L1 composition lemma (any number of atoms m = 1..5, uninterpreted state sort). Atoms g_1..g_m (predicates),
   measures mu_j >= 0, achiever transition relations T_j. Contracts:
     progress      not g_j(s) and T_j(s, s')                       ->  mu_j(s') < mu_j(s)
     preservation  i < j, g_i(s) and not g_j(s) and T_j(s, s')     ->  g_i(s')
   The priority controller moves with T_j for the first violated j. Ranking vector rho_i = 0 if g_i else mu_i + 1.
   Claim: every controller move strictly decreases rho lexicographically (so the controller terminates, and it
   stops only when every atom holds, since it stops exactly when no atom is violated).
   Checks: non-vacuity (hypotheses satisfiable) and two mutants (no preservation / no progress) that must fail.
L2 ATLEAST(k) template: a memoryless IF neuron (bias 0, leak = vmax, vmin 0, vmax = max(k, n), threshold k,
   n unit-weight inputs) fires at t iff at least k inputs were 1 at t-1, for every n >= 1 and 1 <= k <= n.
Each result: PROVED / COUNTEREXAMPLE / UNKNOWN (Z3 is the trusted base; nothing here is a proof certificate).
"""

from __future__ import annotations

import time

import z3


def _valid(name, claim, hyp=None):
    s = z3.Solver()
    s.set("timeout", 60_000)
    s.add(z3.Not(claim))
    t0 = time.perf_counter()
    r = s.check()
    out = {"name": name, "status": "PROVED" if r == z3.unsat else "COUNTEREXAMPLE" if r == z3.sat else "UNKNOWN",
           "time_s": round(time.perf_counter() - t0, 3)}
    if hyp is not None:
        s2 = z3.Solver()
        s2.add(hyp)
        out["hypotheses_satisfiable"] = s2.check() == z3.sat
    return out


def lemma_composition(m, drop=None):
    S = z3.DeclareSort("State")
    s, s2 = z3.Consts("s s2", S)
    g = [z3.Function(f"g{i}", S, z3.BoolSort()) for i in range(m)]
    mu = [z3.Function(f"mu{i}", S, z3.IntSort()) for i in range(m)]
    T = [z3.Function(f"T{i}", S, S, z3.BoolSort()) for i in range(m)]
    a, b = z3.Consts("a b", S)
    hyps = []
    for j in range(m):
        hyps.append(z3.ForAll([a], mu[j](a) >= 0))
        if drop != "progress":
            hyps.append(z3.ForAll([a, b], z3.Implies(z3.And(z3.Not(g[j](a)), T[j](a, b)), mu[j](b) < mu[j](a))))
        if drop != "preservation":
            for i in range(j):
                hyps.append(z3.ForAll([a, b], z3.Implies(z3.And(g[i](a), z3.Not(g[j](a)), T[j](a, b)), g[i](b))))
    rho = lambda i, x: z3.If(g[i](x), 0, mu[i](x) + 1)

    def lex_less(x, y):          # rho(x) <_lex rho(y)
        terms = []
        for k in range(m):
            eq = [rho(i, x) == rho(i, y) for i in range(k)]
            terms.append(z3.And(*eq, rho(k, x) < rho(k, y)))
        return z3.Or(*terms)
    claims = []
    for j in range(m):
        first = z3.And(*[g[i](s) for i in range(j)], z3.Not(g[j](s)))
        claims.append(z3.Implies(z3.And(first, T[j](s, s2)), lex_less(s2, s)))
    hyp = z3.And(*hyps)
    tag = f" without {drop} (expected COUNTEREXAMPLE)" if drop else ""
    return _valid(f"L1 composition lemma, m = {m}{tag}", z3.Implies(hyp, z3.And(*claims)),
                  hyp=z3.And(hyp, z3.Exists([a], z3.Not(g[0](a)))))


def lemma_atleast():
    n, k, sumx = z3.Ints("n k sumx")
    vmax = z3.If(k > n, k, n)
    v = z3.If(sumx < 0, 0, z3.If(sumx > vmax, vmax, sumx))          # clip(0 + current, 0, vmax), carried u = 0
    carried = z3.If(v > vmax, v - vmax, 0)                           # leak = vmax: potential returns to 0
    hyp = z3.And(n >= 1, k >= 1, k <= n, sumx >= 0, sumx <= n)
    claim = z3.Implies(hyp, z3.And((v >= k) == (sumx >= k), carried == 0))
    return _valid("L2 ATLEAST(k) memoryless threshold neuron fires iff at least k of n inputs (any n, k)", claim, hyp)


def run_all():
    res = [lemma_composition(m) for m in range(1, 6)]
    res += [lemma_composition(3, drop="preservation"), lemma_composition(3, drop="progress")]
    res.append(lemma_atleast())
    return res


if __name__ == "__main__":
    for r in run_all():
        print(r)
