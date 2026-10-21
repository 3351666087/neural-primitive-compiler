#!/bin/sh
# Gate 4: unseal the official ALFWorld held-out split valid_unseen (judge side). Run from the repository root, only
# after the Gate 4 freeze commit has been pushed. Prints counts only, no file names.
set -eu
DATA=mission-06/env/alfworld-data
for z in "$DATA"/json_2.1.1_json.zip "$DATA"/json_2.1.3_tw-pddl.zip; do
    unzip -q -o "$z" '*/valid_unseen/*' -d "$DATA"
done
printf 'valid_unseen traj_data %s game.tw-pddl %s\n' \
    "$(find "$DATA" -path '*/valid_unseen/*' -name traj_data.json | wc -l)" \
    "$(find "$DATA" -path '*/valid_unseen/*' -name game.tw-pddl | wc -l)"
