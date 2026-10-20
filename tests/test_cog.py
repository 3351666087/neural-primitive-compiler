"""Mission 02 (cog): judges, primitives, learning, proofs, and the separation between spec and construction."""

import random
import re
from pathlib import Path

import pytest

from cog.check import RefStepper, differential, reach_equiv
from cog.ir import IRError, compile_ir
from cog.learn import active_refine, learn, recheck, to_ir
from cog.proofs import all_proofs
from cog.realize import latency1_exact
from cog.tasks import Letter, family_a, family_ab, family_b, random_trace, run_reference, valid
from npc.fsm import latency1_weights, machine_from_spec, minimize
from npc.gen import random_formula
from npc.spec import F, Prev, Spec, TRUE, atom

SRC = Path(__file__).resolve().parents[1] / "src" / "cog"


def test_constructors_never_import_the_spec():
    """The reference semantics (cog.tasks) is the specification; construction code must not read it."""
    for mod in ("prims.py", "ir.py", "learn.py"):
        text = (SRC / mod).read_text()
        assert not re.search(r"from \.tasks|cog\.tasks|import tasks", text), mod


def test_ir_has_no_escape_hatch():
    t = family_a(2, ["ROT90"])
    for bad in ({"id": "m", "op": "PYTHON", "code": "print(1)"},
                {"id": "m", "op": "CMR", "letters": {"ROT90": {"map": ["eval", "1+1"]}}}):
        with pytest.raises(IRError):
            compile_ir({"name": "x", "nodes": [bad], "outputs": {}}, t.interface())


def tasks_small():
    a = family_a(3, ["ROT90", "RIGHT", "DILATE"], queries=["top", "cell"], cond=("COND", "left", "FLIPV", "ROT90", 3))
    b = family_b(3, 2, ["STORE", "SWAP", "COPY", "CLEAR"], queries=["value", "who", "same"])
    ab = family_ab(2, 3, ["ROT90", "LEFT"], queries=["toptouch", "occupant"])
    return [a, b, ab]


@pytest.mark.parametrize("task", tasks_small(), ids=lambda t: t.name)
def test_incremental_reference_matches_reference(task):
    rng = random.Random(3)
    ref = RefStepper(task)
    for _ in range(40):
        T = 14
        tr = random_trace(task, T, rng)
        assert valid(task, tr, T)
        full = run_reference(task, tr, T)
        st = ref.init()
        for t in range(T):
            st = ref.step(st, {k: v[t] for k, v in tr.items()})
            out = ref.outputs(st)
            for ch, col in full.items():
                assert out[ch] == col[t], (ch, t)


def a_prog(cmds):
    m = {"ROT90": ["rot90"], "FLIPH": ["fliph"], "FLIPV": ["flipv"], "RIGHT": ["shift", 1, 0, "clip"], "DILATE": ["dilate"]}
    return {"name": "a", "nodes": [{"id": "mem", "op": "CMR", "letters": dict(
        {"LOAD": {"map": ["load", "see"]}}, **{c: {"map": m[c]} for c in cmds})},
        {"id": "any_top", "op": "ANY", "of": "mem", "where": {"row": 0}},
        {"id": "cellon", "op": "SEL", "of": "mem", "select": "qcell", "axis": "all", "delay": 2}],
        "outputs": {"img": "mem", "any_top": "any_top", "cellon": "cellon"}}


@pytest.mark.parametrize("N", [2, 3, 5])
def test_hand_construction_passes_differential(N):
    t = family_a(N, ["ROT90", "FLIPH", "RIGHT", "DILATE"], queries=["top", "cell"])
    assert differential(compile_ir(a_prog(["ROT90", "FLIPH", "RIGHT", "DILATE"]), t.interface()), t, n=120, T=12).ok


def test_wrong_map_is_caught_with_counterexample():
    t = family_a(3, ["ROT90"], queries=["top", "cell"])
    p = a_prog(["ROT90"])
    p["nodes"][0]["letters"]["ROT90"] = {"map": ["rot270"]}
    r = differential(compile_ir(p, t.interface()), t, n=120, T=10)
    assert r.ok is False and r.counterexample is not None


def test_unbounded_equivalence_small():
    t = family_a(2, ["ROT90", "RIGHT"])
    p = {"name": "a", "nodes": [{"id": "mem", "op": "CMR", "letters": {"LOAD": {"map": ["load", "see"]}, "ROT90": {"map": ["rot90"]},
                                                                    "RIGHT": {"map": ["shift", 1, 0, "clip"]}}}],
         "outputs": {"img": "mem"}}
    r = reach_equiv(compile_ir(p, t.interface()), t, max_states=500_000)
    assert r.ok is True


def test_active_learning_constructs_correct_networks_and_rejects_non_union():
    t = family_a(3, ["ROT90", "DILATE"], queries=["top", "cell"])
    orc = lambda tr, T: run_reference(t, tr, T)
    L = active_refine(t.interface(), orc, learn(t.interface(), orc, n_traces=150, T=14, seed=1))
    assert recheck(t.interface(), orc, L) == []
    assert differential(compile_ir(to_ir(t.interface(), L), t.interface()), t, n=150, T=12).ok
    inv = family_a(3, ["ROT90"])
    allc = frozenset(inv.space.coords)
    inv.letters.append(Letter("INVERT", lambda S, f: allc - S))
    Li = learn(inv.interface(), lambda tr, T: run_reference(inv, tr, T), n_traces=150, T=14, seed=1)
    assert Li.letters["INVERT"] == "nonlinear"


def test_parametric_proofs():
    for name, status, _, _ in all_proofs():
        expected = "COUNTEREXAMPLE" if "expected COUNTEREXAMPLE" in name else ("SAT" if "non-vacuity" in name else "PROVED")
        assert status == expected, name


def test_exact_latency1_agrees_with_bounded_for_small_m():
    for seed in range(30):
        rng = random.Random(seed)
        names = ["a", "b", "c"][: 1 + seed % 3]
        phi = random_formula(rng, names, depth=2)
        sp = Spec("r", tuple(names), ("y",), TRUE, F("iff", (atom("y"), Prev(phi))))
        M = minimize(machine_from_spec(sp))
        assert latency1_exact(M).realizable == latency1_weights(M, 64).realizable


def test_auto_route_extrapolates_without_oracle_calls_at_new_sizes():
    from cog.auto import construct_auto
    tasks = [family_b(K, V, ["STORE", "SWAP", "CLEAR"], queries=["value"]) for K, V in ((2, 2), (3, 3), (4, 4))]
    r = construct_auto([t.interface() for t in tasks[:2]], [lambda tr, T, t=t: run_reference(t, tr, T) for t in tasks[:2]],
                       n_traces=150, T=14)
    assert r.status == "BUILT" and ("STORE", 1) in r.rules.letters_family
    big = tasks[-1]
    assert differential(compile_ir(r.rules.instantiate(big.interface()), big.interface()), big, n=100, T=12).ok


def test_auto_route_refuses_conditional_and_match():
    from cog.auto import construct_auto
    for make in (lambda N: family_a(N, ["ROT90"], cond=("COND", "top", "FLIPV", "ROT90", 3)),):
        tasks = [make(2), make(3)]
        r = construct_auto([t.interface() for t in tasks], [lambda tr, T, t=t: run_reference(t, tr, T) for t in tasks],
                           n_traces=100, T=14)
        assert r.status == "FAIL" and "conditional" in r.reason
