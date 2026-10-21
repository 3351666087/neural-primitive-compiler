"""Round 8 (amendment 8, DEV): A vs A+ vs A++ on STRAT-DEV, LIB and G3-DEV.

  1  sample 1,000 valid distinct specs per atom type (r7/rand_specs.sample, seed 11)
  2  stage 1: truth at N = 3..5 for every instance; "progresses" = always moves and some own measure always decreases
  3  stage 2: every instance passing stage 1, plus 50 failing ones (seed 11); truth at N = 3..7; the STRAT-DEV specs are
     those with an instance in stage 2 (checkpoint after stage 1: strat_stage1.json)
  4  tables A (g3/a_dsl), A+ (r7/zplus), A++ (zpp) on STRAT-DEV stage-2 instances, LIB and G3-DEV; soundness and
     calibration; A+ vs A++ entry by entry
  5  STRAT-DEV specs only: A-P' and A-P with each table (evidence "TZ"); every constructed plan judged
     (J1-sym on V_train and V_unseen, J2 on all N = 6 instances)

  python -I run_r8.py      # writes r8.json
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
sys.path.insert(0, str(HERE))
import a_dsl  # noqa: E402
import construct as C  # noqa: E402
import dsl  # noqa: E402
import truth  # noqa: E402
import zplus  # noqa: E402
import zpp  # noqa: E402
from rand_specs import sample  # noqa: E402
from run_pa3 import goals  # noqa: E402

INF = float("inf")
STAGE1 = HERE / "strat_stage1.json"


def num(b):
    return INF if b in (None, "inf") else b


def draw():
    rng = random.Random(11)
    out, seen = [], set()
    for t in ("ORDER", "ZONE", "GROUP"):
        n = 0
        while n < 1000:
            sp = sample(rng, t)
            key = json.dumps(sp, sort_keys=True)
            if key in seen:
                continue
            sp = {"id": f"S-{t[:3]}-{n:04d}", **sp}
            if dsl.validate(sp):
                continue
            seen.add(key)
            out.append(sp)
            n += 1
    return out


def main():
    t0 = time.perf_counter()
    if STAGE1.exists():
        st1 = json.loads(STAGE1.read_text())
        pool = st1["pool"]
        print("stage 1 loaded from checkpoint", flush=True)
    else:
        pool = draw()
        inst = [(k, a) for s in pool for k, a in dsl.instances(s)]
        by = {s["id"]: s for s in pool}
        tr5, c5 = truth.tables([(k, a, dsl.make_select(by[k.split("|")[0]])) for k, a in inst], Ns=(3, 4, 5))
        tp5 = a_dsl.truth_progress(tr5, dict(inst))
        passed = sorted(k for k, v in tp5.items() if v["good"])
        failed = sorted(k for k, v in tp5.items() if not v["good"])
        extra = sorted(random.Random(11).sample(failed, min(50, len(failed))))
        st1 = {"pool": pool, "instances": len(inst), "passed": passed, "failed_sample": extra, "cpu_s": c5}
        STAGE1.write_text(json.dumps(st1, default=str))
        print("stage 1:", len(inst), "instances,", len(passed), "pass at N<=5;", round(c5, 1), "s", flush=True)
    by = {s["id"]: s for s in pool}
    chosen = set(st1["passed"]) | set(st1["failed_sample"])
    strat_specs = [s for s in pool if any(k in chosen for k, _ in dsl.instances(s))]
    sets = {"STRAT-DEV": strat_specs,
            "LIB": json.loads((EXP / "g3" / "specs_library.json").read_text())["specs"],
            "G3-DEV": json.loads((EXP / "g3" / "specs_dev.json").read_text())["specs"]}
    for ss in sets.values():
        for s in ss:
            by[s["id"]] = s
    inst = {"STRAT-DEV": [(k, a) for s in strat_specs for k, a in dsl.instances(s) if k in chosen],
            "LIB": [(k, a) for s in sets["LIB"] for k, a in dsl.instances(s)],
            "G3-DEV": [(k, a) for s in sets["G3-DEV"] for k, a in dsl.instances(s)]}
    allinst = [x for v in inst.values() for x in v]
    atom_of = dict(allinst)
    tr, tcpu = truth.tables([(k, a, dsl.make_select(by[k.split("|")[0]])) for k, a in allinst])
    print("stage 2 truth:", len(allinst), "instances,", round(tcpu, 1), "s", flush=True)
    out = {"label": "round 8 (amendment 8, DEV): A vs A+ vs A++", "stage1": {k: v for k, v in st1.items() if k != "pool"},
           "strat_specs": [s["id"] for s in strat_specs], "truth_cpu_s": tcpu, "sets": {}}
    tables = {}
    for name, ss in sets.items():
        trs = {k: tr[k] for k, _ in inst[name]}
        row = {"instances": len(inst[name])}
        tabs = {}
        for tname, fn in (("A", a_dsl.a_tables), ("A+", zplus.a_tables_plus), ("A++", zpp.a_tables_pp)):
            c0 = time.process_time()
            tabs[tname] = fn(ss, inst[name], tr)
            row[f"{tname}_z3_cpu_s"] = time.process_time() - c0
            row[f"{tname}_soundness"] = a_dsl.soundness(tabs[tname], trs, atom_of)
        tables[name] = tabs
        A, AP, APP = tabs["A"], tabs["A+"], tabs["A++"]
        looser, tighter = [], []
        for k, r in AP["damage"].items():
            for x, e in r["entries"].items():
                b1, b2 = num(e["bound"]), num(APP["damage"][k]["entries"][x]["bound"])
                if b2 > b1:
                    looser.append(f"{k} / {x}")
                elif b2 < b1:
                    tighter.append(f"{k} / {x}")
        row["App_looser_than_Ap"] = looser
        row["App_tighter_than_Ap"] = len(tighter)
        row["lost_vs_Ap"] = [k for k in AP["progress"] if AP["progress"][k]["ok"] and not APP["progress"][k]["ok"]]
        if name == "LIB":
            row["App_vs_A_damage_differences"] = [f"{k} / {x}" for k, r in A["damage"].items() for x, e in r["entries"].items()
                                                  if num(e["bound"]) != num(APP["damage"][k]["entries"][x]["bound"])]
            row["App_vs_A_progress_same"] = all(A["progress"][k]["ok"] == APP["progress"][k]["ok"] for k in A["progress"])
        row["progress"] = {k: {t: tabs[t]["progress"][k]["ok"] for t in tabs} for k in A["progress"]}
        tp = a_dsl.truth_progress(trs, atom_of)
        row["truly_good"] = sorted(k for k, v in tp.items() if v["good"])
        out["sets"][name] = row
        cal = {t: row[f"{t}_soundness"]["certified_among_truth_good"] for t in tabs}
        print(name, len(inst[name]), "instances;", len(row["truly_good"]), "truly good; certified", cal,
              "| A++ below truth", len(row["A++_soundness"]["damage_below_truth"]),
              "false progress", len(row["A++_soundness"]["progress_certified_but_false"]), flush=True)
    G = goals()
    cache = {}
    out["constructions"] = {}
    for tname in ("A", "A+", "A++"):
        table = tables["STRAT-DEV"][tname]
        usable = [s for s in strat_specs if any(table["progress"].get(k, {}).get("ok") for k, _ in dsl.instances(s))]
        for route, fn in (("A-P'", C.construct_app), ("A-P", C.construct_ap)):
            res = {}
            for gid, spec in G.items():
                r = fn(spec, usable, table, "TZ")
                row = {"status": r["status"]}
                if r["status"] == "CONSTRUCTED":
                    row["plan"] = r["plan"]
                    row["failures"] = C.judge_plan(spec, r["plan"], by, cache, gid + "|" + json.dumps(r["plan"]))["failures"]
                res[gid] = row
            out["constructions"][f"{tname}/{route}"] = res
            print(tname, route, "usable specs", len(usable), "constructed", sum(x["status"] == "CONSTRUCTED" for x in res.values()),
                  "wrong", sum(x.get("failures", 0) > 0 for x in res.values()), flush=True)
    out["judged"] = cache
    out["time_s"] = round(time.perf_counter() - t0, 1)
    (HERE / "r8.json").write_text(json.dumps(out, indent=1, default=str))
    print("done", out["time_s"], "s")


if __name__ == "__main__":
    main()
