"""Discrete integer integrate-and-fire network: data model and validation.

Formal semantics (see theory.md, Section 1). A network has binary input
channels and neurons. At every integer time step t = 0, 1, 2, ...:

    I_i(t) = bias_i + sum_{syn (j -> i, w, d)} w * s_j(t - d)     (s_j(t') = 0 for t' < 0)
    v_i(t) = clip(u_i(t) + I_i(t), vmin_i, vmax_i)
    s_i(t) = 1  iff  v_i(t) >= threshold_i
    u_i(t+1) = reset_i                 if s_i(t) = 1
             = leak(v_i(t), leak_i)    otherwise
    u_i(0) = init_i

where j ranges over inputs and neurons (an input's "spike" s_k(t) is x_k(t)),
every synaptic delay d >= 1, and leak(v, l) moves v toward 0 by l
(v - l if v > l; v + l if v < -l; else 0).

Because every delay is >= 1, all neurons update simultaneously from strictly
past values: there is no evaluation-order dependence and every feedback loop
is well defined.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Iterable, Mapping, Sequence

DEFAULT_VMIN = 0
DEFAULT_VMAX = 15
DEFAULT_MAX_DELAY = 8
FORMAT = "npc-network/1"


class NetworkError(ValueError):
    """Raised when a network violates the static well-formedness rules."""

    def __init__(self, problems: Sequence[str]):
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


def full_leak(vmin: int, vmax: int) -> int:
    """Smallest leak that returns any potential in [vmin, vmax] to 0 in one step."""
    return max(vmax, -vmin)


@dataclass(frozen=True)
class Neuron:
    name: str
    threshold: Any
    leak: Any = 0
    bias: Any = 0
    reset: Any = 0
    init: Any = 0
    vmin: Any = DEFAULT_VMIN
    vmax: Any = DEFAULT_VMAX

    @property
    def memoryless(self) -> bool:
        """True if the carried potential is always 0 after t = 0 (McCulloch-Pitts unit)."""
        return self.reset == 0 and self.leak >= full_leak(self.vmin, self.vmax)


@dataclass(frozen=True)
class Synapse:
    src: str
    dst: str
    weight: Any
    delay: Any = 1


@dataclass(frozen=True)
class Network:
    name: str
    inputs: tuple[str, ...]
    neurons: tuple[Neuron, ...]
    synapses: tuple[Synapse, ...]
    outputs: tuple[tuple[str, str], ...]  # (output port, neuron name)
    max_delay: int = DEFAULT_MAX_DELAY
    meta: Mapping[str, Any] = field(default_factory=dict, compare=False, hash=False)

    # ------------------------------------------------------------------ lookups
    @property
    def neuron_names(self) -> tuple[str, ...]:
        return tuple(n.name for n in self.neurons)

    @property
    def output_names(self) -> tuple[str, ...]:
        return tuple(p for p, _ in self.outputs)

    def neuron(self, name: str) -> Neuron:
        for n in self.neurons:
            if n.name == name:
                return n
        raise KeyError(name)

    def output_neuron(self, port: str) -> str:
        for p, n in self.outputs:
            if p == port:
                return n
        raise KeyError(port)

    # --------------------------------------------------------------- validation
    def problems(self) -> list[str]:
        out: list[str] = []
        names = [n.name for n in self.neurons]
        if len(set(names)) != len(names):
            out.append("duplicate neuron names")
        if len(set(self.inputs)) != len(self.inputs):
            out.append("duplicate input names")
        clash = set(names) & set(self.inputs)
        if clash:
            out.append(f"names used both as input and neuron: {sorted(clash)}")
        if not isinstance(self.max_delay, int) or self.max_delay < 1:
            out.append("max_delay must be an integer >= 1")
        for n in self.neurons:
            for f in ("threshold", "leak", "bias", "reset", "init", "vmin", "vmax"):
                if not isinstance(getattr(n, f), int) or isinstance(getattr(n, f), bool):
                    out.append(f"neuron {n.name}: {f} must be an integer")
            if out:
                continue
            if not (n.vmin <= 0 <= n.vmax):
                out.append(f"neuron {n.name}: need vmin <= 0 <= vmax")
            if not (1 <= n.threshold <= n.vmax):
                out.append(f"neuron {n.name}: threshold must lie in [1, vmax]")
            if n.leak < 0:
                out.append(f"neuron {n.name}: leak must be >= 0")
            if not (n.vmin <= n.reset <= n.vmax):
                out.append(f"neuron {n.name}: reset outside [vmin, vmax]")
            if not (n.vmin <= n.init <= n.vmax):
                out.append(f"neuron {n.name}: init outside [vmin, vmax]")
        sources = set(names) | set(self.inputs)
        for s in self.synapses:
            if s.src not in sources:
                out.append(f"synapse {s.src}->{s.dst}: unknown source")
            if s.dst not in names:
                out.append(f"synapse {s.src}->{s.dst}: destination must be a neuron")
            if not isinstance(s.weight, int) or isinstance(s.weight, bool):
                out.append(f"synapse {s.src}->{s.dst}: weight must be an integer")
            elif s.weight == 0:
                out.append(f"synapse {s.src}->{s.dst}: zero weight (omit the synapse)")
            if not isinstance(s.delay, int) or isinstance(s.delay, bool):
                out.append(f"synapse {s.src}->{s.dst}: delay must be an integer")
            elif not (1 <= s.delay <= self.max_delay):
                out.append(
                    f"synapse {s.src}->{s.dst}: delay {s.delay} outside [1, {self.max_delay}]"
                    " (zero delay is forbidden: it would create instantaneous loops)"
                )
        ports = [p for p, _ in self.outputs]
        if len(set(ports)) != len(ports):
            out.append("duplicate output ports")
        for p, n in self.outputs:
            if n not in names:
                out.append(f"output {p}: unknown neuron {n}")
            if p in self.inputs:
                out.append(f"output {p}: name clashes with an input")
        return out

    def validate(self) -> "Network":
        probs = self.problems()
        if probs:
            raise NetworkError(probs)
        return self

    # ------------------------------------------------------------------ metrics
    def history_depth(self) -> dict[str, int]:
        """Number of past values each source must remember (max outgoing delay)."""
        depth = {s: 0 for s in (*self.inputs, *self.neuron_names)}
        for s in self.synapses:
            depth[s.src] = max(depth[s.src], s.delay)
        return depth

    def stats(self) -> dict[str, Any]:
        """Architecture cost. state_bits is an upper bound on log2(#reachable states)."""
        pot_bits = 0
        for n in self.neurons:
            if not n.memoryless:
                pot_bits += math.ceil(math.log2(n.vmax - n.vmin + 1))
        hist_bits = sum(self.history_depth().values())
        return {
            "neurons": len(self.neurons),
            "synapses": len(self.synapses),
            "max_abs_weight": max((abs(s.weight) for s in self.synapses), default=0),
            "max_delay_used": max((s.delay for s in self.synapses), default=0),
            "memoryless_neurons": sum(1 for n in self.neurons if n.memoryless),
            "recurrent_synapses": sum(1 for s in self.synapses if s.src in self.neuron_names),
            "potential_bits": pot_bits,
            "history_bits": hist_bits,
            "state_bits": pot_bits + hist_bits,
        }

    # ------------------------------------------------------------ serialisation
    def to_dict(self) -> dict[str, Any]:
        return {
            "format": FORMAT,
            "name": self.name,
            "inputs": list(self.inputs),
            "outputs": {p: n for p, n in self.outputs},
            "max_delay": self.max_delay,
            "neurons": [asdict(n) for n in self.neurons],
            "synapses": [asdict(s) for s in self.synapses],
            "meta": dict(self.meta),
        }

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)

    @staticmethod
    def from_dict(d: Mapping[str, Any]) -> "Network":
        if d.get("format") != FORMAT:
            raise NetworkError([f"unsupported format {d.get('format')!r}"])
        return Network(
            name=d["name"],
            inputs=tuple(d["inputs"]),
            neurons=tuple(Neuron(**n) for n in d["neurons"]),
            synapses=tuple(Synapse(**s) for s in d["synapses"]),
            outputs=tuple((p, n) for p, n in d["outputs"].items()),
            max_delay=d.get("max_delay", DEFAULT_MAX_DELAY),
            meta=d.get("meta", {}),
        ).validate()

    @staticmethod
    def from_json(text: str) -> "Network":
        return Network.from_dict(json.loads(text))

    # ------------------------------------------------------------------ helpers
    def renamed(self, name: str) -> "Network":
        return replace(self, name=name)

    def permuted(self, order: Iterable[int]) -> "Network":
        """Same network with neurons listed in a different order (semantics must not change)."""
        order = list(order)
        return replace(self, neurons=tuple(self.neurons[i] for i in order))

    def pretty(self) -> str:
        lines = [f"network {self.name}  (inputs: {', '.join(self.inputs)}; max_delay={self.max_delay})"]
        for n in self.neurons:
            leak = "full" if n.leak >= full_leak(n.vmin, n.vmax) else n.leak
            lines.append(
                f"  neuron {n.name}: threshold={n.threshold} leak={leak} bias={n.bias} "
                f"reset={n.reset} init={n.init} range=[{n.vmin},{n.vmax}]"
            )
        for s in self.synapses:
            lines.append(f"  synapse {s.src} -> {s.dst}  w={s.weight:+d} d={s.delay}")
        for p, n in self.outputs:
            lines.append(f"  output {p} = {n}")
        return "\n".join(lines)
