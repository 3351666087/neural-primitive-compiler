#!/bin/sh
# Gate 4 B2: run the judge-side server for one batch until the agent asks past the last game.
#   sh serve_g4.sh <g4c|g4p> <batch> <socket name>      (run from the repository root)
set -eu
P=$1; K=$2; S=$3
EXTRA=""
[ "$P" = "g4p" ] && EXTRA="--perturb-base 7300"
mission-06/env/venv-alf/bin/python -I mission-06/experiments/b2/alf_server.py --sock "$TMPDIR/$S.sock" \
    --games-file "mission-06/experiments/b2/run/${P}_batch${K}.json" --max-steps 50 --tag "_${P}${K}" $EXTRA \
    > "$TMPDIR/${P}${K}.log" 2>&1
echo "server ${P}${K} exited $?"
