"""Phase 2 discovery study (design tasks only; fixed before any unseen task exists).

  python mission-02/experiments/discovery/run_discovery.py

1. Black-box learning of every (letter, coordinate) update rule and every query output on the design tasks.
2. Rule-shape statistics and cross-family reuse (anti-unification target: M'_j = OR(Src(j))).
3. Parametrization: which learned tables coincide, at every probed size, with one vocabulary map.
4. Description length: flat FSM vs learned union tables vs parametric program.
Raw output: discovery.json; summary: DISCOVERY.md.
"""

from __future__ import annotations

import json
import math
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from cog.check import differential  # noqa: E402
from cog.ir import compile_ir  # noqa: E402
from cog.learn import active_refine, learn, match_vocab, recheck, to_ir  # noqa: E402
from cog.tasks import Letter, family_a, family_b, run_reference  # noqa: E402

OUT = Path(__file__).parent


def design_tasks():
    tasks = []
    for N in (2, 3, 4):
        tasks.append(family_a(N, ["ROT90", "FLIPH", "RIGHT", "DILATE"], queries=["top", "cell"], name=f"A{N}"))
    for K, V in ((2, 2), (3, 3)):
        tasks.append(family_b(K, V, ["STORE", "SWAP", "COPY", "CLEAR"], queries=["value", "who", "same"], name=f"B{K}x{V}"))
    t = family_a(3, ["ROT90", "FLIPV"], queries=["top"], cond=("COND", "top", "FLIPV", "ROT90", 3), name="A3cond")
    tasks.append(t)
    inv = family_a(3, ["ROT90"], name="A3invert")  # negative control: complement is not a union of sources
    allc = frozenset(inv.space.coords)
    inv.letters.append(Letter("INVERT", lambda S, f, allc=allc: allc - S))
    tasks.append(inv)
    return tasks


def shape(srcs) -> str:
    if not srcs:
        return "zero"
    kinds = Counter(s[0] for s in srcs)
    if srcs == [("one",)]:
        return "one"
    if len(srcs) == 1:
        return "copy" if kinds["c"] else "load"
    return "union"


def relation_class(tab: dict) -> str:
    """Classify a letter's source relation."""
    srcs = [s for v in tab.values() for s in v if s[0] == "c"]
    if any(s[0] in ("d", "one") for v in tab.values() for s in v):
        return "load/mixed"
    if all(len(v) == 1 for v in tab.values()) and len(set(srcs)) == len(srcs) == len(tab):
        return "permutation"
    if all(len(v) <= 1 for v in tab.values()):
        return "partial-map" if len(set(srcs)) == len(srcs) else "many-to-one map"
    return "relation (union)"


def flat_fsm_bits(task) -> float:
    if task.space.kind == "grid":
        states = 2 ** len(task.space.coords)
    else:
        K, V = task.space.dims
        states = (V + 1) ** K
    frames = 1 + sum((2 ** len(task.data[l.data].coords) if (l.data and task.data[l.data].kind != "vec")
                      else (len(task.data[l.data].coords) if l.data else 1)) for l in task.letters)
    return states * frames * math.log2(states)


def main():
    rows = []
    shapes = Counter()
    shapes_by_family = {"A": Counter(), "B": Counter()}
    rel_by_family = {"A": Counter(), "B": Counter()}
    out_shapes = Counter()
    tables_by_letter = {}
    for task in design_tasks():
        iface = task.interface()
        orc = lambda tr, T, task=task: run_reference(task, tr, T)
        # passive learning only (recorded: it can overgeneralize)
        Lp = learn(iface, orc, n_traces=300, T=16, seed=1)
        prog_p = to_ir(iface, Lp)
        passive_ok = differential(compile_ir(prog_p, iface), task, n=400, T=14, seed=9).ok if prog_p else None
        t0 = time.perf_counter()
        L = learn(iface, orc, n_traces=300, T=16, seed=1)
        L = active_refine(iface, orc, L)
        rechecked = recheck(iface, orc, L)
        dt = time.perf_counter() - t0
        prog = to_ir(iface, L)
        active_ok = differential(compile_ir(prog, iface), task, n=400, T=14, seed=9).ok if prog else None
        row = {"task": task.name, "family": task.family, "coords": len(task.space.coords), "letters": {},
               "outputs": {}, "observations": L.observations, "active_probes": getattr(L, "probes", 0),
               "learn_time_s": round(dt, 3), "passive_construction_correct": passive_ok,
               "active_construction_correct": active_ok, "recheck_nonlinear": rechecked, "notes": L.notes}
        union_bits = 0.0
        nfeat = len(task.space.coords) + max((len(task.data[l.data].coords) for l in task.letters if l.data), default=0) + 1
        for lname, tab in L.letters.items():
            if isinstance(tab, str):
                row["letters"][lname] = tab
                shapes[tab] += 1
                shapes_by_family[task.family][tab] += 1
                continue
            sh = Counter(shape(v) for v in tab.values())
            rc = relation_class(tab)
            row["letters"][lname] = {"rule_shapes": dict(sh), "relation": rc}
            for k, v in sh.items():
                shapes[k] += v
                shapes_by_family[task.family][k] += v
            rel_by_family[task.family][rc] += 1
            union_bits += sum(1 + len(v) * math.log2(nfeat) for v in tab.values())
            base = lname.rstrip("0123456789")
            tables_by_letter.setdefault((task.family, lname), []).append((task, tab))
        for oname, st in L.outputs.items():
            kinds = sorted({(v if isinstance(v, str) else v[0]) for v in st.values()})
            row["outputs"][oname] = kinds
            for k in kinds:
                out_shapes[k] += 1
        row["description_bits"] = {"flat_fsm": round(flat_fsm_bits(task)), "union_tables": round(union_bits)}
        rows.append(row)
        print(json.dumps({k: row[k] for k in ("task", "letters", "outputs", "description_bits")})[:600], flush=True)

    # parametrization across sizes (family A letters on A2, A3, A4; family B on B2x2, B3x3)
    param = {}
    for (fam, lname), lst in sorted(tables_by_letter.items(), key=lambda x: x[0]):
        per_size = []
        for task, tab in lst:
            sp = {"kind": task.space.kind, "dims": list(task.space.dims)}
            data = [l.data for l in task.letters if l.name == lname and l.data]
            per_size.append({repr(m) for m in match_vocab(tab, sp, data)})
        common = set.intersection(*per_size) if per_size else set()
        param[f"{fam}:{lname}"] = {"sizes": [t.name for t, _ in lst], "vocabulary_matches_at_every_size": sorted(common)}
    total_rules = sum(v for k, v in shapes.items() if k not in ("nonlinear", "unobserved"))
    union_cov = total_rules / max(1, total_rules + shapes["nonlinear"] * 1.0)
    summary = {
        "rule_shapes_all": dict(shapes), "rule_shapes_by_family": {k: dict(v) for k, v in shapes_by_family.items()},
        "letter_relation_classes_by_family": {k: dict(v) for k, v in rel_by_family.items()},
        "output_shapes": dict(out_shapes),
        "letters_nonlinear": [(r["task"], l) for r in rows for l, v in r["letters"].items() if v == "nonlinear"],
        "outputs_nonlinear": [(r["task"], o) for r in rows for o, v in r["outputs"].items() if "nonlinear" in v],
        "union_template_coverage_letters": f"{total_rules} coordinate rules fit; {shapes['nonlinear']} letters do not",
    }
    (OUT / "discovery.json").write_text(json.dumps({"rows": rows, "parametrization": param, "summary": summary}, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))
    print(json.dumps(param, indent=1)[:3000])


if __name__ == "__main__":
    main()
