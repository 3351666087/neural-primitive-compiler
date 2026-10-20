"""The .npc description language: specs, primitives (with contracts) and networks.

Everything a network computes must be written as neurons and synapses; the
language has no escape hatch to host-language code. Parameter arithmetic in
primitives (e.g. ``threshold=k``, ``weight=-k``) is restricted to integer
+, -, * on declared parameters and is parsed with a whitelisting AST walker.

Grammar (one statement per line, ``#`` starts a comment):

  spec NAME {
    inputs a, b            outputs y
    assume FORMULA         guarantee FORMULA      (repeatable; conjunction)
    warmup INT             mode inclusive|strict
    doc "text"
  }

  primitive NAME(p1, p2=default, ...) {
    doc "text"
    require EXPR CMP EXPR
    ports a, b
    neuron N key=EXPR ...          keys: threshold leak bias reset init vmin vmax (leak=full allowed)
    synapse SRC -> DST weight=EXPR delay=EXPR      (delay=LO..HI expands to one synapse per delay)
    output NAME = NEURON
    contract {
      assume FORMULA       guarantee FORMULA       mode strict|inclusive
    }
  }
  (Inside contract formulas, $p is replaced by the value of parameter p.)

  network NAME {
    maxdelay INT
    inputs a, b
    neuron N key=VALUE ...         VALUE may be a hole ?[lo,hi]
    synapse SRC -> DST weight=VALUE delay=INT
    inst NAME = PRIM(p=VALUE, ...) port=REF ...    VALUE/REF may be a choice ?{x,y,...}
    output NAME = REF
  }
  REF := input | neuron | instance.output | _   (``_`` leaves a port unconnected)
"""

from __future__ import annotations

import ast
import operator
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from .network import DEFAULT_MAX_DELAY, DEFAULT_VMAX, DEFAULT_VMIN, Network, Neuron, Synapse, full_leak
from .smt import Hole
from .spec import Spec, SpecError, TRUE, And, parse


class DSLError(ValueError):
    pass


@dataclass(frozen=True)
class Choice:
    """A finite choice hole (enumerated by the sketch synthesiser)."""

    name: str
    options: tuple

    def __repr__(self) -> str:
        return f"?{{{', '.join(map(str, self.options))}}}"


NEURON_KEYS = ("threshold", "leak", "bias", "reset", "init", "vmin", "vmax")


# ------------------------------------------------------------- integer arithmetic
_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul}


def eval_int(expr: str, env: Mapping[str, int]) -> int:
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError as e:
        raise DSLError(f"bad integer expression {expr!r}") from e

    def go(n: ast.AST) -> int:
        if isinstance(n, ast.Expression):
            return go(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, int) and not isinstance(n.value, bool):
            return n.value
        if isinstance(n, ast.Name):
            if n.id not in env:
                raise DSLError(f"unknown parameter {n.id!r} in {expr!r}")
            return int(env[n.id])
        if isinstance(n, ast.BinOp) and type(n.op) in _BIN:
            return _BIN[type(n.op)](go(n.left), go(n.right))
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            v = go(n.operand)
            return -v if isinstance(n.op, ast.USub) else v
        raise DSLError(f"only integer + - * on parameters is allowed: {expr!r}")

    return go(tree)


_CMP = {">=": operator.ge, "<=": operator.le, "==": operator.eq, "!=": operator.ne, ">": operator.gt, "<": operator.lt}


def eval_require(expr: str, env: Mapping[str, int]) -> bool:
    m = re.match(r"^(.*?)(>=|<=|==|!=|>|<)(.*)$", expr)
    if not m:
        raise DSLError(f"require needs a comparison: {expr!r}")
    return _CMP[m.group(2)](eval_int(m.group(1), env), eval_int(m.group(3), env))


# ---------------------------------------------------------------------- AST types
@dataclass
class SynapseDecl:
    src: str
    dst: str
    weight: Any
    delay: Any  # str expr, int, or (lo_expr, hi_expr) range


@dataclass
class PrimitiveDef:
    name: str
    params: list[tuple[str, str | None]]
    ports: list[str] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)
    neurons: list[tuple[str, dict[str, str]]] = field(default_factory=list)
    synapses: list[SynapseDecl] = field(default_factory=list)
    outputs: list[tuple[str, str]] = field(default_factory=list)
    assume: list[str] = field(default_factory=list)
    guarantee: list[str] = field(default_factory=list)
    mode: str = "strict"
    doc: str = ""

    def bind(self, args: Mapping[str, int]) -> dict[str, int]:
        env: dict[str, int] = {}
        names = [p for p, _ in self.params]
        for k in args:
            if k not in names:
                raise DSLError(f"{self.name}: unknown parameter {k!r}")
        for p, default in self.params:
            if p in args:
                env[p] = int(args[p])
            elif default is not None:
                env[p] = eval_int(default, env)
            else:
                raise DSLError(f"{self.name}: missing parameter {p!r}")
        for r in self.requires:
            if not eval_require(r, env):
                raise DSLError(f"{self.name}{env}: requirement violated: {r}")
        return env

    def instantiate(self, args: Mapping[str, int] | None = None, max_delay: int = DEFAULT_MAX_DELAY) -> tuple[Network, Spec]:
        """Standalone network (ports become inputs) and its contract as a Spec."""
        env = self.bind(args or {})
        neurons = []
        for nm, fields in self.neurons:
            vals: dict[str, int] = {}
            vmin = eval_int(fields.get("vmin", str(DEFAULT_VMIN)), env)
            vmax = eval_int(fields.get("vmax", str(DEFAULT_VMAX)), env)
            for key in NEURON_KEYS:
                if key in fields:
                    vals[key] = full_leak(vmin, vmax) if (key == "leak" and fields[key] == "full") else eval_int(fields[key], env)
            neurons.append(Neuron(name=nm, **vals))
        syns = []
        for sd in self.synapses:
            w = eval_int(sd.weight, env)
            if isinstance(sd.delay, tuple):
                lo, hi = eval_int(sd.delay[0], env), eval_int(sd.delay[1], env)
                delays = range(lo, hi + 1)
            else:
                delays = [eval_int(sd.delay, env)]
            for d in delays:
                if w != 0:
                    syns.append(Synapse(sd.src, sd.dst, w, d))
        tag = ",".join(f"{k}={v}" for k, v in env.items())
        net = Network(f"{self.name}({tag})", tuple(self.ports), tuple(neurons), tuple(syns),
                      tuple(self.outputs), max_delay=max(max_delay, max((s.delay for s in syns), default=1)))
        net.validate()
        return net, self.contract(env)

    def contract(self, env: Mapping[str, int]) -> Spec:
        def sub(text: str) -> str:
            return re.sub(r"\$([A-Za-z_]\w*)", lambda m: str(env[m.group(1)]), text)
        try:
            A = And(*[parse(sub(a)) for a in self.assume]) if self.assume else TRUE
            G = And(*[parse(sub(g)) for g in self.guarantee]) if self.guarantee else TRUE
        except (SpecError, KeyError) as e:
            raise DSLError(f"{self.name}: bad contract: {e}") from e
        tag = ",".join(f"{k}={v}" for k, v in env.items())
        return Spec(f"contract:{self.name}({tag})", tuple(self.ports), tuple(o for o, _ in self.outputs),
                    A, G, 0, self.mode, self.doc)


@dataclass
class InstDecl:
    name: str
    prim: str
    args: dict[str, Any]
    bindings: dict[str, Any]


@dataclass
class NetworkDef:
    name: str
    max_delay: int = DEFAULT_MAX_DELAY
    inputs: list[str] = field(default_factory=list)
    neurons: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    synapses: list[SynapseDecl] = field(default_factory=list)
    instances: list[InstDecl] = field(default_factory=list)
    outputs: list[tuple[str, Any]] = field(default_factory=list)
    doc: str = ""

    def choices(self) -> list[Choice]:
        out = []
        for inst in self.instances:
            if isinstance(inst.prim, Choice):
                out.append(inst.prim)
            out += [v for v in (*inst.args.values(), *inst.bindings.values()) if isinstance(v, Choice)]
        out += [v for _, v in self.outputs if isinstance(v, Choice)]
        return out


@dataclass
class Library:
    primitives: dict[str, PrimitiveDef] = field(default_factory=dict)
    specs: dict[str, Spec] = field(default_factory=dict)
    networks: dict[str, NetworkDef] = field(default_factory=dict)

    def merge(self, other: "Library") -> "Library":
        for kind in ("primitives", "specs", "networks"):
            mine, theirs = getattr(self, kind), getattr(other, kind)
            dup = set(mine) & set(theirs)
            if dup:
                raise DSLError(f"duplicate {kind}: {sorted(dup)}")
            mine.update(theirs)
        return self


# ------------------------------------------------------------------------ parsing
_HDR = re.compile(r"^(spec|primitive|network)\s+([A-Za-z_]\w*)\s*(\((.*)\))?\s*\{$")
_HOLE_RANGE = re.compile(r"^\?\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]$")
_HOLE_CHOICE = re.compile(r"^\?\{(.*)\}$")


def _strip(line: str) -> str:
    out, in_str = [], False
    for ch in line:
        if ch == '"':
            in_str = not in_str
        if ch == "#" and not in_str:
            break
        out.append(ch)
    return "".join(out).strip()


def _split_kv(text: str) -> dict[str, str]:
    """Split 'a=1 b=?{x, y} c=-k+1' into a dict (values may contain spaces inside braces/parens)."""
    res: dict[str, str] = {}
    i, n = 0, len(text)
    while i < n:
        while i < n and text[i].isspace():
            i += 1
        if i >= n:
            break
        m = re.match(r"([A-Za-z_]\w*)\s*=\s*", text[i:])
        if not m:
            raise DSLError(f"expected key=value at {text[i:]!r}")
        key = m.group(1)
        i += m.end()
        depth, j = 0, i
        while j < n:
            c = text[j]
            if c in "([{":
                depth += 1
            elif c in ")]}":
                depth -= 1
            elif c.isspace() and depth == 0:
                break
            j += 1
        res[key] = text[i:j]
        i = j
    return res


def _split_top(text: str, sep: str = ",") -> list[str]:
    parts, depth, cur = [], 0, []
    for c in text:
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        if c == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(c)
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def _names(text: str) -> list[str]:
    return [t.strip() for t in text.split(",") if t.strip()]


def _doc(text: str) -> str:
    m = re.match(r'^"(.*)"$', text.strip())
    if not m:
        raise DSLError(f"doc needs a quoted string: {text!r}")
    return m.group(1)


class _HoleNamer:
    def __init__(self):
        self.count = 0

    def value(self, text: str, label: str, numeric: bool) -> Any:
        text = text.strip()
        m = _HOLE_RANGE.match(text)
        if m:
            if not numeric:
                raise DSLError(f"range hole not allowed for {label}")
            self.count += 1
            return Hole(label, int(m.group(1)), int(m.group(2)))
        m = _HOLE_CHOICE.match(text)
        if m:
            self.count += 1
            opts = tuple(_names(m.group(1)))
            if numeric:
                opts = tuple(int(o) for o in opts)
            return Choice(label, opts)
        return text


def parse_library(text: str, source: str = "<string>") -> Library:
    lib = Library()
    lines = [_strip(l) for l in text.splitlines()]
    i = 0
    while i < len(lines):
        if not lines[i]:
            i += 1
            continue
        m = _HDR.match(lines[i])
        if not m:
            raise DSLError(f"{source}:{i + 1}: expected 'spec|primitive|network NAME {{', got {lines[i]!r}")
        kind, name, params = m.group(1), m.group(2), m.group(4)
        body, depth, j = [], 1, i + 1
        while j < len(lines):
            ln = lines[j]
            if ln.endswith("{"):
                depth += 1
            if ln == "}":
                depth -= 1
                if depth == 0:
                    break
            body.append((j + 1, ln))
            j += 1
        if depth != 0:
            raise DSLError(f"{source}:{i + 1}: unterminated block {name}")
        try:
            if kind == "spec":
                if name in lib.specs:
                    raise DSLError(f"duplicate spec {name}")
                lib.specs[name] = _parse_spec(name, body)
            elif kind == "primitive":
                if name in lib.primitives:
                    raise DSLError(f"duplicate primitive {name}")
                lib.primitives[name] = _parse_primitive(name, params or "", body)
            else:
                if name in lib.networks:
                    raise DSLError(f"duplicate network {name}")
                lib.networks[name] = _parse_network(name, body)
        except (SpecError, DSLError) as e:
            raise DSLError(f"{source}: in {kind} {name}: {e}") from e
        i = j + 1
    return lib


def _parse_spec(name: str, body) -> Spec:
    ins, outs, assume, guar, warm, mode, doc = [], [], [], [], 0, "inclusive", ""
    for ln_no, ln in body:
        if not ln:
            continue
        kw, _, rest = ln.partition(" ")
        if kw == "inputs":
            ins += _names(rest)
        elif kw == "outputs":
            outs += _names(rest)
        elif kw == "assume":
            assume.append(parse(rest))
        elif kw == "guarantee":
            guar.append(parse(rest))
        elif kw == "warmup":
            warm = int(rest)
        elif kw == "mode":
            mode = rest.strip()
        elif kw == "doc":
            doc = _doc(rest)
        else:
            raise DSLError(f"line {ln_no}: unknown spec statement {kw!r}")
    return Spec(name, tuple(ins), tuple(outs), And(*assume) if assume else TRUE,
                And(*guar) if guar else TRUE, warm, mode, doc)


def _parse_synapse(rest: str, holes: _HoleNamer | None) -> SynapseDecl:
    m = re.match(r"^(\S+)\s*->\s*(\S+)\s*(.*)$", rest)
    if not m:
        raise DSLError(f"bad synapse: {rest!r}")
    src, dst, kv = m.group(1), m.group(2), _split_kv(m.group(3))
    unknown = set(kv) - {"weight", "delay"}
    if unknown or "weight" not in kv:
        raise DSLError(f"synapse needs weight= (and optional delay=): {rest!r}")
    delay: Any = kv.get("delay", "1")
    if ".." in delay:
        lo, hi = delay.split("..", 1)
        delay = (lo, hi)
    weight: Any = kv["weight"]
    if holes is not None:
        label = f"w[{src}->{dst}@{delay}]"
        weight = holes.value(weight, label, numeric=True)
        if isinstance(weight, str):
            weight = eval_int(weight, {})
        if isinstance(delay, str):
            delay = eval_int(delay, {})
        else:
            delay = (eval_int(delay[0], {}), eval_int(delay[1], {}))
    return SynapseDecl(src, dst, weight, delay)


def _parse_primitive(name: str, params: str, body) -> PrimitiveDef:
    plist: list[tuple[str, str | None]] = []
    for p in _names(params):
        if "=" in p:
            k, v = p.split("=", 1)
            plist.append((k.strip(), v.strip()))
        else:
            plist.append((p, None))
    pd = PrimitiveDef(name, plist)
    in_contract = False
    for ln_no, ln in body:
        if not ln:
            continue
        if ln == "contract {":
            in_contract = True
            continue
        if ln == "}":
            in_contract = False
            continue
        kw, _, rest = ln.partition(" ")
        if in_contract:
            if kw == "assume":
                pd.assume.append(rest)
            elif kw == "guarantee":
                pd.guarantee.append(rest)
            elif kw == "mode":
                pd.mode = rest.strip()
            else:
                raise DSLError(f"line {ln_no}: unknown contract statement {kw!r}")
            continue
        if kw == "doc":
            pd.doc = _doc(rest)
        elif kw == "require":
            pd.requires.append(rest)
        elif kw == "ports":
            pd.ports += _names(rest)
        elif kw == "neuron":
            nm, _, kv = rest.strip().partition(" ")
            fields = _split_kv(kv)
            bad = set(fields) - set(NEURON_KEYS)
            if bad or "threshold" not in fields:
                raise DSLError(f"line {ln_no}: neuron needs threshold= and only {NEURON_KEYS}")
            pd.neurons.append((nm, fields))
        elif kw == "synapse":
            pd.synapses.append(_parse_synapse(rest, None))
        elif kw == "output":
            o, _, n = rest.partition("=")
            pd.outputs.append((o.strip(), n.strip()))
        else:
            raise DSLError(f"line {ln_no}: unknown primitive statement {kw!r}")
    if not pd.guarantee:
        raise DSLError(f"primitive {name} has no contract guarantee: a primitive may not be declared by name only")
    return pd


def _parse_network(name: str, body) -> NetworkDef:
    nd = NetworkDef(name)
    holes = _HoleNamer()
    for ln_no, ln in body:
        if not ln:
            continue
        kw, _, rest = ln.partition(" ")
        if kw == "maxdelay":
            nd.max_delay = int(rest)
        elif kw == "inputs":
            nd.inputs += _names(rest)
        elif kw == "doc":
            nd.doc = _doc(rest)
        elif kw == "neuron":
            nm, _, kv = rest.strip().partition(" ")
            raw = _split_kv(kv)
            bad = set(raw) - set(NEURON_KEYS)
            if bad or "threshold" not in raw:
                raise DSLError(f"line {ln_no}: neuron needs threshold= and only {NEURON_KEYS}")
            fields: dict[str, Any] = {}
            for k, v in raw.items():
                if k == "leak" and v.strip() == "full":
                    fields[k] = "full"
                    continue
                hv = holes.value(v, f"{nm}.{k}", numeric=True)
                fields[k] = eval_int(hv, {}) if isinstance(hv, str) else hv
            nd.neurons.append((nm, fields))
        elif kw == "synapse":
            nd.synapses.append(_parse_synapse(rest, holes))
        elif kw == "inst":
            m = re.match(r"^([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*|\?\{[^}]*\})\s*\((.*?)\)\s*(.*)$", rest)
            if not m:
                raise DSLError(f"line {ln_no}: bad inst: {rest!r}")
            iname, prim, argtxt, bindtxt = m.groups()
            if prim.startswith("?"):
                prim = holes.value(prim, f"{iname}.type", numeric=False)
            args = {}
            for item in _split_top(argtxt):
                if "=" not in item:
                    raise DSLError(f"line {ln_no}: instance arguments must be name=value: {item!r}")
                k, v = (t.strip() for t in item.split("=", 1))
                hv = holes.value(v, f"{iname}.{k}", numeric=True)
                args[k] = eval_int(hv, {}) if isinstance(hv, str) else hv
            binds = {}
            for k, v in _split_kv(bindtxt).items():
                binds[k] = holes.value(v, f"{iname}<-{k}", numeric=False)
            nd.instances.append(InstDecl(iname, prim, args, binds))
        elif kw == "output":
            o, _, r = rest.partition("=")
            nd.outputs.append((o.strip(), holes.value(r, f"out:{o.strip()}", numeric=False)))
        else:
            raise DSLError(f"line {ln_no}: unknown network statement {kw!r}")
    return nd


def load(*paths: str | Path) -> Library:
    lib = Library()
    for p in paths:
        p = Path(p)
        lib.merge(parse_library(p.read_text(), str(p)))
    return lib


def stdlib_path() -> Path:
    return Path(__file__).parent / "lib" / "primitives.npc"


def load_with_stdlib(*paths: str | Path) -> Library:
    return load(stdlib_path(), *paths)


# ----------------------------------------------------------------------- flatten
@dataclass
class Flattened:
    network: Network
    instances: dict[str, tuple[str, dict[str, int], dict[str, str | None]]]  # name -> (prim, args, resolved bindings)
    output_neurons: dict[str, str]  # "inst.out" -> neuron name


def flatten(lib: Library, nd: NetworkDef, assignment: Mapping[str, Any] | None = None,
            allow_holes: bool = False) -> Flattened:
    """Macro-expand instances into raw neurons. ``assignment`` resolves Choice holes by name."""
    assignment = assignment or {}

    def res(v: Any) -> Any:
        if isinstance(v, Choice):
            if v.name not in assignment:
                raise DSLError(f"unresolved choice hole {v.name}")
            return assignment[v.name]
        return v

    errors: list[str] = []
    neurons: list[Neuron] = []
    synapses: list[Synapse] = []
    inst_out: dict[str, str] = {}
    inst_info = {}
    expanded = {}
    for inst in nd.instances:
        prim = res(inst.prim)
        if prim not in lib.primitives:
            errors.append(f"instance {inst.name}: unknown primitive {prim}")
            continue
        pd = lib.primitives[prim]
        try:
            args = {k: int(res(v)) for k, v in inst.args.items()}
            pnet, _ = pd.instantiate(args, nd.max_delay)
        except DSLError as e:
            errors.append(f"instance {inst.name}: {e}")
            continue
        expanded[inst.name] = (pd, pnet, args)
        for o, n in pnet.outputs:
            inst_out[f"{inst.name}.{o}"] = f"{inst.name}.{n}"
    raw_names = {nm for nm, _ in nd.neurons}

    def resolve_ref(r: Any, what: str) -> str | None:
        r = res(r)
        if r == "_":
            return None
        if r in nd.inputs or r in raw_names:
            return r
        if r in inst_out:
            return inst_out[r]
        errors.append(f"{what}: unknown reference {r!r}")
        return None

    for iname, (pd, pnet, args) in expanded.items():
        inst = next(i for i in nd.instances if i.name == iname)
        bound: dict[str, str | None] = {}
        for p in pd.ports:
            if p not in inst.bindings:
                errors.append(f"instance {iname}: port {p} is not connected (use {p}=_ to leave it silent)")
                continue
            bound[p] = resolve_ref(inst.bindings[p], f"instance {iname} port {p}")
        for k in inst.bindings:
            if k not in pd.ports:
                errors.append(f"instance {iname}: primitive {pd.name} has no port {k}")
        for n in pnet.neurons:
            neurons.append(Neuron(f"{iname}.{n.name}", n.threshold, n.leak, n.bias, n.reset, n.init, n.vmin, n.vmax))
        for s in pnet.synapses:
            if s.src in pd.ports:
                src = bound.get(s.src)
                if src is None:
                    continue
            else:
                src = f"{iname}.{s.src}"
            synapses.append(Synapse(src, f"{iname}.{s.dst}", s.weight, s.delay))
        inst_info[iname] = (pd.name, args, bound)
    for nm, fields in nd.neurons:
        vals = {}
        vmin = fields.get("vmin", DEFAULT_VMIN)
        vmax = fields.get("vmax", DEFAULT_VMAX)
        for k, v in fields.items():
            if k == "leak" and v == "full":
                if isinstance(vmin, Hole) or isinstance(vmax, Hole):
                    errors.append(f"neuron {nm}: leak=full needs concrete vmin/vmax")
                    continue
                v = full_leak(vmin, vmax)
            vals[k] = res(v)
        neurons.append(Neuron(name=nm, **vals))
    for sd in nd.synapses:
        src = resolve_ref(sd.src, f"synapse {sd.src}->{sd.dst}")
        if sd.dst not in raw_names:
            errors.append(f"synapse {sd.src}->{sd.dst}: destination must be a raw neuron of this network")
            continue
        if src is None:
            continue
        w = res(sd.weight)
        delays = range(sd.delay[0], sd.delay[1] + 1) if isinstance(sd.delay, tuple) else [sd.delay]
        for d in delays:
            wd = Hole(f"{w.name}@{d}", w.lo, w.hi) if (isinstance(w, Hole) and isinstance(sd.delay, tuple)) else w
            synapses.append(Synapse(src, sd.dst, wd, d))
    outs = []
    for o, r in nd.outputs:
        rr = res(r)
        if rr in nd.inputs:
            errors.append(f"output {o}: cannot be wired directly to input {rr} (zero latency is not realisable)")
            continue
        n = resolve_ref(rr, f"output {o}")
        if n is not None:
            outs.append((o, n))
    if errors:
        raise DSLError("; ".join(errors))
    net = Network(nd.name, tuple(nd.inputs), tuple(neurons), tuple(synapses), tuple(outs), max_delay=nd.max_delay)
    has_holes = any(isinstance(getattr(n, k), Hole) for n in neurons for k in NEURON_KEYS) or \
        any(isinstance(s.weight, Hole) for s in synapses)
    if has_holes and not allow_holes:
        raise DSLError(f"network {nd.name} still contains integer holes; use the synthesiser")
    if not has_holes:
        net.validate()
    return Flattened(net, inst_info, inst_out)
