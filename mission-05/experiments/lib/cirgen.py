"""Emit the controller IR (CIR, defined in judge/cir_interp.py docstring) for a priority plan. CONSTRUCTOR SIDE.

A plan is [(atom, variant), ...] in priority order. The emitted controller, for one track length N, is:
  perception   relational features of the observation (colour bundles, prefix ORs, extremes, zone and window
               features, counts with ATLEAST), all combinational;
  binding      for cue specs, one register per colour variable, loaded from the cue channels at step 0;
  selection    for the first violated atom, the achiever's (x, y) cells and the spare cell;
  memory       registers X, Y, S (one-hot positions), XO (x was occupied), PH (six relocation phases; all zero = idle);
  control      walk to the phase's target register, PICK or DROP there, advance the phase; STOP when idle and every
               atom holds with an empty hand.
The same plan instantiates at every N; nothing in it is specific to a training size.
"""

from __future__ import annotations

from model import zcells


class G:
    def __init__(self, name):
        self.nodes, self.n, self.name = [], 0, name
        self.T = self.AND([], [], tag="T")
        self.F = self.AND([self.T], [self.T], tag="F")

    def _id(self, tag):
        self.n += 1
        return f"{tag}{self.n}"

    def OR(self, ins, tag="o"):
        ins = [x for x in ins if x != self.F] if hasattr(self, "F") else ins
        if not ins:
            return self.F
        if len(ins) == 1:
            return ins[0]
        i = self._id(tag)
        self.nodes.append({"id": i, "op": "OR", "in": list(ins)})
        return i

    def AND(self, pos, neg, tag="a"):
        if hasattr(self, "F") and self.F in pos:
            return self.F
        i = self._id(tag)
        self.nodes.append({"id": i, "op": "AND", "pos": list(pos), "neg": [x for x in neg if x != getattr(self, "F", None)]})
        return i

    def NOT(self, x):
        return self.AND([], [x], tag="n")

    def ATLEAST(self, k, ins):
        i = self._id("c")
        self.nodes.append({"id": i, "op": "ATLEAST", "k": k, "in": list(ins)})
        return i

    def REG(self, name, n, letters):
        self.nodes.append({"id": name, "op": "REG", "n": n, "letters": letters})
        return [f"{name}[{j}]" for j in range(n)]

    # bundle helpers (lists of refs indexed by position)
    def prefix_left(self, v):          # L[p] = OR v[q], q < p
        return [self.OR(v[:p]) for p in range(len(v))]

    def prefix_right(self, v):         # R[p] = OR v[q], q > p
        return [self.OR(v[p + 1:]) for p in range(len(v))]

    def leftmost(self, v):
        L = self.prefix_left(v)
        return [self.AND([v[p]], [L[p]]) for p in range(len(v))]

    def rightmost(self, v):
        R = self.prefix_right(v)
        return [self.AND([v[p]], [R[p]]) for p in range(len(v))]


def emit(plan, spec, N):
    g = G("ctrl")
    rule = any(s[0] == "NO_DROP_HAZARD" for s in spec["safety"])
    fixedcols = [s[1] for s in spec["safety"] if s[0] == "NO_PICK"]
    cue = spec.get("cue") or []
    P = range(N)
    # binding registers for cue variables
    bind = {}
    for v in cue:
        present = g.OR([f"cue_{v}_{k}" for k in range(1, 5)])
        relays = [g.AND([f"cue_{v}_{k}"], []) for k in range(1, 5)]          # neuron relays of the raw cue channels
        bind[v] = g.REG(f"B{v}", 4, [{"when": present, "load": relays}])
    ready = g.OR(bind[cue[0]]) if cue else None

    cache = {}

    def obj(c):
        if c in cache:
            return cache[c]
        if isinstance(c, str):
            out = [g.OR([g.AND([bind[c][k], f"col_{p}_{k + 1}"], []) for k in range(4)]) for p in P]
        else:
            out = [f"col_{p}_{c}" for p in P]
        cache[c] = out
        return out
    empty = [f"col_{p}_0" for p in P]
    occ = [g.NOT(f"col_{p}_0") for p in P]
    af = [g.AND([f"col_{p}_0"], [f"haz_{p}"]) if rule else f"col_{p}_0" for p in P]
    fixed = [g.OR([f"col_{p}_{c}" for c in fixedcols]) if fixedcols else g.F for p in P]

    def atom_viol(a):
        t = a[0]
        if t == "ORDER":
            A1, A2 = obj(a[1]), obj(a[2])
            L2 = g.prefix_left(A2)
            return g.OR([g.AND([A1[q], L2[q]], []) for q in P])
        if t == "ZONE":
            z = set(zcells(N, a[2], a[3]))
            return g.OR([obj(a[1])[p] for p in P if p not in z])
        o = obj(a[1])
        L, R = g.prefix_left(o), g.prefix_right(o)
        return g.OR([g.AND([L[q], R[q]], [o[q]]) for q in P])

    def selection(a, var):
        t = a[0]
        if t == "ORDER":
            A1, A2 = obj(a[1]), obj(a[2])
            X = g.leftmost(A2)
            if var == "O1":
                Y = g.rightmost(A1)
            else:
                aft = g.prefix_left(X)
                Y = g.leftmost([g.AND([A1[q], aft[q]], []) for q in P])
            return X, Y
        if t == "ZONE":
            c = a[1]
            o = obj(c)
            z = set(zcells(N, a[2], a[3]))
            elig = [g.OR([af[p], g.AND([], [f"col_{p}_0", o[p], fixed[p]])]) if p in z else g.F for p in P]
            out = [o[p] if p not in z else g.F for p in P]
            near = var == "Z1"
            if a[2] == "left":
                return (g.rightmost(elig), g.leftmost(out)) if near else (g.leftmost(elig), g.rightmost(out))
            return (g.leftmost(elig), g.rightmost(out)) if near else (g.rightmost(elig), g.leftmost(out))
        c = a[1]
        o = obj(c)
        ge = [g.ATLEAST(k, o) for k in range(1, N + 1)] + [g.F]
        eq = {k: g.AND([ge[k - 1]], [ge[k]]) for k in range(1, N + 1)}
        other_fixed = [g.OR([f"col_{p}_{f}" for f in fixedcols if f != c]) if [f for f in fixedcols if f != c] else g.F
                       for p in P]
        cellok = [g.AND([], ([f"haz_{p}"] if rule else []) + [other_fixed[p]]) for p in P]
        valid = []
        win = {}
        for s in P:
            terms = []
            for k in range(1, N - s + 1):
                win[(s, k)] = g.AND(cellok[s:s + k], [])
                terms.append(g.AND([eq[k], win[(s, k)]], []))
            valid.append(g.OR(terms))
        wsel = g.leftmost(valid) if var == "G1" else g.rightmost(valid)
        wsk = {(s, k): g.AND([wsel[s], eq[k]], []) for s in P for k in range(1, N - s + 1)}
        inwin = [g.OR([wsk[(s, k)] for (s, k) in wsk if s <= p < s + k]) for p in P]
        oow = [g.AND([o[p]], [inwin[p]]) for p in P]
        wl = [g.AND([inwin[p]], [o[p]]) for p in P]
        return (g.leftmost(wl), g.leftmost(oow)) if var == "G1" else (g.rightmost(wl), g.rightmost(oow))

    viol = [atom_viol(a) for a, _ in plan]
    sels = [selection(a, v) for a, v in plan]
    first = [g.AND([viol[i]], viol[:i]) for i in range(len(plan))]
    Xsel = [g.OR([g.AND([first[i], sels[i][0][p]], []) for i in range(len(plan))]) for p in P]
    Ysel = [g.OR([g.AND([first[i], sels[i][1][p]], []) for i in range(len(plan))]) for p in P]
    spare = g.leftmost(af)
    xocc = g.OR([g.AND([Xsel[p], occ[p]], []) for p in P])
    nxocc = g.NOT(xocc)
    anyviol = g.OR(viol)
    agR = g.prefix_right([f"ag_{p}" for p in P])      # agent strictly right of p
    agL = g.prefix_left([f"ag_{p}" for p in P])       # agent strictly left of p
    PH = [f"PH[{k}]" for k in range(6)]
    regs = {r: [f"{r}[{p}]" for p in P] for r in ("X", "Y", "S")}

    def nav(r):
        R = regs[r]
        at = g.OR([g.AND([R[p], f"ag_{p}"], []) for p in P])
        tl = g.OR([g.AND([R[p], agR[p]], []) for p in P])
        tr = g.OR([g.AND([R[p], agL[p]], []) for p in P])
        return at, tl, tr
    navs = {r: nav(r) for r in ("X", "Y", "S")}
    target = ["X", "S", "Y", "X", "S", "Y"]
    idle = g.AND([], PH)
    base = [ready] if cue else []
    start = g.AND([idle, anyviol, "hand_0"] + base, [])
    stop = g.AND([idle, "hand_0"] + base, [anyviol])
    left = g.OR([g.AND([PH[k], navs[target[k]][1]], []) for k in range(6)])
    right = g.OR([g.AND([PH[k], navs[target[k]][2]], []) for k in range(6)])
    arrive = [g.AND([PH[k], navs[target[k]][0]], []) for k in range(6)]
    pick = g.OR([arrive[0], arrive[2], arrive[4]])
    drop = g.OR([arrive[1], arrive[3], arrive[5]])
    a3_occ = g.AND([arrive[3], "XO[0]"], [])
    a3_free = g.AND([arrive[3]], ["XO[0]"])
    g.REG("PH", 6, [{"when": start, "load": [xocc, g.F, nxocc, g.F, g.F, g.F]},
                    {"when": arrive[0], "one": 1}, {"when": arrive[1], "one": 2}, {"when": arrive[2], "one": 3},
                    {"when": a3_occ, "one": 4}, {"when": a3_free, "zero": True},
                    {"when": arrive[4], "one": 5}, {"when": arrive[5], "zero": True}])
    g.REG("X", N, [{"when": start, "load": Xsel}])
    g.REG("Y", N, [{"when": start, "load": Ysel}])
    g.REG("S", N, [{"when": start, "load": spare}])
    g.REG("XO", 1, [{"when": start, "load": [xocc]}])
    return {"name": f"plan@N{N}", "nodes": g.nodes,
            "outputs": {"LEFT": left, "RIGHT": right, "PICK": pick, "DROP": drop, "STOP": stop}}


def emit_flat(rules, spec, N):
    """CIR for an A-FLAT decision list: features here_k, hand_k, lex_k, rex_k, hazhere, goal; rule i fires iff its
    literals hold and no earlier rule fires; each action is the OR of the rules that choose it. No registers."""
    g = G("flat")
    P = range(N)
    agR = g.prefix_right([f"ag_{p}" for p in P])
    agL = g.prefix_left([f"ag_{p}" for p in P])
    f = {}
    for k in range(5):
        f[f"here_{k}"] = g.OR([g.AND([f"ag_{p}", f"col_{p}_{k}"], []) for p in P])
        f[f"hand_{k}"] = g.AND([f"hand_{k}"], [])
    for k in range(1, 5):
        f[f"lex_{k}"] = g.OR([g.AND([f"col_{p}_{k}", agR[p]], []) for p in P])
        f[f"rex_{k}"] = g.OR([g.AND([f"col_{p}_{k}", agL[p]], []) for p in P])
    f["hazhere"] = g.OR([g.AND([f"ag_{p}", f"haz_{p}"], []) for p in P])
    viols = []
    for a in spec["atoms"]:
        o = lambda c: [f"col_{p}_{c}" for p in P]
        if a[0] == "ORDER":
            L2 = g.prefix_left(o(a[2]))
            viols.append(g.OR([g.AND([o(a[1])[q], L2[q]], []) for q in P]))
        elif a[0] == "ZONE":
            z = set(zcells(N, a[2], a[3]))
            viols.append(g.OR([o(a[1])[p] for p in P if p not in z]))
        else:
            L, R = g.prefix_left(o(a[1])), g.prefix_right(o(a[1]))
            viols.append(g.OR([g.AND([L[q], R[q]], [o(a[1])[q]]) for q in P]))
    f["goal"] = g.AND([], viols)
    fired = []
    acts = {a: [] for a in ("LEFT", "RIGHT", "PICK", "DROP", "STOP")}
    for cond, act in rules:
        pos = [f[n] for n, v in cond if v]
        neg = [f[n] for n, v in cond if not v]
        lit = g.AND(pos, neg)
        r = g.AND([lit], list(fired))
        fired.append(r)
        acts[act].append(r)
    return {"name": f"flat@N{N}", "nodes": g.nodes, "outputs": {a: g.OR(v) for a, v in acts.items()}}
