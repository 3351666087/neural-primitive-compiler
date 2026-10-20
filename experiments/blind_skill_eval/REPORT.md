# Blind re-run of the "LLM proposes, verifier decides" arm

This is the blind re-run asked for in `limitations.md` §5. One agent session (Claude Opus 5.5, started from another session) acted as a user of `skills/neural-compiler/SKILL.md` on 10 tasks, without having seen how the tasks were solved before. The agent followed the skill's workflow (realize → sketch → `synth --method sketch` → counterexamples via `sim` → at most 5 revisions). Every number below comes from a file in this folder.

## Result in one paragraph

All 10 tasks ended with `[reach] VERIFIED_UNBOUNDED` on the **first** proposal: 10 proposals and 10 in-loop verifier calls in total. No counterexample ever came up, so the revise loop (sim → diagnose → revise) was **never exercised**. Each run is checked a second time with `npc verify` on the stored network, and that also printed `[reach] VERIFIED_UNBOUNDED` for all 10. Against the earlier sketch arm (written by the same model that designed the library and tasks), this run solved one more task (D02, which the earlier sketch left `EXHAUSTED`). It had fewer or equal neurons on 8 of the 9 tasks both arms solved, and more on Dhand (5 vs 2). It never had fewer state bits: equal on 5 tasks, +1 on 4. The sketches left **all** weights and thresholds to Z3. So this run measures "LLM chooses topology, taps and delays; Z3 chooses weights", not "LLM designs the network".

## Blindness protocol and its limits

- **Read before and during the runs:** `skills/neural-compiler/SKILL.md`, `src/npc/lib/primitives.npc`, the module docstring of `src/npc/spec.py` (printed via `ast.get_docstring`, not the rest of the file), `experiments/tasks.npc`, `experiments/D_unseen/tasks.npc`, `experiments/D_unseen/hand.npc`, plus CLI output (`npc --help`, `npc synth|realize|sim|verify --help`, `npc primitives`).
- **Not opened at any time:** `experiments/results/`, `experiments/designs.npc`, any file in `experiments/llm_sketches/` other than `abc_results.json`, `experiments/D_unseen/SUMMARY.md`, `evidence-ledger.md`, `README.md`, `examples/`.
- **Opened only after the own results were frozen:** `experiments/llm_sketches/abc_results.json` and `experiments/D_unseen/results.json`. `per_task.tsv` was hashed first (`per_task.sha256`, sha256 `12b1dbb8…`), and `markers.tsv` has a `COMPARE start` row at that point.
- **Leaks / limits, stated plainly:**
  1. The proposer is the same model family as the designer. The run is blind to *solutions and results*, not independent in *priors*. For example, B2/B3 came out the same size as the earlier arm.
  2. Directory listings showed file names. One of them, `experiments/D_unseen/D02_cegis_n3_300s.json`, was visible before D02 was attempted and hints that D02 was hard for 3-neuron CEGIS. The file was not opened.
  3. SKILL.md does not document the `network` syntax. It was learned from `npc check` parse errors: 2 logged probes (`raw/001`, `raw/002`, file `syntax_probe.npc`) plus 6 variants in one shell loop that the wrapper did **not** log (their output is only in the session transcript). The variant that worked was `inst m = latch() set=s rst=r` with `output y = m.out`.
  4. Another session was editing this checkout at the same time. `src/npc/verify.py` changed at 05:13:50Z. Every verifier call here ran earlier (last at 05:12:20Z, see `calls.tsv`), and at that time the diff was a docstring plus one import line.

## Protocol per task (as run)

1. `npc realize` (SKILL step 3).
2. Write one sketch into `sketches.npc` (`<TASK>_p1`). Topology, taps and delays are fixed by the proposer. Every weight and threshold is an integer hole `?[lo,hi]`, and no `?{…}` discrete choices were used. The comment above each sketch records the spec reading and the intended role of each neuron.
3. `npc synth … --method sketch --sketch <TASK>_p1 --out rec/<TASK>_p1.json`. This counts as **one verifier call**: it runs `[bmc]` and `[reach]` itself.
4. Post-hoc check (not part of the loop): extract `.network` to `rec/<TASK>_p1.net.json` and run `npc verify --horizon 10`. Each task's first attempt with the whole record failed with an input error (exit 3, see the friction section).

**Wall time** is measured from the previous task's synth result to this task's synth result (B2: from its `realize` call). It includes model generation time for reading the spec, designing and writing the sketch. The marker windows in `markers.tsv` are **shifted by one task**: design thinking for task k+1 usually happened before the command that marked task k as ended. So use the column below, not the markers. From the first logged call (05:05:17Z) to the last synth result (05:11:41Z) took 384.4 s. Time spent reading the docs before that was not timed. In-loop `npc` time was 29.83 s over 20 calls (10 realize + 10 synth). All 44 logged calls took 36.24 s.

## Results

| task | `npc realize` | proposals | verifier calls in loop | wall s (prev result → this result) | npc tool s | final status | neurons | synapses | state_bits | max \|w\| | max delay |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B2_remember_query | COMPILED (min 3 states, one-hot 26 neurons) | 1 | 1 | 8.1 | 0.37 | reach VERIFIED_UNBOUNDED | 2 | 7 | 4 | 2 | 1 |
| B3_first_since_reset | COMPILED (min 3 states, one-hot 14 neurons) | 1 | 1 | 15.6 | 0.22 | reach VERIFIED_UNBOUNDED | 2 | 6 | 3 | 2 | 1 |
| C1_toggle_sparse | COMPILED (min 4 states, one-hot 8 neurons) | 1 | 1 | 25.7 | 0.35 | reach VERIFIED_UNBOUNDED | 2 | 5 | 4 | 2 | 2 |
| C2_parity_dense | COMPILED (min 4 states, one-hot 10 neurons) | 1 | 1 | 31.5 | 0.35 | reach VERIFIED_UNBOUNDED | 2 | 7 | 6 | 3 | 3 |
| C3_latched_alarm | COMPILED (min 12 states, one-hot 50 neurons) | 1 | 1 | 20.5 | 0.37 | reach VERIFIED_UNBOUNDED | 1 | 5 | 7 | 5 | 4 |
| D02 | COMPILED (min 7 states, one-hot 30 neurons) | 1 | 1 | 130.6 | 5.98 | reach VERIFIED_UNBOUNDED | 5 | 20 | 13 | 4 | 3 |
| D06 | COMPILED (min 16 states, one-hot 66 neurons) | 1 | 1 | 17.5 | 0.42 | reach VERIFIED_UNBOUNDED | 2 | 3 | 12 | 2 | 4 |
| D17 | COMPILED (min 64 states, one-hot 258 neurons) | 1 | 1 | 17.3 | 0.36 | reach VERIFIED_UNBOUNDED | 2 | 3 | 10 | 1 | 6 |
| D18 | COMPILED (min 32 states, one-hot 130 neurons) | 1 | 1 | 9.7 | 0.22 | reach VERIFIED_UNBOUNDED | 2 | 2 | 10 | 1 | 5 |
| Dhand_second_b_after_a | COMPILED (min 4 states, one-hot 34 neurons) | 1 | 1 | 70.6 | 21.19 | reach VERIFIED_UNBOUNDED | 5 | 24 | 8 | 3 | 1 |

### Verbatim status lines (from `raw/`)

**B2_remember_query**: proposal `B2_p1`, synth log `raw/004_B2_synth.txt`, re-check log `raw/033_B2_recheck_verify.txt` (exit 2)

```
$ npc synth experiments/tasks.npc experiments/blind_skill_eval/sketches.npc --spec B2_remember_query --method sketch --sketch B2_p1 --out experiments/blind_skill_eval/rec/B2_p1.json
method=sketch status=SOLVED iterations=2 candidates=1 examples=4 time=0.06s (synth 0.06s, verify 0.00s)
[bmc] VERIFIED_BOUNDED (0.017s) - holds for all binary input traces over ['s', 'r', 'q'] of length 8 (steps 0..7); says nothing about later steps
[reach] VERIFIED_UNBOUNDED (0.001s) - holds for all binary input traces over ['s', 'r', 'q'], every length (finite-state proof)
$ npc verify experiments/tasks.npc --net-json experiments/blind_skill_eval/rec/B2_p1.net.json --spec B2_remember_query --horizon 10 --out experiments/blind_skill_eval/rec/B2_p1_reverify.json
[bmc] VERIFIED_BOUNDED (0.051s) - holds for all binary input traces over ['s', 'r', 'q'] of length 10 (steps 0..9); says nothing about later steps
[exhaustive] RESOURCE_LIMIT (0.000s) - NO CONCLUSION {'traces_needed': 1073741824, 'max_traces': 1048576}
[reach] VERIFIED_UNBOUNDED (0.000s) - holds for all binary input traces over ['s', 'r', 'q'], every length (finite-state proof)
```

**B3_first_since_reset**: proposal `B3_p1`, synth log `raw/006_B3_synth.txt`, re-check log `raw/034_B3_recheck_verify.txt` (exit 0)

```
$ npc synth experiments/tasks.npc experiments/blind_skill_eval/sketches.npc --spec B3_first_since_reset --method sketch --sketch B3_p1 --out experiments/blind_skill_eval/rec/B3_p1.json
method=sketch status=SOLVED iterations=1 candidates=1 examples=3 time=0.02s (synth 0.02s, verify 0.00s)
[bmc] VERIFIED_BOUNDED (0.008s) - holds for all binary input traces over ['a', 'r'] of length 8 (steps 0..7); says nothing about later steps
[reach] VERIFIED_UNBOUNDED (0.000s) - holds for all binary input traces over ['a', 'r'], every length (finite-state proof)
$ npc verify experiments/tasks.npc --net-json experiments/blind_skill_eval/rec/B3_p1.net.json --spec B3_first_since_reset --horizon 10 --out experiments/blind_skill_eval/rec/B3_p1_reverify.json
[bmc] VERIFIED_BOUNDED (0.033s) - holds for all binary input traces over ['a', 'r'] of length 10 (steps 0..9); says nothing about later steps
[exhaustive] VERIFIED_BOUNDED (0.575s) - holds for all binary input traces over ['a', 'r'] of length 10 (steps 0..9); says nothing about later steps
[reach] VERIFIED_UNBOUNDED (0.000s) - holds for all binary input traces over ['a', 'r'], every length (finite-state proof)
```

**C1_toggle_sparse**: proposal `C1_p1`, synth log `raw/008_C1_synth.txt`, re-check log `raw/035_C1_recheck_verify.txt` (exit 0)

```
$ npc synth experiments/tasks.npc experiments/blind_skill_eval/sketches.npc --spec C1_toggle_sparse --method sketch --sketch C1_p1 --out experiments/blind_skill_eval/rec/C1_p1.json
method=sketch status=SOLVED iterations=1 candidates=1 examples=3 time=0.03s (synth 0.03s, verify 0.00s)
[bmc] VERIFIED_BOUNDED (0.007s) - holds for all binary input traces over ['a'] satisfying the assumption of length 8 (steps 0..7); says nothing about later steps
[reach] VERIFIED_UNBOUNDED (0.000s) - holds for all binary input traces over ['a'] satisfying the assumption, every length (finite-state proof)
$ npc verify experiments/tasks.npc --net-json experiments/blind_skill_eval/rec/C1_p1.net.json --spec C1_toggle_sparse --horizon 10 --out experiments/blind_skill_eval/rec/C1_p1_reverify.json
[bmc] VERIFIED_BOUNDED (0.018s) - holds for all binary input traces over ['a'] satisfying the assumption of length 10 (steps 0..9); says nothing about later steps
[exhaustive] VERIFIED_BOUNDED (0.001s) - holds for all binary input traces over ['a'] satisfying the assumption of length 10 (steps 0..9); says nothing about later steps
[reach] VERIFIED_UNBOUNDED (0.000s) - holds for all binary input traces over ['a'] satisfying the assumption, every length (finite-state proof)
```

**C2_parity_dense**: proposal `C2_p1`, synth log `raw/010_C2_synth.txt`, re-check log `raw/036_C2_recheck_verify.txt` (exit 0)

```
$ npc synth experiments/tasks.npc experiments/blind_skill_eval/sketches.npc --spec C2_parity_dense --method sketch --sketch C2_p1 --out experiments/blind_skill_eval/rec/C2_p1.json
method=sketch status=SOLVED iterations=1 candidates=1 examples=3 time=0.03s (synth 0.03s, verify 0.00s)
[bmc] VERIFIED_BOUNDED (0.009s) - holds for all binary input traces over ['a'] of length 8 (steps 0..7); says nothing about later steps
[reach] VERIFIED_UNBOUNDED (0.000s) - holds for all binary input traces over ['a'], every length (finite-state proof)
$ npc verify experiments/tasks.npc --net-json experiments/blind_skill_eval/rec/C2_p1.net.json --spec C2_parity_dense --horizon 10 --out experiments/blind_skill_eval/rec/C2_p1_reverify.json
[bmc] VERIFIED_BOUNDED (0.016s) - holds for all binary input traces over ['a'] of length 10 (steps 0..9); says nothing about later steps
[exhaustive] VERIFIED_BOUNDED (0.001s) - holds for all binary input traces over ['a'] of length 10 (steps 0..9); says nothing about later steps
[reach] VERIFIED_UNBOUNDED (0.000s) - holds for all binary input traces over ['a'], every length (finite-state proof)
```

**C3_latched_alarm**: proposal `C3_p1`, synth log `raw/012_C3_synth.txt`, re-check log `raw/037_C3_recheck_verify.txt` (exit 0)

```
$ npc synth experiments/tasks.npc experiments/blind_skill_eval/sketches.npc --spec C3_latched_alarm --method sketch --sketch C3_p1 --out experiments/blind_skill_eval/rec/C3_p1.json
method=sketch status=SOLVED iterations=7 candidates=1 examples=9 time=0.07s (synth 0.07s, verify 0.00s)
[bmc] VERIFIED_BOUNDED (0.005s) - holds for all binary input traces over ['a', 'r'] of length 8 (steps 0..7); says nothing about later steps
[reach] VERIFIED_UNBOUNDED (0.002s) - holds for all binary input traces over ['a', 'r'], every length (finite-state proof)
$ npc verify experiments/tasks.npc --net-json experiments/blind_skill_eval/rec/C3_p1.net.json --spec C3_latched_alarm --horizon 10 --out experiments/blind_skill_eval/rec/C3_p1_reverify.json
[bmc] VERIFIED_BOUNDED (0.011s) - holds for all binary input traces over ['a', 'r'] of length 10 (steps 0..9); says nothing about later steps
[exhaustive] VERIFIED_BOUNDED (0.270s) - holds for all binary input traces over ['a', 'r'] of length 10 (steps 0..9); says nothing about later steps
[reach] VERIFIED_UNBOUNDED (0.002s) - holds for all binary input traces over ['a', 'r'], every length (finite-state proof)
```

**D02**: proposal `D02_p1`, synth log `raw/014_D02_synth.txt`, re-check log `raw/038_D02_recheck_verify.txt` (exit 0)

```
$ npc synth experiments/D_unseen/tasks.npc experiments/blind_skill_eval/sketches.npc --spec D02 --method sketch --sketch D02_p1 --out experiments/blind_skill_eval/rec/D02_p1.json
method=sketch status=SOLVED iterations=13 candidates=1 examples=15 time=5.60s (synth 5.60s, verify 0.00s)
[bmc] VERIFIED_BOUNDED (0.023s) - holds for all binary input traces over ['a', 'b'] of length 8 (steps 0..7); says nothing about later steps
[reach] VERIFIED_UNBOUNDED (0.002s) - holds for all binary input traces over ['a', 'b'], every length (finite-state proof)
$ npc verify experiments/D_unseen/tasks.npc --net-json experiments/blind_skill_eval/rec/D02_p1.net.json --spec D02 --horizon 10 --out experiments/blind_skill_eval/rec/D02_p1_reverify.json
[bmc] VERIFIED_BOUNDED (0.127s) - holds for all binary input traces over ['a', 'b'] of length 10 (steps 0..9); says nothing about later steps
[exhaustive] VERIFIED_BOUNDED (1.052s) - holds for all binary input traces over ['a', 'b'] of length 10 (steps 0..9); says nothing about later steps
[reach] VERIFIED_UNBOUNDED (0.002s) - holds for all binary input traces over ['a', 'b'], every length (finite-state proof)
```

**D06**: proposal `D06_p1`, synth log `raw/016_D06_synth.txt`, re-check log `raw/039_D06_recheck_verify.txt` (exit 0)

```
$ npc synth experiments/D_unseen/tasks.npc experiments/blind_skill_eval/sketches.npc --spec D06 --method sketch --sketch D06_p1 --out experiments/blind_skill_eval/rec/D06_p1.json
method=sketch status=SOLVED iterations=1 candidates=1 examples=3 time=0.03s (synth 0.03s, verify 0.00s)
[bmc] VERIFIED_BOUNDED (0.004s) - holds for all binary input traces over ['a', 'b'] of length 8 (steps 0..7); says nothing about later steps
[reach] VERIFIED_UNBOUNDED (0.005s) - holds for all binary input traces over ['a', 'b'], every length (finite-state proof)
$ npc verify experiments/D_unseen/tasks.npc --net-json experiments/blind_skill_eval/rec/D06_p1.net.json --spec D06 --horizon 10 --out experiments/blind_skill_eval/rec/D06_p1_reverify.json
[bmc] VERIFIED_BOUNDED (0.007s) - holds for all binary input traces over ['a', 'b'] of length 10 (steps 0..9); says nothing about later steps
[exhaustive] VERIFIED_BOUNDED (0.506s) - holds for all binary input traces over ['a', 'b'] of length 10 (steps 0..9); says nothing about later steps
[reach] VERIFIED_UNBOUNDED (0.005s) - holds for all binary input traces over ['a', 'b'], every length (finite-state proof)
```

**D17**: proposal `D17_p1`, synth log `raw/018_D17_synth.txt`, re-check log `raw/040_D17_recheck_verify.txt` (exit 0)

```
$ npc synth experiments/D_unseen/tasks.npc experiments/blind_skill_eval/sketches.npc --spec D17 --method sketch --sketch D17_p1 --out experiments/blind_skill_eval/rec/D17_p1.json
method=sketch status=SOLVED iterations=1 candidates=1 examples=3 time=0.02s (synth 0.02s, verify 0.00s)
[bmc] VERIFIED_BOUNDED (0.003s) - holds for all binary input traces over ['a', 'b'] of length 8 (steps 0..7); says nothing about later steps
[reach] VERIFIED_UNBOUNDED (0.001s) - holds for all binary input traces over ['a', 'b'], every length (finite-state proof)
$ npc verify experiments/D_unseen/tasks.npc --net-json experiments/blind_skill_eval/rec/D17_p1.net.json --spec D17 --horizon 10 --out experiments/blind_skill_eval/rec/D17_p1_reverify.json
[bmc] VERIFIED_BOUNDED (0.006s) - holds for all binary input traces over ['a', 'b'] of length 10 (steps 0..9); says nothing about later steps
[exhaustive] VERIFIED_BOUNDED (0.504s) - holds for all binary input traces over ['a', 'b'] of length 10 (steps 0..9); says nothing about later steps
[reach] VERIFIED_UNBOUNDED (0.001s) - holds for all binary input traces over ['a', 'b'], every length (finite-state proof)
```

**D18**: proposal `D18_p1`, synth log `raw/020_D18_synth.txt`, re-check log `raw/041_D18_recheck_verify.txt` (exit 0)

```
$ npc synth experiments/D_unseen/tasks.npc experiments/blind_skill_eval/sketches.npc --spec D18 --method sketch --sketch D18_p1 --out experiments/blind_skill_eval/rec/D18_p1.json
method=sketch status=SOLVED iterations=1 candidates=1 examples=3 time=0.01s (synth 0.01s, verify 0.00s)
[bmc] VERIFIED_BOUNDED (0.004s) - holds for all binary input traces over ['a', 'b'] of length 8 (steps 0..7); says nothing about later steps
[reach] VERIFIED_UNBOUNDED (0.001s) - holds for all binary input traces over ['a', 'b'], every length (finite-state proof)
$ npc verify experiments/D_unseen/tasks.npc --net-json experiments/blind_skill_eval/rec/D18_p1.net.json --spec D18 --horizon 10 --out experiments/blind_skill_eval/rec/D18_p1_reverify.json
[bmc] VERIFIED_BOUNDED (0.006s) - holds for all binary input traces over ['a', 'b'] of length 10 (steps 0..9); says nothing about later steps
[exhaustive] VERIFIED_BOUNDED (0.441s) - holds for all binary input traces over ['a', 'b'] of length 10 (steps 0..9); says nothing about later steps
[reach] VERIFIED_UNBOUNDED (0.001s) - holds for all binary input traces over ['a', 'b'], every length (finite-state proof)
```

**Dhand_second_b_after_a**: proposal `Dhand_p1`, synth log `raw/022_Dhand_synth.txt`, re-check log `raw/042_Dhand_recheck_verify.txt` (exit 2)

```
$ npc synth experiments/D_unseen/hand.npc experiments/blind_skill_eval/sketches.npc --spec Dhand_second_b_after_a --method sketch --sketch Dhand_p1 --out experiments/blind_skill_eval/rec/Dhand_p1.json
method=sketch status=SOLVED iterations=21 candidates=1 examples=23 time=20.82s (synth 20.82s, verify 0.00s)
[bmc] VERIFIED_BOUNDED (0.093s) - holds for all binary input traces over ['a', 'b', 'r'] of length 8 (steps 0..7); says nothing about later steps
[reach] VERIFIED_UNBOUNDED (0.002s) - holds for all binary input traces over ['a', 'b', 'r'], every length (finite-state proof)
$ npc verify experiments/D_unseen/hand.npc --net-json experiments/blind_skill_eval/rec/Dhand_p1.net.json --spec Dhand_second_b_after_a --horizon 10 --out experiments/blind_skill_eval/rec/Dhand_p1_reverify.json
[bmc] VERIFIED_BOUNDED (0.162s) - holds for all binary input traces over ['a', 'b', 'r'] of length 10 (steps 0..9); says nothing about later steps
[exhaustive] RESOURCE_LIMIT (0.000s) - NO CONCLUSION {'traces_needed': 1073741824, 'max_traces': 1048576}
[reach] VERIFIED_UNBOUNDED (0.002s) - holds for all binary input traces over ['a', 'b', 'r'], every length (finite-state proof)
```

### Comparison with the earlier (designer-written) sketch arm

| task | this run: status / proposals / N-S-bits / synth s | earlier arm: sketch → status / candidates / choice space / N-S-bits / synth s |
|---|---|---|
| B2_remember_query | SOLVED / 1 / 2-7-4 / 0.06 | `B2_llm1` → SOLVED / 1 / 1 / 2-7-4 / 0.051 |
| B3_first_since_reset | SOLVED / 1 / 2-6-3 / 0.02 | `B3_llm1` → SOLVED / 1 / 1 / 2-6-3 / 0.021 |
| C1_toggle_sparse | SOLVED / 1 / 2-5-4 / 0.03 | `C1_llm1` → SOLVED / 1 / 2 / 3-7-4 / 0.011 |
| C2_parity_dense | SOLVED / 1 / 2-7-6 / 0.03 | `C2_llm1` → SOLVED / 1 / 16 / 3-5-6 / 0.013 |
| C3_latched_alarm | SOLVED / 1 / 1-5-7 / 0.07 | `C3_llm1` → SOLVED / 7 / 12 / 3-7-7 / 0.013 |
| D02 | SOLVED / 1 / 5-20-13 / 5.60 | `D02_llm1` → EXHAUSTED / 1 / n/a / — / 0.411 |
| D06 | SOLVED / 1 / 2-3-12 / 0.03 | `D06_llm1` → SOLVED / 1 / n/a / 2-5-11 / 0.029 |
| D17 | SOLVED / 1 / 2-3-10 / 0.02 | `D17_llm1` → SOLVED / 1 / n/a / 3-4-9 / 0.039 |
| D18 | SOLVED / 1 / 2-2-10 / 0.01 | `D18_llm1` → SOLVED / 1 / n/a / 3-6-9 / 0.02 |
| Dhand_second_b_after_a | SOLVED / 1 / 5-24-8 / 20.82 | `Dhand_second_b_after_a_llm1` → SOLVED / 1 / n/a / 2-7-7 / 1.046<br>`Dhand_second_b_after_a_llm2` → EXHAUSTED / 1 / n/a / — / 0.669 |

## Notes per design (what the proposer did vs what Z3 did)

| task | proposer's idea (from the sketch comment) | did Z3's weights implement the stated per-neuron roles? |
|---|---|---|
| B2 | `latch(s,r)` + one readout reading q, s, r, latch at delay 1 | yes (q +2, s +1, r −2, latch +1, threshold 3) |
| B3 | `latch(a,r)` + readout `a & !r & !latch` | yes |
| C1 | toggle `p` + helper `h = a & p`, using `!(a & prev(a))` | yes, exactly the planned weights |
| C2 | latency-2 pipeline: 3-input parity of (p@2, a@3, a@2) with one hidden unit | **no**: the topology was kept, but e.g. `a→m d=2` is −3, while the planned majority unit needed a positive weight. Z3 found a different 2-neuron function. |
| C3 | a single neuron: self-loop + a@2,3,4 + r@2 | yes (self +3, a +1 each, r −5, threshold 2) |
| D02 | tonic `d` (enables the hold term for t≥3), latency-2 parity-with-reset `o` with two hidden units, readout | hidden-unit roles were left to Z3 on purpose. The sketch has 21 synapse lines, and the record has 20 (one weight was presumably solved as 0 and dropped). |
| D06 | read `(t≥4) & !(a&b)(t-4)`: tonic `d`@4, a@4, b@4 | yes. `raw/044_D06_sim_sim.txt` shows the trace. |
| D17 | read `t∈{2,3}` or `(t≥6 & b(t-6))`: `d@2 − d@4 + b@6` | yes (+1, −1, +1). `raw/043_D17_sim_sim.txt` shows the start-up pulses. |
| D18 | read `(t≥5) & !b(t-5)`: `d@5 − b@5` | yes |
| Dhand | one-hot split of (A∧odd, A∧even) by the last input: 5 neurons, output = one of them | **no**: e.g. `v→yn` is −3, while the plan needed it positive. Z3 re-purposed the neurons inside the given wiring. |

In 3 of 10 tasks (C2, D02, Dhand) the verified network therefore exists **because Z3 searched inside the proposed wiring**, not because the proposer's functional decomposition was right. This run gives no evidence on whether those decompositions would have verified with the intended weights.

## Comparison with the earlier arm (computed after freezing `per_task.tsv`)

The comparison table at the end of **Results** comes from `abc_results.json` (B/C) and the `llm_sketches` field of `D_unseen/results.json` (D). N-S-bits means neurons-synapses-state_bits as reported by each record's `stats`/`network_stats`.

- **Solve rate on these 10 tasks:** this run 10/10, each with 1 proposal. Earlier arm 9/10 of tasks with at least one `SOLVED` sketch: D02 is `EXHAUSTED`, and Dhand has one `SOLVED` (`_llm1`) and one `EXHAUSTED` (`_llm2`). The earlier records keep no revision history or wall time, so their "number of proposals" can only be read as the number of listed sketches, and effort cannot be compared.
- **Neurons:** fewer in this run on C1, C2, C3, D17, D18 (5 tasks); equal on B2, B3, D06 (3); more on Dhand (5 vs 2).
- **Synapses:** fewer on C1, C3, D06, D17, D18; equal on B2, B3; more on C2 (7 vs 5) and Dhand (24 vs 7).
- **State bits:** equal on B2, B3, C1, C2, C3; **higher by 1** on D06, D17, D18 and Dhand. On no task did this run have fewer state bits. In the D tasks the extra bits come from a tonic neuron plus long delay lines (history bits). The earlier networks there use `init=1`, `leak` 1–4, `vmin<0` and `bias=2` (visible in the network JSON). `init` does not appear in any file the blind user was allowed to read, and SKILL.md lists no neuron attributes. That is one concrete, checkable advantage the designer had.
- **Solver effort:** these sketches have 0 discrete choices and 3–29 integer holes each (raw integer box from 1.5e2 for D18 up to 4.7e22 for Dhand; see `holes.tsv`). Synth time was larger where the hole count was large: Dhand 20.82 s here vs 1.046 s for the earlier `_llm1`. The earlier arm reports `choice_space` 2/16/12 for C1/C2/C3, so it used discrete choices there. How many integer holes it used cannot be told without opening its `.npc` files, which were not opened.
- **D02** is the only difference in success. It is one task, and the earlier failure is a single sketch that came out `EXHAUSTED`, so it supports no general claim beyond "a different decomposition existed and Z3 found weights for it".

## What this run does not show

- **The counterexample-driven loop.** Zero counterexamples came up, so SKILL steps 6–7 (sim, diagnosis, revise, fall back to CEGIS after ~5) were never tested.
- **Independence from the designer's priors.** Same model family, see above.
- **A rate with a tight interval.** 10/10 on one run, with no repetitions. The exact (Clopper-Pearson) 95% lower bound for 10/10 is 0.692. Task difficulty is uneven: after reading the spec, D06, D17 and D18 reduce to delays plus a start-up guard.
- **Minimality** (none claimed), **behaviour on hardware or with noise** (`VERIFIED_UNBOUNDED` covers the ideal integer semantics only), or anything about tasks outside these 10.

## Skill and tool friction found (useful for SKILL.md)

1. SKILL.md never shows `network` syntax (`inputs …`, `inst x = prim() port=sig`, `neuron …`, `synapse …`, `output y = …`; there is no `outputs` line). A skill-only user has to probe the parser.
2. SKILL step 8.5 says the `--out` record lets the user re-run `npc verify`, but `npc verify --net-json rec.json` rejects it with `error: unsupported format None` (`raw/023`–`raw/032`). Only the record's `.network` object is accepted.
3. `npc verify` exits **2** ("no conclusion") for B2 and Dhand even though `[reach] VERIFIED_UNBOUNDED`, because `[exhaustive]` hits `RESOURCE_LIMIT`. An agent that trusts the exit code would under-report. SKILL.md's rule "read the status line of every engine" is what catches this.
4. Neuron attributes (`init`, `reset`, `vmin`/`vmax`, non-`full` leak) are not described in SKILL.md, and `init` appears in none of the allowed files.

## Files

| file | content |
|---|---|
| `sketches.npc` | every proposal (10, all `_p1`), with spec reading and design rationale in comments |
| `syntax_probe.npc` | the syntax probe (deliberately broken, not a proposal) |
| `raw/NNN_<task>_<cmd>.txt` | full stdout/stderr of every wrapped `npc` call (44) |
| `calls.tsv` | one row per wrapped call: time, seconds, exit code, status summary |
| `markers.tsv` | task start/end markers (shifted, see above) and the `COMPARE start` marker |
| `per_task.tsv`, `per_task.sha256` | own results, frozen and hashed before the comparison files were opened |
| `holes.tsv` | integer holes / discrete choices per sketch |
| `tables.md` | generated tables, including the verbatim status lines and the comparison |
| `rec/<T>_p1.json` | synth records (`--out`) · `rec/<T>_p1.net.json` bare network · `rec/<T>_p1_reverify.json` verify records |
| `npcl.sh`, `mark.sh`, `tabulate.py`, `make_tables.py` | logging wrapper, markers, table generators |

Nothing under `src/`, `tests/` or any existing file was modified by this run, and nothing was committed.
