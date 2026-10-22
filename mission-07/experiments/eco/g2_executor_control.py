"""Gate 2 positive control of the shared executor (JUDGE SIDE; development family alpha, seeds 100-104).
A structure-free fixed-catalogue agent (B1, learning off) receives alpha's true structures by transplant (designer
knowledge, used only for this control) and external goals every 600 steps, alternating cnt[stone]>=2 and bit[lamp].
The judge checks whether the hidden class condition holds while each external goal is pursued.
  python3 -I g2_executor_control.py      # writes g2_executor_control.json"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_eco as R  # noqa: E402
import score_eco as S  # noqa: E402
from g2_ground_control import ORACLE  # noqa: E402

OUT = HERE / "run" / "g2_executor"


def main():
    res = []
    for seed in range(100, 105):
        gifts = [[t, ["cnt[2]>=2"] if (t // 600) % 2 == 0 else ["bit[4]"]] for t in range(600, 12000, 600)]
        R.run("B1", str(HERE / "family_alpha.json"), seed, 12000, OUT, opts={"learn_off": True, "transplant": ORACLE, "gift": gifts})
        j, a = S.load(OUT, f"B1_alpha_{seed}")
        last = {}
        for rec in a["actions"]:
            if rec.get("goal_id") is not None:
                last[rec["goal_id"]] = rec["t"]
        cls = {S.class_key(c): i for i, c in enumerate(j["classes"])}
        target = {"cnt[2]>=2": cls["LATENT:stone.charge:(2, 3)"], "bit[4]": cls["LATENT:lamp.armed:(1,)"]}
        out = {"seed": seed}
        for p, ci in target.items():
            gs = [g for g in a["goals"] if g["reason"] == "external" and g["formula"] == [p]]
            ok = 0
            for g in gs:
                t0, t1 = g["t_logged"], last.get(g["goal_id"], g["t_logged"]) + 1
                ok += any(s0 <= t1 and (s1 is None or s1 >= t0) for s0, s1 in j["intervals"][str(ci)])
            out[p] = f"{ok}/{len(gs)}"
        res.append(out)
        print(out, flush=True)
    (HERE / "g2_executor_control.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
