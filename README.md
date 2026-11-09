# homelab-infrastructure

Infrastructure as Code for a personal homelab: three Proxmox nodes, Docker Swarm, DNS, an edge pair
and Home Assistant. The design is in [`docs/architecture-target.md`](docs/architecture-target.md).
Rules for AI sessions and the order of work are in [`AGENTS.md`](AGENTS.md).

**Status:** the Proxmox base and the Tailscale routers are live. OpenTofu has created `edge01`. The
runbooks are in [`docs/runbooks/`](docs/runbooks/).

## Requirements

Python 3.12, `make` and [mise](https://mise.jdx.dev/) for OpenTofu (`mise install`). The tools install into `~/.cache/homelab-infrastructure/venv`, not the repo,
because the repo mount cannot create symlinks. Set `VENV=...` to use another location.

## Offline checks

Run from the repo root, so that Ansible finds `ansible.cfg`.

```sh
make check
```

| Target | What it does |
|---|---|
| `make venv` | Creates the venv and installs `requirements-dev.txt` |
| `make inventory` | Prints the inventory groups and hosts |
| `make syntax` | Runs `ansible-playbook --syntax-check` on each playbook |
| `make yamllint` | Lints all YAML files |
| `make ansible-lint` | Lints the Ansible content |
| `make shellcheck` | Lints the shell script |
| `make tofu` | Checks the OpenTofu format and validates the configuration |
| `make test` | Checks the inventory against the design rules |
| `make secrets` | Scans the repo for secret patterns |

GitHub Actions runs `make check` on each push to `main` and on each pull request. It has no secrets
and cannot reach the LAN. The secret scan reads the current files only, not Git history.

## Layout

| Path | Content |
|---|---|
| `inventory/hosts.yml` | The one source for hosts, addresses and guest IDs |
| `inventory/group_vars/` | Variables for each group |
| `playbooks/site.yml` | Applies the desired state, one host at a time. Needs `--limit` for a real run, to select one Tailscale router |
| `playbooks/verify.yml` | Read-only health checks |
| `roles/` | Ansible roles |
| `tofu/` | OpenTofu configuration for the guests. Run it through `tofu/run.sh` |
| `secrets/` | Secrets encrypted with Vault |
| `tests/` | Offline tests |
| `docs/` | The target design and the runbooks |

## Running against real machines

Set `HOMELAB_PRIVATE_DIR` to a private folder outside the repo, for example in your shell profile:

```sh
export HOMELAB_PRIVATE_DIR=/media/VMPal/ansible-vault   # on the Ubuntu VM
```

That folder holds `vault-pass` (the Vault password) and `tofu/` (the encrypted OpenTofu state). Only
with explicit approval for that action. See `AGENTS.md`. This needs `sshpass` on the machine
that runs Ansible, and that machine must already trust each host's SSH key.

```sh
ansible-playbook playbooks/verify.yml --ask-pass
```
