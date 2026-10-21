"""Controller IR (CIR): definition and the judge's own step interpreter (J1-sym). JUDGE SIDE.

A CIR program is JSON:
  {"name": str, "D": int,                       # D = network ticks per environment step (network only)
   "nodes": [
     {"id": i, "op": "OR",      "in": [ref, ...]},                     # 1 iff some input is 1
     {"id": i, "op": "AND",     "pos": [ref, ...], "neg": [ref, ...]},  # all pos are 1 and no neg is 1
     {"id": i, "op": "ATLEAST", "k": k, "in": [ref, ...]},             # at least k inputs are 1
     {"id": i, "op": "REG",     "n": n, "letters": [                   # one-hot style register, n bits
         {"when": ref, "load": [ref] * n} | {"when": ref, "zero": true} | {"when": ref, "one": j}]}],
   "outputs": {"LEFT": ref, "RIGHT": ref, "PICK": ref, "DROP": ref, "STOP": ref}}
A ref is an observation channel (col_p_k, haz_p, ag_p, hand_k, cue_v_k), the id of a combinational node defined
earlier in the list, or "R[j]" for bit j of register R (any register, anywhere in the list).

Step semantics at environment step t:
  1. observation channels take their values at t; every register bit takes its contents at t (all 0 at t = 0);
  2. combinational nodes are evaluated in list order;
  3. the outputs give the action (none = NOOP, more than one = failure MULTIPLE_ACTIONS);
  4. every register whose letter `when` is 1 takes the new contents; two active letters on one register is the
     failure REG_CONFLICT; a register with no active letter keeps its contents.
"""

from __future__ import annotations

import re

import numpy as np

from env import ACTIONS, BatchEnv

REGREF = re.compile(r"^(.*)\[(\d+)\]$")


def check_program(prog):
    """Structural checks: unique ids, refs defined before use (registers excepted), known ops."""
    ids, regs = set(), {}
    for nd in prog["nodes"]:
        if nd["id"] in ids:
            raise ValueError(f"duplicate id {nd['id']}")
        ids.add(nd["id"])
        if nd["op"] == "REG":
            regs[nd["id"]] = nd["n"]
        elif nd["op"] not in ("OR", "AND", "ATLEAST"):
            raise ValueError(f"unknown op {nd['op']}")
    return regs


class Interp:
    def __init__(self, prog, B):
        self.prog = prog
        self.regs = check_program(prog)
        self.state = {r: np.zeros((B, n), dtype=bool) for r, n in self.regs.items()}
        self.B = B

    def _get(self, vals, ref):
        if ref in vals:
            return vals[ref]
        m = REGREF.match(ref)
        if m and m.group(1) in self.state:
            return self.state[m.group(1)][:, int(m.group(2))]
        raise KeyError(f"undefined ref {ref}")

    def step(self, obs):
        """obs: channel -> bool (B,). Returns (actions dict, conflict mask)."""
        vals = dict(obs)
        B = self.B
        for nd in self.prog["nodes"]:
            op = nd["op"]
            if op == "OR":
                v = np.zeros(B, dtype=bool)
                for r in nd["in"]:
                    v |= self._get(vals, r)
            elif op == "AND":
                v = np.ones(B, dtype=bool)
                for r in nd["pos"]:
                    v &= self._get(vals, r)
                for r in nd["neg"]:
                    v &= ~self._get(vals, r)
            elif op == "ATLEAST":
                s = np.zeros(B, dtype=np.int64)
                for r in nd["in"]:
                    s += self._get(vals, r)
                v = s >= nd["k"]
            else:
                continue
            vals[nd["id"]] = v
        acts = {a: (self._get(vals, self.prog["outputs"][a]) if a in self.prog["outputs"] else np.zeros(B, bool))
                for a in ACTIONS}
        conflict = np.zeros(B, dtype=bool)
        new = {}
        for nd in self.prog["nodes"]:
            if nd["op"] != "REG":
                continue
            r = nd["id"]
            cur = self.state[r].copy()
            seen = np.zeros(B, dtype=bool)
            for L in nd["letters"]:
                w = self._get(vals, L["when"])
                conflict |= seen & w
                seen |= w
                if "load" in L:
                    val = np.stack([self._get(vals, x) for x in L["load"]], axis=1)
                elif L.get("zero"):
                    val = np.zeros((B, nd["n"]), dtype=bool)
                else:
                    val = np.zeros((B, nd["n"]), dtype=bool)
                    val[:, L["one"]] = True
                cur = np.where(w[:, None], val, cur)
            new[r] = cur
        self.state.update(new)
        return acts, conflict


def run_closed_loop(prog, spec, insts, trace_actions=False):
    """J1-sym: run the CIR controller against the reference environment. Returns outcomes (and per-step actions)."""
    env = BatchEnv(spec, insts)
    it = Interp(prog, env.B)
    log = []
    while not env.done.all():
        acts, conflict = it.step(env.observation())
        env._finish(conflict, "REG_CONFLICT")
        if trace_actions:
            log.append({a: v.copy() for a, v in acts.items()})
        env.act(acts)
    return env.outcome.tolist(), env.steps.tolist(), log


def judge_set(prog, spec, insts):
    """Groups instances by N, runs J1-sym, returns counts per outcome and failing instance indices."""
    byN = {}
    for i, inst in enumerate(insts):
        byN.setdefault(inst["N"], []).append(i)
    outcomes = [None] * len(insts)
    steps = [None] * len(insts)
    for N, idx in byN.items():
        o, s, _ = run_closed_loop(prog, spec, [insts[i] for i in idx])
        for j, i in enumerate(idx):
            outcomes[i], steps[i] = o[j], s[j]
    counts = {}
    for o in outcomes:
        counts[o] = counts.get(o, 0) + 1
    fails = [i for i, o in enumerate(outcomes) if o != "SUCCESS"]
    return {"n": len(insts), "counts": counts, "failures": len(fails), "first_failures": fails[:5],
            "max_steps": max(steps) if steps else 0}
