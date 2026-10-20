"""Frozen neural templates for the candidate primitives, emitted as Mission 01 integer IF neurons.

Nothing here knows any task. Every template is a fixed wiring rule whose only parameters are an index
set and source relations / coordinate sets supplied by the caller. Weights are not searched: they are
fixed functions of fan-in (e.g. letter weight = number of sources).

Contracts (proved for arbitrary index sets in cog/proofs.py; checked per instance in tests):

  CMR  (letter-gated union register)
       Y_j(t) = M_j(t-2), M(-1) = {}, and for the letter l active at t (at most one):
       M_j(t) = OR_{k in Src_l(j)} M_k(t-1)  OR  OR_{d in DSrc_l(j)} d(t)  [OR 1 if Src_l(j) has "one"],
       M_j(t) = M_j(t-1) if no letter is active.
       Neural form: P[j,l](t) = l(t-1) AND (sum of sources at t-1 >= 1), sources of P[j,l] are the
       P[k,*] neurons of every source coordinate k (exactly one or none of P[k,*] fires, because at
       most one letter was active) and data channels; idle neuron P[j,_](t) = no letter(t-1) AND M_j(t-2).
  SEL  (gated selection / pair table)
       out_b(t) = OR_{(s, x) in Pairs(b)} s(t-1-d) AND x(t-1-e)
  ANY  (region reduction)   out(t) = OR_{x in R} x(t-e)
  GATE (and / and-not with delays)   g(t) = AND_i p_i(t-dp_i) AND NOT OR_k n_k(t-dn_k)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from npc.network import Network, Neuron, Synapse


@dataclass
class Builder:
    name: str
    max_delay: int = 4
    inputs: list[str] = field(default_factory=list)
    neurons: dict[str, Neuron] = field(default_factory=dict)
    synapses: list[Synapse] = field(default_factory=list)
    outputs: list[tuple[str, str]] = field(default_factory=list)
    _pos: dict[str, int] = field(default_factory=dict)  # positive fan-in per neuron (for vmax)

    def input(self, name: str) -> str:
        if name not in self.inputs:
            self.inputs.append(name)
        return name

    def neuron(self, name: str, threshold: int, bias: int = 0) -> str:
        if name in self.neurons or name in self.inputs:
            raise ValueError(f"duplicate signal {name}")
        self.neurons[name] = Neuron(name, threshold=threshold, leak=0, bias=bias)  # leak/vmax fixed in build()
        self._pos[name] = max(0, bias)
        return name

    def syn(self, src: str, dst: str, w: int, d: int = 1) -> None:
        if w == 0:
            return
        if not (1 <= d <= self.max_delay):
            raise ValueError(f"delay {d} outside [1, {self.max_delay}] on {src}->{dst}")
        self.synapses.append(Synapse(src, dst, w, d))
        if w > 0:
            self._pos[dst] += w

    def output(self, port: str, neuron: str) -> None:
        self.outputs.append((port, neuron))

    def build(self) -> Network:
        neurons = []
        for n in self.neurons.values():
            vmax = max(n.threshold, self._pos[n.name], 1)
            neurons.append(Neuron(n.name, threshold=n.threshold, leak=vmax, bias=n.bias, vmin=0, vmax=vmax))
        return Network(self.name, tuple(self.inputs), tuple(neurons), tuple(self.synapses), tuple(self.outputs),
                       max_delay=self.max_delay).validate()


ONE = ("one",)


def cmr(b: Builder, prefix: str, coords: list, rules: dict[str, dict], letter_chan: dict[str, str]) -> dict:
    """Letter-gated union register.

    rules[l][j] = list of sources for target coordinate j under letter l; a source is ("c", k) for old
    coordinate k, ("d", channel) for a data channel read together with the letter, or ONE.
    Coordinates missing from rules[l] (or with no sources) become 0 under l.
    Returns {coord: output neuron name}, Y_j(t) = M_j(t-2).
    """
    letters = list(rules)
    idle = "_"
    P: dict[tuple, str] = {}
    for j in coords:
        for l in letters:
            srcs = rules[l].get(j, [])
            if srcs:
                n = 1 if ONE in srcs else sum(1 for s in srcs if s != ONE)
                P[(j, l)] = b.neuron(f"{prefix}.P[{_s(j)}|{l}]", threshold=1 if ONE in srcs else n + 1)
        P[(j, idle)] = b.neuron(f"{prefix}.P[{_s(j)}|_]", threshold=1)
    tags = letters + [idle]
    for j in coords:
        for l in letters:
            if (j, l) not in P:
                continue
            srcs = rules[l][j]
            if ONE in srcs:
                b.syn(letter_chan[l], P[(j, l)], 1)
                continue
            n = len(srcs)
            b.syn(letter_chan[l], P[(j, l)], n)
            for s in srcs:
                if s[0] == "c":
                    for t2 in tags:
                        if (s[1], t2) in P:
                            b.syn(P[(s[1], t2)], P[(j, l)], 1)
                elif s[0] == "d":
                    b.syn(b.input(s[1]) if s[1] not in b.neurons else s[1], P[(j, l)], 1)
                else:
                    raise ValueError(f"bad source {s}")
        for t2 in tags:  # idle: hold
            if (j, t2) in P:
                b.syn(P[(j, t2)], P[(j, idle)], 1)
        for l in letters:
            b.syn(letter_chan[l], P[(j, idle)], -1)
    Y = {}
    for j in coords:
        Y[j] = b.neuron(f"{prefix}.Y[{_s(j)}]", threshold=1)
        for t2 in tags:
            if (j, t2) in P:
                b.syn(P[(j, t2)], Y[j], 1)
    return Y


def sel(b: Builder, prefix: str, pairs: dict, delay: int, xdelay: int = 1) -> dict:
    """pairs[b_coord] = list of (selector coord, selector signal, table signal).
    out_b(t) = OR s(t-1-delay) AND x(t-1-xdelay)."""
    out = {}
    for bc, lst in pairs.items():
        ands = []
        for i, (key, s, x) in enumerate(lst):
            nm = f"{prefix}.A[{_s(bc)}|{_s(key)}]" if bc != () else f"{prefix}.A[{_s(key)}]"
            if nm in b.neurons:
                nm = f"{prefix}.A[{_s(bc)}|{_s(key)}#{i}]"
            a = b.neuron(nm, threshold=2)
            b.syn(s, a, 1, delay)
            b.syn(x, a, 1, xdelay)
            ands.append(a)
        o = b.neuron(f"{prefix}.O[{_s(bc)}]", threshold=1)
        for a in ands:
            b.syn(a, o, 1, 1)
        out[bc] = o
    return out


def any_(b: Builder, name: str, srcs: list[str], delay: int = 1) -> str:
    """out(t) = OR_{x in srcs} x(t-delay)."""
    o = b.neuron(name, threshold=1)
    for s in srcs:
        b.syn(s, o, 1, delay)
    return o


def gate(b: Builder, name: str, pos: list[tuple[str, int]], neg: list[tuple[str, int]] = ()) -> str:
    """g(t) = AND_i p_i(t - d_i) AND NOT OR_k n_k(t - e_k)."""
    g = b.neuron(name, threshold=len(pos))
    for s, d in pos:
        b.syn(s, g, 1, d)
    for s, d in neg:
        b.syn(s, g, -len(pos), d)
    return g


def _s(c) -> str:
    return ",".join(str(x) for x in c) if isinstance(c, tuple) else str(c)
