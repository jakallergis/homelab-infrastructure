# Homelab from scratch: implementation brief

You're helping me build a personal homelab from scratch as Infrastructure as Code. Apart from
this brief, the Git repository contains only a minimal `.gitignore` and
`docs/architecture-target.md`, which describes the agreed target. Read it fully first. It is the design authority; this brief covers context, working rules
and the order of work.

## What exists today

- **Three Proxmox VE nodes**, freshly installed, with nothing else on them: `pve01`
  `192.168.0.11`, `pve02` `192.168.0.12`, `pve03` `192.168.0.13` (hardware in the target doc).
  I log in as `root` with a password over SSH and the web UI on `:8006`.
- **Router** (TP-Link Archer C6): its DHCP pool is `192.168.0.150`–`.254`, so `192.168.0.2`–`.149`
  is free for the homelab. The three Proxmox nodes already have their addresses. Everything else
  in the target address plan is free and to be created.
- **Domain** `krikri.dev`, DNS hosted at Cloudflare. `lab.krikri.dev` is for internal use only.
- **Nothing else**: no VMs, containers, Tailscale setup, DNS servers, certificates or code yet.

### My workstation (where you run)
- Ubuntu 26.04, **arm64**. Python 3 is available. Docker/Podman, HAProxy, Keepalived and
  shellcheck are not installed. Ask before installing anything system-wide; prefer a project
  `.venv` and user-level tools.
- The repo is at `/media/VMPal/homelab-infrastructure` on a virtiofs mount where **creating
  symlinks fails**. Keep tool caches and extracted packages outside the repo (e.g. `~/.cache/…`).
- The GitHub remote is `origin`. Never push unless I ask.

## How I want to work

I'm learning as we go, and I want to understand everything in this repo.
- Work in **small milestones**. For each one: (1) a short plan listing the files you'll create and
  why; (2) wait for my OK; (3) write the code and run offline tests; (4) explain in ASD-STE100
  what each new file does; (5) I review and commit; (6) only then, if the milestone touches real
  machines, ask for explicit approval for that specific live action.
- **Don't build ahead.** No placeholder roles, speculative variables or files for later
  milestones. Prefer the simplest thing that meets the target. Fewer files beat clever
  abstractions.
- When something can't be known from the repo, ask me or give the exact read-only command that
  would reveal it, and mark it UNKNOWN in the docs until answered. Don't guess facts about my
  network or hardware.
- Keep docs short and current: `README.md` (how to use the repo), `AGENTS.md` (rules for future AI
  sessions, matching this brief), `docs/architecture-target.md`, and a runbook per area once that
  area is live.

## Safety and authorization rules

- By default, only edit files in this repo and run **local/offline** checks. Connecting to any
  host, running Ansible or OpenTofu against real machines, or changing Tailscale, Cloudflare or
  router settings each needs my explicit approval for that specific action. Approval for one step
  doesn't carry over to the next.
- Before any live action, state: which hosts change, what could break, how you'll verify it, and
  how to roll back.
- **Remote access:** once Tailscale is in use, never change both subnet routers in one operation,
  and never change Proxmox networking on a node that is my only access path. Do Proxmox
  network/Tailscale work while I'm on the LAN unless I say otherwise.
- **Redundant pairs** (edge, DNS, Tailscale routers, Swarm managers): change one node at a time and
  verify before the second.
- **Floating IP `.30`:** never allow two owners. Edge nodes come up with Keepalived disabled. VRRP is
  enabled deliberately, one node at a time, with a duplicate-address check (`arping -D`) first.
  Check that the Proxmox firewall / IP filter doesn't block the VIP on the edge NICs.
- **Secrets:** never print, log or commit passwords, password hashes (including Cloud-Init
  `hashed_passwd`), API tokens, private keys, `/etc/letsencrypt` private files, Vault passwords or
  OpenTofu state containing secrets. Use `no_log: true` on Ansible tasks that handle secrets.
  Document where a secret lives and how to recover it, never its value. Add a test that scans the
  repo for secret patterns.
- No blanket `apt upgrade`, no destructive `qm`/`pct`/`pvecm` commands, no `tofu apply` that
  destroys or replaces a resource, and no service restarts on live hosts without approval.
- Report honestly: show real command output when it matters, never claim something is healthy
  based on lint, and say clearly which steps were only coded and which were actually applied.

## Order of work (suggested; propose changes if you see a better order)

1. **Repo foundation**
   - `ansible.cfg`, an `inventory/` holding every host and address from the target doc, an extended `.gitignore`;
   - a `Makefile` with offline checks (`ansible-inventory --graph`, `--syntax-check`, yamllint,
     ansible-lint, unit tests, secret scan), pinned `requirements-dev.txt`;
   - `README.md` and `AGENTS.md`;
   - a GitHub Actions workflow that runs the same offline checks (no secrets, no deploy).
2. **Proxmox base.** Confirm or create the 3-node cluster (one-time steps may be a documented
   manual runbook rather than Ansible). Ansible for host basics: package repositories (ask me:
   no-subscription vs enterprise), NTP, basic packages, storage facts. Read-only verify first.
3. **Remote access.** A `tailscale_router` role for `pve02` and `pve03`: identical `/32` routes
   generated from the inventory, IP forwarding, one router per run, with my manual route approval in
   the Tailscale admin console in between. Then split DNS (after step 5).
4. **Guest provisioning with OpenTofu** (`bpg/proxmox`). The Debian 13 generic cloud image must be
   available on each node's local storage (no cross-node cloning). Cloud-Init sets static IP,
   hostname, user `john`, password (from the secret store) and installs `qemu-guest-agent`. VM/CT IDs
   and sizes come from the target table. Start with one guest, review the plan output together, then
   add the rest. Decide with me how OpenTofu authenticates to Proxmox (an API token for a dedicated
   user is preferred) and where state lives.
5. **DNS.** AdGuard Home on `dns01`/`dns02` (unprivileged LXCs), with the wildcard
   `*.lab.krikri.dev` → `192.168.0.30` and upstream resolvers (ask me). Verify both resolve
   independently. Then I change the router's DHCP DNS to `.31`/`.32`, and you add Tailscale split
   DNS.
6. **Docker hosts and Swarm.** A `docker_host` role (Engine + Compose plugin from Docker's repo,
   pinned), Swarm init/join as a separate bootstrap step, 3 managers.
7. **Swarm stacks.** Traefik (2 replicas, HTTP entrypoint on ingress `:18080`, no ACME, trusts
   forwarded headers only from `.33`/`.34`), Portainer CE + agent, adguardhome-sync
   (`dns01` → `dns02`). One deploy path from the repo; pinned image tags.
8. **Edge pair.** Roles split by concern:
   - `edge_install`: packages; Keepalived masked;
   - `edge_tls`: Certbot + Cloudflare DNS-01, token from Vault, deploy hook, Let's Encrypt
     **staging / `--dry-run` first**. The production limit is 5 certificates per identical name
     set per week, and both edges count;
   - `edge_config`: HAProxy and Keepalived templates validated with `haproxy -c` / `keepalived -t`
     before install, a loopback health endpoint for the track script, VRRP behind an explicit
     opt-in variable that defaults to false;
   - `edge_verify`: read-only; exactly one VIP owner, cert expiry, routes.

   Test each edge directly on its own IP before enabling VRRP. Enable VRRP on `edge01`, verify,
   then `edge02`, then do a failover drill with my approval.
9. **Home Assistant.** HAOS VM via OpenTofu (ask me whether USB devices such as a Zigbee/Z-Wave
   stick need passing through; that ties HAOS to one node). HAProxy route direct to `.20:8123`.
   Configure `use_x_forwarded_for` and `trusted_proxies` (`.33`, `.34`) in HA **before** testing
   through the edge.
10. **Backups and recovery.** vzdump jobs to the NAS (ask me about its status), HA backups, AdGuard,
    Portainer data and encrypted secrets, then a restore test for each class. Runbooks.

## Technical notes to save you time

- Ansible must run from the repo root so `ansible.cfg` (inventory, `roles_path`) is picked up.
- Password SSH with Ansible needs `sshpass` and `--ask-pass` / `--ask-become-pass`. Keep
  `host_key_checking` on: confirm each new guest's SSH host key fingerprint from the Proxmox
  console before the first connection.
- `failed_when: false` / `ignore_errors` hide real failures. Use them only with an explicit
  assertion afterwards.
- Keepalived 2.x refuses track scripts unless `global_defs` has `enable_script_security` (and
  `script_user`) and the script is root-owned and not writable by others. `keepalived -t` returns
  non-zero for this, so treat any non-zero exit as a failure.
- `keepalived -t` and `haproxy -c` can be run offline against rendered templates. If the binaries
  aren't installed, document the gap rather than skipping silently. Debian/Ubuntu `.deb`s can be
  extracted without root (`apt-get download` + `dpkg-deb -x`) into `~/.cache`. `keepalived -t` also
  needs `keepalived.config-opts` next to the binary, a real interface name, and, when not root,
  `script_user` set to the current user.
- `curl -I` sends HEAD, and Home Assistant answers HEAD on `/` with 405. Test HA with GET and a real
  browser login.
- Swarm's ingress routing mesh source-NATs traffic. That's why HA is proxied directly from HAProxy
  and Traefik's trusted-proxy list contains only the edge IPs.
- Proxmox clustering doesn't make single-instance guests highly available here (local storage).
  Don't present it as failover.
- A Proxmox VIP problem can come from the guest NIC's `firewall=1` + IP filter. Check before
  enabling VRRP.
- Debian cloud images use a DHCP client ID based on DUID, not MAC. Irrelevant here because guests
  use static addresses, but don't switch them to DHCP reservations without accounting for it.

## Start here

1. Read `docs/architecture-target.md`.
2. Ask me the open questions you need answered before milestone 1 (batch them), at least:
   - whether the Proxmox nodes are already clustered, and their PVE version and storage names;
   - whether I have a Tailscale account/tailnet;
   - whether I have a Cloudflare API token for DNS-01 (scope: Zone DNS Edit on `krikri.dev`);
   - NAS availability;
   - Home Assistant USB devices;
   - preferred upstream DNS.
3. Propose the milestone 1 plan (files and purpose). Don't create files until I approve it.
