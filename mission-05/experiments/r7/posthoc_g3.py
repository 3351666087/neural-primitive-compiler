"""POST-HOC (amendment 7): A+ on the spent G3 held-out set. No verdict: the set was used once for G3; this only shows
how A+ behaves on it. Truth tables recomputed (N = 3..7); A+ tables; soundness and calibration; A's G3 figures
(heldout_run.json) for comparison.

  python -I posthoc_g3.py      # writes posthoc_g3.json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(EXP / "lib"))
sys.path.insert(0, str(EXP / "g3"))
sys.path.insert(0, str(HERE))
import a_dsl  # noqa: E402
import dsl  # noqa: E402
import truth  # noqa: E402
import zplus  # noqa: E402


def main():
    t0 = time.perf_counter()
    specs = json.loads((EXP.parent / "external" / "g3_heldout" / "achievers.json").read_text())["specs"]
    by_id = {s["id"]: s for s in specs}
    inst = [(k, a) for s in specs for k, a in dsl.instances(s)]
    tr, tcpu = truth.tables([(k, a, dsl.make_select(by_id[k.split("|")[0]])) for k, a in inst])
    AP = zplus.a_tables_plus(specs, inst, tr)
    snd = a_dsl.soundness(AP, tr, dict(inst))
    g3 = json.loads((EXP / "g3" / "heldout_run.json").read_text())
    out = {"label": "POST-HOC: A+ on the spent G3 held-out set (no verdict)", "truth_cpu_s": tcpu,
           "Aplus_soundness": snd, "A_G3_soundness": g3["A"]["soundness"],
           "newly_certified": sorted(k for k, p in AP["progress"].items() if p["ok"] and not g3["A"]["progress"][k]["ok"]),
           "lost": sorted(k for k, p in AP["progress"].items() if not p["ok"] and g3["A"]["progress"][k]["ok"]),
           "time_s": round(time.perf_counter() - t0, 1)}
    (HERE / "posthoc_g3.json").write_text(json.dumps(out, indent=1, default=str))
    print("A+ certified", snd["certified_among_truth_good"], "/", snd["truth_good_instances"], "| below truth",
          len(snd["damage_below_truth"]), "false progress", len(snd["progress_certified_but_false"]),
          "| newly", len(out["newly_certified"]), "lost", len(out["lost"]))


if __name__ == "__main__":
    main()
