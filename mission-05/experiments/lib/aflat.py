"""A-FLAT: no achievers, no priority composition. A reactive decision list over cell-level and agent-relative
features and the primitive actions, learned from optimal plans (decision-list induction from solved examples, in
the style of Khardon 1999), verified on V_train by step-level simulation, with counterexamples fed back.
CONSTRUCTOR SIDE (own step model; instances are plain data from the runner).

Features of a state (all Boolean): here_k (colour under the agent, k = 0..4), hand_k (k = 0..4), lex_k / rex_k
(colour k exists strictly left / right of the agent, k = 1..4), hazhere, goal (the whole goal holds).
Rules: a conjunction of at most two literals -> one action. The first matching rule acts; none = NOOP.
Learning: BFS gives the set of optimal actions in every state on optimal paths of the training examples; greedy
induction adds the rule that covers the most remaining states with an optimal action and never a non-optimal one.
"""

from __future__ import annotations

import itertools
import random
import time
from collections import deque

from model import holds, rc, step_limit

ACTS = ("LEFT", "RIGHT", "PICK", "DROP", "STOP")


def lstep(spec, inst, state, a):
    cells, ag, hand = state
    N = len(cells)
    b = inst["binding"]
    if a == "LEFT":
        return (cells, max(0, ag - 1), hand), False
    if a == "RIGHT":
        return (cells, min(N - 1, ag + 1), hand), False
    if a == "PICK":
        if hand == 0 and cells[ag]:
            if any(s[0] == "NO_PICK" and rc(s[1], b) == cells[ag] for s in spec["safety"]):
                return state, True
            c = list(cells)
            h, c[ag] = c[ag], 0
            return (tuple(c), ag, h), False
        return state, False
    if a == "DROP":
        if hand and not cells[ag]:
            if any(s[0] == "NO_DROP_HAZARD" for s in spec["safety"]) and inst["hazards"][ag]:
                return state, True
            c = list(cells)
            c[ag] = hand
            return (tuple(c), ag, 0), False
        return state, False
    return state, False


def goal(spec, inst, state):
    return state[2] == 0 and all(holds(a, state[0], inst["binding"]) for a in spec["atoms"])


def feats(spec, inst, state):
    cells, ag, hand = state
    f = {f"here_{k}": cells[ag] == k for k in range(5)}
    f.update({f"hand_{k}": hand == k for k in range(5)})
    for k in range(1, 5):
        f[f"lex_{k}"] = any(cells[p] == k for p in range(ag))
        f[f"rex_{k}"] = any(cells[p] == k for p in range(ag + 1, len(cells)))
    f["hazhere"] = bool(inst["hazards"][ag])
    f["goal"] = all(holds(a, cells, inst["binding"]) for a in spec["atoms"])
    return f


def optimal_examples(spec, inst, max_states=200_000):
    """(features, set of optimal actions) for every state on some optimal path; None if unsolved."""
    start = (tuple(inst["cells"]), inst["agent"], 0)
    par = {start: []}
    order = [start]
    q = deque([start])
    goals = []
    while q:
        s = q.popleft()
        if goal(spec, inst, s):
            goals.append(s)
            continue
        for a in ACTS[:4]:
            s2, bad = lstep(spec, inst, s, a)
            if bad or s2 == s:
                continue
            if s2 not in par:
                par[s2] = []
                order.append(s2)
                q.append(s2)
                if len(par) > max_states:
                    return None
            par[s2].append((s, a))
    if not goals:
        return None
    dist = {g: 0 for g in goals}
    q = deque(goals)
    while q:
        s = q.popleft()
        for p, a in par[s]:
            if p not in dist:
                dist[p] = dist[s] + 1
                q.append(p)
    ex = []
    for s, d in dist.items():
        if d == 0:
            ex.append((feats(spec, inst, s), {"STOP"}))
            continue
        best = {a for a in ACTS[:4] if dist.get(lstep(spec, inst, s, a)[0], 10 ** 9) == d - 1}
        ex.append((feats(spec, inst, s), best))
    return ex


def induce(examples, names, deadline):
    lits = [(n, v) for n in names for v in (True, False)]
    conds = [()] + [(l,) for l in lits] + [c for c in itertools.combinations(lits, 2) if c[0][0] != c[1][0]]
    rules, rest = [], list(examples)
    while rest:
        if time.perf_counter() > deadline:
            return None
        best, best_cov = None, 0
        for c in conds:
            cov = [e for e in rest if all(e[0][n] == v for n, v in c)]
            if not cov:
                continue
            for a in ACTS:
                if all(a in e[1] for e in cov) and len(cov) > best_cov:
                    best, best_cov = (c, a), len(cov)
        if best is None:
            return None
        rules.append(best)
        rest = [e for e in rest if not all(e[0][n] == v for n, v in best[0])]
    return rules


def run_policy(rules, spec, inst):
    state = (tuple(inst["cells"]), inst["agent"], 0)
    N, K = len(state[0]), sum(1 for x in state[0] if x)
    limit = step_limit(len(spec["atoms"]), N, K)
    for t in range(limit):
        f = feats(spec, inst, state)
        a = next((act for c, act in rules if all(f[n] == v for n, v in c)), None)
        if a == "STOP":
            return "SUCCESS" if goal(spec, inst, state) else "FALSE_STOP"
        if a is not None:
            state, bad = lstep(spec, inst, state, a)
            if bad:
                return "UNSAFE"
    return "TIMEOUT"


def construct(spec, train, budget_s=600.0, n_seed=200, seed=0):
    t0 = time.perf_counter()
    deadline = t0 + budget_s
    rng = random.Random(seed)
    pool = [i for i in train if i["N"] <= 6]
    seed_insts = rng.sample(pool, min(n_seed, len(pool)))
    examples, solved = [], 0
    for inst in seed_insts:
        if time.perf_counter() > deadline:
            return {"status": "RESOURCE_LIMIT", "rules": None, "time_s": time.perf_counter() - t0}
        ex = optimal_examples(spec, inst)
        if ex:
            examples += ex
            solved += 1
    names = sorted(examples[0][0]) if examples else []
    rounds = 0
    while True:
        rounds += 1
        rules = induce(examples, names, deadline)
        if rules is None:
            return {"status": "RESOURCE_LIMIT" if time.perf_counter() > deadline else "NO_CONSISTENT_LIST",
                    "rules": None, "rounds": rounds, "examples": len(examples), "time_s": time.perf_counter() - t0}
        fail = None
        for inst in train:
            if time.perf_counter() > deadline:
                return {"status": "RESOURCE_LIMIT", "rules": None, "rounds": rounds, "examples": len(examples),
                        "time_s": time.perf_counter() - t0}
            if run_policy(rules, spec, inst) != "SUCCESS":
                fail = inst
                break
        if fail is None:
            return {"status": "CONSTRUCTED", "rules": rules, "rounds": rounds, "examples": len(examples),
                    "time_s": time.perf_counter() - t0}
        ex = optimal_examples(spec, fail)
        if not ex:
            return {"status": "RESOURCE_LIMIT", "rules": None, "rounds": rounds, "time_s": time.perf_counter() - t0}
        examples += ex
