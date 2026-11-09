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
- Storage `local` allows `backup,import,iso,snippets,vztmpl`. This setting is cluster-wide. Before the
  role added `snippets`, it was `import,iso,backup,vztmpl`.

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

## OpenTofu access

OpenTofu logs in as `tofu@pve` with an API token. If you rebuild the cluster, do this once.

1. In the web UI, open a node, then **Shell**, and create the role:

   ```sh
   pveum role add TofuProvision -privs "Datastore.Allocate Datastore.AllocateSpace Datastore.AllocateTemplate Datastore.Audit SDN.Audit SDN.Use Sys.Audit Sys.Modify VM.Allocate VM.Audit VM.Config.CDROM VM.Config.CPU VM.Config.Cloudinit VM.Config.Disk VM.Config.HWType VM.Config.Memory VM.Config.Network VM.Config.Options VM.GuestAgent.Audit VM.PowerMgmt"
   ```

2. **Datacenter > Permissions > Users > Add:** user `tofu`, realm `Proxmox VE authentication server`.
3. **Datacenter > Permissions > API Tokens > Add:** user `tofu@pve`, token ID `tofu`. Clear **Privilege
   Separation**. Copy the secret: Proxmox shows it only once.
4. **Datacenter > Permissions > Add > User Permission:** path `/`, user `tofu@pve`, role `TofuProvision`.
5. Put the token in `secrets/tofu.env` with `ansible-vault`. Never store it anywhere else.

`secrets/tofu.env` holds these three exports, with the values in single quotes:

| Variable | Value |
|---|---|
| `PROXMOX_VE_API_TOKEN` | `tofu@pve!tofu=<secret>` |
| `TF_VAR_john_password_hash` | The output of `openssl passwd -6` |
| `TF_VAR_state_passphrase` | A long random passphrase. Without it, the state cannot be read |

## Undo the repository change

Run on the affected node:

1. Delete `/etc/apt/sources.list.d/pve-no-subscription.sources`.
2. Remove the `Enabled: false` line from `pve-enterprise.sources` and `ceph.sources`.
3. Run `apt update`.
