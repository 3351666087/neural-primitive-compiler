"""G0-K1 (part 2): per-network premise checker for the compile_cir preservation theorem (M05_TRUST_BOUNDARY.md, T-K).

check(prog, net, info) verifies, for one CIR program and the network compile_cir produced from it:
  P0  the program is in class C: ids unique and distinct from observation channels and compiler names; comb refs
      defined earlier; ATLEAST k >= 1; load lists of length n; "one" index < n
  P1  every neuron is memoryless with vmin = 0, init = 0, 1 <= threshold <= vmax; every synapse has delay 1
  P2  every comb node is one neuron with exactly the synapse multiset and threshold of its template (OR, AND with
      __T for an empty positive list, ATLEAST); bias 0
  P3  relays, __T, and every register's letter, P, idle and Y neurons have exactly the cog.prims.cmr wiring for the
      register's letters; no other neuron exists
  P4  the outputs are the expected neurons
  P5  timing: with depth(input) = 0, depth(__T) = 0, depth(Y bit) = 2, depth(neuron) = 1 + max depth(sources):
      depth(output) <= D - 1, depth(when) <= D - 1, depth(load source) <= D, and D >= 3
Returns a list of problems (empty: the theorem's premises hold for this network).
"""

from __future__ import annotations

import re
from collections import Counter

REGREF = re.compile(r"^(.*)\[(\d+)\]$")
OBS = re.compile(r"^(col_\d+_\d+|haz_\d+|ag_\d+|hand_\d+|cue_\w+_\d+|clk|i\d+)$")


def check(prog, net, info, only_class=False):
    pr = []
    nodes = prog["nodes"]
    regs = {nd["id"]: nd for nd in nodes if nd["op"] == "REG"}
    comb = [nd for nd in nodes if nd["op"] != "REG"]
    ids = [nd["id"] for nd in nodes]
    # ---------------------------------------------------------------- P0
    if len(set(ids)) != len(ids):
        pr.append("P0 duplicate ids")
    for i in ids:
        if OBS.match(i) or i.startswith("__") or "." in i or REGREF.match(i):
            pr.append(f"P0 id {i} clashes with a channel or compiler name")
    seen = set()

    def isreg(r):
        m = REGREF.match(r)
        return m is not None and m.group(1) in regs and int(m.group(2)) < regs[m.group(1)]["n"]

    def ref_ok(r, earlier):
        return r in earlier or isreg(r) or OBS.match(r) is not None

    order = [nd["id"] for nd in nodes if nd["op"] == "REG"]
    for nd in nodes:
        refs = nd.get("in", []) + nd.get("pos", []) + nd.get("neg", [])
        for L in nd.get("letters", []):
            refs += [L["when"]] + L.get("load", [])
            if "load" in L and len(L["load"]) != nd["n"]:
                pr.append(f"P0 {nd['id']}: load length")
            for r in L.get("load", []):                       # class C_K: compile_cir builds registers in list order
                m = REGREF.match(r)
                if isreg(r) and order.index(m.group(1)) >= order.index(nd["id"]):
                    pr.append(f"P0K {nd['id']}: load from register {m.group(1)} (same or later)")
            if "one" in L and not 0 <= L["one"] < nd["n"]:
                pr.append(f"P0 {nd['id']}: one index")
        for r in refs:
            if not ref_ok(r, seen if nd["op"] != "REG" else {x["id"] for x in comb}):
                pr.append(f"P0 {nd['id']}: bad ref {r}")
        if nd["op"] == "ATLEAST" and nd["k"] < 1:
            pr.append(f"P0 {nd['id']}: ATLEAST k < 1")
        if nd["op"] != "REG":
            seen.add(nd["id"])
    for r in prog["outputs"].values():
        if not ref_ok(r, seen):
            pr.append(f"P0 output ref {r}")
    if pr or only_class:
        return pr
    # ---------------------------------------------------------------- P1
    N = {n.name: n for n in net.neurons}
    inc = {n: Counter() for n in N}
    for s in net.synapses:
        if s.delay != 1:
            pr.append(f"P1 delay {s.delay} on {s.src}->{s.dst}")
        inc[s.dst][(s.src, s.weight)] += 1
    for n in net.neurons:
        if not (n.memoryless and n.vmin == 0 and n.init == 0 and 1 <= n.threshold <= n.vmax):
            pr.append(f"P1 neuron {n.name} parameters")
    combids = {nd["id"] for nd in comb}

    def sig(r):
        if r in combids:
            return r
        if isreg(r):
            m = REGREF.match(r)
            return f"{m.group(1)}.Y[{m.group(2)}]"
        return r

    def nsrc(r):
        return sig(r) if (r in combids or isreg(r)) else f"__relay[{r}]"

    expected = {}

    def expect(name, thr, syns, bias=0):
        expected[name] = (thr, Counter(syns), bias)

    expect("__T", 1, [], 1)
    for nd in comb:
        if nd["op"] == "OR":
            expect(nd["id"], 1, [(sig(r), 1) for r in nd["in"]])
        elif nd["op"] == "AND":
            pos = [sig(r) for r in nd["pos"]] or ["__T"]
            expect(nd["id"], len(pos), [(s, 1) for s in pos] + [(sig(r), -len(pos)) for r in nd["neg"]])
        else:
            expect(nd["id"], nd["k"], [(sig(r), 1) for r in nd["in"]])
    raw = set()
    for nd in regs.values():
        for L in nd["letters"]:
            for r in [L["when"]] + L.get("load", []):
                if not (r in combids or isreg(r)):
                    raw.add(r)
    for r in prog["outputs"].values():
        if not (r in combids or isreg(r)):
            raw.add(r)
    for r in raw:
        expect(f"__relay[{r}]", 1, [(r, 1)])
    for rid, nd in regs.items():
        letters = [f"{rid}.L{i}" for i in range(len(nd["letters"]))]
        for i, L in enumerate(nd["letters"]):
            expect(letters[i], 2, [(nsrc(L["when"]), 1), ("clk", 1)])
        for j in range(nd["n"]):
            ps = []
            for i, L in enumerate(nd["letters"]):
                nm = f"{rid}.P[{j}|l{i}]"
                if "load" in L:
                    expect(nm, 2, [(letters[i], 1), (nsrc(L["load"][j]), 1)])
                    ps.append(nm)
                elif not L.get("zero") and L["one"] == j:
                    expect(nm, 1, [(letters[i], 1)])
                    ps.append(nm)
            idle = f"{rid}.P[{j}|_]"
            ps.append(idle)
            expect(idle, 1, [(p, 1) for p in ps] + [(l, -1) for l in letters])
            expect(f"{rid}.Y[{j}]", 1, [(p, 1) for p in ps])
    if set(N) != set(expected):
        pr.append(f"P3 neuron set differs: missing {sorted(set(expected) - set(N))[:5]}, extra {sorted(set(N) - set(expected))[:5]}")
    for nm, (thr, syns, bias) in expected.items():
        if nm not in N:
            continue
        n = N[nm]
        if n.threshold != thr or n.bias != bias or inc[nm] != syns:
            pr.append(f"P2/P3 {nm}: threshold {n.threshold}/{thr}, bias {n.bias}/{bias}, synapses differ {inc[nm] != syns}")
    # ---------------------------------------------------------------- P4
    if dict(net.outputs) != {p: nsrc(r) for p, r in prog["outputs"].items()}:
        pr.append("P4 outputs")
    # ---------------------------------------------------------------- P5
    D = info["D"]
    depth = {"__T": 0}
    for rid, nd in regs.items():
        for j in range(nd["n"]):
            depth[f"{rid}.Y[{j}]"] = 2

    def dp(s):
        if s in depth:
            return depth[s]
        if s.startswith("__relay["):
            return 1
        return 0                                               # observation channel

    for nd in comb:
        depth[nd["id"]] = 1 + max([dp(src) for (src, _w) in expected[nd["id"]][1]] or [0])
    if D < 3:
        pr.append("P5 D < 3")
    for r in prog["outputs"].values():
        if dp(nsrc(r)) > D - 1:
            pr.append(f"P5 output {r} depth {dp(nsrc(r))} > D - 1 = {D - 1}")
    for nd in regs.values():
        for L in nd["letters"]:
            if dp(nsrc(L["when"])) > D - 1:
                pr.append(f"P5 when {L['when']} depth > D - 1")
            for r in L.get("load", []):
                if dp(nsrc(r)) > D:
                    pr.append(f"P5 load {r} depth > D")
    return pr
