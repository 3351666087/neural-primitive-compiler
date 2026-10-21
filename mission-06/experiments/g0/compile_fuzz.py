"""G0-K2: counterexample search for compile_cir (Mission 06). Random small CIR programs in class C (compile_check P0),
run on random input sequences by the judge's CIR interpreter (judge/cir_interp.Interp) and, after compile_cir, by two
network simulators: the judge's NetBatch (judge/net_loop.py) for every program and the npc reference interpreter
(npc.simulator.simulate) for every 10th program (4 sequences). Protocol of the judge: the observation is held for D
ticks, clk = 1 at the last tick, outputs and register bits are read at the last tick. A step counts only while no
REG_CONFLICT has occurred in that sequence (a conflict is a CIR failure; the network's behaviour after it is outside C).

Compared at the last tick of every step k: every output port (vs the interpreter's action at step k) and every register
bit Y (vs the interpreter's register contents at the start of step k).

Outside class C (exploratory): mutations ATLEAST k = 0, load list of the wrong length, a node id equal to an input
channel, and conflicts (two letters of one register active together): each records whether compile_cir raised, and
otherwise whether the network and the interpreter diverged.

  python -I compile_fuzz.py [programs=10000]        # writes compile_fuzz.json
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
EXP = REPO / "mission-05" / "experiments"
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(EXP / "lib"))
sys.path.insert(0, str(EXP / "judge"))
sys.path.insert(0, str(HERE))
from cir_interp import Interp  # noqa: E402
from compile_check import check  # noqa: E402
from compile_cir import compile_cir  # noqa: E402
from env import ACTIONS  # noqa: E402
from net_loop import NetBatch  # noqa: E402
from npc.simulator import simulate  # noqa: E402

INPUTS = ["i0", "i1", "i2", "i3"]


def gen(rng, mutate=None):
    nreg = rng.randint(0, 2)
    regs = [(f"R{r}", rng.randint(1, 2)) for r in range(nreg)]
    regbits = [f"{r}[{j}]" for r, n in regs for j in range(n)]
    comb = []
    nodes = []
    for i in range(rng.randint(1, 8)):
        pool = INPUTS + comb + regbits
        op = rng.choice(["OR", "AND", "ATLEAST"])
        nid = f"x{i}"
        if op == "OR":
            nodes.append({"id": nid, "op": "OR", "in": [rng.choice(pool) for _ in range(rng.randint(1, 3))]})
        elif op == "AND":
            nodes.append({"id": nid, "op": "AND", "pos": [rng.choice(pool) for _ in range(rng.randint(0, 2))],
                          "neg": [rng.choice(pool) for _ in range(rng.randint(0, 2))]})
        else:
            ins = [rng.choice(pool) for _ in range(rng.randint(1, 3))]
            nodes.append({"id": nid, "op": "ATLEAST", "k": rng.randint(1, len(ins) + 1), "in": ins})
        comb.append(nid)
    pool = INPUTS + comb + regbits
    for r, n in regs:
        letters = []
        for _ in range(rng.randint(1, 2)):
            kind = rng.choice(["load", "load", "zero", "one"])
            L = {"when": rng.choice(pool)}
            if kind == "load":
                L["load"] = [rng.choice(pool) for _ in range(n)]
            elif kind == "zero":
                L["zero"] = True
            else:
                L["one"] = rng.randrange(n)
            letters.append(L)
        nodes.insert(rng.randint(0, len(nodes)), {"id": r, "op": "REG", "n": n, "letters": letters})
    outputs = {a: rng.choice(pool) for a in ACTIONS if rng.random() < 0.8}
    prog = {"name": "fuzz", "nodes": nodes, "outputs": outputs}
    if mutate == "atleast0":
        cand = [nd for nd in nodes if nd["op"] == "ATLEAST"]
        if not cand:
            return None
        cand[0]["k"] = 0
    elif mutate == "load_len":
        cand = [L for nd in nodes if nd["op"] == "REG" for L in nd["letters"] if "load" in L]
        if not cand:
            return None
        cand[0]["load"] = cand[0]["load"] + [INPUTS[0]]
    elif mutate == "id_is_channel":
        cand = [nd for nd in nodes if nd["op"] != "REG"]
        old = cand[-1]["id"]
        cand[-1]["id"] = "i3"
        for nd in nodes:
            for f in ("in", "pos", "neg"):
                if f in nd:
                    nd[f] = ["i3" if x == old else x for x in nd[f]]
            for L in nd.get("letters", []):
                L["when"] = "i3" if L["when"] == old else L["when"]
                if "load" in L:
                    L["load"] = ["i3" if x == old else x for x in L["load"]]
        prog["outputs"] = {a: ("i3" if r == old else r) for a, r in outputs.items()}
    return prog


def interp_run(prog, X):
    """X: (B, steps, 4) bool. Returns outputs (B, steps, ports), regbits (B, steps, bits) at step start, conflict step."""
    B, S, _ = X.shape
    it = Interp(prog, B)
    ports = list(prog["outputs"])
    bits = [(r, j) for r, n in it.regs.items() for j in range(n)]
    out = np.zeros((B, S, len(ports)), bool)
    rb = np.zeros((B, S, len(bits)), bool)
    first_conf = np.full(B, S)
    for k in range(S):
        for b, (r, j) in enumerate(bits):
            rb[:, k, b] = it.state[r][:, j]
        acts, conf = it.step({ch: X[:, k, i] for i, ch in enumerate(INPUTS)})
        for p, port in enumerate(ports):
            out[:, k, p] = acts[port]
        first_conf = np.where(conf & (first_conf == S), k, first_conf)
    return out, rb, bits, first_conf


def net_run(prog, net, D, X, bits):
    B, S, _ = X.shape
    sim = NetBatch(net, B)
    ports = list(prog["outputs"])
    oi = [sim.out_idx[p] for p in ports]
    yi = [sim.idx[f"{r}.Y[{j}]"] for r, j in bits]
    out = np.zeros((B, S, len(ports)), bool)
    rb = np.zeros((B, S, len(bits)), bool)
    for k in range(S):
        x = np.zeros((B, sim.m), dtype=np.int64)
        for i, ch in enumerate(INPUTS):
            if ch in sim.inputs:
                x[:, sim.inputs.index(ch)] = X[:, k, i]
        ci = sim.inputs.index("clk") if "clk" in sim.inputs else None
        for t in range(D):
            if ci is not None:
                x[:, ci] = 1 if t == D - 1 else 0
            now = sim.tick(x)
        out[:, k] = now[:, oi] == 1
        rb[:, k] = now[:, yi] == 1 if yi else rb[:, k]
    return out, rb


def ref_run(prog, net, D, X, bits, b):
    """npc reference interpreter on sequence b."""
    S = X.shape[1]
    T = S * D
    inputs = {}
    for ch in net.inputs:
        if ch == "clk":
            inputs[ch] = [1 if t % D == D - 1 else 0 for t in range(T)]
        else:
            i = INPUTS.index(ch)
            inputs[ch] = [int(X[b, t // D, i]) for t in range(T)]
    tr = simulate(net, inputs, T)
    ports = list(prog["outputs"])
    out = np.array([[tr.outputs[p][k * D + D - 1] for p in ports] for k in range(S)], bool)
    rb = np.array([[tr.spikes[f"{r}.Y[{j}]"][k * D + D - 1] for r, j in bits] for k in range(S)], bool).reshape(S, len(bits))
    return out, rb


def run_one(prog, rng, B=64, S=8, ref=False):
    X = np.array([[[rng.random() < 0.5 for _ in INPUTS] for _ in range(S)] for _ in range(B)], bool)
    io, ir, bits, conf = interp_run(prog, X)
    net, info = compile_cir(prog)
    D = info["D"]
    no, nr = net_run(prog, net, D, X, bits)
    valid = np.arange(S)[None, :] < conf[:, None]             # steps before the first conflict
    mis = ((io != no).any(2) | (ir != nr).any(2)) & valid
    res = {"D": D, "neurons": info["neurons"], "steps_compared": int(valid.sum()), "mismatch_steps": int(mis.sum()),
           "conflict_sequences": int((conf < S).sum())}
    if ref:
        rm = 0
        for b in range(4):
            ro, rr = ref_run(prog, net, D, X, bits, b)
            v = np.arange(S) < conf[b]
            rm += int((((ro != io[b]).any(1) | (rr != ir[b]).any(1)) & v).sum())
        res["ref_mismatch_steps"] = rm
    if res["mismatch_steps"]:
        k = np.argwhere(mis)[0]
        res["first_mismatch"] = {"sequence": X[k[0]].astype(int).tolist(), "step": int(k[1])}
    if conf.min() < S:                                         # exploratory: divergence after a conflict
        after = ~valid
        res["diverged_after_conflict"] = int((((io != no).any(2) | (ir != nr).any(2)) & after).sum())
    return res


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    t0 = time.perf_counter()
    rng = random.Random(2026)
    tot = {"programs": 0, "premise_failures": 0, "steps_compared": 0, "mismatch_steps": 0, "ref_programs": 0,
           "ref_mismatch_steps": 0, "programs_with_conflicts": 0, "conflict_divergent_steps": 0,
           "outside_C_K_generated": 0, "outside_C_K_rejected_loudly": 0, "outside_C_K_compiled": 0,
           "inside_C_K_compile_errors": 0}
    examples = []
    for i in range(n):
        prog = gen(rng)
        k_out = any(p.startswith("P0K") for p in check(prog, None, None, only_class=True))
        try:
            net, info = compile_cir(prog)
        except Exception as e:                                 # noqa: BLE001
            if k_out:
                tot["outside_C_K_generated"] += 1
                tot["outside_C_K_rejected_loudly"] += 1
            else:
                tot["inside_C_K_compile_errors"] += 1
                if len(examples) < 10:
                    examples.append({"kind": "compile_error_in_C_K", "program": prog, "error": str(e)[:200]})
            continue
        if k_out:
            tot["outside_C_K_generated"] += 1
            tot["outside_C_K_compiled"] += 1
            continue
        pr = check(prog, net, info)
        if pr:
            tot["premise_failures"] += 1
            if len(examples) < 5:
                examples.append({"kind": "premise", "program": prog, "problems": pr[:5]})
        r = run_one(prog, rng, ref=(i % 10 == 0))
        tot["programs"] += 1
        tot["steps_compared"] += r["steps_compared"]
        tot["mismatch_steps"] += r["mismatch_steps"]
        if "ref_mismatch_steps" in r:
            tot["ref_programs"] += 1
            tot["ref_mismatch_steps"] += r["ref_mismatch_steps"]
        if r["conflict_sequences"]:
            tot["programs_with_conflicts"] += 1
            tot["conflict_divergent_steps"] += r.get("diverged_after_conflict", 0)
        if (r["mismatch_steps"] or r.get("ref_mismatch_steps")) and len(examples) < 10:
            examples.append({"kind": "mismatch", "program": prog, "result": r})
    outside = {}
    for mut in ("atleast0", "load_len", "id_is_channel"):
        rec = {"tried": 0, "compile_error": 0, "premise_flagged": 0, "ran": 0, "diverged": 0, "errors": []}
        r2 = random.Random(f"mut|{mut}")
        while rec["tried"] < 200:
            prog = gen(r2, mut)
            if prog is None:
                continue
            rec["tried"] += 1
            try:
                net, info = compile_cir(prog)
            except Exception as e:                             # noqa: BLE001
                rec["compile_error"] += 1
                if len(rec["errors"]) < 3:
                    rec["errors"].append(f"{type(e).__name__}: {str(e)[:120]}")
                continue
            if check(prog, net, info):
                rec["premise_flagged"] += 1
            try:
                r = run_one(prog, r2)
            except Exception as e:                             # noqa: BLE001
                rec["errors"].append(f"run {type(e).__name__}: {str(e)[:120]}")
                continue
            rec["ran"] += 1
            rec["diverged"] += r["mismatch_steps"] > 0
        outside[mut] = rec
    out = {"label": "G0-K2 (Mission 06): compile_cir differential fuzzing", "class_C": tot, "examples": examples,
           "outside_C": outside, "time_s": round(time.perf_counter() - t0, 1)}
    (HERE / "compile_fuzz.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({"class_C": tot, "outside_C": {k: {x: v[x] for x in v if x != "errors"} for k, v in outside.items()},
                      "time_s": out["time_s"]}, indent=1))


if __name__ == "__main__":
    main()
