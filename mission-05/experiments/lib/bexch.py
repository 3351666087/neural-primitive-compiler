"""B-EXCH (amendment 4): learn the local decomposition of template increments from observed relocations, then derive
bounds that do not depend on N.

Observations: the same draws as bdisc.py (same sampler, seed, order and counts), so B-EXCH and B-DISC see the same
data. B sees the full state before and after each relocation and the template values; nothing else.
  L0     each observation: exactly two cells changed and their contents were exchanged (l < r)
  phi    a cell's feature: (content, member of the template's region) -- the zone of OUT, the window of OOW in the
         state before (no window: not a member), none for KD
  H_end  delta = E[phi(l), phi(r)]
  H_loc  delta = E[phi(l), phi(r)] + sum over l < z < r of B[phi(l), phi(r), phi(z)]
  H_glob neither fits exactly: no bound
The first class that fits every training observation exactly is selected (least squares, residual 0). A coefficient
is identified iff the null space of the design matrix vanishes on it; others are unknown. Under H_end the between
term is taken to be 0 (that is the class's claim).
Support:  S-obs  the observed (phi_l, phi_r) pairs and (phi_l, phi_r, phi_z) triples
          S-given  the combinations the library's selection rules allow (the TZ encoding, z3_damage.achiever_base),
                   decided by Z3 for each combination
Bound: infinite if the class is H_glob, or (H_loc) a supported triple has an unknown or positive between term, or a
supported pair has an unknown end term; else the maximum end term over the supported pairs. Evidence tag "BX".
Progress: the achiever's own measure template has bound <= -1 (applicability lemma [P], as in TZ).
"""

from __future__ import annotations

import itertools
import random
import time

import numpy as np
import z3

from bdisc import sample_state
from libval import ROLE, achiever_instances
from libval2 import eligible
from libval3 import Evaluator, parse_key
from model import group_window, reloc, select, zcells
from potentials import patterns
from z3_damage import PyOps, ZOps, achiever_base, exch, kd_between, kd_end, own_measure_key, template_region

A1 = ROLE["A1"]
CONTENTS = range(5)


# ------------------------------------------------------------------ observation
def observe(a, v, N, n, rng, max_tries=200_000):
    """The same draws as bdisc.observe; returns [(cells, haz, fixed, after)]."""
    obs = []
    got = tries = 0
    while got < n and tries < max_tries:
        tries += 1
        cells, haz, fixed = sample_state(N, rng)
        if not eligible(a, cells, haz, fixed):
            continue
        sel = select(a, v, cells, haz, True, fixed, ROLE)
        if sel is None:
            continue
        r = reloc(cells, 0, sel[0], sel[1], haz, True)
        if r is None:
            continue
        got += 1
        obs.append((cells, haz, fixed, r[0]))
    return obs, tries


def exchange_cells(cells, after):
    ch = [i for i in range(len(cells)) if cells[i] != after[i]]
    if len(ch) == 2 and cells[ch[0]] == after[ch[1]] and cells[ch[1]] == after[ch[0]]:
        return ch[0], ch[1]
    return None


def region(t, cells, haz, fixed):
    if t[0] == "KD":
        return None
    if t[0] == "OUT":
        return set(zcells(len(cells), t[2], t[3]))
    w = group_window(["GROUP", t[1]], cells, {}, haz, True, fixed, t[2])
    return w if w is not None else set()


def phi(cells, z, reg):
    return (cells[z], 0 if reg is None else int(z in reg))


# ------------------------------------------------------------------ fitting
def rows_for(key, obs):
    """[(pair, [triples], delta)] for one template over the observations (L0 failures are skipped and counted)."""
    t = parse_key(key)
    out = []
    for cells, haz, fixed, after, vals_b, vals_a, lr in obs:
        if lr is None:
            continue
        l, r = lr
        reg = region(t, cells, haz, fixed)
        pl, pr = phi(cells, l, reg), phi(cells, r, reg)
        out.append(((pl, pr), [(pl, pr, phi(cells, z, reg)) for z in range(l + 1, r)], vals_a[key] - vals_b[key]))
    return out


_SVD = {}


def _identified(M):
    """Coefficient i is identified iff every null-space vector of M is 0 at i (cached: the KD templates of one
    achiever share the design matrix)."""
    key = (M.shape, hash(M.tobytes()))
    if key not in _SVD:
        if M.shape[0] < M.shape[1]:                # zero rows do not change the null space
            M = np.vstack([M, np.zeros((M.shape[1] - M.shape[0], M.shape[1]))])
        _, S, Vt = np.linalg.svd(M, full_matrices=False)
        rank = int(np.sum(S > 1e-9 * max(1.0, S[0])))
        null = Vt[rank:]
        _SVD[key] = np.all(np.abs(null) < 1e-8, axis=0) if len(null) else np.ones(M.shape[1], dtype=bool)
    return _SVD[key]


def fit(rows):
    pairs = {}
    for p, _, d in rows:
        pairs.setdefault(p, set()).add(d)
    triples_seen = sorted({t for _, ts, _ in rows for t in ts})
    if all(len(s) == 1 for s in pairs.values()):
        return {"law": "END", "E": {p: next(iter(s)) for p, s in pairs.items()}, "B": {},
                "pairs": set(pairs), "triples": set(triples_seen)}
    E_idx = {p: i for i, p in enumerate(sorted(pairs))}
    B_idx = {t: len(E_idx) + j for j, t in enumerate(triples_seen)}
    M = np.zeros((len(rows), len(E_idx) + len(B_idx)))
    d = np.zeros(len(rows))
    for o, (p, ts, dd) in enumerate(rows):
        M[o, E_idx[p]] = 1
        for t in ts:
            M[o, B_idx[t]] += 1
        d[o] = dd
    sol, *_ = np.linalg.lstsq(M, d, rcond=None)
    if np.max(np.abs(M @ sol - d)) > 1e-6:
        return {"law": "GLOB", "E": {}, "B": {}, "pairs": set(pairs), "triples": set(triples_seen)}
    ident = _identified(M)

    def val(i):
        if not ident[i]:
            return None
        x = float(sol[i])
        return int(round(x)) if abs(x - round(x)) < 1e-6 else x
    return {"law": "LOC", "E": {p: val(i) for p, i in E_idx.items()}, "B": {t: val(i) for t, i in B_idx.items()},
            "pairs": set(pairs), "triples": set(triples_seen)}


def predict(f, pair, triples):
    if f["law"] == "GLOB":
        return None
    e = f["E"].get(pair)
    if e is None:
        return None
    if f["law"] == "END":
        return e
    tot = e
    for t in triples:
        b = f["B"].get(t)
        if b is None:
            return None
        tot += b
    return tot


def derive(f, pairs_S, triples_S):
    if f["law"] == "GLOB":
        return "inf", "glob"
    if f["law"] == "LOC":
        for t in triples_S:
            b = f["B"].get(t)
            if b is None:
                return "inf", "unknown_between"
            if b > 0:
                return "inf", "positive_between"
    vals = []
    for p in pairs_S:
        e = f["E"].get(p)
        if e is None:
            return "inf", "unknown_end"
        vals.append(e)
    return (max(vals) if vals else None), "ok"


# ------------------------------------------------------------------ the exchange formula (for the D1 check only)
def formula(key, pair, triple=None):
    t = parse_key(key)
    (cl, ml), (cr, mr) = pair
    if t[0] == "KD":
        return kd_end(t[1], cl, cr, PyOps) if triple is None else kd_between(t[1], cl, cr, triple[2][0], PyOps)
    if triple is not None:
        return 0
    return exch(t[1], cl, cr, ml == 0, mr == 0, PyOps)


# ------------------------------------------------------------------ S-given: the library's allowed combinations
def given_support(atom, var, key, want_triples):
    s, V, no_A1_between = achiever_base(atom, var)
    N, x, y, u, v, sa, ca = V
    t = parse_key(key)
    L, R = z3.If(x < y, u, v), z3.If(x < y, v, u)
    if t[0] == "KD":
        mem = lambda z: z3.BoolVal(False)
    else:
        inR = template_region(s, atom, var, t, V)
        mem = inR
    lo, hi = z3.If(x < y, x, y), z3.If(x < y, y, x)
    ms = (0,) if t[0] == "KD" else (0, 1)
    pairs, triples = set(), set()
    for cl, cr, ml, mr in itertools.product(CONTENTS, CONTENTS, ms, ms):
        s.push()
        s.add(L == cl, R == cr, mem(lo) == bool(ml), mem(hi) == bool(mr))
        if s.check() == z3.sat:
            pairs.add(((cl, ml), (cr, mr)))
            if want_triples:
                zc = z3.Int("zc")
                for cw, mw in itertools.product(CONTENTS, ms):
                    if no_A1_between and cw == A1:
                        continue
                    s.push()
                    s.add(lo < zc, zc < hi, mem(zc) == bool(mw))
                    if s.check() == z3.sat:
                        triples.add(((cl, ml), (cr, mr), (cw, mw)))
                    s.pop()
        s.pop()
    return pairs, triples


# ------------------------------------------------------------------ learning
def learn(n, sizes=(5, 6, 7), seed=11, holdout_N=8, holdout_n=200, holdout_seed=12):
    """Returns per-entry fits (with the training data summary) and L0 / hold-out diagnostics."""
    c0 = time.process_time()
    rng = random.Random(seed)
    ach = achiever_instances()
    data = {}
    cost = {"observations": 0, "draws": 0, "L0_failures": 0}
    for akey, a, v in ach:
        keys = patterns(a[0])
        allobs = []
        for N in sizes:
            obs, tries = observe(a, v, N, n, rng)
            ev = Evaluator(keys, N)
            for cells, haz, fixed, after in obs:
                lr = exchange_cells(cells, after)
                cost["L0_failures"] += lr is None
                allobs.append((cells, haz, fixed, after, ev(cells, haz, fixed), ev(after, haz, fixed), lr))
            cost["observations"] += len(obs)
            cost["draws"] += tries
        data[akey] = allobs
    fits = {}
    for akey, a, v in ach:
        fits[akey] = {k: fit(rows_for(k, data[akey])) for k in patterns(a[0])}
    cost["fit_cpu"] = time.process_time() - c0
    # hold-out at a larger N (never used for bounds)
    hrng = random.Random(holdout_seed)
    hold = {"predicted": 0, "unpredicted": 0, "errors": 0, "examples": []}
    for akey, a, v in ach:
        keys = patterns(a[0])
        obs, _ = observe(a, v, holdout_N, holdout_n, hrng)
        ev = Evaluator(keys, holdout_N)
        hobs = [(c, h, f, af, ev(c, h, f), ev(af, h, f), exchange_cells(c, af)) for c, h, f, af in obs]
        for k in keys:
            for p, ts, d in rows_for(k, hobs):
                pr = predict(fits[akey][k], p, ts)
                if pr is None:
                    hold["unpredicted"] += 1
                else:
                    hold["predicted"] += 1
                    if pr != d:
                        hold["errors"] += 1
                        if len(hold["examples"]) < 10:
                            hold["examples"].append({"entry": f"{akey} / {k}", "pair": str(p), "pred": pr, "obs": d})
    cost["cpu"] = time.process_time() - c0
    return fits, cost, hold


def law_check(fits, given):
    """D1(c): identified coefficients against the exchange formula; H_end only where the formula's between term is 0
    on every S-given triple (KD; for OUT/OOW the formula has no between term)."""
    mism, end_wrong = [], []
    for akey, row in fits.items():
        for k, f in row.items():
            for p, e in f["E"].items():
                if e is not None and e != formula(k, p):
                    mism.append(f"{akey} / {k} E{p}: {e} vs {formula(k, p)}")
            for t, b in f["B"].items():
                if b is not None and b != formula(k, t[:2], t):
                    mism.append(f"{akey} / {k} B{t}: {b} vs {formula(k, t[:2], t)}")
            if f["law"] == "END" and k.startswith("KD"):
                if any(formula(k, t[:2], t) != 0 for t in given[akey][k][1]):
                    end_wrong.append(f"{akey} / {k}")
    return {"coefficient_mismatches": len(mism), "mismatch_examples": mism[:10],
            "end_selected_with_nonzero_between": end_wrong}


def tables(fits, given=None):
    """Bound tables (ap2 layout) from the fits, with support S-obs (given=None) or S-given."""
    dmg, prog = {}, {}
    for akey, row in fits.items():
        ent = {}
        for k, f in row.items():
            if given is None:
                b, why = derive(f, f["pairs"], f["triples"])
            else:
                b, why = derive(f, given[akey][k][0], given[akey][k][1])
            ent[k] = {"law": f["law"], "bound": b, "reason": why,
                      "evidence": "BX" if b not in (None, "inf") else None}
        dmg[akey] = {"entries": ent}
        mk = ent[own_measure_key(akey)]
        ok = mk["bound"] not in (None, "inf") and mk["bound"] <= -1
        prog[akey] = {"ok": ok, "evidence": "BX" if ok else None}
    return dmg, prog


def given_all(need_triples=frozenset()):
    """S-given for every entry. KD supports do not depend on the template (no region), so they are computed once per
    achiever, with triples. For OUT/OOW only the pairs are computed, plus the triples for the entries in need_triples
    (those an H_loc fit needs); an H_end bound uses only pairs."""
    c0 = time.process_time()
    out = {}
    kd_cache = {}
    for akey, a, v in achiever_instances():
        out[akey] = {}
        for k in patterns(a[0]):
            if k.startswith("KD"):
                if akey not in kd_cache:
                    kd_cache[akey] = given_support(a, v, k, True)
                out[akey][k] = kd_cache[akey]
            else:
                out[akey][k] = given_support(a, v, k, (akey, k) in need_triples)
    return out, time.process_time() - c0
