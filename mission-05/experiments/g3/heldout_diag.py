"""POST-HOC (after heldout_scores.json): which truly progressing held-out instances did A fail to certify (Q2), and
what do their specs look like? Recomputes the truth tables for the 14 instances whose decrease Z3 did not prove.

  python -I heldout_diag.py      # writes heldout_diag.json
"""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "lib"))
import a_dsl, dsl, truth, z3_dsl

d = json.loads((HERE / "heldout_run.json").read_text())
specs = {s["id"]: s for s in json.loads((HERE.parent.parent / "external/g3_heldout/achievers.json").read_text())["specs"]}
cand = [k for k, v in d["A"]["progress"].items() if not v["decrease_proved"] and v["applicability_N7"]]
inst = [(k, a) for s in specs.values() for k, a in dsl.instances(s) if k in cand]
tr, cpu = truth.tables([(k, a, dsl.make_select(specs[k.split("|")[0]])) for k, a in inst])
tp = a_dsl.truth_progress(tr, dict(inst))
out = {"label": "POST-HOC: held-out instances with a true decrease that A did not certify", "cpu_s": cpu, "instances": {}}
for k, a in inst:
    sp = specs[k.split("|")[0]]
    out["instances"][k] = {"truly_good": tp[k]["good"], "decreasing_measures": tp[k]["decreasing_measures"],
                           "measure_max_by_N": {m: tr[k]["damage"][m]["max_by_N"] for m in z3_dsl.own_measures(a)},
                           "z3": {m: d["A"]["progress"][k]["measure"] for m in [0]},
                           "dest": sp["dest"], "source": sp["source"]}
(HERE / "heldout_diag.json").write_text(json.dumps(out, indent=1, default=str))
for k, r in out["instances"].items():
    print(k, "good" if r["truly_good"] else "not good", r["decreasing_measures"], "| dest", json.dumps(r["dest"]), "| source", json.dumps(r["source"]))
