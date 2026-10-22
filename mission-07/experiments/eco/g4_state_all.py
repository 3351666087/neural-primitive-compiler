"""Run g4_state.state_test for one arm over a family's confirmation seeds (JUDGE SIDE).
  python3 -I g4_state_all.py FAMILY ARM        # writes run/g4_FAMILY/state_ARM.json"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import g4_state as GS  # noqa: E402
from g4_jobs import SEEDS, out_dir  # noqa: E402


def main(name, arm):
    res = {}
    for seed in SEEDS[name]:
        try:
            res[seed] = GS.state_test(arm, name, seed, str(out_dir(name)))
        except FileNotFoundError as e:
            res[seed] = {"missing": str(e)}
        print(seed, res[seed], flush=True)
    passes = sum(1 for v in res.values() if v.get("pass"))
    out = {"arm": arm, "family": name, "passes": passes, "runs": res}
    (out_dir(name) / f"state_{arm}.json").write_text(json.dumps(out, indent=1))
    print(arm, "state-intervention passes", passes)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
