"""Compile a CIR program to an integer IF network with the frozen templates of cog.prims (amendment 1, item 4).

  OR       -> prims.any_            AND -> prims.gate (an empty pos list gets the constant-true neuron __T)
  ATLEAST  -> one IF neuron, threshold k, unit weights (the only new template; contract proved in judge/j2.py L2)
  REG      -> prims.cmr over coordinates (0,)..(n-1,); every letter is gated by the clock: L = gate(when, clk);
              load sources that are raw input channels get a relay neuron (cmr reads its sources one tick after
              the letter condition; relays keep every source a neuron computed from the held observation)
Clocking: the observation is held for D ticks per environment step; `clk` is 1 at the last tick; actions are read
at the last tick. D = (longest combinational path in ticks, register bits counted as available at tick 2) + 4.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))
from cog.prims import ONE, Builder, any_, cmr, gate  # noqa: E402

REGREF = re.compile(r"^(.*)\[(\d+)\]$")


def compile_cir(prog):
    nodes = prog["nodes"]
    regs = {nd["id"]: nd for nd in nodes if nd["op"] == "REG"}
    comb = {nd["id"] for nd in nodes if nd["op"] != "REG"}
    b = Builder(prog.get("name", "cir"), max_delay=1)
    tconst = b.neuron("__T", threshold=1, bias=1)        # constant true: bias 1, threshold 1, fires every tick

    def is_regbit(r):
        m = REGREF.match(r)
        return m is not None and m.group(1) in regs

    def sig(r):
        if r in comb:
            return r
        if is_regbit(r):
            m = REGREF.match(r)
            return f"{m.group(1)}.Y[{m.group(2)}]"
        return b.input(r)

    depth = {}

    def dep(r):
        if r in depth:
            return depth[r]
        if r in comb:
            raise KeyError(r)
        return 2 if is_regbit(r) else 0

    for nd in nodes:
        op = nd["op"]
        if op == "REG":
            continue
        i = nd["id"]
        if op == "OR":
            any_(b, i, [sig(r) for r in nd["in"]], 1)
            depth[i] = 1 + max(dep(r) for r in nd["in"])
        elif op == "AND":
            pos = [sig(r) for r in nd["pos"]] or [tconst]
            gate(b, i, [(s, 1) for s in pos], [(sig(r), 1) for r in nd["neg"]])
            depth[i] = 1 + max([dep(r) for r in nd["pos"] + nd["neg"]] or [0])
        elif op == "ATLEAST":
            b.neuron(i, threshold=nd["k"])
            for r in nd["in"]:
                b.syn(sig(r), i, 1, 1)
            depth[i] = 1 + max(dep(r) for r in nd["in"])
        else:
            raise ValueError(op)
    clk = b.input("clk")
    relay = {}

    def neuron_src(r):
        s = sig(r)
        if r in comb or is_regbit(r):
            return s
        if r not in relay:
            relay[r] = any_(b, f"__relay[{r}]", [s], 1)
        return relay[r]

    for rid, nd in regs.items():
        rules, chans = {}, {}
        for li, L in enumerate(nd["letters"]):
            lname = f"l{li}"
            chans[lname] = gate(b, f"{rid}.L{li}", [(neuron_src(L["when"]), 1), (clk, 1)], [])
            if "load" in L:
                rules[lname] = {(j,): [("d", neuron_src(r))] for j, r in enumerate(L["load"])}
            elif L.get("zero"):
                rules[lname] = {}
            else:
                rules[lname] = {(L["one"],): [ONE]}
        cmr(b, rid, [(j,) for j in range(nd["n"])], rules, chans)
    for port, r in prog["outputs"].items():
        b.output(port, neuron_src(r))
    whens = [L["when"] for nd in regs.values() for L in nd["letters"]]
    loads = [x for nd in regs.values() for L in nd["letters"] for x in L.get("load", [])]
    maxdep = max(dep(r) if r not in depth else depth[r] for r in list(prog["outputs"].values()) + whens + loads)
    D = maxdep + 4
    net = b.build()
    return net, {"D": D, "neurons": len(net.neurons), "synapses": len(net.synapses), "inputs": len(net.inputs),
                 "max_comb_depth": maxdep}
