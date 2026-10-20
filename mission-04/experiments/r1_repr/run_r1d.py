"""Mission 04 pilot P-R1d (protocol amendment 3): which structure inside blocks explains non-uniform recolouring?

Mechanism "colour inside blocks by a lookup": every block cell x gets colour h(key(x)), with key either the cell
attribute alone or (block colour, cell attribute); h is learned from the training pairs; non-block cells must be
background in the output. Cell attributes, by family:
  W1 boundary   border4, border8, depth4 (4-neighbour distance to the outside of the block)
  W2 position   r_rel, c_rel, r_from_bottom, c_from_right, r_par, c_par, rc_par, on_bbox_edge
  W3 relation   adj_other (8-adjacent to another block), line_other (another block in the same row or column)
All 9 partition rules; same-size tasks only. ARC-AGI-1 training split, DEV. Prints only ids and labels.

  python -I mission-04/experiments/r1_repr/run_r1d.py
"""

from __future__ import annotations

import json
import sys
import time
from collections import deque
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import blocks as B  # noqa: E402
import run_r1 as R  # noqa: E402

FAMILY = {"W1": ["border4", "border8", "depth4"],
          "W2": ["r_rel", "c_rel", "r_from_bottom", "c_from_right", "r_par", "c_par", "rc_par", "on_bbox_edge"],
          "W3": ["adj_other", "line_other"]}
N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
N8 = N4 + ((1, 1), (1, -1), (-1, 1), (-1, -1))


def cell_attrs(g, blocks):
    """dict cell -> dict of attributes, for every block cell."""
    owner = {}
    for i, b in enumerate(blocks):
        for x in b:
            owner[x] = i
    rows_of, cols_of = {}, {}
    for i, b in enumerate(blocks):
        for r, c in b:
            rows_of.setdefault(r, set()).add(i)
            cols_of.setdefault(c, set()).add(i)
    out = {}
    for i, b in enumerate(blocks):
        rs, cs = [r for r, _ in b], [c for _, c in b]
        r0, r1, c0, c1 = min(rs), max(rs), min(cs), max(cs)
        depth, q = {}, deque()
        for x in b:
            if any((x[0] + d[0], x[1] + d[1]) not in b for d in N4):
                depth[x] = 1
                q.append(x)
        while q:
            x = q.popleft()
            for d in N4:
                y = (x[0] + d[0], x[1] + d[1])
                if y in b and y not in depth:
                    depth[y] = depth[x] + 1
                    q.append(y)
        for x in b:
            r, c = x
            out[x] = {
                "border4": any((r + d[0], c + d[1]) not in b for d in N4),
                "border8": any((r + d[0], c + d[1]) not in b for d in N8),
                "depth4": depth.get(x, 0),
                "r_rel": r - r0, "c_rel": c - c0, "r_from_bottom": r1 - r, "c_from_right": c1 - c,
                "r_par": (r - r0) % 2, "c_par": (c - c0) % 2, "rc_par": ((r - r0) % 2, (c - c0) % 2),
                "on_bbox_edge": r in (r0, r1) or c in (c0, c1),
                "adj_other": any(owner.get((r + d[0], c + d[1]), i) != i for d in N8),
                "line_other": bool((rows_of.get(r, set()) | cols_of.get(c, set())) - {i}),
                "_block_colour": B.features([b], g)[0]["colour"],
            }
    return out


def fit(train, rule, attr, keyed):
    lut = {}
    for I, O in train:
        if I.shape != O.shape:
            return None
        blocks = B.partition(I, rule)
        if not blocks:
            return None
        ca = cell_attrs(I, blocks)
        covered = np.zeros(I.shape, bool)
        for x, a in ca.items():
            k = (a["_block_colour"], a[attr]) if keyed else a[attr]
            if lut.setdefault(k, int(O[x])) != int(O[x]):
                return None
            covered[x] = True
        if (O[~covered] != 0).any():
            return None
    return lut


def apply(g, rule, attr, keyed, lut):
    blocks = B.partition(g, rule)
    out = np.zeros_like(g)
    for x, a in cell_attrs(g, blocks).items():
        k = (a["_block_colour"], a[attr]) if keyed else a[attr]
        if k not in lut:
            return None
        out[x] = lut[k]
    return out


def decide(preds, truth):
    if not preds or any(p is None for p in preds):
        return "abstain"
    if len({p.tobytes() for p in preds}) != 1:
        return "abstain"
    return "correct" if preds[0].shape == truth.shape and (preds[0] == truth).all() else "wrong"


def task(train, tests, families):
    expl = []
    for rule in B.GRAMMAR:
        for fam in families:
            for attr in FAMILY[fam]:
                for keyed in (False, True):
                    lut = fit(train, rule, attr, keyed)
                    if lut is not None:
                        expl.append((rule, attr, keyed, lut))
    res = {}
    for pol in ("S0", "S2"):
        labels = []
        for I, T in tests:
            preds = [apply(I, r, a, k, l) for r, a, k, l in expl]
            if pol == "S2":
                preds = [p for p in preds if p is not None]
            labels.append(decide(preds, T))
        res[pol] = "correct" if all(l == "correct" for l in labels) else "wrong" if "wrong" in labels else "abstain"
    res["attrs"] = sorted({a for _, a, _, _ in expl})
    res["rules"] = sorted({r for r, _, _, _ in expl})
    return res


def main():
    t0 = time.perf_counter()
    diag = json.loads((HERE / "gap_diagnostics.json").read_text())["rows"]
    target = sorted(t for t, r in diag.items() if r["category"] == "K: non-uniform recolouring inside blocks")
    configs = {"W1": ["W1"], "W2": ["W2"], "W3": ["W3"], "W123": ["W1", "W2", "W3"]}
    rows = {}
    for f in sorted(R.DATA.glob("*.json")):
        train, tests = R.load(f)
        if not all(I.shape == O.shape for I, O in train):
            continue
        rows[f.stem] = {c: task(train, tests, fams) for c, fams in configs.items()}
        print(f.stem, {c: (v["S0"], v["S2"]) for c, v in rows[f.stem].items()}, flush=True)
    summary = {}
    for c in configs:
        for pol in ("S0", "S2"):
            st_t = [rows[t][c][pol] for t in target if t in rows]
            st_a = [r[c][pol] for r in rows.values()]
            summary[f"{c}|{pol}"] = {"target_correct": st_t.count("correct"), "target_wrong": st_t.count("wrong"),
                                     "all_correct": st_a.count("correct"), "all_wrong": st_a.count("wrong")}
    solved = {c: sorted(t for t in target if t in rows and rows[t][c]["S2"] == "correct") for c in configs}
    reuse = {}
    for t, r in rows.items():
        if r["W123"]["S2"] == "correct":
            for a in r["W123"]["attrs"]:
                reuse[a] = reuse.get(a, 0) + 1
    out = {"label": "ARC-AGI-1 training split, DEV", "target_tasks": target, "summary": summary,
           "target_solved_S2": solved, "attribute_reuse_on_solved_tasks": dict(sorted(reuse.items(), key=lambda kv: -kv[1])),
           "wrong_tasks": {c: sorted(t for t, r in rows.items() if r[c]["S0"] == "wrong" or r[c]["S2"] == "wrong") for c in configs},
           "rows": rows, "time_s": round(time.perf_counter() - t0, 1)}
    (HERE / "r1d.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=1, default=str))


if __name__ == "__main__":
    main()
