"""POST-HOC diagnostic for G4b-f (registered before it ran; not part of any locked prediction). JUDGE SIDE, booleans
only: for every F3L goal, is an instance of the object to look at (T2) already at the desk lamp's location at the start?
If so, "look at a T2 under the desklamp" can be read as examining it in place, without picking it up; the official
ALFWorld goal (and this judge) require holding it.
  venv-alf/bin/python -I posthoc_f3l.py"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sets4b as S  # noqa: E402


def main():
    import textworld
    import textworld.gym
    from alfworld.agents.environment.alfred_tw_env import AlfredDemangler, AlfredInfos
    h = S.heldout()
    b2 = set(S.b2())
    rows = []
    for i, (g, fam, spec) in enumerate(h):
        if fam != "F3L":
            continue
        env = textworld.gym.make(textworld.gym.register_games([g], textworld.EnvInfos(facts=True), batch_size=1,
                                 asynchronous=False, max_episode_steps=5, wrappers=[AlfredDemangler, AlfredInfos]))
        _o, info = env.reset()
        F = [(x.name, [y.name for y in x.arguments]) for x in info["facts"][0]]
        env.close()
        otype = {a[0]: a[1].strip()[:-4] for n, a in F if n == "objecttype"}
        oloc = {a[0]: a[1] for n, a in F if n == "objectatlocation"}
        rloc = {a[0]: a[1] for n, a in F if n == "receptacleatlocation"}
        inrec = {a[0]: a[1] for n, a in F if n == "inreceptacle"}
        T2 = next(a[1] for a in spec["atoms"] if a[0] == "HOLDING")
        lamp_t = next(a[1] for a in spec["atoms"] if a[0] == "LIT")
        lamp_locs = {oloc.get(o) for o, t in otype.items() if t == lamp_t}
        at_lamp = any(t == T2 and (rloc.get(inrec.get(o)) in lamp_locs or oloc.get(o) in lamp_locs) for o, t in otype.items())
        rows.append({"goal": i, "in_b2_subset": i in b2, "T2_already_at_lamp": at_lamp})
    out = {"F3L_goals": len(rows), "T2_already_at_lamp": sum(r["T2_already_at_lamp"] for r in rows),
           "b2_subset": sum(r["in_b2_subset"] for r in rows),
           "b2_subset_T2_already_at_lamp": sum(r["T2_already_at_lamp"] for r in rows if r["in_b2_subset"]), "rows": rows}
    diag = []
    for k in (0, 1):
        for l in (HERE / "run" / f"b2_judge_log_diag{k}.jsonl").read_text().splitlines():
            e = json.loads(l)
            if e["event"] == "end":
                diag.append({"goal": e["idx"], "won": e["won"], "steps": e["steps"], "first_step_true": e["first_step_true"]})
    out["diagnostic_b2_rerun"] = diag
    (HERE / "posthoc_f3l.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=1))


if __name__ == "__main__":
    main()
