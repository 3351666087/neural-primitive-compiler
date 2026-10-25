"""CPU-time accounting and result records (RESOURCE_BUDGET.md). Every experiment script writes one JSON record per
run with its git commit, inputs' hashes, seeds, CPU seconds (self + children) and peak RSS; ledgers sum the records."""

from __future__ import annotations

import json
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"


def cpu_seconds():
    s = resource.getrusage(resource.RUSAGE_SELF)
    c = resource.getrusage(resource.RUSAGE_CHILDREN)
    return s.ru_utime + s.ru_stime + c.ru_utime + c.ru_stime


def peak_rss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)      # bytes on macOS


def git_commit():
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    except Exception:
        return None


class Run:
    def __init__(self, gate, name, **meta):
        self.gate, self.name, self.meta = gate, name, meta
        self.t0, self.c0 = time.time(), cpu_seconds()

    def write(self, results, sub=None):
        from .raw import FILES, _CHECKED
        rec = {"gate": self.gate, "name": self.name, "meta": self.meta, "commit": git_commit(),
               "python": sys.version.split()[0], "platform": platform.platform(),
               "inputs": {k: FILES[k][3] for k in sorted(_CHECKED)},
               "wall_s": round(time.time() - self.t0, 2), "cpu_s": round(cpu_seconds() - self.c0, 2),
               "peak_rss_mb": round(peak_rss_mb(), 1), "results": results}
        out = RESULTS / self.gate / (sub or "")
        out.mkdir(parents=True, exist_ok=True)
        p = out / f"{self.name}.json"
        p.write_text(json.dumps(rec, indent=1, default=float))
        return p


def total_cpu_hours(gate):
    tot = 0.0
    for p in (RESULTS / gate).rglob("*.json"):
        try:
            tot += json.loads(p.read_text()).get("cpu_s", 0.0)
        except Exception:
            pass
    return tot / 3600.0
