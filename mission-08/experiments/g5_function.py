"""Gate 5 judge, worm function line (PRE_REGISTRATION.md section 3, amendment A1.5). Runs once after the freeze with
M08_JUDGE=1: g and the calibration of every structure condition are fitted on all development columns; AUPRC and
AUROC are scored on the held-out stimulated classes, with a bootstrap over held-out classes. F-a to F-e as registered;
if F-a or F-b fails, F-c / F-d are reported as "dependency unmet". R1 uses the gamma selected at Gate 4
(results/g4/selection.json). Secondary analyses of amendment A4.3 (gap junctions added to every structure, one-step
and one-plus-two-step scores, split-half reliability reference) are reported and do not enter the verdict. Writes
results/g5/function.json.
  M08_JUDGE=1 python3 -I experiments/g5_function.py [--grid 10] [--boot 2000] [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from m08 import celegans as C  # noqa: E402
from m08 import function as F, ledger, metrics as M, models as Mo, randi  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GAMMA = float(json.loads((ROOT / "results" / "g4" / "selection.json").read_text())["results"]["chosen"]["R1_gamma"])


def class_boot(score_a, score_b, y, cls, fun, n_boot, seed=20261025):
    """Point difference and 95 % interval of fun(a) - fun(b), resampling stimulated classes."""
    rng = np.random.default_rng(seed)
    u, inv = np.unique(cls, return_inverse=True)
    point = fun(score_a, y, None) - fun(score_b, y, None)
    ds = []
    for _ in range(n_boot):
        w = np.bincount(rng.integers(0, len(u), len(u)), minlength=len(u))[inv].astype(float)
        ds.append(fun(score_a, y, w) - fun(score_b, y, w))
    lo, hi = np.nanpercentile(ds, [2.5, 97.5])
    return {"diff": float(point), "lo": float(lo), "hi": float(hi)}


def ap(s, y, w):
    return M.auprc(s, y, w)


def gap_junctions(cells, ks=(7, 8)):
    """Symmetric binary electrical-synapse matrices of the training animals, averaged."""
    out = []
    for k in ks:
        G = C.matrix(C.witvliet(k, kind="electrical"), cells)
        out.append(((G + G.T) > 0).astype(float))
    return sum(out) / len(out)


def steps_scores(A, fit_pairs, sc_pairs, two):
    """Section 3.1 secondary: score = A_hat[j, i] (one step) or (A_hat + A_hat^2)[j, i], logistic calibration on the
    development pairs."""
    from sklearn.linear_model import LogisticRegression as LR
    A = np.asarray(A, dtype=float).copy()
    np.fill_diagonal(A, 0)
    Ah = A / np.max(np.abs(np.linalg.eigvals(A)))
    S = Ah + Ah @ Ah if two else Ah
    x = lambda pr: np.log(np.maximum(S[pr[1], pr[0]], 0) + 1e-6)[:, None]       # noqa: E731
    lr = LR(C=1e3, max_iter=2000).fit(x(fit_pairs), fit_pairs[2])
    return lr.predict_proba(x(sc_pairs))[:, 1]


def main():
    ap_ = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap_.add_argument("--grid", type=int, default=10)
    ap_.add_argument("--boot", type=int, default=2000)
    ap_.add_argument("--dry-run", action="store_true", help="score an inner split of development columns instead")
    a = ap_.parse_args()
    run = ledger.Run("g4" if a.dry_run else "g5", "function_dryrun" if a.dry_run else "function", boot=a.boot)
    w7, w8 = C.witvliet(7), C.witvliet(8)
    ref = sorted(C.cells_of(w7) & C.cells_of(w8))
    cells = randi.usable_cells(ref)
    ctx = Mo.make_ctx(cells)
    c7, c8 = C.conn(cells, k=7), C.conn(cells, k=8)
    A_real = 0.5 * (c7.A + c8.A)
    g = np.linspace(0, 0.05, a.grid + 1)[:-1]
    r1 = Mo.RS(types=ctx.cook, beta0_grid=g, sminus_grid=g, iters=20, gamma=GAMMA).fit(ctx, [c7, c8])
    P_rule = np.zeros_like(A_real)
    P_rule[ctx.I, ctx.J] = r1.p
    sbm = Mo.Block(ctx.cook, "B2").fit(ctx, [c7, c8]).predict(ctx, 50.0)
    A_sbm = np.zeros_like(A_real)
    A_sbm[ctx.I, ctx.J] = sbm
    rng = np.random.default_rng(0)
    conds = {"A-real": [A_real], "A-rule": [P_rule], "A-sbm": [A_sbm],
             "A-rule-s": [(rng.random(P_rule.shape) < P_rule).astype(float) for _ in range(20)],
             "A-rewire": [F.rewire(A_real > 0, np.random.default_rng(s)) for s in range(20)],
             "A-er": [(np.random.default_rng(100 + s).random(A_real.shape) < (A_real > 0).mean()).astype(float)
                      for s in range(20)]}
    G = gap_junctions(cells)
    # F-d ablations of the rule (only interpreted if F-c holds)
    rng2 = np.random.default_rng(1)
    abl = {}
    for name, kw in (("no-distance", {"beta0_grid": np.array([0.0])}), ("shuffled-types", {}), ("shuffled-birth", {})):
        ctx2 = Mo.make_ctx(cells)
        types = ctx.cook.copy()
        if name == "shuffled-types":
            types = rng2.permutation(types)
        if name == "shuffled-birth":
            ctx2.birth = rng2.permutation(ctx2.birth)
        m = Mo.RS(types=types, beta0_grid=kw.get("beta0_grid", g), sminus_grid=g, iters=20, gamma=GAMMA).fit(ctx2, [c7, c8])
        Pm = np.zeros_like(A_real)
        Pm[ctx.I, ctx.J] = m.p
        abl[name] = Pm
    out = {}
    for strain in ("wt", "unc31"):
        if a.dry_run:
            d = randi.dev(strain, cells)
            cls = C.lr_class(cells)
            inner = np.array([int(hashlib.sha256(("m08-randi-inner-v1:" + c).encode()).hexdigest()[-1], 16) % 2 == 0
                              for c in cls])
            dev_cols, held_cols = ~d["heldout_columns"] & inner, ~d["heldout_columns"] & ~inner
        else:
            d = randi.judge(strain, cells)
            dev_cols, held_cols = ~d["heldout_columns"], d["heldout_columns"]
        fit_pairs, sc_pairs = randi.labels(d, dev_cols), randi.labels(d, held_cols)
        I, J, y = sc_pairs
        cls_j = C.lr_class(cells)[J]
        scores = {}
        for name, mats in list(conds.items()) + [(f"ablation:{k}", [v]) for k, v in abl.items()]:
            ss = []
            for A in mats:
                f = F.fit_condition(A, fit_pairs)
                ss.append(F.predict(A, f, sc_pairs))
            scores[name] = np.mean(ss, axis=0)
        X = Mo.feature_matrix(ctx, 50.0)
        idx = {(i, j): k for k, (i, j) in enumerate(zip(ctx.I, ctx.J))}
        fx = lambda pr: X[[idx[(j, i)] for i, j in zip(pr[0], pr[1])]]          # noqa: E731
        mu, sd = fx(fit_pairs).mean(0), fx(fit_pairs).std(0) + 1e-9
        lr = LogisticRegression(C=1.0, max_iter=5000).fit((fx(fit_pairs) - mu) / sd, fit_pairs[2])
        scores["A-none"] = lr.predict_proba((fx(sc_pairs) - mu) / sd)[:, 1]
        res = {"n_pairs": int(len(y)), "pos_rate": float(y.mean()),
               "auprc": {k: M.auprc(v, y) for k, v in scores.items()},
               "auroc": {k: M.auroc(v, y) for k, v in scores.items()}}
        diffs = {f"{a1}-vs-{b1}": class_boot(scores[a1], scores[b1], y, cls_j, ap, a.boot)
                 for a1, b1 in (("A-real", "A-er"), ("A-real", "A-none"), ("A-real", "A-rewire"), ("A-rule", "A-none"),
                                ("A-rule", "A-er"), ("A-rule-s", "A-er"))}
        res["diffs"] = diffs
        er = res["auprc"]["A-er"]
        res["F-a"] = diffs["A-real-vs-A-er"]["lo"] > 0 and diffs["A-real-vs-A-none"]["lo"] > 0
        res["F-b"] = diffs["A-real-vs-A-rewire"]["lo"] > 0
        gain_real = res["auprc"]["A-real"] - er
        res["F-c"] = None if not (res["F-a"] and res["F-b"]) else bool(
            res["auprc"]["A-rule"] - er >= 0.5 * gain_real and diffs["A-rule-vs-A-none"]["lo"] > 0)
        if res["F-c"]:
            gain_rule = res["auprc"]["A-rule"] - er
            res["F-d"] = {k: bool(res["auprc"][f"ablation:{k}"] - er <= 0.75 * gain_rule) for k in abl}
        else:
            res["F-d"] = None
        res["gain_over_none"] = res["auprc"]["A-real"] - res["auprc"]["A-none"]
        # amendment A4.3: gap junctions added to every structure; one-step and one-plus-two-step scores
        sec = {}
        for name, mats in conds.items():
            ss = [F.predict(A + G, F.fit_condition(A + G, fit_pairs), sc_pairs) for A in mats]
            sec[f"{name}+gap"] = np.mean(ss, axis=0)
        sec["A-real one-step"] = steps_scores(A_real, fit_pairs, sc_pairs, two=False)
        sec["A-real one+two-step"] = steps_scores(A_real, fit_pairs, sc_pairs, two=True)
        res["secondary"] = {k: {"auprc": M.auprc(v, y), "auroc": M.auroc(v, y)} for k, v in sec.items()}
        ha, hb = randi.split_half(strain, cells, held_cols)
        res["split_half_reference"] = {"n_pairs": int(len(ha)),
                                       "spearman": float(spearmanr(ha, hb)[0]) if len(ha) > 2 else None}
        out[strain] = res
    out["F-e"] = {"wt_gain": out["wt"]["gain_over_none"], "unc31_gain": out["unc31"]["gain_over_none"],
                  "unc31_greater": out["unc31"]["gain_over_none"] > out["wt"]["gain_over_none"]}
    out["rule_fit"] = {"beta0": float(r1.beta0), "sminus": float(r1.sminus), "gamma": GAMMA}
    print(run.write(out))


if __name__ == "__main__":
    main()
