"""Gate 5 judge, fly T4 (PRE_REGISTRATION.md section 4 with amendment A1.6). Runs once after the freeze with
M08_JUDGE=1: downloads the held-out T4 recordings from Edmond (MD5 checked against the dataset listing; SHA-256
recorded), computes per-cell DSI on ON edges, and evaluates T-a to T-d against the structure-only predictions written
at Gate 3 (results/g3/t4_dev.json, frozen). Writes results/g5/t4.json.
  M08_JUDGE=1 python3 -I experiments/g5_t4.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from m08 import custody, ledger, t4  # noqa: E402
from m08.raw import EDMOND, EDMOND_ID, RAW  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
# Edmond listing (Dataverse API, 2026-10-25): file -> MD5
HELD = {"fig3_T4v.npy": "1da37faf7e5117aaeb0ebb1d93413f0e", "fig4_T4_vm_gfp.npy": "9a451db84a57d877c3b2092f41cf0c3f",
        "fig4_T4_vm_gluclarnai.npy": "e5804d63b1eea1cde3a485350ab3c29b"}


def fetch_heldout():
    custody.allow("groschner_t4")
    d = RAW / "groschner_2022_edmond"
    out = {}
    for name, md5 in HELD.items():
        p = d / name
        if not p.exists():
            urllib.request.urlretrieve(EDMOND + str(EDMOND_ID[name]), p)
        b = p.read_bytes()
        if hashlib.md5(b).hexdigest() != md5:
            raise ValueError(f"{name}: MD5 mismatch")
        out[name] = {"md5": md5, "sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b)}
    return out


def main():
    run = ledger.Run("g5", "t4")
    pred = json.loads((ROOT / "results" / "g3" / "t4_dev.json").read_text())["results"]["predictions"]
    files = fetch_heldout()
    d = RAW / "groschner_2022_edmond"
    obs3 = t4.observed_dsi(np.load(d / "fig3_T4v.npy", allow_pickle=False))
    gfp = np.load(d / "fig4_T4_vm_gfp.npy", allow_pickle=False)
    rnai = np.load(d / "fig4_T4_vm_gluclarnai.npy", allow_pickle=False)
    keep = ~np.all(np.isnan(gfp.reshape(len(gfp), -1)), axis=1)
    obs_gfp, obs_rnai = t4.observed_dsi(gfp[keep]), t4.observed_dsi(rnai)
    subs = ["T4a", "T4b", "T4c", "T4d"]
    pd = np.array([pred[s]["dsi_on"] for s in subs])
    q1, q3 = np.percentile(obs3, [25, 75])
    res = {"files": files, "observed": {"fig3_dsi_on": obs3.tolist(), "median": float(np.median(obs3)),
                                        "iqr": [float(q1), float(q3)],
                                        "gfp_median": float(np.median(obs_gfp)), "rnai_median": float(np.median(obs_rnai)),
                                        "n_gfp": int(keep.sum()), "n_rnai": int(len(rnai))},
           "predicted": {s: pred[s]["dsi_on"] for s in subs}}
    res["T-a"] = bool(all(pred[s]["dsi_on"] > 0 and pred[s]["mirrored_dsi_on"] < 0 for s in subs))
    res["T-b"] = bool(q1 <= pd.mean() <= q3)
    res["T-c"] = bool(all(pred[s]["frac_shuffles_above"] < 0.05 for s in subs))
    res["T-d"] = bool(all(pred[s]["no_mi9_dsi_on"] < pred[s]["dsi_on"] for s in subs)
                      and np.median(obs_rnai) < np.median(obs_gfp))
    res["observed_sign_fraction_positive"] = float(np.mean(obs3 > 0))
    print(run.write(res))


if __name__ == "__main__":
    main()
