"""G4 freeze manifest: SHA-256 of every file the G4 held-out run depends on, and one overall hash.

  python -I freeze.py write     # writes mission-05/G4_FREEZE.json (at freeze time only)
  python -I freeze.py verify    # recomputes and compares; exits 1 on any difference (before the held-out run)
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
M5 = REPO / "mission-05"
PATTERNS = ["mission-05/experiments/lib/*.py", "mission-05/experiments/judge/*.py", "mission-05/experiments/judge/pool.json",
            "mission-05/experiments/g3/*.py", "mission-05/experiments/g3/specs_library.json",
            "mission-05/experiments/r7/zplus.py", "mission-05/experiments/r8/zpp.py", "mission-05/experiments/g4/*.py",
            "mission-05/experiments/pilots/run_pa1.py", "mission-05/experiments/pilots/run_pa3.py",
            "mission-05/experiments/pilots/run_r4.py", "mission-05/experiments/pilots/run_cr.py",
            "src/cog/*.py", "mission-05/G4_DESIGN.md", "mission-05/G4_GENERATOR_BRIEF.md"]
OUT = M5 / "G4_FREEZE.json"


def manifest():
    files = sorted({p for pat in PATTERNS for p in REPO.glob(pat) if p.is_file()})
    rows = {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    overall = hashlib.sha256("".join(f"{k}:{v}\n" for k, v in sorted(rows.items())).encode()).hexdigest()
    return {"files": rows, "overall": overall}


def main():
    if sys.argv[1:] == ["write"]:
        m = manifest()
        OUT.write_text(json.dumps(m, indent=1))
        print("files", len(m["files"]), "overall", m["overall"])
    elif sys.argv[1:] == ["verify"]:
        old, new = json.loads(OUT.read_text()), manifest()
        diff = sorted(k for k in set(old["files"]) | set(new["files"]) if old["files"].get(k) != new["files"].get(k))
        print("overall", new["overall"], "matches" if not diff else f"DIFFERS: {diff}")
        sys.exit(1 if diff else 0)
    else:
        sys.exit("usage: freeze.py write|verify")


if __name__ == "__main__":
    main()
