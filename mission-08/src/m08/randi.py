"""Randi et al. 2023 signal-propagation atlas (wormneuroatlas funatlas.h5). Matrices are indexed [i, j] = response of
neuron i to stimulation of neuron j (the reader's convention: "pair i <- j"). Stimulated columns are split into
development and held-out classes by the hash rule of DATA_SPLITS_AND_CUSTODY.md section 2; held-out columns are
returned only to the judge after the freeze (custody key "randi_heldout").
"""

from __future__ import annotations

import hashlib

import h5py
import numpy as np

from . import celegans as C
from . import custody
from .raw import path

FIELDS = ("q", "q_eq", "dFF", "occ1")


def ids():
    with h5py.File(path("funatlas"), "r") as f:
        return [x.decode() for x in f["neuron_ids"][:]]


def heldout_class(c):
    return int(hashlib.sha256((custody.RANDI_SALT + c).encode()).hexdigest()[-1], 16) % 2 == 1


def column_split(cells):
    """Boolean array over `cells`: True for held-out stimulated classes."""
    return np.array([heldout_class(c) for c in C.lr_class(cells)])


def _load(strain, cells):
    names = ids()
    ix = {n: i for i, n in enumerate(names)}
    sel = np.array([ix[c] for c in cells])
    out = {}
    with h5py.File(path("funatlas"), "r") as f:
        for k in FIELDS:
            out[k] = np.asarray(f[strain][k][:], dtype=float)[np.ix_(sel, sel)]
    return out


def usable_cells(ref_cells):
    names = set(ids())
    return [c for c in ref_cells if c in names]


def dev(strain, cells):
    """Development view: held-out stimulated columns are set to NaN (q, q_eq, dFF) and 0 (occ1)."""
    d = _load(strain, cells)
    held = column_split(cells)
    for k in ("q", "q_eq", "dFF"):
        d[k][:, held] = np.nan
    d["occ1"][:, held] = 0
    d["heldout_columns"] = held
    return d


def judge(strain, cells):
    custody.allow("randi_heldout")
    d = _load(strain, cells)
    d["heldout_columns"] = column_split(cells)
    return d


def labels(d, columns):
    """Pairs (i, j), j in `columns`, i != j, measured: y = 1 if q < 0.05, 0 if q_eq < 0.05, else excluded."""
    n = d["q"].shape[0]
    I, J = np.where(~np.eye(n, dtype=bool))
    keep = columns[J] & (d["occ1"][I, J] > 0)
    pos = keep & (d["q"][I, J] < 0.05)
    neg = keep & ~pos & (d["q_eq"][I, J] < 0.05)
    m = pos | neg
    return I[m], J[m], pos[m].astype(float)
