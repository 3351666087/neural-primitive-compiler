"""Specification language: parser, three evaluators (batch, monitor, SMT) must agree."""

import random

import numpy as np
import pytest
import z3
from hypothesis import given, settings, strategies as st

from npc.gen import random_formula
from npc.smt import encode_formula
from npc.spec import Monitor, SpecError, evaluate, make_spec, parse, show


def ev1(text, **sig):
    T = len(next(iter(sig.values())))
    env = {k: np.array([v]) for k, v in sig.items()}
    return [int(b) for b in evaluate(parse(text), env)[0]]


def test_prev_strong_and_weak():
    assert ev1("prev(a)", a=[1, 0, 1]) == [0, 1, 0]
    assert ev1("wprev(a)", a=[1, 0, 1]) == [1, 1, 0]
    assert ev1("prev[2](a)", a=[1, 1, 0, 0]) == [0, 0, 1, 1]


def test_bounded_once_hist():
    assert ev1("once[1,2](a)", a=[1, 0, 0, 0, 1]) == [0, 1, 1, 0, 0]
    assert ev1("hist[0,1](a)", a=[1, 1, 0, 1, 1]) == [1, 1, 0, 0, 1]


def test_since_is_latch():
    #            set=s, reset=r : (!r) since (s & !r)
    s = [0, 1, 0, 0, 1, 1, 0]
    r = [0, 0, 0, 1, 0, 1, 0]
    assert ev1("since(!r, s & !r)", s=s, r=r) == [0, 1, 1, 0, 1, 0, 0]


def test_counting():
    assert ev1("count[3](a) >= 2", a=[1, 0, 1, 0, 0, 1]) == [0, 0, 1, 0, 0, 0]
    assert ev1("modcount[3](a) == 0", a=[1, 1, 1, 0, 1]) == [0, 0, 1, 1, 0]
    assert ev1("modcount[2](a; r) == 1", a=[1, 1, 1, 1], r=[0, 0, 1, 0]) == [1, 0, 0, 1]
    assert ev1("count[2](a) - count[2](b) >= 1", a=[1, 1, 0], b=[0, 1, 1]) == [1, 1, 0]


def test_parse_errors():
    for bad in ["prev(", "a &", "once[2,1](a)", "count[0](a) > 1", "atleast(a)", "a b"]:
        with pytest.raises(SpecError):
            parse(bad)


def test_spec_assumption_semantics():
    sp = make_spec("s", ["a"], ["y"], guarantee="y", assume="!a")
    # inclusive: violation at t only if assumption held at all t' <= t
    assert sp.first_violation({"a": [0, 1, 0], "y": [1, 0, 0]}) is None
    assert sp.first_violation({"a": [0, 0, 0], "y": [1, 0, 0]}) == 1
    sps = make_spec("s", ["a"], ["y"], guarantee="y", assume="!a", assume_mode="strict")
    # strict: assumption only needs to have held strictly before t
    assert sps.first_violation({"a": [0, 1, 0], "y": [1, 0, 0]}) == 1


seeds = st.integers(min_value=0, max_value=10**9)


@settings(max_examples=150, deadline=None)
@given(seeds)
def test_print_parse_round_trip(seed):
    rng = random.Random(seed)
    f = random_formula(rng, ["a", "b", "c"], depth=4)
    assert parse(show(f)) == f


@settings(max_examples=150, deadline=None)
@given(seeds)
def test_batch_and_monitor_agree(seed):
    rng = random.Random(seed)
    f = random_formula(rng, ["a", "b"], depth=4)
    T = rng.randint(1, 12)
    tr = {k: [rng.randint(0, 1) for _ in range(T)] for k in "ab"}
    batch = evaluate(f, {k: np.array([v]) for k, v in tr.items()})[0].tolist()
    mon = Monitor(f).run(tr, T)
    assert [bool(b) if isinstance(b, (bool, np.bool_)) else b for b in batch] == mon


@settings(max_examples=80, deadline=None)
@given(seeds)
def test_batch_and_smt_agree(seed):
    rng = random.Random(seed)
    f = random_formula(rng, ["a", "b"], depth=3)
    T = rng.randint(1, 8)
    tr = {k: [rng.randint(0, 1) for _ in range(T)] for k in "ab"}
    batch = evaluate(f, {k: np.array([v]) for k, v in tr.items()})[0].tolist()
    terms = encode_formula(f, {k: [bool(b) for b in v] for k, v in tr.items()}, T)
    smt = [z3.simplify(t) for t in terms]
    for b, s in zip(batch, smt):
        if z3.is_bool(s):
            assert z3.is_true(s) == bool(b)
        else:
            assert s.as_long() == b
