"""Judge self-tests (run before any constructor exists).

  1. exact feasibility (feasibility.feasible) == brute-force BFS on every instance with N <= 5, K <= 3 for 17 specs
  2. BatchEnv == scalar step on random instances and random action sequences
  3. NetBatch == npc.simulator.BatchSim on random networks (delays 1..3, random inputs)
  4. CIR interpreter on a hand-written register program
  5. J2 lemmas (Z3)

  python -I selftest.py            # writes selftest.json
"""

from __future__ import annotations

import itertools
import json
import random
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "src"))
import cir_interp as CI  # noqa: E402
import j2  # noqa: E402
from env import ACTIONS, BatchEnv, hazard_rule, step  # noqa: E402
from feasibility import bfs_feasible, feasible  # noqa: E402
from instances import DISTRACTOR, bindings, goal_colours  # noqa: E402
from net_loop import NetBatch  # noqa: E402
from npc.network import Network, Neuron, Synapse  # noqa: E402
from npc.simulator import BatchSim  # noqa: E402


def raw_instances(spec, N, Kmax):
    pal = goal_colours(spec) + [DISTRACTOR]
    for K in range(1, Kmax + 1):
        for pos in itertools.combinations(range(N), K):
            free = [p for p in range(N) if p not in pos]
            hz_sets = [()] if not hazard_rule(spec) else [h for r in range(3) for h in itertools.combinations(free, r)]
            for cols in itertools.product(pal, repeat=K):
                cells = [0] * N
                for p, c in zip(pos, cols):
                    cells[p] = c
                for hz in hz_sets:
                    for a in range(N):
                        for b in bindings(spec):
                            yield {"N": N, "cells": tuple(cells), "hazards": tuple(1 if p in hz else 0 for p in range(N)),
                                   "agent": a, "binding": b}


def test_feasibility(specs):
    res = {}
    for sid, spec in specs.items():
        n = agree = budget = 0
        dis = []
        for N in (3, 4, 5):
            for inst in raw_instances(spec, N, 3):
                b = bfs_feasible(spec, inst)
                if b is None:
                    budget += 1
                    continue
                n += 1
                if b == feasible(spec, inst):
                    agree += 1
                elif len(dis) < 3:
                    dis.append(inst)
        res[sid] = {"instances": n, "agree": agree, "bfs_budget": budget, "disagreements": dis}
        print("feasibility", sid, res[sid]["instances"], res[sid]["agree"], flush=True)
    return res


def test_env(specs, n=300, T=60):
    rng = random.Random(3)
    bad = 0
    for sid, spec in specs.items():
        from instances import random_instance
        insts = [random_instance(spec, rng.choice((5, 7, 9)), 5, rng) for _ in range(n)]
        for N in sorted({i["N"] for i in insts}):
            grp = [i for i in insts if i["N"] == N]
            env = BatchEnv(spec, grp)
            states = [(i["cells"], i["agent"], 0) for i in grp]
            alive = [True] * len(grp)
            for _ in range(T):
                choice = [rng.choice(ACTIONS[:4]) for _ in grp]
                acts = {a: np.array([c == a for c in choice]) for a in ACTIONS}
                env.act(acts)
                for k, inst in enumerate(grp):
                    if not alive[k]:
                        continue
                    s2, unsafe = step(spec, inst, states[k], choice[k])
                    if unsafe:
                        alive[k] = False
                        bad += env.outcome[k] != "UNSAFE"
                        continue
                    states[k] = s2
                    if env.done[k]:
                        alive[k] = False
                        bad += env.outcome[k] != "TIMEOUT"
                        continue
                    bad += (tuple(env.cells[k]) != s2[0]) or (env.agent[k] != s2[1]) or (env.hand[k] != s2[2])
    return {"mismatches": int(bad)}


def test_netbatch(trials=30):
    rng = random.Random(4)
    bad = 0
    for t in range(trials):
        ins = [f"x{i}" for i in range(rng.randint(1, 4))]
        names = [f"n{i}" for i in range(rng.randint(2, 8))]
        neurons = [Neuron(nm, threshold=rng.randint(1, 3), leak=rng.randint(0, 2), bias=rng.randint(-1, 1),
                          reset=0, vmin=-4, vmax=6) for nm in names]
        syn = [Synapse(rng.choice(ins + names), rng.choice(names), rng.choice((-2, -1, 1, 2)), rng.randint(1, 3))
               for _ in range(rng.randint(1, 15))]
        net = Network(f"r{t}", tuple(ins), tuple(neurons), tuple(syn), ((("o", names[0])),), max_delay=3)
        X = np.array([[[rng.randint(0, 1) for _ in range(12)] for _ in ins] for _ in range(5)])
        ref = BatchSim(net).run(X)
        sim = NetBatch(net, 5)
        for tt in range(12):
            now = sim.tick(X[:, :, tt])
            bad += int((now != ref[:, :, tt]).any())
    return {"trials": trials, "mismatching_ticks": bad}


def test_cir():
    """Register R latches 'ag_0' when hand_0; STOP when R[0] is set and agent is at 1."""
    prog = {"name": "t", "D": 4, "nodes": [
        {"id": "w", "op": "AND", "pos": ["ag_0", "hand_0"], "neg": []},
        {"id": "R", "op": "REG", "n": 1, "letters": [{"when": "w", "one": 0}]},
        {"id": "s", "op": "AND", "pos": ["R[0]", "ag_1"], "neg": []},
        {"id": "r", "op": "AND", "pos": [], "neg": ["s"]}],
        "outputs": {"STOP": "s", "RIGHT": "r"}}
    spec = {"atoms": [], "safety": [], "cue": []}
    inst = {"N": 4, "cells": (0, 0, 0, 0), "hazards": (0, 0, 0, 0), "agent": 0, "binding": {}}
    o, s, _ = CI.run_closed_loop(prog, spec, [inst])
    return {"outcome": o[0], "steps": s[0], "ok": o[0] == "SUCCESS" and s[0] == 1}


def main():
    t0 = time.perf_counter()
    pool = json.loads((HERE / "pool.json").read_text())
    rng = random.Random(11)
    pa2 = pool["PA2"]
    pick = rng.sample(sorted(k for k in pa2 if k.startswith("P2")), 6) + \
        rng.sample(sorted(k for k in pa2 if k.startswith("PN")), 2) + rng.sample(sorted(k for k in pa2 if k.startswith("P3")), 2)
    specs = {k: v for k, v in pool["PA1"].items()}
    specs.update({k: pa2[k] for k in pick})
    out = {"feasibility_vs_bfs": test_feasibility(specs), "batch_env_vs_scalar": test_env(specs),
           "netbatch_vs_npc": test_netbatch(), "cir_interpreter": test_cir(), "j2": j2.run_all()}
    out["summary"] = {
        "feasibility_disagreements": sum(v["instances"] - v["agree"] for v in out["feasibility_vs_bfs"].values()),
        "feasibility_instances": sum(v["instances"] for v in out["feasibility_vs_bfs"].values()),
        "env_mismatches": out["batch_env_vs_scalar"]["mismatches"],
        "netbatch_mismatches": out["netbatch_vs_npc"]["mismatching_ticks"],
        "cir_ok": out["cir_interpreter"]["ok"],
        "j2": {r["name"]: r["status"] for r in out["j2"]}}
    out["time_s"] = round(time.perf_counter() - t0, 1)
    (HERE / "selftest.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(out["summary"], indent=1), "time", out["time_s"])


if __name__ == "__main__":
    main()
