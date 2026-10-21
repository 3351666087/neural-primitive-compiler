"""ARC-like transformation families.

Every family works in an abstract space: 0 is the background and every role
(object colour, marker colour, fill colour, ...) has one colour per task, kept
in P['roles'].  `rule(grid, P)` is the single definition of the transformation;
`gen` only builds inputs.  Roles listed in P['perm'] are visible in every input
and are recognisable from structure alone, so they may be recoloured per pair;
roles in P['const'] are output-only constants and are never recoloured per pair.

Family attributes:
  kind      'same'   -> output has the input's size
            'resize' -> output size differs (computed by the rule)
  ti        True when the rule is translation invariant, i.e. padding the
            content with background anywhere does not change the result
  panels_ok whether the content may be placed in one panel of a partitioned grid
"""
from grids import (N4, N8, DIAG4, Placer, bbox, component_at, components, copy, dims,
                   fliplr, flipud, random_shape, rot180, rot90ccw, rot90cw, shape_dims,
                   transpose, zeros)

PALETTE = ['P1', 'P2', 'P3']
DIRS = {'down': (1, 0), 'up': (-1, 0), 'right': (0, 1), 'left': (0, -1)}


def set_roles(P, rng, perm, const, primary=None):
    cols = rng.sample(range(1, 10), len(perm) + len(const))
    P['roles'] = dict(zip(perm + const, cols))
    P['perm'] = list(perm)
    P['const'] = list(const)
    P['primary'] = primary or perm[0]
    return P


def palette_roles(rng, lo=2, hi=3):
    return PALETTE[:rng.randint(lo, hi)]


def palette(P):
    return [P['roles'][r] for r in PALETTE if r in P['roles']]


def pick_hw(rng, cap, lo_h, hi_h, lo_w, hi_w, square=False):
    """Choose content dims within family bounds and layout caps (or honour cap['fix'])."""
    fix = cap.get('fix')
    if fix:
        h, w = fix
        if not (lo_h <= h <= cap['h'] and lo_w <= w <= cap['w']):
            return None
        if square and h != w:
            return None
        return h, w
    hi_h, hi_w = min(hi_h, cap['h']), min(hi_w, cap['w'])
    if square:
        lo, hi = max(lo_h, lo_w), min(hi_h, hi_w)
        if hi < lo:
            return None
        s = rng.randint(lo, hi)
        return s, s
    if hi_h < lo_h or hi_w < lo_w:
        return None
    return rng.randint(lo_h, hi_h), rng.randint(lo_w, hi_w)


def random_picture(rng, h, w, pal, dens):
    return [[rng.choice(pal) if rng.random() < dens else 0 for _ in range(w)] for _ in range(h)]


def paint(g, cells, v):
    for r, c in cells:
        g[r][c] = v


class Family:
    name = ''
    kind = 'same'
    ti = False
    panels_ok = True

    def min_dims(self, P):
        return 3, 3

    def check_pair(self, g, out, P):
        return out != g


# ---------------------------------------------------------------------------
class Gravity(Family):
    name = 'gravity'

    def min_dims(self, P):
        return 4, 4

    def sample(self, rng, cat):
        P = {'dir': rng.choice(list(DIRS))}
        P['walls'] = 'b' not in cat and rng.random() < 0.5
        return set_roles(P, rng, ['A'] + (['W'] if P['walls'] else []), [])

    def gen(self, rng, P, k, cap):
        hw = pick_hw(rng, cap, 4, 14, 4, 14)
        if not hw:
            return None
        h, w = hw
        A = P['roles']['A']
        dens = rng.uniform(0.12, 0.3)
        g = [[A if rng.random() < dens else 0 for _ in range(w)] for _ in range(h)]
        if P['walls']:
            W = P['roles']['W']
            vertical_motion = P['dir'] in ('down', 'up')
            for _ in range(rng.randint(1, 3)):
                if vertical_motion:
                    L = rng.randint(2, min(4, w))
                    r, c0 = rng.randint(1, h - 2), rng.randint(0, w - L)
                    paint(g, [(r, c) for c in range(c0, c0 + L)], W)
                else:
                    L = rng.randint(2, min(4, h))
                    c, r0 = rng.randint(1, w - 2), rng.randint(0, h - L)
                    paint(g, [(r, c) for r in range(r0, r0 + L)], W)
        return g

    @staticmethod
    def lines(h, w, d):
        if d == 'down':
            return [[(r, c) for r in range(h)] for c in range(w)]
        if d == 'up':
            return [[(r, c) for r in reversed(range(h))] for c in range(w)]
        if d == 'right':
            return [[(r, c) for c in range(w)] for r in range(h)]
        return [[(r, c) for c in reversed(range(w))] for r in range(h)]

    def rule(self, g, P):
        h, w = dims(g)
        A = P['roles']['A']
        W = P['roles'].get('W', -1)
        out = copy(g)
        for line in self.lines(h, w, P['dir']):
            seg = []
            for cell in line + [None]:
                if cell is None or g[cell[0]][cell[1]] == W:
                    n = sum(1 for r, c in seg if g[r][c] == A)
                    for i, (r, c) in enumerate(seg):
                        out[r][c] = A if i >= len(seg) - n else 0
                    seg = []
                else:
                    seg.append(cell)
        return out


# ---------------------------------------------------------------------------
class FillEnclosed(Family):
    name = 'fill_enclosed'
    ti = True

    def min_dims(self, P):
        return 6, 6

    def sample(self, rng, cat):
        return set_roles({}, rng, ['A'], ['F'])

    def gen(self, rng, P, k, cap):
        hw = pick_hw(rng, cap, 6, 16, 6, 16)
        if not hw:
            return None
        h, w = hw
        A = P['roles']['A']
        g = zeros(h, w)
        pl = Placer(h, w)
        closed_any = False
        for _ in range(rng.randint(1, 4)):
            bh, bw = rng.randint(3, min(7, h)), rng.randint(3, min(7, w))
            pos = pl.place(rng, bh, bw)
            if pos is None:
                continue
            r0, c0 = pos
            border = [(r, c) for r in range(r0, r0 + bh) for c in range(c0, c0 + bw)
                      if r in (r0, r0 + bh - 1) or c in (c0, c0 + bw - 1)]
            paint(g, border, A)
            if not closed_any or rng.random() < 0.55:
                closed_any = True
            else:
                mids = [(r, c) for r, c in border
                        if not (r in (r0, r0 + bh - 1) and c in (c0, c0 + bw - 1))]
                r, c = rng.choice(mids)
                g[r][c] = 0
        return g if closed_any else None

    def rule(self, g, P):
        h, w = dims(g)
        F = P['roles']['F']
        stack = [(r, c) for r in range(h) for c in range(w)
                 if (r in (0, h - 1) or c in (0, w - 1)) and g[r][c] == 0]
        reach = set(stack)
        while stack:
            r, c = stack.pop()
            for dr, dc in N4:
                nr, nc = r + dr, c + dc
                if 0 <= nr < h and 0 <= nc < w and g[nr][nc] == 0 and (nr, nc) not in reach:
                    reach.add((nr, nc))
                    stack.append((nr, nc))
        out = copy(g)
        for r in range(h):
            for c in range(w):
                if g[r][c] == 0 and (r, c) not in reach:
                    out[r][c] = F
        return out


# ---------------------------------------------------------------------------
class RecolorBySize(Family):
    name = 'recolor_extreme_size'
    ti = True

    def min_dims(self, P):
        return 6, 6

    def sample(self, rng, cat):
        P = {'both': rng.random() < 0.5}
        return set_roles(P, rng, ['A'], ['L'] + (['S'] if P['both'] else []))

    def gen(self, rng, P, k, cap):
        hw = pick_hw(rng, cap, 6, 16, 6, 16)
        if not hw:
            return None
        h, w = hw
        A = P['roles']['A']
        g = zeros(h, w)
        pl = Placer(h, w)
        for _ in range(rng.randint(3, 6)):
            shp = random_shape(rng, rng.randint(1, 9), 4, 4)
            pos = pl.place(rng, *shape_dims(shp))
            if pos:
                paint(g, [(pos[0] + r, pos[1] + c) for r, c in shp], A)
        return g

    def rule(self, g, P):
        A = P['roles']['A']
        out = copy(g)
        comps = components(g, lambda v: v == A)
        if not comps:
            return out
        sizes = [len(c) for c in comps]
        mx, mn = max(sizes), min(sizes)
        if sizes.count(mx) == 1:
            paint(out, comps[sizes.index(mx)], P['roles']['L'])
        if P['both'] and mn != mx and sizes.count(mn) == 1:
            paint(out, comps[sizes.index(mn)], P['roles']['S'])
        return out

    def check_pair(self, g, out, P):
        sizes = [len(c) for c in components(g, lambda v: v == P['roles']['A'])]
        if len(sizes) < 3 or sizes.count(max(sizes)) != 1:
            return False
        if P['both'] and (sizes.count(min(sizes)) != 1 or min(sizes) == max(sizes)):
            return False
        return out != g


# ---------------------------------------------------------------------------
def sym_images(r, c, h, w, sym):
    if sym == 'lr':
        return [(r, w - 1 - c)]
    if sym == 'ud':
        return [(h - 1 - r, c)]
    return [(r, w - 1 - c), (h - 1 - r, c), (h - 1 - r, w - 1 - c)]


class SymmetryRepair(Family):
    name = 'symmetry_repair'

    def min_dims(self, P):
        return 6, 6

    def sample(self, rng, cat):
        P = {'sym': rng.choice(['lr', 'ud', 'both'])}
        return set_roles(P, rng, ['M'] + palette_roles(rng), [], primary='M')

    def gen(self, rng, P, k, cap):
        hw = pick_hw(rng, cap, 6, 14, 6, 14)
        if not hw:
            return None
        h, w = hw
        sym = P['sym']
        pal = palette(P)
        dens = rng.uniform(0.45, 0.75)
        pic = zeros(h, w)
        hh = (h + 1) // 2 if sym in ('ud', 'both') else h
        ww = (w + 1) // 2 if sym in ('lr', 'both') else w
        for r in range(hh):
            for c in range(ww):
                v = rng.choice(pal) if rng.random() < dens else 0
                pic[r][c] = v
                for rr, cc in sym_images(r, c, h, w, sym):
                    pic[rr][cc] = v

        def span(n, mirrored):
            if mirrored:
                half = n // 2
                m = rng.randint(2, min(4, half))
                start = rng.randint(0, half - m) if rng.random() < 0.5 else rng.randint(n - half, n - m)
            else:
                m = rng.randint(2, min(4, n - 2))
                start = rng.randint(0, n - m)
            return start, m

        r0, mh = span(h, sym in ('ud', 'both'))
        c0, mw = span(w, sym in ('lr', 'both'))
        cells = [(r, c) for r in range(r0, r0 + mh) for c in range(c0, c0 + mw)]
        if sum(1 for r, c in cells if pic[r][c]) < 2:
            return None
        g = copy(pic)
        paint(g, cells, P['roles']['M'])
        return g

    def rule(self, g, P):
        h, w = dims(g)
        M = P['roles']['M']
        out = copy(g)
        for r in range(h):
            for c in range(w):
                if g[r][c] == M:
                    for rr, cc in sym_images(r, c, h, w, P['sym']):
                        if g[rr][cc] != M:
                            out[r][c] = g[rr][cc]
                            break
        return out

    def check_pair(self, g, out, P):
        return out != g and all(P['roles']['M'] not in row for row in out)


# ---------------------------------------------------------------------------
class MirrorTiling(Family):
    name = 'mirror_tiling'
    kind = 'resize'

    def sample(self, rng, cat):
        P = {'mode': rng.choice(['quad', 'quad_r', 'h', 'v'])}
        return set_roles(P, rng, palette_roles(rng), [])

    def factors(self, P):
        m = P['mode']
        return (2 if m in ('quad', 'quad_r', 'v') else 1), (2 if m in ('quad', 'quad_r', 'h') else 1)

    def gen(self, rng, P, k, cap):
        fh, fw = self.factors(P)
        c2 = dict(cap, h=min(cap['h'], cap['oh'] // fh), w=min(cap['w'], cap['ow'] // fw))
        hw = pick_hw(rng, c2, 3, 8, 3, 8)
        if not hw:
            return None
        g = random_picture(rng, hw[0], hw[1], palette(P), rng.uniform(0.35, 0.65))
        if (fh == 2 and flipud(g) == g) or (fw == 2 and fliplr(g) == g):
            return None
        return g

    def rule(self, g, P):
        m = P['mode']
        if m == 'h':
            return [a + b for a, b in zip(g, fliplr(g))]
        if m == 'v':
            return copy(g) + flipud(g)
        if m == 'quad':
            tl, tr, bl, br = g, fliplr(g), flipud(g), rot180(g)
        else:
            tl, tr, bl, br = rot180(g), flipud(g), fliplr(g), g
        return [a + b for a, b in zip(tl, tr)] + [a + b for a, b in zip(bl, br)]


# ---------------------------------------------------------------------------
class Upscale(Family):
    name = 'upscale'
    kind = 'resize'

    def sample(self, rng, cat):
        P = {'k': rng.choice([2, 3])}
        return set_roles(P, rng, palette_roles(rng), [])

    def gen(self, rng, P, k, cap):
        f = P['k']
        c2 = dict(cap, h=min(cap['h'], cap['oh'] // f), w=min(cap['w'], cap['ow'] // f))
        hw = pick_hw(rng, c2, 3, 7, 3, 7)
        if not hw:
            return None
        g = random_picture(rng, hw[0], hw[1], palette(P), rng.uniform(0.35, 0.65))
        return g if any(any(row) for row in g) else None

    def rule(self, g, P):
        f = P['k']
        h, w = dims(g)
        return [[g[r // f][c // f] for c in range(w * f)] for r in range(h * f)]


# ---------------------------------------------------------------------------
class CropMarked(Family):
    name = 'crop_marked_object'
    kind = 'resize'
    ti = True

    def min_dims(self, P):
        return 8, 8

    def sample(self, rng, cat):
        return set_roles({}, rng, ['A', 'M'], [])

    def gen(self, rng, P, k, cap):
        hw = pick_hw(rng, cap, 8, 16, 8, 16)
        maxb = min(5, cap['oh'], cap['ow'])
        if not hw or maxb < 3:
            return None
        h, w = hw
        A, M = P['roles']['A'], P['roles']['M']
        shp = None
        for _ in range(30):
            s = random_shape(rng, rng.randint(5, min(12, maxb * maxb)), maxb, maxb)
            if min(shape_dims(s)) >= 3:
                shp = s
                break
        if shp is None:
            return None
        g = zeros(h, w)
        pl = Placer(h, w)
        pos = pl.place(rng, *shape_dims(shp))
        if pos is None:
            return None
        cells = [(pos[0] + r, pos[1] + c) for r, c in shp]
        paint(g, cells, A)
        mr, mc = rng.choice(cells)
        g[mr][mc] = M
        placed = 0
        for _ in range(rng.randint(2, 4)):
            s = random_shape(rng, rng.randint(3, 10), 5, 5)
            p = pl.place(rng, *shape_dims(s))
            if p:
                paint(g, [(p[0] + r, p[1] + c) for r, c in s], A)
                placed += 1
        return g if placed else None

    def rule(self, g, P):
        M = P['roles']['M']
        h, w = dims(g)
        marks = [(r, c) for r in range(h) for c in range(w) if g[r][c] == M]
        if len(marks) != 1:
            return copy(g)
        comp = component_at(g, marks[0], lambda v: v != 0)
        cs = set(comp)
        r0, c0, r1, c1 = bbox(comp)
        return [[g[r][c] if (r, c) in cs else 0 for c in range(c0, c1 + 1)] for r in range(r0, r1 + 1)]


# ---------------------------------------------------------------------------
class CountToGrid(Family):
    name = 'count_objects_to_grid'
    kind = 'resize'
    ti = True

    def min_dims(self, P):
        return 5, 5

    def sample(self, rng, cat):
        P = {'order': rng.choice(['row', 'col']), 'distract': rng.random() < 0.5,
             'ns': rng.sample(range(1, 8), 5)}
        return set_roles(P, rng, ['A'] + (['D'] if P['distract'] else []), [])

    def gen(self, rng, P, k, cap):
        n = P['ns'][k % 5]
        hw = pick_hw(rng, cap, 5, 14, 5, 14)
        if not hw:
            return None
        h, w = hw
        A = P['roles']['A']
        g = zeros(h, w)
        pl = Placer(h, w)
        for _ in range(n):
            s = random_shape(rng, rng.randint(2, 4), *rng.choice([(2, 3), (3, 2)]))
            p = pl.place(rng, *shape_dims(s), tries=200)
            if p is None:
                return None
            paint(g, [(p[0] + r, p[1] + c) for r, c in s], A)
        if P['distract']:
            placed = 0
            for _ in range(rng.randint(1, 3)):
                p = pl.place(rng, 1, 1)
                if p:
                    g[p[0]][p[1]] = P['roles']['D']
                    placed += 1
            if not placed:
                return None
        return g

    def rule(self, g, P):
        A = P['roles']['A']
        n = len(components(g, lambda v: v == A))
        if P['order'] == 'row':
            order = [(r, c) for r in range(3) for c in range(3)]
        else:
            order = [(r, c) for c in range(3) for r in range(3)]
        out = zeros(3, 3)
        paint(out, order[:n], A)
        return out

    def check_pair(self, g, out, P):
        return any(any(row) for row in out)


# ---------------------------------------------------------------------------
class ConnectPairs(Family):
    name = 'connect_aligned_pairs'
    ti = True

    def min_dims(self, P):
        return 6, 6

    def sample(self, rng, cat):
        P = {'orient': rng.choice(['h', 'v', 'both'])}
        return set_roles(P, rng, ['A'], ['L'])

    def gen(self, rng, P, k, cap):
        hw = pick_hw(rng, cap, 6, 16, 6, 16)
        if not hw:
            return None
        h, w = hw
        A = P['roles']['A']
        g = zeros(h, w)
        occ = set()
        placed = 0
        for i in range(rng.randint(2, 4)):
            o = P['orient'] if P['orient'] != 'both' else ('h' if i == 0 else 'v' if i == 1 else rng.choice('hv'))
            for _ in range(100):
                if o == 'h':
                    d = rng.randint(2, w - 2)
                    r, c1 = rng.randint(0, h - 1), rng.randint(0, w - d - 2)
                    cells = [(r, c) for c in range(c1, c1 + d + 2)]
                else:
                    d = rng.randint(2, h - 2)
                    c, r1 = rng.randint(0, w - 1), rng.randint(0, h - d - 2)
                    cells = [(r, c) for r in range(r1, r1 + d + 2)]
                if any((r + dr, c + dc) in occ for r, c in cells for dr in (-1, 0, 1) for dc in (-1, 0, 1)):
                    continue
                occ.update(cells)
                paint(g, [cells[0], cells[-1]], A)
                placed += 1
                break
        return g if placed >= 2 else None

    @staticmethod
    def segments(g, A):
        h, w = dims(g)
        segs = []
        for r in range(h):
            cols = [c for c in range(w) if g[r][c] == A]
            for c1, c2 in zip(cols, cols[1:]):
                if c2 - c1 >= 2 and all(g[r][c] == 0 for c in range(c1 + 1, c2)):
                    segs.append(((r, c1), (r, c2), [(r, c) for c in range(c1 + 1, c2)]))
        for c in range(w):
            rows = [r for r in range(h) if g[r][c] == A]
            for r1, r2 in zip(rows, rows[1:]):
                if r2 - r1 >= 2 and all(g[r][c] == 0 for r in range(r1 + 1, r2)):
                    segs.append(((r1, c), (r2, c), [(r, c) for r in range(r1 + 1, r2)]))
        return segs

    def rule(self, g, P):
        out = copy(g)
        for _, _, cells in self.segments(g, P['roles']['A']):
            paint(out, cells, P['roles']['L'])
        return out

    def check_pair(self, g, out, P):
        A = P['roles']['A']
        h, w = dims(g)
        segs = self.segments(g, A)
        ends = sorted(e for s in segs for e in s[:2])
        acells = sorted((r, c) for r in range(h) for c in range(w) if g[r][c] == A)
        inner = [x for s in segs for x in s[2]]
        return len(segs) >= 2 and ends == acells and len(inner) == len(set(inner)) and out != g


# ---------------------------------------------------------------------------
class ExtendRays(Family):
    name = 'extend_rays'

    def min_dims(self, P):
        return 5, 5

    def sample(self, rng, cat):
        P = {'dir': rng.choice(list(DIRS)), 'obst': rng.random() < 0.5,
             'raymode': rng.choice(['same', 'const'])}
        return set_roles(P, rng, ['A'] + (['B'] if P['obst'] else []),
                         ['R'] if P['raymode'] == 'const' else [])

    def gen(self, rng, P, k, cap):
        hw = pick_hw(rng, cap, 5, 15, 5, 15)
        if not hw:
            return None
        h, w = hw
        dr, dc = DIRS[P['dir']]
        A = P['roles']['A']
        g = zeros(h, w)
        pl = Placer(h, w)
        lines = set()

        def line_of(r, c):
            return c if dr else r

        def place_seed(r, c):
            if not (0 <= r < h and 0 <= c < w and 0 <= r + dr < h and 0 <= c + dc < w):
                return False
            if line_of(r, c) in lines or not pl.free(r, c, r, c):
                return False
            pl.add((r, c, r, c))
            lines.add(line_of(r, c))
            g[r][c] = A
            return True

        if P['obst']:
            obs = []
            for _ in range(rng.randint(1, 2)):
                p = pl.place(rng, 2, 2)
                if p:
                    obs.append(p)
                    paint(g, [(p[0] + i, p[1] + j) for i in (0, 1) for j in (0, 1)], P['roles']['B'])
            if not obs:
                return None
            r0, c0 = obs[0]
            targets = [(r0 + i, c0 + j) for i in (0, 1) for j in (0, 1)]
            for _ in range(40):
                tr, tc = rng.choice(targets)
                t = rng.randint(2, 6)
                if place_seed(tr - t * dr, tc - t * dc):
                    break
            else:
                return None
        want = rng.randint(2, 4)
        for _ in range(300):
            if len(lines) >= want:
                break
            place_seed(rng.randrange(h), rng.randrange(w))
        return g if len(lines) >= 2 else None

    def walk(self, g, P):
        """Yield (cells_painted, stop_value) for every seed."""
        h, w = dims(g)
        dr, dc = DIRS[P['dir']]
        A = P['roles']['A']
        for r in range(h):
            for c in range(w):
                if g[r][c] == A:
                    y, x = r + dr, c + dc
                    cells = []
                    while 0 <= y < h and 0 <= x < w and g[y][x] == 0:
                        cells.append((y, x))
                        y, x = y + dr, x + dc
                    stop = g[y][x] if 0 <= y < h and 0 <= x < w else None
                    yield cells, stop

    def rule(self, g, P):
        col = P['roles']['A'] if P['raymode'] == 'same' else P['roles']['R']
        out = copy(g)
        for cells, _ in self.walk(g, P):
            paint(out, cells, col)
        return out

    def check_pair(self, g, out, P):
        if out == g:
            return False
        if P['obst']:
            return any(stop == P['roles']['B'] for _, stop in self.walk(g, P))
        return True


# ---------------------------------------------------------------------------
STAMPS = {'ring8': N8, 'plus': N4, 'diag': DIAG4,
          'cross2': N4 + [(2 * a, 2 * b) for a, b in N4]}


class StampAround(Family):
    name = 'stamp_around_points'
    ti = True

    def min_dims(self, P):
        return 5, 5

    def sample(self, rng, cat):
        P = {'stamp': rng.choice(list(STAMPS))}
        return set_roles(P, rng, ['A'], ['O'])

    def gen(self, rng, P, k, cap):
        hw = pick_hw(rng, cap, 5, 15, 5, 15)
        if not hw:
            return None
        h, w = hw
        rad = 2 if P['stamp'] == 'cross2' else 1
        g = zeros(h, w)
        pl = Placer(h, w)
        placed = 0
        for _ in range(rng.randint(2, 5)):
            p = pl.place(rng, 2 * rad + 1, 2 * rad + 1)
            if p:
                g[p[0] + rad][p[1] + rad] = P['roles']['A']
                placed += 1
        return g if placed else None

    def rule(self, g, P):
        h, w = dims(g)
        out = copy(g)
        for r in range(h):
            for c in range(w):
                if g[r][c] == P['roles']['A']:
                    for dr, dc in STAMPS[P['stamp']]:
                        y, x = r + dr, c + dc
                        if 0 <= y < h and 0 <= x < w and g[y][x] == 0:
                            out[y][x] = P['roles']['O']
        return out


# ---------------------------------------------------------------------------
class SlideToWall(Family):
    name = 'slide_to_wall'
    ti = True

    def min_dims(self, P):
        return 7, 7

    def sample(self, rng, cat):
        P = {'orient': rng.choice(['h', 'v', 'mixed'])}
        return set_roles(P, rng, ['A', 'W'], [])

    def gen(self, rng, P, k, cap):
        o = P['orient'] if P['orient'] != 'mixed' else rng.choice(['h', 'v'])
        hw = pick_hw(rng, cap, 7, 16, 7, 16)
        if not hw:
            return None
        h, w = hw if o == 'h' else (hw[1], hw[0])
        A, W = P['roles']['A'], P['roles']['W']
        g = zeros(h, w)
        pl = Placer(h, w)
        L = rng.randint(4, w)
        c0, rw = rng.randint(0, w - L), rng.randint(0, h - 1)
        sides = [s for s, ok in (('above', rw >= 3), ('below', rw <= h - 4)) if ok]
        if not sides:
            return None
        paint(g, [(rw, c) for c in range(c0, c0 + L)], W)
        pl.add((rw, c0, rw, c0 + L - 1))
        objs = []
        for _ in range(rng.randint(1, 2)):
            for _ in range(60):
                side = rng.choice(sides)
                s = random_shape(rng, rng.randint(3, 6), 3, 3)
                sh, sw = shape_dims(s)
                if sw > L:
                    continue
                cc = rng.randint(c0, c0 + L - sw)
                if side == 'above':
                    if rw - 1 - sh < 0:
                        continue
                    rr = rng.randint(0, rw - 1 - sh)
                else:
                    if rw + 2 > h - sh:
                        continue
                    rr = rng.randint(rw + 2, h - sh)
                if not pl.free(rr, cc, rr + sh - 1, cc + sw - 1):
                    continue
                if any(os == side and not (cc + sw - 1 < a - 1 or cc > b + 1) for os, a, b in objs):
                    continue
                pl.add((rr, cc, rr + sh - 1, cc + sw - 1))
                objs.append((side, cc, cc + sw - 1))
                paint(g, [(rr + r, cc + c) for r, c in s], A)
                break
        if not objs:
            return None
        return g if o == 'h' else transpose(g)

    @staticmethod
    def _slide(g, A, W):
        h, w = dims(g)
        wall = [(r, c) for r in range(h) for c in range(w) if g[r][c] == W]
        rw = wall[0][0]
        wcols = {c for _, c in wall}
        out = [[0 if v == A else v for v in row] for row in g]
        for comp in components(g, lambda v: v == A):
            above = max(r for r, _ in comp) < rw
            gaps = []
            for c in sorted({c for _, c in comp} & wcols):
                rs = [r for r, cc in comp if cc == c]
                gaps.append(rw - max(rs) - 1 if above else min(rs) - rw - 1)
            s = min(gaps) if gaps else 0
            s = s if above else -s
            for r, c in comp:
                out[r + s][c] = A
        return out

    def rule(self, g, P):
        A, W = P['roles']['A'], P['roles']['W']
        h, w = dims(g)
        wall = [(r, c) for r in range(h) for c in range(w) if g[r][c] == W]
        if not wall:
            return copy(g)
        if len({r for r, _ in wall}) == 1:
            return self._slide(g, A, W)
        if len({c for _, c in wall}) == 1:
            return transpose(self._slide(transpose(g), A, W))
        return copy(g)

    def check_pair(self, g, out, P):
        A = P['roles']['A']
        return out != g and sum(row.count(A) for row in g) == sum(row.count(A) for row in out)


# ---------------------------------------------------------------------------
class RecolorOrientation(Family):
    name = 'recolor_by_orientation'
    ti = True

    def min_dims(self, P):
        return 5, 5

    def sample(self, rng, cat):
        P = {'dots': rng.random() < 0.4}
        return set_roles(P, rng, ['A'], ['H', 'V'])

    def gen(self, rng, P, k, cap):
        hw = pick_hw(rng, cap, 5, 15, 5, 15)
        if not hw:
            return None
        h, w = hw
        A = P['roles']['A']
        g = zeros(h, w)
        pl = Placer(h, w)
        for i in range(rng.randint(3, 6)):
            o = 'h' if i == 0 else 'v' if i == 1 else rng.choice('hv')
            L = rng.randint(2, min(5, w if o == 'h' else h))
            bh, bw = (1, L) if o == 'h' else (L, 1)
            p = pl.place(rng, bh, bw)
            if p:
                paint(g, [(p[0] + r, p[1] + c) for r in range(bh) for c in range(bw)], A)
        if P['dots']:
            for _ in range(rng.randint(1, 2)):
                p = pl.place(rng, 1, 1)
                if p:
                    g[p[0]][p[1]] = A
        return g

    def rule(self, g, P):
        out = copy(g)
        for comp in components(g, lambda v: v == P['roles']['A']):
            if len(comp) < 2:
                continue
            if len({r for r, _ in comp}) == 1:
                paint(out, comp, P['roles']['H'])
            elif len({c for _, c in comp}) == 1:
                paint(out, comp, P['roles']['V'])
        return out

    def check_pair(self, g, out, P):
        return any(P['roles']['H'] in row for row in out) and any(P['roles']['V'] in row for row in out)


# ---------------------------------------------------------------------------
class DenoiseRects(Family):
    name = 'denoise_rectangles'
    ti = True

    def min_dims(self, P):
        return 7, 7

    def sample(self, rng, cat):
        return set_roles({}, rng, ['A', 'N'], [])

    def gen(self, rng, P, k, cap):
        hw = pick_hw(rng, cap, 7, 16, 7, 16)
        if not hw:
            return None
        h, w = hw
        A, N = P['roles']['A'], P['roles']['N']
        g = zeros(h, w)
        pl = Placer(h, w)
        nrect = 0
        for _ in range(rng.randint(1, 3)):
            rh, rw = rng.randint(3, min(6, h - 2)), rng.randint(3, min(6, w - 2))
            p = pl.place(rng, rh, rw)
            if p:
                paint(g, [(p[0] + r, p[1] + c) for r in range(rh) for c in range(rw)], A)
                nrect += 1
        if not nrect:
            return None
        target = rng.randint(3, max(3, h * w // 12))
        cells = [(r, c) for r in range(h) for c in range(w)]
        rng.shuffle(cells)
        chosen = []
        for r, c in cells:
            if len(chosen) >= target:
                break
            if all(max(abs(r - y), abs(c - x)) > 1 for y, x in chosen):
                chosen.append((r, c))
        on = [x for x in chosen if g[x[0]][x[1]] == A]
        if not on or len(on) == len(chosen):
            return None
        paint(g, chosen, N)
        return g

    def rule(self, g, P):
        A, N = P['roles']['A'], P['roles']['N']
        boxes = [bbox(c) for c in components(g, lambda v: v == A)]
        out = copy(g)
        h, w = dims(g)
        for r in range(h):
            for c in range(w):
                if g[r][c] == N:
                    inside = any(r0 <= r <= r1 and c0 <= c <= c1 for r0, c0, r1, c1 in boxes)
                    out[r][c] = A if inside else 0
        return out

    def check_pair(self, g, out, P):
        A = P['roles']['A']
        if out == g or any(P['roles']['N'] in row for row in out):
            return False
        for comp in components(out, lambda v: v == A):
            r0, c0, r1, c1 = bbox(comp)
            if len(comp) != (r1 - r0 + 1) * (c1 - c0 + 1):
                return False
        return True


# ---------------------------------------------------------------------------
FLIP_OPS = {'lr': fliplr, 'ud': flipud, 'rot180': rot180, 'rot90cw': rot90cw,
            'rot90ccw': rot90ccw, 'transpose': transpose}


class FlipRotate(Family):
    name = 'grid_flip_rotate'

    def sample(self, rng, cat):
        P = {'op': rng.choice(list(FLIP_OPS))}
        return set_roles(P, rng, palette_roles(rng), [])

    def gen(self, rng, P, k, cap):
        square = P['op'] in ('rot90cw', 'rot90ccw', 'transpose')
        hw = pick_hw(rng, cap, 3, 12, 3, 12, square=square)
        if not hw:
            return None
        return random_picture(rng, hw[0], hw[1], palette(P), rng.uniform(0.3, 0.6))

    def rule(self, g, P):
        return FLIP_OPS[P['op']](g)


# ---------------------------------------------------------------------------
BOOL_OPS = {'and': lambda a, b: a and b, 'or': lambda a, b: a or b,
            'xor': lambda a, b: a != b, 'nor': lambda a, b: not (a or b)}


class PanelBoolean(Family):
    name = 'panel_boolean'
    kind = 'resize'
    panels_ok = False

    def min_dims(self, P):
        return (3, 7) if P['split'] == 'v' else (7, 3)

    def sample(self, rng, cat):
        P = {'op': rng.choice(list(BOOL_OPS)), 'split': rng.choice(['v', 'h'])}
        return set_roles(P, rng, ['A', 'B', 'S'], ['R'])

    def gen(self, rng, P, k, cap):
        A, B, S = P['roles']['A'], P['roles']['B'], P['roles']['S']
        if P['split'] == 'v':
            hi_h, hi_w = min(7, cap['h'], cap['oh']), min(7, (cap['w'] - 1) // 2, cap['ow'])
        else:
            hi_h, hi_w = min(7, (cap['h'] - 1) // 2, cap['oh']), min(7, cap['w'], cap['ow'])
        if hi_h < 3 or hi_w < 3:
            return None
        ph, pw = rng.randint(3, hi_h), rng.randint(3, hi_w)
        left = [[A if rng.random() < 0.5 else 0 for _ in range(pw)] for _ in range(ph)]
        right = [[B if rng.random() < 0.5 else 0 for _ in range(pw)] for _ in range(ph)]
        if P['split'] == 'v':
            return [a + [S] + b for a, b in zip(left, right)]
        return left + [[S] * pw] + right

    def rule(self, g, P):
        h, w = dims(g)
        if P['split'] == 'v':
            pw = (w - 1) // 2
            L, Rg = [row[:pw] for row in g], [row[pw + 1:] for row in g]
        else:
            ph = (h - 1) // 2
            L, Rg = g[:ph], g[ph + 1:]
        f = BOOL_OPS[P['op']]
        R = P['roles']['R']
        return [[R if f(a != 0, b != 0) else 0 for a, b in zip(ra, rb)] for ra, rb in zip(L, Rg)]

    def check_pair(self, g, out, P):
        flat = [v for row in out for v in row]
        return any(flat) and not all(flat)


# ---------------------------------------------------------------------------
class CopyTemplate(Family):
    name = 'copy_template_to_markers'
    ti = True

    def min_dims(self, P):
        return 7, 7

    def sample(self, rng, cat):
        return set_roles({}, rng, ['M', 'T'], [])

    def gen(self, rng, P, k, cap):
        hw = pick_hw(rng, cap, 7, 16, 7, 16)
        if not hw:
            return None
        h, w = hw
        M, T = P['roles']['M'], P['roles']['T']
        g = zeros(h, w)
        pl = Placer(h, w)
        p = pl.place(rng, 3, 3)
        if p is None:
            return None
        g[p[0] + 1][p[1] + 1] = M
        paint(g, [(p[0] + 1 + dr, p[1] + 1 + dc) for dr, dc in rng.sample(N8, rng.randint(3, 6))], T)
        placed = 0
        for _ in range(rng.randint(1, 3)):
            q = pl.place(rng, 3, 3)
            if q:
                g[q[0] + 1][q[1] + 1] = M
                placed += 1
        return g if placed else None

    @staticmethod
    def _nbrs(g, r, c):
        h, w = dims(g)
        return [(r + dr, c + dc) for dr, dc in N8
                if 0 <= r + dr < h and 0 <= c + dc < w and g[r + dr][c + dc] != 0]

    def templates(self, g, M):
        h, w = dims(g)
        marks = [(r, c) for r in range(h) for c in range(w) if g[r][c] == M]
        return marks, [m for m in marks if self._nbrs(g, *m)]

    def rule(self, g, P):
        marks, templ = self.templates(g, P['roles']['M'])
        out = copy(g)
        if len(templ) != 1:
            return out
        tr, tc = templ[0]
        pat = [(r - tr, c - tc, g[r][c]) for r, c in self._nbrs(g, tr, tc)]
        h, w = dims(g)
        for r, c in marks:
            if (r, c) != (tr, tc) and not self._nbrs(g, r, c):
                for dr, dc, v in pat:
                    if 0 <= r + dr < h and 0 <= c + dc < w and g[r + dr][c + dc] == 0:
                        out[r + dr][c + dc] = v
        return out

    def check_pair(self, g, out, P):
        return out != g and len(self.templates(g, P['roles']['M'])[1]) == 1


# ---------------------------------------------------------------------------
class SortBars(Family):
    name = 'sort_bars'

    def min_dims(self, P):
        return (4, 3) if P['base'] in ('bottom', 'top') else (3, 4)

    def sample(self, rng, cat):
        P = {'base': rng.choice(['bottom', 'top', 'left', 'right']), 'order': rng.choice(['asc', 'desc'])}
        return set_roles(P, rng, ['A'], [])

    def gen(self, rng, P, k, cap):
        vertical = P['base'] in ('bottom', 'top')
        hw = pick_hw(rng, cap, 4, 12, 3, 12) if vertical else pick_hw(rng, cap, 3, 12, 4, 12)
        if not hw:
            return None
        L, nb = hw if vertical else (hw[1], hw[0])
        heights = [rng.randint(0, L) for _ in range(nb)]
        if heights == sorted(heights, reverse=P['order'] == 'desc'):
            return None
        return self.render(heights, L, P)

    def render(self, heights, L, P):
        A = P['roles']['A']
        base = P['base']
        nb = len(heights)
        if base in ('bottom', 'top'):
            g = zeros(L, nb)
            for j, ht in enumerate(heights):
                for i in range(ht):
                    g[L - 1 - i if base == 'bottom' else i][j] = A
        else:
            g = zeros(nb, L)
            for j, ht in enumerate(heights):
                for i in range(ht):
                    g[j][i if base == 'left' else L - 1 - i] = A
        return g

    def rule(self, g, P):
        A = P['roles']['A']
        h, w = dims(g)
        if P['base'] in ('bottom', 'top'):
            L, heights = h, [sum(1 for r in range(h) if g[r][c] == A) for c in range(w)]
        else:
            L, heights = w, [row.count(A) for row in g]
        return self.render(sorted(heights, reverse=P['order'] == 'desc'), L, P)


# ---------------------------------------------------------------------------
class FilterByBox(Family):
    name = 'filter_by_box'
    ti = True

    def min_dims(self, P):
        return 8, 8

    def sample(self, rng, cat):
        P = {'mode': rng.choice(['keep_in', 'keep_out'])}
        return set_roles(P, rng, ['A', 'B'], [])

    def gen(self, rng, P, k, cap):
        hw = pick_hw(rng, cap, 8, 16, 8, 16)
        if not hw:
            return None
        h, w = hw
        A, B = P['roles']['A'], P['roles']['B']
        bh, bw = rng.randint(4, h - 2), rng.randint(4, w - 2)
        r0, c0 = rng.randint(0, h - bh), rng.randint(0, w - bw)
        g = zeros(h, w)
        paint(g, [(r, c) for r in range(r0, r0 + bh) for c in range(c0, c0 + bw)
                  if r in (r0, r0 + bh - 1) or c in (c0, c0 + bw - 1)], B)
        inside = [(r, c) for r in range(r0 + 1, r0 + bh - 1) for c in range(c0 + 1, c0 + bw - 1)]
        outside = [(r, c) for r in range(h) for c in range(w)
                   if not (r0 <= r < r0 + bh and c0 <= c < c0 + bw)]
        paint(g, rng.sample(inside, rng.randint(1, min(5, len(inside)))), A)
        paint(g, rng.sample(outside, rng.randint(1, min(6, len(outside)))), A)
        return g

    def rule(self, g, P):
        A, B = P['roles']['A'], P['roles']['B']
        h, w = dims(g)
        r0, c0, r1, c1 = bbox([(r, c) for r in range(h) for c in range(w) if g[r][c] == B])
        out = copy(g)
        for r in range(h):
            for c in range(w):
                if g[r][c] == A:
                    inside = r0 < r < r1 and c0 < c < c1
                    if inside != (P['mode'] == 'keep_in'):
                        out[r][c] = 0
        return out


# ---------------------------------------------------------------------------
class ContinuePattern(Family):
    name = 'continue_periodic_pattern'

    def min_dims(self, P):
        return (6, 3) if P['axis'] == 'down' else (3, 6)

    def sample(self, rng, cat):
        P = {'axis': rng.choice(['down', 'right'])}
        return set_roles(P, rng, palette_roles(rng), [])

    def gen(self, rng, P, k, cap):
        p = rng.choice([2, 3])
        if P['axis'] == 'down':
            hw = pick_hw(rng, cap, 2 * p + 2, 16, 3, 12)
        else:
            hw = pick_hw(rng, cap, 3, 12, 2 * p + 2, 16)
        if not hw:
            return None
        along, across = hw if P['axis'] == 'down' else (hw[1], hw[0])
        pal = palette(P)
        motif = []
        for _ in range(p):
            row = [rng.choice(pal) if rng.random() < 0.55 else 0 for _ in range(across)]
            if not any(row):
                return None
            motif.append(row)
        if all(row == motif[0] for row in motif):
            return None
        g = zeros(along, across)
        for r in range(2 * p):
            g[r] = motif[r % p][:]
        return g if P['axis'] == 'down' else transpose(g)

    @staticmethod
    def _continue(g):
        nonempty = [r for r, row in enumerate(g) if any(row)]
        if not nonempty:
            return copy(g)
        q = nonempty[-1] + 1
        for p in range(1, q // 2 + 1):
            if all(g[i] == g[i + p] for i in range(q - p)):
                return [g[r % p][:] for r in range(len(g))]
        return copy(g)

    def rule(self, g, P):
        if P['axis'] == 'down':
            return self._continue(g)
        return transpose(self._continue(transpose(g)))


FAMILIES = [Gravity(), FillEnclosed(), RecolorBySize(), SymmetryRepair(), MirrorTiling(),
            Upscale(), CropMarked(), CountToGrid(), ConnectPairs(), ExtendRays(),
            StampAround(), SlideToWall(), RecolorOrientation(), DenoiseRects(), FlipRotate(),
            PanelBoolean(), CopyTemplate(), SortBars(), FilterByBox(), ContinuePattern()]
