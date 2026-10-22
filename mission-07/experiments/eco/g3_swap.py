"""History-swap L1 test for Gate 3 arms (JUDGE SIDE; same procedure as Gate 2: seeds 100 and 101, checkpoint at
step 20,000, 2,000-step horizon, reseeded noise floor).
  python3 -I g3_swap.py REV ARM          # runs the two checkpointed full runs if missing, then the swap test"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_eco as R  # noqa: E402
import swap_eco as SW  # noqa: E402
from g3_dev import FAM, STEPS, out_dir  # noqa: E402


def main(rev, arm):
    d = out_dir(rev) / "swap"
    d.mkdir(parents=True, exist_ok=True)
    for seed in (100, 101):
        if not (d / f"{arm}_alpha_{seed}.ckpt_20000.pkl").exists():
            R.run(arm, str(FAM), seed, 22000, str(d), checkpoint=20000)
    res = SW.swap_test(arm, str(FAM), 100, 101, 20000, 2000, str(d))
    (d / f"swap_{arm}.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
