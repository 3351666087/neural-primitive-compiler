"""Score G4b (EXPERIMENT_PRE_REGISTRATION.md section G4b).
  python3 -I g4b_score.py dev          descriptive (development)
  python3 -I g4b_score.py heldout      the locked predictions G4b-a..h; B2 from run/b2_judge_log_*.jsonl when present
Writes g4b_scores_<set>.json."""

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "g4"))
import stats as S  # noqa: E402

ARMS = ("CMP-0", "CMP-1", "SEQ")
FAMS = ("F2", "F3", "F3L", "F4")


def b2_results():
    rep = HERE / "run" / "b2_reported.json"
    if not rep.exists():
        return None
    reported = {int(k): v for k, v in json.loads(rep.read_text()).items()}
    games, batches = {}, {}
    for k in sorted(reported):
        ev = [json.loads(l) for l in (HERE / "run" / f"b2_judge_log_{k}.jsonl").read_text().splitlines()]
        acts = sum(1 for e in ev if e["event"] == "act")
        resets = sum(1 for e in ev if e["event"] == "reset")
        dones = sum(1 for e in ev if e["event"] == "end" and e["reason"] == "agent done")
        batches[k] = {"acts": acts, **reported[k], "extra_tool_calls": reported[k]["tool_uses"] - (acts + resets + dones + 1)}
        for e in ev:
            if e["event"] == "end":
                games[e["idx"]] = e
    return {"games": games, "batches": batches, "tokens_total": sum(v["tokens"] for v in reported.values())}


def main():
    which = sys.argv[1]
    J = {(r["variant"], r["game"]): r for r in map(json.loads, (HERE / f"g4b_{which}_judge.jsonl").read_text().splitlines())}
    Cn = {(r["variant"], r["game"]): r for r in map(json.loads, (HERE / f"g4b_{which}_constructor.jsonl").read_text().splitlines())}
    n = 1 + max(k[1] for k in Cn)
    fam = {i: J[("CMP-1", i)]["family"] for i in range(n)}
    out = {"set": which, "goals": n, "arms": {}, "paired": {}}
    for v in ARMS:
        won = [int(J[(v, i)]["won"]) for i in range(n)]
        oc = Counter("won" if J[(v, i)]["won"] else Cn[(v, i)]["outcome"].split(" did not")[0][:50] for i in range(n))
        out["arms"][v] = {
            "won": sum(won), "success": sum(won) / n, "wilson95": S.wilson(sum(won), n),
            "by_family": {f: f"{sum(won[i] for i in range(n) if fam[i] == f)}/{sum(1 for i in range(n) if fam[i] == f)}" for f in FAMS},
            "silent_failures": sum(1 for i in range(n) if not won[i] and Cn[(v, i)]["outcome"] == "claims done"),
            "take_abstentions": sum(1 for i in range(n) if "monitor: 'take'" in Cn[(v, i)]["outcome"]),
            "orig_won": sum(J[(v, i)]["orig_won"] for i in range(n)),
            "mean_steps": sum(Cn[(v, i)]["steps"] for i in range(n)) / n, "outcomes": dict(oc.most_common())}
    for a, b in (("CMP-1", "CMP-0"), ("CMP-1", "SEQ")):
        wa = [int(J[(a, i)]["won"]) for i in range(n)]
        wb = [int(J[(b, i)]["won"]) for i in range(n)]
        d, ci = S.paired_diff(wa, wb)
        p, n10, n01 = S.mcnemar_exact(wa, wb)
        out["paired"][f"{a} vs {b}"] = {"diff": d, "ci95": ci, "mcnemar_p": p, f"{a}_only": n10, f"{b}_only": n01}
    if which == "heldout":
        A = out["arms"]
        f4 = [i for i in range(n) if fam[i] == "F4"]
        f2 = [i for i in range(n) if fam[i] == "F2"]
        rate = lambda v, idx: sum(J[(v, i)]["won"] for i in idx) / len(idx)
        pc = out["paired"]
        v = {
            "G4b-a  frozen law at depth 4: CMP-0 F4 success <= 0.10 and >= 80% of its F4 goals end in a 'take' abstention":
                (rate("CMP-0", f4) <= 0.10 and sum("monitor: 'take'" in Cn[("CMP-0", i)]["outcome"] for i in f4) >= 0.8 * len(f4),
                 rate("CMP-0", f4)),
            "G4b-b  upgraded contracts: CMP-1 - CMP-0 >= 0.30, CI excludes 0":
                (pc["CMP-1 vs CMP-0"]["diff"] >= 0.30 and pc["CMP-1 vs CMP-0"]["ci95"][0] > 0, pc["CMP-1 vs CMP-0"]["diff"]),
            "G4b-c  H0-CLASSIC: |CMP-1 - SEQ| <= 0.03": (abs(pc["CMP-1 vs SEQ"]["diff"]) <= 0.03, pc["CMP-1 vs SEQ"]["diff"]),
            "G4b-d  level: CMP-1 success >= 0.75": (A["CMP-1"]["success"] >= 0.75, A["CMP-1"]["success"]),
            "G4b-e  no silent failures: each arm <= 1": (all(A[x]["silent_failures"] <= 1 for x in ARMS),
                                                          {x: A[x]["silent_failures"] for x in ARMS}),
            "G4b-g  depth 2 has no ordering problem: CMP-0 F2 >= CMP-1 F2 - 0.10": (rate("CMP-0", f2) >= rate("CMP-1", f2) - 0.10,
                                                                                    rate("CMP-0", f2), rate("CMP-1", f2)),
            "G4b-h  the game's own goal is not tripped: orig_won <= 2 per arm": (all(A[x]["orig_won"] <= 2 for x in ARMS),
                                                                                  {x: A[x]["orig_won"] for x in ARMS})}
        b2 = b2_results()
        if b2:
            idx = sorted(b2["games"])
            bw = sum(b2["games"][i]["won"] for i in idx) / len(idx)
            bs = sum(b2["games"][i]["steps"] for i in idx) / len(idx)
            cw = rate("CMP-1", idx)
            cs = sum(Cn[("CMP-1", i)]["steps"] for i in idx) / len(idx)
            out["B2"] = {"goals": len(idx), "success": bw, "mean_steps": bs, "CMP-1_same": cw, "CMP-1_steps_same": cs,
                         "SEQ_same": rate("SEQ", idx), "CMP-0_same": rate("CMP-0", idx),
                         "by_family": {f: f"{sum(b2['games'][i]['won'] for i in idx if fam[i] == f)}/{sum(1 for i in idx if fam[i] == f)}" for f in FAMS},
                         "claims_done_but_lost": sum(1 for i in idx if b2["games"][i]["reason"] == "agent done" and not b2["games"][i]["won"]),
                         "orig_won": sum(b2["games"][i]["orig_won"] for i in idx),
                         "tokens_total": b2["tokens_total"], "batches": b2["batches"]}
            v["G4b-f  B2: success >= CMP-1 on the same goals and mean steps <= 0.8 x CMP-1"] = (
                bw >= cw and bs <= 0.8 * cs, bw, cw, bs, cs)
        out["verdicts"] = {k: {"verdict": "HOLDS" if t[0] else "FALSIFIED", "values": t[1:]} for k, t in v.items()}
    (HERE / f"g4b_scores_{which}.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: out[k] for k in out if k not in ("arms",)} | {"arms": {x: {kk: out["arms"][x][kk] for kk in
          ("won", "by_family", "silent_failures", "take_abstentions", "orig_won", "mean_steps")} for x in ARMS}}, indent=1, default=str))


if __name__ == "__main__":
    main()
