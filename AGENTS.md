# Rules for AI sessions

The owner is learning as we go and wants to understand everything in this repo.
`docs/architecture-target.md` is the design authority. Read it fully before you do any work.

## Workstation

- Ubuntu 26.04, arm64, Python 3. Docker/Podman, HAProxy, Keepalived and shellcheck are not installed.
  Ask before you install anything system-wide. Prefer user-level tools.
- The repo is on a virtiofs mount where creating symlinks fails. The venv, tool caches and extracted
  packages stay in `~/.cache/homelab-infrastructure/`.
- The GitHub remote is `origin` and the repo is private. Never push unless the owner asks.

## How to work

Work in small milestones. For each one:

1. Give a short plan that lists the files and why.
2. Wait for the owner's OK.
3. Write the code and run offline tests.
4. Explain in ASD-STE100 what each new file does.
5. The owner reviews and commits. Each time you finish updating files, give a short commit message
   for that iteration.
6. Only then, if the milestone touches real machines, ask for approval for that specific live action.

- **Don't build ahead.** No placeholder roles, speculative variables or files for later milestones.
  Prefer the simplest thing that meets the target. Fewer files beat clever abstractions.
- If the repo can't answer something, ask, or give the exact read-only command that reveals it. Mark
  it UNKNOWN in the docs until answered. Don't guess facts about the network or hardware.
- Keep docs short and current: `README.md`, this file, `docs/architecture-target.md`, and one runbook
  per area once that area is live.

## Safety and authorization

- By default, only edit files in this repo and run local/offline checks. Connecting to any host,
  running Ansible or OpenTofu against real machines, or changing Tailscale, Cloudflare or router
  settings each needs explicit approval for that specific action. Approval doesn't carry over.
- Before any live action, state which hosts change, what could break, how you'll verify it, and how
  to roll back.
- **Remote access:** once Tailscale is in use, never change both subnet routers in one operation, and
  never change Proxmox networking on a node that is the owner's only access path. Do Proxmox
  network/Tailscale work while the owner is on the LAN unless they say otherwise.
- **Redundant pairs** (edge, DNS, Tailscale routers, Swarm managers): change one node at a time and
  verify before the second.
- **Floating IP `.30`:** never allow two owners. Edge nodes come up with Keepalived disabled. Enable
  VRRP deliberately, one node at a time, with a duplicate-address check (`arping -D`) first. Check
  that the Proxmox firewall / IP filter doesn't block the VIP on the edge NICs.
- **Secrets:** never print, log or commit passwords, password hashes (including Cloud-Init
  `hashed_passwd`), API tokens, private keys, `/etc/letsencrypt` private files, Vault passwords or
  OpenTofu state containing secrets. Use `no_log: true` on Ansible tasks that handle secrets. Document
  where a secret lives and how to recover it, never its value.
- No blanket `apt upgrade`, no destructive `qm`/`pct`/`pvecm` commands, no `tofu apply` that destroys
  or replaces a resource, and no service restarts on live hosts without approval.
- Report honestly: show real command output when it matters, never claim something is healthy based
  on lint, and say clearly which steps were only coded and which were actually applied.

## Order of work

1. **Repo foundation.** Done.
2. **Proxmox base.** Done. See `docs/runbooks/proxmox.md`.
3. **Remote access.** Done, except split DNS, which comes after step 5. See
   `docs/runbooks/tailscale.md`. Set up Ansible Vault at the first milestone that needs a secret.
4. **Guest provisioning with OpenTofu** (`bpg/proxmox`). Code is in `tofu/`, run through `tofu/run.sh`.
   Cloud-Init sets the static IP, hostname, user `john`, password and installs `qemu-guest-agent`. The
   image is on each node's local storage (no cross-node cloning). A guest is provisioned once the
   inventory gives it a size. Start with `edge01`, review the plan together, then add the rest. LXC
   guests need a Debian 13 container template and another way to create `john`. Proxmox hosts stay off
   `.31`/`.32`.
5. **DNS.** AdGuard Home on `dns01`/`dns02` (unprivileged LXCs), wildcard `*.lab.krikri.dev` →
   `192.168.0.30`, upstream Cloudflare and Quad9 over DoT or DoH. Verify both resolve independently.
   Then the owner changes the router's DHCP DNS to
   `.31`/`.32`, and you add Tailscale split DNS.
6. **Docker hosts and Swarm.** A `docker_host` role (Engine + Compose plugin from Docker's repo,
   pinned), Swarm init/join as a separate bootstrap step, 3 managers.
7. **Swarm stacks.** Traefik (2 replicas, HTTP entrypoint on ingress `:18080`, no ACME, trusts forwarded
   headers only from `.33`/`.34`), Portainer CE + agent, adguardhome-sync (`dns01` → `dns02`). One
   deploy path from the repo; pinned image tags.
8. **Edge pair.** Roles split by concern:
   - `edge_install`: packages; Keepalived masked.
   - `edge_tls`: Certbot + Cloudflare DNS-01, token from Vault, deploy hook, Let's Encrypt staging /
     `--dry-run` first. The production limit is 5 certificates per identical name set per week, and
     both edges count.
   - `edge_config`: HAProxy and Keepalived templates validated with `haproxy -c` / `keepalived -t`
     before install, a loopback health endpoint for the track script, VRRP behind an explicit opt-in
     variable that defaults to false.
   - `edge_verify`: read-only; exactly one VIP owner, cert expiry, routes.

   Test each edge directly on its own IP before VRRP. Enable VRRP on `edge01`, verify, then `edge02`,
   then do a failover drill with approval.
9. **Home Assistant.** HAOS VM via OpenTofu, no USB passthrough for now (HAOS is on `pve02`, so a
   stick can be added there later). HAProxy route direct to `.20:8123`. Configure
   `use_x_forwarded_for` and `trusted_proxies` (`.33`, `.34`) in HA before testing through the edge.
10. **Backups and recovery.** vzdump jobs to the NAS, HA backups, AdGuard, Portainer data and encrypted
    secrets, then a restore test for each class. Runbooks. The NAS is not available yet, so this step
    is blocked on it.

## UNKNOWN

Remove each item once it is answered.

- NAS: address, protocol, free space (the NAS is not available yet).
- `/media/VMPal/ansible-vault/`: whether it has a backup off the MacBook. `chmod` works only on the Mac
  side of the share.

## Accounts

- Tailnet: `tail8b0eff.ts.net`.
- A Cloudflare API token exists. It is not in this repo yet.
- Tailscale login is manual. There is no auth key.
- Vault password: the file `vault-pass` in `/media/VMPal/ansible-vault/`, outside the repo. Do not set
  `vault_password_file` in `ansible.cfg`, because CI has no such file. `tofu/run.sh` sets it instead.
- OpenTofu state: `/media/VMPal/ansible-vault/tofu/`, encrypted, not in Git.
- Secrets for OpenTofu: `secrets/tofu.env`, encrypted with Vault. The root password is typed at each
  run. See `docs/runbooks/proxmox.md`.

## Technical notes

- Run Ansible from the repo root so `ansible.cfg` (inventory, `roles_path`) is picked up.
- Password SSH with Ansible needs `sshpass` and `--ask-pass` / `--ask-become-pass`. Keep
  `host_key_checking` on: confirm each new guest's SSH host key fingerprint from the Proxmox console
  before the first connection.
- A bare expression in `assert` or `when` reads `'\b'` as a backspace, but `{{ }}` does not. Test an
  assertion in its real form, not wrapped in `{{ }}`.
- Plain `tailscale up` and `tailscale login` reset the routes and `accept-dns`. The role logs in with
  the full flags. Do not log in by hand.
- The workstation is a VM on a MacBook. Its clock falls behind when the Mac sleeps, and `chrony` steps
  only in its first 3 updates unless `makestep 1 -1` is set.
- `failed_when: false` / `ignore_errors` hide real failures. Use them only with an explicit assertion
  afterwards.
- Keepalived 2.x refuses track scripts unless `global_defs` has `enable_script_security` (and
  `script_user`) and the script is root-owned and not writable by others. `keepalived -t` returns
  non-zero for this, so treat any non-zero exit as a failure.
- `keepalived -t` and `haproxy -c` can run offline against rendered templates. If the binaries aren't
  installed, document the gap rather than skipping silently. Debian/Ubuntu `.deb`s can be extracted
  without root (`apt-get download` + `dpkg-deb -x`) into `~/.cache`. `keepalived -t` also needs
  `keepalived.config-opts` next to the binary, a real interface name, and, when not root, `script_user`
  set to the current user.
- `curl -I` sends HEAD, and Home Assistant answers HEAD on `/` with 405. Test HA with GET and a real
  browser login.
- Swarm's ingress routing mesh source-NATs traffic. That's why HA is proxied directly from HAProxy and
  Traefik's trusted-proxy list contains only the edge IPs.
- Proxmox clustering doesn't make single-instance guests highly available here (local storage). Don't
  present it as failover.
- A Proxmox VIP problem can come from the guest NIC's `firewall=1` + IP filter. Check before enabling
  VRRP.
- Debian cloud images use a DHCP client ID based on DUID, not MAC. Irrelevant here because guests use
  static addresses, but don't switch them to DHCP reservations without accounting for it.
