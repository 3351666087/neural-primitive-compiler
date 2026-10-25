"""Typed loaders for the C. elegans structural data (Witvliet et al. 2021; Cook et al. 2019; Brittin et al. 2021) and
the WormAtlas neuron list. Every loader goes through `custody.allow`, so a held-out dataset cannot be read by
development code (DATA_SPLITS_AND_CUSTODY.md).

Conventions (BIOLOGICAL_ASSUMPTIONS.md): chemical synapses only unless stated; direction pre -> post; autapses
dropped; a pair is connected if it has at least one synapse; neurons are those on the WormAtlas list, so muscles
(BWM-*), glia (CEPsh*, GLR*) and the excretory gland are excluded.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import custody
from .raw import path

# Witvliet et al. 2021, Fig. 1: hours after birth of the eight animals.
WITVLIET_AGE_H = {1: 0, 2: 5, 3: 8, 4: 16, 5: 23, 6: 27, 7: 50, 8: 50}
WITVLIET_STAGE = {1: "L1", 2: "L1", 3: "L1", 4: "L1", 5: "L2", 6: "L3", 7: "adult", 8: "adult"}


def neuron_names():
    df = pd.read_csv(path("wormatlas_names"), sep=";", comment="#", header=None)
    return set(df[0].str.strip())


def neuron_table():
    """WormAtlas list: name, lineage name, classification (one row per neuron)."""
    df = pd.read_csv(path("wormatlas_names"), sep=";", comment="#", header=None, names=["name", "detail", "lineage", "cls"])
    for c in df.columns:
        df[c] = df[c].astype(str).str.strip()
    return df.set_index("name")


def witvliet(k, kind="chemical"):
    """Pair table (pre, post, synapses) of Witvliet dataset k, neurons only."""
    custody.allow(f"witvliet_{k}")
    df = pd.read_excel(path(f"witvliet_{k}"))
    if set(df.columns) != {"pre", "post", "type", "synapses"}:
        raise ValueError(f"witvliet_{k}: unexpected columns {list(df.columns)}")
    if df.duplicated(["pre", "post", "type"]).any():
        raise ValueError(f"witvliet_{k}: duplicated (pre, post, type) rows")
    names = neuron_names()
    df = df[(df.type == kind) & df.pre.isin(names) & df.post.isin(names) & (df.pre != df.post)]
    if (df.synapses <= 0).any():
        raise ValueError(f"witvliet_{k}: non-positive synapse count")
    return df[["pre", "post", "synapses"]].reset_index(drop=True)


def nemanode(key, kind="chemical"):
    """Pair table from a NemaNode JSON (keys nema_witvliet_k, nema_white_jsh, nema_white_n2u), neurons only."""
    import json
    custody.allow(key)
    df = pd.DataFrame(json.loads(path(key).read_text()))
    names = neuron_names()
    df = df[(df.type == kind) & df.pre.isin(names) & df.post.isin(names) & (df.pre != df.post)]
    df = df.groupby(["pre", "post"], as_index=False)["synapses"].sum()
    return df


def cells_of(df):
    return set(df.pre) | set(df.post)


def present_in(k=None, key=None):
    """Neurons that appear in any record (chemical or electrical) of a data set."""
    if k is not None:
        custody.allow(f"witvliet_{k}")
        df = pd.read_excel(path(f"witvliet_{k}"))
    else:
        import json
        custody.allow(key)
        df = pd.DataFrame(json.loads(path(key).read_text()))
    names = neuron_names()
    return (set(df.pre) | set(df.post)) & names


def conn(cells, k=None, key=None, age_h=None, name=None, min_syn=1):
    """models.Conn for Witvliet data set k (cect xlsx) or a NemaNode key, over the reference list `cells`; an edge
    needs at least `min_syn` synapses."""
    from .models import Conn
    df = witvliet(k) if k is not None else nemanode(key)
    pres = present_in(k=k, key=key)
    mask = np.array([c in pres for c in cells])
    if age_h is None:
        age_h = WITVLIET_AGE_H[k]
    return Conn(name or (f"W{k}" if k is not None else key), float(age_h), matrix(df, cells), mask, min_syn)


# ---- features measured independently of the connectomes (BIOLOGICAL_ASSUMPTIONS.md section 2) ----

def positions(cells):
    """Skuhersky 2022 atlas (high-resolution head and tail version, the one Richter & Schneidman used), um."""
    df = pd.read_csv(path("sku_hires"), header=None).set_index(0)
    return df.loc[list(cells)].values.astype(float)


def birth_times(cells):
    """Pathak 2020 S5 table (minutes after fertilisation; transcribed from Sulston's lineages)."""
    df = pd.read_excel(path("pathak_s5"), sheet_name=0, engine="xlrd").set_index("Neuron")
    return df.loc[list(cells), "Birth time (min.)"].values.astype(float)


def cook_categories(cells):
    """Cook 2019 cell categories; HSNL/R (hermaphrodite-specific sheet) get their own category."""
    df = pd.read_excel(path("rs_celltypes"), sheet_name="sex-shared", header=0)
    df.columns = ["name", "type", "category", "notes", "x"]
    s = df.set_index("name")
    cat = s["category"].reindex(list(cells)).fillna("HSN")
    coarse = s["type"].reindex(list(cells)).fillna("motorneuron")
    return cat.values, coarse.values


def lr_class(cells):
    """Bilateral class: drop a trailing L/R when the counterpart exists (AVAL, AVAR -> AVA)."""
    cs = set(cells)
    out = []
    for c in cells:
        if c[-1] in "LR" and (c[:-1] + ("R" if c[-1] == "L" else "L")) in cs:
            out.append(c[:-1])
        else:
            out.append(c)
    return np.array(out)


def codes(labels):
    u = sorted(set(labels))
    m = {x: i for i, x in enumerate(u)}
    return np.array([m[x] for x in labels]), u


def matrix(df, cells):
    """Synapse-count matrix over the ordered list `cells` (pairs with cells outside the list are dropped)."""
    ix = {c: i for i, c in enumerate(cells)}
    M = np.zeros((len(cells), len(cells)))
    for p, q, s in zip(df.pre, df.post, df.synapses):
        if p in ix and q in ix:
            M[ix[p], ix[q]] += s
    np.fill_diagonal(M, 0)
    return M


def offdiag(n):
    return ~np.eye(n, dtype=bool)


class Blocked(Exception):
    """A registered analysis cannot be run on the data as found (recorded as BLOCKED, PRE_REGISTRATION.md A4.3)."""


def brittin_contacts(cells):
    """Membrane contact of every unordered neuron pair in Brittin et al. 2021 (Zenodo 4383277, adjacency.tar.bz2),
    {"JSH": n x n, "N2U": n x n}. The format was not inspected before the freeze; the reader follows the authors'
    parsetrakem2 (scripts/measure_adjacency.py, xml2csv.py): <layer name> elements holding <area> elements with
    <cell1>, <cell2> and <adjacency> (boundary length in pixels); contact = adjacency summed over layers. Files are
    assigned to animals by name ('jsh' or 'l4' -> JSH; 'n2u' or 'adult' -> N2U). Raises Blocked otherwise."""
    import tarfile
    import xml.etree.ElementTree as ET
    src = path("brittin_adjacency")
    out_dir = src.parent / "adjacency_extracted"
    if not out_dir.exists():
        out_dir.mkdir()
        with tarfile.open(src, "r:bz2") as tf:
            tf.extractall(out_dir, filter="data")
    xmls = sorted(p for p in out_dir.rglob("*.xml") if not p.name.startswith("._"))
    pick = {}
    for animal, keys in (("JSH", ("jsh", "l4")), ("N2U", ("n2u", "adult"))):
        hits = [p for p in xmls if any(k in p.name.lower() for k in keys)]
        if len(hits) != 1:
            raise Blocked(f"{animal}: {len(hits)} matching files among {[p.name for p in xmls]}")
        pick[animal] = hits[0]
    ix = {c: i for i, c in enumerate(cells)}
    out = {}
    for animal, p in pick.items():
        M = np.zeros((len(cells), len(cells)))
        n_area, names = 0, set()
        for layer in ET.parse(p).getroot().iter("layer"):
            for area in layer.iter("area"):
                c1, c2, adj = area.findtext("cell1"), area.findtext("cell2"), area.findtext("adjacency")
                if c1 is None or c2 is None or adj is None:
                    continue
                n_area += 1
                names.update((c1, c2))
                if c1 in ix and c2 in ix and c1 != c2:
                    M[ix[c1], ix[c2]] += float(adj)
                    M[ix[c2], ix[c1]] += float(adj)
        found = len(names & set(cells))
        if n_area == 0 or found < 0.5 * len(cells):
            raise Blocked(f"{animal} ({p.name}): {n_area} area records, {found} of {len(cells)} neurons named")
        out[animal] = M
    out["files"] = {a: p.name for a, p in pick.items()}
    return out
