"""Mission 04 second confirmation: twin tasks from an independent session. Protocol: mission-04/CONFIRMATION_TWINS.md.

The frozen P-R2 code (r2_priors/run_r2.py, normalize.py) and the frozen solvers run, unchanged, on the canonical and
the twin version of every base task. Labels only are written; never grid contents.

  python -I confirm2.py dryrun                         # self-made twins of DEV tasks (implementation check)
  python -I confirm2.py freeze                         # sha256 of every frozen file -> freeze2.json
  python -I confirm2.py confirm <data dir> <sha256 of MANIFEST.json as reported by the generator>

The generator chose its own metadata format, so pairs and prior classes are read generically (section 3 of the
protocol). If fewer than 90 % of the entries can be read, the run stops before any method runs (STOPPED_FORMAT).
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "mission-04" / "experiments" / "r2_priors"))
import run_r2 as R2  # noqa: E402

R = R2.R
MDISC_CFGS = {"C0": ["BG-0"], "C8": ["BG-0", "EDGE-content"]}
MDISC_REPS = {r: R2.SINGLE_MDISC[r] for r in ("BG-0", "EDGE-content")}
FREEZE = HERE / "freeze2.json"
OUT = HERE / "confirm2_twins.json"
FROZEN = [HERE / "confirm2.py", HERE / "score2.py", REPO / "mission-04" / "CONFIRMATION_TWINS.md",
          REPO / "mission-04" / "experiments" / "r2_priors" / "run_r2.py",
          REPO / "mission-04" / "experiments" / "r2_priors" / "normalize.py",
          REPO / "mission-04" / "experiments" / "r1_repr" / "blocks.py",
          REPO / "mission-04" / "experiments" / "r1_repr" / "run_r1.py",
          REPO / "mission-04" / "experiments" / "a0_uniqueness" / "uniqueness.py",
          REPO / "mission-04" / "experiments" / "a0_uniqueness" / "resolve_unknown.py",
          REPO / "mission-04" / "experiments" / "a0_uniqueness" / "rerun_arc.py",
          REPO / "mission-03" / "experiments" / "arc" / "m_disc.py"]
HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
LETTERS = re.compile(r"^\s*[abcABC](\s*[+,&/|_\-\s]?\s*[abcABC])*\s*$")
CAT_KEYS = ("prior", "perturb", "categor", "class", "change", "kind", "type", "variant", "shift")


# ------------------------------------------------------------------ reading the generator's files generically
def walk_strings(x, key=None):
    if isinstance(x, str):
        yield key, x
    elif isinstance(x, dict):
        for k, v in x.items():
            yield from walk_strings(v, str(k))
    elif isinstance(x, list):
        for v in x:
            yield from walk_strings(v, key)


def entry_list(meta):
    """The list of per-task entries: the largest list of dicts anywhere, or the values of a dict of dicts."""
    best = []

    def visit(x):
        nonlocal best
        if isinstance(x, list) and x and all(isinstance(v, dict) for v in x) and len(x) > len(best):
            best = x
        if isinstance(x, dict):
            vals = list(x.values())
            if vals and all(isinstance(v, dict) for v in vals) and len(vals) > len(best):
                best = [dict(v, _key=k) for k, v in x.items()]
            for v in vals:
                visit(v)
        elif isinstance(x, list):
            for v in x:
                visit(v)
    visit(meta)
    return best


def parse_pairs(meta, can_names, twin_names):
    pairs, bad = [], 0
    entries = entry_list(meta)
    for e in entries:
        ss = list(walk_strings(e))
        can, tw = set(), set()
        for _, s in ss:
            name = Path(s).name
            in_c, in_t = name in can_names, name in twin_names
            if in_c and in_t:
                (can if "canon" in s.lower() else tw if "twin" in s.lower() else set()).add(name)
            elif in_c:
                can.add(name)
            elif in_t:
                tw.add(name)
        keyed = [s for k, s in ss if k and any(w in k.lower() for w in CAT_KEYS) and LETTERS.match(s)]
        pool = keyed or [s for _, s in ss if LETTERS.match(s)]
        cats = sorted({ch.lower() for s in pool for ch in s if ch.lower() in "abc"})
        if len(can) == 1 and len(tw) == 1 and cats:
            pairs.append({"canonical": can.pop(), "twin": tw.pop(), "classes": cats})
        else:
            bad += 1
    return pairs, bad, len(entries)


def manifest_map(man):
    """path -> sha256 from any reasonable manifest layout."""
    out = {}

    def looks_path(s):
        return isinstance(s, str) and s.endswith(".json")

    def visit(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if isinstance(v, str) and HEX64.match(v) and looks_path(k):
                    out[k.lstrip("./")] = v.lower()
            hx = [v for v in x.values() if isinstance(v, str) and HEX64.match(v)]
            ps = [v for v in x.values() if looks_path(v)]
            if len(hx) == 1 and len(ps) == 1:
                out[ps[0].lstrip("./")] = hx[0].lower()
            for v in x.values():
                visit(v)
        elif isinstance(x, list):
            for v in x:
                visit(v)
    visit(man)
    return out


def verify_files(root):
    man = json.loads((root / "MANIFEST.json").read_text())
    mm = manifest_map(man)
    byname = {}
    for k, v in mm.items():
        byname.setdefault(Path(k).name, set()).add(v)
    files = sorted(root.glob("canonical/*.json")) + sorted(root.glob("twin/*.json")) + [root / "metadata.json"]
    missing, mismatch = [], []
    for f in files:
        rel = str(f.relative_to(root))
        h = hashlib.sha256(f.read_bytes()).hexdigest()
        want = {mm[rel]} if rel in mm else byname.get(f.name)
        if not want:
            missing.append(rel)
        elif h not in want:
            mismatch.append(rel)
    return {"files": len(files), "missing_in_manifest": len(missing), "hash_mismatch": len(mismatch)}


# ------------------------------------------------------------------ running the frozen methods on one task version
def version_record(path):
    train, tests = R.load(path)
    b = R2.task_blocks(train, tests)
    md = {name: R2.guarded(R2.BUDGET["mdisc"], R2.mdisc_rep, train, tests, rep) for name, rep in MDISC_REPS.items()}
    return {"blocks": {c: {"S0": v["S0"], "S2": v["S2"]} for c, v in b["configs"].items()},
            "mdisc": {c: R2.pooled_mdisc([md[r] for r in reps]) for c, reps in MDISC_CFGS.items()}}


def run(root, label):
    t0 = time.perf_counter()
    can_names = {p.name for p in (root / "canonical").glob("*.json")}
    twin_names = {p.name for p in (root / "twin").glob("*.json")}
    meta = json.loads((root / "metadata.json").read_text())
    pairs, bad, n = parse_pairs(meta, can_names, twin_names)
    out = {"label": label, "entries": n, "parsed_pairs": len(pairs), "unparsed_entries": bad}
    if not n or len(pairs) < 0.9 * n:
        out["status"] = "STOPPED_FORMAT"
        return out
    recs = {}
    for p in pairs:
        for side, d in (("canonical", "canonical"), ("twin", "twin")):
            name = p[side]
            if f"{d}/{name}" not in recs:
                recs[f"{d}/{name}"] = version_record(root / d / name)
        print(p["canonical"], p["twin"], p["classes"],
              {s: {c: recs[f"{s}/{p[s]}"]["blocks"][c]["S0"] for c in ("C0", "C4", "C9")} for s in ("canonical", "twin")},
              flush=True)
    out.update(status="COMPLETED", pairs=pairs, records=recs, time_s=round(time.perf_counter() - t0, 1))
    return out


# ------------------------------------------------------------------ dry run on self-made twins of DEV tasks
def perturb(train, tests, kind, rng):
    pairs = train + tests
    used = set()
    for I, O in pairs:
        used |= set(np.unique(I).tolist()) | set(np.unique(O).tolist())
    free = [c for c in range(1, 10) if c not in used]
    if kind == "a":
        if not free:
            return None
        c = rng.choice(free)
        lut = np.arange(10)
        lut[0], lut[c] = c, 0
        res = [(lut[I], lut[O]) for I, O in pairs]
    elif kind == "b":
        res = []
        for I, O in pairs:
            cols = sorted((set(np.unique(I).tolist()) | set(np.unique(O).tolist())) - {0})
            lut = np.arange(10)
            for c, d in zip(cols, rng.sample(range(1, 10), len(cols))):
                lut[c] = d
            res.append((lut[I], lut[O]))
    else:
        if not free:
            return None
        f = rng.choice(free)

        def frame(g, p):
            out = np.zeros((g.shape[0] + 2 * p + 2, g.shape[1] + 2 * p + 2), dtype=int)
            out[0, :], out[-1, :], out[:, 0], out[:, -1] = f, f, f, f
            out[p + 1:p + 1 + g.shape[0], p + 1:p + 1 + g.shape[1]] = g
            return out
        res = []
        for I, O in pairs:
            p = rng.randint(1, 2)
            res.append((frame(I, p), frame(O, p) if I.shape == O.shape else O))
    return res[:len(train)], res[len(train):]


def write_task(path, train, tests):
    path.write_text(json.dumps({"train": [{"input": I.tolist(), "output": O.tolist()} for I, O in train],
                                "test": [{"input": I.tolist(), "output": O.tolist()} for I, O in tests]}))


def build_dryrun(root):
    rng = random.Random(20261021)
    r2 = json.loads((REPO / "mission-04/experiments/r2_priors/r2.json").read_text())
    bl = json.loads((REPO / "mission-04/experiments/r2_priors/r2_blocks.json").read_text())["rows"]
    solved = {t for t, r in bl.items() if any(v[p] == "correct" for v in r["configs"].values() for p in ("S0", "S2"))}
    for rows in r2["mdisc_rows"].values():
        solved |= {t for t, v in rows.items() if v == "correct"}
    others = sorted(set(bl) - solved)
    base = rng.sample(sorted(solved), 30) + rng.sample(others, 6)
    (root / "canonical").mkdir(parents=True)
    (root / "twin").mkdir()
    entries = []
    for t in base:
        train, tests = R.load(R.DATA / f"{t}.json")
        cname = f"{rng.getrandbits(32):08x}.json"
        write_task(root / "canonical" / cname, train, tests)
        for kind in ("a", "b", "c"):
            p = perturb(train, tests, kind, rng)
            if p is None:
                continue
            tname = f"{rng.getrandbits(32):08x}.json"
            write_task(root / "twin" / tname, *p)
            entries.append({"canonical": cname, "twin": tname, "family": "dev", "prior_change": kind})
    (root / "metadata.json").write_text(json.dumps({"tasks": entries}))
    files = sorted(root.glob("canonical/*.json")) + sorted(root.glob("twin/*.json")) + [root / "metadata.json"]
    (root / "MANIFEST.json").write_text(json.dumps(
        {"files": {str(f.relative_to(root)): hashlib.sha256(f.read_bytes()).hexdigest() for f in files}}))
    return entries


def parser_selftest(entries, can_names, twin_names):
    """The generic reader must give the same pairs for several plausible layouts."""
    want = sorted((e["canonical"], e["twin"], (e["prior_change"],)) for e in entries)
    layouts = {
        "list": entries,
        "dict_of_dicts": {f"t{i}": {"files": {"canonical": f"canonical/{e['canonical']}", "twin": f"twin/{e['twin']}"},
                                    "transform": "x", "changed_prior": [e["prior_change"]]} for i, e in enumerate(entries)},
        "nested": {"version": 1, "items": [{"pair": [e["canonical"], e["twin"]], "category": e["prior_change"].upper()}
                                           for e in entries]},
    }
    res = {}
    for name, meta in layouts.items():
        pairs, bad, n = parse_pairs(meta, can_names, twin_names)
        got = sorted((p["canonical"], p["twin"], tuple(p["classes"])) for p in pairs)
        res[name] = {"entries": n, "unparsed": bad, "same_as_expected": got == want}
    return res


def file_hashes():
    return {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in FROZEN}


def main():
    mode = sys.argv[1]
    if mode == "dryrun":
        root = Path(os.environ["TMPDIR"]) / "c2_dryrun"
        if root.exists():
            sys.exit(f"{root} exists; remove it first")
        entries = build_dryrun(root)
        selftest = parser_selftest(entries, {p.name for p in (root / "canonical").glob("*.json")},
                                   {p.name for p in (root / "twin").glob("*.json")})
        print("parser self-test:", selftest, flush=True)
        print("manifest check:", verify_files(root), flush=True)
        out = run(root, "DRY RUN: self-made twins of ARC-AGI-1 training tasks (DEV); implementation check, not evidence")
        out["parser_selftest"] = selftest
        (HERE / "dryrun2_dev.json").write_text(json.dumps(out, indent=1, default=str))
        print("status", out["status"], "pairs", out["parsed_pairs"], "time", out.get("time_s"))
    elif mode == "freeze":
        FREEZE.write_text(json.dumps({"files": file_hashes(), "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S")}, indent=1))
        print(json.dumps(json.loads(FREEZE.read_text()), indent=1))
    elif mode == "confirm":
        root, reported = Path(sys.argv[2]), sys.argv[3].lower()
        if json.loads(FREEZE.read_text())["files"] != file_hashes():
            sys.exit("frozen files changed since the freeze; refusing to run")
        if OUT.exists():
            sys.exit("the confirmation has already been run once; refusing to run it again")
        mh = hashlib.sha256((root / "MANIFEST.json").read_bytes()).hexdigest()
        if mh != reported:
            sys.exit("MANIFEST.json does not match the hash the generator reported; refusing to run")
        check = verify_files(root)
        if check["missing_in_manifest"] or check["hash_mismatch"]:
            sys.exit(f"files do not match MANIFEST.json: {check}")
        out = run(root, "CONFIRMATION: twin tasks from an independent session, first and only run of the frozen methods")
        out.update(manifest_sha256=mh, file_check=check, freeze=json.loads(FREEZE.read_text())["files"])
        OUT.write_text(json.dumps(out, indent=1, default=str))
        print("status", out["status"], "pairs", out["parsed_pairs"], "time", out.get("time_s"))
    else:
        sys.exit(f"unknown mode {mode}")


if __name__ == "__main__":
    main()
