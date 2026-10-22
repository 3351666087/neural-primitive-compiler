#!/bin/sh
# Craftax-Classic environment for Mission 07 (third-party code, installed outside git; not redistributed).
# Versions as used in Gate 1 and Gate 4 (G1_FEASIBILITY.md): craftax 1.6.1, crafter 1.8.3, jax / jaxlib 0.12.0.
set -e
cd "$(dirname "$0")/../.."
${PYTHON:-python3.12} -m venv env/venv-craft
env/venv-craft/bin/pip install --quiet craftax==1.6.1 crafter==1.8.3 jax==0.12.0 jaxlib==0.12.0
env/venv-craft/bin/python -I -c "import craftax, jax; print('craftax ok, jax', jax.__version__)"
