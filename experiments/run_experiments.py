"""Reproducible experiment runner.

  python experiments/run_experiments.py abc        # groups A-C, all baselines and synthesisers
  python experiments/run_experiments.py scaling    # Q3: monolithic vs compositional verification cost
  python experiments/run_experiments.py summary    # regenerate markdown tables from raw JSON

Raw results go to experiments/results/*.json. Nothing here trains parameters by
gradient; "task-level parameter search" is reported per method.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "src"))

from npc.compose import compositional_verify  # noqa: E402
from npc.dsl import InstDecl, NetworkDef, flatten, load_with_stdlib  # noqa: E402
from npc.fsm import NotCausal, NotFunctional, classical_network, machine_from_spec, minimize  # noqa: E402
from npc.network import full_leak  # noqa: E402
from npc.spec import make_spec  # noqa: E402
from npc.synth import (compose_cyclic, compose_dag, enumerate_params, fully_connected,  # noqa: E402
                       minimize_synapses, search_neurons)
from npc.verify import Status, bmc, reach, verify_all  # noqa: E402

RES = ROOT / "results"
TASKS = ["A1_delayed_coincidence", "A2_burst2of3", "A3_a_without_recent_b",
         "B1_count3_reset", "B2_remember_query", "B2r_remember_query_lat2", "B3_first_since_reset",
         "C1_toggle_sparse", "C2_parity_dense", "C3_latched_alarm"]
DESIGNS = {"A1_delayed_coincidence": ["A1_direct", "A1_prims"], "A2_burst2of3": ["A2_direct"],
           "A3_a_without_recent_b": ["A3_direct"], "B1_count3_reset": ["B1_direct"],
           "B2_remember_query": ["B2_direct"], "B2r_remember_query_lat2": ["B2r_direct"],
           "B3_first_since_reset": ["B3_direct"], "C1_toggle_sparse": ["C1_direct"], "C3_latched_alarm": ["C3_direct"]}
T = 8


def net_entry(net, spec, t_build=0.0):
    t0 = time.perf_counter()
    res = verify_all(net, spec, T=T, timeout_s=300, max_traces=1 << 20)
    st = net.stats()
    r = res[-1]
    return {
        "stats": st,
        "effective_state_bits": r.stats.get("effective_state_bits"),
        "reachable_network_states": r.stats.get("system_states"),
        "verification": {x.engine: {"status": x.status.value, "time_s": round(x.time_s, 4)} for x in res},
        "verify_total_s": round(time.perf_counter() - t0, 4),
        "build_time_s": round(t_build, 4),
        "network": net.to_dict(),
    }


def synth_entry(r, spec, training):
    e = {"status": r.status, "method": r.method, "iterations": r.iterations, "candidates": r.candidates,
         "counterexamples_used": max(0, len(r.examples) - 1), "synth_time_s": round(r.synth_time_s, 3),
         "verify_time_s": round(r.verify_time_s, 3), "total_time_s": round(r.total_time_s, 3),
         "task_level_parameter_search": training, "gradient_training": False,
         "detail": {k: v for k, v in r.detail.items() if k != "attempts"}, "log": r.log[-12:]}
    if r.network is not None:
        e["result"] = net_entry(r.network, spec, r.total_time_s)
    return e


def run_task(lib, name, budget):
    sp = lib.specs[name]
    row = {"task": name, "doc": sp.doc, "spec": sp.to_dict(), "horizon": T}
    print(f"\n=== {name}: {sp.doc}", flush=True)
    # 1. traditional FSM baseline
    try:
        M = machine_from_spec(sp)
        Mm = minimize(M)
        row["fsm"] = {"machine_states": M.n, "minimal_states": Mm.n, "state_bits": Mm.stats()["state_bits"]}
    except NotCausal as e:
        row["fsm"] = {"status": "UNREALIZABLE", "reason": str(e)}
    except NotFunctional as e:
        row["fsm"] = {"status": "NOT_APPLICABLE", "reason": str(e)}
    print("  fsm:", row["fsm"], flush=True)
    # 2. classical construction (no search)
    t0 = time.perf_counter()
    net, info = classical_network(sp)
    row["classical"] = {"info": {k: v for k, v in info.items() if k != "witness"}, "witness": info.get("witness")}
    if net is not None:
        row["classical"]["result"] = net_entry(net, sp, time.perf_counter() - t0)
    print("  classical:", info.get("status"), info.get("neurons"), flush=True)
    # 3. direct designs
    row["direct"] = {}
    for d in DESIGNS.get(name, []):
        nd = lib.networks[d]
        net = flatten(lib, nd).network
        ent = net_entry(net, sp)
        if not nd.neurons:
            c = compositional_verify(lib, nd, sp)
            ent["compositional"] = {"status": c.result.status.value, "abstract_states": c.result.stats.get("product_states"),
                                    "time_s": round(c.abstract_time_s, 4), "proof_time_s": round(c.proof_time_s, 4)}
        row["direct"][d] = ent
        print(f"  direct {d}:", ent["verification"]["reach"]["status"], ent["stats"]["neurons"], "neurons", flush=True)
    # 4. monolithic CEGIS, integrate-and-fire neurons
    r, trail = search_neurons(sp, n_max=4, T=T, timeout_s=budget)
    if r.network is not None:
        n = r.network.meta.get("n") or len(r.network.neurons)
        tpl = fully_connected(sp, int(trail[-1]["n"]))
        r = minimize_synapses(tpl, sp, r, T=T, timeout_s=budget / 2)
    row["cegis_if"] = synth_entry(r, sp, "yes: integer parameters found by SMT constraint solving on counterexamples")
    row["cegis_if"]["neuron_search"] = trail
    print("  cegis_if:", r.status, trail, flush=True)
    # 5. monolithic CEGIS, memoryless (McCulloch-Pitts) neurons only - the Q2 control
    full = full_leak(0, 7)
    r, trail = search_neurons(sp, n_max=4, T=T, timeout_s=budget, leak=(full, full))
    row["cegis_memoryless"] = synth_entry(r, sp, "yes: as cegis_if, but every neuron forced memoryless (leak=full)")
    row["cegis_memoryless"]["neuron_search"] = trail
    print("  cegis_memoryless:", r.status, trail, flush=True)
    # 6. compositional enumeration over the primitive library (DAGs)
    r = compose_dag(lib, sp, T=T, max_size=3, timeout_s=budget / 2)
    row["compose_dag"] = synth_entry(r, sp, "structure only: parameters picked from a fixed primitive grid")
    print("  compose_dag:", r.status, r.detail.get("expr"), flush=True)
    # 7. compositions with feedback (C group)
    if name.startswith("C"):
        for k in (2, 3):
            r = compose_cyclic(lib, sp, k=k, T=T, timeout_s=budget)
            row[f"compose_cyclic_k{k}"] = synth_entry(r, sp, "structure only: parameters picked from a fixed grid")
            print(f"  compose_cyclic k={k}:", r.status, r.candidates, "candidates", flush=True)
            if r.status == "SOLVED":
                break
    # 8. brute-force parameter enumeration (no solver) on a small 1-neuron template, A group only
    if name.startswith("A"):
        tpl = fully_connected(sp, 1, in_delays=(1, 2, 3), rec_delays=(), wmax=1, vmax=3, bias=(0, 0))
        r = enumerate_params(tpl, sp, T=T, timeout_s=budget / 2)
        row["enumerate"] = synth_entry(r, sp, "yes: exhaustive enumeration of integer parameters")
        row["enumerate"]["space"] = r.detail.get("space")
        tpl_m = fully_connected(sp, 1, in_delays=(1, 2, 3), rec_delays=(), wmax=1, vmax=3, bias=(0, 0))
        from npc.synth import cegis
        r2 = cegis(tpl_m, sp, T=T, timeout_s=budget / 2)
        row["cegis_same_template"] = synth_entry(r2, sp, "yes: SMT on the same small template as `enumerate`")
        print("  enumerate:", r.status, r.candidates, "candidates; cegis same template:", r2.status, flush=True)
    return row


def part_abc(args):
    lib = load_with_stdlib(ROOT / "tasks.npc", ROOT / "designs.npc")
    RES.mkdir(exist_ok=True)
    for name in args.tasks or TASKS:
        t0 = time.perf_counter()
        try:
            row = run_task(lib, name, args.budget)
        except Exception as e:  # keep going; failures are data
            row = {"task": name, "error": repr(e), "traceback": traceback.format_exc()}
            print("  ERROR", e, flush=True)
        row["wall_time_s"] = round(time.perf_counter() - t0, 2)
        (RES / f"{name}.json").write_text(json.dumps(row, indent=2, default=str))


# ---------------------------------------------------------------- Q3 scaling
def chain(prim, args, N, ports):
    nd = NetworkDef(f"chain_{prim}_{N}", max_delay=4, inputs=["a"])
    prev = "a"
    for j in range(N):
        b = {p: "_" for p in ports}
        b[ports[0]] = prev
        nd.instances.append(InstDecl(f"i{j}", prim, dict(args), b))
        prev = f"i{j}.out"
    nd.outputs.append(("y", prev))
    return nd


def part_scaling(args):
    from npc import compose
    lib = load_with_stdlib()
    rows = []
    fams = [("relay", {"d": 1}, ["in"], lambda N: f"y <-> prev[{N}](a)", 14),
            ("counter", {"k": 2}, ["in", "rst"], lambda N: f"y <-> prev[{N}](a & modcount[{2 ** N}](a) == 0)", 9),
            ("window", {"k": 2, "w": 2}, ["in"], None, 7)]
    for prim, pargs, ports, specf, Nmax in fams:
        for N in range(1, Nmax + 1):
            nd = chain(prim, pargs, N, ports)
            net = flatten(lib, nd).network
            if specf is None:
                # no closed-form spec: check a safety property instead (output never fires twice in a row
                # is false for windows; use a tautology-free invariant: y -> prev(true))
                sp = make_spec(f"chain{N}", ["a"], ["y"], "y -> once[1,%d](a)" % (2 * N))
            else:
                sp = make_spec(f"chain{N}", ["a"], ["y"], specf(N))
            compose._PROOF_CACHE.clear()
            mono = reach(net, sp, max_states=3_000_000, timeout_s=args.budget)
            comp = compositional_verify(lib, nd, sp, max_states=3_000_000, timeout_s=args.budget)
            comp2 = compositional_verify(lib, nd, sp, max_states=3_000_000, timeout_s=args.budget)  # cached proofs
            b = bmc(net, sp, N + 6, timeout_s=args.budget)
            row = {"family": prim, "N": N, "neurons": len(net.neurons), "spec": specf(N) if specf else sp.to_dict()["guarantee"],
                   "monolithic": {"status": mono.status.value, "states": mono.stats.get("product_states"),
                                  "network_states": mono.stats.get("system_states"), "time_s": round(mono.time_s, 4)},
                   "compositional": {"status": comp.result.status.value, "states": comp.result.stats.get("product_states"),
                                     "abstract_states": comp.result.stats.get("system_states"),
                                     "time_s": round(comp.abstract_time_s, 4), "proof_time_s": round(comp.proof_time_s, 4),
                                     "time_s_cached": round(comp2.abstract_time_s + comp2.proof_time_s, 4)},
                   "bmc": {"status": b.status.value, "horizon": N + 6, "time_s": round(b.time_s, 4)}}
            rows.append(row)
            print(json.dumps(row), flush=True)
            if mono.status != Status.VERIFIED_UNBOUNDED and comp.result.status != Status.VERIFIED_UNBOUNDED:
                break
    (RES / "scaling.json").write_text(json.dumps(rows, indent=2))


# ---------------------------------------------------------------- Q2 sweep
def part_q2(args):
    """Integrate-and-fire vs memoryless-only neurons on counters (need state) and windows (need history)."""
    specs = [make_spec(f"count{k}_reset", ["a", "r"], ["y"], f"y <-> prev(a & !r & modcount[{k}](a; r) == 0)")
             for k in (2, 3, 4)]
    specs += [make_spec(f"window{k}of{w}", ["a"], ["y"], f"y <-> prev(count[{w}](a) >= {k})") for k, w in ((2, 3), (3, 4))]
    full = full_leak(0, 7)
    rows = []
    for sp in specs:
        Q = minimize(machine_from_spec(sp)).n
        row = {"task": sp.name, "guarantee": sp.to_dict()["guarantee"], "fsm_states": Q}
        for label, kw in (("if", {}), ("memoryless", {"leak": (full, full)})):
            r, trail = search_neurons(sp, n_max=4, T=T, timeout_s=args.budget, **kw)
            row[label] = {"status": r.status, "trail": trail, "time_s": round(r.total_time_s, 2),
                          "stats": r.network.stats() if r.network else None,
                          "network": r.network.to_dict() if r.network else None}
            print(sp.name, label, r.status, trail, flush=True)
        rows.append(row)
    (RES / "q2_dynamics.json").write_text(json.dumps(rows, indent=2))


# ---------------------------------------------------------------- summary
def _fmt(x):
    return "—" if x is None else x


def part_summary(args):
    lines = ["# Experiment summary (groups A–C)", "",
             "Generated by `python experiments/run_experiments.py summary` from `experiments/results/*.json`.",
             "Neurons / synapses / state_bits (upper bound) / effective bits = log2(reachable network states).",
             "Every listed network was re-verified by bmc (T=8), exhaustive (when ≤ 2^20 traces) and unbounded reach.",
             "CEGIS time = neuron-search time (all sizes tried) + synapse-minimisation time.", ""]
    hdr = "| task | FSM min states (bits) | classical | direct | CEGIS (IF) | CEGIS (memoryless) | compose_dag | other |"
    lines += [hdr, "|" + "---|" * 8]
    for name in TASKS:
        p = RES / f"{name}.json"
        if not p.exists():
            continue
        r = json.loads(p.read_text())
        if "error" in r:
            lines.append(f"| {name} | ERROR {r['error']} |")
            continue
        f = r["fsm"]
        fsm = f"{f['minimal_states']} ({f['state_bits']})" if "minimal_states" in f else f.get("status")

        def cell(e):
            if e is None:
                return "—"
            if "neuron_search" in e and "result" in e:  # CEGIS: search time from the trail + minimisation
                e = dict(e)
                e["total_time_s"] = round(sum(x["time_s"] for x in e["neuron_search"])
                                          + (e["detail"].get("minimization_time_s") or 0), 3)
            if "result" not in e:
                return f"{e.get('status')} ({e.get('total_time_s', '?')}s)"
            s = e["result"]["stats"]
            stat = e["result"]["verification"]["reach"]["status"].replace("VERIFIED_", "")
            return (f"{s['neurons']}n/{s['synapses']}s, {s['state_bits']}b/{e['result']['effective_state_bits']}eb, "
                    f"{e.get('total_time_s', e['result']['build_time_s'])}s, {stat}")
        cl = r["classical"]
        clc = cell({"result": cl["result"], "total_time_s": cl["result"]["build_time_s"]}) if "result" in cl else cl["info"].get("status")
        dr = "; ".join(f"{k}: {cell({'result': v, 'total_time_s': v['verify_total_s']})}" for k, v in r["direct"].items()) or "—"
        other = []
        for k in ("compose_cyclic_k2", "compose_cyclic_k3", "enumerate", "cegis_same_template"):
            if k in r:
                other.append(f"{k}: {cell(r[k]) if 'result' in r[k] else r[k]['status'] + ' (' + str(r[k]['total_time_s']) + 's, ' + str(r[k]['candidates']) + ' cand)'}")
        lines.append(f"| {name} | {fsm} | {clc} | {dr} | {cell(r['cegis_if'])} | {cell(r['cegis_memoryless'])} | "
                     f"{cell(r['compose_dag'])} | {'<br>'.join(other) or '—'} |")
    lines += ["", "## Minimal neuron counts proved by CEGIS (UNREALIZABLE below the reported size)", "",
              "| task | IF neuron search | memoryless neuron search |", "|---|---|---|"]
    for name in TASKS:
        p = RES / f"{name}.json"
        if not p.exists():
            continue
        r = json.loads(p.read_text())
        if "error" in r:
            continue
        f1 = ", ".join(f"n={t['n']}:{t['status']}" for t in r["cegis_if"]["neuron_search"])
        f2 = ", ".join(f"n={t['n']}:{t['status']}" for t in r["cegis_memoryless"]["neuron_search"])
        lines.append(f"| {name} | {f1} | {f2} |")
    q2 = RES / "q2_dynamics.json"
    if q2.exists():
        lines += ["", "## Q2 sweep: integrate-and-fire vs memoryless-only neurons (CEGIS neuron search, same template ranges)", "",
                  "| task | min FSM states | IF trail | memoryless trail |", "|---|---|---|---|"]
        for x in json.loads(q2.read_text()):
            f = lambda tr: ", ".join(f"n={t['n']}:{t['status']}" for t in tr)
            lines.append(f"| {x['task']} | {x['fsm_states']} | {f(x['if']['trail'])} | {f(x['memoryless']['trail'])} |")
    sp = RES / "scaling.json"
    if sp.exists():
        rows = json.loads(sp.read_text())
        lines += ["", "## Q3 scaling: monolithic vs compositional (explicit-state) verification", "",
                  "| family | N | neurons | mono states | mono time s | comp abstract states | comp time s (+proofs) | comp cached s | BMC(N+6) s |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for x in rows:
            m, c, b = x["monolithic"], x["compositional"], x["bmc"]
            lines.append(f"| {x['family']} | {x['N']} | {x['neurons']} | {_fmt(m['states'])} ({m['status'].replace('VERIFIED_', '')}) | "
                         f"{m['time_s']} | {_fmt(c['states'])} ({c['status'].replace('VERIFIED_', '')}) | {c['time_s']} (+{c['proof_time_s']}) | "
                         f"{c['time_s_cached']} | {b['time_s']} ({b['status'].replace('VERIFIED_', '')}) |")
    (RES / "SUMMARY_ABC.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("part", choices=["abc", "scaling", "q2", "summary"])
    ap.add_argument("--tasks", nargs="*")
    ap.add_argument("--budget", type=float, default=240.0, help="seconds per searcher per task")
    args = ap.parse_args()
    {"abc": part_abc, "scaling": part_scaling, "q2": part_q2, "summary": part_summary}[args.part](args)


if __name__ == "__main__":
    main()
