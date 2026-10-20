"""Score the locked predictions T1-T7 and decision rules D1-D3 of CONFIRMATION_TWINS.md.

  python -I score2.py                 # the confirmation output confirm2_twins.json -> scores2.json
  python -I score2.py dryrun          # the DEV dry run dryrun2_dev.json -> scores2_dryrun.json (calibration only)

Retention of a method on a prior class = base tasks solved in BOTH versions / base tasks solved in the canonical
version. A claim about a class and method needs at least MIN_CAN canonical solves; otherwise INCONCLUSIVE.
Twins that change more than one prior form the class "multi" (reported, not predicted).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MIN_CAN = 5
METHODS = {"blocks-S0-C0": ("blocks", "C0", "S0"), "blocks-S0-C4": ("blocks", "C4", "S0"),
           "blocks-S0-C9": ("blocks", "C9", "S0"), "blocks-S2-C0": ("blocks", "C0", "S2"),
           "blocks-S2-C4": ("blocks", "C4", "S2"), "blocks-S2-C9": ("blocks", "C9", "S2"),
           "mdisc-C0": ("mdisc", "C0", None), "mdisc-C8": ("mdisc", "C8", None)}
# forecasts (CONFIRMATION_TWINS.md section 5) and admission rules (section 6), set after the DEV dry run
T1_MAX_C0_A = 0.70                       # background twins break the designer prior
T2_MIN_C4_A, T2_MIN_GAIN_A = 0.75, 0.20  # background chosen by evidence restores it
T3_MAX_GAIN_B = 0.10                     # colour pooling gives no meaningful gain (forecast of no effect)
T4_MAX_MDISC_C0_C, T4_MAX_GAIN_C_MDISC, T4_MIN_BLOCK_C0_C = 0.50, 0.20, 0.70
T5_MAX_BLOCK_WRONG, T5_MAX_EXTRA_MDISC_WRONG = 1, 2
T6_SLACK = 1
T7_MIN_EXTRA_TWINS_C4 = 3
D1_MIN, D1_GAIN, D2_GAIN, D3_GAIN = 0.75, 0.20, 0.10, 0.20


def status(rec, m):
    layer, cfg, pol = METHODS[m]
    return rec["blocks"][cfg][pol] if layer == "blocks" else rec["mdisc"][cfg]


def cls(p):
    return p["classes"][0] if len(p["classes"]) == 1 else "multi"


def main():
    dry = sys.argv[1:] == ["dryrun"]
    d = json.loads((HERE / ("dryrun2_dev.json" if dry else "confirm2_twins.json")).read_text())
    if d.get("status") != "COMPLETED":
        print("run status:", d.get("status"))
        return
    recs, pairs = d["records"], d["pairs"]
    get = lambda p, side, m: status(recs[f"{side}/{p[side]}"], m)
    table = {}
    for k in ("a", "b", "c", "multi"):
        ps = [p for p in pairs if cls(p) == k]
        row = {"pairs": len(ps)}
        for m in METHODS:
            can = [p for p in ps if get(p, "canonical", m) == "correct"]
            kept = [p for p in can if get(p, "twin", m) == "correct"]
            row[m] = {"canonical_solved": len(can), "kept": len(kept),
                      "retention": round(len(kept) / len(can), 3) if can else None,
                      "twin_solved": sum(get(p, "twin", m) == "correct" for p in ps),
                      "twin_wrong": sum(get(p, "twin", m) == "wrong" for p in ps),
                      "canonical_wrong": sum(get(p, "canonical", m) == "wrong" for p in ps)}
        table[k] = row
    # distinct canonical files (one canonical may be paired with several twins in the dry run)
    cans = sorted({p["canonical"] for p in pairs})
    canon = {m: sum(status(recs[f"canonical/{c}"], m) == "correct" for c in cans) for m in METHODS}
    twins_all = {m: sum(table[k][m]["twin_solved"] for k in table) for m in METHODS}
    twin_wrong = {m: sum(table[k][m]["twin_wrong"] for k in table) for m in METHODS}

    def ret(k, m):
        r = table[k][m]
        return r["retention"] if r["canonical_solved"] >= MIN_CAN else None

    def v(cond, ok):
        return "INCONCLUSIVE" if not cond else "HOLDS" if ok else "FALSIFIED"

    def both(k, m1, m2):
        a, b = ret(k, m1), ret(k, m2)
        return (a, b, a is not None and b is not None)
    T = {}
    r0, r4, ok = both("a", "blocks-S0-C0", "blocks-S0-C4")
    T["T1"] = {"verdict": v(r0 is not None, r0 is not None and r0 <= T1_MAX_C0_A), "C0": r0}
    T["T2"] = {"verdict": v(ok, ok and r4 >= T2_MIN_C4_A and r4 >= r0 + T2_MIN_GAIN_A), "C0": r0, "C4": r4}
    b0, b9, okb = both("b", "blocks-S0-C0", "blocks-S0-C9")
    T["T3"] = {"verdict": v(okb, okb and b9 - b0 < T3_MAX_GAIN_B), "C0": b0, "C9": b9}
    m0, m8, okm = both("c", "mdisc-C0", "mdisc-C8")
    c0 = ret("c", "blocks-S0-C0")
    parts = [v(m0 is not None, m0 is not None and m0 <= T4_MAX_MDISC_C0_C), v(okm, okm and m8 - m0 < T4_MAX_GAIN_C_MDISC),
             v(c0 is not None, c0 is not None and c0 >= T4_MIN_BLOCK_C0_C)]
    T["T4"] = {"verdict": "FALSIFIED" if "FALSIFIED" in parts else "HOLDS" if all(x == "HOLDS" for x in parts) else "INCONCLUSIVE",
               "parts": parts, "mdisc_C0": m0, "mdisc_C8": m8, "blocks_C0": c0}
    bw = all(twin_wrong[m] <= T5_MAX_BLOCK_WRONG for m in ("blocks-S0-C0", "blocks-S0-C4", "blocks-S0-C9"))
    mw = twin_wrong["mdisc-C8"] <= twin_wrong["mdisc-C0"] + T5_MAX_EXTRA_MDISC_WRONG
    T["T5"] = {"verdict": "HOLDS" if bw and mw else "FALSIFIED", "blocks_part": bw, "mdisc_part": mw, "twin_wrong": twin_wrong}
    b6 = canon["blocks-S0-C4"] >= canon["blocks-S0-C0"] - T6_SLACK and canon["blocks-S0-C9"] >= canon["blocks-S0-C0"] - T6_SLACK
    m6 = canon["mdisc-C8"] >= canon["mdisc-C0"] - T6_SLACK
    T["T6"] = {"verdict": "HOLDS" if b6 and m6 else "FALSIFIED", "blocks_part": b6, "mdisc_part": m6, "canonical_solved": canon}
    T["T7"] = {"verdict": "HOLDS" if twins_all["blocks-S0-C4"] - twins_all["blocks-S0-C0"] >= T7_MIN_EXTRA_TWINS_C4 else "FALSIFIED",
               "twin_solved": twins_all}
    c4ok = canon["blocks-S0-C4"] >= canon["blocks-S0-C0"] - T6_SLACK
    c9ok = canon["blocks-S0-C9"] >= canon["blocks-S0-C0"] - T6_SLACK
    D = {"D1_background_by_evidence_admitted": bool(ok and r4 >= D1_MIN and r4 >= r0 + D1_GAIN and bw and c4ok),
         "D2_colour_pooling_admitted": bool(okb and b9 >= b0 + D2_GAIN and bw and c9ok),
         "D3_frame_pooling_for_mdisc_admitted": bool(okm and m8 >= m0 + D3_GAIN and mw and m6),
         "note": "a rule whose class has fewer than MIN_CAN canonical solves for either configuration is not admitted"}
    out = {"label": d["label"], "pairs": len(pairs), "table": table, "predictions": T, "decisions": D}
    (HERE / ("scores2_dryrun.json" if dry else "scores2.json")).write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
