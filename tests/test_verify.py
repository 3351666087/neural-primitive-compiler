"""Phase 3 verifier: engines agree, counterexamples are real, bounded != unbounded."""

import random

import pytest
import z3
from hypothesis import given, settings, strategies as st

from npc.compose import compositional_symbolic
from npc.dsl import InstDecl, NetworkDef, flatten, load_with_stdlib
from npc.gen import random_formula, random_network
from npc.network import Network, Neuron, Synapse
from npc.smt import unroll, violation_terms
from npc.spec import F, Prev, Spec, atom, make_spec
from npc.verify import (Status, SymNetSystem, SymProduct, bmc, check_consistency, exhaustive, kinduction, pdr,
                        reach, replay, verify_all)


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


def random_problem(seed):
    rng = random.Random(seed)
    m = rng.randint(1, 2)
    ins = tuple("ab"[:m])
    net = random_network(rng, rng.randint(1, 4), ins, max_delay=rng.randint(1, 3))
    phi = random_formula(rng, list(ins), depth=2)
    form = rng.choice(["iff", "imp", "plain"])
    if form == "iff":
        g = F("iff", (atom("y"), Prev(phi)))
    elif form == "imp":
        g = F("implies", (atom("y"), phi))
    else:
        g = random_formula(rng, list(ins) + ["y"], depth=2)
    assume = random_formula(rng, list(ins), depth=1) if rng.random() < 0.3 else F("const", (), (True,))
    sp = Spec("rand", ins, ("y",), assume, g, warmup=rng.randint(0, 2),
              assume_mode=rng.choice(["inclusive", "strict"]))
    return net, sp, rng.randint(1, 6)


@settings(max_examples=60, deadline=None)
@given(seeds)
def test_engines_agree_on_random_problems(seed):
    net, sp, T = random_problem(seed)
    verify_all(net, sp, T=T, max_states=200_000)  # raises EngineBug on any disagreement


# ------------------------------------------------------- symbolic unbounded engines (kind, pdr)
def _check_symbolic(net, sp, results):
    """Shared honesty checks: replayable counterexamples, checked PDR certificates, no contradictions
    with reach (check_consistency also demands the same earliest violation time)."""
    check_consistency(results)
    for r in results:
        assert r.status in (Status.VERIFIED_UNBOUNDED, Status.COUNTEREXAMPLE, Status.UNKNOWN, Status.TIMEOUT,
                            Status.RESOURCE_LIMIT)
        assert r.horizon is None
        if r.status == Status.COUNTEREXAMPLE:
            assert replay(net, sp, r.counterexample) == r.violation_time
        if r.status == Status.VERIFIED_UNBOUNDED and "pdr" in r.engine:
            assert r.stats["certificate"] == "checked"


@settings(max_examples=60, deadline=None)
@given(seeds)
def test_symbolic_engines_never_contradict_reach_on_random_problems(seed):
    net, sp, _ = random_problem(seed)
    r = reach(net, sp, max_states=200_000)
    _check_symbolic(net, sp, [r, kinduction(net, sp, k_max=60, timeout_s=20), pdr(net, sp, timeout_s=10)])


@settings(max_examples=40, deadline=None)
@given(seeds)
def test_symbolic_product_matches_smt_unroll(seed):
    """The state-based encoding used by kind/pdr, unrolled from the initial state, gives the same outputs
    and the same violation condition as smt.unroll + violation_terms (the BMC encoding), for every input."""
    net, sp, T = random_problem(seed)
    P = SymProduct(SymNetSystem(net), sp)
    x = {k: [z3.Bool(f"x_{k}_{t}") for t in range(T)] for k in net.inputs}
    cons = []
    spikes = unroll(net, T, x, cons, prefix="v_")
    env = dict(x)
    env.update({p: spikes[n] for p, n in net.outputs})
    ref = dict(violation_terms(sp, env, T))
    s, held, diffs = P.init_values(), z3.BoolVal(True), []
    for t in range(T):
        st = P.step(s, {k: x[k][t] for k in net.inputs})
        sig, _ = P.system.fire(s[:len(P.system.components)])
        diffs.append(z3.And(held, st.bad) != ref.get(t, z3.BoolVal(False)))
        diffs += [sig[p] != spikes[n][t] for p, n in net.outputs]
        held = z3.And(held, st.aok)
        s = st.nxt
    solver = z3.Solver()
    solver.add(*cons)
    solver.add(z3.Or(*diffs))
    assert solver.check() == z3.unsat


CHAIN_LIB = load_with_stdlib()
CHAINS = {  # the Q3 scaling families (experiments/run_experiments.py: scaling, scaling_symbolic)
    "relay": ({"d": 1}, ["in"], lambda N: f"y <-> prev[{N}](a)"),
    "counter": ({"k": 2}, ["in", "rst"], lambda N: f"y <-> prev[{N}](a & modcount[{2 ** N}](a) == 0)"),
    "window": ({"k": 2, "w": 2}, ["in"], lambda N: f"y -> once[1,{2 * N}](a)"),
}
WRONG = {  # specs the chains do not meet
    "relay": lambda N: f"y <-> prev[{N + 1}](a)",
    "counter": lambda N: f"y <-> prev[{N}](a & modcount[{2 ** N}](a) == 1)",
    "window": lambda N: "!y",
}


def chain_def(fam, N):
    args, ports, _ = CHAINS[fam]
    nd = NetworkDef(f"chain_{fam}_{N}", max_delay=4, inputs=["a"])
    prev = "a"
    for j in range(N):
        b = {p: "_" for p in ports}
        b[ports[0]] = prev
        nd.instances.append(InstDecl(f"i{j}", fam, dict(args), b))
        prev = f"i{j}.out"
    nd.outputs.append(("y", prev))
    return nd


@pytest.mark.parametrize("fam,N", [("relay", 1), ("relay", 2), ("relay", 4), ("window", 1), ("window", 2),
                                   ("window", 4), ("counter", 1), ("counter", 2)])
def test_symbolic_engines_on_chain_families(fam, N):
    nd = chain_def(fam, N)
    net = flatten(CHAIN_LIB, nd).network
    for g in (CHAINS[fam][2](N), WRONG[fam](N), "!y"):
        sp = make_spec(f"{fam}{N}", ["a"], ["y"], g)
        r = reach(net, sp)
        res = [r, kinduction(net, sp, k_max=100, timeout_s=60), pdr(net, sp, timeout_s=60)]
        res += [compositional_symbolic(CHAIN_LIB, nd, sp, engine=e, timeout_s=60).result for e in ("kind", "pdr")]
        _check_symbolic(net, sp, res)
        assert all(x.status == r.status for x in res), [(x.engine, x.status) for x in res]  # small N: all decide


def test_symbolic_inconclusive_is_not_a_proof():
    """counter chain N=3 needs k = 22: stopping earlier must say UNKNOWN / TIMEOUT, never VERIFIED."""
    net = flatten(CHAIN_LIB, chain_def("counter", 3)).network
    sp = make_spec("c3", ["a"], ["y"], CHAINS["counter"][2](3))
    k = kinduction(net, sp, k_max=3)
    assert k.status == Status.UNKNOWN and not k.verified
    assert k.stats["bounded_safe_upto"] == 3 and "k_max" in k.stats["reason"]
    assert "every length" in k.scope  # scope names what a proof *would* cover; the status says there is none
    for r in (kinduction(net, sp, timeout_s=0.01), pdr(net, sp, timeout_s=0.01)):
        assert r.status in (Status.TIMEOUT, Status.UNKNOWN) and not r.verified


def test_symbolic_engines_find_late_violation():
    """The 5-counter that BMC(5) passes: both symbolic engines refute it at t = 5 with a replayable trace."""
    sp = make_spec("never", ["a"], ["y"], "!y")
    for r in (kinduction(counter(5), sp), pdr(counter(5), sp)):
        assert r.status == Status.COUNTEREXAMPLE and r.violation_time == 5
        assert replay(counter(5), sp, r.counterexample) == 5


def test_pdr_zero_arity_invariant_regression():
    """Seed 2963 gives a product with no state components; Spacer's invariant is then a plain Bool
    (no function table). The certificate check must handle it instead of crashing."""
    net, sp, _ = random_problem(2963)
    r = reach(net, sp, max_states=200_000)
    _check_symbolic(net, sp, [r, kinduction(net, sp, k_max=60, timeout_s=20), pdr(net, sp, timeout_s=10)])
