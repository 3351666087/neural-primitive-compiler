# ECO mechanism DSL (reference for mechanism authors)

A mechanism family is one JSON document interpreted by `eco_env.py` (judge side). Actors never see it. This file
describes exactly what the interpreter implements; anything not listed here is not supported.

## World

- Square grid of `size` (default 11) with border walls plus `interior_walls` random wall cells (default 6).
- One agent with a facing direction, at most one carried object, and two needs `food` and `water` (0..100, start 100,
  each decreases by 1 every 8 steps). When a need reaches 0 the agent is moved to a random free cell with both needs
  at 100 (a "life reset"); the world is unchanged.
- Actions: `N E S W` (turn to that direction and move one cell if the cell is free; a solid object or wall only turns
  the agent), `POKE` (the visible object in the facing cell), `PICK` (a visible pickable object in the facing cell, if
  the hand is empty), `DROP` (into the facing cell if it is free), `CONSUME` (the carried object, else a visible
  object in the facing cell, if it is consumable and its cooldown has passed), `WAIT`.
- Observation (all an actor gets): the 5x5 cells around the agent (wall flag, kind id of the visible object, values of
  its visible features), facing, carried kind id, needs, and the result code of the last action.

## Top-level keys

| key | meaning |
|---|---|
| `name`, `author` | strings |
| `interior_walls` | integer |
| `phase` | optional `{"every": T, "k": K}`: global phase `(t // T) % K`, readable with `["phase"]` |
| `kinds` | object: kind name -> kind spec |
| `placement` | object: kind name -> number of instances at the start |
| `placement_constraints` | list of `{"type": "near", "kind": A, "to": B, "dist": d, "count": n?, "target_offset": m?}`: the first n objects of kind A are moved to a free cell within Chebyshev distance d of objects of kind B (targets taken from the m-th onwards, cyclically) |
| `relations` | list of `{"kind": A, "name": R}`: objects of kind A are paired at random per seed; each stores its partner's id in latent `R` |
| `rules` | list of rules (below), evaluated in order |
| `nonstationarity` | list of `{"type": "reshuffle_relation", "kind": A, "name": R, "every": T}` (re-pairs every T steps) |

## Kind spec

| field | meaning |
|---|---|
| `solid` | blocks movement (default false) |
| `pickable` | can be carried (default false) |
| `visible_features` | list of feature names (integers, start 0), shown in the observation |
| `latent` | object: var -> `{"domain": [...], "init": v}`; never shown |
| `consumable` | `{"need": "food" or "water", "amount": n, "cooldown": c?, "vanish": bool?}` |
| `visibility` | `"always"` (default) or `"revealed"` (visible only while `t <= revealed_until`, set by a `reveal` effect) |

## Rules

`{"on": EVENT, "kind": K, "guard": EXPR?, "effects": [EFFECT, ...], "exclusive": bool?}`

- EVENT is `poke`, `pick`, `drop`, `consume` (fired on the object acted upon) or `tick` (fired for every object
  every step, after the action).
- For one (event, object), the first rule whose guard holds fires; with `"exclusive": false` evaluation continues.
- Inside a rule, `self` is the object.

## Expressions

| form | value |
|---|---|
| number, `true`, `false` | constant |
| `["latent", REF, var]`, `["visible", REF, feature]` | value of a latent variable / visible feature of the referenced object |
| `["==", a, b]` and `!=`, `<`, `<=`, `>`, `>=` | comparison (false if an operand is missing) |
| `["and", ...]`, `["or", ...]`, `["not", e]` | logic |
| `["exists_near", K, d, WHERE?]` | some other object of kind K within Chebyshev distance d of `self` (WHERE may use `"it"`) |
| `["since", name]` | steps since `self` last executed `["mark", name]` (very large if never) |
| `["chance", p]` | Bernoulli(p) from the world's seeded generator |
| `["phase"]` | global phase |

REF is `"self"`, `"it"`, `["related", R]` (the partner stored in latent R) or `["nearest", K, d, WHERE?]`.

## Effects

| form | effect |
|---|---|
| `["set", REF, var, EXPR]` | set a latent variable |
| `["inc", REF, var, delta, lo, hi]` | add delta, clipped to [lo, hi] |
| `["set_visible", REF, feature, value]` | set a visible feature |
| `["spawn", K, REF, d]` | create a new object of kind K at a random free cell within distance d of REF |
| `["reveal", K, d, duration]` | make every object of kind K within distance d of `self` visible for `duration` steps |
| `["mark", name]` | remember the current time on `self` (for `since`) |
| `["delay", steps, EFFECT]` | apply EFFECT after `steps` (same `self`) |
| `["log", name]` | write a judge-only event (used to verify mechanisms; never shown to actors) |
