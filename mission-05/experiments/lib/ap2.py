"""A-P': shared-potential certificates from the damage table (amendment 2). CONSTRUCTOR SIDE; no simulation.

For each choice of achiever variants (atoms kept in goal order; a potential certificate does not depend on the
priority order, so any order is sound), build the goal's templates:
  L-tmpl  one KD over the transitive closure of all ORDER atoms (no certificate if it has a cycle),
          one OUT per ZONE atom, one OOW per GROUP atom (with the chosen GROUP variant)
  L-lin   one INV (= KD over one pair) per ORDER atom, OUT and OOW as above
and search integer weights w in {0..4}^|T| (not all 0) such that every achiever j in the plan has
sum_k w_k * maxDelta(j, k) <= -1 (a growing entry forces w_k = 0), with the smallest worst-case potential, then
check the resource condition. Reasons for refusal are recorded.
"""

from __future__ import annotations

import itertools
import json
import time
from pathlib import Path

from potentials import closure, roles_for, template_key, template_max

HERE = Path(__file__).resolve().parent
VARS = {"ORDER": ("O1", "O2"), "ZONE": ("Z1", "Z2"), "GROUP": ("G1", "G2")}


def load_damage(path=None):
    return json.loads(Path(path or HERE / "damage_table.json").read_text())["table"]


def load_progress():
    return json.loads((HERE / "contract_table.json").read_text())["progress"]


def achiever_key(atom, var):
    return f"ZONE:{var}:{atom[2]}:{atom[3]}" if atom[0] == "ZONE" else f"{atom[0]}:{var}"


def templates(atoms, plan_vars, mode):
    orders = [(a[1], a[2]) for a in atoms if a[0] == "ORDER"]
    T = []
    if orders:
        if mode == "tmpl":
            cl = closure(orders)
            if cl is None:
                return None
            T.append(("KD", tuple(cl)))
        else:
            T += [("KD", ((lo, hi),)) for lo, hi in orders]
    for a, v in zip(atoms, plan_vars):
        if a[0] == "ZONE":
            T.append(("OUT", a[1], a[2], a[3]))
        elif a[0] == "GROUP":
            T.append(("OOW", a[1], v))
    return T


def colours(atoms, fixed):
    cs = []
    for a in atoms:
        for c in ([a[1], a[2]] if a[0] == "ORDER" else [a[1]]):
            if c not in cs:
                cs.append(c)
    return cs + [c for c in fixed if c not in cs]


def resource_ok(w, T, m, cue):
    for N in range(5, 16):
        for K in range(1, min(7, N - 1) + 1):
            phi = sum(wk * template_max(t, K) for wk, t in zip(w, T))
            if phi * (6 * N + 1) + (1 if cue else 0) >= 8 * m * N * (K + 1):
                return False
    return True


def construct(spec, mode="tmpl", damage=None, progress=None, max_variants=2):
    t0 = time.perf_counter()
    damage = damage or load_damage()
    progress = progress or load_progress()
    atoms = spec["atoms"]
    fixed = [s[1] for s in spec["safety"] if s[0] == "NO_PICK"]
    cols = colours(atoms, fixed)
    cand = weight_checks = 0
    reasons = {}
    for vs in itertools.product(*[VARS[a[0]][:max_variants] for a in atoms]):
        cand += 1
        why = None
        for a, v in zip(atoms, vs):
            roles = [a[1], a[2]] if a[0] == "ORDER" else [a[1]]
            if any(c in fixed for c in roles):
                why = "applicability"
            elif not progress[achiever_key(a, v)]["ok"]:
                why = "progress"
        T = None if why else templates(atoms, vs, mode)
        if why is None and T is None:
            why = "cycle"
        if why is None:
            # damage matrix: rows = achievers in the plan, columns = templates
            D = []
            for a, v in zip(atoms, vs):
                rmap = roles_for(a, cols, fixed)
                ent = damage[achiever_key(a, v)]["entries"]
                row = []
                for t in T:
                    k = template_key(t, rmap) if rmap else None
                    b = ent.get(k, {}).get("bound") if k else None
                    row.append(float("inf") if b in (None, "inf") else b)
                D.append(row)
            best = None
            for w in itertools.product(range(5), repeat=len(T)):
                if not any(w):
                    continue
                weight_checks += 1
                ok = True
                for row in D:
                    s = 0
                    for wk, d in zip(w, row):
                        if wk == 0:
                            continue
                        if d == float("inf"):
                            ok = False
                            break
                        s += wk * d
                    if not ok or s > -1:
                        ok = False
                        break
                if ok:
                    phi = sum(wk * template_max(t, 7) for wk, t in zip(w, T))
                    if best is None or phi < best[0]:
                        best = (phi, w)
            if best is None:
                why = "no_weights"
            elif not resource_ok(best[1], T, len(atoms), spec.get("cue")):
                why = "resource"
            else:
                return {"status": "CONSTRUCTED", "plan": list(zip(atoms, vs)), "weights": list(best[1]),
                        "templates": [list(map(str, t)) for t in T], "candidates": cand, "weight_checks": weight_checks,
                        "time_s": time.perf_counter() - t0}
        reasons[why] = reasons.get(why, 0) + 1
    return {"status": "OUT_OF_CLASS", "plan": None, "candidates": cand, "weight_checks": weight_checks,
            "reasons": reasons, "time_s": time.perf_counter() - t0}
