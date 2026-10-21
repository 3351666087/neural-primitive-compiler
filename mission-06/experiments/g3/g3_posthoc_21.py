"""POST-HOC diagnostic (after the Gate 3 results; not part of any locked prediction). Replays G3-LP on evaluation game
21 (the agent is deterministic) with a judge that records, per step, only the command verb, whether the observation
contained an arrival / "Nothing happens.", and whether `won` was already true. No observation text is printed.

  mission-06/env/venv-alf/bin/python -I mission-06/experiments/g3/g3_posthoc_21.py
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "g1"))
sys.path.insert(0, str(HERE.parent / "g2"))
import alf_core as C  # noqa: E402
import belief as BL  # noqa: E402
import g3_core as G3  # noqa: E402
import games as G  # noqa: E402
import alf_judge as J  # noqa: E402

path, ttype = G.evaluation()[21]
g = J.Game(path, max_steps=55)
first, info = g.reset()
state = {"won": bool(info["won"])}
trace = []


def act(cmd):
    if state["won"]:
        obs = "Nothing happens."
        trace.append({"verb": cmd.split(" ")[0], "won_before": True, "masked": True})
        return obs
    obs, _s, _d, inf = g.step(cmd)
    trace.append({"verb": cmd.split(" ")[0], "won_before": False, "arrived": "You arrive at" in obs,
                  "nothing_happens": "Nothing happens" in obs, "won_after": bool(inf["won"])})
    state["won"] = bool(inf["won"])
    return obs


disc = json.loads((HERE / "g3_discovery.json").read_text())
agent = G3.Agent3(act, first, 50, law=True, monitor="literal", prior=disc["P_loc"])
atoms = C.parse_goal(BL.belief_after([(None, first)]).goal)
order, _ = C.construct(atoms)
try:
    out = G3.run_priority3(agent, order)
except C.Abstain as e:
    out = f"abstain: {e}"
res = {"task_type": ttype, "outcome": out.split(":")[0], "outcome_detail": out.split(":", 1)[-1].split("'")[1] if "'" in out else "",
       "trace": trace}
print(json.dumps(res, indent=1))
(HERE / "g3_posthoc_21.json").write_text(json.dumps(res, indent=1))
