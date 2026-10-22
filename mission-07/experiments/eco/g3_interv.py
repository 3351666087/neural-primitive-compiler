"""Paired interventions for the candidate (JUDGE SIDE; PROTOCOL.md section 6.6 with amendment A2 item 5).
For every scored full run with an s1 (earliest structure grounded to C2):
  .del        do(s1 absent): delete s1's (form, kind) at t(s1) + 500 and block re-adoption and revision
  .fake       the same deletion, plus a random ungrounded M1 added at t(s1) (parameters drawn with seed + 7000, redrawn
              while any predicate grounds)
  .transplant the last structure of s1's lineage installed at t = 0 in a fresh candidate
  .giftb1m    B1+M given s1 at t(s1) and every C2-class top-level goal formula of the full run at its logged time
  .giftcand   the candidate with its own goal proposal off, given the same transplant and gifts
Every intervention run is scored with score_eco2 against the full run's twin.
  python3 -I g3_interv.py jobs REV ARM SEEDS
  python3 -I g3_interv.py run REV INDEX
  python3 -I g3_interv.py score REV ARM
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ground_eco as G  # noqa: E402
import run_eco as R  # noqa: E402
import score_eco2 as S2  # noqa: E402
from eco_env import load_family  # noqa: E402
from g3_dev import C2, C3, FAM, STEPS, out_dir, seeds_of  # noqa: E402

THETAS, DECAYS = (1, 2, 3, 4), (10, 25, 50, 100, 10 ** 9)


def draw_fake(seed, kinds, probes, classes):
    k = 0
    while True:
        rng = random.Random(seed + 7000 + k)
        ctx = rng.choice([None] + kinds)
        d = {"struct_id": 900, "form": "M1", "stats": {},
             "params": {"K": rng.choice(kinds), "E": rng.choice(["poke", "pick", "drop", "consume"]),
                        "theta": rng.choice(THETAS), "D": rng.choice(DECAYS), "reset": rng.random() < 0.5,
                        "ctx": ctx, "dctx": rng.choice([1, 2]) if ctx is not None else 0,
                        "ftype": rng.choice(["appear", "vanish", "feat"]), "K2": rng.choice(kinds)}}
        top = d["params"]["theta"] - (1 if d["params"]["reset"] else 0)
        d["predicates"] = [f"cnt[{d['params']['K']}]>={v}" for v in range(1, max(top, 1) + 1)]
        gr = G.ground([d], probes, classes)
        if not any(g["grounded"] for g in gr.values()):
            d["draw"] = k
            return d
        k += 1


def jobs(rev, arm, seeds):
    out = out_dir(rev)
    scores = json.loads((out / "scores.json").read_text())["runs"]
    fam = load_family(FAM)
    probes, classes = G.make_probes(fam)
    kinds = sorted(set(json.loads(json.dumps(fam["kinds"])).keys()))
    lines = []
    import gzip
    for seed in seeds_of(seeds):
        stem = f"{arm}_alpha_{seed}"
        r = scores.get(stem)
        if not r or "missing" in r or not r["L3"]["s1"]:
            print("no s1:", stem)
            continue
        t1, sid1 = r["L3"]["s1"]
        with gzip.open(out / f"{stem}.agent.json.gz", "rt") as f:
            a = json.load(f)
        with gzip.open(out / f"{stem}.judge.json.gz", "rt") as f:
            kid = json.load(f)["kind_id"]
        structs = {s["struct_id"]: s for s in a["export"]["structures"]}
        s1 = structs[sid1]
        lineage = [s for s in a["export"]["structures"] if s["form"] == s1["form"] and s["params"]["K"] == s1["params"]["K"]]
        last = max(lineage, key=lambda s: s["t_created"])
        sub = dict(r)
        gifts = []
        prov_ok = {f"struct:{sid}" for sid, si in r["structures"].items()
                   if any(p["class"] and p["class"].startswith(C2) for p in si["predicates"].values())}
        for g in a["goals"]:
            if g["parent_goal"] is None and g["reason"] not in ("need", "external") and any(p in prov_ok for p in g["provenance"]):
                gifts.append([g["t_logged"], g["formula"]])
        kind_ids = sorted(kid.values())
        fake = draw_fake(seed, kind_ids, probes, classes)
        base = {"family": str(FAM), "seed": seed, "steps": STEPS, "out": str(out)}
        dele = {"t": t1 + 500, "form": s1["form"], "K": s1["params"]["K"]}
        lines += [
            {**base, "arm": arm, "tag": ".del", "opts": {"delete": dele}},
            {**base, "arm": arm, "tag": ".fake", "opts": {"delete": dele, "fake": {"t": t1, "desc": fake}}},
            {**base, "arm": arm, "tag": ".transplant", "opts": {"transplant": [last]}},
            {**base, "arm": "B1+M", "tag": f".giftb1m_{arm}", "opts": {"transplant": [s1], "transplant_t": t1, "gift": gifts}},
            {**base, "arm": arm, "tag": ".giftcand", "opts": {"transplant": [s1], "transplant_t": t1, "gift": gifts,
                                                              "no_propose": True}},
        ]
        print(stem, "s1", sid1, "t", t1, "gifts", len(gifts), "fake draw", fake["draw"], fake["params"])
    with open(out / "interv_jobs.jsonl", "a") as f:
        for l in lines:
            f.write(json.dumps(l) + "\n")
    print(len(lines), "intervention jobs appended")


def run(rev, idx):
    spec = json.loads((out_dir(rev) / "interv_jobs.jsonl").read_text().splitlines()[idx])
    stem = f"{spec['arm']}_alpha_{spec['seed']}{spec.get('tag', '')}"
    if (Path(spec["out"]) / f"{stem}.judge.json.gz").exists():
        print("exists", stem)
        return
    print(json.dumps(R.run_job(spec)), flush=True)


def score(rev, arm):
    out = out_dir(rev)
    fam = load_family(FAM)
    probes, classes = G.make_probes(fam)
    specs = [json.loads(l) for l in (out / "interv_jobs.jsonl").read_text().splitlines()]
    res = {}
    for spec in specs:
        if not spec["tag"].endswith(arm) and spec["arm"] != arm:
            continue
        stem = f"{spec['arm']}_alpha_{spec['seed']}{spec['tag']}"
        twin = f"{arm}_alpha_{spec['seed']}.twin"
        try:
            r = S2.score_run(stem, out, probes, classes, twin_stem=twin)
        except FileNotFoundError as e:
            res[stem] = {"missing": str(e)}
            continue
        r["L3"] = S2.l3(r, C2, C3)
        res[stem] = S2.public(r)
        print(stem, "C2_L2", r["L3"]["C2_L2"], "C3_L2", r["L3"]["C3_L2"], "s2", r["L3"]["s2"],
              {k: (v["top_achieved"], v["achieved_per_10k"], v["twin_incidental_per_10k"]) for k, v in r["L2"].items()}, flush=True)
    (out / f"interv_scores_{arm}.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "jobs":
        jobs(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == "run":
        run(sys.argv[2], int(sys.argv[3]))
    elif cmd == "score":
        score(sys.argv[2], sys.argv[3])
