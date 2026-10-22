"""Gate 3 candidate for Mission 07 (PROTOCOL.md section 4.2, amendment A2) and its ablations. AGENT SIDE.

The candidate shares the substrate, the structure meta-language M, the learner and the executor with every baseline
(agent.py, structures.py, substrate.py). What it adds is organisation:

1. Prediction monitor. A held structure issues a prediction whenever its tracker fires (an M1 count reaching its
   trigger level; an M2 event on an instance whose bit is set). A timed effect (appear / vanish / feature change seen
   at most 3 steps earlier, not at the acted cell) that matches an open prediction is explained; one that matches
   none is an anomaly. A prediction that expires while the agent was near the cell is a failure of its structure.
2. Experiment goals derived from the forms of M (candidate-specific designer knowledge, KNOWLEDGE_PROVENANCE.md):
     X1   (K, E, c)      perform E on one rested instance of K whose surroundings (kinds within 2) include c
                         ('none': no other kind within 2) up to 4 times in a row, then watch W steps;
     X1s  (s, spacing)   perform the event of M1 structure s on an instance satisfying its context at the spacing that
                         splits the M1 parameter sets fitting the data about equally well (discriminating experiment);
     X2   (K, E, Kq, p)  make p true at a Kq instance next to a K instance (p: a learned instance predicate on Kq,
                         or None for mere presence), perform E on the K instance twice 3 steps apart, then watch.
   Untested keys have value 1; each trial lowers it by 1/3; (K, E) pairs that preceded an anomaly get a decaying
   bonus. X2 keys with a learned p exist only once that structure exists: the experiment language grows with the
   goal language (OC1 removes them).
3. Goal choice when no goal is active: needs first (the shared override below 35, and a need term below 60);
   otherwise one sample, in proportion to weight, from the feasible experiment keys (weight = value) and the
   mastery goals over L(S) (weight = learning progress, optimistic for new predicates, + explanatory gap of the
   owning structure + 0.05).
4. Acquisition: after each experiment (at most every 100 steps) and every 2,000 steps (learner.fit, the shared
   learner); revision of a held M1 or M2 structure whose predictions fail (>= 3 failures among its last 8): refit
   its kind on the learner's full window and replace it when the refit is better on the same data (rev1).
5. Experiment values (rev1): a key whose trials were followed by a timed effect near its targets is replicated up to
   8 times, other keys 3 times; discriminating designs choose (spacing, number of events) by the number of distinct
   observable outcomes (how often the effect occurs) among the near-best parameter sets.

Every top-level goal is logged before its first action (prospective); experiment goals carry their plan.
"""

from __future__ import annotations

import itertools
from collections import Counter, defaultdict, deque

from agent import GOAL_T, NEED_LOW, Agent
from structures import ACT, FX, DECAYS, THETAS, W, Bit, Counter as M1Counter, Learner, cheb
from substrate import frontier_step

N_MAX = 3                       # trials of a key whose trials showed no effect
N_REP = 8                       # trials of a key whose trials showed an effect (replicate surprising results)
NS = (2, 3, 4, 5, 6)
SPACINGS = (1, 5, 10, 15, 20, 30, 40, 60)
LIT = {"poke": "poked", "pick": "picked", "consume": "consumed", "drop": "dropped"}
REST = 100                      # an instance acted upon in the last REST steps is not 'rested'
NEED_TERM = 60


def m1_score(lr, mem, ev, p, poses):
    """(predicted, testable, confirmed) of one M1 parameter set on events `ev` (mirrors Learner.fit_m1)."""
    inst = defaultdict(list)
    for a in ev:
        if a["type"] == p["E"] and a.get("kind") == p["K"]:
            inst[(a["frame"],) + tuple(a["cell"])].append(a["t"])
    fx_k = [f for f in ev if f["type"] == p["ftype"] and f.get("kind") == p["K2"] and f.get("gap", 99) <= 3]
    pred = test = conf = 0
    for (fr, x, y), times in inst.items():
        if p.get("ctx") is not None and not lr._near_kind(mem, fr, (x, y), p["ctx"], p["dctx"]):
            continue
        c, mark = 0, times[0]
        for t in times:
            while c > 0 and t - mark >= p["D"]:
                c -= 1
                mark += p["D"]
            c = min(c + 1, p["theta"])
            mark = t
            if c >= p["theta"]:
                pred += 1
                if lr._testable(poses, fr, (x, y), t, t + W, r=1):
                    test += 1
                    if any(f["frame"] == fr and 0 <= f["t"] - t <= W + 1 and 0 < cheb(f["cell"], (x, y)) <= 3 for f in fx_k):
                        conf += 1
                if p["reset"]:
                    c = 0
    return pred, test, conf


def simulate_m1(p, spacing, n):
    """Indices (0-based) of the events at which an M1 with parameters p fires, for n events `spacing` steps apart
    on a fresh instance whose context holds."""
    c, mark, out = 0, 0, []
    for i in range(n):
        t = i * spacing
        while c > 0 and t - mark >= p["D"]:
            c -= 1
            mark += p["D"]
        c = min(c + 1, p["theta"])
        mark = t
        if c >= p["theta"]:
            out.append(i)
            if p["reset"]:
                c = 0
    return tuple(out)


class Candidate(Agent):
    name = "CAND"
    learn_every = 2000
    grow_language = True          # OC1: False (goal language fixed to L(S0); structures still learned and used)
    experiments = True            # OC5: False (no experiment goals)
    triggered = True              # OC3: False (acquisition only every 2,000 steps, no failure-triggered revision)
    use_needs = True              # OC4: False (needs ignored)
    learner_window = 10000        # OC2: short window (no episodic memory beyond the last steps)

    def __init__(self, seed, learner_kwargs=None):
        kw = dict(learner_kwargs or {})
        kw.setdefault("window", self.learner_window)
        super().__init__(seed, kw)
        self.use_structures_in_goals = self.grow_language
        self.tests = Counter()
        self.effects = Counter()                # experiment key -> trials followed by a timed effect near its targets
        self.boost = defaultdict(float)
        self.preds = []                         # open predictions: [t, frame, cell, ftype, K2, sid]
        self.pred_hist = defaultdict(lambda: deque(maxlen=8))
        self.retired = []
        self.plan = None
        self.fit_due = False
        self.last_fit = -10 ** 9
        self.revise_due = set()
        self.act_ok = Counter()                 # (K, E) successes
        self.act_fail = Counter()               # (K, E) failures
        self.last_acted = {}                    # (frame, x, y) -> t of the last own act there
        self.disc = {}                          # sid -> (spacing, n_events, n_distinct)
        self._inst = (None, None)

    # ------------------------------------------------------------ predicates
    def s0_predicates(self):
        return super().s0_predicates()

    def holds(self, p):
        if p.startswith("dropped:"):
            last = self.mem.events[-1] if self.mem.events else None
            return bool(last) and last["t"] == self.mem.t and last["type"] == "drop" and last["kind"] == int(p.split(":")[1])
        return super().holds(p)

    def instances(self):
        key = (self.mem.t, self.mem.frame)
        if self._inst[0] != key:
            self._inst = (key, self.mem.instances())
        return self._inst[1]

    def context_kinds(self, cell):
        inst = self.instances()
        ks = {k for c, k in inst.items() if c != tuple(cell) and cheb(c, cell) <= 2}
        return ks

    def rested(self, cell):
        return self.mem.t - self.last_acted.get((self.mem.frame,) + tuple(cell), -10 ** 9) > REST

    def key_value(self, key):
        n, m = self.tests[key], self.effects[key]
        return max(0.0, 1.0 - n / (N_REP if m else N_MAX))

    def applicable(self, K, E):
        return not (self.act_fail[(K, E)] >= 2 and self.act_ok[(K, E)] == 0)

    # ------------------------------------------------------------ main step
    def act(self, obs):
        self.obs = obs
        self.mem.observe(obs, self.last_action)
        new = self.mem.events[self.ev_idx:]
        self.ev_idx = len(self.mem.events)
        for e in new:
            if e["type"] == "consume" and e.get("kind"):
                for i in (0, 1):
                    d = e["needs_after"][i] - e["needs_before"][i]
                    if d > 0:
                        self.aff[e["kind"]][i] += d
            if e["type"] == "reset":
                self.goal_stack.clear()
                self.plan = None
                self.preds.clear()
            if e["type"] == "fail_consume":
                self.unavailable[(e["frame"],) + tuple(e["cell"])] = e["t"]
            if e["type"] in ACT and e.get("kind"):
                self.act_ok[(e["kind"], e["type"])] += 1
                self.last_acted[(e["frame"],) + tuple(e["cell"])] = e["t"]
            if e["type"].startswith("fail_") and e.get("kind"):
                self.act_fail[(e["kind"], e["type"][5:])] += 1
        tracked = self.tracked_structs()
        snap = {sid: (dict((k, list(v)) for k, v in s.cnt.items()) if s.form == "M1" else dict(s.bit) if s.form == "M2" else None)
                for sid, s in tracked.items()}
        for form in ("M1", "M2", "M3", "M4"):
            for s in tracked.values():
                if s.form == form:
                    s.step(self.mem, new, tracked)
        self.monitor(new, snap, tracked)
        for k in list(self.boost):
            self.boost[k] *= 0.9995
            if self.boost[k] < 0.01:
                del self.boost[k]
        if self.learn_every:
            due = self.mem.t % self.learn_every == 0
            if self.triggered and (self.fit_due or self.revise_due) and self.mem.t - self.last_fit >= 100:
                due = True
            if due:
                self.acquire()
        self.manage_goals()
        a = self.execute()
        self.last_action = a
        self.logs.actions.append({"t": self.mem.t, "action": a, "goal_id": self.goal_stack[-1][0] if self.goal_stack else None})
        from substrate import A
        return A[a]

    # ------------------------------------------------------------ prediction monitor
    def monitor(self, new, snap, tracked):
        mem = self.mem
        for e in new:
            if e["type"] not in ACT or not e.get("kind"):
                continue
            key = (e["frame"],) + tuple(e["cell"])
            for sid, s in tracked.items():
                p = s.params
                if p.get("E") != e["type"] or p.get("K") != e["kind"]:
                    continue
                fired = False
                if s.form == "M1":
                    before = snap[sid].get(key)
                    b = 0
                    if before is not None:
                        b, mark = before
                        while b > 0 and e["t"] - mark >= p["D"]:
                            b -= 1
                            mark += p["D"]
                    after = s.cnt.get(key, [0])[0]
                    if p["reset"]:
                        fired = after == 0 and b >= p["theta"] - 1 and s._ctx_ok(mem, tuple(e["cell"]))
                    else:
                        fired = after >= p["theta"]
                elif s.form == "M2":
                    fired = key in snap[sid] and key not in s.bit
                if fired:
                    self.preds.append([e["t"], e["frame"], tuple(e["cell"]), p.get("ftype"), p.get("K2"), sid])
        for f in new:
            if f["type"] not in FX or f.get("gap", 99) > 3:
                continue
            hit = None
            for pr in self.preds:
                if pr[1] == f["frame"] and pr[3] == f["type"] and pr[4] == f["kind"] and 0 <= f["t"] - pr[0] <= W + 1 \
                        and cheb(pr[2], f["cell"]) <= 3:
                    hit = pr
                    break
            if hit is not None:
                self.pred_hist[hit[5]].append(1)
                self.preds.remove(hit)
                continue
            for a in mem.events[-60:]:                     # anomaly: credit the own acts that preceded it nearby
                if a["type"] in ACT and a.get("kind") and a["frame"] == f["frame"] and 0 <= f["t"] - a["t"] <= W \
                        and cheb(a["cell"], f["cell"]) <= 3:
                    self.boost[(a["kind"], a["type"])] = min(2.0, self.boost[(a["kind"], a["type"])] + 0.5)
        keep = []
        for pr in self.preds:
            if mem.t - pr[0] > W + 1:
                near = any(fr == pr[1] and cheb((x, y), pr[2]) <= 2 for (t, fr, x, y) in mem.poses[-(W + 2):])
                if near:
                    self.pred_hist[pr[5]].append(0)
                    h = self.pred_hist[pr[5]]
                    if self.triggered and sum(1 for v in h if v == 0) >= 3:
                        self.revise_due.add(pr[5])
            else:
                keep.append(pr)
        self.preds = keep

    # ------------------------------------------------------------ acquisition
    def acquire(self):
        if not self.learn_every:
            return
        self.last_fit = self.mem.t
        self.fit_due = False
        for s in self.learner.fit(self.mem, self.structs, self.mem.t):
            self.add_structure(s, trigger="fit")
        if self.triggered:
            for sid in list(self.revise_due):
                self.try_revision(sid)
            self.revise_due.clear()
        self.update_discriminators()

    def try_revision(self, sid):
        """Refit the structure's kind on the full learner window (ignoring that it is held) and replace it when the
        refit is better on the same data by >= 0.1 precision (or equal precision with at least half as many more
        confirmations)."""
        s = self.structs.get(sid)
        if s is None or s.form not in ("M1", "M2") or (s.form, s.params["K"]) in self.learner.blocked:
            return
        K = s.params["K"]
        t = self.mem.t
        lr = self.learner
        ev = [e for e in self.mem.events if e["t"] >= t - lr.window]
        if s.form == "M1":
            new = lr.fit_m1(self.mem, [e for e in ev if e["type"] in FX or e.get("kind") == K], set(), t)
            if new is None or new.params["K"] != K or new.params == s.params:
                return
            poses = lr._poses_by_t(self.mem)
            _, test, conf = m1_score(lr, self.mem, ev, s.params, poses)
            cur, cur_conf = (conf / test if test else 0.0), conf
            better = new.stats["precision"] >= cur + 0.1 or (new.stats["precision"] >= cur and new.stats["confirmed"] >= 1.5 * max(cur_conf, 1))
            cls = M1Counter
        else:
            others = {k: v for k, v in self.structs.items() if k != sid}
            new = lr.fit_m2(self.mem, ev, {(f, k) for (f, k) in {(x.form, x.params.get("K")) for x in others.values()} if f != "M2" or k != K},
                            others, t)
            if new is None or new.params["K"] != K or new.params == s.params:
                return
            cur = s.stats.get("precision", 0.0)
            better = new.stats["precision"] >= cur + 0.1 or (new.stats["precision"] >= cur and new.stats["positives"] >= 1.5 * max(s.stats.get("positives", 1), 1))
            cls = Bit
        if not better:
            return
        repl = cls(new.sid, new.params, new.stats, new.evidence, t)
        self.retire(sid, reason="revised")
        for b in self.structs.values():
            if b.form == "M2" and b.params.get("q_struct") == sid:
                b.params["q_struct"] = repl.sid
        self.add_structure(repl, trigger="revision")
        self.logs.structures[-1]["replaces"] = sid

    def retire(self, sid, reason):
        s = self.structs.pop(sid)
        d = s.describe()
        d["retired"] = self.mem.t
        d["retired_reason"] = reason
        self.retired.append(d)
        self.pred_hist.pop(sid, None)

    def update_discriminators(self):
        """For every held M1: the (spacing, number of events) whose observable outcome (how many times the effect
        occurs) differs most among the parameter sets that fit the learner's data about equally well; keys already
        tried enough are skipped."""
        self.disc = {}
        if not self.experiments:
            return
        lr = self.learner
        t = self.mem.t
        poses = None
        for sid, s in self.structs.items():
            if s.form != "M1":
                continue
            K = s.params["K"]
            ev = [e for e in self.mem.events if e["t"] >= t - lr.window and (e["type"] in FX or e.get("kind") == K)]
            if poses is None:
                poses = lr._poses_by_t(self.mem)
            scored = []
            for theta, D, reset in itertools.product(THETAS, DECAYS, (True, False)):
                p = dict(s.params, theta=theta, D=D, reset=reset)
                _, test, conf = m1_score(lr, self.mem, ev, p, poses)
                if test >= 2 and conf >= 1:
                    scored.append((conf / test, conf, p))
            if not scored:
                continue
            top = max(x[0] for x in scored)
            H = [p for prec, conf, p in scored if prec >= top - 0.15]
            if len(H) <= 1:
                continue
            best = None
            for sp in SPACINGS:
                for n in NS:
                    if self.key_value(("X1s", K, s.params["E"], sp, n)) <= 0:
                        continue
                    d = len({len(simulate_m1(p, sp, n)) for p in H})
                    cost = sp * (n - 1) + n
                    if d > 1 and (best is None or (d, -cost) > (best[2], -best[3])):
                        best = (sp, n, d, cost)
            if best:
                self.disc[sid] = best[:3]

    # ------------------------------------------------------------ goal management
    def manage_goals(self):
        mem = self.mem
        last = mem.events[-1] if mem.events else None
        if self.goal_stack and last and last["t"] == mem.t and last["type"].startswith("fail_"):
            self.goal_fails += 1
            if self.goal_fails >= 2:
                self.goal_fails = 0
                self.end_top(False)
        while self.goal_stack:
            gid, formula, t0, parent = self.goal_stack[-1]
            if self.plan is not None and gid == self.plan["gid"]:
                if self.plan.get("done") or self.plan.get("abort"):
                    self.end_top(bool(self.plan.get("done")))
                    continue
                if mem.t - t0 > GOAL_T:
                    self.end_top(False)
                    continue
                break
            if all(self.holds(p) for p in formula):
                self.end_top(True)
            elif mem.t - t0 > GOAL_T:
                self.end_top(False)
            else:
                break
        if self.use_needs:
            idx = self.need_goal()
            if idx is not None and not any(g[1] == [f"hi:{idx}"] for g in self.goal_stack):
                self.log_goal([f"hi:{idx}"], reason="need", priority=1.0)
                return
        if not self.goal_stack:
            g = self.propose()
            if g is not None:
                formula, reason, priority = g[:3]
                plan = g[3] if len(g) > 3 else None
                prov = g[4] if len(g) > 4 else None
                gid = self.log_goal(formula, reason, priority, provenance=prov)
                if plan is not None:
                    self.logs.goals[-1]["plan"] = plan["desc"]
                    plan["gid"] = gid
                    plan["t0"] = self.mem.t
                    plan["frame"] = self.mem.frame
                    self.plan = plan

    def end_top(self, ok):
        gid = self.goal_stack[-1][0]
        if self.plan is not None and gid == self.plan["gid"]:
            self.goal_fails = 0
            self.goal_stack.pop()
            self.tests[self.plan["key"]] += 1
            P = self.plan
            seen = False
            for e in reversed(self.mem.events):
                if e["t"] < P["t0"]:
                    break
                if e["type"] in FX and e.get("gap", 99) <= 3 and e["frame"] == P["frame"] \
                        and any(cheb(e["cell"], c) <= 3 for c in P.get("targets", ())):
                    seen = True
                    break
            if seen:
                self.effects[P["key"]] += 1
            self.logs.goals[gid]["outcome"] = ("done" if ok else "aborted") + ("+effect" if seen else "")
            self.plan = None
            self.fit_due = True
            return
        self.finish_goal(ok)

    def need_goal(self):
        if not self.use_needs:
            return None
        return super().need_goal()

    # ------------------------------------------------------------ proposals
    def mastery_weights(self):
        preds = self.s0_predicates() + [p for p, _ in self.learned_predicates()]
        out = []
        for p in preds:
            h = list(self.attempts.get(p, ()))
            if len(h) < 4:
                lp = 1.0
            else:
                half = len(h) // 2
                lp = abs(sum(h[half:]) / (len(h) - half) - sum(h[:half]) / half)
            gap = 0.0
            s = self.predicate_owner(p)
            if s is not None:
                hist = self.pred_hist.get(s.sid)
                if hist and len(hist) >= 3:
                    gap = sum(1 for v in hist if v == 0) / len(hist)
            out.append((lp + gap + 0.05, p))
        return out

    def propose(self):
        pool = []
        if self.use_needs:
            n = self.obs["needs"]
            for i in (0, 1):
                if n[i] < NEED_TERM and any(g[i] > 0 for g in self.aff.values()):
                    pool.append((2.0 * (NEED_TERM - n[i]) / NEED_TERM, ("need", i)))
        if self.experiments:
            pool += [(w, ("exp", mk)) for w, mk in self.experiment_options()]
        for w, p in self.mastery_weights():
            pool.append((w, ("mastery", p)))
        pool = [x for x in pool if x[0] > 0]
        if not pool:
            return None
        w, choice = self.rng.choices(pool, weights=[x[0] for x in pool])[0]
        if choice[0] == "need":
            return ([f"hi:{choice[1]}"], "need_term", round(w, 4))
        if choice[0] == "mastery":
            return ([choice[1]], "mastery", round(w, 4))
        return choice[1](w)

    # ------------------------------------------------------------ experiments
    def experiment_options(self):
        inst = self.instances()
        if not inst:
            return []
        pos = self.mem.pos
        opts = []
        kinds = sorted(set(inst.values()))
        by_kind = defaultdict(list)
        for c, k in inst.items():
            by_kind[k].append(c)
        pickable = {K for (K, E), n in self.act_ok.items() if E == "pick" and n > 0}
        # X1
        best_x1 = {}
        for K in kinds:
            for E in ("poke", "pick", "consume"):
                if not self.applicable(K, E):
                    continue
                for c in by_kind[K]:
                    if not self.rested(c):
                        continue
                    ctx = self.context_kinds(c) or {"none"}
                    for k3 in ctx:
                        key = ("X1", K, E, k3)
                        v = self.key_value(key)
                        if v <= 0:
                            continue
                        v += self.boost.get((K, E), 0.0) * 0.5
                        d = cheb(c, pos)
                        if key not in best_x1 or d < best_x1[key][1]:
                            best_x1[key] = (v, d, c)
        for key, (v, d, c) in best_x1.items():
            opts.append((v / (1 + d / 8), self._x1_maker(key, c)))
        # X1 with drop: carry a pickable K next to a context kind
        for K in pickable:
            if not self.applicable(K, "drop") or not by_kind.get(K) and self.obs["carried"] != K:
                continue
            for k3 in kinds:
                key = ("X1", K, "drop", k3)
                v = self.key_value(key)
                if v > 0:
                    v += self.boost.get((K, "drop"), 0.0) * 0.5
                    opts.append((v / 2, self._x1d_maker(key, K, k3)))
        # X1s: discriminating spacing for held counters
        for sid, (sp, n, dist) in self.disc.items():
            s = self.structs.get(sid)
            if s is None:
                continue
            key = ("X1s", s.params["K"], s.params["E"], sp, n)
            v = self.key_value(key)
            if v <= 0:
                continue
            cands = [c for c in by_kind.get(s.params["K"], []) if self.rested(c) and s._ctx_ok(self.mem, c)]
            if cands:
                c = min(cands, key=lambda c: cheb(c, pos))
                opts.append(((v + 0.5 * sum(1 for x in self.pred_hist.get(sid, ()) if x == 0) / 8) / (1 + cheb(c, pos) / 8),
                             self._x1s_maker(key, s, c, sp, n)))
        # X2
        ctx_preds = []                                       # (Kq, predicate, sid, level)
        if self.grow_language:
            for s in self.structs.values():
                if s.form == "M1":
                    for p in s.predicates():
                        ctx_preds.append((s.params["K"], p, s.sid, int(p.split(">=")[1])))
                elif s.form == "M2":
                    ctx_preds.append((s.params["K"], s.predicates()[0], s.sid, 1))
        best_x2 = {}
        for K in kinds:
            for E in ("poke", "pick"):
                if not self.applicable(K, E) or (E == "pick" and K not in pickable):
                    continue
                for c in by_kind[K]:
                    if not self.rested(c):
                        continue
                    for q, Kq in inst.items():
                        if q == c or cheb(q, c) > 1:
                            continue
                        opts_q = [(None, None, None)] + [(p, sid, lev) for (kk, p, sid, lev) in ctx_preds if kk == Kq]
                        for p, sid, lev in opts_q:
                            key = ("X2", K, E, Kq, p, sid)
                            v = self.key_value(key)
                            if v <= 0:
                                continue
                            v += self.boost.get((K, E), 0.0) * 0.5
                            d = cheb(c, pos)
                            if key not in best_x2 or d < best_x2[key][1]:
                                best_x2[key] = (v, d, c, q, sid, lev)
        for key, (v, d, c, q, sid, lev) in best_x2.items():
            opts.append((v / (1 + d / 8), self._x2_maker(key, c, q, sid, lev)))
        return opts

    def _ops_for(self, E, c, n, spacing=1):
        if E == "poke":
            return [("act", c, "POKE", n, spacing)]
        if E == "consume":
            return [("act", c, "CONSUME", 1, 1)]
        if E == "pick":
            out = []
            for _ in range(n):
                out += [("act", c, "PICK", 1, 1), ("act", c, "DROP", 1, 1)]
            return out
        return []

    def _x1_maker(self, key, c):
        _, K, E, k3 = key

        def make(w):
            n = 4 if E == "poke" else 2 if E == "pick" else 1
            ops = self._ops_for(E, c, n) + [("wait", W)]
            plan = {"key": key, "ops": ops, "i": 0, "k": 0, "w": 0, "tries": 0, "kind": K, "targets": [c],
                    "desc": {"type": "X1", "K": K, "E": E, "context": k3, "cell": list(c), "n": n}}
            return ([f"{LIT[E]}:{K}"], "experiment", round(w, 4), plan, ["S0"])
        return make

    def _x1d_maker(self, key, K, k3):
        def make(w):
            ops = [("fetch", K), ("drop_near", k3), ("wait", W)]
            plan = {"key": key, "ops": ops, "i": 0, "k": 0, "w": 0, "tries": 0, "kind": K,
                    "desc": {"type": "X1", "K": K, "E": "drop", "context": k3}}
            return ([f"dropped:{K}"], "experiment", round(w, 4), plan, ["S0"])
        return make

    def _x1s_maker(self, key, s, c, sp, n):
        def make(w):
            E = s.params["E"]
            ops = self._ops_for(E, c, n, sp) + [("wait", W)]
            plan = {"key": key, "ops": ops, "i": 0, "k": 0, "w": 0, "tries": 0, "kind": s.params["K"], "targets": [c],
                    "desc": {"type": "X1s", "struct": s.sid, "spacing": sp, "n": n, "cell": list(c)}}
            return ([f"{LIT[E]}:{s.params['K']}"], "experiment", round(w, 4), plan, ["S0"])
        return make

    def _x2_maker(self, key, c, q, sid, lev):
        _, K, E, Kq, p, _sid = key

        def make(w):
            ops = []
            if p is not None:
                ops.append(("setup", sid, lev, q, 0))
            ops += self._ops_for(E, c, 1) + [("wait", 3)] + self._ops_for(E, c, 1) + [("wait", W)]
            plan = {"key": key, "ops": ops, "i": 0, "k": 0, "w": 0, "tries": 0, "kind": K, "targets": [c, q],
                    "desc": {"type": "X2", "K": K, "E": E, "Kq": Kq, "context": p, "cell": list(c), "q": list(q)}}
            formula = ([p] if p else []) + [f"{LIT[E]}:{K}"]
            prov = ([f"struct:{sid}"] if p else []) + ["S0"]
            return (formula, "experiment", round(w, 4), plan, prov)
        return make

    # ------------------------------------------------------------ execution
    def execute(self):
        if self.plan is not None and self.goal_stack and self.goal_stack[-1][0] == self.plan["gid"]:
            return self.plan_step()
        return super().execute()

    def _abort(self):
        self.plan["abort"] = True
        return frontier_step(self.mem, self.obs["facing"], self.rng)

    def plan_step(self):
        P = self.plan
        mem = self.mem
        while P["i"] < len(P["ops"]):
            op = P["ops"][P["i"]]
            if op[0] == "wait":
                if P["k"] < op[1]:
                    P["k"] += 1
                    return "WAIT"
                P["i"] += 1
                P["k"] = 0
                continue
            if op[0] == "act":
                _, cell, action, n, sp = op
                if P["k"] >= n:
                    P["i"] += 1
                    P["k"] = P["w"] = 0
                    continue
                if P["k"] > 0 and P["w"] < sp - 1:
                    P["w"] += 1
                    return "WAIT"
                cur = mem.cell(*cell)
                if action == "DROP":
                    if not self.obs["carried"] or (cur is not None and (cur[0] or cur[1])):
                        return self._abort()
                elif action == "PICK":
                    if self.obs["carried"] or cur is None or cur[1] != P["kind"]:
                        return self._abort()
                elif cur is None or not cur[1]:
                    return self._abort()
                step = self.face_then(cell, action)
                if step == action:
                    P["k"] += 1
                    P["w"] = 0
                return step
            if op[0] == "setup":
                _, sid, lev, q, depth = op
                s = self.structs.get(sid)
                cur = mem.cell(*q)
                if s is None or cur is None or cur[1] != s.params["K"]:
                    return self._abort()
                if s.form == "M1":
                    if s.count(mem, q) >= lev:
                        P["i"] += 1
                        continue
                    P["tries"] += 1
                    if P["tries"] > 3 * s.params["theta"] + 4:
                        return self._abort()
                    return self.face_then(q, s.params["E"].upper())
                if s.form == "M2":
                    if (mem.frame,) + tuple(q) in s.bit:
                        P["i"] += 1
                        continue
                    if s.q_holds(mem, q, self.structs):
                        P["tries"] += 1
                        if P["tries"] > 12:
                            return self._abort()
                        return self.face_then(q, s.params["E"].upper())
                    if depth < 2 and s.params.get("q_pred") is not None:
                        qs = [c for c, k in self.instances().items() if k == s.params["Kq"] and cheb(c, q) <= s.params["dq"]]
                        if qs:
                            q2 = min(qs, key=lambda c: cheb(c, mem.pos))
                            P["ops"].insert(P["i"], ("setup", s.params["q_struct"], s.params["q_v"], q2, depth + 1))
                            continue
                    return self._abort()
                return self._abort()
            if op[0] == "fetch":
                K = op[1]
                if self.obs["carried"] == K:
                    P["i"] += 1
                    continue
                if self.obs["carried"]:
                    return self._abort()
                cs = [c for c, k in self.instances().items() if k == K]
                if not cs:
                    return self._abort()
                P["tries"] += 1
                if P["tries"] > 60:
                    return self._abort()
                return self.face_then(min(cs, key=lambda c: cheb(c, mem.pos)), "PICK")
            if op[0] == "drop_near":
                k3 = op[1]
                if not self.obs["carried"]:
                    P["i"] += 1
                    continue
                targets = [c for c, k in self.instances().items() if k == k3]
                free = []
                for t3 in targets:
                    for dx, dy in ((0, 1), (1, 0), (0, -1), (-1, 0)):
                        f = (t3[0] + dx, t3[1] + dy)
                        cf = mem.cell(*f)
                        if cf is not None and not cf[0] and not cf[1] and f != mem.pos:
                            free.append(f)
                if not free:
                    return self._abort()
                P["tries"] += 1
                if P["tries"] > 120:
                    return self._abort()
                return self.face_then(min(free, key=lambda c: cheb(c, mem.pos)), "DROP")
            return self._abort()
        P["done"] = True
        return "WAIT"

    # ------------------------------------------------------------ need competence (structures used instrumentally)
    def instrumental_for_need(self, i):
        good = {K for K, g in self.aff.items() if g[i] > 0}
        for s in self.structs.values():
            if s.form in ("M1", "M2") and s.params.get("K2") in good and s.params.get("ftype") == "appear":
                self.pending_sub = s.predicates()[-1]
                return "SUBGOAL"
        return None

    def export(self):
        out = super().export()
        out["structures"] = out["structures"] + self.retired
        out["experiments"] = {"|".join(map(str, k)): v for k, v in self.tests.items()}
        return out


# ================================================================ ablations (organisation conditions)
class OC1FixedLanguage(Candidate):
    """Goal language fixed to L(S0): structures are learned, track and predict, and serve need goals instrumentally,
    but never enter top-level goals or experiment contexts."""
    name = "OC1"
    grow_language = False


class OC2NoMemory(Candidate):
    """No episodic memory beyond the last 60 steps for structure acquisition."""
    name = "OC2"
    learner_window = 60


class OC3Passive(Candidate):
    """Passive acquisition: refit every 2,000 steps only (as B4); no failure-triggered revision."""
    name = "OC3"
    triggered = False


class OC4NoNeeds(Candidate):
    """No need variables in goal choice (needs are ignored entirely)."""
    name = "OC4"
    use_needs = False


class OC5NoExperiments(Candidate):
    """No experiment goals: needs and mastery goals over L(S) only (acquisition and revision as the candidate)."""
    name = "OC5"
    experiments = False


ARMS = {c.name: c for c in (Candidate, OC1FixedLanguage, OC2NoMemory, OC3Passive, OC4NoNeeds, OC5NoExperiments)}
