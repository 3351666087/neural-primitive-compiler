"""G0 audit experiment: is Mission 01's bounded latency-1 test (bound=64) consistent with Theorem 3?

  python mission-02/experiments/g0/latency1_bound_audit.py

Writes mission-02/experiments/g0/latency1_bound_audit.json.
Part 1: random functional specs, m = 1..5 inputs: bounded(64), bounded(1), bounded(2) vs exact.
Part 2: an explicit witness family: y(t) = [x(t-1) >= z(t-1)] for two k-bit numbers (m = 2k inputs).
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from cog.realize import bound_is_provably_complete, latency1_exact  # noqa: E402
from npc.fsm import NotCausal, latency1_weights, machine_from_spec, minimize  # noqa: E402
from npc.gen import random_formula  # noqa: E402
from npc.spec import F, Prev, Spec, TRUE, atom, make_spec  # noqa: E402

OUT = Path(__file__).with_suffix(".json")


def part_random(n_per_m: int = 60):
    rows = []
    for m in range(1, 6):
        names = [f"x{i}" for i in range(m)]
        stats = {"m": m, "specs": 0, "not_causal": 0, "agree64": 0, "disagree64": 0, "disagree_b1": 0,
                 "disagree_b2": 0, "exact_realizable": 0, "max_abs_W_exact": 0, "provably_complete_64": bound_is_provably_complete(m)}
        for seed in range(n_per_m):
            rng = random.Random(1000 * m + seed)
            phi = random_formula(rng, names, depth=2)
            sp = Spec("r", tuple(names), ("y",), TRUE, F("iff", (atom("y"), Prev(phi))))
            try:
                M = minimize(machine_from_spec(sp, max_states=5000))
            except NotCausal:
                stats["not_causal"] += 1
                continue
            except MemoryError:
                continue
            stats["specs"] += 1
            ex = latency1_exact(M)
            b64, b1, b2 = latency1_weights(M, 64), latency1_weights(M, 1), latency1_weights(M, 2)
            stats["exact_realizable"] += int(ex.realizable)
            stats["agree64"] += int(b64.realizable == ex.realizable)
            stats["disagree64"] += int(b64.realizable != ex.realizable)
            stats["disagree_b1"] += int(b1.realizable != ex.realizable)
            stats["disagree_b2"] += int(b2.realizable != ex.realizable)
            if ex.realizable:
                stats["max_abs_W_exact"] = max(stats["max_abs_W_exact"], max((abs(w) for w in ex.W["y"]), default=0))
        rows.append(stats)
        print(stats, flush=True)
    return rows


def comparison_spec(k: int) -> Spec:
    xs, zs = [f"x{i}" for i in range(k)], [f"z{i}" for i in range(k)]
    terms = " + ".join(f"{2 ** i}*count[1]({x})" for i, x in enumerate(xs))
    terms += "".join(f" - {2 ** i}*count[1]({z})" for i, z in enumerate(zs))
    return make_spec(f"cmp{k}", xs + zs, ["y"], f"y <-> prev({terms} >= 0)")


def part_witness(ks=(4, 6, 7, 8)):
    rows = []
    for k in ks:
        t0 = time.perf_counter()
        sp = comparison_spec(k)
        M = minimize(machine_from_spec(sp, max_states=10))
        t_machine = time.perf_counter() - t0
        t1 = time.perf_counter()
        b64 = latency1_weights(M, 64)
        t_b = time.perf_counter() - t1
        t2 = time.perf_counter()
        ex = latency1_exact(M)
        t_e = time.perf_counter() - t2
        row = {"k_bits": k, "m_inputs": 2 * k, "letters": 2 ** (2 * k), "bounded64_realizable": b64.realizable,
               "exact_realizable": None if ex is None else ex.realizable,
               "exact_W": None if ex is None or not ex.realizable else ex.W["y"],
               "time_machine_s": round(t_machine, 2), "time_bounded_s": round(t_b, 2), "time_exact_s": round(t_e, 2)}
        rows.append(row)
        print(row, flush=True)
    return rows


if __name__ == "__main__":
    res = {"random": part_random(), "witness_comparison": part_witness()}
    OUT.write_text(json.dumps(res, indent=2))
    print("wrote", OUT)
