"""Gate 3, developmental targets on development data only: leave-one-stage-out proxies W5 (23 h) and W1 (0 h).
Neuron set: the 180 adult nerve-ring neurons minus those whose presence in any development data set contradicts
their birth time (computed from development data only). Models: B0, B2 (Cook blocks, age-interpolated), B4, M1, M2
(trained on the other development stages) and the three-epoch R1 (constraints W3, W6, W7 + W8; Cook types).
  python3 -I experiments/g3_development_dev.py [--grid 10]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from m08 import celegans as C  # noqa: E402
from m08 import ledger, metrics as M, models as Mo, rs  # noqa: E402

DEV = (1, 3, 5, 6, 7, 8)


def dev_cells():
    w7, w8 = C.witvliet(7), C.witvliet(8)
    ref = sorted(C.cells_of(w7) & C.cells_of(w8))
    bt = dict(zip(ref, C.birth_times(ref)))
    bad = set()
    for k in DEV:
        pres, t = C.present_in(k=k), rs.minutes(C.WITVLIET_AGE_H[k])
        bad |= {c for c in ref if (bt[c] < t) != (c in pres)}
    return [c for c in ref if c not in bad], sorted(bad)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--grid", type=int, default=10)
    a = ap.parse_args()
    run = ledger.Run("g3", "development_dev_grid%d" % a.grid)
    cells, excluded = dev_cells()
    ctx = Mo.make_ctx(cells)
    conns = {k: C.conn(cells, k=k) for k in DEV}
    res = {"n_cells": len(cells), "excluded": excluded}
    g = np.linspace(0, 0.05, a.grid + 1)[:-1]
    r1 = Mo.RSDev(ctx.cook, g, g, iters=20, name="R1-dev-cook").fit(ctx, [[conns[3]], [conns[6]], [conns[7], conns[8]]])
    res["R1_fit"] = {"beta0": float(r1.beta0), "sminus": float(r1.sminus), "ll": float(r1.ll), "n_params": r1.n_params}
    # density trajectory of R1 against every development data set (positive control of the developmental path)
    traj = {}
    for k in DEV:
        t = conns[k]
        m = ctx.pair_mask(t.present)
        traj[f"W{k}"] = {"age_h": t.age_h, "data_density": float(ctx.flat(t.A)[m].mean()),
                         "r1_density": float(r1.predict(ctx, t.age_h)[m].mean())}
    res["density_trajectory"] = traj
    for target in (5, 1):
        tgt = conns[target]
        train = [conns[k] for k in DEV if k != target]
        base = Mo.ER().fit(ctx, train).predict(ctx, tgt.age_h)
        m = ctx.pair_mask(tgt.present)
        y = ctx.flat(tgt.A)[m]
        rows = {}
        models = [Mo.ER(), Mo.Block(ctx.cook, "B2-block-cook"), Mo.Features(), Mo.Copy(), Mo.Copy(interpolate=True)]
        for model in models:
            p = model.fit(ctx, train).predict(ctx, tgt.age_h)
            rows[model.name] = M.summary(p[m], y, base[m])
        p = r1.predict(ctx, tgt.age_h)
        rows["R1-dev-cook"] = M.summary(p[m], y, base[m])
        res[f"proxy_W{target}"] = rows
    print(run.write(res))


if __name__ == "__main__":
    main()
