"""Phase 1: semantic invariants of the integer integrate-and-fire substrate."""

import itertools
import random

import numpy as np
import pytest
from hypothesis import given, settings, strategies as st

from npc.gen import random_network
from npc.network import Network, NetworkError, Neuron, Synapse, full_leak
from npc.simulator import BatchSim, CompiledNet, simulate


def relay(d: int) -> Network:
    return Network("relay", ("a",), (Neuron("n", threshold=1, leak=15),), (Synapse("a", "n", 1, d),),
                   (("y", "n"),), max_delay=8).validate()


def rand_inputs(rng, names, T):
    return {k: [rng.randint(0, 1) for _ in range(T)] for k in names}


# ---------------------------------------------------------------- well-formedness
@pytest.mark.parametrize("bad, msg", [
    (dict(synapses=(Synapse("a", "n", 1, 0),)), "zero delay"),
    (dict(synapses=(Synapse("zz", "n", 1, 1),)), "unknown source"),
    (dict(synapses=(Synapse("a", "a", 1, 1),)), "destination must be a neuron"),
    (dict(synapses=(Synapse("a", "n", 0, 1),)), "zero weight"),
    (dict(synapses=(Synapse("a", "n", 1, 9),)), "outside"),
    (dict(neurons=(Neuron("n", threshold=16),)), "threshold"),
    (dict(neurons=(Neuron("n", threshold=1, vmin=1),)), "vmin <= 0"),
    (dict(neurons=(Neuron("n", threshold=1, init=99),)), "init"),
    (dict(neurons=(Neuron("n", threshold=1), Neuron("n", threshold=1))), "duplicate"),
    (dict(outputs=(("y", "nope"),)), "unknown neuron"),
])
def test_validation_rejects(bad, msg):
    base = dict(name="x", inputs=("a",), neurons=(Neuron("n", threshold=1),),
                synapses=(Synapse("a", "n", 1, 1),), outputs=(("y", "n"),), max_delay=8)
    base.update(bad)
    with pytest.raises(NetworkError, match=msg):
        Network(**base).validate()


# ---------------------------------------------------------------- basic dynamics
@pytest.mark.parametrize("d", [1, 2, 5])
def test_relay_delays_exactly_d(d):
    rng = random.Random(d)
    x = [rng.randint(0, 1) for _ in range(20)]
    y = simulate(relay(d), {"a": x}).outputs["y"]
    assert y == [0] * d + x[: 20 - d]


def test_perfect_integrator_counts_modulo_threshold():
    net = Network("cnt", ("a",), (Neuron("c", threshold=3, leak=0, vmax=3),), (Synapse("a", "c", 1, 1),),
                  (("y", "c"),)).validate()
    x = [1, 0, 1, 1, 0, 0, 1, 1, 1, 0]
    y = simulate(net, {"a": x}).outputs["y"]
    # fires one step after every 3rd input spike
    assert y == [0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def test_linear_leak_forgets():
    net = Network("lk", ("a",), (Neuron("c", threshold=3, leak=1, vmax=7),), (Synapse("a", "c", 2, 1),),
                  (("y", "c"),)).validate()
    tr = simulate(net, {"a": [1, 0, 1, 1, 0, 0]})
    # charge 2 decays by 1 per step; two inputs one step apart reach threshold 3, two steps apart do not
    assert tr.potentials["c"] == [0, 2, 1, 2, 3, 0]
    assert tr.outputs["y"] == [0, 0, 0, 0, 1, 0]


def test_clipping_and_floor():
    net = Network("cl", ("a", "b"), (Neuron("c", threshold=3, leak=0, vmin=0, vmax=4),),
                  (Synapse("a", "c", 2, 1), Synapse("b", "c", -5, 1)), (("y", "c"),)).validate()
    tr = simulate(net, {"a": [1, 0, 0, 1, 1], "b": [0, 1, 0, 0, 0]})
    assert tr.potentials["c"] == [0, 2, 0, 0, 2]  # inhibition clamps at the floor, charge is lost
    assert all(0 <= v <= 4 for v in tr.potentials["c"])


def test_bias_drives_spontaneous_periodic_firing():
    net = Network("clk", (), (Neuron("c", threshold=3, leak=0, bias=1, vmax=3),), (), (("y", "c"),)).validate()
    assert simulate(net, {}, T=9).outputs["y"] == [0, 0, 1, 0, 0, 1, 0, 0, 1]


# -------------------------------------------------------------- property tests
seeds = st.integers(min_value=0, max_value=10**9)


@settings(max_examples=60, deadline=None)
@given(seeds)
def test_three_simulators_agree(seed):
    rng = random.Random(seed)
    m = rng.randint(1, 2)
    ins = tuple("ab"[:m])
    net = random_network(rng, rng.randint(1, 6), ins, n_outputs=1, max_delay=rng.randint(1, 4))
    T = rng.randint(1, 14)
    x = rand_inputs(rng, ins, T)
    ref = simulate(net, x)
    comp = CompiledNet(net).run(x)
    X = np.array([[x[k] for k in ins]])
    S = BatchSim(net).run(X)
    for j, nm in enumerate(net.neuron_names):
        assert ref.spikes[nm] == comp[nm]
        assert ref.spikes[nm] == list(S[0, m + j])


@settings(max_examples=60, deadline=None)
@given(seeds)
def test_determinism_and_order_independence(seed):
    rng = random.Random(seed)
    net = random_network(rng, rng.randint(2, 6), ("a", "b"))
    x = rand_inputs(rng, ("a", "b"), 12)
    a, b = simulate(net, x), simulate(net, x)
    assert a.spikes == b.spikes and a.potentials == b.potentials
    perm = list(range(len(net.neurons)))
    rng.shuffle(perm)
    c = simulate(net.permuted(perm), x)
    assert c.spikes == a.spikes


@settings(max_examples=60, deadline=None)
@given(seeds)
def test_potentials_stay_in_declared_range(seed):
    rng = random.Random(seed)
    net = random_network(rng, rng.randint(1, 6), ("a",), wmax=6)
    tr = simulate(net, rand_inputs(rng, ("a",), 15))
    for n in net.neurons:
        assert all(n.vmin <= v <= n.vmax for v in tr.potentials[n.name])


@settings(max_examples=60, deadline=None)
@given(seeds)
def test_strict_causality(seed):
    """Spikes at times <= t0 do not depend on inputs at times >= t0 (all delays >= 1)."""
    rng = random.Random(seed)
    net = random_network(rng, rng.randint(1, 6), ("a", "b"))
    T = 12
    x = rand_inputs(rng, ("a", "b"), T)
    t0 = rng.randint(0, T - 1)
    x2 = {k: v[:t0] + [rng.randint(0, 1) for _ in range(T - t0)] for k, v in x.items()}
    s1, s2 = simulate(net, x).spikes, simulate(net, x2).spikes
    for nm in net.neuron_names:
        assert s1[nm][: t0 + 1] == s2[nm][: t0 + 1]


@settings(max_examples=60, deadline=None)
@given(seeds)
def test_time_shift_invariance_from_rest(seed):
    """With zero bias and zero initial potential, prepending k silent steps delays everything by k."""
    rng = random.Random(seed)
    net = random_network(rng, rng.randint(1, 6), ("a",), rest=True)
    x = rand_inputs(rng, ("a",), 10)
    k = rng.randint(1, 4)
    y1 = simulate(net, x).spikes
    y2 = simulate(net, {"a": [0] * k + x["a"]}).spikes
    for nm in net.neuron_names:
        assert y2[nm] == [0] * k + y1[nm]


def test_state_space_is_finite_and_bounded():
    rng = random.Random(7)
    net = random_network(rng, 3, ("a",), max_delay=2)
    cn = CompiledNet(net)
    seen = set()
    frontier = [cn.initial_state()]
    while frontier:
        s = frontier.pop()
        if s in seen:
            continue
        seen.add(s)
        sp, p = cn.fire(s)
        for x in (0, 1):
            frontier.append(cn.advance(s, sp, p, (x,)))
    bound = 1
    for n in net.neurons:
        bound *= n.vmax - n.vmin + 1
    bound *= 2 ** sum(net.history_depth().values())
    assert len(seen) <= bound


def test_json_round_trip():
    rng = random.Random(3)
    net = random_network(rng, 4, ("a", "b"))
    again = Network.from_json(net.to_json())
    assert again == net
    x = rand_inputs(rng, ("a", "b"), 10)
    assert simulate(again, x).spikes == simulate(net, x).spikes


def test_memoryless_flag():
    assert Neuron("n", threshold=1, leak=full_leak(0, 15)).memoryless
    assert not Neuron("n", threshold=1, leak=0).memoryless
