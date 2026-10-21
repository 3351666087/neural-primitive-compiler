"""TZ-P (amendment 4): parametric proofs of the pairwise-preservation contracts, for every N >= 3. CONSTRUCTOR SIDE.

A relocation exchanges the contents u (at x) and v (at y) [exchange lemma, P]. Whether an atom g that held before
still holds after:
  ORDER(p, q)  broken iff the increase of KD{p<q} is >= 1; increase = end term + sum of between terms (as in TZ),
               with the between cells counted by content (n_p, n_q, others; n_p + n_q + n_o = |x - y| - 1).
               g held before, on these cells: L = q => no p between and R != p; R = p => no q between and L != q.
               Pairs with cells outside [min(x,y), max(x,y)] keep their count (exchange lemma), so stay 0.
  ZONE(p, Z)   broken iff (v = p and x not in Z) or (u = p and y not in Z); held: u = p => x in Z, v = p => y in Z
  GROUP(p)     the p cells form the interval [s, s + c); held: u = p <=> x inside, v = p <=> y inside.
               After the exchange the p cells are contiguous iff c = 1, or the moved end is adjacent to the new
               place (u = p: x = s and y = s + c, or x = s + c - 1 and y = s - 1; v = p: symmetric)
The achiever's allowed values are those of z3_damage.py (necessary constraints only), so PROVED is sound.
  TZ-P0  only these constraints
  TZ-P1  adds one consequence of joint satisfiability: for a GROUP achiever and g = ZONE(A1, ...), some valid window
         of length ca lies inside g's zone (start s*); G1's window starts <= s*, G2's >= s*
Self-check: the after-truth formulas against the real relocation (exhaustive N <= 5, 20 000 random states N = 6..10).

  python -I z3_preserve.py            # writes tzp_table.json
  python -I z3_preserve.py --p2       # TZ-P2 (amendment 5): writes tzp2_table.json
  python -I z3_preserve.py --smoke    # development check: formula self-check (2 000 random states) and every
                                      # 12th entry with a real N <= 5 counterexample (must not be PROVED)
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

import z3

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from libval import ROLE, _parse, achiever_instances, states  # noqa: E402
from model import holds, reloc, select, zcells  # noqa: E402
from z3_damage import PyOps, ZOps, _zone, achiever_base, kd_between, kd_end  # noqa: E402

A1 = ROLE["A1"]


# ------------------------------------------------------------------ after-truth formulas (Python backend)
def breaks_py(g, cells, x, y):
    """Does the exchange of x and y break g (which held before)? Formula version, for the self-check."""
    t = g[0]
    u, v = cells[x], cells[y]
    if t == "ORDER":
        p, q = ROLE[g[1]], ROLE[g[2]]
        lo_, hi_ = min(x, y), max(x, y)
        L, R = cells[lo_], cells[hi_]
        d = kd_end([(p, q)], L, R, PyOps) + sum(kd_between([(p, q)], L, R, cells[z], PyOps) for z in range(lo_ + 1, hi_))
        return d >= 1
    if t == "ZONE":
        p = ROLE[g[1]]
        Z = set(zcells(len(cells), g[2], g[3]))
        return (v == p and x not in Z) or (u == p and y not in Z)
    p = ROLE[g[1]]
    ps = [i for i, c in enumerate(cells) if c == p]
    if not ps or (u == p) == (v == p):
        return False
    s, c = ps[0], len(ps)
    if u == p:
        return not (c == 1 or (x == s and y == s + c) or (x == s + c - 1 and y == s - 1))
    return not (c == 1 or (y == s and x == s + c) or (y == s + c - 1 and x == s - 1))


def self_check(seed=4, n_random=20000):
    ach = achiever_instances()
    roles = {k: (["A1", "A2", "X1", "X2"] if a[0] == "ORDER" else ["A1", "X1", "X2"]) for k, a, _ in ach}
    from libval import patterns
    pats = {k: [gp for gp in patterns(roles[k])] for k, _, _ in ach}
    bad, checked = [], 0

    def one(cells, haz, fixed):
        nonlocal checked
        for akey, a, v in ach:
            if holds(a, cells, ROLE):
                continue
            sel = select(a, v, cells, haz, True, fixed, ROLE)
            r = reloc(cells, 0, sel[0], sel[1], haz, True) if sel else None
            if r is None:
                continue
            for g in pats[akey]:
                if not holds(g, cells, ROLE):
                    continue
                checked += 1
                if breaks_py(g, cells, sel[0], sel[1]) != (not holds(g, r[0], ROLE)) and len(bad) < 20:
                    bad.append({"achiever": akey, "g": g, "cells": cells, "haz": haz, "fixed": fixed})

    if n_random >= 20000:
        for N in (3, 4, 5):
            for st in states(N):
                one(*st)
    rng = random.Random(seed)
    for _ in range(n_random):
        N = rng.randint(6, 10)
        K = rng.randint(1, N - 1)
        pos = rng.sample(range(N), K)
        cells = [0] * N
        for p in pos:
            cells[p] = rng.randint(1, 4)
        free = [p for p in range(N) if cells[p] == 0]
        hz = rng.sample(free, rng.randint(0, min(2, len(free))))
        haz = tuple(1 if p in hz else 0 for p in range(N))
        one(tuple(cells), haz, rng.choice(((), (4,))))
    return {"checked": checked, "mismatches": len(bad), "examples": bad}


# ------------------------------------------------------------------ Z3
def prove(atom, var, gkey, plus=False, timeout_ms=20000, extreme=False):
    s, V, no_A1_between = achiever_base(atom, var, timeout_ms)
    N, x, y, u, v, sa, ca = V
    g = _parse(gkey)
    if g[0] == "ORDER":
        p, q = ROLE[g[1]], ROLE[g[2]]
        L, R = z3.If(x < y, u, v), z3.If(x < y, v, u)
        n_p, n_q, n_o = z3.Ints("n_p n_q n_o")
        dist = z3.If(x < y, y - x, x - y)
        s.add(n_p >= 0, n_q >= 0, n_o >= 0, n_p + n_q + n_o == dist - 1)
        if no_A1_between:
            if p == A1:
                s.add(n_p == 0)
            if q == A1:
                s.add(n_q == 0)
        s.add(z3.Implies(L == q, z3.And(n_p == 0, R != p)), z3.Implies(R == p, z3.And(n_q == 0, L != q)))
        d = kd_end([(p, q)], L, R, ZOps) + n_p * kd_between([(p, q)], L, R, p, ZOps) + n_q * kd_between([(p, q)], L, R, q, ZOps)
        brk = d >= 1
    elif g[0] == "ZONE":
        p = ROLE[g[1]]
        inx, iny = _zone(N, x, g[2], g[3]), _zone(N, y, g[2], g[3])
        s.add(z3.Implies(u == p, inx), z3.Implies(v == p, iny))
        brk = z3.Or(z3.And(v == p, z3.Not(inx)), z3.And(u == p, z3.Not(iny)))
        if plus and atom[0] == "GROUP" and p == A1:
            st = z3.Int("sstar")
            s.add(_zone(N, st, g[2], g[3]), _zone(N, st + ca - 1, g[2], g[3]))
            s.add(sa <= st if var == "G1" else sa >= st)
        if extreme and atom[0] == "ZONE" and p == A1:
            # TZ-P2 (amendment 5): an eligible cell z* in both zones exists (joint satisfiability), and the selection
            # takes the rightmost (left zone, Z1; right zone, Z2) or leftmost eligible zone cell
            zs = z3.Int("zstar")
            s.add(_zone(N, zs, atom[2], atom[3]), _zone(N, zs, g[2], g[3]))
            rightmost = (atom[2] == "left") == (var == "Z1")
            s.add(zs <= x if rightmost else zs >= x)
    else:
        p = ROLE[g[1]]
        bs, bc = z3.Ints("bs bc")
        inb = lambda z: z3.And(bs <= z, z < bs + bc)
        s.add(bc >= 0, bs >= 0, bs + bc <= N, (u == p) == inb(x), (v == p) == inb(y))
        ok_u = z3.Or(bc == 1, z3.And(x == bs, y == bs + bc), z3.And(x == bs + bc - 1, y == bs - 1))
        ok_v = z3.Or(bc == 1, z3.And(y == bs, x == bs + bc), z3.And(y == bs + bc - 1, x == bs - 1))
        brk = z3.Or(z3.And(u == p, v != p, z3.Not(ok_u)), z3.And(v == p, u != p, z3.Not(ok_v)))
    s.add(brk)
    r = s.check()
    if r == z3.unsat:
        return {"status": "PROVED"}
    if r == z3.sat:
        m = s.model()
        return {"status": "NOT_PROVED", "model": {str(dd): str(m[dd]) for dd in m.decls()}}
    return {"status": "UNKNOWN"}


def main_p2():
    """TZ-P2 (amendment 5): TZ-P1 plus the extremality family; writes tzp2_table.json."""
    t0 = time.perf_counter()
    g2 = json.loads((HERE / "contract_table.json").read_text())
    t7 = json.loads((HERE / "t7_tables.json").read_text())
    tab = {}
    for akey, a, v in achiever_instances():
        row = {}
        for gk, e in g2["preserves"][akey].items():
            r = prove(a, v, gk, plus=True, extreme=True)
            e7 = t7["preserves"][akey][gk]
            r.update(ok_N5=e["ok"], states_N5=e["states"], ok_N7=e7["ok"], ok=r["status"] == "PROVED",
                     proved=r["status"] == "PROVED", evidence="TZ" if r["status"] == "PROVED" else None)
            row[gk] = r
        tab[akey] = row
    out = {"label": "TZ-P2: TZ-P1 plus the selection-extremality family (amendment 5)", "table": tab,
           "z3_time_s": round(time.perf_counter() - t0, 2)}
    (HERE / "tzp2_table.json").write_text(json.dumps(out, indent=1, default=str))
    print("TZ-P2", sum(e["proved"] for r in tab.values() for e in r.values()), "proved", out["z3_time_s"], "s")


def main():
    if "--p2" in sys.argv:
        return main_p2()
    if "--smoke" in sys.argv:
        sc = self_check(n_random=2000)
        print("self-check", sc["checked"], "mismatches", sc["mismatches"], sc["examples"][:3])
        g2 = json.loads((HERE / "contract_table.json").read_text())
        ach = {k: (a, v) for k, a, v in achiever_instances()}
        known = [(k, gk) for k in ach for gk, e in g2["preserves"][k].items() if not e["ok"]][::12]
        for k, gk in known:                        # entries with real counterexamples: must not be PROVED
            print(k, gk, prove(*ach[k], gk)["status"], prove(*ach[k], gk, plus=True)["status"])
        return
    t0 = time.perf_counter()
    g2 = json.loads((HERE / "contract_table.json").read_text())
    t7 = json.loads((HERE / "t7_tables.json").read_text())
    out = {"label": "TZ-P: parametric pairwise-preservation proofs (Z3, exchange lemma [P]); amendment 4", "tables": {}}
    for variant, plus in (("TZ-P0", False), ("TZ-P1", True)):
        tab = {}
        for akey, a, v in achiever_instances():
            row = {}
            for gk, e in g2["preserves"][akey].items():
                r = prove(a, v, gk, plus)
                e7 = t7["preserves"][akey][gk]
                r.update(ok_N5=e["ok"], states_N5=e["states"], ok_N7=e7["ok"],
                         ok=r["status"] == "PROVED", proved=r["status"] == "PROVED",
                         evidence="TZ" if r["status"] == "PROVED" else None)
                row[gk] = r
            tab[akey] = row
        out["tables"][variant] = tab
        print(variant, sum(e["proved"] for r in tab.values() for e in r.values()), "proved",
              round(time.perf_counter() - t0, 1), "s", flush=True)
    out["z3_time_s"] = round(time.perf_counter() - t0, 2)
    t1 = time.perf_counter()
    out["self_check"] = self_check()
    out["self_check_time_s"] = round(time.perf_counter() - t1, 1)
    print("self-check", out["self_check"]["checked"], "mismatches", out["self_check"]["mismatches"], flush=True)
    (HERE / "tzp_table.json").write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
