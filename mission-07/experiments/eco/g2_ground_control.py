"""Gate 2 positive / negative control of the grounding test (JUDGE SIDE script; development family alpha only).
Oracle structures are hand-written with alpha's true parameters (designer knowledge, used ONLY to validate the judge):
their predicates must ground to the true hidden classes. A mis-parameterised counter must not ground to them.
  python3 -I g2_ground_control.py      # writes g2_ground_control.json"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ground_eco as G  # noqa: E402
from eco_env import load_family  # noqa: E402

FAM = load_family(HERE / "family_alpha.json")
kid = {k: i + 1 for i, k in enumerate(FAM["kinds"])}
ORACLE = [
    {"struct_id": 0, "form": "M1", "stats": {}, "params": {"K": kid["stone"], "E": "poke", "theta": 3, "D": 25, "reset": True,
                                                         "ctx": kid["tree"], "dctx": 2, "ftype": "appear", "K2": kid["fruit"]}},
    {"struct_id": 1, "form": "M2", "stats": {}, "params": {"K": kid["lamp"], "E": "poke", "Kq": kid["stone"], "dq": 1,
                                                         "q_pred": f"cnt[{kid['stone']}]>=2", "q_struct": 0, "q_v": 2, "T": 150,
                                                         "ftype": "appear", "K2": kid["spring"]}},
]
FAKE = [{"struct_id": 7, "form": "M1", "stats": {}, "params": {"K": kid["tree"], "E": "poke", "theta": 2, "D": 10, "reset": False,
                                                             "ctx": None, "dctx": 0, "ftype": "appear", "K2": kid["fruit"]}}]


def main():
    probes, classes = G.make_probes(FAM)
    pos = {c: sum(pr["truth"][i] for pr in probes) for i, c in enumerate(map(tuple, [(c[0], c[1], c[2]) for c in classes]))}
    res = {"probes": len(probes), "class_positives": {f"{c[0]}:{c[1]}:{c[2]}": n for c, n in pos.items()},
           "oracle": G.ground(ORACLE, probes, classes), "fake": G.ground(FAKE, probes, classes)}
    (HERE / "g2_ground_control.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "class_positives"}, indent=1))
    print("positives per class:", res["class_positives"])


if __name__ == "__main__":
    main()
