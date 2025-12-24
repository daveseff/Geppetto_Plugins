"""
Geppetto plugin for managing Let's Encrypt certificates via certbot.

Provides a `letsencrypt_cert` operation that issues, renews, or deletes
certificates using the certbot CLI and the webroot challenge.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import shutil
import ssl

from geppetto_automation.executors import Executor
from geppetto_automation.operations.base import Operation
from geppetto_automation.types import ActionResult, HostConfig


class LetsEncryptCertificate(Operation):
    """Issue or renew Let's Encrypt certificates with certbot."""

    def __init__(self, spec: dict[str, Any]):
        super().__init__(spec)
        raw_domains = spec.get("domains") or spec.get("domain")
        if isinstance(raw_domains, str):
            self.domains = [raw_domains]
        else:
            self.domains = list(raw_domains or [])
        if not self.domains:
            raise ValueError("letsencrypt_cert requires at least one domain")
        self.domains = [str(domain).lower() for domain in self.domains]

        raw_email = spec.get("email")
        if not raw_email:
            raise ValueError("letsencrypt_cert requires an email for registration")
        self.email = str(raw_email)

        raw_webroot = spec.get("webroot")
        self.webroot = Path(str(raw_webroot)) if raw_webroot else None
        self.standalone = bool(spec.get("standalone", False) or not self.webroot)

        self.cert_name = str(spec.get("cert_name") or self.domains[0])
        self.state = str(spec.get("state", "present"))
        if self.state not in {"present", "absent"}:
            raise ValueError("letsencrypt_cert state must be 'present' or 'absent'")

        self.force_renew = bool(spec.get("force_renew", False))
        self.staging = bool(spec.get("staging", False))
        self.renew_before_days = int(spec.get("renew_before_days", 30))
        extra_args = spec.get("extra_args")
        if extra_args is None:
            self.extra_args: list[str] = []
        elif isinstance(extra_args, list):
            self.extra_args = [str(arg) for arg in extra_args]
        else:
            raise ValueError("extra_args must be a list of strings when provided")

        self.live_cert_path = Path("/etc/letsencrypt/live") / self.cert_name / "cert.pem"

    def apply(self, host: HostConfig, executor: Executor) -> ActionResult:
        if not shutil.which("certbot"):
            raise RuntimeError("certbot binary not found on PATH")

        if self.state == "absent":
            return self._ensure_absent(host, executor)

        if self.webroot and not self.webroot.exists() and not self.standalone:
            raise ValueError(f"webroot path {self.webroot} does not exist on target host")
        if not self.webroot and not self.standalone:
            raise ValueError("either provide webroot or set standalone=true")

        expiry = self._current_expiry(executor)
        current_domains = self._current_domains()
        domain_mismatch = bool(current_domains) and not set(self.domains).issubset(current_domains)
        if (
            expiry
            and not self.force_renew
            and not domain_mismatch
            and expiry - datetime.now(timezone.utc) > timedelta(days=self.renew_before_days)
        ):
            detail = f"valid-until={expiry.isoformat()}"
            return ActionResult(
                host=host.name,
                action="letsencrypt_cert",
                changed=False,
                details=detail,
            )

        existing = self.live_cert_path.exists()
        self._issue_or_renew(executor)
        mode = "standalone" if self.standalone else "webroot"
        detail = ("renewed" if existing else "requested") + f" mode={mode}"
        return ActionResult(host=host.name, action="letsencrypt_cert", changed=True, details=detail)

    def _current_expiry(self, executor: Executor) -> datetime | None:
        if not self.live_cert_path.exists():
            return None
        result = executor.run(
            [
                "openssl",
                "x509",
                "-enddate",
                "-noout",
                "-in",
                str(self.live_cert_path),
            ],
            check=False,
            mutable=False,
        )
        if result.returncode != 0:
            return None

        line = result.stdout.strip() or result.stderr.strip()
        if line.startswith("notAfter="):
            line = line.split("=", 1)[1].strip()
        try:
            return datetime.strptime(line, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    def _issue_or_renew(self, executor: Executor) -> None:
        cmd = [
            "certbot",
            "certonly",
            "--non-interactive",
            "--agree-tos",
            "--keep-until-expiring",
            "--email",
            self.email,
            "--cert-name",
            self.cert_name,
        ]
        if self.standalone:
            cmd.append("--standalone")
        else:
            cmd.extend(["--webroot", "-w", str(self.webroot)])
        if self.force_renew:
            cmd.append("--force-renewal")
        if self.staging:
            cmd.append("--staging")
        for domain in self.domains:
            cmd.extend(["-d", domain])
        cmd.extend(self.extra_args)
        executor.run(cmd)

    def _current_domains(self) -> set[str]:
        if not self.live_cert_path.exists():
            return set()
        try:
            info = ssl._ssl._test_decode_cert(str(self.live_cert_path))
        except Exception:
            return set()

        sans = {value for key, value in info.get("subjectAltName", []) if key == "DNS"}
        common_names = {value for key, value in info.get("subject", []) if key == "commonName"}
        domains = sans or common_names
        return {str(domain).lower() for domain in domains}

    def _ensure_absent(self, host: HostConfig, executor: Executor) -> ActionResult:
        if not self.live_cert_path.exists():
            return ActionResult(host=host.name, action="letsencrypt_cert", changed=False, details="noop")
        executor.run(
            ["certbot", "delete", "--non-interactive", "--cert-name", self.cert_name],
        )
        return ActionResult(host=host.name, action="letsencrypt_cert", changed=True, details="deleted")


def register_operations(registry) -> None:
    registry["letsencrypt_cert"] = LetsEncryptCertificate
