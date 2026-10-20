"""Cognitive IR: a JSON description of primitive instances over typed index spaces, compiled to IF neurons.

The IR has no escape hatch: nodes are CMR / SEL / ANY / GATE, map expressions come from a fixed
vocabulary of coordinate maps (pullback form), and there are no user functions. Constructors (the LLM
route, the automatic route in cog/learn.py, the grammar baseline) emit IR; only this compiler emits neurons.

Map expressions (pullback: for each target coordinate, the list of source coordinates / data channels):
  ["id"] ["zero"] ["load", bundle]                         any space
  ["rot90"] ["rot180"] ["rot270"] ["fliph"] ["flipv"] ["transpose"] ["dilate"]
  ["shift", dx, dy, "clip"|"wrap"]                          grid (forward: point moves by (dx, dy))
  ["store_row", k, bundle] ["swap_rows", j, k] ["copy_row", j, k] ["clear_row", k]   table (rows = objects)
  ["on_slice", k, <grid map>] ["place", k, bundle]          objgrid (slice k = object k on its grid)
  ["compose", m1, m2, ...]                                   apply m1, then m2, ...
  ["table", {"x,y": [["c", "x,y"] | ["d", channel] | ["one"]], ...}]   literal (used by learned constructions)
"""

from __future__ import annotations

import json
from typing import Any

from npc.network import Network

from .prims import ONE, Builder, any_, cmr, gate, sel

Coord = tuple


class IRError(ValueError):
    pass


def cname(bundle: str, coord: Coord) -> str:
    return bundle + "_" + "_".join(str(c) for c in coord) if coord else bundle


def space_coords(sp: dict) -> list[Coord]:
    kind, dims = sp["kind"], sp["dims"]
    if kind == "grid":
        (N,) = dims
        return [(x, y) for y in range(N) for x in range(N)]
    if kind == "table":
        K, V = dims
        return [(k, v) for k in range(K) for v in range(V)]
    if kind == "objgrid":
        K, N = dims
        return [(k, x, y) for k in range(K) for y in range(N) for x in range(N)]
    if kind == "vec":
        (n,) = dims
        return [(i,) for i in range(n)]
    raise IRError(f"unknown space kind {kind}")


# ------------------------------------------------------------------ maps (pullback form)
def _grid_src(op: str, args: list, N: int, x: int, y: int) -> list[Coord]:
    M = N - 1
    if op == "id":
        return [(x, y)]
    if op == "rot90":
        return [(y, M - x)]
    if op == "rot180":
        return [(M - x, M - y)]
    if op == "rot270":
        return [(M - y, x)]
    if op == "fliph":
        return [(M - x, y)]
    if op == "flipv":
        return [(x, M - y)]
    if op == "transpose":
        return [(y, x)]
    if op == "shift":
        dx, dy, mode = args
        sx, sy = x - dx, y - dy
        if mode == "wrap":
            return [(sx % N, sy % N)]
        return [(sx, sy)] if 0 <= sx <= M and 0 <= sy <= M else []
    if op == "dilate":
        return [(a, b) for a, b in [(x, y), (x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)] if 0 <= a <= M and 0 <= b <= M]
    raise IRError(f"map {op} is not defined on grids")


def map_rules(expr: list, sp: dict) -> dict[Coord, list]:
    """Pullback table: target coord -> list of sources (("c", coord) | ("d", channel) | ONE)."""
    if not isinstance(expr, list) or not expr:
        raise IRError(f"bad map expression {expr!r}")
    op, args = expr[0], expr[1:]
    coords = space_coords(sp)
    kind, dims = sp["kind"], sp["dims"]
    if op == "id":
        return {j: [("c", j)] for j in coords}
    if op == "zero":
        return {j: [] for j in coords}
    if op == "load":
        (bundle,) = args
        return {j: [("d", cname(bundle, j))] for j in coords}
    if op == "compose":
        tables = [map_rules(m, sp) for m in args]
        cur = tables[0]
        for nxt in tables[1:]:
            new = {}
            for j in coords:
                srcs = []
                for s in nxt.get(j, []):
                    if s[0] == "c":
                        srcs += cur.get(s[1], [])
                    else:
                        srcs.append(s)  # data/one sources are read at the last step only
                new[j] = _dedup(srcs)
            cur = new
        return cur
    if op == "table":
        (tab,) = args
        out = {j: [] for j in coords}
        for key, srcs in tab.items():
            j = tuple(int(v) for v in key.split(","))
            out[j] = [("c", tuple(int(v) for v in s[1].split(","))) if s[0] == "c" else (("d", s[1]) if s[0] == "d" else ONE)
                      for s in srcs]
        return out
    if kind == "grid":
        (N,) = dims
        return {(x, y): [("c", s) for s in _grid_src(op, args, N, x, y)] for (x, y) in coords}
    if kind == "table":
        K, V = dims
        out = {j: [("c", j)] for j in coords}
        if op == "store_row":
            k, bundle = args
            for v in range(V):
                out[(k, v)] = [("d", cname(bundle, (v,)))]
        elif op == "swap_rows":
            j, k = args
            for v in range(V):
                out[(j, v)], out[(k, v)] = [("c", (k, v))], [("c", (j, v))]
        elif op == "copy_row":
            j, k = args
            for v in range(V):
                out[(k, v)] = [("c", (j, v))]
        elif op == "clear_row":
            (k,) = args
            for v in range(V):
                out[(k, v)] = []
        else:
            raise IRError(f"map {op} is not defined on tables")
        return out
    if kind == "objgrid":
        K, N = dims
        out = {j: [("c", j)] for j in coords}
        if op == "on_slice":
            k, inner = args
            g = map_rules(inner, {"kind": "grid", "dims": [N]})
            for (x, y), srcs in g.items():
                out[(k, x, y)] = [("c", (k,) + s[1]) if s[0] == "c" else s for s in srcs]
        elif op == "place":
            k, bundle = args
            for y in range(N):
                for x in range(N):
                    out[(k, x, y)] = [("d", cname(bundle, (x, y)))]
        else:
            raise IRError(f"map {op} is not defined on objgrids")
        return out
    raise IRError(f"map {op} undefined for space {kind}")


def _dedup(xs: list) -> list:
    out = []
    for x in xs:
        if x not in out:
            out.append(x)
    return out


def region(where: dict, sp: dict) -> list[Coord]:
    """Conjunction of conditions. row/col accept an index or "last" (size-independent)."""
    coords = space_coords(sp)
    N = sp["dims"][-1] if sp["kind"] in ("grid", "objgrid") else None
    val = lambda v: (N - 1) if v == "last" else v
    if not where or set(where) - {"all", "row", "col", "slice", "set"}:
        raise IRError(f"bad region {where}")
    out = coords
    if "row" in where:
        out = [c for c in out if c[-1] == val(where["row"])]
    if "col" in where:
        out = [c for c in out if c[-2] == val(where["col"])]
    if "slice" in where:
        axis, v = where["slice"]
        out = [c for c in out if c[axis] == v]
    if "set" in where:
        s = {tuple(c) for c in where["set"]}
        out = [c for c in out if c in s]
    return out


# ------------------------------------------------------------------ compiler
def compile_ir(prog: dict, iface: dict) -> Network:
    """Compile an IR program against a task interface (channel names, bundle spaces). Raises IRError."""
    b = Builder(prog.get("name", "ir"), max_delay=prog.get("max_delay", 4))
    sig: dict[str, Any] = {}  # id -> scalar signal name | {coord: signal}
    spaces: dict[str, dict] = {}
    forward: set[str] = set()
    for l in iface["letters"]:
        sig[l["name"]] = b.input(l["name"])
    for bundle, sp in {**iface["data"], **iface["queries"]}.items():
        sig[bundle] = {c: b.input(cname(bundle, c)) for c in space_coords(sp)}
        spaces[bundle] = sp
    for node in prog["nodes"]:
        nid, op = node["id"], node["op"]
        if nid in sig:
            raise IRError(f"duplicate id {nid}")
        if op == "CMR":
            sp = node.get("space") or iface["state_space"]
            coords = space_coords(sp)
            rules, chans = {}, {}
            for lname, spec in node["letters"].items():
                if lname in sig and not isinstance(sig[lname], str):
                    raise IRError(f"CMR {nid}: letter {lname} must be a scalar signal")
                if lname not in sig:  # forward reference to a scalar node defined later (feedback loops)
                    forward.add(lname)
                rules[lname] = map_rules(spec["map"], sp)
                chans[lname] = sig.get(lname, lname)
            sig[nid] = cmr(b, nid, coords, rules, chans)
            spaces[nid] = sp
        elif op == "ANY":
            src = _bundle(sig, node["of"])
            sp = spaces[node["of"]]
            sig[nid] = any_(b, nid, [src[c] for c in region(node.get("where", {"all": True}), sp)], node.get("delay", 1))
        elif op == "SEL":
            tab = _bundle(sig, node["of"])
            sp = spaces[node["of"]]
            selb = _bundle(sig, node["select"])
            axis = node["axis"]
            pairs: dict = {}
            axes = list(range(len(next(iter(tab))))) if axis == "all" else ([axis] if isinstance(axis, int) else list(axis))
            for c, x in tab.items():
                a = tuple(c[i] for i in axes)
                rest = tuple(c[i] for i in range(len(c)) if i not in axes)
                if a not in selb:
                    raise IRError(f"SEL {nid}: selector {node['select']} has no channel for {a}")
                pairs.setdefault(rest, []).append((a, selb[a], x))
            outs = sel(b, nid, pairs, node.get("delay", 1), node.get("xdelay", 1))
            sig[nid] = outs[()] if list(outs) == [()] else outs
            rest_dims = [d for i, d in enumerate(_dims_list(sp)) if i not in axes]
            if rest_dims:
                spaces[nid] = {"kind": "vec", "dims": rest_dims} if len(rest_dims) == 1 else {"kind": "?", "dims": rest_dims}
        elif op == "SELT":  # literal pair table: {"suffix": [[selector channel, "coord"], ...]}
            tab = _bundle(sig, node["of"])
            pairs = {}
            for suffix, lst in node["pairs"].items():
                key = tuple(int(v) for v in suffix.split("_")) if suffix else ()
                pairs[key] = [(ch, b.input(ch) if ch not in b.neurons else ch, tab[tuple(int(v) for v in ck.split(","))])
                              for ch, ck in lst]
            outs = sel(b, nid, pairs, node.get("delay", 1), node.get("xdelay", 1))
            sig[nid] = outs[()] if list(outs) == [()] else outs
        elif op == "GATE":
            pos, neg = node.get("pos", []), node.get("neg", [])
            refs = [sig[r] for r, _ in pos + neg]
            if any(isinstance(r, dict) for r in refs):  # elementwise over a common bundle space
                keys = next(r for r in refs if isinstance(r, dict)).keys()
                out = {}
                for c in keys:
                    pick = lambda name: sig[name][c] if isinstance(sig[name], dict) else sig[name]
                    out[c] = gate(b, f"{nid}[{','.join(map(str, c))}]", [(pick(r), d) for r, d in pos],
                                  [(pick(r), d) for r, d in neg])
                sig[nid] = out
                src_space = next(spaces[r] for r, _ in pos + neg if isinstance(sig[r], dict) and r in spaces)
                spaces[nid] = src_space
            else:
                sig[nid] = gate(b, nid, [(sig[r], d) for r, d in pos], [(sig[r], d) for r, d in neg])
        else:
            raise IRError(f"unknown op {op}")
    missing = [f for f in forward if f not in b.neurons]
    if missing:
        raise IRError(f"forward references never defined as scalar nodes: {missing}")
    for port, ref in prog["outputs"].items():
        s = sig[ref]
        if isinstance(s, dict):
            for c, n in s.items():
                b.output(cname(port, c), n)
        else:
            b.output(port, s)
    return b.build()


def _bundle(sig: dict, ref: str) -> dict:
    s = sig[ref]
    if not isinstance(s, dict):
        raise IRError(f"{ref} is a scalar, a bundle is required")
    return s


def _dims_list(sp: dict) -> list:
    if sp["kind"] == "grid":
        return [sp["dims"][0], sp["dims"][0]]
    if sp["kind"] == "objgrid":
        return [sp["dims"][0], sp["dims"][1], sp["dims"][1]]
    return list(sp["dims"])


def ir_size(prog: dict) -> int:
    """Description length proxy: number of JSON tokens of the program (excluding the name)."""
    p = dict(prog)
    p.pop("name", None)
    return len(json.dumps(p, separators=(",", ":")).replace("[", " ").replace("]", " ").replace(",", " ").split())
