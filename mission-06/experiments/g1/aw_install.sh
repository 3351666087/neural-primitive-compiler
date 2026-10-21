#!/bin/sh
# Install AppWorld 0.1.3.post1 into an isolated venv and fetch its data bundle 0.2.0 (ENVIRONMENT_SELECTION.md 10,
# MISSION06_FREEZE_PLAN.md 7). Run from the repository root after the user approved these downloads.
# APPWORLD_ROOT points into mission-06/env/appworld (gitignored: the license forbids plaintext redistribution).
set -eu
ENV=mission-06/env
export APPWORLD_ROOT="$PWD/$ENV/appworld"
mkdir -p "$APPWORLD_ROOT"
"$HOME/.local/bin/python3.12" -m venv "$ENV/venv-aw"
PY="$ENV/venv-aw/bin/python"
$PY -m pip install --report "$ENV/appworld_pip_report.json" "appworld==0.1.3.post1"
( cd "$APPWORLD_ROOT" && "$PWD/../venv-aw/bin/appworld" install )
( cd "$APPWORLD_ROOT" && "$PWD/../venv-aw/bin/appworld" download data )
$PY -m pip freeze > "$ENV/appworld_install.txt"
for split in train dev test_normal test_challenge; do                       # counts only, no task text
    f="$APPWORLD_ROOT/data/datasets/$split.txt"
    [ -f "$f" ] && printf '%s %s\n' "$split" "$(wc -l < "$f" | tr -d ' ')" || printf '%s missing\n' "$split"
done | tee "$ENV/appworld_split_counts.txt"
du -sh "$ENV/venv-aw" "$APPWORLD_ROOT" | tee "$ENV/appworld_disk.txt"
