"""G3 self-check (DEV): the generic ACH-DSL pipeline must reproduce the library on the library's own achievers,
re-expressed as specs (specs_library.json). Nothing here is held out.

  1 selection   dsl.select_dsl == model.select on every state N = 3..7 (hazard rule on) and N = 3..6 (rule off)
                where the atom is violated
  2 controller  cir_dsl.emit_dsl and cirgen.emit give the same outcome and step count on every V_train instance,
                for every plan constructed in rounds 3-5 (A-P' with TZ, A-P with TZ-P2)
  3 truth       truth.tables == T7 (damage maxima at N = 3..7; counterexample present or not for every
                preservation pattern); no applicability counterexample
  4 A tables    z3_dsl bounds: same as TZ or tighter, never below the N <= 7 truth; z3_dsl.prove: PROVED on every
                entry TZ-P2 proves, and on no entry with a truth counterexample
  5 constructors construct_app (evidence TZ) builds TZ's 30 goals; construct_ap builds TZ-P2's 36
  6 B           b_dsl on the library (N = 5, n = 1000): version-space sizes as in round 6; 0 dangerous vs T7

  python -I selfcheck.py      # writes selfcheck.json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(EXP / "lib"))
sys.path.insert(0, str(EXP / "judge"))
sys.path.insert(0, str(EXP / "pilots"))
sys.path.insert(0, str(HERE))
import b_dsl  # noqa: E402
import cir_interp as CI  # noqa: E402
import cirgen  # noqa: E402
import construct as C  # noqa: E402
import dsl  # noqa: E402
import instances as INS  # noqa: E402
import truth  # noqa: E402
import z3_dsl  # noqa: E402
from cir_dsl import emit_dsl  # noqa: E402
from libval import ROLE, achiever_instances, states  # noqa: E402
from model import holds, select  # noqa: E402
from potentials import patterns  # noqa: E402
from a_dsl import a_tables  # noqa: E402
from run_pa3 import goals  # noqa: E402
from run_r4 import compare  # noqa: E402

LIBMAP = {"ORDER:O1": "LIB-O1", "ORDER:O2": "LIB-O2", "GROUP:G1": "LIB-G1", "GROUP:G2": "LIB-G2"}
for _z in ("Z1", "Z2"):
    for _s, _t in (("left", "L"), ("right", "R")):
        for _w in (2, "half"):
            LIBMAP[f"ZONE:{_z}:{_s}:{_w}"] = f"LIB-{_z}-{_t}|{_s}|{_w}"
VARMAP = {("ORDER", "O1"): "LIB-O1", ("ORDER", "O2"): "LIB-O2", ("GROUP", "G1"): "LIB-G1", ("GROUP", "G2"): "LIB-G2"}


def spec_id_for(atom, var):
    if atom[0] == "ZONE":
        return f"LIB-{var}-{'L' if atom[2] == 'left' else 'R'}"
    return VARMAP[(atom[0], var)]


def main():
    t0 = time.process_time()
    specs = json.loads((HERE / "specs_library.json").read_text())["specs"]
    by_id = {s["id"]: s for s in specs}
    assert all(not dsl.validate(s) for s in specs)
    out = {"label": "G3 self-check on the library re-expressed in ACH-DSL (DEV)"}
    lib = {k: (a, v) for k, a, v in achiever_instances()}

    # 1 selection
    mism = {"rule_on": 0, "rule_off": 0, "checked": 0}
    for libkey, (a, v) in lib.items():
        sid = LIBMAP[libkey].split("|")[0]
        for N in (3, 4, 5, 6, 7):
            for cells, haz, fixed in states(N):
                if holds(a, cells, ROLE):
                    continue
                for rule in ((True, False) if N <= 6 else (True,)):
                    mism["checked"] += 1
                    if select(a, v, cells, haz, rule, fixed, ROLE) != dsl.select_dsl(by_id[sid], a, cells, haz, rule, fixed, ROLE):
                        mism["rule_on" if rule else "rule_off"] += 1
    out["1_selection"] = mism
    print("1 selection", mism, flush=True)

    # 2 controller
    G = goals()
    cr = json.loads((EXP / "pilots" / "cr.json").read_text())
    r5 = json.loads((EXP / "pilots" / "r5.json").read_text())
    plans = {}
    for g, r in cr["A-P'"]["TZ"].items():
        if r["status"] == "CONSTRUCTED":
            plans[f"{g}|app"] = (g, r["plan"])
    for g, r in r5["A-P"].items():
        if r["status"] == "CONSTRUCTED":
            plans[f"{g}|ap"] = (g, r["plan"])
    diff = {"plans": len(plans), "instances": 0, "differences": 0, "examples": []}
    for name, (g, plan) in plans.items():
        spec = G[g]
        insts = INS.v_train(spec)
        for N in (5, 6, 7):
            sub = [i for i in insts if i["N"] == N]
            o1, s1, _ = CI.run_closed_loop(cirgen.emit([tuple(p) for p in plan], spec, N), spec, sub)
            o2, s2, _ = CI.run_closed_loop(emit_dsl([(a, by_id[spec_id_for(a, v)]) for a, v in plan], spec, N), spec, sub)
            diff["instances"] += len(sub)
            dd = sum(1 for a_, b_, c_, d_ in zip(o1, o2, s1, s2) if a_ != b_ or c_ != d_)
            diff["differences"] += dd
            if dd and len(diff["examples"]) < 5:
                diff["examples"].append(name)
    out["2_controller"] = diff
    print("2 controller", diff, flush=True)

    # 3 truth
    inst = [(k, a) for sp in specs for k, a in dsl.instances(sp)]
    achs = [(k, a, dsl.make_select(by_id[k.split("|")[0]])) for k, a in inst]
    tr, tcpu = truth.tables(achs)
    t7 = json.loads((EXP / "lib" / "t7_tables.json").read_text())
    g2 = json.loads((EXP / "lib" / "contract_table.json").read_text())
    inv = {v_: k_ for k_, v_ in LIBMAP.items()}
    dm = pm = 0
    for k, row in tr.items():
        lk = inv[k]
        for x, e in row["damage"].items():
            if {str(n): v_ for n, v_ in e["max_by_N"].items()} != {str(n): v_ for n, v_ in t7["damage"][lk]["entries"][x]["max_by_N"].items()}:
                dm += 1
        for gk, e in row["preserves"].items():
            has7 = (not g2["preserves"][lk][gk]["ok"]) or (t7["preserves"][lk][gk]["cex_N67"] is not None)
            pm += (e["cex"] is not None) != has7
    out["3_truth"] = {"damage_mismatches": dm, "preservation_mismatches": pm,
                      "applicability_cex": [k for k, r in tr.items() if r["applicability_cex"]], "cpu_s": tcpu}
    print("3 truth", out["3_truth"], flush=True)

    # 4 A tables
    A = a_tables(specs, inst, tr)
    raw = {k: r["entries"] for k, r in A["damage"].items()}
    tz = json.loads((EXP / "lib" / "tz_table.json").read_text())["table"]
    tzp2 = json.loads((EXP / "lib" / "tzp2_table.json").read_text())["table"]
    num = lambda b: float("inf") if b in (None, "inf") else b
    looser = tighter = unsound = 0
    for k, row in raw.items():
        lk = inv[k]
        for x, e in row.items():
            a_, z_ = num(e["bound"]), num(tz[lk]["entries"][x]["bound"])
            m7 = max((v_ for v_ in tr[k]["damage"][x]["max_by_N"].values() if v_ is not None), default=None)
            looser += a_ > z_
            tighter += a_ < z_
            if m7 is not None and a_ < m7:
                unsound += 1
    lost = gained = bad = 0
    for k, row in A["preserves"].items():
        lk = inv[k]
        for gk, e in row.items():
            lost += tzp2[lk][gk]["proved"] and not e["ok"]
            gained += e["ok"] and not tzp2[lk][gk]["proved"]
            bad += e["ok"] and tr[k]["preserves"][gk]["cex"] is not None
    out["4_A_tables"] = {"damage_looser_than_TZ": looser, "damage_tighter_than_TZ": tighter, "damage_below_truth": unsound,
                         "preservation_lost_vs_TZP2": lost, "preservation_gained_vs_TZP2": gained,
                         "preservation_proved_with_cex": bad, "progress_ok": sum(p["ok"] for p in A["progress"].values())}
    print("4 A tables", out["4_A_tables"], flush=True)

    # 5 constructors
    tzset = {g for g, r in cr["A-P'"]["TZ"].items() if r["status"] == "CONSTRUCTED"}
    apset = {g for g, r in r5["A-P"].items() if r["status"] == "CONSTRUCTED"}
    b1 = {g for g, s in G.items() if C.construct_app(s, specs, A, "TZ")["status"] == "CONSTRUCTED"}
    b2 = {g for g, s in G.items() if C.construct_ap(s, specs, A, "TZ")["status"] == "CONSTRUCTED"}
    out["5_constructors"] = {"A-P'": len(b1), "A-P'_same_as_TZ": b1 == tzset, "A-P": len(b2), "A-P_same_as_TZP2": b2 == apset,
                             "A-P'_extra": sorted(b1 - tzset), "A-P'_missing": sorted(tzset - b1),
                             "A-P_extra": sorted(b2 - apset), "A-P_missing": sorted(apset - b2)}
    print("5 constructors", out["5_constructors"], flush=True)

    # 6 B
    data, stuck = b_dsl.collect(achs, 1000, (5,))
    rec = b_dsl.fit_all(achs, data)
    rules, sizes = b_dsl.learn(achs, data)
    sup, h1, scpu = b_dsl.simulate(rules, achs)
    dmg, prog = b_dsl.table(achs, rec, sup, rules, stuck)
    t7d = {k: t7["damage"][inv[k]] for k in dmg}
    tzd = {k: tz[inv[k]] for k in dmg}
    out["6_B"] = {"pairs": {k: v_["pairs"] for k, v_ in sizes.items()}, "H1_disagreements": sum(v_["disagree"] for v_ in h1.values()),
                  "stuck_observed": sum(stuck.values()), "progress_ok": sum(p_["ok"] for p_ in prog.values()),
                  "vs_T7": {x: compare(dmg, t7d)[x] for x in ("equal", "dangerous", "conservative")},
                  "agreement_with_TZ": compare(dmg, tzd)["agreement"], "simulate_cpu_s": scpu}
    print("6 B", out["6_B"], flush=True)
    out["cpu_s"] = round(time.process_time() - t0, 1)
    (HERE / "selfcheck.json").write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
