"""Craftax-Classic agent substrate and arms for Mission 07 (Gate 4; PROTOCOL.md sections 3-4). AGENT SIDE.

Pure Python. Each step the agent receives the official symbolic observation (1,345 floats) and a flag that a new
world started (the game itself shows a fresh world; the flag spares the agent from detecting it), and returns an
action index 0..16. No reward, achievement or judge information is ever received.

Designer knowledge shared by every arm (KNOWLEDGE_PROVENANCE.md section 2):
  - the observation layout (7 x 9 view of 17 block ids and 4 mob ids, 12 inventory counts / 10, 4 vitals / 10,
    facing one-hot, light, sleeping) and that the player sits at the centre of the view;
  - action names, that LEFT / RIGHT / UP / DOWN turn the player and move it one cell if it can, and that DO / PLACE_*
    act on the facing cell;
  - dead reckoning from the view's shift; a planner (BFS) and frontier exploration.
Learned from the agent's own experience: which blocks can be walked on, which actions change the inventory, the
vitals or the facing block, and under which conditions (structure form M6), where blocks were seen (M3).

Structure forms:
  M6 Rule   action a, preconditions (<= 3 literals among face:B, near:B (8-neighbourhood), inv:i>=k), effect
            (inventory deltas, facing-block change); selected by a likelihood-ratio test as in the ECO learner
            (amendment A3): effect probability when the preconditions hold vs. when they do not.
  M3 Place  blocks of kind B persist where they were seen; predicate memnear:B (a remembered B within Chebyshev
            distance 6 of the player and outside the view).
Goal language L(S): S0 = inv:i>=k (k <= 9), face:B, near:B, see:B, hi:v (vital v >= 7); learned: memnear:B.
"""

from __future__ import annotations

import itertools
import math
import random
from collections import Counter, defaultdict, deque
from statistics import NormalDist

ROWS, COLS, NB, NM = 7, 9, 17, 4
CR, CC = 3, 4
ITEMS = ("wood", "stone", "coal", "iron", "diamond", "sapling", "wood_pickaxe", "stone_pickaxe", "iron_pickaxe",
         "wood_sword", "stone_sword", "iron_sword")
VITALS = ("health", "food", "drink", "energy")
ACTIONS = ("NOOP", "LEFT", "RIGHT", "UP", "DOWN", "DO", "SLEEP", "PLACE_STONE", "PLACE_TABLE", "PLACE_FURNACE",
           "PLACE_PLANT", "MAKE_WOOD_PICKAXE", "MAKE_STONE_PICKAXE", "MAKE_IRON_PICKAXE", "MAKE_WOOD_SWORD",
           "MAKE_STONE_SWORD", "MAKE_IRON_SWORD")
A = {a: i for i, a in enumerate(ACTIONS)}
MOVES = {"LEFT": (0, -1), "RIGHT": (0, 1), "UP": (-1, 0), "DOWN": (1, 0)}
FACING = ("LEFT", "RIGHT", "UP", "DOWN")          # facing one-hot index order
ACTING = ("DO",) + tuple(a for a in ACTIONS if a.startswith(("PLACE", "MAKE"))) + ("SLEEP",)
GOAL_T = 600
NEED_LOW = 3


def cheb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def parse(v):
    base = ROWS * COLS * (NB + NM)
    blocks, mobs = [], []
    for r in range(ROWS):
        br, mr = [], []
        for c in range(COLS):
            o = (r * COLS + c) * (NB + NM)
            seg = v[o:o + NB]
            br.append(max(range(NB), key=seg.__getitem__))
            m = v[o + NB:o + NB + NM]
            mr.append(next((i + 1 for i, x in enumerate(m) if x > 0.5), 0))
        blocks.append(br)
        mobs.append(mr)
    inv = tuple(int(round(x * 10)) for x in v[base:base + 12])
    vit = tuple(int(round(x * 10)) for x in v[base + 12:base + 16])
    fd = max(range(4), key=lambda i: v[base + 16 + i])
    return {"blocks": blocks, "mobs": mobs, "inv": inv, "vit": vit, "facing": FACING[fd], "light": v[base + 20],
            "sleeping": v[base + 21] > 0.5}


class Memory:
    def __init__(self):
        self.frame = 0
        self.pos = (0, 0)
        self.t = 0
        self.cells = {}                 # (frame, R, C) -> (block, t_seen)
        self.walk = Counter()           # block -> times stood on
        self.block_ct = Counter()       # block -> times a move into it was refused
        self.events = []                # per acting step: action, literals before, deltas
        self.prev = None
        self.poses = []

    def is_walkable(self, b):
        if self.walk[b] > 0:
            return True
        return self.block_ct[b] == 0

    def absolute(self, r, c):
        return (self.pos[0] + r - CR, self.pos[1] + c - CC)

    def literals(self, o):
        lits = set()
        fr, fc = (CR + MOVES[o["facing"]][0], CC + MOVES[o["facing"]][1])
        lits.add(f"face:{o['blocks'][fr][fc]}")
        if o["mobs"][fr][fc]:
            lits.add(f"facemob:{o['mobs'][fr][fc]}")
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr or dc:
                    lits.add(f"near:{o['blocks'][CR + dr][CC + dc]}")
        for i, k in enumerate(o["inv"]):
            for v in range(1, min(k, 9) + 1):
                lits.add(f"inv:{i}>={v}")
        return lits

    def observe(self, o, last_action, new_world):
        self.t += 1
        if new_world:
            self.frame += 1
            self.pos = (0, 0)
            self.events.append({"t": self.t, "type": "reset", "frame": self.frame})
        elif self.prev is not None and last_action in MOVES:
            dr, dc = MOVES[last_action]
            old, new = self.prev["blocks"], o["blocks"]
            moved = stay = 0
            for r in range(ROWS):
                for c in range(COLS):
                    if new[r][c] == old[r][c]:
                        stay += 1
                    r2, c2 = r + dr, c + dc
                    if 0 <= r2 < ROWS and 0 <= c2 < COLS and new[r][c] == old[r2][c2]:
                        moved += 1
            tgt = self.prev["blocks"][CR + dr][CC + dc]
            if moved * 63 > stay * 56 and moved > stay * 0.9:          # overlap is 56 cells after a move, 63 if not
                self.pos = (self.pos[0] + dr, self.pos[1] + dc)
                self.walk[tgt] += 1
            else:
                self.block_ct[tgt] += 1
        for r in range(ROWS):
            for c in range(COLS):
                R, C = self.absolute(r, c)
                self.cells[(self.frame, R, C)] = (o["blocks"][r][c], self.t)
        self.poses.append((self.t, self.frame) + self.pos)
        if self.prev is not None and not new_world and last_action in ACTING:
            p = self.prev
            fr, fc = CR + MOVES[p["facing"]][0], CC + MOVES[p["facing"]][1]
            dinv = tuple(b - a for a, b in zip(p["inv"], o["inv"]))
            dvit = tuple(b - a for a, b in zip(p["vit"], o["vit"]))
            fb_before = p["blocks"][fr][fc]
            fr2, fc2 = CR + MOVES[o["facing"]][0], CC + MOVES[o["facing"]][1]
            fb_after = o["blocks"][fr2][fc2]
            self.events.append({"t": self.t, "type": "act", "frame": self.frame, "action": last_action,
                                "lits": self.literals(p), "dinv": dinv, "dvit": dvit,
                                "block": (fb_before, fb_after) if fb_before != fb_after else None,
                                "mob": p["mobs"][fr][fc]})
        self.prev = o

    def facing_cell(self, o):
        dr, dc = MOVES[o["facing"]]
        return (self.pos[0] + dr, self.pos[1] + dc)

    def known(self, B):
        return [(R, C) for (f, R, C), (b, ts) in self.cells.items() if f == self.frame and b == B]

    def passable(self, R, C):
        v = self.cells.get((self.frame, R, C))
        return True if v is None else self.is_walkable(v[0])


def plan_to_face(mem, facing, target, max_nodes=6000):
    """Actions that end next to `target` facing it (BFS over (cell, facing); a move into a non-walkable cell only
    turns the player)."""
    start = (mem.pos[0], mem.pos[1], facing)
    goals = {(target[0] - dr, target[1] - dc, d) for d, (dr, dc) in MOVES.items()}
    if start in goals:
        return []
    prev = {start: None}
    q = deque([start])
    n = 0
    while q and n < max_nodes:
        st = q.popleft()
        n += 1
        r, c, f = st
        for d, (dr, dc) in MOVES.items():
            nr, nc = r + dr, c + dc
            ns = (nr, nc, d) if (nr, nc) != tuple(target) and mem.passable(nr, nc) else (r, c, d)
            if ns in prev:
                continue
            prev[ns] = (st, d)
            if ns in goals:
                path = []
                while prev[ns] is not None:
                    ns, a = prev[ns]
                    path.append(a)
                return path[::-1]
            q.append(ns)
    return None


def frontier_step(mem, rng):
    start = mem.pos
    prev = {start: None}
    q = deque([start])
    while q and len(prev) < 4000:
        c = q.popleft()
        if (mem.frame,) + c not in mem.cells:
            path = []
            while prev[c] is not None:
                c, a = prev[c]
                path.append(a)
            return path[-1] if path else rng.choice(list(MOVES))
        for d, (dr, dc) in MOVES.items():
            n = (c[0] + dr, c[1] + dc)
            if n not in prev and mem.passable(*n):
                prev[n] = (c, d)
                q.append(n)
    return rng.choice(list(MOVES))


# ---------------------------------------------------------------- structures
class Rule:
    form = "M6"

    def __init__(self, sid, params, stats, evidence, t_created):
        self.sid, self.params, self.stats, self.evidence, self.t_created = sid, params, stats, evidence, t_created

    def predicates(self):
        return []

    def describe(self):
        return {"struct_id": self.sid, "form": self.form, "params": self.params, "stats": self.stats, "predicates": [],
                "t_created": self.t_created, "data_provenance": self.evidence[:200], "n_evidence": len(self.evidence)}


class Place:
    form = "M3"

    def __init__(self, sid, params, stats, evidence, t_created):
        self.sid, self.params, self.stats, self.evidence, self.t_created = sid, params, stats, evidence, t_created

    def predicates(self):
        return [f"memnear:{self.params['B']}"]

    def value(self, mem):
        B = self.params["B"]
        for (R, C) in mem.known(B):
            if cheb((R, C), mem.pos) <= 6 and not (abs(R - mem.pos[0]) <= CR and abs(C - mem.pos[1]) <= CC):
                return True
        return False

    def describe(self):
        return {"struct_id": self.sid, "form": self.form, "params": self.params, "stats": self.stats,
                "predicates": self.predicates(), "t_created": self.t_created, "data_provenance": self.evidence[:200],
                "n_evidence": len(self.evidence)}


class RuleLearner:
    """M6 rules by a likelihood-ratio test (alpha 0.01, Bonferroni over the hypotheses scored in one fit), M3 by
    revisits: a block kind seen again at the same cell after it left the view at least `min_support` times."""

    def __init__(self, window=20000, min_support=3, alpha=0.01, blocked=()):
        self.window, self.min_support, self.alpha, self.blocked = window, min_support, alpha, set(blocked)
        self.next_sid = 0

    @staticmethod
    def _ll(k, n):
        if n == 0:
            return 0.0
        q = (k + 0.5) / (n + 1)
        return k * math.log(q) + (n - k) * math.log(1 - q)

    def lr2(self, k1, n1, k0, n0):
        return 2 * (self._ll(k1, n1) + self._ll(k0, n0) - self._ll(k1 + k0, n1 + n0))

    @staticmethod
    def effect_of(e):
        inv = tuple((ITEMS[i], d) for i, d in enumerate(e["dinv"]) if d)
        return (inv, e["block"])

    def fit(self, mem, have, t_now):
        ev = [e for e in mem.events if e["type"] == "act" and e["t"] >= t_now - self.window]
        held = {(s.params.get("action"), repr(s.params.get("effect"))) for s in have.values() if s.form == "M6"}
        by_action = defaultdict(list)
        for e in ev:
            by_action[e["action"]].append(e)
        rows = []
        for a, lst in by_action.items():
            effects = Counter(self.effect_of(e) for e in lst if self.effect_of(e) != ((), None))
            for eff, n in effects.items():
                if n < self.min_support or (a, repr(eff)) in held or (a, repr(eff)) in self.blocked:
                    continue
                pos = [e for e in lst if self.effect_of(e) == eff]
                common = set.intersection(*(e["lits"] for e in pos))
                # rank literals by how well they separate, keep the 8 best, search conjunctions of <= 3
                def sep(l):
                    k1 = sum(1 for e in pos if l in e["lits"])
                    n1 = sum(1 for e in lst if l in e["lits"])
                    return -(n1 - k1)
                cands = sorted(common, key=lambda l: (sep(l), l))[:8]
                for r in (1, 2, 3):
                    for combo in itertools.combinations(cands, r):
                        cs = set(combo)
                        n1 = k1 = n0 = k0 = 0
                        for e in lst:
                            y = self.effect_of(e) == eff
                            if cs <= e["lits"]:
                                n1 += 1
                                k1 += y
                            else:
                                n0 += 1
                                k0 += y
                        if n1 == 0 or k1 * (n0 + 1) <= k0 * (n1 + 1):
                            continue
                        rows.append((self.lr2(k1, n1, k0, n0), k1, n1, k0, n0, a, eff, tuple(sorted(cs)),
                                     [e["t"] for e in pos]))
        out = []
        if rows:
            crit = NormalDist().inv_cdf(1 - self.alpha / len(rows) / 2) ** 2
            best = {}
            for r in rows:
                if r[0] >= crit and r[1] >= self.min_support:
                    key = (r[5], repr(r[6]))
                    if key not in best or (round(r[0], 6), -len(r[7])) > (round(best[key][0], 6), -len(best[key][7])):
                        best[key] = r
            for key, r in best.items():
                s = Rule(self.next_sid, {"action": r[5], "effect": r[6], "pre": list(r[7])},
                         {"lr2": round(r[0], 3), "critical": round(crit, 3), "hypotheses": len(rows), "k1": r[1], "n1": r[2],
                          "k0": r[3], "n0": r[4]}, r[8], t_now)
                self.next_sid += 1
                out.append(s)
        # M3: kinds re-seen at the same cell after leaving the view
        held3 = {s.params.get("B") for s in have.values() if s.form == "M3"}
        revis = getattr(mem, "revisits", Counter())
        for B, n in revis.items():
            if n >= self.min_support and B not in held3 and ("M3", B) not in self.blocked:
                out.append(Place(self.next_sid, {"B": B}, {"revisits": n}, [], t_now))
                self.next_sid += 1
        return out


# ---------------------------------------------------------------- agents
class Agent:
    name = "base"
    learn_every = 2000
    use_structures_in_goals = True

    def __init__(self, seed, **kw):
        self.rng = random.Random(seed)
        self.mem = Memory()
        self.mem.revisits = Counter()
        self.learner = RuleLearner()
        self.structs = {}
        self.goal_stack = []
        self.last_action = "NOOP"
        self.o = None
        self.goals, self.actions_log, self.structures_log, self.deletions = [], [], [], []
        self.attempts = defaultdict(deque)
        self.aff = defaultdict(Counter)            # (action, face literal) -> Counter{vital: gain}
        self.fails = 0
        self.left_view = {}                        # (frame, R, C) -> block, cells that left the view

    # ---------------- predicates
    def s0_predicates(self):
        inv = self.o["inv"]
        out = [f"inv:{i}>={k}" for i in range(12) for k in (1, 2) if self.ever_had(i)]
        blocks = sorted({b for (f, R, C), (b, ts) in self.mem.cells.items() if f == self.mem.frame})
        out += [f"face:{b}" for b in blocks] + [f"near:{b}" for b in blocks]
        out += [f"hi:{v}" for v in (1, 2, 3)]
        return out

    def ever_had(self, i):
        return any(e["type"] == "act" and e["dinv"][i] > 0 for e in self.mem.events[-5000:]) or self.o["inv"][i] > 0

    def learned_predicates(self):
        if not self.use_structures_in_goals:
            return []
        return [(p, s.sid) for s in self.structs.values() for p in s.predicates()]

    def holds(self, p):
        o = self.o
        typ, arg = p.split(":", 1)
        if typ == "inv":
            i, k = arg.split(">=")
            return o["inv"][int(i)] >= int(k)
        if typ == "hi":
            return o["vit"][int(arg)] >= 7
        if typ in ("face", "near", "see"):
            B = int(arg)
            fr, fc = CR + MOVES[o["facing"]][0], CC + MOVES[o["facing"]][1]
            if typ == "face":
                return o["blocks"][fr][fc] == B
            if typ == "near":
                return any(o["blocks"][CR + dr][CC + dc] == B for dr in (-1, 0, 1) for dc in (-1, 0, 1) if dr or dc)
            return any(B in row for row in o["blocks"])
        if typ == "memnear":
            s = next((s for s in self.structs.values() if p in s.predicates()), None)
            return bool(s) and s.value(self.mem)
        return False

    def owner(self, p):
        return next((s for s in self.structs.values() if p in s.predicates()), None)

    # ---------------- goals
    def log_goal(self, formula, reason, priority=0.0, parent=None, provenance=None):
        prov = provenance or [("S0" if self.owner(p) is None else f"struct:{self.owner(p).sid}") for p in formula]
        gid = len(self.goals)
        self.goals.append({"goal_id": gid, "t_logged": self.mem.t, "formula": formula, "provenance": prov,
                           "priority": round(priority, 4), "reason": reason, "parent_goal": parent})
        self.goal_stack.append([gid, formula, self.mem.t, parent])
        return gid

    def finish_goal(self, ok):
        gid, formula, t0, parent = self.goal_stack.pop()
        dq = self.attempts[formula[0]]
        dq.append(1 if ok else 0)
        while len(dq) > 20:
            dq.popleft()
        self.fails = 0

    def need_goal(self):
        v = self.o["vit"]
        for i in (2, 1, 3):                                     # drink, food, energy
            if v[i] <= NEED_LOW:
                return i
        return None

    # ---------------- main step
    def act(self, vec, new_world):
        o = parse(vec)
        self.o = o
        prev_cells = None
        self.mem.observe(o, self.last_action, new_world)
        if new_world:
            self.goal_stack.clear()
        self.track_revisits()
        for e in self.mem.events[-1:]:
            if e["type"] == "act" and e["t"] == self.mem.t:
                face = next((l for l in e["lits"] if l.startswith("face:")), None)
                key = (e["action"], face if not e["mob"] else f"mob:{e['mob']}")
                for i, d in enumerate(e["dvit"]):
                    if d > 0:
                        self.aff[key][i] += d
        if self.learn_every and self.mem.t % self.learn_every == 0:
            self.acquire()
        self.manage_goals()
        a = self.execute()
        self.last_action = a
        self.actions_log.append((self.mem.t, A[a], self.goal_stack[-1][0] if self.goal_stack else None))
        return A[a]

    def track_revisits(self):
        mem = self.mem
        vis = {(mem.frame, mem.pos[0] + dr, mem.pos[1] + dc) for dr in range(-CR, CR + 1) for dc in range(-CC, CC + 1)}
        for k in list(self.left_view):
            if k in vis:
                b = self.left_view.pop(k)
                if mem.cells.get(k, (None,))[0] == b and b not in (2,):          # grass excluded as background
                    mem.revisits[b] += 1
        if mem.poses and len(mem.poses) > 1:
            t, f, r, c = mem.poses[-2]
            if f == mem.frame and (r, c) != mem.pos:
                for dr in range(-CR, CR + 1):
                    for dc in range(-CC, CC + 1):
                        k = (f, r + dr, c + dc)
                        if k not in vis and k in mem.cells and len(self.left_view) < 5000:
                            self.left_view[k] = mem.cells[k][0]

    def acquire(self):
        for s in self.learner.fit(self.mem, self.structs, self.mem.t):
            self.structs[s.sid] = s
            self.structures_log.append({**s.describe(), "trigger": "periodic"})

    def completed(self, gid, formula):
        return all(self.holds(p) for p in formula)

    def manage_goals(self):
        while self.goal_stack:
            gid, formula, t0, parent = self.goal_stack[-1]
            if self.completed(gid, formula):
                self.finish_goal(True)
            elif self.mem.t - t0 > GOAL_T or self.fails >= 40:
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
                self.log_goal(g[0], g[1], g[2])

    def propose(self):
        return None

    # ---------------- executor
    def execute(self):
        if self.o["sleeping"]:
            return "NOOP"
        if not self.goal_stack:
            return frontier_step(self.mem, self.rng)
        gid, formula, t0, parent = self.goal_stack[-1]
        p = next((q for q in formula if not self.holds(q)), formula[0])
        step = self.achieve(p, depth=0)
        if step is None:
            self.fails += 1
            return frontier_step(self.mem, self.rng)
        return step

    def go_face(self, B):
        cells = self.mem.known(B)
        if not cells:
            return frontier_step(self.mem, self.rng)
        cells.sort(key=lambda c: cheb(c, self.mem.pos))
        for c in cells[:5]:
            path = plan_to_face(self.mem, self.o["facing"], c)
            if path is not None:
                return path[0] if path else "FACED"
        return frontier_step(self.mem, self.rng)

    def rules_for(self, typ, arg):
        out = []
        for s in self.structs.values():
            if s.form != "M6":
                continue
            inv, blk = s.params["effect"]
            if typ == "inv" and any(ITEMS.index(n) == arg and d > 0 for n, d in inv):
                out.append(s)
            if typ == "block" and blk is not None and blk[1] == arg:
                out.append(s)
        return sorted(out, key=lambda s: -s.stats["k1"] / max(1, s.stats["n1"]))

    def achieve(self, p, depth):
        if depth > 5:
            return None
        typ, arg = p.split(":", 1)
        if typ == "hi":
            return self.achieve_vital(int(arg))
        if typ in ("face", "see"):
            st = self.go_face(int(arg))
            return "NOOP" if st == "FACED" else st
        if typ == "near":
            B = int(arg)
            if self.mem.known(B):
                st = self.go_face(B)
                return "NOOP" if st == "FACED" else st
            for s in self.rules_for("block", B):                 # make the block by an action (e.g. placing it)
                st = self.apply_rule(s, depth)
                if st:
                    return st
            return frontier_step(self.mem, self.rng)
        if typ == "inv":
            i, k = arg.split(">=")
            for s in self.rules_for("inv", int(i)):
                st = self.apply_rule(s, depth)
                if st:
                    return st
            return None
        if typ == "memnear":
            s = self.owner(p)
            if s is None:
                return None
            cells = [c for c in self.mem.known(s.params["B"]) if cheb(c, self.mem.pos) > 3]
            if not cells:
                return frontier_step(self.mem, self.rng)
            c = min(cells, key=lambda c: cheb(c, self.mem.pos))
            path = plan_to_face(self.mem, self.o["facing"], c)
            return path[0] if path else frontier_step(self.mem, self.rng)
        return None

    def apply_rule(self, s, depth):
        """Next primitive action toward applying rule s: satisfy its preconditions in order, then perform it."""
        for lit in s.params["pre"]:
            if not self.holds(lit):
                typ, arg = lit.split(":", 1)
                if typ == "face":
                    st = self.go_face(int(arg))
                    if st == "FACED":
                        continue
                    return st
                if typ == "facemob":
                    return None
                return self.achieve(lit, depth + 1)
        return s.params["action"]

    def achieve_vital(self, i):
        good = [(k, g[i]) for k, g in self.aff.items() if g[i] > 0]
        good.sort(key=lambda x: -x[1])
        for (action, face), gain in good:
            if action == "SLEEP":
                return "SLEEP"
            if face and face.startswith("face:"):
                B = int(face.split(":")[1])
                st = self.go_face(B)
                if st == "FACED":
                    return action
                return st
            if face and face.startswith("mob:"):
                st = self.chase_mob(int(face.split(":")[1]))
                if st == "FACED":
                    return action
                return st
        # untried: try DO on the nearest unfamiliar visible thing
        return self.explore_act()

    def chase_mob(self, m):
        o = self.o
        best = None
        for r in range(ROWS):
            for c in range(COLS):
                if o["mobs"][r][c] == m:
                    d = abs(r - CR) + abs(c - CC)
                    if best is None or d < best[0]:
                        best = (d, (self.mem.pos[0] + r - CR, self.mem.pos[1] + c - CC))
        if best is None:
            return frontier_step(self.mem, self.rng)
        path = plan_to_face(self.mem, o["facing"], best[1])
        if path is None:
            return frontier_step(self.mem, self.rng)
        return path[0] if path else "FACED"

    def explore_act(self):
        o = self.o
        fr, fc = CR + MOVES[o["facing"]][0], CC + MOVES[o["facing"]][1]
        if o["blocks"][fr][fc] not in (2,) or o["mobs"][fr][fc]:
            return "DO"
        return frontier_step(self.mem, self.rng)

    def export(self):
        return {"structures": [s.describe() for s in self.structs.values()],
                "aff": {repr(k): dict(v) for k, v in self.aff.items()}}

    def dump(self):
        return {"goals": self.goals, "actions": self.actions_log, "structures": self.structures_log,
                "deletions": self.deletions, "export": self.export()}


class RandomArm(Agent):
    name = "RANDOM"
    learn_every = None

    def act(self, vec, new_world):
        self.o = parse(vec)
        self.mem.t += 1
        a = self.rng.choice(ACTIONS)
        self.actions_log.append((self.mem.t, A[a], None))
        return A[a]


class B1Fixed(Agent):
    """Fixed catalogue: needs, then round-robin over face:B / near:B for seen blocks and each acting action once
    per block (no learning)."""
    name = "B1"
    learn_every = None
    use_structures_in_goals = False

    def propose(self):
        blocks = sorted({b for (f, R, C), (b, ts) in self.mem.cells.items() if f == self.mem.frame})
        cat = [f"face:{b}" for b in blocks]
        if not cat:
            return None
        last = {}
        for g in self.goals:
            last[g["formula"][0]] = g["t_logged"]
        p = min(cat, key=lambda q: (last.get(q, -1), q))
        return ([p], "catalogue", 0.5)

    def execute(self):
        if self.goal_stack and self.goal_stack[-1][1][0].startswith("face:") and self.holds(self.goal_stack[-1][1][0]):
            return self.rng.choice(ACTING[:-1])                  # act on what is faced
        return super().execute()


class B4LP(Agent):
    """Learning progress over L(S) with a passively learned goal space."""
    name = "B4"

    def lp(self, p):
        h = list(self.attempts.get(p, ()))
        if len(h) < 4:
            return 1.0
        half = len(h) // 2
        return abs(sum(h[half:]) / (len(h) - half) - sum(h[:half]) / half)

    def propose(self):
        preds = self.s0_predicates() + [p for p, _ in self.learned_predicates()]
        if not preds:
            return None
        w = [self.lp(p) + 0.05 for p in preds]
        p = self.rng.choices(preds, weights=w)[0]
        return ([p], "learning_progress", self.lp(p))


class B3Novelty(Agent):
    """Count-based novelty over (facing block, action): no goals except needs."""
    name = "B3"

    def __init__(self, seed, **kw):
        super().__init__(seed, **kw)
        self.tried = Counter()

    def execute(self):
        if self.goal_stack:
            return super().execute()
        o = self.o
        fr, fc = CR + MOVES[o["facing"]][0], CC + MOVES[o["facing"]][1]
        fb = o["blocks"][fr][fc]
        opts = [(self.tried[(fb, a)], a) for a in ACTING]
        n, a = min(opts)
        if n < 3:
            self.tried[(fb, a)] += 1
            return a
        return frontier_step(self.mem, self.rng)


class Candidate(B4LP):
    """The ECO candidate's organisation ported to Craftax: needs, learning progress over L(S), and experiment goals
    X1 (action a while facing block B: each (a, B) pair untested until 3 trials, 8 if an inventory or block effect
    followed), with acquisition after experiments (at most every 200 steps) and every 2,000 steps."""
    name = "CAND"

    def __init__(self, seed, **kw):
        super().__init__(seed, **kw)
        self.tests = Counter()
        self.effects = Counter()
        self.exp = None
        self.last_fit = 0

    def propose(self):
        pool = []
        blocks = sorted({b for (f, R, C), (b, ts) in self.mem.cells.items() if f == self.mem.frame})
        for B in blocks:
            for a in ACTING:
                key = (a, B)
                n, m = self.tests[key], self.effects[key]
                v = max(0.0, 1.0 - n / (8 if m else 3))
                if v > 0:
                    pool.append((v, ("exp", key)))
        for p in self.s0_predicates() + [p for p, _ in self.learned_predicates()]:
            pool.append((self.lp(p) + 0.05, ("mastery", p)))
        if not pool:
            return None
        w, ch = self.rng.choices(pool, weights=[x[0] for x in pool])[0]
        if ch[0] == "mastery":
            return ([ch[1]], "mastery", w)
        a, B = ch[1]
        self.exp = {"key": ch[1], "action": a, "B": B, "done": False, "t0": self.mem.t}
        return ([f"face:{B}"], "experiment", w)

    def log_goal(self, formula, reason, priority=0.0, parent=None, provenance=None):
        gid = super().log_goal(formula, reason, priority, parent, provenance)
        if reason == "experiment" and self.exp is not None:
            self.exp["gid"] = gid
            self.goals[-1]["plan"] = {"action": self.exp["action"], "B": self.exp["B"]}
        return gid

    def completed(self, gid, formula):
        if self.exp is not None and gid == self.exp.get("gid"):
            return False                                        # an experiment ends when its action was performed
        return super().completed(gid, formula)

    def manage_goals(self):
        if self.exp is not None and self.goal_stack and self.goal_stack[-1][0] == self.exp.get("gid"):
            if self.exp["done"] or self.mem.t - self.exp["t0"] > GOAL_T:
                gid = self.goal_stack.pop()[0]
                key = self.exp["key"]
                self.tests[key] += 1
                hit = any(e["type"] == "act" and e["t"] >= self.exp["t0"] and (any(e["dinv"]) or e["block"])
                          for e in self.mem.events[-50:])
                if hit:
                    self.effects[key] += 1
                self.goals[gid]["outcome"] = "done" if self.exp["done"] else "timeout"
                self.exp = None
                if self.learn_every and self.mem.t - self.last_fit >= 200:
                    self.last_fit = self.mem.t
                    self.acquire()
        return super().manage_goals()

    def execute(self):
        if self.exp is not None and self.goal_stack and self.goal_stack[-1][0] == self.exp.get("gid") and not self.o["sleeping"]:
            st = self.go_face(self.exp["B"])
            if st == "FACED":
                self.exp["done"] = True
                return self.exp["action"]
            return st
        return super().execute()


ARMS = {c.name: c for c in (RandomArm, B1Fixed, B3Novelty, B4LP, Candidate)}
