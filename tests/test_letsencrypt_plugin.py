import importlib.util
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from geppetto_automation.executors import CommandResult, Executor
from geppetto_automation.types import HostConfig


def _load_le_plugin():
    plugin_path = Path(__file__).resolve().parent.parent / "LetsEncrypt" / "letsencrypt.py"
    spec = importlib.util.spec_from_file_location("geppetto_plugin_letsencrypt", plugin_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class ScriptExecutor(Executor):
    """Executor that returns pre-seeded CommandResults in order."""

    def __init__(self, host: HostConfig, script: list[CommandResult]):
        super().__init__(host, dry_run=False)
        self.script = script
        self.commands: list[list[str]] = []

    def run(self, command, *, check=True, mutable=True, env=None, cwd=None, timeout=None):
        self.commands.append(list(command))
        if not self.script:
            raise AssertionError("No scripted CommandResult available")
        result = self.script.pop(0)
        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, command, result.stdout, result.stderr)
        return result


def test_skips_when_cert_valid_and_domains_match(monkeypatch, tmp_path):
    plugin = _load_le_plugin()
    host = HostConfig("local")
    cert_path = tmp_path / "cert.pem"
    cert_path.write_text("dummy")

    future = datetime.now(timezone.utc) + timedelta(days=60)
    expiry = future.strftime("notAfter=%b %d %H:%M:%S %Y GMT")

    script = [
        CommandResult(["openssl", "x509"], expiry, "", 0),
    ]
    executor = ScriptExecutor(host, script)
    monkeypatch.setattr(plugin.shutil, "which", lambda _: "/usr/bin/certbot")
    monkeypatch.setattr(plugin.ssl._ssl, "_test_decode_cert", lambda _path: {"subjectAltName": [("DNS", "example.com")]})

    op = plugin.LetsEncryptCertificate(
        {"domains": ["example.com"], "email": "admin@example.com", "standalone": True}
    )
    op.live_cert_path = cert_path

    result = op.apply(host, executor)

    assert result.changed is False
    assert "valid-until=" in result.details


def test_requests_when_missing_cert(monkeypatch, tmp_path):
    plugin = _load_le_plugin()
    host = HostConfig("local")

    script = [
        CommandResult(["certbot"], "", "", 0),
    ]
    executor = ScriptExecutor(host, script)
    monkeypatch.setattr(plugin.shutil, "which", lambda _: "/usr/bin/certbot")
    monkeypatch.setattr(plugin.ssl._ssl, "_test_decode_cert", lambda _path: {})

    op = plugin.LetsEncryptCertificate(
        {"domains": ["example.com"], "email": "admin@example.com", "standalone": True}
    )
    op.live_cert_path = tmp_path / "cert.pem"

    result = op.apply(host, executor)

    assert result.changed is True
    assert result.details.startswith("requested")
    assert any(cmd[0] == "certbot" for cmd in executor.commands)


def test_renews_when_domains_mismatch(monkeypatch, tmp_path):
    plugin = _load_le_plugin()
    host = HostConfig("local")
    cert_path = tmp_path / "cert.pem"
    cert_path.write_text("dummy")

    future = datetime.now(timezone.utc) + timedelta(days=60)
    expiry = future.strftime("notAfter=%b %d %H:%M:%S %Y GMT")

    script = [
        CommandResult(["openssl", "x509"], expiry, "", 0),
        CommandResult(["certbot"], "", "", 0),
    ]
    executor = ScriptExecutor(host, script)
    monkeypatch.setattr(plugin.shutil, "which", lambda _: "/usr/bin/certbot")
    monkeypatch.setattr(plugin.ssl._ssl, "_test_decode_cert", lambda _path: {"subjectAltName": [("DNS", "old.example.com")]})

    op = plugin.LetsEncryptCertificate(
        {"domains": ["example.com"], "email": "admin@example.com", "standalone": True}
    )
    op.live_cert_path = cert_path

    result = op.apply(host, executor)

    assert result.changed is True
    assert result.details.startswith("renewed")
    assert any(cmd[0] == "certbot" for cmd in executor.commands)
