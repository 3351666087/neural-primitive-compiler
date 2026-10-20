# LLM-guided arm: proposal log

Proposer: Claude (this session), following `skills/neural-compiler/SKILL.md`. Raw outcomes:
`abc_results.json` (groups A–C) and `../D_unseen/results.json` (group D, field `llm_sketches`).

**Bias statement.** For groups A–C the proposer also wrote the primitive library, the task specs and
the direct designs, and had already seen some blind-search outputs during development (in
particular the `compose_dag` solution for dense parity, `latch[relay(a), counter(k=2)[a,_]]`, during
the first smoke test). A–C outcomes therefore measure *how much a correct decomposition helps the
solver*, not whether an LLM can find that decomposition. Group D is the less biased test.

## Groups A–C (sketches in `ABC.npc`, one proposal each, no revisions needed)

| sketch | reasoning written before running | choice space / integer holes |
|---|---|---|
| A3_llm1 | Latency 1 with four input taps (a@1, b@1..3) cannot go through any primitive, since each one adds a layer. So: one raw neuron, solver fills weights/threshold. | 1 / 5 |
| B2_llm1 | Memory = `latch(set=s, rst=r)`. The answer must combine q, r, s at t-1 with the latch, at latency 1, so one raw answer neuron reads all four. | 1 / 5 |
| B3_llm1 | Latch remembers "an a has occurred since reset". The output is a & !r & !latch: one raw neuron. | 1 / 4 |
| C1_llm1 | Toggle: gates read the latch state to decide set vs reset (feedback). Offered `latch` vs `latch_lite`. | 2 / 0 |
| C2_llm1 | Latch set by every a, reset by every second a (counter k=2). The counter fires one step after the a, so the set path needs a relay. Offered delays, k and port order. | 32 / 0 |
| C3_llm1 | Latch set by a window detector and reset by a delayed r. Offered window parameters and relay delay. | 12 / 0 |

Group D proposals are appended below once the D tasks exist (written **before** the automatic
searchers were run on D).

## Group D (sketches in `D_sketches.npc`)

Written after the freeze (`522f7b8`) and task generation, before any automatic searcher ran on D.
Only `npc realize` was used (SKILL step 3). Predictions written down at the same time:

| task | LLM reading of the spec | LLM verdict before running searchers |
|---|---|---|
| D01 | reset `count[3](b) >= 0` is always true, so the counter never reaches 1: y never fires | trivial (no sketch) |
| D05 | parity-like `modcount[4](b) == 0` at latency 1: the newest b raises the output after 3 b's but lowers it after 0 | UNREALIZABLE (confirmed by `realize`) |
| D12 | "exactly 2 b in the last 4 steps" at latency 1: non-monotone in the newest b | UNREALIZABLE (confirmed) |
| D13 | `once(b) ^ a`: XOR with the newest a | UNREALIZABLE (confirmed) |
| D14 | `a(t-3) <-> a(t-1)` at latency 1: XNOR with the newest a | UNREALIZABLE (confirmed) |
| D02 | latch-like loop gated by a parity-with-reset signal delayed by 3 | sketch `D02_llm1` (3 raw neurons, structure fixed, 21 integer holes) |
| D06 | NAND of 4-step-old inputs, silent for t < 4 | sketch `D06_llm1` (start pulse + 1 neuron) |
| D16 | `b(t-5) or b(t-6)` | sketch `D16_llm1` (relay + window, 6 choices) |
| D17 | start-up bump at t=2,3 then `b(t-6)` | sketch `D17_llm1` (relay + start pulse + 1 neuron) |
| D18 | `not b(t-5)` from t=5 on | sketch `D18_llm1` (relay + start pulse + biased neuron) |
| Dhand | latch for "a since r" + integrating output neuron for b-parity, gated by the latch | `Dhand_..._llm1`; fallback `_llm2` with a separate parity neuron |
| others | plain delays / constants (D00, D03, D04, D07–D11, D15, D19) | trivial, left to the automatic pipeline |

### Outcome summary (group D)

- Round 1: 5 of 6 attempted tasks solved (D06 2n, D16 2n, D17 3n, D18 3n, D-hand 2n); D02 failed (UNSAT in the proposed structure). D-hand fallback `_llm2` also UNSAT.
- D02 round 2 (start-up fix): UNSAT in structure. Semantics re-checked against the spec evaluator: 0/2000 mismatches, so the reading was right and the decomposition was wrong.
- D02 round 3 (3-neuron parity block): TIMEOUT at 300 s. Fallback CEGIS with exactly 3 neurons: TIMEOUT at 300 s.
- Net: an LLM can contribute spec simplification and good decompositions, but it also proposes wrong structures. The solver/verifier caught every one of them (no false acceptances).
