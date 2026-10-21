"""Constructors and judging for ACH-DSL achievers (G3). The A-P and A-P' procedures of ap.py / ap2.py, with the
variant set given explicitly (every spec that applies to the atom) and contract tables keyed by dsl.ach_key.

Tables (A or B):
  damage[key]["entries"][template] = {"bound", "evidence"}
  progress[key] = {"ok", "evidence", "measure"}     (measure: the template whose decrease was proved)
  preserves[key][pattern] = {"ok", "evidence"}     (A-P only)
An entry counts only if it carries the required evidence tag. Resource checks as in ap / ap2, with the macro bound of
a spec achiever = the maximum of its measure (ORDER: K*K // 4; ZONE, GROUP: K).
"""

from __future__ import annotations

import itertools
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(EXP / "lib"))
sys.path.insert(0, str(EXP / "judge"))
sys.path.insert(0, str(EXP / "pilots"))
sys.path.insert(0, str(HERE))
import cir_interp as CI  # noqa: E402
import instances as INS  # noqa: E402
import dsl  # noqa: E402
from ap import pattern_key  # noqa: E402
from ap2 import colours  # noqa: E402
from cir_dsl import emit_dsl  # noqa: E402
from potentials import closure, roles_for, template_key, template_max  # noqa: E402
from run_pa1 import judge_all  # noqa: E402

INF = float("inf")


def macro_bound(atom_type, K):
    return (K * K) // 4 if atom_type == "ORDER" else K


def _gate(atoms, plan_specs, fixed, progress, evidence):
    for a, sp in zip(atoms, plan_specs):
        roles = [a[1], a[2]] if a[0] == "ORDER" else [a[1]]
        if any(c in fixed for c in roles):
            return "applicability"
        p = progress.get(dsl.ach_key(sp, a))
        if not p or not p["ok"] or p.get("evidence") != evidence:
            return "progress"
    return None


def construct_ap(spec, specs, table, evidence):
    t0 = time.perf_counter()
    atoms = spec["atoms"]
    fixed = {s[1] for s in spec["safety"] if s[0] == "NO_PICK"}
    reasons, cand = {}, 0
    for perm in itertools.permutations(range(len(atoms))):
        order = [atoms[i] for i in perm]
        for sps in itertools.product(*[[s for s in specs if dsl.applies_to(s, a)] for a in order]):
            cand += 1
            why = _gate(order, sps, fixed, table["progress"], evidence)
            if why is None:
                for j in range(len(order)):
                    row = table["preserves"].get(dsl.ach_key(sps[j], order[j]), {})
                    for i in range(j):
                        e = row.get(pattern_key(order[i], order[j], fixed))
                        if e is None or not e["ok"] or e.get("evidence") != evidence:
                            why = "preservation"
                            break
                    if why:
                        break
            if why is None:
                m = len(order)
                ok = True
                for N in range(5, 16):
                    for K in range(1, min(7, N - 1) + 1):
                        need = sum(macro_bound(a[0], K) for a in order) * (6 * N + 1) + (1 if spec.get("cue") else 0)
                        if need >= 8 * m * N * (K + 1):
                            ok = False
                if not ok:
                    why = "resource"
            if why is None:
                return {"status": "CONSTRUCTED", "plan": [[a, s["id"]] for a, s in zip(order, sps)], "candidates": cand,
                        "time_s": time.perf_counter() - t0}
            reasons[why] = reasons.get(why, 0) + 1
    return {"status": "OUT_OF_CLASS", "plan": None, "candidates": cand, "reasons": reasons, "time_s": time.perf_counter() - t0}


def _templates(atoms, plan_specs, progress):
    orders = [(a[1], a[2]) for a in atoms if a[0] == "ORDER"]
    T = []
    if orders:
        cl = closure(orders)
        if cl is None:
            return None
        T.append(("KD", tuple(cl)))
    for a, sp in zip(atoms, plan_specs):
        if a[0] == "ZONE":
            T.append(("OUT", a[1], a[2], a[3]))
        elif a[0] == "GROUP":
            m = progress[dsl.ach_key(sp, a)]["measure"]           # "OOW(A1,G1)" or "OOW(A1,G2)"
            T.append(("OOW", a[1], m[-3:-1]))
    return T


def _row(a, sp, T, cols, fixed, damage, evidence):
    rmap = roles_for(a, cols, fixed)
    ent = damage.get(dsl.ach_key(sp, a), {}).get("entries", {})
    out = []
    for t in T:
        k = template_key(t, rmap) if rmap else None
        e = ent.get(k, {}) if k else {}
        b = e.get("bound") if e.get("evidence") == evidence else None
        out.append(INF if b in (None, "inf") else b)
    return out


def construct_app(spec, specs, table, evidence):
    t0 = time.perf_counter()
    atoms = spec["atoms"]
    fixed = [s[1] for s in spec["safety"] if s[0] == "NO_PICK"]
    cols = colours(atoms, fixed)
    reasons, cand = {}, 0
    for sps in itertools.product(*[[s for s in specs if dsl.applies_to(s, a)] for a in atoms]):
        cand += 1
        why = _gate(atoms, sps, set(fixed), table["progress"], evidence)
        T = None if why else _templates(atoms, sps, table["progress"])
        if why is None and T is None:
            why = "cycle"
        if why is None:
            D = [_row(a, sp, T, cols, fixed, table["damage"], evidence) for a, sp in zip(atoms, sps)]
            best = None
            for w in itertools.product(range(5), repeat=len(T)):
                if not any(w):
                    continue
                ok = True
                for row in D:
                    s_ = 0
                    for wk, d in zip(w, row):
                        if wk == 0:
                            continue
                        if d == INF:
                            ok = False
                            break
                        s_ += wk * d
                    if not ok or s_ > -1:
                        ok = False
                        break
                if ok:
                    phi = sum(wk * template_max(t, 7) for wk, t in zip(w, T))
                    if best is None or phi < best[0]:
                        best = (phi, w)
            if best is None:
                why = "no_weights"
            else:
                okr = True
                for N in range(5, 16):
                    for K in range(1, min(7, N - 1) + 1):
                        phi = sum(wk * template_max(t, K) for wk, t in zip(best[1], T))
                        if phi * (6 * N + 1) + (1 if spec.get("cue") else 0) >= 8 * len(atoms) * N * (K + 1):
                            okr = False
                if not okr:
                    why = "resource"
                else:
                    return {"status": "CONSTRUCTED", "plan": [[a, s["id"]] for a, s in zip(atoms, sps)],
                            "weights": list(best[1]), "templates": [list(map(str, t)) for t in T], "candidates": cand,
                            "time_s": time.perf_counter() - t0}
        reasons[why] = reasons.get(why, 0) + 1
    return {"status": "OUT_OF_CLASS", "plan": None, "candidates": cand, "reasons": reasons, "time_s": time.perf_counter() - t0}


def check_certificate(spec, plan, weights, specs_by_id, table, evidence):
    atoms = [a for a, _ in plan]
    sps = [specs_by_id[i] for _, i in plan]
    fixed = [s[1] for s in spec["safety"] if s[0] == "NO_PICK"]
    if _gate(atoms, sps, set(fixed), table["progress"], evidence):
        return False
    T = _templates(atoms, sps, table["progress"])
    if T is None:
        return False
    cols = colours(atoms, fixed)
    for a, sp in zip(atoms, sps):
        row = _row(a, sp, T, cols, fixed, table["damage"], evidence)
        if sum(wk * d for wk, d in zip(weights, row) if wk) > -1:
            return False
    return True


def judge_plan(spec, plan, specs_by_id, cache, key):
    if key in cache:
        return cache[key]
    pl = [(a, specs_by_id[i]) for a, i in plan]
    train, unseen = INS.v_train(spec), INS.v_unseen(spec)
    mk = lambda N: emit_dsl(pl, spec, N)
    res = {"J1_sym": judge_all(mk, spec, train, unseen), "J2_mc6": CI.judge_set(mk(6), spec, INS.v_mc6(spec))}
    res["failures"] = res["J1_sym"]["total_failures"] + res["J2_mc6"]["failures"]
    cache[key] = res
    return res
