"""The fast metrics agree with scikit-learn on random data, including ties and bootstrap weights."""

import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from m08 import metrics as M  # noqa: E402


def test_auroc_auprc_match_sklearn_with_ties():
    rng = np.random.default_rng(0)
    for _ in range(20):
        y = (rng.random(500) < 0.1).astype(float)
        s = np.round(rng.random(500) + 0.5 * y, 1)          # many ties
        assert abs(M.auroc(s, y) - roc_auc_score(y, s)) < 1e-12
        assert abs(M.auprc(s, y) - average_precision_score(y, s)) < 1e-12


def test_weights_equal_repetition():
    rng = np.random.default_rng(1)
    y = (rng.random(200) < 0.2).astype(float)
    s = rng.random(200) + 0.3 * y
    w = rng.integers(0, 3, 200).astype(float)
    rep = np.repeat(np.arange(200), w.astype(int))
    assert abs(M.auroc(s, y, w) - roc_auc_score(y[rep], s[rep])) < 1e-12
    assert abs(M.auprc(s, y, w) - average_precision_score(y[rep], s[rep])) < 1e-12
