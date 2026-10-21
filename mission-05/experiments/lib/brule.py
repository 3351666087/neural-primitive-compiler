"""B-RULE and B-SYM (amendment 6): B obtains the achievers' support without the library's selection encoding.

B-RULE
  From each observation B takes the two exchanged cells: s (held A1 before) and d (the other).
  Cell types (7): safe empty, hazard empty, A1, A2, X1, movable X2, fixed X2.
  Rule = (type set P, region, extreme): the leftmost / rightmost cell of the region whose type is in P.
  Regions: ALL; for ZONE atoms the zone (IN) and its complement (OUT); for GROUP atoms the A1 window of G1 / G2 and
  their complements (the window concept comes from the template definitions); for s also: right / left of d.
  For one (region, extreme) the consistent P form an interval  R <= P <= not F : R = types of the chosen cells,
  F = types of region cells more extreme than a chosen cell (and the region must contain every chosen cell).
  The version space is the union of these intervals; its size is sum 2^(free types). Empty, or more than 64
  (d-rule, s-rule) pairs: no support (every entry infinite).
  Simulation: on every state of N = 3..7 (libval.states, the observation distribution) where the atom is violated,
  every selection any rule of the version space can make; no satisfiability or spare-cell test (only enlarges).
  S-rule = observed support + simulated support. Bounds from the B-GRAM law (bgram.derive_gram).
B-SYM
  Left-right mirror: z -> N-1-z; left <-> right zones; G1 <-> G2; Z1, Z2 unchanged; KD{a<b} <-> KD{b<a}; the two ends
  swap. S-sym(entry) = S-fact(entry) + mirror of S-fact(mirror partner). ORDER achievers have no partner.
"""

from __future__ import annotations

import time

from libval import ROLE, achiever_instances, states
from libval2 import eligible
from libval3 import parse_key
from model import group_window, holds, reloc, select, zcells
from potentials import kd_key, patterns

A1 = ROLE["A1"]
TYPES = 7
FULL = (1 << TYPES) - 1


def ctype(c, h, fixed):
    if c == 0:
        return 1 if h else 0
    if c == 4:
        return 6 if 4 in fixed else 5
    return c + 1                                  # A1 -> 2, A2 -> 3, X1 -> 4


def base_regions(atom):
    if atom[0] == "ZONE":
        return ("ALL", "IN", "OUT")
    if atom[0] == "GROUP":
        return ("ALL", "W1", "NW1", "W2", "NW2")
    return ("ALL",)


def masks(atom, cells, haz, fixed):
    N = len(cells)
    m = {"ALL": [True] * N}
    if atom[0] == "ZONE":
        z = set(zcells(N, atom[2], atom[3]))
        m["IN"] = [p in z for p in range(N)]
        m["OUT"] = [p not in z for p in range(N)]
    elif atom[0] == "GROUP":
        for v, tag in (("G1", "1"), ("G2", "2")):
            w = group_window(["GROUP", A1], cells, {}, haz, True, fixed, v) or set()
            m["W" + tag] = [p in w for p in range(N)]
            m["NW" + tag] = [p not in w for p in range(N)]
    return m


def rel_mask(name, N, d):
    return [p > d for p in range(N)] if name == "R_D" else [p < d for p in range(N)]


# ------------------------------------------------------------------ learning (version space)
def families(examples, region_names, get_mask):
    """examples: [(types, chosen, ctx)]. Returns [(region, extreme, R, F)] with R <= P <= ~F non-empty."""
    out = []
    for reg in region_names:
        for ext in ("L", "R"):
            R = F = 0
            ok = True
            for types, chosen, ctx in examples:
                mk = get_mask(reg, ctx)
                if not mk[chosen]:
                    ok = False
                    break
                R |= 1 << types[chosen]
                order = range(chosen) if ext == "L" else range(len(types) - 1, chosen, -1)
                for p in order:
                    if mk[p]:
                        F |= 1 << types[p]
            if ok and not (R & F):
                out.append((reg, ext, R, F))
    return out


def vs_size(fams):
    return sum(2 ** (TYPES - bin(R | F).count("1")) for _, _, R, F in fams)


def learn_rules(atom, obs):
    """obs: [(cells, haz, fixed, after, vb, va, lr)] -> d families, s families, sizes."""
    ex_d, ex_s = [], []
    for cells, haz, fixed, after, vb, va, lr in obs:
        if lr is None:
            continue
        s = lr[0] if cells[lr[0]] == A1 else lr[1]
        d = lr[1] if s == lr[0] else lr[0]
        types = [ctype(c, h, fixed) for c, h in zip(cells, haz)]
        mk = masks(atom, cells, haz, fixed)
        ex_d.append((types, d, mk))
        ex_s.append((types, s, (mk, d)))
    fd = families(ex_d, base_regions(atom), lambda reg, mk: mk[reg])
    fs = families(ex_s, base_regions(atom) + ("R_D", "L_D"),
                  lambda reg, c: c[0][reg] if reg in c[0] else rel_mask(reg, len(c[0]["ALL"]), c[1]))
    return fd, fs, vs_size(fd), vs_size(fs)


def possible(types, mk, ext, R, F):
    """All cells some P in [R, ~F] can select in this region (scan from the extreme end)."""
    free = FULL & ~(R | F)
    out, seen = [], 0
    order = range(len(types)) if ext == "L" else range(len(types) - 1, -1, -1)
    for p in order:
        if not mk[p]:
            continue
        b = 1 << types[p]
        if b & F:
            continue
        if b & R:
            out.append(p)
            break
        if b & free and not (b & seen):
            out.append(p)
            seen |= b
    return out


def selections(atom, fd, fs, cells, haz, fixed, types, mk):
    sel = set()
    ds = set()
    for reg, ext, R, F in fd:
        ds.update(possible(types, mk[reg], ext, R, F))
    N = len(cells)
    for d in ds:
        for reg, ext, R, F in fs:
            m = mk[reg] if reg in mk else rel_mask(reg, N, d)
            for s in possible(types, m, ext, R, F):
                if s != d and cells[s] != cells[d]:
                    sel.add((d, s))
    return sel


# ------------------------------------------------------------------ simulation
def template_regions(keys):
    sig = {}
    for k in keys:
        t = parse_key(k)
        sig[k] = None if t[0] == "KD" else t
    return sig


def region_of(t, cells, haz, fixed, cache):
    if t not in cache:
        if t[0] == "OUT":
            cache[t] = set(zcells(len(cells), t[2], t[3]))
        else:
            cache[t] = group_window(["GROUP", t[1]], cells, {}, haz, True, fixed, t[2]) or set()
    return cache[t]


def simulate(rules, Ns=(3, 4, 5, 6, 7), check_true=(6, 7)):
    """rules: {akey: (fd, fs)} (None = no support). Returns supports {akey: {key: (pairs, triples)}}, the N at which
    each combination first appeared, and the H1 check (disagreements with the true selection on eligible states)."""
    t0 = time.process_time()
    ach = [(k, a, v) for k, a, v in achiever_instances()]
    keys = {k: patterns(a[0]) for k, a, _ in ach}
    regs = {k: template_regions(keys[k]) for k, _, _ in ach}
    sup = {k: {kk: (set(), set()) for kk in keys[k]} for k, _, _ in ach}
    new_at = {k: {kk: {} for kk in keys[k]} for k, _, _ in ach}
    h1 = {k: {"checked": 0, "disagree": 0, "example": None} for k, _, _ in ach}
    for N in Ns:
        for cells, haz, fixed in states(N):
            types = [ctype(c, h, fixed) for c, h in zip(cells, haz)]
            rcache = {}
            for akey, a, v in ach:
                if holds(a, cells, ROLE):
                    continue
                r = rules.get(akey)
                sel = set()
                if r is not None:
                    mk = masks(a, cells, haz, fixed)
                    sel = selections(a, r[0], r[1], cells, haz, fixed, types, mk)
                if N in check_true:
                    ts = select(a, v, cells, haz, True, fixed, ROLE)
                    rr = reloc(cells, 0, ts[0], ts[1], haz, True) if ts else None
                    if rr is not None:
                        h1[akey]["checked"] += 1
                        if sel != {(ts[0], ts[1])} and eligible(a, cells, haz, fixed):
                            h1[akey]["disagree"] += 1
                            if h1[akey]["example"] is None:
                                h1[akey]["example"] = {"cells": cells, "haz": haz, "fixed": fixed, "true": ts,
                                                       "B": sorted(sel)}
                for d, s in sel:
                    l, rgt = min(d, s), max(d, s)
                    for kk, t in regs[akey].items():
                        if t is None:
                            pair = ((cells[l], 0), (cells[rgt], 0))
                            trip = {(pair[0], pair[1], (cells[z], 0)) for z in range(l + 1, rgt)}
                        else:
                            R = region_of(t, cells, haz, fixed, rcache)
                            pair = ((cells[l], int(l in R)), (cells[rgt], int(rgt in R)))
                            trip = set()
                        P, T = sup[akey][kk]
                        if pair not in P:
                            P.add(pair)
                            new_at[akey][kk][str(pair)] = N
                        for tr in trip:
                            if tr not in T:
                                T.add(tr)
                                new_at[akey][kk][str(tr)] = N
    return sup, new_at, h1, time.process_time() - t0


# ------------------------------------------------------------------ B-SYM
MIRROR_ACH = {}
for _k, _a, _v in achiever_instances():
    if _a[0] == "ZONE":
        MIRROR_ACH[_k] = _k.replace(":left:", ":right:") if ":left:" in _k else _k.replace(":right:", ":left:")
    elif _a[0] == "GROUP":
        MIRROR_ACH[_k] = "GROUP:G2" if _k == "GROUP:G1" else "GROUP:G1"


def mirror_key(k):
    t = parse_key(k)
    if t[0] == "KD":
        inv = {v: r for r, v in ROLE.items()}
        return kd_key([(inv[hi], inv[lo]) for lo, hi in t[1]])
    if t[0] == "OUT":
        return k.replace("left", "@").replace("right", "left").replace("@", "right")
    return k.replace("G1", "@").replace("G2", "G1").replace("@", "G2")


def mirror_pair(p):
    return (p[1], p[0])


def mirror_triple(t):
    return (t[1], t[0], t[2])


def s_sym(akey, k, fact):
    """fact: {akey: {key: (pairs, triples)}} (S-fact)."""
    P, T = set(fact[akey][k][0]), set(fact[akey][k][1])
    m = MIRROR_ACH.get(akey)
    if m is not None:
        mk = mirror_key(k)
        P |= {mirror_pair(p) for p in fact[m][mk][0]}
        T |= {mirror_triple(t) for t in fact[m][mk][1]}
    return P, T
