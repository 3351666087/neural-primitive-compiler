"""The AUD instance sets of G0.3 (217 achiever instances): LIB, G3-DEV, STRAT-DEV (round 8, stage 2), G3-HO, G4-HO.

load() -> {"sets": {name: [spec, ...]}, "inst": {name: [(key, atom), ...]}, "by_id": {spec id: spec}}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

M05 = Path(__file__).resolve().parents[3] / "mission-05"
EXP = M05 / "experiments"
sys.path.insert(0, str(EXP / "g3"))
sys.path.insert(0, str(EXP / "lib"))
import dsl  # noqa: E402

HELD_OUT = ("G3-HO", "G4-HO")


def load():
    sets = {"LIB": json.loads((EXP / "g3" / "specs_library.json").read_text())["specs"],
            "G3-DEV": json.loads((EXP / "g3" / "specs_dev.json").read_text())["specs"]}
    st1 = json.loads((EXP / "r8" / "strat_stage1.json").read_text())
    r8 = json.loads((EXP / "r8" / "r8.json").read_text())
    ids = set(r8["strat_specs"])
    chosen = set(st1["passed"]) | set(st1["failed_sample"])
    sets["STRAT-DEV"] = [s for s in st1["pool"] if s["id"] in ids]
    sets["G3-HO"] = json.loads((M05 / "external" / "g3_heldout" / "achievers.json").read_text())["specs"]
    sets["G4-HO"] = json.loads((M05 / "external" / "g4_heldout" / "achievers.json").read_text())["specs"]
    inst = {}
    by_id = {}
    for name, ss in sets.items():
        bad = [s.get("id") for s in ss if dsl.validate(s)]
        if bad:
            raise ValueError(f"{name}: invalid specs {bad}")
        for s in ss:
            if s["id"] in by_id and by_id[s["id"]] != s:
                raise ValueError(f"spec id {s['id']} differs between sets")
            by_id[s["id"]] = s
        inst[name] = [(k, a) for s in ss for k, a in dsl.instances(s) if name != "STRAT-DEV" or k in chosen]
    return {"sets": sets, "inst": inst, "by_id": by_id}


if __name__ == "__main__":
    d = load()
    print({n: (len(d["sets"][n]), len(v)) for n, v in d["inst"].items()}, sum(len(v) for v in d["inst"].values()))
