"""Run the LLM-proposed sketches for groups A-C and store raw results."""
import json, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "src"))
from npc.dsl import load_with_stdlib
from npc.synth import sketch
from npc.verify import verify_all

lib = load_with_stdlib(HERE.parent / "tasks.npc", HERE / "ABC.npc")
pairs = {"A3_llm1": "A3_a_without_recent_b", "B2_llm1": "B2_remember_query", "B3_llm1": "B3_first_since_reset",
         "C1_llm1": "C1_toggle_sparse", "C2_llm1": "C2_parity_dense", "C3_llm1": "C3_latched_alarm"}
rows = {}
for sk, task in pairs.items():
    sp = lib.specs[task]
    r = sketch(lib, lib.networks[sk], sp, T=8, timeout_s=240)
    row = {"task": task, "status": r.status, "candidates": r.candidates, "solver_iterations": r.iterations,
           "time_s": round(r.total_time_s, 3), "assignment": r.detail.get("assignment"),
           "choice_space": r.detail.get("choice_space"), "attempts": r.detail.get("attempts")}
    if r.network is not None:
        res = verify_all(r.network, sp, T=8)
        row["reverify"] = {x.engine: x.status.value for x in res}
        row["stats"] = r.network.stats()
        row["network"] = r.network.to_dict()
    rows[sk] = row
    print(sk, task, r.status, row.get("stats", {}).get("neurons"), "neurons", row["time_s"], "s",
          "attempts:", [(a.get("assignment"), a["status"]) for a in (r.detail.get("attempts") or [])][:6], flush=True)
(HERE / "abc_results.json").write_text(json.dumps(rows, indent=2, default=str))
