"""Data-interface positive control: the two Witvliet adults reproduce the counts that Richter & Schneidman (PNAS 2025,
section "The Generative Model Reveals the Shared Backbone") report for the nerve ring: 180 neurons, 1,933 connected
ordered pairs in one adult, 1,279 shared by both."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from m08 import celegans as C  # noqa: E402
from m08 import custody  # noqa: E402


def adults():
    a, b = C.witvliet(7), C.witvliet(8)
    cells = sorted(C.cells_of(a) & C.cells_of(b))
    return cells, C.matrix(a, cells) > 0, C.matrix(b, cells) > 0


def test_adult_counts_match_published():
    cells, A, B = adults()
    assert len(cells) == 180
    assert int(B.sum()) == 1933
    assert int((A & B).sum()) == 1279


def test_no_autapses_and_neurons_only():
    a = C.witvliet(8)
    assert (a.pre != a.post).all()
    names = C.neuron_names()
    assert a.pre.isin(names).all() and a.post.isin(names).all()
    assert not any(c.startswith(("BWM", "CEPsh", "GLR")) for c in C.cells_of(a))


def test_heldout_refused(monkeypatch):
    monkeypatch.setattr(custody, "HELDOUT", {"witvliet_8"})
    monkeypatch.delenv("M08_JUDGE", raising=False)
    with pytest.raises(custody.CustodyError):
        C.witvliet(8)


def test_registered_heldout_refused_without_freeze(monkeypatch):
    monkeypatch.setenv("M08_JUDGE", "1")              # judge flag alone is not enough before the freeze
    monkeypatch.setattr(custody, "FREEZE", Path("/nonexistent/FREEZE_MANIFEST.sha256"))
    for k in (2, 4):
        with pytest.raises(custody.CustodyError):
            C.witvliet(k)
    from m08.raw import path
    for key in ("nema_white_jsh", "nema_white_n2u"):
        with pytest.raises(custody.CustodyError):
            path(key)


def test_matrix_drops_diagonal():
    cells, A, _ = adults()
    assert not np.diag(A).any()
