"""Library validation: the achiever contracts, by exhaustive bounded checking at N = 3..5 (amendment 1, item 6).

For every achiever instance a (atom type, variant, and for ZONE its side and width) with role colours A1 (, A2):
  progress[a]      in every state where a's atom is violated but feasible and a spare cell exists, the selection
                   applies and one relocation strictly decreases a's measure
  preserves[a][g]  for every atom pattern g over roles {A1, A2, X1, X2}: in every state where g holds, a's atom is
                   violated, g and a's atom are jointly satisfiable and a spare cell exists, one relocation keeps g
States: objects of colours A1=1, A2=2, X1=3, X2=4, K <= N-1; hazard subsets of size <= 2 of the empty cells (with the
hazard rule on); NO_PICK on X2 or on nothing. The table is the union over both settings (conservative). Agent position
does not affect the relocation's effect, so it is fixed at 0. Generalisation beyond N = 5 is an assumption [P].

  python -I libval.py        # writes contract_table.json
"""

from __future__ import annotations

import itertools
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from model import holds, measure, reloc, satisfiable, select  # noqa: E402

ROLE = {"A1": 1, "A2": 2, "X1": 3, "X2": 4}
WS = (2, "half")


def achiever_instances():
    out = []
    for v in ("O1", "O2"):
        out.append((f"ORDER:{v}", ["ORDER", "A1", "A2"], v))
    for v in ("Z1", "Z2"):
        for side in ("left", "right"):
            for w in WS:
                out.append((f"ZONE:{v}:{side}:{w}", ["ZONE", "A1", side, w], v))
    for v in ("G1", "G2"):
        out.append((f"GROUP:{v}", ["GROUP", "A1"], v))
    return out


def patterns(roles):
    out = []
    for p, q in itertools.permutations(roles, 2):
        out.append(["ORDER", p, q])
    for p in roles:
        for side in ("left", "right"):
            for w in WS:
                out.append(["ZONE", p, side, w])
        out.append(["GROUP", p])
    return out


def key(atom):
    return atom[0] + "(" + ",".join(str(x) for x in atom[1:]) + ")"


def states(N):
    for K in range(1, N):
        for pos in itertools.combinations(range(N), K):
            free = [p for p in range(N) if p not in pos]
            for cols in itertools.product((1, 2, 3, 4), repeat=K):
                cells = [0] * N
                for p, c in zip(pos, cols):
                    cells[p] = c
                for r in range(3):
                    for hz in itertools.combinations(free, r):
                        haz = tuple(1 if p in hz else 0 for p in range(N))
                        for fixed in ((), (4,)):
                            yield tuple(cells), haz, fixed


def main():
    t0 = time.perf_counter()
    b = ROLE
    ach = achiever_instances()
    progress = {k: {"ok": True, "states": 0, "cex": None} for k, _, _ in ach}
    pres = {}
    for k, a, v in ach:
        roles = ["A1", "A2", "X1", "X2"] if a[0] == "ORDER" else ["A1", "X1", "X2"]
        pres[k] = {key(gp): {"ok": True, "states": 0, "cex": None} for gp in patterns(roles) if key(gp) != key(a)}
    for N in (3, 4, 5):
        for cells, haz, fixed in states(N):
            for k, a, v in ach:
                if holds(a, cells, b):
                    continue
                if any(cells[p] == 0 and not haz[p] for p in range(N)) is False:
                    continue
                if not satisfiable([a], cells, haz, True, fixed, b):
                    continue
                # progress
                pr = progress[k]
                pr["states"] += 1
                sel = select(a, v, cells, haz, True, fixed, b)
                r = reloc(cells, 0, sel[0], sel[1], haz, True) if sel else None
                ok = r is not None and measure(a, r[0], b, haz, True, fixed, v) < measure(a, cells, b, haz, True, fixed, v)
                if not ok and pr["ok"]:
                    pr["ok"], pr["cex"] = False, {"cells": cells, "haz": haz, "fixed": fixed}
                if r is None:
                    continue
                after = r[0]
                for gk, ent in pres[k].items():
                    gp = _parse(gk)
                    if not holds(gp, cells, b):
                        continue
                    if not satisfiable([a, gp], cells, haz, True, fixed, b):
                        continue
                    ent["states"] += 1
                    if not holds(gp, after, b) and ent["ok"]:
                        ent["ok"], ent["cex"] = False, {"cells": cells, "haz": haz, "fixed": fixed, "after": after}
        print("N", N, "done", round(time.perf_counter() - t0, 1), flush=True)
    out = {"label": "library validation: achiever contracts by exhaustive checking at N = 3..5 (bounded, [M] up to N = 5)",
           "progress": progress, "preserves": pres, "time_s": round(time.perf_counter() - t0, 1),
           "summary": {"achievers": len(ach), "pairs": sum(len(v) for v in pres.values()),
                       "preserving_pairs": sum(e["ok"] for v in pres.values() for e in v.values()),
                       "progress_ok": sum(p["ok"] for p in progress.values())}}
    (HERE / "contract_table.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(out["summary"]), "time", out["time_s"])


def _parse(gk):
    t, rest = gk.split("(", 1)
    args = rest[:-1].split(",")
    if t == "ZONE":
        return [t, args[0], args[1], args[2] if args[2] == "half" else int(args[2])]
    return [t] + args


if __name__ == "__main__":
    main()
