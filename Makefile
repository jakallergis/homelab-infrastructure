# Offline checks only. Nothing here connects to a homelab host.
# The venv and caches stay outside the repo: the repo mount cannot create symlinks.
CACHE ?= $(HOME)/.cache/homelab-infrastructure
VENV ?= $(CACHE)/venv
BIN := $(VENV)/bin
STAMP := $(VENV)/.installed

export PATH := $(BIN):$(PATH)
export ANSIBLE_HOME ?= $(CACHE)/ansible
export PYTHONDONTWRITEBYTECODE := 1
PYTEST := pytest -q -p no:cacheprovider

.PHONY: venv check inventory syntax yamllint ansible-lint test secrets

check: inventory syntax yamllint ansible-lint test secrets

venv: $(STAMP)

$(STAMP): requirements-dev.txt
	python3 -m venv $(VENV)
	$(BIN)/pip install -q --upgrade pip
	$(BIN)/pip install -q -r requirements-dev.txt
	touch $(STAMP)

inventory: $(STAMP)
	ansible-inventory --graph

syntax: $(STAMP)
	ansible-playbook --syntax-check playbooks/*.yml

yamllint: $(STAMP)
	yamllint --strict .

ansible-lint: $(STAMP)
	ansible-lint

test: $(STAMP)
	$(PYTEST) tests/test_inventory.py

secrets: $(STAMP)
	$(PYTEST) tests/test_secrets.py
