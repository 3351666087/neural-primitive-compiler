"""A+ (amendment 7): the G3 encoding (g3/z3_dsl.py, unchanged) plus two necessary-constraint families.

R1  KD increments with between cells counted by content: delta = end term + sum_c n_c * B(L, R, c), n_c >= 0,
    sum_c n_c = |x - y| - 1; "no OWN between" is n_A1 = 0; a violation witness of certain content (OWN, PARTNER)
    strictly between x and y forces n_content >= the number of such witnesses. INF iff delta >= 50 is satisfiable;
    otherwise the bound is the largest k with delta >= k satisfiable (binary search; delta >= k+1 is unsat).
R2  joint-satisfiability witness cells. ZONE atom, violated and satisfiable on its own: some cell z* in the zone is
    usable and holds no A1, so it is EMPTY or OTHER. GROUP atom, violated and satisfiable: both A1 windows exist and
    each holds a cell of type EMPTY or OTHER. For a dest rule picking leftmost (rightmost) whose types contain EMPTY
    and OTHER: a witness cell in the rule's region gives x <= cell (x >= cell).
OUT / OOW use the same exchange term as before, under the R2-extended constraints.
"""

from __future__ import annotations

import sys
from pathlib import Path

import z3

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(EXP / "lib"))
sys.path.insert(0, str(EXP / "g3"))
import dsl  # noqa: E402
import z3_dsl  # noqa: E402
from libval import ROLE  # noqa: E402
from libval3 import parse_key  # noqa: E402
from potentials import patterns  # noqa: E402
from z3_damage import ZOps, _check, _zone, exch, kd_end  # noqa: E402

A1, A2 = ROLE["A1"], ROLE["A2"]
TOP = 50


def base_plus(spec, atom, timeout_ms=20000):
    s = z3.Solver()
    s.set("timeout", timeout_ms)
    N, x, y, u, v = z3.Ints("N x y u v")
    s.add(N >= 3, 0 <= x, x < N, 0 <= y, y < N, x != y, 0 <= u, u <= 4, v == A1)
    s.add(z3.Or([u == c for c in sorted(z3_dsl._contents(atom, spec["dest"]["types"]))]))
    c = z3.Int("cA1")
    s.add(c >= 1)
    win = {}
    for vname in ("G1", "G2"):
        used = any(z3_dsl._uses(spec[r]["region"], n + vname) for r in ("dest", "source") for n in ("WINDOW_", "NOT_WINDOW_"))
        if used or atom[0] == "GROUP":
            sv = z3.Int("s_" + vname)
            s.add(sv >= 0, sv + c <= N)
            win[vname] = sv
    if len(win) == 2:
        s.add(win["G1"] <= win["G2"])

    def inreg(r, p):
        if isinstance(r, dict):
            if "and" in r:
                return z3.And(inreg(r["and"][0], p), inreg(r["and"][1], p))
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
    s.add(inreg(rd["region"], x), inreg(rs["region"], y))
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
            cond = inreg(r["region"], w)
            if r["pick"] == "leftmost":
                s.add(z3.Implies(cond, sel <= w))
            elif r["pick"] == "rightmost":
                s.add(z3.Implies(cond, sel >= w))
            elif r["pick"] == "nearest_to_dest":
                s.add(z3.Implies(z3.And(cond, w != x), z3.If(sel > x, sel - x, x - sel) <= z3.If(w > x, w - x, x - w)))
    # R2: joint-satisfiability witness cells (type EMPTY or OTHER)
    cells = []
    if atom[0] == "ZONE":
        zs = z3.Int("zstar")
        s.add(0 <= zs, zs < N, _zone(N, zs, atom[2], atom[3]))
        cells.append(zs)
    elif atom[0] == "GROUP":
        for vname, sv in win.items():
            g = z3.Int("wcell_" + vname)
            s.add(sv <= g, g < sv + c)
            cells.append(g)
    if rd["pick"] in ("leftmost", "rightmost") and {"EMPTY", "OTHER"} <= set(rd["types"]):
        for g in cells:
            s.add(z3.Implies(inreg(rd["region"], g), x <= g if rd["pick"] == "leftmost" else x >= g))
    reg = rs["region"]
    nob = (rs["pick"] == "leftmost" and reg == "RIGHT_OF_DEST") or (rs["pick"] == "rightmost" and reg == "LEFT_OF_DEST") or \
          (rs["pick"] == "nearest_to_dest" and (reg in ("ALL", "LEFT_OF_DEST", "RIGHT_OF_DEST") or (isinstance(reg, dict) and "within" in reg)))
    content = {"OWN": A1, "PARTNER": A2}
    return s, {"N": N, "x": x, "y": y, "u": u, "v": v, "c": c, "win": win,
               "witnesses": [(w, content[t]) for w, t in wit]}, nob


def _scaled(pairs, L, R, cc, n):
    """n * B(L, R, cc) for a constant between content cc, as a linear term."""
    t = 0
    for lo, hi in pairs:
        if cc == lo:
            t += z3.If(R == hi, n, 0) - z3.If(L == hi, n, 0)
        if cc == hi:
            t += z3.If(L == lo, n, 0) - z3.If(R == lo, n, 0)
    return t


def bound_plus(spec, atom, key):
    s, V, nob = base_plus(spec, atom)
    x, y, u, v = V["x"], V["y"], V["u"], V["v"]
    if _check(s, [])[0] == z3.unsat:
        return {"status": "VACUOUS", "bound": None}
    t = parse_key(key)
    if t[0] == "KD":
        L, R = z3.If(x < y, u, v), z3.If(x < y, v, u)
        lo, hi = z3.If(x < y, x, y), z3.If(x < y, y, x)
        n = [z3.Int(f"n{cc}") for cc in range(5)]
        s.add(*[nc >= 0 for nc in n], z3.Sum(n) == hi - lo - 1)
        if nob:
            s.add(n[A1] == 0)
        for cc in (A1, A2):
            ws = [w for w, wc in V["witnesses"] if wc == cc]
            if ws:
                s.add(n[cc] >= z3.Sum([z3.If(z3.And(lo < w, w < hi), 1, 0) for w in ws]))
        dT = kd_end(t[1], L, R, ZOps) + z3.Sum([_scaled(t[1], L, R, cc, n[cc]) for cc in range(5)])
    else:
        inR = z3_dsl.template_region(s, V, t)
        dT = exch(t[1], u, v, z3.Not(inR(x)), z3.Not(inR(y)), ZOps)
    r, _ = _check(s, [dT >= TOP])
    if r == z3.sat:
        return {"status": "INF", "bound": "inf"}
    if r == z3.unknown:
        return {"status": "UNKNOWN", "bound": "inf"}
    lo_k, hi_k = -TOP, TOP
    r, _ = _check(s, [dT >= lo_k])
    if r != z3.sat:
        return {"status": "UNKNOWN", "bound": "inf"}
    while hi_k - lo_k > 1:
        mid = (lo_k + hi_k) // 2
        r, _ = _check(s, [dT >= mid])
        if r == z3.unknown:
            return {"status": "UNKNOWN", "bound": "inf"}
        if r == z3.sat:
            lo_k = mid
        else:
            hi_k = mid
    return {"status": "PROVED", "bound": lo_k}


def a_tables_plus(specs, inst, tr):
    """As a_dsl.a_tables, with bound_plus for damage and progress; preservation as in G3 (z3_dsl.prove)."""
    damage, progress, preserves = {}, {}, {}
    sp_of = {k: sp for sp in specs for k, _ in dsl.instances(sp)}
    for k, a in inst:
        sp = sp_of[k]
        b = {x: bound_plus(sp, a, x) for x in patterns(a[0])}
        damage[k] = {"entries": {x: {"bound": e["bound"], "evidence": "TZ" if e["status"] == "PROVED" else None,
                                     "status": e["status"]} for x, e in b.items()}}
        m = z3_dsl.progress(sp, a, b)
        ok = m is not None and tr[k]["applicability_cex"] is None
        progress[k] = {"ok": ok, "evidence": "TZ" if ok else None, "measure": m,
                       "decrease_proved": m is not None, "applicability_N7": tr[k]["applicability_cex"] is None}
        preserves[k] = {}
        for gk in tr[k]["preserves"]:
            st = z3_dsl.prove(sp, a, gk)["status"]
            preserves[k][gk] = {"ok": st == "PROVED", "evidence": "TZ" if st == "PROVED" else None, "status": st}
    return {"damage": damage, "progress": progress, "preserves": preserves}
