"""CLI behaviour found by the blind skill evaluation (experiments/blind_skill_eval/REPORT.md, friction 2-3)."""

import json

from npc.cli import _status_code, main
from npc.verify import Result, Status


def test_verify_accepts_a_synth_record(tmp_path):
    out = tmp_path / "rec.json"
    assert main(["synth", "experiments/tasks.npc", "--spec", "A2_burst2of3", "--method", "compose",
                 "--timeout", "60", "--out", str(out)]) == 0
    assert "network" in json.loads(out.read_text())
    assert main(["verify", "experiments/tasks.npc", "--net-json", str(out), "--spec", "A2_burst2of3",
                 "--horizon", "6"]) == 0


def test_exit_code_unbounded_proof_beats_bounded_resource_limit():
    r = lambda st, h: Result(st, "x", "", 0.0, h)
    assert _status_code([r(Status.VERIFIED_BOUNDED, 8), r(Status.RESOURCE_LIMIT, 8), r(Status.VERIFIED_UNBOUNDED, None)]) == 0
    assert _status_code([r(Status.VERIFIED_BOUNDED, 8), r(Status.RESOURCE_LIMIT, 8)]) == 2
    assert _status_code([r(Status.COUNTEREXAMPLE, None), r(Status.VERIFIED_BOUNDED, 8)]) == 1
