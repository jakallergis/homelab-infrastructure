# Runbook: Swarm stacks

The stack files in `stacks/` define Traefik, Portainer and adguardhome-sync. `playbooks/stacks.yml`
is the only way they reach the Swarm. Portainer shows these stacks as "limited" and does not own
them: change them in Git, never in its UI. Live runs need approval (see `AGENTS.md`). Run all
commands from the repo root.

```sh
export PATH=$HOME/.cache/homelab-infrastructure/venv/bin:$PATH
```

## Current state

- All three stacks are deployed. On 2026-11-13, `verify.yml` passed and `docker service ls` showed
  every service with all its replicas. The Portainer login and the first sync to `dns02` are not
  checked yet.

## The stacks

| Stack | Runs | Reached at |
|---|---|---|
| `traefik` | 2 replicas, at most 1 per node, managers only | Port `18080` in host mode, only on the 2 nodes that run it. `/ping` answers 200 |
| `portainer` | Server on `docker01` (data in volume `portainer_data`), agent on every node | `portainer.lab.krikri.dev` through Traefik |
| `adguardhome-sync` | 1 replica | Nothing. It copies `dns01` → `dns02` every 10 minutes |

Versions are the image tags in each file. `make test` checks each file with `docker stack config`
(Docker's own parser, version 29.9.3), checks that each image has a version tag, and checks that
Traefik trusts only the edge IPs from the inventory.

Not tested offline: Traefik's command-line flags. They come from the Traefik documentation. The
first deploy and `verify.yml` test them.

## Passwords

`secrets/stacks.yml` (Vault) holds `portainer_admin_password` and `adguard_admin_password`. The
playbook creates a Swarm secret with the same name from each one, only if it does not exist.

- `adguard_admin_password` must be the password whose hash is in `secrets/dns.yml`. AdGuard Home
  blocks a client for 15 minutes after 5 failed logins, so a wrong value blocks the sync.
- Portainer reads its password only at the first start. After that, the UI owns it.

Create the file (it opens an editor; write the two lines `name: value`):

```sh
ansible-vault create --vault-password-file "$HOMELAB_PRIVATE_DIR/vault-pass" secrets/stacks.yml
```

### Change a password

A Swarm secret cannot change, and Swarm does not delete a secret that a service uses.

1. Change the value with `ansible-vault edit`.
2. For the AdGuard password: `sudo docker stack rm adguardhome-sync`, then
   `sudo docker secret rm adguard_admin_password` on a manager.
3. Run the deploy. It creates the secret again and deploys the missing stack.

## Deploy

```sh
ansible-playbook playbooks/stacks.yml --check --diff --ask-pass --ask-become-pass --vault-password-file "$HOMELAB_PRIVATE_DIR/vault-pass"
ansible-playbook playbooks/stacks.yml --diff --ask-pass --ask-become-pass --vault-password-file "$HOMELAB_PRIVATE_DIR/vault-pass"
ansible-playbook playbooks/verify.yml --limit swarm_managers --ask-pass --ask-become-pass
```

A stack is deployed only if its file changed or the stack does not exist. After a failed deploy,
add `-e stacks_force=true`: the file on the host is already new, so the next run would skip it.

## Open Portainer before the edge exists

Until milestone 8, Portainer is plain HTTP on port `18080`, and its name points to `.30`, which
does not answer yet. Editing `/etc/hosts` on the Mac needs admin rights, so tell only one browser
where the name is:

1. Find a node that runs Traefik. Two of `.21`, `.22` and `.23` answer `OK`:
   `curl http://192.168.0.21:18080/ping`
2. Check the route from the terminal. Use a node that answered. The page title must be Portainer:
   `curl -s --resolve portainer.lab.krikri.dev:18080:192.168.0.21 http://portainer.lab.krikri.dev:18080/ | grep -i '<title>'`
3. Start a separate Chrome with a resolver rule. It needs no admin rights and does not change your
   normal Chrome:

   ```sh
   open -na "Google Chrome" --args --user-data-dir="$HOME/.chrome-lab" \
     --host-resolver-rules="MAP portainer.lab.krikri.dev 192.168.0.21"
   ```

4. In that window, open `http://portainer.lab.krikri.dev:18080` and log in as `admin`.

If Traefik moves to another node, use that node's IP. When the edge works, use the normal browser.

## The Docker socket

Traefik and the Portainer agent mount `/var/run/docker.sock`. Anything that controls that socket
controls the node as root, and on a manager it controls the whole Swarm. `:ro` does not limit
this: it protects the file, not the API. A bug in Traefik that lets a request run code is the main
path. Traefik is reached only from the LAN and the tailnet, never from the internet. A socket
proxy that allows only read requests would limit Traefik. It is not used now.

## Check health

```sh
ansible-playbook playbooks/verify.yml --limit swarm_managers --ask-pass --ask-become-pass
ssh -t john@192.168.0.21 'sudo docker service ls'
```

## Remove the stacks

On a manager. This keeps the volume `portainer_data` and the secrets. `adguardhome-sync` only
copied `dns01`'s settings to `dns02`, so removing it undoes nothing on `dns02`.

```sh
ssh -t john@192.168.0.21 'sudo docker stack rm adguardhome-sync portainer traefik'
```
