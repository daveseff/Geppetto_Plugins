import importlib.util
import subprocess
from pathlib import Path

import pytest

from geppetto_automation.executors import CommandResult, Executor
from geppetto_automation.types import HostConfig


def _load_docker_plugin():
    plugin_path = Path(__file__).resolve().parent.parent / "Docker" / "docker.py"
    spec = importlib.util.spec_from_file_location("geppetto_plugin_docker", plugin_path)
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


def test_create_container_when_absent(monkeypatch):
    plugin = _load_docker_plugin()
    host = HostConfig("local")
    script = [
        CommandResult(["docker", "pull", "nginx:latest"], "", "", 0),
        CommandResult(["docker", "inspect", "web"], "", "", 1),  # not found
        CommandResult(["docker", "image", "inspect", "nginx:latest"], "sha256:new\n", "", 0),
        CommandResult(["docker", "run"], "", "", 0),
    ]
    executor = ScriptExecutor(host, script)
    monkeypatch.setattr(plugin.shutil, "which", lambda _: "/usr/bin/docker")

    op = plugin.DockerContainer({"name": "web", "image": "nginx:latest"})
    result = op.apply(host, executor)

    assert result.changed is True
    assert result.details == "created"
    assert ["docker", "pull", "nginx:latest"] in executor.commands
    assert any(cmd[:2] == ["docker", "run"] for cmd in executor.commands)


def test_recreate_when_image_changes(monkeypatch):
    plugin = _load_docker_plugin()
    host = HostConfig("local")
    container_info = {
        "State": {"Running": True},
        "Image": "sha256:old",
    }
    script = [
        CommandResult(["docker", "pull", "app:1"], "", "", 0),
        CommandResult(["docker", "inspect", "app"], plugin.json.dumps([container_info]), "", 0),
        CommandResult(["docker", "image", "inspect", "app:1"], "sha256:new\n", "", 0),
        CommandResult(["docker", "rm", "-f", "app"], "", "", 0),
        CommandResult(["docker", "run"], "", "", 0),
    ]
    executor = ScriptExecutor(host, script)
    monkeypatch.setattr(plugin.shutil, "which", lambda _: "/usr/bin/docker")

    op = plugin.DockerContainer({"name": "app", "image": "app:1"})
    result = op.apply(host, executor)

    assert result.changed is True
    assert result.details == "recreated"
    assert ["docker", "rm", "-f", "app"] in executor.commands
    assert any(cmd[:2] == ["docker", "run"] for cmd in executor.commands)


def test_absent_removes_existing_container(monkeypatch):
    plugin = _load_docker_plugin()
    host = HostConfig("local")
    container_info = {"State": {"Running": False}, "Image": "sha256:abc"}
    script = [
        CommandResult(["docker", "inspect", "old"], plugin.json.dumps([container_info]), "", 0),
        CommandResult(["docker", "rm", "-f", "old"], "", "", 0),
    ]
    executor = ScriptExecutor(host, script)
    monkeypatch.setattr(plugin.shutil, "which", lambda _: "/usr/bin/docker")

    op = plugin.DockerContainer({"name": "old", "state": "absent"})
    result = op.apply(host, executor)

    assert result.changed is True
    assert result.details == "removed"
    assert ["docker", "rm", "-f", "old"] in executor.commands
