"""A++ (amendment 8): A+ (r7/zplus.py, unchanged) plus witness-position consistency: a violation witness of certain
content (OWN, PARTNER) that coincides with x has content u, and one that coincides with y has content v. A necessary
constraint (the real witness satisfies it). Bounds and progress as in A+.
"""

from __future__ import annotations

import sys
from pathlib import Path

import z3

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(EXP / "lib"))
sys.path.insert(0, str(EXP / "g3"))
sys.path.insert(0, str(EXP / "r7"))
import dsl  # noqa: E402
import z3_dsl  # noqa: E402
import zplus  # noqa: E402
from libval3 import parse_key  # noqa: E402
from potentials import patterns  # noqa: E402
from z3_damage import ZOps, _check, exch, kd_end  # noqa: E402

A1, A2 = zplus.A1, zplus.A2
TOP = zplus.TOP


def base_pp(spec, atom, timeout_ms=20000):
    s, V, nob = zplus.base_plus(spec, atom, timeout_ms)
    for w, cw in V["witnesses"]:
        s.add(z3.Implies(w == V["x"], V["u"] == cw), z3.Implies(w == V["y"], V["v"] == cw))
    return s, V, nob


def bound_pp(spec, atom, key):
    s, V, nob = base_pp(spec, atom)
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
        dT = kd_end(t[1], L, R, ZOps) + z3.Sum([zplus._scaled(t[1], L, R, cc, n[cc]) for cc in range(5)])
    else:
        inR = z3_dsl.template_region(s, V, t)
        dT = exch(t[1], u, v, z3.Not(inR(x)), z3.Not(inR(y)), ZOps)
    r, _ = _check(s, [dT >= TOP])
    if r == z3.sat:
        return {"status": "INF", "bound": "inf"}
    if r == z3.unknown:
        return {"status": "UNKNOWN", "bound": "inf"}
    lo_k, hi_k = -TOP, TOP
    if _check(s, [dT >= lo_k])[0] != z3.sat:
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


def a_tables_pp(specs, inst, tr):
    damage, progress, preserves = {}, {}, {}
    sp_of = {k: sp for sp in specs for k, _ in dsl.instances(sp)}
    for k, a in inst:
        sp = sp_of[k]
        b = {x: bound_pp(sp, a, x) for x in patterns(a[0])}
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
