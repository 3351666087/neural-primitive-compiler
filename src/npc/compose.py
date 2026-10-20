"""Contract-based (compositional) verification of primitive compositions.

Rule (theory.md, Theorem 5). Let a network be built only from primitive
instances. Suppose

  (1) every instance's implementation satisfies its contract (A_i, G_i) in
      strict mode, where G_i is a conjunction of `o <-> P_o` with P_o strictly
      in the past (proved once per primitive/parameter, then cached);
  (2) in the *abstract system* - where each instance output o is computed as
      P_o over the bound signals, with no neurons at all - every A_i holds
      whenever the environment assumption has held, and the target spec holds.

Then the flattened neural network satisfies the target spec. Proof by
induction on time; the base of the induction is that every P_o reads only
strictly earlier values, so circular (feedback) bindings are sound.

The abstract system is explored with the same explicit-state engine as the
monolithic check. Its states are tuples of contract-monitor states rather than
neuron potentials/spike histories, which is what the Q3 experiment compares.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from .dsl import DSLError, Library, NetworkDef, flatten
from .network import Network
from .spec import FALSE, F, Monitor, Spec, atom, strictly_past, subst
from .verify import Result, Status, explore, reach

_PROOF_CACHE: dict[tuple, Result] = {}


def _key(prim: str, args: Mapping[str, int]) -> tuple:
    return (prim, tuple(sorted(args.items())))


def prove_primitive(lib: Library, prim: str, args: Mapping[str, int] | None = None,
                    max_states: int = 500_000) -> Result:
    """Unbounded proof that a primitive instance meets its contract (cached)."""
    pd = lib.primitives[prim]
    env = pd.bind(args or {})
    key = _key(prim, env)
    if key not in _PROOF_CACHE:
        net, contract = pd.instantiate(env)
        _PROOF_CACHE[key] = reach(net, contract, max_states=max_states)
    return _PROOF_CACHE[key]


def functional_parts(contract: Spec) -> dict[str, F]:
    """Split a contract guarantee into {output: P} and check P is strictly past."""
    fo = contract.functional_outputs()
    if fo is None:
        raise DSLError(f"{contract.name}: guarantee is not of the form `out <-> P` per output")
    sig = set(contract.inputs) | set(contract.outputs)
    for o, p in fo.items():
        if not strictly_past(p, sig):
            raise DSLError(f"{contract.name}: P for {o} reads current-step values; not strictly causal")
    return fo


def _silence(f: F, unbound: set[str]) -> F:
    if f.op == "atom" and f.params[0] in unbound:
        return FALSE
    if not f.args:
        return f
    return F(f.op, tuple(_silence(a, unbound) for a in f.args), f.params)


class AbstractSystem:
    """Composition seen only through contracts: no neurons, one monitor per instance output."""

    def __init__(self, lib: Library, nd: NetworkDef, assignment: Mapping[str, Any] | None = None):
        if nd.neurons or nd.synapses:
            raise DSLError("compositional verification needs a network made only of primitive instances")
        flat = flatten(lib, nd, assignment)  # validates bindings and parameters
        self.flat = flat
        self.inputs = tuple(nd.inputs)
        self.defs: list[tuple[str, Monitor]] = []
        self.obligations: list[tuple[str, Monitor]] = []
        self.contracts: dict[str, tuple[str, dict[str, int]]] = {}
        for iname, (prim, args, bound) in flat.instances.items():
            _, contract = lib.primitives[prim].instantiate(args)
            ren = {p: (b if b is not None else f"__unbound_{p}") for p, b in bound.items()}
            # bound values are neuron names; map them back to "inst.out" signal names
            neuron_to_sig = {n: s for s, n in flat.output_neurons.items()}
            ren = {p: neuron_to_sig.get(v, v) for p, v in ren.items()}
            for o in contract.outputs:
                ren[o] = f"{iname}.{o}"
            unbound = {v for v in ren.values() if v.startswith("__unbound_")}
            for o, p in functional_parts(contract).items():
                self.defs.append((f"{iname}.{o}", Monitor(_silence(subst(p, ren), unbound))))
            if contract.assume.op != "const" or contract.assume.params != (True,):
                a = _silence(subst(contract.assume, ren), unbound)
                self.obligations.append((f"assumption of {iname} ({prim}): {contract.assume}", Monitor(a)))
            self.contracts[iname] = (prim, args)
        self.port_alias = {}
        for o, ref in nd.outputs:
            neuron = dict(flat.network.outputs)[o]
            sig = {n: s for s, n in flat.output_neurons.items()}[neuron]
            self.port_alias[o] = sig
        self._dummy = {name: False for name, _ in self.defs}
        self._dummy.update({k: False for k in self.inputs})
        self.signals = tuple(n for n, _ in self.defs) + tuple(self.port_alias)

    def initial_state(self):
        return tuple(m.init for _, m in self.defs)

    def fire(self, state):
        vals = {}
        for (name, mon), st in zip(self.defs, state):
            _, v = mon.step(st, self._dummy)  # value is independent of current inputs (strictly past)
            vals[name] = v
        for o, sig in self.port_alias.items():
            vals[o] = vals[sig]
        return vals, vals

    def advance(self, state, aux, x):
        val = dict(zip(self.inputs, x))
        val.update(aux)
        return tuple(mon.step(st, val)[0] for (_, mon), st in zip(self.defs, state))


@dataclass
class CompositionalResult:
    result: Result
    primitive_proofs: dict[str, Result] = field(default_factory=dict)
    abstract_time_s: float = 0.0
    proof_time_s: float = 0.0  # time spent proving primitives in this call (0 if cached)

    def summary(self) -> str:
        lines = [self.result.summary().replace("[reach]", "[compositional]")]
        for k, r in self.primitive_proofs.items():
            lines.append(f"    contract {k}: {r.status.value}")
        return "\n".join(lines)


def compositional_verify(lib: Library, nd: NetworkDef, spec: Spec, assignment: Mapping[str, Any] | None = None,
                         max_states: int = 2_000_000, timeout_s: float = 120.0) -> CompositionalResult:
    t0 = time.perf_counter()
    system = AbstractSystem(lib, nd, assignment)
    proofs = {}
    for iname, (prim, args) in system.contracts.items():
        r = prove_primitive(lib, prim, args)
        proofs[f"{iname}={prim}{args}"] = r
        if r.status != Status.VERIFIED_UNBOUNDED:
            res = Result(Status.UNKNOWN, "compositional", "contract of a component is not proven", 0.0,
                         stats={"reason": f"contract of {iname} not proven: {r.status.value}"})
            return CompositionalResult(res, proofs)
    t1 = time.perf_counter()
    missing = set(spec.outputs) - set(system.port_alias)
    if missing:
        raise DSLError(f"network lacks outputs {sorted(missing)}")
    res = explore(system, spec, system.obligations, max_states=max_states, timeout_s=timeout_s,
                  replay_net=system.flat.network, engine="compositional")
    if res.status == Status.VERIFIED_UNBOUNDED:
        res.scope = ("all input traces, every length, for the flattened network - derived from per-primitive "
                     "unbounded contract proofs plus an unbounded check of the contract-level system")
    return CompositionalResult(res, proofs, time.perf_counter() - t1, t1 - t0)
