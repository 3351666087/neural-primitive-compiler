"""Fruit-fly-derived variants of the frozen candidate (PROTOCOL.md section 4.4; HYPOTHESES.md section 3). AGENT SIDE.
Each variant changes one organisational element of the candidate; each has a non-biological control of the same
capacity. Biological similarity scores nothing by itself; only changed behaviour, goal formation or data efficiency
counts.

F-STATE (need-gated memory expression; Krashes et al. 2009)
  F-STATE      the mastery-goal weights of a structure's predicates are multiplied by (1 + 2u) when the
               structure's effect kind restores a need that is currently low (u = (60 - need) / 60 for needs below
               60): the same learned association is expressed more when the need it serves is low.
  F-STATE-off  control: no need term in goal choice at all (needs act only through the shared survival override
               below 35), i.e. no state input to the choice of non-survival goals.
  The candidate itself is the "need as an additive input" condition (a need goal enters the pool with weight 2u).
  Metric: state intervention at step 20,000 (food set to 40 vs 95, everything else equal), total-variation distance
  between the next 2,000 steps' goal distributions (g4_state.py).

F-MB (parallel memory compartments with different learning rates; Aso & Rubin 2016)
  The candidate has a fast compartment (structures whose predictions fail are refitted on the last 3,000 steps) and
  a slow one (other comparisons on an evidence window up to 10,000 steps).
  F-MB-slow    single slow rate: every refit and comparison uses the learner's 10,000-step window.
  F-MB-fast    single fast rate: the learner, every refit and every comparison use only the last 3,000 steps.
  Metric: seeds with a grounded s1 and time to the first grounded s1; C2 / C3 L2 events; L3.

F-CX (allocentric goal-vector memory; Seelig & Jayaraman 2015)
  The candidate's place structures (M3) store remembered cells in the life's own coordinate frame.
  F-CX-off     no place structures (M3 removed from the learner).
  Metric: place-class goals (PLACE:*), their achievement, and lives per run.
"""

from __future__ import annotations

from cand import NEED_TERM, RECENT, Candidate


class FState(Candidate):
    name = "F-STATE"

    def gate(self, st):
        if st is None or not self.use_needs:
            return 1.0
        k2 = st.params.get("K2")
        g = 1.0
        for i in (0, 1):
            n = self.obs["needs"][i]
            if n < NEED_TERM and self.aff.get(k2, {}).get(i, 0) > 0:
                g = max(g, 1.0 + 2.0 * (NEED_TERM - n) / NEED_TERM)
        return g

    def mastery_weights(self):
        return [(w * self.gate(self.predicate_owner(p)), p) for w, p in super().mastery_weights()]


class FStateOff(Candidate):
    name = "F-STATE-off"

    def propose(self):
        saved = self.use_needs
        self.use_needs = False                                 # removes the need term from the pool only
        try:
            return super().propose()
        finally:
            self.use_needs = saved


class FMBSlow(Candidate):
    name = "F-MB-slow"

    def acquire(self):
        if not self.learn_every:
            return
        self.last_fit = self.mem.t
        self.fit_due = False
        for s in self.learner.fit(self.mem, self.structs, self.mem.t):
            self.add_structure(s, trigger="fit")
        for sid in [sid for sid, s in self.structs.items() if s.form in ("M1", "M2")]:
            self.try_revision(sid, window=self.learner.window)
        self.revise_due.clear()
        self.update_discriminators()


class FMBFast(Candidate):
    name = "F-MB-fast"
    learner_window = RECENT

    def evidence_window(self, st, need=40):
        return RECENT


class FCXOff(Candidate):
    name = "F-CX-off"

    def __init__(self, seed, learner_kwargs=None):
        kw = dict(learner_kwargs or {})
        kw["allowed"] = ("M1", "M2", "M4")
        super().__init__(seed, kw)


ARMS = {c.name: c for c in (FState, FStateOff, FMBSlow, FMBFast, FCXOff)}
