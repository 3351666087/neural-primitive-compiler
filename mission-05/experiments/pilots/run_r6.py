"""Round 6 (amendment 6, DEV): B obtains the achievers' support itself.

  1  variants disc-1000 (N = 5, 6, 7), five-1000, five-200, five-50 (N = 5): the round-4/5 draws (seed 11); B-GRAM
     fits (bgram.run_variant) and selection-rule version spaces (brule.learn_rules)
  2  simulation of every version space on all states N = 3..7 (one run per distinct version space); H1 check against
     the true selection on eligible N = 6, 7 states; when each combination first appeared
  3  bound tables: B-RULE (observed + simulated support) for all variants; B-SYM (S-fact + mirror) for disc-1000 and
     five-1000; each against T7 and TZ; mirror consistency of the B-GRAM laws
  4  A-P' (L-tmpl, evidence "BX") with the B-RULE tables; certificates re-checked under TZ; new plans judged

  python -I mission-05/experiments/pilots/run_r6.py      # writes r6.json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
LIB = EXP / "lib"
sys.path.insert(0, str(EXP / "judge"))
sys.path.insert(0, str(LIB))
sys.path.insert(0, str(HERE))
import ap2  # noqa: E402
import bgram  # noqa: E402
import brule  # noqa: E402
from libval import achiever_instances  # noqa: E402
from run_cr import plan_key  # noqa: E402
from run_pa3 import goals, judge_plan  # noqa: E402
from run_r4 import compare  # noqa: E402
from z3_damage import own_measure_key  # noqa: E402

CAP = 64


def table_from(rec, supfn):
    dmg, prog = {}, {}
    for akey, row in rec.items():
        ent = {}
        for k, r in row.items():
            P, T = supfn(akey, k)
            b, why = bgram.derive_gram(r["gram"], P, T)
            ent[k] = {"law": r["gram"].law, "bound": b, "reason": why, "evidence": "BX" if b not in (None, "inf") else None}
        dmg[akey] = {"entries": ent}
        mk = ent[own_measure_key(akey)]
        ok = mk["bound"] not in (None, "inf") and mk["bound"] <= -1
        prog[akey] = {"ok": ok, "evidence": "BX" if ok else None}
    return dmg, prog


def summary(dmg, t7, tz):
    reasons = {}
    for row in dmg.values():
        for e in row["entries"].values():
            reasons[e["reason"]] = reasons.get(e["reason"], 0) + 1
    return {"vs_T7": compare(dmg, t7["damage"]), "vs_TZ": compare(dmg, tz["table"]), "reasons": reasons}


def main():
    t0 = time.perf_counter()
    G = goals()
    t7 = json.loads((LIB / "t7_tables.json").read_text())
    tz = json.loads((LIB / "tz_table.json").read_text())
    cr = json.loads((HERE / "cr.json").read_text())
    r4 = json.loads((HERE / "r4.json").read_text())
    cache = r4["judged"]
    n_cached = len(cache)
    tzset = sorted(g for g, r in cr["A-P'"]["TZ"].items() if r["status"] == "CONSTRUCTED")
    ach = {k: a for k, a, _ in achiever_instances()}
    out = {"label": "round 6 (amendment 6, DEV)", "TZ_A-P'_constructed": tzset, "variants": {}}

    hold = bgram.holdout()
    variants = {"disc-1000": (1000, (5, 6, 7)), "five-1000": (1000, (5,)), "five-200": (200, (5,)), "five-50": (50, (5,))}
    recs, rules, sig = {}, {}, {}
    for name, (n, sizes) in variants.items():
        c0 = time.process_time()
        data = bgram.collect(n, sizes)
        rr, sizes_vs = {}, {}
        for akey, a in ach.items():
            fd, fs, nd, ns = brule.learn_rules(a, data[akey])
            sizes_vs[akey] = {"d": nd, "s": ns, "pairs": nd * ns, "d_families": [list(f) for f in fd],
                              "s_families": [list(f) for f in fs]}
            rr[akey] = (fd, fs) if fd and fs and nd * ns <= CAP else None
        learn_cpu = time.process_time() - c0
        rec, diag = bgram.run_variant(n, sizes, hold)
        recs[name], rules[name] = rec, rr
        sig[name] = json.dumps({k: v for k, v in sorted(rr.items())}, default=str)
        out["variants"][name] = {"version_spaces": sizes_vs, "rule_learning_cpu_s": learn_cpu,
                                 "no_rules": sorted(k for k, v in rr.items() if v is None), "gram_diag": diag}
        print(name, "version-space pairs", {k: v["pairs"] for k, v in sizes_vs.items()}, "cpu", round(learn_cpu, 1), flush=True)

    sims = {}
    for name in variants:
        if sig[name] in sims:
            out["variants"][name]["simulation"] = {"shared_with": sims[sig[name]][0]}
            continue
        sup, new_at, h1, cpu = brule.simulate(rules[name])
        sims[sig[name]] = (name, sup, new_at, h1, cpu)
        late = sorted(f"{a} / {k}" for a, row in new_at.items() for k, d in row.items() if any(v == 7 for v in d.values()))
        out["variants"][name]["simulation"] = {"cpu_s": cpu, "H1": h1, "entries_with_new_combination_at_N7": late}
        print(name, "simulated", round(cpu, 1), "s; H1 disagreements", sum(v["disagree"] for v in h1.values()),
              "; new at N=7", len(late), flush=True)

    tabs = {}
    for name in variants:
        _, sup, _, _, _ = sims[sig[name]]
        rec = recs[name]
        fn = lambda akey, k, rec=rec, sup=sup: (rec[akey][k]["rows_obs"][0] | sup[akey][k][0],
                                                rec[akey][k]["rows_obs"][1] | sup[akey][k][1])
        dmg, prog = table_from(rec, fn)
        tabs[(name, "rule")] = (dmg, prog)
        out["variants"][name]["B-RULE"] = summary(dmg, t7, tz)
        if name in ("disc-1000", "five-1000"):
            fact = {a: {k: r["rows_fact"] for k, r in row.items()} for a, row in rec.items()}
            dmg2, prog2 = table_from(rec, lambda akey, k, fact=fact: brule.s_sym(akey, k, fact))
            tabs[(name, "sym")] = (dmg2, prog2)
            out["variants"][name]["B-SYM"] = summary(dmg2, t7, tz)
            out["variants"][name]["B-FACT_reference"] = summary(
                table_from(rec, lambda akey, k, fact=fact: fact[akey][k])[0], t7, tz)
            mism = []
            for akey, m in brule.MIRROR_ACH.items():
                for k, r in rec[akey].items():
                    mk = brule.mirror_key(k)
                    g, g2 = r["gram"], rec[m][mk]["gram"]
                    for p in r["rows_obs"][0]:
                        x, y = g.value(bgram.e_func(p)), g2.value(bgram.e_func(brule.mirror_pair(p)))
                        if x is not None and y is not None and x != y:
                            mism.append(f"{akey} / {k} {p}")
                    for t in r["rows_obs"][1]:
                        x, y = g.value(bgram.b_func(t)), g2.value(bgram.b_func(brule.mirror_triple(t)))
                        if g.law != "t" and x is not None and y is not None and x != y:
                            mism.append(f"{akey} / {k} {t}")
            out["variants"][name]["mirror_law_mismatches"] = {"count": len(mism), "examples": mism[:10]}
        v = out["variants"][name]
        print(name, "B-RULE dangerous vs T7", v["B-RULE"]["vs_T7"]["dangerous"], "agreement TZ",
              round(v["B-RULE"]["vs_TZ"]["agreement"], 3),
              *(["B-SYM dangerous vs T7", v["B-SYM"]["vs_T7"]["dangerous"]] if "B-SYM" in v else []), flush=True)

    out["A-P'"] = {}
    for name in variants:
        dmg, prog = tabs[(name, "rule")]
        res = {}
        for gid, spec in G.items():
            c0 = time.process_time()
            r = ap2.construct(spec, "tmpl", dmg, prog, evidence="BX")
            row = {"status": r["status"], "cpu": time.process_time() - c0}
            if r["status"] == "CONSTRUCTED":
                plan = [tuple(x) for x in r["plan"]]
                row.update(plan=plan, weights=r["weights"])
                row["accepted_under_TZ"] = ap2.check_certificate(spec, [p[1] for p in r["plan"]], r["weights"], "tmpl",
                                                                 tz["table"], tz["progress"], "TZ")["accepted"]
                row["failures"] = judge_plan(spec, plan, cache, plan_key(gid, plan))["failures"]
            res[gid] = row
        out["A-P'"][name] = res
        print("A-P'", name, "constructed", sum(x["status"] == "CONSTRUCTED" for x in res.values()),
              "wrong", sum(x.get("failures", 0) > 0 for x in res.values()),
              "rejected under TZ", sum(x["status"] == "CONSTRUCTED" and not x["accepted_under_TZ"] for x in res.values()),
              flush=True)
    out["newly_judged_plans"] = len(cache) - n_cached
    out["judged"] = cache
    out["time_s"] = round(time.perf_counter() - t0, 1)
    (HERE / "r6.json").write_text(json.dumps(out, indent=1, default=str))
    print("done", out["time_s"], "s; newly judged plans", out["newly_judged_plans"])


if __name__ == "__main__":
    main()
