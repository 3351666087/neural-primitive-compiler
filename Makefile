# Single-command entry points. Tested on an Apple M4 MacBook Air (arm64, macOS), Python 3.12, z3-solver 5.3.1.
PY     ?= $(shell command -v python3.12 || command -v python3.11 || command -v python3)
VENV   := .venv
BIN    := $(VENV)/bin
NPC    := $(BIN)/npc

.PHONY: all install test test-fast demo experiments unseen mission02 clean

all: install test demo

install:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -q --upgrade pip
	$(BIN)/pip install -q -e ".[dev]"
	$(BIN)/python -c "import z3, platform; print('z3', z3.get_version_string(), 'on', platform.machine())"

test:
	$(BIN)/python -m pytest -q

demo:
	$(NPC) check examples/toggle.npc
	$(NPC) sim examples/toggle.npc --network toggle_lite --input a=10010100
	$(NPC) verify examples/toggle.npc --network toggle_lite --spec parity_sparse --horizon 10 --compositional
	$(NPC) realize experiments/tasks.npc --spec C2_parity_dense
	-$(NPC) synth experiments/tasks.npc --spec C2_parity_dense --method cegis --timeout 120 --out out/C2_cegis.json
	-$(NPC) realize examples/parity_latency1.npc --spec parity_latency1
	@echo "(exit code 1 from the last step is expected: Theorem 3 proves parity at latency 1 unrealizable)"

experiments:
	$(BIN)/python experiments/run_experiments.py abc
	$(BIN)/python experiments/run_experiments.py scaling
	$(BIN)/python experiments/run_experiments.py q2
	$(BIN)/python experiments/run_experiments.py summary
	$(BIN)/python experiments/llm_sketches/run_abc_sketches.py

unseen:
	$(BIN)/python experiments/D_unseen/run_unseen.py run

mission02:
	$(BIN)/python -m cog.proofs
	$(BIN)/python mission-02/experiments/unseen/run_unseen.py run
	$(BIN)/python mission-02/experiments/unseen/posthoc_third_size.py

clean:
	rm -rf out .pytest_cache .hypothesis
