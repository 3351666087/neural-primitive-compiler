"""Follow-up to L2 (exploration ledger round 1).

Observation: the generic prior "unions of unimodular affine maps, clipped once at the end" fits 23/25 commands
but has no cover for DILATE-then-LEFT and DILATE-then-DOWN. Hypothesis C1: the prior fails because it is not
closed under composition: a clip in the middle of a composite restricts the *domain* of each affine piece,
which an end-of-map clip cannot express. Competing hypothesis C2: the two commands need more than 5 pieces
(the cover size bound, not the representation, is the limit).

Test: enlarge each piece to a partial affine map restricted to a box domain lo <= x <= hi, lo <= y <= hi,
with lo in {0, 1, 2} and hi in {N-1, N-2, N-3} (a minimal composition-closed extension for these maps), and
keep the 5-piece bound. C1 predicts covers for both commands; C2 predicts none. Also measured: how much the
richer prior increases ambiguity (minimal covers that agree on N = 3, 5 but disagree at N = 8, 11) on all
25 commands. Selection never looks at N = 8, 11; they are used only to group identical hypotheses and score.

  python mission-03/experiments/p0_leakage/l2_closure.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_leakage import GENERIC, UNSEEN, generate, learn, active_refine, relation_from_table, run_reference, true_relation  # noqa: E402

PROBES, HORIZON = (3, 5), (8, 11)
LO, HI = (0, 1, 2), (0, 1, 2)   # x >= LO[i], x <= N-1-HI[j]
CAP = 200


def piece_graph(g, box, N):
    A, (cx, dx), (cy, dy), mode = g
    lx, hx, ly, hy = box
    out = set()
    for x in range(lx, N - hx):
        for y in range(ly, N - hy):
            X = A[0] * x + A[1] * y + cx * (N - 1) + dx
            Y = A[2] * x + A[3] * y + cy * (N - 1) + dy
            if mode == "wrap":
                X, Y = X % N, Y % N
            elif not (0 <= X < N and 0 <= Y < N):
                continue
            out.add(((x, y), (X, Y)))
    return frozenset(out)


BOXES = [(a, b, c, d) for a in LO for b in HI for c in LO for d in HI]
_FULL = {}


def full_graphs():
    """Unrestricted (end-clipped) graph of every generic map, as point lists, at probe and horizon sizes."""
    if not _FULL:
        for gi, g in enumerate(GENERIC):
            _FULL[gi] = {N: sorted(piece_graph(g, (0, 0, 0, 0), N)) for N in (*PROBES, *HORIZON)}
    return _FULL


def restrict(points, box, N):
    lx, hx, ly, hy = box
    return frozenset(pq for pq in points if lx <= pq[0][0] <= N - 1 - hx and ly <= pq[0][1] <= N - 1 - hy)


def candidates(rels):
    """Box-restricted pieces whose probe graphs are non-empty subsets of the relation. Only pieces that are
    maximal at the probe sizes are kept (a dominated piece can be swapped for its dominator in any minimum
    cover), so the ambiguity reported below is a LOWER bound."""
    seen = {}
    for gi, fg in full_graphs().items():
        if not all(any(pq in rels[N] for pq in fg[N]) for N in PROBES):
            continue
        for box in BOXES:
            pg = tuple(restrict(fg[N], box, N) for N in PROBES)
            if not all(pg[i] and pg[i] <= rels[N] for i, N in enumerate(PROBES)):
                continue
            hg = tuple(restrict(fg[N], box, N) for N in HORIZON)
            seen.setdefault(pg + hg, (pg, hg))
    cands = list(seen.values())
    maximal = [c for c in cands if not any(o[0] != c[0] and all(c[0][i] <= o[0][i] for i in range(len(PROBES))) for o in cands)]
    return maximal


def min_covers(cands, rels, kmax=5):
    """Exact minimum covers (union equals the relation at both probe sizes), by branching on an uncovered pair."""
    target = {N: rels[N] for N in PROBES}
    best, found = None, []

    def rec(chosen, covered, k):
        nonlocal best
        if best is not None and k > best:
            return
        missing = [(i, p) for i, N in enumerate(PROBES) for p in target[N] - covered[i]]
        if not missing:
            if best is None or k < best:
                best, found[:] = k, []
            if len(found) < CAP:
                found.append(tuple(chosen))
            return
        if k == kmax:
            return
        i, p = missing[0]
        for idx, (pg, _) in enumerate(cands):
            if p in pg[i]:
                rec(chosen + [idx], [covered[j] | pg[j] for j in range(len(PROBES))], k + 1)

    rec([], [frozenset() for _ in PROBES], 0)
    uniq = {tuple(sorted(c)) for c in found}
    return [list(c) for c in uniq]


def main():
    seed = json.loads((UNSEEN / "tasks.json").read_text())["seed"]
    rows = []
    t0 = time.perf_counter()
    for u in generate(seed):
        if u.family != "A":
            continue
        probe = {N: u.build(N) for N in PROBES}
        learned = {}
        for N, t in probe.items():
            iface = t.interface()
            orc = lambda tr, T, t=t: run_reference(t, tr, T)
            learned[N] = active_refine(iface, orc, learn(iface, orc, n_traces=300, T=16, seed=1))
        for name, _ in u.params["commands"]:
            rels = {N: relation_from_table(learned[N].letters[name]) for N in PROBES}
            cands = candidates(rels)
            covers = min_covers(cands, rels)
            preds = {}
            for c in covers:
                for j, N in enumerate(HORIZON):
                    preds.setdefault(N, set()).add(frozenset().union(*(cands[i][1][j] for i in c)) if c else frozenset())
            truth = {N: true_relation(u.build(N), name) for N in HORIZON}
            verdict = ("no cover" if not covers else
                       "correct" if all(preds[N] == {truth[N]} for N in HORIZON) else
                       "ambiguous" if any(len(preds[N]) > 1 for N in HORIZON) else "wrong")
            n_ok = sum(all(frozenset().union(*(cands[i][1][j] for i in c)) == truth[N] for j, N in enumerate(HORIZON)) for c in covers)
            row = {"uid": u.uid, "command": name, "moves": dict(u.params["commands"])[name], "pieces_consistent": len(cands),
                   "minimal_covers": len(covers), "cover_size": len(covers[0]) if covers else None,
                   "covers_correct_at_horizon": n_ok, "verdict": verdict}
            print(row, flush=True)
            rows.append(row)
    summary = {"commands": len(rows), "correct": sum(r["verdict"] == "correct" for r in rows),
               "ambiguous": sum(r["verdict"] == "ambiguous" for r in rows), "no_cover": sum(r["verdict"] == "no cover" for r in rows),
               "wrong": sum(r["verdict"] == "wrong" for r in rows), "time_s": round(time.perf_counter() - t0, 1)}
    print(summary)
    (HERE / "l2_closure.json").write_text(json.dumps({"rows": rows, "summary": summary, "cover_cap": CAP}, indent=1, default=str))


if __name__ == "__main__":
    main()
