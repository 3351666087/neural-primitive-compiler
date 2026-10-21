"""Round 7 (amendment 7, DEV): A (G3 encoding) vs A+ (R1 + R2) on LIB, G3-DEV and RAND-DEV.

  1  truth tables at N = 3..7 for every instance of the three sets (g3/truth.py)
  2  per set: A tables (g3/a_dsl.a_tables) and A+ tables (zplus.a_tables_plus), with Z3 time; soundness and
     calibration of each against the truth (a_dsl.soundness); A vs A+ entry by entry
  3  RAND-DEV specs only: A-P' and A-P with A and with A+ (evidence "TZ"); every constructed plan judged
     (J1-sym on V_train and V_unseen, J2 on all N = 6 instances)

  python -I run_r7.py      # writes r7.json
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
sys.path.insert(0, str(EXP / "g3"))
sys.path.insert(0, str(HERE))
import a_dsl  # noqa: E402
import construct as C  # noqa: E402
import dsl  # noqa: E402
import truth  # noqa: E402
import zplus  # noqa: E402
from run_pa3 import goals  # noqa: E402

INF = float("inf")


def num(b):
    return INF if b in (None, "inf") else b


def main():
    t0 = time.perf_counter()
    sets = {"LIB": json.loads((EXP / "g3" / "specs_library.json").read_text())["specs"],
            "G3-DEV": json.loads((EXP / "g3" / "specs_dev.json").read_text())["specs"],
            "RAND-DEV": json.loads((HERE / "specs_rand.json").read_text())["specs"]}
    by_id = {s["id"]: s for ss in sets.values() for s in ss}
    inst = {name: [(k, a) for s in ss for k, a in dsl.instances(s)] for name, ss in sets.items()}
    allinst = [x for v in inst.values() for x in v]
    atom_of = dict(allinst)
    tr, tcpu = truth.tables([(k, a, dsl.make_select(by_id[k.split("|")[0]])) for k, a in allinst])
    print("truth", round(tcpu, 1), "s for", len(allinst), "instances", flush=True)
    out = {"label": "round 7 (amendment 7, DEV): A vs A+", "truth_cpu_s": tcpu, "sets": {}}
    tables = {}
    for name, ss in sets.items():
        trs = {k: tr[k] for k, _ in inst[name]}
        c0 = time.process_time()
        A = a_dsl.a_tables(ss, inst[name], tr)
        ta = time.process_time() - c0
        c0 = time.process_time()
        AP = zplus.a_tables_plus(ss, inst[name], tr)
        tp = time.process_time() - c0
        tables[name] = (A, AP)
        looser, tighter, lost = [], [], []
        for k, row in A["damage"].items():
            for x, e in row["entries"].items():
                ea, ep = num(e["bound"]), num(AP["damage"][k]["entries"][x]["bound"])
                if ep > ea:
                    looser.append(f"{k} / {x}: A {e['bound']}, A+ {AP['damage'][k]['entries'][x]['bound']}")
                elif ep < ea:
                    tighter.append(f"{k} / {x}")
        for k, p in A["progress"].items():
            if p["ok"] and not AP["progress"][k]["ok"]:
                lost.append(k)
        sa, sp = a_dsl.soundness(A, trs, atom_of), a_dsl.soundness(AP, trs, atom_of)
        out["sets"][name] = {"instances": len(inst[name]), "A_z3_cpu_s": ta, "Aplus_z3_cpu_s": tp,
                             "A_soundness": sa, "Aplus_soundness": sp,
                             "Aplus_looser_than_A": looser, "Aplus_tighter_than_A": tighter,
                             "certified_by_A_not_Aplus": lost,
                             "progress": {k: {"A": A["progress"][k]["ok"], "A+": AP["progress"][k]["ok"],
                                              "A+_measure": AP["progress"][k]["measure"]} for k in A["progress"]}}
        print(name, "A certified", sa["certified_among_truth_good"], "/", sa["truth_good_instances"],
              "| A+", sp["certified_among_truth_good"], "/", sp["truth_good_instances"],
              "| A+ below truth", len(sp["damage_below_truth"]), "false progress", len(sp["progress_certified_but_false"]),
              "| tighter", len(tighter), "looser", len(looser), "| z3", round(ta, 1), round(tp, 1), flush=True)
    G = goals()
    cache = {}
    out["constructions"] = {}
    rs = sets["RAND-DEV"]
    for tname, idx in (("A", 0), ("A+", 1)):
        table = tables["RAND-DEV"][idx]
        for route, fn in (("A-P'", C.construct_app), ("A-P", C.construct_ap)):
            res = {}
            for gid, spec in G.items():
                r = fn(spec, rs, table, "TZ")
                row = {"status": r["status"]}
                if r["status"] == "CONSTRUCTED":
                    row["plan"] = r["plan"]
                    row["failures"] = C.judge_plan(spec, r["plan"], by_id, cache, gid + "|" + json.dumps(r["plan"]))["failures"]
                res[gid] = row
            out["constructions"][f"{tname}/{route}"] = res
            print(tname, route, "constructed", sum(x["status"] == "CONSTRUCTED" for x in res.values()),
                  "wrong", sum(x.get("failures", 0) > 0 for x in res.values()), flush=True)
    out["judged"] = cache
    out["time_s"] = round(time.perf_counter() - t0, 1)
    (HERE / "r7.json").write_text(json.dumps(out, indent=1, default=str))
    print("done", out["time_s"], "s")


if __name__ == "__main__":
    main()
