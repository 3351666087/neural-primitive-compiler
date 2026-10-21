"""G0-A1..A5: APP-R on the 217 AUD instances, against the N <= 7 truth tables (AUDIT: reads truth for scoring only).

  1  truth at N = 3..7 for every AUD instance (truth.tables, in 8 parallel chunks); reproduction check against the
     Mission 05 archives (G3-HO / G4-HO truth_progress, round 8 truly_good)
  2  APP-R in S_T, S_D, S_A for every instance (no truth input)
  3  every truth-applicable instance: random search, S_T, N = 8..12, 5,000 eligible states each (seed 8);
     every truth-applicable instance NOT_PROVED in a scope: up to 20 relaxed models of that scope, each concretised
     (500 shuffles, seed 9); in S_A also a random search, N = 8..12, 2,000 eligible states each (seed 10)

  python -I run_app.py        # writes app.json, aud_truth.json
"""

from __future__ import annotations

import json
import random
import sys
import time
from multiprocessing import Pool
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import aud  # noqa: E402

EXP = aud.EXP
sys.path.insert(0, str(EXP / "g3"))
import a_dsl  # noqa: E402
import truth  # noqa: E402

import app_r  # noqa: E402
import concretize  # noqa: E402

D = aud.load()
BY = D["by_id"]


def spec_of(k):
    return BY[k.split("|")[0]]


def truth_chunk(chunk):
    tr, cpu = truth.tables([(k, a, aud.dsl.make_select(spec_of(k))) for k, a in chunk])
    return tr, cpu


def prove_one(x):
    k, a = x
    out = {}
    for sc in app_r.SCOPES:
        r = app_r.prove(spec_of(k), a, sc)
        out[sc] = {"status": r["status"], "query": r["query"], "time_s": r["time_s"], "model": r["model"]}
    return k, out


def search_one(x):
    k, a, scopes_np = x
    sp = spec_of(k)
    res = {"random_S_T": [], "concrete": {}, "random_S_A": []}
    rng = random.Random(f"8|{k}")
    for N in range(8, 13):
        c, got, draws = concretize.random_search(sp, a, N, 5000, rng, "S_T")
        res["random_S_T"].append({"N": N, "eligible_checked": got, "draws": draws, "cex": c})
    for sc in scopes_np:
        ms = app_r.models(sp, a, sc, k=20)
        found = []
        rng2 = random.Random(f"9|{k}|{sc}")
        for m in ms:
            c = concretize.from_model(sp, a, m["model"], rng2)
            if c:
                found.append({"query": m["query"], "model_N": m["model"]["N"], "cex": c})
        res["concrete"][sc] = {"models": len(ms), "model_N": sorted({m["model"]["N"] for m in ms}), "found": found}
        if sc == "S_A":
            rng3 = random.Random(f"10|{k}")
            for N in range(8, 13):
                c, got, draws = concretize.random_search(sp, a, N, 2000, rng3, "S_A")
                res["random_S_A"].append({"N": N, "eligible_checked": got, "draws": draws, "cex": c})
    return k, res


def main():
    t0 = time.perf_counter()
    allinst = [(k, a) for v in D["inst"].values() for k, a in v]
    chunks = [allinst[i::8] for i in range(8)]
    with Pool(8) as p:
        parts = p.map(truth_chunk, chunks)
    tr = {k: v for t, _ in parts for k, v in t.items()}
    truth_cpu = sum(c for _, c in parts)
    atom_of = dict(allinst)
    tp = a_dsl.truth_progress(tr, atom_of)
    (HERE / "aud_truth.json").write_text(json.dumps({"truth": tr, "truth_progress": tp, "cpu_s": truth_cpu}, default=str))
    # reproduction check against the Mission 05 archives (G3 stores only applicability, as A.progress[k].applicability_N7)
    repro = {}
    old = json.loads((EXP / "g3" / "heldout_run.json").read_text())["A"]["progress"]
    repro["G3-HO"] = [k for k, _ in D["inst"]["G3-HO"] if old[k]["applicability_N7"] != tp[k]["applies"]]
    old = json.loads((EXP / "g4" / "heldout_run.json").read_text())["truth_progress"]
    repro["G4-HO"] = [k for k, _ in D["inst"]["G4-HO"] if old[k]["applies"] != tp[k]["applies"] or old[k]["good"] != tp[k]["good"]]
    r8 = json.loads((EXP / "r8" / "r8.json").read_text())
    for name in ("STRAT-DEV", "LIB", "G3-DEV"):
        good = set(r8["sets"][name]["truly_good"])
        repro[name] = [k for k, _ in D["inst"][name] if (k in good) != tp[k]["good"]]
    print("truth", round(truth_cpu, 1), "s CPU; reproduction mismatches", {n: len(v) for n, v in repro.items()}, flush=True)
    t1 = time.perf_counter()
    with Pool(8) as p:
        proofs = dict(p.map(prove_one, allinst, chunksize=1))
    prove_cpu = sum(r[sc]["time_s"] for r in proofs.values() for sc in app_r.SCOPES)
    print("APP-R", round(time.perf_counter() - t1, 1), "s wall,", round(prove_cpu, 1), "s summed", flush=True)
    jobs = []
    for k, a in allinst:
        if tr[k]["applicability_cex"] is None:
            jobs.append((k, a, [sc for sc in app_r.SCOPES if proofs[k][sc]["status"] != "PROVED"]))
    t2 = time.perf_counter()
    with Pool(8) as p:
        search = dict(p.map(search_one, jobs, chunksize=1))
    print("search", round(time.perf_counter() - t2, 1), "s wall over", len(jobs), "truth-applicable instances", flush=True)
    out = {"label": "G0-A1..A5 (Mission 06): APP-R vs N <= 7 truth on AUD",
           "sets": {n: [k for k, _ in v] for n, v in D["inst"].items()},
           "truth_applicable": {k: tr[k]["applicability_cex"] is None for k, _ in allinst},
           "truth_applicability_cex": {k: tr[k]["applicability_cex"] for k, _ in allinst},
           "reproduction_mismatches": repro, "truth_cpu_s": truth_cpu,
           "proofs": proofs, "prove_cpu_s": prove_cpu, "search": search,
           "time_s": round(time.perf_counter() - t0, 1)}
    (HERE / "app.json").write_text(json.dumps(out, indent=1, default=str))
    print("done", out["time_s"], "s")


if __name__ == "__main__":
    main()
