"""Check the inventory against the rules in docs/architecture-target.md."""

import json
import re
import subprocess
from ipaddress import ip_address
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
INVENTORY = yaml.safe_load((ROOT / "inventory/hosts.yml").read_text())
GROUP_VARS = yaml.safe_load((ROOT / "inventory/group_vars/all.yml").read_text())


def walk(group):
    """Yield (name, vars) for each host in a group and in its child groups."""
    for name, host_vars in (group.get("hosts") or {}).items():
        yield name, host_vars or {}
    for child in (group.get("children") or {}).values():
        yield from walk(child)


def find_group(name, group=INVENTORY["all"]):
    children = group.get("children") or {}
    if name in children:
        return children[name]
    for child in children.values():
        found = find_group(name, child)
        if found is not None:
            return found
    return None


def host_names(group_name):
    return [name for name, _ in walk(find_group(group_name))]


# A host can be in two groups (pve02 is also a Tailscale router), so merge its vars.
HOSTS = {}
for host, values in walk(INVENTORY["all"]):
    HOSTS.setdefault(host, {}).update(values)

GUESTS = {name: values for name, values in HOSTS.items() if name not in host_names("proxmox")}
VIP = GROUP_VARS["edge_vip"]

DESIGN = (ROOT / "docs/architecture-target.md").read_text()
# Table rows like: | `.21` | `docker01` | VM (Debian 13) | pve01 | 121 | 6 vCPU, 8 GB, 80 GB | ...
DESIGN_GUESTS = {
    name: {
        "kind": kind,
        "pve_node": node,
        "vmid": int(vmid),
        "cores": int(cores),
        "memory_mb": int(memory) * (1024 if memory_unit == "GB" else 1),
        "disk_gb": int(disk),
    }
    for name, kind, node, vmid, cores, memory, memory_unit, disk in re.findall(
        r"^\| `[^`]+` \| `(\w+)` \| ([^|]+?) \| (pve\d+) \| (\d+) \| "
        r"(\d+) [^,]+, (\d+) (GB|MB), (\d+) GB \|",
        DESIGN,
        re.MULTILINE,
    )
}
LOCAL_LVM_GIB = {node: int(size) for size, node in re.findall(r"(\d+) GiB on `(pve\d+)`", DESIGN)}

# The inventory "type" for each kind in the design table. OpenTofu creates the guests of type debian_vm.
TYPES = {"debian_vm": "VM (Debian 13)"}
SIZE_KEYS = ["cores", "memory_mb", "disk_gb"]


def address(host):
    return HOSTS[host]["ansible_host"]


def test_every_host_has_an_address():
    assert [name for name, values in HOSTS.items() if "ansible_host" not in values] == []


def test_addresses_are_unique():
    addresses = [address(name) for name in HOSTS]
    assert len(addresses) == len(set(addresses))


def test_addresses_are_in_the_homelab_range():
    first, last = ip_address("192.168.0.2"), ip_address("192.168.0.149")
    assert [name for name in HOSTS if not first <= ip_address(address(name)) <= last] == []


def test_floating_ip_is_not_assigned_to_a_host():
    assert VIP not in [address(name) for name in HOSTS]


def test_total_address_count():
    assert len(HOSTS) + 1 == 12  # 11 hosts plus the floating IP


def test_guest_ids_follow_the_address():
    wrong = [
        name
        for name, values in GUESTS.items()
        if values.get("vmid") != 100 + int(values["ansible_host"].rsplit(".", 1)[1])
    ]
    assert wrong == []


def test_guests_run_on_a_known_node():
    nodes = host_names("proxmox")
    assert [name for name, values in GUESTS.items() if values.get("pve_node") not in nodes] == []


def test_exactly_two_edge_nodes():
    assert len(host_names("edge")) == 2


def test_exactly_two_tailscale_routers_on_proxmox_hosts():
    routers = host_names("tailscale_routers")
    assert len(routers) == 2
    assert set(routers) <= set(host_names("proxmox"))


@pytest.mark.parametrize("group", ["edge", "dns", "swarm_managers"])
def test_redundant_members_are_on_separate_nodes(group):
    nodes = [HOSTS[name]["pve_node"] for name in host_names(group)]
    assert len(nodes) == len(set(nodes))


def test_every_guest_is_in_the_design_table():
    assert set(DESIGN_GUESTS) == set(GUESTS)


def test_inventory_matches_the_design():
    """Node and ID always. Size only once the inventory gives one, which makes OpenTofu create the guest."""
    wrong = [
        f"{name}: {key}"
        for name, values in GUESTS.items()
        for key, expected in DESIGN_GUESTS[name].items()
        if key in values and values[key] != expected
    ]
    assert wrong == []


def test_guest_types_match_the_design():
    wrong = [
        name
        for name, values in GUESTS.items()
        if "type" in values and TYPES.get(values["type"]) != DESIGN_GUESTS[name]["kind"]
    ]
    assert wrong == []


def test_debian_vms_have_a_size():
    vms = [name for name, values in GUESTS.items() if values.get("type") == "debian_vm"]
    assert [name for name in vms if not all(key in GUESTS[name] for key in SIZE_KEYS)] == []


def test_planned_disks_fit_in_local_lvm():
    assert set(LOCAL_LVM_GIB) == set(host_names("proxmox"))
    for node, pool in LOCAL_LVM_GIB.items():
        planned = sum(guest["disk_gb"] for guest in DESIGN_GUESTS.values() if guest["pve_node"] == node)
        assert planned <= pool, f"{node}: {planned} GB of disks on a {pool} GiB pool"


def rendered_routes(host):
    """Render the real route list with Ansible. The debug module does not connect to the host."""
    output = subprocess.run(
        ["ansible", host, "-c", "local", "-m", "debug", "-a", "var=tailscale_router_routes"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return json.loads(output.split("=>", 1)[1])["tailscale_router_routes"]


def test_routers_advertise_identical_routes():
    assert rendered_routes("pve02") == rendered_routes("pve03")


def test_routes_are_a_32_for_each_homelab_address():
    expected = {f"{address(name)}/32" for name in HOSTS} | {f"{VIP}/32"}
    routes = rendered_routes("pve02")
    assert len(routes) == 12
    assert set(routes) == expected
