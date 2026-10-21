#!/bin/sh
# G1-P1: install the pinned WorkArena stack into an isolated venv (EXPERIMENT_PRE_REGISTRATION.md, section G1-P).
# Run from the repository root, only after the user approved these downloads. Touches no ServiceNow instance.
# Downloads: PyPI (pypi.org, files.pythonhosted.org) and Playwright's Chromium build for playwright 1.44.0.
set -eu
ENV=mission-06/env
mkdir -p "$ENV"
"$HOME/.local/bin/python3.12" -m venv "$ENV/venv-wa"
"$ENV/venv-wa/bin/python" -m pip install --report "$ENV/workarena_pip_report.json" \
    "browsergym-core==0.14.3" "browsergym-workarena==0.5.3"
PLAYWRIGHT_BROWSERS_PATH="$ENV/ms-playwright" "$ENV/venv-wa/bin/python" -m playwright install chromium
"$ENV/venv-wa/bin/python" -m pip freeze > "$ENV/workarena_install.txt"
du -sh "$ENV/venv-wa" "$ENV/ms-playwright" | tee "$ENV/workarena_disk.txt"
