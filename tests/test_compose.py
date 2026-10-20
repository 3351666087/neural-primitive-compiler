"""Compositional verification is sound: it never disagrees with monolithic verification."""

import random

from hypothesis import given, settings, strategies as st

from npc.compose import compositional_verify
from npc.dsl import InstDecl, NetworkDef, flatten, load_with_stdlib, parse_library
from npc.gen import random_formula
from npc.spec import F, Prev, Spec, TRUE, atom, make_spec
from npc.verify import Status, reach

LIB = load_with_stdlib("examples/toggle.npc")


def test_toggle_compositional_matches_monolithic():
    nd, sp = LIB.networks["toggle_lite"], LIB.specs["parity_sparse"]
    c = compositional_verify(LIB, nd, sp)
    m = reach(flatten(LIB, nd).network, sp)
    assert c.result.status == m.status == Status.VERIFIED_UNBOUNDED


def test_undischarged_assumption_is_not_a_proof():
    lib = load_with_stdlib()
    lib.merge(parse_library("network l {\n inputs a, b\n inst L = latch_lite() set=a rst=b\n output y = L.out\n}\n"))
    sp = make_spec("latch", ["a", "b"], ["y"], "y <-> prev(since(!b, a & !b))")
    c = compositional_verify(lib, lib.networks["l"], sp)
    assert c.result.status == Status.UNKNOWN
    assert "obligation not discharged" in c.result.stats["reason"]
    assert reach(flatten(lib, lib.networks["l"]).network, sp).status == Status.COUNTEREXAMPLE


PRIMS = [("relay", {"d": 1}), ("relay", {"d": 2}), ("and2", {}), ("or2", {}), ("gate", {}), ("inv", {}),
         ("rise", {}), ("window", {"k": 2, "w": 3}), ("counter", {"k": 2}), ("latch", {}), ("latch_lite", {}),
         ("pairdet", {}), ("compare", {"w": 2, "k": 1})]


def random_composition(rng, k):
    nd = NetworkDef("rc", max_delay=4, inputs=["a", "b"])
    srcs = ["a", "b", "_"] + [f"i{j}.out" for j in range(k)]
    for j in range(k):
        prim, args = rng.choice(PRIMS)
        ports = LIB.primitives[prim].ports
        nd.instances.append(InstDecl(f"i{j}", prim, dict(args), {p: rng.choice(srcs) for p in ports}))
    nd.outputs.append(("y", "i0.out"))
    return nd


@settings(max_examples=40, deadline=None)
@given(st.integers(min_value=0, max_value=10**9))
def test_compositional_never_contradicts_monolithic(seed):
    rng = random.Random(seed)
    nd = random_composition(rng, rng.randint(1, 3))
    phi = random_formula(rng, ["a", "b"], depth=2, unbounded=False)
    g = F("iff", (atom("y"), Prev(phi, rng.randint(1, 2)))) if rng.random() < 0.7 else \
        random_formula(rng, ["a", "b", "y"], depth=2, unbounded=False)
    sp = Spec("r", ("a", "b"), ("y",), TRUE, g)
    c = compositional_verify(LIB, nd, sp)
    m = reach(flatten(LIB, nd).network, sp)
    if c.result.status in (Status.VERIFIED_UNBOUNDED, Status.COUNTEREXAMPLE):
        assert c.result.status == m.status
