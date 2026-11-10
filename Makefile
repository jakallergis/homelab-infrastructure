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
TOFU ?= mise exec -- tofu

.PHONY: venv check inventory syntax yamllint ansible-lint shellcheck tofu test secrets

check: inventory syntax yamllint ansible-lint shellcheck tofu test secrets

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

shellcheck: $(STAMP)
	shellcheck tofu/run.sh

# The passphrase is a dummy: validate reads no state, and -backend=false skips the real state file.
tofu:
	$(TOFU) -chdir=tofu fmt -check
	TF_DATA_DIR=$(CACHE)/tofu-check $(TOFU) -chdir=tofu init -backend=false -input=false
	TF_DATA_DIR=$(CACHE)/tofu-check TF_VAR_state_passphrase=offline-check-only $(TOFU) -chdir=tofu validate

test: $(STAMP)
	$(PYTEST) tests/test_inventory.py tests/test_adguard.py

secrets: $(STAMP)
	$(PYTEST) tests/test_secrets.py
