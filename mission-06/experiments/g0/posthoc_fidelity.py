"""POST-HOC diagnostic of G0-M1 (written after the locked run scored FALSIFIED; does not change that verdict).

The official comparison (fidelity.py) required identical full traces. In looping episodes the environment stops at its
step limit (TIMEOUT) while the model's trace is cut at 200 macro steps, so full traces differ in length even when the
behaviour is the same. This diagnostic re-runs only the instances flagged by fidelity.json and classifies each flagged
episode:
  PREFIX_AGREE  the environment trace equals the model trace's prefix of the same length, the environment did not
                succeed and the model did not reach the goal (both loop)
  REAL          anything else (a cell configuration differs, or exactly one side succeeds)

  python -I posthoc_fidelity.py        # writes posthoc_fidelity.json
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fidelity as F  # noqa: E402


def main():
    fd = json.loads((HERE / "fidelity.json").read_text())
    flagged = sorted({k for g in fd["total"].values() for k in g["instances_disagreeing"]})
    atom_of = {k: a for v in F.D["inst"].values() for k, a in v}
    out = {}
    for k in flagged:
        atom = atom_of[k]
        spec = F.BY[k.split("|")[0]]
        res = {}
        for var, safety, fixed in (("fixed", [["NO_DROP_HAZARD"], ["NO_PICK", 4]], (4,)), ("movable", [["NO_DROP_HAZARD"]], ())):
            goal = {"atoms": [F.concrete(atom)], "safety": safety, "cue": [], "name": f"M1 {k} {var}"}
            plan = [(goal["atoms"][0], spec)]
            for N, insts in ((5, F.INS.enumerate_all(goal, 5, 3)),
                             (9, [F.INS.random_instance(goal, 9, 7, random.Random(f"M1|{k}|{var}")) for _ in range(100)])):
                traces, outcomes = F.env_traces(goal, F.emit_dsl(plan, goal, N), insts)
                cls = {"AGREE": 0, "PREFIX_AGREE": 0, "REAL": 0}
                real = []
                for inst, et, o in zip(insts, traces, outcomes):
                    mt, ok = F.model_trace(spec, atom, inst["cells"], inst["hazards"], fixed, limit=10_000)
                    if et == mt and (o == "SUCCESS") == ok:
                        cls["AGREE"] += 1
                    elif o != "SUCCESS" and not ok and len(et) <= len(mt) and mt[:len(et)] == et:
                        cls["PREFIX_AGREE"] += 1
                    else:
                        cls["REAL"] += 1
                        if len(real) < 3:
                            real.append({"cells": list(inst["cells"]), "haz": list(inst["hazards"]), "env_outcome": o,
                                         "env_len": len(et), "model_len": len(mt), "model_success": ok})
                res[f"{var}_N{N}"] = {**cls, "outcomes": {x: outcomes.count(x) for x in set(outcomes)}, "real_examples": real}
        out[k] = res
    tot = {c: sum(r[g][c] for r in out.values() for g in r) for c in ("AGREE", "PREFIX_AGREE", "REAL")}
    (HERE / "posthoc_fidelity.json").write_text(json.dumps({"label": "POST-HOC diagnostic of G0-M1", "flagged": flagged,
                                                            "total": tot, "results": out}, indent=1))
    print(flagged)
    print(tot)


if __name__ == "__main__":
    main()
