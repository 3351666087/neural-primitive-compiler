"""Gate 4: the hyperparameter selections of PRE_REGISTRATION.md section 2.2 under the rules of amendment A4.1
(development data only). B3 k, M1 alpha, B4 L2 strength and R1 gamma on the adult proxies (W7 -> W8, W8 -> W7);
M2 alpha on the developmental leave-one-stage proxies W3, W5, W6. Writes results/g4/selection.json.
  python3 -I experiments/g4_selection.py [--grid 10] [--workers 6]
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from g3_development_dev import DEV, dev_cells  # noqa: E402
from m08 import celegans as C, ledger, metrics as M, models as Mo, rs  # noqa: E402

K_GRID = (4, 8, 16)
ALPHA_GRID = (0.01, 0.02, 0.05, 0.1, 0.2)
C_GRID = (0.01, 0.1, 1.0, 10.0)
GAMMA_GRID = (1.0, 3.0, 7.0, 15.0)
GAMMA_MIN_GAIN = 0.001                      # bits / pair over gamma = 1 (amendment A4.1)


def adult():
    w7, w8 = C.witvliet(7), C.witvliet(8)
    cells = sorted(C.cells_of(w7) & C.cells_of(w8))
    ctx = Mo.make_ctx(cells)
    return ctx, C.conn(cells, k=7), C.conn(cells, k=8)


def gain(ctx, p, te, base):
    m = ctx.pair_mask(te.present)
    s = M.summary(p[m], ctx.flat(te.A)[m], base[m])
    return {k: s[k] for k in ("ll_gain_bits_per_pair", "auroc", "auprc")}


def reciprocity(ctx, A, present):
    """Fraction of edges whose reverse edge exists, over the evaluated pairs, and its ratio to density^2."""
    m = ctx.pair_mask(present)
    y = ctx.flat(A)
    rec = float((y * A[ctx.J, ctx.I])[m].sum() / y[m].sum())
    return {"reciprocity": rec, "ratio_to_density2": rec / float(y[m].mean()) ** 2}


def gamma_job(args):
    gamma, direction, grid = args
    ctx, c7, c8 = adult()
    tr, te = (c7, c8) if direction == "W7->W8" else (c8, c7)
    g = np.linspace(0, 0.05, grid + 1)[:-1]
    r1 = Mo.RS(types=ctx.cook, beta0_grid=g, sminus_grid=g, iters=20, gamma=gamma).fit(ctx, [tr])
    p = r1.predict(ctx, te.age_h)
    base = Mo.ER().fit(ctx, [tr]).predict(ctx, te.age_h)
    out = gain(ctx, p, te, base) | {"gamma": gamma, "direction": direction, "beta0": float(r1.beta0),
                                     "sminus": float(r1.sminus), "count_err": float(r1.count_err),
                                     "table": r1.table}
    # model-implied reciprocity on the target's evaluated pairs
    m = ctx.pair_mask(te.present)
    S = rs.Setup(ctx.pos, ctx.birth, r1.types, rs.minutes(te.age_h))
    if gamma == 1.0:
        rev = np.empty(len(p), dtype=int)
        rev[S.u], rev[S.r] = S.r, S.u
        num = float((p * p[rev])[m].sum())
    else:
        pr = r1.reciprocal(ctx, te.age_h)
        num = float(2 * pr[m[S.u]].sum())
    out["model_reciprocity"] = num / float(p[m].sum())
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--grid", type=int, default=10)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    run = ledger.Run("g4", "selection", grid=a.grid)
    ctx, c7, c8 = adult()
    res = {"observed_reciprocity": {"W7": reciprocity(ctx, c7.A, c7.present), "W8": reciprocity(ctx, c8.A, c8.present)}}

    proxies = (("W7->W8", c7, c8), ("W8->W7", c8, c7))
    rows = {"B3_k": {}, "M1_alpha": {}, "B4_C": {}}
    for name, tr, te in proxies:
        base = Mo.ER().fit(ctx, [tr]).predict(ctx, te.age_h)
        for k in K_GRID:
            t = rs.hit_rate_types(tr.A > 0, k)
            rows["B3_k"].setdefault(k, {})[name] = gain(ctx, Mo.Block(t, "B3").fit(ctx, [tr]).predict(ctx, te.age_h), te, base)
        for al in ALPHA_GRID:
            rows["M1_alpha"].setdefault(al, {})[name] = gain(ctx, Mo.Copy(alpha=al).fit(ctx, [tr]).predict(ctx, te.age_h), te, base)
        for cr in C_GRID:
            rows["B4_C"].setdefault(cr, {})[name] = gain(ctx, Mo.Features(C_reg=cr).fit(ctx, [tr]).predict(ctx, te.age_h), te, base)

    cells, _ = dev_cells()
    dctx = Mo.make_ctx(cells)
    conns = {k: C.conn(cells, k=k) for k in DEV}
    rows["M2_alpha"] = {}
    for target in (3, 5, 6):
        te = conns[target]
        train = [conns[k] for k in DEV if k != target]
        base = Mo.ER().fit(dctx, train).predict(dctx, te.age_h)
        for al in ALPHA_GRID:
            p = Mo.Copy(alpha=al, interpolate=True).fit(dctx, train).predict(dctx, te.age_h)
            rows["M2_alpha"].setdefault(al, {})[f"W{target}"] = gain(dctx, p, te, base)

    def pick(table):
        mean = {k: float(np.mean([v["ll_gain_bits_per_pair"] for v in d.values()])) for k, d in table.items()}
        return max(mean, key=mean.get), mean

    chosen = {}
    for key, table in rows.items():
        best, mean = pick(table)
        chosen[key] = best
        res[key] = {"per_proxy": table, "mean_ll_gain": mean, "chosen": best}

    jobs = [(g, d, a.grid) for g in GAMMA_GRID for d in ("W7->W8", "W8->W7")]
    with ProcessPoolExecutor(a.workers) as ex:
        gam = list(ex.map(gamma_job, jobs))
    mean = {g: float(np.mean([r["ll_gain_bits_per_pair"] for r in gam if r["gamma"] == g])) for g in GAMMA_GRID}
    best = max(mean, key=mean.get)
    chosen_gamma = best if mean[best] - mean[1.0] >= GAMMA_MIN_GAIN else 1.0
    res["R1_gamma"] = {"fits": gam, "mean_ll_gain": mean, "best": best, "chosen": chosen_gamma,
                       "rule": f"best unless it beats gamma = 1 by < {GAMMA_MIN_GAIN} bits/pair"}
    chosen["R1_gamma"] = chosen_gamma
    res["chosen"] = chosen
    print(run.write(res))


if __name__ == "__main__":
    main()
