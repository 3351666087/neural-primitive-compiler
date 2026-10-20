"""Black-box structure learning from a task oracle (used by discovery and by the automatic route A).

The learner is given only a task *interface* (channel names, spaces, declared lags) and a function
`oracle(trace) -> outputs` (the reference semantics as a black box). It never sees letter definitions.

  learn_letters   per (letter, target coordinate): the minimal monotone disjunction over
                  {previous coordinates} U {data channels of that letter} U {one} consistent with every
                  observed transition (elimination algorithm for disjunctions). Inconsistent -> "nonlinear".
  learn_outputs   per query output channel: disjunction over (selector channel AND previous coordinate)
                  pairs ("sel") or over previous coordinates ("any"); inconsistent -> "nonlinear".
  to_ir           an IR program from the learned tables (literal maps), with no weight search.
  parametrize     match learned tables against the IR map vocabulary (and 2-step compositions) at
                  every probed size, so the program can be re-instantiated at sizes never probed.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable

from .ir import cname, map_rules, space_coords

ONEF = ("one",)


@dataclass
class Learned:
    letters: dict = field(default_factory=dict)     # letter -> {coord: [sources]} or "nonlinear"
    outputs: dict = field(default_factory=dict)     # output name -> structure
    observations: int = 0
    traces: int = 0
    notes: list = field(default_factory=list)


def _random_trace(iface: dict, T: int, rng: random.Random) -> dict:
    """Valid random traces from the interface alone (<= 1 letter/step, one-hot vec data, one-hot queries,
    pacing after conditional letters)."""
    coords = lambda sp: space_coords(sp)
    chans = [l["name"] for l in iface["letters"]]
    for b, sp in {**iface["data"], **iface["queries"]}.items():
        chans += [cname(b, c) for c in coords(sp)]
    tr = {c: [0] * T for c in chans}
    quiet = -1
    for t in range(T):
        if t > quiet and rng.random() < 0.65:
            l = rng.choice(iface["letters"])
            tr[l["name"]][t] = 1
            if l["data"]:
                sp = iface["data"][l["data"]]
                if sp["kind"] == "vec":
                    tr[cname(l["data"], rng.choice(coords(sp)))][t] = 1
                else:
                    for c in coords(sp):
                        tr[cname(l["data"], c)][t] = int(rng.random() < 0.35)
            if l["cond_delay"] is not None:
                quiet = t + l["cond_delay"]
        for b, sp in iface["queries"].items():
            if rng.random() < 0.5:
                tr[cname(b, rng.choice(coords(sp)))][t] = 1
    return tr


def collect(iface: dict, oracle: Callable[[dict, int], dict], n_traces: int, T: int, seed: int) -> tuple[list, list]:
    """Run the oracle on random traces; recover the hidden state S(t) from the img output (lag declared)."""
    img = next(o for o in iface["outputs"] if o["kind"] == "img")
    L = img["lag"]
    sp = iface["state_space"]
    coords = space_coords(sp)
    rng = random.Random(seed)
    runs = []
    for _ in range(n_traces):
        tr = _random_trace(iface, T, rng)
        out = oracle(tr, T)
        states = []
        for t in range(T - L):
            states.append(frozenset(c for c in coords if out[cname(img["name"], c)][t + L]))
        runs.append((tr, out, states))
    return runs, coords


def learn_letters(iface: dict, runs: list, coords: list) -> dict:
    res = {}
    for l in iface["letters"]:
        name, D = l["name"], l["cond_delay"]
        data_ch = [cname(l["data"], c) for c in space_coords(iface["data"][l["data"]])] if l["data"] else []
        feats = [("c", k) for k in coords] + [("d", d) for d in data_ch] + [ONEF]
        examples = []  # (true feature set, next state)
        for tr, _, S in runs:
            for t in range(len(S)):
                if tr[name][t] and t + (D or 0) < len(S):
                    prev = S[t - 1] if t >= 1 else frozenset()
                    on = {("c", k) for k in prev} | {("d", d) for d in data_ch if tr[d][t]} | {ONEF}
                    examples.append((on, S[t + (D or 0)]))
        if not examples:
            res[name] = "unobserved"
            continue
        table, ok = {}, True
        for j in coords:
            cand = set(feats)
            for on, nxt in examples:
                if j not in nxt:
                    cand -= on
            for on, nxt in examples:
                if j in nxt and not (cand & on):
                    ok = False
                    break
            if not ok:
                break
            table[j] = sorted(cand, key=repr)
        res[name] = table if ok else "nonlinear"
    return res


def learn_outputs(iface: dict, runs: list, coords: list) -> dict:
    res = {}
    for o in iface["outputs"]:
        if o["kind"] == "img":
            continue
        L = o["lag"]
        chans = [ch for ch in runs[0][1] if ch == o["name"] or ch.startswith(o["name"] + "_")]
        qs = {b: [cname(b, c) for c in space_coords(sp)] for b, sp in iface["queries"].items()}
        q_all = [q for lst in qs.values() for q in lst]
        struct = {}
        for ch in chans:
            # features: previous coordinate alone (lag L) or selector AND coordinate (selector at t-L, state at t-L-1)
            feats_any = [("c", k) for k in coords]
            feats_sel = [("q", q, k) for q in q_all for k in coords]
            ex_any, ex_sel = [], []
            for tr, out, S in runs:
                for t in range(len(S) + 2):
                    if t >= len(out[ch]):
                        break
                    tq = t - L
                    if tq - 1 < 0 or tq - 1 >= len(S) or tq >= len(S):
                        continue
                    y = out[ch][t]
                    ex_any.append(({("c", k) for k in S[tq]}, y))
                    on = {("q", q, k) for q in q_all if tr[q][tq] for k in S[tq - 1]}
                    ex_sel.append((on, y))
            found = None
            for kind, feats, ex in (("any", feats_any, ex_any), ("sel", feats_sel, ex_sel)):
                cand = set(feats)
                for on, y in ex:
                    if not y:
                        cand -= on
                if all((not y) or (cand & on) for on, y in ex) and ex:
                    found = (kind, sorted(cand, key=repr))
                    break
            struct[ch] = found or "nonlinear"
        res[o["name"]] = struct
    return res


def learn(iface: dict, oracle, n_traces: int = 400, T: int = 16, seed: int = 0) -> Learned:
    runs, coords = collect(iface, oracle, n_traces, T, seed)
    L = Learned(observations=sum(len(s) for _, _, s in runs), traces=n_traces)
    L.letters = learn_letters(iface, runs, coords)
    L.outputs = learn_outputs(iface, runs, coords)
    return L


# ------------------------------------------------------------------ IR from learned tables
def _key(c) -> str:
    return ",".join(map(str, c))


def to_ir(iface: dict, L: Learned, name: str = "learned") -> dict | None:
    """Literal-table IR. Returns None (with reasons in L.notes) if some structure is outside the schemas."""
    letters = {}
    for l in iface["letters"]:
        tab = L.letters.get(l["name"])
        if not isinstance(tab, dict):
            L.notes.append(f"letter {l['name']}: {tab} (outside the union-register schema)")
            return None
        if l["cond_delay"] is not None:
            L.notes.append(f"letter {l['name']}: conditional letters need a gated composition; not attempted")
            return None
        lit = {_key(j): [["c", _key(s[1])] if s[0] == "c" else (["d", s[1]] if s[0] == "d" else ["one"]) for s in srcs]
               for j, srcs in tab.items()}
        letters[l["name"]] = {"map": ["table", lit]}
    nodes = [{"id": "mem", "op": "CMR", "letters": letters}]
    outputs = {"img": "mem"}
    for o in iface["outputs"]:
        if o["kind"] == "img":
            continue
        st = L.outputs.get(o["name"], {})
        if any(v == "nonlinear" for v in st.values()):
            L.notes.append(f"output {o['name']}: not a disjunction of single or selector-gated coordinates")
            return None
        kinds = {v[0] for v in st.values()}
        if kinds == {"any"} and len(st) == 1:
            (ch, (_, feats)), = st.items()
            nodes.append({"id": o["name"], "op": "ANY", "of": "mem", "where": {"set": [list(f[1]) for f in feats]},
                          "delay": o["lag"] - 2})
            outputs[o["name"]] = o["name"]
        elif kinds <= {"sel", "any"}:
            pairs = {}
            for ch, (kind, feats) in st.items():
                if kind != "sel":
                    L.notes.append(f"output {o['name']}: mixed structure")
                    return None
                suffix = ch[len(o["name"]):].lstrip("_")
                pairs[suffix] = [[f[1], _key(f[2])] for f in feats]
            nodes.append({"id": o["name"], "op": "SELT", "of": "mem", "pairs": pairs, "delay": o["lag"] - 1,
                          "xdelay": o["lag"] - 2})
            outputs[o["name"]] = o["name"]
        else:
            return None
    return {"name": name, "max_delay": 6, "nodes": nodes, "outputs": outputs}


# ------------------------------------------------------------------ parametrization (size generalization)
GRID_VOCAB = [["id"], ["zero"], ["rot90"], ["rot180"], ["rot270"], ["fliph"], ["flipv"], ["transpose"], ["dilate"]] + \
    [["shift", dx, dy, m] for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)) for m in ("clip", "wrap")]


def vocab_for(sp: dict, data_bundles: list[str]) -> list:
    if sp["kind"] == "grid":
        base = GRID_VOCAB + [["load", b] for b in data_bundles]
        return base + [["compose", a, b] for a in GRID_VOCAB[2:] for b in GRID_VOCAB[2:]]
    if sp["kind"] == "table":
        K = sp["dims"][0]
        v = [["id"], ["zero"]]
        v += [["store_row", k, b] for k in range(K) for b in data_bundles]
        v += [["swap_rows", j, k] for j in range(K) for k in range(j + 1, K)]
        v += [["copy_row", j, k] for j in range(K) for k in range(K) if j != k]
        v += [["clear_row", k] for k in range(K)]
        return v
    if sp["kind"] == "objgrid":
        K = sp["dims"][0]
        v = [["id"], ["zero"]] + [["place", k, b] for k in range(K) for b in data_bundles]
        v += [["on_slice", k, m] for k in range(K) for m in GRID_VOCAB[2:]]
        return v
    return [["id"], ["zero"]] + [["load", b] for b in data_bundles]


def match_vocab(table: dict, sp: dict, data_bundles: list[str]) -> list:
    """All vocabulary map expressions whose pullback table equals the learned one (on this space)."""
    target = {j: sorted(srcs, key=repr) for j, srcs in table.items()}
    hits = []
    for expr in vocab_for(sp, data_bundles):
        try:
            rules = map_rules(expr, sp)
        except Exception:
            continue
        if all(sorted(rules.get(j, []), key=repr) == target[j] for j in target):
            hits.append(expr)
    return hits


# ------------------------------------------------------------------ active refinement (singleton probes)
def _apply_model(table: dict, S: frozenset, data_on: set) -> frozenset:
    out = set()
    for j, srcs in table.items():
        for s in srcs:
            if (s[0] == "c" and s[1] in S) or (s[0] == "d" and s[1] in data_on) or s[0] == "one":
                out.add(j)
                break
    return frozenset(out)


def active_refine(iface: dict, oracle, L: Learned, max_prep: int = 2) -> Learned:
    """Exact pullback tables for union-type letters by singleton experiments.

    1. For each coordinate p, plan (with the passively learned model) a sequence of <= max_prep frames that
       leads from the empty state to {p}; execute it on the oracle and confirm {p} on the img output.
    2. From {p}, apply each letter with no data; from the empty state, apply each data letter with exactly
       one data channel on. Under the union hypothesis S' = U_{p in S} R(p) U D(data) U C these
       experiments determine the letter exactly.
    3. Re-check every passive observation against the rebuilt table; any contradiction -> "nonlinear".
    Experiments cost is recorded in L.notes / L.probes.
    """
    img = next(o for o in iface["outputs"] if o["kind"] == "img")
    lag = img["lag"]
    coords = space_coords(iface["state_space"])
    letters = [l for l in iface["letters"] if l["cond_delay"] is None and isinstance(L.letters.get(l["name"]), dict)]
    chans = [l["name"] for l in iface["letters"]]
    for b, sp in {**iface["data"], **iface["queries"]}.items():
        chans += [cname(b, c) for c in space_coords(sp)]
    frames_opts = []  # (frame dict, letter, data_on)
    for l in letters:
        if l["data"]:
            for c in space_coords(iface["data"][l["data"]]):
                frames_opts.append(({l["name"]: 1, cname(l["data"], c): 1}, l["name"], {cname(l["data"], c)}))
        else:
            frames_opts.append(({l["name"]: 1}, l["name"], set()))
    probes = 0

    def run(frames: list[dict]) -> list[frozenset]:
        nonlocal probes
        probes += 1
        T = len(frames) + lag + 1
        tr = {c: [0] * T for c in chans}
        for t, f in enumerate(frames):
            for k, v in f.items():
                tr[k][t] = v
        out = oracle(tr, T)
        return [frozenset(c for c in coords if out[cname(img["name"], c)][t + lag]) for t in range(len(frames))]

    # 1. preparation plans for singletons (BFS over the learned model)
    plans = {}
    frontier = [(frozenset(), [])]
    seen = {frozenset()}
    for depth in range(max_prep):
        nxt = []
        for S, plan in frontier:
            for f, lname, don in frames_opts:
                S2 = _apply_model(L.letters[lname], S, don)
                if S2 not in seen:
                    seen.add(S2)
                    nxt.append((S2, plan + [f]))
                    if len(S2) == 1:
                        plans.setdefault(next(iter(S2)), plan + [f])
        frontier = nxt
    prepared = {}
    for p, plan in plans.items():
        if run(plan)[-1] == frozenset([p]):
            prepared[p] = plan
    missing = [p for p in coords if p not in prepared]
    if missing:
        L.notes.append(f"active: could not prepare {len(missing)} singleton states; tables for them stay passive")
    # 2. experiments
    new = {}
    for l in letters:
        name = l["name"]
        R = {}
        for p, plan in prepared.items():
            R[p] = run(plan + [{name: 1}])[-1]
        base = run([{name: 1}])[-1]  # from empty, no data: constants
        D = {}
        if l["data"]:
            for c in space_coords(iface["data"][l["data"]]):
                d = cname(l["data"], c)
                D[d] = run([{name: 1, d: 1}])[-1]
        tab = {}
        for j in coords:
            srcs = [("c", p) for p in coords if p in R and j in R[p]]
            srcs += [("d", d) for d in D if j in D[d] - base]
            if j in base:
                srcs = [("one",)]
            if not all(p in R for p in coords):  # fall back to passive sources for unprepared coordinates
                srcs += [s for s in L.letters[name].get(j, []) if s[0] == "c" and s[1] not in R]
            tab[j] = sorted(set(srcs), key=repr)
        new[name] = tab
    L.letters.update(new)
    # 3. query outputs: from each prepared singleton state, issue each selector channel alone (or nothing)
    if len(prepared) == len(coords):
        qchans = [cname(b, c) for b, sp in iface["queries"].items() for c in space_coords(sp)]
        for o in iface["outputs"]:
            if o["kind"] == "img" or not isinstance(L.outputs.get(o["name"]), dict):
                continue
            chs = list(L.outputs[o["name"]])
            lag2 = o["lag"]
            seen_on = {ch: [] for ch in chs}
            for p, plan in prepared.items():
                for q in [None] + qchans:
                    frames = plan + [({q: 1} if q else {})]
                    T = len(frames) + lag2 + 1
                    tr = {c: [0] * T for c in chans}
                    for t, f in enumerate(frames):
                        for k, v in f.items():
                            tr[k][t] = v
                    probes += 1
                    out = oracle(tr, T)
                    tq = len(plan)
                    for ch in chs:
                        if out[ch][tq + lag2]:
                            seen_on[ch].append((q, p))
            for ch in chs:
                kind = L.outputs[o["name"]][ch][0] if isinstance(L.outputs[o["name"]][ch], tuple) else None
                if kind == "any":
                    L.outputs[o["name"]][ch] = ("any", sorted({("c", p) for q, p in seen_on[ch] if q is None}, key=repr))
                elif kind == "sel":
                    L.outputs[o["name"]][ch] = ("sel", sorted({("q", q, p) for q, p in seen_on[ch] if q}, key=repr))
    L.notes.append(f"active: {probes} probe traces, {len(prepared)}/{len(coords)} singleton states prepared")
    L.probes = probes
    return L


def recheck(iface: dict, oracle, L: Learned, n_traces: int = 200, T: int = 16, seed: int = 99) -> list[str]:
    """Fresh random observations; letters whose table mispredicts any transition become 'nonlinear'."""
    runs, coords = collect(iface, oracle, n_traces, T, seed)
    bad = []
    for l in iface["letters"]:
        tab = L.letters.get(l["name"])
        if not isinstance(tab, dict):
            continue
        D = l["cond_delay"] or 0
        dch = [cname(l["data"], c) for c in space_coords(iface["data"][l["data"]])] if l["data"] else []
        for tr, _, S in runs:
            for t in range(len(S) - D):
                if tr[l["name"]][t]:
                    prev = S[t - 1] if t else frozenset()
                    if _apply_model(tab, prev, {d for d in dch if tr[d][t]}) != S[t + D]:
                        bad.append(l["name"])
                        break
            if l["name"] in bad:
                break
    for b in bad:
        L.letters[b] = "nonlinear"
    return bad
