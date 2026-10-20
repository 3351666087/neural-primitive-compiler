"""Generate tables.md from own logs (per_task.tsv, raw/) and, last, the prior-arm result files."""
import csv, json
from pathlib import Path
D = Path(__file__).parent
R = D.parent
rows = list(csv.DictReader(open(D / "per_task.tsv"), delimiter="\t"))
out = []
out.append("| task | `npc realize` | proposals | verifier calls in loop | wall s (prev result → this result) | npc tool s | final status | neurons | synapses | state_bits | max \\|w\\| | max delay |")
out.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
for r in rows:
    status = r["reach_line"].split(" (")[0].replace("[reach] ", "reach ")
    out.append(f"| {r['task']} | {r['realize']} | {r['proposals']} | {r['verifier_calls_in_loop']} | {r['wall_s_prev_result_to_result']} | {r['tool_s']} | {status} | {r['neurons']} | {r['synapses']} | {r['state_bits']} | {r['max_abs_weight']} | {r['max_delay_used']} |")
out.append("")
out.append("### Verbatim status lines (from `raw/`)\n")
calls = list(csv.DictReader(open(D / "calls.tsv"), delimiter="\t"))
short = {"B2_remember_query": "B2", "B3_first_since_reset": "B3", "C1_toggle_sparse": "C1", "C2_parity_dense": "C2",
         "C3_latched_alarm": "C3", "Dhand_second_b_after_a": "Dhand"}
for r in rows:
    k = short.get(r["task"], r["task"])
    synth = [c for c in calls if c["task"] == k and c["sub"] == "synth"][-1]
    rechk = [c for c in calls if c["task"] == f"{k}_recheck" and c["sub"] == "verify" and c["exit"] != "3"][-1]
    out.append(f"**{r['task']}**: proposal `{k}_p1`, synth log `raw/{synth['raw']}`, re-check log `raw/{rechk['raw']}` (exit {rechk['exit']})\n")
    out.append("```")
    for f in (synth["raw"], rechk["raw"]):
        for l in (D / "raw" / f).read_text().splitlines():
            if l.startswith(("$ npc", "method=", "[bmc]", "[reach]", "[exhaustive]")):
                out.append(l)
    out.append("```\n")
# ---- prior arm, read only now
abc = json.load(open(R / "llm_sketches" / "abc_results.json"))
dres = json.load(open(R / "D_unseen" / "results.json"))["rows"]
prior = {}
for v in abc.values():
    prior.setdefault(v["task"], []).append((v["network"]["name"], v["status"], v.get("candidates"), v.get("choice_space"), v.get("time_s"), v.get("stats")))
for row in dres:
    for name, v in (row.get("llm_sketches") or {}).items():
        prior.setdefault(row["task"], []).append((name, v["status"], v.get("candidates"), None, v.get("time_s"), v.get("stats")))
out.append("### Comparison with the earlier (designer-written) sketch arm\n")
out.append("| task | this run: status / proposals / N-S-bits / synth s | earlier arm: sketch → status / candidates / choice space / N-S-bits / synth s |")
out.append("|---|---|---|")
for r in rows:
    k = short.get(r["task"], r["task"])
    synth = [c for c in calls if c["task"] == k and c["sub"] == "synth"][-1]
    stime = [l for l in (D / "raw" / synth["raw"]).read_text().splitlines() if l.startswith("method=")][0].split("time=")[1].split("s ")[0]
    mine = f"SOLVED / {r['proposals']} / {r['neurons']}-{r['synapses']}-{r['state_bits']} / {stime}"
    ps = []
    for name, st, cand, cs, t, stats in prior.get(r["task"], []):
        size = f"{stats['neurons']}-{stats['synapses']}-{stats['state_bits']}" if stats else "—"
        ps.append(f"`{name}` → {st} / {cand} / {cs if cs is not None else 'n/a'} / {size} / {t}")
    out.append(f"| {r['task']} | {mine} | {'<br>'.join(ps) if ps else 'no entry'} |")
(D / "tables.md").write_text("\n".join(out) + "\n")
print("\n".join(out))
