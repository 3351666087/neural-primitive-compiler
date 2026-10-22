"""Mechanical C2 / C3 determination for a held-out family (JUDGE SIDE; PROTOCOL.md section 6.5 with amendment A2
item 4). Run only after the candidate, ablations and criteria are frozen and pushed, and after the family file's
SHA-256 matches CUSTODY.md.

Rule (A2 item 4): C2 (C3) is the latent variable read or written by the rules that log a stage-1 (stage-2) event;
if several, the one appearing in the guard (first in guard order) is taken, else the first one written by the
effects. The kind of a latent reference is the rule's kind for "self", K for ["nearest", K, ...] and for "it" inside
["exists_near", K, ...]; ["related", R] refers to the relation partner (kind from the relations list).
  python3 -I heldout_classes.py FAMILY.json DEMOS.json      # prints JSON {"C2": "LATENT:kind.var", "C3": ...}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _latents(expr, self_kind, fam, it_kind=None, out=None):
    """Latent (kind, var) references in an expression, in order."""
    out = [] if out is None else out
    if not isinstance(expr, list) or not expr:
        return out
    op = expr[0]
    if op == "latent":
        ref, var = expr[1], expr[2]
        out.append((_ref_kind(ref, self_kind, fam, it_kind), var))
        return out
    if op == "exists_near":
        K = expr[1]
        if len(expr) > 3:
            _latents(expr[3], self_kind, fam, it_kind=K, out=out)
        return out
    for x in expr[1:]:
        if isinstance(x, list):
            _latents(x, self_kind, fam, it_kind, out)
    return out


def _ref_kind(ref, self_kind, fam, it_kind):
    if ref == "self":
        return self_kind
    if ref == "it":
        return it_kind
    if isinstance(ref, list) and ref and ref[0] == "nearest":
        return ref[1]
    if isinstance(ref, list) and ref and ref[0] == "related":
        for r in fam.get("relations", []):
            if r["name"] == ref[1]:
                return r["kind"]
    return None


def _effect_latents(eff, self_kind, fam):
    out = []
    if not isinstance(eff, list) or not eff:
        return out
    if eff[0] in ("set", "inc"):
        out.append((_ref_kind(eff[1], self_kind, fam, None), eff[2]))
    if eff[0] == "delay":
        out += _effect_latents(eff[2], self_kind, fam)
    for x in eff[1:]:
        if isinstance(x, list) and x and x[0] in ("nearest",):
            for y in x[3:] if len(x) > 3 else []:
                out += _latents(y, self_kind, fam, it_kind=x[1])
    return out


def logs_of(eff):
    if not isinstance(eff, list) or not eff:
        return []
    if eff[0] == "log":
        return [eff[1]]
    if eff[0] == "delay":
        return logs_of(eff[2])
    return []


def class_for(fam, events):
    guard_l, eff_l = [], []
    for rule in fam["rules"]:
        names = [n for e in rule["effects"] for n in logs_of(e)]
        if not any(n in events for n in names):
            continue
        K = rule["kind"]
        if "guard" in rule:
            guard_l += _latents(rule["guard"], K, fam)
        for e in rule["effects"]:
            eff_l += _effect_latents(e, K, fam)
    pick = next((x for x in guard_l if x[0]), None) or next((x for x in eff_l if x[0]), None)
    return (f"LATENT:{pick[0]}.{pick[1]}" if pick else None), {"guard": guard_l, "effects": eff_l}


def main(fam_path, demos_path):
    fam = json.loads(Path(fam_path).read_text())
    demos = json.loads(Path(demos_path).read_text())
    c2, d2 = class_for(fam, set(demos["stage1_events"]))
    c3, d3 = class_for(fam, set(demos["stage2_events"]))
    return {"C2": c2, "C3": c3, "stage1_events": demos["stage1_events"], "stage2_events": demos["stage2_events"],
            "candidates_C2": d2, "candidates_C3": d3}


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1], sys.argv[2]), indent=1, default=str))
