# Runbook: guest VMs (OpenTofu)

OpenTofu creates the Debian VMs from `tofu/`. Run it only through `tofu/run.sh`, from the repo root.
Live runs need approval (see `AGENTS.md`).

## Current state

- `edge01`, `edge02` and `docker01`–`03` are live. Their SSH host keys were checked against the console.
- `dns01`/`dns02` (LXC) and `homeassistant` (HAOS) are not managed here yet.
- OpenTofu creates every inventory host with `type: debian_vm`. It does not look at group names.

## What a run needs

| Item | Where |
|---|---|
| `HOMELAB_PRIVATE_DIR` | Set in your shell. The folder holds `vault-pass` and the state in `tofu/` |
| API token, `john` password hash, state passphrase | `secrets/tofu.env`, encrypted with Vault. See `proxmox.md` |
| Proxmox root password | Typed at each run. SSH is used only to upload the Cloud-Init file |

A copy of `vault-pass` must be in the owner's password manager. Without it, `secrets/tofu.env` and the
state cannot be read.

## Plan and apply

```sh
tofu/run.sh plan
tofu/run.sh apply
```

`apply` shows the plan again. Type `yes` only if the summary line is what you expect. Type `no` if it
shows `destroy` or `must be replaced` that you did not plan.

If `init` fails to download the provider signature from GitHub, use the copy that `make check` already
verified. OpenTofu still checks it against the hashes in `tofu/.terraform.lock.hcl`:

```sh
TF_PLUGIN_CACHE_DIR=$HOME/.cache/homelab-infrastructure/tofu-check/providers tofu/run.sh init
```

## Add a guest

1. Give the host `type: debian_vm`, `cores`, `memory_mb` and `disk_gb` in `inventory/hosts.yml`.
   They must match the table in `docs/architecture-target.md`. `make test` checks this, and that the
   disks fit in `local-lvm`.
2. Check that the address is free: `ping -c 3 <address>` must fail.
3. `tofu/run.sh apply`. Expect only `to add`, with `0 to change, 0 to destroy`.
4. `tofu/run.sh plan` must show `No changes.`
5. Check the host key. In the Proxmox UI, open the VM, then **Console**. Log in as `john` and run
   `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`. Then run `ssh john@<address>` from the
   workstation and accept the key only if the `SHA256:` values are equal.

## If an apply fails

Do not run `apply` again before you read the next plan.

- A resource that failed before it was created is simply planned again (`to add`).
- A VM that was created but failed later (for example, the guest agent did not start within 15
  minutes) is marked tainted, and the next plan wants to replace it. Find the cause on the VM console
  first. If the VM is fine, `tofu/run.sh untaint 'proxmox_virtual_environment_vm.guest["<name>"]'`
  keeps it.
- A `403 Permission check failed` names the missing privilege. Add it to the `TofuProvision` role and
  to the command in `proxmox.md`.

## Change a guest

- **Size:** change the design table and the inventory. The plan shows `~ update in-place`. A change
  that needs a reboot (for example, memory) reboots the VM during `apply`.
- **Debian image:** a new `image_url` gives new image files. The plan can then want to replace every
  VM, because each disk was imported from the old file. Read the plan before you answer `yes`.
  This was not tested.

## Remove a guest

Removing `type: debian_vm` from the inventory makes the next plan destroy the VM and its disk. A destroy
needs approval, and the guest's data is lost unless it is backed up.
