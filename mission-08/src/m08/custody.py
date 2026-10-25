"""Held-out custody (DATA_SPLITS_AND_CUSTODY.md). Development code may read only datasets on the development list.
A held-out dataset is readable only by the judge, and only after FREEZE_MANIFEST.sha256 exists and every file it
lists matches its hash; the judge sets M08_JUDGE=1. Until Gate 2 fixes the split, nothing is held out by name, but
`allow` already refuses any dataset listed in HELDOUT.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FREEZE = ROOT / "FREEZE_MANIFEST.sha256"

# DATA_SPLITS_AND_CUSTODY.md sections 1 and 3 (Randi held-out columns are masked in m08.randi, section 2)
HELDOUT: set[str] = {
    "witvliet_2", "witvliet_4", "nema_witvliet_2", "nema_witvliet_4",
    "nema_white_jsh", "nema_white_n2u", "brittin_adjacency",
    "groschner_t4", "groschner_t4_rnai", "groschner_t4_rf", "randi_heldout",
}
RANDI_SALT = "m08-randi-split-v1:"


class CustodyError(PermissionError):
    pass


def frozen():
    if not FREEZE.exists():
        return False
    for line in FREEZE.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        digest, name = line.split(None, 1)
        p = ROOT / name.strip().lstrip("*")
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            raise CustodyError(f"freeze manifest mismatch: {name}")
    return True


def allow(dataset):
    if dataset in HELDOUT and not (os.environ.get("M08_JUDGE") == "1" and frozen()):
        raise CustodyError(f"{dataset} is held out; readable only by the judge after the freeze")
