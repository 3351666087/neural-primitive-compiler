"""Candidates expected to be eliminated (pre-registered in hypotheses.md), and the boundary of the union schema.

  python mission-02/experiments/candidates/run_eliminated.py

E1 superposition binding  object map + value map instead of the product (object x value) code.
   (a) certificate: two reachable true states with the same superposition code but different answers
       (so NO read-out of that code is correct), for K, V in {2, 3}; plus a counting bound for any code;
   (b) a concrete superposition network, refuted by the differential judge.
E2 group-law shortcut     composite command "RIGHT then LEFT" built as the identity (offset arithmetic)
   versus the pullback composition; judged by the differential checker.
E3 non-union command      INVERT (complement): the learner rejects it; the IR vocabulary cannot express it.
"""

from __future__ import annotations

import itertools
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from cog.check import differential  # noqa: E402
from cog.ir import compile_ir  # noqa: E402
from cog.learn import learn  # noqa: E402
from cog.tasks import Letter, Task, family_a, family_b, grid_point_maps, pmap, run_reference, Output, grid  # noqa: E402

OUT = Path(__file__).parent / "eliminated.json"


def e1_certificate(K: int, V: int) -> dict:
    states = list(itertools.product([None] + list(range(V)), repeat=K))  # value of each object (None = empty)
    code = lambda s: (frozenset(k for k in range(K) if s[k] is not None), frozenset(v for v in s if v is not None))
    groups = {}
    for s in states:
        groups.setdefault(code(s), []).append(s)
    collision = None
    for c, members in groups.items():
        for a, b in itertools.combinations(members, 2):
            k = next((k for k in range(K) if a[k] != b[k]), None)
            if k is not None:
                collision = {"code": [sorted(c[0]), sorted(c[1])], "state_a": a, "state_b": b, "object_queried": k,
                             "answer_a": a[k], "answer_b": b[k]}
                break
        if collision:
            break
    # counting: any code that answers "value of object k" for every k must separate all (V+1)^K states
    return {"K": K, "V": V, "true_states": len(states), "distinct_superposition_codes": len(groups),
            "bits_needed_by_any_code": round(K * math.log2(V + 1), 2), "superposition_bits": K + V,
            "product_code_bits": K * V, "collision": collision}


def e1_network(K: int = 2, V: int = 2) -> dict:
    t = family_b(K, V, ["STORE"], queries=["value"], name="B_superposition")
    # superposition: OBJ (which objects hold something), VAL (which values are present), both union registers
    # on vec spaces; read-out: value v reported for object q iff q holds something and v is present.
    letters_obj = {f"STORE{k}": {"map": ["table", {f"{j}": ([["one"]] if j == k else [["c", f"{j}"]]) for j in range(K)}]}
                   for k in range(K)}
    letters_val = {f"STORE{k}": {"map": ["table", {f"{v}": [["c", f"{v}"], ["d", f"val_{v}"]] for v in range(V)}]}
                   for k in range(K)}
    prog = {"name": "superposition", "nodes": [
        {"id": "obj", "op": "CMR", "space": {"kind": "vec", "dims": [K]}, "letters": letters_obj},
        {"id": "vreg", "op": "CMR", "space": {"kind": "vec", "dims": [V]}, "letters": letters_val},
        {"id": "has", "op": "SEL", "of": "obj", "select": "qobj", "axis": "all", "delay": 2},
        {"id": "valueof", "op": "GATE", "pos": [["has", 1], ["vreg", 2]]}],
        "outputs": {"valueof": "valueof"}}
    net = compile_ir(prog, t.interface())
    t_q = family_b(K, V, ["STORE"], queries=["value"], name="B_superposition_q")
    t_q.outputs = [o for o in t_q.outputs if o.name == "valueof"]  # judge only the query answer
    d = differential(net, t_q, n=400, T=12, seed=11)
    return {"neurons": len(net.neurons), "differential_ok": d.ok, "failing_traces": d.detail.get("failing_traces"),
            "counterexample": d.counterexample}


def e2_group_shortcut(N: int = 4) -> dict:
    pm = grid_point_maps(N)
    sp = grid(N)
    t = family_a(N, ["RIGHT", "LEFT"], name="A_rl")
    def rl(S, f):
        return pmap(pm["LEFT"], sp.coords)(pmap(pm["RIGHT"], sp.coords)(S, f), f)
    t.letters.append(Letter("RL", rl))
    base = {"LOAD": {"map": ["load", "see"]}, "RIGHT": {"map": ["shift", 1, 0, "clip"]}, "LEFT": {"map": ["shift", -1, 0, "clip"]}}
    res = {}
    for label, m in (("shortcut: offsets cancel -> identity", ["id"]),
                     ("pullback composition", ["compose", ["shift", 1, 0, "clip"], ["shift", -1, 0, "clip"]])):
        prog = {"name": "rl", "nodes": [{"id": "mem", "op": "CMR", "letters": dict(base, RL={"map": m})}], "outputs": {"img": "mem"}}
        d = differential(compile_ir(prog, t.interface()), t, n=400, T=12, seed=12)
        res[label] = {"differential_ok": d.ok, "failing_traces": d.detail.get("failing_traces"), "counterexample": d.counterexample}
    return res


def e3_invert(N: int = 3) -> dict:
    t = family_a(N, ["ROT90"], name="A_invert")
    allc = frozenset(t.space.coords)
    t.letters.append(Letter("INVERT", lambda S, f: allc - S))
    L = learn(t.interface(), lambda tr, T: run_reference(t, tr, T), n_traces=300, T=16, seed=1)
    return {"learner_verdict_INVERT": L.letters["INVERT"] if isinstance(L.letters["INVERT"], str) else "union-table",
            "learner_verdict_ROT90": "union-table" if isinstance(L.letters["ROT90"], dict) else L.letters["ROT90"],
            "ir_vocabulary_has_complement": False}


def main():
    res = {"E1_certificate": [e1_certificate(K, V) for K, V in ((2, 2), (3, 3), (4, 4))],
           "E1_network": e1_network(), "E2_group_shortcut": e2_group_shortcut(), "E3_invert": e3_invert()}
    OUT.write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps(res, indent=1, default=str)[:4000])


if __name__ == "__main__":
    main()
