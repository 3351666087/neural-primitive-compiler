"""Gate 4 additions (EXPERIMENT_PRE_REGISTRATION.md section G4), developed on development games only. CONSTRUCTOR SIDE.

Agent4 = Agent3 (g3_core.py) + recovery: when a manipulation command does not give its expected feedback, re-issue it up
to `recover` times (each costs a step) before the monitor decides. Movement is not retried (a `go to` without arrival is
handled by L_co). With recover=0 Agent4 is Agent3.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "g3"))
import g3_core as G3  # noqa: E402

MANIP = ("take", "move", "put", "open", "close", "clean", "heat", "cool", "use")


class Agent4(G3.Agent3):
    def __init__(self, act, first_obs, budget, law=False, monitor="literal", prior=None, recover=0):
        super().__init__(act, first_obs, budget, law=law, monitor=monitor, prior=prior)
        self.recover, self.retries = recover, 0

    def act(self, cmd, expect, check=True):
        if self.recover and cmd.split(" ")[0] in MANIP:
            for _ in range(self.recover):
                if self.steps >= self.budget:
                    break
                obs = self._raw(cmd)
                if expect in obs:
                    return obs
                self.retries += 1
            return super().act(cmd, expect, check)
        return super().act(cmd, expect, check)

    def _raw(self, cmd):
        """One attempt without the monitor: the step and the observation enter the history as usual."""
        self.steps += 1
        obs = self._act(cmd)
        self.hist.append((cmd, obs))
        import re
        m = re.search(r"You (clean|heat|cool) the (.*?) using", obs)
        if m:
            self.flags.setdefault(m.group(2), set()).add({"clean": "clean", "heat": "hot", "cool": "cool"}[m.group(1)])
        if "You turn on the" in obs:
            self.lamp_on_at = self.b.location
        return obs
