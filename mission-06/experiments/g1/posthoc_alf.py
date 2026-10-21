"""POST-HOC diagnostic of P-ALF-1 (after the locked scoring; does not change any verdict). AUDIT: uses both sides in
one process. Re-records the same 60 train episodes (same seeds; the driver is deterministic) and reports:
  1  U_M restricted to episodes whose goal type was parsed (the locked U_M counts unparsed episodes as unknown)
  2  the goal sentences the parser missed (train split only)
  3  the P-layer errors grouped by verb and by (belief label, truth), with up to 3 examples each
  4  how many P-layer errors involve a receptacle co-located with the agent's current place (judge-derived: r' is
     co-located at step t iff the agent stands somewhere, r' is not the arrival receptacle, and "go to r'" is not legal)

  mission-06/env/venv-alf/bin/python -I mission-06/experiments/g1/posthoc_alf.py        # writes posthoc_alf.json
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import alf_judge as J  # noqa: E402
import alf_pilot as AP  # noqa: E402
import belief as BL  # noqa: E402


def main():
    games, _ = J.sample_games(AP.DATA, "train", 10, 61)
    m_steps = m_unknown = 0
    unparsed, errs, examples = [], Counter(), {}
    coloc = Counter()
    for i, gf in enumerate(games):
        rec = J.record_episode(gf, 20, 1000 + i)
        queries = sorted({c for adm in rec["admissible"] for c in adm if c.startswith(J.SKILL_VERBS)})
        ep = {"episode": i, "history": list(zip(rec["actions"], rec["obs"])), "queries": queries}
        lab = AP.label_episode(ep)
        if not lab["goal_type"]:
            b0 = BL.belief_after(ep["history"][:1])
            unparsed.append(b0.goal)
        else:
            m_steps += len(lab["M"])
            m_unknown += sum(1 for x in lab["M"] if not x)
        for t, adm in enumerate(rec["admissible"]):
            adm = set(adm)
            for cmd, y in lab["P"][t].items():
                truth = cmd in adm
                if y != BL.UNKNOWN and (y == BL.APPLICABLE) != truth:
                    here = lab["at"][t]
                    gotos = {c[6:] for c in adm if c.startswith("go to ")}
                    recs = [w for w in BL.belief_after(ep["history"][:1]).receptacles]
                    near = {r for r in recs if here is not None and r != here and r not in gotos}
                    involved = [r for r in near if cmd.endswith(" " + r) or f" from {r}" in cmd or f" to {r}" in cmd]
                    coloc["co-located receptacle involved" if involved else "other"] += 1
                    key = f"{cmd.split(' ')[0]}: belief {y}, truth {'A' if truth else 'N'}"
                    errs[key] += 1
                    ex = examples.setdefault(key, [])
                    if len(ex) < 3:
                        ex.append({"command": cmd, "last_action": rec["actions"][t], "obs": rec["obs"][t][:300]})
    out = {"label": "POST-HOC diagnostic of P-ALF-1", "U_M_parsed_only": m_unknown / m_steps if m_steps else None,
           "M_steps_parsed_only": m_steps, "unparsed_goals": unparsed, "P_errors": dict(errs.most_common()), "P_errors_by_colocation": dict(coloc),
           "P_error_examples": examples}
    (HERE / "posthoc_alf.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("U_M_parsed_only", "M_steps_parsed_only", "unparsed_goals", "P_errors", "P_errors_by_colocation")}, indent=1))


if __name__ == "__main__":
    main()
