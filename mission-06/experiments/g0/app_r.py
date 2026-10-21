"""APP-R: an oracle-free applicability prover for ACH-DSL achievers (Mission 06, G0.2). CONSTRUCTOR SIDE.

Imports no truth table and nothing from mission-05/experiments/judge. Applicability of an achiever instance: in every
eligible state (atom violated, atom satisfiable on its own, a non-hazard empty cell exists) the selection gives (d, s).
The relocation then always runs (if d is occupied, the spare cell e exists and differs from d and s).

Encoding (a relaxation: only constraints every concrete counterexample satisfies, so UNSAT is a proof for every N >= 3):
  classes   the line is split into L = [0, d), D = {d}, R = (d, N); each part is split again by membership in the base
            intervals used by the atom and the spec: ZONE zone, windows W1 / W2 = [s_v, s_v + c) (c = number of A1; a window
            may not exist), and [d - k, d + k] for every "within k". Class sizes by inclusion-exclusion of interval
            intersections; N symbolic.
  counts    per class and type: E (non-hazard empty), H (hazard), O (A1), P (A2, ORDER only), X (other movable object),
            F (NO_PICK object of a non-atom colour); the counts of a class sum to its size.
  witnesses violation witnesses, the spare cell e and d, each with a type; the count of its class and type is >= 1 (two
            distinct O witnesses of GROUP in one class: >= 2).
  eligible  violated; satisfiable (ORDER: always; ZONE: allowed cells in the zone >= c; GROUP: W1 exists); spare cell.
  windows   an existing window has no H and no F; s_1 <= s_2; a missing window: H + F >= N div c (every block of c cells
            holds a blocker); leftmost / rightmost minimality is dropped.
  selection dest candidates: cells in the dest region whose type is a dest type; pick leftmost: no candidate in L (second
            leftmost: exactly one); rightmost / second rightmost symmetric. Source candidates: O cells in the source region.
  queries   Q1: eligible and fewer dest candidates than needed (2 for second_*, else 1);
            Q2: eligible, d is the picked dest, and fewer source candidates than needed.
Scopes: S_T (H <= 2), S_D (H <= 2 and K <= 7), S_A (no bound on H); always N >= 3 and an empty cell (K <= N - 1).
"""

from __future__ import annotations

import itertools
import time

import z3

E, H, O, P, X, F = range(6)
TYPE_NAMES = "EHOPXF"
DEST_TYPE = {"EMPTY": E, "PARTNER": P, "OTHER": X}
SCOPES = ("S_T", "S_D", "S_A")


def _zmax(*a):
    m = a[0]
    for x in a[1:]:
        m = z3.If(x > m, x, m)
    return m


def _zmin(*a):
    m = a[0]
    for x in a[1:]:
        m = z3.If(x < m, x, m)
    return m


def _uses(r, pred):
    if isinstance(r, str):
        return pred(r)
    if "and" in r:
        return any(_uses(x, pred) for x in r["and"])
    return pred(r)


def _withins(r, out):
    if isinstance(r, dict):
        if "and" in r:
            for x in r["and"]:
                _withins(x, out)
        else:
            out.add(r["within"])
    return out


def region_member(r, part, bits):
    """Static membership of a class (part in L / D / R, bits: base-set name -> bool) in a region."""
    if isinstance(r, dict):
        if "and" in r:
            return all(region_member(x, part, bits) for x in r["and"])
        return bits[f"K{r['within']}"]
    if r == "ALL":
        return True
    if r == "ZONE":
        return bits["Z"]
    if r == "NOT_ZONE":
        return not bits["Z"]
    if r == "LEFT_OF_DEST":
        return part == "L"
    if r == "RIGHT_OF_DEST":
        return part == "R"
    v = "W1" if r.endswith("G1") else "W2"
    return bits[v] if not r.startswith("NOT_") else not bits[v]


class Encoding:
    def __init__(self, spec, atom, scope, timeout_ms=60000, n_lo=3, n_hi=None):
        self.spec, self.atom, self.scope = spec, atom, scope
        s = self.s = z3.Solver()
        s.set("timeout", timeout_ms)
        N = self.N = z3.Int("N")
        d = self.d = z3.Int("d")
        c = self.c = z3.Int("c")
        s.add(N >= n_lo, 0 <= d, d < N, c >= 1)
        if n_hi is not None:
            s.add(N <= n_hi)
        t = atom[0]
        rd, rs = spec["dest"]["region"], spec["source"]["region"]
        # ---------------------------------------------------------------- base intervals
        self.iv = {}
        if t == "ZONE":
            w = z3.IntVal(2) if atom[3] == 2 else N / 2
            self.iv["Z"] = (z3.IntVal(0), w) if atom[2] == "left" else (N - w, N)
        self.win = {}
        for v, tag in (("W1", "G1"), ("W2", "G2")):
            used = _uses(rd, lambda r, tag=tag: isinstance(r, str) and r.endswith(tag)) or \
                   _uses(rs, lambda r, tag=tag: isinstance(r, str) and r.endswith(tag))
            if used or (t == "GROUP" and v == "W1"):
                hw, sv = z3.Bool(f"h{v}"), z3.Int(f"s{v}")
                s.add(z3.Implies(hw, z3.And(sv >= 0, sv + c <= N)))
                self.win[v] = (hw, sv)
                self.iv[v] = (z3.If(hw, sv, 0), z3.If(hw, sv + c, 0))
                # the side beyond the extreme end (amendment G0-1): left of W1, right of W2
                self.iv["B" + v] = (z3.IntVal(0), z3.If(hw, sv, 0)) if v == "W1" else (z3.If(hw, sv + c, 0), z3.If(hw, N, 0))
        if "W1" in self.win and "W2" in self.win:
            s.add(self.win["W1"][0] == self.win["W2"][0])            # both exist iff some run of c ok cells exists
            s.add(z3.Implies(self.win["W1"][0], self.win["W1"][1] <= self.win["W2"][1]))
        for k in sorted(_withins(rs, set()) | _withins(rd, set())):
            self.iv[f"K{k}"] = (_zmax(z3.IntVal(0), d - k), _zmin(N, d + k + 1))
        self.base = list(self.iv)
        self.parts = {"L": (z3.IntVal(0), d), "D": (d, d + 1), "R": (d + 1, N)}
        # ---------------------------------------------------------------- classes and counts
        self.classes = []
        self.n = {}
        self.size = {}
        for part in ("L", "D", "R"):
            for vals in itertools.product((True, False), repeat=len(self.base)):
                bits = dict(zip(self.base, vals))
                C = (part, vals)
                self.classes.append(C)
                ins = [b for b in self.base if bits[b]]
                outs = [b for b in self.base if not bits[b]]
                size = 0
                for r in range(len(outs) + 1):
                    for T in itertools.combinations(outs, r):
                        sets = [self.parts[part]] + [self.iv[b] for b in ins + list(T)]
                        inter = _zmax(z3.IntVal(0), _zmin(*[h for _, h in sets]) - _zmax(*[l for l, _ in sets]))
                        size = size + (-1) ** r * inter
                self.size[C] = size
                self.n[C] = [z3.Int(f"n_{part}_{''.join('1' if v else '0' for v in vals)}_{TYPE_NAMES[k]}") for k in range(6)]
                s.add(*[x >= 0 for x in self.n[C]], z3.Sum(self.n[C]) == size)
                if t != "ORDER":
                    s.add(self.n[C][P] == 0)
        self.bits_of = {C: dict(zip(self.base, C[1])) for C in self.classes}
        tot = lambda k, cls=None: z3.Sum([self.n[C][k] for C in (cls or self.classes)])
        self.tot = tot
        s.add(tot(O) == c)
        if scope in ("S_T", "S_D"):
            s.add(tot(H) <= 2)
        if scope == "S_D":
            s.add(tot(O) + tot(P) + tot(X) + tot(F) <= 7)
        # ---------------------------------------------------------------- windows
        for v, (hw, sv) in self.win.items():
            inside = [C for C in self.classes if self.bits_of[C][v]]
            s.add(z3.Implies(hw, z3.And(tot(H, inside) == 0, tot(F, inside) == 0)))
            s.add(z3.Implies(z3.Not(hw), tot(H) + tot(F) >= N / c))
            # no window (amendment G0-1): every interval J (a part intersected with base intervals) has at least
            # |J| div c blockers, since each disjoint block of c cells in J holds one
            if v == next(iter(self.win)):                         # once per encoding (both windows share hw)
                for part in ("L", "R"):
                    for r in range(len(self.base) + 1):
                        for S in itertools.combinations(self.base, r):
                            cls = [C for C in self.classes if C[0] == part and all(self.bits_of[C][b] for b in S)]
                            sets = [self.parts[part]] + [self.iv[b] for b in S]
                            ln = _zmax(z3.IntVal(0), _zmin(*[h for _, h in sets]) - _zmax(*[l for l, _ in sets]))
                            s.add(z3.Implies(z3.Not(hw), tot(H, cls) + tot(F, cls) >= ln / c))
            # extremality, local form (amendment G0-1): the cell just left of W1 / just right of W2, if any, is a
            # blocker; otherwise a run of c ok cells would start further left / right
            bp, cond = (sv - 1, z3.And(hw, sv > 0)) if v == "W1" else (sv + c, z3.And(hw, sv + c < N))
            for C in self.classes:
                s.add(z3.Implies(z3.And(cond, self.member(bp, C)), self.n[C][H] + self.n[C][F] >= 1))
            # every disjoint block of c cells beyond the extreme end holds a blocker
            side = [C for C in self.classes if self.bits_of[C]["B" + v]]
            blen = sv if v == "W1" else N - sv - c
            s.add(z3.Implies(z3.And(hw, blen >= 1), tot(H, side) + tot(F, side) >= 1 + (blen - 1) / c))   # first cell is one
            # every interval J inside that side (a part intersected with base intervals including the side) has at
            # least |J| div c blockers
            others = [b for b in self.base if b != "B" + v]
            for part in ("L", "R"):
                for r in range(len(others) + 1):
                    for S in itertools.combinations(others, r):
                        S2 = ("B" + v,) + S
                        cls = [C for C in self.classes if C[0] == part and all(self.bits_of[C][b] for b in S2)]
                        sets = [self.parts[part]] + [self.iv[b] for b in S2]
                        ln = _zmax(z3.IntVal(0), _zmin(*[h for _, h in sets]) - _zmax(*[l for l, _ in sets]))
                        s.add(z3.Implies(hw, tot(H, cls) + tot(F, cls) >= ln / c))
        # ---------------------------------------------------------------- witnesses
        self.wit = []
        if t == "ORDER":
            i, j = z3.Ints("wi wj")
            s.add(0 <= i, i < j, j < N)
            self.wit += [("wi", i, z3.IntVal(P)), ("wj", j, z3.IntVal(O))]
        elif t == "ZONE":
            j = z3.Int("wj")
            zl, zh = self.iv["Z"]
            s.add(0 <= j, j < N, z3.Not(z3.And(zl <= j, j < zh)))
            self.wit.append(("wj", j, z3.IntVal(O)))
        else:
            i, k, j = z3.Ints("wi wk wj")
            tk = z3.Int("tk")
            s.add(0 <= i, i < k, k < j, j < N, tk >= 0, tk <= 5, tk != O)
            self.wit += [("wi", i, z3.IntVal(O)), ("wk", k, tk), ("wj", j, z3.IntVal(O))]
        e = z3.Int("we")
        s.add(0 <= e, e < N)
        self.wit.append(("we", e, z3.IntVal(E)))
        td = self.td = z3.Int("td")
        s.add(td >= 0, td <= 5)
        self.wit.append(("d", d, td))
        for _, p, tp in self.wit:
            for C in self.classes:
                inc = self.member(p, C)
                for k in range(6):
                    s.add(z3.Implies(z3.And(inc, tp == k), self.n[C][k] >= 1))
        if t == "GROUP":
            for C in self.classes:
                s.add(self.n[C][O] >= z3.If(self.member(i, C), 1, 0) + z3.If(self.member(j, C), 1, 0))
        # runs (amendment G0-1): with no window, every ok witness cell lies in a run of ok cells shorter than c,
        # bounded by blockers (H / F) or the ends of the line; the same holds for an ok witness cell beyond the extreme
        # end of an existing window (left of W1, right of W2), since the cell next to that end is a blocker
        if self.win:
            hw = next(iter(self.win.values()))[0]
            okt = lambda tp: z3.Or(tp == E, tp == O, tp == P, tp == X)
            for wn, p, tp in self.wit:
                bl, br = z3.Ints(f"bl_{wn} br_{wn}")
                beyond = [z3.And(hw, self.iv["B" + v][0] <= p, p < self.iv["B" + v][1]) for v in self.win]
                cond = z3.And(okt(tp), z3.Or(z3.Not(hw), *beyond))
                s.add(z3.Implies(cond, z3.And(-1 <= bl, bl < p, p < br, br <= N, br - bl <= c)))
                for b in (bl, br):
                    for C in self.classes:
                        s.add(z3.Implies(z3.And(cond, b >= 0, b < N, self.member(b, C)), self.n[C][H] + self.n[C][F] >= 1))
                    for wn2, p2, tp2 in self.wit:
                        s.add(z3.Implies(z3.And(cond, okt(tp2)), b != p2))
        # ---------------------------------------------------------------- satisfiable
        if t == "ZONE":
            zc = [C for C in self.classes if self.bits_of[C]["Z"]]
            s.add(z3.Sum([self.size[C] for C in zc]) - tot(H, zc) - tot(F, zc) >= c)
        if t == "GROUP":
            s.add(self.win["W1"][0])

    def member(self, p, C):
        part, vals = C
        lo, hi = self.parts[part]
        conds = [lo <= p, p < hi]
        for b, v in zip(self.base, vals):
            bl, bh = self.iv[b]
            inb = z3.And(bl <= p, p < bh)
            conds.append(inb if v else z3.Not(inb))
        return z3.And(*conds)

    def cand(self, region, types, parts=("L", "D", "R")):
        cls = [C for C in self.classes if C[0] in parts and region_member(region, C[0], self.bits_of[C])]
        return z3.Sum([self.n[C][k] for C in cls for k in types]) if cls else z3.IntVal(0)

    def q1(self):
        r = self.spec["dest"]
        need = 2 if r["pick"].startswith("second") else 1
        return [self.cand(r["region"], [DEST_TYPE[x] for x in r["types"]]) < need]

    def q2(self):
        r, rs = self.spec["dest"], self.spec["source"]
        types = [DEST_TYPE[x] for x in r["types"]]
        out = [z3.Or([self.td == k for k in types])]
        for C in self.classes:
            if C[0] == "D" and not region_member(r["region"], "D", self.bits_of[C]):
                out.append(z3.Not(self.member(self.d, C)))
        pk = r["pick"]
        if pk == "leftmost":
            out.append(self.cand(r["region"], types, ("L",)) == 0)
        elif pk == "rightmost":
            out.append(self.cand(r["region"], types, ("R",)) == 0)
        elif pk == "second_leftmost":
            out.append(self.cand(r["region"], types, ("L",)) == 1)
        else:
            out.append(self.cand(r["region"], types, ("R",)) == 1)
        need = 2 if rs["pick"].startswith("second") else 1
        out.append(self.cand(rs["region"], [O]) < need)
        return out

    def model(self, m):
        ev = lambda x: m.eval(x, model_completion=True).as_long()
        out = {"N": ev(self.N), "d": ev(self.d), "c": ev(self.c), "intervals": {}, "counts": {}, "witnesses": {}}
        for b, (lo, hi) in self.iv.items():
            out["intervals"][b] = [ev(lo), ev(hi)]
        for C in self.classes:
            cnt = [ev(x) for x in self.n[C]]
            if any(cnt):
                out["counts"][C[0] + "|" + "".join("1" if v else "0" for v in C[1])] = cnt
        for name, p, tp in self.wit:
            out["witnesses"][name] = [ev(p), ev(tp)]
        return out


def prove(spec, atom, scope, timeout_ms=60000, n_lo=3, n_hi=None):
    """Returns {"status": PROVED | NOT_PROVED | UNKNOWN, "query", "model", "time_s"}."""
    t0 = time.perf_counter()
    res = {"status": "PROVED", "query": None, "model": None}
    for qn in ("q1", "q2"):
        enc = Encoding(spec, atom, scope, timeout_ms, n_lo, n_hi)
        r = enc.s.check(*getattr(enc, qn)())
        if r == z3.sat:
            res = {"status": "NOT_PROVED", "query": qn, "model": enc.model(enc.s.model())}
            break
        if r == z3.unknown:
            res = {"status": "UNKNOWN", "query": qn, "model": None, "reason": enc.s.reason_unknown()}
    res["time_s"] = round(time.perf_counter() - t0, 3)
    return res


def models(spec, atom, scope, k=20, timeout_ms=60000, n_lo=3, n_hi=None):
    """Up to k distinct relaxed models (blocking the count signature) for each query that is SAT."""
    out = []
    for qn in ("q1", "q2"):
        enc = Encoding(spec, atom, scope, timeout_ms, n_lo, n_hi)
        enc.s.add(*getattr(enc, qn)())
        for _ in range(k):
            if enc.s.check() != z3.sat:
                break
            m = enc.s.model()
            out.append({"query": qn, "model": enc.model(m)})
            sig = [enc.N == m.eval(enc.N, model_completion=True)] + \
                  [x == m.eval(x, model_completion=True) for C in enc.classes for x in enc.n[C]]
            enc.s.add(z3.Not(z3.And(*sig)))
    return out
