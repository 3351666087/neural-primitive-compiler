"""Gate 3, structure line, development data only (W7 <-> W8). Positive control: the re-implemented Richter & Schneidman
model reproduces the published AUROC (0.78 with 13 Cook types, 0.81 with 8 inferred types, test worm 8, tolerance
+-0.03; PRE_REGISTRATION.md section 8). Baselines B0-B4 and memorisation M1, M3, M4 on the same proxy, both
directions. Negative controls: R1 trained on a degree-preserving rewiring, on shuffled Cook labels, on the transposed
adjacency, and with shuffled positions or birth times must lose accuracy.
  python3 -I experiments/g3_structure_dev.py [--grid 40] [--workers 4]
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from m08 import celegans as C  # noqa: E402
from m08 import ledger, models as Mo, metrics as M  # noqa: E402


def setup():
    w7, w8 = C.witvliet(7), C.witvliet(8)
    cells = sorted(C.cells_of(w7) & C.cells_of(w8))
    ctx = Mo.make_ctx(cells)
    return ctx, C.conn(cells, k=7), C.conn(cells, k=8)


def rewire(A, rng, n_swaps=None):
    """Degree-preserving rewiring of a directed binary graph by double edge swaps (no self loops, no multi-edges)."""
    A = A.copy().astype(bool)
    np.fill_diagonal(A, False)
    E = np.argwhere(A)
    n_swaps = n_swaps or 10 * len(E)
    for _ in range(n_swaps):
        a, b = rng.integers(0, len(E), 2)
        (i, j), (k, l) = E[a], E[b]
        if len({i, j, k, l}) < 4 or A[i, l] or A[k, j]:
            continue
        A[i, j] = A[k, l] = False
        A[i, l] = A[k, j] = True
        E[a], E[b] = (i, l), (k, j)
    return A.astype(float)


def score(ctx, p, tgt, base):
    m = ctx.pair_mask(tgt.present)
    y = ctx.flat(tgt.A)[m]
    return M.summary(p[m], y, base[m])


def fit_rs(args):
    """Worker: fit one R1 variant on one training Conn and score it on the test Conn."""
    variant, train, test, grid, seed = args
    ctx, _, _ = setup()
    rng = np.random.default_rng(seed)
    cook = ctx.cook.copy()
    pos, birth = ctx.pos.copy(), ctx.birth.copy()
    tr = train
    if variant == "shuffled_labels":
        cook = rng.permutation(cook)
    if variant == "rewired":
        tr = Mo.Conn(train.name + "-rewired", train.age_h, rewire(train.A, rng), train.present)
    if variant == "transposed":
        tr = Mo.Conn(train.name + "-T", train.age_h, train.counts.T.copy(), train.present)
    if variant == "shuffled_positions":
        ctx.pos = rng.permutation(pos)
        ctx.__post_init__()
    if variant == "shuffled_birth":
        ctx.birth = rng.permutation(birth)
    g = np.linspace(0, 0.05, grid + 1)[:-1]
    if variant == "inferred8":
        model = Mo.RS(k_inferred=8, beta0_grid=g, sminus_grid=g, iters=20)
    else:
        model = Mo.RS(types=cook, beta0_grid=g, sminus_grid=g, iters=20)
    c0 = ledger.cpu_seconds()
    model.fit(ctx, [tr])
    p = model.predict(ctx, test.age_h)
    base = Mo.ER().fit(ctx, [train]).predict(ctx, test.age_h)
    out = score(ctx, p, test, base)
    out.update({"variant": variant, "train": train.name, "test": test.name, "beta0": float(model.beta0),
                "sminus": float(model.sminus), "n_params": model.n_params, "label_bits": float(model.label_bits),
                "cpu_s_worker": ledger.cpu_seconds() - c0})
    return out, p


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--grid", type=int, default=40)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--positive-only", action="store_true", help="only the two R1 positive controls (W7 -> W8)")
    a = ap.parse_args()
    run = ledger.Run("g3", "structure_dev" + ("_positive_grid%d" % a.grid if a.positive_only else ""), grid=a.grid)
    ctx, w7, w8 = setup()
    res = {"n_neurons": len(ctx.cells), "n_pairs": int(len(ctx.I))}

    # baselines and memorisation, both directions
    for train, test in (() if a.positive_only else ((w7, w8), (w8, w7))):
        key = f"{train.name}->{test.name}"
        base = Mo.ER().fit(ctx, [train]).predict(ctx, test.age_h)
        rows = {}
        for model in (Mo.ER(), Mo.Distance(), Mo.Block(ctx.cook, "B2-block-cook"), Mo.Features()):
            p = model.fit(ctx, [train]).predict(ctx, test.age_h)
            rows[model.name] = score(ctx, p, test, base) | {"n_params": model.n_params}
        from m08 import rs
        t8 = rs.hit_rate_types(train.A > 0, 8)
        p = Mo.Block(t8, "B3-block-inferred8").fit(ctx, [train]).predict(ctx, test.age_h)
        rows["B3-block-inferred8"] = score(ctx, p, test, base) | {"n_params": 64}
        cp = Mo.Copy(alpha=0.05)
        rows["M1-copy"] = score(ctx, cp.fit(ctx, [train]).predict(ctx, test.age_h), test, base) | {"bits": cp.bits(ctx)}
        calib = [(test.counts, train)]          # calibrate counts on the reverse proxy (source = test animal)
        for rev in (False, True):
            mm = Mo.CountCopy(reverse=rev).fit(ctx, [train], calib)
            rows[mm.name] = score(ctx, mm.predict(ctx, test.age_h), test, base) | {"bits": mm.bits(ctx)}
        res[key] = rows

    # R1 positive controls and negative controls (process pool)
    jobs = [("cook", w7, w8, a.grid, 0), ("inferred8", w7, w8, a.grid, 0), ("cook", w8, w7, a.grid, 0),
            ("inferred8", w8, w7, a.grid, 0)]
    if a.positive_only:
        jobs = jobs[:2]
    else:
        jobs += [(v, w7, w8, a.grid, s) for v in ("rewired", "shuffled_labels", "transposed", "shuffled_positions",
                                                 "shuffled_birth") for s in (0,)]
    with ProcessPoolExecutor(a.workers) as ex:
        outs = list(ex.map(fit_rs, jobs))
    res["R1"] = [o for o, _ in outs]
    res["published"] = {"cook13_auroc_w8": 0.78, "inferred8_auroc_w8": 0.81, "tolerance": 0.03}
    pc = {o["variant"]: o["auroc"] for o in res["R1"] if o["train"] == "W7" and o["variant"] in ("cook", "inferred8")}
    res["positive_control"] = {"cook_ok": abs(pc["cook"] - 0.78) <= 0.03, "inferred8_ok": abs(pc["inferred8"] - 0.81) <= 0.03,
                               "values": pc}
    print(run.write(res))


if __name__ == "__main__":
    main()
