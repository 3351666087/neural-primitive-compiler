"""Specification language: bounded past-time temporal logic with counting.

Syntax (precedence low -> high):  <->   ->   |   ^   &   !
  true | false | NAME | ( f )
  prev(f)  prev[k](f)      strong yesterday: f held at t-k  (false if t-k < 0)
  wprev(f) wprev[k](f)     weak yesterday:   f held at t-k  (true  if t-k < 0)
  once[lo,hi](f)           f held at some t-j, lo <= j <= hi, t-j >= 0
  hist[lo,hi](f)           f held at every t-j, lo <= j <= hi, t-j >= 0
  once(f)  hist(f)         unbounded versions (j >= 0)
  since(f, g)              g held at some j <= t and f held at every step in (j, t]
  atleast(k; f1, ..., fn)  at least k of the fi hold now
  E1 CMP E2                CMP in {>=, <=, ==, !=, >, <}; integer expressions:
      INT | c*TERM | E + E | E - E,  TERM is
      count[w](f)          number of steps in [t-w+1, t] (and >= 0) where f held
      modcount[k](f)       c(t) mod k, c(t) = c(t-1) + [f(t)], c(-1) = 0
      modcount[k](f; r)    same but c(t) = 0 whenever r(t) holds (reset wins)

A Spec = (inputs, outputs, assume A, guarantee G, warmup w, mode). A finite
trace of length T satisfies it iff for every t in [w, T):
    inclusive mode:  (A held at every t' <= t)  implies  G(t)
    strict mode:     (A held at every t' <  t)  implies  G(t)
Strict mode is the Abadi-Lamport style "guarantee one step longer than the
assumption" used for component contracts (theory.md, Section 5).

Three evaluators are provided and cross-tested: batch numpy evaluation,
an incremental finite-state ``Monitor`` (Havelund-Rosu style) and the SMT
encoding in smt.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

BOOL_OPS = {"const", "atom", "not", "and", "or", "xor", "implies", "iff", "prev", "wprev",
            "once", "hist", "since", "atleast", "cmp"}
INT_OPS = {"int", "count", "modcount", "add", "sub", "mul"}
UNBOUNDED = -1


class SpecError(ValueError):
    pass


@dataclass(frozen=True)
class F:
    op: str
    args: tuple = ()
    params: tuple = ()

    def __str__(self) -> str:  # pragma: no cover - convenience
        return show(self)


# ------------------------------------------------------------------ constructors
TRUE = F("const", (), (True,))
FALSE = F("const", (), (False,))


def atom(name: str) -> F:
    return F("atom", (), (name,))


def Not(f: F) -> F:
    return F("not", (f,))


def And(*fs: F) -> F:
    fs = tuple(fs)
    if not fs:
        return TRUE
    return fs[0] if len(fs) == 1 else F("and", fs)


def Or(*fs: F) -> F:
    fs = tuple(fs)
    if not fs:
        return FALSE
    return fs[0] if len(fs) == 1 else F("or", fs)


def Iff(a: F, b: F) -> F:
    return F("iff", (a, b))


def Prev(f: F, k: int = 1) -> F:
    return F("prev", (f,), (k,))


# ----------------------------------------------------------------------- parsing
_TOKEN = re.compile(r"\s*(<->|->|>=|<=|==|!=|[A-Za-z_][A-Za-z0-9_.]*|\d+|[()\[\],;&|^!<>+\-*])")
_KEYWORDS = {"true", "false", "prev", "wprev", "once", "hist", "since", "atleast", "count", "modcount"}


def _tokenize(text: str) -> list[str]:
    pos, toks = 0, []
    text = text.rstrip()
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            raise SpecError(f"unexpected character at {pos}: {text[pos:pos+10]!r}")
        toks.append(m.group(1))
        pos = m.end()
    return toks


class _Parser:
    def __init__(self, text: str):
        self.toks = _tokenize(text)
        self.i = 0
        self.text = text

    def peek(self, k: int = 0) -> str | None:
        j = self.i + k
        return self.toks[j] if j < len(self.toks) else None

    def take(self, expect: str | None = None) -> str:
        tok = self.peek()
        if tok is None:
            raise SpecError(f"unexpected end of formula: {self.text!r}")
        if expect is not None and tok != expect:
            raise SpecError(f"expected {expect!r} but found {tok!r} in {self.text!r}")
        self.i += 1
        return tok

    def integer(self) -> int:
        neg = False
        if self.peek() == "-":
            self.take()
            neg = True
        tok = self.take()
        if not tok.isdigit():
            raise SpecError(f"expected integer, found {tok!r}")
        return -int(tok) if neg else int(tok)

    def done(self) -> None:
        if self.peek() is not None:
            raise SpecError(f"trailing tokens {self.toks[self.i:]} in {self.text!r}")

    # formula grammar
    def formula(self) -> F:
        left = self.imp()
        while self.peek() == "<->":
            self.take()
            left = F("iff", (left, self.imp()))
        return left

    def imp(self) -> F:
        left = self.disj()
        if self.peek() == "->":
            self.take()
            return F("implies", (left, self.imp()))
        return left

    def disj(self) -> F:
        parts = [self.xor()]
        while self.peek() == "|":
            self.take()
            parts.append(self.xor())
        return parts[0] if len(parts) == 1 else F("or", tuple(parts))

    def xor(self) -> F:
        left = self.conj()
        while self.peek() == "^":
            self.take()
            left = F("xor", (left, self.conj()))
        return left

    def conj(self) -> F:
        parts = [self.unary()]
        while self.peek() == "&":
            self.take()
            parts.append(self.unary())
        return parts[0] if len(parts) == 1 else F("and", tuple(parts))

    def unary(self) -> F:
        if self.peek() == "!":
            self.take()
            return F("not", (self.unary(),))
        return self.primary()

    def _bracket_ints(self, n: int) -> tuple[int, ...]:
        self.take("[")
        vals = [self.integer()]
        while self.peek() == ",":
            self.take()
            vals.append(self.integer())
        self.take("]")
        if len(vals) != n:
            raise SpecError(f"expected {n} bracket argument(s), got {vals}")
        return tuple(vals)

    def primary(self) -> F:
        tok = self.peek()
        if tok is None:
            raise SpecError(f"unexpected end of formula: {self.text!r}")
        if tok in ("count", "modcount") or tok.isdigit() or (tok == "-" and (self.peek(1) or "").isdigit()):
            return self.comparison()
        if tok == "(":
            self.take()
            f = self.formula()
            self.take(")")
            return f
        if tok == "true":
            self.take()
            return TRUE
        if tok == "false":
            self.take()
            return FALSE
        if tok in ("prev", "wprev"):
            self.take()
            k = self._bracket_ints(1)[0] if self.peek() == "[" else 1
            if k < 1:
                raise SpecError(f"{tok}[k] needs k >= 1")
            self.take("(")
            f = self.formula()
            self.take(")")
            return F(tok, (f,), (k,))
        if tok in ("once", "hist"):
            self.take()
            if self.peek() == "[":
                lo, hi = self._bracket_ints(2)
                if not (0 <= lo <= hi):
                    raise SpecError(f"{tok}[lo,hi] needs 0 <= lo <= hi")
            else:
                lo, hi = 0, UNBOUNDED
            self.take("(")
            f = self.formula()
            self.take(")")
            return F(tok, (f,), (lo, hi))
        if tok == "since":
            self.take()
            self.take("(")
            a = self.formula()
            self.take(",")
            b = self.formula()
            self.take(")")
            return F("since", (a, b))
        if tok == "atleast":
            self.take()
            self.take("(")
            k = self.integer()
            self.take(";")
            fs = [self.formula()]
            while self.peek() == ",":
                self.take()
                fs.append(self.formula())
            self.take(")")
            return F("atleast", tuple(fs), (k,))
        if tok in _KEYWORDS:
            raise SpecError(f"misplaced keyword {tok!r}")
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", tok):
            self.take()
            return atom(tok)
        raise SpecError(f"unexpected token {tok!r} in {self.text!r}")

    def comparison(self) -> F:
        left = self.intexpr()
        op = self.take()
        if op not in (">=", "<=", "==", "!=", ">", "<"):
            raise SpecError(f"expected comparison operator, found {op!r}")
        right = self.intexpr()
        return F("cmp", (left, right), (op,))

    def intexpr(self) -> F:
        left = self.intterm()
        while self.peek() in ("+", "-"):
            op = self.take()
            right = self.intterm()
            left = F("add" if op == "+" else "sub", (left, right))
        return left

    def intterm(self) -> F:
        tok = self.peek()
        if tok == "-" or (tok is not None and tok.isdigit()):
            c = self.integer()
            if self.peek() == "*":
                self.take()
                return F("mul", (self.intatom(),), (c,))
            return F("int", (), (c,))
        return self.intatom()

    def intatom(self) -> F:
        tok = self.take()
        if tok == "count":
            (w,) = self._bracket_ints(1)
            if w < 1:
                raise SpecError("count[w] needs w >= 1")
            self.take("(")
            f = self.formula()
            self.take(")")
            return F("count", (f,), (w,))
        if tok == "modcount":
            (k,) = self._bracket_ints(1)
            if k < 1:
                raise SpecError("modcount[k] needs k >= 1")
            self.take("(")
            f = self.formula()
            r = FALSE
            if self.peek() == ";":
                self.take()
                r = self.formula()
            self.take(")")
            return F("modcount", (f, r), (k,))
        raise SpecError(f"expected count/modcount, found {tok!r}")


def parse(text: str) -> F:
    p = _Parser(text)
    f = p.formula()
    p.done()
    return f


# ------------------------------------------------------------------ pretty print
def show(f: F) -> str:
    op = f.op
    if op == "const":
        return "true" if f.params[0] else "false"
    if op == "atom":
        return f.params[0]
    if op == "not":
        return f"!{_paren(f.args[0])}"
    if op in ("and", "or"):
        sym = " & " if op == "and" else " | "
        return sym.join(_paren(a) for a in f.args)
    if op == "xor":
        return f"{_paren(f.args[0])} ^ {_paren(f.args[1])}"
    if op == "implies":
        return f"{_paren(f.args[0])} -> {_paren(f.args[1])}"
    if op == "iff":
        return f"{_paren(f.args[0])} <-> {_paren(f.args[1])}"
    if op in ("prev", "wprev"):
        k = f.params[0]
        return f"{op}({show(f.args[0])})" if k == 1 else f"{op}[{k}]({show(f.args[0])})"
    if op in ("once", "hist"):
        lo, hi = f.params
        if hi == UNBOUNDED:
            return f"{op}({show(f.args[0])})"
        return f"{op}[{lo},{hi}]({show(f.args[0])})"
    if op == "since":
        return f"since({show(f.args[0])}, {show(f.args[1])})"
    if op == "atleast":
        return f"atleast({f.params[0]}; " + ", ".join(show(a) for a in f.args) + ")"
    if op == "cmp":
        return f"{show(f.args[0])} {f.params[0]} {show(f.args[1])}"
    if op == "int":
        return str(f.params[0])
    if op == "count":
        return f"count[{f.params[0]}]({show(f.args[0])})"
    if op == "modcount":
        if f.args[1] == FALSE:
            return f"modcount[{f.params[0]}]({show(f.args[0])})"
        return f"modcount[{f.params[0]}]({show(f.args[0])}; {show(f.args[1])})"
    if op == "add":
        return f"{show(f.args[0])} + {show(f.args[1])}"
    if op == "sub":
        rhs = f.args[1]
        r = show(rhs)
        return f"{show(f.args[0])} - {r}"
    if op == "mul":
        return f"{f.params[0]}*{show(f.args[0])}"
    raise SpecError(f"unknown op {op}")


def _paren(f: F) -> str:
    s = show(f)
    if f.op in ("const", "atom", "not", "prev", "wprev", "once", "hist", "since", "atleast"):
        return s
    return f"({s})"


# ---------------------------------------------------------------------- analysis
def atoms(f: F) -> set[str]:
    if f.op == "atom":
        return {f.params[0]}
    out: set[str] = set()
    for a in f.args:
        out |= atoms(a)
    return out


def subst(f: F, mapping: Mapping[str, str]) -> F:
    """Rename atoms."""
    if f.op == "atom":
        return atom(mapping.get(f.params[0], f.params[0]))
    if not f.args:
        return f
    return F(f.op, tuple(subst(a, mapping) for a in f.args), f.params)


def lookback(f: F) -> int:
    """Max finite past horizon referenced (unbounded operators count as 0 here)."""
    op = f.op
    inner = max((lookback(a) for a in f.args), default=0)
    if op in ("prev", "wprev"):
        return inner + f.params[0]
    if op in ("once", "hist"):
        return inner + (f.params[1] if f.params[1] != UNBOUNDED else f.params[0])
    if op == "count":
        return inner + f.params[0] - 1
    return inner


def strictly_past(f: F, names: set[str]) -> bool:
    """True if every occurrence of an atom in ``names`` is under some prev/wprev
    (so the value of f at t depends on those signals only at times < t)."""
    op = f.op
    if op == "atom":
        return f.params[0] not in names
    if op in ("prev", "wprev"):
        return True
    if op in ("once", "hist") and f.params[0] >= 1:
        return True
    return all(strictly_past(a, names) for a in f.args)


# -------------------------------------------------------------- batch evaluation
def _shift(x: np.ndarray, k: int, fill) -> np.ndarray:
    out = np.empty_like(x)
    T = x.shape[1]
    if k >= T:
        out[...] = fill
        return out
    out[:, :k] = fill
    out[:, k:] = x[:, : T - k]
    return out


def evaluate(f: F, env: Mapping[str, np.ndarray]) -> np.ndarray:
    """Evaluate on a batch. env maps signal name -> array (B, T) of 0/1 or bool."""
    any_arr = next(iter(env.values()))
    B, T = np.asarray(any_arr).shape
    memo: dict[int, np.ndarray] = {}

    def ev(g: F) -> np.ndarray:
        key = id(g)
        if key in memo:
            return memo[key]
        op = g.op
        if op == "const":
            r = np.full((B, T), bool(g.params[0]))
        elif op == "atom":
            name = g.params[0]
            if name not in env:
                raise SpecError(f"unknown signal {name!r}")
            r = np.asarray(env[name]).astype(bool)
        elif op == "not":
            r = ~ev(g.args[0])
        elif op == "and":
            r = np.logical_and.reduce([ev(a) for a in g.args])
        elif op == "or":
            r = np.logical_or.reduce([ev(a) for a in g.args])
        elif op == "xor":
            r = ev(g.args[0]) ^ ev(g.args[1])
        elif op == "implies":
            r = ~ev(g.args[0]) | ev(g.args[1])
        elif op == "iff":
            r = ev(g.args[0]) == ev(g.args[1])
        elif op == "prev":
            r = _shift(ev(g.args[0]), g.params[0], False)
        elif op == "wprev":
            r = _shift(ev(g.args[0]), g.params[0], True)
        elif op in ("once", "hist"):
            lo, hi = g.params
            x = ev(g.args[0])
            is_once = op == "once"
            if hi == UNBOUNDED:
                xs = _shift(x, lo, not is_once)
                r = (np.logical_or if is_once else np.logical_and).accumulate(xs, axis=1)
            else:
                parts = [_shift(x, j, not is_once) for j in range(lo, hi + 1)]
                r = (np.logical_or if is_once else np.logical_and).reduce(parts)
        elif op == "since":
            a, b = ev(g.args[0]), ev(g.args[1])
            r = np.zeros((B, T), dtype=bool)
            prev = np.zeros(B, dtype=bool)
            for t in range(T):
                prev = b[:, t] | (a[:, t] & prev)
                r[:, t] = prev
        elif op == "atleast":
            r = np.sum([ev(a).astype(np.int64) for a in g.args], axis=0) >= g.params[0]
        elif op == "cmp":
            l, rr = ev(g.args[0]), ev(g.args[1])
            r = {">=": l >= rr, "<=": l <= rr, "==": l == rr, "!=": l != rr, ">": l > rr, "<": l < rr}[g.params[0]]
        elif op == "int":
            r = np.full((B, T), g.params[0], dtype=np.int64)
        elif op == "count":
            x = ev(g.args[0]).astype(np.int64)
            r = np.sum([_shift(x, j, 0) for j in range(g.params[0])], axis=0)
        elif op == "modcount":
            k = g.params[0]
            a, rst = ev(g.args[0]), ev(g.args[1])
            r = np.zeros((B, T), dtype=np.int64)
            c = np.zeros(B, dtype=np.int64)
            for t in range(T):
                c = np.where(rst[:, t], 0, (c + a[:, t]) % k)
                r[:, t] = c
        elif op == "add":
            r = ev(g.args[0]) + ev(g.args[1])
        elif op == "sub":
            r = ev(g.args[0]) - ev(g.args[1])
        elif op == "mul":
            r = g.params[0] * ev(g.args[0])
        else:
            raise SpecError(f"unknown op {op}")
        memo[key] = r
        return r

    return ev(f)


# --------------------------------------------------------- incremental monitor
class Monitor:
    """Finite-state incremental evaluator. ``step(state, valuation) -> (state', value)``.

    The state is a tuple of hashable per-node components, so the product with a
    network's state can be explored explicitly (unbounded reachability).
    """

    def __init__(self, f: F):
        self.root = f
        self.nodes: list[tuple[F, tuple[int, ...], int]] = []  # (node, children idx, slot or -1)
        self.init_slots: list[Any] = []
        self._build(f)
        self.init = tuple(self.init_slots)

    def _build(self, g: F) -> int:
        kids = tuple(self._build(a) for a in g.args)
        slot = -1
        op = g.op
        init: Any = None
        if op == "prev":
            init = (False,) * g.params[0]
        elif op == "wprev":
            init = (True,) * g.params[0]
        elif op in ("once", "hist"):
            lo, hi = g.params
            if hi == UNBOUNDED:
                if lo != 0:
                    raise SpecError("unbounded once/hist with lo > 0 is not supported by the monitor")
                init = op == "hist"
            elif hi > 0:
                init = ((op == "hist"),) * hi
        elif op == "since":
            init = False
        elif op == "count":
            if g.params[0] > 1:
                init = (0,) * (g.params[0] - 1)
        elif op == "modcount":
            init = 0
        if init is not None:
            slot = len(self.init_slots)
            self.init_slots.append(init)
        self.nodes.append((g, kids, slot))
        return len(self.nodes) - 1

    def step(self, state: tuple, val: Mapping[str, Any]) -> tuple[tuple, Any]:
        vals: list[Any] = [None] * len(self.nodes)
        new = list(state)
        for idx, (g, kids, slot) in enumerate(self.nodes):
            op = g.op
            if op == "atom":
                v = bool(val[g.params[0]])
            elif op == "const":
                v = g.params[0]
            elif op == "not":
                v = not vals[kids[0]]
            elif op == "and":
                v = all(vals[k] for k in kids)
            elif op == "or":
                v = any(vals[k] for k in kids)
            elif op == "xor":
                v = vals[kids[0]] != vals[kids[1]]
            elif op == "implies":
                v = (not vals[kids[0]]) or vals[kids[1]]
            elif op == "iff":
                v = vals[kids[0]] == vals[kids[1]]
            elif op in ("prev", "wprev"):
                q = state[slot]
                v = q[0]
                new[slot] = q[1:] + (vals[kids[0]],)
            elif op in ("once", "hist"):
                lo, hi = g.params
                cur = vals[kids[0]]
                if hi == UNBOUNDED:
                    v = (state[slot] or cur) if op == "once" else (state[slot] and cur)
                    new[slot] = v
                else:
                    q = state[slot] if hi > 0 else ()
                    window = [q[hi - j] for j in range(max(lo, 1), hi + 1)]
                    if lo == 0:
                        window.append(cur)
                    v = any(window) if op == "once" else all(window)
                    if hi > 0:
                        new[slot] = q[1:] + (cur,)
            elif op == "since":
                v = vals[kids[1]] or (vals[kids[0]] and state[slot])
                new[slot] = v
            elif op == "atleast":
                v = sum(1 for k in kids if vals[k]) >= g.params[0]
            elif op == "cmp":
                l, r = vals[kids[0]], vals[kids[1]]
                c = g.params[0]
                v = (l >= r) if c == ">=" else (l <= r) if c == "<=" else (l == r) if c == "==" else \
                    (l != r) if c == "!=" else (l > r) if c == ">" else (l < r)
            elif op == "int":
                v = g.params[0]
            elif op == "count":
                cur = 1 if vals[kids[0]] else 0
                if g.params[0] > 1:
                    q = state[slot]
                    v = cur + sum(q)
                    new[slot] = q[1:] + (cur,)
                else:
                    v = cur
            elif op == "modcount":
                k = g.params[0]
                v = 0 if vals[kids[1]] else (state[slot] + (1 if vals[kids[0]] else 0)) % k
                new[slot] = v
            elif op == "add":
                v = vals[kids[0]] + vals[kids[1]]
            elif op == "sub":
                v = vals[kids[0]] - vals[kids[1]]
            elif op == "mul":
                v = g.params[0] * vals[kids[0]]
            else:
                raise SpecError(f"unknown op {op}")
            vals[idx] = v
        return tuple(new), vals[-1]

    def run(self, trace: Mapping[str, Sequence[int]], T: int) -> list[Any]:
        st = self.init
        out = []
        for t in range(T):
            st, v = self.step(st, {k: trace[k][t] for k in trace})
            out.append(v)
        return out


# --------------------------------------------------------------------------- spec
@dataclass(frozen=True)
class Spec:
    name: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    assume: F = TRUE
    guarantee: F = TRUE
    warmup: int = 0
    assume_mode: str = "inclusive"  # or "strict"
    doc: str = field(default="", compare=False)

    def __post_init__(self):
        if self.assume_mode not in ("inclusive", "strict"):
            raise SpecError(f"assume_mode must be inclusive|strict, got {self.assume_mode}")
        sig = set(self.inputs) | set(self.outputs)
        unknown = (atoms(self.assume) | atoms(self.guarantee)) - sig
        if unknown:
            raise SpecError(f"spec {self.name}: unknown signals {sorted(unknown)}")
        if atoms(self.assume) & set(self.outputs):
            raise SpecError(f"spec {self.name}: assumptions may only mention inputs")

    def describe(self) -> str:
        lines = [f"spec {self.name}  inputs={list(self.inputs)} outputs={list(self.outputs)}"]
        if self.assume != TRUE:
            lines.append(f"  assume    {show(self.assume)}   [{self.assume_mode}]")
        lines.append(f"  guarantee {show(self.guarantee)}")
        if self.warmup:
            lines.append(f"  warmup    {self.warmup}")
        return "\n".join(lines)

    def violation_mask(self, env: Mapping[str, np.ndarray]) -> np.ndarray:
        """(B, T) bool array: True where the trace violates the spec at that step."""
        A = evaluate(self.assume, env)
        G = evaluate(self.guarantee, env)
        B, T = G.shape
        held = np.logical_and.accumulate(A, axis=1)
        if self.assume_mode == "strict":
            held = np.concatenate([np.ones((B, 1), dtype=bool), held[:, :-1]], axis=1)
        mask = held & ~G
        mask[:, : min(self.warmup, T)] = False
        return mask

    def first_violation(self, signals: Mapping[str, Sequence[int]]) -> int | None:
        env = {k: np.asarray(v, dtype=np.int64).reshape(1, -1) for k, v in signals.items()}
        m = self.violation_mask(env)[0]
        idx = np.flatnonzero(m)
        return int(idx[0]) if idx.size else None

    def functional_outputs(self) -> dict[str, F] | None:
        """If G is a conjunction of `out <-> phi` (one per output), return {out: phi}."""
        conj = self.guarantee.args if self.guarantee.op == "and" else (self.guarantee,)
        res: dict[str, F] = {}
        for c in conj:
            if c.op != "iff":
                return None
            l, r = c.args
            if l.op == "atom" and l.params[0] in self.outputs and l.params[0] not in res:
                res[l.params[0]] = r
            elif r.op == "atom" and r.params[0] in self.outputs and r.params[0] not in res:
                res[r.params[0]] = l
            else:
                return None
        if set(res) != set(self.outputs):
            return None
        return res

    def renamed(self, mapping: Mapping[str, str], name: str | None = None) -> "Spec":
        return Spec(
            name=name or self.name,
            inputs=tuple(mapping.get(k, k) for k in self.inputs),
            outputs=tuple(mapping.get(k, k) for k in self.outputs),
            assume=subst(self.assume, mapping),
            guarantee=subst(self.guarantee, mapping),
            warmup=self.warmup,
            assume_mode=self.assume_mode,
            doc=self.doc,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "assume": show(self.assume),
            "guarantee": show(self.guarantee),
            "warmup": self.warmup,
            "assume_mode": self.assume_mode,
        }


def make_spec(name: str, inputs: Iterable[str], outputs: Iterable[str], guarantee: str,
              assume: str = "true", warmup: int = 0, assume_mode: str = "inclusive", doc: str = "") -> Spec:
    return Spec(name, tuple(inputs), tuple(outputs), parse(assume), parse(guarantee), warmup, assume_mode, doc)
