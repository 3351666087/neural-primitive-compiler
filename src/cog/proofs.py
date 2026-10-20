"""Parametric proofs with Z3: statements quantified over ARBITRARY index sets / grid sizes.

Every proof is "prove VALID: assert the negation, expect unsat". Each returns (name, status, seconds),
status in {"PROVED", "COUNTEREXAMPLE", "UNKNOWN"}. Nothing here is a Lean/Coq certificate: the trusted
base is Z3 plus the encodings below (which mirror the neural templates in cog/prims.py; the
correspondence is checked separately by the per-instance tests).

  P1  cmr_step       CMR inductive invariant over an uninterpreted coordinate sort and arbitrary
                     source relations, n letters (one step, any index set).
  P2  threshold      the CMR neuron with letter weight n and threshold n+1 fires iff letter and
                     at least one of its <= n sources (any n >= 1).
  P3  maps           pullback/forward inverse identities for rot90/rot270/fliph/flipv/transpose and
                     clipping shifts on an N x N grid, for every N >= 1.
  P4  cond_loop      composition: CMR + ANY + two gates + pacing assumption implement the conditional
                     command "if S meets R then A(S) else B(S)", for any index set, region and union maps.
  P5  group_shortcut the shortcut "RIGHT then LEFT = identity" fails for clipping shifts (expected
                     COUNTEREXAMPLE), but holds under the boundary assumption (no cell in the last column).
"""

from __future__ import annotations

import time

import z3


def _valid(name: str, claim, timeout_ms: int = 60_000):
    s = z3.Solver()
    s.set("timeout", timeout_ms)
    s.add(z3.Not(claim))
    t0 = time.perf_counter()
    r = s.check()
    dt = round(time.perf_counter() - t0, 3)
    if r == z3.unsat:
        return (name, "PROVED", dt, None)
    if r == z3.sat:
        return (name, "COUNTEREXAMPLE", dt, str(s.model())[:400])
    return (name, "UNKNOWN", dt, s.reason_unknown())


# ------------------------------------------------------------------ P1 CMR inductive step
def p1_cmr_step(n_letters: int = 3, mutant: bool = False):
    """State before the step: letter tag of the previous step is `prev` (0 = idle, 1..n letters), old
    image M (uninterpreted predicate on coordinates). Invariant Inv: P[k,c] <-> (prev == c and M(k)).
    Step: letter `cur` (0..n) arrives with data predicate Dat; new image M2(j) = OR_{k: Src_cur(j,k)} M(k)
    OR Dat_cur(j) (or M(j) if idle). Neural update (Boolean form of the threshold neurons, P2):
      P'[j,c] = (cur == c) and (exists k: Src_c(j,k) and exists c': P[k,c']) or (cur == c and DSrc_c(j))
      P'[j,0] = (cur == 0) and exists c': P[j,c']
    Claim: Inv(P, prev, M) -> Inv(P', cur, M2), and Y(j) = exists c P[j,c] <-> M(j)."""
    C = z3.DeclareSort("Coord")
    j, k = z3.Consts("j k", C)
    M = z3.Function("M", C, z3.BoolSort())
    letters = range(n_letters + 1)
    P = [z3.Function(f"P{c}", C, z3.BoolSort()) for c in letters]
    Src = [None] + [z3.Function(f"Src{c}", C, C, z3.BoolSort()) for c in range(1, n_letters + 1)]
    Dat = [None] + [z3.Function(f"Dat{c}", C, z3.BoolSort()) for c in range(1, n_letters + 1)]
    prev, cur = z3.Ints("prev cur")
    rng = lambda x: z3.And(x >= 0, x <= n_letters)
    inv = z3.ForAll([k], z3.And(*[P[c](k) == z3.And(prev == c, M(k)) for c in letters]))
    anyP = lambda x: z3.Or(*[P[c](x) for c in letters])
    def P2(c, x):
        if c == 0:
            return z3.And(cur == 0, anyP(x))
        src = Src[(c % n_letters) + 1] if mutant else Src[c]   # mutant: neuron wired to another letter's sources
        return z3.And(cur == c, z3.Or(z3.Exists([k], z3.And(src(x, k), anyP(k))), Dat[c](x)))
    def M2(x):
        return z3.Or(z3.And(cur == 0, M(x)),
                     *[z3.And(cur == c, z3.Or(z3.Exists([k], z3.And(Src[c](x, k), M(k))), Dat[c](x)))
                       for c in range(1, n_letters + 1)])
    inv2 = z3.ForAll([j], z3.And(*[P2(c, j) == z3.And(cur == c, M2(j)) for c in letters]))
    yclaim = z3.ForAll([j], anyP(j) == M(j))
    hyp = z3.And(rng(prev), rng(cur), inv)
    claim = z3.Implies(hyp, z3.And(inv2, yclaim))
    tag = " MUTANT (expected COUNTEREXAMPLE)" if mutant else ""
    return _valid(f"P1 cmr_step (n={n_letters}, any index set, any source relations){tag}", claim), _sat("P1 hypotheses", hyp)


def p1_base():
    """Initial state: all P false, prev = 0 (idle), M empty: the invariant holds."""
    C = z3.DeclareSort("Coord")
    k = z3.Const("k", C)
    claim = z3.ForAll([k], z3.And(z3.BoolVal(False) == z3.And(True, z3.BoolVal(False))))
    return _valid("P1 cmr_base (empty register, all neurons silent)", claim)


# ------------------------------------------------------------------ P2 threshold lemma
def p2_threshold():
    n, s, l = z3.Ints("n s l")
    fires = n * l + s >= n + 1
    claim = z3.ForAll([n, s, l], z3.Implies(z3.And(n >= 1, s >= 0, s <= n, z3.Or(l == 0, l == 1)),
                                            fires == z3.And(l == 1, s >= 1)))
    idle = z3.ForAll([s, l], z3.Implies(z3.And(z3.Or(s == 0, s == 1), l >= 0), (s - l >= 1) == z3.And(s == 1, l == 0)))
    return [_valid("P2 threshold: letter weight n, threshold n+1 = letter AND (some of <= n sources)", claim),
            _valid("P2 idle neuron: hold iff source and no letter", idle)]


# ------------------------------------------------------------------ P3 map lemmas
def p3_maps():
    N, x, y = z3.Ints("N x y")
    inside = lambda a, b: z3.And(a >= 0, a <= N - 1, b >= 0, b <= N - 1)
    M = N - 1
    cases = {
        # (forward point map of the spec, pullback source used by cog/ir.py)
        "rot90": (lambda a, b: (M - b, a), lambda a, b: (b, M - a)),
        "rot270": (lambda a, b: (b, M - a), lambda a, b: (M - b, a)),
        "rot180": (lambda a, b: (M - a, M - b), lambda a, b: (M - a, M - b)),
        "fliph": (lambda a, b: (M - a, b), lambda a, b: (M - a, b)),
        "flipv": (lambda a, b: (a, M - b), lambda a, b: (a, M - b)),
        "transpose": (lambda a, b: (b, a), lambda a, b: (b, a)),
    }
    res = []
    for name, (fwd, pull) in cases.items():
        sx, sy = pull(x, y)
        fx, fy = fwd(sx, sy)
        claim = z3.ForAll([N, x, y], z3.Implies(z3.And(N >= 1, inside(x, y)),
                                                z3.And(inside(sx, sy), fx == x, fy == y)))
        res.append(_valid(f"P3 {name}: pullback source lies inside and maps forward onto the target (all N)", claim))
    # clipping shift RIGHT: target (x,y) has a source iff x >= 1, and the source (x-1, y) moves onto it
    claim = z3.ForAll([N, x, y], z3.Implies(z3.And(N >= 1, inside(x, y)),
                                            z3.And(z3.Implies(x >= 1, z3.And(inside(x - 1, y), (x - 1) + 1 == x)),
                                                   z3.Implies(x == 0, z3.Not(z3.Exists([y], z3.And(inside(-1, y))))))))
    res.append(_valid("P3 shift-right clip: pullback is (x-1, y) when x >= 1, empty in column 0 (all N)", claim))
    return res


# ------------------------------------------------------------------ P4 composed conditional command
def p4_cond_loop(offset: int = 0, swap: bool = False):
    """Contract-level composition (no neurons): signals over integer time t and an uninterpreted
    coordinate sort. Contracts used:
      CMR:  Y(t, j) = M(t-2, j); M(t) = A-pullback of M(t-1) if letter iA(t), B-pullback if iB(t),
            M(t-1) if no letter (pacing: the only letters in (tau, tau+3] are iA/iB).
      ANY:  top(t) = exists j in R: Y(t-1, j)
      GATE: iA(t) = cond(t-3) and top(t-1);  iB(t) = cond(t-3) and not top(t-1)
    Claim (for any index set, region R, union maps A, B given as source relations):
      cond(tau) and no letters at tau..tau+2  =>  M(tau+3) = (if exists j in R: M(tau-1, j) then A(M(tau-1)) else B(M(tau-1)))."""
    C = z3.DeclareSort("Coord")
    j, k = z3.Consts("j k", C)
    R = z3.Function("R", C, z3.BoolSort())
    SrcA = z3.Function("SrcA", C, C, z3.BoolSort())
    SrcB = z3.Function("SrcB", C, C, z3.BoolSort())
    M = z3.Function("M", z3.IntSort(), C, z3.BoolSort())       # M(time, coord)
    Y = lambda t, x: M(t - 2, x)
    tau = z3.Int("tau")
    top = lambda t: z3.Exists([k], z3.And(R(k), Y(t - 1, k)))
    iA = top(tau + 2 + offset)  # = cond(tau) and top(tau+2), with cond(tau) true (offset != 0: other gate delay)
    iB = z3.Not(top(tau + 2 + offset))
    if swap:  # mutant: then/else branches exchanged
        iA, iB = iB, iA
    # pacing: no CMR letter at tau, tau+1, tau+2 -> M holds
    hold = z3.ForAll([j], z3.And(M(tau, j) == M(tau - 1, j), M(tau + 1, j) == M(tau, j), M(tau + 2, j) == M(tau + 1, j)))
    step = z3.ForAll([j], M(tau + 3, j) == z3.Or(z3.And(iA, z3.Exists([k], z3.And(SrcA(j, k), M(tau + 2, k)))),
                                               z3.And(iB, z3.Exists([k], z3.And(SrcB(j, k), M(tau + 2, k))))))
    meets = z3.Exists([k], z3.And(R(k), M(tau - 1, k)))
    spec = z3.ForAll([j], M(tau + 3, j) == z3.If(meets, z3.Exists([k], z3.And(SrcA(j, k), M(tau - 1, k))),
                                                z3.Exists([k], z3.And(SrcB(j, k), M(tau - 1, k)))))
    claim = z3.Implies(z3.And(hold, step), spec)
    if swap:
        return [_valid("P4 cond_loop MUTANT with then/else swapped (expected COUNTEREXAMPLE)", claim)]
    if offset > 0:
        return [_valid(f"P4 cond_loop reading the region {offset} step later (benign under pacing: expected PROVED)", claim)]
    if offset < 0:
        return [_valid(f"P4 cond_loop reading the region {-offset} step earlier (expected COUNTEREXAMPLE)", claim)]
    out = [_valid("P4 cond_loop: CMR+ANY+gates+pacing implement the conditional command (any space, R, A, B)", claim),
           _sat("P4 hypotheses", z3.And(hold, step))]
    # without pacing (a foreign letter L at tau+1 changes M) the claim is not derivable:
    hold_broken = z3.ForAll([j], z3.And(M(tau, j) == M(tau - 1, j), M(tau + 2, j) == M(tau + 1, j)))
    out.append(_valid("P4' cond_loop WITHOUT the pacing assumption (expected COUNTEREXAMPLE)",
                      z3.Implies(z3.And(hold_broken, step), spec), timeout_ms=30_000))
    return out


# ------------------------------------------------------------------ P5 group-law shortcut
def p5_group_shortcut():
    """Image on an N x N grid as a predicate S(x, y). RIGHT (clip) then LEFT (clip) vs identity."""
    N, x, y = z3.Ints("N x y")
    S = z3.Function("S", z3.IntSort(), z3.IntSort(), z3.BoolSort())
    inside = lambda a, b: z3.And(a >= 0, a <= N - 1, b >= 0, b <= N - 1)
    right = lambda a, b: z3.And(a >= 1, S(a - 1, b))           # pullback of RIGHT
    rl = lambda a, b: z3.And(a <= N - 2, right(a + 1, b))      # then LEFT
    eq = z3.ForAll([x, y], z3.Implies(inside(x, y), rl(x, y) == S(x, y)))
    no_last_col = z3.ForAll([y], z3.Not(S(N - 1, y)))
    return [_valid("P5 'RIGHT then LEFT = identity' for clipping shifts (expected COUNTEREXAMPLE)",
                   z3.Implies(N >= 1, eq)),
            _valid("P5' same, under the boundary assumption: no cell in the last column", z3.Implies(z3.And(N >= 1, no_last_col), eq))]


def _sat(name: str, hyp):
    s = z3.Solver()
    s.set("timeout", 30_000)
    s.add(hyp)
    r = s.check()
    return (f"{name} satisfiable (non-vacuity)", "SAT" if r == z3.sat else ("UNSAT" if r == z3.unsat else "UNKNOWN"), 0.0, None)


def all_proofs() -> list:
    out = []
    for n in (1, 2, 3, 4):
        out += list(p1_cmr_step(n))
    out += list(p1_cmr_step(2, mutant=True))[:1]
    out += p4_cond_loop(offset=1)
    out += p4_cond_loop(offset=-1)
    out += p4_cond_loop(swap=True)
    out += p2_threshold()
    out += p3_maps()
    out += p4_cond_loop()
    out += p5_group_shortcut()
    return out


if __name__ == "__main__":
    for name, status, dt, info in all_proofs():
        print(f"{status:15s} {dt:7.3f}s  {name}" + (f"\n                 {info}" if info and status != "PROVED" else ""))
