"""Minimal counterexample for policy S2 ("ignore explanations whose test prediction is undetermined").

The generator recolours blocks BY SIZE (size 1 -> 3, size 2 -> 4, size 3 -> 5). In training, size and colour are
perfectly correlated (colour 1 has size 1, colour 2 has size 2), so "recolour by colour" is equally consistent.
The test input contains a block of colour 2 and size 3 next to a single cell of colour 1: the size explanation
is undetermined (size 3 never seen), while the colour, size-rank, largest and smallest explanations are determined
and agree with each other. S0 abstains; S2 answers with the colour explanation, and is wrong for this
generator. S2 is right only if the test input is promised to be answerable by the intended explanation, which is
a property of how ARC tasks are built, not of the data.

  python -I mission-04/experiments/r1_repr/s2_counterexample.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blocks as B  # noqa: E402
import run_r1b as RB  # noqa: E402

TRUE_LUT = {1: 3, 2: 4, 3: 5}


def recolour_by_size(g):
    out = np.zeros_like(g)
    for b in B.partition(g, "A4-NONBG"):
        for x in b:
            out[x] = TRUE_LUT[len(b)]
    return out


def grid(cells, shape=(5, 5)):
    g = np.zeros(shape, int)
    for (r, c), col in cells.items():
        g[r, c] = col
    return g


train_inputs = [grid({(0, 0): 1, (2, 2): 2, (2, 3): 2}), grid({(4, 4): 1, (0, 3): 2, (1, 3): 2, (3, 0): 1})]
train = [(I, recolour_by_size(I)) for I in train_inputs]
test_I = grid({(0, 0): 2, (0, 1): 2, (0, 2): 2, (3, 3): 1})
tests = [(test_I, recolour_by_size(test_I))]

if __name__ == "__main__":
    rows = RB.task_explanations(train, tests)
    print("consistent explanations:", sorted({r["type"] for r in rows}, key=repr))
    print("S0 (strict):", RB.decide(rows))
    det = [r for r in rows if r["determined"]]
    print("determined explanation types:", sorted({r["type"][2] for r in det}))
    print("S2 (permissive):", RB.decide(det), "(the generator's answer for the size-3 block is colour", TRUE_LUT[3], ")")
