# Runbook: Docker hosts and Swarm

`docker01` (`.21`), `docker02` (`.22`) and `docker03` (`.23`) run Docker Engine from Docker's apt
repository and form a Swarm with 3 managers. The Swarm keeps working when any one of them is down.
Live runs need approval (see `AGENTS.md`). Run all commands from the repo root.

```sh
export PATH=$HOME/.cache/homelab-infrastructure/venv/bin:$PATH
```

## Current state

- `docker01`: Docker installed on 2026-11-12. `hello-world` ran, and a second check run shows
  `changed=0`.
- `docker02`, `docker03`: not installed yet. The Swarm does not exist yet.

## How it is built

| Item | Where |
|---|---|
| Package versions and the key checksum | `inventory/group_vars/swarm_managers.yml` |
| Repository | `/etc/apt/sources.list.d/docker.sources`, key `/usr/share/keyrings/docker.asc` |
| Version lock | The 4 packages are on `apt` hold. Only the role changes them, from the pins |
| Daemon settings | `/etc/docker/daemon.json`: the `local` log driver, which rotates container logs |
| Swarm | Made once by `playbooks/swarm_bootstrap.yml`. Autolock is off, so a reboot needs no unlock key |
| Docker commands | Through `sudo`. `john` is not in the `docker` group, because that group gives root without a password |

The Swarm uses TCP 2377 (managers), TCP and UDP 7946 (nodes) and UDP 4789 (overlay traffic). The
Proxmox firewall is off on the guest NICs, and the guests have no firewall. Overlay networks use
Docker's default pool `10.0.0.0/8`, which does not overlap the LAN or Tailscale (`100.64.0.0/10`).

The join token lets a machine join as a manager. The playbook reads it with `no_log` and never
writes it to a file. To see it by hand: `sudo docker swarm join-token manager` on a manager. To
replace it: `sudo docker swarm join-token --rotate manager`.

## Install Docker

One host at a time. Do the next host only after the checks pass.

```sh
ansible-playbook playbooks/site.yml --limit docker01 --check --diff --ask-pass --ask-become-pass
ansible-playbook playbooks/site.yml --limit docker01 --diff --ask-pass --ask-become-pass
ssh john@192.168.0.21 'sudo docker run --rm hello-world'
```

On a new host, check mode adds the key and repository on paper and skips the rest: the packages are
not in the index until the repository is really added.

## Create the Swarm

After Docker is on all three hosts. The playbook stops if the states are mixed in a way it does not
expect (for example, `docker01` outside a Swarm that the others are in).

```sh
ansible-playbook playbooks/swarm_bootstrap.yml --check --ask-pass --ask-become-pass
ansible-playbook playbooks/swarm_bootstrap.yml --ask-pass --ask-become-pass
ansible-playbook playbooks/verify.yml --limit swarm_managers --ask-pass --ask-become-pass
```

## Check health

Read-only. It checks the Docker version against the pin, that each node is a manager, that all 3
nodes are `Ready`, and that there is exactly one `Leader`.

```sh
ansible-playbook playbooks/verify.yml --limit swarm_managers --ask-pass --ask-become-pass
ssh -t john@192.168.0.21 'sudo docker node ls'
```

## Upgrade Docker

1. Copy the new versions from Docker's index into `inventory/group_vars/swarm_managers.yml`.
2. Run `make test`. It fails if a version does not exist in the repository.
3. Apply to one host, verify, then the next. A restart stops the containers of that node, and Swarm
   starts them again on the other nodes.

## Remove the Swarm and Docker

This deletes every service, network and secret in the Swarm. It needs approval each time.

1. On each host: `sudo docker swarm leave --force`.
2. On each host: `sudo apt-mark unhold docker-ce docker-ce-cli containerd.io docker-compose-plugin`,
   then `sudo apt purge` the same packages.
3. Delete `/etc/apt/sources.list.d/docker.sources`, `/usr/share/keyrings/docker.asc` and
   `/var/lib/docker`.
