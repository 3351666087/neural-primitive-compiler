"""B on ACH-DSL achievers (G3): the round-5/6 learners (B-GRAM law, B-RULE version space + simulation) applied to
achievers B only observes. Observations: libval-distribution states drawn as in bexch.observe (same sampler), the
achiever's selection and the relocation; B sees states before and after and the template values.
Bounds: B-GRAM law with support = observed + simulated (N = 3..7) from the version space; version space empty or
larger than 64 rule pairs: no support (every entry infinite). Progress: some own measure template bound <= -1, and
the achiever moved in every observed eligible state (B's only applicability evidence, at N = 5).
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(EXP / "lib"))
sys.path.insert(0, str(HERE))
import bexch  # noqa: E402
import bgram  # noqa: E402
import brule  # noqa: E402
from bdisc import sample_state  # noqa: E402
from libval import ROLE, states  # noqa: E402
from libval2 import eligible  # noqa: E402
from libval3 import Evaluator  # noqa: E402
from model import holds, reloc  # noqa: E402
from potentials import patterns  # noqa: E402
from z3_dsl import own_measures  # noqa: E402

CAP = 64


def observe(a, sel_fn, N, n, rng, max_tries=200_000):
    """n eligible states (atom violated, satisfiable, spare cell), drawn as in bexch.observe. B sees the move, or
    that the achiever did not move ("stuck"). For an achiever that always moves, the draws equal bexch.observe's."""
    obs, got, tries, stuck = [], 0, 0, 0
    while got < n and tries < max_tries:
        tries += 1
        cells, haz, fixed = sample_state(N, rng)
        if not eligible(a, cells, haz, fixed):
            continue
        got += 1
        sel = sel_fn(a, None, cells, haz, True, fixed, ROLE)
        r = reloc(cells, 0, sel[0], sel[1], haz, True) if sel else None
        if r is None:
            stuck += 1
            continue
        obs.append((cells, haz, fixed, r[0]))
    return obs, tries, stuck


def collect(achs, n, sizes=(5,), seed=11):
    """Returns (data, stuck): the observed moves per instance, and the number of observed eligible states in which
    the achiever did not move."""
    rng = random.Random(seed)
    data, stuck = {}, {}
    for akey, a, sel_fn in achs:
        keys = patterns(a[0])
        out, st = [], 0
        for N in sizes:
            o, _, s_ = observe(a, sel_fn, N, n, rng)
            st += s_
            ev = Evaluator(keys, N)
            out += [(c, h, f, af, ev(c, h, f), ev(af, h, f), bexch.exchange_cells(c, af)) for c, h, f, af in o]
        data[akey], stuck[akey] = out, st
    return data, stuck


def fit_all(achs, data):
    rec = {}
    for akey, a, _ in achs:
        cache = {}
        rec[akey] = {}
        for k in patterns(a[0]):
            rows = bexch.rows_for(k, data[akey])
            F, d, l1 = bgram.gram_design(k, data[akey], cache)
            rec[akey][k] = {"gram": bgram.fit_gram(F, d) if len(d) else bgram.Gram("GLOB"), "rows_obs": bgram.s_obs(rows)}
    return rec


def learn(achs, data):
    rules, sizes = {}, {}
    for akey, a, _ in achs:
        fd, fs, nd, ns = brule.learn_rules(a, data[akey]) if data[akey] else ([], [], 0, 0)
        sizes[akey] = {"d": nd, "s": ns, "pairs": nd * ns, "d_families": [list(f) for f in fd],
                       "s_families": [list(f) for f in fs]}
        rules[akey] = (fd, fs) if fd and fs and nd * ns <= CAP else None
    return rules, sizes


def simulate(rules, achs, Ns=(3, 4, 5, 6, 7), check_true=(6, 7)):
    """Supports from the version spaces and the H1 check (B's selections vs the true selection on eligible N = 6, 7
    states where the true achiever moves): disagree = B's set of moves is not exactly {true move}; miss = the true
    move is not in B's set (only a miss can make B's support incomplete)."""
    t0 = time.process_time()
    keys = {k: patterns(a[0]) for k, a, _ in achs}
    regs = {k: brule.template_regions(keys[k]) for k, _, _ in achs}
    sup = {k: {kk: (set(), set()) for kk in keys[k]} for k, _, _ in achs}
    h1 = {k: {"checked": 0, "disagree": 0, "miss": 0, "example": None} for k, _, _ in achs}
    for N in Ns:
        for cells, haz, fixed in states(N):
            types = [brule.ctype(c, h, fixed) for c, h in zip(cells, haz)]
            rcache = {}
            for akey, a, sel_fn in achs:
                if holds(a, cells, ROLE):
                    continue
                r = rules.get(akey)
                sel = brule.selections(a, r[0], r[1], cells, haz, fixed, types, brule.masks(a, cells, haz, fixed)) if r else set()
                if N in check_true:
                    ts = sel_fn(a, None, cells, haz, True, fixed, ROLE)
                    rr = reloc(cells, 0, ts[0], ts[1], haz, True) if ts else None
                    if rr is not None:
                        h1[akey]["checked"] += 1
                        if sel != {(ts[0], ts[1])} and eligible(a, cells, haz, fixed):
                            h1[akey]["disagree"] += 1
                            h1[akey]["miss"] += (ts[0], ts[1]) not in sel     # the true move is not among B's moves
                            if h1[akey]["example"] is None:
                                h1[akey]["example"] = {"cells": cells, "haz": haz, "fixed": fixed, "true": ts, "B": sorted(sel)}
                for d, s in sel:
                    l, rg = min(d, s), max(d, s)
                    for kk, t in regs[akey].items():
                        if t is None:
                            pair = ((cells[l], 0), (cells[rg], 0))
                            trip = {(pair[0], pair[1], (cells[z], 0)) for z in range(l + 1, rg)}
                        else:
                            R = brule.region_of(t, cells, haz, fixed, rcache)
                            pair = ((cells[l], int(l in R)), (cells[rg], int(rg in R)))
                            trip = set()
                        P, T = sup[akey][kk]
                        P.add(pair)
                        T |= trip
    return sup, h1, time.process_time() - t0


def table(achs, rec, sup, rules, stuck=None):
    """Progress needs the decrease (some own measure bound <= -1) and, when stuck counts are given, no observed
    eligible state in which the achiever did not move (applicability evidence from observation only)."""
    dmg, prog = {}, {}
    for akey, a, _ in achs:
        ent = {}
        for k, r in rec[akey].items():
            if rules.get(akey) is None:
                b, why = "inf", "no_rules"
            else:
                P = r["rows_obs"][0] | sup[akey][k][0]
                T = r["rows_obs"][1] | sup[akey][k][1]
                b, why = bgram.derive_gram(r["gram"], P, T)
            ent[k] = {"law": r["gram"].law, "bound": b, "reason": why, "evidence": "BX" if b not in (None, "inf") else None}
        dmg[akey] = {"entries": ent}
        m = next((x for x in own_measures(a) if ent[x]["bound"] not in (None, "inf") and ent[x]["bound"] <= -1), None)
        ok = m is not None and (stuck is None or stuck[akey] == 0)
        prog[akey] = {"ok": ok, "evidence": "BX" if ok else None, "measure": m,
                      "stuck_observed": None if stuck is None else stuck[akey]}
    return dmg, prog
