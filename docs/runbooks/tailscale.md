# Runbook: Tailscale routers

`pve02` and `pve03` are redundant subnet routers. They advertise identical routes: a `/32` for each
homelab address, made from the inventory. These nodes are the remote access path, so change one
router per run and do this work from the LAN. Live runs need approval (see `AGENTS.md`).

```sh
export PATH=$HOME/.cache/homelab-infrastructure/venv/bin:$PATH
```

## Current state

- Tailnet: `tail8b0eff.ts.net`. Both routers are logged in, with key expiry disabled.
- Both routers have `accept-dns` and `accept-routes` off, so their DNS and LAN traffic stay local.
- Failover drill passed: with `tailscaled` stopped on `pve02`, a device off the LAN reached `pve01`
  through `pve03`.
- Split DNS (set by hand in the admin console, DNS page, since 2026-11-11): `lab.krikri.dev` goes to
  `192.168.0.31` and `192.168.0.32`, with "Restrict to domain" on. No global nameservers, and
  "Override DNS servers" is off. Verified off the LAN: `test.lab.krikri.dev` resolved to
  `192.168.0.30`, and the AdGuard query log showed the query from `192.168.0.13` (the routers
  rewrite the source address). To undo it, delete the two nameserver entries.

## Check health

Read-only. Expect `failed=0` and `changed=0` on all nodes.

```sh
ansible-playbook playbooks/verify.yml --ask-pass
```

This does not prove that the routes are approved. To prove that, use a device on the tailnet but off
the LAN, and open `https://192.168.0.11:8006`.

## Change a router

The role stops if the run selects both routers. Always use `--limit`, and finish one router first.

```sh
ansible-playbook playbooks/site.yml --limit pve02 --check --diff --ask-pass
ansible-playbook playbooks/site.yml --limit pve02 --diff --ask-pass
ansible-playbook playbooks/verify.yml --ask-pass
```

Do the same for `pve03` only after these pass.

## Add a homelab address

1. Add the host to `inventory/hosts.yml`. The route list changes by itself.
2. Run the role on one router, then approve the new route in the admin console.
3. Verify, then do the same on the other router.

## Log in again

Do not run `tailscale up` or `tailscale login` by hand: without all flags, they reset the routes and
`accept-dns`. Run the role with `--limit`. It starts the login, shows the URL and pauses. Log in,
approve the routes, disable key expiry, and press Enter.

## Stop a router for maintenance

On one router only, run `systemctl stop tailscaled`. The other router takes over (the time was not
measured). `systemctl start tailscaled` brings it back, logged in and with the same settings.

## Remove Tailscale from a router

Run on the affected node:

1. Run `tailscale down`, then `apt remove tailscale`.
2. Delete `/etc/apt/sources.list.d/tailscale.sources`, `/usr/share/keyrings/tailscale-archive-keyring.gpg`
   and `/etc/sysctl.d/99-tailscale.conf`.
3. Run `sysctl -w net.ipv4.ip_forward=0`.
4. Remove the device from the admin console.
