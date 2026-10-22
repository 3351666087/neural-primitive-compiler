"""JUDGE SIDE grounding test (PROTOCOL.md section 6.1). Generates probe histories in fresh worlds of a family (probe seed
range 9000+), records the judge truth of every expanded goal class at the end of each probe, sends observations and
actions (nothing else) to the agent-side evaluator, and maps each learned predicate to the class it is grounded to
(precision and recall both >= 0.9, and at least 10 probes on which the class holds), if any.

Probe scripts (generic: they use only the family's kind list and which kinds have latent variables, judge side):
  A  approach an object of a kind with latent variables; a random string of POKE / WAIT (1-12) then 0-40 WAITs
  B  approach a neighbour Y of such an object X (within 2), POKE Y 0-3 times, approach X, POKE X 0-2 times, 0-30 WAITs
  C  a random walk of 20-80 steps with 15 % POKE
"""

from __future__ import annotations

import multiprocessing as mp
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AGENTS = HERE.parent / "agents"
sys.path.insert(0, str(HERE))
import judge_eco as JE  # noqa: E402
from eco_env import ACTIONS, EcoWorld  # noqa: E402
from run_eco import expanded_classes  # noqa: E402


def make_probes(fam, n=480, seed0=9000, min_cover=20, cap=2400):
    """At least n probes; continue until every LATENT class holds on >= min_cover probes and fails on >= min_cover
    probes, or `cap` probes."""
    rng = random.Random(seed0)
    latent_kinds = [k for k, s in fam["kinds"].items() if s.get("latent")]
    classes = expanded_classes(fam)
    lat_idx = [ci for ci, c in enumerate(classes) if c[0] == "LATENT"]
    probes = []
    i = 0

    def covered():
        return all(min_cover <= sum(pr["truth"][ci] for pr in probes) <= len(probes) - min_cover for ci in lat_idx)
    while (len(probes) < n or not covered()) and len(probes) < cap and i < cap * 5:
        i += 1
        w = EcoWorld(fam, seed0 + i)
        obs_seq = [w.observe()]
        acts = []

        def do(a):
            acts.append(a)
            obs_seq.append(w.step(JE.A[a]))
        typ = "ABBC"[i % 4]
        X = None
        if typ in "AB" and latent_kinds:
            cands = [o for o in w.objs if o.kind in latent_kinds and not o.carried]
            rng.shuffle(cands)
            if typ == "B" and rng.random() < 0.7:                # prefer objects with a latent-kind neighbour
                cands.sort(key=lambda o: not any(q is not o and q.kind in latent_kinds and w.cheb(q, o) <= 1 for q in w.objs))
            for o in cands:
                if JE.face_toward(w, o) is not None:
                    X = o
                    break
        if typ == "A" and X is not None:
            for a in JE.face_toward(w, X):
                do(a)
            for _ in range(rng.randint(1, 12)):
                do(rng.choice(["POKE", "POKE", "WAIT"]))
            for _ in range(rng.randint(0, 40)):
                do("WAIT")
        elif typ == "B" and X is not None:
            d = 1 if rng.random() < 0.5 else 2
            nbrs = [o for o in w.objs if o is not X and not o.carried and w.cheb(o, X) <= d and fam["kinds"][o.kind].get("solid")]
            lat_n = [o for o in nbrs if o.kind in latent_kinds]
            if lat_n and rng.random() < 0.7:
                nbrs = lat_n
            if nbrs:
                Y = rng.choice(nbrs)
                p = JE.face_toward(w, Y)
                if p is not None:
                    for a in p:
                        do(a)
                    for _ in range(rng.randint(0, 4)):
                        do("POKE")
            p = JE.face_toward(w, X)
            if p is not None:
                for a in p:
                    do(a)
                for _ in range(rng.randint(0, 2)):
                    do("POKE")
            for _ in range(rng.randint(0, 30)):
                do("WAIT")
        else:
            for _ in range(rng.randint(20, 80)):
                do("POKE" if rng.random() < 0.15 else rng.choice("NESW"))
        truth = [bool(JE.condition(w, (c[0], c[1]), set(c[2]) if c[2] else None)) for c in classes]
        probes.append({"obs": obs_seq, "actions": acts, "truth": truth})
    return probes, classes


def evaluate_agent(descs, probes):
    ctx = mp.get_context("spawn")
    a, b = ctx.Pipe()
    sys.path.insert(0, str(AGENTS))
    p = ctx.Process(target=_proc, args=(b,))
    p.start()
    a.send((descs, [{"obs": pr["obs"], "actions": pr["actions"]} for pr in probes]))
    vals = a.recv()
    p.join(timeout=60)
    return vals


def _proc(conn):
    sys.path.insert(0, str(AGENTS))
    import probe_eval
    probe_eval.proc(conn)


def ground(descs, probes, classes, thr=0.9, min_pos=10):
    vals = evaluate_agent(descs, probes)
    preds = sorted({p for v in vals for p in v})
    out = {}
    for p in preds:
        av = [v.get(p, False) for v in vals]
        best = None
        for ci, c in enumerate(classes):
            jv = [pr["truth"][ci] for pr in probes]
            g = JE.grounding(av, jv)
            g["class"] = [c[0], c[1], list(c[2]) if c[2] else None]
            g["positives_judge"] = sum(jv)
            if best is None or (g["precision"] + g["recall"]) > (best["precision"] + best["recall"]):
                best = g
        best["agent_true"] = sum(av)
        best["grounded"] = bool(best["grounded"] and best["positives_judge"] >= min_pos)
        out[p] = best
    return out
