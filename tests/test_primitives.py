"""Phase 2: every primitive's contract is proved, never assumed from its name."""

import pytest

from npc.dsl import DSLError, load_with_stdlib, parse_library
from npc.network import Network, Neuron
from npc.spec import Spec, parse
from npc.verify import Status, bmc, reach

LIB = load_with_stdlib()

GRID = [("relay", {"d": d}) for d in range(1, 5)]
GRID += [("window", {"k": k, "w": w}) for w in range(1, 5) for k in range(1, w + 1)]
GRID += [("compare", {"w": w, "k": k}) for w in range(1, 4) for k in range(1, w + 1)]
GRID += [("counter", {"k": k}) for k in range(1, 7)]
GRID += [("clock", {"p": p}) for p in range(2, 7)]
GRID += [(p, {}) for p in ("and2", "or2", "gate", "inv", "rise", "latch", "latch_lite", "pairdet")]


@pytest.mark.parametrize("prim,args", GRID, ids=[f"{p}{a}" for p, a in GRID])
def test_contract_holds_unbounded_and_bounded(prim, args):
    net, contract = LIB.primitives[prim].instantiate(args)
    r = reach(net, contract)
    assert r.status == Status.VERIFIED_UNBOUNDED, r.summary()
    assert bmc(net, contract, 10).status == Status.VERIFIED_BOUNDED


def test_all_library_primitives_are_covered():
    assert {p for p, _ in GRID} == set(LIB.primitives)


def _with(contract: Spec, guarantee: str, assume: str = "true") -> Spec:
    return Spec("variant", contract.inputs, contract.outputs, parse(assume), parse(guarantee), 0, "strict")


def test_name_is_not_evidence_pairdet():
    """`pairdet` looks like 'fires after two consecutive spikes', but its leak and reset make it skip."""
    net, c = LIB.primitives["pairdet"].instantiate({})
    r = reach(net, _with(c, "out <-> prev(in & prev(in))"))
    assert r.status == Status.COUNTEREXAMPLE
    assert r.counterexample == {"in": [1, 1, 1, 0]}


def test_latch_lite_needs_its_assumption():
    net, c = LIB.primitives["latch_lite"].instantiate({})
    r = reach(net, _with(c, "out <-> prev(since(!rst, set & !rst))"))
    assert r.status == Status.COUNTEREXAMPLE


def test_counter_depends_on_its_floor():
    """The counter's reset relies on clipping at vmin = 0; with a negative floor the contract breaks."""
    net, c = LIB.primitives["counter"].instantiate({"k": 3})
    n = net.neurons[0]
    lowered = Network(net.name, net.inputs, (Neuron(n.name, n.threshold, n.leak, n.bias, n.reset, n.init, -3, n.vmax),),
                      net.synapses, net.outputs, net.max_delay).validate()
    assert reach(lowered, c).status == Status.COUNTEREXAMPLE


def test_primitive_without_contract_is_rejected():
    with pytest.raises(DSLError, match="declared by name only"):
        parse_library("""
primitive magic() {
  ports in
  neuron n threshold=1 leak=full
  synapse in -> n weight=1 delay=1
  output out = n
}
""")


def test_parameter_requirements_enforced():
    with pytest.raises(DSLError, match="requirement"):
        LIB.primitives["window"].instantiate({"k": 4, "w": 2})
    with pytest.raises(DSLError, match="requirement"):
        LIB.primitives["clock"].instantiate({"p": 1})
