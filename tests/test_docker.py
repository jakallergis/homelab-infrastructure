"""Check the pinned Docker packages, the signing key and the daemon settings, without the LAN."""

import hashlib
import json
import urllib.request
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
DOCKER = yaml.safe_load((ROOT / "inventory/group_vars/swarm_managers.yml").read_text())
# The suite and architecture of roles/docker_host/files/docker.sources.
REPOSITORY = "https://download.docker.com/linux/debian"
INDEX = f"{REPOSITORY}/dists/trixie/stable/binary-amd64/Packages"


@pytest.fixture(scope="module")
def published():
    """Return {package: set of versions} from Docker's package index."""
    text = urllib.request.urlopen(INDEX, timeout=60).read().decode()
    versions = {}
    for stanza in text.split("\n\n"):
        fields = dict(line.split(": ", 1) for line in stanza.splitlines() if ": " in line and not line[0].isspace())
        if "Package" in fields:
            versions.setdefault(fields["Package"], set()).add(fields["Version"])
    return versions


@pytest.mark.parametrize("package", DOCKER["docker_packages"])
def test_pinned_version_exists(published, package):
    assert DOCKER["docker_packages"][package] in published.get(package, set())


def test_signing_key_checksum():
    key = urllib.request.urlopen(f"{REPOSITORY}/gpg", timeout=60).read()
    assert hashlib.sha256(key).hexdigest() == DOCKER["docker_key_sha256"]


def test_sources_match_the_index():
    sources = (ROOT / "roles/docker_host/files/docker.sources").read_text()
    assert f"URIs: {REPOSITORY}\n" in sources
    assert "Suites: trixie\n" in sources
    assert "Architectures: amd64\n" in sources


def test_daemon_settings_are_json():
    assert json.loads((ROOT / "roles/docker_host/files/daemon.json").read_text()) == {"log-driver": "local"}
