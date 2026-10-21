"""Verify the generated dataset on disk.

Usage:  python3 src/check.py

Checks performed (any failure is listed and the exit code is 1):
  * layout: canonical/ and twin/ hold one <8 hex>.json per task, names unique,
    metadata.json pairs every file exactly once, MANIFEST.json hashes match;
  * format: 3-4 train pairs, 1 test pair, rectangular grids, sides 3..20,
    colours 0..9;
  * the generator is re-run in memory (fixed seeds) and every file must match
    it byte for byte; this gives each task's rule parameters and, for twins,
    the per-pair colour map / background / layout used;
  * canonical: every train and test pair satisfies the family rule with the
    task's single parameter set, background 0, only the task's role colours,
    no pair is unchanged, train outputs are not all identical;
  * twin: every grid is decoded back to abstract form with an independent
    decoder (structure cells, background field and colour map must be exactly
    as declared, colour classes must not collide), the decoded content must
    equal the canonical pair, the same rule must map decoded input to decoded
    output for all train and test pairs (also in extra panels), and for offset
    layouts the rule must also hold on the whole decoded canvas;
  * prior labels: (a) the background is non-zero or multi-coloured in every
    pair, (b) the primary role colour differs across all train pairs, is
    visible in each input, and no two pairs share a colour assignment,
    (c) the content does not fill the grid (border / panels / window /
    offset); priors that are not in the label must be left unchanged.
"""
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate  # noqa: E402
from families import FAMILIES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FAM = {f.name: f for f in FAMILIES}
NAME_RE = re.compile(r'^[0-9a-f]{8}\.json$')


class Fail(Exception):
    pass


def ensure(cond, msg):
    if not cond:
        raise Fail(msg)


# --------------------------------------------------------------------------- format

def check_grid(g, where):
    ensure(isinstance(g, list) and 3 <= len(g) <= 20, '%s: bad height' % where)
    w = len(g[0]) if isinstance(g[0], list) else -1
    ensure(3 <= w <= 20, '%s: bad width' % where)
    for row in g:
        ensure(isinstance(row, list) and len(row) == w, '%s: ragged grid' % where)
        for v in row:
            ensure(type(v) is int and 0 <= v <= 9, '%s: bad colour' % where)


def check_format(task, where):
    ensure(set(task) == {'train', 'test'}, '%s: keys' % where)
    ensure(3 <= len(task['train']) <= 4, '%s: train count' % where)
    ensure(len(task['test']) == 1, '%s: test count' % where)
    for i, pair in enumerate(task['train'] + task['test']):
        ensure(set(pair) == {'input', 'output'}, '%s: pair keys' % where)
        check_grid(pair['input'], '%s pair %d input' % (where, i))
        check_grid(pair['output'], '%s pair %d output' % (where, i))


def pairs_of(task):
    return [(p['input'], p['output']) for p in task['train'] + task['test']]


# --------------------------------------------------------------------------- decoder
# Deliberately independent of priors.render / priors.field_value.

def bg_at(field, r, c, H, W):
    t, cs = field['type'], field['colors']
    table = {
        'solid': lambda: cs[0],
        'checker': lambda: cs[(r + c) & 1],
        'rows': lambda: cs[r % len(cs)],
        'cols': lambda: cs[c % len(cs)],
        'block': lambda: cs[((r >> 1) + (c >> 1)) & 1],
        'diag': lambda: cs[(r + c) % len(cs)],
        'anti': lambda: cs[(r - c) % len(cs)],
        'split_v': lambda: cs[0 if 2 * c < 2 * (W // 2) else 1],
        'split_h': lambda: cs[0 if 2 * r < 2 * (H // 2) else 1],
    }
    return table[t]()


def struct_colors(lay):
    return {v - 100 for row in lay['T'] for v in row if v >= 100}


def decode(G, lay, sigma, field):
    T = lay['T']
    H, W = len(G), len(G[0])
    ensure((H, W) == (len(T), len(T[0])), 'decoded grid size differs from layout')
    inv = {}
    for k, v in sigma.items():
        ensure(v not in inv, 'colour map is not injective')
        inv[v] = k
    ensure(not (set(inv) & set(field['colors'])), 'role colour equals a background colour')
    ensure(not (set(inv) & struct_colors(lay)), 'role colour equals a structure colour')
    owner = {}
    for idx, (r0, c0, h, w) in enumerate(lay['regions']):
        for i in range(h):
            for j in range(w):
                ensure((r0 + i, c0 + j) not in owner, 'overlapping regions')
                owner[(r0 + i, c0 + j)] = (idx, i, j)
    out = {idx: [[None] * w for _ in range(h)] for idx, (_, _, h, w) in enumerate(lay['regions'])}
    for r in range(H):
        for c in range(W):
            v, bg = G[r][c], bg_at(field, r, c, H, W)
            if (r, c) in owner:
                idx, i, j = owner[(r, c)]
                if v == bg:
                    out[idx][i][j] = 0
                else:
                    ensure(v in inv, 'unexpected colour %d inside content' % v)
                    out[idx][i][j] = inv[v]
            elif T[r][c] >= 100:
                ensure(v == T[r][c] - 100, 'structure cell has wrong colour')
            else:
                ensure(v == bg, 'background cell outside content has wrong colour')
    return out


def decode_canvas(G, sigma, field):
    """Whole-grid decode for offset layouts (no structure cells)."""
    H, W = len(G), len(G[0])
    inv = {v: k for k, v in sigma.items()}
    res = []
    for r in range(H):
        row = []
        for c in range(W):
            v = G[r][c]
            row.append(0 if v == bg_at(field, r, c, H, W) else inv[v])
        res.append(row)
    return res


# --------------------------------------------------------------------------- task checks

def verify_canonical(rec, task):
    fam, P = FAM[rec['family']], rec['P']
    allowed = {0} | set(P['roles'].values())
    prs = pairs_of(task)
    for k, (gi, go) in enumerate(prs):
        ensure(fam.rule(gi, P) == go, 'canonical pair %d violates the rule' % k)
        ensure(gi != go, 'canonical pair %d is unchanged' % k)
        for r in P['perm']:
            ensure(any(P['roles'][r] in row for row in gi), 'canonical pair %d: role colour not visible' % k)
        for g in (gi, go):
            ensure({v for row in g for v in row} <= allowed, 'canonical pair %d uses a foreign colour' % k)
    outs = {json.dumps(go) for _, go in prs[:len(task['train'])]}
    ensure(len(outs) > 1, 'all canonical train outputs identical')


def verify_twin(rec, twin, canon):
    fam, P, prior = FAM[rec['family']], rec['P'], rec['prior']
    roles, prim = P['roles'], P['primary']
    tp, cp = pairs_of(twin), pairs_of(canon)
    n_train = len(twin['train'])
    ensure(len(tp) == len(cp) and n_train == len(canon['train']), 'pair count differs from canonical')
    ctx = rec['ctx']
    for k, ((ti, to), (ci, co)) in enumerate(zip(tp, cp)):
        x = ctx[k]
        lin, lout, sigma, field = x['lay_in'], x['lay_out'], x['sigma'], x['field']
        din = decode(ti, lin, sigma, field)
        dout = decode(to, lout, sigma, field)
        m = lin['main']
        ensure(din[m] == ci, 'twin pair %d: decoded input differs from canonical' % k)
        ensure(dout[lout['main']] == co, 'twin pair %d: decoded output differs from canonical' % k)
        ensure(fam.rule(din[m], P) == dout[lout['main']], 'twin pair %d violates the rule' % k)
        if fam.kind == 'same':
            ensure(lout is lin or lout == lin, 'twin pair %d: output layout differs' % k)
            for idx in din:
                if idx == m:
                    continue
                if idx in x['extras']:
                    ensure(fam.rule(din[idx], P) == dout[idx], 'twin pair %d panel %d violates rule' % (k, idx))
                    ensure(din[idx] != dout[idx], 'twin pair %d panel %d unchanged' % (k, idx))
                else:
                    ensure(all(v == 0 for row in din[idx] + dout[idx] for v in row),
                           'twin pair %d: empty panel %d is not empty' % (k, idx))
        if rec['layout'] and rec['layout']['type'] == 'offset':
            full_in = decode_canvas(ti, sigma, field)
            want = decode_canvas(to, sigma, field) if fam.kind == 'same' else co
            ensure(fam.rule(full_in, P) == want, 'twin pair %d: rule fails on the whole canvas' % k)

        # (a) background
        fl = field['type'] != 'solid' or field['colors'] != [0]
        if 'a' in prior:
            H, W = len(ti), len(ti[0])
            seen = {bg_at(field, r, c, H, W) for r in range(H) for c in range(W)
                    if lin['T'][r][c] == -1}
            ensure(fl and (len(seen) > 1 or 0 not in seen), 'twin pair %d: background prior not changed' % k)
        else:
            ensure(not fl, 'twin pair %d: background changed without label a' % k)
        # (c) frame of reference
        moved = len(lin['regions']) > 1 or dims_of(ti) != dims_of(ci) or struct_colors(lin)
        if 'c' in prior:
            ensure(moved, 'twin pair %d: frame of reference not changed' % k)
        else:
            ensure(not moved and lin['regions'][0][:2] == (0, 0), 'twin pair %d: layout changed without c' % k)

    sig = [x['sigma'] for x in ctx]
    if 'b' in prior:
        prims = [s[roles[prim]] for s in sig]
        ensure(len(set(prims[:n_train])) == n_train, 'primary role colour repeats across train pairs')
        for k, (ti, _) in enumerate(tp):
            for r in P['perm']:
                ensure(any(sig[k][roles[r]] in row for row in ti), 'pair %d: role colour not visible' % k)
        assign = {tuple(s[roles[r]] for r in P['perm']) for s in sig}
        ensure(len(assign) == len(sig), 'two pairs share the same colour assignment')
        for s in sig:
            for r in P['const']:
                ensure(s[roles[r]] == sig[0][roles[r]], 'constant role recoloured per pair')
    else:
        ensure(all(s == sig[0] for s in sig), 'colours vary per pair without label b')
    if 'a' not in prior and 'b' not in prior:
        ensure(all(k == v for k, v in sig[0].items()), 'colours changed without label a/b')


def dims_of(g):
    return len(g), len(g[0])


# --------------------------------------------------------------------------- main

def main():
    errors = []
    meta = json.loads((ROOT / 'metadata.json').read_text())
    man = json.loads((ROOT / 'MANIFEST.json').read_text())
    cfiles = sorted(p.name for p in (ROOT / 'canonical').iterdir())
    tfiles = sorted(p.name for p in (ROOT / 'twin').iterdir())
    entries = meta['tasks']

    def check(cond, msg):
        if not cond:
            errors.append(msg)

    check(all(NAME_RE.match(n) for n in cfiles + tfiles), 'file name pattern')
    check(len(set(cfiles + tfiles)) == len(cfiles) + len(tfiles), 'file names not unique across dirs')
    check(sorted(e['canonical'] for e in entries) == cfiles, 'metadata canonical set != canonical/')
    check(sorted(e['twin'] for e in entries) == tfiles, 'metadata twin set != twin/')
    check(meta['n_base_tasks'] == len(entries), 'n_base_tasks mismatch')

    # manifest
    files = {}
    for d, names in (('canonical', cfiles), ('twin', tfiles)):
        for n in names:
            files['%s/%s' % (d, n)] = hashlib.sha256((ROOT / d / n).read_bytes()).hexdigest()
    files['metadata.json'] = hashlib.sha256((ROOT / 'metadata.json').read_bytes()).hexdigest()
    check(man['files'] == files, 'MANIFEST file hashes mismatch')
    agg = hashlib.sha256(''.join('%s  %s\n' % (files[p], p) for p in sorted(files)).encode()).hexdigest()
    check(man['aggregate_sha256'] == agg, 'MANIFEST aggregate mismatch')

    records = {r['canonical_file']: r for r in generate.build_all()}
    check(len(records) == len(entries), 'regenerated task count differs')
    passed = 0
    for e in entries:
        where = e['canonical']
        try:
            rec = records.get(e['canonical'])
            ensure(rec is not None, 'no regenerated record')
            ensure(rec['twin_file'] == e['twin'] and rec['family'] == e['family'] and rec['prior'] == e['prior'],
                   'metadata entry differs from regeneration')
            ctext = (ROOT / 'canonical' / e['canonical']).read_text()
            ttext = (ROOT / 'twin' / e['twin']).read_text()
            ensure(ctext == generate.dump_task(rec['canonical']), 'canonical file differs from regeneration')
            ensure(ttext == generate.dump_task(rec['twin']), 'twin file differs from regeneration')
            ctask, ttask = json.loads(ctext), json.loads(ttext)
            check_format(ctask, 'canonical')
            check_format(ttask, 'twin')
            verify_canonical(rec, ctask)
            verify_twin(rec, ttask, ctask)
            passed += 1
        except Fail as ex:
            errors.append('%s: %s' % (where, ex))
        except Exception as ex:  # decoding errors etc.
            errors.append('%s: %s: %s' % (where, type(ex).__name__, ex))

    priors = Counter(e['prior'] for e in entries)
    per_class = {k: sum(v for p, v in priors.items() if k in p) for k in 'abc'}
    print('base tasks: %d' % len(entries))
    print('canonical files: %d, twin files: %d' % (len(cfiles), len(tfiles)))
    print('prior labels: %s' % json.dumps(dict(sorted(priors.items()))))
    print('per prior class (incl. combos): %s' % json.dumps(per_class))
    print('base tasks passing all checks: %d / %d' % (passed, len(entries)))
    print('MANIFEST.json sha256: %s' % hashlib.sha256((ROOT / 'MANIFEST.json').read_bytes()).hexdigest())
    print('aggregate sha256: %s' % man['aggregate_sha256'])
    if errors:
        print('FAILURES: %d' % len(errors))
        for m in errors[:50]:
            print('  ' + m)
        return 1
    print('ALL CHECKS PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
