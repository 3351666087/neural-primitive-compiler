"""Emit the controller IR for a priority plan whose achievers are ACH-DSL specs (G3). CONSTRUCTOR SIDE.

Identical to cirgen.emit except for the selection: plan = [(atom, spec), ...]; the spec's dest and source rules are
compiled from the same primitives (colour bundles, prefix ORs, leftmost / rightmost, window features with
ATLEAST). nearest_to_dest compiles to, for each pair (d, p), an AND of dest[d], cand[p] and the negation of every
candidate strictly nearer to d (or equally near and to the left).
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))
from cirgen import G  # noqa: E402
from model import zcells  # noqa: E402


def emit_dsl(plan, spec, N):
    g = G("ctrl")
    rule = any(s[0] == "NO_DROP_HAZARD" for s in spec["safety"])
    fixedcols = [s[1] for s in spec["safety"] if s[0] == "NO_PICK"]
    cue = spec.get("cue") or []
    P = range(N)
    bind = {}
    for v in cue:
        present = g.OR([f"cue_{v}_{k}" for k in range(1, 5)])
        relays = [g.AND([f"cue_{v}_{k}"], []) for k in range(1, 5)]
        bind[v] = g.REG(f"B{v}", 4, [{"when": present, "load": relays}])
    ready = g.OR(bind[cue[0]]) if cue else None
    cache = {}

    def obj(c):
        if c in cache:
            return cache[c]
        if isinstance(c, str):
            out = [g.OR([g.AND([bind[c][k], f"col_{p}_{k + 1}"], []) for k in range(4)]) for p in P]
        else:
            out = [f"col_{p}_{c}" for p in P]
        cache[c] = out
        return out
    occ = [g.NOT(f"col_{p}_0") for p in P]
    af = [g.AND([f"col_{p}_0"], [f"haz_{p}"]) if rule else f"col_{p}_0" for p in P]
    fixed = [g.OR([f"col_{p}_{c}" for c in fixedcols]) if fixedcols else g.F for p in P]

    def atom_viol(a):
        t = a[0]
        if t == "ORDER":
            A1, A2 = obj(a[1]), obj(a[2])
            L2 = g.prefix_left(A2)
            return g.OR([g.AND([A1[q], L2[q]], []) for q in P])
        if t == "ZONE":
            z = set(zcells(N, a[2], a[3]))
            return g.OR([obj(a[1])[p] for p in P if p not in z])
        o = obj(a[1])
        L, R = g.prefix_left(o), g.prefix_right(o)
        return g.OR([g.AND([L[q], R[q]], [o[q]]) for q in P])

    def window(c, var):
        o = obj(c)
        ge = [g.ATLEAST(k, o) for k in range(1, N + 1)] + [g.F]
        eq = {k: g.AND([ge[k - 1]], [ge[k]]) for k in range(1, N + 1)}
        other_fixed = [g.OR([f"col_{p}_{f}" for f in fixedcols if f != c]) if [f for f in fixedcols if f != c] else g.F
                       for p in P]
        cellok = [g.AND([], ([f"haz_{p}"] if rule else []) + [other_fixed[p]]) for p in P]
        valid = []
        for s in P:
            valid.append(g.OR([g.AND([eq[k], g.AND(cellok[s:s + k], [])], []) for k in range(1, N - s + 1)]))
        wsel = g.leftmost(valid) if var == "G1" else g.rightmost(valid)
        wsk = {(s, k): g.AND([wsel[s], eq[k]], []) for s in P for k in range(1, N - s + 1)}
        return [g.OR([wsk[(s, k)] for (s, k) in wsk if s <= p < s + k]) for p in P]

    def types_vec(a, names):
        c1 = a[1]
        own = obj(c1)
        partner = obj(a[2]) if a[0] == "ORDER" else [g.F] * N
        vec = []
        for p in P:
            terms = []
            if "EMPTY" in names:
                terms.append(af[p])
            if "PARTNER" in names:
                terms.append(partner[p])
            if "OTHER" in names:
                terms.append(g.AND([occ[p]], [own[p], partner[p], fixed[p]]))
            if "OWN" in names:
                terms.append(own[p])
            vec.append(g.OR(terms))
        return vec

    def region(a, r, d=None, wcache=None):
        if isinstance(r, dict):
            if "and" in r:
                m1, m2 = region(a, r["and"][0], d, wcache), region(a, r["and"][1], d, wcache)
                return [g.AND([m1[p], m2[p]], []) for p in P]
            k = r["within"]
            return [g.OR([d[q] for q in P if abs(q - p) <= k]) for p in P]
        if r == "ALL":
            return [g.T] * N
        if r in ("ZONE", "NOT_ZONE"):
            z = set(zcells(N, a[2], a[3]))
            return [g.T if (p in z) == (r == "ZONE") else g.F for p in P]
        if r == "LEFT_OF_DEST":
            return g.prefix_right(d)                   # some dest cell right of p
        if r == "RIGHT_OF_DEST":
            return g.prefix_left(d)
        v = "G1" if r.endswith("G1") else "G2"
        if v not in wcache:
            wcache[v] = window(a[1], v)
        w = wcache[v]
        return w if not r.startswith("NOT_") else [g.NOT(w[p]) for p in P]

    def pick(cand, how, d=None):
        if how == "leftmost":
            return g.leftmost(cand)
        if how == "rightmost":
            return g.rightmost(cand)
        if how == "second_leftmost":
            L = g.prefix_left(cand)
            return g.leftmost([g.AND([cand[p], L[p]], []) for p in P])
        if how == "second_rightmost":
            R = g.prefix_right(cand)
            return g.rightmost([g.AND([cand[p], R[p]], []) for p in P])
        out = [[] for _ in P]                          # nearest_to_dest
        for dd in P:
            for p in P:
                if p == dd:
                    continue
                block = [cand[q] for q in P if q != p and (abs(q - dd) < abs(p - dd) or (abs(q - dd) == abs(p - dd) and q < p))]
                out[p].append(g.AND([d[dd], cand[p]], block))
        return [g.OR(t) for t in out]

    def selection(a, sp):
        wcache = {}
        rd, rs = sp["dest"], sp["source"]
        md = region(a, rd["region"], wcache=wcache)
        td = types_vec(a, rd["types"])
        X = pick([g.AND([md[p], td[p]], []) for p in P], rd["pick"])
        ms = region(a, rs["region"], d=X, wcache=wcache)
        ts = types_vec(a, ["OWN"])
        Y = pick([g.AND([ms[p], ts[p]], []) for p in P], rs["pick"], d=X)
        return X, Y

    viol = [atom_viol(a) for a, _ in plan]
    sels = [selection(a, sp) for a, sp in plan]
    first = [g.AND([viol[i]], viol[:i]) for i in range(len(plan))]
    Xsel = [g.OR([g.AND([first[i], sels[i][0][p]], []) for i in range(len(plan))]) for p in P]
    Ysel = [g.OR([g.AND([first[i], sels[i][1][p]], []) for i in range(len(plan))]) for p in P]
    spare = g.leftmost(af)
    xocc = g.OR([g.AND([Xsel[p], occ[p]], []) for p in P])
    nxocc = g.NOT(xocc)
    anyviol = g.OR(viol)
    agR = g.prefix_right([f"ag_{p}" for p in P])
    agL = g.prefix_left([f"ag_{p}" for p in P])
    PH = [f"PH[{k}]" for k in range(6)]
    regs = {r: [f"{r}[{p}]" for p in P] for r in ("X", "Y", "S")}

    def nav(r):
        R = regs[r]
        at = g.OR([g.AND([R[p], f"ag_{p}"], []) for p in P])
        tl = g.OR([g.AND([R[p], agR[p]], []) for p in P])
        tr = g.OR([g.AND([R[p], agL[p]], []) for p in P])
        return at, tl, tr
    navs = {r: nav(r) for r in ("X", "Y", "S")}
    target = ["X", "S", "Y", "X", "S", "Y"]
    idle = g.AND([], PH)
    base = [ready] if cue else []
    start = g.AND([idle, anyviol, "hand_0"] + base, [])
    stop = g.AND([idle, "hand_0"] + base, [anyviol])
    left = g.OR([g.AND([PH[k], navs[target[k]][1]], []) for k in range(6)])
    right = g.OR([g.AND([PH[k], navs[target[k]][2]], []) for k in range(6)])
    arrive = [g.AND([PH[k], navs[target[k]][0]], []) for k in range(6)]
    pick_ = g.OR([arrive[0], arrive[2], arrive[4]])
    drop = g.OR([arrive[1], arrive[3], arrive[5]])
    a3_occ = g.AND([arrive[3], "XO[0]"], [])
    a3_free = g.AND([arrive[3]], ["XO[0]"])
    g.REG("PH", 6, [{"when": start, "load": [xocc, g.F, nxocc, g.F, g.F, g.F]},
                    {"when": arrive[0], "one": 1}, {"when": arrive[1], "one": 2}, {"when": arrive[2], "one": 3},
                    {"when": a3_occ, "one": 4}, {"when": a3_free, "zero": True},
                    {"when": arrive[4], "one": 5}, {"when": arrive[5], "zero": True}])
    g.REG("X", N, [{"when": start, "load": Xsel}])
    g.REG("Y", N, [{"when": start, "load": Ysel}])
    g.REG("S", N, [{"when": start, "load": spare}])
    g.REG("XO", 1, [{"when": start, "load": [xocc]}])
    return {"name": f"plan@N{N}", "nodes": g.nodes,
            "outputs": {"LEFT": left, "RIGHT": right, "PICK": pick_, "DROP": drop, "STOP": stop}}
