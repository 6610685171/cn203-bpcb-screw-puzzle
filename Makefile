PYTHON ?= python3
VENV := .venv
VENV_PYTHON := $(VENV)/bin/python
VENV_PIP := $(VENV)/bin/pip
SETUP_STAMP := $(VENV)/.setup-complete

.PHONY: setup test verify graphs reproduce benchmark clean

setup: $(SETUP_STAMP)

$(SETUP_STAMP): requirements.txt
	$(PYTHON) -m venv $(VENV)
	$(VENV_PIP) install --upgrade pip
	$(VENV_PIP) install -r requirements.txt
	touch $(SETUP_STAMP)

test:
	$(PYTHON) -m unittest discover -s tests -v

verify:
	$(PYTHON) -m unittest discover -s tests -q
	$(PYTHON) scripts/verify_final_benchmark.py

graphs: setup
	$(VENV_PYTHON) scripts/run_final_evaluation.py --repeats 5 --warmup 1

reproduce: setup
	$(VENV_PYTHON) -m unittest discover -s tests -q
	$(VENV_PYTHON) scripts/verify_final_benchmark.py
	$(VENV_PYTHON) scripts/run_final_evaluation.py --repeats 5 --warmup 1

benchmark: setup
	$(VENV_PYTHON) scripts/run_final_evaluation.py --repeats 5 --warmup 1 --restart

clean:
	rm -rf $(VENV)

