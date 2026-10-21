"""Generate the canonical / twin task pairs, metadata.json and MANIFEST.json.

Usage:  python3 src/generate.py          (writes into the project root)

Fully deterministic (fixed seeds); src/check.py regenerates in memory and
verifies the files on disk against it.
"""
import hashlib
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import priors  # noqa: E402
from families import FAMILIES  # noqa: E402
from grids import dims  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SEED = 7340211
NAME_SEED = 90210417
COMBOS = ['a+b', 'a+c', 'b+c']
PER_FAMILY = ['a'] * 3 + ['b'] * 3 + ['c'] * 3


def task_plan():
    plan = []
    for i, fam in enumerate(FAMILIES):
        for prior in PER_FAMILY + [COMBOS[i % len(COMBOS)]]:
            plan.append((fam, prior))
    return plan


def gen_pair(rng, fam, P, k, caps, tries=400):
    for _ in range(tries):
        g = fam.gen(rng, P, k, caps)
        if g is None:
            continue
        h, w = dims(g)
        if not (3 <= h <= caps['h'] and 3 <= w <= caps['w']):
            continue
        if caps.get('fix') and (h, w) != tuple(caps['fix']):
            continue
        o = fam.rule(g, P)
        oh, ow = dims(o)
        if not (3 <= oh <= caps['oh'] and 3 <= ow <= caps['ow']):
            continue
        if fam.kind == 'same' and (oh, ow) != (h, w):
            continue
        # every recolourable role must be visible in the input
        if not all(any(P['roles'][r] in row for row in g) for r in P['perm']):
            continue
        if not fam.check_pair(g, o, P):
            continue
        return g, o
    return None


def task_ok(pairs, n_train):
    ins = [json.dumps(p[0]) for p in pairs]
    if len(set(ins)) != len(ins):
        return False
    return len({json.dumps(p[1]) for p in pairs[:n_train]}) > 1


def to_task(pairs, n_train):
    return {'train': [{'input': i, 'output': o} for i, o in pairs[:n_train]],
            'test': [{'input': i, 'output': o} for i, o in pairs[n_train:]]}


def build_base(rng, fam, prior):
    cat = prior.replace('+', '')
    for _ in range(300):
        P = fam.sample(rng, cat)
        c = priors.choose_layout(rng, fam, P) if 'c' in cat else None
        if 'c' in cat and c is None:
            continue
        caps = c['caps'] if c else priors.DEFAULT_CAPS
        n_train = rng.choice([3, 4])
        n = n_train + 1
        pairs = []
        for k in range(n):
            pr = gen_pair(rng, fam, P, k, caps)
            if pr is None:
                break
            pairs.append(pr)
        if len(pairs) < n or not task_ok(pairs, n_train):
            continue
        colors = priors.plan_colors(rng, fam, P, cat, n, n_train, c)
        if colors is None:
            continue
        twin_pairs, ctx = [], []
        failed = False
        for k, (gi, go) in enumerate(pairs):
            h, w = dims(gi)
            lay_in = priors.make_layout(rng, c, h, w, colors['struct']) if c else priors.direct_layout(h, w)
            cin, cout = {lay_in['main']: gi}, {lay_in['main']: go}
            extras = []
            if c and c['type'] == 'panels_all':
                for idx in range(len(lay_in['regions'])):
                    if idx == lay_in['main']:
                        continue
                    pr = gen_pair(rng, fam, P, k, dict(caps, fix=(h, w)))
                    if pr is None:
                        failed = True
                        break
                    cin[idx], cout[idx] = pr
                    extras.append(idx)
                if failed:
                    break
            if fam.kind == 'same':
                lay_out = lay_in
            else:
                lay_out = priors.make_out_layout(c, *dims(go), colors['struct'])
                cout = {lay_out['main']: go}
            sigma, field = colors['sigmas'][k], colors['fields'][k]
            twin_pairs.append((priors.render(lay_in, cin, sigma, field),
                               priors.render(lay_out, cout, sigma, field)))
            ctx.append({'lay_in': lay_in, 'lay_out': lay_out, 'sigma': sigma, 'field': field,
                        'extras': extras})
        if failed:
            continue
        if any(not 3 <= d <= 20 for ti, to in twin_pairs for d in dims(ti) + dims(to)):
            continue
        return {'family': fam.name, 'prior': prior, 'P': P, 'n_train': n_train,
                'pairs': pairs, 'ctx': ctx, 'layout': c, 'struct': colors['struct'],
                'info': colors['info'],
                'canonical': to_task(pairs, n_train), 'twin': to_task(twin_pairs, n_train)}
    raise RuntimeError('could not build a task for %s / %s' % (fam.name, prior))


def build_all():
    rng = random.Random(SEED)
    records = [build_base(rng, fam, prior) for fam, prior in task_plan()]
    nrng = random.Random(NAME_SEED)
    used = set()

    def fresh():
        while True:
            s = '%08x.json' % nrng.getrandbits(32)
            if s not in used:
                used.add(s)
                return s

    for rec in records:
        rec['canonical_file'] = fresh()
    order = list(range(len(records)))
    nrng.shuffle(order)
    for i in order:
        records[i]['twin_file'] = fresh()
    return records


def dump_task(task):
    return json.dumps(task, separators=(',', ':'))


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def manifest(root):
    files = {}
    for d in ('canonical', 'twin'):
        for p in sorted((root / d).glob('*.json')):
            files['%s/%s' % (d, p.name)] = sha256_file(p)
    files['metadata.json'] = sha256_file(root / 'metadata.json')
    lines = ''.join('%s  %s\n' % (files[k], k) for k in sorted(files))
    return {'algorithm': 'sha256',
            'aggregate_method': "sha256 of the UTF-8 text formed by one line '<sha256>  <path>\\n' "
                                'per listed file, files sorted by path',
            'aggregate_sha256': hashlib.sha256(lines.encode('utf-8')).hexdigest(),
            'files': {k: files[k] for k in sorted(files)}}


def write_outputs(records, root=ROOT):
    for d in ('canonical', 'twin'):
        (root / d).mkdir(exist_ok=True)
        for p in (root / d).glob('*.json'):
            p.unlink()
    for rec in records:
        (root / 'canonical' / rec['canonical_file']).write_text(dump_task(rec['canonical']))
        (root / 'twin' / rec['twin_file']).write_text(dump_task(rec['twin']))
    entries = sorted(({'canonical': r['canonical_file'], 'twin': r['twin_file'],
                       'family': r['family'], 'prior': r['prior']} for r in records),
                     key=lambda e: e['canonical'])
    meta = {
        'n_base_tasks': len(entries),
        'prior_legend': {
            'a': 'background is not 0, or not a single colour',
            'b': 'colours of the same role differ between pairs (consistent within a pair)',
            'c': 'content sits inside a border / partition of a larger grid, or at an offset',
        },
        'tasks': entries,
    }
    (root / 'metadata.json').write_text(json.dumps(meta, indent=1) + '\n')
    (root / 'MANIFEST.json').write_text(json.dumps(manifest(root), indent=1) + '\n')


def main():
    records = build_all()
    write_outputs(records)
    counts = {}
    for r in records:
        counts[r['prior']] = counts.get(r['prior'], 0) + 1
    print('base tasks:', len(records))
    print('prior counts:', json.dumps(counts, sort_keys=True))
    print('MANIFEST.json sha256:', sha256_file(ROOT / 'MANIFEST.json'))
    print('aggregate sha256:', json.loads((ROOT / 'MANIFEST.json').read_text())['aggregate_sha256'])


if __name__ == '__main__':
    main()
