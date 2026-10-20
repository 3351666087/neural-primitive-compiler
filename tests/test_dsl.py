"""DSL: parsing, flattening, composition restrictions, no host-language escape."""

import pytest

from npc.dsl import Choice, DSLError, eval_int, flatten, load_with_stdlib, parse_library
from npc.simulator import simulate
from npc.smt import Hole

LIB = load_with_stdlib("examples/toggle.npc")


def lib_with(text):
    lib = load_with_stdlib()
    return lib.merge(parse_library(text))


def test_toggle_flattens_to_raw_neurons():
    flat = flatten(LIB, LIB.networks["toggle_lite"])
    net = flat.network
    assert set(net.neuron_names) == {"g1.n", "g2.n", "L.m"}
    assert dict(net.outputs) == {"y": "L.m"}
    y = simulate(net, {"a": [1, 0, 0, 1, 0, 1, 0, 0]}).outputs["y"]
    assert y == [0, 0, 1, 1, 1, 0, 0, 1]


@pytest.mark.parametrize("body, msg", [
    ("inst c = counter(k=2) in=a", "not connected"),
    ("inst c = nosuch() in=a", "unknown primitive"),
    ("inst c = relay(d=1) in=zz", "unknown reference"),
    ("inst c = relay(d=1) in=a q=a", "has no port"),
    ("inst c = window(k=5, w=2) in=a", "requirement"),
])
def test_composition_errors(body, msg):
    lib = lib_with(f"network bad {{\n inputs a\n {body}\n output y = c.out\n}}\n")
    with pytest.raises(DSLError, match=msg):
        flatten(lib, lib.networks["bad"])


def test_output_cannot_be_an_input():
    lib = lib_with("network bad {\n inputs a\n output y = a\n}\n")
    with pytest.raises(DSLError, match="zero latency"):
        flatten(lib, lib.networks["bad"])


def test_zero_delay_rejected():
    lib = lib_with("network bad {\n inputs a\n neuron n threshold=1 leak=full\n synapse a -> n weight=1 delay=0\n output y = n\n}\n")
    with pytest.raises(Exception, match="zero delay"):
        flatten(lib, lib.networks["bad"])


def test_silent_port():
    lib = lib_with("network ok {\n inputs a\n inst c = counter(k=2) in=a rst=_\n output y = c.out\n}\n")
    net = flatten(lib, lib.networks["ok"]).network
    assert [s.src for s in net.synapses] == ["a"]


def test_holes_parse_and_resolve():
    lib = lib_with("""
network sk {
  inputs a, b
  inst c = counter(k=?{2,3}) in=?{a,b} rst=_
  neuron n threshold=?[1,3] leak=full
  synapse a -> n weight=?[-2,2] delay=1..2
  output y = ?{c.out, n}
}
""")
    nd = lib.networks["sk"]
    ch = nd.choices()
    assert [c.options for c in ch] == [(2, 3), ("a", "b"), ("c.out", "n")]
    with pytest.raises(DSLError, match="unresolved choice"):
        flatten(lib, nd)
    assign = {c.name: c.options[0] for c in ch}
    with pytest.raises(DSLError, match="integer holes"):
        flatten(lib, nd, assign)
    tpl = flatten(lib, nd, assign, allow_holes=True).network
    holes = [s.weight for s in tpl.synapses if isinstance(s.weight, Hole)]
    assert len(holes) == 2 and holes[0].name != holes[1].name  # one hole per delay


@pytest.mark.parametrize("expr", ["__import__('os')", "k.real", "k ** 2", "f(k)", "[k]", "k if k else 1"])
def test_parameter_arithmetic_has_no_escape_hatch(expr):
    with pytest.raises(DSLError):
        eval_int(expr, {"k": 2})


def test_parameter_arithmetic():
    assert eval_int("-k + 2*w - 1", {"k": 3, "w": 4}) == 4


def test_primitive_type_choice_hole():
    lib = lib_with("network sk {\n inputs a, b\n inst g = ?{and2, or2}() a=a b=b\n output y = g.out\n}\n")
    nd = lib.networks["sk"]
    (c,) = nd.choices()
    assert c.options == ("and2", "or2")
    net = flatten(lib, nd, {c.name: "or2"}).network
    assert net.neurons[0].threshold == 1
