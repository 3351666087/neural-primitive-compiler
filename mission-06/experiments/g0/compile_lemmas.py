"""G0-K1 (part 1): the neuron-level lemmas behind the compile_cir preservation theorem, proved with Z3 for symbolic
fan-in. Semantics: npc (src/npc/network.py): I = bias + sum w * s(t - d); v = clip(u + I, vmin, vmax); s = [v >= theta];
u' = reset if s else leak(v, l). compile_cir's neurons (cog.prims.Builder.build): vmin = 0, vmax = max(theta, positive
fan-in, 1), leak = vmax, reset = 0, init = 0.

  M    memoryless: for every v in [0, vmax], leak(v, vmax) = 0; so u = 0 at every t (u(0) = init = 0)
  CL   with u = 0 and theta <= vmax: s = 1 iff I >= theta (clipping never changes the comparison)
  OR   theta 1, n >= 1 unit inputs (multiset): s iff sum >= 1
  AND  theta p >= 1, p unit positive synapses (multiset), q >= 0 negative synapses of weight -p:
       s iff all positive sources are 1 and no negative source is 1
  ATL  theta k >= 1, n >= 0 unit inputs (k > n allowed): s iff sum >= k
  CONST  __T: bias 1, theta 1, no inputs: s = 1 at every t
  CMR  one register bit j (compile_cir uses only letters with one data source, "one", or "zero"):
       letters with weights as built by cog.prims.cmr; a = number of letters of the register active at t - 1 (CIR: at
       most one, else REG_CONFLICT), b = number of the bit's P-neurons active at t - 1 (inductive hypothesis: <= 1).
       Claims: at most one P-neuron of the bit fires at t; if a = 1 for letter l, the bit's value at t is l's new value
       (data source at t - 1, 1 for "one" on j, 0 otherwise); if a = 0 it is the value at t - 1 (hold).
Each lemma: PROVED (the negation is UNSAT), with a non-vacuity check of its hypotheses.

  python -I compile_lemmas.py        # writes compile_lemmas.json
"""

from __future__ import annotations

import json
from pathlib import Path

import z3

HERE = Path(__file__).resolve().parent


def clip(x, lo, hi):
    return z3.If(x < lo, lo, z3.If(x > hi, hi, x))


def leak(v, l):
    return z3.If(v > l, v - l, z3.If(v < -l, v + l, 0))


def fires(I, theta, vmax):
    return clip(I, 0, vmax) >= theta                         # u = 0 (lemma M)


def valid(name, hyp, claim):
    s = z3.Solver()
    s.set("timeout", 60000)
    s.add(hyp, z3.Not(claim))
    r = s.check()
    s2 = z3.Solver()
    s2.add(hyp)
    return {"lemma": name, "status": "PROVED" if r == z3.unsat else ("COUNTEREXAMPLE" if r == z3.sat else "UNKNOWN"),
            "hypotheses_satisfiable": s2.check() == z3.sat,
            "counterexample": str(s.model()) if r == z3.sat else None}


def zmax(*a):
    m = a[0]
    for x in a[1:]:
        m = z3.If(x > m, x, m)
    return m


def lemmas():
    out = []
    v, vmax, theta, I = z3.Ints("v vmax theta I")
    out.append(valid("M memoryless", z3.And(vmax >= 1, 0 <= v, v <= vmax), leak(v, vmax) == 0))
    out.append(valid("CL clip", z3.And(vmax >= 1, theta >= 1, theta <= vmax),
                     (clip(I, 0, vmax) >= theta) == (I >= theta)))
    n, s_ = z3.Ints("n s")
    out.append(valid("OR", z3.And(n >= 1, s_ >= 0, s_ <= n), fires(s_, 1, zmax(z3.IntVal(1), n)) == (s_ >= 1)))
    p, q, sp, sn = z3.Ints("p q sp sn")
    hyp = z3.And(p >= 1, q >= 0, sp >= 0, sp <= p, sn >= 0, sn <= q)
    out.append(valid("AND (positive multiset of size p, negatives of weight -p)", hyp,
                     fires(sp - p * sn, p, zmax(p, p, z3.IntVal(1))) == z3.And(sp == p, sn == 0)))
    k = z3.Int("k")
    out.append(valid("ATLEAST (any n >= 0, k >= 1, k > n allowed)", z3.And(n >= 0, k >= 1, s_ >= 0, s_ <= n),
                     fires(s_, k, zmax(k, n, z3.IntVal(1))) == (s_ >= k)))
    out.append(valid("CONST __T", z3.BoolVal(True), fires(z3.IntVal(1), 1, 1)))
    # CMR, one bit: the bit's P-neurons are P_l for the letters that write it (load: theta 2, letter weight 1, source
    # weight 1; one: theta 1, letter weight 1) and the idle neuron (theta 1, +1 from each P of the bit, -1 from each
    # letter of the register). a = active letters of the register at t-1, b = active P-neurons of the bit at t-1.
    a, b = z3.Ints("a b")
    act, src, writes, isone = z3.Bools("letter_active src writes_bit is_one")   # the (at most one) active letter
    old = z3.Bool("old")                                                          # bit value at t-1 (some P active)
    hyp = z3.And(a >= 0, a <= 1, b >= 0, b <= 1, (b == 1) == old, (a == 1) == act)
    # the active letter's P-neuron for this bit (absent if the letter does not write the bit: zero letters, or
    # "one" on another bit)
    p_l = z3.And(act, writes, z3.If(isone, fires(z3.If(act, 1, 0), 1, 1), fires(z3.If(act, 1, 0) + z3.If(src, 1, 0), 2, 2)))
    # P-neurons of inactive letters receive letter input 0: load ones need 2 (source alone gives <= 1), one ones need 1
    p_inactive_load = fires(z3.IntVal(0) + z3.If(src, 1, 0), 2, 2)
    p_inactive_one = fires(z3.IntVal(0), 1, 1)
    idle = fires(b - a, 1, zmax(z3.IntVal(1), b))
    new_val = z3.If(act, z3.And(writes, z3.If(isone, True, src)), old)
    bit_t = z3.Or(p_l, idle)
    count_t = z3.If(p_l, 1, 0) + z3.If(idle, 1, 0)
    out.append(valid("CMR inactive letters' P-neurons stay silent", z3.BoolVal(True),
                     z3.And(z3.Not(p_inactive_load), z3.Not(p_inactive_one))))
    out.append(valid("CMR bit update (load / one / zero / hold) and at most one P active", hyp,
                     z3.And(bit_t == new_val, count_t <= 1)))
    return out


def main():
    res = lemmas()
    (HERE / "compile_lemmas.json").write_text(json.dumps(res, indent=1))
    for r in res:
        print(r["status"], r["hypotheses_satisfiable"], r["lemma"])


if __name__ == "__main__":
    main()
