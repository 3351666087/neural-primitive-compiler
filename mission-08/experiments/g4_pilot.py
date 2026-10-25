"""Gate 4 pilots on development data (G4_CANDIDATE_LOG.md). K1: greedy forward selection of independent feature
blocks on the adult proxies W7 -> W8 and W8 -> W7, then the same blocks (+ age) on the developmental proxies W5 and
W1. K2: shrinkage of memory towards B3 (adult) or the three-epoch R1 (development), kappa on the proxies; compared
with the best memory model and with the pre-registered combination C(X).
  python3 -I experiments/g4_pilot.py [--grid 10]
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

BLOCKS = ["dist", "birth", "lineage", "coarse", "nt_pre_post", "nt_pair", "homolog", "same_class_nt", "lineage_x_dist"]


def ev(ctx, p, tgt, base):
    m = ctx.pair_mask(tgt.present)
    return M.summary(p[m], ctx.flat(tgt.A)[m], base[m])


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--grid", type=int, default=10)
    a = ap.parse_args()
    run = ledger.Run("g4", "pilot")
    res = {}

    # ---------------- adult proxies (180 neurons)
    w7, w8 = C.witvliet(7), C.witvliet(8)
    cells = sorted(C.cells_of(w7) & C.cells_of(w8))
    ctx = Mo.make_ctx(cells)
    c7, c8 = C.conn(cells, k=7), C.conn(cells, k=8)
    bank = K.FeatureBank(ctx)
    proxies = [([c7], c8), ([c8], c7)]
    sel, trace = K.forward_select(ctx, proxies, BLOCKS, bank=bank)
    res["K1_selection"] = {"selected": sel, "trace": trace}
    adult = {}
    for train, test in proxies:
        key = f"{train[0].name}->{test.name}"
        base = Mo.ER().fit(ctx, train).predict(ctx, test.age_h)
        rows = {}
        k1 = K.K1(sel).fit(ctx, train, bank)
        rows["K1"] = ev(ctx, k1.predict(ctx, test.age_h), test, base) | {"n_params": k1.n_params}
        b4 = Mo.Features().fit(ctx, train)
        rows["B4"] = ev(ctx, b4.predict(ctx, test.age_h), test, base)
        t8 = rs.hit_rate_types(train[0].A > 0, 8)
        b3 = Mo.Block(t8, "B3").fit(ctx, train)
        q = b3.predict(ctx, test.age_h)
        rows["B3"] = ev(ctx, q, test, base)
        m4 = Mo.CountCopy(reverse=True).fit(ctx, train, [(test.counts, train[0])])
        rows["M4"] = ev(ctx, m4.predict(ctx, test.age_h), test, base)
        rows["M1"] = ev(ctx, Mo.Copy().fit(ctx, train).predict(ctx, test.age_h), test, base)
        adult[key] = {"rows": rows, "q": q, "k": ctx.flat(train[0].A), "y": ctx.flat(test.A), "m": ctx.pair_mask(test.present),
                      "k1q": k1.predict(ctx, test.age_h)}
    # K2 on adult proxies: kappa fitted on one proxy, scored on the other (and the reverse)
    keys = list(adult)
    k2 = {}
    for fit_key, sc_key in ((keys[0], keys[1]), (keys[1], keys[0])):
        f = adult[fit_key]
        kap, _ = K.fit_kappa([(f["k"][f["m"]], 1.0, f["q"][f["m"]], f["y"][f["m"]])])
        s = adult[sc_key]
        base = np.full(s["m"].sum(), s["y"][s["m"]].mean())
        p = np.clip((s["k"] + kap * s["q"]) / (1 + kap), 1e-6, 1 - 1e-6)
        k2[sc_key] = {"kappa": kap, **M.summary(p[s["m"]], s["y"][s["m"]])}
        pk1 = np.clip((s["k"] + kap * s["k1q"]) / (1 + kap), 1e-6, 1 - 1e-6)
        k2[sc_key + "_K1prior"] = M.summary(pk1[s["m"]], s["y"][s["m"]])
    res["adult"] = {k: v["rows"] for k, v in adult.items()}
    res["K2_adult"] = k2

    # ---------------- developmental proxies (166 neurons)
    dcells, _ = dev_cells()
    dctx = Mo.make_ctx(dcells)
    dbank = K.FeatureBank(dctx)
    conns = {k: C.conn(dcells, k=k) for k in DEV}
    g = np.linspace(0, 0.05, a.grid + 1)[:-1]
    r1 = Mo.RSDev(dctx.cook, g, g, iters=20).fit(dctx, [[conns[3]], [conns[6]], [conns[7], conns[8]]])
    dev = {}
    dev_k2 = []
    for target in (5, 1):
        tgt = conns[target]
        train = [conns[k] for k in DEV if k != target]
        base = Mo.ER().fit(dctx, train).predict(dctx, tgt.age_h)
        m = dctx.pair_mask(tgt.present)
        y = dctx.flat(tgt.A)
        rows = {}
        k1d = K.K1(sel + ["age"]).fit(dctx, train, dbank)
        rows["K1"] = ev(dctx, k1d.predict(dctx, tgt.age_h), tgt, base)
        q = r1.predict(dctx, tgt.age_h)
        rows["R1-dev"] = ev(dctx, q, tgt, base)
        cp = Mo.Copy(interpolate=True).fit(dctx, train)
        pm = cp.predict(dctx, tgt.age_h)
        rows["M2"] = ev(dctx, pm, tgt, base)
        w = Mo.age_weights([t.age_h for t in train], tgt.age_h)
        kk = sum(wi * dctx.flat(t.A) for wi, t in zip(w, train) if wi > 0)
        dev_k2.append((target, kk, q, y, m, base))
        dev[f"W{target}"] = rows
    # K2 developmental: kappa fitted on one proxy, scored on the other
    for (t_fit, kf, qf, yf, mf, _), (t_sc, ks, qs, ys, ms, bs) in ((dev_k2[0], dev_k2[1]), (dev_k2[1], dev_k2[0])):
        kap, _ = K.fit_kappa([(kf[mf], 1.0, qf[mf], yf[mf])])
        p = np.clip((ks + kap * qs) / (1 + kap), 1e-6, 1 - 1e-6)
        dev[f"W{t_sc}"]["K2"] = {"kappa": kap, **M.summary(p[ms], ys[ms], bs[ms])}
    res["development"] = dev
    print(run.write(res))


if __name__ == "__main__":
    main()
