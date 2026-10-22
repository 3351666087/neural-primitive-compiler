"""Agent framework and the Gate 2 baselines for Mission 07 (PROTOCOL.md section 4.1). AGENT SIDE.

Every arm shares: Memory (substrate.py), the structure learner over M (structures.py), the executor, the goal logs,
need-affordance learning (which kinds raise which need, from the agent's own consume events), and one survival
override (a need below 35 makes the matching need goal top-level). Arms differ only in how they choose goals
(`propose`) and when / how they acquire structure (`learn_every`, learner settings).

Goal language L(S): conjunctions of at most k = 3 literals over P(S); in practice the arms use single literals.
S0 predicates (functions of the current observation and needs):
  see:K  face:K  carry:K  poked:K  picked:K  consumed:K  hi:0 (food >= 80)  hi:1 (water >= 80)
Learned predicates come from structures: cnt[K]>=v, bit[K], memnear[K], pairfx[K>Kb].
"""

from __future__ import annotations

import random
from collections import Counter, defaultdict, deque

from structures import FORMS, Learner
from substrate import ACTIONS, A, DIRS, Logs, Memory, frontier_step, plan_to_face

GOAL_T = 400           # time bound of a goal (steps)
NEED_LOW = 35


class Agent:
    name = "base"
    learn_every = 2000                 # passive refit period; None = no structure learning
    use_structures_in_goals = True     # learned predicates enter L(S)

    def __init__(self, seed, learner_kwargs=None):
        self.rng = random.Random(seed)
        self.mem = Memory()
        self.logs = Logs()
        self.learner = Learner(**(learner_kwargs or {}))
        self.structs = {}                       # sid -> Structure
        self.goal_stack = []                    # [(gid, formula, t_start, parent)]
        self.last_action = "WAIT"
        self.obs = None
        self.ev_idx = 0
        self.aff = defaultdict(Counter)         # kind -> Counter{need index: total gain}
        self.tried = Counter()                  # (kind, action) -> attempts
        self.attempts = defaultdict(deque)      # predicate -> deque of 0/1 outcomes (competence)
        self.pending_sub = None
        self.goal_fails = 0
        self.unavailable = {}                   # (frame, x, y) -> t of the last failed consume there

    # ------------------------------------------------------------ predicates
    def kinds(self):
        return sorted({v[1] for v in self.mem.cells.values() if v[1]})

    def s0_predicates(self):
        out = []
        for K in self.kinds():
            out += [f"see:{K}", f"face:{K}", f"carry:{K}", f"poked:{K}", f"picked:{K}", f"consumed:{K}"]
        return out + ["hi:0", "hi:1"]

    def learned_predicates(self):
        if not self.use_structures_in_goals:
            return []
        out = []
        for s in self.structs.values():
            out += [(p, s.sid) for p in s.predicates()]
        return out

    def predicate_owner(self, p):
        for s in self.structs.values():
            if p in s.predicates():
                return s
        return None

    def holds(self, p):
        obs, mem = self.obs, self.mem
        if ":" in p and "[" not in p:
            typ, arg = p.split(":")
            if typ == "hi":
                return obs["needs"][int(arg)] >= 80
            K = int(arg)
            fc = mem.cell(*mem.facing_cell(obs["facing"]))
            if typ == "see":
                return any(cell[1] == K for row in obs["view"] for cell in row)
            if typ == "face":
                return bool(fc) and fc[1] == K
            if typ == "carry":
                return obs["carried"] == K
            last = mem.events[-1] if mem.events else None
            want = {"poked": "poke", "picked": "pick", "consumed": "consume"}[typ]
            return bool(last) and last["t"] == mem.t and last["type"] == want and last["kind"] == K
        s = self.predicate_owner(p)
        return bool(s) and s.value(p, mem, self.tracked_structs())

    # ------------------------------------------------------------ goal machinery
    def log_goal(self, formula, reason, priority=0.0, parent=None, provenance=None):
        prov = provenance or [("S0" if self.predicate_owner(p) is None else f"struct:{self.predicate_owner(p).sid}") for p in formula]
        hist = self.attempts.get(formula[0], ())
        pred = (sum(hist) / len(hist)) if hist else None
        gid = self.logs.goal(self.mem.t, formula, prov, round(priority, 4), reason, pred,
                             [e["t"] for e in self.mem.events[-5:]], parent)
        self.goal_stack.append([gid, formula, self.mem.t, parent])
        return gid

    def finish_goal(self, ok):
        self.goal_fails = 0
        gid, formula, t0, parent = self.goal_stack.pop()
        dq = self.attempts[formula[0]]
        dq.append(1 if ok else 0)
        while len(dq) > 20:
            dq.popleft()
        self.on_goal_end(formula, ok)

    def on_goal_end(self, formula, ok):
        pass

    def need_goal(self):
        n = self.obs["needs"]
        idx = min((0, 1), key=lambda i: n[i])
        if n[idx] < NEED_LOW:
            return idx
        return None

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
            if e["type"] == "fail_consume":
                self.unavailable[(e["frame"],) + tuple(e["cell"])] = e["t"]
        tracked = self.tracked_structs()
        for form in ("M1", "M2", "M3", "M4"):
            for s in tracked.values():
                if s.form == form:
                    s.step(self.mem, new, tracked)
        if self.learn_every and self.mem.t % self.learn_every == 0:
            self.acquire()
        self.manage_goals()
        a = self.execute()
        self.last_action = a
        self.logs.actions.append({"t": self.mem.t, "action": a, "goal_id": self.goal_stack[-1][0] if self.goal_stack else None})
        return A[a]

    def acquire(self, **fit_kwargs):
        for s in self.learner.fit(self.mem, self.structs, self.mem.t):
            self.add_structure(s, trigger="periodic")

    def tracked_structs(self):
        return self.structs

    def add_structure(self, s, trigger):
        self.structs[s.sid] = s
        self.replay(s)
        self.logs.structures.append({**s.describe(), "trigger": trigger})

    def replay(self, s):
        """Replay the agent's own events of the current life through the new tracker."""
        s.reset_tracker()
        s.step(self.mem, [e for e in self.mem.events if e.get("frame") == self.mem.frame], self.tracked_structs())

    def manage_goals(self):
        last = self.mem.events[-1] if self.mem.events else None
        if self.goal_stack and last and last["t"] == self.mem.t and last["type"].startswith("fail_"):
            self.goal_fails += 1
            if self.goal_fails >= 2:                       # the action keeps having no effect: give the goal up
                self.goal_fails = 0
                self.finish_goal(False)
        # drop finished / expired goals
        while self.goal_stack:
            gid, formula, t0, parent = self.goal_stack[-1]
            if all(self.holds(p) for p in formula):
                self.finish_goal(True)
            elif self.mem.t - t0 > GOAL_T:
                self.finish_goal(False)
            else:
                break
        idx = self.need_goal()
        if idx is not None and not any(g[1] == [f"hi:{idx}"] for g in self.goal_stack):
            self.log_goal([f"hi:{idx}"], reason="need", priority=1.0)
            return
        if not self.goal_stack:
            g = self.propose()
            if g is not None:
                formula, reason, priority = g
                self.log_goal(formula, reason, priority)

    def propose(self):
        return None

    # ------------------------------------------------------------ executor
    def execute(self):
        if not self.goal_stack:
            return frontier_step(self.mem, self.obs["facing"], self.rng)
        gid, formula, t0, parent = self.goal_stack[-1]
        p = next((q for q in formula if not self.holds(q)), formula[0])
        step = self.achieve(p)
        if step == "SUBGOAL" and self.pending_sub:
            sub = self.pending_sub
            self.pending_sub = None
            if len(self.goal_stack) < 4 and not any(g[1] == [sub] for g in self.goal_stack):
                self.log_goal([sub], reason="instrumental", priority=0.0, parent=gid)
            return self.execute_inner()
        return step

    def execute_inner(self):
        gid, formula, t0, parent = self.goal_stack[-1]
        p = next((q for q in formula if not self.holds(q)), formula[0])
        step = self.achieve(p)
        return step if step != "SUBGOAL" else frontier_step(self.mem, self.obs["facing"], self.rng)

    def face_then(self, cell, action):
        plan = plan_to_face(self.mem, self.obs["facing"], cell)
        if plan is None:
            return frontier_step(self.mem, self.obs["facing"], self.rng)
        if not plan:
            self.tried[(self.mem.cell(*cell)[1] if self.mem.cell(*cell) else 0, action)] += 1
            return action
        return plan[0]

    def nearest(self, K):
        insts = self.mem.instances(K)
        if not insts:
            return None
        return min(insts, key=lambda c: max(abs(c[0] - self.mem.pos[0]), abs(c[1] - self.mem.pos[1])))

    def achieve(self, p):
        mem = self.mem
        if ":" in p and "[" not in p:
            typ, arg = p.split(":")
            if typ == "hi":
                return self.achieve_need(int(arg))
            K = int(arg)
            c = self.nearest(K)
            if c is None:
                return frontier_step(mem, self.obs["facing"], self.rng)
            if typ in ("see", "face"):
                return self.face_then(c, "WAIT")
            if typ in ("carry", "picked"):
                return self.face_then(c, "PICK")
            if typ == "poked":
                return self.face_then(c, "POKE")
            if typ == "consumed":
                return self.face_then(c, "CONSUME")
        s = self.predicate_owner(p)
        if s is None:
            return frontier_step(mem, self.obs["facing"], self.rng)
        r = s.recipe(p, mem, self.tracked_structs())
        if r is None or r[0] == "explore_for":
            return frontier_step(mem, self.obs["facing"], self.rng)
        if r[0] == "act":
            return self.face_then(r[1], r[2])
        if r[0] == "goto":
            return self.face_then(r[1], "WAIT")
        if r[0] == "subgoal":
            self.pending_sub = r[1]
            return "SUBGOAL"
        return frontier_step(mem, self.obs["facing"], self.rng)

    def achieve_need(self, i):
        if self.obs["carried"] and self.aff[self.obs["carried"]][i] > 0:
            return "CONSUME"
        good = [K for K, g in self.aff.items() if g[i] > 0]
        cands = [(c, K) for K in good for c in self.mem.instances(K)
                 if self.mem.t - self.unavailable.get((self.mem.frame,) + tuple(c), -10 ** 9) > 150]
        if cands:
            c, K = min(cands, key=lambda x: max(abs(x[0][0] - self.mem.pos[0]), abs(x[0][1] - self.mem.pos[1])))
            return self.face_then(c, "CONSUME")
        alt = self.instrumental_for_need(i)
        if alt:
            return alt
        untried = [(c, K) for K in self.kinds() if self.tried[(K, "CONSUME")] < 3 and not self.aff.get(K) for c in self.mem.instances(K)]
        if untried:
            c, K = min(untried, key=lambda x: max(abs(x[0][0] - self.mem.pos[0]), abs(x[0][1] - self.mem.pos[1])))
            return self.face_then(c, "CONSUME")
        return frontier_step(self.mem, self.obs["facing"], self.rng)

    def instrumental_for_need(self, i):
        return None

    # ------------------------------------------------------------ inspection
    def export(self):
        return {"structures": [s.describe() for s in self.structs.values()], "aff": {k: dict(v) for k, v in self.aff.items()}}


# ================================================================ baselines
class B1Fixed(Agent):
    """Fixed catalogue + planner: needs first, then round-robin over interaction goals on every seen kind."""
    name = "B1"
    learn_every = None
    use_structures_in_goals = False

    def propose(self):
        cat = [f"{t}:{K}" for K in self.kinds() for t in ("poked", "picked", "consumed", "see")]
        if not cat:
            return None
        last = {}
        for g in self.logs.goals:
            last[g["formula"][0]] = g["t_logged"]
        p = min(cat, key=lambda q: (last.get(q, -1), q))
        return ([p], "catalogue", 0.5)


class B1M(B1Fixed):
    """B1 + passive structure learning used only instrumentally (structure can help existing goals, never becomes a
    top-level goal)."""
    name = "B1+M"
    learn_every = 2000

    def instrumental_for_need(self, i):
        good = {K for K, g in self.aff.items() if g[i] > 0}
        for s in self.structs.values():
            if s.form == "M1" and s.params["K2"] in good and s.params["ftype"] == "appear":
                top = s.predicates()[-1]
                self.pending_sub = top
                return "SUBGOAL"
        return None


class B2Random(Agent):
    name = "B2"

    def propose(self):
        preds = self.s0_predicates() + [p for p, _ in self.learned_predicates()]
        return ([self.rng.choice(preds)], "random", 0.0) if preds else None


class B3Novelty(Agent):
    """Count-based novelty over (kind, action, structure signature); no explicit goals except needs."""
    name = "B3"

    def propose(self):
        return None

    def execute(self):
        if self.goal_stack:
            return super().execute()
        sig = tuple(sorted(p for p, _ in self.learned_predicates() if self.holds(p)))
        best = None
        for K in self.kinds():
            c = self.nearest(K)
            if c is None:
                continue
            for a in ("POKE", "PICK", "CONSUME"):
                n = self.tried.get((K, a, sig), 0) + self.tried.get((K, a), 0)
                d = max(abs(c[0] - self.mem.pos[0]), abs(c[1] - self.mem.pos[1]))
                score = (n, d)
                if best is None or score < best[0]:
                    best = (score, c, a, K)
        if best is None or best[0][0] > 50:
            return frontier_step(self.mem, self.obs["facing"], self.rng)
        _, c, a, K = best
        step = self.face_then(c, a)
        if step == a:
            self.tried[(K, a, sig)] += 1
        return step


class B4LP(Agent):
    """Learning progress over L(S) with a passively learned goal space (Péré 2018 style)."""
    name = "B4"

    def lp(self, p):
        h = list(self.attempts.get(p, ()))
        if len(h) < 4:
            return 1.0                                        # optimistic for new goals
        half = len(h) // 2
        return abs(sum(h[half:]) / (len(h) - half) - sum(h[:half]) / half)

    def propose(self):
        preds = self.s0_predicates() + [p for p, _ in self.learned_predicates()]
        if not preds:
            return None
        w = [self.lp(p) + 0.05 for p in preds]
        p = self.rng.choices(preds, weights=w)[0]
        return ([p], "learning_progress", self.lp(p))


class B5Meta(B4LP):
    """PowerPlay-style: provisional structures (relaxed fit) are turned into new tasks; a structure is kept when its
    task is achieved; otherwise learning-progress goal selection as in B4."""
    name = "B5"

    def __init__(self, seed, learner_kwargs=None):
        super().__init__(seed, learner_kwargs)
        self.provisional = {}
        self.relaxed = Learner(min_prec=0.5, min_support=2, alpha=0.5)          # relaxed fit (amendment A3: alpha 0.5)

    def acquire(self):
        super().acquire()
        self.relaxed.next_sid = 10000 + len(self.provisional) * 10
        for s in self.relaxed.fit(self.mem, {**self.structs, **self.provisional}, self.mem.t):
            self.provisional[s.sid] = s
            self.replay(s)

    def tracked_structs(self):
        return {**self.structs, **self.provisional}

    def predicate_owner(self, p):
        return super().predicate_owner(p) or next((s for s in self.provisional.values() if p in s.predicates()), None)

    def propose(self):
        for sid, s in list(self.provisional.items()):
            p = s.predicates()[-1]
            if not any(g["formula"] == [p] for g in self.logs.goals[-20:]):
                return ([p], "meta_task", 1.0)
        return super().propose()

    def on_goal_end(self, formula, ok):
        for sid, s in list(self.provisional.items()):
            if formula[0] in s.predicates() and ok:
                del self.provisional[sid]
                self.add_structure(s, trigger="meta_confirmed")



ARMS = {"B1": B1Fixed, "B1+M": B1M, "B2": B2Random, "B3": B3Novelty, "B4": B4LP, "B5": B5Meta}
