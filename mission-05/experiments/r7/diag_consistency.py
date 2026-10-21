"""POST-HOC diagnostic (after r7_scores.json and posthoc_g3.json): does adding witness-position consistency to A+
(a witness on x has content u; a witness on y has content v) close the remaining gaps? Instances: DEV-O-empty (the one
truly progressing G3-DEV instance A+ misses) and the held-out instances A+ still misses. Exploratory, not a verdict;
the constraint would have to be locked in a new round to count.

  python -I diag_consistency.py      # writes diag_consistency.json
"""
import json, sys
from pathlib import Path
import z3
HERE = Path(__file__).resolve().parent
EXP = HERE.parent
sys.path.insert(0, str(EXP / "lib")); sys.path.insert(0, str(EXP / "g3")); sys.path.insert(0, str(HERE))
import dsl, truth, zplus, z3_dsl
from potentials import patterns

_orig = zplus.base_plus


def base_pp(spec, atom, timeout_ms=20000):
    s, V, nob = _orig(spec, atom, timeout_ms)
    for w, cw in V["witnesses"]:
        s.add(z3.Implies(w == V["x"], V["u"] == cw), z3.Implies(w == V["y"], V["v"] == cw))
    return s, V, nob


def main():
    dev = {s["id"]: s for s in json.loads((EXP / "g3" / "specs_dev.json").read_text())["specs"]}
    ho = {s["id"]: s for s in json.loads((EXP.parent / "external" / "g3_heldout" / "achievers.json").read_text())["specs"]}
    ph = json.loads((HERE / "posthoc_g3.json").read_text())
    dg = json.loads((EXP / "g3" / "heldout_diag.json").read_text())
    missed = sorted({k for k, v in dg["instances"].items() if v["truly_good"]} - set(ph["newly_certified"]))
    targets = [("G3-DEV", k, a, dev[k.split("|")[0]]) for s in dev.values() for k, a in dsl.instances(s) if k == "DEV-O-empty"]
    targets += [("G3-heldout", k, a, ho[k.split("|")[0]]) for s in ho.values() for k, a in dsl.instances(s) if k in missed]
    tr, _ = truth.tables([(k, a, dsl.make_select(sp)) for _, k, a, sp in targets])
    zplus.base_plus = base_pp
    out = {"label": "POST-HOC: A+ with witness-position consistency", "instances": {}}
    for setname, k, a, sp in targets:
        b = {x: zplus.bound_plus(sp, a, x) for x in patterns(a[0])}
        below = [x for x, e in b.items() if e["status"] == "PROVED"
                 and max((v for v in tr[k]["damage"][x]["max_by_N"].values() if v is not None), default=-99) > e["bound"]]
        out["instances"][k] = {"set": setname, "decrease_proved": z3_dsl.progress(sp, a, b),
                               "applicability_N7": tr[k]["applicability_cex"] is None, "bounds_below_truth": below}
        print(setname, k, out["instances"][k])
    zplus.base_plus = _orig
    (HERE / "diag_consistency.json").write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
