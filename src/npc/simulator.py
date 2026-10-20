"""Three executions of the same semantics (network.py docstring).

* ``simulate``       - reference interpreter, pure Python, one trace, written to
                       mirror the formal definition line by line.
* ``simulate_batch`` - numpy implementation over many traces at once (used by
                       the exhaustive bounded checker and the enumerative synthesiser).
* ``CompiledNet``    - explicit finite-state step function on hashable states
                       (used by the unbounded reachability checker).

The test-suite checks that all three agree on random networks and inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

from .network import Network


def clip(v: int, lo: int, hi: int) -> int:
    return lo if v < lo else hi if v > hi else v


def leak_toward_zero(v: int, lam: int) -> int:
    if v > lam:
        return v - lam
    if v < -lam:
        return v + lam
    return 0


@dataclass
class Trace:
    T: int
    inputs: dict[str, list[int]]
    spikes: dict[str, list[int]]
    potentials: dict[str, list[int]]  # v(t): potential after integration, before reset
    outputs: dict[str, list[int]]

    def table(self) -> str:
        rows = []
        width = max(len(k) for k in (*self.inputs, *self.spikes, *self.outputs)) if self.T else 1
        hdr = " " * (width + 2) + "".join(f"{t % 10}" for t in range(self.T))
        rows.append(hdr)
        for k, v in self.inputs.items():
            rows.append(f"{k:>{width}} |" + "".join("1" if b else "." for b in v))
        for k, v in self.spikes.items():
            rows.append(f"{k:>{width}} |" + "".join("1" if b else "." for b in v))
        for k, v in self.outputs.items():
            rows.append(f"{k:>{width}}*|" + "".join("1" if b else "." for b in v))
        return "\n".join(rows)


def _normalise_inputs(net: Network, inputs: Mapping[str, Sequence[int]], T: int | None) -> tuple[dict[str, list[int]], int]:
    missing = [k for k in net.inputs if k not in inputs]
    extra = [k for k in inputs if k not in net.inputs]
    if missing or extra:
        raise ValueError(f"input mismatch: missing={missing} extra={extra}")
    lens = {len(v) for v in inputs.values()}
    if T is None:
        if len(lens) > 1:
            raise ValueError("input sequences have different lengths")
        T = lens.pop() if lens else 0
    out = {}
    for k in net.inputs:
        seq = [int(bool(b)) for b in inputs[k]]
        if len(seq) < T:
            seq = seq + [0] * (T - len(seq))
        out[k] = seq[:T]
    return out, T


def simulate(net: Network, inputs: Mapping[str, Sequence[int]], T: int | None = None) -> Trace:
    """Reference interpreter. Mirrors the definition in network.py exactly."""
    net.validate()
    x, T = _normalise_inputs(net, inputs, T)
    incoming: dict[str, list] = {n.name: [] for n in net.neurons}
    for s in net.synapses:
        incoming[s.dst].append(s)
    hist: dict[str, list[int]] = {k: x[k] for k in net.inputs}
    for n in net.neurons:
        hist[n.name] = []
    u = {n.name: n.init for n in net.neurons}
    pots: dict[str, list[int]] = {n.name: [] for n in net.neurons}
    for t in range(T):
        v_now: dict[str, int] = {}
        s_now: dict[str, int] = {}
        for n in net.neurons:  # order irrelevant: only values at t-d (d >= 1) are read
            current = n.bias
            for syn in incoming[n.name]:
                tt = t - syn.delay
                if tt >= 0:
                    current += syn.weight * hist[syn.src][tt]
            v = clip(u[n.name] + current, n.vmin, n.vmax)
            v_now[n.name] = v
            s_now[n.name] = 1 if v >= n.threshold else 0
        for n in net.neurons:
            u[n.name] = n.reset if s_now[n.name] else leak_toward_zero(v_now[n.name], n.leak)
            hist[n.name].append(s_now[n.name])
            pots[n.name].append(v_now[n.name])
    spikes = {n.name: hist[n.name] for n in net.neurons}
    outputs = {p: list(spikes[n]) for p, n in net.outputs}
    return Trace(T=T, inputs=x, spikes=spikes, potentials=pots, outputs=outputs)


# --------------------------------------------------------------------------- batch
class BatchSim:
    """Vectorised simulator. X has shape (B, m, T) with values in {0,1}."""

    def __init__(self, net: Network):
        net.validate()
        self.net = net
        self.m = len(net.inputs)
        self.n = len(net.neurons)
        idx = {k: i for i, k in enumerate(net.inputs)}
        for j, nr in enumerate(net.neurons):
            idx[nr.name] = self.m + j
        self.delays = sorted({s.delay for s in net.synapses})
        self.W = {d: np.zeros((self.m + self.n, self.n), dtype=np.int64) for d in self.delays}
        for s in net.synapses:
            self.W[s.delay][idx[s.src], idx[s.dst] - self.m] += s.weight
        f = lambda a: np.array([getattr(nr, a) for nr in net.neurons], dtype=np.int64)
        self.theta, self.leak, self.bias = f("threshold"), f("leak"), f("bias")
        self.reset, self.init, self.vmin, self.vmax = f("reset"), f("init"), f("vmin"), f("vmax")
        self.out_idx = [net.neuron_names.index(n) for _, n in net.outputs]

    def run(self, X: np.ndarray) -> np.ndarray:
        """Returns all source values S with shape (B, m+n, T): inputs then neuron spikes."""
        X = np.asarray(X)
        B, m, T = X.shape
        assert m == self.m
        S = np.zeros((B, self.m + self.n, T), dtype=np.int64)
        S[:, : self.m, :] = X
        u = np.broadcast_to(self.init, (B, self.n)).copy()
        for t in range(T):
            cur = np.broadcast_to(self.bias, (B, self.n)).copy()
            for d in self.delays:
                if t - d >= 0:
                    cur += S[:, :, t - d] @ self.W[d]
            v = np.clip(u + cur, self.vmin, self.vmax)
            s = (v >= self.theta).astype(np.int64)
            lk = np.where(v > self.leak, v - self.leak, np.where(v < -self.leak, v + self.leak, 0))
            u = np.where(s == 1, self.reset, lk)
            S[:, self.m :, t] = s
        return S

    def outputs(self, X: np.ndarray) -> np.ndarray:
        S = self.run(X)
        return S[:, [self.m + i for i in self.out_idx], :]


def simulate_batch(net: Network, X: np.ndarray) -> np.ndarray:
    return BatchSim(net).run(X)


# ------------------------------------------------------------------ finite state
class CompiledNet:
    """Explicit-state view: state = (carried potentials u, per-source spike history bitmasks).

    Bit (d-1) of hist[k] holds the value of source k at time t-d. Only
    max-outgoing-delay bits are kept per source, so the state space is finite:
    |states| <= prod_i (vmax_i - vmin_i + 1) * 2^(sum of history depths).
    """

    def __init__(self, net: Network):
        net.validate()
        self.net = net
        self.m = len(net.inputs)
        self.n = len(net.neurons)
        names = list(net.inputs) + list(net.neuron_names)
        idx = {k: i for i, k in enumerate(names)}
        depth = net.history_depth()
        self.depth = tuple(depth[k] for k in names)
        self.mask = tuple((1 << d) - 1 for d in self.depth)
        self.incoming = [[] for _ in range(self.n)]
        for s in net.synapses:
            self.incoming[idx[s.dst] - self.m].append((idx[s.src], s.weight, s.delay - 1))
        self.params = [(nr.threshold, nr.leak, nr.bias, nr.reset, nr.vmin, nr.vmax) for nr in net.neurons]
        self.out_idx = tuple(net.neuron_names.index(n) for _, n in net.outputs)

    def initial_state(self) -> tuple:
        return (tuple(nr.init for nr in self.net.neurons), tuple(0 for _ in self.depth))

    def fire(self, state: tuple) -> tuple[tuple[int, ...], tuple[int, ...]]:
        """Spikes and potentials at the current step. Independent of the current input."""
        u, hist = state
        spikes, pots = [], []
        for i in range(self.n):
            th, lk, bias, reset, lo, hi = self.params[i]
            cur = bias
            for src, w, sh in self.incoming[i]:
                if (hist[src] >> sh) & 1:
                    cur += w
            v = u[i] + cur
            v = lo if v < lo else hi if v > hi else v
            pots.append(v)
            spikes.append(1 if v >= th else 0)
        return tuple(spikes), tuple(pots)

    def advance(self, state: tuple, spikes: tuple, pots: tuple, x: Sequence[int]) -> tuple:
        u, hist = state
        new_u = []
        for i in range(self.n):
            th, lk, bias, reset, lo, hi = self.params[i]
            if spikes[i]:
                new_u.append(reset)
            else:
                v = pots[i]
                new_u.append(v - lk if v > lk else v + lk if v < -lk else 0)
        vals = list(x) + list(spikes)
        new_hist = tuple(((hist[k] << 1) | vals[k]) & self.mask[k] for k in range(self.m + self.n))
        return (tuple(new_u), new_hist)

    def outputs(self, spikes: tuple) -> tuple[int, ...]:
        return tuple(spikes[i] for i in self.out_idx)

    def run(self, inputs: Mapping[str, Sequence[int]], T: int | None = None) -> dict[str, list[int]]:
        x, T = _normalise_inputs(self.net, inputs, T)
        st = self.initial_state()
        res = {n: [] for n in self.net.neuron_names}
        for t in range(T):
            s, p = self.fire(st)
            for i, n in enumerate(self.net.neuron_names):
                res[n].append(s[i])
            st = self.advance(st, s, p, [x[k][t] for k in self.net.inputs])
        return res
