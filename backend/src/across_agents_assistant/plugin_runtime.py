from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
import json
import os
import shutil
import subprocess

from .paths import component_cache_home, ecosystem_bin_dir, ecosystem_home, ecosystem_plugin_root


@dataclass(frozen=True)
class KnownAcrossPlugin:
    plugin_id: str
    display_name: str
    kind: str
    command: str
    install_command: str
    install_source_env: str | None = None
    default_install_source: str | None = None


KNOWN_PLUGINS: tuple[KnownAcrossPlugin, ...] = (
    KnownAcrossPlugin(
        plugin_id="across-context",
        display_name="Across Context",
        kind="memory-provider",
        command="across-context",
        install_command="across-context install host-plugin",
        install_source_env="ACROSS_AGENTS_CONTEXT_INSTALL_SOURCE",
        default_install_source="git+https://github.com/fantasyce/across-context.git#v0.6.0",
    ),
    KnownAcrossPlugin(
        plugin_id="across-orchestrator",
        display_name="Across Orchestrator",
        kind="task-runtime",
        command="across-orchestrator",
        install_command="python3 -m pip install git+https://github.com/fantasyce/across-orchestrator.git@v0.5.0",
        install_source_env="ACROSS_AGENTS_ORCHESTRATOR_INSTALL_SOURCE",
        default_install_source="git+https://github.com/fantasyce/across-orchestrator.git@v0.5.0",
    ),
)


class PluginLifecycleError(RuntimeError):
    """Raised when a plugin lifecycle action cannot be completed safely."""


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
        "version": str(manifest.get("version") or ""),
        "status": public_status.get("status") or ("installed" if installed else "not_installed"),
        "installed": bool(public_status.get("installed", installed)),
        "available": bool(public_status.get("available", command_exists)),
        "probe": bool(probe),
        "manifest": manifest,
        "capabilities": manifest.get("capabilities") or {},
        "compatibility": manifest.get("compatibility") or {},
        "permissions": manifest.get("permissions") or {},
        "diagnostics": manifest.get("diagnostics") or {},
        "lifecycle": public_status.get("lifecycle") or _default_lifecycle(plugin),
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
            "source": _install_source(plugin, source),
        },
    }


def run_context_plugin_lifecycle_action(
    action: str,
    *,
    env: Mapping[str, str] | None = None,
    runner: Any = subprocess.run,
) -> dict[str, Any]:
    normalized = _normalize_action(action)
    if normalized == "probe":
        return inspect_across_plugin("across-context", probe=True, env=env)
    if normalized in {"install", "repair", "upgrade"}:
        return _install_across_context(env=env, runner=runner)
    if normalized == "uninstall":
        return _uninstall_managed_plugin("across-context", "across-context", env=env)
    raise PluginLifecycleError("Unsupported Across Context lifecycle action")


def list_context_memories(
    *,
    project_root: str | None = None,
    status: str | None = None,
    scope: str | None = None,
    type: str | None = None,
    env: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    args = ["list", "--json"]
    if project_root:
        args.extend(["--project", project_root])
    if status:
        args.extend(["--status", status])
    payload = _run_context_cli_json(args, env=env, timeout=15)
    memories = payload if isinstance(payload, list) else payload.get("memories", [])
    if not isinstance(memories, list):
        return []
    entries = [entry for entry in memories if isinstance(entry, dict)]
    if scope:
        entries = [entry for entry in entries if str(entry.get("scope") or "") == scope]
    if type:
        entries = [entry for entry in entries if str(entry.get("type") or "") == type]
    return entries


def remember_context_memory(
    *,
    text: str,
    project_root: str | None = None,
    scope: str = "global",
    type: str = "note",
    status: str = "pending",
    tags: list[str] | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    args = ["remember", text, "--scope", scope, "--type", type, "--status", status, "--json"]
    if project_root:
        args.extend(["--project", project_root])
    for tag in tags or []:
        args.extend(["--tag", str(tag)])
    payload = _run_context_cli_json(args, env=env, timeout=15)
    memory = payload.get("memory") if isinstance(payload, dict) else None
    if not isinstance(memory, dict):
        raise PluginLifecycleError("Across Context did not return a memory record")
    return memory


def update_context_memory_status(
    memory_id: str,
    status: str,
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    payload = _run_context_cli_json(["update-status", status, memory_id, "--json"], env=env, timeout=15)
    updated = payload.get("updated") if isinstance(payload, dict) else None
    if isinstance(updated, list) and updated:
        first = updated[0]
        if isinstance(first, dict):
            return first
    raise PluginLifecycleError("Across Context memory was not found")


def forget_context_memory(memory_id: str, *, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    payload = _run_context_cli_json(["forget", memory_id, "--json"], env=env, timeout=15)
    forgotten = 0
    if isinstance(payload, dict):
        forgotten = int(payload.get("forgotten") or 0)
    return {"forgotten": forgotten > 0, "id": memory_id}


def uninstall_managed_plugin(plugin_id: str, *, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    plugin = _known_plugin(plugin_id)
    if plugin is None:
        raise PluginLifecycleError("Unknown Across plugin")
    return _uninstall_managed_plugin(plugin.plugin_id, plugin.command, env=env)


def _known_plugin(plugin_id: str) -> KnownAcrossPlugin | None:
    return next((plugin for plugin in KNOWN_PLUGINS if plugin.plugin_id == plugin_id), None)


def _normalize_action(action: str) -> str:
    normalized = str(action or "").strip().lower().replace("-", "_")
    if normalized == "refresh":
        return "probe"
    if normalized in {"install", "upgrade", "repair", "uninstall", "probe"}:
        return normalized
    raise PluginLifecycleError("Unsupported plugin lifecycle action")


def _default_lifecycle(plugin: KnownAcrossPlugin) -> dict[str, Any]:
    return {
        "actions": ["probe", "install", "repair", "upgrade", "uninstall"],
        "preservesDataOnUninstall": True,
        "installSource": plugin.default_install_source,
    }


def _install_source(plugin: KnownAcrossPlugin, env: Mapping[str, str]) -> str | None:
    if plugin.install_source_env:
        configured = str(env.get(plugin.install_source_env) or "").strip()
        if configured:
            return configured
    return plugin.default_install_source


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


def _install_across_context(
    *,
    env: Mapping[str, str] | None = None,
    runner: Any = subprocess.run,
) -> dict[str, Any]:
    source = env if env is not None else os.environ
    across_home = ecosystem_home(source)
    command_path = _resolve_command("across-context", source)
    if command_path.is_file() and os.access(command_path, os.X_OK):
        _run_checked(
            [str(command_path), "install", "host-plugin", "--across-home", str(across_home)],
            source,
            runner=runner,
        )
        return inspect_across_plugin("across-context", probe=True, env=source)

    npm = shutil.which("npm", path=source.get("PATH"))
    if not npm:
        raise PluginLifecycleError("npm is required to install Across Context when no existing command is available")

    plugin = _known_plugin("across-context")
    install_source = _install_source(plugin, source) if plugin else None
    if not install_source:
        raise PluginLifecycleError("Across Context install source is not configured")

    cache_dir = component_cache_home(env=source) / "plugin-installers" / "across-context"
    shutil.rmtree(cache_dir, ignore_errors=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    _run_checked([npm, "install", "--prefix", str(cache_dir), install_source], source, runner=runner)
    installed_command = cache_dir / "node_modules" / ".bin" / "across-context"
    if not installed_command.is_file():
        raise PluginLifecycleError("Across Context installed but its CLI command was not found")
    _run_checked(
        [str(installed_command), "install", "host-plugin", "--across-home", str(across_home)],
        source,
        runner=runner,
    )
    return inspect_across_plugin("across-context", probe=True, env=source)


def _uninstall_managed_plugin(plugin_id: str, command: str, *, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = env if env is not None else os.environ
    plugin_dir = ecosystem_plugin_root(source) / plugin_id
    wrapper = ecosystem_bin_dir(source) / command
    shutil.rmtree(plugin_dir, ignore_errors=True)
    try:
        wrapper.unlink()
    except FileNotFoundError:
        pass
    return {
        "plugin_id": plugin_id,
        "status": "not_installed",
        "removed": True,
        "plugin_dir": str(plugin_dir),
        "wrapper": str(wrapper),
        "preserved_data": str(ecosystem_home(source) / "data" / plugin_id),
    }


def _run_checked(args: list[str], env: Mapping[str, str], *, runner: Any = subprocess.run) -> None:
    safe_env = os.environ.copy()
    safe_env.update({str(key): str(value) for key, value in env.items()})
    safe_env.setdefault("ACROSS_HOME", str(ecosystem_home(env)))
    safe_env.setdefault("ACROSS_PLUGIN_HOME", str(ecosystem_plugin_root(env)))
    safe_env.setdefault("ACROSS_BIN_HOME", str(ecosystem_bin_dir(env)))
    completed = runner(
        args,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=900,
        env=safe_env,
        check=False,
    )
    if int(getattr(completed, "returncode", 1)) != 0:
        raise PluginLifecycleError("Plugin lifecycle command failed")


def _safe_plugin_env(env: Mapping[str, str]) -> dict[str, str]:
    safe_env = os.environ.copy()
    safe_env.update({str(key): str(value) for key, value in env.items()})
    safe_env.setdefault("ACROSS_HOME", str(ecosystem_home(env)))
    safe_env.setdefault("ACROSS_PLUGIN_HOME", str(ecosystem_plugin_root(env)))
    safe_env.setdefault("ACROSS_BIN_HOME", str(ecosystem_bin_dir(env)))
    return safe_env


def _run_context_cli_json(args: list[str], *, env: Mapping[str, str] | None = None, timeout: int = 15) -> Any:
    source = env if env is not None else os.environ
    command_path = _resolve_command("across-context", source)
    if not command_path.is_file() or not os.access(command_path, os.X_OK):
        raise PluginLifecycleError("Across Context plugin is not installed")
    completed = subprocess.run(
        [str(command_path), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        env=_safe_plugin_env(source),
        check=False,
    )
    if completed.returncode != 0:
        raise PluginLifecycleError("Across Context command failed")
    try:
        return json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise PluginLifecycleError("Across Context returned invalid JSON") from exc


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _run_json(args: list[str], env: Mapping[str, str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            args,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            env=_safe_plugin_env(env),
            check=False,
        )
        if completed.returncode != 0:
            return {}
        payload = json.loads(completed.stdout or "{}")
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}
