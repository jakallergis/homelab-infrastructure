#!/usr/bin/env bash
# Run OpenTofu with the secrets from Vault. Example: tofu/run.sh plan
set -euo pipefail

cd "$(dirname "$0")/.."
export PATH="$HOME/.cache/homelab-infrastructure/venv/bin:$PATH"
export TF_DATA_DIR="$HOME/.cache/homelab-infrastructure/tofu"
: "${HOMELAB_PRIVATE_DIR:?Set HOMELAB_PRIVATE_DIR to the folder with vault-pass and the OpenTofu state}"
export ANSIBLE_VAULT_PASSWORD_FILE="$HOMELAB_PRIVATE_DIR/vault-pass"
export TF_CLI_ARGS_init="-backend-config=path=$HOMELAB_PRIVATE_DIR/tofu/terraform.tfstate"
mkdir -p "$HOMELAB_PRIVATE_DIR/tofu"

secrets="$(ansible-vault view secrets/tofu.env)"
# shellcheck disable=SC1090
source <(printf '%s\n' "$secrets")
unset secrets

# Ansible uses the same hash for the containers, so it lives in one Vault file for both.
TF_VAR_john_password_hash="$(ansible-vault view secrets/guests.yml |
  python3 -c 'import sys, yaml; print(yaml.safe_load(sys.stdin)["john_password_hash"])')"
export TF_VAR_john_password_hash

read -rsp "Proxmox root password: " PROXMOX_VE_SSH_PASSWORD
echo
export PROXMOX_VE_SSH_PASSWORD

exec mise exec -- tofu -chdir=tofu "$@"
