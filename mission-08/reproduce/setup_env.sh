#!/bin/sh
# Mission 08 environment: Python 3.12, CPU only, versions pinned in requirements.lock. Third-party raw data are
# downloaded from their pinned sources and checked against the SHA-256 table in src/m08/raw.py (data/README.md).
set -e
cd "$(dirname "$0")/.."
${PYTHON:-python3.12} -m venv env/venv
env/venv/bin/pip install --quiet -r reproduce/requirements.lock
SP=$(env/venv/bin/python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')
echo "$(pwd)/src" > "$SP/m08_src.pth"
env/venv/bin/python -I -m m08.raw fetch
env/venv/bin/python -I -m pytest -q -p no:cacheprovider tests
