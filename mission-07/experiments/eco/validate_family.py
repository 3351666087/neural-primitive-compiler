"""Validate an ECO mechanism family against the held-out requirements of BETA_AUTHOR_BRIEF.md (JUDGE SIDE).
Prints only pass/fail per requirement and counts; never prints rules.

  python3 -I validate_family.py FAMILY.json DEMOS.json

DEMOS.json: {"stage1_events": [names], "stage2_events": [names],
             "demos": [{"seed": s, "actions": ["N", "POKE", ...], "expect_event": name}, ...]}
Requirements:
  R1 the family is interpretable for 10 seeds x 2,000 random steps without error
  R2 needs: a uniformly random policy lives on average >= 300 steps per life (10 seeds x 20,000 steps)
  R3 every log event named in stage1_events / stage2_events is produced by at least one demo (<= 60 actions each)
  R4 stage-1 events occur >= 50 times under the random policy (10 x 20,000 steps); stage-2 events occur <= 50 times
  R5 at least one kind with visibility "revealed", at least one latent variable, at least one phase or
     nonstationarity entry, both needs have a consumable kind
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from eco_env import ACTIONS, EcoWorld  # noqa: E402


def main():
    fam = json.loads(Path(sys.argv[1]).read_text())
    demos = json.loads(Path(sys.argv[2]).read_text())
    res = {}
    try:
        for seed in range(10):
            w = EcoWorld(fam, 1000 + seed)
            rng = random.Random(seed)
            for _ in range(2000):
                w.step(rng.randrange(len(ACTIONS)))
        res["R1 interpretable"] = True
    except Exception as e:                                   # report the type only
        res["R1 interpretable"] = f"error {type(e).__name__}"
    ev = Counter()
    lives = steps = 0
    for seed in range(10):
        w = EcoWorld(fam, 2000 + seed)
        rng = random.Random(seed + 7)
        for _ in range(20000):
            w.step(rng.randrange(len(ACTIONS)))
        steps += 20000
        lives += w.lives + 1
        ev.update(e[1] for e in w.events)
    res["R2 mean steps per life (>= 300)"] = round(steps / lives)
    ok3 = {}
    for d in demos["demos"]:
        w = EcoWorld(fam, d["seed"])
        for a in d["actions"][:60]:
            w.step(ACTIONS.index(a))
        ok3[d["expect_event"]] = ok3.get(d["expect_event"], False) or any(e[1] == d["expect_event"] for e in w.events)
    needed = set(demos["stage1_events"]) | set(demos["stage2_events"])
    res["R3 demos cover every stage event"] = all(ok3.get(n, False) for n in needed)
    s1 = sum(ev[n] for n in demos["stage1_events"])
    s2 = sum(ev[n] for n in demos["stage2_events"])
    res["R4 stage-1 random count (>= 50)"] = s1
    res["R4 stage-2 random count (<= 50)"] = s2
    kinds = fam["kinds"].values()
    res["R5 structure"] = (any(k.get("visibility") == "revealed" for k in kinds)
                           and any(k.get("latent") for k in kinds)
                           and bool(fam.get("phase") or fam.get("nonstationarity"))
                           and {k.get("consumable", {}).get("need") for k in kinds} >= {"food", "water"})
    passed = (res["R1 interpretable"] is True and res["R2 mean steps per life (>= 300)"] >= 300 and res["R3 demos cover every stage event"]
              and s1 >= 50 and s2 <= 50 and res["R5 structure"])
    res["ALL PASS"] = passed
    res["counts"] = {"kinds": len(fam["kinds"]), "rules": len(fam["rules"]),
                     "latent_vars": sum(len(k.get("latent", {})) for k in kinds)}
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
