"""Build per_task.tsv from calls.tsv, markers.tsv and the synth records (own results only)."""
import csv, json, re
from pathlib import Path
D = Path(__file__).parent
calls = list(csv.DictReader(open(D / "calls.tsv"), delimiter="\t"))
marks = list(csv.DictReader(open(D / "markers.tsv"), delimiter="\t"))
tasks = ["B2", "B3", "C1", "C2", "C3", "D02", "D06", "D17", "D18", "Dhand"]
full = {"B2": "B2_remember_query", "B3": "B3_first_since_reset", "C1": "C1_toggle_sparse",
        "C2": "C2_parity_dense", "C3": "C3_latched_alarm", "Dhand": "Dhand_second_b_after_a"}
rows, prev_end = [], None
for t in tasks:
    mine = [c for c in calls if c["task"] == t]
    synths = [c for c in mine if c["sub"] in ("synth", "verify")]
    realize = [c for c in mine if c["sub"] == "realize"]
    t0 = float(mine[0]["start_epoch"])
    last = synths[-1]
    t_end = float(last["start_epoch"]) + float(last["seconds"])
    start = prev_end if prev_end is not None else t0
    raw = (D / "raw" / last["raw"]).read_text()
    reach = [l for l in raw.splitlines() if l.startswith("[reach]")]
    bmc = [l for l in raw.splitlines() if l.startswith("[bmc]")]
    synth_line = [l for l in raw.splitlines() if l.startswith("method=")]
    rraw = (D / "raw" / realize[0]["raw"]).read_text()
    minimal = re.search(r"minimal: (\d+)", rraw).group(1)
    rstatus = re.search(r'"status": "(\w+)"', rraw).group(1)
    rneur = re.search(r'"neurons": (\d+)', rraw).group(1)
    rec = json.load(open(D / "rec" / f"{t}_p1.json"))
    st = rec["network_stats"]
    m = [x for x in marks if x["task"] == t]
    rows.append({
        "task": full.get(t, t), "proposals": len(synths), "verifier_calls_in_loop": len(synths),
        "realize": f"{rstatus} (min {minimal} states, one-hot {rneur} neurons)",
        "wall_s_prev_result_to_result": round(t_end - start, 1),
        "wall_s_marker_window": int(m[1]["epoch"]) - int(m[0]["epoch"]),
        "tool_s": round(sum(float(c["seconds"]) for c in mine), 2),
        "synth_line": synth_line[0] if synth_line else "",
        "bmc_line": bmc[0] if bmc else "", "reach_line": reach[0] if reach else "",
        "neurons": st["neurons"], "synapses": st["synapses"], "state_bits": st["state_bits"],
        "max_abs_weight": st["max_abs_weight"], "max_delay_used": st["max_delay_used"],
    })
    prev_end = t_end
with open(D / "per_task.tsv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter="\t")
    w.writeheader(); w.writerows(rows)
for r in rows:
    print(r["task"], r["proposals"], r["wall_s_prev_result_to_result"], r["wall_s_marker_window"], r["tool_s"],
          r["neurons"], r["synapses"], r["state_bits"], "|", r["reach_line"][:60])
first = float(calls[0]["start_epoch"]); print("first logged call -> last synth end (s):", round(prev_end - first, 1))
