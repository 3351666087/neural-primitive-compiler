"""Gate 1 feasibility of ECO with the development family alpha (JUDGE SIDE; no agent is built here).

  1. determinism: same seed and actions give the same observation stream
  2. speed: random policy, environment steps per second
  3. base rates under a uniformly random policy (10 seeds x 20,000 steps): mechanism events and how often each
     hidden condition holds; this measures how rare the stepping stones are without deliberate control
  4. witness pairs (restricted inexpressibility for S0) for LATENT:stone.charge, LATENT:lamp.armed and PLACE:spring,
     constructed and verified by simulation on every seed
  5. positive control: a judge-side oracle script (reads latent state; NOT an agent) shows that each affordance can be
     produced within a small step budget: charge a stone next to a tree -> fruit; arm a lamp -> springs revealed

  python3 -I g1_feasibility_eco.py         # writes g1_feasibility_eco.json
"""

from __future__ import annotations

import json
import random
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import judge_eco as JE  # noqa: E402
from eco_env import ACTIONS, EcoWorld, load_family  # noqa: E402

FAM = load_family(HERE / "family_alpha.json")
SEEDS = list(range(100, 110))


def determinism():
    rng = random.Random(1)
    acts = [rng.randrange(len(ACTIONS)) for _ in range(3000)]
    a, b = EcoWorld(FAM, 5), EcoWorld(FAM, 5)
    return all(JE.obs_key(a.step(x)) == JE.obs_key(b.step(x)) for x in acts)


def base_rates(steps=20000):
    out = []
    t0 = time.perf_counter()
    total = 0
    for seed in SEEDS:
        w = EcoWorld(FAM, seed)
        rng = random.Random(seed + 1)
        hold = Counter()
        for _ in range(steps):
            w.step(rng.randrange(len(ACTIONS)))
            total += 1
            hold["charge>=3"] += JE.condition(w, ("LATENT", "stone.charge"), {3})
            hold["charge>=2"] += JE.condition(w, ("LATENT", "stone.charge"), {2, 3})
            hold["armed"] += JE.condition(w, ("LATENT", "lamp.armed"), {1})
        ev = Counter(e[1] for e in w.events)
        out.append({"seed": seed, "events": dict(ev), "frac_steps": {k: v / steps for k, v in hold.items()}, "lives": w.lives})
    sps = total / (time.perf_counter() - t0)
    return out, sps


def witnesses():
    res = []
    for seed in SEEDS:
        w = EcoWorld(FAM, seed)
        r = {"seed": seed}
        # LATENT:stone.charge, value 3
        r["stone.charge"] = False
        for oid, h1, h2 in JE.witness_latent(w, "stone", "charge", 1):
            v = JE.verify_witness(w, h1, h2, ("LATENT", "stone.charge"), {1, 2, 3})
            if v["witness"]:
                r["stone.charge"] = True
                break
        # LATENT:lamp.armed: charge a stone that is adjacent to a lamp, then (poke lamp, wait) vs (wait, wait)
        r["lamp.armed"] = False
        for lamp in [o for o in w.objs if o.kind == "lamp"]:
            stones = [o for o in w.objs if o.kind == "stone" and w.cheb(o, lamp) <= 1]
            for st in stones:
                p1 = JE.face_toward(w, st)
                if p1 is None:
                    continue
                w1, _ = JE.run(w, p1 + ["POKE"] * 2)
                p2 = JE.face_toward(w1, lamp)
                if p2 is None:
                    continue
                pre = p1 + ["POKE"] * 2 + p2
                v = JE.verify_witness(w, pre + ["POKE", "WAIT"], pre + ["WAIT", "WAIT"], ("LATENT", "lamp.armed"), {1})
                if v["witness"]:
                    r["lamp.armed"] = True
                    break
            if r["lamp.armed"]:
                break
        bi = JE.bounded_inexpressible(JE.place_rows(w, "spring"), k=3)
        r["spring.place"] = bi["expressible_within_bound"] is False
        r["spring.place_detail"] = bi
        res.append(r)
    return res


def oracle_control():
    """Judge-side script with latent access: steps until (a) fruit from a charged stone, (b) springs revealed."""
    out = []
    for seed in SEEDS:
        w = EcoWorld(FAM, seed)
        rec = {"seed": seed}
        trees = [o for o in w.objs if o.kind == "tree"]
        stone = next((s for s in w.objs if s.kind == "stone" and any(w.cheb(s, t) <= 2 for t in trees)), None)
        if stone is not None:
            path = JE.face_toward(w, stone)
            if path is not None:
                for a in path + ["POKE"] * 3 + ["WAIT"] * 6:
                    w.step(JE.A[a])
                rec["charged_fruit_steps"] = w.t if any(e[1] == "charged_fruit" for e in w.events) else None
        w = EcoWorld(FAM, seed)
        done = False
        for lamp in [o for o in w.objs if o.kind == "lamp"]:
            for st in [o for o in w.objs if o.kind == "stone" and w.cheb(o, lamp) <= 1]:
                p1 = JE.face_toward(w, st)
                if p1 is None:
                    continue
                for a in p1 + ["POKE"] * 2:
                    w.step(JE.A[a])
                p2 = JE.face_toward(w, lamp)
                if p2 is None:
                    continue
                for a in p2 + ["POKE", "POKE"]:
                    w.step(JE.A[a])
                if any(e[1] == "spring_reveal" for e in w.events):
                    rec["spring_reveal_steps"] = w.t
                    done = True
                    break
            if done:
                break
        rec.setdefault("spring_reveal_steps", None)
        out.append(rec)
    return out


def main():
    det = determinism()
    rates, sps = base_rates()
    wit = witnesses()
    orc = oracle_control()
    agg = Counter()
    for r in rates:
        agg.update(r["events"])
    out = {"family": FAM["name"], "seeds": SEEDS, "deterministic": det, "random_policy_steps_per_s": round(sps),
           "base_rates": {"events_total_over_200k_steps": dict(agg),
                          "mean_frac_steps": {k: sum(r["frac_steps"][k] for r in rates) / len(rates) for k in rates[0]["frac_steps"]},
                          "lives_total": sum(r["lives"] for r in rates), "per_seed": rates},
           "witness_pairs": {"per_seed": wit, "count": {k: sum(r[k] for r in wit) for k in ("stone.charge", "lamp.armed", "spring.place")}},
           "oracle_control": orc}
    (HERE / "g1_feasibility_eco.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k not in ("base_rates", "witness_pairs", "oracle_control")}, indent=1))
    print("events over 200k random steps:", dict(agg))
    print("mean fraction of steps:", out["base_rates"]["mean_frac_steps"], "lives:", out["base_rates"]["lives_total"])
    print("witness pairs (of 10 seeds):", out["witness_pairs"]["count"])
    print("oracle control:", orc)


if __name__ == "__main__":
    main()
