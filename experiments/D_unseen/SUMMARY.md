# Group D results

| task | guarantee | FSM states | classical | CEGIS | compose_dag | LLM sketch |
|---|---|---|---|---|---|---|
| D00 | `y <-> prev(a)` | 2 | COMPILED 10n/53s (0.004s) | SOLVED 1n/1s (0.036s) | SOLVED 1n/1s (0.004s) | — |
| D01 | `y <-> prev(modcount[4](since(a, true) -> once[2,2](true); count[3](b) >= 0) == 1)` | 1 | COMPILED 6n/28s (0.002s) | SOLVED 1n/1s (0.023s) | SOLVED 1n/1s (0.007s) | — |
| D02 | `y <-> prev(since(once[2,2](modcount[2](a; b) == 0), a))` | 7 | COMPILED 30n/181s (0.003s) | TIMEOUT (120.008s) | EXHAUSTED (11.223s) | D02_llm1: EXHAUSTED |
| D03 | `y <-> prev(b)` | 2 | COMPILED 10n/53s (0.002s) | SOLVED 1n/4s (0.054s) | SOLVED 1n/1s (0.005s) | — |
| D04 | `y <-> prev[2](b)` | 4 | COMPILED 18n/108s (0.003s) | SOLVED 1n/3s (0.042s) | SOLVED 1n/1s (0.006s) | — |
| D05 | `y <-> prev(atleast(1; false, false, true) <-> (modcount[4](b) == 0))` | 5 | UNREALIZABLE (0.003s) | TIMEOUT (120.007s) | EXHAUSTED (9.142s) | — |
| D06 | `y <-> prev(once[1,2](modcount[3](a; a) == 1) <-> wprev[3](b & a))` | 16 | COMPILED 66n/420s (0.008s) | TIMEOUT (120.011s) | EXHAUSTED (10.695s) | D06_llm1: SOLVED |
| D07 | `y <-> prev(hist[1,1](true & b))` | 4 | COMPILED 18n/109s (0.003s) | SOLVED 2n/11s (1.489s) | EXHAUSTED (8.433s) | — |
| D08 | `y <-> prev(a)` | 2 | COMPILED 10n/53s (0.002s) | SOLVED 1n/5s (0.124s) | SOLVED 1n/1s (0.006s) | — |
| D09 | `y <-> prev[2](b)` | 4 | COMPILED 18n/108s (0.003s) | SOLVED 1n/5s (0.141s) | SOLVED 1n/1s (0.005s) | — |
| D10 | `y <-> prev[2](!((b & b) ^ (a <-> a)))` | 4 | COMPILED 18n/108s (0.003s) | SOLVED 1n/5s (0.525s) | SOLVED 1n/1s (0.006s) | — |
| D11 | `y <-> prev(once[0,2](b) \| hist[0,0](false))` | 4 | COMPILED 18n/111s (0.003s) | SOLVED 1n/5s (0.321s) | SOLVED 1n/3s (0.011s) | — |
| D12 | `y <-> prev((count[4](b) == 2) & a)` | 14 | UNREALIZABLE (0.007s) | TIMEOUT (120.011s) | EXHAUSTED (8.055s) | — |
| D13 | `y <-> prev(once(b) ^ a)` | 4 | UNREALIZABLE (0.003s) | UNREALIZABLE (1.183s) | EXHAUSTED (7.104s) | — |
| D14 | `y <-> prev(prev[2](a) <-> a)` | 8 | UNREALIZABLE (0.003s) | UNREALIZABLE (57.651s) | EXHAUSTED (6.134s) | — |
| D15 | `y <-> prev[2]((count[2](b) == 0) <-> (count[2](b) == 0))` | 3 | COMPILED 14n/88s (0.002s) | SOLVED 1n/5s (0.023s) | SOLVED 2n/2s (0.102s) | — |
| D16 | `y <-> prev(prev[3](once[1,2](b)))` | 28 | COMPILED 114n/740s (0.011s) | TIMEOUT (120.009s) | SOLVED 3n/4s (0.268s) | D16_llm1: SOLVED |
| D17 | `y <-> prev[2](wprev[2](prev[2](b)))` | 64 | COMPILED 258n/1668s (0.025s) | TIMEOUT (120.009s) | EXHAUSTED (6.267s) | D17_llm1: SOLVED |
| D18 | `y <-> prev[2](prev[3](!b))` | 32 | COMPILED 130n/836s (0.013s) | TIMEOUT (120.005s) | EXHAUSTED (6.129s) | D18_llm1: SOLVED |
| D19 | `y <-> prev[2](true -> (a \| b \| a))` | 4 | COMPILED 18n/112s (0.002s) | SOLVED 1n/4s (0.155s) | SOLVED 2n/3s (0.016s) | — |
| Dhand_second_b_after_a | `y <-> prev(b & !a & !r & since(!r, a & !r) & (modcount[2](b; a \| r) == 0))` | 4 | COMPILED 34n/393s (0.004s) | TIMEOUT (120.011s) | EXHAUSTED (55.679s) | Dhand_second_b_after_a_llm1: SOLVED; Dhand_second_b_after_a_llm2: EXHAUSTED |
