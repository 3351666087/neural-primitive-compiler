"""Route A, automatic constructor: black-box experiments at small sizes -> parametric IR -> any size.

No weights are searched. What is searched: (1) experiments on the oracle (counted), (2) a match of each
learned table against the finite IR vocabulary (counted). Construction at sizes beyond the probed ones
uses no oracle call at all.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .ir import map_rules, region, space_coords
from .learn import active_refine, learn, match_vocab, recheck


INDEX_MAPS = {"store_row": 1, "clear_row": 1, "swap_rows": 2, "copy_row": 2, "on_slice": 1, "place": 1}


def _template(name: str, m: list):
    """Anti-unify a (command name, map) pair: if the map's index parameters, written as digits, form the
    name's suffix, return (base, nidx, map template with "$i" placeholders); else None."""
    if not isinstance(m, list) or not m or m[0] not in INDEX_MAPS:
        return None
    n = INDEX_MAPS[m[0]]
    idx = m[1:1 + n]
    if not all(isinstance(i, int) for i in idx):
        return None
    suffix = "".join(str(i) for i in idx)
    if not name.endswith(suffix):
        return None
    tmpl = [m[0]] + [f"${i}" for i in range(n)] + list(m[1 + n:])
    return name[: len(name) - len(suffix)], n, tmpl


def _instantiate(tmpl, vals):
    if isinstance(tmpl, dict):
        return {k: _instantiate(v, vals) for k, v in tmpl.items()}
    if isinstance(tmpl, list):
        return [_instantiate(t, vals) for t in tmpl]
    if isinstance(tmpl, str) and tmpl.startswith("$"):
        return vals[int(tmpl[1:])]
    return tmpl


@dataclass
class Rules:
    """Size-independent description: exact entries plus indexed families learned by anti-unification."""
    letters_exact: dict = field(default_factory=dict)      # name -> map
    letters_family: dict = field(default_factory=dict)     # (base, nidx) -> map template
    outputs_exact: dict = field(default_factory=dict)      # name -> node (without id)
    outputs_family: dict = field(default_factory=dict)     # (base, nidx) -> node template ("$0" in slice)

    def instantiate(self, iface: dict) -> dict:
        letters = {}
        for l in iface["letters"]:
            name = l["name"]
            if name in self.letters_exact:
                letters[name] = {"map": self.letters_exact[name]}
                continue
            for (base, n), tmpl in self.letters_family.items():
                rest = name[len(base):]
                if name.startswith(base) and len(rest) == n and rest.isdigit():
                    letters[name] = {"map": _instantiate(tmpl, [int(ch) for ch in rest])}
                    break
            else:
                raise KeyError(f"no rule for command {name}")
        nodes = [{"id": "mem", "op": "CMR", "letters": letters}]
        outputs = {"img": "mem"}
        for o in iface["outputs"]:
            if o["kind"] == "img":
                continue
            name = o["name"]
            node = self.outputs_exact.get(name)
            if node is None:
                for (base, n), tmpl in self.outputs_family.items():
                    rest = name[len(base):]
                    if name.startswith(base) and len(rest) == n and rest.isdigit():
                        node = _instantiate(tmpl, [int(ch) for ch in rest])
                        break
            if node is None:
                raise KeyError(f"no rule for output {name}")
            nodes.append(dict(node, id=name))
            outputs[name] = name
        return {"name": "auto", "max_delay": 6, "nodes": nodes, "outputs": outputs}


@dataclass
class AutoResult:
    status: str                      # "BUILT" | "FAIL"
    program: dict | None = None
    rules: Rules | None = None
    reason: str = ""
    oracle_traces: int = 0
    vocab_candidates: int = 0
    time_s: float = 0.0
    notes: list = field(default_factory=list)


REGION_CANDIDATES_GRID = [{"row": 0}, {"row": "last"}, {"col": 0}, {"col": "last"}, {"all": True}]


def _region_candidates(sp: dict) -> list[dict]:
    if sp["kind"] == "grid":
        return REGION_CANDIDATES_GRID
    if sp["kind"] == "objgrid":
        K = sp["dims"][0]
        out = []
        for k in range(K):
            out += [dict(c, slice=[0, k]) if "all" not in c else {"slice": [0, k]} for c in REGION_CANDIDATES_GRID]
        return out + REGION_CANDIDATES_GRID
    if sp["kind"] == "table":
        K, V = sp["dims"]
        return [{"slice": [0, k]} for k in range(K)] + [{"slice": [1, v]} for v in range(V)] + [{"all": True}]
    return [{"all": True}]


SEL_AXES = {"grid": ["all"], "table": [0, 1], "objgrid": [[1, 2], 0, "all"]}


def construct_auto(ifaces: list[dict], oracles: list, n_traces: int = 300, T: int = 16) -> AutoResult:
    """ifaces/oracles for the probe sizes (two smallest). Returns a size-independent IR program."""
    t0 = time.perf_counter()
    res = AutoResult("FAIL")
    learned = []
    for iface, orc in zip(ifaces, oracles):
        L = learn(iface, orc, n_traces=n_traces, T=T, seed=1)
        L = active_refine(iface, orc, L)
        recheck(iface, orc, L)
        res.oracle_traces += n_traces + getattr(L, "probes", 0) + 200
        learned.append(L)
    iface0 = ifaces[0]
    letters = {}
    for l in iface0["letters"]:
        name = l["name"]
        if l["cond_delay"] is not None:
            res.reason = f"conditional command {name}: data-dependent, outside the union schema (needs a gated composition)"
            break
        tabs = [L.letters.get(name) for L in learned]
        if any(not isinstance(t, dict) for t in tabs):
            res.reason = f"command {name}: {next(t for t in tabs if not isinstance(t, dict))} (outside the union schema)"
            break
        common = None
        for iface, tab in zip(ifaces, tabs):
            data = [l2["data"] for l2 in iface["letters"] if l2["name"] == name and l2["data"]]
            hits = {repr(m): m for m in match_vocab(tab, iface["state_space"], data)}
            res.vocab_candidates += 1
            common = hits if common is None else {k: v for k, v in common.items() if k in hits}
        if not common:
            res.reason = f"command {name}: learned tables do not match one vocabulary map at every probed size"
            break
        letters[name] = {"map": sorted(common.values(), key=lambda m: len(repr(m)))[0]}
    # letters present only at the larger probe size are learned there too (their maps feed the families)
    extra = {}
    for l in ifaces[-1]["letters"]:
        name = l["name"]
        if name in letters or l["cond_delay"] is not None:
            continue
        tab = learned[-1].letters.get(name)
        if not isinstance(tab, dict):
            res.reason = res.reason or f"command {name}: outside the union schema"
            continue
        data = [l["data"]] if l["data"] else []
        hits = match_vocab(tab, ifaces[-1]["state_space"], data)
        res.vocab_candidates += 1
        if hits:
            extra[name] = sorted(hits, key=lambda m: len(repr(m)))[0]
    if res.reason:
        res.time_s = time.perf_counter() - t0
        return res
    nodes = [{"id": "mem", "op": "CMR", "letters": letters}]
    outputs = {"img": "mem"}
    for o in iface0["outputs"]:
        if o["kind"] == "img":
            continue
        name, lag = o["name"], o["lag"]
        structs = [L.outputs.get(name) for L in learned]
        if any(not isinstance(s, dict) or any(v == "nonlinear" for v in s.values()) for s in structs):
            res.reason = f"output {name}: not a disjunction of coordinates or selector-gated coordinates"
            break
        kinds = {v[0] for s in structs for v in s.values()}
        if kinds == {"any"}:
            ok_where = None
            for cand in _region_candidates(ifaces[0]["state_space"]):
                good = True
                for iface, s in zip(ifaces, structs):
                    (ch, (_, feats)), = s.items()
                    try:
                        reg = set(region(cand, iface["state_space"]))
                    except Exception:
                        good = False
                        break
                    if reg != {f[1] for f in feats}:
                        good = False
                        break
                res.vocab_candidates += 1
                if good:
                    ok_where = cand
                    break
            if ok_where is None:
                res.reason = f"output {name}: learned region matches no region in the vocabulary"
                break
            nodes.append({"id": name, "op": "ANY", "of": "mem", "where": ok_where, "delay": lag - 2})
            outputs[name] = name
        elif kinds == {"sel"}:
            ok_axis = None
            qname = next(iter(ifaces[0]["queries"]), None)
            for axis in SEL_AXES.get(ifaces[0]["state_space"]["kind"], []):
                for qb in ifaces[0]["queries"]:
                    good = True
                    for iface, s in zip(ifaces, structs):
                        want = _sel_pairs(iface, axis, qb, name)
                        got = {ch: sorted((f[1], f[2]) for f in feats) for ch, (_, feats) in s.items()}
                        if want != got:
                            good = False
                            break
                    res.vocab_candidates += 1
                    if good:
                        ok_axis = (axis, qb)
                        break
                if ok_axis:
                    break
            if ok_axis is None:
                res.reason = f"output {name}: learned selection matches no axis selection"
                break
            nodes.append({"id": name, "op": "SEL", "of": "mem", "select": ok_axis[1], "axis": ok_axis[0],
                          "delay": lag - 1, "xdelay": lag - 2})
            outputs[name] = name
        else:
            res.reason = f"output {name}: mixed structure"
            break
    res.time_s = time.perf_counter() - t0
    if res.reason:
        return res
    rules = Rules()
    groups = {}
    for name, m in list({k: v["map"] for k, v in letters.items()}.items()) + list(extra.items()):
        t = _template(name, m)
        if t is None:
            rules.letters_exact[name] = m
        else:
            base, n, tmpl = t
            groups.setdefault((base, n, repr(tmpl)), (tmpl, []))[1].append(name)
    for (base, n, _), (tmpl, names) in groups.items():
        if len(names) >= 2:
            rules.letters_family[(base, n)] = tmpl       # anti-unified family (seen at >= 2 indices)
        else:
            for nm in names:
                rules.letters_exact[nm] = _instantiate(tmpl, [int(ch) for ch in nm[len(base):]])
    for node in nodes[1:]:
        nm = node["id"]
        body = {k: v for k, v in node.items() if k != "id"}
        sl = body.get("where", {}).get("slice") if body.get("op") == "ANY" else None
        if sl and sl[0] == 0 and nm.endswith(str(sl[1])):
            base = nm[: len(nm) - len(str(sl[1]))]
            tmpl = dict(body, where=dict(body["where"], slice=[0, "$0"]))
            rules.outputs_family[(base, 1)] = tmpl
        else:
            rules.outputs_exact[nm] = body
    res.status = "BUILT"
    res.rules = rules
    res.program = {"name": "auto", "max_delay": 6, "nodes": nodes, "outputs": outputs}
    return res


def _sel_pairs(iface: dict, axis, qb: str, oname: str) -> dict:
    from .ir import cname
    sp = iface["state_space"]
    coords = space_coords(sp)
    out = {}
    for c in coords:
        axes = list(range(len(c))) if axis == "all" else ([axis] if isinstance(axis, int) else list(axis))
        a = tuple(c[i] for i in axes)
        rest = tuple(c[i] for i in range(len(c)) if i not in axes)
        ch = cname(oname, rest)
        out.setdefault(ch, []).append((cname(qb, a), c))
    return {k: sorted(v) for k, v in out.items()}
