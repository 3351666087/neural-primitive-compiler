"""Contract reliability round (amendment 3, DEV). Needs t7_tables.json (lib/libval3.py) and tz_table.json
(lib/z3_damage.py); written before either was run.

  1  A-P' (L-tmpl) on the 98 goals with T5 (no evidence rule: the round-2 reference), T7 and TZ (evidence rule)
  2  A-P (pairwise) with the G2 table (no evidence rule) and with the T7 tables (evidence rule)
  3  every constructed plan not judged before: J1-sym (V_train, V_unseen) and J2 (all N = 6 instances)
  4  C4: the 6 round-2 certificates that B-DISC refused (constructed with T5, not with disc-1000), re-checked with
     the same variants and weights under T7 and TZ
  5  table comparisons: T7 vs TZ (classes, maxima), T5 vs TZ on the round-2 witness entries (b1_witness.json),
     the round-2 learned tables (seed 11, n = 1000) vs TZ

  python -I mission-05/experiments/pilots/run_cr.py      # writes cr.json
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
LIB = EXP / "lib"
sys.path.insert(0, str(EXP / "judge"))
sys.path.insert(0, str(LIB))
sys.path.insert(0, str(HERE))
import ap  # noqa: E402
import ap2  # noqa: E402
import bdisc  # noqa: E402
from run_pa3 import goals, judge_plan  # noqa: E402

INF = float("inf")


def num(b):
    return INF if b in (None, "inf") else b


def plan_key(gid, plan):
    return gid + "|" + json.dumps([[list(a), v] for a, v in plan])


def compare(learned, ref):
    """As run_b1.compare, against an arbitrary reference table {achiever: {"entries": {k: {"bound"}}}}."""
    eq = dang = cons = 0
    ex = []
    for a, row in ref.items():
        for k, e in row["entries"].items():
            g, l = num(e["bound"]), num(learned[a]["entries"][k]["bound"])
            if g == l:
                eq += 1
            elif l < g:
                dang += 1
                ex.append(f"{a} / {k}: learned {l}, reference {g}")
            else:
                cons += 1
    tot = eq + dang + cons
    return {"entries": tot, "equal": eq, "dangerous": dang, "conservative": cons, "agreement": eq / tot,
            "dangerous_fraction": dang / tot, "dangerous_examples": ex[:20]}


def main():
    t0 = time.perf_counter()
    t5 = ap2.load_damage()
    g2 = ap.load_table()
    t7 = json.loads((LIB / "t7_tables.json").read_text())
    tz = json.loads((LIB / "tz_table.json").read_text())
    pa3 = json.loads((HERE / "pa3.json").read_text())
    b1 = json.loads((HERE / "b1.json").read_text())
    cache = pa3["judged"]
    n_cached = len(cache)
    G = goals()
    sources = {"T5": (t5, g2["progress"], None), "T7": (t7["damage"], t7["progress"], "T7"),
               "TZ": (tz["table"], tz["progress"], "TZ")}
    out = {"label": "contract reliability (amendment 3, DEV)", "A-P'": {}, "A-P": {}}
    for src, (dmg, prog, evid) in sources.items():
        res = {}
        for gid, spec in G.items():
            c0 = time.process_time()
            r = ap2.construct(spec, "tmpl", dmg, prog, evidence=evid)
            row = {"status": r["status"], "cpu": time.process_time() - c0, "reasons": r.get("reasons", {})}
            if r["status"] == "CONSTRUCTED":
                plan = [tuple(x) for x in r["plan"]]
                row.update(plan=plan, weights=r["weights"], used=r["used"])
                row["failures"] = judge_plan(spec, plan, cache, plan_key(gid, plan))["failures"]
            res[gid] = row
        out["A-P'"][src] = res
        print("A-P'", src, "constructed", sum(v["status"] == "CONSTRUCTED" for v in res.values()),
              "wrong", sum(v.get("failures", 0) > 0 for v in res.values()), round(time.perf_counter() - t0, 1), "s",
              flush=True)
    for src, (table, evid) in {"G2": (g2, None), "T7": ({"progress": t7["progress"], "preserves": t7["preserves"]}, "T7")}.items():
        res = {}
        for gid, spec in G.items():
            c0 = time.process_time()
            r = ap.construct(spec, table, evidence=evid)
            row = {"status": r["status"], "cpu": time.process_time() - c0, "reasons": r.get("reasons", {})}
            if r["status"] == "CONSTRUCTED":
                plan = [tuple(x) for x in r["plan"]]
                row["plan"] = plan
                row["failures"] = judge_plan(spec, plan, cache, plan_key(gid, plan))["failures"]
            res[gid] = row
        out["A-P"][src] = res
        print("A-P", src, "constructed", sum(v["status"] == "CONSTRUCTED" for v in res.values()),
              "wrong", sum(v.get("failures", 0) > 0 for v in res.values()), round(time.perf_counter() - t0, 1), "s",
              flush=True)
    out["newly_judged_plans"] = len(cache) - n_cached
    out["judged"] = {k: v for k, v in cache.items()}

    # C4: the 6 certificates B-DISC refused in round 2
    six = [g for g, r in pa3["goals"].items() if r["tmpl"]["status"] == "CONSTRUCTED"
           and b1["A"]["disc-1000"][g]["status"] != "CONSTRUCTED"]
    c4 = {}
    for g in six:
        r = pa3["goals"][g]["tmpl"]
        vs, w = [p[1] for p in r["plan"]], r["weights"]
        c4[g] = {"variants": vs, "weights": w}
        for src in ("T5", "T7", "TZ"):
            dmg, prog, evid = sources[src]
            c4[g][src] = ap2.check_certificate(G[g], vs, w, "tmpl", dmg, prog, evid)
    out["C4_certificates"] = c4

    # table comparisons
    cmp_ = {"entries": 0, "agree": 0, "T7_bounded_TZ_inf": [], "TZ_bounded_T7_inf": [], "T7_max_above_TZ": [],
            "TZ_looser_than_T7": 0, "tz_status": {}}
    for a, row in tz["table"].items():
        for k, e in row["entries"].items():
            e7 = t7["damage"][a]["entries"][k]
            c7 = "inf" if e7["bound"] in (None, "inf") else "bounded"
            cz = "bounded" if e["status"] == "PROVED" else "inf"
            cmp_["entries"] += 1
            cmp_["agree"] += c7 == cz
            cmp_["tz_status"][e["status"]] = cmp_["tz_status"].get(e["status"], 0) + 1
            if c7 == "bounded" and cz == "inf":
                cmp_["T7_bounded_TZ_inf"].append({"entry": f"{a} / {k}", "T7": e7["max_by_N"], "tz": e})
            if cz == "bounded" and c7 == "inf":
                cmp_["TZ_bounded_T7_inf"].append({"entry": f"{a} / {k}", "T7": e7["max_by_N"], "tz_bound": e["bound"]})
            if cz == "bounded":
                m7 = max(v for v in e7["max_by_N"].values() if v is not None)
                if m7 > e["bound"]:
                    cmp_["T7_max_above_TZ"].append({"entry": f"{a} / {k}", "T7": e7["max_by_N"], "tz_bound": e["bound"]})
                elif c7 == "bounded" and e["bound"] > num(e7["bound"]):
                    cmp_["TZ_looser_than_T7"] += 1
    cmp_["agreement"] = cmp_["agree"] / cmp_["entries"]
    out["T7_vs_TZ"] = cmp_
    wit = json.loads((HERE / "b1_witness.json").read_text())
    wrows = []
    for ek, v in wit.items():
        if not v["witness"]:
            continue
        a, k = ek.split(" / ")
        wrows.append({"entry": ek, "T5": t5[a]["entries"][k]["bound"], "T7": t7["damage"][a]["entries"][k]["bound"],
                      "TZ": tz["table"][a]["entries"][k]["bound"], "TZ_status": tz["table"][a]["entries"][k]["status"],
                      "TZ_above_T5": num(tz["table"][a]["entries"][k]["bound"]) > num(t5[a]["entries"][k]["bound"])})
    out["witness_entries"] = wrows
    learned = {}
    for mode in ("disc", "null"):
        tab, _ = bdisc.learn(1000, mode, seed=11)
        learned[mode] = {"vs_TZ": compare(tab, tz["table"]), "vs_T7": compare(tab, t7["damage"])}
    out["B_vs_TZ"] = learned
    out["T5_vs_TZ"] = compare(t5, tz["table"])
    out["T5_vs_T7"] = compare(t5, t7["damage"])
    out["costs"] = {"T7_cpu_s": t7["cpu_s"], "T7_wall_s": t7["time_s"], "TZ_z3_s": tz["time_s"],
                    "A-P'_median_cpu_s": {s: statistics.median(r["cpu"] for r in out["A-P'"][s].values()) for s in sources},
                    "A-P_median_cpu_s": {s: statistics.median(r["cpu"] for r in out["A-P"][s].values()) for s in out["A-P"]}}
    out["time_s"] = round(time.perf_counter() - t0, 1)
    (HERE / "cr.json").write_text(json.dumps(out, indent=1, default=str))
    print("done", out["time_s"], "s; newly judged plans", out["newly_judged_plans"])


if __name__ == "__main__":
    main()
