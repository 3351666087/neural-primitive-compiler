"""WorkArena++ development / held-out split (Mission 06, EXPERIMENT_PRE_REGISTRATION.md section G1-S).

Run ONLY by the custodian session (D5), in its own empty folder, with the pinned interpreter:
    HF_HUB_OFFLINE=1 <repo>/mission-06/env/venv-wa/bin/python -I split_tool.py --out .
It never touches the network or a ServiceNow instance: it reads the task registry of the installed
browsergym-workarena 0.5.3 package only.

Rule (locked): the unit is the curriculum bucket (a template group of workflow families). Per capability category,
buckets are put in a random order drawn from a secret seed (os.urandom(16)) and scanned once: a bucket moves to the
held-out side if the held-out families stay <= 45 % of the category, until they reach >= 30 %. If the scan ends below
30 %, the smallest remaining bucket that reaches 30 % is added. At least one bucket per category stays development.
A family is held out at both levels (L2, L3). The 33 L1 atomic tasks are development.

Writes heldout.json (custodian keeps it), dev.json (for the research session), MANIFEST.json (hashes and counts).
Prints only what the custodian may report: the overall MANIFEST hash, the dev.json hash and the per-category counts.

    python -I split_tool.py --selftest        # synthetic registry with the observed bucket sizes; writes nothing
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
from pathlib import Path

HELD_FRACTION = 0.30
HELD_CAP = 0.45
CATEGORY_ORDER = ("planning_and_problem_solving", "information_retrieval", "data_driven_decision_making_and_reasoning",
                  "sophisticated_memory", "contextual_understanding_infeasible_tasks")
OBSERVED_BUCKET_SIZES = {"planning_and_problem_solving": [9, 3, 6, 8, 8, 16, 16],
                         "information_retrieval": [9, 1, 1, 4, 4, 10, 1, 9],
                         "data_driven_decision_making_and_reasoning": [12, 57, 9, 9, 9, 3, 3, 8, 8, 8, 10, 10, 10],
                         "sophisticated_memory": [5, 9, 6, 6, 1, 1],
                         "contextual_understanding_infeasible_tasks": [5, 5, 9, 9, 6, 6, 6, 6]}


def family_key(task_id: str) -> str:
    return re.sub(r"(^|[._-])l[23](?=$|[._-])", r"\1LX", task_id.lower())


def _flat(x):
    import inspect
    if inspect.isclass(x):
        return [x]
    if isinstance(x, (list, tuple)):
        return [c for y in x for c in _flat(y)]
    if isinstance(x, dict):
        return [c for y in x.values() for c in _flat(y)]
    return []


def real_registry():
    """{"categories": {cat: [[family, ...] per bucket]}, "ids": {family: {"L2": id, "L3": id}}, "l1": [ids]}"""
    os.environ["HF_HUB_OFFLINE"] = "1"
    import browsergym.workarena as W
    ids = {}
    for lvl, lst in (("L2", W.ALL_COMPOSITIONAL_TASKS_L2), ("L3", W.ALL_COMPOSITIONAL_TASKS_L3)):
        for c in lst:
            ids.setdefault(family_key(c.get_task_id()), {})[lvl] = c.get_task_id()
    cats = {}
    for cat in CATEGORY_ORDER:
        cats[cat] = [sorted({family_key(c.get_task_id()) for c in _flat(b)}) for b in W.AGENT_CURRICULUM_L2[cat]["buckets"]]
    import importlib.metadata as md
    return {"categories": cats, "ids": ids, "l1": sorted(c.get_task_id() for c in W.ATOMIC_TASKS),
            "package": f"browsergym-workarena {md.version('browsergym-workarena')}"}


def synthetic_registry():
    cats, ids = {}, {}
    for cat, sizes in OBSERVED_BUCKET_SIZES.items():
        cats[cat] = []
        for j, n in enumerate(sizes):
            fams = [f"workarena.servicenow.synthetic-{cat[:4]}-{j}-{k}-LX" for k in range(n)]
            cats[cat].append(fams)
            for f in fams:
                ids[f] = {"L2": f.replace("LX", "l2"), "L3": f.replace("LX", "l3")}
    return {"categories": cats, "ids": ids, "l1": [f"workarena.servicenow.synthetic-atomic-{i}" for i in range(33)],
            "package": "synthetic"}


def check_registry(reg):
    fams = [f for bs in reg["categories"].values() for b in bs for f in b]
    problems = []
    if len(fams) != len(set(fams)):
        problems.append("a family appears in more than one bucket")
    if set(fams) != set(reg["ids"]):
        problems.append("buckets do not cover exactly the L2/L3 families")
    if any(set(v) != {"L2", "L3"} for v in reg["ids"].values()):
        problems.append("a family lacks its L2 or L3 task")
    if list(reg["categories"]) != list(CATEGORY_ORDER):
        problems.append("unexpected categories")
    return problems


def split(reg, seed: bytes):
    rng = random.Random(int.from_bytes(seed, "big"))
    dev, held = [], []
    for cat in CATEGORY_ORDER:
        buckets = reg["categories"][cat]
        total = sum(len(b) for b in buckets)
        order = list(range(len(buckets)))
        rng.shuffle(order)
        held_idx, n_held = [], 0
        for j in order:
            if n_held >= HELD_FRACTION * total or len(held_idx) == len(buckets) - 1:
                break
            if n_held + len(buckets[j]) <= HELD_CAP * total:
                held_idx.append(j)
                n_held += len(buckets[j])
        if n_held < HELD_FRACTION * total:
            rest = sorted((len(buckets[j]), j) for j in order if j not in held_idx)
            fill = [j for n, j in rest if n_held + n >= HELD_FRACTION * total]
            j = fill[0] if fill else rest[-1][1]
            held_idx.append(j)
            n_held += len(buckets[j])
        for j, b in enumerate(buckets):
            side = held if j in held_idx else dev
            side += [{"family": f, "category": cat, "bucket": j, **reg["ids"][f]} for f in b]
    return dev, held


def counts(reg, dev, held):
    out = {}
    for cat in CATEGORY_ORDER:
        d = [x for x in dev if x["category"] == cat]
        h = [x for x in held if x["category"] == cat]
        out[cat] = {"dev_families": len(d), "heldout_families": len(h),
                    "dev_buckets": len({x["bucket"] for x in d}), "heldout_buckets": len({x["bucket"] for x in h}),
                    "heldout_fraction": round(len(h) / (len(d) + len(h)), 3)}
    out["total"] = {"dev_families": len(dev), "heldout_families": len(held), "l1_atomic_dev": len(reg["l1"])}
    return out


def canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, indent=1).encode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    tool_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if a.selftest:
        reg = synthetic_registry()
        assert not check_registry(reg), check_registry(reg)
        fracs, tot = [], []
        for s in range(2000):
            dev, held = split(reg, s.to_bytes(16, "big"))
            assert {x["family"] for x in dev}.isdisjoint({x["family"] for x in held})
            assert len(dev) + len(held) == len(reg["ids"])
            c = counts(reg, dev, held)
            for cat in CATEGORY_ORDER:
                assert c[cat]["dev_buckets"] >= 1 and c[cat]["heldout_fraction"] >= HELD_FRACTION
                fracs.append((c[cat]["heldout_fraction"], cat))
            tot.append(c["total"]["heldout_families"])
        per = {cat: [min(f for f, c in fracs if c == cat), max(f for f, c in fracs if c == cat)] for cat in CATEGORY_ORDER}
        print(json.dumps({"selftest": "ok", "seeds": 2000, "tool_sha256": tool_sha, "heldout_fraction_range_by_category": per,
                          "heldout_families_range": [min(tot), max(tot)]}, indent=1))
        return
    if not a.out:
        sys.exit("--out required")
    reg = real_registry()
    pr = check_registry(reg)
    if pr:
        sys.exit("registry check failed: " + "; ".join(pr))
    seed = os.urandom(16)
    dev, held = split(reg, seed)
    c = counts(reg, dev, held)
    out = Path(a.out)
    dev_doc = {"rule": "G1-S.2", "families": dev, "l1_atomic": reg["l1"], "package": reg["package"]}
    held_doc = {"rule": "G1-S.2", "families": held, "secret_seed_hex": seed.hex(), "package": reg["package"]}
    (out / "dev.json").write_bytes(canon(dev_doc))
    (out / "heldout.json").write_bytes(canon(held_doc))
    files = {n: hashlib.sha256((out / n).read_bytes()).hexdigest() for n in ("dev.json", "heldout.json")}
    manifest = {"tool_sha256": tool_sha, "package": reg["package"], "files": files, "counts": c}
    (out / "MANIFEST.json").write_bytes(canon(manifest))
    overall = hashlib.sha256(canon(manifest)).hexdigest()
    print(json.dumps({"MANIFEST_overall_sha256": overall, "dev.json_sha256": files["dev.json"], "counts": c,
                      "tool_sha256": tool_sha}, indent=1))


if __name__ == "__main__":
    main()
