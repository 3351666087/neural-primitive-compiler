"""G1-P4 step 1: read-only check of the user's gated access to ServiceNow/WorkArena-Instances. Prints only the outcome
(never the token).  mission-06/env/venv-wa/bin/python -I mission-06/experiments/g1/p4_access.py"""

import json
from pathlib import Path

from huggingface_hub import HfApi

try:
    HfApi().auth_check("ServiceNow/WorkArena-Instances", repo_type="dataset")
    out = {"access": "granted"}
except Exception as e:                                         # noqa: BLE001
    out = {"access": "not granted", "error_type": type(e).__name__}
(Path(__file__).resolve().parent / "p4_access.json").write_text(json.dumps(out))
print(json.dumps(out))
