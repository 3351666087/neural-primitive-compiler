"""T7 (amendment 3): contract tables by exhaustive checking at N = 3..7. CONSTRUCTOR SIDE.

  damage     for every achiever instance and template pattern, the maximum one-step increase at each N = 3..7
             (state distribution and eligibility as in libval2.py). Bounded iff max(N=7) <= max(N=6), with bound =
             the maximum over all N; otherwise infinite. A bounded entry carries evidence "T7".
  preserves  every entry certified by G2 (contract_table.json, ok): exhaustive search for a counterexample at N = 6
             and N = 7 (conditions as in libval.py). An entry keeps evidence "T7" iff it has no counterexample and
             is non-vacuous at N <= 5.
  progress   (supplementary; no locked prediction) every achiever's progress contract re-checked at N = 6, 7.
The satisfiability check (the expensive part of eligibility) runs only when a state could change the result: a
delta above the current maximum, a pattern that breaks, or a relocation that does not decrease the measure. The
tables are the same as when every state is checked. Self-check: the maxima at N = 3..5 equal damage_table.json.

  python -I libval3.py            # writes t7_tables.json
  python -I libval3.py --smoke    # development check: N = 3..5 only, writes nothing
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from libval import ROLE, _parse, achiever_instances, states  # noqa: E402
from libval2 import classify  # noqa: E402
from model import group_window, holds, measure, reloc, satisfiable, select, zcells  # noqa: E402
from potentials import evaluate, patterns  # noqa: E402

COLS = (1, 2, 3, 4)


def parse_key(k):
    if k.startswith("KD{"):
        return ("KD", tuple((ROLE[a], ROLE[c]) for a, c in (x.split("<") for x in k[3:-1].split(";"))))
    t, rest = k.split("(", 1)
    args = rest[:-1].split(",")
    if t == "OUT":
        return ("OUT", ROLE[args[0]], args[1], args[2] if args[2] == "half" else int(args[2]))
    return ("OOW", ROLE[args[0]], args[1])


class Evaluator:
    """All template values of one cell configuration at once (the same quantities as potentials.evaluate)."""

    def __init__(self, keys, N):
        self.keys = keys
        self.parsed = {k: parse_key(k) for k in keys}
        self.zones = {(s, w): set(zcells(N, s, w)) for s in ("left", "right") for w in (2, "half")}

    def __call__(self, cells, haz, fixed):
        inv = [[0] * 5 for _ in range(5)]          # inv[lo][hi] = pairs with hi before lo
        seen = [0] * 5
        for x in cells:
            if x:
                for h in COLS:
                    if h != x:
                        inv[x][h] += seen[h]
                seen[x] += 1
        wins = {}
        out = {}
        for k, p in self.parsed.items():
            if p[0] == "KD":
                out[k] = sum(inv[lo][hi] for lo, hi in p[1])
            elif p[0] == "OUT":
                z = self.zones[(p[2], p[3])]
                out[k] = sum(1 for q, x in enumerate(cells) if x == p[1] and q not in z)
            else:
                if (p[1], p[2]) not in wins:
                    wins[(p[1], p[2])] = group_window(["GROUP", p[1]], cells, {}, haz, True, fixed, p[2])
                win = wins[(p[1], p[2])]
                out[k] = 0 if win is None else sum(1 for q, x in enumerate(cells) if x == p[1] and q not in win)
        return out


def self_check_evaluator(N):
    keys = sorted(set(patterns("ORDER")) | set(patterns("ZONE")))
    ev = Evaluator(keys, N)
    bad = 0
    for cells, haz, fixed in states(N):
        vals = ev(cells, haz, fixed)
        for k in keys:
            if vals[k] != evaluate(k, cells, haz, True, fixed, ROLE):
                bad += 1
    return bad


def main():
    t0, c0 = time.perf_counter(), time.process_time()
    ach = achiever_instances()
    keys_of = {akey: patterns(a[0]) for akey, a, _ in ach}
    all_keys = sorted({k for ks in keys_of.values() for k in ks})
    g2 = json.loads((HERE / "contract_table.json").read_text())
    t5 = json.loads((HERE / "damage_table.json").read_text())["table"]
    pres_keys = {akey: [(gk, _parse(gk)) for gk, e in g2["preserves"][akey].items() if e["ok"]] for akey, _, _ in ach}
    mx = {akey: {k: {} for k in keys_of[akey]} for akey, _, _ in ach}
    pres_cex = {akey: {gk: None for gk, _ in pres_keys[akey]} for akey, _, _ in ach}
    prog_cex = {akey: None for akey, _, _ in ach}
    stats = {"sat_calls": 0, "candidates": {}}
    bad_eval = {N: self_check_evaluator(N) for N in (3, 4)}
    print("evaluator self-check (mismatches)", bad_eval, flush=True)
    smoke = "--smoke" in sys.argv
    NS = (3, 4, 5) if smoke else (3, 4, 5, 6, 7)
    for N in NS:
        ev = Evaluator(all_keys, N)
        for akey in mx:
            for k in mx[akey]:
                mx[akey][k][N] = None
        cand = 0
        for cells, haz, fixed in states(N):
            if not any(cells[p] == 0 and not haz[p] for p in range(N)):
                continue
            before = None
            after_vals = {}
            sat_cache = {}

            def eligible1(a):
                key = ("1", tuple(a))
                if key not in sat_cache:
                    stats["sat_calls"] += 1
                    sat_cache[key] = satisfiable([a], cells, haz, True, fixed, ROLE)
                return sat_cache[key]

            for akey, a, v in ach:
                if holds(a, cells, ROLE):
                    continue
                sel = select(a, v, cells, haz, True, fixed, ROLE)
                r = reloc(cells, 0, sel[0], sel[1], haz, True) if sel else None
                if N >= 6 and prog_cex[akey] is None:
                    m0 = measure(a, cells, ROLE, haz, True, fixed, v)
                    dec = r is not None and m0 is not None and measure(a, r[0], ROLE, haz, True, fixed, v) < m0
                    if not dec and eligible1(a):
                        prog_cex[akey] = {"N": N, "cells": cells, "haz": haz, "fixed": fixed}
                if r is None:
                    continue
                cand += 1
                after = r[0]
                if before is None:
                    before = ev(cells, haz, fixed)
                if sel not in after_vals:
                    after_vals[sel] = ev(after, haz, fixed)
                av = after_vals[sel]
                row = mx[akey]
                new = [(k, av[k] - before[k]) for k in keys_of[akey]
                       if row[k][N] is None or av[k] - before[k] > row[k][N]]
                if new and eligible1(a):
                    for k, d in new:
                        row[k][N] = d
                if N >= 6:
                    for gk, gp in pres_keys[akey]:
                        if pres_cex[akey][gk] is not None:
                            continue
                        if holds(gp, cells, ROLE) and not holds(gp, after, ROLE) and eligible1(a):
                            stats["sat_calls"] += 1
                            if satisfiable([a, gp], cells, haz, True, fixed, ROLE):
                                pres_cex[akey][gk] = {"N": N, "cells": cells, "haz": haz, "fixed": fixed, "after": after}
        stats["candidates"][N] = cand
        print("N", N, "done", round(time.perf_counter() - t0, 1), "s", "sat calls", stats["sat_calls"], flush=True)
    damage = {}
    t5_mismatch = []
    for akey in mx:
        ent = {}
        for k, per in mx[akey].items():
            b = classify(per) if not smoke else None
            ent[k] = {"max_by_N": per, "bound": b, "evidence": "T7" if b not in (None, "inf") else None}
            for N in (3, 4, 5):
                if t5[akey]["entries"][k]["max_by_N"][str(N)] != per[N]:
                    t5_mismatch.append(f"{akey} / {k} / N={N}")
        damage[akey] = {"entries": ent}
    preserves = {}
    for akey, _, _ in ach:
        preserves[akey] = {}
        for gk, e in g2["preserves"][akey].items():
            cex = pres_cex[akey].get(gk)
            ok = e["ok"] and cex is None
            preserves[akey][gk] = {"ok": ok, "states": e["states"], "ok_N5": e["ok"], "cex_N67": cex,
                                   "evidence": "T7" if ok and e["states"] > 0 else None}
    progress = {}
    for akey, _, _ in ach:
        ok = g2["progress"][akey]["ok"] and prog_cex[akey] is None
        progress[akey] = {"ok": ok, "cex_N67": prog_cex[akey], "evidence": "T7" if ok else None}
    out = {"label": "T7: contract tables by exhaustive checking at N = 3..7 (amendment 3); bounded iff max(N=7) <= max(N=6) [P]",
           "damage": damage, "preserves": preserves, "progress": progress,
           "self_check": {"evaluator_mismatches_N3_N4": bad_eval, "t5_reproduced": not t5_mismatch,
                          "t5_mismatches": t5_mismatch[:20]},
           "summary": {"damage_entries": sum(len(d["entries"]) for d in damage.values()),
                       "damage_bounded": sum(e["bound"] not in (None, "inf") for d in damage.values() for e in d["entries"].values()),
                       "pairwise_checked": sum(len(v) for v in pres_keys.values()),
                       "pairwise_refuted": sum(c is not None for v in pres_cex.values() for c in v.values()),
                       "progress_refuted": sum(c is not None for c in prog_cex.values())},
           "stats": stats, "time_s": round(time.perf_counter() - t0, 1), "cpu_s": round(time.process_time() - c0, 1)}
    if not smoke:
        (HERE / "t7_tables.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(out["summary"]), json.dumps(out["self_check"]), "time", out["time_s"], "cpu", out["cpu_s"])


if __name__ == "__main__":
    main()
