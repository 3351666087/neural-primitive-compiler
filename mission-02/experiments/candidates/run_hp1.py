"""HP-1 ("threshold + state feedback", Mission 01 route): generic IF neurons + per-task CEGIS search.

  python mission-02/experiments/candidates/run_hp1.py

Task: family A, N = 2, letters {LOAD, ROT90}, output img (lag 2). The spec is written in Mission 01's
temporal logic (recursive in the outputs). It is first checked against the HP-2 construction with BMC,
so that HP-1 is given a correct spec of the same function. Then npc.synth.search_neurons runs with
n = 4..7 fully connected neurons (4 are needed just for the 4 outputs), 600 s total.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from cog.ir import compile_ir, map_rules  # noqa: E402
from cog.tasks import family_a  # noqa: E402
from npc.spec import make_spec  # noqa: E402
from npc.synth import cegis, fully_connected  # noqa: E402
from npc.verify import bmc  # noqa: E402

OUT = Path(__file__).parent / "hp1.json"


def npc_spec(N: int):
    task = family_a(N, ["ROT90"], name=f"A{N}rot")
    src = map_rules(["rot90"], {"kind": "grid", "dims": [N]})
    ins = task.input_channels()
    outs = task.output_channels()
    g = []
    for (x, y) in task.space.coords:
        (_, (sx, sy)), = src[(x, y)]
        g.append(f"(img_{x}_{y} <-> (prev[2](LOAD & see_{x}_{y}) | (prev[2](ROT90) & prev(img_{sx}_{sy})) | "
                 f"(prev[2](!LOAD & !ROT90) & prev(img_{x}_{y}))))")
    return task, make_spec(f"A{N}rot", ins, outs, " & ".join(g), assume="!(LOAD & ROT90)")


def main():
    N = 2
    task, sp = npc_spec(N)
    prog = {"name": "hp2", "nodes": [{"id": "mem", "op": "CMR", "letters": {"LOAD": {"map": ["load", "see"]},
                                                                              "ROT90": {"map": ["rot90"]}}}],
            "outputs": {"img": "mem"}}
    net = compile_ir(prog, task.interface())
    chk = bmc(net, sp, 8, timeout_s=120)
    print("spec consistency (HP-2 network vs npc spec, BMC T=8):", chk.status.value, flush=True)
    rows = {"spec_check": chk.status.value, "hp2_neurons": len(net.neurons), "search": []}
    t_start = time.perf_counter()
    budget = 600.0
    for n in range(4, 8):
        remaining = budget - (time.perf_counter() - t_start)
        if remaining <= 5:
            rows["search"].append({"n": n, "status": "NOT_RUN (budget)"})
            break
        tpl = fully_connected(sp, n, in_delays=(1, 2), rec_delays=(1,), wmax=3, vmax=7, bias=(0, 1))
        r = cegis(tpl, sp, T=6, timeout_s=remaining, max_states=200_000)
        rows["search"].append({"n": n, "status": r.status, "iterations": r.iterations, "time_s": round(r.total_time_s, 1),
                               "holes": r.detail.get("holes")})
        print(rows["search"][-1], flush=True)
        if r.status in ("SOLVED", "SOLVED_BOUNDED", "TIMEOUT", "UNKNOWN"):
            break
    rows["total_time_s"] = round(time.perf_counter() - t_start, 1)
    OUT.write_text(json.dumps(rows, indent=2))
    print(json.dumps(rows))


if __name__ == "__main__":
    main()
