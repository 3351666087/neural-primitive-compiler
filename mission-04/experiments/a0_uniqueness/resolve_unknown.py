"""Re-decide the UNKNOWN cases of the exact uniqueness check with a second, independent exact procedure:
complete enumeration of every minimum cover over ALL coverage groups (no dominance pruning, no cap), with a
popcount bound for pruning and early exit as soon as two different test predictions (or an undetermined one)
appear. Sound and complete when it finishes within the time budget; otherwise the case stays UNKNOWN.
Same labels as rerun_arc.py (training = DEV; evaluation = POST-HOC re-evaluation, not held-out).

  python -I mission-04/experiments/a0_uniqueness/resolve_unknown.py
"""

from __future__ import annotations

import itertools
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rerun_arc as RA  # noqa: E402
import uniqueness as U  # noqa: E402

M = U.M
BUDGET_S = 300.0


class Timeout(Exception):
    pass


class Decided(Exception):
    pass


def decide(train, I, colour_mode, mdl):
    rules = M.size_rules(train)
    shape = M.apply_size(rules, I)
    if shape is None:
        return "size rule ambiguous", None
    mats = [tuple(tuple(k * v for v in r) for r in Mx) for k in (1, 2, 3) for Mx in M.D4M]
    pieces = M.admissible_pieces(train, mats, M.translations())
    need = M.requirement(train)
    groups = {}
    for p in pieces:
        groups.setdefault(M.coverage(p, train), []).append(p)
    gl = list(groups.items())
    k_star = len(M.min_covers(gl, need)[0])
    # distinct test behaviours per group (pieces with the same coverage and the same test image are interchangeable)
    beh = []
    for cov, ps in gl:
        imgs = {}
        for p in ps:
            im = U.test_image(p, I, shape, colour_mode)
            key = None if im is None else tuple(sorted(im.items()))
            d = M.piece_dl(p)
            if key not in imgs or d < imgs[key][1]:
                imgs[key] = (p, d)      # MDL needs the cheapest piece per behaviour
        beh.append(list(imgs.items()))
    keys = [g[0] for g in gl]
    pop = [bin(k).count("1") for k in keys]
    deadline = time.perf_counter() + BUDGET_S
    preds, undet_dls = {}, set()

    def record(cover):
        for combo in itertools.product(*[beh[i] for i in cover]):
            dl = sum(d for _, (_, d) in combo)
            if any(k is None for k, _ in combo):
                preds[("undetermined",)] = min(preds.get(("undetermined",), 10 ** 9), dl)
                undet_dls.add(dl)
                continue
            cells, ok = {}, True
            for k, _ in combo:
                for cell, col in k:
                    if cells.setdefault(cell, col) != col:
                        ok = False
            key = ("conflict",) if not ok else tuple(sorted(cells.items()))
            preds[key] = min(preds.get(key, 10 ** 9), dl)
        if not mdl and (len(preds) > 1 or ("undetermined",) in preds or ("conflict",) in preds):
            raise Decided()     # two different (or undefined) predictions: AMBIGUOUS, no need to continue

    def rec(chosen, cov):
        if time.perf_counter() > deadline:
            raise Timeout()
        miss = need & ~cov
        if not miss:
            record(chosen)
            return
        slots = k_star - len(chosen)
        if slots == 0:
            return
        low = miss & -miss
        cands = [i for i, b in enumerate(keys) if b & low and i not in chosen]
        # valid bound: no group can cover more of the missing cells than the best group overall
        best_any = max((bin(b & miss).count("1") for i, b in enumerate(keys) if i not in chosen), default=0)
        if best_any * slots < bin(miss).count("1"):
            return
        for i in cands:
            rec(chosen + [i], cov | keys[i])

    try:
        rec([], 0)
    except Timeout:
        return dict(verdict="UNKNOWN (budget)")
    except Decided:
        return dict(verdict="AMBIGUOUS", n=len(preds))
    if not preds:
        return dict(verdict="ERROR: no cover found although one exists")
    if mdl:
        # Same definition as M-DISC-MDL-fixed in uniqueness.solve_fixed: D* = least description length among covers
        # whose test prediction is defined; UNIQUE iff every cover of length exactly D* (undetermined ones included)
        # gives one and the same prediction. Conservative reading: undetermined covers SHORTER than D* also compete.
        defined = {k: v for k, v in preds.items() if k != ("undetermined",)}
        if not defined:
            return dict(verdict="AMBIGUOUS", n=len(preds), conservative="AMBIGUOUS")
        d_star = min(defined.values())
        top = [k for k, v in defined.items() if v == d_star]
        ok = len(top) == 1 and top[0] != ("conflict",) and d_star not in undet_dls
        cons = ok and not any(d < d_star for d in undet_dls)
        return dict(verdict="UNIQUE" if ok else "AMBIGUOUS", n=len(preds), conservative="UNIQUE" if cons else "AMBIGUOUS",
                    pred=top[0] if ok else None, shape=shape)
    good = [k for k in preds if k not in (("undetermined",), ("conflict",))]   # k may be () (empty prediction)
    ok = len(preds) == 1 and bool(good)
    return dict(verdict="UNIQUE" if ok else "AMBIGUOUS", n=len(preds), pred=good[0] if ok else None, shape=shape)


def label(v, T):
    if v["verdict"] != "UNIQUE":
        return "abstain"
    out = np.full(v["shape"], U.BG, dtype=int)
    for cell, col in v["pred"]:
        out[cell] = col
    return "correct" if out.shape == T.shape and (out == T).all() else "wrong"


def main():
    out = {}
    for split in ("training", "evaluation"):
        res = json.loads((HERE / f"rerun_{split}.json").read_text())
        for tid, row in res["rows"].items():
            for name, kw in RA.VARIANTS.items():
                r = row[name]
                if not (isinstance(r, dict) and r.get("uniqueness") and "UNKNOWN" in r["uniqueness"]):
                    continue
                train, tests = RA.load(RA.DATA / split / f"{tid}.json")
                t0 = time.perf_counter()
                verdicts = [decide(train, I, kw.get("colour_mode", "prior"), kw.get("tiebreak") == "mdl") for I, _ in tests]
                labels = [label(v, T) for v, (_, T) in zip(verdicts, tests)]
                status = "correct" if all(l == "correct" for l in labels) else "wrong" if "wrong" in labels else "abstain"
                out[f"{split}|{tid}|{name}"] = {"label": RA.LABEL[split], "z3_60s": r["uniqueness"],
                                                "enumeration": [v["verdict"] for v in verdicts],
                                                "distinct_predictions": [v.get("n") for v in verdicts],
                                                "mdl_conservative": [v.get("conservative") for v in verdicts],
                                                "status_after_resolution": status, "rerun_status": r["status"],
                                                "M03": row["M03-M-DISC"], "time_s": round(time.perf_counter() - t0, 1)}
                print(split, tid, name, out[f"{split}|{tid}|{name}"], flush=True)
    (HERE / "resolve_unknown.json").write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
