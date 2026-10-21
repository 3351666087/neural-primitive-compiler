"""G0-C1, G0-C2: A++ with the truth's applicability replaced (Mission 06).

Variants of A++'s progress evidence (damage bounds and pairwise preservation are A++'s Z3 derivations in every variant):
  A++   (tag TZ)   Mission 05 as run: decrease PROVED and applicability_cex is None in the N <= 7 truth (zpp.a_tables_pp)
  A++r  (tag TZR)  decrease PROVED and APP-R PROVED in S_D (app.json); reads no truth
  A++0  (tag TZ0)  decrease PROVED only; no applicability evidence
Per set (LIB, G3-DEV, STRAT-DEV, G3-HO, G4-HO; each set's own specs) and route (A-P', A-P): the 98 goals of run_pa3;
every constructed plan judged once (J1-sym on V_train and V_unseen, J2 on V_mc6; construct.judge_plan), 8 processes.
The tables of A++r and A++0 are built by tables_r below, which reads no truth table; the A++ row reads the truth
exactly as Mission 05 did and is the comparison baseline. G3-HO and G4-HO are spent sets: POST-HOC audit.

  python -I oracle_free.py        # needs app.json and aud_truth.json; writes oracle_free.json
"""

from __future__ import annotations

import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import aud  # noqa: E402

EXP = aud.EXP
for p in ("lib", "judge", "pilots", "g3", "r7", "r8"):
    sys.path.insert(0, str(EXP / p))
import construct as C  # noqa: E402
import dsl  # noqa: E402
import z3_dsl  # noqa: E402
import zpp  # noqa: E402
from libval import key as atom_key, patterns as atom_patterns  # noqa: E402
from potentials import patterns  # noqa: E402
from run_pa3 import goals  # noqa: E402

D = aud.load()
BY = D["by_id"]
G = goals()
TAGS = {"A++": "TZ", "A++r": "TZR", "A++0": "TZ0"}


def roles_of(atom):
    return ["A1", "A2", "X1", "X2"] if atom[0] == "ORDER" else ["A1", "X1", "X2"]


def tables_r(specs, inst, applicable):
    """A++'s Z3 tables with progress = decrease PROVED and applicable(key). CONSTRUCTOR SIDE: no truth input."""
    damage, prog_r, prog_0, preserves = {}, {}, {}, {}
    sp_of = {k: sp for sp in specs for k, _ in dsl.instances(sp)}
    for k, a in inst:
        sp = sp_of[k]
        b = {x: zpp.bound_pp(sp, a, x) for x in patterns(a[0])}
        damage[k] = {"entries": {x: {"bound": e["bound"], "evidence": "TZ" if e["status"] == "PROVED" else None,
                                     "status": e["status"]} for x, e in b.items()}}
        m = z3_dsl.progress(sp, a, b)
        prog_r[k] = {"ok": m is not None and applicable(k), "evidence": "TZR", "measure": m}
        prog_0[k] = {"ok": m is not None, "evidence": "TZ0", "measure": m}
        preserves[k] = {}
        for gp in atom_patterns(roles_of(a)):
            gk = atom_key(gp)
            if gk == atom_key(a):
                continue
            st = z3_dsl.prove(sp, a, gk)["status"]
            preserves[k][gk] = {"ok": st == "PROVED", "evidence": "TZ" if st == "PROVED" else None, "status": st}
    return damage, prog_r, prog_0, preserves


def retag(damage, preserves, tag):
    d = {k: {"entries": {x: {**e, "evidence": tag if e["evidence"] else None} for x, e in r["entries"].items()}}
         for k, r in damage.items()}
    p = {k: {g: {**e, "evidence": tag if e["evidence"] else None} for g, e in r.items()} for k, r in preserves.items()}
    return d, p


def judge(x):
    gid, plan = x
    r = C.judge_plan(G[gid], plan, BY, {}, "")
    return gid + "|" + json.dumps(plan), {"failures": r["failures"], "J1": {n: v["counts"] for n, v in r["J1_sym"].items()
                                                                                if isinstance(v, dict)},
                                          "J2": r["J2_mc6"]["counts"]}


def main():
    t0 = time.perf_counter()
    app = json.loads((HERE / "app.json").read_text())
    trd = json.loads((HERE / "aud_truth.json").read_text())["truth"]
    applicable = lambda k: app["proofs"][k]["S_D"]["status"] == "PROVED"
    out = {"label": "G0-C1/C2 (Mission 06): A++ vs A++r vs A++0", "sets": {}, "constructions": {}}
    plans = set()
    for name, specs in D["sets"].items():
        inst = D["inst"][name]
        c0 = time.process_time()
        dmg, pr, p0, pres = tables_r(specs, inst, applicable)
        cpu_r = time.process_time() - c0
        c1 = time.process_time()
        Tt = zpp.a_tables_pp(specs, inst, trd)
        cpu_t = time.process_time() - c1
        same = {"damage": all(dmg[k]["entries"][x]["bound"] == Tt["damage"][k]["entries"][x]["bound"] for k in dmg for x in dmg[k]["entries"]),
                "preserves": all(pres[k][g]["ok"] == Tt["preserves"][k][g]["ok"] for k in pres for g in pres[k])
                             and all(set(pres[k]) == set(Tt["preserves"][k]) for k in pres),
                "measure": all(pr[k]["measure"] == Tt["progress"][k]["measure"] for k in pr)}
        tabs = {"A++": Tt}
        for v, prog in (("A++r", pr), ("A++0", p0)):
            d2, p2 = retag(dmg, pres, TAGS[v])
            tabs[v] = {"damage": d2, "progress": prog, "preserves": p2}
        out["sets"][name] = {"instances": len(inst), "tables_r_cpu_s": cpu_r, "tables_truth_cpu_s": cpu_t,
                             "same_z3_entries": same,
                             "progress_ok": {v: sorted(k for k, p in t["progress"].items() if p["ok"]) for v, t in tabs.items()}}
        for v, T in tabs.items():
            for route, fn in (("A-P'", C.construct_app), ("A-P", C.construct_ap)):
                res = {}
                for gid, spec in G.items():
                    r = fn(spec, specs, T, TAGS[v])
                    res[gid] = {"status": r["status"], "plan": r["plan"], "reasons": r.get("reasons", {})}
                    if r["status"] == "CONSTRUCTED":
                        plans.add((gid, json.dumps(r["plan"])))
                out["constructions"][f"{name}/{v}/{route}"] = res
                print(name, v, route, "constructed", sum(x["status"] == "CONSTRUCTED" for x in res.values()), flush=True)
    t1 = time.perf_counter()
    with Pool(8) as p:
        judged = dict(p.map(judge, [(g, json.loads(pl)) for g, pl in sorted(plans)], chunksize=1))
    out["judged"] = judged
    for key, res in out["constructions"].items():
        for gid, r in res.items():
            if r["status"] == "CONSTRUCTED":
                r["failures"] = judged[gid + "|" + json.dumps(r["plan"])]["failures"]
    out["judge_wall_s"] = round(time.perf_counter() - t1, 1)
    out["time_s"] = round(time.perf_counter() - t0, 1)
    (HERE / "oracle_free.json").write_text(json.dumps(out, indent=1, default=str))
    for key, res in out["constructions"].items():
        print(key, "constructed", sum(x["status"] == "CONSTRUCTED" for x in res.values()),
              "failing", sum(x.get("failures", 0) > 0 for x in res.values()))
    print("plans judged", len(judged), "in", out["judge_wall_s"], "s; total", out["time_s"], "s")


if __name__ == "__main__":
    main()
