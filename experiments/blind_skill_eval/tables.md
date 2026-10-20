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
