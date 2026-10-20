# Unseen tasks (strict route A)

| task | family | params | A-auto | A-LLM | random structure (img only) | one-hot FSM neurons (by size) |
|---|---|---|---|---|---|---|
| UA0 | A | `{"commands": [["CMD0", ["DOWN", "ROT90"]], ["CMD1", ["ROT180"]], ["CMD2", ["FLIPH", "RIGHTWRAP"]]], "queries": [], "cond` | FAIL conditional command CMD3: data-dependent, outside the union schema (needs a gate | OK 3:ok, 5:ok, 8:ok | 0/100 | 2.65e+05, 1.13e+15, 3.4e+38 |
| UA1 | A | `{"commands": [["CMD0", ["LEFT"]], ["CMD1", ["LEFT"]], ["CMD2", ["DOWN"]]], "queries": [], "cond": null}` | OK 3:45n, 5:135n, 8:360n | OK 3:ok, 5:ok, 8:ok | 0/100 | 2.64e+05, 1.13e+15, 3.4e+38 |
| UA2 | A | `{"commands": [["CMD0", ["ROT270", "ROT270"]], ["CMD1", ["TRANSPOSE"]], ["CMD2", ["DILATE", "LEFT"]], ["CMD3", ["ROT270",` | FAIL conditional command CMD4: data-dependent, outside the union schema (needs a gate | OK 3:ok, 5:ok, 8:ok | 0/100 | 2.65e+05, 1.13e+15, 3.4e+38 |
| UA3 | A | `{"commands": [["CMD0", ["ROT90", "TRANSPOSE"]], ["CMD1", ["UP", "FLIPH"]], ["CMD2", ["DOWN"]]], "queries": ["all"], "con` | FAIL conditional command CMD3: data-dependent, outside the union schema (needs a gate | OK 3:ok, 5:ok, 8:ok | 0/100 | 2.65e+05, 1.13e+15, 3.4e+38 |
| UA4 | A | `{"commands": [["CMD0", ["ROT270", "TRANSPOSE"]], ["CMD1", ["ROT180"]], ["CMD2", ["UP", "RIGHT"]], ["CMD3", ["RIGHT"]]], ` | FAIL conditional command CMD4: data-dependent, outside the union schema (needs a gate | OK 3:ok, 5:ok, 8:ok | 0/100 | 2.65e+05, 1.13e+15, 3.4e+38 |
| UA5 | A | `{"commands": [["CMD0", ["TRANSPOSE", "FLIPH"]], ["CMD1", ["DILATE", "DOWN"]], ["CMD2", ["FLIPV"]], ["CMD3", ["TRANSPOSE"` | OK 3:60n, 5:170n, 8:440n | OK 3:ok, 5:ok, 8:ok | 0/100 | 2.65e+05, 1.13e+15, 3.4e+38 |
| UA6 | A | `{"commands": [["CMD0", ["TRANSPOSE"]], ["CMD1", ["UP"]]], "queries": ["bottom"], "cond": null}` | OK 3:43n, 5:121n, 8:313n | OK 3:ok, 5:ok, 8:ok | 0/100 | 2.64e+05, 1.13e+15, 3.4e+38 |
| UA7 | A | `{"commands": [["CMD0", ["LEFT", "FLIPH"]], ["CMD1", ["ROT270"]]], "queries": ["left"], "cond": null}` | OK 3:43n, 5:121n, 8:313n | OK 3:ok, 5:ok, 8:ok | 0/100 | 2.64e+05, 1.13e+15, 3.4e+38 |
| UB0 | B | `{"ops": ["STORE", "SWAP"], "queries": ["same"]}` | FAIL output same: not a disjunction of coordinates or selector-gated coordinates | OK (2, 2):ok, (4, 3):ok | 0/100 | 54, 4.86e+03 |
| UB1 | B | `{"ops": ["STORE", "COPY"], "queries": ["same"]}` | FAIL output same: not a disjunction of coordinates or selector-gated coordinates | OK (2, 3):ok, (4, 4):ok | 0/100 | 144, 1.81e+04 |
| UB2 | B | `{"ops": ["STORE", "CLEAR"], "queries": ["who"]}` | OK (3, 3):75n, (5, 4):245n | OK (3, 3):ok, (5, 4):ok | 0/100 | 832, 8.12e+04 |
| UB3 | B | `{"ops": ["STORE", "SWAP"], "queries": ["value", "who"]}` | OK (3, 3):96n, (5, 4):389n | OK (3, 3):ok, (5, 4):ok | 0/100 | 832, 9.69e+04 |
| UAB0 | AB | `{"cmds": ["ROT270", "ROT90"], "queries": []}` | OK (2, 3):144n, (3, 5):825n | OK (2, 3):ok, (3, 5):ok | 0/100 | 2.7e+08, 3.8e+30 |
| UAB1 | AB | `{"cmds": ["FLIPH"], "queries": ["toptouch"]}` | OK (2, 3):110n, (3, 5):603n | OK (2, 3):ok, (3, 5):ok | 0/100 | 2.69e+08, 3.8e+30 |
| UAB2 | AB | `{"cmds": ["RIGHT"], "queries": ["toptouch"]}` | OK (2, 3):104n, (3, 5):588n | OK (2, 3):ok, (3, 5):ok | 0/100 | 2.69e+08, 3.8e+30 |
| UAB3 | AB | `{"cmds": ["LEFT"], "queries": []}` | OK (2, 3):102n, (3, 5):585n | OK (2, 3):ok, (3, 5):ok | 0/100 | 2.69e+08, 3.8e+30 |
