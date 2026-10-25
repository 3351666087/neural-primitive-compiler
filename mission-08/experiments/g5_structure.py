"""Gate 5 judge, structure line (PRE_REGISTRATION.md section 2 with amendments A1, A2, A4). Runs once, after the
freeze, with M08_JUDGE=1. All models are fitted on development data only, with the hyperparameters selected at Gate 4
(results/g4/selection.json); the held-out targets are read only to score. Targets: White N2U (adult; training W7,
W8), White JSH (40 h), Witvliet 2 (5 h) and 4 (16 h) (training W1, W3, W5, W6, W7, W8 on the developmental neuron
set). Secondary analyses of amendment A4.3 (degrees, reciprocity, bilateral mirror, ambiguity, contact condition) are
reported alongside and do not enter the verdict. Writes results/g5/structure.json (structure_min3.json with
--min-synapses 3, the section 1 sensitivity analysis).
  M08_JUDGE=1 python3 -I experiments/g5_structure.py [--grid 10] [--boot 2000] [--min-synapses 1]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from g3_development_dev import DEV, dev_cells  # noqa: E402
from m08 import candidates as K, celegans as C, ledger, metrics as M, models as Mo, rs  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
K1_BLOCKS = ["coarse", "nt_pair", "dist", "lineage", "birth"]          # G4_CANDIDATE_LOG.md trial 1
SEL = json.loads((ROOT / "results" / "g4" / "selection.json").read_text())["results"]["chosen"]
K_B3, C_B4, GAMMA = int(SEL["B3_k"]), float(SEL["B4_C"]), float(SEL["R1_gamma"])
ALPHA_M1, ALPHA_M2 = float(SEL["M1_alpha"]), float(SEL["M2_alpha"])
FAMILIES = ("B1", "B2", "B3", "B4", "K1", "R1-cook", "R1-inferred8", "R1-dev", "M1", "M2", "M3", "M4")
DRY = False
MIN_SYN = 1


def mirror_index(cells):
    """Index of the bilateral counterpart (AVAL <-> AVAR), -1 for unpaired neurons."""
    ix = {c: i for i, c in enumerate(cells)}
    return np.array([ix.get(c[:-1] + ("R" if c[-1] == "L" else "L"), -1) if c[-1] in "LR" else -1 for c in cells])


def secondary(ctx, tgt, preds, m, y, joint):
    """Amendment A4.3: degree correlations, reciprocity, bilateral mirror bound, cross-family correlations."""
    I, J = ctx.I[m], ctx.J[m]
    n = len(ctx.cells)
    obs_out, obs_in = np.bincount(I, y, n), np.bincount(J, y, n)
    pres = tgt.present
    deg = {}
    for k, p in preds.items():
        q = p[m]
        deg[k] = {"out": float(spearmanr(np.bincount(I, q, n)[pres], obs_out[pres])[0]),
                  "in": float(spearmanr(np.bincount(J, q, n)[pres], obs_in[pres])[0])}
    A = tgt.A
    rev = A[ctx.J, ctx.I][m]
    dens = float(y.mean())
    rec_obs = float((y * rev).sum() / y.sum())
    pos_index = {(i, j): t for t, (i, j) in enumerate(zip(ctx.I, ctx.J))}
    rev_idx = np.array([pos_index[(j, i)] for i, j in zip(ctx.I, ctx.J)])
    rec = {}
    for k, p in preds.items():
        if k in joint:                               # reciprocity model: joint dyad probability over pairs i < j
            rec[k] = float(2 * joint[k][m[ctx.I < ctx.J]].sum() / p[m].sum())
        else:
            rec[k] = float((p * p[rev_idx])[m].sum() / p[m].sum())
    mir = mirror_index(ctx.cells)
    ok = (mir[ctx.I] >= 0) & (mir[ctx.J] >= 0) & m
    ok &= pres[np.maximum(mir[ctx.I], 0)] & pres[np.maximum(mir[ctx.J], 0)]
    ys = ctx.flat(A)[ok]
    mscore = A[mir[ctx.I[ok]], mir[ctx.J[ok]]]
    mirror = {"n_pairs": int(ok.sum()), "n_pos": int(ys.sum()), "mirror": {"auroc": M.auroc(mscore, ys), "auprc": M.auprc(mscore, ys)},
              "models_auprc_same_pairs": {k: M.auprc(p[ok], ys) for k, p in preds.items()}}
    fam = [k for k in FAMILIES if k in preds]
    rho = spearmanr(np.column_stack([Mo.logit(preds[k][m]) for k in fam]))[0]
    corr = {a: {b: float(rho[i, j]) for j, b in enumerate(fam)} for i, a in enumerate(fam)}
    return {"degree_spearman": deg, "reciprocity": {"observed": rec_obs, "observed_over_density2": rec_obs / dens ** 2,
                                                    "models": rec}, "mirror_bound": mirror, "family_spearman": corr}


def contact_condition(ctx, tgt, preds, contact, keys):
    """Amendment A4.3 (section 2.4): parameter-free contact analyses on the same animal's membrane contact."""
    m = ctx.pair_mask(tgt.present)
    y, c = ctx.flat(tgt.A)[m], ctx.flat(contact)[m]
    has = c > 0
    out = {"frac_pairs_with_contact": float(has.mean()), "frac_edges_on_contact": float(y[has].sum() / y.sum()),
           "log_contact_score": {"auroc": M.auroc(np.log1p(c), y), "auprc": M.auprc(np.log1p(c), y)}}
    for k in keys:
        s = preds[k][m] * has
        out[f"{k} x [contact>0]"] = {"auroc": M.auroc(s, y), "auprc": M.auprc(s, y),
                                     "without_gate": {"auroc": M.auroc(preds[k][m], y), "auprc": M.auprc(preds[k][m], y)}}
    return out


def judge_target(ctx, tgt, preds, base_key, memory_key, dl_bits, boot, joint=None):
    """Scores of every prediction on the evaluated pairs of `tgt`, and the pre-registered differences."""
    m = ctx.pair_mask(tgt.present)
    y = ctx.flat(tgt.A)[m]
    groups = ctx.I[m]
    base = preds[base_key][m]
    scores = {k: M.summary(p[m], y, base) | {"dl_bits": dl_bits.get(k)} for k, p in preds.items()}

    def d_ll(a, b):
        return M.boot_diff(M.wll, preds[a][m], preds[b][m], y, groups, n_boot=boot)

    def d_ap(a, b):
        return M.boot_diff(lambda s, yy, w: M.auprc(s, yy, w), preds[a][m], preds[b][m], y, groups, n_boot=boot)

    diffs = {}
    for rule in [k for k in preds if k.startswith("R1")] + ["B3", "K1"]:
        diffs[f"{rule}-vs-B1"] = d_ll(rule, "B1")
        diffs[f"{rule}-vs-{memory_key}"] = d_ll(rule, memory_key)
    ref = f"C({memory_key},ER)"
    for k in [k for k in preds if k.startswith("C(")]:
        diffs[f"{k}-vs-{memory_key}"] = d_ll(k, memory_key)
        if k != ref:
            diffs[f"{k}-vs-{ref}"] = d_ll(k, ref)
            diffs[f"{k}-vs-{ref}-auprc"] = d_ap(k, ref)
    return {"n_pairs": int(m.sum()), "n_pos": int(y.sum()), "scores": scores, "diffs": diffs,
            "secondary": secondary(ctx, tgt, preds, m, y, joint or {})}


def fit_combos(proxy_preds, names, memory_key):
    """Combination weights fitted on the pooled development proxies (A1.7). proxy_preds: list of dicts with the
    memory, the priors and y over evaluated pairs."""
    out = {}
    for q in names:
        out[q] = Mo.Combine(f"C({memory_key},{q})").fit([(d[memory_key], d[q], d["y"]) for d in proxy_preds])
    return out


def ambiguity(table):
    """Section 5.4: grid points whose training log-likelihood is within 1 % of the best; also (descriptive, added
    before the freeze because the 1 % band covered the whole grid in the dry run) within 1.92 nats, the
    likelihood-ratio 95 % band for one parameter."""
    t = np.array(table)
    best = t[:, 2].max()

    def band(ok):
        return {"n_points": int(len(ok)), "of": int(len(t)), "beta0": [float(ok[:, 0].min()), float(ok[:, 0].max())],
                "sminus": [float(ok[:, 1].min()), float(ok[:, 1].max())]}
    return band(t[t[:, 2] >= best - 0.01 * abs(best)]) | {"lr_1.92": band(t[t[:, 2] >= best - 1.92])}


def contacts_or_blocked(cells):
    if DRY:
        return None, "not run in the dry run (held-out covariate)"
    try:
        return C.brittin_contacts(cells), None
    except C.Blocked as e:
        return None, f"BLOCKED: {e}"


def adult(grid, boot):
    w7, w8 = C.witvliet(7), C.witvliet(8)
    cells = sorted(C.cells_of(w7) & C.cells_of(w8))
    ctx = Mo.make_ctx(cells)
    bank = K.FeatureBank(ctx)
    c7, c8 = C.conn(cells, k=7, min_syn=MIN_SYN), C.conn(cells, k=8, min_syn=MIN_SYN)
    g = np.linspace(0, 0.05, grid + 1)[:-1]

    def build(train, test_age, calib):
        tk = rs.hit_rate_types(sum(t.A for t in train) > 0, K_B3)
        P = {"B0": Mo.ER().fit(ctx, train).predict(ctx, test_age),
             "B1": Mo.Distance().fit(ctx, train).predict(ctx, test_age),
             "B2": Mo.Block(ctx.cook, "B2").fit(ctx, train).predict(ctx, test_age),
             "B3": Mo.Block(tk, "B3").fit(ctx, train).predict(ctx, test_age),
             "B4": Mo.Features(C_reg=C_B4).fit(ctx, train).predict(ctx, test_age),
             "K1": K.K1(K1_BLOCKS).fit(ctx, train, bank).predict(ctx, test_age),
             "M1": Mo.Copy(alpha=ALPHA_M1).fit(ctx, train).predict(ctx, test_age)}
        m3 = Mo.CountCopy().fit(ctx, train, calib)
        m4 = Mo.CountCopy(reverse=True).fit(ctx, train, calib)
        P["M3"], P["M4"] = m3.predict(ctx, test_age), m4.predict(ctx, test_age)
        r1c = Mo.RS(types=ctx.cook, beta0_grid=g, sminus_grid=g, iters=20, gamma=GAMMA).fit(ctx, train)
        r1i = Mo.RS(k_inferred=8, beta0_grid=g, sminus_grid=g, iters=20, gamma=GAMMA).fit(ctx, train)
        P["R1-cook"], P["R1-inferred8"] = r1c.predict(ctx, test_age), r1i.predict(ctx, test_age)
        dl = {"B0": 32.0, "B1": 4 * 32.0, "B2": 169 * 32.0, "B3": K_B3 ** 2 * 32.0 + len(cells) * np.log2(K_B3),
              "B4": 32.0 * Mo.Features(C_reg=C_B4).fit(ctx, train).n_params,
              "R1-cook": float(r1c.n_params * 32), "R1-inferred8": float(r1i.n_params * 32 + r1i.label_bits),
              "M1": Mo.Copy().fit(ctx, train).bits(ctx), "M3": m3.bits(ctx), "M4": m4.bits(ctx)}
        joint = {k: r.reciprocal(ctx, test_age) for k, r in (("R1-cook", r1c), ("R1-inferred8", r1i))}
        return P, dl, {"R1-cook": r1c, "R1-inferred8": r1i}, {k: v for k, v in joint.items() if v is not None}

    # development proxies for the combination weights, the S-e reference gain and the ambiguity ranges
    proxies, proxy_gain, amb = [], {}, {}
    for (tr, te), name in zip(((c7, c8), (c8, c7)), ("W7->W8", "W8->W7")):
        P, _, r1s, _ = build([tr], te.age_h, [(te.counts, tr)])
        m = ctx.pair_mask(te.present)
        d = {k: v[m] for k, v in P.items()}
        d["y"] = ctx.flat(te.A)[m]
        proxies.append(d)
        for k in ("R1-cook", "R1-inferred8", "M4", "B3"):
            proxy_gain.setdefault(k, {})[name] = M.summary(d[k], d["y"], d["B0"])["ll_gain_bits_per_pair"]
        amb[name] = {k: ambiguity(r.table) for k, r in r1s.items()}
    combos = fit_combos(proxies, ["R1-cook", "R1-inferred8", "B3", "B0", "K1"], "M4")

    tgt = C.conn(cells, k=8, min_syn=MIN_SYN) if DRY else \
        C.conn(cells, key="nema_white_n2u", age_h=54.0, name="N2U", min_syn=MIN_SYN)
    P, dl, r1s, joint = build([c7, c8], 50.0, [(c8.counts, c7), (c7.counts, c8)])
    for q, cmb in combos.items():
        P[f"C(M4,{q})" if q != "B0" else "C(M4,ER)"] = cmb.predict(P["M4"], P[q])
    out = judge_target(ctx, tgt, P, "B0", "M4", dl, boot, joint)
    out["fits"] = {k: {"beta0": float(r.beta0), "sminus": float(r.sminus), "gamma": r.gamma} for k, r in r1s.items()}
    out["proxy_gain"] = proxy_gain
    out["ambiguity_proxies"] = amb
    out["neurons_evaluated"] = int(tgt.present.sum())
    contact, why = contacts_or_blocked(cells)
    out["contact_condition"] = contact_condition(ctx, tgt, P, contact["N2U"], ["R1-cook", "B2", "B3", "M4"]) | \
        {"file": contact["files"]["N2U"]} if contact else why
    return out


def development(grid, boot):
    cells, excluded = dev_cells()
    ctx = Mo.make_ctx(cells)
    bank = K.FeatureBank(ctx)
    conns = {k: C.conn(cells, k=k, min_syn=MIN_SYN) for k in DEV}
    g = np.linspace(0, 0.05, grid + 1)[:-1]
    r1 = Mo.RSDev(ctx.cook, g, g, iters=20, gamma=GAMMA).fit(ctx, [[conns[3]], [conns[6]], [conns[7], conns[8]]])

    def build(train, age):
        tk = rs.hit_rate_types(sum(t.A for t in train) > 0, K_B3)
        P = {"B0": Mo.ER().fit(ctx, train).predict(ctx, age),
             "B1": Mo.Distance().fit(ctx, train).predict(ctx, age),
             "B2": Mo.Block(ctx.cook, "B2").fit(ctx, train).predict(ctx, age),
             "B3": Mo.Block(tk, "B3").fit(ctx, train).predict(ctx, age),
             "B4": Mo.Features(C_reg=C_B4).fit(ctx, train).predict(ctx, age),
             "K1": K.K1(K1_BLOCKS + ["age"]).fit(ctx, train, bank).predict(ctx, age),
             "M1": Mo.Copy(alpha=ALPHA_M1).fit(ctx, train).predict(ctx, age),
             "M2": Mo.Copy(alpha=ALPHA_M2, interpolate=True).fit(ctx, train).predict(ctx, age),
             "R1-dev": r1.predict(ctx, age)}
        n_ages = len({t.age_h for t in train})
        dl = {"B0": 32.0 * len(train), "R1-dev": float(r1.n_params * 32), "B2": 169 * 32.0 * n_ages,
              "B3": K_B3 ** 2 * 32.0 * n_ages + len(cells) * np.log2(K_B3)}
        return P, dl

    proxies = []
    for target in (5, 1):
        tgt = conns[target]
        train = [conns[k] for k in DEV if k != target]
        P, _ = build(train, tgt.age_h)
        m = ctx.pair_mask(tgt.present)
        d = {k: v[m] for k, v in P.items()}
        d["y"] = ctx.flat(tgt.A)[m]
        proxies.append(d)
    combos = fit_combos(proxies, ["R1-dev", "B3", "B0", "K1"], "M2")

    train = [conns[k] for k in DEV]
    results = {"excluded_dev": excluded}
    bt = dict(zip(cells, ctx.birth))
    targets = (("W2", {"k": 2}, 5.0), ("W4", {"k": 4}, 16.0),
               ("JSH", {"key": "nema_white_jsh", "age_h": 40.0, "name": "JSH"}, 40.0))
    if DRY:                                    # code-path check on development data only (no held-out file)
        targets = (("dry-W5", {"k": 5}, 23.0), ("dry-W6", {"k": 6}, 27.0))
    contact, why = contacts_or_blocked(cells)
    for name, kwargs, age in targets:
        tgt = C.conn(cells, min_syn=MIN_SYN, **kwargs)
        t = rs.minutes(age)
        contra = [c for c, p in zip(cells, tgt.present) if (bt[c] < t) != bool(p)]
        keep = np.array([c not in contra for c in cells])
        tgt = Mo.Conn(tgt.name, age, tgt.counts, tgt.present & keep, MIN_SYN)
        P, dl = build(train, age)
        for q, cmb in combos.items():
            P[f"C(M2,{q})" if q != "B0" else "C(M2,ER)"] = cmb.predict(P["M2"], P[q])
        # stored memory bits: the two neighbouring development data sets used by M2
        w = Mo.age_weights([x.age_h for x in train], age)
        used = [x for wi, x in zip(w, train) if wi > 0]
        dl["M2"] = Mo.Copy().fit(ctx, used).bits(ctx)
        joint = {}
        if GAMMA != 1.0:
            S = rs.Setup(ctx.pos, ctx.birth, r1.types, rs.minutes(age))
            mm = int(np.searchsorted(r1.bounds, rs.minutes(age), side="right"))
            sp = np.vstack([f[S.tp] for f in r1.splus[:mm + 1]])
            joint["R1-dev"] = S.final_states(sp, r1.beta0, r1.sminus, GAMMA, r1.bounds[:mm] if mm else None)[3]
        out = judge_target(ctx, tgt, P, "B0", "M2", dl, boot, joint)
        out["contradictory_neurons_excluded"] = contra
        out["neurons_evaluated"] = int(tgt.present.sum())
        if name == "JSH":
            out["contact_condition"] = contact_condition(ctx, tgt, P, contact["JSH"], ["R1-dev", "B2", "B3", "M2"]) | \
                {"file": contact["files"]["JSH"]} if contact else why
        results[name] = out
    results["R1_fit"] = {"beta0": float(r1.beta0), "sminus": float(r1.sminus), "gamma": GAMMA}
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--grid", type=int, default=10)
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--min-synapses", type=int, default=1, choices=(1, 3))
    ap.add_argument("--dry-run", action="store_true", help="development targets instead of held-out ones")
    a = ap.parse_args()
    global DRY, MIN_SYN
    DRY, MIN_SYN = a.dry_run, a.min_synapses
    name = ("structure_dryrun" if DRY else "structure") + ("_min3" if MIN_SYN == 3 else "")
    run = ledger.Run("g4" if DRY else "g5", name, grid=a.grid, boot=a.boot, min_synapses=MIN_SYN, selection=SEL)
    res = {"N2U": adult(a.grid, a.boot)}
    res.update(development(a.grid, a.boot))
    print(run.write(res))


if __name__ == "__main__":
    main()
