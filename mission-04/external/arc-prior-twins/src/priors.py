"""Twin construction: one prior shift applied to an abstract (canonical) task.

(a) background: a solid non-zero background (optionally with colour 0 taking
    over one of the roles), a per-pair solid background (only together with b),
    or a position-dependent multi-colour background pattern (same-size families).
(b) role colours: the roles visible in the input are recoloured per pair
    (consistent inside a pair).  Several schemes are used: all roles fresh,
    only the primary role, roles crossing over between consecutive pairs, and
    a test pair whose colours never occur in training.
(c) frame of reference: content inside a border (with varying outer margin),
    in one panel or in every panel of a partitioned grid, in a window cut out
    of a filled grid, or at a varying offset inside a larger canvas.

A layout is a template grid T (-1 = background, 100 + c = structural colour c)
plus a list of content regions; the content of every region is rendered with
the pair's colour map `sigma` and background field.
"""
from grids import dims

DEFAULT_CAPS = {'h': 20, 'w': 20, 'oh': 20, 'ow': 20}
PATTERNS = ['checker', 'rows', 'cols', 'block', 'diag', 'anti', 'split_v', 'split_h']


def solid(c):
    return {'type': 'solid', 'colors': [c]}


def field_value(f, r, c, H, W):
    t, cs = f['type'], f['colors']
    if t == 'solid':
        return cs[0]
    if t == 'checker':
        return cs[(r + c) % 2]
    if t == 'rows':
        return cs[r % len(cs)]
    if t == 'cols':
        return cs[c % len(cs)]
    if t == 'block':
        return cs[(r // 2 + c // 2) % 2]
    if t == 'diag':
        return cs[(r + c) % len(cs)]
    if t == 'anti':
        return cs[(r - c) % len(cs)]
    if t == 'split_v':
        return cs[0] if c < W // 2 else cs[1]
    if t == 'split_h':
        return cs[0] if r < H // 2 else cs[1]
    raise ValueError(t)


def weighted(rng, options):
    total = sum(wt for _, wt in options)
    x = rng.uniform(0, total)
    for name, wt in options:
        x -= wt
        if x <= 0:
            return name
    return options[-1][0]


# ---------------------------------------------------------------------------
# layouts

def direct_layout(h, w):
    return {'T': [[-1] * w for _ in range(h)], 'regions': [(0, 0, h, w)], 'main': 0}


def frame_layout(h, w, th, mt, mb, ml, mr, color):
    H, W = h + 2 * th + mt + mb, w + 2 * th + ml + mr
    T = [[-1] * W for _ in range(H)]
    r0, c0 = mt + th, ml + th
    for r in range(mt, mt + h + 2 * th):
        for c in range(ml, ml + w + 2 * th):
            if not (r0 <= r < r0 + h and c0 <= c < c0 + w):
                T[r][c] = 100 + color
    return {'T': T, 'regions': [(r0, c0, h, w)], 'main': 0}


def window_layout(h, w, mt, mb, ml, mr, color):
    H, W = h + mt + mb, w + ml + mr
    T = [[100 + color] * W for _ in range(H)]
    for r in range(mt, mt + h):
        for c in range(ml, ml + w):
            T[r][c] = -1
    return {'T': T, 'regions': [(mt, ml, h, w)], 'main': 0}


def panels_layout(h, w, R, C, b, color, main):
    H, W = R * h + (R - 1) + 2 * b, C * w + (C - 1) + 2 * b
    T = [[100 + color] * W for _ in range(H)]
    regions = []
    for i in range(R):
        for j in range(C):
            r0, c0 = b + i * (h + 1), b + j * (w + 1)
            for r in range(r0, r0 + h):
                for c in range(c0, c0 + w):
                    T[r][c] = -1
            regions.append((r0, c0, h, w))
    return {'T': T, 'regions': regions, 'main': main}


def offset_layout(h, w, H, W, r0, c0):
    return {'T': [[-1] * W for _ in range(H)], 'regions': [(r0, c0, h, w)], 'main': 0}


def choose_layout(rng, fam, P):
    """Pick the (c) layout type for a task and the content size caps it implies."""
    mh, mw = fam.min_dims(P)
    opts = [('frame', 3), ('window', 2)]
    if fam.panels_ok:
        opts.append(('panels_one', 2))
        if fam.kind == 'same':
            opts.append(('panels_all', 2))
    if fam.ti:
        opts.append(('offset', 3))
    while opts:
        t = weighted(rng, opts)
        opts = [o for o in opts if o[0] != t]
        c = _layout_params(rng, t, fam, mh, mw)
        if c:
            return c
    return None


def _layout_params(rng, t, fam, mh, mw):
    resize = fam.kind == 'resize'
    if t == 'frame':
        th = rng.choice([1, 1, 2])
        cap = 20 - 2 * th - rng.choice([0, 2, 4])
        out_mode = rng.choice(['raw', 'framed']) if resize else 'same'
        ocap = 20 - 2 * th if out_mode == 'framed' else 20
        c = {'type': t, 'thick': th, 'out_mode': out_mode,
             'caps': {'h': cap, 'w': cap, 'oh': ocap, 'ow': ocap}}
    elif t == 'window':
        cap = 20 - rng.choice([2, 3, 4])
        c = {'type': t, 'out_mode': 'raw' if resize else 'same',
             'caps': {'h': cap, 'w': cap, 'oh': 20, 'ow': 20}}
    elif t in ('panels_one', 'panels_all'):
        arrs = [(1, 2), (2, 1), (1, 3), (3, 1), (2, 2)]
        rng.shuffle(arrs)
        c = None
        for R, C in arrs:
            b = rng.choice([0, 1])
            ch, cw = (20 - (R - 1) - 2 * b) // R, (20 - (C - 1) - 2 * b) // C
            if ch >= mh and cw >= mw:
                c = {'type': t, 'grid': [R, C], 'border': b, 'out_mode': 'raw' if resize else 'same',
                     'caps': {'h': ch, 'w': cw, 'oh': 20, 'ow': 20}}
                break
        if c is None:
            return None
    else:
        cap = rng.choice([12, 14, 16])
        c = {'type': 'offset', 'out_mode': 'raw' if resize else 'same',
             'caps': {'h': cap, 'w': cap, 'oh': 20, 'ow': 20}}
    if c['caps']['h'] < mh or c['caps']['w'] < mw:
        return None
    return c


def make_layout(rng, c, h, w, struct):
    t = c['type']
    if t == 'frame':
        th = c['thick']
        ev = rng.randint(0, min(20 - h - 2 * th, 4))
        eh = rng.randint(0, min(20 - w - 2 * th, 4))
        mt, ml = rng.randint(0, ev), rng.randint(0, eh)
        return frame_layout(h, w, th, mt, ev - mt, ml, eh - ml, struct)
    if t == 'window':
        while True:
            ev, eh = rng.randint(0, min(20 - h, 5)), rng.randint(0, min(20 - w, 5))
            if ev + eh >= 2:
                break
        mt, ml = rng.randint(0, ev), rng.randint(0, eh)
        return window_layout(h, w, mt, ev - mt, ml, eh - ml, struct)
    if t in ('panels_one', 'panels_all'):
        R, C = c['grid']
        return panels_layout(h, w, R, C, c['border'], struct, rng.randrange(R * C))
    while True:
        ev, eh = rng.randint(0, min(20 - h, 8)), rng.randint(0, min(20 - w, 8))
        if ev + eh >= 3:
            break
    return offset_layout(h, w, h + ev, w + eh, rng.randint(0, ev), rng.randint(0, eh))


def make_out_layout(c, oh, ow, struct):
    if c and c['out_mode'] == 'framed':
        return frame_layout(oh, ow, c['thick'], 0, 0, 0, 0, struct)
    return direct_layout(oh, ow)


def render(lay, contents, sigma, field):
    T = lay['T']
    H, W = dims(T)
    G = [row[:] for row in T]
    for idx, g in contents.items():
        r0, c0, h, w = lay['regions'][idx]
        for i in range(h):
            for j in range(w):
                G[r0 + i][c0 + j] = g[i][j] if g[i][j] != 0 else -1
    out = []
    for r in range(H):
        row = []
        for c in range(W):
            v = G[r][c]
            if v == -1:
                row.append(field_value(field, r, c, H, W))
            elif v >= 100:
                row.append(v - 100)
            else:
                row.append(sigma[v])
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# colours

def plan_colors(rng, fam, P, cat, n, n_train, c):
    roles = P['roles']
    canon = sorted(set(roles.values()))
    sigma = {v: v for v in canon}
    free_nz = [x for x in range(1, 10) if x not in canon]
    info = {}
    if 'a' in cat:
        modes = [('solid', 3), ('solid_zero', 2)]
        if fam.kind == 'same':
            modes += [(p, 1.2) for p in PATTERNS]
        mode = weighted(rng, modes)
        if mode == 'solid':
            if 'b' in cat and len(free_nz) >= n and rng.random() < 0.5:
                fields = [solid(x) for x in rng.sample(free_nz, n)]
                mode = 'solid_per_pair'
            else:
                fields = [solid(rng.choice(free_nz))] * n
        elif mode == 'solid_zero':
            sigma[roles[rng.choice(sorted(roles))]] = 0
            fields = [solid(rng.choice(free_nz))] * n
        else:
            if mode in ('checker', 'block', 'split_v', 'split_h'):
                k = 2
            elif mode in ('diag', 'anti'):
                k = 3
            else:
                k = rng.choice([2, 3])
            cols = [0] + rng.sample(free_nz, k - 1) if rng.random() < 0.35 else rng.sample(free_nz, k)
            rng.shuffle(cols)
            fields = [{'type': mode, 'colors': cols}] * n
        info['a_mode'] = mode
    else:
        fields = [solid(0)] * n
    fcols = {x for f in fields for x in f['colors']}
    struct = None
    if c:
        used = set(sigma.values()) | fcols
        cand = [x for x in range(10) if x not in used]
        if not cand:
            return None
        struct = rng.choice(cand)
        info['c_type'] = c['type']
    if 'b' in cat:
        excl = fcols | {sigma[roles[r]] for r in P['const']}
        if struct is not None:
            excl.add(struct)
        pool = [x for x in range(10) if x not in excl]
        res = choose_sigmas(rng, P, sigma, pool, n, n_train)
        if res is None:
            return None
        info['b_mode'], sigmas = res
    else:
        sigmas = [dict(sigma) for _ in range(n)]
    return {'fields': fields, 'struct': struct, 'sigmas': sigmas, 'info': info}


def choose_sigmas(rng, P, base, pool, n, n_train):
    roles, perm, prim = P['roles'], P['perm'], P['primary']
    modes = ['all', 'primary', 'novel'] + (['cross'] if len(perm) >= 2 else [])
    mode = rng.choice(modes)
    keep = [base[roles[r]] for r in perm if r != prim]
    others = [r for r in perm if r != prim]
    for attempt in range(800):
        strict = attempt < 500
        sig = []
        for k in range(n):
            s = dict(base)
            if mode == 'primary':
                ch = [x for x in pool if x not in keep]
                if not ch:
                    return None
                s[roles[prim]] = rng.choice(ch)
            else:
                avail = pool[:]
                if mode == 'novel' and k == n - 1:
                    seen = {sig[j][roles[r]] for j in range(n_train) for r in perm}
                    fresh = [x for x in avail if x not in seen]
                    if len(fresh) >= len(perm):
                        avail = fresh
                if len(avail) < len(perm):
                    return None
                if mode == 'cross' and k >= 1:
                    pc = rng.choice([sig[k - 1][roles[r]] for r in others])
                    cols = [pc] + rng.sample([x for x in avail if x != pc], len(perm) - 1)
                    order = [prim] + others
                else:
                    cols = rng.sample(avail, len(perm))
                    order = perm
                for r, x in zip(order, cols):
                    s[roles[r]] = x
            sig.append(s)
        prims = [s[roles[prim]] for s in sig]
        if len(set(prims[:n_train])) != n_train:
            continue
        if strict and prims[-1] in prims[:n_train]:
            continue
        if len({tuple(s[roles[r]] for r in perm) for s in sig}) != n:
            continue
        if any(len(set(s.values())) != len(s) for s in sig):
            continue
        return mode, sig
    return None
