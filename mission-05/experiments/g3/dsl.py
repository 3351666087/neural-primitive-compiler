"""ACH-DSL: the declared language for achiever variants (G3). CONSTRUCTOR SIDE (also used by the G3 truth tables).

An achiever spec chooses, in a state where its atom is violated, a destination cell d and a source cell s; the fixed
relocation macro RELOC(d, s) then exchanges their contents (the object at s moves to d; an object at d, if any, ends
at s through the spare cell). Spec (JSON):
  {"id": str, "atom_type": "ORDER" | "ZONE" | "GROUP", "side": "left" | "right" | "any"  (ZONE only; default any),
   "dest":   {"types": [...], "region": REGION, "pick": PICK},
   "source": {"types": ["OWN"], "region": REGION, "pick": PICK | "nearest_to_dest"}}
Cell types, relative to the atom: OWN = the atom's (first) colour; PARTNER = the second colour of an ORDER atom;
OTHER = any other object that may be picked up (not NO_PICK); EMPTY = an empty cell an object may be dropped on
(not a hazard when the hazard rule is on). dest types are a non-empty subset of {EMPTY, PARTNER, OTHER}
(PARTNER only for ORDER); source types are exactly ["OWN"].
REGION: "ALL" | "ZONE" | "NOT_ZONE" (ZONE atoms) | "WINDOW_G1" | "NOT_WINDOW_G1" | "WINDOW_G2" | "NOT_WINDOW_G2"
  (the leftmost / rightmost run of free cells, of length = number of OWN objects, in which OWN can be grouped:
  every cell is neither a hazard (rule on) nor a NO_PICK object of another colour) | "LEFT_OF_DEST" |
  "RIGHT_OF_DEST" (source only) | {"within": k, "of": "DEST"} (source only, 1 <= k <= 3: |p - d| <= k) |
  {"and": [REGION, REGION]} (nesting depth <= 2).
PICK: "leftmost" | "rightmost" | "second_leftmost" | "second_rightmost"; the source may also use "nearest_to_dest"
  (smallest |p - d|, ties to the left).
The achiever is not applicable (no move) if a rule finds no cell, or if an atom colour is a NO_PICK colour.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))
from model import group_window, rc, zcells  # noqa: E402

TYPES = ("EMPTY", "PARTNER", "OTHER", "OWN")
BASE_REGIONS = ("ALL", "ZONE", "NOT_ZONE", "WINDOW_G1", "NOT_WINDOW_G1", "WINDOW_G2", "NOT_WINDOW_G2")
REL_REGIONS = ("LEFT_OF_DEST", "RIGHT_OF_DEST")
PICKS = ("leftmost", "rightmost", "second_leftmost", "second_rightmost")


# ------------------------------------------------------------------ validation
def _region_ok(r, atom_type, is_source, depth=0):
    if isinstance(r, str):
        if r in ("ZONE", "NOT_ZONE"):
            return atom_type == "ZONE"
        if r in REL_REGIONS:
            return is_source
        return r in BASE_REGIONS
    if isinstance(r, dict) and set(r) == {"within", "of"}:
        return is_source and r["of"] == "DEST" and isinstance(r["within"], int) and 1 <= r["within"] <= 3
    if isinstance(r, dict) and set(r) == {"and"}:
        return (depth < 2 and isinstance(r["and"], list) and len(r["and"]) == 2
                and all(_region_ok(x, atom_type, is_source, depth + 1) for x in r["and"]))
    return False


def validate(spec):
    """Returns a list of problems (empty = valid)."""
    p = []
    if not isinstance(spec, dict):
        return ["not an object"]
    if not isinstance(spec.get("id"), str) or not spec["id"]:
        p.append("id")
    t = spec.get("atom_type")
    if t not in ("ORDER", "ZONE", "GROUP"):
        return p + ["atom_type"]
    if spec.get("side", "any") not in ("left", "right", "any") or ("side" in spec and t != "ZONE"):
        p.append("side")
    extra = set(spec) - {"id", "atom_type", "side", "dest", "source", "note"}
    if extra:
        p.append(f"unknown fields {sorted(extra)}")
    for role in ("dest", "source"):
        r = spec.get(role)
        if not isinstance(r, dict) or set(r) != {"types", "region", "pick"}:
            p.append(f"{role} fields")
            continue
        ty = r["types"]
        if role == "dest":
            allowed = {"EMPTY", "OTHER"} | ({"PARTNER"} if t == "ORDER" else set())
            if not isinstance(ty, list) or not ty or not set(ty) <= allowed or len(set(ty)) != len(ty):
                p.append("dest types")
            if r["pick"] not in PICKS:
                p.append("dest pick")
        else:
            if ty != ["OWN"]:
                p.append("source types")
            if r["pick"] not in PICKS + ("nearest_to_dest",):
                p.append("source pick")
        if not _region_ok(r["region"], t, role == "source"):
            p.append(f"{role} region")
    return p


def in_b_grammar(spec):
    """Is the spec inside B-RULE's rule grammar (single region available to B for this atom type; leftmost or
    rightmost)? Types are always expressible in B's seven cell types."""
    t = spec["atom_type"]
    base = {"ORDER": ("ALL",), "ZONE": ("ALL", "ZONE", "NOT_ZONE"),
            "GROUP": ("ALL", "WINDOW_G1", "NOT_WINDOW_G1", "WINDOW_G2", "NOT_WINDOW_G2")}[t]
    for role in ("dest", "source"):
        r = spec[role]
        if r["pick"] not in ("leftmost", "rightmost"):
            return False
        ok = base + (REL_REGIONS if role == "source" else ())
        if not (isinstance(r["region"], str) and r["region"] in ok):
            return False
    return True


# ------------------------------------------------------------------ instances
def instances(spec):
    """The atom instances (with role colours A1 = 1, A2 = 2) a spec applies to, as (key, atom)."""
    t = spec["atom_type"]
    if t == "ORDER":
        return [(spec["id"], ["ORDER", "A1", "A2"])]
    if t == "GROUP":
        return [(spec["id"], ["GROUP", "A1"])]
    sides = ("left", "right") if spec.get("side", "any") == "any" else (spec["side"],)
    return [(f"{spec['id']}|{s}|{w}", ["ZONE", "A1", s, w]) for s in sides for w in (2, "half")]


def applies_to(spec, atom):
    if spec["atom_type"] != atom[0]:
        return False
    return atom[0] != "ZONE" or spec.get("side", "any") in ("any", atom[2])


def ach_key(spec, atom):
    return f"{spec['id']}|{atom[2]}|{atom[3]}" if atom[0] == "ZONE" else spec["id"]


# ------------------------------------------------------------------ interpreter
def cell_types(atom, cells, haz, rule, fixedcols, b):
    c1 = rc(atom[1], b)
    c2 = rc(atom[2], b) if atom[0] == "ORDER" else None
    out = []
    for p, c in enumerate(cells):
        if c == 0:
            out.append("EMPTY" if not (rule and haz[p]) else "HAZARD")
        elif c == c1:
            out.append("OWN")
        elif c == c2:
            out.append("PARTNER")
        elif c in fixedcols:
            out.append("FIXED")
        else:
            out.append("OTHER")
    return out


def region_mask(r, atom, cells, haz, rule, fixedcols, b, d=None, cache=None):
    N = len(cells)
    if isinstance(r, dict):
        if "and" in r:
            m1 = region_mask(r["and"][0], atom, cells, haz, rule, fixedcols, b, d, cache)
            m2 = region_mask(r["and"][1], atom, cells, haz, rule, fixedcols, b, d, cache)
            return [x and y for x, y in zip(m1, m2)]
        return [abs(p - d) <= r["within"] for p in range(N)]
    if r == "ALL":
        return [True] * N
    if r in ("ZONE", "NOT_ZONE"):
        z = set(zcells(N, atom[2], atom[3]))
        return [(p in z) == (r == "ZONE") for p in range(N)]
    if r in REL_REGIONS:
        return [p < d for p in range(N)] if r == "LEFT_OF_DEST" else [p > d for p in range(N)]
    v = "G1" if r.endswith("G1") else "G2"
    key = ("W", v)
    if cache is None or key not in cache:
        w = group_window(["GROUP", atom[1]], cells, b, haz, rule, fixedcols, v)
        w = w or set()
        if cache is not None:
            cache[key] = w
    else:
        w = cache[key]
    inside = not r.startswith("NOT_")
    return [(p in w) == inside for p in range(N)]


def pick_cell(cands, pick, d=None):
    if not cands:
        return None
    if pick == "leftmost":
        return cands[0]
    if pick == "rightmost":
        return cands[-1]
    if pick == "second_leftmost":
        return cands[1] if len(cands) > 1 else None
    if pick == "second_rightmost":
        return cands[-2] if len(cands) > 1 else None
    return min(cands, key=lambda p: (abs(p - d), p))                       # nearest_to_dest, ties to the left


def select_dsl(spec, atom, cells, haz, rule, fixedcols, b):
    """(d, s) or None. Mirrors cir_dsl.selection exactly."""
    c1 = rc(atom[1], b)
    if c1 in fixedcols or (atom[0] == "ORDER" and rc(atom[2], b) in fixedcols):
        return None
    ty = cell_types(atom, cells, haz, rule, fixedcols, b)
    cache = {}
    rd = spec["dest"]
    md = region_mask(rd["region"], atom, cells, haz, rule, fixedcols, b, cache=cache)
    d = pick_cell([p for p in range(len(cells)) if md[p] and ty[p] in rd["types"]], rd["pick"])
    if d is None:
        return None
    rs = spec["source"]
    ms = region_mask(rs["region"], atom, cells, haz, rule, fixedcols, b, d=d, cache=cache)
    s = pick_cell([p for p in range(len(cells)) if ms[p] and ty[p] == "OWN"], rs["pick"], d)
    if s is None:
        return None
    return d, s


def make_select(spec):
    """A function with model.select's signature (atom, variant, cells, haz, rule, fixedcols, b) -> (x, y) | None."""
    return lambda atom, _v, cells, haz, rule, fixedcols, b: select_dsl(spec, atom, cells, haz, rule, fixedcols, b)
