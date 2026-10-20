"""Mission 04 pilot P-R1c (protocol amendment 2): what do the conserved-but-unexplained tasks lack?

Same 9 partition rules and the same KEEP / RECOLOUR / CROP layer as P-R1; only the attribute table grows, one
generically constructed family at a time:
  FAM-INT    has_hole, is_rect, sym_h                       (intrinsic)
  FAM-COUNT  mult_colour, mult_shape, mult_size, unique_*   (aggregation over the block set: counting)
  FAM-REL    n_touch, inside_other, contains_other         (relations, from lattice adjacency between blocks)
  FAM-POS    top_rank, left_rank, bottom_rank, right_rank, dist_border
ARC-AGI-1 training split, DEV. Prints only task ids and outcome labels.

  python -I mission-04/experiments/r1_repr/run_r1c.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import blocks as B  # noqa: E402
import run_r1 as R  # noqa: E402

FAMS = {
    "INT": (["has_hole", "is_rect", "sym_h"], set()),
    "COUNT": (["mult_colour", "mult_shape", "mult_size", "unique_colour", "unique_shape", "unique_size"],
              {"mult_colour", "mult_shape", "mult_size"}),
    "REL": (["n_touch", "inside_other", "contains_other"], {"n_touch"}),
    "POS": (["top_rank", "left_rank", "bottom_rank", "right_rank", "dist_border"],
            {"top_rank", "left_rank", "bottom_rank", "right_rank", "dist_border"}),
}
CONFIGS = {"base": [], "+INT": ["INT"], "+COUNT": ["COUNT"], "+REL": ["REL"], "+POS": ["POS"],
           "+ALL": ["INT", "COUNT", "REL", "POS"]}


def bbox(b):
    rs, cs = [r for r, _ in b], [c for _, c in b]
    return min(rs), max(rs), min(cs), max(cs)


def has_hole(b):
    r0, r1, c0, c1 = bbox(b)
    free = {(r, c) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)} - set(b)
    reach = {x for x in free if x[0] in (r0, r1) or x[1] in (c0, c1)}
    stack = list(reach)
    while stack:
        r, c = stack.pop()
        for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            y = (r + d[0], c + d[1])
            if y in free and y not in reach:
                reach.add(y)
                stack.append(y)
    return len(free - reach) > 0


def features_ext(blocks, g, fams):
    fs = B.features(blocks, g)
    H, W = g.shape
    boxes = [bbox(b) for b in blocks]
    if "INT" in fams:
        for b, f, bx in zip(blocks, fs, boxes):
            f["has_hole"] = has_hole(b)
            f["is_rect"] = len(b) == f["bbox_h"] * f["bbox_w"]
            f["sym_h"] = f["shape"] == frozenset((r, f["bbox_w"] - 1 - c) for r, c in f["shape"])
    if "COUNT" in fams:
        for key in ("colour", "shape", "size"):
            vals = [f[key] for f in fs]
            for f in fs:
                m = vals.count(f[key])
                f[f"mult_{key}"] = m
                f[f"unique_{key}"] = m == 1
    if "REL" in fams:
        for i, (b, f) in enumerate(zip(blocks, fs)):
            near = {(r + dr, c + dc) for r, c in b for dr in (-1, 0, 1) for dc in (-1, 0, 1)}
            f["n_touch"] = sum(1 for j, o in enumerate(blocks) if j != i and near & o)
            r0, r1, c0, c1 = boxes[i]
            f["inside_other"] = any(j != i and o[0] <= r0 and r1 <= o[1] and o[2] <= c0 and c1 <= o[3] and o != boxes[i]
                                    for j, o in enumerate(boxes))
            f["contains_other"] = any(j != i and r0 <= o[0] and o[1] <= r1 and c0 <= o[2] and o[3] <= c1 and o != boxes[i]
                                      for j, o in enumerate(boxes))
    if "POS" in fams:
        def rank(vals, rev):
            u = sorted(set(vals), reverse=rev)
            return [u.index(v) for v in vals]
        tops = rank([bx[0] for bx in boxes], False)
        bots = rank([bx[1] for bx in boxes], True)
        lefts = rank([bx[2] for bx in boxes], False)
        rights = rank([bx[3] for bx in boxes], True)
        for k, (f, bx) in enumerate(zip(fs, boxes)):
            f.update(top_rank=tops[k], bottom_rank=bots[k], left_rank=lefts[k], right_rank=rights[k],
                     dist_border=min(bx[0], bx[2], H - 1 - bx[1], W - 1 - bx[3]))
    return fs


def names_for(fams):
    names, numeric = list(B.FEATURES), set(B.NUMERIC)
    for fam in fams:
        n, num = FAMS[fam]
        names += n
        numeric |= num
    return names, numeric


def candidate_phis(train_feats, names, numeric):
    phis = []
    for feat in names:
        vals = {f[feat] for fs in train_feats for f in fs}
        phis += [(feat, "eq", v) for v in vals]
        if feat in numeric:
            phis += [(feat, "max", None), (feat, "min", None)]
    return phis


def explanations(train, rule, fams):
    names, numeric = names_for(fams)
    parts = []
    for I, O in train:
        blocks = B.partition(I, rule)
        parts.append((I, O, blocks, features_ext(blocks, I, fams)))
    phis = candidate_phis([p[3] for p in parts], names, numeric)
    found = []
    if all(I.shape == O.shape for I, O in train):
        for phi in phis:
            if all(np.array_equal(B.keep_apply(I, b, f, phi), O) for I, O, b, f in parts):
                found.append((rule, "KEEP", phi))
        for feat in names:
            lut = B.recolour_fit(parts, feat)
            if lut is not None:
                found.append((rule, "RECOLOUR", (feat, tuple(sorted(lut.items(), key=repr)))))
    for variant in ("block", "box"):
        for phi in phis:
            if all((o := B.crop_apply(I, b, f, phi, variant)) is not None and np.array_equal(o, O) for I, O, b, f in parts):
                found.append((rule, f"CROP-{variant}", phi))
    return found


def predict(e, g, fams):
    rule, mech, params = e
    blocks = B.partition(g, rule)
    fs = features_ext(blocks, g, fams)
    if mech == "KEEP":
        return B.keep_apply(g, blocks, fs, params)
    if mech == "RECOLOUR":
        feat, items = params
        return B.recolour_apply(g, blocks, fs, feat, dict(items))
    return B.crop_apply(g, blocks, fs, params, mech.split("-")[1])


def decide(preds, truth):
    if not preds or any(p is None for p in preds):
        return "abstain"
    keys = {(p.shape, p.tobytes()) for p in preds}
    if len(keys) != 1:
        return "abstain"
    p = preds[0]
    return "correct" if p.shape == truth.shape and (p == truth).all() else "wrong"


def task_status(train, tests, fams):
    expl = []
    for rule in B.GRAMMAR:
        expl += [e for e in explanations(train, rule, fams)]
    res, rules_new = {}, set()
    for pol in ("S0", "S2"):
        labels = []
        for I, T in tests:
            preds = [predict(e, I, fams) for e in expl]
            if pol == "S2":
                preds = [p for p in preds if p is not None]
            labels.append(decide(preds, T))
        res[pol] = "correct" if all(l == "correct" for l in labels) else "wrong" if "wrong" in labels else "abstain"
    res["rules_with_explanations"] = sorted({e[0] for e in expl})
    return res


def main():
    t0 = time.perf_counter()
    tasks = {f.stem: R.load(f) for f in sorted(R.DATA.glob("*.json"))}
    r1b = json.loads((HERE / "r1b.json").read_text())["rows"]
    gap = sorted(t for t, (train, _) in tasks.items()
                 if any(B.law_K(train, r) or B.law_C(train, r) for r in B.GRAMMAR) and r1b[t]["S2"] != "correct")
    rows = {}
    for tid, (train, tests) in tasks.items():
        rows[tid] = {cfg: task_status(train, tests, fams) for cfg, fams in CONFIGS.items()}
        print(tid, {c: (v["S0"], v["S2"]) for c, v in rows[tid].items()}, flush=True)
    summary = {}
    for cfg in CONFIGS:
        for pol in ("S0", "S2"):
            st_all = [rows[t][cfg][pol] for t in rows]
            st_gap = [rows[t][cfg][pol] for t in gap]
            summary[f"{cfg}|{pol}"] = {"all_correct": st_all.count("correct"), "all_wrong": st_all.count("wrong"),
                                       "gap_correct": st_gap.count("correct"), "gap_wrong": st_gap.count("wrong")}
    gained = {cfg: sorted(t for t in gap if rows[t][cfg]["S2"] == "correct") for cfg in CONFIGS}
    outside_f1 = {cfg: sorted(t for t in gained[cfg]
                              if any(r not in B.F1_LIST for r in rows[t][cfg]["rules_with_explanations"]))
                  for cfg in CONFIGS}
    out = {"label": "ARC-AGI-1 training split, DEV", "gap_tasks": gap, "summary": summary, "gap_gained_S2": gained,
           "gained_with_non_F1_rules": outside_f1, "rows": rows, "time_s": round(time.perf_counter() - t0, 1)}
    (HERE / "r1c.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=1, default=str))


if __name__ == "__main__":
    main()
