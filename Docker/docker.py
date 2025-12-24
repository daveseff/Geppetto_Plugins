"""
Geppetto plugin for managing Docker containers.

Exposes a `docker_container` operation that can ensure containers are running
with a given image, optionally recreating them when the image changes.
"""

from __future__ import annotations

import json
import shutil
from typing import Any, Iterable, Optional

from geppetto_automation.executors import Executor
from geppetto_automation.operations.base import Operation
from geppetto_automation.types import ActionResult, HostConfig


class DockerContainer(Operation):
    def __init__(self, spec: dict[str, Any]):
        super().__init__(spec)
        raw_name = spec.get("name") or spec.get("container")
        if not raw_name:
            raise ValueError("docker_container requires a name")
        self.name = str(raw_name)

        self.state = str(spec.get("state", "present"))
        if self.state not in {"present", "absent"}:
            raise ValueError("docker_container state must be 'present' or 'absent'")

        raw_image = spec.get("image")
        if self.state == "present" and not raw_image:
            raise ValueError("docker_container requires an image when state=present")
        self.image = str(raw_image) if raw_image else None

        self.pull = bool(spec.get("pull", True))
        self.detach = bool(spec.get("detach", True))
        self.restart_policy: Optional[str] = spec.get("restart") or spec.get("restart_policy")
        self.network: Optional[str] = spec.get("network")
        self.workdir: Optional[str] = spec.get("workdir")
        self.command = spec.get("command")
        self.recreate = bool(spec.get("recreate", False))
        self.recreate_on_image_change = bool(spec.get("recreate_on_image_change", True))

        self.env = self._listify_env(spec.get("env"))
        self.ports = self._listify_strings(spec.get("ports"))
        self.volumes = self._listify_strings(spec.get("volumes"))
        self.extra_args = self._listify_strings(spec.get("extra_args"))

    def apply(self, host: HostConfig, executor: Executor) -> ActionResult:
        if not shutil.which("docker"):
            raise RuntimeError("docker binary not found on PATH")

        if self.state == "absent":
            return self._ensure_absent(host, executor)

        if self.pull and self.image:
            executor.run(["docker", "pull", self.image])

        container_info = self._inspect_container(executor)
        desired_image_id = self._inspect_image(executor, self.image) if self.image else None

        if container_info is None:
            self._run_container(executor)
            return ActionResult(host=host.name, action="docker_container", changed=True, details="created")

        running = bool(container_info.get("State", {}).get("Running"))
        current_image_id = container_info.get("Image")
        needs_recreate = self.recreate
        if (
            self.recreate_on_image_change
            and desired_image_id
            and current_image_id
            and desired_image_id != current_image_id
        ):
            needs_recreate = True

        if needs_recreate:
            self._remove_container(executor)
            self._run_container(executor)
            return ActionResult(host=host.name, action="docker_container", changed=True, details="recreated")

        if not running:
            executor.run(["docker", "start", self.name])
            return ActionResult(host=host.name, action="docker_container", changed=True, details="started")

        return ActionResult(host=host.name, action="docker_container", changed=False, details="noop")

    def _ensure_absent(self, host: HostConfig, executor: Executor) -> ActionResult:
        if self._inspect_container(executor) is None:
            return ActionResult(host=host.name, action="docker_container", changed=False, details="noop")
        self._remove_container(executor)
        return ActionResult(host=host.name, action="docker_container", changed=True, details="removed")

    def _run_container(self, executor: Executor) -> None:
        if not self.image:
            raise ValueError("image is required to run a container")
        cmd = ["docker", "run"]
        if self.detach:
            cmd.append("-d")
        cmd.extend(["--name", self.name])
        if self.restart_policy:
            cmd.extend(["--restart", str(self.restart_policy)])
        if self.network:
            cmd.extend(["--network", self.network])
        if self.workdir:
            cmd.extend(["-w", self.workdir])
        for env in self.env:
            cmd.extend(["-e", env])
        for port in self.ports:
            cmd.extend(["-p", port])
        for volume in self.volumes:
            cmd.extend(["-v", volume])
        cmd.extend(self.extra_args)
        cmd.append(self.image)
        if self.command:
            if isinstance(self.command, str):
                cmd.append(self.command)
            elif isinstance(self.command, Iterable):
                cmd.extend([str(part) for part in self.command])
            else:
                raise ValueError("command must be a string or list")
        executor.run(cmd)

    def _inspect_container(self, executor: Executor) -> Optional[dict[str, Any]]:
        result = executor.run(["docker", "inspect", self.name], check=False, mutable=False)
        if result.returncode != 0:
            return None
        try:
            data = json.loads(result.stdout)
            return data[0] if data else None
        except json.JSONDecodeError:
            return None

    def _inspect_image(self, executor: Executor, image: Optional[str]) -> Optional[str]:
        if not image:
            return None
        result = executor.run(
            ["docker", "image", "inspect", image, "--format", "{{.Id}}"],
            check=False,
            mutable=False,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip()

    def _remove_container(self, executor: Executor) -> None:
        executor.run(["docker", "rm", "-f", self.name])

    @staticmethod
    def _listify_strings(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return [str(item) for item in value]

    @staticmethod
    def _listify_env(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, dict):
            return [f"{k}={v}" for k, v in value.items()]
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, str):
            return [value]
        raise ValueError("env must be a map, list, or string when provided")


def register_operations(registry) -> None:
    registry["docker_container"] = DockerContainer
