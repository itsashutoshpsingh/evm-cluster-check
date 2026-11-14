# One command per step; `make all` reproduces every committed result from scratch.
PY ?= .venv/bin/python
ETH_START = 26316189
ETH_END   = 26337722
BASE_START = 53350927
BASE_END   = 53361726
SWEEP = https://raw.githubusercontent.com/liziwei1/SweeperHunter/b623678970ef6aa2e61c27720a9da9c58267fea2/dataset

.PHONY: all setup inputs fetch run injected figures summary notebook test

all: setup inputs fetch run injected figures summary notebook

setup:
	python3 -m venv .venv && $(PY) -m pip install -r requirements.txt

inputs:  ## ground truth, sanctions list, sweeper release
	$(PY) -m src.groundtruth
	mkdir -p data/raw/ofac data/raw/sweeperhunter
	curl -sL -o data/raw/ofac/SDN.XML https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML
	curl -sL -o data/raw/sweeperhunter/ETH_sweeper_contracts.csv $(SWEEP)/ETH_sweeper_contracts.csv
	curl -sL -o data/raw/sweeperhunter/attack_results.csv $(SWEEP)/attack_results.csv

fetch:  ## ~70 min for Ethereum, ~60 min for Base on free endpoints
	FETCH_RATE=6 $(PY) -m src.fetch blocks --chain eth --start $(ETH_START) --end $(ETH_END) --workers 10
	FETCH_RATE=4 $(PY) -m src.fetch blocks --chain base --start $(BASE_START) --end $(BASE_END) --workers 6

run:
	$(PY) -m src.run --chain eth
	$(PY) -m src.run --chain base --bootstrap 0
	$(PY) -m src.reproduce

injected:  ## needs `anvil --fork-url <rpc> --hardfork prague --port 8545` running
	$(PY) -m anvil.inject
	$(PY) -m anvil.fetch_blocks
	$(PY) -m anvil.evaluate

figures:
	$(PY) -m src.figures

notebook:
	$(PY) notebooks/make_notebook.py
	$(PY) -m jupyter nbconvert --to notebook --execute --inplace notebooks/01_week1_result.ipynb

test:
	$(PY) -m pytest -q tests

summary:  ## results/summary.json for the project site
	$(PY) -m src.summary
