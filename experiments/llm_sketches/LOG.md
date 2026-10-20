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
