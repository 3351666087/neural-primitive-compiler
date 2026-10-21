# Brief for the held-out mechanism author (Mission 07)

You are writing hidden mechanisms for a small simulated world. A research team will later test whether artificial
agents can discover them. You work independently: the team must not learn anything about your mechanisms before
their methods are frozen, and you must not learn anything about their methods.

## What you may read

Only these three files in the repository at `/Users/null3351/Code/neural-primitive-research/neural-primitive-compiler`:
- `mission-07/experiments/eco/DSL.md` (the mechanism language),
- `mission-07/experiments/eco/eco_env.py` (the interpreter),
- `mission-07/experiments/eco/validate_family.py` (the validator).

Do not read any other file of the repository, its git history, or any file in `/Users/null3351/Code/neural-primitive-research/neural-primitive-compiler/mission-07/` other than these three. In particular, do not open any
`family_*.json`, protocol, hypothesis or agent file. Do not use the web.

## What to write

Write your files only in `/Users/null3351/Code/m07-custodian/` (create it). Never write inside the repository.

1. `family_beta.json`: one mechanism family in the DSL.
2. `demos_beta.json`: demonstrations for the validator (format in the validator's docstring).
3. Optionally `family_gamma.json` + `demos_gamma.json`: a second, different family under the same rules.

## Requirements for each family

- It must pass `validate_family.py` (run it yourself with `python3 -I`):
  - R1: interpretable;
  - R2: a random policy lives at least 300 steps on average;
  - R3: every stage event is triggered by a demo of at most 60 actions;
  - R4: stage-1 events at least 50 times under the random policy, stage-2 events at most 50 times;
  - R5: at least one kind with visibility "revealed", at least one latent variable, a phase or nonstationarity entry,
    and consumables for both food and water.
- Design **at least two hidden mechanisms in a dependency**: the events that would let someone learn the second
  mechanism happen only while a hidden condition of the first mechanism holds. Log the first mechanism's events as
  stage-1 events and the second's as stage-2 events (use `["log", name]`).
- Hidden variables must stay hidden: do not mirror a latent value into a visible feature.
- Make the mechanisms matter for the agent's needs (food or water), so that an agent has a reason to care.
- Beyond these rules, design freely. Prefer mechanisms you find genuinely different from the most obvious ones (for
  example, avoid making every mechanism a simple counter). Use any DSL construct.
- Give kinds neutral names (`k1`, `k2`, ...).

## What to report back

Report **only**:
- the SHA-256 of each file you wrote;
- the validator's printed output for each family (it shows only pass/fail and counts);
- the number of families written.

Do **not** describe the mechanisms, kinds, rules, demos or design ideas in your report or anywhere else. Keep the files
where they are; the team will read them only after freezing their methods and publishing the hashes you report.
