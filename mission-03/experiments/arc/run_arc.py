"""ARC-AGI-1 comparison runner (protocol amendment 9).

  python -I mission-03/experiments/arc/run_arc.py training      # development split
  python -I mission-03/experiments/arc/run_arc.py uset          # synthetic underdetermined tasks (DEV)
  python -I mission-03/experiments/arc/run_arc.py selftest      # synthetic sanity tasks for the solvers
  python -I mission-03/experiments/arc/run_arc.py freeze        # write arc_freeze.json (hash of the solver files)
  python -I mission-03/experiments/arc/run_arc.py evaluation    # held-out split; refuses unless frozen hashes match

The runner prints and stores only task ids and outcome labels, never grid contents.
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import b_dsl  # noqa: E402
import m_disc  # noqa: E402

DATA = HERE.parents[1] / "external" / "arc-agi-1" / "data"
FROZEN = [HERE / "m_disc.py", HERE / "b_dsl.py", HERE / "run_arc.py"]
FREEZE = HERE / "arc_freeze.json"

METHODS = {
    "M-DISC": lambda tr, te: m_disc.solve(tr, te),
    "M-DISC-MDL": lambda tr, te: m_disc.solve(tr, te, tiebreak="mdl"),
    "A1-no-far-anchors": lambda tr, te: m_disc.solve(tr, te, anchor_far=False),
    "A2-translations-only": lambda tr, te: m_disc.solve(tr, te, mats_kind="identity"),
    "A3-no-uniqueness": lambda tr, te: m_disc.solve(tr, te, unique=False),
    "B-SAME": lambda tr, te: b_dsl.solve(tr, te, rich=False),
    "B-RICH": lambda tr, te: b_dsl.solve(tr, te, rich=True),
    "B-TRIVIAL-identity": lambda tr, te: b_dsl.trivial(tr, te, "identity"),
    "B-TRIVIAL-first-output": lambda tr, te: b_dsl.trivial(tr, te, "first"),
}


def load(path):
    d = json.loads(Path(path).read_bytes())
    train = [(np.array(p["input"]), np.array(p["output"])) for p in d["train"]]
    tests = [(np.array(p["input"]), np.array(p["output"])) for p in d["test"]]
    return train, tests


def score(pred, truth):
    if pred is None:
        return "abstain"
    return "correct" if pred.shape == truth.shape and (pred == truth).all() else "wrong"


def run_task(train, tests, methods):
    row = {}
    for name in methods:
        t0 = time.perf_counter()
        try:
            outs, info = METHODS[name](train, [I for I, _ in tests])
            labels = [score(o, T) for o, (_, T) in zip(outs, tests)]
        except Exception as e:      # a crash is a result (recorded), not a reason to stop
            labels, info = ["error"], {"error": f"{type(e).__name__}: {e}"}
        status = "correct" if all(l == "correct" for l in labels) else "wrong" if "wrong" in labels or "error" in labels else "abstain"
        row[name] = {"status": status, "time_s": round(time.perf_counter() - t0, 3),
                     "info": {k: v for k, v in info.items() if k in ("reason", "program", "min_covers", "cover_size", "pieces", "error")}}
    return row


def summarise(rows, methods):
    out = {}
    for m in methods:
        st = [r[m]["status"] for r in rows.values()]
        n = len(st)
        c, w, a = st.count("correct"), st.count("wrong"), st.count("abstain")
        out[m] = {"tasks": n, "correct": c, "wrong": w, "abstain": a, "solve_rate": round(c / n, 4),
                  "precision": round(c / (c + w), 3) if c + w else None,
                  "mean_time_s": round(sum(r[m]["time_s"] for r in rows.values()) / n, 3)}
    return out


def file_hashes():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in FROZEN}


# ------------------------------------------------------------------ synthetic task sets (no ARC content)
D4F = {"flipH": lambda g: g[:, ::-1], "flipV": lambda g: g[::-1, :], "rot90": lambda g: np.rot90(g, -1),
       "rot180": lambda g: np.rot90(g, 2), "rot270": lambda g: np.rot90(g, 1), "transpose": lambda g: g.T,
       "antitranspose": lambda g: np.rot90(g, 2).T}


def rand_grid(rng, h, w, p=0.35):
    return np.array([[rng.randint(1, 9) if rng.random() < p else 0 for _ in range(w)] for _ in range(h)])


INV = {"flipH": "flipH", "flipV": "flipV", "rot90": "rot270", "rot270": "rot90", "rot180": "rot180",
       "transpose": "transpose", "antitranspose": "antitranspose"}


def uset(n=20, seed=3):
    """Underdetermined tasks: two D4 maps f1, f2 agree on every training input (each input is made invariant
    under h = f1^-1 f2 by taking the pointwise max over its h-orbit) but not on the test input."""
    rng = random.Random(seed)
    tasks = []
    names = list(D4F)
    while len(tasks) < n:
        f1, f2 = rng.sample(names, 2)
        N = rng.randint(4, 7)
        h = lambda g: D4F[INV[f1]](D4F[f2](g))
        train = []
        for _ in range(3):
            g = rand_grid(rng, N, N)
            while True:
                g2 = np.maximum(g, h(g))
                if (g2 == g).all():
                    break
                g = g2
            train.append((g, D4F[f1](g)))
        test = rand_grid(rng, N, N)
        if not (D4F[f1](test) == D4F[f2](test)).all() and all((D4F[f1](g) == D4F[f2](g)).all() for g, _ in train):
            tasks.append((f"U{len(tasks)}:{f1}|{f2}", train, [(test, D4F[f1](test))]))
    return tasks


def selftest():
    """Sanity tasks with known answers for both solvers (rotations, tiling, mirror, scale, colour map, crop)."""
    rng = random.Random(5)
    specs = {
        "rot90": lambda g: np.rot90(g, -1), "flipH": lambda g: g[:, ::-1], "tile2x2": lambda g: np.tile(g, (2, 2)),
        "hmirror": lambda g: np.hstack([g, g[:, ::-1]]), "scale2": lambda g: np.kron(g, np.ones((2, 2), int)),
        "recolour": lambda g: np.vectorize(lambda v: {0: 0}.get(v, (v % 9) + 1))(g),
        "shift-right-1": lambda g: np.hstack([np.zeros((g.shape[0], 1), int), g[:, :-1]]),
        "crop": b_dsl.crop, "gravity_down": lambda g: b_dsl.gravity(g, "down"),
    }
    tasks = []
    for name, f in specs.items():
        sizes = [(rng.randint(3, 6), rng.randint(3, 6)) for _ in range(4)]
        if name in ("rot90",):
            sizes = [(s[0], s[0]) for s in sizes]
        grids = [rand_grid(rng, h, w) for h, w in sizes]
        if name == "crop":
            grids = [np.pad(g, ((1, 1), (2, 1))) for g in grids]
        tasks.append((name, [(g, f(g)) for g in grids[:3]], [(grids[3], f(grids[3]))]))
    return tasks


def main(mode):
    methods = list(METHODS)
    if mode == "freeze":
        FREEZE.write_text(json.dumps({"files": file_hashes(), "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S")}, indent=1))
        print("frozen", file_hashes())
        return
    if mode == "evaluation":
        man = json.loads(FREEZE.read_text())
        if man["files"] != file_hashes():
            sys.exit("solver files changed since the freeze; refusing to touch the held-out split")
    if mode in ("training", "evaluation"):
        files = sorted((DATA / mode).glob("*.json"))
        items = ((f.stem, *load(f)) for f in files)
    elif mode == "uset":
        items = uset()
    else:
        items = selftest()
    rows = {}
    t0 = time.perf_counter()
    for tid, train, tests in items:
        rows[tid] = run_task(train, tests, methods)
        print(tid, {m: rows[tid][m]["status"] for m in methods}, flush=True)
    summary = summarise(rows, methods)
    out = {"mode": mode, "solver_hashes": file_hashes(), "summary": summary, "rows": rows,
           "time_s": round(time.perf_counter() - t0, 1)}
    (HERE / f"arc_{mode}.json").write_text(json.dumps(out, indent=1, default=str))
    for m, s in summary.items():
        print(m, s)


if __name__ == "__main__":
    main(sys.argv[1])
