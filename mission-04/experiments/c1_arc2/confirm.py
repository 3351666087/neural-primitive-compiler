"""Mission 04 confirmation challenge on the ARC-AGI-2 public evaluation set. Protocol: mission-04/CONFIRMATION_ARC2.md.

Runs the FROZEN Mission 04 methods, unchanged, on a task directory and writes labels only (task ids and outcome
labels; never grid contents):
  block layer   routes F1, F3, F3-noselect, F4; policies S0, S2, S3, S4 (preferences learned on ARC-AGI-1 training,
                frozen in learned_preferences.json); attribute families (P-R1c); part attributes (P-R1d);
                conservation-law specificity; gap categories; pair-level leave-one-out on the training pairs
  M-DISC        M-DISC-fixed, -strict, -MDL-fixed with the exact uniqueness check (Z3 60 s, then complete
                enumeration 300 s for Z3 timeouts); answers re-checked by the enumeration procedure
Budgets per task: block layer 600 s, leave-one-out 600 s, M-DISC (all three variants) 1200 s. A component that
exceeds its budget is recorded as RESOURCE_LIMIT and counts as an abstention.

Modes:
  python -I confirm.py learn                       # S3/S4 preferences from ARC-AGI-1 training (DEV) -> learned_preferences.json
  python -I confirm.py dryrun                      # whole pipeline on ARC-AGI-1 training (DEV); M-DISC on the first 60 ids
  python -I confirm.py freeze                      # sha256 of every frozen file -> freeze.json
  python -I confirm.py confirm <task dir>          # the single confirmation run; refuses if hashes changed or if it ran before
"""

from __future__ import annotations

import hashlib
import json
import signal
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
R1 = REPO / "mission-04" / "experiments" / "r1_repr"
A0 = REPO / "mission-04" / "experiments" / "a0_uniqueness"
sys.path.insert(0, str(R1))
sys.path.insert(0, str(A0))
import blocks as B  # noqa: E402
import run_r1 as R  # noqa: E402
import run_r1b as R1B  # noqa: E402
import run_r1c as R1C  # noqa: E402
import run_r1d as R1D  # noqa: E402
import rerun_arc as RA  # noqa: E402
import resolve_unknown as RU  # noqa: E402
import uniqueness as U  # noqa: E402

DEV = REPO / "mission-03" / "external" / "arc-agi-1" / "data" / "training"
PREFS = HERE / "learned_preferences.json"
FREEZE = HERE / "freeze.json"
OUT = HERE / "confirm_arc2.json"
FROZEN = [HERE / "confirm.py", PREFS, REPO / "mission-04" / "CONFIRMATION_ARC2.md",
          R1 / "blocks.py", R1 / "run_r1.py", R1 / "run_r1b.py", R1 / "run_r1c.py", R1 / "run_r1d.py",
          A0 / "uniqueness.py", A0 / "resolve_unknown.py", A0 / "rerun_arc.py",
          REPO / "mission-03" / "experiments" / "arc" / "m_disc.py"]
BUDGET = {"blocks": 600, "loo": 600, "mdisc": 1200}
LOO_ROUTES = ["F1", "F3", "F3-noselect"]
DRYRUN_MDISC = 60


class Budget(BaseException):
    """Raised by the alarm; BaseException so that no `except Exception` in the frozen code can swallow it."""


def _alarm(signum, frame):
    raise Budget()


def guarded(seconds, fn, *args):
    signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(seconds)
    t0 = time.perf_counter()
    try:
        out = fn(*args)
    except Budget:
        out = "RESOURCE_LIMIT"
    finally:
        signal.alarm(0)
    return out, round(time.perf_counter() - t0, 2)


def label(o, T):
    return "abstain" if o is None else "correct" if o.shape == T.shape and (o == T).all() else "wrong"


def combine(labels):
    return "correct" if all(l == "correct" for l in labels) else "wrong" if "wrong" in labels else "abstain"


# ------------------------------------------------------------------ block layer (frozen P-R1 ... P-R1d code)
def gap_category(train):
    """Same rule as r1_repr/gap_diagnostics.py (descriptive)."""
    K = [r for r in B.GRAMMAR if B.law_K(train, r)]
    if not K:
        return "C only: crop target not selectable by any attribute"
    r = K[0]
    uniform, added = True, False
    for I, O in train:
        blocks = B.partition(I, r)
        covered = np.zeros(I.shape, bool)
        for b in blocks:
            if len({int(O[x]) for x in b}) > 1:
                uniform = False
            for x in b:
                covered[x] = True
        if (O[~covered] != 0).any():
            added = True
    return ("K: non-uniform recolouring inside blocks" if not uniform else
            "K: new cells outside input blocks" if added else
            "K: uniform per block, not a function of any attribute")


def block_layer(train, tests, prefs):
    rec = {}
    inputs = [I for I, _ in tests]
    for route in R.ROUTES:
        outs, info = R.route_solve(route, train, inputs)
        rec[route] = {"status": R.status(outs, tests), "rules_tried": info["rules_tried"], "rules_used": info["rules_used"]}
    rec["law_K_rules"] = [r for r in B.GRAMMAR if B.law_K(train, r)]
    rec["law_C_rules"] = [r for r in B.GRAMMAR if B.law_C(train, r)]
    rec["law_holds"] = bool(rec["law_K_rules"] or rec["law_C_rules"])
    rec["specificity"] = R.specificity(train)
    rows = R1B.task_explanations(train, tests)
    rec["n_explanations"] = len(rows)
    rec["n_undetermined"] = sum(not r["determined"] for r in rows)
    pol = {"S0": R1B.decide(rows), "S1": rec["F1"]["status"], "S2": R1B.decide([r for r in rows if r["determined"]])}
    for p in ("S3", "S4"):
        sc = [prefs[p].get(repr(r["type"]), 0) for r in rows]
        pol[p] = "abstain" if not rows or max(sc) == 0 else R1B.decide([r for r, s in zip(rows, sc) if s == max(sc)])
    rec["policies"] = pol
    rec["families"] = {c: {k: v for k, v in R1C.task_status(train, tests, fams).items() if k in ("S0", "S2")}
                       for c, fams in R1C.CONFIGS.items()}
    if all(I.shape == O.shape for I, O in train):
        rec["parts"] = {c: {k: v for k, v in R1D.task(train, tests, fams).items() if k in ("S0", "S2")}
                        for c, fams in {"W1": ["W1"], "W2": ["W2"], "W3": ["W3"], "W123": ["W1", "W2", "W3"]}.items()}
    else:
        rec["parts"] = None
    gap = rec["law_holds"] and pol["S2"] != "correct"
    rec["gap"] = gap
    rec["gap_category"] = gap_category(train) if gap and rec["families"]["+ALL"]["S2"] != "correct" and not (
        rec["parts"] and rec["parts"]["W123"]["S2"] == "correct") else None
    return rec


def loo_pairs(train):
    """Pair-level leave-one-out on the training pairs (uses no test output)."""
    if len(train) < 3:
        return None
    out = {}
    for route in LOO_ROUTES:
        labels = []
        for j in range(len(train)):
            rest = train[:j] + train[j + 1:]
            o, _ = R.route_solve(route, rest, [train[j][0]])
            labels.append(label(o[0], train[j][1]))
        out[route] = {k: labels.count(k) for k in ("correct", "wrong", "abstain")}
    return out


# ------------------------------------------------------------------ M-DISC with the exact uniqueness check
def grid_of(v):
    out = np.full(v["shape"], U.BG, dtype=int)
    for cell, col in v["pred"]:
        out[cell] = col
    return out


def mdisc(train, tests):
    res = {}
    for name, kw in RA.VARIANTS.items():
        outs, info = U.solve_fixed(train, [I for I, _ in tests], **kw)
        sts = list(info.get("uniqueness") or [info.get("reason")] * len(tests))
        final, verdicts, recheck = list(outs), [], []
        for k, (I, _) in enumerate(tests):
            st = sts[k]
            mode, mdl = kw.get("colour_mode", "prior"), kw.get("tiebreak") == "mdl"
            if st == "UNKNOWN":                       # Z3 timeout: decide with the enumeration procedure
                v = RU.decide(train, I, mode, mdl)
                st = "enumeration:" + v["verdict"]
                final[k] = grid_of(v) if v["verdict"] == "UNIQUE" else None
            elif st == "UNIQUE":                      # answered by Z3: re-check with the second procedure
                recheck.append(RU.decide(train, I, mode, mdl)["verdict"])
            verdicts.append(st)
        res[name] = {"status": combine([label(o, T) for o, (_, T) in zip(final, tests)]), "verdicts": verdicts,
                     "reason": info.get("reason"), "enumeration_recheck_of_z3_unique": recheck}
    return res


# ------------------------------------------------------------------ summaries
def summarise(rows):
    def count(get):
        st = [get(r) for r in rows.values()]
        st = [s for s in st if s is not None]
        c, w = st.count("correct"), st.count("wrong")
        return {"correct": c, "wrong": w, "abstain": st.count("abstain"), "RESOURCE_LIMIT": st.count("RESOURCE_LIMIT"),
                "precision": round(c / (c + w), 3) if c + w else None}

    bl = {t: r["blocks"] for t, r in rows.items() if isinstance(r["blocks"], dict)}
    s = {"tasks": len(rows), "block_layer_completed": len(bl),
         "block_layer_RESOURCE_LIMIT": sorted(t for t, r in rows.items() if r["blocks"] == "RESOURCE_LIMIT")}
    for route in R.ROUTES:
        s[route] = count(lambda r, x=route: r["blocks"][x]["status"] if isinstance(r["blocks"], dict) else r["blocks"])
    for p in ("S0", "S1", "S2", "S3", "S4"):
        s[p] = count(lambda r, x=p: r["blocks"]["policies"][x] if isinstance(r["blocks"], dict) else r["blocks"])
    for c in R1C.CONFIGS:
        s[f"fam{c}|S2"] = count(lambda r, x=c: r["blocks"]["families"][x]["S2"] if isinstance(r["blocks"], dict) else None)
        s[f"fam{c}|S0"] = count(lambda r, x=c: r["blocks"]["families"][x]["S0"] if isinstance(r["blocks"], dict) else None)
    s["partsW123|S2"] = count(lambda r: r["blocks"]["parts"]["W123"]["S2"] if isinstance(r["blocks"], dict) and r["blocks"]["parts"] else None)
    s["partsW123|S0"] = count(lambda r: r["blocks"]["parts"]["W123"]["S0"] if isinstance(r["blocks"], dict) and r["blocks"]["parts"] else None)
    spec = [b["specificity"] for b in bl.values() if b["specificity"]]
    nt, ns = sum(x["true"] for x in spec), sum(x["shuffled"] for x in spec)
    s["specificity"] = {"tasks_with_2plus_pairs": len(spec), "law_holds_true_pairs": nt, "law_holds_shuffled_pairs": ns,
                        "ratio": round(nt / ns, 2) if ns else None}
    law = [b for b in bl.values() if b["law_holds"]]
    f1 = set(B.F1_LIST)
    s["law_holding_tasks"] = len(law)
    s["law_holding_with_an_F1_rule"] = sum(bool(f1 & set(b["law_K_rules"] + b["law_C_rules"])) for b in law)
    s["law_holding_only_non_F1_rules"] = sum(not (f1 & set(b["law_K_rules"] + b["law_C_rules"])) for b in law)
    s["F3_rules_tried_mean_on_law_tasks"] = round(float(np.mean([b["F3"]["rules_tried"] for b in law])), 2) if law else None
    s["F3_solved_using_F1_rules"] = sum(1 for b in bl.values() if b["F3"]["status"] == "correct" and f1 & set(b["F3"]["rules_used"]))
    ident = [t for t, b in bl.items() if b["policies"]["S0"] == "abstain" and b["policies"]["S2"] in ("correct", "wrong")]
    s["identifiability_abstentions"] = {"tasks": len(ident),
                                        "S2_correct_among_them": sum(bl[t]["policies"]["S2"] == "correct" for t in ident),
                                        "S2_wrong_among_them": sum(bl[t]["policies"]["S2"] == "wrong" for t in ident)}
    gap = [t for t, b in bl.items() if b["gap"]]
    expl = [t for t in gap if bl[t]["families"]["+ALL"]["S2"] == "correct" or (bl[t]["parts"] and bl[t]["parts"]["W123"]["S2"] == "correct")]
    cats = {}
    for t in gap:
        if bl[t]["gap_category"]:
            cats[bl[t]["gap_category"]] = cats.get(bl[t]["gap_category"], 0) + 1
    s["gap"] = {"tasks": len(gap), "explained_by_attributes_or_parts_S2": len(expl), "unexplained_categories": cats}
    loo = {route: {"correct": 0, "wrong": 0, "abstain": 0} for route in LOO_ROUTES}
    nloo = 0
    for r in rows.values():
        if isinstance(r["loo"], dict):
            nloo += 1
            for route in LOO_ROUTES:
                for k in loo[route]:
                    loo[route][k] += r["loo"][route][k]
    for route in LOO_ROUTES:
        c, w = loo[route]["correct"], loo[route]["wrong"]
        loo[route]["precision"] = round(c / (c + w), 3) if c + w else None
    s["loo_pairs"] = dict(loo, tasks=nloo, RESOURCE_LIMIT=sorted(t for t, r in rows.items() if r["loo"] == "RESOURCE_LIMIT"))
    md = {t: r["mdisc"] for t, r in rows.items() if r.get("mdisc") is not None}
    for name in RA.VARIANTS:
        s[name] = count(lambda r, x=name: (r["mdisc"][x]["status"] if isinstance(r.get("mdisc"), dict) else r.get("mdisc")))
    rc = [v for m in md.values() if isinstance(m, dict) for x in m.values() for v in x["enumeration_recheck_of_z3_unique"]]
    s["z3_unique_rechecked"] = {"n": len(rc), "agree": rc.count("UNIQUE"), "other": sorted(set(v for v in rc if v != "UNIQUE"))}
    blk_ok = lambda b: any(b[x]["status"] == "correct" for x in R.ROUTES) or any(
        b["policies"][p] == "correct" for p in ("S0", "S2", "S3", "S4"))
    s["block_correct_not_mdisc_fixed"] = sorted(
        t for t, r in rows.items() if isinstance(r["blocks"], dict) and blk_ok(r["blocks"])
        and not (isinstance(r.get("mdisc"), dict) and r["mdisc"]["M-DISC-fixed"]["status"] == "correct"))
    s["mdisc_tasks_run"] = len(md)
    return s


def run(task_dir, label_text, mdisc_ids=None):
    prefs = json.loads(PREFS.read_text())
    rows = {}
    t0 = time.perf_counter()
    files = sorted(Path(task_dir).glob("*.json"))
    files = [f for f in files if f.name != "MANIFEST.json"]
    for f in files:
        train, tests = R.load(f)
        row = {}
        row["blocks"], row["t_blocks"] = guarded(BUDGET["blocks"], block_layer, train, tests, prefs)
        row["loo"], row["t_loo"] = guarded(BUDGET["loo"], loo_pairs, train)
        if mdisc_ids is None or f.stem in mdisc_ids:
            row["mdisc"], row["t_mdisc"] = guarded(BUDGET["mdisc"], mdisc, train, tests)
        else:
            row["mdisc"] = None
        rows[f.stem] = row
        b = row["blocks"]
        print(f.stem, "blocks:", b if isinstance(b, str) else {k: b[k]["status"] for k in R.ROUTES} | b["policies"],
              "| mdisc:", row["mdisc"] if not isinstance(row["mdisc"], dict) else {k: v["status"] for k, v in row["mdisc"].items()},
              flush=True)
    out = {"label": label_text, "budgets_s": BUDGET, "summary": summarise(rows), "rows": rows,
           "time_s": round(time.perf_counter() - t0, 1)}
    return out


def file_hashes():
    return {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in FROZEN}


def main():
    mode = sys.argv[1]
    if mode == "learn":
        score = {"S3": {}, "S4": {}}
        for f in sorted(DEV.glob("*.json")):
            rows = R1B.task_explanations(*R.load(f))
            for ty in {repr(r["type"]) for r in rows}:
                score["S3"][ty] = score["S3"].get(ty, 0) + 1
            for ty in {repr(r["type"]) for r in rows if r["correct"]}:
                score["S4"][ty] = score["S4"].get(ty, 0) + 1
        PREFS.write_text(json.dumps({"label": "learned on ARC-AGI-1 training (DEV); S4 uses its test outputs as feedback",
                                     **score}, indent=1, sort_keys=True))
        print("types:", {k: len(v) for k, v in score.items()})
    elif mode == "dryrun":
        ids = sorted(f.stem for f in DEV.glob("*.json"))[:DRYRUN_MDISC]
        out = run(DEV, f"DRY RUN on ARC-AGI-1 training (DEV); S3/S4 in-sample (preferences learned on these tasks); "
                       f"M-DISC on the first {DRYRUN_MDISC} ids only", set(ids))
        (HERE / "dryrun_dev.json").write_text(json.dumps(out, indent=1, default=str))
        print(json.dumps(out["summary"], indent=1, default=str))
    elif mode == "freeze":
        FREEZE.write_text(json.dumps({"files": file_hashes(), "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S")}, indent=1))
        print(json.dumps(json.loads(FREEZE.read_text()), indent=1))
    elif mode == "confirm":
        task_dir = Path(sys.argv[2])
        frozen = json.loads(FREEZE.read_text())["files"]
        if frozen != file_hashes():
            sys.exit("frozen files changed since the freeze; refusing to run the confirmation")
        if OUT.exists():
            sys.exit("the confirmation has already been run once; refusing to run it again")
        man = json.loads((task_dir / "MANIFEST.json").read_text())
        have = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(task_dir.glob("*.json")) if f.name != "MANIFEST.json"}
        if have != man["files"]:
            sys.exit("task files do not match MANIFEST.json; refusing to run")
        out = run(task_dir, "CONFIRMATION: ARC-AGI-2 public evaluation set, first and only run of the frozen methods")
        out["freeze"] = frozen
        OUT.write_text(json.dumps(out, indent=1, default=str))
        print(json.dumps(out["summary"], indent=1, default=str))
    else:
        sys.exit(f"unknown mode {mode}")


if __name__ == "__main__":
    main()
