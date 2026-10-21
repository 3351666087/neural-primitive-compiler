"""Constructor-side model of LINE at the level of macros. CONSTRUCTOR SIDE: imports nothing from the judge.

This is the library's own knowledge of the environment (shared prior, A05_KNOWLEDGE_LEDGER.md): atom semantics,
the achiever selection rules, and the effect and step cost of the relocation macro. It is used by library
validation (contracts), by A-SAME (macro-level simulation) and as the specification that cirgen.py implements.

Relocation macro RELOC(x, y): the object at y moves to x; if x held an object, that object ends at y (through the
spare cell s = leftmost free allowed cell). Step cost: 1 (the start step, which loads the registers) plus, for each
visited target, the walk to it and one PICK or DROP. Targets: x, s, y, x, s, y if x was occupied, else y, x.
"""

from __future__ import annotations

from functools import lru_cache

VARIANTS = {"ORDER": ("O1", "O2"), "ZONE": ("Z1", "Z2"), "GROUP": ("G1", "G2")}


def zcells(N, side, w):
    w = N // 2 if w == "half" else int(w)
    return range(w) if side == "left" else range(N - w, N)


def rc(c, b):
    return b.get(c, c) if isinstance(c, str) else c


def holds(atom, cells, b):
    N = len(cells)
    t = atom[0]
    if t == "ORDER":
        c1, c2 = rc(atom[1], b), rc(atom[2], b)
        first2 = next((p for p in range(N) if cells[p] == c2), N)
        return not any(cells[p] == c1 for p in range(first2, N))
    if t == "ZONE":
        c = rc(atom[1], b)
        z = set(zcells(N, atom[2], atom[3]))
        return all(cells[p] != c or p in z for p in range(N))
    if t == "GROUP":
        c = rc(atom[1], b)
        ps = [p for p in range(N) if cells[p] == c]
        return not ps or ps[-1] - ps[0] + 1 == len(ps)
    raise ValueError(atom)


def measure(atom, cells, b, haz=None, rule=False, fixedcols=(), variant="G1"):
    """Progress measure of the achiever of `atom` (smaller is better; 0 iff the atom holds for ORDER/ZONE)."""
    N = len(cells)
    if atom[0] == "ORDER":
        c1, c2 = rc(atom[1], b), rc(atom[2], b)
        return sum(1 for p in range(N) for q in range(p + 1, N) if cells[p] == c2 and cells[q] == c1)
    if atom[0] == "ZONE":
        c = rc(atom[1], b)
        z = set(zcells(N, atom[2], atom[3]))
        return sum(1 for p in range(N) if cells[p] == c and p not in z)
    win = group_window(atom, cells, b, haz, rule, fixedcols, variant)
    c = rc(atom[1], b)
    if win is None:
        return None
    return sum(1 for p in range(N) if cells[p] == c and p not in win)


def allowed_free(cells, haz, rule):
    return [p for p in range(len(cells)) if cells[p] == 0 and not (rule and haz[p])]


def group_window(atom, cells, b, haz, rule, fixedcols, variant):
    c = rc(atom[1], b)
    N = len(cells)
    cnt = sum(1 for x in cells if x == c)
    ok = [not (rule and haz[p]) and not (cells[p] != 0 and cells[p] != c and cells[p] in fixedcols) for p in range(N)]
    starts = [s for s in range(N - cnt + 1) if all(ok[s:s + cnt])]
    if not starts:
        return None
    s = starts[0] if variant == "G1" else starts[-1]
    return set(range(s, s + cnt))


def select(atom, variant, cells, haz, rule, fixedcols, b):
    """(x, y): move the object at y to cell x (an object at x, if any, ends at y). None if not applicable."""
    N = len(cells)
    t = atom[0]
    if t == "ORDER":
        c1, c2 = rc(atom[1], b), rc(atom[2], b)
        if c1 in fixedcols or c2 in fixedcols:
            return None
        p2 = [p for p in range(N) if cells[p] == c2]
        p1 = [p for p in range(N) if cells[p] == c1]
        if not p1 or not p2:
            return None
        x = p2[0]
        if variant == "O1":
            y = p1[-1]
        else:
            right = [p for p in p1 if p > x]
            y = right[0] if right else -1
        return (x, y) if y > x else None
    if t == "ZONE":
        c = rc(atom[1], b)
        if c in fixedcols:
            return None
        z = set(zcells(N, atom[2], atom[3]))
        elig = [p for p in z if (cells[p] == 0 and not (rule and haz[p])) or
                (cells[p] != 0 and cells[p] != c and cells[p] not in fixedcols)]
        out = [p for p in range(N) if cells[p] == c and p not in z]
        if not elig or not out:
            return None
        elig.sort()
        nearest = (variant == "Z1")
        if atom[2] == "left":
            return (elig[-1], out[0]) if nearest else (elig[0], out[-1])
        return (elig[0], out[-1]) if nearest else (elig[-1], out[0])
    if t == "GROUP":
        c = rc(atom[1], b)
        if c in fixedcols:
            return None
        win = group_window(atom, cells, b, haz, rule, fixedcols, variant)
        if win is None:
            return None
        oow = [p for p in range(N) if cells[p] == c and p not in win]
        wl = sorted(p for p in win if cells[p] != c)
        if not oow or not wl:
            return None
        return (wl[0], oow[0]) if variant == "G1" else (wl[-1], oow[-1])
    raise ValueError(atom)


def reloc(cells, agent, x, y, haz, rule):
    """Returns (cells', agent', steps) or None if a spare cell is needed and missing."""
    cells = list(cells)
    if cells[x] != 0:
        free = allowed_free(cells, haz, rule)
        if not free:
            return None
        s = free[0]
        targets = [x, s, y, x, s, y]
    else:
        targets = [y, x]
    steps, a = 1, agent
    for t in targets:
        steps += abs(a - t) + 1
        a = t
    cells[x], cells[y] = cells[y], cells[x]
    return tuple(cells), a, steps


def step_limit(m, N, K):
    return 8 * max(1, m) * N * (K + 1)


def simulate(plan, spec, inst):
    """Macro-level run of the priority controller `plan` = [(atom, variant), ...]. Returns (outcome, steps)."""
    b = inst["binding"]
    cells, agent = tuple(inst["cells"]), inst["agent"]
    haz = inst["hazards"]
    rule = any(s[0] == "NO_DROP_HAZARD" for s in spec["safety"])
    fixedcols = {rc(s[1], b) for s in spec["safety"] if s[0] == "NO_PICK"}
    N, K = len(cells), sum(1 for x in cells if x)
    limit = step_limit(len(spec["atoms"]), N, K)
    steps = 1 if spec.get("cue") else 0          # cue: the binding is latched during step 0 (NOOP)
    while True:
        if steps >= limit:
            return "TIMEOUT", steps
        first = next(((a, v) for a, v in plan if not holds(a, cells, b)), None)
        if first is None:
            if all(holds(a, cells, b) for a in spec["atoms"]):
                return "SUCCESS", steps
            return "FALSE_STOP", steps
        sel = select(first[0], first[1], cells, haz, rule, fixedcols, b)
        if sel is None:
            return "STUCK", steps
        r = reloc(cells, agent, sel[0], sel[1], haz, rule)
        if r is None:
            return "STUCK", steps
        cells, agent, st = r
        steps += st


# ------------------------------------------------------------------ the library's own feasibility solver
def satisfiable(atoms, cells, haz, rule, fixedcols, b):
    N = len(cells)
    fixed = {p: cells[p] for p in range(N) if cells[p] != 0 and cells[p] in fixedcols}
    allowed = [p for p in range(N) if p not in fixed and not (rule and haz[p])]
    movable = sorted(cells[p] for p in range(N) if cells[p] != 0 and p not in fixed)
    cols = sorted(set(movable))
    A = [(a[0], rc(a[1], b), rc(a[2], b) if a[0] == "ORDER" else None,
          set(zcells(N, a[2], a[3])) if a[0] == "ZONE" else None) for a in atoms]
    aset = set(allowed)

    @lru_cache(maxsize=None)
    def go(p, counts, st):
        if p == N:
            return not any(counts)
        if sum(counts) > sum(1 for q in range(p, N) if q in aset):
            return False
        opts = [fixed[p]] if p in fixed else ([0] + [c for c, n in zip(cols, counts) if n] if p in aset else [0])
        for c in opts:
            ns, ok = list(st), True
            for i, (t, x, y, z) in enumerate(A):
                if t == "ORDER":
                    if c == y:
                        ns[i] = 1
                    elif c == x and st[i]:
                        ok = False
                elif t == "ZONE":
                    if c == x and p not in z:
                        ok = False
                else:
                    if c == x:
                        if st[i] == 2:
                            ok = False
                        ns[i] = 1
                    elif st[i] == 1:
                        ns[i] = 2
                if not ok:
                    break
            if not ok:
                continue
            nc = counts if (c == 0 or p in fixed) else tuple(n - (col == c) for col, n in zip(cols, counts))
            if go(p + 1, nc, tuple(ns)):
                return True
        return False
    return go(0, tuple(movable.count(c) for c in cols), tuple(0 for _ in A))
