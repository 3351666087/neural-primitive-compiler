#!/bin/sh
# G4b B2: judge-side server for one batch of composite goals.  sh serve_b2.sh <batch> <socket name>  (repository root)
set -eu
K=$1; S=$2
mission-06/env/venv-alf/bin/python -I mission-06/experiments/g4b/cmp_server.py --sock "$TMPDIR/$S.sock" \
    --idx-file "mission-06/experiments/g4b/run/b2_batch${K}.json" --max-steps 100 --tag "_${K}" > "$TMPDIR/g4b_b2_${K}.log" 2>&1
echo "server g4b-${K} exited $?"
