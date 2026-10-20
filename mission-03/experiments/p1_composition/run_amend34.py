"""P1 under protocol amendments 3 and 4 (DEV tasks UA0, UA2, UA3, UA4), plus the UA0 end-to-end build.

  python mission-03/experiments/p1_composition/run_amend34.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "p1b_concept"))

import cond_fit as C  # noqa: E402
from run_concept import solve  # noqa: E402
from run_p1 import (HORIZON, PROBES, UNSEEN, W, compile_ir, differential, generate, observe, table_map)  # noqa: E402

REGION_IR = {"row0": {"row": 0}, "row-1": {"row": "last"}, "col0": {"col": 0}, "col-1": {"col": "last"}, "all": {"all": True}}


def solve_region(pairs, coords):
    out, R = solve(pairs, coords, "region")
    return R, out.get("second_solution") == "unsat"


def assemble(u, data, fits, guard_ir, d):
    """Whole program: plain commands fitted from delay-0 events (one 'branch' each), conditional command from
    `fits`, wired with the generic CMR + ANY + GATE pattern (Mission 02, P4)."""
    name = u.params["cond"][0]
    probe = {N: u.build(N) for N in PROBES}
    coords = {N: probe[N].space.coords for N in PROBES}
    plain = {}
    for cmd, _ in u.params["commands"]:
        ev = {N: C.at_delay(C.letter_events(probe[N], data[N], cmd), 0) for N in PROBES}
        fit, why = C.branch_fit(ev, coords)
        if fit is None:
            return {"status": f"command {cmd}: {why}"}
        if len(fit[1]) != 1:
            return {"status": f"command {cmd}: {len(fit[1])} minimal explanations"}
        plain[cmd] = fit
    if any(len(f[1]) != 1 for f in fits.values()):
        return {"status": "conditional branches not unique"}
    out = []
    for N in (3, 5, 8, 11):
        t = u.build(N)

        def rel(fit, N=N):
            pieces, covers = fit
            k = PROBES.index(N) if N in PROBES else None
            return frozenset().union(*((pieces[i][0][k] if k is not None else pieces[i][1][HORIZON.index(N)]) for i in covers[0]))
        cmds = {c: table_map(rel(f)) for c, f in plain.items()}
        prog = W.spatial(cmds, cond=(name, "top row", table_map(rel(fits[True])), table_map(rel(fits[False])), d))
        for node in prog["nodes"]:
            if node["id"] == "condR":
                node["where"] = guard_ir
        r = differential(compile_ir(prog, t.interface()), t, n=400, T=16, seed=7)
        out.append({"N": N, "differential": r.ok, "failing": r.detail.get("failing_traces")})
    return {"status": "built", "per_size": out}


def main(uids=("UA0", "UA2", "UA3", "UA4"), units=None, out_name="p1_amend34.json"):
    if units is None:
        seed = json.loads((UNSEEN / "tasks.json").read_text())["seed"]
        units = {u.uid: u for u in generate(seed)}
    rows = []
    t0 = time.perf_counter()
    for uid in uids:
        u = units[uid]
        data = {N: observe(u.build(N)) for N in PROBES}
        stash = {}
        row = C.explain(u, u.params["cond"][0], data, solve_region=solve_region, stash=stash)
        gs = row.get("guard_family", {}).get("consistent_guards", [])
        if uid == "UA0" and len(gs) == 1 and gs[0].startswith("ANY ") and gs[0][4:] in REGION_IR:
            fits, _, d = stash[gs[0]]
            row["end_to_end_guard_family"] = assemble(u, data, fits, REGION_IR[gs[0][4:]], d)
        print(json.dumps(row, default=str)[:3000], flush=True)
        rows.append(row)
    (HERE / out_name).write_text(json.dumps({"rows": rows, "time_s": round(time.perf_counter() - t0, 1)}, indent=1, default=str))


if __name__ == "__main__":
    main()
