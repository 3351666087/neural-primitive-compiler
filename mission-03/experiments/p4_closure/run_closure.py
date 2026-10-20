"""Mission 03 round R6: is closure of the prior a predictive principle? (protocol amendment 8, locked before
this file was written.)

Concept = the gating region of a conditional command. Identification uses only the two-sided union-consistency
test (both branches must be union maps); branch maps are not fitted here.

Libraries are built ONLY from the training tasks:
  L_mem     regions found in training tasks by the list-free route (Z3 + edge-anchored interval description)
  L_D4      closure of L_mem under the dihedral group of the square (supplied by the designer)
  L_disc    closure of L_mem under the plain-command maps DISCOVERED in the training tasks (piecewise-affine
            fits from passive data), iterated up to 3 rounds; images without an interval description are dropped
  L_rand    L_mem plus random interval descriptions, padded to |L_D4| (5 draws)
  L_generic all 1,296 interval descriptions
  L_none    no library: Z3 invents the region, the interval prior extends it

Held-out tasks are generated from the seed below and observed only after the libraries are built.

  python mission-03/experiments/p4_closure/run_closure.py
"""

from __future__ import annotations

import hashlib
import itertools
import json
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "mission-03" / "experiments" / "p1_composition"))
sys.path.insert(0, str(REPO / "mission-03" / "experiments" / "p1b_concept"))

from cog.tasks import Letter, Output, Task, grid, grid_point_maps, pmap  # noqa: E402
from cog.unseen import A_POOL  # noqa: E402
import cond_fit as C  # noqa: E402
from run_concept import solve  # noqa: E402
from run_p1 import at_delay, change_delays, letter_events, observe  # noqa: E402

PROBES, HORIZON, ALL = (3, 5), (8, 11), (3, 5, 8, 11)
SIZES_N = (10, 30, 100, 300, 1000)
TRAIN_REGIONS = {"top row": ("0", "N-1", "0", "0"), "top-left 2x2": ("0", "1", "0", "1")}
HELDOUT = {  # name: (interval description, relation to the training regions)
    "bottom row": (("0", "N-1", "N-1", "N-1"), "D4"),
    "left column": (("0", "0", "0", "N-1"), "D4"),
    "bottom-right 2x2": (("N-2", "N-1", "N-2", "N-1"), "D4"),
    "right column": (("N-1", "N-1", "0", "N-1"), "D4"),
    "second row": (("0", "N-1", "1", "1"), "shift"),
    "top-left 2x2 moved right": (("1", "2", "0", "1"), "shift"),
}


class Cond:
    """LOAD + two plain one-move commands + one conditional command gated by an interval region."""

    def __init__(self, uid, cmds, region, then_m, else_m, D):
        self.uid, self.cmds, self.region, self.then_m, self.else_m, self.D = uid, cmds, region, then_m, else_m, D
        self.params = {"commands": [(f"CMD{i}", [m]) for i, m in enumerate(cmds)],
                       "cond": ("CMD2", region, [then_m], [else_m], D)}

    def build(self, N):
        sp = grid(N)
        pm = grid_point_maps(N)
        letters = [Letter("LOAD", lambda S, f: frozenset(c for c in sp.coords if f.get("see_" + "_".join(map(str, c)), 0)), data="see")]
        for i, m in enumerate(self.cmds):
            letters.append(Letter(f"CMD{i}", pmap(pm[m], sp.coords)))
        R = C.interval_region(self.region, N)
        fa, fb = pmap(pm[self.then_m], sp.coords), pmap(pm[self.else_m], sp.coords)
        letters.append(Letter("CMD2", lambda S, f, R=R, fa=fa, fb=fb: fa(S, f) if S & R else fb(S, f), cond_delay=self.D))
        return Task(f"{self.uid}@{N}", "A", sp, letters, {"see": sp}, {}, [Output("img", "img", 2)], "", self.D)


def make_tasks():
    h = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    rng = random.Random(int(h[:16], 16))

    def one(uid, region):
        then_m, else_m = rng.sample(A_POOL, 2)
        return Cond(uid, rng.sample(A_POOL, 2), region, then_m, else_m, rng.choice([3, 4]))
    train = [one(f"T{i}", list(TRAIN_REGIONS.values())[i % 2]) for i in range(6)]
    test = [one(f"H{i}", desc) for i, (desc, _) in enumerate(HELDOUT.values())]
    return h, train, test


# ------------------------------------------------------------------ fast two-sided union test
def masks(pairs, coords):
    idx = {c: i for i, c in enumerate(coords)}
    m = lambda S: sum(1 << idx[c] for c in S)
    return [(m(a), m(b)) for a, b in pairs]


def union_ok(ev, ncell):
    for j in range(ncell):
        bit = 1 << j
        cand = (1 << ncell) - 1
        for a, b in ev:
            if not b & bit:
                cand &= ~a
        for a, b in ev:
            if b & bit and not a & cand:
                return False
    return True


def region_mask(R, coords):
    idx = {c: i for i, c in enumerate(coords)}
    return sum(1 << idx[c] for c in R)


def consistent(desc_regions, ev_by_N, coords_by_N, cache):
    """desc_regions: {N: region set}; both sides union-consistent at both probe sizes (cached per region)."""
    for N in PROBES:
        R = region_mask(desc_regions[N], coords_by_N[N])
        key = (N, R)
        if key not in cache:
            ev = ev_by_N[N]
            a = [e for e in ev if e[0] & R]
            b = [e for e in ev if not e[0] & R]
            n = len(coords_by_N[N])
            cache[key] = bool(a) and bool(b) and union_ok(a, n) and union_ok(b, n)
        if not cache[key]:
            return False
    return True


# ------------------------------------------------------------------ region algebra
def inst(desc):
    return {N: C.interval_region(desc, N) for N in ALL}


_INDEX = {}


def describe_all(instances):
    """Interval descriptions matching a region at every size in `instances` (instances must cover ALL sizes)."""
    if not _INDEX:
        for d in C.INTERVALS:
            _INDEX.setdefault(tuple(frozenset(C.interval_region(d, N)) for N in ALL), d)
    d = _INDEX.get(tuple(frozenset(instances[N]) for N in ALL))
    return [d] if d else []


D4 = [lambda x, y, M: (x, y), lambda x, y, M: (M - y, x), lambda x, y, M: (M - x, M - y), lambda x, y, M: (y, M - x),
      lambda x, y, M: (M - x, y), lambda x, y, M: (x, M - y), lambda x, y, M: (y, x), lambda x, y, M: (M - y, M - x)]


def close(library, ops, rounds):
    """library: set of descriptions; ops: functions (N, region) -> region. Returns the closure (descriptions)."""
    lib = set(library)
    for _ in range(rounds):
        new = set()
        for d in lib:
            I = inst(d)
            for op in ops:
                img = {N: frozenset(op(N, I[N])) for N in ALL}
                if any(not img[N] for N in ALL):
                    continue
                ds = describe_all(img)
                if ds:
                    new.add(ds[0])
        if new <= lib:
            break
        lib |= new
    return lib


def canon(desc):
    return tuple(frozenset(C.interval_region(desc, N)) for N in ALL)


def dedupe(lib):
    return list({canon(d): d for d in lib}.values())


# ------------------------------------------------------------------ discovery inside training tasks
def discovered_map(u, cmd, data):
    probe = {N: u.build(N) for N in PROBES}
    ev = {N: at_delay(letter_events(probe[N], data[N], cmd), 0) for N in PROBES}
    fit, why = C.branch_fit(ev, {N: probe[N].space.coords for N in PROBES})
    if fit is None or len(fit[1]) != 1:
        return None
    pieces, (cover,) = fit
    rel = {}
    for N in ALL:
        if N in PROBES:
            rel[N] = frozenset().union(*(pieces[i][0][PROBES.index(N)] for i in cover))
        else:
            rel[N] = frozenset().union(*(pieces[i][1][HORIZON.index(N)] for i in cover))
    return rel


def free_region(pairs, coords):
    out, R = solve(pairs, coords, "region")
    return R, out.get("second_solution") == "unsat"


def events_for(u, n_traces):
    data = {N: observe(u.build(N), n=n_traces) for N in PROBES}
    ev = {N: letter_events(u.build(N), data[N], "CMD2") for N in PROBES}
    ds = set.intersection(*(change_delays(ev[N])[0] for N in PROBES))
    if len(ds) != 1:
        return None, data
    d = min(ds)
    return {N: at_delay(ev[N], d) for N in PROBES}, data


def identify(lib, pairs, truth_desc):
    coords = {N: grid(N).coords for N in PROBES}
    evm = {N: masks(pairs[N], coords[N]) for N in PROBES}
    cache = {}
    cons = [d for d in lib if consistent({N: C.interval_region(d, N) for N in PROBES}, evm, coords, cache)]
    classes = {tuple(frozenset(C.interval_region(d, N)) for N in HORIZON) for d in cons}
    truth = tuple(frozenset(C.interval_region(truth_desc, N)) for N in HORIZON)
    if not classes:
        return "none"
    if len(classes) > 1:
        return "ambiguous" if truth in classes else "ambiguous (truth absent)"
    return "correct" if classes == {truth} else "wrong"


def main():
    t0 = time.perf_counter()
    h, train, test = make_tasks()
    out = {"script_sha256": h, "train": {u.uid: u.params for u in train}, "test": {u.uid: u.params for u in test}}
    # ---- libraries from training tasks only
    L_mem, maps, mem_detail = set(), [], {}
    for u in train:
        pairs, data = events_for(u, 1000)
        if pairs is None:
            mem_detail[u.uid] = "delay not identified"
            continue
        regs = {}
        for N in PROBES:
            R, uniq = free_region(pairs[N], grid(N).coords)
            regs[N] = R
        descs = C.describe_region(regs) if all(r is not None for r in regs.values()) else []
        mem_detail[u.uid] = [list(d) for d in descs]
        L_mem |= set(descs[:1])
        for i in range(2):
            rel = discovered_map(u, f"CMD{i}", data)
            if rel is not None:
                maps.append((u.uid, u.cmds[i], rel))
    L_mem = set(dedupe(L_mem))
    d4_ops = [lambda N, R, g=g: {g(x, y, N - 1) for x, y in R} for g in D4]
    disc_ops = [lambda N, R, rel=rel: {q for p, q in rel[N] if p in R} for _, _, rel in maps]
    L_D4 = set(dedupe(close(L_mem, d4_ops, 1)))
    L_disc = set(dedupe(close(L_mem, disc_ops, 3)))
    rng = random.Random(7)
    L_rands = []
    for _ in range(5):
        pad = set(L_mem)
        while len(pad) < len(L_D4):
            pad.add(rng.choice(C.INTERVALS))
        L_rands.append(pad)
    L_generic = C.INTERVALS
    out["libraries"] = {"L_mem": [list(d) for d in L_mem], "L_D4": [list(d) for d in L_D4], "L_disc": [list(d) for d in L_disc],
                        "L_rand_size": len(L_D4), "L_generic_size": len(L_generic), "train_regions_found": mem_detail,
                        "discovered_maps": [(uid, m) for uid, m, _ in maps]}
    print("libraries:", {k: len(v) if isinstance(v, list) else v for k, v in out["libraries"].items() if k.startswith("L_")}, flush=True)
    print("discovered maps:", out["libraries"]["discovered_maps"], flush=True)
    covered = {name: {"L_D4": canon(desc) in {canon(d) for d in L_D4}, "L_disc": canon(desc) in {canon(d) for d in L_disc},
                      "L_mem": canon(desc) in {canon(d) for d in L_mem}} for name, (desc, _) in HELDOUT.items()}
    out["coverage"] = covered
    print("coverage:", covered, flush=True)
    # ---- held-out tasks, observed only now
    rows = []
    for u, (name, (desc, kind)) in zip(test, HELDOUT.items()):
        full, data = events_for(u, 1000)
        for n in SIZES_N:
            pairs, _ = events_for(u, n) if n != 1000 else (full, data)
            row = {"task": u.uid, "region": name, "kind": kind, "n_traces": n}
            if pairs is None:
                row.update({k: "delay not identified" for k in ("L_mem", "L_D4", "L_disc", "L_rand", "L_generic", "L_none")})
            else:
                row["events"] = {str(N): len(pairs[N]) for N in PROBES}
                row["L_mem"] = identify(L_mem, pairs, desc)
                row["L_D4"] = identify(L_D4, pairs, desc)
                row["L_disc"] = identify(L_disc, pairs, desc)
                row["L_rand"] = [identify(L, pairs, desc) for L in L_rands]
                row["L_generic"] = identify(L_generic, pairs, desc)
                regs = {}
                for N in PROBES:
                    R, uniq = free_region(pairs[N], grid(N).coords)
                    regs[N] = (R, uniq)
                if any(R is None for R, _ in regs.values()):
                    row["L_none"] = "none"
                elif not all(uq for _, uq in regs.values()):
                    row["L_none"] = "ambiguous"
                else:
                    ds = C.describe_region({N: R for N, (R, _) in regs.items()})
                    preds = {tuple(frozenset(C.interval_region(d, N)) for N in HORIZON) for d in ds}
                    truth = tuple(frozenset(C.interval_region(desc, N)) for N in HORIZON)
                    row["L_none"] = "none" if not preds else "correct" if preds == {truth} else "ambiguous" if len(preds) > 1 else "wrong"
            print(row, flush=True)
            rows.append(row)
    out["rows"] = rows
    out["time_s"] = round(time.perf_counter() - t0, 1)
    (HERE / "closure.json").write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
