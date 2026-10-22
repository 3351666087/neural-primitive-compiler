"""Learner positive controls for amendment A3 (JUDGE SIDE harness). Uses g3_learner_control.teacher_memory.
  M1-phase0 : teacher data of the first 3,990 steps (alpha's phase 0 only); fit the shared learner; ground.
  M1-full   : teacher data of 12,000 steps (phases 0, 1, 0); fit; ground (shows the effect of alpha's phase switch).
  M2-given  : teacher data of 6,000 steps; the true stone counter is given; fit M2 only; ground.
  python3 -I g3_learner_control_run.py      # writes g3_learner_control.json"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "agents"))
import ground_eco as G  # noqa: E402
import g3_learner_control as LC  # noqa: E402
from eco_env import load_family  # noqa: E402
from fakes import ORACLE_ALPHA  # noqa: E402
from structures import Counter, Learner  # noqa: E402

SEEDS = list(range(150, 158))


def ground(descs, probes, classes):
    out = {}
    for d in descs:
        dep = [d] + [x for x in descs if x["struct_id"] == d["params"].get("q_struct")]
        g = G.ground(dep, probes, classes)
        out.update({f"{d['struct_id']}:{p}": {"class": g[p]["class"], "precision": round(g[p]["precision"], 3),
                                              "recall": round(g[p]["recall"], 3), "grounded": g[p]["grounded"]}
                    for p in d["predicates"] if p in g})
    return out


def main():
    fam = load_family(HERE / "family_alpha.json")
    probes, classes = G.make_probes(fam)
    res = {}
    for name, T in (("M1-phase0", 3990), ("M1-full", 12000)):
        res[name] = {}
        for seed in SEEDS:
            mem, w = LC.teacher_memory(fam, seed, T)
            lr = Learner()
            structs = {}
            for _ in range(3):
                for s in lr.fit(mem, structs, mem.t):
                    structs[s.sid] = s
            descs = [s.describe() for s in structs.values()]
            res[name][seed] = {"structures": [{k: d[k] for k in ("struct_id", "form", "params", "stats")} for d in descs],
                               "grounding": ground(descs, probes, classes)}
            print(name, seed, {k: v["grounded"] for k, v in res[name][seed]["grounding"].items()}, flush=True)
    res["M2-given"] = {}
    for seed in SEEDS:
        mem, w = LC.teacher_memory(fam, seed, 6000)
        lr = Learner()
        lr.next_sid = 100
        m1 = Counter(0, dict(ORACLE_ALPHA[0][1], delta=4), {}, [], 0)
        have = {0: m1}
        held = {("M1", 2)}
        found = []
        for _ in range(3):
            ev = [e for e in mem.events if e["t"] >= mem.t - lr.window]
            s = lr.fit_m2(mem, ev, held | {("M2", x.params["K"]) for x in found}, have, mem.t)
            if s is None:
                break
            found.append(s)
        descs = [m1.describe()] + [s.describe() for s in found]
        res["M2-given"][seed] = {"arms": sum(1 for e in w.events if e[1] == "arm"),
                                 "structures": [{k: d[k] for k in ("struct_id", "form", "params", "stats")} for d in descs[1:]],
                                 "grounding": {k: v for k, v in ground(descs, probes, classes).items() if not k.startswith("0:")}}
        print("M2-given", seed, res["M2-given"][seed]["arms"], {k: v["grounded"] for k, v in res["M2-given"][seed]["grounding"].items()}, flush=True)
    (HERE / "g3_learner_control.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
