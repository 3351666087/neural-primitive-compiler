#!/bin/sh
# Gate 3 (development data only): structure positive and negative controls, developmental proxies, function-line
# interface checks and controls, T4 structure-only predictions. Outputs: results/g3/*.json.
set -e
cd "$(dirname "$0")/.."
PY="env/venv/bin/python -I -W ignore"
$PY experiments/g3_structure_dev.py --grid 10 --workers 5
mv results/g3/structure_dev.json results/g3/structure_dev_grid10.json
$PY experiments/g3_structure_dev.py --grid 40 --workers 2 --positive-only
$PY experiments/g3_development_dev.py --grid 10
$PY experiments/g3_function_dev.py
$PY experiments/g3_t4_dev.py
