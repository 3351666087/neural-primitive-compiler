#!/bin/sh
# G1-A1: install ALFWorld (text only) into an isolated venv and fetch the two data archives
# (EXPERIMENT_PRE_REGISTRATION.md, section G1-A). Run from the repository root, only after the user approved these
# downloads. Source packages are built locally with Homebrew cmake (no build isolation, so no cmake download).
# Only train/ and valid_seen/ are extracted; valid_unseen/ (the official held-out split) stays sealed in the archives.
set -eu
ENV=mission-06/env
DATA="$ENV/alfworld-data"
mkdir -p "$ENV" "$DATA"
"$HOME/.local/bin/python3.12" -m venv "$ENV/venv-alf"
PY="$ENV/venv-alf/bin/python"
$PY -m pip install --report "$ENV/alfworld_pip_report_1.json" "setuptools>=61" wheel
$PY -m pip install --report "$ENV/alfworld_pip_report_2.json" --no-build-isolation "fast-downward-textworld==20.6.4"
$PY -m pip install --report "$ENV/alfworld_pip_report_3.json" --no-build-isolation --no-deps "jericho==3.3.1"
$PY -m pip install --report "$ENV/alfworld_pip_report_4.json" --no-deps "textworld==1.6.2" "alfworld==0.4.2"
# their declared dependencies except jericho's spaCy (explicit, so the resolver cannot pull spaCy in through jericho)
$PY -m pip install --report "$ENV/alfworld_pip_report_5.json" numpy tqdm cffi "networkx>=2" more_itertools "tatsu==5.8.3" \
    "hashids>=1.2.0" "mementos>=1.3.1" termcolor prompt_toolkit pyyaml click
$PY -m pip check > "$ENV/alfworld_pip_check.txt" || true                   # expected: jericho requires spacy
curl -fL -o "$DATA/json_2.1.1_json.zip" https://github.com/alfworld/alfworld/releases/download/0.2.2/json_2.1.1_json.zip
curl -fL -o "$DATA/json_2.1.3_tw-pddl.zip" https://github.com/alfworld/alfworld/releases/download/0.4.2/json_2.1.3_tw-pddl.zip
shasum -a 256 "$DATA"/*.zip | tee "$ENV/alfworld_data_sha256.txt"
TOTAL=0                                                                     # uncompressed size of what we extract
for z in "$DATA"/json_2.1.1_json.zip "$DATA"/json_2.1.3_tw-pddl.zip; do      # (totals only, no file names printed)
    T=$(unzip -l "$z" '*/train/*' '*/valid_seen/*' | tail -1 | awk '{print $1}')
    TOTAL=$((TOTAL + T))
done
echo "to extract: $TOTAL bytes" | tee "$ENV/alfworld_extract_size.txt"
[ "$TOTAL" -lt 2500000000 ] || { echo "ABORT: extraction would exceed 2.5 GB"; exit 3; }
for z in "$DATA"/json_2.1.1_json.zip "$DATA"/json_2.1.3_tw-pddl.zip; do
    unzip -q -o "$z" '*/train/*' '*/valid_seen/*' -d "$DATA"            # held-out valid_unseen stays sealed
done
for split in train valid_seen valid_unseen; do                              # counts only, no names
    printf '%s traj_data %s game.tw-pddl %s\n' "$split" \
        "$(find "$DATA" -path "*/$split/*" -name traj_data.json | wc -l)" \
        "$(find "$DATA" -path "*/$split/*" -name game.tw-pddl | wc -l)"
done | tee "$ENV/alfworld_split_counts.txt"
$PY -m pip freeze > "$ENV/alfworld_install.txt"
du -sh "$ENV/venv-alf" "$DATA" | tee "$ENV/alfworld_disk.txt"
