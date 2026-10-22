"""Quick look at one development run (JUDGE SIDE): structures with grounding, L2 per class, L3.
  python3 -I g3_peek.py REV STEM [STEM ...]"""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ground_eco as G  # noqa: E402
import score_eco2 as S2  # noqa: E402
from eco_env import load_family  # noqa: E402
from g3_dev import C2, C3, FAM, out_dir  # noqa: E402



def main():
    fam = load_family(FAM)
    probes, classes = G.make_probes(fam)
    for stem in sys.argv[2:]:
        d = Path(sys.argv[1]) if Path(sys.argv[1]).is_dir() else out_dir(sys.argv[1])
        twin = f"{stem}.twin" if (d / f"{stem}.twin.judge.json.gz").exists() else None
        r = S2.score_run(stem, d, probes, classes, twin_stem=twin)
        print("==", stem, "lives", r["lives"])
        for sid, s in r["structures"].items():
            p = s["params"]
            short = {k: p.get(k) for k in ("K", "E", "theta", "D", "reset", "ctx", "dctx", "K2", "Kq", "dq", "q_pred", "T") if k in p}
            print(" ", sid, s["form"], s["t_created"], s["retired"], s["trigger"], short, "audit", s["audit"]["ok"],
                  {k: (v["best_class"], v["precision"], v["recall"], v["grounded"]) for k, v in s["predicates"].items()})
        print("  L2", {k: (v["top_after_structure"], v["top_achieved"], v["achieved_per_10k"], v["twin_incidental_per_10k"], v["event"]) for k, v in r["L2"].items()})
        print("  L3", S2.l3(r, C2, C3))


if __name__ == "__main__":
    main()
