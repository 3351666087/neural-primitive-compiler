"""Intake of the ARC-AGI-2 public evaluation set (Mission 04 confirmation challenge). Not part of the frozen methods.

  python -I intake.py plan <listing.json> <out urls.txt>    # from the GitHub contents listing: names, sizes, blob shas
  python -I intake.py verify <listing.json> <task dir>      # git blob sha of every file equals the listing; structure
                                                            # check; writes <task dir>/MANIFEST.json

The structure check reads the files but prints only counts, ids and pass/fail; never grid contents.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SHA = "f3283f727488ad98fe575ea6a5ac981e4a188e49"
RAW = f"https://raw.githubusercontent.com/arcprize/ARC-AGI-2/{SHA}/data/evaluation/"


def entries(listing):
    items = json.loads(Path(listing).read_text())
    out = [(it["name"], it["size"], it["sha"]) for it in items if it.get("type") == "file" and it["name"].endswith(".json")]
    for name, _, _ in out:
        if not (len(name) == 13 and all(c in "0123456789abcdef" for c in name[:8])):
            sys.exit(f"unexpected file name in listing: {name!r}")
    return out


def git_blob_sha(b):
    return hashlib.sha1(b"blob " + str(len(b)).encode() + b"\0" + b).hexdigest()


def grid_ok(g):
    return (isinstance(g, list) and 1 <= len(g) <= 30 and all(isinstance(r, list) and len(r) == len(g[0]) for r in g)
            and 1 <= len(g[0]) <= 30 and all(isinstance(v, int) and 0 <= v <= 9 for r in g for v in r))


def main():
    mode = sys.argv[1]
    es = entries(sys.argv[2])
    if mode == "plan":
        Path(sys.argv[3]).write_text("".join(f"{RAW}{n}\n" for n, _, _ in es))
        print("files:", len(es), "total bytes:", sum(s for _, s, _ in es))
        return
    task_dir = Path(sys.argv[3])
    want = {n: (s, h) for n, s, h in es}
    have = sorted(p.name for p in task_dir.glob("*.json") if p.name != "MANIFEST.json")
    problems = []
    if sorted(want) != have:
        problems.append(f"file set differs: missing {sorted(set(want) - set(have))}, extra {sorted(set(have) - set(want))}")
    stats = {"train_pairs": 0, "test_pairs": 0, "extra_keys": []}
    files = {}
    for name in have:
        b = (task_dir / name).read_bytes()
        if name in want and (len(b) != want[name][0] or git_blob_sha(b) != want[name][1]):
            problems.append(f"{name}: size or git blob sha differs from the listing")
        d = json.loads(b)
        if set(d) - {"train", "test"}:
            stats["extra_keys"].append(name)
        ok = isinstance(d.get("train"), list) and isinstance(d.get("test"), list) and d["train"] and d["test"]
        for p in (d.get("train") or []) + (d.get("test") or []):
            ok = ok and isinstance(p, dict) and grid_ok(p.get("input")) and grid_ok(p.get("output"))
        if not ok:
            problems.append(f"{name}: structure check failed")
        stats["train_pairs"] += len(d.get("train") or [])
        stats["test_pairs"] += len(d.get("test") or [])
        files[name] = hashlib.sha256(b).hexdigest()
    overall = hashlib.sha256("".join(f"{k}:{v}\n" for k, v in sorted(files.items())).encode()).hexdigest()
    (task_dir / "MANIFEST.json").write_text(json.dumps(
        {"source": f"github.com/arcprize/ARC-AGI-2 @ {SHA}, data/evaluation", "files": files, "overall_sha256": overall,
         "structure": stats, "problems": problems}, indent=1))
    print("files:", len(have), "train pairs:", stats["train_pairs"], "test pairs:", stats["test_pairs"],
          "files with extra keys:", len(stats["extra_keys"]), "problems:", problems or "none", "overall:", overall)


if __name__ == "__main__":
    main()
