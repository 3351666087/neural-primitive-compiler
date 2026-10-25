"""POST-HOC, after the Gate 5 T4 judge (not frozen, not part of the verdict): description of the T-d result. For
the GFP control and GluClalpha RNAi T4 cells (Groschner et al. 2022, Fig. 4 voltages, already downloaded by the
judge), the per-cell ON-edge peak depolarisation over the first-500-ms baseline in PD and ND, the baseline itself,
and the DSI, so that "RNAi DSI higher than control" can be traced to PD or ND. Writes results/g5/posthoc_t4.json.
  python3 -I experiments/g5_posthoc_t4.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from m08 import ledger  # noqa: E402
from m08.raw import RAW  # noqa: E402


def describe(a):
    keep = ~np.all(np.isnan(a.reshape(len(a), -1)), axis=1)
    a = a[keep]
    on = a[:, 0]                                      # (cells, PD / ND, time)
    base = np.nanmean(on[:, :, :500], axis=(1, 2))
    pk = np.maximum(np.nanmax(on - base[:, None, None], axis=2), 0)
    dsi = np.where(pk.sum(1) > 0, (pk[:, 0] - pk[:, 1]) / np.maximum(pk.sum(1), 1e-12), 0)
    q = lambda x: [float(v) for v in np.nanpercentile(x, [25, 50, 75])]      # noqa: E731
    return {"n": int(len(a)), "baseline_mV_q": q(base), "pd_peak_mV_q": q(pk[:, 0]), "nd_peak_mV_q": q(pk[:, 1]),
            "dsi_q": q(dsi), "trace_ms": int(a.shape[-1])}


def main():
    run = ledger.Run("g5", "posthoc_t4", note="post-hoc description, not part of the verdict")
    d = RAW / "groschner_2022_edmond"
    res = {"gfp": describe(np.load(d / "fig4_T4_vm_gfp.npy", allow_pickle=False)),
           "rnai": describe(np.load(d / "fig4_T4_vm_gluclarnai.npy", allow_pickle=False)),
           "fig3": describe(np.load(d / "fig3_T4v.npy", allow_pickle=False))}
    print(run.write(res))


if __name__ == "__main__":
    main()
