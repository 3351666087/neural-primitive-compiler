#!/usr/bin/env bash
# One command: install, run all tests, run the demo.
set -euo pipefail
cd "$(dirname "$0")"
make all
