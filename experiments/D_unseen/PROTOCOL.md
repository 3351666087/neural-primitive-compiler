# Protocol for group D (unseen tasks)

Goal: reduce the risk that the synthesiser was tuned to the demo tasks.

1. **Freeze.** After groups A–C have run, and before any group-D task exists, `run_unseen.py freeze`
   hashes every file under `src/npc/` (sorted path + SHA-256 of content) into
   `freeze-manifest.json`. The tree hash is the SHA-256 of the concatenated per-file lines.
2. **Generate.** `run_unseen.py generate` refuses to run unless the current `src/npc/` matches the
   manifest. It derives the seed as `int(tree_hash[:16], 16)` and draws 20 specs from the fixed
   generator below. Any later change to the compiler changes the seed, and therefore the tasks,
   so the compiler cannot be tuned to tasks it has already seen without the tasks moving too.
   - inputs `a, b`; one output `y`; no assumption;
   - `phi = gen.random_formula(rng, ["a","b"], depth=d)` with `d = rng.choice([2, 2, 3])`;
   - guarantee `y <-> prev[L](phi)` with `L = rng.choice([1, 2])`;
   - specs are **not** filtered for triviality or realisability (the statistics are reported).
3. **Hand-written unseen task (D-hand).** Written only after the freeze, recorded below with its
   time. It is chosen to need state *and* gating, but its wording was decided after the code froze.
4. **LLM proposals.** Before running the automatic searchers on group D, the LLM (Claude, in this
   session, following `skills/neural-compiler/SKILL.md`) writes sketches for D-hand and for 5 of the
   random tasks into `experiments/llm_sketches/`. Their outcomes are recorded whatever they are.
5. **Run.** `run_unseen.py run` checks the manifest again, then runs: realisability decision +
   classical construction, CEGIS neuron search (n <= 3, 120 s), `compose_dag` (size <= 3, 60 s), and
   independent re-verification of every network produced. Raw output: `results.json`.

Known weakness: the manifest proves *which* code produced the results, but it cannot prove the
author did not try several code versions before freezing ("seed grinding"). We did not do this,
but nothing here can prove it; a third party should re-run the generator with a different seed.
