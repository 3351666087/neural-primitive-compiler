"""G4b constructors (EXPERIMENT_PRE_REGISTRATION.md section G4b). CONSTRUCTOR SIDE: input is the goal atoms (a goal-level
logical specification, task brief section 3) and the legal observations; nothing else.

  CMP-0   the frozen composition law: A-P over the kind-level preservation table of G2 (alf_core.construct)
  CMP-1   A-P with two added contract relations, developed on development rooms only:
            (i)  object-indexed preservation: treating an object disturbs only that object's placement; any achiever
                 that walks away disturbs LIT; any achiever that fetches another object disturbs HOLDING;
            (ii) applicability preservation for the hand (ALFWorld agents hold one object): an achiever that starts by
                 fetching object type T needs the hand empty or already holding T; TREAT(T) and HOLDING(T) end
                 holding T, IN(T) ends with an empty hand, LIT leaves the hand unchanged.
          An order is accepted when every later achiever preserves every earlier atom (i) and the hand chain is
          applicable (ii).
  SEQ     same-knowledge classical method (designer-written, no contract reasoning): objects one at a time in the
          order the goal lists them, treatment before placement; the object to hold and the lamp last.
All three run on the same executor: the G3-LPR agent (L_co, P_loc, literal monitors, recovery) and the priority loop.
"""

import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "g2"))
import alf_core as C  # noqa: E402

TREAT = ("CLEAN", "HEAT", "COOL")
FETCHES = ("IN", "IN2", "CLEAN", "HEAT", "COOL", "HOLDING")


def construct_frozen(atoms):
    return C.construct([tuple(a) for a in atoms])


def preserves1(later, earlier):
    """(i) object-indexed: does the achiever of `later` keep `earlier` true?"""
    kl, Tl, _ = later
    ke, Te, _ = earlier
    if ke == "LIT":
        return kl == "LIT"                       # every other achiever walks away from the lamp
    if ke == "HOLDING":
        return kl == "LIT" or (kl in FETCHES and Tl == Te)
    if ke == "IN":
        return not (kl in TREAT and Tl == Te)    # treating takes that object out of its receptacle
    return True                                  # CLEAN / HEAT / COOL flags are never undone


def hand_after(atom, hand):
    k, T, _ = atom
    if k in TREAT or k == "HOLDING":
        return T
    if k in ("IN", "IN2"):
        return None
    return hand


def hand_ok(atom, hand):
    k, T, _ = atom
    return k not in FETCHES or hand is None or hand == T


def construct_upgraded(atoms):
    atoms = [tuple(a) for a in atoms]
    if not atoms:
        return None, "goal not parsed"
    for perm in itertools.permutations(atoms):
        if not all(preserves1(perm[j], perm[i]) for j in range(len(perm)) for i in range(j)):
            continue
        hand, ok = None, True
        for a in perm:
            if not hand_ok(a, hand):
                ok = False
                break
            hand = hand_after(a, hand)
        if ok:
            return list(perm), None
    return None, "no order satisfies preservation and hand applicability"


def seq_method(atoms):
    """Classical method: group by object type in the listed order; treatment, then placement; holding and lamp last."""
    atoms = [tuple(a) for a in atoms]
    types = []
    for a in atoms:
        if a[0] != "LIT" and a[1] not in types:
            types.append(a[1])
    hold = [a for a in atoms if a[0] == "HOLDING"]
    order = []
    for T in types:
        if any(a[0] == "HOLDING" and a[1] == T for a in atoms):
            continue
        order += [a for a in atoms if a[1] == T and a[0] in TREAT] + [a for a in atoms if a[1] == T and a[0] == "IN"]
    order += hold + [a for a in atoms if a[0] == "LIT"]
    return order, None
