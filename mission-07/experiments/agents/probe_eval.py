"""AGENT SIDE evaluator for the judge's grounding test (PROTOCOL.md sections 2 and 6.1).
Rebuilds an agent's exported structures from their parameters, replays judge-supplied probe histories (observations
and actions only) through a fresh Memory and the structure trackers, and returns every predicate's value at the end of
each probe. No learning and no logging happen here."""

from __future__ import annotations

import sys

from structures import FORMS
from substrate import Memory


def rebuild(descs):
    structs = {}
    for d in descs:
        s = FORMS[d["form"]](d["struct_id"], d["params"], d["stats"], [], 0)
        structs[s.sid] = s
    return structs


def evaluate(descs, probes):
    """descs: exported structure descriptions; probes: list of {"obs": [...], "actions": [...]} where obs[0] is the
    first observation and obs[i] follows actions[i-1]. Returns a list of {predicate: bool}."""
    out = []
    for pr in probes:
        structs = rebuild(descs)
        mem = Memory()
        idx = 0
        last = "WAIT"
        for i, obs in enumerate(pr["obs"]):
            mem.observe(obs, last)
            new = mem.events[idx:]
            idx = len(mem.events)
            for form in ("M1", "M2", "M3", "M4"):
                for s in structs.values():
                    if s.form == form:
                        s.step(mem, new, structs)
            if i < len(pr["actions"]):
                last = pr["actions"][i]
        vals = {}
        for s in structs.values():
            for p in s.predicates():
                vals[p] = bool(s.value(p, mem, structs))
        out.append(vals)
    return out


def proc(conn):
    descs, probes = conn.recv()
    conn.send(evaluate(descs, probes))
