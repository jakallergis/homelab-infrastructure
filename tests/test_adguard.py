"""Run the pinned AdGuard Home release against the rendered configuration, on local high ports."""

import hashlib
import json
import platform
import shutil
import socket
import subprocess
import tarfile
import time
import urllib.request
from pathlib import Path

import bcrypt
import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path.home() / ".cache/homelab-infrastructure/adguardhome"
ALL = yaml.safe_load((ROOT / "inventory/group_vars/all.yml").read_text())
DNS = yaml.safe_load((ROOT / "inventory/group_vars/dns.yml").read_text())
ARCH = {"x86_64": "amd64", "aarch64": "arm64"}[platform.machine()]


@pytest.fixture(scope="module")
def adguard():
    """Return the path of the pinned binary. Download it once, and check its sha256."""
    folder = CACHE / DNS["adguard_version"] / ARCH
    binary = folder / "AdGuardHome/AdGuardHome"
    if not binary.exists():
        url = (
            "https://github.com/AdguardTeam/AdGuardHome/releases/download/"
            f"{DNS['adguard_version']}/AdGuardHome_linux_{ARCH}.tar.gz"
        )
        data = urllib.request.urlopen(url, timeout=60).read()
        assert hashlib.sha256(data).hexdigest() == DNS["adguard_sha256"][ARCH]
        archive = folder.parent / f"AdGuardHome_linux_{ARCH}.tar.gz"
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(data)
        with tarfile.open(archive) as tar:
            tar.extractall(folder, filter="data")
    return binary


def free_port(kind):
    with socket.socket(socket.AF_INET, kind) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def render(tmp_path, dns_port, http_port):
    """Render the template with Ansible's template module, then move it to local high ports.

    Ansible, not plain Jinja: AdGuard Home rewrites the file if even the final newline differs.
    """
    hash_file = tmp_path / "hash.json"
    hash_file.write_text(
        json.dumps({"adguard_admin_password_hash": bcrypt.hashpw(b"offline-test-only", bcrypt.gensalt(4)).decode()})
    )
    rendered = tmp_path / "rendered.yaml"
    subprocess.run(
        [
            "ansible", "localhost", "--connection=local", "-m", "ansible.builtin.template",
            "-a", f"src=roles/adguard_config/templates/AdGuardHome.yaml.j2 dest={rendered}",
            "-e", "@inventory/group_vars/all.yml", "-e", "@inventory/group_vars/dns.yml", "-e", f"@{hash_file}",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    text = rendered.read_text()
    for old, new in [
        ("address: 0.0.0.0:80\n", f"address: 127.0.0.1:{http_port}\n"),
        ("    - 0.0.0.0\n  port: 53\n", f"    - 127.0.0.1\n  port: {dns_port}\n"),
    ]:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    return text


def test_config_is_valid(adguard, tmp_path):
    config = tmp_path / "AdGuardHome.yaml"
    config.write_text(render(tmp_path, 53, 80))
    result = subprocess.run(
        [adguard, "--check-config", "--config", config, "--work-dir", tmp_path],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_wildcard_answer_and_no_rewrite(adguard, tmp_path):
    """The lab wildcard answers the floating IP, and AdGuard Home leaves the file unchanged."""
    dns_port = free_port(socket.SOCK_DGRAM)
    config = tmp_path / "AdGuardHome.yaml"
    config.write_text(render(tmp_path, dns_port, free_port(socket.SOCK_STREAM)))
    expected = config.read_bytes()
    work = tmp_path / "work"
    work.mkdir(mode=0o700)
    server = subprocess.Popen(
        [adguard, "--config", config, "--work-dir", work, "--no-check-update"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        answer = ""
        for _ in range(20):
            answer = subprocess.run(
                ["dig", "+short", "+time=1", "+tries=1", "-p", str(dns_port), "@127.0.0.1",
                 f"test.{ALL['lab_domain']}"],
                capture_output=True,
                text=True,
            ).stdout.strip()
            # Before the server listens, dig prints an error that starts with ";;".
            if answer and not answer.startswith(";;"):
                break
            time.sleep(0.5)
        assert answer == ALL["edge_vip"]
        time.sleep(3)
    finally:
        server.terminate()
        server.wait(timeout=10)
    assert config.read_bytes() == expected


def test_dig_is_installed():
    assert shutil.which("dig"), "dig is needed for the wildcard test"
