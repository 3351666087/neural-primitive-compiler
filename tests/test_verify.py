"""Phase 3 verifier: engines agree, counterexamples are real, bounded != unbounded."""

import random

import pytest
from hypothesis import given, settings, strategies as st

from npc.gen import random_formula, random_network
from npc.network import Network, Neuron, Synapse
from npc.spec import Spec, make_spec
from npc.verify import Status, bmc, exhaustive, reach, replay, verify_all


def relay(d):
    return Network("relay", ("a",), (Neuron("n", threshold=1, leak=15),), (Synapse("a", "n", 1, d),),
                   (("y", "n"),)).validate()


def counter(k):
    return Network("cnt", ("a",), (Neuron("c", threshold=k, leak=0, vmax=k),), (Synapse("a", "c", 1, 1),),
                   (("y", "c"),)).validate()


def test_correct_relay_verified_by_all_engines():
    sp = make_spec("r2", ["a"], ["y"], "y <-> prev[2](a)")
    res = verify_all(relay(2), sp, T=8)
    assert [r.status for r in res] == [Status.VERIFIED_BOUNDED, Status.VERIFIED_BOUNDED, Status.VERIFIED_UNBOUNDED]


def test_wrong_spec_gives_replayable_counterexamples():
    sp = make_spec("r1", ["a"], ["y"], "y <-> prev(a)")
    for r in verify_all(relay(2), sp, T=6):
        assert r.status == Status.COUNTEREXAMPLE
        assert replay(relay(2), sp, r.counterexample) == r.violation_time


def test_bounded_verification_is_not_unbounded():
    """A 5-counter never fires within 5 steps, but does fire later."""
    sp = make_spec("never", ["a"], ["y"], "!y")
    b = bmc(counter(5), sp, T=5)
    e = exhaustive(counter(5), sp, T=5)
    u = reach(counter(5), sp)
    assert b.status == Status.VERIFIED_BOUNDED and e.status == Status.VERIFIED_BOUNDED
    assert u.status == Status.COUNTEREXAMPLE and u.violation_time == 5
    assert "says nothing about later steps" in b.scope


def test_resource_limits_are_reported_not_hidden():
    sp = make_spec("never", ["a"], ["y"], "!y")
    assert reach(counter(5), sp, max_states=3).status == Status.RESOURCE_LIMIT
    assert exhaustive(counter(5), sp, T=30, max_traces=1000).status == Status.RESOURCE_LIMIT


def test_bmc_timeout_is_not_a_proof():
    rng = random.Random(11)
    net = random_network(rng, 10, ("a", "b"), max_delay=4, p_syn=0.6)
    sp = make_spec("hard", ["a", "b"], ["y"], "y <-> prev(modcount[3](a; b) == 1)")
    r = bmc(net, sp, T=40, timeout_s=0.001)
    assert r.status in (Status.TIMEOUT, Status.UNKNOWN, Status.COUNTEREXAMPLE, Status.VERIFIED_BOUNDED)
    if r.status in (Status.TIMEOUT, Status.UNKNOWN):
        assert not r.verified


def test_assumption_restricts_domain():
    # A gate that is only correct if a and b never fire together.
    net = Network("g", ("a", "b"), (Neuron("n", threshold=1, leak=15),),
                  (Synapse("a", "n", 1, 1), Synapse("b", "n", 1, 1)), (("y", "n"),)).validate()
    sp_bad = make_spec("xor", ["a", "b"], ["y"], "y <-> prev(a ^ b)")
    sp_ok = make_spec("xor_assumed", ["a", "b"], ["y"], "y <-> prev(a ^ b)", assume="!(a & b)")
    assert reach(net, sp_bad).status == Status.COUNTEREXAMPLE
    for r in verify_all(net, sp_ok, T=6):
        assert r.verified


seeds = st.integers(min_value=0, max_value=10**9)


@settings(max_examples=60, deadline=None)
@given(seeds)
def test_engines_agree_on_random_problems(seed):
    rng = random.Random(seed)
    m = rng.randint(1, 2)
    ins = tuple("ab"[:m])
    net = random_network(rng, rng.randint(1, 4), ins, max_delay=rng.randint(1, 3))
    phi = random_formula(rng, list(ins), depth=2)
    form = rng.choice(["iff", "imp", "plain"])
    from npc.spec import F, atom, Prev
    if form == "iff":
        g = F("iff", (atom("y"), Prev(phi)))
    elif form == "imp":
        g = F("implies", (atom("y"), phi))
    else:
        g = random_formula(rng, list(ins) + ["y"], depth=2)
    assume = random_formula(rng, list(ins), depth=1) if rng.random() < 0.3 else F("const", (), (True,))
    sp = Spec("rand", ins, ("y",), assume, g, warmup=rng.randint(0, 2),
              assume_mode=rng.choice(["inclusive", "strict"]))
    T = rng.randint(1, 6)
    verify_all(net, sp, T=T, max_states=200_000)  # raises EngineBug on any disagreement
