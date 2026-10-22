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
from collections import Counter as Cnt, defaultdict

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
    """Fits M1-M4 to the agent's episodic memory. `fit` returns new structures (not already held)."""

    def __init__(self, window=10000, min_prec=0.75, min_support=3, allowed=("M1", "M2", "M3", "M4"), blocked=()):
        self.window, self.min_prec, self.min_support = window, min_prec, min_support
        self.allowed, self.blocked = set(allowed), set(blocked)        # blocked: {(form, K)} (do(s absent))
        self.next_sid = 0

    # -------------------------------------------------- helpers
    def _poses_by_t(self, mem):
        return {t: (f, x, y) for (t, f, x, y) in mem.poses}

    def _testable(self, poses, frame, cell, t0, t1, r=2):
        for t in range(t0, t1 + 1):
            p = poses.get(t)
            if p and p[0] == frame and cheb((p[1], p[2]), cell) <= r:
                return True
        return False

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

    # -------------------------------------------------- M1
    def fit_m1(self, mem, ev, held, t_now):
        acts = [e for e in ev if e["type"] in ACT and e["kind"]]
        fxs = [e for e in ev if e["type"] in FX and e.get("gap", 99) <= 3]
        trip = Cnt()
        for f in fxs:
            for a in acts:
                if a["frame"] == f["frame"] and 0 <= f["t"] - a["t"] <= W and 0 < cheb(a["cell"], f["cell"]) <= 3:
                    trip[(a["kind"], a["type"], f["type"], f["kind"])] += 1
        poses = self._poses_by_t(mem)
        best = None
        for (K, E, ftype, K2), n in trip.most_common(6):
            if n < self.min_support or ("M1", K) in held or ("M1", K) in self.blocked:
                continue
            inst_ev = defaultdict(list)
            for a in acts:
                if a["kind"] == K and a["type"] == E:
                    inst_ev[(a["frame"],) + tuple(a["cell"])].append(a["t"])
            fx_k = [f for f in fxs if f["kind"] == K2 and f["type"] == ftype]
            kinds_seen = {v[1] for v in mem.cells.values() if v[1]}
            ctx_opts = [(None, 0)] + [(k3, d) for k3 in sorted(kinds_seen) if k3 != K for d in (1, 2)]
            ctx_ok = {}
            for (ctx, dctx) in ctx_opts:
                for (fr, x, y) in inst_ev:
                    ctx_ok[(ctx, dctx, fr, x, y)] = ctx is None or self._near_kind(mem, fr, (x, y), ctx, dctx)
            for (ctx, dctx), theta, D, reset in itertools.product(ctx_opts, THETAS, DECAYS, (True, False)):
                pred = conf = test = 0
                evid = []
                for (fr, x, y), times in inst_ev.items():
                    cell = (x, y)
                    if not ctx_ok[(ctx, dctx, fr, x, y)]:
                        continue
                    c, mark = 0, times[0]
                    for t in times:
                        while c > 0 and t - mark >= D:
                            c -= 1
                            mark += D
                        c = min(c + 1, theta)
                        mark = t
                        if c >= theta:
                            pred += 1
                            if self._testable(poses, fr, cell, t, t + W, r=1):
                                test += 1
                                hit = any(f["frame"] == fr and 0 <= f["t"] - t <= W + 1 and 0 < cheb(f["cell"], cell) <= 3 for f in fx_k)
                                if hit:
                                    conf += 1
                                    evid.append(t)
                            if reset:
                                c = 0
                if test >= 4 and conf >= self.min_support:
                    prec = conf / test
                    score = (prec >= self.min_prec, prec, conf, -theta, D == 10 ** 9, not reset, ctx is None)
                    if best is None or score > best[0]:
                        best = (score, {"K": K, "E": E, "theta": theta, "D": D, "reset": reset, "ctx": ctx, "dctx": dctx,
                                        "ftype": ftype, "K2": K2},
                                {"precision": round(prec, 3), "confirmed": conf, "testable": test, "predicted": pred}, evid)
        if best and best[0][0]:
            return self._new(Counter, best[1], best[2], best[3], t_now)
        return None

    def _near_kind(self, mem, frame, cell, kind, d):
        return any(k[0] == frame and v[1] == kind and cheb((k[1], k[2]), cell) <= d for k, v in mem.cells.items())

    # -------------------------------------------------- M2
    def fit_m2(self, mem, ev, held, have, t_now):
        acts = [e for e in ev if e["type"] in ACT and e["kind"]]
        fxs = [e for e in ev if e["type"] in FX and e.get("gap", 99) <= 3]
        by_inst = defaultdict(list)
        for a in acts:
            by_inst[(a["frame"], a["type"], a["kind"]) + tuple(a["cell"])].append(a)
        counters = {s.params["K"]: s for s in have.values() if s.form == "M1"}
        best = None
        cand_fx = Cnt()
        for a in acts:
            for f in fxs:
                if f["frame"] == a["frame"] and 0 <= f["t"] - a["t"] <= W and 0 < cheb(a["cell"], f["cell"]) <= 3:
                    cand_fx[(a["kind"], a["type"], f["type"], f["kind"])] += 1
        for (K, E, ftype, K2), n in cand_fx.most_common(8):
            if n < 2 or ("M2", K) in held or ("M2", K) in self.blocked:
                continue
            pairs = []
            for key, lst in by_inst.items():
                if key[1] != E or key[2] != K:
                    continue
                for e1, e2 in zip(lst, lst[1:]):
                    if e2["t"] - e1["t"] > 300:
                        continue
                    fx1 = any(f["frame"] == e1["frame"] and f["kind"] == K2 and f["type"] == ftype and 0 <= f["t"] - e1["t"] <= W
                              and 0 < cheb(f["cell"], e1["cell"]) <= 3 for f in fxs)
                    fx2 = any(f["frame"] == e2["frame"] and f["kind"] == K2 and f["type"] == ftype and 0 <= f["t"] - e2["t"] <= W
                              and 0 < cheb(f["cell"], e2["cell"]) <= 3 for f in fxs)
                    if not fx1:
                        pairs.append((e1, e2, fx2))
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
                    if pos >= 2 and pos / (pos + neg) >= self.min_prec and (posn + negn == 0 or posn / (posn + negn) <= 0.25):
                        T = max(e2["t"] - e1["t"] for e1, e2, y in pairs if y)
                        T = min(x for x in (50, 150, 300, 10 ** 9) if x >= T)
                        score = (pos / (pos + neg), pos, q_pred is None)
                        if best is None or score > best[0]:
                            best = (score, {"K": K, "E": E, "Kq": Kq, "dq": dq, "q_pred": q_pred, "q_struct": q_struct, "q_v": q_v,
                                            "T": T, "ftype": ftype, "K2": K2},
                                    {"precision": round(pos / (pos + neg), 3), "positives": pos, "negatives": neg,
                                     "without_q": [posn, negn]}, evid)
        if best:
            return self._new(Bit, best[1], best[2], best[3], t_now)
        return None

    def _q_at(self, mem, e1, Kq, dq, counter, q_v):
        """Context at the time of e1: a Kq instance within dq (and, if a counter is given, with count >= q_v then)."""
        cells = [(k[1], k[2]) for k, v in mem.cells.items() if k[0] == e1["frame"] and v[1] == Kq and cheb((k[1], k[2]), e1["cell"]) <= dq]
        if not cells:
            return False
        if counter is None:
            return True
        for c in cells:
            if self._count_at(mem, counter, e1["frame"], c, e1["t"]) >= q_v:
                return True
        return False

    def _count_at(self, mem, counter, frame, cell, t):
        p = counter.params
        c, mark = 0, None
        for a in mem.events:
            if a["t"] > t:
                break
            if a["type"] == p["E"] and a["kind"] == p["K"] and a["frame"] == frame and tuple(a["cell"]) == tuple(cell):
                if mark is not None:
                    while c > 0 and a["t"] - mark >= p["D"]:
                        c -= 1
                        mark += p["D"]
                c = min(c + 1, p["theta"])
                mark = a["t"]
                if p["reset"] and c >= p["theta"] and (p.get("ctx") is None or
                                                       self._near_kind(mem, frame, cell, p["ctx"], p["dctx"])):
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
