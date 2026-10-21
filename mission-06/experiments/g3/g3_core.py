"""Gate 3 (EXPERIMENT_PRE_REGISTRATION.md section G3-M2): the G2 agent extended with what B discovered. CONSTRUCTOR SIDE.

Options of Agent3:
  law        use L_co: when `go to r` gives no arrival, treat it as "already at r's place" (co-location) and read r's
             state with `examine r`; a failed examine is a real violation
  monitor    "literal" (G2A-1: any unexpected feedback -> abstain), "post" (only each achiever's postcondition is
             checked, from the belief), "none" (B1)
  prior      P_loc: {object type: {receptacle type: count}} from B's exploration; fetch searches receptacle types in
             descending count (ties: order of the first observation)
The G2 module alf_core.py is left as it ran; here `place` records an object as placed only when the feedback confirms it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "g2"))
import alf_core as C  # noqa: E402

Abstain = C.Abstain


class Agent3(C.Agent):
    def __init__(self, act, first_obs, budget, law=False, monitor="literal", prior=None):
        super().__init__(act, first_obs, budget, monitors=(monitor == "literal"))
        self.law, self.monitor, self.prior = law, monitor, prior or {}
        self.colocated_hits = 0

    def act(self, cmd, expect, check=True):
        if self.steps >= self.budget:
            raise Abstain("budget exhausted")
        self.steps += 1
        obs = self._act(cmd)
        self.hist.append((cmd, obs))
        import re
        m = re.search(r"You (clean|heat|cool) the (.*?) using", obs)
        if m:
            self.flags.setdefault(m.group(2), set()).add({"clean": "clean", "heat": "hot", "cool": "cool"}[m.group(1)])
        if "You turn on the" in obs:
            self.lamp_on_at = self.b.location
        if expect not in obs:
            self.violations.append(cmd.split(" ")[0])
            if check and self.monitor == "literal":
                raise Abstain(f"monitor: '{cmd.split(' ')[0]}' did not give '{expect}'")
        return obs

    def goto(self, r, open_closed=True):
        if self.b.location != r:
            obs = self.act(f"go to {r}", f"You arrive at {r}", check=not self.law)
            if f"You arrive at {r}" not in obs and self.law:
                ex = self.act(f"examine {r}", r, check=True)          # L_co: the agent is already at r's place
                if r in ex and "Nothing happens" not in ex:
                    self.colocated_hits += 1
                    self.hist.append(("go to " + r, f"You arrive at {r}. " + ex))   # belief: now at r
                elif self.monitor == "literal":
                    raise Abstain("monitor: co-location law contradicted")
        if open_closed and self.b.state.get(r) == "closed":
            self.act(f"open {r}", f"You open the {r}")

    def receptacles(self):
        base = super().receptacles()
        T = getattr(self, "_search_type", None)
        if not T or T not in self.prior:
            return base
        score = self.prior[T]
        return sorted(base, key=lambda r: (-score.get(r.split(" ")[0], 0), base.index(r)))

    def fetch(self, T, exclude=()):
        self._search_type = T
        try:
            return super().fetch(T, exclude)
        finally:
            self._search_type = None

    def find_lamp_use(self, lamp_type):
        self._search_type = lamp_type
        for r in self.receptacles():
            self.goto(r, open_closed=False)           # as in G2: the lamp search does not open receptacles
            lamps = [o for o in sorted(self.b.contents.get(r, ())) if o.split(" ")[0] == lamp_type]
            if lamps:
                self.act(f"use {lamps[0]}", "You turn on")
                return
        raise Abstain("lamp not found")

    def place(self, o, R):
        r = self.first_of_type(R)
        self.goto(r)
        obs = self.act(f"move {o} to {r}", "You move")
        if "You move" in obs:
            self.placed.add(o)


def run_priority3(agent, order, max_rounds=8):
    for _ in range(max_rounds):
        first = next((a for a in order if not C.holds(agent, a)), None)
        if first is None:
            return "claims done"
        C.achieve(agent, first)
        if agent.monitor == "post" and not C.holds(agent, first):
            raise Abstain(f"postcondition of {first[0]} not met")
    raise Abstain("no progress across rounds")
