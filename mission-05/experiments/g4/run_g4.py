"""G4 runner: the G3 pipeline with A++ (r8/zpp.py) as A's tables, on a set of ACH-DSL specs (G4_DESIGN.md).
A (the G3 encoding) and A+ (r7/zplus.py) tables are also computed, for calibration comparisons only; constructions,
soundness and J1-net use A++.

  1  validation (dsl.validate); instances of the valid specs
  2  truth tables at N = 3..7 for the specs and for the library specs (truth.tables)
  3  A tables (a_dsl.a_tables) and their soundness / calibration against the truth
  4  constructions on the 98 DEV goals, evidence "TZ": A-P' and A-P with (a) the specs only, (b) library + specs;
     every constructed plan judged (J1-sym on V_train and V_unseen, J2 on all N = 6 instances); J1-net (network,
     lockstep, 200 V_train + 50 per unseen size) on up to 10 plans that use a spec achiever
  5  B (b_dsl), observations at N = 5 only, n in {1000, 200} eligible states per instance (moves and non-moves):
     version spaces, the H1 check, bound tables; bounds below an observed N <= 7 delta (a_dsl.observed_violations);
     agreement with A; A-P' with the B tables (evidence "BX", specs only), certificates re-checked under the A tables
  6  per-spec classification: inside / outside B's rule grammar

  python -I run_g3.py SPECS.json OUT.json [LABEL]
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(EXP / "lib"))
sys.path.insert(0, str(EXP / "judge"))
sys.path.insert(0, str(EXP / "pilots"))
sys.path.insert(0, str(EXP / "g3"))
sys.path.insert(0, str(EXP / "r7"))
sys.path.insert(0, str(EXP / "r8"))
sys.path.insert(0, str(HERE))
import a_dsl  # noqa: E402
import b_dsl  # noqa: E402
import compile_cir as CC  # noqa: E402
import construct as C  # noqa: E402
import dsl  # noqa: E402
import instances as INS  # noqa: E402
import net_loop as NL  # noqa: E402
import truth  # noqa: E402
import zplus  # noqa: E402
import zpp  # noqa: E402
from cir_dsl import emit_dsl  # noqa: E402
from run_pa3 import goals  # noqa: E402
from run_r4 import compare  # noqa: E402


def net_check(plan, spec, seed=5):
    rng = random.Random(seed)
    train, unseen = INS.v_train(spec), INS.v_unseen(spec)
    groups = {"train": rng.sample(train, min(200, len(train)))}
    for N, insts in unseen.items():
        groups[f"unseen_N{N}"] = rng.sample(insts, 50)
    out = {}
    for gname, insts in groups.items():
        byN = {}
        for i in insts:
            byN.setdefault(i["N"], []).append(i)
        mism = fails = n = 0
        for N, grp in byN.items():
            prog = emit_dsl(plan, spec, N)
            net, info = CC.compile_cir(prog)
            prog["D"] = info["D"]
            r = NL.run_net_lockstep(net, prog, spec, grp)
            mism += r["episodes_with_mismatch"]
            fails += sum(o != "SUCCESS" for o in r["outcomes"])
            n += len(grp)
        out[gname] = {"episodes": n, "mismatch_episodes": mism, "failures": fails}
    return out


def plan_key(gid, plan):
    return gid + "|" + json.dumps(plan)


def main():
    t0 = time.perf_counter()
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    label = sys.argv[3] if len(sys.argv) > 3 else src.name
    raw = json.loads(src.read_text())
    specs_in = raw["specs"] if isinstance(raw, dict) else raw
    out = {"label": f"G4 run: {label}", "source": str(src)}

    # 1 validation
    valid, invalid, seen = [], [], set()
    for sp in specs_in:
        prob = dsl.validate(sp)
        if not prob and sp["id"] in seen:
            prob = ["duplicate id"]
        if not prob and sp["id"].startswith("LIB-"):
            prob = ["reserved id prefix"]
        (invalid if prob else valid).append({"spec": sp, "problems": prob} if prob else sp)
        if not prob:
            seen.add(sp["id"])
    out["validation"] = {"given": len(specs_in), "valid": len(valid), "invalid": [{"id": x["spec"].get("id") if isinstance(x["spec"], dict) else None,
                                                                                  "problems": x["problems"]} for x in invalid]}
    lib = json.loads((EXP / "g3" / "specs_library.json").read_text())["specs"]
    by_id = {s["id"]: s for s in valid + lib}
    inst = [(k, a) for sp in valid for k, a in dsl.instances(sp)]
    linst = [(k, a) for sp in lib for k, a in dsl.instances(sp)]
    atom_of = dict(inst + linst)
    sel = lambda k: dsl.make_select(by_id[k.split("|")[0]])
    print("specs", len(valid), "valid,", len(invalid), "invalid;", len(inst), "instances", flush=True)

    # 2 truth
    tr, tcpu = truth.tables([(k, a, sel(k)) for k, a in inst + linst])
    out["truth_cpu_s"] = tcpu
    trs = {k: tr[k] for k, _ in inst}
    print("truth", round(tcpu, 1), "s", flush=True)

    # 3 A tables
    c0 = time.process_time()
    A = zpp.a_tables_pp(valid, inst, tr)
    AL = zpp.a_tables_pp(lib, linst, tr)
    out["A_cpu_s"] = time.process_time() - c0
    out["comparison"] = {}
    for cname, fn in (("A(G3)", a_dsl.a_tables), ("A+", zplus.a_tables_plus)):
        T = fn(valid, inst, tr)
        out["comparison"][cname] = {"soundness": a_dsl.soundness(T, trs, atom_of),
                                    "certified": sorted(k for k, p in T["progress"].items() if p["ok"])}
    out["truth_progress"] = a_dsl.truth_progress(trs, atom_of)
    out["A"] = {"soundness": a_dsl.soundness(A, trs, atom_of),
                "progress": A["progress"],
                "damage_status": {s: sum(e["status"] == s for r in A["damage"].values() for e in r["entries"].values())
                                  for s in ("PROVED", "INF", "UNKNOWN", "VACUOUS")},
                "preservation_proved": sum(e["ok"] for r in A["preserves"].values() for e in r.values())}
    print("A++", {k: (len(v) if isinstance(v, list) else v) for k, v in out["A"]["soundness"].items()},
          "| A(G3) certified", out["comparison"]["A(G3)"]["soundness"]["certified_among_truth_good"],
          "| A+ certified", out["comparison"]["A+"]["soundness"]["certified_among_truth_good"], flush=True)
    AA = {x: {**AL[x], **A[x]} for x in ("damage", "progress", "preserves")}

    # 4 constructions
    G = goals()
    cache = {}
    out["constructions"] = {}
    for setname, specset, table in (("specs", valid, A), ("library+specs", lib + valid, AA)):
        for route, fn in (("A-P'", C.construct_app), ("A-P", C.construct_ap)):
            res = {}
            for gid, spec in G.items():
                c1 = time.process_time()
                r = fn(spec, specset, table, "TZ")
                row = {"status": r["status"], "cpu": time.process_time() - c1, "reasons": r.get("reasons", {})}
                if r["status"] == "CONSTRUCTED":
                    row["plan"] = r["plan"]
                    row["uses_spec"] = any(not i.startswith("LIB-") for _, i in r["plan"])
                    row["failures"] = C.judge_plan(spec, r["plan"], by_id, cache, plan_key(gid, r["plan"]))["failures"]
                res[gid] = row
            out["constructions"][f"{setname}/{route}"] = res
            print(setname, route, "constructed", sum(x["status"] == "CONSTRUCTED" for x in res.values()),
                  "using specs", sum(x.get("uses_spec", False) for x in res.values()),
                  "wrong", sum(x.get("failures", 0) > 0 for x in res.values()), flush=True)
    netplans = []
    for name, res in out["constructions"].items():
        for gid, r in res.items():
            if r.get("uses_spec") and len(netplans) < 10 and (gid, json.dumps(r["plan"])) not in [(g, json.dumps(p)) for g, p in netplans]:
                netplans.append((gid, r["plan"]))
    out["J1_net"] = {f"{g}|{json.dumps(p)}": net_check([(a, by_id[i]) for a, i in p], G[g]) for g, p in netplans}
    print("J1-net", sum(v["mismatch_episodes"] for r in out["J1_net"].values() for v in r.values()), "mismatching episodes", flush=True)

    # 5 B
    achs = [(k, a, sel(k)) for k, a in inst]
    tdmg = a_dsl.truth_damage(trs)
    out["B"] = {}
    for name, n in (("five-1000", 1000), ("five-200", 200)):
        c2 = time.process_time()
        data, stuck = b_dsl.collect(achs, n, (5,))
        rec = b_dsl.fit_all(achs, data)
        rules, sizes = b_dsl.learn(achs, data)
        sup, h1, scpu = b_dsl.simulate(rules, achs)
        dmg, prog = b_dsl.table(achs, rec, sup, rules, stuck)
        vsT = compare(dmg, tdmg)
        viol = a_dsl.observed_violations(dmg, trs)
        vsA = compare(dmg, A["damage"])
        res = {}
        for gid, spec in G.items():
            r = C.construct_app(spec, valid, {"damage": dmg, "progress": prog, "preserves": {}}, "BX")
            row = {"status": r["status"]}
            if r["status"] == "CONSTRUCTED":
                row["plan"] = r["plan"]
                row["accepted_under_A"] = C.check_certificate(spec, r["plan"], r["weights"], by_id, A, "TZ")
                row["failures"] = C.judge_plan(spec, r["plan"], by_id, cache, plan_key(gid, r["plan"]))["failures"]
            res[gid] = row
        out["B"][name] = {"version_space": sizes, "no_rules": sorted(k for k, v in rules.items() if v is None),
                          "observations": {k: len(v) for k, v in data.items()}, "stuck_observed": stuck,
                          "violations": viol, "progress": prog,
                          "H1": h1, "vs_truth": vsT, "vs_A": vsA, "progress_ok": sum(p["ok"] for p in prog.values()),
                          "laws": {k: {x: r["gram"].law for x, r in row.items()} for k, row in rec.items()},
                          "A-P'": res, "cpu_s": time.process_time() - c2, "simulate_cpu_s": scpu}
        print("B", name, "below observed", len(viol["below_observed"]), "no rules", len(out["B"][name]["no_rules"]),
              "H1 disagreements", sum(v["disagree"] for v in h1.values()),
              "A-P' constructed", sum(x["status"] == "CONSTRUCTED" for x in res.values()), flush=True)

    # 6 grammar classification
    out["in_B_grammar"] = {sp["id"]: dsl.in_b_grammar(sp) for sp in valid}
    out["judged"] = cache
    out["time_s"] = round(time.perf_counter() - t0, 1)
    dst.write_text(json.dumps(out, indent=1, default=str))
    print("done", out["time_s"], "s")


if __name__ == "__main__":
    main()
