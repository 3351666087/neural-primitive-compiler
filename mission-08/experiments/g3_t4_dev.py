"""Gate 3, fly T4: structure-only predictions from the flyvis connectome and the Groschner input recordings (no T4
recording is read). Checks that the structural Mi9 -> Mi4 / C3 axis is collinear with flyvis's literature preferred
directions, and writes the predictions that the Gate 5 judge compares with the held-out T4 recordings.
  python3 -I experiments/g3_t4_dev.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from m08 import ledger, t4  # noqa: E402

FLYVIS_PD = {"T4a": 180, "T4b": 0, "T4c": 90, "T4d": 270}     # flyvis groundtruth_utils.preferred_directions


def main():
    run = ledger.Run("g3", "t4_dev")
    conn = t4.connectome()
    resp = t4.inputs_mean()
    out = {"geometry": {}, "predictions": {}}
    for s, pd in FLYVIS_PD.items():
        inp = t4.subtype_inputs(conn, s)
        o = {k: np.array(v[2]) for k, v in inp.items()}
        ax = (o["Mi4"] + o["C3"]) / 2 - o["Mi9"]
        ang = math.degrees(math.atan2(ax[1], ax[0])) % 360
        dev = min(abs(ang - (pd + 180) % 360), 360 - abs(ang - (pd + 180) % 360))
        out["geometry"][s] = {"mi9_to_mi4c3_angle_deg": ang, "flyvis_pd_deg": pd, "deviation_from_antiparallel_deg": dev}
        p = t4.predictions(s, resp)
        p["shuffled_offsets_dsi_on"] = [float(x) for x in p["shuffled_offsets_dsi_on"]]
        p["shuffled_signs_dsi_on"] = [float(x) for x in p["shuffled_signs_dsi_on"]]
        out["predictions"][s] = p
    print(run.write(out))


if __name__ == "__main__":
    main()
