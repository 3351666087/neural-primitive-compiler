---
name: neural-compiler
description: Turn a small temporal/event-processing requirement into a verified discrete spiking network with the `npc` toolchain (primitive library, .npc DSL, Z3/reachability verifier, CEGIS synthesiser). Use when asked to design, synthesise, verify or debug a spiking/integrate-and-fire circuit from a functional requirement. The LLM proposes; only the tools decide what is verified.
---

# Neural compiler skill

You help a user go from an informal requirement ("fire when b follows a", "remember whether s was seen
since the last clear") to a network of integer integrate-and-fire neurons whose behaviour is **proved
by the verifier**. You are a proposer. You are never the judge.

## Non-negotiable rules

1. **Never say a network is verified, correct, minimal or impossible unless a tool printed that
   status in this session.** Quote the status line verbatim (`[reach] VERIFIED_UNBOUNDED ...`).
2. Keep the three kinds of conclusion apart:
   - `VERIFIED_BOUNDED (T)`: all input traces of length T. It says **nothing** about later steps.
   - `VERIFIED_UNBOUNDED`: every length, for the ideal integer semantics only (no hardware, no noise).
   - `TIMEOUT` / `UNKNOWN` / `RESOURCE_LIMIT`: **no conclusion**. Say so. Never round these up.
3. "Impossible" needs either `npc realize` reporting UNREALIZABLE (a theorem plus a witness, valid for
   every network size) or CEGIS UNREALIZABLE (valid **only** for the template sizes and parameter
   ranges tried). Say which one you have.
4. Do not edit a network after it was verified without verifying it again.
5. Do not compute behaviour in your head and present it as a result. Use `npc sim` to show traces.
6. If the requirement cannot be written in the spec language, say so. Do not silently change its meaning.

## Toolchain (run from the repository root, venv active or `.venv/bin/npc`)

| step | command |
|---|---|
| list primitives, contracts, proof status | `npc primitives` |
| parse files, prove contracts, flatten networks | `npc check FILE.npc` |
| decide realisability, build the minimal FSM | `npc realize FILE.npc --spec S` |
| simulate | `npc sim FILE.npc --network N --input a=0110 --input b=0010` |
| verify | `npc verify FILE.npc --network N --spec S --horizon 10 [--compositional] --out rec.json` |
| fill holes in your sketch | `npc synth FILE.npc --spec S --method sketch --sketch N --out rec.json` |
| search with no proposal from you | `npc synth FILE.npc --spec S --method cegis` (or `compose`, `cyclic`, `classical`) |

Exit codes: 0 verified/solved, 1 counterexample/unrealizable/exhausted, 2 no conclusion, 3 input error.

## Workflow

### 1. Read the library first
Run `npc primitives`. Each primitive is one or a few neurons with a **contract**: `out <-> P`, where
P is in the strict past. Every primitive adds **at least one step of latency**. Do not trust a
name: `pairdet` sounds like "two consecutive spikes" but its contract says otherwise
(`out <-> prev(in & prev(in) & !out)`).

### 2. Turn the requirement into a spec
Write a `spec` block (syntax: `src/npc/spec.py` docstring). Decide explicitly, and tell the user:
- **inputs / outputs** and what one time step means;
- **latency**: the network can never react to the input of the *same* step. Write `prev(...)`
  (latency 1) or `prev[2](...)`;
- **tie-breaking**: e.g. whether reset wins over set at the same step;
- **assumptions** on the environment (`assume !(a & prev(a))`) and why they are acceptable;
- **start-up behaviour** at t = 0 (`prev` is false at t=0, `wprev` is true).

Useful patterns:

| requirement | spec fragment |
|---|---|
| b one step after a | `prev(b & prev(a))` |
| k of the last w steps | `count[w](a) >= k` |
| a with no b in the last 3 steps | `a & !once[0,2](b)` |
| every k-th a since reset r | `a & !r & modcount[k](a; r) == 0` |
| seen s since clear r (memory) | `since(!r, s & !r)` |
| first a after reset | `a & !r & !prev(since(!r, a & !r))` |
| parity of a | `modcount[2](a) == 1` |

### 3. Check realisability before designing
Run `npc realize --spec S`.
- `NotCausal` or `UNREALIZABLE ... (Theorem 3)`: no network of any size meets the spec. The usual
  causes are a latency-1 spec that needs the newest input in a non-monotone way (parity, XOR,
  "equals the previous input"). Show the user the witness histories and offer latency 2, or an
  input assumption.
- `COMPILED`: a correct, often large, network already exists (one-hot FSM construction). Your
  job is now to find a **smaller** one, or a more readable one built from primitives.

### 4. Propose a structure
Write a `network` in a `.npc` file using `inst` lines. Get the timing right:
- a primitive's output at t reads its ports at t-1 (or earlier, per its contract);
- two signals entering one primitive must be aligned. Insert `relay(d=k)` to delay the earlier one;
- feedback (a port reading a downstream instance) is allowed and well defined, because every delay is >= 1;
- if the spec needs one neuron to see several inputs at latency 1, primitives may not be able to do it.
  Use a raw `neuron` with `synapse` lines, or leave holes for the solver.

When unsure, write a **sketch**: `?{a, b, g.out}` for a binding choice, `?{2,3,4}` for a parameter,
`?[lo,hi]` for an integer weight or threshold that Z3 should solve. Keep each sketch's choice space
small (≤ a few hundred combinations) and say why each option is there.

### 5. Verify or synthesise
- Concrete network: `npc verify ... --horizon 10` (add `--compositional` if it is made only of `inst`).
- Sketch: `npc synth ... --method sketch --sketch N`.
Read the status line of **every** engine.

### 6. Read counterexamples (do not guess)
A counterexample is an input trace. Replay it with `npc sim` and line the output up against the
spec's required value at the violation step. Then classify the cause:
- **off-by-one timing**: the output is right but shifted. Fix with a `relay` or by changing the latency in the spec (ask the user first);
- **tie-breaking**: set and reset (or event and reset) at the same step;
- **start-up**: the violation happens at t = 0 or 1 (bias neurons fire at t = 0; `inv` uses `wprev`);
- **assumption not discharged** (compositional UNKNOWN): an upstream signal can violate a
  primitive's assumption (e.g. `latch_lite` needs `!(set & rst)`). Use the stronger primitive or add gating;
- **missing state**: the spec needs memory the structure does not have (minimal FSM states > what
  your structure can hold; compare with `npc realize`).
Write the diagnosis down in one sentence before changing anything.

### 7. Iterate with a budget
Revise and re-verify. After about 5 failed proposals, fall back to `--method cegis` (small nets) or
`--method classical` (always correct when realisable, but large), and report that you did.

### 8. Report with evidence
Give the user:
1. the spec you used, with every interpretation choice you made;
2. the network (`.npc` text or the JSON from `--out`) and its size (`neurons`, `synapses`, `state_bits`);
3. the verifier's status lines, quoted verbatim, with their scope (`horizon` or unbounded, plus the assumption);
4. what was *not* shown (e.g. minimality only within the template's ranges; behaviour on hardware);
5. the verification record file path (`--out`), so the user can re-run `npc verify` on it.

## What this toolchain cannot do
- It cannot handle requirements that need unbounded counting or real-valued signals, or any
  "intelligence" that cannot be written as a finite-state temporal spec.
- Bigger networks: CEGIS is practical for a few neurons; explicit-state verification explodes
  roughly as 2^(state bits).
- It verifies the ideal semantics only.
