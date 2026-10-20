---
name: cognitive-compiler
description: Build a verified spiking network for a small structured cognitive task (spatial working memory over a grid, object-value binding, objects on a grid) by composing the frozen Mission 02 primitives (CMR, SEL, ANY, GATE) in the cog IR. No weights are searched. The LLM proposes the composition; the judges (differential testing, product-state search, Z3 contracts) decide.
---

# Cognitive compiler skill (Mission 02)

You turn a capability description into an **IR program** (JSON) over typed index spaces. The program is
compiled into integer integrate-and-fire neurons by `cog.ir.compile_ir`, whose primitive templates are
frozen. You never choose weights, and you never claim correctness yourself.

## Rules
1. Expose every interpretation choice: axis orientation (y grows downward), clockwise/counter-clockwise,
   what "then" means (apply in order), border behaviour (clip vs wrap), tie and timing conventions.
2. Use only the IR vocabulary (`src/cog/ir.py` docstring). If a capability needs something outside it
   (complement, counting beyond OR, comparison of quantities, search/planning, choosing among many valid
   outputs), say so and stop. Do not smuggle the behaviour into a literal table unless you derived that
   table from an experiment you report.
3. Results come only from the judges: `cog.check.differential` (statistical, [E]),
   `cog.check.reach_equiv` (all trace lengths at one size, [M]), `cog.proofs` (any size, [M], for the
   primitive contracts and the conditional-command composition). Quote their outcome; never round
   "differential passed at N=8" up to "proved for N=8".

## Workflow
1. **Formalise.** Identify the state space (grid N, table K x V, objgrid K x N), the commands (letters),
   data bundles, query bundles and output lags from the interface. Restate each command as a forward point
   map ("each cell moves to ...").
2. **Choose primitives.**
   - State plus commands: one `CMR` over the state space; each command maps to a vocabulary map in
     **pullback** form. "A then B" is `["compose", A, B]`. Clipping shifts are not a group: do not cancel
     "right then left" (P5).
   - "Is anything in region R": `ANY` with `where` (`row`/`col` accept `"last"`, so the program does not
     depend on the size); delay = lag - 2.
   - "Look up by a query": `SEL` with `select` = the query bundle, `axis` = the coordinate(s) the query
     names, delay = lag - 1, xdelay = lag - 2.
   - Relations between two lookups ("same value"): two `SEL`s, an element-wise `GATE` (AND), then `ANY`. Add
     one step of lag per layer.
   - Data-dependent commands ("if the shape touches R, do A, else B; result after D steps"): internal
     letters `condA`/`condB` on the CMR with maps A/B; `ANY` over R (delay 1);
     `GATE condA = [COND, D] AND [anyR, 1]`, `GATE condB = [COND, D] AND NOT [anyR, 1]`. This is
     correct under the pacing assumption (no other command during D), proved for any space as P4.
3. **Indexed families.** The IR has no `for k` construct (N-IR-1). For object-count changes, write one
   program per size from the description.
4. **Compile and judge.** `compile_ir(prog, iface)`, then `differential` at every size of interest and
   `reach_equiv` at the smallest size if the state space is small (<= 9 cells, no free-form queries).
5. **Counterexamples.** A counterexample trace shows the output channel, the time and the inputs. Replay
   your forward-map reading on that trace by hand, then check orientation, composition order, lag
   arithmetic and the pacing assumption, in that order.
6. **Report.** The program, the network size per size, each judge's verdict and level, and what remains
   unproven (the compiler itself is UNPROVEN; correctness beyond the reach-checked size rests on the
   contracts plus testing).

## What this cannot do
Nothing generative (many valid outputs, aesthetic objectives), nothing perceptual from raw noisy pixels,
no search or planning, no counting or comparison of magnitudes, no non-monotone updates (complement,
toggle). These are the open gaps recorded in `mission-02/SCIENTIFIC_VERDICT.md`.
