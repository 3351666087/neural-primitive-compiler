"""Conditional-command explanation under protocol amendments 3 and 4 (frozen before the confirmation run).

Fit criterion (amendment 3): a branch explanation is a set of piecewise-affine pieces whose graphs lie inside
(elimination table U unobserved-sources x all cells) and whose union reproduces every observed post-state; the
fewest pieces win (Occam). Regions (amendment 4): intervals whose bounds are anchored at either edge.

Two concept routes:
  guard-family : the 22 hand-listed guards of P1 (ANY/ALL over rows, columns, diagonals, all)
  region-invent: R found by Z3 under "the concept is occupancy of some region" (no list), then described by
                 edge-anchored intervals so that it can be instantiated at new sizes
"""

from __future__ import annotations

import itertools
import time

from run_p1 import (GUARDS, HORIZON, PROBES, at_delay, candidates, change_delays, guard, latent_conflicts,
                    learn_union, letter_events, mono_violation, observe)

CAP = 200
ANCH = ("0", "1", "2", "N-3", "N-2", "N-1")


def anchor(a, N):
    return {"0": 0, "1": 1, "2": 2, "N-3": N - 3, "N-2": N - 2, "N-1": N - 1}[a]


def interval_region(desc, N):
    a, b, c, d = (anchor(v, N) for v in desc)
    return frozenset((x, y) for x in range(N) for y in range(N) if a <= x <= b and c <= y <= d)


INTERVALS = [d for d in itertools.product(ANCH, repeat=4)]


def describe_region(regions: dict) -> list:
    """All edge-anchored interval descriptions matching the region at every probed size."""
    return [d for d in INTERVALS if all(interval_region(d, N) == R for N, R in regions.items())]


def branch_fit(parts_by_size: dict, coords: dict):
    """parts_by_size[N] = events (pre, post) of one branch. Returns (pieces, covers) or (None, reason)."""
    allowed, reqs = {}, {}
    for N, ev in parts_by_size.items():
        rel = learn_union(ev, coords[N])
        if rel is None:
            return None, "not a union map"
        U = set(coords[N]) - set().union(*(pre for pre, _ in ev))
        allowed[N] = rel | {(p, q) for p in U for q in coords[N]}
        reqs[N] = [(i, j) for i, (pre, post) in enumerate(ev) for j in post]
    pieces = candidates(allowed)
    masks = []
    for pg, hg in pieces:
        m = {}
        for k, N in enumerate(PROBES):
            src = {}
            for p, q in pg[k]:
                src.setdefault(q, set()).add(p)
            ev = parts_by_size[N]
            bits = 0
            for r, (i, j) in enumerate(reqs[N]):
                if src.get(j) and src[j] & ev[i][0]:
                    bits |= 1 << r
            m[N] = bits
        masks.append(m)
    full = {N: (1 << len(reqs[N])) - 1 for N in PROBES}
    best, found = None, []

    def rec(chosen, cov, k):
        nonlocal best
        if best is not None and k > best:
            return
        miss = next(((N, (~cov[N]) & full[N]) for N in PROBES if cov[N] != full[N]), None)
        if miss is None:
            if best is None or k < best:
                best, found[:] = k, []
            if len(found) < CAP:
                found.append(tuple(sorted(chosen)))
            return
        if k == 5:
            return
        N, bits = miss
        low = bits & -bits
        for idx, m in enumerate(masks):
            if m[N] & low and idx not in chosen:
                rec(chosen + [idx], {M: cov[M] | m[M] for M in PROBES}, k + 1)

    rec([], {N: 0 for N in PROBES}, 0)
    covers = sorted(set(found))
    if not covers:
        return None, "no cover with <= 5 pieces"
    return (pieces, covers), None


def horizon_relations(fit, hi):
    pieces, covers = fit
    return {frozenset().union(*(pieces[i][1][hi] for i in c)) for c in covers}


_EVAL = {}


def score(pred_fn, tN, name, d, n=300):
    key = (tN.name, name, d)
    if key not in _EVAL:
        _EVAL[key] = at_delay(letter_events(tN, observe(tN, n=n, seed=5), name), d)
    evN = _EVAL[key]
    return sum(pred_fn(pre) != post for pre, post in evN), len(evN)


def explain(u, name, data, solve_region=None, stash=None):
    """Both concept routes on one conditional command. data[N] = passive observations at probe sizes.
    stash (dict) receives the fitted branches per route, for end-to-end assembly."""
    stash = {} if stash is None else stash
    probe = {N: u.build(N) for N in PROBES}
    coords = {N: probe[N].space.coords for N in PROBES}
    ev = {N: letter_events(probe[N], data[N], name) for N in PROBES}
    row = {"uid": u.uid, "command": name}
    ds = set.intersection(*(change_delays(ev[N])[0] for N in PROBES))
    row["delays_consistent"] = sorted(ds)
    if len(ds) != 1:
        row["verdict"] = "delay not identified"
        return row
    d = min(ds)
    row["identified_d"] = d
    pairs = {N: at_delay(ev[N], d) for N in PROBES}
    row["events"] = {str(N): len(pairs[N]) for N in PROBES}
    row["E-latent"] = "SUPPORTED" if any(latent_conflicts(pairs[N]) for N in PROBES) else "rejected"
    row["E-union"] = "rejected" if any(learn_union(pairs[N], coords[N]) is None for N in PROBES) else "consistent"
    row["E-mono"] = "rejected" if mono_violation(pairs[3]) else "consistent"

    def route(label, guard_fn_by_size, guard_at):
        t0 = time.perf_counter()
        fits = {}
        for side in (True, False):
            parts = {N: [(pre, post) for pre, post in pairs[N] if guard_fn_by_size[N](pre) == side] for N in PROBES}
            if not all(parts.values()):
                return {"status": f"{label}: a branch has no events"}
            fit, why = branch_fit(parts, coords)
            if fit is None:
                return {"status": f"{label}: {why}"}
            fits[side] = fit
        stash[label] = (fits, guard_at, d)
        out = {"status": "consistent", "covers": {str(s): len(f[1]) for s, f in fits.items()},
               "pieces": {str(s): len(f[1][0]) for s, f in fits.items()}, "fit_s": round(time.perf_counter() - t0, 1)}
        for N in HORIZON:
            hi = HORIZON.index(N)
            A, B = horizon_relations(fits[True], hi), horizon_relations(fits[False], hi)
            g = guard_at(N)
            results = []
            for relA, relB in itertools.product(A, B):
                def pred(pre, relA=relA, relB=relB):
                    rel = relA if g(pre) else relB
                    return frozenset(q for p, q in rel if p in pre)
                results.append(score(pred, u.build(N), name, d))
            out[f"N{N}"] = {"hypotheses": len(results), "wrong_per_hypothesis": [w for w, _ in results],
                            "events": results[0][1] if results else 0}
        return out

    # route 1: hand-listed guard family
    consistent, rejected = [], {}
    for g in GUARDS:
        r = route(f"{g[0]} {g[1]}", {N: (lambda pre, g=g, N=N: guard(g, N, pre)) for N in PROBES},
                  lambda N, g=g: (lambda pre: guard(g, N, pre)))
        if r["status"] == "consistent":
            consistent.append((f"{g[0]} {g[1]}", r))
        else:
            rejected[f"{g[0]} {g[1]}"] = r["status"]
    row["guard_family"] = {"consistent_guards": [c[0] for c in consistent], "detail": dict(consistent),
                           "rejected": rejected}
    # route 2: region invented by Z3, described by edge-anchored intervals
    if solve_region is not None:
        regions, uniq = {}, True
        for N in PROBES:
            R, unique = solve_region(pairs[N], coords[N])
            if R is None:
                regions = None
                break
            regions[N], uniq = R, uniq and unique
        if regions is None:
            row["region_invention"] = {"status": "unsat"}
        else:
            descs = describe_region(regions)
            info = {"unique_at_probe_sizes": uniq, "region_sizes": {str(N): len(R) for N, R in regions.items()},
                    "interval_descriptions": [list(x) for x in descs]}
            if len(descs) == 0:
                info["status"] = "no interval description"
            else:
                for N in HORIZON:
                    info[f"region_N{N}_distinct_predictions"] = len({interval_region(x, N) for x in descs})
                desc = descs[0]
                r = route("invented", {N: (lambda pre, R=regions[N]: bool(pre & R)) for N in PROBES},
                          lambda N, desc=desc: (lambda pre, R=interval_region(desc, N): bool(pre & R)))
                info.update(r)
            row["region_invention"] = info
    return row
