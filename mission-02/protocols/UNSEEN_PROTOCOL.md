# Mission 02 unseen-task protocol (strict route A)

1. **Freeze.** `run_unseen.py freeze` hashes every file under `src/cog/` and `src/npc/` (primitives, IR,
   compiler, learner, automatic constructor, judges, task semantics and the unseen generator) into
   `experiments/unseen/freeze-manifest.json`, which is committed on its own ("M2 freeze ...").
2. **Generate.** `run_unseen.py generate` refuses to run if the tree hash changed. Seed =
   `int(tree_sha256[:16], 16)`; `cog.unseen.generate(seed)` draws 8 spatial tasks (opaque command names,
   two-move composite commands, base moves never used at design time, optional conditional command, sizes
   3/5/8), 4 binding tasks (sizes K, V and K+2, V+1) and 4 objects-on-grid tasks (a family never used at
   design time; sizes (2, 3) and (3, 5)). The interfaces and natural-language descriptions are written to
   `experiments/unseen/tasks.json` and committed.
3. **LLM route (A-LLM).** Claude reads only `tasks.json` (interfaces + descriptions; no reference code,
   no oracle calls) and writes one size-independent IR program per task into `experiments/unseen/llm_programs.json`.
   That file is committed **before** any judge or automatic constructor runs on the unseen tasks.
4. **Run.** `run_unseen.py run` checks the hash again, then for every task:
   - **A-auto**: `cog.auto.construct_auto` with oracle access at the two smallest sizes only; the larger
     size is built from the learned rules with no oracle call;
   - **A-LLM**: compile the committed program at every size;
   - **random structure baseline**: for each command, a random map from the IR vocabulary (100 samples);
   - **classical FSM**: one-hot (state, frame) neuron count from Mission 01's construction, computed analytically;
   - **judges**: differential testing at every size (400 traces), unbounded product search at the smallest
     size when the task has no queries and the search fits in 2M states.
   Strict route A: no weight is searched anywhere; what each route searched or probed is counted.

Known weaknesses: the generator, the vocabulary, the primitives and the LLM programs were written by the
same model; the hash proves which code produced the results, not that the author did not iterate before
freezing. Two-move composite commands are "new combinations" only relative to the design tasks.

## Amendment 1 (made after task generation, before any constructor or judge ran on unseen tasks)

While writing the A-LLM programs, Claude found that the frozen IR has no construct for indexed command
families (STOREk, PLACEk, outputs topk): a single program cannot serve sizes with different object counts.
The automatic route has such families (anti-unified rules in `cog.auto`), but they live outside the IR.
Change: `llm_programs.json` may give either one size-independent `program` (used for every size; all spatial
tasks) or `per_size` programs, one per listed size, each written from the natural-language description
(binding and objects-on-grid tasks). Only `run_unseen.py` (outside the frozen tree) was edited, to read that
format. The missing IR construct is recorded as a negative result (negative-results.md, N-IR-1).
