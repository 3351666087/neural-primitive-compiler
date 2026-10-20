"""Mission 03, Phase 0: three checkable leakage hypotheses about Mission 02's unseen-task results.

L1  keyword decoding: the A-LLM programs are reproduced by a fixed phrase -> map lookup (the inverse of the
    generator's own phrase table cog.tasks.DESCR) plus the per-family scaffolds in write_llm_programs.py.
    If so, A-LLM 16/16 measures the injectivity of the description encoding, not mechanism discovery.
L2  vocabulary: A-auto's size extrapolation needs the designer's 12-map vocabulary. Test: replace the
    vocabulary by a generic prior (unions of unimodular integer-affine maps of the lattice, translation
    c*(N-1)+d, clip or wrap; no named maps), fit it to the same probe tables at N = 3, 5, and check the
    instantiation at N = 8 and 11 against the reference relation.
L3  observability: A-auto's correctness needs the single-cell probes. Test: the same pipeline with the
    probes removed (passive random traces only, 1,000 per probe size), judged at every listed size.

Mission 02 code is imported unchanged (frozen); L3 replaces cog.auto.active_refine inside this process only.

  python mission-03/experiments/p0_leakage/run_leakage.py
"""

from __future__ import annotations

import itertools
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "mission-02" / "experiments" / "unseen"))

import cog.auto as auto  # noqa: E402
from cog.check import differential  # noqa: E402
from cog.ir import compile_ir  # noqa: E402
from cog.learn import active_refine, learn, match_vocab  # noqa: E402
from cog.tasks import DESCR, run_reference  # noqa: E402
from cog.unseen import generate  # noqa: E402
import write_llm_programs as W  # noqa: E402

UNSEEN = REPO / "mission-02" / "experiments" / "unseen"
OUT = HERE / "leakage.json"


# ------------------------------------------------------------------ L1 keyword decoding
PHRASE = {v: k.lower() for k, v in DESCR.items()}      # the generator's phrase table, inverted
PHRASES = sorted(PHRASE, key=len, reverse=True)
REGION_WORD = {"the top row": "top row", "the bottom row": "bottom row", "the left column": "left column",
               "anywhere": "anywhere"}


def moves(text: str) -> list[str]:
    """'phrase, then phrase' -> move keys, longest phrase first."""
    out, rest = [], text.strip()
    while rest:
        for p in PHRASES:
            if rest.startswith(p):
                out.append(PHRASE[p])
                rest = rest[len(p):].lstrip(", ").removeprefix("then ").strip()
                break
        else:
            raise ValueError(f"no phrase for: {rest[:60]}")
    return out


def decode_spatial(desc: str) -> dict:
    cmds, cond, anys, cellon = {}, None, [], False
    for m in re.finditer(r"Command (CMD\d+): (.*?)\.(?= Command| Query| Output| Decided|$)", desc):
        name, body = m.group(1), m.group(2)
        c = re.match(r"if the shape has a cell in (.*?), then (.*?); otherwise (.*)", body)
        if c:
            D = int(re.search(r"appears as the state (\d+) steps later", desc).group(1))
            cond = (name, REGION_WORD[c.group(1)], W.seq(*moves(c.group(2))), W.seq(*moves(c.group(3))), D)
        else:
            cmds[name] = W.seq(*moves(body))
    for m in re.finditer(r"Output (any_\w+): 1 iff the shape has a cell in (.*?), 3 steps late", desc):
        anys.append((m.group(1), REGION_WORD[m.group(2)]))
    cellon = "Query qcell" in desc
    return W.spatial(cmds, cond=cond, any_outputs=anys, cellon=cellon)


def decode_binding(desc: str, size) -> dict:
    ops = ["STORE"] + [op for op in ("SWAP", "COPY", "CLEAR") if f"{op}j" in desc or f"{op}k" in desc]
    qs = [q for q, key in (("value", "valueof"), ("who", "who"), ("same", "output same")) if key in desc]
    return W.binding(size[0], ops, qs)


def decode_objects(desc: str, size) -> dict:
    cmds = {}
    for sentence in desc.split(". "):
        m = re.match(r"([A-Z0-9]+)k: (.*) -- applied to object k only", sentence)
        if m:
            cmds[m.group(1)] = W.MOVE[moves(m.group(2))[0]]
    return W.objects(size[0], cmds, "Outputs topk" in desc)


def check_l1() -> dict:
    tasks = json.loads((UNSEEN / "tasks.json").read_text())["tasks"]
    llm = json.loads((UNSEEN / "llm_programs.json").read_text())
    rows = []
    for t in tasks:
        uid, desc = t["uid"], t["interface_smallest"]["description"]
        try:
            if t["family"] == "A":
                got = {"program": decode_spatial(desc)}
            elif t["family"] == "B":
                got = {"per_size": {str(tuple(s)): decode_binding(desc, s) for s in t["sizes"]}}
            else:
                got = {"per_size": {str(tuple(s)): decode_objects(desc, s) for s in t["sizes"]}}
            same = json.loads(json.dumps(got)) == llm[uid]
            rows.append({"uid": uid, "identical_to_llm_program": same})
        except Exception as e:  # a decoding failure is a result, not a crash
            rows.append({"uid": uid, "identical_to_llm_program": False, "error": f"{type(e).__name__}: {e}"})
    return {"rows": rows, "identical": sum(r["identical_to_llm_program"] for r in rows), "total": len(rows)}


# ------------------------------------------------------------------ L2 generic affine prior
UNIMOD = [A for A in itertools.product((-1, 0, 1), repeat=4) if abs(A[0] * A[3] - A[1] * A[2]) == 1]
TRANS = [(c, d) for c in (0, 1) for d in (-2, -1, 0, 1, 2)]
GENERIC = [(A, tx, ty, mode) for A in UNIMOD for tx in TRANS for ty in TRANS for mode in ("clip", "wrap")]


def graph(g, N: int) -> frozenset:
    A, (cx, dx), (cy, dy), mode = g
    out = set()
    for x in range(N):
        for y in range(N):
            X = A[0] * x + A[1] * y + cx * (N - 1) + dx
            Y = A[2] * x + A[3] * y + cy * (N - 1) + dy
            if mode == "wrap":
                X, Y = X % N, Y % N
            elif not (0 <= X < N and 0 <= Y < N):
                continue
            out.add(((x, y), (X, Y)))
    return frozenset(out)


def relation_from_table(table: dict) -> frozenset:
    return frozenset((s[1], j) for j, srcs in table.items() for s in srcs if s[0] == "c")


def true_relation(task, name: str) -> frozenset:
    letter = next(l for l in task.letters if l.name == name)
    return frozenset((p, q) for p in task.space.coords for q in letter.act(frozenset({p}), {}))


def fit_generic(rels: dict, horizon=(8, 11)) -> tuple[list, int]:
    """All minimum-size unions of generic maps whose graphs equal the relation at every probed size.
    Maps that behave identically at the probed sizes AND at the horizon sizes are merged (bookkeeping only:
    selection never looks at the horizon); maps that agree on the probes but differ later stay separate,
    so ambiguity is reported, not hidden."""
    cands = [g for g in GENERIC if all(graph(g, N) <= R for N, R in rels.items())]
    cands = list({tuple(graph(g, N) for N in (*rels, *horizon)): g for g in cands}.values())
    if all(not R for R in rels.values()):
        return [()], len(cands)
    for k in range(1, 6):
        covers = [c for c in itertools.combinations(cands, k)
                  if all(frozenset().union(*(graph(g, N) for g in c)) == R for N, R in rels.items())]
        if covers:
            return covers, len(cands)
    return [], len(cands)


def check_l2() -> dict:
    seed = json.loads((UNSEEN / "tasks.json").read_text())["seed"]
    rows = []
    for u in generate(seed):
        if u.family != "A":
            continue
        probe = {N: u.build(N) for N in (3, 5)}
        cond = u.params.get("cond")
        names = [n for n, _ in u.params["commands"]] + ([cond[0]] if cond else [])
        learned, traces = {}, 0
        for N, t in probe.items():
            iface = t.interface()
            orc = lambda tr, T, t=t: run_reference(t, tr, T)
            L = active_refine(iface, orc, learn(iface, orc, n_traces=300, T=16, seed=1))
            traces += 300 + getattr(L, "probes", 0)
            learned[N] = L
        for name in names:
            row = {"uid": u.uid, "command": name, "conditional": bool(cond and name == cond[0])}
            tabs = {N: L.letters.get(name) for N, L in learned.items()}
            if any(not isinstance(tb, dict) for tb in tabs.values()):
                row["generic"] = row["vocab"] = "table not learned (outside the union schema)"
                rows.append(row)
                continue
            rels = {N: relation_from_table(tb) for N, tb in tabs.items()}
            row["probe_tables_correct"] = all(rels[N] == true_relation(probe[N], name) for N in rels)
            covers, ncand = fit_generic(rels)
            row["generic_candidates_consistent"] = ncand
            row["generic_minimal_covers"] = len(covers)
            row["generic_union_size"] = len(covers[0]) if covers else None
            for N in (8, 11):
                truth = true_relation(u.build(N), name)
                preds = {frozenset().union(*(graph(g, N) for g in c)) if c else frozenset() for c in covers}
                row[f"generic_N{N}"] = ("no cover" if not covers else
                                        "correct" if preds == {truth} else
                                        "ambiguous (covers disagree)" if len(preds) > 1 else "wrong")
            vocab_hits = [match_vocab(tabs[N], probe[N].interface()["state_space"], []) for N in tabs]
            common = [m for m in vocab_hits[0] if m in vocab_hits[1]]
            row["vocab"] = "match" if common else "no match"
            rows.append(row)
    ok = [r for r in rows if isinstance(r.get("generic_N11"), str)]
    return {"rows": rows, "probe_traces_note": "same probe procedure as A-auto (300 passive traces + singleton probes per size)",
            "generic_family_size": len(GENERIC),
            "generic_correct_at_N8_and_N11": sum(r["generic_N8"] == r["generic_N11"] == "correct" for r in ok),
            "vocab_match": sum(r.get("vocab") == "match" for r in rows), "commands": len(rows)}


# ------------------------------------------------------------------ L3 passive-only observation
def check_l3(n_passive: int = 1000) -> dict:
    seed = json.loads((UNSEEN / "tasks.json").read_text())["seed"]
    real_refine = auto.active_refine
    auto.active_refine = lambda iface, orc, L, **kw: L        # remove the single-cell probes
    rows = []
    try:
        for u in generate(seed):
            tasks = [u.build(s) for s in u.sizes]
            probe = tasks[:2]
            r = auto.construct_auto([t.interface() for t in probe],
                                    [lambda tr, T, t=t: run_reference(t, tr, T) for t in probe], n_traces=n_passive)
            row = {"uid": u.uid, "status": r.status, "reason": r.reason, "oracle_traces": r.oracle_traces, "per_size": []}
            if r.status == "BUILT":
                for s, t in zip(u.sizes, tasks):
                    try:
                        d = differential(compile_ir(r.rules.instantiate(t.interface()), t.interface()), t, n=400, T=16, seed=7)
                        row["per_size"].append({"size": str(s), "differential": d.ok, "failing": d.detail.get("failing_traces")})
                    except Exception as e:
                        row["per_size"].append({"size": str(s), "error": f"{type(e).__name__}: {e}"})
            row["success_all_sizes"] = bool(row["per_size"]) and all(p.get("differential") for p in row["per_size"])
            rows.append(row)
            print("L3", u.uid, row["status"], row["reason"][:70], [(p["size"], p.get("differential")) for p in row["per_size"]], flush=True)
    finally:
        auto.active_refine = real_refine
    return {"rows": rows, "n_passive_per_size": n_passive, "success": sum(r["success_all_sizes"] for r in rows)}


def main():
    t0 = time.perf_counter()
    res = {"L1": check_l1()}
    print("L1", res["L1"]["identical"], "/", res["L1"]["total"], flush=True)
    res["L2"] = check_l2()
    print("L2 generic correct at N=8,11:", res["L2"]["generic_correct_at_N8_and_N11"], "/", res["L2"]["commands"],
          " vocab match:", res["L2"]["vocab_match"], flush=True)
    res["L3"] = check_l3()
    print("L3 passive-only success:", res["L3"]["success"], "/", len(res["L3"]["rows"]), flush=True)
    res["time_s"] = round(time.perf_counter() - t0, 1)
    OUT.write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
