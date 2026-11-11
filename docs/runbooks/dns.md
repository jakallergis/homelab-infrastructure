# Runbook: DNS (AdGuard Home)

`dns01` (`.31`) and `dns02` (`.32`) run AdGuard Home in unprivileged LXCs. Each one alone answers
`*.lab.krikri.dev` → `192.168.0.30` and forwards all other names to Cloudflare and Quad9 over DoH.
Live runs need approval (see `AGENTS.md`). Run all commands from the repo root.

```sh
export PATH=$HOME/.cache/homelab-infrastructure/venv/bin:$PATH
```

## Current state

- `dns01` and `dns02`: applied, verified, idempotent, and the web UI login works.
- adguardhome-sync does not exist yet (milestone 7). Make each UI change on both servers.
- The router's DHCP still gives `192.168.0.1` as DNS. Tailscale split DNS is not set.

## How it is built

| Item | Where |
|---|---|
| Version and checksums | `inventory/group_vars/dns.yml` |
| Starting upstream and bootstrap servers | `inventory/group_vars/dns.yml` |
| Program | `/opt/AdGuardHome/<version>/AdGuardHome/AdGuardHome`, owned by root |
| Configuration and data | `/var/lib/adguardhome/`, owned by the user `adguardhome`, mode `0700` |
| Service | `adguardhome.service`, runs as `adguardhome` with only `CAP_NET_BIND_SERVICE` |
| Web UI | `http://192.168.0.31/` and `http://192.168.0.32/`, user `admin`, LAN only, plain HTTP |
| Admin password hash | `secrets/dns.yml` (`adguard_admin_password_hash`), encrypted with Vault |

The admin password itself is in the owner's password manager.

## Who owns the settings

| What | Owner |
|---|---|
| Starting configuration: ports, admin user, upstreams, the `*.lab.krikri.dev` rewrite | Git. `roles/adguard_config` writes it only when `/var/lib/adguardhome/AdGuardHome.yaml` does not exist |
| All later changes (filters, blocking, clients, rewrites, upstreams) | The web UI of `dns01`. Ansible does not overwrite them |
| Copy from `dns01` to `dns02` | adguardhome-sync (milestone 7). Until then, change both UIs |
| The lab wildcard and public names still work | `verify.yml` (read-only) checks it on each server |
| Recovery of UI changes | Backups (milestone 10). Without a backup, a rebuilt server starts from the Git config |

A change to the template or to `dns.yml` reaches only new or reset servers. AdGuard Home writes the
file back each time it starts, so the template is AdGuard Home's own output for the pinned version.
`make test` starts the pinned version on local ports, checks the wildcard answer, and checks that
AdGuard Home leaves the rendered file unchanged.

The Vault hash is also used only by new or reset servers. The web UI cannot change the password.

## Create the admin password hash

The command asks for the admin password (prompt `Password:`), hashes it with bcrypt and encrypts
the result. The hash is never shown.

```sh
python3 -c 'import bcrypt, getpass, yaml; h = bcrypt.hashpw(getpass.getpass().encode(), bcrypt.gensalt(10)).decode(); print(yaml.safe_dump({"adguard_admin_password_hash": h}), end="")' | ansible-vault encrypt --vault-password-file "$HOMELAB_PRIVATE_DIR/vault-pass" --output secrets/dns.yml
```

## Apply

One server at a time. Do `dns02` only after `dns01` passes the checks.

```sh
ansible-playbook playbooks/site.yml --limit dns01 --check --diff --ask-pass --ask-become-pass --vault-password-file "$HOMELAB_PRIVATE_DIR/vault-pass"
ansible-playbook playbooks/site.yml --limit dns01 --ask-pass --ask-become-pass --vault-password-file "$HOMELAB_PRIVATE_DIR/vault-pass"
ansible-playbook playbooks/verify.yml --limit dns01
```

On the first install, skip the `--check` line: check mode cannot unpack a file it did not download,
so it fails. The configuration task uses `no_log`, so `--diff` does not show that file (it contains
the hash). It still shows whether the file changes.

## Check health

Read-only. It asks each server alone, from the workstation, and needs no password:

```sh
ansible-playbook playbooks/verify.yml --limit dns
dig +short @192.168.0.31 test.lab.krikri.dev
dig +short @192.168.0.32 test.lab.krikri.dev
```

## Upgrade AdGuard Home

1. Set `adguard_version` and both checksums from the release's `checksums.txt` in
   `inventory/group_vars/dns.yml`.
2. Run `make test`. If AdGuard Home rewrites the file, the new version writes a different format:
   start it once on a copy of the rendered file and update the template from its output.
3. Before the apply, copy `/var/lib/adguardhome/AdGuardHome.yaml` on each server. The new version can
   change the file's format at its first start, and an older version may not read it again.
4. Apply to `dns01`, verify, then `dns02`. The old release stays in `/opt/AdGuardHome/` for a rollback:
   put the copy back, set the old version again and apply.

## Reset a server to the Git configuration

This deletes every change made in that server's web UI. It is a live action that needs approval each
time. Reset one server at a time, and verify it before the other.

```sh
ssh -t john@192.168.0.32 'sudo systemctl stop adguardhome && sudo rm /var/lib/adguardhome/AdGuardHome.yaml'
ansible-playbook playbooks/site.yml --limit dns02 --ask-pass --ask-become-pass --vault-password-file "$HOMELAB_PRIVATE_DIR/vault-pass"
ansible-playbook playbooks/verify.yml --limit dns02
```
