"""Fly T4 test (PRE_REGISTRATION.md section 4). Structure: synapse counts, signs and hexagonal offsets of the T4
inputs in the flyvis FIB-25/FIB-19 consensus connectome. Drive: Groschner et al. 2022 mean input-neuron voltage
responses to ON / OFF edges at 30 deg/s (development data). No parameter is fitted on T4 recordings.

Geometry (fixed before any T4 recording was read; G3_BASELINE_REPRODUCTION.md section 4): offsets are mapped to the
visual plane with flyvis's default hex_to_pixel (x = 1.5 v, y = -sqrt(3) (u + v / 2); neighbour spacing sqrt(3)).
For each subtype the motion axis is the unit vector from Mi9's synapse-weighted mean offset to the mean of Mi4's and
C3's; in the preferred direction the edge crosses Mi9's position first (Groschner's convention and the literature
mechanism; flyvis's preferred-direction labels are collinear with this axis but of opposite sign under the default
mapping). An input at axis position p (columns, positive towards Mi4 / C3) is delayed by p * 160 ms in PD and by
-p * 160 ms in ND (4.8 deg inter-ommatidial angle, Groschner's value).
"""

from __future__ import annotations

import itertools
import json
import math

import numpy as np

from .raw import path

INPUTS = ("Mi1", "Tm3", "Mi4", "Mi9", "C3")
MS_PER_COLUMN = 4.8 * 1000 / 30.0
FS = 1000


def connectome():
    return json.loads(path("flyvis_connectome").read_text())


def subtype_inputs(conn, subtype):
    """{input: (synapses, sign, (x, y) mean offset in column units)} for the five recorded input types."""
    out = {}
    for e in conn["edges"]:
        if e["tar"] == subtype and e["src"] in INPUTS:
            tot = sum(n for _, n in e["offsets"])
            u = sum(o[0] * n for o, n in e["offsets"]) / tot
            v = sum(o[1] * n for o, n in e["offsets"]) / tot
            x, y = 1.5 * v, -math.sqrt(3) * (u + v / 2)
            out[e["src"]] = (float(tot), int(e["alpha"]), (x / math.sqrt(3), y / math.sqrt(3)))
    return out


def axis_positions(inp):
    """Projection (columns) of each input's mean offset on the Mi9 -> (Mi4 + C3) / 2 axis, centred on Mi1."""
    o = {k: np.array(v[2]) for k, v in inp.items()}
    ax = (o["Mi4"] + o["C3"]) / 2 - o["Mi9"]
    ax = ax / np.linalg.norm(ax)
    return {k: float(np.dot(o[k] - o["Mi1"], ax)) for k in inp}


def inputs_mean():
    """Mean normalised responses (min-max over the whole trace, as Groschner) per input type: (2 stimuli, 8000)."""
    out = {}
    for k in INPUTS:
        a = np.load(path(f"groschner_{k}"), allow_pickle=False)
        m = np.nanmean(a, axis=1)
        out[k] = np.stack([(s - s.min()) / (s.max() - s.min()) for s in m])
    return out


def shift(trace, ms):
    s = int(round(ms))
    out = np.roll(trace, s)
    if s > 0:
        out[:s] = trace[0]
    elif s < 0:
        out[s:] = trace[-1]
    return out


def model(inp, pos, resp, weights=None, signs=None):
    """Linear-rectified T4 drive for ON / OFF x PD / ND: sum_k sign_k * n_k * r_k(t - delay_k), minus its pre-stimulus
    baseline, rectified. Returns array (2 stimuli, 2 directions, 8000)."""
    T = next(iter(resp.values())).shape[1]
    out = np.zeros((2, 2, T))
    for s in range(2):
        for d, sgn in enumerate((+1, -1)):                      # PD, ND
            tot = np.zeros(T)
            for k in INPUTS:
                n = inp[k][0] if weights is None else weights[k]
                sg = inp[k][1] if signs is None else signs[k]
                tot += sg * n * shift(resp[k][s], sgn * pos[k] * MS_PER_COLUMN)
            base = tot[:500].mean()
            out[s, d] = np.maximum(tot - base, 0.0)
    return out


def dsi(resp_pd_nd):
    """(peak PD - peak ND) / (peak PD + peak ND) for one stimulus."""
    pd, nd = resp_pd_nd[0].max(), resp_pd_nd[1].max()
    return float((pd - nd) / (pd + nd)) if (pd + nd) > 0 else 0.0


def predictions(subtype, resp=None):
    conn = connectome()
    inp = subtype_inputs(conn, subtype)
    pos = axis_positions(inp)
    resp = inputs_mean() if resp is None else resp
    full = model(inp, pos, resp)
    out = {"positions": pos, "synapses": {k: inp[k][0] for k in INPUTS}, "signs": {k: inp[k][1] for k in INPUTS},
           "dsi_on": dsi(full[0]), "dsi_off": dsi(full[1])}
    out["mirrored_dsi_on"] = dsi(model(inp, {k: -v for k, v in pos.items()}, resp)[0])
    out["zero_offset_dsi_on"] = dsi(model(inp, {k: 0.0 for k in pos}, resp)[0])
    perm = []
    keys = list(INPUTS)
    for p in itertools.permutations(keys):
        perm.append(dsi(model(inp, {k: pos[q] for k, q in zip(keys, p)}, resp)[0]))
    out["shuffled_offsets_dsi_on"] = perm
    out["frac_shuffles_above"] = float(np.mean(np.array(perm) > out["dsi_on"]))
    sign_perm = []
    for p in set(itertools.permutations([inp[k][1] for k in keys])):
        sign_perm.append(dsi(model(inp, pos, resp, signs=dict(zip(keys, p)))[0]))
    out["shuffled_signs_dsi_on"] = sign_perm
    w = {k: inp[k][0] for k in INPUTS}
    w["Mi9"] = 0.0
    out["no_mi9_dsi_on"] = dsi(model(inp, pos, resp, weights=w)[0])
    return out


def observed_dsi(t4v):
    """Per-cell DSI from recordings of shape (cells, 2 stimuli, 2 directions, 8000): peak depolarisation over the
    first-500-ms baseline, PD vs ND, ON edges (judge only)."""
    out = []
    for c in t4v:
        on = c[0]
        base = np.nanmean(on[:, :500])
        pk = np.nanmax(on - base, axis=1)
        pk = np.maximum(pk, 0)
        out.append(float((pk[0] - pk[1]) / (pk[0] + pk[1])) if pk.sum() > 0 else 0.0)
    return np.array(out)
