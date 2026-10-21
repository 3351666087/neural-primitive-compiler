"""G0-T1: field-level information flow of the Mission 05 trust base (static AST scan + dynamic access log).

Static: for every module under mission-05/experiments, src/cog and mission-06/experiments: its declared side (module
docstring: JUDGE SIDE / CONSTRUCTOR SIDE / unlabelled), its imports, and every subscript of a truth-table field
("applicability_cex", "max_by_N", "cex", "preserves", "damage") on a name bound to truth tables (tr, trs, tr5, and loop
variables over them), with the enclosing function.
Dynamic: the three table builders (a_dsl.a_tables, zplus.a_tables_plus, zpp.a_tables_pp) run on the library instances
with truth tables wrapped in a proxy that logs every key path read; then A-P and A-P' run with every judge entry point
replaced by a function that raises.
Isolation (G0.2): mission-06 modules labelled CONSTRUCTOR SIDE must not import truth or judge modules.

  python -I trust_flow.py        # writes trust_flow.json
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
M05 = REPO / "mission-05" / "experiments"
FIELDS = {"applicability_cex", "max_by_N", "cex", "preserves", "damage"}
TRUTH_NAMES = {"tr", "trs", "tr5"}
JUDGE_MODULES = {"env", "cir_interp", "instances", "feasibility", "net_loop", "j2", "pool", "selftest"}


def side_of(doc):
    if not doc:
        return "UNLABELLED"
    if "JUDGE SIDE" in doc:
        return "JUDGE"
    if "CONSTRUCTOR SIDE" in doc:
        return "CONSTRUCTOR"
    return "UNLABELLED"


def root_name(node):
    while isinstance(node, (ast.Subscript, ast.Attribute, ast.Call)):
        node = node.value if not isinstance(node, ast.Call) else node.func
    return node.id if isinstance(node, ast.Name) else None


class Scan(ast.NodeVisitor):
    def __init__(self):
        self.func = ["<module>"]
        self.reads = []
        self.imports = set()
        self.alias = {}                         # loop variable -> truth name it iterates over

    def visit_FunctionDef(self, node):
        self.func.append(node.name)
        self.generic_visit(node)
        self.func.pop()

    def visit_Import(self, node):
        for a in node.names:
            self.imports.add(a.name.split(".")[0])

    def visit_ImportFrom(self, node):
        if node.module:
            self.imports.add(node.module.split(".")[0])

    def visit_For(self, node):
        it = node.iter
        if isinstance(it, ast.Call) and isinstance(it.func, ast.Attribute) and root_name(it.func.value) in TRUTH_NAMES:
            for t in ast.walk(node.target):
                if isinstance(t, ast.Name):
                    self.alias[t.id] = root_name(it.func.value)
        if root_name(it) in TRUTH_NAMES and isinstance(it, ast.Subscript):
            self.reads.append({"function": self.func[-1], "line": node.lineno, "kind": "iterate", "expr": ast.unparse(it)})
        self.generic_visit(node)

    def visit_Subscript(self, node):
        sl = node.slice
        if isinstance(sl, ast.Constant) and sl.value in FIELDS:
            r = root_name(node.value)
            if r in TRUTH_NAMES or self.alias.get(r) in TRUTH_NAMES:
                self.reads.append({"function": self.func[-1], "line": node.lineno, "kind": "value", "field": sl.value,
                                   "expr": ast.unparse(node)})
        self.generic_visit(node)


def static():
    files = sorted(M05.rglob("*.py")) + sorted((REPO / "src" / "cog").glob("*.py")) + sorted((REPO / "mission-06" / "experiments").rglob("*.py"))
    out = {}
    for f in files:
        if "__pycache__" in f.parts:
            continue
        tree = ast.parse(f.read_text())
        sc = Scan()
        sc.visit(tree)
        rel = str(f.relative_to(REPO))
        out[rel] = {"side": side_of(ast.get_docstring(tree)), "imports": sorted(sc.imports), "truth_reads": sc.reads,
                    "imports_truth": "truth" in sc.imports, "imports_judge": sorted(sc.imports & JUDGE_MODULES)}
    return out


class Proxy:
    """Wraps a truth table; logs every key path read (including iteration)."""

    def __init__(self, data, path, log):
        self._d, self._p, self._log = data, path, log

    def _wrap(self, v, p):
        return Proxy(v, p, self._log) if isinstance(v, dict) else v

    def __getitem__(self, k):
        p = self._p + (k if self._p == () else _field(k),)
        self._log.add(p)
        return self._wrap(self._d[k], p)

    def get(self, k, default=None):
        return self[k] if k in self._d else default

    def __contains__(self, k):
        return k in self._d

    def __iter__(self):
        self._log.add(self._p + ("<iterate keys>",))
        return iter(self._d)

    def items(self):
        self._log.add(self._p + ("<items>",))
        return [(k, self._wrap(v, self._p + (_field(k),))) for k, v in self._d.items()]

    def keys(self):
        self._log.add(self._p + ("<keys>",))
        return self._d.keys()

    def values(self):
        self._log.add(self._p + ("<values>",))
        return [self._wrap(v, self._p + ("*",)) for v in self._d.values()]

    def __len__(self):
        return len(self._d)


def _field(k):
    return k if isinstance(k, str) and not ("|" in k or k.startswith(("LIB-", "KD", "OUT", "OOW", "ORDER", "ZONE", "GROUP"))) else "<key>"


def dynamic():
    for p in ("lib", "judge", "pilots", "g3", "r7", "r8"):
        sys.path.insert(0, str(M05 / p))
    import a_dsl
    import construct as C
    import dsl
    import truth
    import zplus
    import zpp
    from run_pa3 import goals
    lib = json.loads((M05 / "g3" / "specs_library.json").read_text())["specs"]
    inst = [(k, a) for sp in lib for k, a in dsl.instances(sp)]
    by = {s["id"]: s for s in lib}
    tr, _ = truth.tables([(k, a, dsl.make_select(by[k.split("|")[0]])) for k, a in inst], Ns=(3, 4, 5))
    res = {}
    tables = {}
    for name, fn in (("a_dsl.a_tables", a_dsl.a_tables), ("zplus.a_tables_plus", zplus.a_tables_plus),
                     ("zpp.a_tables_pp", zpp.a_tables_pp)):
        log = set()
        tables[name] = fn(lib, inst, {k: Proxy(v, ("<instance>",), log) for k, v in tr.items()})
        res[name] = sorted(" / ".join(map(str, p)) for p in log)

    def boom(*a, **k):
        raise RuntimeError("judge called")
    for mod, names in ((C.CI, ("judge_set", "run_closed_loop")), (C.INS, ("v_train", "v_unseen", "v_mc6", "enumerate_all"))):
        for nm in names:
            setattr(mod, nm, boom)
    C.judge_all = boom
    G = goals()
    built, errors = 0, []
    for gid, spec in G.items():
        for route, fn in (("A-P'", C.construct_app), ("A-P", C.construct_ap)):
            try:
                r = fn(spec, lib, tables["zpp.a_tables_pp"], "TZ")
                built += r["status"] == "CONSTRUCTED"
            except RuntimeError as e:
                errors.append(f"{gid} {route}: {e}")
    res["constructors_with_judge_poisoned"] = {"goals": len(G), "constructed (both routes, N<=5 truth)": built,
                                               "judge_calls": errors}
    return res


def main():
    st = static()
    flow = {f: {k: v for k, v in r.items() if k != "imports"} for f, r in st.items() if r["truth_reads"] or r["imports_truth"]}
    readers = sorted({(f, x["function"], x.get("field", x["kind"])) for f, r in st.items() for x in r["truth_reads"]})
    m06 = {f: r for f, r in st.items() if f.startswith("mission-06")}
    isolation = {f: {"side": r["side"], "imports_truth": r["imports_truth"], "imports_judge": r["imports_judge"]}
                 for f, r in m06.items()}
    iso_bad = [f for f, r in isolation.items() if r["side"] == "CONSTRUCTOR" and (r["imports_truth"] or r["imports_judge"])]
    out = {"static": {"modules": {f: {"side": r["side"], "imports": r["imports"]} for f, r in st.items()},
                      "truth_flow": flow, "truth_readers": [list(x) for x in readers]},
           "mission06_isolation": {"modules": isolation, "violations": iso_bad},
           "dynamic": dynamic()}
    (HERE / "trust_flow.json").write_text(json.dumps(out, indent=1))
    print("truth readers (file, function, field):")
    for x in readers:
        print("  ", *x)
    print("dynamic access logs:")
    for k, v in out["dynamic"].items():
        print("  ", k, v)
    print("mission-06 isolation violations:", iso_bad)


if __name__ == "__main__":
    main()
