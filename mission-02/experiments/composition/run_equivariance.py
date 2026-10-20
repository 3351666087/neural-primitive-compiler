"""Equivariance from wiring symmetry (compositional-semantics.md, Lemma E).

  python mission-02/experiments/composition/run_equivariance.py

For a compiled network and a relabeling sigma (of coordinates, letters, query channels), check
  (structural, exact)  sigma maps every neuron to a neuron with identical parameters and every synapse
                       to a synapse with identical weight and delay, and maps output ports consistently;
  (behavioural, [E])   on random traces x: out(sigma x) = sigma out(x).
By Lemma E the structural check implies the behavioural property for every trace of every length.
"""

from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402

from cog.check import automorphism  # noqa: E402
from cog.ir import compile_ir  # noqa: E402
from cog.tasks import family_a, family_b, random_trace  # noqa: E402
from npc.simulator import BatchSim  # noqa: E402

OUT = Path(__file__).parent / "equivariance.json"


def b_program(K):
    letters = {}
    for k in range(K):
        letters[f"STORE{k}"] = {"map": ["store_row", k, "val"]}
        letters[f"CLEAR{k}"] = {"map": ["clear_row", k]}
        for j in range(K):
            if j < k:
                letters[f"SWAP{j}{k}"] = {"map": ["swap_rows", j, k]}
            if j != k:
                letters[f"COPY{j}{k}"] = {"map": ["copy_row", j, k]}
    return {"name": "b", "nodes": [{"id": "mem", "op": "CMR", "letters": letters},
                                   {"id": "valueof", "op": "SEL", "of": "mem", "select": "qobj", "axis": 0, "delay": 2},
                                   {"id": "who", "op": "SEL", "of": "mem", "select": "qval", "axis": 1, "delay": 2}],
            "outputs": {"img": "mem", "valueof": "valueof", "who": "who"}}


def b_renamer(sig: dict):
    def L(name):
        m = re.fullmatch(r"(STORE|CLEAR)(\d)", name)
        if m:
            return f"{m.group(1)}{sig[int(m.group(2))]}"
        m = re.fullmatch(r"SWAP(\d)(\d)", name)
        if m:
            a, b = sorted((sig[int(m.group(1))], sig[int(m.group(2))]))
            return f"SWAP{a}{b}"
        m = re.fullmatch(r"COPY(\d)(\d)", name)
        if m:
            return f"COPY{sig[int(m.group(1))]}{sig[int(m.group(2))]}"
        return name

    def rn(s):
        m = re.fullmatch(r"mem\.(P|Y)\[(\d+),(\d+)(\|(.*))?\]", s)
        if m:
            tag = "" if m.group(5) is None else "|" + (L(m.group(5)) if m.group(5) != "_" else "_")
            return f"mem.{m.group(1)}[{sig[int(m.group(2))]},{m.group(3)}{tag}]"
        m = re.fullmatch(r"valueof\.A\[(\d+)\|(\d+)\]", s)
        if m:
            return f"valueof.A[{m.group(1)}|{sig[int(m.group(2))]}]"
        m = re.fullmatch(r"who\.A\[(\d+)\|(\d+)\]", s)
        if m:
            return f"who.A[{sig[int(m.group(1))]}|{m.group(2)}]"
        m = re.fullmatch(r"who\.O\[(\d+)\]", s)
        if m:
            return f"who.O[{sig[int(m.group(1))]}]"
        m = re.fullmatch(r"qobj_(\d+)", s)
        if m:
            return f"qobj_{sig[int(m.group(1))]}"
        m = re.fullmatch(r"img_(\d+)_(\d+)", s)
        if m:
            return f"img_{sig[int(m.group(1))]}_{m.group(2)}"
        m = re.fullmatch(r"who_(\d+)", s)
        if m:
            return f"who_{sig[int(m.group(1))]}"
        return L(s)
    return rn


def a_program():
    return {"name": "a", "nodes": [{"id": "mem", "op": "CMR", "letters": {
        "LOAD": {"map": ["load", "see"]}, "ROT90": {"map": ["rot90"]}, "FLIPH": {"map": ["fliph"]}, "FLIPV": {"map": ["flipv"]}}}],
        "outputs": {"img": "mem"}}


def a_renamer(N):
    rot = lambda x, y: (N - 1 - y, x)   # sigma = rotate the whole picture clockwise
    L = {"FLIPH": "FLIPV", "FLIPV": "FLIPH"}  # conjugating a mirror by a quarter turn swaps the two mirrors

    def rn(s):
        m = re.fullmatch(r"mem\.(P|Y)\[(\d+),(\d+)(\|(.*))?\]", s)
        if m:
            x, y = rot(int(m.group(2)), int(m.group(3)))
            tag = "" if m.group(5) is None else "|" + L.get(m.group(5), m.group(5))
            return f"mem.{m.group(1)}[{x},{y}{tag}]"
        m = re.fullmatch(r"(see|img)_(\d+)_(\d+)", s)
        if m:
            x, y = rot(int(m.group(2)), int(m.group(3)))
            return f"{m.group(1)}_{x}_{y}"
        return L.get(s, s)
    return rn


def behavioural(net, task, rn, n=200, T=12, seed=0) -> bool:
    rng = random.Random(seed)
    sim = BatchSim(net)
    port = dict(net.outputs)
    idx = {nm: i for i, nm in enumerate(net.neuron_names)}
    for _ in range(n):
        tr = random_trace(task, T, rng)
        tr2 = {rn(k): v for k, v in tr.items()}
        X = np.array([[tr.get(ch, [0] * T) for ch in net.inputs], [tr2.get(ch, [0] * T) for ch in net.inputs]])
        S = sim.run(X)
        for p, nrn in port.items():
            a = S[0, sim.m + idx[nrn]]
            b = S[1, sim.m + idx[port[rn(p)]]]
            if list(a) != list(b):
                return False
    return True


def check(net, rn):
    st = automorphism(net, rn)
    port = dict(net.outputs)
    ports_ok = all(rn(port[p]) == port.get(rn(p)) for p in port)
    return st.ok and ports_ok, st.detail


def main():
    rows = []
    for K, V in ((3, 3), (5, 4)):
        task = family_b(K, V, ["STORE", "SWAP", "COPY", "CLEAR"], queries=["value", "who"])
        net = compile_ir(b_program(K), task.interface())
        for name, sig in (("swap objects 0,1", {i: ({0: 1, 1: 0}.get(i, i)) for i in range(K)}),
                          ("cycle all objects", {i: (i + 1) % K for i in range(K)})):
            rn = b_renamer(sig)
            ok, det = check(net, rn)
            rows.append({"task": task.name, "sigma": name, "structural": ok, "behavioural": behavioural(net, task, rn), **det})
            print(rows[-1], flush=True)
    for N in (3, 4, 7):
        task = family_a(N, ["ROT90", "FLIPH", "FLIPV"])
        net = compile_ir(a_program(), task.interface())
        rn = a_renamer(N)
        ok, det = check(net, rn)
        rows.append({"task": task.name, "sigma": "rotate grid 90 deg (FLIPH<->FLIPV)", "structural": ok,
                     "behavioural": behavioural(net, task, rn), **det})
        print(rows[-1], flush=True)
    # negative control: a letter set that is NOT closed under the symmetry (FLIPH without FLIPV)
    task = family_a(4, ["ROT90", "FLIPH"])
    prog = a_program()
    prog["nodes"][0]["letters"].pop("FLIPV")
    net = compile_ir(prog, task.interface())
    rn = a_renamer(4)
    try:
        ok, det = check(net, rn)
    except KeyError as e:
        ok, det = False, {"reason": f"no image for {e}"}
    rows.append({"task": task.name, "sigma": "rotate grid 90 deg, letter set not closed (control)", "structural": ok, **det})
    print(rows[-1])
    OUT.write_text(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
