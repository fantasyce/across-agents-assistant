from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
import json
import os
import subprocess

from .paths import ecosystem_bin_dir, ecosystem_home, ecosystem_plugin_root


@dataclass(frozen=True)
class KnownAcrossPlugin:
    plugin_id: str
    display_name: str
    kind: str
    command: str
    install_command: str


KNOWN_PLUGINS: tuple[KnownAcrossPlugin, ...] = (
    KnownAcrossPlugin(
        plugin_id="across-context",
        display_name="Across Context",
        kind="memory-provider",
        command="across-context",
        install_command="across-context install host-plugin",
    ),
    KnownAcrossPlugin(
        plugin_id="across-orchestrator",
        display_name="Across Orchestrator",
        kind="task-runtime",
        command="across-orchestrator",
        install_command="python3 -m pip install across-orchestrator",
    ),
)


def discover_across_plugins(
    *,
    plugin_ids: list[str] | None = None,
    probe: bool = False,
    env: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    requested = set(plugin_ids or [])
    return [
        inspect_across_plugin(plugin.plugin_id, probe=probe, env=env)
        for plugin in KNOWN_PLUGINS
        if not requested or plugin.plugin_id in requested
    ]


def inspect_across_plugin(
    plugin_id: str,
    *,
    probe: bool = False,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    plugin = _known_plugin(plugin_id)
    if plugin is None:
        raise ValueError(f"Unknown Across plugin: {plugin_id}")

    source = env if env is not None else os.environ
    across_home = ecosystem_home(source)
    plugin_dir = ecosystem_plugin_root(source) / plugin.plugin_id
    manifest_path = plugin_dir / "manifest.json"
    command_path = _resolve_command(plugin.command, source)
    manifest = _read_json_file(manifest_path)
    command_exists = command_path.is_file() and os.access(command_path, os.X_OK)
    manifest_exists = bool(manifest)
    status: dict[str, Any] | None = None

    if probe and command_exists:
        probed_manifest = _run_json([str(command_path), "plugin-manifest", "--json"], source)
        if probed_manifest:
            manifest = probed_manifest
            manifest_exists = True
        status = _run_json([str(command_path), "plugin-status", "--json"], source)

    installed = manifest_exists or command_exists
    public_status = status or {}
    return {
        "plugin_id": plugin.plugin_id,
        "display_name": str(manifest.get("displayName") or plugin.display_name),
        "kind": str(manifest.get("kind") or plugin.kind),
        "status": public_status.get("status") or ("installed" if installed else "not_installed"),
        "installed": bool(public_status.get("installed", installed)),
        "available": bool(public_status.get("available", command_exists)),
        "probe": bool(probe),
        "manifest": manifest,
        "manifest_path": str(manifest_path),
        "manifest_exists": manifest_exists,
        "command": str(public_status.get("command") or command_path),
        "command_exists": bool(public_status.get("commandExists", command_exists)),
        "paths": {
            "home": str(across_home),
            "plugin": str(plugin_dir),
            "bin": str(ecosystem_bin_dir(source)),
            "data": str(across_home / "data" / plugin.plugin_id),
            "config": str(across_home / "config" / plugin.plugin_id),
            "run": str(across_home / "run" / plugin.plugin_id),
            "logs": str(across_home / "logs" / plugin.plugin_id),
            "cache": str(across_home / "cache" / plugin.plugin_id),
        },
        "install": public_status.get("install") or {
            "installable": True,
            "command": plugin.install_command,
            "install_dir": str(plugin_dir),
        },
    }


def _known_plugin(plugin_id: str) -> KnownAcrossPlugin | None:
    return next((plugin for plugin in KNOWN_PLUGINS if plugin.plugin_id == plugin_id), None)


def _resolve_command(command: str, env: Mapping[str, str]) -> Path:
    bin_path = ecosystem_bin_dir(env) / command
    if bin_path.exists():
        return bin_path
    for item in str(env.get("PATH") or "").split(os.pathsep):
        if not item:
            continue
        candidate = Path(item) / command
        if candidate.exists():
            return candidate
    return bin_path


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _run_json(args: list[str], env: Mapping[str, str]) -> dict[str, Any]:
    safe_env = os.environ.copy()
    safe_env.update({str(key): str(value) for key, value in env.items()})
    safe_env.setdefault("ACROSS_HOME", str(ecosystem_home(env)))
    safe_env.setdefault("ACROSS_PLUGIN_HOME", str(ecosystem_plugin_root(env)))
    safe_env.setdefault("ACROSS_BIN_HOME", str(ecosystem_bin_dir(env)))
    try:
        completed = subprocess.run(
            args,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            env=safe_env,
            check=False,
        )
        if completed.returncode != 0:
            return {}
        payload = json.loads(completed.stdout or "{}")
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}
