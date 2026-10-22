"""Run one (arm, family, seed) in ECO with the judge and the agent in separate processes (PROTOCOL.md section 2).
JUDGE SIDE: this process holds the world; the spawned agent process receives observations only and returns actions.

Per step the judge records, for every goal class of the frozen taxonomy (judge_eco.classes, LATENT classes expanded
to threshold sets 'value >= v'), the intervals during which the class condition holds.

Options for the agent process (interventions, PROTOCOL.md section 6.6):
  learn_off            no structure acquisition (the S0 twin)
  delete               {"t": t, "form": "M1", "K": kind_id}: delete matching structures at t and block re-adoption
  transplant           list of structure descriptions installed at t = 0
  gift                 list of [t, formula]: goals pushed from outside at time t (reason "external")
  arm_kwargs           extra constructor arguments for the arm
  transplant_t         install the `transplant` structures at this step instead of t = 0 (amendment A2, G-B1M)
  fake                 {"t": t, "desc": structure description}: a fake structure added at t (amendment A2)
  no_propose           the agent's own top-level goal proposal is switched off (amendment A2, G-CAND)

  python3 -I run_eco.py ARM FAMILY.json SEED STEPS OUT_DIR
"""

from __future__ import annotations

import gzip
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
AGENTS = HERE.parent / "agents"
sys.path.insert(0, str(HERE))
import judge_eco as JE  # noqa: E402
from eco_env import EcoWorld, load_family  # noqa: E402


def expanded_classes(fam):
    out = []
    for typ, name in JE.classes(fam):
        if typ == "LATENT":
            kind, var = name.split(".")
            dom = fam["kinds"][kind]["latent"][var]["domain"]
            for v in sorted(x for x in dom if isinstance(x, int) and x > 0):
                out.append((typ, name, tuple(x for x in dom if isinstance(x, int) and x >= v)))
        elif typ in ("PLACE", "OBS"):
            out.append((typ, name, None))
    return out


def agent_proc(conn, arm, seed, opts):
    sys.path.insert(0, str(AGENTS))
    import agent as AG
    from structures import FORMS
    import pickle
    import fakes
    arms = dict(AG.ARMS)
    arms.update(fakes.ARMS)
    try:
        import cand
        arms.update(cand.ARMS)
    except ImportError:
        pass
    if opts.get("agent_pickle"):
        ag = pickle.loads(opts["agent_pickle"])
        if opts.get("reseed") is not None:
            import random as _r
            ag.rng = _r.Random(opts["reseed"])
    else:
        ag = arms[arm](seed, **opts.get("arm_kwargs", {}))
    if opts.get("learn_off"):
        ag.learn_every = None
    def install(descs, trigger, t_now):
        for d in descs:
            params = dict(d["params"])
            if params.get("q_struct") is not None:             # keep references between transplanted structures
                params["q_struct"] = 10 ** 6 + params["q_struct"]
            s = FORMS[d["form"]](10 ** 6 + d["struct_id"], params, d.get("stats", {}), [], t_now)
            ag.add_structure(s, trigger=trigger)
    if opts.get("no_propose"):
        ag.propose = lambda: None
    t_tr = opts.get("transplant_t")
    if t_tr is None:
        install(opts.get("transplant", []), "transplant", 0)
    fake = opts.get("fake")
    gifts = sorted(opts.get("gift", []))
    dele = opts.get("delete")
    while True:
        kind, payload = conn.recv()
        if kind == "obs":
            t = ag.mem.t + 1
            if t_tr is not None and t == t_tr:
                ag.obs = payload
                install(opts.get("transplant", []), "transplant", t)
            if fake and t == fake["t"]:
                ag.obs = payload
                install([fake["desc"]], "fake", t)
            if dele and t == dele["t"]:
                for sid in [sid for sid, s in ag.structs.items() if s.form == dele["form"] and s.params.get("K") == dele["K"]]:
                    ag.logs.deletions.append({"t": t, "struct_id": sid, "form": dele["form"], "K": dele["K"]})
                    del ag.structs[sid]
                ag.learner.blocked.add((dele["form"], dele["K"]))
                ag.goal_stack.clear()
            while gifts and gifts[0][0] <= t:
                _, formula = gifts.pop(0)
                ag.obs = payload
                ag.log_goal(formula, reason="external", priority=1.0, provenance=["external"] * len(formula))
            conn.send(ag.act(payload))
        elif kind == "pickle":
            conn.send(pickle.dumps(ag))
        elif kind == "end":
            conn.send({**ag.logs.dump(), "export": ag.export(), "arm": arm})
            break


def run(arm, family_path, seed, steps, out_dir, opts=None, tag="", world=None, checkpoint=None):
    """world: an EcoWorld to continue (default: a fresh one from the seed). checkpoint: a step t at which the world
    and the agent are pickled into OUT_DIR/<stem>.ckpt_<t>.pkl (judge side; used for the history-swap test)."""
    import pickle
    opts = opts or {}
    fam = load_family(family_path)
    w = world if world is not None else EcoWorld(fam, seed)
    classes = expanded_classes(fam)
    ctx = mp.get_context("spawn")
    a, b = ctx.Pipe()
    p = ctx.Process(target=agent_proc, args=(b, arm, seed, opts))
    p.start()
    t0 = time.perf_counter()
    obs = opts.pop("start_obs", None) or w.observe()
    state = [False] * len(classes)
    intervals = {i: [] for i in range(len(classes))}
    stem = f"{arm}_{fam['name']}_{seed}{tag}"
    for t in range(steps):
        if checkpoint is not None and t == checkpoint:
            a.send(("pickle", None))
            agent_bytes = a.recv()
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            (Path(out_dir) / f"{stem}.ckpt_{t}.pkl").write_bytes(pickle.dumps({"world": w, "agent": agent_bytes, "obs": obs}))
        a.send(("obs", obs))
        while not a.poll(1.0):
            if not p.is_alive():
                raise RuntimeError(f"agent process died at step {t} ({arm}, seed {seed})")
        act = a.recv()
        obs = w.step(act)
        for i, (typ, name, vals) in enumerate(classes):
            c = JE.condition(w, (typ, name), set(vals) if vals else None)
            if c and not state[i]:
                intervals[i].append([w.t, None])
            elif not c and state[i]:
                intervals[i][-1][1] = w.t
            state[i] = c
    a.send(("end", None))
    agent_out = a.recv()
    p.join(timeout=60)
    secs = time.perf_counter() - t0
    judge_out = {"arm": arm, "family": fam["name"], "seed": seed, "steps": steps, "opts": {k: v for k, v in opts.items() if k not in ("transplant", "agent_pickle")},
                 "classes": [list(c) for c in classes], "intervals": {str(i): v for i, v in intervals.items()},
                 "events": w.events, "lives": w.lives, "secs": round(secs, 1), "kind_id": w.kind_id}
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with gzip.open(out / f"{stem}.judge.json.gz", "wt") as f:
        json.dump(judge_out, f)
    with gzip.open(out / f"{stem}.agent.json.gz", "wt") as f:
        json.dump(agent_out, f)
    return {"stem": stem, "secs": round(secs, 1), "lives": w.lives, "goals": len(agent_out["goals"]),
            "structures": len(agent_out["structures"])}


def run_job(spec):
    """spec: {"arm", "family", "seed", "steps", "out", "opts"?, "tag"?, "checkpoint"?} (one JSON object)."""
    return run(spec["arm"], spec["family"], spec["seed"], spec["steps"], spec["out"], spec.get("opts"), spec.get("tag", ""),
               checkpoint=spec.get("checkpoint"))


if __name__ == "__main__":
    if sys.argv[1] == "--job":
        res = run_job(json.loads(sys.argv[2]))
        print(json.dumps(res))
    else:
        arm, fam, seed, steps, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
        print(json.dumps(run(arm, fam, seed, steps, out)))
