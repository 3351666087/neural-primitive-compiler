"""Mission 03 pilot P1 (protocol: mission-03/CHALLENGE_PROTOCOL.md section 3; predictions locked there).

Explain the two task classes Mission 02's automatic route could not solve, from passive traces only, without
descriptions, the named vocabulary, family scaffolds, the declared conditional delay or the declared `same` lag.

T1 conditional commands (UA0, UA2, UA3, UA4): competing explanations E-latent, E-union, E-mono, E-guard.
T2 `same` (UB0, UB1): F-sel (one node), F-comp (library compositions, depth <= 3).

Privileged information still used (recorded): the full state readout on `img` (lag 2) and the environment's
random state injection (LOAD/STORE with random data).

  python mission-03/experiments/p1_composition/run_p1.py
"""

from __future__ import annotations

import itertools
import json
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "mission-03" / "experiments" / "p0_leakage"))
sys.path.insert(0, str(REPO / "mission-02" / "experiments" / "unseen"))

from cog.check import differential  # noqa: E402
from cog.ir import compile_ir  # noqa: E402
from cog.learn import _random_trace  # noqa: E402
from cog.tasks import cname, run_reference  # noqa: E402
from cog.unseen import generate  # noqa: E402
from l2_closure import HORIZON, PROBES, candidates, min_covers  # noqa: E402
import write_llm_programs as W  # noqa: E402  (only the generic CMR+ANY+GATE wiring; no map is read from it)

UNSEEN = REPO / "mission-02" / "experiments" / "unseen"
N_TRACES, T_LEN, MAX_D = 1000, 16, 6
OUT = HERE / "p1.json"


# ------------------------------------------------------------------ observation (black box)
def observe(task, n=N_TRACES, seed=1):
    """Passive random traces; the hidden state is read from img (lag 2). Returns (traces, states)."""
    iface = task.interface()
    lag = next(o for o in iface["outputs"] if o["kind"] == "img")["lag"]
    coords = task.space.coords
    rng = random.Random(seed)
    data = []
    for _ in range(n):
        tr = _random_trace(iface, T_LEN, rng)
        out = run_reference(task, tr, T_LEN)
        S = [frozenset(c for c in coords if out[cname("img", c)][t + lag]) for t in range(T_LEN - lag)]
        data.append((tr, out, S))
    return data


def letter_events(task, data, name):
    """For each occurrence of letter `name` at tau: (pre = S(tau-1), trajectory S(tau..next letter - 1))."""
    letters = [l.name for l in task.letters]
    ev = []
    for tr, _, S in data:
        times = [t for t in range(len(S)) if any(tr[l][t] for l in letters)]
        for i, tau in enumerate(times):
            if not tr[name][tau]:
                continue
            nxt = times[i + 1] if i + 1 < len(times) else len(S)
            pre = S[tau - 1] if tau >= 1 else frozenset()
            ev.append((pre, S[tau:nxt]))
    return ev


# ------------------------------------------------------------------ T1 explanations
def change_delays(events):
    """Delays d consistent with 'the state stays at pre until tau + d, then jumps once and stays'."""
    ok = set(range(0, MAX_D + 1))
    informative = 0
    for pre, traj in events:
        moves = [j for j in range(len(traj)) if traj[j] != (traj[j - 1] if j else pre)]
        if not moves:
            continue
        informative += 1
        if len(moves) > 1:
            return set(), informative
        ok &= {moves[0]}
    return ok, informative


def at_delay(events, d):
    return [(pre, traj[d]) for pre, traj in events if len(traj) > d]


def latent_conflicts(pairs):
    seen = {}
    for pre, post in pairs:
        if seen.setdefault(pre, post) != post:
            return True
    return False


def learn_union(pairs, coords):
    """Elimination algorithm for 'post_j = OR of pre over Src(j)'; None if no disjunction is consistent."""
    rel = set()
    for j in coords:
        cand = set(coords)
        for pre, post in pairs:
            if j not in post:
                cand -= pre
        if any(j in post and not (pre & cand) for pre, post in pairs):
            return None
        rel |= {(p, j) for p in cand}
    return frozenset(rel)


def mono_violation(pairs, limit=3000):
    ps = pairs[:limit]
    for (a, fa), (b, fb) in itertools.product(ps, ps):
        if a <= b and not fa <= fb:
            return True
    return False


def regions(N):
    R = {}
    for k in (0, 1):
        R[f"row{k}"] = frozenset((x, k) for x in range(N))
        R[f"row-{k + 1}"] = frozenset((x, N - 1 - k) for x in range(N))
        R[f"col{k}"] = frozenset((k, y) for y in range(N))
        R[f"col-{k + 1}"] = frozenset((N - 1 - k, y) for y in range(N))
    R["diag"] = frozenset((i, i) for i in range(N))
    R["anti"] = frozenset((i, N - 1 - i) for i in range(N))
    R["all"] = frozenset((x, y) for x in range(N) for y in range(N))
    return R


GUARDS = [(q, r) for q in ("ANY", "ALL") for r in regions(3)]


def guard(g, N, S):
    q, r = g
    R = regions(N)[r]
    return bool(S & R) if q == "ANY" else R <= S


def fit_geo(rels):
    cands = candidates(rels)
    return cands, min_covers(cands, rels)


def explain_cond(u, name):
    probe = {N: u.build(N) for N in PROBES}
    data = {N: observe(t) for N, t in probe.items()}
    ev = {N: letter_events(probe[N], data[N], name) for N in PROBES}
    row = {"uid": u.uid, "command": name, "events": {str(N): len(ev[N]) for N in PROBES}}
    ds = set.intersection(*(change_delays(ev[N])[0] for N in PROBES))
    row["delays_consistent"] = sorted(ds)
    if len(ds) != 1:
        row["verdict"] = "delay not identified"
        return row
    d = ds.pop()
    pairs = {N: at_delay(ev[N], d) for N in PROBES}
    row["E-latent"] = "consistent" if not any(latent_conflicts(pairs[N]) for N in PROBES) else "rejected"
    # E-latent is rejected only by a conflict; record the inverse wording explicitly
    row["E-latent"] = "rejected (no history dependence)" if row["E-latent"] == "consistent" else "SUPPORTED (history dependence)"
    row["E-union"] = "rejected" if any(learn_union(pairs[N], probe[N].space.coords) is None for N in PROBES) else "consistent"
    row["E-mono"] = "rejected" if mono_violation(pairs[3]) else "consistent"
    hyps = []
    t0 = time.perf_counter()
    for g in GUARDS:
        parts = {}
        ok = True
        for side in (True, False):
            rels = {}
            for N in PROBES:
                sub = [(pre, post) for pre, post in pairs[N] if guard(g, N, pre) == side]
                rel = learn_union(sub, probe[N].space.coords) if sub else None
                if rel is None:
                    ok = False
                    break
                rels[N] = rel
            if not ok:
                break
            cands, covers = fit_geo(rels)
            if not covers:
                ok = False
                break
            parts[side] = (cands, covers)
        if ok:
            hyps.append((g, parts))
    row["E-guard_search_s"] = round(time.perf_counter() - t0, 1)
    row["E-guard_consistent_guards"] = [f"{q} {r}" for (q, r), _ in hyps]
    # horizon check: component level, against fresh reference events at N = 8, 11
    preds_ok, n_combos = [], 0
    for N in HORIZON:
        hi = HORIZON.index(N)
        tN = u.build(N)
        evN = at_delay(letter_events(tN, observe(tN, n=300, seed=5), name), d)
        for g, parts in hyps:
            for cA, cB in itertools.product(parts[True][1], parts[False][1]):
                n_combos += 1
                relA = frozenset().union(*(parts[True][0][i][1][hi] for i in cA))
                relB = frozenset().union(*(parts[False][0][i][1][hi] for i in cB))
                wrong = 0
                for pre, post in evN:
                    rel = relA if guard(g, N, pre) else relB
                    if frozenset(q for p, q in rel if p in pre) != post:
                        wrong += 1
                preds_ok.append({"N": N, "guard": f"{g[0]} {g[1]}", "events": len(evN), "wrong": wrong})
    row["E-guard_hypotheses"] = n_combos // len(HORIZON) if HORIZON else 0
    row["horizon"] = preds_ok
    good = [p for p in preds_ok if p["wrong"] == 0]
    row["identified_d"] = d
    row["verdict"] = ("no consistent guarded hypothesis" if not hyps else
                      "unique and correct at N=8,11" if row["E-guard_hypotheses"] == 1 and len(good) == len(HORIZON) else
                      "all consistent hypotheses correct at N=8,11" if len(good) == len(preds_ok) else
                      "ambiguous: consistent hypotheses disagree at N=8,11")
    row["_hyps"] = hyps
    return row


# ------------------------------------------------------------------ T1 end-to-end (UA0: img output only)
def table_map(rel):
    tab = {}
    for p, q in rel:
        tab.setdefault(f"{q[0]},{q[1]}", []).append(["c", f"{p[0]},{p[1]}"])
    return ["table", tab]


def end_to_end_ua0(u, cond_row):
    """Assemble the whole UA0 program from passively learned pieces: plain commands by the L2 method
    (union table -> piecewise-affine cover), the conditional command by the guard found above, wired
    with the generic CMR + ANY + GATE pattern (Mission 02, P4). Judged by differential testing."""
    name = u.params["cond"][0]
    hyps = cond_row["_hyps"]
    if len(hyps) != 1:
        return {"status": "skipped (needs a unique guard)"}
    g, parts = hyps[0]
    region_ir = {"row0": {"row": 0}, "row-1": {"row": "last"}, "col0": {"col": 0}, "col-1": {"col": "last"}, "all": {"all": True}}
    if g[0] != "ANY" or g[1] not in region_ir:
        return {"status": f"guard {g} is not expressible as an IR region"}
    probe = {N: u.build(N) for N in PROBES}
    data = {N: observe(t) for N, t in probe.items()}
    plain = {}
    for cmd, _ in u.params["commands"]:
        rels = {}
        for N in PROBES:
            rels[N] = learn_union(at_delay(letter_events(probe[N], data[N], cmd), 0), probe[N].space.coords)
        if any(r is None for r in rels.values()):
            return {"status": f"command {cmd}: no union table"}
        cands, covers = fit_geo(rels)
        if len(covers) != 1:
            return {"status": f"command {cmd}: {len(covers)} covers"}
        plain[cmd] = (cands, covers[0])
    results = []
    for N in (3, 5, 8, 11):
        t = u.build(N)

        def rel_at(cands, cover, N=N):
            if N in PROBES:
                return frozenset().union(*(cands[i][0][PROBES.index(N)] for i in cover))
            return frozenset().union(*(cands[i][1][HORIZON.index(N)] for i in cover))
        cmds = {c: table_map(rel_at(*plain[c])) for c in plain}
        A = table_map(rel_at(parts[True][0], parts[True][1][0]))
        B = table_map(rel_at(parts[False][0], parts[False][1][0]))
        prog = W.spatial(cmds, cond=(name, "top row", A, B, cond_row["identified_d"]))  # region overwritten below
        for node in prog["nodes"]:
            if node["id"] == "condR":
                node["where"] = region_ir[g[1]]
        d = differential(compile_ir(prog, t.interface()), t, n=400, T=16, seed=7)
        results.append({"N": N, "differential": d.ok, "failing": d.detail.get("failing_traces")})
    return {"status": "built", "per_size": results}


# ------------------------------------------------------------------ T2 `same`
def same_points(task, data, out_name="same"):
    """(t, query frames, state timeline) for every time step; the lag is searched later."""
    return [(tr, out[out_name], S) for tr, out, S in data]


def terms(K, V):
    """Well-typed terms with at most 3 layers of library nodes (SEL0, GATE{AND,OR,ANDNOT}, ANY) over the
    inputs qa:K, qb:K, M:KV (inputs are not counted as layers)."""
    leaves = {"K": [("qa",), ("qb",)], "KV": [("M",)], "V": [], "S": []}
    allt = {k: list(v) for k, v in leaves.items()}
    for layer in (1, 2, 3):
        new = {"K": [], "V": [], "KV": [], "S": []}
        for q in allt["K"]:
            for m in allt["KV"]:
                new["V"].append(("SEL0", q, m))
        for ty in ("K", "V", "S"):
            for a, b in itertools.product(allt[ty], repeat=2):
                if a < b:
                    new[ty] += [("AND", a, b), ("OR", a, b)]
                if a != b:
                    new[ty].append(("ANDNOT", a, b))
        for ty in ("K", "V", "KV"):
            for a in allt[ty]:
                new["S"].append(("ANY", a))
        for k in new:
            allt[k] = allt[k] + [t for t in new[k] if t not in allt[k]]
    return allt["S"]


def evaluate(term, env):
    op = term[0]
    if op in ("qa", "qb", "M"):
        return env[op]
    if op == "SEL0":
        q, M = evaluate(term[1], env), evaluate(term[2], env)
        return frozenset(v for (k, v) in M if k in q)
    if op == "ANY":
        return bool(evaluate(term[1], env))
    a, b = evaluate(term[1], env), evaluate(term[2], env)
    if isinstance(a, bool):
        return {"AND": a and b, "OR": a or b, "ANDNOT": a and not b}[op]
    return {"AND": a & b, "OR": a | b, "ANDNOT": a - b}[op]


def envs(task, data, L, delta):
    K = task.space.dims[0]
    for tr, out, S in data:
        for t in range(len(S)):
            tq = t - L
            if tq < 0 or tq - delta >= len(S):
                continue
            qa = frozenset(k for k in range(K) if tr[cname("qa", (k,))][tq])
            qb = frozenset(k for k in range(K) if tr[cname("qb", (k,))][tq])
            st = tq - delta
            M = S[st] if st >= 0 else frozenset()
            yield {"qa": qa, "qb": qb, "M": M}, out["same"][t]


def explain_same(u):
    sizes = [tuple(s) for s in u.sizes]
    third = (sizes[0][0] + 3, sizes[0][1] + 2)
    probe = {s: u.build(s) for s in sizes}
    data = {s: observe(t) for s, t in probe.items()}
    K, V = sizes[0]
    T = terms(K, V)
    t0 = time.perf_counter()
    def nodes(t):
        return 0 if t[0] in ("qa", "qb", "M") else 1 + sum(nodes(c) for c in t[1:])
    single = {t for t in T if nodes(t) <= 2 and not any(op in repr(t) for op in ("AND", "OR"))}  # ANY(leaf), ANY(SEL0(q, M))
    consistent, tried, first = [], 0, None
    for L in range(1, MAX_D + 1):
        for delta in (0, 1, 2):
            pts = {s: list(envs(probe[s], data[s], L, delta)) for s in sizes}
            for term in T:
                tried += 1
                if all(evaluate(term, e) == bool(y) for s in sizes for e, y in pts[s]):
                    consistent.append((term, L, delta))
                    first = first or tried
    row = {"uid": u.uid, "sizes": [str(s) for s in sizes], "third_size": str(third), "terms": len(T),
           "candidates_tried": tried, "search_s": round(time.perf_counter() - t0, 1)}
    row["first_consistent_at_candidate"] = first
    row["F-sel"] = "consistent" if any(c[0] in single for c in consistent) else "rejected"
    row["F-comp_consistent"] = [f"{c[0]} L={c[1]} delta={c[2]}" for c in consistent]
    t3 = u.build(third)
    d3 = observe(t3, n=400, seed=5)
    res = []
    for term, L, delta in consistent:
        pts = list(envs(t3, d3, L, delta))
        res.append(sum(evaluate(term, e) != bool(y) for e, y in pts))
    row["third_size_wrong"] = res
    row["verdict"] = ("no consistent composition" if not consistent else
                      "all consistent compositions correct at the third size" if all(w == 0 for w in res) else
                      "ambiguous or wrong at the third size")
    return row


def main():
    seed = json.loads((UNSEEN / "tasks.json").read_text())["seed"]
    units = {u.uid: u for u in generate(seed)}
    t0 = time.perf_counter()
    rows_t1, rows_t2 = [], []
    for uid in ("UA0", "UA2", "UA3", "UA4"):
        u = units[uid]
        r = explain_cond(u, u.params["cond"][0])
        if uid == "UA0":
            r["end_to_end"] = end_to_end_ua0(u, r)
        r.pop("_hyps", None)
        print({k: v for k, v in r.items() if k != "horizon"}, flush=True)
        rows_t1.append(r)
    for uid in ("UB0", "UB1"):
        r = explain_same(units[uid])
        print(r, flush=True)
        rows_t2.append(r)
    OUT.write_text(json.dumps({"T1": rows_t1, "T2": rows_t2, "time_s": round(time.perf_counter() - t0, 1),
                               "n_traces_per_probe_size": N_TRACES}, indent=1, default=str))


if __name__ == "__main__":
    main()
