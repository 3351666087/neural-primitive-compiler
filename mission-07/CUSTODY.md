# Held-out mechanism families: custody record

Written by the isolated session "Mission 07 held-out mechanism author" (2026-10-21/22) from `BETA_AUTHOR_BRIEF.md`
(SHA-256 prefix 44b82e8fb02bc233). Files are kept outside the repository in `/Users/null3351/Code/m07-custodian/`.
This session has **not read** them. Hashes below were computed with `shasum -a 256` (contents not displayed); the
family_beta hash matches the prefix in the author's report. Validator output (pass/fail and counts only) re-run here.

| file | SHA-256 |
|---|---|
| family_beta.json | 41c050373310a512c13d33f10ff84d9f5e8a509ffe6a85cc3bc2863d00ca5bfb |
| demos_beta.json | abbe165d84a5c81bd0d9ef171aabaa4aa27ac3596c224f798f8fc8e82169b50e |
| family_gamma.json | 2a43a5dfc5537d06307a4f4bca2b91fd78c16d294b59e120a5eabc0608faa911 |
| demos_gamma.json | c09fd24b5f43582123b71ed2bee1f6486525d2ad9b9af8438727ace5e77d9995 |

| family | R1 | R2 mean steps / life | R3 | R4 stage-1 (random, 200k) | R4 stage-2 (random, 200k) | R5 | kinds / rules / latent vars |
|---|---|---|---|---|---|---|---|
| beta | pass | 797 | pass | 1,045 | 4 | pass | 5 / 6 / 2 |
| gamma | pass | 800 | pass | 696 | 19 | pass | 5 / 7 / 3 |

Per `PROTOCOL.md` §1 these files are read only after the candidate, the ablations and the judge's criteria are frozen
and that freeze is pushed; the hashes are checked again before reading.
