"""Truth tables for arbitrary achievers by exhaustive checking at N = 3..7 (G3; the libval3 procedure generalised).

For each achiever instance (key, atom, select_fn) and the state distribution of libval.states:
  damage       maximum one-step change of every template pattern at each N, over eligible states (atom violated,
               satisfiable on its own, spare cell) where the selection applies and the macro can run;
               bounded iff max(N=7) <= max(N=6) (bound = max over N)
  preserves    for every atom pattern over the roles: a counterexample (eligible, pattern held, jointly satisfiable,
               pattern broken by the move) or none
  applicable   eligible states where the selection gives no move or the macro cannot run (counterexample) or none
The satisfiability checks run only when a state could change the result (same results as checking every state).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))
from libval import ROLE, _parse, key as atom_key, patterns as atom_patterns, states  # noqa: E402
from libval2 import classify  # noqa: E402
from libval3 import Evaluator  # noqa: E402
from model import holds, reloc, satisfiable  # noqa: E402
from potentials import patterns  # noqa: E402


def roles_of(atom):
    return ["A1", "A2", "X1", "X2"] if atom[0] == "ORDER" else ["A1", "X1", "X2"]


def tables(achs, Ns=(3, 4, 5, 6, 7)):
    t0 = time.process_time()
    keys_of = {k: patterns(a[0]) for k, a, _ in achs}
    all_keys = sorted({x for ks in keys_of.values() for x in ks})
    pres = {k: [(atom_key(gp), gp) for gp in atom_patterns(roles_of(a)) if atom_key(gp) != atom_key(a)] for k, a, _ in achs}
    mx = {k: {x: {} for x in keys_of[k]} for k, _, _ in achs}
    pcex = {k: {gk: None for gk, _ in pres[k]} for k, _, _ in achs}
    acex = {k: None for k, _, _ in achs}
    for N in Ns:
        ev = Evaluator(all_keys, N)
        for k in mx:
            for x in mx[k]:
                mx[k][x][N] = None
        for cells, haz, fixed in states(N):
            if not any(cells[p] == 0 and not haz[p] for p in range(N)):
                continue
            before = None
            after_vals = {}
            sat = {}

            def elig(a, akey):
                if akey not in sat:
                    sat[akey] = satisfiable([a], cells, haz, True, fixed, ROLE)
                return sat[akey]
            for akey, a, sel_fn in achs:
                if holds(a, cells, ROLE):
                    continue
                sel = sel_fn(a, None, cells, haz, True, fixed, ROLE)
                r = reloc(cells, 0, sel[0], sel[1], haz, True) if sel else None
                if r is None:
                    if acex[akey] is None and elig(a, akey):
                        acex[akey] = {"N": N, "cells": cells, "haz": haz, "fixed": fixed, "selection": sel}
                    continue
                after = r[0]
                if before is None:
                    before = ev(cells, haz, fixed)
                if after not in after_vals:
                    after_vals[after] = ev(after, haz, fixed)
                av = after_vals[after]
                row = mx[akey]
                new = [(x, av[x] - before[x]) for x in keys_of[akey] if row[x][N] is None or av[x] - before[x] > row[x][N]]
                if new and elig(a, akey):
                    for x, d in new:
                        row[x][N] = d
                for gk, gp in pres[akey]:
                    if pcex[akey][gk] is not None:
                        continue
                    if holds(gp, cells, ROLE) and not holds(gp, after, ROLE) and elig(a, akey):
                        if satisfiable([a, gp], cells, haz, True, fixed, ROLE):
                            pcex[akey][gk] = {"N": N, "cells": cells, "haz": haz, "fixed": fixed, "after": after}
    out = {}
    for akey, a, _ in achs:
        dmg = {x: {"max_by_N": per, "bound": classify(per)} for x, per in mx[akey].items()}
        out[akey] = {"atom": a, "damage": dmg, "preserves": {gk: {"cex": c} for gk, c in pcex[akey].items()},
                     "applicability_cex": acex[akey]}
    return out, time.process_time() - t0
