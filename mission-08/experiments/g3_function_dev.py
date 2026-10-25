"""Gate 3, worm function line, development columns only. Interface checks (funatlas.h5 against the Source Data of
Fig. 2; orientation; the hash split) and the positive / negative controls of PRE_REGISTRATION.md section 3 on an
inner split of the development columns (half of the development classes fit g and the calibration, the other half
score): A-real must beat A-er and A-none (F-a), and A-rewire must lose to A-real (F-b). Held-out columns are not read.
  python3 -I experiments/g3_function_dev.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from m08 import celegans as C  # noqa: E402
from m08 import function as F, ledger, metrics as M, models as Mo, randi  # noqa: E402
from m08.raw import path  # noqa: E402


def source_data_check(cells, d):
    """Compare funatlas WT dFF with the Source Data Fig. 2a matrix on development columns (same orientation?)."""
    wb = openpyxl.load_workbook(path("randi_fig2"), read_only=True)
    ws = wb["Figure2a, df_over_f"]
    rows = list(ws.iter_rows(values_only=True))
    header = [str(x) for x in rows[0][1:]]
    rnames = [str(r[0]) for r in rows[1:]]
    S = np.array([[np.nan if v is None else float(v) for v in r[1:]] for r in rows[1:]])
    ix = {c: i for i, c in enumerate(cells)}
    agree, agree_t, n = 0, 0, 0
    for a, ra in enumerate(rnames):
        for b, cb in enumerate(header):
            if ra in ix and cb in ix and not np.isnan(S[a, b]):
                i, j = ix[ra], ix[cb]
                if d["heldout_columns"][j] or d["heldout_columns"][i]:
                    continue
                n += 1
                agree += np.isfinite(d["dFF"][i, j]) and abs(d["dFF"][i, j] - S[a, b]) < 1e-6
                agree_t += np.isfinite(d["dFF"][j, i]) and abs(d["dFF"][j, i] - S[a, b]) < 1e-6
    return {"compared": n, "same_orientation": int(agree), "transposed": int(agree_t)}


def inner_split(cells, dev_cols):
    """Half of the development classes for fitting, half for scoring (fixed hash, salt 'm08-randi-inner-v1:')."""
    cls = C.lr_class(cells)
    a = np.array([int(hashlib.sha256(("m08-randi-inner-v1:" + c).encode()).hexdigest()[-1], 16) % 2 == 0 for c in cls])
    return dev_cols & a, dev_cols & ~a


def main():
    run = ledger.Run("g3", "function_dev")
    w7, w8 = C.witvliet(7), C.witvliet(8)
    ref = sorted(C.cells_of(w7) & C.cells_of(w8))
    cells = randi.usable_cells(ref)
    ctx = Mo.make_ctx(cells)
    c7, c8 = C.conn(cells, k=7), C.conn(cells, k=8)
    res = {"n_ref": len(ref), "n_usable": len(cells)}
    out = {}
    for strain in ("wt", "unc31"):
        d = randi.dev(strain, cells)
        dev_cols = ~d["heldout_columns"]
        if strain == "wt":
            res["source_data_check"] = source_data_check(cells, d)
            res["split"] = {"dev_classes": int(len(set(C.lr_class(cells)[dev_cols]))),
                            "heldout_classes": int(len(set(C.lr_class(cells)[~dev_cols]))),
                            "dev_cells": int(dev_cols.sum()), "heldout_cells": int((~dev_cols).sum())}
        fit_cols, score_cols = inner_split(cells, dev_cols)
        fit_pairs, score_pairs = randi.labels(d, fit_cols), randi.labels(d, score_cols)
        A_real = 0.5 * (c7.A + c8.A)
        rng = np.random.default_rng(0)
        dens = (A_real > 0).mean()
        conds = {"A-real": A_real, "A-er": (rng.random(A_real.shape) < dens).astype(float)}
        rows = {}
        for name, A in conds.items():
            f = F.fit_condition(A, fit_pairs)
            p = F.predict(A, f, score_pairs)
            rows[name] = {"g": f["g"], "auprc": M.auprc(p, score_pairs[2]), "auroc": M.auroc(p, score_pairs[2])}
        rw = []
        for s in range(20):
            A = F.rewire(A_real > 0, np.random.default_rng(s))
            f = F.fit_condition(A, fit_pairs)
            p = F.predict(A, f, score_pairs)
            rw.append(M.auprc(p, score_pairs[2]))
        rows["A-rewire"] = {"auprc_mean": float(np.mean(rw)), "auprc_min": float(np.min(rw)), "auprc_max": float(np.max(rw))}
        # A-none: independent features only, logistic fit on the fitting pairs
        X = Mo.feature_matrix(ctx, 50.0)
        pair_index = {(i, j): k for k, (i, j) in enumerate(zip(ctx.I, ctx.J))}
        def fx(pairs):
            I, J, _ = pairs
            return X[[pair_index[(j, i)] for i, j in zip(I, J)]]      # structure-free features of the pair j -> i
        from sklearn.linear_model import LogisticRegression
        mu, sd = fx(fit_pairs).mean(0), fx(fit_pairs).std(0) + 1e-9
        lr = LogisticRegression(C=1.0, max_iter=5000).fit((fx(fit_pairs) - mu) / sd, fit_pairs[2])
        p = lr.predict_proba((fx(score_pairs) - mu) / sd)[:, 1]
        rows["A-none"] = {"auprc": M.auprc(p, score_pairs[2]), "auroc": M.auroc(p, score_pairs[2])}
        rows["n_fit_pairs"] = int(len(fit_pairs[2]))
        rows["n_score_pairs"] = int(len(score_pairs[2]))
        rows["pos_rate_score"] = float(score_pairs[2].mean())
        out[strain] = rows
    res["inner_split_controls"] = out
    print(run.write(res))


if __name__ == "__main__":
    main()
