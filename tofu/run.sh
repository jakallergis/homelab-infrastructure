#!/usr/bin/env bash
# Run OpenTofu with the secrets from Vault. Example: tofu/run.sh plan
set -euo pipefail

cd "$(dirname "$0")/.."
export PATH="$HOME/.cache/homelab-infrastructure/venv/bin:$PATH"
export TF_DATA_DIR="$HOME/.cache/homelab-infrastructure/tofu"
export ANSIBLE_VAULT_PASSWORD_FILE=/media/VMPal/ansible-vault/vault-pass

secrets="$(ansible-vault view secrets/tofu.env)"
# shellcheck disable=SC1090
source <(printf '%s\n' "$secrets")
unset secrets

read -rsp "Proxmox root password: " PROXMOX_VE_SSH_PASSWORD
echo
export PROXMOX_VE_SSH_PASSWORD

exec mise exec -- tofu -chdir=tofu "$@"
