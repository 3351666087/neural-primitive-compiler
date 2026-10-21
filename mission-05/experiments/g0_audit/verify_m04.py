"""Mission 05 G0: re-check Mission 04's reported results from the raw outputs (not from the Markdown summaries),
verify both freeze records against the files at HEAD, and test whether the twin confirmation can be reproduced
from the repository alone (vendored copy in mission-04/external/arc-prior-twins).

Prints only counts, ids, hashes and labels.

  python -I mission-05/experiments/g0_audit/verify_m04.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
M4 = REPO / "mission-04" / "experiments"
TWINS = REPO / "mission-04" / "external" / "arc-prior-twins"
REPORTED_MANIFEST = "75e761bcef4e0c8572dbfd227469fc541008b436cc5bd9f1b0060bad685d7b91"


def load(p):
    return json.loads(Path(p).read_text())


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def check(claims, key, got, want):
    claims[key] = {"reported": want, "recomputed": got, "match": got == want}


def main():
    t0 = time.perf_counter()
    c = {}
    # --- task 1 audit (counterexamples, corrected numbers, cross-check)
    ce = load(M4 / "a0_uniqueness/counterexamples.json")["C1_dominance_pruning"]
    check(c, "C1 answered / hidden ambiguity / verified / old answer wrong",
          [ce["old_answered"], ce["pruning_hid_ambiguity"], ce["verified"], ce["old_answer_wrong_among_those"]], [250, 10, 10, 4])
    fn = load(M4 / "a0_uniqueness/final_numbers.json")
    s = fn["summary"]
    check(c, "M-DISC-fixed training (DEV) correct/wrong", [s["training|M-DISC-fixed"]["correct"], s["training|M-DISC-fixed"]["wrong"]], [33, 2])
    check(c, "M-DISC-fixed evaluation (POST-HOC) correct/wrong", [s["evaluation|M-DISC-fixed"]["correct"], s["evaluation|M-DISC-fixed"]["wrong"]], [11, 1])
    agree = fn["cross_check"]["training"]["agree"] + fn["cross_check"]["evaluation"]["agree"]
    dis = fn["cross_check"]["training"]["disagree"] + fn["cross_check"]["evaluation"]["disagree"]
    real = [d for d in dis if d["enumeration"] in ("UNIQUE", "AMBIGUOUS") and d["enumeration"] != d["z3"]]
    check(c, "cross-check agree / real disagreements / budget-only", [agree, len(real), len(dis) - len(real)], [130, 0, 1])
    # --- ARC-AGI-2 confirmation
    cp = load(M4 / "c1_arc2/cp_scores.json")
    blocks_answers = sum(len(v) for k, v in cp["correct_tasks"].items() if not k.startswith("M-DISC")) + \
        sum(len(v) for k, v in cp["wrong_tasks"].items() if not k.startswith("M-DISC"))
    check(c, "ARC-AGI-2 block layer answers (all routes and policies)", blocks_answers, 0)
    check(c, "ARC-AGI-2 M-DISC-fixed correct / wrong",
          [len(cp["correct_tasks"]["M-DISC-fixed"]), len(cp["wrong_tasks"]["M-DISC-fixed"])], [1, 0])
    check(c, "ARC-AGI-2 CP verdicts", {k: v["verdict"] for k, v in cp["cp"].items()},
          {"CP1": "FALSIFIED", "CP2": "HOLDS", "CP3": "HOLDS", "CP4": "INCONCLUSIVE", "CP5": "HOLDS", "CP6": "INCONCLUSIVE",
           "CP7": "INCONCLUSIVE", "CP8": "INCONCLUSIVE", "CP9": "INCONCLUSIVE"})
    # --- P-R2 (DEV)
    r2 = load(M4 / "r2_priors/r2.json")["summary"]
    check(c, "P-R2 block C0 / C3 (S0, S2)", [r2["blocks"]["C0|S0"]["correct"], r2["blocks"]["C0|S2"]["correct"],
                                              r2["blocks"]["C3|S0"]["correct"], r2["blocks"]["C3|S2"]["correct"]], [10, 18, 14, 24])
    check(c, "P-R2 block wrong answers, all configurations", sum(v["wrong"] for v in r2["blocks"].values()), 0)
    # --- twin confirmation
    sc = load(M4 / "c2_twins/scores2.json")
    a = sc["table"]["a"]
    check(c, "twins (a): block S0 C0 kept/can, C4 kept/can",
          [a["blocks-S0-C0"]["kept"], a["blocks-S0-C0"]["canonical_solved"], a["blocks-S0-C4"]["kept"], a["blocks-S0-C4"]["canonical_solved"]],
          [0, 5, 3, 5])
    check(c, "twins decisions D1-D3 admitted", [sc["decisions"][k] for k in sorted(sc["decisions"]) if k.startswith("D")], [False, False, False])
    # --- freeze records still match the files
    fz = {}
    for name, path in (("ARC-AGI-2 freeze", M4 / "c1_arc2/confirm.py"), ("twin freeze", M4 / "c2_twins/confirm2.py")):
        m = module(name.replace(" ", "_").replace("-", "_"), path)
        fz[name] = load(m.FREEZE)["files"] == m.file_hashes()
    # --- twin portability: vendored copy, manifest, and a re-run of sampled pairs
    port = {"vendored_manifest_sha256": hashlib.sha256((TWINS / "MANIFEST.json").read_bytes()).hexdigest()}
    port["manifest_matches_reported"] = port["vendored_manifest_sha256"] == REPORTED_MANIFEST
    c2 = module("confirm2_g0", M4 / "c2_twins/confirm2.py")
    port["file_check"] = c2.verify_files(TWINS)
    run = load(M4 / "c2_twins/confirm2_twins.json")
    rng = random.Random(5)
    sample = []
    for k in ("a", "b", "c"):
        ps = [p for p in run["pairs"] if p["classes"] == [k]]
        sample += rng.sample(ps, 4)
    same, diff = 0, []
    for p in sample:
        for side in ("canonical", "twin"):
            key = f"{side}/{p[side]}"
            rec = c2.version_record(TWINS / side / p[side])
            if rec == run["records"][key]:
                same += 1
            else:
                diff.append(key)
    port["rerun_versions"] = {"n": 2 * len(sample), "identical": same, "different": diff}
    out = {"label": "Mission 05 G0: verification of Mission 04 from raw outputs", "claims": c,
           "all_claims_match": all(v["match"] for v in c.values()), "freeze_records_match": fz,
           "twin_portability": port, "time_s": round(time.perf_counter() - t0, 1)}
    (HERE / "verify_m04.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: v for k, v in out.items() if k != "claims"}, indent=1, default=str))
    print("mismatched claims:", [k for k, v in c.items() if not v["match"]])


if __name__ == "__main__":
    main()
