"""Mission 02 strict route A on unseen tasks. See mission-02/protocols/UNSEEN_PROTOCOL.md.

  python mission-02/experiments/unseen/run_unseen.py freeze
  python mission-02/experiments/unseen/run_unseen.py generate
  python mission-02/experiments/unseen/run_unseen.py run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "src"))

from cog.auto import construct_auto  # noqa: E402
from cog.check import differential, reach_equiv  # noqa: E402
from cog.ir import IRError, compile_ir, ir_size  # noqa: E402
from cog.learn import vocab_for  # noqa: E402
from cog.tasks import run_reference  # noqa: E402
from cog.unseen import generate  # noqa: E402

MANIFEST = HERE / "freeze-manifest.json"
TASKS = HERE / "tasks.json"
LLM = HERE / "llm_programs.json"
RESULTS = HERE / "results.json"


def tree_hash():
    files = {}
    for root in ("src/cog", "src/npc"):
        for p in sorted((REPO / root).rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                files[str(p.relative_to(REPO))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return hashlib.sha256("".join(f"{k} {v}\n" for k, v in files.items()).encode()).hexdigest(), files


def check_frozen():
    man = json.loads(MANIFEST.read_text())
    h, _ = tree_hash()
    if h != man["tree_sha256"]:
        sys.exit(f"source changed since the freeze ({h[:12]} != {man['tree_sha256'][:12]}); refusing")
    return man


def cmd_freeze(_):
    if MANIFEST.exists():
        sys.exit("already frozen")
    h, files = tree_hash()
    MANIFEST.write_text(json.dumps({"tree_sha256": h, "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "files": files}, indent=2))
    print("frozen", h)


def cmd_generate(_):
    man = check_frozen()
    seed = int(man["tree_sha256"][:16], 16)
    tasks = generate(seed)
    out = []
    for u in tasks:
        t0 = u.build(u.sizes[0])
        out.append({"uid": u.uid, "family": u.family, "params": u.params, "sizes": u.sizes,
                    "interface_smallest": t0.interface()})
    TASKS.write_text(json.dumps({"seed": seed, "tree_sha256": man["tree_sha256"], "tasks": out}, indent=2, default=str))
    for o in out:
        print(o["uid"], o["sizes"], "|", o["interface_smallest"]["description"][:400])


def fsm_neurons(task) -> float:
    if task.space.kind == "grid":
        states = 2 ** len(task.space.coords)
    elif task.space.kind == "objgrid":
        states = 2 ** len(task.space.coords)
    else:
        K, V = task.space.dims
        states = (V + 1) ** K
    frames = 1 + sum((2 ** len(task.data[l.data].coords) if (l.data and task.data[l.data].kind != "vec")
                      else (len(task.data[l.data].coords) if l.data else 1)) for l in task.letters)
    return states * frames


def judge(net, task, smallest: bool) -> dict:
    d = differential(net, task, n=400, T=16, seed=7)
    out = {"differential": d.ok, "failing": d.detail.get("failing_traces"),
           "counterexample": d.counterexample if d.ok is False else None}
    if smallest and not task.queries and d.ok and len(task.space.coords) <= 9 and task.space.kind != "objgrid":
        r = reach_equiv(net, task, max_states=2_000_000, timeout_s=300)
        out["reach_equiv"] = r.ok
        out["reach_states"] = r.detail.get("states")
    return out


def random_baseline(u, n=100, seed=0) -> dict:
    """Random structure: each command gets a uniformly random map from the vocabulary; outputs as LLM wrote them."""
    rng = random.Random(seed)
    t = u.build(u.sizes[0])
    iface = t.interface()
    data = [l["data"] for l in iface["letters"] if l["data"]]
    vocab = vocab_for(iface["state_space"], data)
    ok = 0
    for i in range(n):
        letters = {l["name"]: {"map": rng.choice(vocab)} for l in iface["letters"] if l["cond_delay"] is None}
        prog = {"name": "rand", "nodes": [{"id": "mem", "op": "CMR", "letters": letters}], "outputs": {"img": "mem"}}
        t_img = u.build(u.sizes[0])
        t_img.outputs = [o for o in t_img.outputs if o.kind == "img"]
        t_img.letters = [l for l in t_img.letters if l.cond_delay is None]
        try:
            if differential(compile_ir(prog, t_img.interface()), t_img, n=60, T=12, seed=i).ok:
                ok += 1
        except IRError:
            pass
    return {"samples": n, "correct_on_state_image": ok, "vocab_size": len(vocab)}


def cmd_run(args):
    man = check_frozen()
    data = json.loads(TASKS.read_text())
    seed = data["seed"]
    units = {u.uid: u for u in generate(seed)}
    llm = json.loads(LLM.read_text()) if LLM.exists() else {}
    rows = []
    for spec in data["tasks"]:
        u = units[spec["uid"]]
        if args.only and u.uid not in args.only:
            continue
        print(f"=== {u.uid} {u.family} {u.params}", flush=True)
        row = {"uid": u.uid, "family": u.family, "params": u.params, "sizes": u.sizes, "routes": {}}
        tasks = [u.build(s) for s in u.sizes]
        row["fsm_onehot_neurons"] = [f"{fsm_neurons(t):.3g}" for t in tasks]
        # A-auto: oracle at the two smallest sizes only
        t0 = time.perf_counter()
        probe = tasks[:2] if len(tasks) >= 2 else tasks
        r = construct_auto([t.interface() for t in probe], [lambda tr, T, t=t: run_reference(t, tr, T) for t in probe])
        auto = {"status": r.status, "reason": r.reason, "oracle_traces": r.oracle_traces, "vocab_candidates": r.vocab_candidates,
                "construct_time_s": round(time.perf_counter() - t0, 2), "per_size": []}
        if r.status == "BUILT":
            for i, t in enumerate(tasks):
                try:
                    prog = r.rules.instantiate(t.interface())
                    net = compile_ir(prog, t.interface())
                    auto["per_size"].append({"size": str(u.sizes[i]), "neurons": len(net.neurons), "synapses": len(net.synapses),
                                             "ir_tokens": ir_size(prog), **judge(net, t, i == 0)})
                except (KeyError, IRError) as e:
                    auto["per_size"].append({"size": str(u.sizes[i]), "error": str(e)})
        auto["success_all_sizes"] = bool(auto["per_size"]) and all(p.get("differential") for p in auto["per_size"])
        row["routes"]["A_auto"] = auto
        print("  A_auto:", auto["status"], auto["reason"], [(p["size"], p.get("differential")) for p in auto["per_size"]], flush=True)
        # A-LLM
        if u.uid in llm:
            entry = llm[u.uid]
            progs = [entry["program"] if "program" in entry else entry["per_size"][str(tuple(s) if isinstance(s, list) else s)]
                     for s in u.sizes]
            lr = {"ir_tokens": [ir_size(p) for p in progs], "per_size_programs": "per_size" in entry, "per_size": []}
            for i, t in enumerate(tasks):
                prog = progs[i]
                try:
                    net = compile_ir(prog, t.interface())
                    lr["per_size"].append({"size": str(u.sizes[i]), "neurons": len(net.neurons), "synapses": len(net.synapses),
                                           **judge(net, t, i == 0)})
                except (KeyError, IRError) as e:
                    lr["per_size"].append({"size": str(u.sizes[i]), "error": str(e)})
            lr["success_all_sizes"] = all(p.get("differential") for p in lr["per_size"])
            row["routes"]["A_llm"] = lr
            print("  A_llm:", [(p["size"], p.get("differential"), p.get("reach_equiv"), p.get("error")) for p in lr["per_size"]], flush=True)
        row["routes"]["random_structure"] = random_baseline(u)
        print("  random:", row["routes"]["random_structure"], flush=True)
        rows.append(row)
    RESULTS.write_text(json.dumps({"tree_sha256": man["tree_sha256"], "rows": rows}, indent=2, default=str))
    summarize(rows)


def summarize(rows):
    lines = ["# Unseen tasks (strict route A)", "",
             "| task | family | params | A-auto | A-LLM | random structure (img only) | one-hot FSM neurons (by size) |",
             "|---|---|---|---|---|---|---|"]
    for r in rows:
        a = r["routes"]["A_auto"]
        ac = ("OK " if a["success_all_sizes"] else "FAIL ") + (", ".join(f"{p['size']}:{p.get('neurons', '-')}n" for p in a["per_size"])
                                                              if a["per_size"] else a["reason"][:80])
        l = r["routes"].get("A_llm")
        lc = "—" if not l else ("OK " if l["success_all_sizes"] else "FAIL ") + ", ".join(
            f"{p['size']}:{'ok' if p.get('differential') else 'x'}" for p in l["per_size"])
        rs = r["routes"]["random_structure"]
        params = json.dumps(r["params"]).replace("|", "/")[:120]
        lines.append(f"| {r['uid']} | {r['family']} | `{params}` | {ac} | {lc} | {rs['correct_on_state_image']}/{rs['samples']} | "
                     f"{', '.join(r['fsm_onehot_neurons'])} |")
    (HERE / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["freeze", "generate", "run"])
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()
    {"freeze": cmd_freeze, "generate": cmd_generate, "run": cmd_run}[args.cmd](args)


if __name__ == "__main__":
    main()
