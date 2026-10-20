"""Mission 04 P-R2 (protocol amendment 5): can background, colour roles and the grid frame be derived from evidence?
ARC-AGI-1 training split only (DEV). Prints only task ids and labels; never grid contents.

  python -I run_r2.py blocks     # block layer, configurations C0-C9                    -> r2_blocks.json
  python -I run_r2.py mdisc      # M-DISC-fixed on the five single representations     -> r2_mdisc.json
  python -I run_r2.py combine    # pooled M-DISC decisions, predictions E1-E10         -> r2.json
  python -I run_r2.py check      # implementation check on self-made perturbations     -> r2_check.json
"""

from __future__ import annotations

import hashlib
import itertools
import json
import random
import signal
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "mission-04" / "experiments" / "r1_repr"))
sys.path.insert(0, str(REPO / "mission-04" / "experiments" / "a0_uniqueness"))
import blocks as B  # noqa: E402
import normalize as N  # noqa: E402
import run_r1 as R  # noqa: E402
import resolve_unknown as RU  # noqa: E402
import uniqueness as U  # noqa: E402

DATA = R.DATA
ZERO = ("zero", "id", "grid")
SINGLE_MDISC = {"BG-0": ("zero", "id", "grid"), "BG-mode": ("mode", "id", "grid"), "BG-border": ("border", "id", "grid"),
                "COL-rank": ("zero", "rank", "grid"), "EDGE-content": ("zero", "id", "content")}
BUDGET = {"blocks": 120, "mdisc": 600}
UNCOVERED = {"no cover", "no size rule", "empty outputs"}


class Budget(BaseException):
    pass


def _alarm(signum, frame):
    raise Budget()


def guarded(seconds, fn, *args):
    signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(seconds)
    try:
        return fn(*args)
    except Budget:
        return "RESOURCE_LIMIT"
    finally:
        signal.alarm(0)


def key(p):
    return None if p is None else hashlib.sha1(repr(p.shape).encode() + p.astype(np.int64).tobytes()).hexdigest()


def label_of(p, T):
    return "abstain" if p is None else "correct" if p.shape == T.shape and (p == T).all() else "wrong"


def rep_name(rep):
    bg = rep[0] if isinstance(rep[0], str) else f"c{rep[0][1]}"
    return f"{bg}|{rep[1]}|{rep[2]}"


# ------------------------------------------------------------------ block layer under one representation
def block_rows(train, tests, rep):
    """Every consistent explanation under rep (all 9 rules, F3-noselect): per test input (prediction key, label)."""
    a = N.apply_rep(train, [I for I, _ in tests], rep)
    if a is None:
        return []
    train2, tests2, back = a
    expl = []
    for rule in B.GRAMMAR:
        expl += B.explanations(train2, rule)
    rows = []
    for e in expl:
        row = []
        for k, ((_, T), I2) in enumerate(zip(tests, tests2)):
            p = back(k, B.predict(e, I2))
            row.append((key(p), label_of(p, T)))
        rows.append(row)
    return rows


def decide(rows, permissive):
    if permissive:
        rows = [r for r in rows if all(k is not None for k, _ in r)]
    if not rows or any(k is None for r in rows for k, _ in r):
        return "abstain"
    if len({tuple(k for k, _ in r) for r in rows}) != 1:
        return "abstain"
    labels = [l for _, l in rows[0]]
    return "correct" if all(l == "correct" for l in labels) else "wrong"


def discriminating(train2):
    """Conservation law K or C holds on the true pairs and fails on every shape-compatible mismatched pair."""
    k = len(train2)
    for r in B.GRAMMAR:
        if B.law_K(train2, r):
            mism = [(train2[i][0], train2[j][1]) for i in range(k) for j in range(k)
                    if i != j and train2[i][0].shape == train2[j][1].shape]
            ok = all(not B.law_K([p], r) for p in mism) if mism else all(len(B.partition(I, r)) >= 2 for I, _ in train2)
            if ok:
                return True
        if B.law_C(train2, r):
            mism = [(train2[i][0], train2[j][1]) for i in range(k) for j in range(k) if i != j]
            ok = all(not B.law_C([p], r) for p in mism) if mism else all(len(B.partition(I, r)) >= 2 for I, _ in train2)
            if ok:
                return True
    return False


def bg_ev(train, test_inputs):
    """BG-ev: candidates passing the discriminating conservation law (fallback: all BG-pool candidates)."""
    cands = N.candidates(train, test_inputs)
    sel = []
    for c in cands:
        a = N.apply_rep(train, test_inputs, (c, "id", "grid"))
        if a is not None and discriminating(a[0]):
            sel.append(c)
    return sel, cands


def task_blocks(train, tests):
    tin = [I for I, _ in tests]
    cands = N.candidates(train, tin)
    sel, _ = bg_ev(train, tin)
    ev = sel or cands
    configs = {
        "C0": [ZERO], "C1": [("mode", "id", "grid")], "C2": [("border", "id", "grid")],
        "C3": [(c, "id", "grid") for c in cands], "C4": [(c, "id", "grid") for c in ev],
        "C5": [("zero", "rank", "grid")], "C6": [ZERO, ("zero", "rank", "grid")],
        "C7": [("zero", "id", "content")], "C8": [ZERO, ("zero", "id", "content")],
        "C9": [(c, col, edge) for c in ev for col in ("id", "rank") for edge in ("grid", "content")],
    }
    cache = {}
    res = {}
    for name, reps in configs.items():
        rows, limit = [], False
        for rep in reps:
            if rep not in cache:
                cache[rep] = guarded(BUDGET["blocks"], block_rows, train, tests, rep)
            if cache[rep] == "RESOURCE_LIMIT":
                limit = True
            else:
                rows += cache[rep]
        res[name] = {"S0": "RESOURCE_LIMIT" if limit else decide(rows, False),
                     "S2": "RESOURCE_LIMIT" if limit else decide(rows, True), "n_reps": len(reps), "n_expl": len(rows)}
    modes = [N.background(I, "mode") for I, _ in train]
    sel_keys = {N.induced_backgrounds(train, tin, c)[:len(train)] for c in sel}
    content = N.apply_rep(train, tin, ("zero", "id", "content"))
    boxes = [N.content_box(I) for I, _ in train]
    meta = {
        "T_bg": sum(m != 0 for m in modes) > len(modes) / 2,
        "T_col": len({frozenset(np.unique(I).tolist()) for I, _ in train}) > 1,
        "T_edge": any(b is not None and (b[1] - b[0], b[3] - b[2]) != I.shape for b, (I, _) in zip(boxes, train)),
        "same_size": all(I.shape == O.shape for I, O in train),
        "bg_candidates": [rep_name((c, "id", "grid")).split("|")[0] for c in cands],
        "bg_ev_selected": [rep_name((c, "id", "grid")).split("|")[0] for c in sel],
        "bg_ev_contains_mode": tuple(modes) in sel_keys, "bg_ev_contains_zero": tuple([0] * len(train)) in sel_keys,
        "edge_content_applies": content is not None,
    }
    return {"configs": res, "meta": meta}


# ------------------------------------------------------------------ M-DISC under one representation
def grid_of(v):
    out = np.full(v["shape"], U.BG, dtype=int)
    for cell, col in v["pred"]:
        out[cell] = col
    return out


def mdisc_rep(train, tests, rep):
    a = N.apply_rep(train, [I for I, _ in tests], rep)
    if a is None:
        return {"applies": False, "reason": "representation does not apply"}
    train2, tests2, back = a
    outs, info = U.solve_fixed(train2, tests2, colour_mode="prior")
    reason = info.get("reason")
    sts = list(info.get("uniqueness") or [reason] * len(tests2))
    per = []
    for k, ((_, T), I2) in enumerate(zip(tests, tests2)):
        st, p = sts[k], outs[k]
        if st == "UNKNOWN":
            v = RU.decide(train2, I2, "prior", False)
            st = "enumeration:" + v["verdict"]
            p = grid_of(v) if v["verdict"] == "UNIQUE" else None
        q = back(k, p) if p is not None else None
        per.append({"verdict": st, "key": key(q), "label": label_of(q, T)})
    return {"applies": reason not in UNCOVERED, "reason": reason, "tests": per}


def pooled_mdisc(results):
    """Answer only if every applicable representation is UNIQUE on every test input and all predictions agree."""
    app = [r for r in results if isinstance(r, dict) and r["applies"]]
    if any(r == "RESOURCE_LIMIT" for r in results):
        return "abstain"
    if not app:
        return "abstain"
    # per test input, then the same task-level rollup as Mission 03 / the audit: correct only if every test input is
    # correct, wrong if any answered test input is wrong, otherwise abstain (corrected after the C0 reproduction check)
    labels = []
    for k in range(len(app[0]["tests"])):
        if any(not r["tests"][k]["verdict"].endswith("UNIQUE") or r["tests"][k]["key"] is None for r in app) \
                or len({r["tests"][k]["key"] for r in app}) != 1:
            labels.append("abstain")
        else:
            labels.append(app[0]["tests"][k]["label"])
    return "correct" if all(l == "correct" for l in labels) else "wrong" if "wrong" in labels else "abstain"


# ------------------------------------------------------------------ modes
def tasks():
    return {f.stem: R.load(f) for f in sorted(DATA.glob("*.json"))}


def main_blocks():
    t0 = time.perf_counter()
    rows = {}
    for tid, (train, tests) in tasks().items():
        rows[tid] = task_blocks(train, tests)
        print(tid, {c: (v["S0"], v["S2"]) for c, v in rows[tid]["configs"].items()}, flush=True)
    out = {"label": "ARC-AGI-1 training split, DEV (P-R2, amendment 5)", "rows": rows, "time_s": round(time.perf_counter() - t0, 1)}
    (HERE / "r2_blocks.json").write_text(json.dumps(out, indent=1, default=str))
    print("time", out["time_s"])


def main_mdisc():
    t0 = time.perf_counter()
    rows = {}
    for tid, (train, tests) in tasks().items():
        rows[tid] = {name: guarded(BUDGET["mdisc"], mdisc_rep, train, tests, rep) for name, rep in SINGLE_MDISC.items()}
        print(tid, {n: (v if isinstance(v, str) else pooled_mdisc([v])) for n, v in rows[tid].items()}, flush=True)
    out = {"label": "ARC-AGI-1 training split, DEV (P-R2, amendment 5)", "rows": rows, "time_s": round(time.perf_counter() - t0, 1)}
    (HERE / "r2_mdisc.json").write_text(json.dumps(out, indent=1, default=str))
    print("time", out["time_s"])


def count(st):
    c, w = st.count("correct"), st.count("wrong")
    return {"correct": c, "wrong": w, "abstain": st.count("abstain"), "RESOURCE_LIMIT": st.count("RESOURCE_LIMIT"),
            "precision": round(c / (c + w), 3) if c + w else None}


def main_combine():
    bl = json.loads((HERE / "r2_blocks.json").read_text())["rows"]
    md = json.loads((HERE / "r2_mdisc.json").read_text())["rows"]
    ids = sorted(bl)
    mcfg = {"C0": ["BG-0"], "C1": ["BG-mode"], "C2": ["BG-border"], "C3": ["BG-0", "BG-mode", "BG-border"],
            "C5": ["COL-rank"], "C6": ["BG-0", "COL-rank"], "C7": ["EDGE-content"], "C8": ["BG-0", "EDGE-content"],
            "C9": list(SINGLE_MDISC)}
    M = {c: {t: pooled_mdisc([md[t][r] for r in reps]) for t in ids} for c, reps in mcfg.items()}
    S = lambda c, pol: {t: bl[t]["configs"][c][pol] for t in ids}
    solved = lambda d: {t for t, v in d.items() if v == "correct"}
    T_bg = {t for t in ids if bl[t]["meta"]["T_bg"]}
    summary = {"blocks": {f"{c}|{p}": count(list(S(c, p).values())) for c in bl[ids[0]]["configs"] for p in ("S0", "S2")},
               "mdisc": {c: count(list(M[c].values())) for c in M},
               "T_bg": len(T_bg), "T_col": sum(bl[t]["meta"]["T_col"] for t in ids),
               "T_edge": sum(bl[t]["meta"]["T_edge"] for t in ids)}
    E = {}
    g = solved(S("C1", "S2")) - solved(S("C0", "S2"))
    l = solved(S("C0", "S2")) - solved(S("C1", "S2"))
    E["E1"] = {"holds": len(g & T_bg) >= 2 and len(l & T_bg) <= 1, "gained_in_T_bg": sorted(g & T_bg), "lost_in_T_bg": sorted(l & T_bg)}
    n = lambda c, p: len(solved(S(c, p)))
    E["E2"] = {"holds": n("C3", "S0") >= max(n("C0", "S0"), n("C1", "S0")) - 1 and n("C3", "S2") >= max(n("C0", "S2"), n("C1", "S2")),
               "C0": [n("C0", "S0"), n("C0", "S2")], "C1": [n("C1", "S0"), n("C1", "S2")], "C3": [n("C3", "S0"), n("C3", "S2")]}
    w = lambda c, p: {t for t, v in S(c, p).items() if v == "wrong"}
    c0s0 = solved(S("C0", "S0"))
    abst = lambda c: {t for t in c0s0 if S(c, "S0")[t] == "abstain"}
    E["E3"] = {"holds": not (w("C4", "S0") - w("C0", "S0")) and len(abst("C4")) <= len(abst("C3")),
               "new_wrong_S0": sorted(w("C4", "S0") - w("C0", "S0")), "C0_solved_abstained_C4": sorted(abst("C4")),
               "C0_solved_abstained_C3": sorted(abst("C3"))}
    selt = [t for t in ids if bl[t]["meta"]["bg_ev_selected"]]
    inb = [t for t in selt if t in T_bg]
    outb = [t for t in selt if t not in T_bg]
    fm = sum(bl[t]["meta"]["bg_ev_contains_mode"] for t in inb) / len(inb) if inb else None
    fz = sum(bl[t]["meta"]["bg_ev_contains_zero"] for t in outb) / len(outb) if outb else None
    E["E4"] = {"holds": fm is not None and fz is not None and fm >= 0.7 and fz >= 0.9, "selected_tasks": len(selt),
               "in_T_bg": len(inb), "share_with_mode": round(fm, 3) if fm is not None else None,
               "outside_T_bg": len(outb), "share_with_zero": round(fz, 3) if fz is not None else None}
    g5 = solved(S("C5", "S2")) - solved(S("C0", "S2"))
    l5 = solved(S("C0", "S2")) - solved(S("C5", "S2"))
    E["E5"] = {"holds": len(l5) >= 2 and len(g5) <= 2, "gained": sorted(g5), "lost": sorted(l5)}
    g6 = solved(S("C6", "S2")) - solved(S("C0", "S2"))
    E["E6"] = {"holds": n("C6", "S2") >= n("C0", "S2") - 1 and len(g6) >= 1, "C6_S2": n("C6", "S2"), "gained": sorted(g6)}
    act = sum(bl[t]["meta"]["edge_content_applies"] and bl[t]["meta"]["same_size"] for t in ids)
    g8 = (solved(S("C8", "S2")) | solved(M["C8"])) - (solved(S("C0", "S2")) | solved(M["C0"]))
    E["E7"] = {"holds": act >= 20 and len(g8) >= 1 and not (w("C8", "S0") - w("C0", "S0")),
               "activated_same_size": act, "gained": sorted(g8), "new_wrong_S0": sorted(w("C8", "S0") - w("C0", "S0"))}
    g3m = solved(M["C3"]) - solved(M["C0"])
    nw3 = {t for t, v in M["C3"].items() if v == "wrong"} - {t for t, v in M["C0"].items() if v == "wrong"}
    l5m = solved(M["C0"]) - solved(M["C5"])
    E["E8"] = {"holds": len(g3m) >= 2 and len(nw3) <= 1 and len(l5m) >= 3, "C0": summary["mdisc"]["C0"],
               "pooled_bg_gained": sorted(g3m), "pooled_bg_new_wrong": sorted(nw3), "COL-rank_lost": sorted(l5m)}
    u0 = solved(S("C0", "S2")) | solved(M["C0"])
    u9 = solved(S("C9", "S2")) | solved(M["C9"])
    p0 = summary["blocks"]["C9|S0"]["precision"]
    p9 = summary["mdisc"]["C9"]["precision"]
    E["E9"] = {"holds": len(u9 - u0) >= 3 and (p0 is None or p0 >= 0.9) and (p9 is None or p9 >= 0.9),
               "gained": sorted(u9 - u0), "lost": sorted(u0 - u9), "C9_S0_precision": p0, "C9_mdisc_precision": p9}
    allu = set()
    for c in bl[ids[0]]["configs"]:
        allu |= solved(S(c, "S0")) | solved(S(c, "S2"))
    for c in M:
        allu |= solved(M[c])
    E["E10"] = {"holds": len(allu - u0) <= 8, "gained_by_any_configuration": sorted(allu - u0)}
    out = {"label": "ARC-AGI-1 training split, DEV (P-R2, amendment 5)", "summary": summary, "predictions": E,
           "mdisc_rows": M, "time_s": {"blocks": json.loads((HERE / "r2_blocks.json").read_text())["time_s"],
                                       "mdisc": json.loads((HERE / "r2_mdisc.json").read_text())["time_s"]}}
    (HERE / "r2.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: v for k, v in out.items() if k != "mdisc_rows"}, indent=1, default=str))


# ------------------------------------------------------------------ implementation check (not evidence)
def perturb(train, tests, kind, rng):
    used = set()
    for I, O in train + tests:
        used |= set(np.unique(I).tolist()) | set(np.unique(O).tolist())
    free = [c for c in range(1, 10) if c not in used]
    if kind == "bg-swap":
        if not free:
            return None
        c = rng.choice(free)
        lut = np.arange(10)
        lut[0], lut[c] = c, 0
        f = lambda g: lut[g]
        return [(f(I), f(O)) for I, O in train], [(f(I), f(O)) for I, O in tests]
    if kind == "global-perm":
        perm = list(range(1, 10))
        rng.shuffle(perm)
        lut = np.array([0] + perm)
        f = lambda g: lut[g]
        return [(f(I), f(O)) for I, O in train], [(f(I), f(O)) for I, O in tests]
    if kind == "pad-offset":
        def pad(g, top, left):
            out = np.zeros((g.shape[0] + top + 2, g.shape[1] + left + 2), dtype=g.dtype)
            out[top:top + g.shape[0], left:left + g.shape[1]] = g
            return out
        res = []
        for I, O in train + tests:
            top, left = rng.randint(1, 3), rng.randint(1, 3)
            res.append((pad(I, top, left), pad(O, top, left) if I.shape == O.shape else O))
        return res[:len(train)], res[len(train):]
    raise ValueError(kind)


def main_check():
    bl = json.loads((HERE / "r2_blocks.json").read_text())["rows"]
    rng = random.Random(20261020)
    tk = tasks()
    base = sorted(t for t, r in bl.items() if r["configs"]["C0"]["S2"] == "correct")
    out = {}
    for kind, cfgs in (("bg-swap", ["C0", "C1", "C3", "C4", "C9"]), ("global-perm", ["C0", "C5", "C6"]),
                       ("pad-offset", ["C0", "C7", "C8", "C9"])):
        kept = {c: 0 for c in cfgs}
        n = 0
        for t in base:
            p = perturb(*tk[t], kind, rng)
            if p is None:
                continue
            n += 1
            r = task_blocks(*p)
            for c in cfgs:
                kept[c] += r["configs"][c]["S2"] == "correct"
        out[kind] = {"C0_solved_tasks_perturbed": n, "still_solved_S2": kept}
        print(kind, out[kind], flush=True)
    (HERE / "r2_check.json").write_text(json.dumps({"label": "implementation check on self-made perturbations of DEV "
                                                             "tasks; by construction, not evidence", **out}, indent=1))


if __name__ == "__main__":
    {"blocks": main_blocks, "mdisc": main_mdisc, "combine": main_combine, "check": main_check}[sys.argv[1]]()
