"""A-LLM route: Claude's reading of each unseen task's natural-language description, written as IR.

Written after reading only experiments/unseen/tasks.json (interfaces of the smallest size + descriptions).
No oracle call, no import of the task semantics (cog.tasks / cog.unseen). Every map below is Claude's
translation of a sentence of the description; mistakes are left in and judged.

  python mission-02/experiments/unseen/write_llm_programs.py   ->  llm_programs.json
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

# sentence -> map (pullback vocabulary of cog.ir); y grows downward, "down" = (0, +1)
MOVE = {
    "rot90": ["rot90"],          # rotate 90 degrees clockwise about the grid centre
    "rot180": ["rot180"],
    "rot270": ["rot270"],        # rotate 90 degrees counter-clockwise
    "fliph": ["fliph"],          # mirror left-right
    "flipv": ["flipv"],          # mirror top-bottom
    "transpose": ["transpose"],  # reflect across the main diagonal (x <-> y)
    "down": ["shift", 0, 1, "clip"], "up": ["shift", 0, -1, "clip"],
    "left": ["shift", -1, 0, "clip"], "right": ["shift", 1, 0, "clip"],
    "rightwrap": ["shift", 1, 0, "wrap"],
    "dilate": ["dilate"],        # thicken: every on cell also turns on its 4 neighbours
}
REGION = {"top row": {"row": 0}, "bottom row": {"row": "last"}, "left column": {"col": 0}, "anywhere": {"all": True}}


def seq(*names):
    ms = [MOVE[n] for n in names]
    return ms[0] if len(ms) == 1 else ["compose", *ms]


def spatial(commands: dict, cond=None, any_outputs=(), cellon=False) -> dict:
    letters = {"LOAD": {"map": ["load", "see"]}}
    letters.update({c: {"map": m} for c, m in commands.items()})
    nodes = []
    outputs = {"img": "mem"}
    if cond:
        name, region, then_m, else_m, D = cond
        letters["condA"] = {"map": then_m}
        letters["condB"] = {"map": else_m}
        nodes += [{"id": "condR", "op": "ANY", "of": "mem", "where": REGION[region], "delay": 1},
                  # fire the chosen internal command exactly D steps after the conditional command; the region
                  # is read from the register, which does not change while the environment stays quiet
                  {"id": "condA", "op": "GATE", "pos": [[name, D], ["condR", 1]]},
                  {"id": "condB", "op": "GATE", "pos": [[name, D]], "neg": [["condR", 1]]}]
    for out_name, region in any_outputs:
        nodes.append({"id": out_name, "op": "ANY", "of": "mem", "where": REGION[region], "delay": 1})
        outputs[out_name] = out_name
    if cellon:
        nodes.append({"id": "cellon", "op": "SEL", "of": "mem", "select": "qcell", "axis": "all", "delay": 2, "xdelay": 1})
        outputs["cellon"] = "cellon"
    return {"name": "llm", "max_delay": 6, "nodes": [{"id": "mem", "op": "CMR", "letters": letters}] + nodes,
            "outputs": outputs}


def binding(K: int, ops: list, queries: list) -> dict:
    letters = {}
    for k in range(K):
        letters[f"STORE{k}"] = {"map": ["store_row", k, "val"]}
        if "CLEAR" in ops:
            letters[f"CLEAR{k}"] = {"map": ["clear_row", k]}
        for j in range(K):
            if "SWAP" in ops and j < k:
                letters[f"SWAP{j}{k}"] = {"map": ["swap_rows", j, k]}
            if "COPY" in ops and j != k:
                letters[f"COPY{j}{k}"] = {"map": ["copy_row", j, k]}
    nodes = [{"id": "mem", "op": "CMR", "letters": letters}]
    outputs = {"img": "mem"}
    if "value" in queries:
        nodes.append({"id": "valueof", "op": "SEL", "of": "mem", "select": "qobj", "axis": 0, "delay": 2, "xdelay": 1})
        outputs["valueof"] = "valueof"
    if "who" in queries:
        nodes.append({"id": "who", "op": "SEL", "of": "mem", "select": "qval", "axis": 1, "delay": 2, "xdelay": 1})
        outputs["who"] = "who"
    if "same" in queries:  # value of a AND value of b, per value, then any value: answer 5 steps after the query
        nodes += [{"id": "va", "op": "SEL", "of": "mem", "select": "qa", "axis": 0, "delay": 2, "xdelay": 1},
                  {"id": "vb", "op": "SEL", "of": "mem", "select": "qb", "axis": 0, "delay": 2, "xdelay": 1},
                  {"id": "both", "op": "GATE", "pos": [["va", 1], ["vb", 1]]},
                  {"id": "same", "op": "ANY", "of": "both", "where": {"all": True}, "delay": 1}]
        outputs["same"] = "same"
    return {"name": "llm", "max_delay": 6, "nodes": nodes, "outputs": outputs}


def objects(K: int, cmds: dict, top_outputs: bool) -> dict:
    letters = {}
    for k in range(K):
        letters[f"PLACE{k}"] = {"map": ["place", k, "see"]}
        for cname_, m in cmds.items():
            letters[f"{cname_}{k}"] = {"map": ["on_slice", k, m]}
    nodes = [{"id": "mem", "op": "CMR", "letters": letters}]
    outputs = {"img": "mem"}
    if top_outputs:
        for k in range(K):
            nodes.append({"id": f"top{k}", "op": "ANY", "of": "mem", "where": {"slice": [0, k], "row": 0}, "delay": 1})
            outputs[f"top{k}"] = f"top{k}"
    return {"name": "llm", "max_delay": 6, "nodes": nodes, "outputs": outputs}


def main():
    P = {}
    # ---- spatial tasks (one program serves every grid size)
    P["UA0"] = spatial({"CMD0": seq("down", "rot90"), "CMD1": seq("rot180"), "CMD2": seq("fliph", "rightwrap")},
                       cond=("CMD3", "top row", seq("left"), seq("dilate"), 4))
    P["UA1"] = spatial({"CMD0": seq("left"), "CMD1": seq("left"), "CMD2": seq("down")})
    P["UA2"] = spatial({"CMD0": seq("rot270", "rot270"), "CMD1": seq("transpose"), "CMD2": seq("dilate", "left"),
                        "CMD3": seq("rot270", "transpose")},
                       cond=("CMD4", "bottom row", seq("left"), seq("rightwrap"), 4), any_outputs=[("any_all", "anywhere")],
                       cellon=True)
    P["UA3"] = spatial({"CMD0": seq("rot90", "transpose"), "CMD1": seq("up", "fliph"), "CMD2": seq("down")},
                       cond=("CMD3", "top row", seq("rot90"), seq("fliph"), 4), any_outputs=[("any_all", "anywhere")])
    P["UA4"] = spatial({"CMD0": seq("rot270", "transpose"), "CMD1": seq("rot180"), "CMD2": seq("up", "right"),
                        "CMD3": seq("right")},
                       cond=("CMD4", "left column", seq("flipv"), seq("up"), 4), any_outputs=[("any_bottom", "bottom row")],
                       cellon=True)
    P["UA5"] = spatial({"CMD0": seq("transpose", "fliph"), "CMD1": seq("dilate", "down"), "CMD2": seq("flipv"),
                        "CMD3": seq("transpose")})
    P["UA6"] = spatial({"CMD0": seq("transpose"), "CMD1": seq("up")}, any_outputs=[("any_bottom", "bottom row")])
    P["UA7"] = spatial({"CMD0": seq("left", "fliph"), "CMD1": seq("rot270")}, any_outputs=[("any_left", "left column")])
    out = {uid: {"program": prog} for uid, prog in P.items()}
    # ---- binding tasks: the description defines STOREk etc. for every k; instantiate at each listed size
    tasks = json.loads((HERE / "tasks.json").read_text())["tasks"]
    sizes = {t["uid"]: t["sizes"] for t in tasks}
    B = {"UB0": (["STORE", "SWAP"], ["same"]), "UB1": (["STORE", "COPY"], ["same"]),
         "UB2": (["STORE", "CLEAR"], ["who"]), "UB3": (["STORE", "SWAP"], ["value", "who"])}
    for uid, (ops, qs) in B.items():
        out[uid] = {"per_size": {str(tuple(s)): binding(s[0], ops, qs) for s in sizes[uid]}}
    AB = {"UAB0": ({"ROT270": MOVE["rot270"], "ROT90": MOVE["rot90"]}, False),
          "UAB1": ({"FLIPH": MOVE["fliph"]}, True),
          "UAB2": ({"RIGHT": MOVE["right"]}, True),
          "UAB3": ({"LEFT": MOVE["left"]}, False)}
    for uid, (cmds, tops) in AB.items():
        out[uid] = {"per_size": {str(tuple(s)): objects(s[0], cmds, tops) for s in sizes[uid]}}
    (HERE / "llm_programs.json").write_text(json.dumps(out, indent=1))
    print("wrote", len(out), "programs")


if __name__ == "__main__":
    main()
