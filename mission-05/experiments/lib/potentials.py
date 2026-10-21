"""Potential templates and their damage tables (protocol amendment 2). CONSTRUCTOR SIDE.

Templates (role-parametrised, goal-independent):
  KD(R)        number of violated ordered pairs w.r.t. a strict partial order R on colours (sum of INV over R)
  OUT(p,s,w)   objects of colour p outside zone (s, w)
  OOW(p,Gv)    objects of colour p outside the window of GROUP variant Gv
A pattern key names a template with colours replaced by roles (A1, A2 = the achiever's colours, X1, X2 = others).
"""

from __future__ import annotations

import itertools

from model import group_window, rc, zcells

ROLES3 = {"ORDER": ("A1", "A2", "X1"), "ZONE": ("A1", "X1", "X2"), "GROUP": ("A1", "X1", "X2")}


def kd(cells, pairs, b):
    tot = 0
    for lo, hi in pairs:
        lo, hi = rc(lo, b), rc(hi, b)
        seen_hi = 0
        for x in cells:
            if x == hi:
                seen_hi += 1
            elif x == lo:
                tot += seen_hi
    return tot


def out(cells, c, side, w, b):
    c = rc(c, b)
    z = set(zcells(len(cells), side, w))
    return sum(1 for p, x in enumerate(cells) if x == c and p not in z)


def oow(cells, c, variant, haz, rule, fixed, b):
    win = group_window(["GROUP", c], cells, b, haz, rule, fixed, variant)
    cc = rc(c, b)
    if win is None:
        return 0
    return sum(1 for p, x in enumerate(cells) if x == cc and p not in win)


def strict_partial_orders(elems):
    """All non-empty strict partial orders on `elems` (transitive, irreflexive, antisymmetric)."""
    pairs = [(a, c) for a in elems for c in elems if a != c]
    out_ = []
    for r in range(1, len(pairs) + 1):
        for S in itertools.combinations(pairs, r):
            s = set(S)
            if any((c, a) in s for a, c in s):
                continue
            if any((a, d) not in s for a, c in s for c2, d in s if c == c2 and a != d):
                continue
            out_.append(tuple(sorted(s)))
    return out_


def kd_key(pairs):
    return "KD{" + ";".join(f"{a}<{c}" for a, c in sorted(pairs)) + "}"


def patterns(atype):
    roles = ROLES3[atype]
    keys = [kd_key(p) for p in strict_partial_orders(roles)]
    keys += [f"OUT({p},{s},{w})" for p in roles for s in ("left", "right") for w in (2, "half")]
    keys += [f"OOW({p},{v})" for p in roles for v in ("G1", "G2")]
    return keys


def evaluate(key, cells, haz, rule, fixed, b):
    if key.startswith("KD{"):
        pairs = [tuple(x.split("<")) for x in key[3:-1].split(";")]
        return kd(cells, pairs, b)
    t, rest = key.split("(", 1)
    args = rest[:-1].split(",")
    if t == "OUT":
        return out(cells, args[0], args[1], args[2] if args[2] == "half" else int(args[2]), b)
    return oow(cells, args[0], args[1], haz, rule, fixed, b)


def closure(orders):
    """Transitive closure of a set of (lo, hi) pairs; None if it has a cycle."""
    s = set(orders)
    changed = True
    while changed:
        changed = False
        for a, c in list(s):
            for c2, d in list(s):
                if c == c2 and (a, d) not in s:
                    s.add((a, d))
                    changed = True
    if any(a == c for a, c in s) or any((c, a) in s for a, c in s):
        return None
    return sorted(s)


def roles_for(ach_atom, colours, fixed):
    """Map goal colours to roles relative to an achiever atom (A1, A2; others X1, X2; a NO_PICK colour is X2)."""
    roles = {ach_atom[1]: "A1"}
    if ach_atom[0] == "ORDER":
        roles[ach_atom[2]] = "A2"
    for c in fixed:
        if c not in roles:
            roles[c] = "X2"
    free = [x for x in ("X1", "X2") if x not in roles.values()]
    for c in colours:
        if c not in roles:
            if not free:
                return None
            roles[c] = free.pop(0)
    return roles


def template_key(tmpl, roles):
    """tmpl: ("KD", pairs) | ("OUT", c, side, w) | ("OOW", c, variant) with goal colours -> pattern key."""
    if tmpl[0] == "KD":
        return kd_key([(roles[a], roles[c]) for a, c in tmpl[1]])
    if tmpl[0] == "OUT":
        return f"OUT({roles[tmpl[1]]},{tmpl[2]},{tmpl[3]})"
    return f"OOW({roles[tmpl[1]]},{tmpl[2]})"


def template_max(tmpl, K):
    if tmpl[0] == "KD":
        return (K * K) // 3 if len(tmpl[1]) > 1 else (K * K) // 4
    return K
