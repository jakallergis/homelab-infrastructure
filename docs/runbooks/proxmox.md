# Runbook: Proxmox hosts

Run all commands from the repo root. Live runs need approval (see `AGENTS.md`). Ansible needs
`sshpass` on the workstation, and the workstation must already trust each node's SSH key.

```sh
export PATH=$HOME/.cache/homelab-infrastructure/venv/bin:$PATH
```

## Current state

- Cluster `homelab`: `pve01`, `pve02`, `pve03`, PVE 9.2.2.
- Package repositories: no-subscription. `pve-enterprise.sources` and `ceph.sources` stay on disk with
  `Enabled: false`.
- The root password is the same on all three nodes. It is not stored in this repo.

## Check health

Read-only. Expect `failed=0` and `changed=0` on all nodes.

```sh
ansible-playbook playbooks/verify.yml --ask-pass
```

## Change a host setting

Change one node at a time. `site.yml` uses `serial: 1`, but `--limit` keeps each run to the node that
you approved.

```sh
ansible-playbook playbooks/site.yml --limit pve01 --check --diff --ask-pass
ansible-playbook playbooks/site.yml --limit pve01 --diff --ask-pass
ansible-playbook playbooks/site.yml --limit pve01 --check --ask-pass
ansible-playbook playbooks/verify.yml --ask-pass
```

The third command must show `changed=0`. Do the same for the next node only after these pass.

The role does not run `apt upgrade`. Upgrades are a separate action that needs approval.

## Undo the repository change

Run on the affected node:

1. Delete `/etc/apt/sources.list.d/pve-no-subscription.sources`.
2. Remove the `Enabled: false` line from `pve-enterprise.sources` and `ceph.sources`.
3. Run `apt update`.
