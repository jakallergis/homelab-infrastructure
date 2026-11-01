# homelab-infrastructure

Infrastructure as Code for a personal homelab: three Proxmox nodes, Docker Swarm, DNS, an edge pair
and Home Assistant. The design is in [`docs/architecture-target.md`](docs/architecture-target.md).
Rules for AI sessions and the order of work are in [`AGENTS.md`](AGENTS.md).

**Status:** the Proxmox base and the Tailscale routers are live. No guests exist yet.

## Requirements

Python 3.12 and `make`. The tools install into `~/.cache/homelab-infrastructure/venv`, not the repo,
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
| `tests/` | Offline tests |
| `docs/` | The target design and the runbooks |

## Running against real machines

Only with explicit approval for that action. See `AGENTS.md`. This needs `sshpass` on the machine
that runs Ansible, and that machine must already trust each host's SSH key.

```sh
ansible-playbook playbooks/verify.yml --ask-pass
```
