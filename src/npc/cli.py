"""Command-line interface.

Exit codes: 0 = verified / solved / compiled, 1 = counterexample / unrealizable / exhausted,
2 = unknown / timeout / resource limit, 3 = usage or input error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any

from . import __version__
from .compose import compositional_verify, prove_primitive
from .dsl import DSLError, flatten, load_with_stdlib
from .fsm import classical_network, machine_from_spec, minimize, NotCausal, NotFunctional
from .network import Network, NetworkError
from .simulator import simulate
from .spec import SpecError, show
from .synth import (SOLVED, SOLVED_BOUNDED, compose_cyclic, compose_dag, cegis, enumerate_params,
                    fully_connected, minimize_synapses, search_neurons, sketch)
from .verify import Status, verify_all


def _env() -> dict[str, Any]:
    import z3
    return {"npc": __version__, "python": platform.python_version(), "z3": z3.get_version_string(),
            "machine": platform.machine(), "system": platform.system(),
            "time": time.strftime("%Y-%m-%dT%H:%M:%S")}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _record(kind: str, spec, net: Network | None, payload: dict[str, Any]) -> dict[str, Any]:
    rec = {"kind": kind, "environment": _env(), "spec": spec.to_dict() if spec else None}
    if net is not None:
        nj = net.to_json()
        rec["network"] = net.to_dict()
        rec["network_sha256"] = _sha(nj)
        rec["network_stats"] = net.stats()
    rec.update(payload)
    rec["note"] = ("This is a verification record, not an independently checkable proof object. "
                   "Re-run `npc verify` on the stored network and spec to re-establish every claim.")
    return rec


def _write(path: str | None, obj: dict[str, Any]) -> None:
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(obj, indent=2))
        print(f"wrote {path}")


def _load(args):
    return load_with_stdlib(*args.files)


def _network(lib, args) -> Network:
    if getattr(args, "net_json", None):
        return Network.from_json(Path(args.net_json).read_text())
    if not args.network:
        raise DSLError("give --network NAME or --net-json FILE")
    return flatten(lib, lib.networks[args.network]).network


def cmd_primitives(args) -> int:
    lib = load_with_stdlib(*args.files)
    for name, pd in lib.primitives.items():
        params = ", ".join(p if d is None else f"{p}={d}" for p, d in pd.params)
        r = prove_primitive(lib, name)
        print(f"{name}({params})  ports={pd.ports} outputs={[o for o, _ in pd.outputs]}")
        print(f"    {pd.doc}")
        for a in pd.assume:
            print(f"    assume    {a}")
        for g in pd.guarantee:
            print(f"    guarantee {g}")
        print(f"    default-parameter contract proof: {r.status.value} ({r.stats.get('product_states', '?')} states)")
    return 0


def cmd_check(args) -> int:
    lib = _load(args)
    ok = True
    print(f"primitives: {len(lib.primitives)}  specs: {len(lib.specs)}  networks: {len(lib.networks)}")
    for name in lib.primitives:
        r = prove_primitive(lib, name)
        ok &= r.status == Status.VERIFIED_UNBOUNDED
        print(f"  primitive {name:12s} contract (default params): {r.status.value}")
    for name, nd in lib.networks.items():
        if nd.choices():
            print(f"  network   {name:12s} sketch with {len(nd.choices())} choice hole(s)")
            continue
        try:
            flat = flatten(lib, nd, allow_holes=True)
            print(f"  network   {name:12s} {flat.network.stats() if not _has_holes(flat.network) else 'template with integer holes'}")
        except DSLError as e:
            ok = False
            print(f"  network   {name:12s} ERROR {e}")
    for name, sp in lib.specs.items():
        print(f"  spec      {name:12s} {show(sp.guarantee)}")
    return 0 if ok else 1


def _has_holes(net: Network) -> bool:
    from .smt import template_holes
    return bool(template_holes(net))


def cmd_show(args) -> int:
    lib = _load(args)
    net = _network(lib, args)
    print(net.pretty())
    print(json.dumps(net.stats()))
    _write(args.out, net.to_dict())
    return 0


def cmd_sim(args) -> int:
    lib = _load(args)
    net = _network(lib, args)
    inputs = {}
    for item in args.input or []:
        k, v = item.split("=", 1)
        inputs[k] = [int(c) for c in v.strip()]
    for k in net.inputs:
        inputs.setdefault(k, [])
    T = args.steps or max((len(v) for v in inputs.values()), default=0)
    tr = simulate(net, inputs, T)
    print(tr.table())
    return 0


def _status_code(results) -> int:
    if any(r.status == Status.COUNTEREXAMPLE for r in results):
        return 1
    if all(r.verified for r in results):
        return 0
    return 2


def cmd_verify(args) -> int:
    lib = _load(args)
    spec = lib.specs[args.spec]
    net = _network(lib, args)
    engines = tuple(args.engines.split(","))
    results = verify_all(net, spec, T=args.horizon, engines=engines, timeout_s=args.timeout,
                         max_states=args.max_states)
    print(spec.describe())
    for r in results:
        print(r.summary())
    payload: dict[str, Any] = {"results": [r.to_dict() for r in results]}
    code = _status_code(results)
    if args.compositional:
        if not args.network:
            raise DSLError("--compositional needs --network (a composition of primitives)")
        c = compositional_verify(lib, lib.networks[args.network], spec, max_states=args.max_states,
                                 timeout_s=args.timeout)
        print(c.summary())
        payload["compositional"] = {"result": c.result.to_dict(),
                                    "primitive_proofs": {k: v.to_dict() for k, v in c.primitive_proofs.items()}}
    _write(args.out, _record("verify", spec, net, payload))
    return code


def cmd_synth(args) -> int:
    lib = _load(args)
    spec = lib.specs[args.spec]
    m = args.method
    kw = dict(T=args.horizon, timeout_s=args.timeout)
    if m == "cegis":
        if args.neurons:
            tpl = fully_connected(spec, args.neurons, wmax=args.wmax, vmax=args.vmax)
            res = cegis(tpl, spec, **kw)
            if args.minimize and res.network is not None:
                res = minimize_synapses(tpl, spec, res, T=args.horizon, timeout_s=args.timeout)
        else:
            res, _ = search_neurons(spec, n_max=args.max_neurons, T=args.horizon, timeout_s=args.timeout,
                                    wmax=args.wmax, vmax=args.vmax)
    elif m == "enumerate":
        res = enumerate_params(fully_connected(spec, args.neurons or 1, wmax=args.wmax, vmax=args.vmax), spec, **kw)
    elif m == "compose":
        res = compose_dag(lib, spec, max_size=args.max_size, **kw)
    elif m == "cyclic":
        res = compose_cyclic(lib, spec, k=args.max_size, **kw)
    elif m == "sketch":
        if not args.sketch:
            raise DSLError("--method sketch needs --sketch NETWORK (a network with ?[..] / ?{..} holes)")
        res = sketch(lib, lib.networks[args.sketch], spec, **kw)
    elif m == "classical":
        net, info = classical_network(spec)
        print(spec.describe())
        print(json.dumps({k: v for k, v in info.items()}, indent=2, default=str))
        if net is None:
            _write(args.out, _record("classical", spec, None, {"info": info}))
            return 1 if info.get("status") == "UNREALIZABLE" else 2
        results = verify_all(net, spec, T=args.horizon, timeout_s=args.timeout)
        for r in results:
            print(r.summary())
        print(net.pretty())
        _write(args.out, _record("classical", spec, net, {"info": info, "results": [r.to_dict() for r in results]}))
        return _status_code(results)
    else:
        raise DSLError(f"unknown method {m}")
    print(spec.describe())
    print(f"method={res.method} status={res.status} iterations={res.iterations} candidates={res.candidates} "
          f"examples={len(res.examples)} time={res.total_time_s:.2f}s (synth {res.synth_time_s:.2f}s, "
          f"verify {res.verify_time_s:.2f}s)")
    for line in res.log[-8:]:
        print("  " + line)
    if "neuron_search" in res.detail:
        print("  neuron search: " + json.dumps(res.detail["neuron_search"]))
    if "program" in res.detail:
        print(res.detail["program"])
    if res.network is not None:
        print(res.network.pretty())
        for r in res.verification:
            print(r.summary())
    _write(args.out, _record("synth", spec, res.network, {"synthesis": res.to_dict()}))
    if res.status in (SOLVED, SOLVED_BOUNDED):
        return 0
    if res.status in ("UNREALIZABLE", "EXHAUSTED"):
        return 1
    return 2


def cmd_realize(args) -> int:
    lib = _load(args)
    spec = lib.specs[args.spec]
    try:
        M = machine_from_spec(spec)
    except NotCausal as e:
        print(f"UNREALIZABLE: {e}\n  witness: {e.witness}")
        return 1
    except NotFunctional as e:
        print(f"NOT APPLICABLE: {e}")
        return 2
    Mm = minimize(M)
    print(f"machine states: {M.n}, minimal: {Mm.n}, state bits: {Mm.stats()['state_bits']}")
    net, info = classical_network(spec)
    print(json.dumps({k: v for k, v in info.items()}, indent=2, default=str))
    return 0 if net is not None else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="npc", description="Verifiable Neural Primitive Compiler")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, net=True):
        sp.add_argument("files", nargs="*", help=".npc files (the standard primitive library is always loaded)")
        if net:
            sp.add_argument("--network", help="network name in the .npc files")
            sp.add_argument("--net-json", help="network JSON produced by `npc synth --out`")

    s = sub.add_parser("primitives", help="list the primitive library with contracts and proof status")
    s.add_argument("files", nargs="*")
    s.set_defaults(fn=cmd_primitives)

    s = sub.add_parser("check", help="parse files, prove primitive contracts, flatten networks")
    common(s, net=False)
    s.set_defaults(fn=cmd_check)

    s = sub.add_parser("show", help="print a flattened network")
    common(s)
    s.add_argument("--out")
    s.set_defaults(fn=cmd_show)

    s = sub.add_parser("sim", help="simulate a network on given input strings")
    common(s)
    s.add_argument("--input", action="append", help="NAME=0101...")
    s.add_argument("--steps", type=int)
    s.set_defaults(fn=cmd_sim)

    s = sub.add_parser("verify", help="verify a network against a spec")
    common(s)
    s.add_argument("--spec", required=True)
    s.add_argument("--horizon", type=int, default=10)
    s.add_argument("--engines", default="bmc,exhaustive,reach")
    s.add_argument("--compositional", action="store_true")
    s.add_argument("--timeout", type=float, default=60.0)
    s.add_argument("--max-states", type=int, default=2_000_000)
    s.add_argument("--out")
    s.set_defaults(fn=cmd_verify)

    s = sub.add_parser("synth", help="synthesise a network for a spec")
    common(s, net=False)
    s.add_argument("--spec", required=True)
    s.add_argument("--method", choices=["cegis", "enumerate", "compose", "cyclic", "sketch", "classical"],
                   default="cegis")
    s.add_argument("--neurons", type=int, help="fixed neuron count for cegis/enumerate")
    s.add_argument("--max-neurons", type=int, default=3)
    s.add_argument("--max-size", type=int, default=3, help="instances for compose/cyclic")
    s.add_argument("--sketch", help="network with holes, for --method sketch")
    s.add_argument("--minimize", action="store_true", help="minimise synapse count (cegis --neurons)")
    s.add_argument("--wmax", type=int, default=3)
    s.add_argument("--vmax", type=int, default=7)
    s.add_argument("--horizon", type=int, default=8)
    s.add_argument("--timeout", type=float, default=120.0)
    s.add_argument("--out")
    s.set_defaults(fn=cmd_synth)

    s = sub.add_parser("realize", help="build the spec's machine and decide realisability (Theorem 3)")
    common(s, net=False)
    s.add_argument("--spec", required=True)
    s.set_defaults(fn=cmd_realize)

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except (DSLError, SpecError, NetworkError, KeyError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
