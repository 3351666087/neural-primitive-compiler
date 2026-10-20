"""Phase 3 synthesis: results are independently re-verified; UNREALIZABLE agrees with theory."""

import random

import pytest
from hypothesis import given, settings, strategies as st

from npc.dsl import load_with_stdlib, parse_library
from npc.fsm import classical_network
from npc.gen import random_formula
from npc.network import Network, Neuron, Synapse
from npc.smt import Hole
from npc.spec import F, Prev, Spec, TRUE, atom, make_spec
from npc.synth import (EXHAUSTED, SOLVED, UNREALIZABLE, cegis, compose_dag, enumerate_params, fully_connected,
                       minimize_synapses, search_neurons, sketch)
from npc.verify import Status, verify_all

SEQ = make_spec("seq_ab", ["a", "b"], ["y"], "y <-> prev(b & prev(a))")
PAR1 = make_spec("parity_L1", ["a"], ["y"], "y <-> prev(modcount[2](a) == 1)")
CNT = make_spec("cnt3_reset", ["a", "r"], ["y"], "y <-> prev(a & !r & modcount[3](a; r) == 0)")


def reverify(net, spec):
    res = verify_all(net, spec, T=8)
    assert all(r.verified for r in res), [r.summary() for r in res]
    assert res[-1].status == Status.VERIFIED_UNBOUNDED


def test_cegis_solves_and_minimises():
    tpl = fully_connected(SEQ, 1)
    r = cegis(tpl, SEQ, T=6, timeout_s=60)
    assert r.status == SOLVED
    reverify(r.network, SEQ)
    m = minimize_synapses(tpl, SEQ, r, T=6, timeout_s=60)
    assert len(m.network.synapses) == 2 and m.detail["synapse_minimality_proven"]
    reverify(m.network, SEQ)


def test_unrealizable_agrees_with_theorem3():
    net, info = classical_network(PAR1)
    assert net is None and info["status"] == "UNREALIZABLE"
    r, trail = search_neurons(PAR1, n_max=2, T=6, timeout_s=60)
    assert [t["status"] for t in trail] == [UNREALIZABLE, UNREALIZABLE]


def test_enumeration_baseline():
    tpl = Network("t", ("a", "b"), (Neuron("n", Hole("th", 1, 3), 15),),
                  (Synapse("a", "n", Hole("wa", -1, 1), 2), Synapse("b", "n", Hole("wb", -1, 1), 1)),
                  (("y", "n"),), max_delay=2)
    r = enumerate_params(tpl, SEQ, T=6)
    assert r.status == SOLVED
    reverify(r.network, SEQ)
    r2 = enumerate_params(fully_connected(PAR1, 1, in_delays=(1,), wmax=1, vmax=2, bias=(0, 0), leak=(0, 0)), PAR1, T=6)
    assert r2.status == EXHAUSTED


def test_compose_dag_regression_silent_signal():
    """Regression: a candidate whose outputs on the examples equal the silent signal must still be checked."""
    r = compose_dag(load_with_stdlib(), CNT, T=8, max_size=2, timeout_s=60)
    assert r.status == SOLVED and r.detail["expr"] == "counter(k=3)[a, r]"
    reverify(r.network, CNT)


def test_sketch_learns_from_counterexamples():
    lib = load_with_stdlib()
    lib.merge(parse_library("network sk {\n inputs a, r\n inst c = counter(k=?{2,4,3}) in=a rst=?{_,r}\n output y = c.out\n}\n"))
    r = sketch(lib, lib.networks["sk"], CNT, T=8, timeout_s=60)
    assert r.status == SOLVED and r.detail["assignment"] == {"c.k": 3, "c<-rst": "r"}
    assert any(a["status"] in ("COUNTEREXAMPLE", "REJECTED_BY_EXAMPLES") for a in r.detail["attempts"])
    reverify(r.network, CNT)


@settings(max_examples=25, deadline=None)
@given(st.integers(min_value=0, max_value=10**9))
def test_classical_construction_is_correct_or_provably_impossible(seed):
    rng = random.Random(seed)
    phi = random_formula(rng, ["a", "b"], depth=2)
    sp = Spec("r", ("a", "b"), ("y",), TRUE, F("iff", (atom("y"), Prev(phi, rng.randint(1, 2)))))
    net, info = classical_network(sp)
    if net is not None:
        res = verify_all(net, sp, T=5)
        assert res[-1].status == Status.VERIFIED_UNBOUNDED
    else:
        assert info["status"] == "UNREALIZABLE"
        r = cegis(fully_connected(sp, 1), sp, T=6, timeout_s=30)
        assert r.status == UNREALIZABLE  # search agrees with the impossibility theorem
