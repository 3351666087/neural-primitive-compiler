"""B-GRAM and B-R1 (amendment 5): laws that extrapolate to feature combinations never observed; factorised support.

Observations: the same draws as bexch.py / bdisc.py (sampler, seed, order, counts), and the same hold-out at N = 8.
B-GRAM  T(state) = sum_z t(c_z, m_z) + sum_{i<j} k(c_i, c_j); t: 10 parameters (content x region membership), k: 25
        (ordered content pairs). Each observation gives  delta = (statistics after - statistics before) . (t, k),
        memberships taken from each state's own region. Classes in order: t only, k only, both; the first exact fit
        is kept (else H_glob). From L0 (two-cell exchange) and the grammar:
          E(phi_l, phi_r)        = t(cr, ml) + t(cl, mr) - t(cl, ml) - t(cr, mr) + k(cr, cl) - k(cl, cr)
          B(phi_l, phi_r, phi_z) = k(cr, cz) + k(cz, cl) - k(cl, cz) - k(cz, cr)
        A value is identified iff its functional is orthogonal to the null space of the design matrix.
        L1: the exchange leaves every cell's region membership unchanged (checked on every observation).
B-R1    for H_end entries of B-EXCH (OUT/OOW): exact rank-1 completion of E[(cl, cr), (ml, mr)] = f(cl, cr) g(ml, mr)
        by the 2x2-minor rule and the zero-row / zero-column rules, to a fixpoint; a contradiction keeps the table.
S-fact  observed end-content pairs x observed end-membership pairs; KD triples: observed end-content pairs x observed
        between contents. It only enlarges the observed support.
Bounds as in bexch.derive (unknown or positive between terms, or unknown end terms, give infinity).
"""

from __future__ import annotations

import itertools
import random
import time

import numpy as np

import bexch
from libval import achiever_instances
from libval3 import Evaluator, parse_key
from potentials import patterns
from z3_damage import own_measure_key

U_IDX = {(c, m): i for i, (c, m) in enumerate(itertools.product(range(5), (0, 1)))}
K_IDX = {(a, b): 10 + i for i, (a, b) in enumerate(itertools.product(range(5), range(5)))}
CLASSES = (("t", list(range(10))), ("k", list(range(10, 35))), ("tk", list(range(35))))
ROWS = list(itertools.product(range(5), range(5)))
COLS = list(itertools.product((0, 1), (0, 1)))


def stats(cells, reg):
    v = np.zeros(35)
    cnt = [0] * 5
    for z, c in enumerate(cells):
        v[U_IDX[(c, 0 if reg is None else int(z in reg))]] += 1
        for a in range(5):
            if cnt[a]:
                v[K_IDX[(a, c)]] += cnt[a]
        cnt[c] += 1
    return v


def e_func(pair):
    (cl, ml), (cr, mr) = pair
    w = np.zeros(35)
    w[U_IDX[(cr, ml)]] += 1
    w[U_IDX[(cl, mr)]] += 1
    w[U_IDX[(cl, ml)]] -= 1
    w[U_IDX[(cr, mr)]] -= 1
    w[K_IDX[(cr, cl)]] += 1
    w[K_IDX[(cl, cr)]] -= 1
    return w


def b_func(triple):
    (cl, _), (cr, _), (cz, _) = triple
    w = np.zeros(35)
    w[K_IDX[(cr, cz)]] += 1
    w[K_IDX[(cz, cl)]] += 1
    w[K_IDX[(cl, cz)]] -= 1
    w[K_IDX[(cz, cr)]] -= 1
    return w


# ------------------------------------------------------------------ data (the same draws as bexch.learn)
def collect(n, sizes=(5, 6, 7), seed=11):
    rng = random.Random(seed)
    data = {}
    for akey, a, v in achiever_instances():
        keys = patterns(a[0])
        obs = []
        for N in sizes:
            o, _ = bexch.observe(a, v, N, n, rng)
            ev = Evaluator(keys, N)
            obs += [(c, h, f, af, ev(c, h, f), ev(af, h, f), bexch.exchange_cells(c, af)) for c, h, f, af in o]
        data[akey] = obs
    return data


def holdout(N=8, n=200, seed=12):
    rng = random.Random(seed)
    data = {}
    for akey, a, v in achiever_instances():
        keys = patterns(a[0])
        o, _ = bexch.observe(a, v, N, n, rng)
        ev = Evaluator(keys, N)
        data[akey] = [(c, h, f, af, ev(c, h, f), ev(af, h, f), bexch.exchange_cells(c, af)) for c, h, f, af in o]
    return data


# ------------------------------------------------------------------ B-GRAM
class Gram:
    def __init__(self, law, theta=None, null=None, cols=None):
        self.law, self.theta, self.null, self.cols = law, theta, null, cols

    def value(self, w):
        if self.law == "GLOB":
            return None
        wc = w[self.cols]
        if self.null is not None and len(self.null) and np.max(np.abs(self.null @ wc)) > 1e-8:
            return None
        x = float(wc @ self.theta)
        return int(round(x)) if abs(x - round(x)) < 1e-6 else x


def gram_design(key, obs, cache):
    t = parse_key(key)
    sig = t[0] if t[0] == "KD" else t
    if sig not in cache:
        F, l1_fail = [], 0
        for cells, haz, fixed, after, vb, va, lr in obs:
            rb, ra = bexch.region(t, cells, haz, fixed), bexch.region(t, after, haz, fixed)
            if rb != ra:
                l1_fail += 1
            F.append(stats(after, ra) - stats(cells, rb))
        cache[sig] = (np.array(F), l1_fail)
    F, l1 = cache[sig]
    d = np.array([va[key] - vb[key] for _, _, _, _, vb, va, _ in obs], dtype=float)
    return F, d, l1


def fit_gram(F, d):
    for name, cols in CLASSES:
        D = F[:, cols]
        sol, *_ = np.linalg.lstsq(D, d, rcond=None)
        if np.max(np.abs(D @ sol - d)) > 1e-6:
            continue
        M = D if D.shape[0] >= D.shape[1] else np.vstack([D, np.zeros((D.shape[1] - D.shape[0], D.shape[1]))])
        _, S, Vt = np.linalg.svd(M, full_matrices=False)
        rank = int(np.sum(S > 1e-9 * max(1.0, S[0]))) if len(S) else 0
        return Gram(name, sol, Vt[rank:], cols)
    return Gram("GLOB")


def derive_gram(g, pairs_S, triples_S):
    if g.law == "GLOB":
        return "inf", "glob"
    if g.law != "t":                               # under "t only" every between term is 0 by the grammar
        for tr in triples_S:
            b = g.value(b_func(tr))
            if b is None:
                return "inf", "unknown_between"
            if b > 0:
                return "inf", "positive_between"
    vals = []
    for p in pairs_S:
        e = g.value(e_func(p))
        if e is None:
            return "inf", "unknown_end"
        vals.append(e)
    return (max(vals) if vals else None), "ok"


# ------------------------------------------------------------------ B-R1
def r1_complete(E):
    """E: {((cl, ml), (cr, mr)): value or None}. Returns (completed dict, contradiction flag)."""
    known = {((cl, cr), (ml, mr)): v for ((cl, ml), (cr, mr)), v in E.items() if v is not None}
    contradiction = False

    def put(rc, v):
        nonlocal contradiction
        if rc in known:
            if abs(known[rc] - v) > 1e-9:
                contradiction = True
            return False
        known[rc] = v
        return True

    changed = True
    while changed and not contradiction:
        changed = False
        nzc = {c for (r, c), v in known.items() if v != 0}
        nzr = {r for (r, c), v in known.items() if v != 0}
        for (r, c), v in list(known.items()):
            if v == 0 and c in nzc:
                for c2 in COLS:
                    changed |= put((r, c2), 0)
            if v == 0 and r in nzr:
                for r2 in ROWS:
                    changed |= put((r2, c), 0)
        nz = [(rc, v) for rc, v in known.items() if v != 0]
        for (r2, c2), v22 in nz:
            col_c2 = [(r, v) for (r, c), v in list(known.items()) if c == c2]
            row_r2 = [(c, v) for (r, c), v in list(known.items()) if r == r2]
            for r, vr in col_c2:
                for c, vc in row_r2:
                    x = vr * vc / v22
                    changed |= put((r, c), int(round(x)) if abs(x - round(x)) < 1e-9 else x)
    out = {((r[0], c[0]), (r[1], c[1])): v for (r, c), v in known.items()}
    return out, contradiction


# ------------------------------------------------------------------ supports
def s_obs(rows):
    return {p for p, _, _ in rows}, {t for _, ts, _ in rows for t in ts}


def s_fact(rows):
    cp = {(p[0][0], p[1][0]) for p, _, _ in rows}
    mp = {(p[0][1], p[1][1]) for p, _, _ in rows}
    cz = {t[2][0] for _, ts, _ in rows for t in ts}
    pairs = {((cl, ml), (cr, mr)) for (cl, cr) in cp for (ml, mr) in mp}
    triples = {((cl, 0), (cr, 0), (c, 0)) for (cl, cr) in cp for c in cz}
    return pairs, triples


# ------------------------------------------------------------------ one variant
def run_variant(n, sizes, hold):
    """Fits (B-EXCH reference, B-GRAM, B-R1) for one variant; returns per-entry records and diagnostics."""
    c0 = time.process_time()
    data = collect(n, sizes)
    t_collect = time.process_time() - c0
    rec, diag = {}, {"L0_failures": 0, "L1_failures": 0, "holdout": {"predicted": 0, "unpredicted": 0, "errors": 0}}
    t_gram = t_r1 = 0.0
    for akey, a, v in achiever_instances():
        obs = data[akey]
        diag["L0_failures"] += sum(lr is None for *_, lr in obs)
        cache = {}
        rec[akey] = {}
        for k in patterns(a[0]):
            rows = bexch.rows_for(k, obs)
            ex = bexch.fit(rows)
            g0 = time.process_time()
            F, d, l1 = gram_design(k, obs, cache)
            g = fit_gram(F, d)
            t_gram += time.process_time() - g0
            r0 = time.process_time()
            r1 = None
            if ex["law"] == "END":
                comp, bad = r1_complete(ex["E"])
                r1 = {"law": "END", "E": ex["E"] if bad else comp, "contradiction": bad}
            t_r1 += time.process_time() - r0
            hp = hu = he = 0
            for p, ts, dd in bexch.rows_for(k, hold[akey]):
                pr = None if g.law == "GLOB" else g.value(e_func(p) + sum((b_func(t) for t in ts), np.zeros(35)))
                if pr is None:
                    hu += 1
                else:
                    hp += 1
                    he += pr != dd
            diag["holdout"]["predicted"] += hp
            diag["holdout"]["unpredicted"] += hu
            diag["holdout"]["errors"] += he
            rec[akey][k] = {"rows_obs": s_obs(rows), "rows_fact": s_fact(rows), "exch": ex, "gram": g, "r1": r1,
                            "l1": l1}
        diag["L1_failures"] += sum(l1 for _, l1 in cache.values())
    diag["cpu"] = {"collect": t_collect, "gram_fit": t_gram, "r1": t_r1, "total": time.process_time() - c0}
    return rec, diag


def tables(rec, law, support, given=None):
    dmg, prog = {}, {}
    for akey, row in rec.items():
        ent = {}
        for k, r in row.items():
            if support == "obs":
                P, T = r["rows_obs"]
            elif support == "fact":
                P, T = r["rows_fact"]
            else:
                P, T = given[akey][k]
            if law == "gram":
                b, why = derive_gram(r["gram"], P, T)
                lname = r["gram"].law
            elif law == "r1" and r["r1"] is not None:
                b, why = bexch.derive(r["r1"], P, T)
                lname = "R1"
            else:
                b, why = bexch.derive(r["exch"], P, T)
                lname = r["exch"]["law"]
            ent[k] = {"law": lname, "bound": b, "reason": why, "evidence": "BX" if b not in (None, "inf") else None}
        dmg[akey] = {"entries": ent}
        mk = ent[own_measure_key(akey)]
        ok = mk["bound"] not in (None, "inf") and mk["bound"] <= -1
        prog[akey] = {"ok": ok, "evidence": "BX" if ok else None}
    return dmg, prog


def gram_law_check(rec, given):
    """F1(c): identified E and B values against the exchange formula on every S-given combination."""
    mism = []
    for akey, row in rec.items():
        for k, r in row.items():
            g = r["gram"]
            if g.law == "GLOB":
                continue
            P, T = given[akey][k]
            for p in P:
                x = g.value(e_func(p))
                if x is not None and x != bexch.formula(k, p):
                    mism.append(f"{akey} / {k} E{p}: {x} vs {bexch.formula(k, p)}")
            if g.law != "t":
                for t in T:
                    x = g.value(b_func(t))
                    if x is not None and x != bexch.formula(k, t[:2], t):
                        mism.append(f"{akey} / {k} B{t}: {x} vs {bexch.formula(k, t[:2], t)}")
    return {"mismatches": len(mism), "examples": mism[:10]}
