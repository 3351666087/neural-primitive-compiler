"""Integrity manifest for the ARC-AGI-1 copy. Checks that every task file parses and has the expected shape,
WITHOUT printing or storing any grid content (the evaluation split is held out; see ARC_PROVENANCE.md).

  python -I mission-03/experiments/arc_intake/manifest.py mission-03/external/arc-agi-1 mission-03/external/arc-agi-1/MANIFEST.json
"""

import hashlib
import json
import sys
from pathlib import Path


def main(root: str, out: str):
    root = Path(root)
    manifest = {"files": {}, "splits": {}}
    for split in ("training", "evaluation"):
        files = sorted((root / "data" / split).glob("*.json"))
        bad = 0
        for f in files:
            raw = f.read_bytes()
            manifest["files"][f"data/{split}/{f.name}"] = hashlib.sha256(raw).hexdigest()
            try:
                d = json.loads(raw)
                ok = set(d) - {"name"} == {"train", "test"} and all({"input", "output"} <= set(p) for p in d["train"] + d["test"])
            except Exception:
                ok = False
            bad += not ok
        manifest["splits"][split] = {"tasks": len(files), "malformed": bad}
    for f in ("LICENSE", "README.md"):
        manifest["files"][f] = hashlib.sha256((root / f).read_bytes()).hexdigest()
    all_hash = hashlib.sha256("".join(f"{k} {v}\n" for k, v in sorted(manifest["files"].items())).encode()).hexdigest()
    manifest["tree_sha256"] = all_hash
    Path(out).write_text(json.dumps(manifest, indent=1))
    print(json.dumps(manifest["splits"]), "tree", all_hash)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
