"""Small grid helpers shared by the generator and the checker (stdlib only)."""

N4 = [(-1, 0), (1, 0), (0, -1), (0, 1)]
DIAG4 = [(-1, -1), (-1, 1), (1, -1), (1, 1)]
N8 = N4 + DIAG4


def zeros(h, w, v=0):
    return [[v] * w for _ in range(h)]


def copy(g):
    return [row[:] for row in g]


def dims(g):
    return len(g), len(g[0])


def fliplr(g):
    return [row[::-1] for row in g]


def flipud(g):
    return [row[:] for row in g[::-1]]


def rot180(g):
    return fliplr(flipud(g))


def transpose(g):
    return [list(col) for col in zip(*g)]


def rot90cw(g):
    return [list(col) for col in zip(*g[::-1])]


def rot90ccw(g):
    return [list(col) for col in zip(*g)][::-1]


def components(g, pred, conn=N4):
    """Connected components (lists of (r, c), sorted) of cells whose value satisfies pred."""
    h, w = dims(g)
    seen = set()
    comps = []
    for r in range(h):
        for c in range(w):
            if (r, c) in seen or not pred(g[r][c]):
                continue
            seen.add((r, c))
            stack = [(r, c)]
            comp = []
            while stack:
                y, x = stack.pop()
                comp.append((y, x))
                for dy, dx in conn:
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and (ny, nx) not in seen and pred(g[ny][nx]):
                        seen.add((ny, nx))
                        stack.append((ny, nx))
            comps.append(sorted(comp))
    return comps


def component_at(g, cell, pred, conn=N4):
    for comp in components(g, pred, conn):
        if cell in comp:
            return comp
    return None


def bbox(cells):
    rs = [r for r, _ in cells]
    cs = [c for _, c in cells]
    return min(rs), min(cs), max(rs), max(cs)


def random_shape(rng, n, maxh, maxw):
    """Random 4-connected polyomino with up to n cells inside a maxh x maxw box, normalised to (0, 0)."""
    cells = [(0, 0)]
    cellset = {(0, 0)}
    tries = 0
    while len(cells) < n and tries < 400:
        tries += 1
        r, c = rng.choice(cells)
        dr, dc = rng.choice(N4)
        nr, nc = r + dr, c + dc
        if (nr, nc) in cellset:
            continue
        r0, c0, r1, c1 = bbox(cells + [(nr, nc)])
        if r1 - r0 + 1 <= maxh and c1 - c0 + 1 <= maxw:
            cells.append((nr, nc))
            cellset.add((nr, nc))
    r0, c0, _, _ = bbox(cells)
    return sorted((r - r0, c - c0) for r, c in cells)


def shape_dims(shape):
    _, _, r1, c1 = bbox(shape)
    return r1 + 1, c1 + 1


class Placer:
    """Places rectangular footprints so that any two are separated by at least `gap` empty cells."""

    def __init__(self, h, w):
        self.h, self.w = h, w
        self.boxes = []

    def free(self, r0, c0, r1, c1, gap=1):
        if r0 < 0 or c0 < 0 or r1 >= self.h or c1 >= self.w:
            return False
        for a0, b0, a1, b1 in self.boxes:
            if r0 <= a1 + gap and a0 <= r1 + gap and c0 <= b1 + gap and b0 <= c1 + gap:
                return False
        return True

    def add(self, box):
        self.boxes.append(box)

    def place(self, rng, bh, bw, gap=1, tries=150):
        if bh > self.h or bw > self.w:
            return None
        for _ in range(tries):
            r0 = rng.randint(0, self.h - bh)
            c0 = rng.randint(0, self.w - bw)
            if self.free(r0, c0, r0 + bh - 1, c0 + bw - 1, gap):
                self.add((r0, c0, r0 + bh - 1, c0 + bw - 1))
                return r0, c0
        return None
