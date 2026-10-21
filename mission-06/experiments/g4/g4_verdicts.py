"""The locked Gate 4 predictions (EXPERIMENT_PRE_REGISTRATION.md section G4.4), evaluated on the held-out runs.
Called by `g4_score.py --heldout`. Writes g4_heldout_verdicts.json."""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main(score):
    C, Jc, Cc = score("heldout_clean")
    P, Jp, Cp = score("heldout_pert")
    A, B = C["arms"], P["arms"]
    pc, pp = C["paired"], P["paired"]
    v = {}
    d = pc["G3-L vs G2A-1"]
    v["G4-a  H-DISC: G3-L - G2A-1 >= 0.10 and the 95% CI excludes 0 (clean)"] = (
        d["success_diff"] >= 0.10 and d["success_diff_ci95"][0] > 0, d["success_diff"], d["success_diff_ci95"])
    d = pc["G3-LP vs G3-L"]
    v["G4-b  H-DISC prior: steps G3-LP / G3-L <= 0.85 and success not lower by > 0.03 (clean)"] = (
        d["steps_ratio"] <= 0.85 and d["success_diff"] >= -0.03, d["steps_ratio"], d["success_diff"])
    x = A["G3-L"]
    v["G4-c  L_co holds in unseen rooms: 0 contradictions in lost games, >= 10 co-location hits (G3-L clean)"] = (
        x["L_co_contradictions_in_lost_games"] == 0 and x["colocated_hits"] >= 10,
        x["L_co_contradictions_in_lost_games"], x["colocated_hits"])
    d = pc["G3-LPR vs B1-LPR"]
    v["G4-d  H0-CLASSIC (clean): |G3-LPR - B1-LPR| <= 0.03"] = (abs(d["success_diff"]) <= 0.03, d["success_diff"], d["success_diff_ci95"])
    v["G4-e  level: G3-LPR success >= 0.75 (clean)"] = (A["G3-LPR"]["success"] >= 0.75, A["G3-LPR"]["success"], A["G3-LPR"]["wilson95"])
    sil = {k: B[k]["silent_failures"] for k in B}
    n = B["B1"]["games"]
    v["G4-f  monitors: B1 silent failures >= 0.25 n; every monitored arm <= 2 (perturbed)"] = (
        sil["B1"] >= 0.25 * n and all(sil[k] <= 2 for k in ("G2A-1", "G3-L", "G3-S", "G3-LP", "G3-LPR")), sil)
    d = pp["G3-LPR vs G3-LP"]
    v["G4-g  recovery: G3-LPR - G3-LP >= 0.30 and the CI excludes 0 (perturbed)"] = (
        d["success_diff"] >= 0.30 and d["success_diff_ci95"][0] > 0, d["success_diff"], d["success_diff_ci95"])
    d = pp["G3-LPR vs B1-LPR"]
    v["G4-h  H0-CLASSIC (perturbed): G3-LPR <= B1-LPR + 0.03 and B1-LPR silent failures <= 2"] = (
        d["success_diff"] <= 0.03 and sil["B1-LPR"] <= 2, d["success_diff"], d["success_diff_ci95"], sil["B1-LPR"])
    out = {"clean": C, "pert": P}
    for cond, run, J, Cn in (("clean", C, Jc, Cc), ("pert", P, Jp, Cp)):
        f = HERE / f"g4_b2_{cond}.json"
        if not f.exists():
            continue
        b2 = json.loads(f.read_text())
        idx = [int(i) for i in b2["won_by_idx"]]
        same = {arm: sum(J[(arm, i)]["won"] for i in idx) / len(idx) for arm in run["arms"]}
        steps = {arm: sum(Cn[(arm, i)]["steps"] for i in idx) / len(idx) for arm in run["arms"]}
        b2["same_games_success"], b2["same_games_mean_steps"] = same, steps
        out[f"B2_{cond}"] = b2
        if cond == "clean":
            v["G4-i  B2 (clean, 60-game subset): success >= G3-LPR and mean steps <= 0.6 x G3-LPR on the same games"] = (
                b2["success"] >= same["G3-LPR"] and b2["mean_steps"] <= 0.6 * steps["G3-LPR"],
                b2["success"], same["G3-LPR"], b2["mean_steps"], steps["G3-LPR"])
        else:
            v["G4-j  B2 (perturbed, 24-game subset): success >= 0.80 and <= 2 claims-done-but-lost"] = (
                b2["success"] >= 0.80 and b2["claims_done_but_lost"] <= 2, b2["success"], b2["claims_done_but_lost"])
    f = HERE / "aw_profile_test_normal_test_challenge.json"
    if f.exists():
        aw = json.loads(f.read_text())
        r = {s: aw[s]["answer_required"] for s in aw}
        v["G4-k  AppWorld held-out: information-goal share in [0.15, 0.45] in test_normal and test_challenge"] = (
            all(0.15 <= x <= 0.45 for x in r.values()), r)
        out["appworld_profile"] = aw
    out["verdicts"] = {k: {"verdict": "HOLDS" if t[0] else "FALSIFIED", "values": t[1:]} for k, t in v.items()}
    (HERE / "g4_heldout_verdicts.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(out["verdicts"], indent=1, default=str))
