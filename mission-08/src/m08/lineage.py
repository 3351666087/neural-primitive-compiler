"""Embryonic / post-embryonic lineage paths from the WormAtlas lineage names (wormneuroatlas cell_lineage.txt), an
observation independent of the connectomes (Sulston et al.). A name such as "AB plapaaaapp" or "QR.paa" becomes the
division path from the zygote; blast-cell roots (QR, G2, W, ...) are expanded through their own entries; roots without
an entry (the ventral-cord P blasts) are attached under AB, where they arise, with an unknown intermediate path."""

from __future__ import annotations

import numpy as np

from .raw import path


def _table():
    rows = [line.split("\t") for line in path("wna_lineage").read_text().splitlines()[1:]]
    return {r[0].strip(): r[1].strip() for r in rows if len(r) > 1}


def expand(name, table, depth=0):
    """List of tokens from the root: e.g. ['P0', 'a', 'p', 'l', ...] (AB = P0.a, MS = P0.paa, C = P0.ppa, ...)."""
    s = table.get(name)
    if s is None or depth > 10:
        return None
    s = s.replace(".", " ").split()
    root, rest = s[0], "".join(s[1:])
    letters = list(rest)
    if root in ("P0", "Z"):
        return ["P0"] + letters
    up = expand(root, table, depth + 1)
    if up is None:
        up = expand("AB", table, depth + 1) + ["?" + root]          # unresolved blast: under AB, unknown path
    return up + letters


def paths(cells):
    t = _table()
    out = []
    for c in cells:
        p = expand(c, t)
        out.append(p if p is not None else ["?" + c])
    return out


def distance_matrix(cells):
    """Number of divisions from each neuron up to the last common ancestor and down to the other neuron;
    common-prefix depth as a second output."""
    ps = paths(cells)
    n = len(ps)
    D = np.zeros((n, n))
    P = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            a, b = ps[i], ps[j]
            k = 0
            while k < min(len(a), len(b)) and a[k] == b[k] and not a[k].startswith("?"):
                k += 1
            D[i, j] = len(a) + len(b) - 2 * k
            P[i, j] = k
    return D, P
