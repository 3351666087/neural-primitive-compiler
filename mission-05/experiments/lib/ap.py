"""A-P: construct a priority plan from the goal spec by LOCAL contract checks only. CONSTRUCTOR SIDE.

For each order of the atoms and each choice of achiever variant (enumerated in a fixed order), accept the first
candidate such that
  applicability   no achiever must PICK a NO_PICK colour (its role colours are movable)
  progress        every chosen achiever has a certified progress contract
  preservation    for every i < j, achiever j preserves atom i: a table entry that is ok AND backed by at least
                  one checked state (vacuous entries are not certificates)
  resource        sum over atoms of (macro bound) * (6N + 1), plus 1 for a cue latch, is below the step limit
                  8 m N (K + 1) for every N in 5..15 and K in 1..min(7, N-1)
Otherwise OUT_OF_CLASS. No simulation, no global verification. Counts candidates and table lookups.
"""

from __future__ import annotations

import itertools
import json
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
VARS = {"ORDER": ("O1", "O2"), "ZONE": ("Z1", "Z2"), "GROUP": ("G1", "G2")}


def load_table():
    return json.loads((HERE / "contract_table.json").read_text())


def achiever_key(atom, var):
    if atom[0] == "ZONE":
        return f"ZONE:{var}:{atom[2]}:{atom[3]}"
    return f"{atom[0]}:{var}"


def pattern_key(g, a, fixed=()):
    """g's colours renamed relative to achiever atom a: A1 (, A2) = a's colours; other colours X1, X2 in order of
    appearance, except that a NO_PICK colour is always X2 (the role the contract table checks as possibly fixed)."""
    roles = {a[1]: "A1"}
    if a[0] == "ORDER":
        roles[a[2]] = "A2"
    for c in fixed:
        if c not in roles:
            roles[c] = "X2"
    free = [x for x in ("X1", "X2") if x not in roles.values()]
    nxt = iter(free)

    def r(c):
        if c not in roles:
            roles[c] = next(nxt)
        return roles[c]
    if g[0] == "ORDER":
        return f"ORDER({r(g[1])},{r(g[2])})"
    if g[0] == "ZONE":
        return f"ZONE({r(g[1])},{g[2]},{g[3]})"
    return f"GROUP({r(g[1])})"


def macro_bound(var, K):
    if var == "O1":
        return K // 2
    if var == "O2":
        return (K // 2) * (K - K // 2)
    return K


def resource_ok(plan, cue):
    m = len(plan)
    for N in range(5, 16):
        for K in range(1, min(7, N - 1) + 1):
            need = sum(macro_bound(v, K) for _, v in plan) * (6 * N + 1) + (1 if cue else 0)
            if need >= 8 * m * N * (K + 1):
                return False
    return True


def construct(spec, table=None, max_variants=2, evidence=None):
    """evidence (amendment 3): when set (e.g. "T7"), every progress and preservation entry a candidate uses must
    carry that evidence tag; otherwise the candidate is refused ("unchecked")."""
    t0 = time.perf_counter()
    table = table or load_table()
    atoms = spec["atoms"]
    fixed = {s[1] for s in spec["safety"] if s[0] == "NO_PICK"}
    cand = lookups = 0
    reasons = {}
    for perm in itertools.permutations(range(len(atoms))):
        order = [atoms[i] for i in perm]
        for vs in itertools.product(*[VARS[a[0]][:max_variants] for a in order]):
            cand += 1
            plan = list(zip(order, vs))
            why = None
            for a, v in plan:
                roles = [a[1], a[2]] if a[0] == "ORDER" else [a[1]]
                if any(c in fixed for c in roles):
                    why = "applicability"
                    break
                if not table["progress"][achiever_key(a, v)]["ok"]:
                    why = "progress"
                    break
                if evidence is not None and table["progress"][achiever_key(a, v)].get("evidence") != evidence:
                    why = "unchecked"
                    break
            if why is None:
                for j in range(len(plan)):
                    aj, vj = plan[j]
                    row = table["preserves"][achiever_key(aj, vj)]
                    for i in range(j):
                        lookups += 1
                        e = row.get(pattern_key(plan[i][0], aj, fixed))
                        if e is None or not e["ok"] or e["states"] == 0:
                            why = "preservation"
                            break
                        if evidence is not None and e.get("evidence") != evidence:
                            why = "unchecked"
                            break
                    if why:
                        break
            if why is None and not resource_ok(plan, spec.get("cue")):
                why = "resource"
            if why is None:
                return {"status": "CONSTRUCTED", "plan": plan, "candidates": cand, "lookups": lookups,
                        "time_s": time.perf_counter() - t0}
            reasons[why] = reasons.get(why, 0) + 1
    return {"status": "OUT_OF_CLASS", "plan": None, "candidates": cand, "lookups": lookups, "reasons": reasons,
            "time_s": time.perf_counter() - t0}
