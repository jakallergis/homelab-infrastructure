# Architecture: target

A small, recoverable homelab built entirely from this Git repository. Every host and service has a
single owner of its desired state, and any guest can be rebuilt from code plus backups.

## Physical layer

Three Proxmox VE nodes on the same LAN, joined into one 3-node cluster. Each node uses its own
local NVMe storage. There is **no shared storage**: guests don't live-migrate, and Proxmox
clustering gives a single management plane and quorum, not automatic application failover.

| Node | IP | Hardware |
|---|---|---|
| `pve01` | `192.168.0.11` | Dell OptiPlex 3080 Micro, i5-10500T, 32 GB RAM, 1 TB NVMe |
| `pve02` | `192.168.0.12` | Dell OptiPlex 3080 Micro, i3-10100T, 32 GB RAM, 256 GB NVMe |
| `pve03` | `192.168.0.13` | Dell OptiPlex 3080 Micro, i3-10100T, 16 GB RAM, 128 GB NVMe |

All nodes run PVE 9.2.2 and are joined in the cluster `homelab`. Each node has the storages `local`
(directory: images and templates) and `local-lvm` (LVM-thin: guest disks). The `local-lvm` pools are
794 GiB on `pve01`, 141 GiB on `pve02` and 54 GiB on `pve03`.

## Network

- LAN `192.168.0.0/24`. Router: TP-Link Archer C6. It provides internet, the default gateway
  (`192.168.0.1`) and DHCP for ordinary clients.
- The router's DHCP pool is `192.168.0.150`–`.254`. **`.2`–`.149` are reserved for the homelab.**
  Homelab guests use **static addresses set through Cloud-Init** (or the LXC network config), so
  their addresses don't depend on MAC addresses or DHCP reservations.
- Clients get DNS from the router's DHCP, which advertises `dns01` and `dns02` (the router's DNS
  setting changes only after both resolvers are working).

### Address and ID plan

VM/CT ID = 100 + last octet of the guest's IP (e.g. `docker01` at `.21` → ID 121).

| Address | Name | Type | Node | ID | Initial size | Purpose |
|---|---|---|---|---|---|---|
| `.11`–`.13` | `pve01`–`pve03` | Proxmox hosts | — | — | — | Hypervisors; `pve02` and `pve03` also run Tailscale |
| `.20` | `homeassistant` | VM (HAOS) | pve02 | 120 | 2 vCPU, 4 GB, 64 GB | Home Assistant OS |
| `.21` | `docker01` | VM (Debian 13) | pve01 | 121 | 6 vCPU, 8 GB, 80 GB | Swarm manager |
| `.22` | `docker02` | VM (Debian 13) | pve02 | 122 | 4 vCPU, 8 GB, 40 GB | Swarm manager |
| `.23` | `docker03` | VM (Debian 13) | pve03 | 123 | 4 vCPU, 4 GB, 40 GB | Swarm manager |
| `.30` | *floating IP* | VRRP VIP | edge01/edge02 | — | — | HTTPS entry point for `*.lab.krikri.dev` |
| `.31` | `dns01` | LXC (Debian 13, unprivileged) | pve03 | 131 | 1 core, 512 MB, 8 GB | AdGuard Home, primary |
| `.32` | `dns02` | LXC (Debian 13, unprivileged) | pve02 | 132 | 1 core, 512 MB, 8 GB | AdGuard Home, replica |
| `.33` | `edge01` | VM (Debian 13) | pve01 | 133 | 1 vCPU, 1 GB, 16 GB | HAProxy + Keepalived + Certbot |
| `.34` | `edge02` | VM (Debian 13) | pve02 | 134 | 1 vCPU, 1 GB, 16 GB | HAProxy + Keepalived + Certbot |

**Failure-domain rule:** every redundant pair (Swarm managers, DNS, edge, Tailscale routers) is
spread so that losing any one node leaves at least one member of each pair running.

## Services and responsibilities

### Edge pair: `edge01` / `edge02`
- Full Debian 13 VMs (not LXCs, because they manage a floating IP with VRRP). HAProxy, Keepalived
  and Certbot are **systemd host services, not containers**.
- **Exactly two** edge nodes. Keepalived uses unicast VRRP between `.33` and `.34` to hold the
  floating IP `.30`. One node is active and the other is standby; there is never more than one
  owner. Keepalived uses `enable_script_security` with a root-owned track script that checks
  local HAProxy health through a loopback-only health endpoint.
- HAProxy: `:80` redirects to HTTPS. `:443` terminates TLS with a publicly trusted wildcard
  certificate for `*.lab.krikri.dev` and routes by host name:
  - `ha.lab.krikri.dev` → **directly** to Home Assistant `192.168.0.20:8123`, never through
    Traefik or the Swarm ingress mesh (the mesh source-NATs connections, which breaks HA's
    client-IP-bound login sessions). WebSockets are supported, and `X-Forwarded-For` /
    `X-Forwarded-Proto` are set consistently.
  - everything else → Traefik through the Swarm ingress port `18080` on `docker01`–`03`, with
    health checks.
- Each edge node obtains and renews **its own** certificate with Certbot using Let's Encrypt
  DNS-01 via the Cloudflare API (`krikri.dev` zone). Credentials are a scoped Cloudflare API token
  (DNS edit on `krikri.dev` only), injected from the secret store. A renewal deploy hook builds
  the HAProxy PEM and reloads HAProxy only if `haproxy -c` passes.
- Each node is reachable and testable on its own address (`curl --resolve name:443:192.168.0.33`).

### Docker Swarm: `docker01` / `docker02` / `docker03`
- Debian 13, Docker Engine + Compose plugin, a 3-manager Swarm. No edge, TLS or VRRP services on
  these hosts.
- Swarm stacks defined in Git, deployed by one single path (CLI from the repo, never also edited
  in a UI):
  - **Traefik**: 2 replicas on different nodes, HTTP-only entrypoint published on ingress port
    `18080`, overlay network `traefik-public`. No ACME in Traefik (TLS is at HAProxy). It trusts
    forwarded headers only from `.33` and `.34`.
  - **Portainer CE**: server plus a global agent. Server data is a local volume on one node, so
    it is a single-instance app. Portainer is for viewing and operations; it doesn't own stack
    definitions.
  - **adguardhome-sync**: replicates configuration from `dns01` to `dns02`.
- Image versions are pinned. Secrets are Swarm secrets created from the secret store and never
  committed.

### DNS: `dns01` / `dns02`
- Two independent AdGuard Home instances in unprivileged LXCs. `dns01` is the configuration source
  and `dns02` receives it through adguardhome-sync.
- Both answer `*.lab.krikri.dev` → `192.168.0.30`, and either one alone is enough for full name
  resolution. Never pair them with a public resolver that doesn't know the internal names.

### Home Assistant: `homeassistant`
- One HAOS VM, reached at `https://ha.lab.krikri.dev` through the edge pair, and directly at
  `http://192.168.0.20:8123` for recovery.
- HA's `http:` config enables `use_x_forwarded_for` with `trusted_proxies` = `192.168.0.33`,
  `192.168.0.34`.
- HAOS can't be configured by Ansible. Its VM is provisioned from code; its configuration lives in
  HA backups.

### Remote access: Tailscale
- Tailscale runs on the Proxmox hosts `pve02` and `pve03` as **redundant subnet routers** that
  advertise **identical** route lists: a `/32` for every homelab address in the table above,
  generated from the inventory. No other device needs Tailscale for homelab access.
- Tailscale split DNS sends `lab.krikri.dev` to `192.168.0.31` and `192.168.0.32`.
- Nothing is exposed publicly: no port forwards, no public A records for `lab.krikri.dev`, no
  Cloudflare proxying of internal services. Cloudflare is used only for DNS-01 validation.

## User-facing endpoints

| Endpoint | Path |
|---|---|
| `https://ha.lab.krikri.dev` | DNS → `.30` → HAProxy → HAOS `.20:8123` |
| `https://portainer.lab.krikri.dev` | DNS → `.30` → HAProxy → Traefik `:18080` → Portainer |
| `https://<app>.lab.krikri.dev` | DNS → `.30` → HAProxy → Traefik → Swarm service |
| `https://192.168.0.11:8006` (…`.12`, `.13`) | Proxmox UI, direct over LAN or Tailscale |
| SSH to every guest | Direct by IP over LAN or Tailscale |
| DNS `.31`, `.32` | Direct |

## Access and accounts

- Debian guests: user `john`, password-based SSH, `sudo`. Proxmox hosts: `root`, password SSH.
  This is a deliberate choice and stays unless the user decides otherwise. No plaintext
  credentials in Git; Cloud-Init password hashes are also treated as secrets.
- Guest OS: the official Debian 13 `generic` cloud image with Cloud-Init and `qemu-guest-agent`.

## Ownership of desired state

| Layer | Owner | Notes |
|---|---|---|
| Hosts, addresses, IDs | `inventory/` | One source; other layers read from it |
| Proxmox guests (VMs, LXCs, cloud images, Cloud-Init) | **OpenTofu** (`bpg/proxmox` provider) | Plans reviewed before apply; state kept out of Git or encrypted; `prevent_destroy` on stateful guests |
| Proxmox host OS, cluster settings, Tailscale | **Ansible** | `tailscale_router` role changes one router per run |
| Debian guest OS and host services | **Ansible** | Roles split into install / TLS & secrets / configuration / read-only verification |
| Swarm stacks and their configs | **Git stack files**, one deploy path | Pinned images, versioned Swarm configs, secrets outside Git |
| AdGuard configuration | Git (starting config) + web UI on `dns01` + sync to `dns02` | Ansible writes the config only on a new server; after that the UI owns it |
| Secrets | `ansible-vault` (or equivalent) | Vault password never in Git; Ansible tasks touching secrets use `no_log` |
| CI | GitHub Actions | Lint, syntax, render and unit tests only; no access to the LAN or the tailnet |
| Data | Backups (below) | Git and DNS sync are not backups |

**Entry points:** `playbooks/site.yml` (converge everything), `playbooks/bootstrap.yml` (first
preparation of a new machine), `playbooks/verify.yml` (strictly read-only health checks). Use
`--limit` for one-host changes. Redundant pairs are changed one node per run (`serial: 1`) with a
check after each.

**Engineering standards:** idempotent roles; modules over shell; templates generated from inventory;
candidate configs validated before they replace live ones (`haproxy -c`, `keepalived -t`,
`validate:`); backups of replaced files; handlers only fire on change; offline tests run without
the LAN.

## Backups and recovery

- Proxmox `vzdump` backups of all guests to a NAS (UGREEN, not available yet), plus Home
  Assistant's native backups, AdGuard configuration, Portainer data, and encrypted copies of
  TLS/secret material.
- At least one restore test for each class (VM, LXC, application data, secrets) before the
  platform counts as done.

## Definition of done

1. Every guest in the address table is provisioned by OpenTofu and configured by Ansible or stack
   files from this repo. A second `site.yml` run reports no changes.
2. `ha.` and `portainer.lab.krikri.dev` work from the LAN and over Tailscale with trusted TLS, and
   Home Assistant login is reliable through the edge.
3. Losing any single edge node, DNS server, Tailscale router or Proxmox node keeps HTTPS ingress,
   name resolution and remote access working. Single-instance apps (HAOS, Portainer) may be down
   until restored.
4. Certificates renew automatically and reload HAProxy, and no public ingress exists.
5. `verify.yml` reports exactly one owner of `.30` and healthy services.
6. CI passes, runbooks exist, and backups have a verified restore.

## Out of scope for now

Media servers, cameras/NVR, monitoring stacks, shared or distributed storage, Kubernetes, and
automatic Home Assistant failover. These come after the platform above is reproducible.
