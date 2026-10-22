"""Structure meta-language M for ECO (PROTOCOL.md section 3, item 5) and its learner. AGENT SIDE.

A structure is an instantiated hypothesis form whose parameters were fitted to the agent's own episodic memory:
  M1 Counter  per-instance hidden count of event E on kind K (saturating at theta), decaying by 1 every D steps without E, triggering an
              observable effect (appear / vanish / feature change of kind K2 near the instance or near a context kind
              K3 within distance dctx) when the count reaches theta; optionally reset to 0 on trigger.
              Predicates: cnt[K]>=v (some known instance has count >= v), v = 1..theta.
  M2 Bit      per-instance hidden bit, set by event E on kind K when a context condition Q holds (Q: another kind K'
              within distance d, optionally with a learned predicate on it), cleared by the next E, which then
              produces an effect; timeout T. Predicate: bit[K].
  M3 Place    objects of kind K keep their cell while invisible (they reappear where they vanished).
              Predicate: memnear[K] (the agent is next to a remembered K cell where K is not visible now).
  M4 Pair     event E on an instance of kind K produces an effect at a distant instance of kind Kb (a hidden pairing).
              Predicate: pairfx[K>Kb] (an effect was produced at a partner within the last W steps).
Every structure exports: predicates, a tracker replayable from (observation, action) histories, an achievement
recipe for each predicate, the evidence (event times) it was fitted on, and its fit statistics.
Effects are 'timed' only when the effect cell had been seen at most 3 steps before (the appearance's 'gap').
"""

from __future__ import annotations

import itertools
import math
from collections import Counter as Cnt, defaultdict
from statistics import NormalDist

W = 6                 # effect window (steps)
ACT = ("poke", "pick", "drop", "consume")
FX = ("appear", "vanish", "feat")
THETAS, DECAYS = (1, 2, 3, 4), (10, 25, 50, 100, 10 ** 9)


def cheb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


class Structure:
    form = "?"

    def __init__(self, sid, params, stats, evidence, t_created):
        self.sid, self.params, self.stats, self.evidence, self.t_created = sid, params, stats, evidence, t_created
        self.reset_tracker()

    def describe(self):
        return {"struct_id": self.sid, "form": self.form, "params": self.params, "stats": self.stats,
                "predicates": self.predicates(), "t_created": self.t_created, "data_provenance": self.evidence[:200],
                "n_evidence": len(self.evidence)}

    def reset_tracker(self):
        pass

    def step(self, mem, new_events, structs):
        pass

    def predicates(self):
        return []

    def value(self, name, mem, structs):
        return False

    def recipe(self, name, mem, structs):
        return None


# ---------------------------------------------------------------- M1
class Counter(Structure):
    form = "M1"

    def reset_tracker(self):
        self.cnt = {}            # (frame, x, y) -> [count, mark]

    def _decay(self, k, t):
        c = self.cnt.get(k)
        if c is None:
            return 0
        D = self.params["D"]
        while c[0] > 0 and t - c[1] >= D:
            c[0] -= 1
            c[1] += D
        return c[0]

    def _ctx_ok(self, mem, cell):
        K3 = self.params.get("ctx")
        if K3 is None:
            return True
        return any(cheb(cell, c) <= self.params["dctx"] for c in mem.instances(K3))

    def step(self, mem, new_events, structs):
        p = self.params
        for e in new_events:
            if e["type"] == p["E"] and e["kind"] == p["K"]:
                k = (e["frame"],) + tuple(e["cell"])
                self._decay(k, e["t"])
                c = self.cnt.setdefault(k, [0, e["t"]])
                c[0] = min(c[0] + 1, p["theta"])                 # the count saturates at its trigger level
                c[1] = e["t"]
                if p["reset"] and c[0] >= p["theta"] and self._ctx_ok(mem, tuple(e["cell"])):
                    c[0] = 0
            elif p["reset"] and e["type"] == p["ftype"] and e["kind"] == p["K2"]:
                # the predicted effect was observed: a full count near it has been used up (context possibly unseen)
                for k, c in self.cnt.items():
                    if k[0] == e["frame"] and c[0] >= p["theta"] and cheb(k[1:], e["cell"]) <= 3 and e["t"] - c[1] <= W + 1:
                        c[0] = 0

    def count(self, mem, cell):
        return self._decay((mem.frame,) + tuple(cell), mem.t)

    def predicates(self):
        K = self.params["K"]
        top = self.params["theta"] - (1 if self.params["reset"] else 0)
        return [f"cnt[{K}]>={v}" for v in range(1, max(top, 1) + 1)]

    def value(self, name, mem, structs):
        v = int(name.split(">=")[1])
        return any(self.count(mem, c) >= v for c in mem.instances(self.params["K"]))

    def recipe(self, name, mem, structs):
        """Perform E on the instance closest to the target count (prefer instances without the context, so that a
        resetting trigger does not consume the count), until the count reaches v."""
        v = int(name.split(">=")[1])
        insts = list(mem.instances(self.params["K"]))
        if not insts:
            return ("explore_for", self.params["K"])
        def key(c):
            return (-(self.count(mem, c)), (self._ctx_ok(mem, c) and self.params["reset"]), cheb(c, mem.pos))
        target = min(insts, key=key)
        return ("act", target, self.params["E"].upper())


# ---------------------------------------------------------------- M2
class Bit(Structure):
    form = "M2"

    def reset_tracker(self):
        self.bit = {}            # (frame, x, y) -> t_set

    def q_holds(self, mem, cell, structs):
        p = self.params
        for c in mem.instances(p["Kq"]):
            if cheb(cell, c) <= p["dq"]:
                if p.get("q_pred") is None:
                    return True
                s = structs.get(p["q_struct"])
                if s is not None and s.count(mem, c) >= p["q_v"]:
                    return True
        return False

    def step(self, mem, new_events, structs):
        p = self.params
        for e in new_events:
            if e["type"] == p["E"] and e["kind"] == p["K"]:
                k = (e["frame"],) + tuple(e["cell"])
                if k in self.bit and e["t"] - self.bit[k] <= p["T"]:
                    del self.bit[k]                       # the second event uses (and clears) the bit
                elif self.q_holds(mem, tuple(e["cell"]), structs):
                    self.bit[k] = e["t"]
        for k in [k for k, t0 in self.bit.items() if mem.t - t0 > p["T"]]:
            del self.bit[k]

    def predicates(self):
        return [f"bit[{self.params['K']}]"]

    def value(self, name, mem, structs):
        return any(k[0] == mem.frame for k in self.bit)

    def recipe(self, name, mem, structs):
        p = self.params
        insts = list(mem.instances(p["K"]))
        if not insts:
            return ("explore_for", p["K"])
        ok = [c for c in insts if self.q_holds(mem, c, structs)]
        if ok:
            return ("act", min(ok, key=lambda c: cheb(c, mem.pos)), p["E"].upper())
        if p.get("q_pred") is not None:                    # make the context true at a located neighbour first
            qs = structs.get(p["q_struct"])
            pairs = [(c, q) for c in insts for q in mem.instances(p["Kq"]) if cheb(c, q) <= p["dq"]]
            if pairs and qs is not None:
                c, q = min(pairs, key=lambda cq: (-qs.count(mem, cq[1]), cheb(cq[1], mem.pos)))
                return ("act", q, qs.params["E"].upper())
        return ("explore_for", p["K"])


# ---------------------------------------------------------------- M3
class Place(Structure):
    form = "M3"

    def predicates(self):
        return [f"memnear[{self.params['K']}]"]

    def remembered(self, mem):
        K = self.params["K"]
        cells = set()
        for e in mem.events:
            if e.get("frame") == mem.frame and e["type"] in ("appear", "vanish") and e["kind"] == K:
                cells.add(tuple(e["cell"]))
        return cells

    def value(self, name, mem, structs):
        vis = mem.instances(self.params["K"])
        for c in self.remembered(mem):
            if cheb(c, mem.pos) <= 1 and c not in vis:
                return True
        return False

    def recipe(self, name, mem, structs):
        cells = self.remembered(mem)
        if not cells:
            return ("explore_for", self.params["K"])
        return ("goto", min(cells, key=lambda c: cheb(c, mem.pos)))


# ---------------------------------------------------------------- M4
class Pair(Structure):
    form = "M4"

    def reset_tracker(self):
        self.last_fx = -10 ** 9

    def step(self, mem, new_events, structs):
        p = self.params
        for e in new_events:
            if e["type"] == p["ftype"] and e["kind"] == p["Kb"]:
                acts = [a for a in mem.events[-40:] if a["type"] == p["E"] and a["kind"] == p["K"] and 0 <= e["t"] - a["t"] <= W
                        and cheb(a["cell"], e["cell"]) > 2]
                if acts:
                    self.last_fx = e["t"]

    def predicates(self):
        return [f"pairfx[{self.params['K']}>{self.params['Kb']}]"]

    def value(self, name, mem, structs):
        return mem.t - self.last_fx <= W

    def recipe(self, name, mem, structs):
        insts = list(mem.instances(self.params["K"]))
        if not insts:
            return ("explore_for", self.params["K"])
        return ("act", min(insts, key=lambda c: cheb(c, mem.pos)), self.params["E"].upper())


FORMS = {"M1": Counter, "M2": Bit, "M3": Place, "M4": Pair}


# ---------------------------------------------------------------- learner
class Learner:
    """Fits M1-M4 to the agent's episodic memory. `fit` returns new structures (not already held).

    Amendment A3: M1 and M2 hypotheses are selected by a likelihood-ratio test instead of a precision threshold.
    Every testable event is classified by the hypothesis as a trigger or not; an effect counts for an M1 trigger only
    if its possible occurrence interval (observation step minus the gap since the cell was last seen) contains the
    trigger step plus the hypothesis' delay (delta, 1..W, the M5 delay of the meta-language). The model has one effect
    probability after triggers (q1) and one after other events (q0); 2 x log-likelihood ratio against a single common
    probability is the score. A hypothesis is accepted when q1 > q0, it has >= min_support confirmed triggers (M1) or
    >= 2 positive pairs (M2), and the score exceeds the chi-square(1) critical value at level alpha / (number of
    hypotheses scored in this fit). Partial observability lowers q1 but not the contrast, which the previous
    precision >= 0.75 rule could not tolerate (Gate 3 learner positive control, g3_learner_control.py).
    min_prec is kept for compatibility and is no longer used by M1 / M2."""

    def __init__(self, window=10000, min_prec=0.75, min_support=3, allowed=("M1", "M2", "M3", "M4"), blocked=(), alpha=0.01):
        self.window, self.min_prec, self.min_support, self.alpha = window, min_prec, min_support, alpha
        self.allowed, self.blocked = set(allowed), set(blocked)        # blocked: {(form, K)} (do(s absent))
        self.next_sid = 0

    # -------------------------------------------------- helpers (indexed; results identical to plain scans)
    def _poses_by_t(self, mem):
        key = (id(mem), len(mem.poses))
        if getattr(self, "_pose_key", None) != key:
            self._poses, self._pose_key = {t: (f, x, y) for (t, f, x, y) in mem.poses}, key
        return self._poses

    def _testable(self, poses, frame, cell, t0, t1, r=2):
        for t in range(t0, t1 + 1):
            p = poses.get(t)
            if p and p[0] == frame and cheb((p[1], p[2]), cell) <= r:
                return True
        return False

    def _cell_index(self, mem):
        key = (id(mem), mem.t, len(mem.cells))
        if getattr(self, "_idx_key", None) != key:
            idx = defaultdict(list)
            for (f, x, y), v in mem.cells.items():
                if v[1]:
                    idx[(f, v[1])].append((x, y))
            self._idx, self._idx_key = idx, key
        return self._idx

    def _near_kind(self, mem, frame, cell, kind, d):
        return any(cheb(c, cell) <= d for c in self._cell_index(mem).get((frame, kind), ()))

    def fit(self, mem, have, t_now):
        ev = [e for e in mem.events if e["t"] >= t_now - self.window]
        out = []
        held = {(s.form, s.params.get("K")) for s in have.values()}
        if "M1" in self.allowed:
            s = self.fit_m1(mem, ev, held, t_now)
            if s:
                out.append(s)
        if "M2" in self.allowed:
            s = self.fit_m2(mem, ev, held, have, t_now)
            if s:
                out.append(s)
        if "M3" in self.allowed:
            s = self.fit_m3(mem, ev, held, t_now)
            if s:
                out.append(s)
        if "M4" in self.allowed:
            s = self.fit_m4(mem, ev, held, t_now)
            if s:
                out.append(s)
        return out

    def _new(self, cls, params, stats, evidence, t_now):
        s = cls(self.next_sid, params, stats, evidence, t_now)
        self.next_sid += 1
        return s

    @staticmethod
    def _ll(k, n):
        if n == 0:
            return 0.0
        q = (k + 0.5) / (n + 1)
        return k * math.log(q) + (n - k) * math.log(1 - q)

    def _lr2(self, k1, n1, k0, n0):
        return 2 * (self._ll(k1, n1) + self._ll(k0, n0) - self._ll(k1 + k0, n1 + n0))

    def critical(self, n_hyp):
        return NormalDist().inv_cdf(1 - self.alpha / max(n_hyp, 1) / 2) ** 2

    # -------------------------------------------------- M1
    def m1_rows(self, mem, ev, K, E, ftype, K2, ctx_opts, poses, combos=None):
        """Every (ctx, theta, D, reset, delta) hypothesis for one (K, E, ftype, K2): rows
        (lr2, k1, n1, k0, n0, params, evidence times)."""
        inst = defaultdict(list)
        for a in ev:
            if a["type"] == E and a.get("kind") == K:
                inst[(a["frame"],) + tuple(a["cell"])].append(a["t"])
        order = [(k, t) for k, ts in inst.items() for t in ts]
        if not order:
            return []
        T = 0
        for i, ((fr, x, y), t) in enumerate(order):
            if self._testable(poses, fr, (x, y), t, t + W, r=1):
                T |= 1 << i
        fx_by_frame = defaultdict(list)
        for f in ev:
            if f["type"] == ftype and f.get("kind") == K2 and f.get("gap", 99) <= 3:
                fx_by_frame[f["frame"]].append(f)
        Y = {d: 0 for d in range(1, W + 1)}
        for i, ((fr, x, y), t) in enumerate(order):
            for f in fx_by_frame.get(fr, ()):
                if 0 < cheb(f["cell"], (x, y)) <= 3:
                    lo, hi = f["t"] - f["gap"] + 1, f["t"]
                    for d in range(max(1, lo - t), min(W, hi - t) + 1):
                        Y[d] |= 1 << i
        ctxmask = {}
        for (ctx, dctx) in ctx_opts:
            m = 0
            for i, ((fr, x, y), t) in enumerate(order):
                if ctx is None or self._near_kind(mem, fr, (x, y), ctx, dctx):
                    m |= 1 << i
            ctxmask[(ctx, dctx)] = m
        times = [t for _, t in order]
        rows = []
        for theta, D, reset in (combos or itertools.product(THETAS, DECAYS, (True, False))):
            for (ctx, dctx), cm in ctxmask.items():
                F = 0
                i = 0
                for k, ts in inst.items():
                    ok = (cm >> i) & 1
                    c, mark = 0, ts[0]
                    for t in ts:
                        while c > 0 and t - mark >= D:
                            c -= 1
                            mark += D
                        c = min(c + 1, theta)
                        mark = t
                        if c >= theta:
                            if ok:
                                F |= 1 << i
                            if reset and ok:
                                c = 0
                        i += 1
                FT, NT = F & T, T & ~F
                n1, n0 = FT.bit_count(), NT.bit_count()
                for d, Yd in Y.items():
                    k1, k0 = (FT & Yd).bit_count(), (NT & Yd).bit_count()
                    if n1 == 0 or k1 * (n0 + 1) <= k0 * (n1 + 1):
                        continue
                    ev_t = [times[j] for j in range(len(order)) if (FT & Yd) >> j & 1]
                    rows.append((self._lr2(k1, n1, k0, n0), k1, n1, k0, n0,
                                 {"K": K, "E": E, "theta": theta, "D": D, "reset": reset, "ctx": ctx, "dctx": dctx,
                                  "ftype": ftype, "K2": K2, "delta": d}, ev_t))
        return rows

    def m1_ctx_opts(self, mem, K):
        kinds_seen = {v[1] for v in mem.cells.values() if v[1]}
        return [(None, 0)] + [(k3, d) for k3 in sorted(kinds_seen) if k3 != K for d in (1, 2)]

    def m1_triples(self, ev):
        acts = [e for e in ev if e["type"] in ACT and e["kind"]]
        fxs = [e for e in ev if e["type"] in FX and e.get("gap", 99) <= 3]
        acts_by_frame = defaultdict(list)
        for a in acts:
            acts_by_frame[a["frame"]].append(a)
        trip = Cnt()
        for f in fxs:
            for a in acts_by_frame.get(f["frame"], ()):
                if 0 <= f["t"] - a["t"] <= W and 0 < cheb(a["cell"], f["cell"]) <= 3:
                    trip[(a["kind"], a["type"], f["type"], f["kind"])] += 1
        return trip

    def fit_m1(self, mem, ev, held, t_now):
        poses = self._poses_by_t(mem)
        rows = []
        for (K, E, ftype, K2), n in self.m1_triples(ev).most_common(6):
            if n < self.min_support or ("M1", K) in held or ("M1", K) in self.blocked:
                continue
            rows += self.m1_rows(mem, ev, K, E, ftype, K2, self.m1_ctx_opts(mem, K), poses)
        if not rows:
            return None
        n_hyp = len(rows)
        crit = self.critical(n_hyp)
        ok = [r for r in rows if r[0] >= crit and r[1] >= self.min_support]
        if not ok:
            return None
        lr2, k1, n1, k0, n0, params, ev_t = max(ok, key=lambda r: (round(r[0], 6), r[1], -r[5]["theta"], r[5]["D"] == 10 ** 9,
                                                                    not r[5]["reset"], r[5]["ctx"] is None, -r[5]["delta"]))
        stats = {"lr2": round(lr2, 3), "critical": round(crit, 3), "hypotheses": n_hyp, "precision": round(k1 / n1, 3),
                 "base_rate": round(k0 / n0, 3) if n0 else None, "confirmed": k1, "testable": n1, "other_events": n0,
                 "other_effects": k0}
        return self._new(Counter, params, stats, ev_t, t_now)

    # -------------------------------------------------- M2
    def fit_m2(self, mem, ev, held, have, t_now):
        acts = [e for e in ev if e["type"] in ACT and e["kind"]]
        fxs = [e for e in ev if e["type"] in FX and e.get("gap", 99) <= 3]
        fx_by_frame = defaultdict(list)
        for f in fxs:
            fx_by_frame[f["frame"]].append(f)
        by_inst = defaultdict(list)
        for a in acts:
            by_inst[(a["frame"], a["type"], a["kind"]) + tuple(a["cell"])].append(a)
        counters = {s.params["K"]: s for s in have.values() if s.form == "M1"}
        cand_fx = Cnt()
        for a in acts:
            for f in fx_by_frame.get(a["frame"], ()):
                if 0 <= f["t"] - a["t"] <= W and 0 < cheb(a["cell"], f["cell"]) <= 3:
                    cand_fx[(a["kind"], a["type"], f["type"], f["kind"])] += 1
        rows = []
        for (K, E, ftype, K2), n in cand_fx.most_common(8):
            if n < 2 or ("M2", K) in held or ("M2", K) in self.blocked:
                continue

            def fx_after(e, until=None):
                hi = W if until is None else min(W, until - e["t"] - 1)
                return any(f["kind"] == K2 and f["type"] == ftype and 0 <= f["t"] - e["t"] <= hi
                           and 0 < cheb(f["cell"], e["cell"]) <= 3 for f in fx_by_frame.get(e["frame"], ()))
            pairs = []
            for key, lst in by_inst.items():
                if key[1] != E or key[2] != K:
                    continue
                for e1, e2 in zip(lst, lst[1:]):
                    if e2["t"] - e1["t"] > 300:
                        continue
                    if not fx_after(e1, until=e2["t"]):          # e1's own effect window ends at the next event
                        pairs.append((e1, e2, fx_after(e2)))
            if sum(1 for p in pairs if p[2]) < 2:
                continue
            kinds = {v[1] for v in mem.cells.values() if v[1] and v[1] != K}
            for Kq, dq in itertools.product(sorted(kinds), (1, 2)):
                q_opts = [(None, None, None)]
                if Kq in counters:
                    s = counters[Kq]
                    q_opts += [(f"cnt[{Kq}]>={v}", s.sid, v) for v in range(1, 5)]
                for q_pred, q_struct, q_v in q_opts:
                    pos = neg = posn = negn = 0
                    evid = []
                    for e1, e2, y in pairs:
                        q = self._q_at(mem, e1, Kq, dq, counters.get(Kq) if q_pred else None, q_v)
                        if q:
                            pos += y
                            neg += not y
                            if y:
                                evid.append(e2["t"])
                        else:
                            posn += y
                            negn += not y
                    if pos + neg == 0 or pos * (posn + negn + 1) <= posn * (pos + neg + 1):
                        continue
                    T = max(e2["t"] - e1["t"] for e1, e2, y in pairs if y)
                    T = min(x for x in (50, 150, 300, 10 ** 9) if x >= T)
                    rows.append((self._lr2(pos, pos + neg, posn, posn + negn), pos, neg, posn, negn,
                                 {"K": K, "E": E, "Kq": Kq, "dq": dq, "q_pred": q_pred, "q_struct": q_struct, "q_v": q_v,
                                  "T": T, "ftype": ftype, "K2": K2}, evid))
        if not rows:
            return None
        n_hyp = len(rows)
        crit = self.critical(n_hyp)
        ok = [r for r in rows if r[0] >= crit and r[1] >= 2]
        if not ok:
            return None
        lr2, pos, neg, posn, negn, params, evid = max(ok, key=lambda r: (round(r[0], 6), r[1], r[5]["q_pred"] is None))
        stats = {"lr2": round(lr2, 3), "critical": round(crit, 3), "hypotheses": n_hyp, "precision": round(pos / (pos + neg), 3),
                 "positives": pos, "negatives": neg, "without_q": [posn, negn]}
        return self._new(Bit, params, stats, evid, t_now)

    def _q_at(self, mem, e1, Kq, dq, counter, q_v):
        """Context at the time of e1: a Kq instance within dq (and, if a counter is given, with count >= q_v then)."""
        cells = [c for c in self._cell_index(mem).get((e1["frame"], Kq), ()) if cheb(c, e1["cell"]) <= dq]
        if not cells:
            return False
        if counter is None:
            return True
        return any(self._count_at(mem, counter, e1["frame"], c, e1["t"]) >= q_v for c in cells)

    def _count_at(self, mem, counter, frame, cell, t):
        key = (id(mem), len(mem.events))
        if getattr(self, "_ev_key", None) != key:
            idx = defaultdict(list)
            for a in mem.events:
                if a.get("cell") is not None and a.get("kind"):
                    idx[(a["type"], a["kind"], a["frame"], tuple(a["cell"]))].append(a["t"])
            self._ev_idx, self._ev_key = idx, key
        p = counter.params
        c, mark = 0, None
        for at in self._ev_idx.get((p["E"], p["K"], frame, tuple(cell)), ()):
            if at > t:
                break
            if mark is not None:
                while c > 0 and at - mark >= p["D"]:
                    c -= 1
                    mark += p["D"]
            c = min(c + 1, p["theta"])
            mark = at
            if p["reset"] and c >= p["theta"] and (p.get("ctx") is None or self._near_kind(mem, frame, cell, p["ctx"], p["dctx"])):
                c = 0
        if mark is not None:
            while c > 0 and t - mark >= p["D"]:
                c -= 1
                mark += p["D"]
        return c

    # -------------------------------------------------- M3
    def fit_m3(self, mem, ev, held, t_now):
        van = defaultdict(list)
        reapp = Cnt()
        evid = defaultdict(list)
        for e in ev:
            if "cell" not in e:
                continue
            key = (e["frame"],) + tuple(e["cell"])
            if e["type"] == "vanish":
                van[key].append(e["kind"])
            elif e["type"] == "appear" and e["kind"] in van.get(key, []):
                reapp[e["kind"]] += 1
                evid[e["kind"]].append(e["t"])
        for K, n in reapp.most_common():
            if n >= 2 and ("M3", K) not in held and ("M3", K) not in self.blocked:
                return self._new(Place, {"K": K}, {"reappearances": n}, evid[K], t_now)
        return None

    # -------------------------------------------------- M4
    def fit_m4(self, mem, ev, held, t_now):
        acts = [e for e in ev if e["type"] in ACT and e["kind"]]
        fxs = [e for e in ev if e["type"] in FX and e.get("gap", 99) <= 3]
        trip = Cnt()
        evid = defaultdict(list)
        for f in fxs:
            for a in acts:
                if a["frame"] == f["frame"] and 0 <= f["t"] - a["t"] <= W and cheb(a["cell"], f["cell"]) > 3:
                    trip[(a["kind"], a["type"], f["type"], f["kind"])] += 1
                    evid[(a["kind"], a["type"], f["type"], f["kind"])].append(f["t"])
        for (K, E, ftype, Kb), n in trip.most_common(3):
            if n >= self.min_support and ("M4", K) not in held and ("M4", K) not in self.blocked:
                # control: the same effect must be rarer without a preceding distant act
                base = sum(1 for f in fxs if f["kind"] == Kb and f["type"] == ftype)
                if n / max(base, 1) >= 0.6:
                    return self._new(Pair, {"K": K, "E": E, "Kb": Kb, "ftype": ftype}, {"cooccurrences": n, "effects": base},
                                     evid[(K, E, ftype, Kb)], t_now)
        return None
