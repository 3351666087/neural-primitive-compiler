"""J1-net: a compiled network (npc.network.Network) in closed loop with the reference environment, in lockstep
with the judge's CIR interpreter. JUDGE SIDE: it receives the network as an object; it does not import the
compiler or any constructor.

Network clocking (amendment 1, item 4): each environment step lasts D ticks; the observation channels are held
for the whole step; the input channel `clk` is 1 only at the last tick; the action is read at the last tick
from the output ports named after the actions. The simulator below re-implements the npc semantics
(network.py) for a batch, tick by tick, so that inputs can depend on earlier outputs; it is cross-checked against
npc.simulator.BatchSim on random networks in the self-test.
"""

from __future__ import annotations

import numpy as np

from cir_interp import Interp
from env import ACTIONS, BatchEnv


class NetBatch:
    def __init__(self, net, B):
        self.net = net
        self.B = B
        self.inputs = list(net.inputs)
        self.m, self.n = len(net.inputs), len(net.neurons)
        idx = {k: i for i, k in enumerate(net.inputs)}
        for j, nr in enumerate(net.neurons):
            idx[nr.name] = self.m + j
        self.idx = idx
        f = lambda a: np.array([getattr(nr, a) for nr in net.neurons], dtype=np.int64)
        self.theta, self.leak, self.bias = f("threshold"), f("leak"), f("bias")
        self.reset, self.vmin, self.vmax = f("reset"), f("vmin"), f("vmax")
        self.u = np.broadcast_to(f("init"), (B, self.n)).copy()
        self.maxd = max([s.delay for s in net.synapses] or [1])
        self.groups = []
        for d in sorted({s.delay for s in net.synapses}):
            syn = sorted([s for s in net.synapses if s.delay == d], key=lambda s: idx[s.dst])
            src = np.array([idx[s.src] for s in syn])
            dst = np.array([idx[s.dst] - self.m for s in syn])
            w = np.array([s.weight for s in syn], dtype=np.int64)
            starts = np.flatnonzero(np.r_[True, dst[1:] != dst[:-1]])
            self.groups.append((d, src, w, starts, dst[starts]))
        self.hist = np.zeros((self.maxd, B, self.m + self.n), dtype=np.int64)   # ring buffer of past values
        self.t = 0
        self.out_idx = {p: self.m + net.neuron_names.index(nm) for p, nm in net.outputs}

    def tick(self, x):
        """x: (B, m) input values at this tick. Returns the full value vector (B, m+n) at this tick."""
        cur = np.broadcast_to(self.bias, (self.B, self.n)).copy()
        for d, src, w, starts, dsts in self.groups:
            if self.t - d < 0:
                continue
            past = self.hist[(self.t - d) % self.maxd]
            contrib = past[:, src] * w
            cur[:, dsts] += np.add.reduceat(contrib, starts, axis=1)
        v = np.clip(self.u + cur, self.vmin, self.vmax)
        s = (v >= self.theta).astype(np.int64)
        lk = np.where(v > self.leak, v - self.leak, np.where(v < -self.leak, v + self.leak, 0))
        self.u = np.where(s == 1, self.reset, lk)
        now = np.concatenate([x.astype(np.int64), s], axis=1)
        self.hist[self.t % self.maxd] = now
        self.t += 1
        return now


def run_net_lockstep(net, prog, spec, insts):
    """Returns per-episode outcomes of the NETWORK-driven loop, and the first step where the network's action
    differed from the CIR interpreter's action (None if never), plus mismatch counts."""
    env = BatchEnv(spec, insts)
    sim = NetBatch(net, env.B)
    it = Interp(prog, env.B)
    D = prog["D"]
    mismatch_steps = np.full(env.B, -1)
    step_no = 0
    while not env.done.all():
        obs = env.observation()
        ref_acts, conflict = it.step(obs)
        x = np.zeros((env.B, sim.m), dtype=np.int64)
        for i, ch in enumerate(sim.inputs):
            if ch in obs:
                x[:, i] = obs[ch]
        clk_i = sim.inputs.index("clk") if "clk" in sim.inputs else None
        for k in range(D):
            if clk_i is not None:
                x[:, clk_i] = 1 if k == D - 1 else 0
            now = sim.tick(x)
        acts = {a: (now[:, sim.out_idx[a]] == 1) if a in sim.out_idx else np.zeros(env.B, bool) for a in ACTIONS}
        diff = np.zeros(env.B, dtype=bool)
        for a in ACTIONS:
            diff |= acts[a] != ref_acts[a]
        new_mis = diff & ~env.done & (mismatch_steps < 0)
        mismatch_steps[new_mis] = step_no
        env._finish(conflict, "REG_CONFLICT")
        env.act(acts)
        step_no += 1
    return {"outcomes": env.outcome.tolist(), "steps": env.steps.tolist(),
            "first_mismatch_step": mismatch_steps.tolist(),
            "episodes_with_mismatch": int((mismatch_steps >= 0).sum())}
