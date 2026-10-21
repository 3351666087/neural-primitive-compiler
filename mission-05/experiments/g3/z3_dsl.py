"""A's generic Z3 encoding of ACH-DSL achievers (G3): damage bounds, pairwise preservation, progress. CONSTRUCTOR SIDE.

Exchange lemma [P] as in TZ / TZ-P: the relocation exchanges d (content u) and s (content v = OWN).
Necessary constraints derived from a spec (nothing about pick order beyond the families below):
  types     u in the contents of the dest types (EMPTY -> 0; PARTNER -> A2; OTHER -> any colour other than the atom's
            colours); v = A1
  regions   ZONE / NOT_ZONE: the atom's zone (symbolic N, width 2 or N div 2); WINDOW_Gv: an interval [s_v, s_v + c)
            with c = number of A1 >= 1 (both variants: the same c and s_G1 <= s_G2); LEFT_OF_DEST / RIGHT_OF_DEST:
            s < d / s > d; within k: |s - d| <= k; and: conjunction
  witnesses the atom is violated: ORDER: cells i < j with A2 at i and A1 at j; ZONE: an A1 cell j outside the zone;
            GROUP: A1 cells i < j with a non-A1 cell between. For a rule with pick leftmost (rightmost) whose types
            contain the witness's type (OWN / PARTNER; types of other cells are not certain), a witness in the
            rule's region gives sel <= w (sel >= w); nearest_to_dest gives |s - d| <= |w - d|
  between   no OWN cell strictly between d and s when the source is the leftmost OWN right of d, the rightmost OWN left
            of d, or the OWN cell nearest to d within ALL, LEFT_OF_DEST, RIGHT_OF_DEST or within k
Damage: the TZ procedure (KD: INF iff a between value with positive term is allowed; else the largest end term;
OUT / OOW: largest exchange term). Preservation: the TZ-P procedure, with the TZ-P1 window family (a rule over
WINDOW_G1 / WINDOW_G2 and g = ZONE(A1, ...): some valid window inside g's zone starts at s* with s_G1 <= s* /
s_G2 >= s*) and the TZ-P2 extremality family (dest region exactly ZONE, pick leftmost / rightmost, types containing
EMPTY and OTHER, g = ZONE(A1, ...): an eligible z* in both zones, with z* >= d / z* <= d). Progress (decrease part):
the own measure template (ORDER: KD{A1<A2}; ZONE: OUT(A1, side, w); GROUP: OOW(A1, G1) or OOW(A1, G2)) has a PROVED
bound <= -1; applicability is checked on all states N <= 7 by the truth tables [M].
"""

from __future__ import annotations

import sys
from pathlib import Path

import z3

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))
from libval import ROLE, _parse  # noqa: E402
from libval3 import parse_key  # noqa: E402
from z3_damage import ZOps, _check, _zone, exch, kd_between, kd_end  # noqa: E402

A1, A2 = ROLE["A1"], ROLE["A2"]


def _contents(atom, types):
    out = set()
    for t in types:
        if t == "EMPTY":
            out.add(0)
        elif t == "PARTNER":
            out.add(A2)
        elif t == "OWN":
            out.add(A1)
        else:
            out |= {c for c in (1, 2, 3, 4) if c != A1 and not (atom[0] == "ORDER" and c == A2)}
    return out


def _uses(r, name):
    if isinstance(r, str):
        return r == name
    if "and" in r:
        return any(_uses(x, name) for x in r["and"])
    return False


def base(spec, atom, timeout_ms=20000):
    s = z3.Solver()
    s.set("timeout", timeout_ms)
    N, x, y, u, v = z3.Ints("N x y u v")
    s.add(N >= 3, 0 <= x, x < N, 0 <= y, y < N, x != y, 0 <= u, u <= 4, v == A1)
    s.add(z3.Or([u == c for c in sorted(_contents(atom, spec["dest"]["types"]))]))
    c = z3.Int("cA1")
    s.add(c >= 1)
    win = {}
    for vname in ("G1", "G2"):
        if _uses(spec["dest"]["region"], "WINDOW_" + vname) or _uses(spec["dest"]["region"], "NOT_WINDOW_" + vname) or \
           _uses(spec["source"]["region"], "WINDOW_" + vname) or _uses(spec["source"]["region"], "NOT_WINDOW_" + vname):
            sv = z3.Int("s_" + vname)
            s.add(sv >= 0, sv + c <= N)
            win[vname] = sv
    if len(win) == 2:
        s.add(win["G1"] <= win["G2"])

    def inreg(r, p, is_src):
        if isinstance(r, dict):
            if "and" in r:
                return z3.And(inreg(r["and"][0], p, is_src), inreg(r["and"][1], p, is_src))
            return z3.And(p - x <= r["within"], x - p <= r["within"])
        if r == "ALL":
            return z3.BoolVal(True)
        if r in ("ZONE", "NOT_ZONE"):
            zin = _zone(N, p, atom[2], atom[3])
            return zin if r == "ZONE" else z3.Not(zin)
        if r == "LEFT_OF_DEST":
            return p < x
        if r == "RIGHT_OF_DEST":
            return p > x
        vname = "G1" if r.endswith("G1") else "G2"
        w = z3.And(win[vname] <= p, p < win[vname] + c)
        return w if not r.startswith("NOT_") else z3.Not(w)

    rd, rs = spec["dest"], spec["source"]
    s.add(inreg(rd["region"], x, False), inreg(rs["region"], y, True))
    # violation witnesses: (position, certain type)
    wit = []
    if atom[0] == "ORDER":
        i, j = z3.Ints("wi wj")
        s.add(0 <= i, i < j, j < N)
        wit = [(i, "PARTNER"), (j, "OWN")]
    elif atom[0] == "ZONE":
        j = z3.Int("wj")
        s.add(0 <= j, j < N, z3.Not(_zone(N, j, atom[2], atom[3])))
        wit = [(j, "OWN")]
    else:
        i, k, j = z3.Ints("wi wk wj")
        s.add(0 <= i, i < k, k < j, j < N)
        wit = [(i, "OWN"), (j, "OWN")]
    for sel, r, is_src in ((x, rd, False), (y, rs, True)):
        types = ["OWN"] if is_src else r["types"]
        for w, wt in wit:
            if wt not in types:
                continue
            cond = inreg(r["region"], w, is_src)
            if r["pick"] == "leftmost":
                s.add(z3.Implies(cond, sel <= w))
            elif r["pick"] == "rightmost":
                s.add(z3.Implies(cond, sel >= w))
            elif r["pick"] == "nearest_to_dest":
                s.add(z3.Implies(z3.And(cond, w != x), z3.If(sel > x, sel - x, x - sel) <= z3.If(w > x, w - x, x - w)))
    reg = rs["region"]
    no_own_between = (rs["pick"] == "leftmost" and reg == "RIGHT_OF_DEST") or \
                     (rs["pick"] == "rightmost" and reg == "LEFT_OF_DEST") or \
                     (rs["pick"] == "nearest_to_dest" and (reg in ("ALL", "LEFT_OF_DEST", "RIGHT_OF_DEST")
                                                          or (isinstance(reg, dict) and "within" in reg)))
    return s, {"N": N, "x": x, "y": y, "u": u, "v": v, "c": c, "win": win}, no_own_between


def template_region(s, V, t):
    N, x, y, u, v, c, win = V["N"], V["x"], V["y"], V["u"], V["v"], V["c"], V["win"]
    if t[0] == "OUT":
        return lambda z: _zone(N, z, t[2], t[3])
    p = t[1]
    st, ct = z3.Ints("st ct")
    hw = z3.Bool("hw")
    s.add(st >= 0, ct >= ZOps.I(u == p) + ZOps.I(v == p), st + ct <= N)
    if p == A1 and win:
        s.add(hw, ct == c)
        if t[2] in win:
            s.add(st == win[t[2]])
        elif t[2] == "G1":
            s.add(st <= win["G2"])
        else:
            s.add(st >= win["G1"])
    return lambda z: z3.And(hw, st <= z, z < st + ct)


def bound(spec, atom, key):
    s, V, nob = base(spec, atom)
    x, y, u, v = V["x"], V["y"], V["u"], V["v"]
    t = parse_key(key)
    if t[0] == "KD":
        L, R = z3.If(x < y, u, v), z3.If(x < y, v, u)
        w = z3.Int("w")
        extra = [0 <= w, w <= 4, z3.Or(y - x >= 2, x - y >= 2), kd_between(t[1], L, R, w, ZOps) > 0]
        if nob:
            extra.append(w != A1)
        r, m = _check(s, extra)
        if r == z3.sat:
            return {"status": "INF", "bound": "inf"}
        if r != z3.unsat:
            return {"status": "UNKNOWN", "bound": "inf"}
        dT = kd_end(t[1], L, R, ZOps)
        ks = range(len(t[1]) + 1, -len(t[1]) - 1, -1)
    else:
        inR = template_region(s, V, t)
        dT = exch(t[1], u, v, z3.Not(inR(x)), z3.Not(inR(y)), ZOps)
        ks = range(2, -2, -1)
    r0, _ = _check(s, [])
    if r0 == z3.unsat:
        return {"status": "VACUOUS", "bound": None}
    for k in ks:
        r, _ = _check(s, [dT >= k])
        if r == z3.unknown:
            return {"status": "UNKNOWN", "bound": "inf"}
        if r == z3.sat:
            return {"status": "PROVED", "bound": k}
    return {"status": "UNKNOWN", "bound": "inf"}


def own_measures(atom):
    if atom[0] == "ORDER":
        return ["KD{A1<A2}"]
    if atom[0] == "ZONE":
        return [f"OUT(A1,{atom[2]},{atom[3]})"]
    return ["OOW(A1,G1)", "OOW(A1,G2)"]


def progress(spec, atom, bounds):
    """Decrease part: some own measure template has a PROVED bound <= -1 (returns that template key or None)."""
    for k in own_measures(atom):
        b = bounds.get(k)
        if b and b["status"] == "PROVED" and b["bound"] <= -1:
            return k
    return None


def prove(spec, atom, gkey):
    s, V, nob = base(spec, atom)
    N, x, y, u, v, c, win = V["N"], V["x"], V["y"], V["u"], V["v"], V["c"], V["win"]
    g = _parse(gkey)
    if g[0] == "ORDER":
        p, q = ROLE[g[1]], ROLE[g[2]]
        L, R = z3.If(x < y, u, v), z3.If(x < y, v, u)
        n_p, n_q, n_o = z3.Ints("n_p n_q n_o")
        dist = z3.If(x < y, y - x, x - y)
        s.add(n_p >= 0, n_q >= 0, n_o >= 0, n_p + n_q + n_o == dist - 1)
        if nob:
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
        if p == A1:
            rd = spec["dest"]
            for vname, sv in win.items():                        # TZ-P1 family
                if _uses(rd["region"], "WINDOW_" + vname):
                    st = z3.Int("sstar_" + vname)
                    s.add(_zone(N, st, g[2], g[3]), _zone(N, st + c - 1, g[2], g[3]))
                    s.add(sv <= st if vname == "G1" else sv >= st)
            if atom[0] == "ZONE" and rd["region"] == "ZONE" and rd["pick"] in ("leftmost", "rightmost") \
                    and {"EMPTY", "OTHER"} <= set(rd["types"]):     # TZ-P2 family
                zs = z3.Int("zstar")
                s.add(_zone(N, zs, atom[2], atom[3]), _zone(N, zs, g[2], g[3]))
                s.add(zs <= x if rd["pick"] == "rightmost" else zs >= x)
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
    return {"status": "PROVED" if r == z3.unsat else "NOT_PROVED" if r == z3.sat else "UNKNOWN"}
