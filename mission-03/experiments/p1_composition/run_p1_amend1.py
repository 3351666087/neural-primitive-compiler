"""P1 under protocol amendment 1: inside a guarded branch, source cells never observed on are unconstrained.

Everything else (data, guard family, geometric prior, budget, scoring) is exactly run_p1.py. Only T1 changes.

  python mission-03/experiments/p1_composition/run_p1_amend1.py
"""

from __future__ import annotations

import itertools
import json
import time
from pathlib import Path

import run_p1 as R
from run_p1 import (GUARDS, HORIZON, PROBES, W, at_delay, candidates, change_delays, compile_ir, differential,
                    generate, guard, latent_conflicts, learn_union, letter_events, min_covers, mono_violation,
                    observe, table_map)

HERE = Path(__file__).resolve().parent


def union_dc(pairs, coords):
    """Union table on the observed sources; U = source cells never on in this branch (unconstrained)."""
    rel = learn_union(pairs, coords)
    if rel is None:
        return None, None
    U = set(coords) - set().union(*(pre for pre, _ in pairs))
    return frozenset(pq for pq in rel if pq[0] not in U), U


def fit_geo_dc(rels_obs, Us, coords):
    allowed = {N: rels_obs[N] | {(p, q) for p in Us[N] for q in coords[N]} for N in PROBES}
    cands = candidates(allowed)
    restricted = [(tuple(frozenset(pq for pq in pg[i] if pq[0] not in Us[N]) for i, N in enumerate(PROBES)), hg)
                  for pg, hg in cands]
    restricted_ok = [c for c in restricted if all(c[0])]
    covers = min_covers(restricted_ok, rels_obs)
    return restricted_ok, covers


def explain_cond_dc(u, name, data):
    probe = {N: u.build(N) for N in PROBES}
    coords = {N: probe[N].space.coords for N in PROBES}
    ev = {N: letter_events(probe[N], data[N], name) for N in PROBES}
    row = {"uid": u.uid, "command": name, "events": {str(N): len(ev[N]) for N in PROBES}}
    ds = set.intersection(*(change_delays(ev[N])[0] for N in PROBES))
    row["delays_consistent"] = sorted(ds)
    if len(ds) != 1:
        row["verdict"] = "delay not identified"
        return row, []
    d = min(ds)
    pairs = {N: at_delay(ev[N], d) for N in PROBES}
    row["E-latent"] = "SUPPORTED (history dependence)" if any(latent_conflicts(pairs[N]) for N in PROBES) else "rejected (no history dependence)"
    row["E-union"] = "rejected" if any(learn_union(pairs[N], coords[N]) is None for N in PROBES) else "consistent"
    row["E-mono"] = "rejected" if mono_violation(pairs[3]) else "consistent"
    hyps = []
    t0 = time.perf_counter()
    for g in GUARDS:
        parts, ok = {}, True
        for side in (True, False):
            rels, Us = {}, {}
            for N in PROBES:
                sub = [(pre, post) for pre, post in pairs[N] if guard(g, N, pre) == side]
                rel, U = union_dc(sub, coords[N]) if sub else (None, None)
                if rel is None:
                    ok = False
                    break
                rels[N], Us[N] = rel, U
            if not ok:
                break
            cands, covers = fit_geo_dc(rels, Us, coords)
            if not covers:
                ok = False
                break
            parts[side] = (cands, covers, {N: sorted(Us[N]) for N in PROBES})
        if ok:
            hyps.append((g, parts))
    row["E-guard_search_s"] = round(time.perf_counter() - t0, 1)
    row["E-guard_consistent_guards"] = [f"{q} {r}" for (q, r), _ in hyps]
    row["unconstrained_cells"] = {f"{g[0]} {g[1]}": {str(s): {str(N): len(p[2][N]) for N in PROBES} for s, p in parts.items()}
                                  for g, parts in hyps}
    preds, n = [], 0
    for N in HORIZON:
        hi = HORIZON.index(N)
        tN = u.build(N)
        evN = at_delay(letter_events(tN, observe(tN, n=300, seed=5), name), d)
        for g, parts in hyps:
            for cA, cB in itertools.product(parts[True][1], parts[False][1]):
                n += 1
                relA = frozenset().union(*(parts[True][0][i][1][hi] for i in cA))
                relB = frozenset().union(*(parts[False][0][i][1][hi] for i in cB))
                wrong = sum(frozenset(q for p, q in (relA if guard(g, N, pre) else relB) if p in pre) != post for pre, post in evN)
                preds.append({"N": N, "guard": f"{g[0]} {g[1]}", "events": len(evN), "wrong": wrong})
    row["E-guard_hypotheses"] = n // len(HORIZON)
    row["horizon"] = preds
    row["identified_d"] = d
    good = [p for p in preds if p["wrong"] == 0]
    row["verdict"] = ("no consistent guarded hypothesis" if not hyps else
                      "unique and correct at N=8,11" if row["E-guard_hypotheses"] == 1 and len(good) == len(HORIZON) else
                      "all consistent hypotheses correct at N=8,11" if len(good) == len(preds) else
                      "ambiguous: consistent hypotheses disagree at N=8,11")
    return row, hyps


def end_to_end_ua0(u, row, hyps, data):
    name = u.params["cond"][0]
    if len(hyps) != 1:
        return {"status": f"skipped ({len(hyps)} consistent guards)"}
    g, parts = hyps[0]
    region_ir = {"row0": {"row": 0}, "row-1": {"row": "last"}, "col0": {"col": 0}, "col-1": {"col": "last"}, "all": {"all": True}}
    if g[0] != "ANY" or g[1] not in region_ir:
        return {"status": f"guard {g} is not expressible as an IR region"}
    probe = {N: u.build(N) for N in PROBES}
    plain = {}
    for cmd, _ in u.params["commands"]:
        rels, Us = {}, {}
        for N in PROBES:
            rels[N], Us[N] = union_dc(at_delay(letter_events(probe[N], data[N], cmd), 0), probe[N].space.coords)
        if any(r is None for r in rels.values()):
            return {"status": f"command {cmd}: no union table"}
        cands, covers = fit_geo_dc(rels, Us, {N: probe[N].space.coords for N in PROBES})
        if len(covers) != 1:
            return {"status": f"command {cmd}: {len(covers)} covers"}
        plain[cmd] = (cands, covers[0])
    out = []
    for N in (3, 5, 8, 11):
        t = u.build(N)

        def rel_at(cands, cover, N=N):
            # pieces are size-generic; instantiate each at N (probe sizes use the stored horizon-free graphs)
            if N in PROBES:
                return frozenset().union(*(cands[i][0][PROBES.index(N)] for i in cover))
            return frozenset().union(*(cands[i][1][HORIZON.index(N)] for i in cover))
        cmds = {c: table_map(rel_at(*plain[c])) for c in plain}
        A = table_map(rel_at(parts[True][0], parts[True][1][0]))
        B = table_map(rel_at(parts[False][0], parts[False][1][0]))
        prog = W.spatial(cmds, cond=(name, "top row", A, B, row["identified_d"]))
        for node in prog["nodes"]:
            if node["id"] == "condR":
                node["where"] = region_ir[g[1]]
        dres = differential(compile_ir(prog, t.interface()), t, n=400, T=16, seed=7)
        out.append({"N": N, "differential": dres.ok, "failing": dres.detail.get("failing_traces")})
    return {"status": "built", "per_size": out}


def main():
    seed = json.loads((R.UNSEEN / "tasks.json").read_text())["seed"]
    units = {u.uid: u for u in generate(seed)}
    rows = []
    t0 = time.perf_counter()
    for uid in ("UA0", "UA2", "UA3", "UA4"):
        u = units[uid]
        data = {N: observe(u.build(N)) for N in PROBES}
        row, hyps = explain_cond_dc(u, u.params["cond"][0], data)
        if uid == "UA0":
            row["end_to_end"] = end_to_end_ua0(u, row, hyps, data)
        print({k: v for k, v in row.items() if k != "horizon"}, flush=True)
        rows.append(row)
    (HERE / "p1_amend1.json").write_text(json.dumps({"T1": rows, "time_s": round(time.perf_counter() - t0, 1)}, indent=1, default=str))


if __name__ == "__main__":
    main()
