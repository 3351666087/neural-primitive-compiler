"""ALFWorld deployment pilot A2/A3 and P-ALF-1 (EXPERIMENT_PRE_REGISTRATION.md, section G1-A). No download, no held-out
data: only train/ is used (valid_unseen stays sealed in its archive).

Process layout: this orchestrating process is the constructor side (import guard installed first). The judge process
(spawned; runs alf_judge) holds the environment and the privileged fields. Only text observations and, for P-ALF-1,
query commands cross to the constructor; labels go back; scoring happens in the judge process.

  A2  10 train games (seed 60, stratified), reset + 5 random legal steps each, timings
  A3  the constructor received only text; won / admissible_commands / gamefile / score never crossed; alfworld and
      textworld imports refused on the constructor side by the guard; static scan clean
  P-ALF-1  60 train games (seed 61, 10 per task type), 20 random legal steps each; U_P, W_P, U_M, W_M, S0

  mission-06/env/venv-alf/bin/python -I mission-06/experiments/g1/alf_pilot.py   # writes alf_pilot.json
"""

from __future__ import annotations

import json
import multiprocessing as mp
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import belief as BL  # noqa: E402
import harness  # noqa: E402

DATA = str(HERE.parents[1] / "env" / "alfworld-data")
CONSTRUCTOR_FORBIDDEN = ("alfworld", "textworld", "alf_judge")


def judge_proc(conn):
    """JUDGE SIDE process: serves episodes as text only, keeps privileged records, scores labels."""
    import alf_judge as J
    records = {}
    while True:
        kind, payload = conn.recv()
        if kind == "smoke":
            games, counts = J.sample_games(DATA, "train", 2, 60)
            out = []
            for gf in games[:10]:
                t0 = time.perf_counter()
                g = J.Game(gf, max_steps=10)
                obs, info = g.reset()
                t1 = time.perf_counter()
                texts = [obs]
                for k in range(5):
                    cands = sorted(c for c in info["admissible_commands"] if not c.startswith(J.EXCLUDE))
                    cmd = cands[k % len(cands)]
                    obs, _s, _d, info = g.step(cmd)
                    texts.append(obs)
                g.close()
                out.append({"reset_s": round(t1 - t0, 3), "steps_s": round(time.perf_counter() - t1, 3),
                            "texts": texts})
            conn.send(("smoke", {"games": out, "train_counts_by_type": counts}))
        elif kind == "record":
            games, _counts = J.sample_games(DATA, "train", 10, 61)
            eps = []
            for i, gf in enumerate(games):
                rec = J.record_episode(gf, 20, 1000 + i)
                records[i] = rec
                queries = sorted({c for adm in rec["admissible"] for c in adm if c.startswith(J.SKILL_VERBS)})
                eps.append({"episode": i, "history": list(zip(rec["actions"], rec["obs"])), "queries": queries})
            conn.send(("episodes", eps))
        elif kind == "score":
            conn.send(("scores", score(records, payload)))
        elif kind == "close":
            conn.send(("closed", None))
            break


def score(records, labels):
    from collections import Counter
    tot, per_verb = Counter(), {}
    m_steps = m_unknown = m_wrong = m_checked = 0
    s0 = []
    for i, rec in records.items():
        lab = labels[str(i)]
        for t, adm in enumerate(rec["admissible"]):
            adm = set(adm)
            for cmd, y in lab["P"][t].items():
                verb = cmd.split(" ")[0]
                c = per_verb.setdefault(verb, Counter())
                truth = cmd in adm
                for ctr in (tot, c):
                    ctr["n"] += 1
                    if y == BL.UNKNOWN:
                        ctr["unknown"] += 1
                    elif (y == BL.APPLICABLE) != truth:
                        ctr["wrong"] += 1
            locs = lab["M"][t]
            m_steps += 1
            m_unknown += not locs
            for o, r in locs:                      # checkable when the agent stands at r with an empty hand
                if r != "<hand>" and lab["at"][t] == r and lab["hand_empty"][t] and lab["open_or_plain"][t]:
                    m_checked += 1
                    m_wrong += f"take {o} from {r}" not in adm
        s0.append(bool(lab["M"][0]))
    f = lambda c: {"n": c["n"], "U": c["unknown"] / c["n"] if c["n"] else None,
                   "W": c["wrong"] / max(1, c["n"] - c["unknown"])}
    return {"P": f(tot), "P_by_verb": {v: f(c) for v, c in sorted(per_verb.items())},
            "M": {"steps": m_steps, "U_M": m_unknown / m_steps, "W_M": (m_wrong / m_checked) if m_checked else None,
                  "W_M_checked": m_checked},
            "S0": sum(s0) / len(s0), "episodes": len(records)}


def label_episode(ep):
    """CONSTRUCTOR SIDE labelling: a pure function of the text history and each query command."""
    hist = [(a, o) for a, o in ep["history"]]
    out = {"P": [], "M": [], "at": [], "hand_empty": [], "open_or_plain": []}
    otype = None
    for t in range(len(hist)):
        b = BL.belief_after(hist[:t + 1])
        if t == 0:
            otype = BL.goal_object_type(b.goal)
        out["P"].append({q: BL.applicable(b, q) for q in ep["queries"]})
        out["M"].append(BL.known_locations(b, otype) if otype else [])
        out["at"].append(b.location)
        out["hand_empty"].append(b.holding is None)
        out["open_or_plain"].append(b.state.get(b.location) in ("open", "plain"))
    out["goal_type"] = otype
    return out


def main():
    t0 = time.perf_counter()
    guard = harness.guard_imports()
    for m in CONSTRUCTOR_FORBIDDEN:
        if m not in harness.FORBIDDEN_MODULES:
            harness.FORBIDDEN_MODULES = harness.FORBIDDEN_MODULES + (m,)
    ctx = mp.get_context("spawn")
    a, b = ctx.Pipe()
    p = ctx.Process(target=judge_proc, args=(b,))
    p.start()
    out = {"label": "G1-A2/A3 and P-ALF-1 (Mission 06)"}
    a.send(("smoke", None))
    _, smoke = a.recv()
    texts_ok = all(isinstance(x, str) for g in smoke["games"] for x in g["texts"])
    out["A2"] = {"games": len(smoke["games"]), "reset_s": [g["reset_s"] for g in smoke["games"]],
                 "five_steps_s": [g["steps_s"] for g in smoke["games"]], "train_counts_by_type": smoke["train_counts_by_type"],
                 "verdict": "HOLDS" if len(smoke["games"]) == 10 and texts_ok else "FALSIFIED"}
    a.send(("record", None))
    _, eps = a.recv()
    labels = {str(ep["episode"]): label_episode(ep) for ep in eps}
    a.send(("score", labels))
    _, sc = a.recv()
    a.send(("close", None))
    a.recv()
    p.join(timeout=60)
    refused = {}
    for m in ("alfworld", "textworld"):
        try:
            __import__(m)
        except ImportError:
            pass
        refused[m] = m in guard.attempts
    crossed = {type(x).__name__ for g in smoke["games"] for x in g["texts"]} | \
              {type(v).__name__ for ep in eps for _a, v in ep["history"]}
    import pilot
    scan = pilot.static_scan()
    out["A3"] = {"types_crossed": sorted(crossed), "imports_refused_by_guard": refused, "static_scan_violations": scan,
                 "verdict": "HOLDS" if crossed == {"str"} and all(refused.values()) and not scan and eps else
                 ("NOT_EVALUABLE" if not eps else "FALSIFIED")}
    out["P_ALF_1"] = sc
    pr = {"ALF1-a": sc["P"]["U"] <= 0.05, "ALF1-b": sc["P"]["W"] <= 0.02, "ALF1-c": sc["M"]["U_M"] >= 0.5,
          "ALF1-d": sc["S0"] <= 0.1, "ALF1-e": sc["M"]["W_M"] in (0, 0.0, None)}
    out["predictions"] = {k: "HOLDS" if v else "FALSIFIED" for k, v in pr.items()}
    out["goal_types_parsed"] = sum(1 for l in labels.values() if l["goal_type"]) / max(1, len(labels))
    out["time_s"] = round(time.perf_counter() - t0, 1)
    (HERE / "alf_pilot.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: out[k]["verdict"] for k in ("A2", "A3")}), json.dumps(out["predictions"]), out["time_s"], "s")


if __name__ == "__main__":
    main()
