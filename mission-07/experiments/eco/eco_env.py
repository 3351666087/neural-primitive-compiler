"""ECO: a persistent, partially observed developmental ecology for mechanism identification (Mission 07, Gate 1).
JUDGE SIDE. The judge holds the mechanism specification and every latent variable; an actor receives only `obs`.

World: an N x N grid with walls, objects of named kinds, one agent. The agent has two bounded need variables (food,
water) that decay with time and are restored by consuming resources. The world persists for the whole run: when a
need reaches 0 the agent's *life* ends and it is placed at a random free cell with full needs (counted as a life reset;
no penalty is applied anywhere); objects and latent states are untouched.

Mechanisms are data, not code: a mechanism family is a JSON document (see `family_alpha.json` and `DSL.md`)
interpreted here. It declares object kinds (visible features, latent variables, consumable resources, visibility
rules), placement counts, event rules (on poke / pick / drop / consume / tick), and nonstationarity events.

Legal observation (the only thing an actor sees):
  view      (2r+1) x (2r+1) cells centred on the agent: wall flag, visible object kind id (0 = none), visible
            feature bits of that object
  facing    the agent's facing direction (0..3)
  carried   kind id of the carried object (0 = none)
  needs     food, water (integers 0..100)
  feedback  result code of the last action: 0 no effect, 1 moved, 2 bumped, 3 poked, 4 picked, 5 dropped, 6 consumed
No global position, no latent value, no object identity beyond what is visible (two objects of a kind look alike).
"""

from __future__ import annotations

import copy
import json
import random
from dataclasses import dataclass, field
from pathlib import Path

ACTIONS = ("N", "E", "S", "W", "POKE", "PICK", "DROP", "CONSUME", "WAIT")
DIRS = ((0, -1), (1, 0), (0, 1), (-1, 0))
FEEDBACK = {"none": 0, "moved": 1, "bumped": 2, "poked": 3, "picked": 4, "dropped": 5, "consumed": 6}


@dataclass
class Obj:
    oid: int
    kind: str
    x: int
    y: int
    latent: dict = field(default_factory=dict)
    visible: dict = field(default_factory=dict)
    cooldown: int = 0
    revealed_until: int = -1
    carried: bool = False


class EcoWorld:
    def __init__(self, family: dict, seed: int, size: int = 11, view_radius: int = 2, need_decay_every: int = 8):
        self.fam, self.seed, self.N, self.r = family, seed, size, view_radius
        self.rng = random.Random(seed)
        self.need_decay_every = need_decay_every
        self.kinds = list(family["kinds"])
        self.kind_id = {k: i + 1 for i, k in enumerate(self.kinds)}
        self.t = 0
        self.lives = 0
        self.pending = []                     # (due_t, effect, context)
        self.events = []                      # judge-only event log: (t, name, details)
        self._generate()

    # ------------------------------------------------------------------ generation
    def _generate(self):
        N, rng = self.N, self.rng
        self.wall = [[x in (0, N - 1) or y in (0, N - 1) for x in range(N)] for y in range(N)]
        for _ in range(self.fam.get("interior_walls", 6)):
            x, y = rng.randrange(2, N - 2), rng.randrange(2, N - 2)
            self.wall[y][x] = True
        self.objs: list[Obj] = []
        free = [(x, y) for y in range(N) for x in range(N) if not self.wall[y][x]]
        rng.shuffle(free)
        oid = 0
        for kind, count in self.fam["placement"].items():
            spec = self.fam["kinds"][kind]
            for _ in range(count):
                x, y = free.pop()
                o = Obj(oid, kind, x, y, latent={v: d["init"] for v, d in spec.get("latent", {}).items()},
                        visible={f: 0 for f in spec.get("visible_features", [])})
                self.objs.append(o)
                oid += 1
        for rel in self.fam.get("relations", []):          # e.g. hidden pairings, assigned per seed
            self._assign_relation(rel)
        for c in self.fam.get("placement_constraints", []):
            self._apply_constraint(c, free)
        self.next_oid = oid
        self.ax, self.ay = free.pop()
        self.facing, self.carried = 0, None
        self.food = self.water = 100
        self.feedback = 0

    def _assign_relation(self, rel):
        objs = [o for o in self.objs if o.kind == rel["kind"]]
        self.rng.shuffle(objs)
        for a, b in zip(objs[0::2], objs[1::2]):
            a.latent[rel["name"]], b.latent[rel["name"]] = b.oid, a.oid

    def _apply_constraint(self, c, free):
        """'near': every object of kind A is moved next to some object of kind B (within distance d) if possible."""
        if c["type"] != "near":
            raise ValueError(c)
        targets = [o for o in self.objs if o.kind == c["to"]][c.get("target_offset", 0):]
        for i, o in enumerate([o for o in self.objs if o.kind == c["kind"]][: c.get("count", 10 ** 6)]):
            t = targets[i % len(targets)]
            cand = [(x, y) for (x, y) in free if max(abs(x - t.x), abs(y - t.y)) <= c["dist"]]
            if cand:
                free.append((o.x, o.y))
                o.x, o.y = cand[0]
                free.remove(cand[0])

    # ------------------------------------------------------------------ helpers
    def objs_at(self, x, y):
        return [o for o in self.objs if not o.carried and o.x == x and o.y == y]

    def cheb(self, a, b):
        return max(abs(a.x - b.x), abs(a.y - b.y))

    def is_visible(self, o):
        vis = self.fam["kinds"][o.kind].get("visibility", "always")
        if vis == "always":
            return True
        if vis == "revealed":
            return self.t <= o.revealed_until
        raise ValueError(vis)

    def facing_cell(self):
        dx, dy = DIRS[self.facing]
        return self.ax + dx, self.ay + dy

    # ------------------------------------------------------------------ expressions
    def ev(self, e, ctx):
        if isinstance(e, (int, float, bool)) or e is None:
            return e
        op = e[0]
        if op == "latent":
            o = self.ref(e[1], ctx)
            return None if o is None else o.latent.get(e[2])
        if op == "visible":
            o = self.ref(e[1], ctx)
            return None if o is None else o.visible.get(e[2])
        if op in ("==", "!=", "<", "<=", ">", ">="):
            a, b = self.ev(e[1], ctx), self.ev(e[2], ctx)
            if a is None or b is None:
                return False
            return {"==": a == b, "!=": a != b, "<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]
        if op == "and":
            return all(self.ev(x, ctx) for x in e[1:])
        if op == "or":
            return any(self.ev(x, ctx) for x in e[1:])
        if op == "not":
            return not self.ev(e[1], ctx)
        if op == "exists_near":                   # ["exists_near", kind, dist, where-expr with "it"]
            me = ctx["self"]
            for o in self.objs:
                if o.kind == e[1] and not o.carried and o is not me and self.cheb(o, me) <= e[2]:
                    if len(e) < 4 or self.ev(e[3], {**ctx, "it": o}):
                        return True
            return False
        if op == "since":                          # steps since the last event of this name on self
            return self.t - ctx["self"].latent.get("_last_" + e[1], -10 ** 9)
        if op == "chance":                         # ["chance", p]: Bernoulli draw from the world's generator
            return self.rng.random() < e[1]
        if op == "phase":                          # global phase for nonstationarity: (t // every) % k
            ph = self.fam.get("phase", {"every": 10 ** 9, "k": 1})
            return (self.t // ph["every"]) % ph["k"]
        raise ValueError(e)

    def ref(self, r, ctx):
        if r in ("self", "it"):
            return ctx.get(r)
        if isinstance(r, list) and r[0] == "related":          # ["related", relation-name]
            oid = ctx["self"].latent.get(r[1])
            return next((o for o in self.objs if o.oid == oid), None)
        if isinstance(r, list) and r[0] == "nearest":          # ["nearest", kind, dist, where]
            me = ctx["self"]
            cand = [o for o in self.objs if o.kind == r[1] and not o.carried and o is not me and self.cheb(o, me) <= r[2]
                    and (len(r) < 4 or self.ev(r[3], {**ctx, "it": o}))]
            return min(cand, key=lambda o: (self.cheb(o, me), o.oid)) if cand else None
        raise ValueError(r)

    # ------------------------------------------------------------------ effects
    def apply(self, eff, ctx):
        op = eff[0]
        if op == "delay":                                     # ["delay", steps, effect]
            self.pending.append((self.t + eff[1], eff[2], {k: v for k, v in ctx.items()}))
            return
        if op == "set":                                       # ["set", ref, var, value-expr]
            o = self.ref(eff[1], ctx)
            if o is not None:
                o.latent[eff[2]] = self.ev(eff[3], ctx)
        elif op == "inc":                                     # ["inc", ref, var, delta, lo, hi]
            o = self.ref(eff[1], ctx)
            if o is not None:
                o.latent[eff[2]] = max(eff[4], min(eff[5], o.latent.get(eff[2], 0) + eff[3]))
        elif op == "set_visible":                             # ["set_visible", ref, feature, value]
            o = self.ref(eff[1], ctx)
            if o is not None:
                o.visible[eff[2]] = eff[3]
        elif op == "spawn":                                   # ["spawn", kind, near-ref, max-dist]
            o = self.ref(eff[2], ctx)
            if o is not None:
                cells = [(o.x + dx, o.y + dy) for dx in range(-eff[3], eff[3] + 1) for dy in range(-eff[3], eff[3] + 1)]
                cells = [(x, y) for x, y in cells if 0 <= x < self.N and 0 <= y < self.N and not self.wall[y][x]
                         and not self.objs_at(x, y) and (x, y) != (self.ax, self.ay)]
                if cells:
                    x, y = self.rng.choice(cells)
                    spec = self.fam["kinds"][eff[1]]
                    self.objs.append(Obj(self.next_oid, eff[1], x, y,
                                         latent={v: d["init"] for v, d in spec.get("latent", {}).items()},
                                         visible={f: 0 for f in spec.get("visible_features", [])}))
                    self.next_oid += 1
                    self.events.append((self.t, "spawn", {"kind": eff[1], "near": o.oid}))
        elif op == "reveal":                                  # ["reveal", kind, dist, duration]
            me = ctx["self"]
            for o in self.objs:
                if o.kind == eff[1] and self.cheb(o, me) <= eff[2]:
                    o.revealed_until = max(o.revealed_until, self.t + eff[3])
                    self.events.append((self.t, "reveal", {"kind": eff[1], "oid": o.oid}))
        elif op == "mark":                                    # ["mark", event-name] -> remembers time on self
            ctx["self"].latent["_last_" + eff[1]] = self.t
        elif op == "log":
            self.events.append((self.t, eff[1], {"oid": ctx["self"].oid}))
        else:
            raise ValueError(eff)

    def fire(self, event, obj, extra=None):
        ctx = {"self": obj, **(extra or {})}
        for rule in self.fam["rules"]:
            if rule["on"] == event and rule["kind"] == obj.kind and self.ev(rule.get("guard", True), ctx):
                for eff in rule["effects"]:
                    self.apply(eff, ctx)
                if rule.get("exclusive", True):
                    break

    # ------------------------------------------------------------------ dynamics
    def step(self, action: int):
        a = ACTIONS[action]
        fb = "none"
        if a in ("N", "E", "S", "W"):
            self.facing = "NESW".index(a)
            nx, ny = self.facing_cell()
            blocked = self.wall[ny][nx] or any(self.fam["kinds"][o.kind].get("solid", False) for o in self.objs_at(nx, ny))
            if blocked:
                fb = "bumped"
            else:
                self.ax, self.ay = nx, ny
                fb = "moved"
        elif a == "POKE":
            fx, fy = self.facing_cell()
            tgt = [o for o in self.objs_at(fx, fy) if self.is_visible(o)]
            if tgt:
                self.fire("poke", tgt[0])
                fb = "poked"
        elif a == "PICK":
            fx, fy = self.facing_cell()
            tgt = [o for o in self.objs_at(fx, fy) if self.is_visible(o) and self.fam["kinds"][o.kind].get("pickable")]
            if tgt and self.carried is None:
                o = tgt[0]
                o.carried, self.carried = True, o
                self.fire("pick", o)
                fb = "picked"
        elif a == "DROP":
            fx, fy = self.facing_cell()
            if self.carried is not None and not self.wall[fy][fx] and not self.objs_at(fx, fy):
                o = self.carried
                o.carried, o.x, o.y, self.carried = False, fx, fy, None
                self.fire("drop", o)
                fb = "dropped"
        elif a == "CONSUME":
            cands = ([self.carried] if self.carried is not None else []) + \
                    [o for o in self.objs_at(*self.facing_cell()) if self.is_visible(o)]
            for o in cands:
                spec = self.fam["kinds"][o.kind].get("consumable")
                if spec and o.cooldown <= self.t:
                    if spec["need"] == "food":
                        self.food = min(100, self.food + spec["amount"])
                    else:
                        self.water = min(100, self.water + spec["amount"])
                    self.fire("consume", o)
                    self.events.append((self.t, "consume", {"kind": o.kind, "oid": o.oid}))
                    if spec.get("vanish"):
                        if o is self.carried:
                            self.carried = None
                        self.objs.remove(o)
                    else:
                        o.cooldown = self.t + spec.get("cooldown", 0)
                    fb = "consumed"
                    break
        self.t += 1
        for o in list(self.objs):                       # tick rules
            self.fire("tick", o)
        due = [p for p in self.pending if p[0] <= self.t]
        self.pending = [p for p in self.pending if p[0] > self.t]
        for _t, eff, ctx in due:
            if ctx.get("self") in self.objs:
                self.apply(eff, ctx)
        for ns in self.fam.get("nonstationarity", []):
            if self.t % ns["every"] == 0 and ns["type"] == "reshuffle_relation":
                self._assign_relation(ns)
                self.events.append((self.t, "reshuffle", {"relation": ns["name"]}))
        if self.t % self.need_decay_every == 0:
            self.food, self.water = max(0, self.food - 1), max(0, self.water - 1)
        if self.food == 0 or self.water == 0:
            self.lives += 1
            self.events.append((self.t, "life_reset", {}))
            free = [(x, y) for y in range(self.N) for x in range(self.N) if not self.wall[y][x] and not self.objs_at(x, y)]
            self.ax, self.ay = self.rng.choice(free)
            self.food = self.water = 100
            if self.carried is not None:
                self.carried.carried, self.carried.x, self.carried.y = False, self.ax, self.ay
                self.carried = None
        self.feedback = FEEDBACK[fb]
        return self.observe()

    # ------------------------------------------------------------------ observation (legal)
    def observe(self):
        r = self.r
        view = []
        for dy in range(-r, r + 1):
            row = []
            for dx in range(-r, r + 1):
                x, y = self.ax + dx, self.ay + dy
                if not (0 <= x < self.N and 0 <= y < self.N) or self.wall[y][x]:
                    row.append((1, 0, ()))
                    continue
                vis = [o for o in self.objs_at(x, y) if self.is_visible(o)]
                if vis:
                    o = vis[0]
                    row.append((0, self.kind_id[o.kind], tuple(o.visible[f] for f in sorted(o.visible))))
                else:
                    row.append((0, 0, ()))
            view.append(tuple(row))
        return {"view": tuple(view), "facing": self.facing,
                "carried": self.kind_id[self.carried.kind] if self.carried is not None else 0,
                "needs": (self.food, self.water), "feedback": self.feedback}

    # ------------------------------------------------------------------ judge-only access
    def latent_snapshot(self):
        return {o.oid: {"kind": o.kind, "x": o.x, "y": o.y, "carried": o.carried,
                        **{k: v for k, v in o.latent.items() if not k.startswith("_")}} for o in self.objs}

    def clone(self):
        return copy.deepcopy(self)


def load_family(path):
    return json.loads(Path(path).read_text())
