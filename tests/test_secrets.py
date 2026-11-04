"""Scan the repo for secrets. Reports file, line and pattern name, never the value."""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

PATTERNS = {
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "password hash": re.compile(r"\$(?:1|2[aby]|5|6|y)\$[^\s'\"]{20,}"),
    "Tailscale key": re.compile(r"tskey-[a-z]+-[A-Za-z0-9-]{10,}"),
    "GitHub token": re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{20,}"),
    "Proxmox API token": re.compile(r"![\w-]+=[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"),
    # A key with a secret-like name and a literal value. Vault and template references are allowed.
    "secret assignment": re.compile(
        r"""[\w.-]*(?:password|passwd|secret|token|api_?key)[\w.-]*\s*[:=]\s*["']?"""
        r"""(?!\{\{|!vault|<|/|\$\{|\$\(|var\.|null\b|true\b|false\b)[^\s"'#]{8,}""",
        re.IGNORECASE,
    ),
}
FORBIDDEN_NAME = re.compile(r"(\.tfstate(\.|$)|\.tfvars$|\.pem$|\.key$|(^|/)\.vault-pass)")
VAULT_NAME = re.compile(r"(^|/)vault[^/]*\.ya?ml$|(^|/)secrets/")
VAULT_HEADER = "$ANSIBLE_VAULT;"


def find_secrets(text):
    """Return (line number, pattern name) for each match in text."""
    return [
        (number, name)
        for number, line in enumerate(text.splitlines(), start=1)
        for name, pattern in PATTERNS.items()
        if pattern.search(line)
    ]


def repo_files():
    """Return tracked files plus new files that Git does not ignore."""
    output = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [name for name in output.split("\0") if name and (ROOT / name).is_file()]


def test_no_secrets_in_repo_files():
    hits = []
    for name in repo_files():
        text = (ROOT / name).read_text(errors="ignore")
        if text.startswith(VAULT_HEADER):
            continue
        hits += [f"{name}:{number}: {pattern}" for number, pattern in find_secrets(text)]
    assert hits == []


def test_no_forbidden_files():
    assert [name for name in repo_files() if FORBIDDEN_NAME.search(name)] == []


def test_vault_files_are_encrypted():
    plain = [
        name
        for name in repo_files()
        if VAULT_NAME.search(name) and not (ROOT / name).read_text(errors="ignore").startswith(VAULT_HEADER)
    ]
    assert plain == []


# The fake values below are joined at run time so that this file does not match its own scan.
@pytest.mark.parametrize(
    ("pattern", "text"),
    [
        ("private key", "-----BEGIN OPENSSH " + "PRIVATE KEY-----"),
        ("password hash", "hashed_passwd: $" + "6$" + "a" * 40),
        ("password hash", "$" + "y$" + "j9T$" + "b" * 40),
        ("Tailscale key", "ts" + "key-auth-" + "c" * 20),
        ("GitHub token", "gh" + "p_" + "d" * 36),
        ("Proxmox API token", "tofu@pve!tofu" + "=" + "12345678-1234-1234-1234-123456789abc"),
        ("secret assignment", "password" + ": hunter2hunter2"),
        ("secret assignment", "cloudflare_api_token" + ' = "' + "e" * 40 + '"'),
    ],
)
def test_scanner_finds_fake_secrets(pattern, text):
    assert pattern in [name for _, name in find_secrets(text)]


@pytest.mark.parametrize(
    "text",
    [
        'password: "{{ vault_password }}"',
        "cloudflare_api_token: !vault |",
        "password: <value>",
        "secrets: $(STAMP)",
        "api_token = var.proxmox_api_token",
        "VAULT_PASSWORD_FILE=/path/to/file",
        "hashed_passwd is a secret",
    ],
)
def test_scanner_allows_references(text):
    assert find_secrets(text) == []
