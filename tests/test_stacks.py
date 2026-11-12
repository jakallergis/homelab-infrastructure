"""Check the Swarm stack files with Docker's own parser and against the inventory, without the LAN."""

import hashlib
import platform
import subprocess
import tarfile
import urllib.request
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path.home() / ".cache/homelab-infrastructure/docker-cli"
INVENTORY = yaml.safe_load((ROOT / "inventory/hosts.yml").read_text())
STACKS = sorted((ROOT / "stacks").glob("*.yml"))
# The static CLI of the version the hosts run. The sha256 values are of the files on
# download.docker.com/linux/static/stable/, taken when the version was pinned.
CLI_VERSION = "29.9.3"
CLI_SHA256 = {
    "aarch64": "1b27fd739378ef938401e81ce5afb73b7ad7432d4f598814a9ff5f826bb464d2",
    "x86_64": "3fb5d1f13014c18cc54945bc177c58a9056a482dada031e17d12cf2e6922c973",
}


@pytest.fixture(scope="module")
def docker_cli():
    """Return the path of the Docker CLI. Download it once, and check its sha256."""
    arch = platform.machine()
    binary = CACHE / CLI_VERSION / arch / "docker/docker"
    if not binary.exists():
        url = f"https://download.docker.com/linux/static/stable/{arch}/docker-{CLI_VERSION}.tgz"
        data = urllib.request.urlopen(url, timeout=120).read()
        assert hashlib.sha256(data).hexdigest() == CLI_SHA256[arch]
        archive = binary.parent.parent / "docker.tgz"
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(data)
        with tarfile.open(archive) as tar:
            tar.extract("docker/docker", binary.parent.parent, filter="data")
    return binary


@pytest.mark.parametrize("stack", STACKS, ids=lambda path: path.stem)
def test_docker_accepts_the_stack(docker_cli, stack, tmp_path):
    """docker stack config reads the file as Swarm does and stops on unknown keys. It needs no daemon."""
    result = subprocess.run(
        [docker_cli, "stack", "config", "--compose-file", stack],
        capture_output=True,
        text=True,
        env={"DOCKER_HOST": "unix:///nonexistent", "DOCKER_CONFIG": str(tmp_path)},
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("stack", STACKS, ids=lambda path: path.stem)
def test_images_have_a_version(stack):
    for service in yaml.safe_load(stack.read_text())["services"].values():
        name, _, tag = service["image"].rpartition(":")
        assert name and tag not in ("", "latest") and any(c.isdigit() for c in tag), service["image"]


def test_traefik_trusts_only_the_edge_nodes():
    edge = INVENTORY["all"]["children"]["debian_guests"]["children"]["edge"]["hosts"]
    command = yaml.safe_load((ROOT / "stacks/traefik.yml").read_text())["services"]["traefik"]["command"]
    trusted = [arg.split("=", 1)[1] for arg in command if arg.startswith("--entryPoints.web.forwardedHeaders.trustedIPs=")]
    assert trusted == [",".join(sorted(host["ansible_host"] for host in edge.values()))]
