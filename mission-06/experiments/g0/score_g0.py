"""Score Gate 0 against the locked predictions (EXPERIMENT_PRE_REGISTRATION.md, section G0.4 and amendment G0-1).
Written before the official runs. G0-F1 is scored by hand in claims_audit.md.

  python -I score_g0.py        # reads trust_flow / app / oracle_free / compile_run / compile_fuzz / stress / fidelity
                               # .json; writes g0_scores.json
"""

from __future__ import annotations

import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONSTRUCTOR_FILES = ("g3/b_dsl.py", "g3/construct.py", "g3/cir_dsl.py", "lib/compile_cir.py", "lib/cirgen.py",
                     "lib/ap.py", "lib/ap2.py", "lib/bdisc.py", "lib/bexch.py", "lib/bgram.py", "lib/brule.py")
TABLE_BUILDERS = {("g3/a_dsl.py", "a_tables"), ("r7/zplus.py", "a_tables_plus"), ("r8/zpp.py", "a_tables_pp")}


def V(ok):
    return "HOLDS" if ok else "FALSIFIED"


def load(name):
    p = HERE / name
    return json.loads(p.read_text()) if p.exists() else None


def main():
    S = {}
    # ---------------------------------------------------------------- T1
    tf = load("trust_flow.json")
    if tf:
        readers = [tuple(x) for x in tf["static"]["truth_readers"]]
        on_path = [x for x in readers if any(x[0].endswith(f) for f in CONSTRUCTOR_FILES)]
        builders = [x for x in readers if any(x[0].endswith(f) and x[1] == fn for f, fn in TABLE_BUILDERS)]
        builder_fields = sorted({x[2] for x in builders})
        dyn = tf["dynamic"]
        dyn_fields = sorted({p.split(" / ")[1] for k, v in dyn.items() if k != "constructors_with_judge_poisoned" for p in v
                             if len(p.split(" / ")) > 1})
        ok = (not on_path and set(builder_fields) <= {"applicability_cex", "preserves", "iterate"}
              and set(dyn_fields) <= {"applicability_cex", "preserves"}
              and not dyn["constructors_with_judge_poisoned"]["judge_calls"] and not tf["mission06_isolation"]["violations"])
        S["G0-T1"] = {"verdict": V(ok), "constructor_path_readers": on_path, "table_builder_fields": builder_fields,
                      "dynamic_fields": dyn_fields, "judge_calls": dyn["constructors_with_judge_poisoned"]["judge_calls"],
                      "mission06_isolation_violations": tf["mission06_isolation"]["violations"]}
    # ---------------------------------------------------------------- A1..A5
    ap = load("app.json")
    if ap:
        app = ap["truth_applicable"]
        P = ap["proofs"]
        good = sorted(k for k, v in app.items() if v)
        false_proof = sorted(k for k in P if not app[k] and any(P[k][sc]["status"] == "PROVED" for sc in P[k]))
        found_in_proved = sorted(k for k, r in ap["search"].items()
                                 if P[k]["S_T"]["status"] == "PROVED" and any(x["cex"] for x in r["random_S_T"]))
        proved_T = sorted(k for k in good if P[k]["S_T"]["status"] == "PROVED")
        sample20 = sorted(random.Random(20).sample(proved_T, min(20, len(proved_T))))
        S["G0-A1"] = {"verdict": V(not false_proof and not found_in_proved), "proved_with_truth_cex": false_proof,
                      "cex_found_in_S_T_proved": found_in_proved, "locked_sample_20": sample20,
                      "locked_sample_cex": [k for k in sample20 if k in found_in_proved]}
        cov = {sc: sum(P[k][sc]["status"] == "PROVED" for k in good) for sc in ("S_T", "S_D", "S_A")}
        status = {sc: {s: sum(P[k][sc]["status"] == s for k in good) for s in ("PROVED", "NOT_PROVED", "UNKNOWN")}
                  for sc in ("S_T", "S_D", "S_A")}
        S["G0-A2"] = {"verdict": V(cov["S_D"] >= 0.90 * len(good)), "truth_applicable": len(good), "proved": cov,
                      "rate_S_D": cov["S_D"] / len(good) if good else None, "status_among_truth_applicable": status,
                      "not_proved_S_D": sorted(k for k in good if P[k]["S_D"]["status"] != "PROVED")}
        in_T, out_T = {}, {}
        for k, r in ap["search"].items():
            cands = [x["cex"] for x in r["random_S_T"] if x["cex"]]
            cands += [f["cex"] for sc in r["concrete"] for f in r["concrete"][sc]["found"]]
            cands += [x["cex"] for x in r.get("random_S_A", []) if x["cex"]]
            for c in cands:
                (in_T if c["H"] <= 2 else out_T).setdefault(k, []).append({x: c[x] for x in ("N", "K", "H", "fixed")})
        S["G0-A3"] = {"verdict": V(not in_T), "instances_with_S_T_cex": {k: v[:3] for k, v in in_T.items()},
                      "in_S_D": sorted(k for k, v in in_T.items() if any(c["K"] <= 7 for c in v))}
        S["G0-A4"] = {"verdict": V(not out_T), "instances_with_cex_only_outside_S_T":
                      {k: v[:3] for k, v in out_T.items() if k not in in_T}}
        lib = ap["sets"]["LIB"]
        S["G0-A5"] = {"verdict": V(all(P[k]["S_A"]["status"] == "PROVED" for k in lib)),
                      "note": "not blind: LIB was used in a development smoke test before the code commit (amendment G0-1)",
                      "S_A": {k: P[k]["S_A"]["status"] for k in lib}}
        S["G0-A_cost"] = {"truth_cpu_s": ap["truth_cpu_s"], "app_r_cpu_s": ap["prove_cpu_s"], "run_s": ap["time_s"],
                          "reproduction_mismatches": ap["reproduction_mismatches"]}
    # ---------------------------------------------------------------- C1, C2
    of = load("oracle_free.json")
    if of:
        cnt = {}
        fail = {}
        for key, res in of["constructions"].items():
            name, v, route = key.split("/", 2)
            cnt[v] = cnt.get(v, 0) + sum(x["status"] == "CONSTRUCTED" for x in res.values())
            fail[v] = fail.get(v, 0) + sum(x.get("failures", 0) > 0 for x in res.values())
        S["G0-C1"] = {"verdict": V(cnt["A++r"] >= 0.95 * cnt["A++"] and fail["A++r"] == 0), "constructed": cnt,
                      "failing": fail, "per_set_route": {k: sum(x["status"] == "CONSTRUCTED" for x in r.values())
                                                          for k, r in of["constructions"].items()},
                      "same_z3_entries": {n: s["same_z3_entries"] for n, s in of["sets"].items()}}
        S["G0-C2"] = {"verdict": V(fail["A++0"] >= 1), "failing_A++0": fail["A++0"],
                      "failing_by_set_route": {k: sorted(g for g, x in r.items() if x.get("failures", 0) > 0)
                                               for k, r in of["constructions"].items() if "/A++0/" in k}}
    # ---------------------------------------------------------------- K1, K2
    cr = load("compile_run.json")
    if cr:
        lem_ok = all(r["status"] == "PROVED" and r["hypotheses_satisfiable"] for r in cr["lemmas"])
        S["G0-K1"] = {"verdict": V(lem_ok and cr["networks_with_problems"] == 0), "lemmas": {r["lemma"]: r["status"] for r in cr["lemmas"]},
                      "plans": cr["plans"], "networks": cr["networks"], "networks_with_problems": cr["networks_with_problems"]}
    cf = load("compile_fuzz.json")
    if cf:
        c = cf["class_C"]
        S["G0-K2"] = {"verdict": V(c["mismatch_steps"] == 0 and c["ref_mismatch_steps"] == 0 and c["inside_C_K_compile_errors"] == 0
                                   and c["premise_failures"] == 0 and c["outside_C_K_compiled"] == 0),
                      "class_C": c, "outside_C": {k: {x: v[x] for x in v if x != "errors"} for k, v in cf["outside_C"].items()}}
    # ---------------------------------------------------------------- S1, S2
    st = load("stress.json")
    if st:
        a = st["aggregate"]
        S["G0-S1"] = {"verdict": V(a["S1_N20"]["failures"] == 0), **a["S1_N20"]}
        S["G0-S2"] = {"verdict": "EXPLORATORY", "N9": a.get("S2_N9"), "N12": a.get("S2_N12")}
    # ---------------------------------------------------------------- M1
    fd = load("fidelity.json")
    if fd:
        S["G0-M1"] = {"verdict": V(all(v["disagreements"] == 0 for v in fd["total"].values())), "total": fd["total"]}
    (HERE / "g0_scores.json").write_text(json.dumps(S, indent=1, default=str))
    print(json.dumps({k: v["verdict"] for k, v in S.items() if "verdict" in v}, indent=1))


if __name__ == "__main__":
    main()
