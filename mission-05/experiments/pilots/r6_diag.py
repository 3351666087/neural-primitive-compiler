"""POST-HOC diagnostics for round 6 (written after r6.json was scored; nothing here changes a verdict).

  (a) Why is B-RULE more conservative than TZ (H2), and why do 40 entries gain combinations at N = 7 (H3)?
      Re-simulate the disc-1000 version spaces keeping only eligible states (libval2.eligible: atom violated,
      satisfiable on its own, spare cell). This uses knowledge B was not allowed (the satisfiability solver and the
      spare-cell rule); it only attributes the gap.
  (b) Why does five-50 have dangerous entries (H6)? The B-GRAM class chosen for those entries and the entries with
      hold-out errors.

  python -I r6_diag.py      # writes r6_diag.json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
LIB = EXP / "lib"
sys.path.insert(0, str(LIB))
sys.path.insert(0, str(HERE))
import bgram  # noqa: E402
import brule  # noqa: E402
from libval import ROLE, achiever_instances, states  # noqa: E402
from libval2 import eligible  # noqa: E402
from model import holds  # noqa: E402
from potentials import patterns  # noqa: E402
from run_r4 import compare  # noqa: E402
from run_r6 import table_from  # noqa: E402


def simulate_eligible(rules, Ns=(3, 4, 5, 6, 7)):
    ach = achiever_instances()
    keys = {k: patterns(a[0]) for k, a, _ in ach}
    regs = {k: brule.template_regions(keys[k]) for k, _, _ in ach}
    sup = {k: {kk: (set(), set()) for kk in keys[k]} for k, _, _ in ach}
    late = {k: set() for k, _, _ in ach}
    for N in Ns:
        for cells, haz, fixed in states(N):
            types = [brule.ctype(c, h, fixed) for c, h in zip(cells, haz)]
            rcache = {}
            for akey, a, v in ach:
                if holds(a, cells, ROLE) or rules.get(akey) is None:
                    continue
                sel = brule.selections(a, *rules[akey], cells, haz, fixed, types, brule.masks(a, cells, haz, fixed))
                if not sel or not eligible(a, cells, haz, fixed):
                    continue
                for d, s in sel:
                    l, r = min(d, s), max(d, s)
                    for kk, t in regs[akey].items():
                        if t is None:
                            pair = ((cells[l], 0), (cells[r], 0))
                            trip = {(pair[0], pair[1], (cells[z], 0)) for z in range(l + 1, r)}
                        else:
                            R = brule.region_of(t, cells, haz, fixed, rcache)
                            pair = ((cells[l], int(l in R)), (cells[r], int(r in R)))
                            trip = set()
                        P, T = sup[akey][kk]
                        if pair not in P:
                            P.add(pair)
                            if N == 7:
                                late[akey].add(kk)
                        for tr in trip - T:
                            T.add(tr)
                            if N == 7:
                                late[akey].add(kk)
    return sup, late


def main():
    t0 = time.process_time()
    t7 = json.loads((LIB / "t7_tables.json").read_text())
    tz = json.loads((LIB / "tz_table.json").read_text())
    ach = {k: a for k, a, _ in achiever_instances()}
    out = {"label": "POST-HOC diagnostics of round 6"}
    data = bgram.collect(1000, (5, 6, 7))
    rules = {}
    for akey, a in ach.items():
        fd, fs, nd, ns = brule.learn_rules(a, data[akey])
        rules[akey] = (fd, fs) if fd and fs and nd * ns <= 64 else None
    hold = bgram.holdout()
    rec, _ = bgram.run_variant(1000, (5, 6, 7), hold)
    sup, late = simulate_eligible(rules)
    dmg, _ = table_from(rec, lambda a, k: (rec[a][k]["rows_obs"][0] | sup[a][k][0], rec[a][k]["rows_obs"][1] | sup[a][k][1]))
    out["a"] = {"vs_T7": compare(dmg, t7["damage"]), "vs_TZ": compare(dmg, tz["table"]),
                "entries_with_new_combination_at_N7": sorted(f"{a} / {k}" for a, ks in late.items() for k in ks)}
    out["a"]["vs_T7"].pop("dangerous_list")
    print("(a) eligible-only simulation: vs T7", {k: out["a"]["vs_T7"][k] for k in ("equal", "dangerous", "conservative")},
          "agreement with TZ", round(out["a"]["vs_TZ"]["agreement"], 3), "new at N=7", len(out["a"]["entries_with_new_combination_at_N7"]))
    rec50, diag50 = bgram.run_variant(50, (5,), hold)
    hold_err = []
    for akey, a in ach.items():
        for k in patterns(a[0]):
            g = rec50[akey][k]["gram"]
            for p, ts, dd in __import__("bexch").rows_for(k, hold[akey]):
                import numpy as np
                pr = None if g.law == "GLOB" else g.value(bgram.e_func(p) + sum((bgram.b_func(t) for t in ts), np.zeros(35)))
                if pr is not None and pr != dd:
                    hold_err.append(f"{akey} / {k}")
                    break
    out["b"] = {"classes_of_dangerous": {e: rec50[e.split(" / ")[0]][e.split(" / ")[1]]["gram"].law
                                         for e in ("GROUP:G2 / KD{X1<X2}", "GROUP:G2 / KD{X2<X1}")},
                "entries_with_holdout_errors": sorted(set(hold_err)), "holdout": diag50["holdout"]}
    print("(b)", out["b"])
    out["cpu_s"] = round(time.process_time() - t0, 1)
    (HERE / "r6_diag.json").write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
