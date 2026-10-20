"""Mission 03 pilot P2 (protocol section 4; predictions locked before this script existed).

Question (A2): can the KIND of a mechanism (and hence its construction schema) be read off behavioural laws,
and what evidence does each law need?

(a) Exact law signatures at N = 3 and N = 4 (every input; joins checked exactly through singletons, monotonicity
    through all single-cell covers, locality through the exact dependency relation), plus interior translation
    equivariance at N = 5 on every input supported in the central 3x3. Signature collisions are reported:
    mechanisms with the same signature but a different construction schema.
(b) Evidence cost at N = 5 and N = 8: samples until a violation of monotonicity is seen, and until the union
    (join) hypothesis is refuted by elimination, under three ways of obtaining data:
      active    : the tester picks A at random and queries A and A + one cell (a hypercube-edge tester)
      iid       : passive, independent random inputs (density 0.35, as in Mission 02)
      coherent  : passive stream in which each input differs from the previous one by one toggled cell

The schema labels are the designer's ground truth for scoring collisions; no learner reads them.

  python mission-03/experiments/p2_laws/run_laws.py
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


# ------------------------------------------------------------------ mechanisms on bitmask grids
class Grid:
    def __init__(self, N):
        self.N = N
        self.cells = [(x, y) for y in range(N) for x in range(N)]
        self.bit = {c: 1 << i for i, c in enumerate(self.cells)}
        self.full = (1 << (N * N)) - 1

    def to_set(self, m):
        return {c for c in self.cells if m & self.bit[c]}

    def to_mask(self, s):
        m = 0
        for c in s:
            if c in self.bit:
                m |= self.bit[c]
        return m


def nbrs(c, N):
    x, y = c
    return [(x + dx, y + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)) if 0 <= x + dx < N and 0 <= y + dy < N]


def m_rot90(S, N):
    return {(N - 1 - y, x) for x, y in S}


def m_right(S, N):
    return {(x + 1, y) for x, y in S if x + 1 < N}


def m_down(S, N):
    return {(x, y + 1) for x, y in S if y + 1 < N}


def m_fliph(S, N):
    return {(N - 1 - x, y) for x, y in S}


def m_dilate(S, N):
    return set(S) | {q for c in S for q in nbrs(c, N)}


def m_rowocc(S, N):
    rows = {y for _, y in S}
    return {(x, y) for y in rows for x in range(N)}


def m_cond(S, N):
    return m_fliph(S, N) if any(y == 0 for _, y in S) else m_down(S, N)


def m_invert(S, N):
    return {(x, y) for x in range(N) for y in range(N)} - set(S)


def m_fillholes(S, N):
    S = set(S)
    seen, stack = set(), [c for c in [(x, y) for x in range(N) for y in range(N)]
                          if (c[0] in (0, N - 1) or c[1] in (0, N - 1)) and c not in S]
    while stack:
        c = stack.pop()
        if c in seen:
            continue
        seen.add(c)
        stack += [q for q in nbrs(c, N) if q not in S and q not in seen]
    return {(x, y) for x in range(N) for y in range(N)} - seen


def m_bbox(S, N):
    if not S:
        return set()
    xs, ys = [x for x, _ in S], [y for _, y in S]
    return {(x, y) for x in range(min(xs), max(xs) + 1) for y in range(min(ys), max(ys) + 1)}


def m_rowfill(S, N):
    out = set()
    for y in {y for _, y in S}:
        xs = [x for x, yy in S if yy == y]
        out |= {(x, y) for x in range(min(xs), max(xs) + 1)}
    return out


def m_gravity(S, N):
    out = set()
    for x in range(N):
        k = sum(1 for xx, _ in S if xx == x)
        out |= {(x, N - 1 - i) for i in range(k)}
    return out


def m_majority(S, N):
    return {(x, y) for x in range(N) for y in range(N)} if 2 * len(S) >= N * N else set()


def m_outline(S, N):
    S = set(S)
    return {c for c in S if len(nbrs(c, N)) < 4 or any(q not in S for q in nbrs(c, N))}


def m_erode(S, N):
    S = set(S)
    return {c for c in S if len(nbrs(c, N)) == 4 and all(q in S for q in nbrs(c, N))}


def m_xorshift(S, N):
    return set(S) ^ m_right(S, N)


def m_identity(S, N):
    return set(S)


ZOO = {  # name: (function, construction schema: designer's ground truth, used only for scoring collisions)
    "rot90": (m_rot90, "union map (relation)"),
    "shift-right-clip": (m_right, "union map (relation)"),
    "dilate": (m_dilate, "union map (relation)"),
    "row-occupancy": (m_rowocc, "union map (relation)"),
    "identity": (m_identity, "union map (relation)"),
    "cond(top: fliph | down)": (m_cond, "guarded union map"),
    "invert": (m_invert, "complement of a union map"),
    "fill-holes": (m_fillholes, "greatest fixpoint of a local rule (border reachability)"),
    "bounding-box fill": (m_bbox, "interval closure on both axes (min/max)"),
    "row interval fill": (m_rowfill, "interval closure per row"),
    "gravity": (m_gravity, "per-column count, then placement"),
    "majority": (m_majority, "global count threshold"),
    "outline": (m_outline, "local, non-monotone (S minus its interior)"),
    "erode": (m_erode, "local AND of neighbours"),
    "xor-shift": (m_xorshift, "local XOR"),
}


def table(f, N):
    G = Grid(N)
    return G, [G.to_mask(f(G.to_set(m), N)) for m in range(1 << (N * N))]


def d4(G):
    N = G.N
    maps = [lambda x, y: (x, y), lambda x, y: (N - 1 - y, x), lambda x, y: (N - 1 - x, N - 1 - y), lambda x, y: (y, N - 1 - x),
            lambda x, y: (N - 1 - x, y), lambda x, y: (x, N - 1 - y), lambda x, y: (y, x), lambda x, y: (N - 1 - y, N - 1 - x)]
    perms = []
    for g in maps[1:]:
        perms.append([G.bit[g(*c)] for c in G.cells])
    return perms


def apply_perm(perm, m):
    out, i = 0, 0
    while m:
        if m & 1:
            out |= perm[i]
        m >>= 1
        i += 1
    return out


def laws_exact(f, N):
    G, T = table(f, N)
    n, cells = 1 << (N * N), G.cells
    single = [T[G.bit[c]] for c in cells]
    res = {"zero": T[0] == 0}
    join = True
    for m in range(1, n):
        u, i, mm = 0, 0, m
        while mm:
            if mm & 1:
                u |= single[i]
            mm >>= 1
            i += 1
        if u != T[m]:
            join = False
            break
    res["join"] = join and res["zero"]
    mono = anti = True
    dep = [0] * len(cells)
    for m in range(n):
        for i, c in enumerate(cells):
            b = G.bit[c]
            m2 = m ^ b
            diff = T[m] ^ T[m2]
            dep[i] |= diff
            if not m & b:
                if T[m] & ~T[m2]:
                    mono = False
                if T[m2] & ~T[m]:
                    anti = False
    res["monotone"] = mono
    res["antitone"] = anti
    res["extensive"] = all(m & ~T[m] == 0 for m in range(n))
    res["contractive"] = all(T[m] & ~m == 0 for m in range(n))
    res["idempotent"] = all(T[T[m]] == T[m] for m in range(n))
    res["D4-equivariant"] = all(T[apply_perm(p, m)] == apply_perm(p, T[m]) for p in d4(G) for m in range(n))
    r = 0
    for i, c in enumerate(cells):
        for j, q in enumerate(cells):
            if dep[i] & G.bit[q]:
                r = max(r, max(abs(c[0] - q[0]), abs(c[1] - q[1])))
    res["locality_radius"] = r
    return res


def interior_translation(f, N=5):
    G = Grid(N)
    inner = [(x, y) for x in range(1, N - 1) for y in range(1, N - 1)]
    for k in range(1 << len(inner)):
        S = {c for i, c in enumerate(inner) if k >> i & 1}
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            sh = lambda T: {(x + dx, y + dy) for x, y in T if 0 <= x + dx < N and 0 <= y + dy < N}
            if set(f(sh(S), N)) != sh(set(f(S, N))):
                return False
    return True


# ------------------------------------------------------------------ evidence cost
def rand_set(N, rng, p=0.35):
    return frozenset((x, y) for x in range(N) for y in range(N) if rng.random() < p)


def union_refuted(samples, N):
    """Elimination for 'f(S) = OR of S over Src(j)' (no constant term); True if inconsistent."""
    cells = [(x, y) for y in range(N) for x in range(N)]
    for j in cells:
        cand = set(cells)
        for S, F in samples:
            if j not in F:
                cand -= S
        if any(j in F and not (S & cand) for S, F in samples):
            return True
    return False


def evidence(f, N, regime, law, rng, cap):
    """Number of observations until the law is refuted (None if not within cap)."""
    samples, prev = [], None
    check_every = 25
    for t in range(1, cap + 1):
        if regime == "coherent":
            if prev is None:
                cur = rand_set(N, rng)
            else:
                c = (rng.randrange(N), rng.randrange(N))
                cur = prev ^ {c}
        elif regime == "iid":
            cur = rand_set(N, rng)
        else:  # active: a fresh random A, then A plus one absent cell, counted as two queries
            A = rand_set(N, rng)
            absent = [(x, y) for x in range(N) for y in range(N) if (x, y) not in A]
            B = A | {rng.choice(absent)} if absent else A
            FA, FB = frozenset(f(A, N)), frozenset(f(B, N))
            if law == "monotone" and not FA <= FB:
                return 2 * t
            if law == "join":
                samples += [(A, FA), (B, FB)]
                if t % check_every == 0 and union_refuted(samples, N):
                    return 2 * t
            continue
        F = frozenset(f(cur, N))
        if law == "monotone":
            for S, FS in samples:
                if (S <= cur and not FS <= F) or (cur <= S and not F <= FS):
                    return t
        samples.append((cur, F))
        if law == "join" and t % check_every == 0 and union_refuted(samples, N):
            return t
        prev = cur
    return None


def main():
    t0 = time.perf_counter()
    sig = {}
    for name, (f, schema) in ZOO.items():
        s3, s4 = laws_exact(f, 3), laws_exact(f, 4)
        sig[name] = {"schema": schema, "N3": s3, "N4": s4, "interior_translation_N5": interior_translation(f)}
        print(name, s4, "TE", sig[name]["interior_translation_N5"], flush=True)
    # collisions: same N=4 signature (+ translation law), different schema
    key = lambda s: json.dumps([s["N4"], s["interior_translation_N5"]], sort_keys=True)
    groups = {}
    for name, s in sig.items():
        groups.setdefault(key(s), []).append(name)
    collisions = [g for g in groups.values() if len({sig[n]["schema"] for n in g}) > 1]
    size_stable = {n: s["N3"] == s["N4"] for n, s in sig.items()}
    # evidence cost
    rng = random.Random(0)
    cost = {}
    runs = 10
    for N in (5, 8):
        for name, (f, _) in ZOO.items():
            for law in ("monotone", "join"):
                holds = sig[name]["N4"]["monotone" if law == "monotone" else "join"]
                if holds:
                    continue   # nothing to detect; testing can only fail to refute
                for regime in ("active", "iid", "coherent"):
                    cap = 2000 if regime == "iid" and law == "monotone" else 4000
                    got = [evidence(f, N, regime, law, rng, cap) for _ in range(runs)]
                    det = [g for g in got if g is not None]
                    cost[f"N{N}|{name}|{law}|{regime}"] = {
                        "detected": f"{len(det)}/{runs}", "median_obs": sorted(det)[len(det) // 2] if det else None, "cap": cap}
        print("evidence N", N, "done", round(time.perf_counter() - t0, 1), flush=True)
    out = {"signatures": sig, "collisions": collisions, "signature_same_at_N3_and_N4": size_stable, "evidence": cost,
           "time_s": round(time.perf_counter() - t0, 1)}
    (HERE / "laws.json").write_text(json.dumps(out, indent=1))
    print("collisions:", collisions)
    print("size-stable signatures:", sum(size_stable.values()), "/", len(size_stable))
    for k, v in cost.items():
        print(k, v)


if __name__ == "__main__":
    main()
