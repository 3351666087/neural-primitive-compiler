"""TZ (amendment 3): parametric damage bounds for every N, derived with Z3. CONSTRUCTOR SIDE.

Exchange lemma [P, classical]: a relocation's net effect is to exchange the contents of cells x and y (the spare
cell is restored; hazards and fixed objects do not move). Hence, for a template T and u, v = contents of x, y before:
  KD(R)     dT = E(L, R) + sum over the cells strictly between x and y of B(L, R, w)
            L, R = contents of the left and right end before the exchange, w = content of a between cell;
            cells outside [min(x,y), max(x,y)] contribute 0
  OUT, OOW  dT = ([v = p] - [u = p]) * ([x not in Z] - [y not in Z])
            Z = the zone, or the colour's GROUP window; a window depends only on the colour count, the hazards and
            the fixed objects, so it is the same before and after (no window: dT = 0)
Allowed values follow the achiever's selection rule. Only constraints that always hold are encoded, so the result is
an upper bound (conservative):
  ORDER  u = A2, v = A1, x < y; O2 also: no A1 between x and y
  ZONE   x in the achiever's zone, y not, v = A1, u = empty or another colour (u != A1)
  GROUP  x in the achiever's window, y not, v = A1, u != A1
  N >= 3 symbolic; zones [0, w) or [N - w, N) with w = 2 or N div 2; windows are symbolic intervals of length equal
  to the colour count (the same window if the template names the achiever's colour and variant; the same length,
  and G1 start <= G2 start, for the achiever's colour and the other variant).
Per entry:
  INF      Z3 finds an allowed between value w with B > 0 (KD only): no finite bound for all N is derived
  PROVED   no allowed w has B > 0 (unsat) and dT > b is unsat for the reported b (b = the largest k with dT >= k sat)
  UNKNOWN  a solver call returned unknown (treated as infinite)
Progress, decrease part: the bound of the achiever's own measure template (ORDER: KD{A1<A2}; ZONE: OUT(A1, side, w);
GROUP: OOW(A1, variant)) is PROVED <= -1. The applicability part (in every eligible state the selection applies
and the macro has a spare cell) is a counting lemma [P]; T7 checks it at N <= 7.
Self-check: the same formulas, evaluated in Python on concrete states, equal the template change of the real
relocation (exhaustive at N <= 5, and 20 000 seeded random states at N = 6..10).

  python -I z3_damage.py            # writes tz_table.json
  python -I z3_damage.py --smoke    # development check: formula self-check (N <= 5 and 2 000 random states) and
                                    # the 12 own-measure entries only (expected -1 by hand); writes nothing
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
from libval import ROLE, achiever_instances, states  # noqa: E402
from libval3 import parse_key  # noqa: E402
from model import group_window, holds, reloc, select, zcells  # noqa: E402
from potentials import evaluate, patterns  # noqa: E402


# ------------------------------------------------------------------ formulas (one definition, two backends)
class PyOps:
    Eq = staticmethod(lambda a, b: a == b)
    And = staticmethod(lambda *a: all(a))
    Not = staticmethod(lambda a: not a)
    I = staticmethod(lambda c: 1 if c else 0)


class ZOps:
    Eq = staticmethod(lambda a, b: a == b)
    And = staticmethod(z3.And)
    Not = staticmethod(z3.Not)
    I = staticmethod(lambda c: z3.If(c, 1, 0))


def kd_end(pairs, L, R, o):
    return sum(o.I(o.And(o.Eq(R, hi), o.Eq(L, lo))) - o.I(o.And(o.Eq(L, hi), o.Eq(R, lo))) for lo, hi in pairs)


def kd_between(pairs, L, R, w, o):
    return sum(o.I(o.And(o.Eq(R, hi), o.Eq(w, lo))) + o.I(o.And(o.Eq(w, hi), o.Eq(L, lo)))
               - o.I(o.And(o.Eq(L, hi), o.Eq(w, lo))) - o.I(o.And(o.Eq(w, hi), o.Eq(R, lo))) for lo, hi in pairs)


def exch(p, u, v, out_x, out_y, o):
    return (o.I(o.Eq(v, p)) - o.I(o.Eq(u, p))) * (o.I(out_x) - o.I(out_y))


def formula_delta(key, cells, x, y, haz, fixed):
    """The exchange formula on a concrete state (Python backend)."""
    t = parse_key(key)
    u, v = cells[x], cells[y]
    if t[0] == "KD":
        lo_, hi_ = min(x, y), max(x, y)
        L, R = cells[lo_], cells[hi_]
        return kd_end(t[1], L, R, PyOps) + sum(kd_between(t[1], L, R, cells[z], PyOps) for z in range(lo_ + 1, hi_))
    if t[0] == "OUT":
        Z = set(zcells(len(cells), t[2], t[3]))
    else:
        Z = group_window(["GROUP", t[1]], cells, {}, haz, True, fixed, t[2])
        if Z is None:
            return 0
    return exch(t[1], u, v, x not in Z, y not in Z, PyOps)


def self_check(seed=3, n_random=20000):
    ach = achiever_instances()
    keys = {akey: patterns(a[0]) for akey, a, _ in ach}
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
            for k in keys[akey]:
                checked += 1
                real = evaluate(k, r[0], haz, True, fixed, ROLE) - evaluate(k, cells, haz, True, fixed, ROLE)
                if real != formula_delta(k, cells, sel[0], sel[1], haz, fixed) and len(bad) < 20:
                    bad.append({"achiever": akey, "key": k, "cells": cells, "haz": haz, "fixed": fixed})

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


# ------------------------------------------------------------------ Z3 encoding
def own_measure_key(akey):
    p = akey.split(":")
    if p[0] == "ORDER":
        return "KD{A1<A2}"
    if p[0] == "ZONE":
        return f"OUT(A1,{p[2]},{p[3]})"
    return f"OOW(A1,{p[1]})"


def _zone(N, p, side, w):
    W = N / 2 if w == "half" else z3.IntVal(int(w))
    return z3.And(0 <= p, p < W) if side == "left" else z3.And(N - W <= p, p < N)


def _check(s, extra):
    s.push()
    s.add(*extra)
    r = s.check()
    m = s.model() if r == z3.sat else None
    s.pop()
    return r, m


def achiever_base(atom, var, timeout_ms=20000):
    """Solver with the achiever's allowed values (necessary constraints only); shared by TZ, TZ-P and B-EXCH."""
    s = z3.Solver()
    s.set("timeout", timeout_ms)
    N, x, y, u, v = z3.Ints("N x y u v")
    s.add(N >= 3, 0 <= x, x < N, 0 <= y, y < N, x != y, 0 <= u, u <= 4, 0 <= v, v <= 4)
    A1, A2 = ROLE["A1"], ROLE["A2"]
    sa, ca = z3.Ints("sa ca")
    no_A1_between = False
    if atom[0] == "ORDER":
        s.add(u == A2, v == A1, x < y)
        no_A1_between = var == "O2"
    elif atom[0] == "ZONE":
        s.add(_zone(N, x, atom[2], atom[3]), z3.Not(_zone(N, y, atom[2], atom[3])), v == A1, u != A1)
    else:
        s.add(ca >= 1, sa >= 0, sa + ca <= N, sa <= x, x < sa + ca, z3.Or(y < sa, y >= sa + ca), v == A1, u != A1)
    return s, (N, x, y, u, v, sa, ca), no_A1_between


def template_region(s, atom, var, t, V):
    """Membership predicate of the template's region (OUT: zone; OOW: window, with its constraints added to s)."""
    N, x, y, u, v, sa, ca = V
    A1 = ROLE["A1"]
    if t[0] == "OUT":
        return lambda z: _zone(N, z, t[2], t[3])
    p = t[1]
    st, ct = z3.Ints("st ct")
    hw = z3.Bool("hw")
    s.add(st >= 0, ct >= ZOps.I(u == p) + ZOps.I(v == p), st + ct <= N)
    if atom[0] == "GROUP" and p == A1:
        s.add(hw, ct == ca)
        if t[2] == var:
            s.add(st == sa)
        elif t[2] == "G1":
            s.add(st <= sa)
        else:
            s.add(st >= sa)
    return lambda z: z3.And(hw, st <= z, z < st + ct)


def bound_entry(atom, var, key, timeout_ms=20000):
    s, V, no_A1_between = achiever_base(atom, var, timeout_ms)
    N, x, y, u, v, sa, ca = V
    A1 = ROLE["A1"]
    t = parse_key(key)
    calls = []
    if t[0] == "KD":
        L, R = z3.If(x < y, u, v), z3.If(x < y, v, u)
        w = z3.Int("w")
        extra = [0 <= w, w <= 4, z3.Or(y - x >= 2, x - y >= 2), kd_between(t[1], L, R, w, ZOps) > 0]
        if no_A1_between:
            extra.append(w != A1)
        r, m = _check(s, extra)
        calls.append(str(r))
        if r == z3.sat:
            return {"status": "INF", "bound": "inf", "witness": {str(d): m[d].as_long() for d in m.decls()
                                                                  if m[d].sort() == z3.IntSort()}, "calls": calls}
        if r != z3.unsat:
            return {"status": "UNKNOWN", "bound": "inf", "calls": calls}
        dT = kd_end(t[1], L, R, ZOps)
        ks = range(len(t[1]) + 1, -len(t[1]) - 1, -1)
    else:
        p = t[1]
        inR = template_region(s, atom, var, t, V)
        if t[0] == "OUT":
            dT = exch(p, u, v, z3.Not(inR(x)), z3.Not(inR(y)), ZOps)
        else:
            # with no window (hw false) every cell is outside, so the formula gives 0, as the template does
            dT = exch(p, u, v, z3.Not(inR(x)), z3.Not(inR(y)), ZOps)
        ks = range(2, -2, -1)
    best = None
    for k in ks:
        r, m = _check(s, [dT >= k])
        calls.append(str(r))
        if r == z3.unknown:
            return {"status": "UNKNOWN", "bound": "inf", "calls": calls}
        if r == z3.sat:
            best = k
            break
    if best is None:
        return {"status": "UNKNOWN", "bound": "inf", "calls": calls, "note": "no k satisfiable"}
    return {"status": "PROVED", "bound": best, "calls": calls}


def smoke():
    for akey, a, v in achiever_instances():
        mk = own_measure_key(akey)
        print(akey, mk, bound_entry(a, v, mk))
    sc = self_check(n_random=2000)
    print("self-check", sc["checked"], "mismatches", sc["mismatches"], sc["examples"][:3])


def main():
    if "--smoke" in sys.argv:
        return smoke()
    t0 = time.perf_counter()
    table = {}
    for akey, a, v in achiever_instances():
        ent = {}
        for k in patterns(a[0]):
            r = bound_entry(a, v, k)
            r["evidence"] = "TZ" if r["status"] == "PROVED" else None
            ent[k] = r
        mk = own_measure_key(akey)
        prog = ent[mk]["status"] == "PROVED" and ent[mk]["bound"] <= -1
        table[akey] = {"entries": ent, "progress_decrease": {"key": mk, "proved": prog}}
        print(akey, sum(e["status"] == "PROVED" for e in ent.values()), "proved", round(time.perf_counter() - t0, 1),
              flush=True)
    z3_time = round(time.perf_counter() - t0, 2)
    t1 = time.perf_counter()
    sc = self_check()
    print("self-check", sc["checked"], "mismatches", sc["mismatches"], round(time.perf_counter() - t1, 1), "s", flush=True)
    progress = {akey: {"ok": row["progress_decrease"]["proved"], "evidence": "TZ" if row["progress_decrease"]["proved"] else None,
                       "basis": "Z3 decrease of own measure template + applicability lemma [P]"} for akey, row in table.items()}
    stat = {}
    for row in table.values():
        for e in row["entries"].values():
            stat[e["status"]] = stat.get(e["status"], 0) + 1
    out = {"label": "TZ: parametric damage bounds for all N >= 3 (Z3, exchange lemma [P]); amendment 3",
           "table": table, "progress": progress, "status_counts": stat, "z3_version": z3.get_version_string(),
           "time_s": z3_time, "self_check": sc, "self_check_time_s": round(time.perf_counter() - t1, 1)}
    (HERE / "tz_table.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(stat), "z3 time", z3_time)


if __name__ == "__main__":
    main()
