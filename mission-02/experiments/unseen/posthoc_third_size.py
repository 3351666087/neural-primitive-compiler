"""POST-HOC check, outside the frozen protocol (added after results.json was written).

In the frozen run, binding (B) and objects-on-grid (AB) tasks list only two sizes and A-auto probed both,
so those rows say nothing about extrapolation. Here A-auto is re-run with the oracle at exactly the same two
sizes, and its rules are instantiated at a third size that no route ever saw, with no oracle call at that
size. The third size (B: K+3, V+2; AB: K+2, N+3; A: N = 11) was chosen after seeing the frozen results.
The source tree hash is checked, so the code is the frozen code.

A-LLM spatial programs are size-independent and are also judged at N = 11. A-LLM B/AB programs are per-size
(N-IR-1) and have no third-size version; none is written here.

  python mission-02/experiments/unseen/posthoc_third_size.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_unseen import LLM, TASKS, check_frozen  # noqa: E402

from cog.auto import construct_auto  # noqa: E402
from cog.check import differential  # noqa: E402
from cog.ir import IRError, compile_ir  # noqa: E402
from cog.tasks import run_reference  # noqa: E402
from cog.unseen import generate  # noqa: E402

OUT = HERE / "posthoc_third_size.json"


def third_size(u):
    if u.family == "A":
        return 11
    a, b = u.sizes[0]
    return (a + 3, b + 2) if u.family == "B" else (a + 2, b + 3)


def main():
    man = check_frozen()
    seed = json.loads(TASKS.read_text())["seed"]
    llm = json.loads(LLM.read_text())
    rows = []
    for u in generate(seed):
        s3 = third_size(u)
        probe = [u.build(s) for s in u.sizes[:2]]
        t3 = u.build(s3)
        oracles = [lambda tr, T, t=t: run_reference(t, tr, T) for t in probe]
        t0 = time.perf_counter()
        r = construct_auto([t.interface() for t in probe], oracles)
        row = {"uid": u.uid, "family": u.family, "probed_sizes": [str(s) for s in u.sizes[:2]], "third_size": str(s3),
               "auto_status": r.status, "oracle_traces_at_probe_sizes": r.oracle_traces}
        if r.status == "BUILT":
            try:
                net = compile_ir(r.rules.instantiate(t3.interface()), t3.interface())
                d = differential(net, t3, n=400, T=16, seed=11)
                row["auto"] = {"neurons": len(net.neurons), "synapses": len(net.synapses), "differential": d.ok,
                               "failing": d.detail.get("failing_traces")}
            except (KeyError, IRError) as e:
                row["auto"] = {"error": f"{type(e).__name__}: {e}"}
        row["oracle_at_third_size"] = "none passed (oracles list covers probed sizes only)"
        entry = llm.get(u.uid, {})
        if "program" in entry:
            try:
                net = compile_ir(entry["program"], t3.interface())
                d = differential(net, t3, n=400, T=16, seed=11)
                row["llm"] = {"neurons": len(net.neurons), "differential": d.ok, "failing": d.detail.get("failing_traces")}
            except (KeyError, IRError) as e:
                row["llm"] = {"error": f"{type(e).__name__}: {e}"}
        else:
            row["llm"] = "no size-independent program (per-size programs only, N-IR-1)"
        row["time_s"] = round(time.perf_counter() - t0, 2)
        print(row, flush=True)
        rows.append(row)
    OUT.write_text(json.dumps({"label": "POST-HOC, outside frozen protocol", "tree_sha256": man["tree_sha256"],
                               "rows": rows}, indent=2, default=str))


if __name__ == "__main__":
    main()
