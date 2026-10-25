"""Gate 4 ablations on development data (G4_CANDIDATE_LOG.md, trial 1): which prior adds information to memory?
Adult proxies (W7 <-> W8): C(M4, X) for X in {B3, B2, ER, K1}, combination fitted on one direction and scored on the
other, with block-bootstrap intervals of the LL difference to M4. Developmental proxies (W5, W1): C(M2, X) and the
Beta-binomial shrinkage for X in {ER-age, B2-age, B3-age, R1-dev, K1}, fitted on one proxy and scored on the other.
  python3 -I experiments/g4_ablation.py [--grid 10] [--k 8] [--alpha-m2 0.05]
With the values selected under amendment A4.1 (--k 16 --alpha-m2 0.01) the output is ablation_selected.json.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from g3_development_dev import DEV, dev_cells  # noqa: E402
from m08 import candidates as K, celegans as C, ledger, metrics as M, models as Mo, rs  # noqa: E402

K1_BLOCKS = ["coarse", "nt_pair", "dist", "lineage", "birth"]          # selected in trial 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--grid", type=int, default=10)
    ap.add_argument("--k", type=int, default=8, help="number of inferred types of B3")
    ap.add_argument("--alpha-m2", type=float, default=0.05)
    a = ap.parse_args()
    selected = (a.k, a.alpha_m2) != (8, 0.05)
    run = ledger.Run("g4", "ablation_selected" if selected else "ablation", k=a.k, alpha_m2=a.alpha_m2)
    res = {"adult": {}, "development": {}}

    w7, w8 = C.witvliet(7), C.witvliet(8)
    cells = sorted(C.cells_of(w7) & C.cells_of(w8))
    ctx = Mo.make_ctx(cells)
    bank = K.FeatureBank(ctx)
    c7, c8 = C.conn(cells, k=7), C.conn(cells, k=8)
    out = {}
    for tr, te in ((c7, c8), (c8, c7)):
        m4 = Mo.CountCopy(reverse=True).fit(ctx, [tr], [(te.counts, tr)]).predict(ctx, te.age_h)
        t8 = rs.hit_rate_types(tr.A > 0, a.k)
        out[te.name] = {"M4": m4, "B3": Mo.Block(t8, "b3").fit(ctx, [tr]).predict(ctx, te.age_h),
                        "B2": Mo.Block(ctx.cook, "b2").fit(ctx, [tr]).predict(ctx, te.age_h),
                        "ER": Mo.ER().fit(ctx, [tr]).predict(ctx, te.age_h),
                        "K1": K.K1(K1_BLOCKS).fit(ctx, [tr], bank).predict(ctx, te.age_h),
                        "y": ctx.flat(te.A), "m": ctx.pair_mask(te.present)}
    for fit, sc in (("W8", "W7"), ("W7", "W8")):
        f, s = out[fit], out[sc]
        m, y = s["m"], s["y"][s["m"]]
        base = s["ER"][m]
        rows = {"M4": M.summary(s["M4"][m], y, base)}
        for q in ("B3", "B2", "ER", "K1"):
            comb = Mo.Combine("c").fit([(f["M4"][f["m"]], f[q][f["m"]], f["y"][f["m"]])])
            p = comb.predict(s["M4"], s[q])[m]
            rows[f"C(M4,{q})"] = M.summary(p, y, base) | {
                "ll_diff_vs_M4": M.boot_diff(M.wll, p, s["M4"][m], y, ctx.I[m], n_boot=2000)}
        res["adult"][f"score_{sc}_fit_{fit}"] = rows

    dcells, _ = dev_cells()
    dctx = Mo.make_ctx(dcells)
    dbank = K.FeatureBank(dctx)
    conns = {k: C.conn(dcells, k=k) for k in DEV}
    g = np.linspace(0, 0.05, a.grid + 1)[:-1]
    r1 = Mo.RSDev(dctx.cook, g, g, iters=20).fit(dctx, [[conns[3]], [conns[6]], [conns[7], conns[8]]])
    data = {}
    for target in (5, 1):
        tgt = conns[target]
        train = [conns[k] for k in DEV if k != target]
        m, y = dctx.pair_mask(tgt.present), dctx.flat(tgt.A)
        w = Mo.age_weights([t.age_h for t in train], tgt.age_h)
        kk = sum(wi * dctx.flat(t.A) for wi, t in zip(w, train) if wi > 0)
        t8 = rs.hit_rate_types(sum(t.A for t in train) > 0, a.k)
        qs = {"ER-age": Mo.ER().fit(dctx, train).predict(dctx, tgt.age_h),
              "B2-age": Mo.Block(dctx.cook, "b2").fit(dctx, train).predict(dctx, tgt.age_h),
              "B3-age": Mo.Block(t8, "b3").fit(dctx, train).predict(dctx, tgt.age_h),
              "R1-dev": r1.predict(dctx, tgt.age_h),
              "K1": K.K1(K1_BLOCKS + ["age"]).fit(dctx, train, dbank).predict(dctx, tgt.age_h)}
        m2 = Mo.Copy(alpha=a.alpha_m2, interpolate=True).fit(dctx, train).predict(dctx, tgt.age_h)
        data[target] = {"kk": kk, "qs": qs, "M2": m2, "y": y, "m": m}
    for tf, ts in ((1, 5), (5, 1)):
        f, s = data[tf], data[ts]
        m, y = s["m"], s["y"][s["m"]]
        base = s["qs"]["ER-age"][m]
        rows = {"M2": M.summary(s["M2"][m], y, base)}
        for name in s["qs"]:
            kap, _ = K.fit_kappa([(f["kk"][f["m"]], 1.0, f["qs"][name][f["m"]], f["y"][f["m"]])])
            p = np.clip((s["kk"] + kap * s["qs"][name]) / (1 + kap), 1e-6, 1 - 1e-6)[m]
            rows[f"shrink[{name}]"] = M.summary(p, y, base) | {"kappa": kap}
            comb = Mo.Combine("c").fit([(f["M2"][f["m"]], f["qs"][name][f["m"]], f["y"][f["m"]])])
            pc = comb.predict(s["M2"], s["qs"][name])[m]
            rows[f"C(M2,{name})"] = M.summary(pc, y, base)
        res["development"][f"score_W{ts}_fit_W{tf}"] = rows
    print(run.write(res))


if __name__ == "__main__":
    main()
