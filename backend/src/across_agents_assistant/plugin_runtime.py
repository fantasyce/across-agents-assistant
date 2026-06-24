from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
import json
import os
import shutil
import subprocess
import urllib.parse

from .paths import component_cache_home, ecosystem_bin_dir, ecosystem_home, ecosystem_plugin_root
from .runtime_boundary import (
    contains_protected_user_reference,
    expand_user,
    is_developer_mode,
    is_product_mode,
    sanitized_product_runtime_env,
)


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
        default_install_source="git+https://github.com/fantasyce/across-context.git#v0.8.2",
    ),
    KnownAcrossPlugin(
        plugin_id="across-orchestrator",
        display_name="Across Orchestrator",
        kind="task-runtime",
        command="across-orchestrator",
        install_command="python3 -m pip install git+https://github.com/fantasyce/across-orchestrator.git@v0.7.2",
        install_source_env="ACROSS_AGENTS_ORCHESTRATOR_INSTALL_SOURCE",
        default_install_source="git+https://github.com/fantasyce/across-orchestrator.git@v0.7.2",
    ),
    KnownAcrossPlugin(
        plugin_id="across-autopilot",
        display_name="Across Autopilot",
        kind="autonomous-workflow",
        command="across-autopilot",
        install_command="across-autopilot install host-plugin",
        install_source_env="ACROSS_AGENTS_AUTOPILOT_INSTALL_SOURCE",
        default_install_source="git+https://github.com/fantasyce/across-autopilot.git#v0.2.2",
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

    source, runtime_boundary_issues = sanitized_product_runtime_env(env if env is not None else os.environ)
    across_home = ecosystem_home(source)
    plugin_dir = ecosystem_plugin_root(source) / plugin.plugin_id
    manifest_path = plugin_dir / "manifest.json"
    command_path = _resolve_command(plugin.command, source)
    manifest = _read_json_file(manifest_path)
    command_exists = command_path.is_file() and os.access(command_path, os.X_OK)
    integrity_issues = _plugin_dir_integrity_issues(plugin.plugin_id, plugin_dir)
    if command_exists:
        integrity_issues.extend(_command_integrity_issues(command_path, plugin_dir, source))
    manifest_exists = bool(manifest)
    status: dict[str, Any] | None = None

    if probe and command_exists and not integrity_issues:
        probed_manifest = _run_json([str(command_path), "plugin-manifest", "--json"], source)
        if probed_manifest:
            manifest = probed_manifest
            manifest_exists = True
        status = _run_json([str(command_path), "plugin-status", "--json"], source)

    installed = manifest_exists or command_exists
    public_status = status or {}
    actual_install_source = _actual_install_source(plugin_dir, plugin.plugin_id)
    configured_install_source = _install_source(plugin, source)
    install_status = public_status.get("install") if isinstance(public_status.get("install"), dict) else None
    if install_status:
        install_payload = dict(install_status)
        install_payload.setdefault("source", actual_install_source or configured_install_source)
        install_payload.setdefault("install_dir", str(plugin_dir))
        install_payload.setdefault("installable", True)
    else:
        install_payload = {
            "installable": True,
            "command": plugin.install_command,
            "install_dir": str(plugin_dir),
            "source": actual_install_source or configured_install_source,
        }
    return {
        "plugin_id": plugin.plugin_id,
        "display_name": str(manifest.get("displayName") or plugin.display_name),
        "kind": str(manifest.get("kind") or plugin.kind),
        "version": str(manifest.get("version") or ""),
        "status": public_status.get("status") or ("needs_repair" if integrity_issues else ("installed" if installed else "not_installed")),
        "installed": bool(public_status.get("installed", installed)),
        "available": bool(public_status.get("available", command_exists and not integrity_issues)),
        "probe": bool(probe),
        "integrity_ok": not integrity_issues,
        "integrity_issues": integrity_issues,
        "runtime_boundary_issues": runtime_boundary_issues,
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
        "install": install_payload,
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
        return _install_across_context(
            env=env,
            runner=runner,
            force_reinstall=normalized in {"repair", "upgrade"},
        )
    if normalized == "uninstall":
        return _uninstall_managed_plugin("across-context", "across-context", env=env)
    raise PluginLifecycleError("Unsupported Across Context lifecycle action")


def run_autopilot_plugin_lifecycle_action(
    action: str,
    *,
    env: Mapping[str, str] | None = None,
    runner: Any = subprocess.run,
) -> dict[str, Any]:
    normalized = _normalize_action(action)
    if normalized == "probe":
        return inspect_across_plugin("across-autopilot", probe=True, env=env)
    if normalized in {"install", "repair", "upgrade"}:
        return _install_node_host_plugin(
            "across-autopilot",
            env=env,
            runner=runner,
            force_reinstall=normalized in {"repair", "upgrade"},
        )
    if normalized == "uninstall":
        return _uninstall_managed_plugin("across-autopilot", "across-autopilot", env=env)
    raise PluginLifecycleError("Unsupported Across Autopilot lifecycle action")


def run_autopilot_cli_json(args: list[str], *, env: Mapping[str, str] | None = None, timeout: int = 60) -> Any:
    return _run_cli_json("across-autopilot", args, env=env, timeout=timeout)


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
    elif status == "pending":
        args.append("--all-projects")
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


def get_agent_loop_memory_metrics(
    *,
    project_root: str | None = None,
    all_projects: bool = True,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    args = ["loop-memory-metrics", "--json"]
    if project_root:
        args.extend(["--project", project_root])
    elif all_projects:
        args.append("--all-projects")
    payload = _run_context_cli_json(args, env=env, timeout=15)
    return payload if isinstance(payload, dict) else {}


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


def _actual_install_source(plugin_dir: Path, plugin_id: str) -> str | None:
    normalized = plugin_id.replace("-", "_")
    dashed = plugin_id.replace("_", "-")
    patterns = {
        f"venv/lib/python*/site-packages/{normalized}*.dist-info/direct_url.json",
        f"venv/lib/python*/site-packages/{dashed}*.dist-info/direct_url.json",
    }
    install_root = plugin_dir.expanduser().resolve()
    for pattern in sorted(patterns):
        for path in sorted(plugin_dir.glob(pattern)):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            url = str(payload.get("url") or "").strip()
            if not url or _contains_protected_user_reference(url):
                continue
            if url.startswith("file:"):
                parsed = urllib.parse.urlparse(url)
                local_path = Path(urllib.parse.unquote(parsed.path)).expanduser()
                if not (local_path.is_absolute() and _is_relative_to(local_path, install_root)):
                    continue
            return url
    return None


def _resolve_command(command: str, env: Mapping[str, str]) -> Path:
    bin_path = ecosystem_bin_dir(env) / command
    if bin_path.exists():
        return bin_path
    for item in str(env.get("PATH") or "").split(os.pathsep):
        if not item:
            continue
        candidate = Path(expand_user(item, env)) / command
        if _is_blocked_product_path(str(candidate), env):
            continue
        if candidate.exists():
            return candidate
    return bin_path


def _is_blocked_product_path(value: str, env: Mapping[str, str]) -> bool:
    return is_product_mode(env) and not is_developer_mode(env) and contains_protected_user_reference(value, env)


def _which_runtime_command(command: str, env: Mapping[str, str]) -> str | None:
    if os.path.isabs(command) or os.sep in command:
        if _is_blocked_product_path(command, env):
            return None
        candidate = Path(expand_user(command, env))
        return str(candidate) if candidate.is_file() and os.access(candidate, os.X_OK) else None
    for item in str(env.get("PATH") or "").split(os.pathsep):
        if not item:
            continue
        candidate = Path(expand_user(item, env)) / command
        if _is_blocked_product_path(str(candidate), env):
            continue
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _install_across_context(
    *,
    env: Mapping[str, str] | None = None,
    runner: Any = subprocess.run,
    force_reinstall: bool = False,
) -> dict[str, Any]:
    source, _runtime_boundary_issues = sanitized_product_runtime_env(env if env is not None else os.environ)
    across_home = ecosystem_home(source)
    command_path = _resolve_command("across-context", source)
    command_integrity_issues = (
        _command_integrity_issues(command_path, ecosystem_plugin_root(source) / "across-context", source)
        if command_path.is_file() and os.access(command_path, os.X_OK)
        else []
    )
    if (
        not force_reinstall
        and command_path.is_file()
        and os.access(command_path, os.X_OK)
        and not command_integrity_issues
    ):
        _run_checked(
            [str(command_path), "install", "host-plugin", "--across-home", str(across_home)],
            source,
            runner=runner,
        )
        return inspect_across_plugin("across-context", probe=True, env=source)

    npm = _which_runtime_command("npm", source)
    if not npm:
        raise PluginLifecycleError("npm is required to install Across Context when no existing command is available")

    plugin = _known_plugin("across-context")
    install_source = _install_source(plugin, source) if plugin else None
    if not install_source:
        raise PluginLifecycleError("Across Context install source is not configured")

    cache_dir = component_cache_home(env=source) / "plugin-installers" / "across-context"
    shutil.rmtree(cache_dir, ignore_errors=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    _run_checked([npm, "install", "--prefix", str(cache_dir), install_source], source, runner=runner, timeout=180)
    installed_command = cache_dir / "node_modules" / ".bin" / "across-context"
    if not installed_command.is_file():
        raise PluginLifecycleError("Across Context installed but its CLI command was not found")
    _run_checked(
        [str(installed_command), "install", "host-plugin", "--across-home", str(across_home)],
        source,
        runner=runner,
        timeout=60,
    )
    return inspect_across_plugin("across-context", probe=True, env=source)


def _install_node_host_plugin(
    plugin_id: str,
    *,
    env: Mapping[str, str] | None = None,
    runner: Any = subprocess.run,
    force_reinstall: bool = False,
) -> dict[str, Any]:
    plugin = _known_plugin(plugin_id)
    if plugin is None:
        raise PluginLifecycleError("Unknown Across plugin")

    source, _runtime_boundary_issues = sanitized_product_runtime_env(env if env is not None else os.environ)
    across_home = ecosystem_home(source)
    command_path = _resolve_command(plugin.command, source)
    command_integrity_issues = (
        _command_integrity_issues(command_path, ecosystem_plugin_root(source) / plugin.plugin_id, source)
        if command_path.is_file() and os.access(command_path, os.X_OK)
        else []
    )
    if (
        not force_reinstall
        and command_path.is_file()
        and os.access(command_path, os.X_OK)
        and not command_integrity_issues
    ):
        _run_checked(
            [str(command_path), "install", "host-plugin", "--across-home", str(across_home)],
            source,
            runner=runner,
            timeout=60,
        )
        return inspect_across_plugin(plugin.plugin_id, probe=True, env=source)

    npm = _which_runtime_command("npm", source)
    if not npm:
        raise PluginLifecycleError(f"npm is required to install {plugin.display_name} when no existing command is available")

    install_source = _install_source(plugin, source)
    if not install_source:
        raise PluginLifecycleError(f"{plugin.display_name} install source is not configured")

    cache_dir = component_cache_home(env=source) / "plugin-installers" / plugin.plugin_id
    shutil.rmtree(cache_dir, ignore_errors=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    _run_checked([npm, "install", "--prefix", str(cache_dir), install_source], source, runner=runner, timeout=180)
    installed_command = cache_dir / "node_modules" / ".bin" / plugin.command
    if not installed_command.is_file():
        raise PluginLifecycleError(f"{plugin.display_name} installed but its CLI command was not found")
    _run_checked(
        [str(installed_command), "install", "host-plugin", "--across-home", str(across_home)],
        source,
        runner=runner,
        timeout=60,
    )
    return inspect_across_plugin(plugin.plugin_id, probe=True, env=source)


def _uninstall_managed_plugin(plugin_id: str, command: str, *, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source, _runtime_boundary_issues = sanitized_product_runtime_env(env if env is not None else os.environ)
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


def _run_checked(
    args: list[str],
    env: Mapping[str, str],
    *,
    runner: Any = subprocess.run,
    timeout: int = 900,
) -> None:
    safe_env = _child_env_with_product_boundary(env)
    safe_env.setdefault("ACROSS_HOME", str(ecosystem_home(safe_env)))
    safe_env.setdefault("ACROSS_PLUGIN_HOME", str(ecosystem_plugin_root(safe_env)))
    safe_env.setdefault("ACROSS_BIN_HOME", str(ecosystem_bin_dir(safe_env)))
    npm_cache = component_cache_home(env=safe_env) / "npm"
    npm_cache.mkdir(parents=True, exist_ok=True)
    safe_env.setdefault("NPM_CONFIG_CACHE", str(npm_cache))
    completed = runner(
        args,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        env=safe_env,
        check=False,
    )
    if int(getattr(completed, "returncode", 1)) != 0:
        raise PluginLifecycleError("Plugin lifecycle command failed")


def _safe_plugin_env(env: Mapping[str, str]) -> dict[str, str]:
    safe_env = _child_env_with_product_boundary(env)
    safe_env.setdefault("ACROSS_HOME", str(ecosystem_home(safe_env)))
    safe_env.setdefault("ACROSS_PLUGIN_HOME", str(ecosystem_plugin_root(safe_env)))
    safe_env.setdefault("ACROSS_BIN_HOME", str(ecosystem_bin_dir(safe_env)))
    return safe_env


def _child_env_with_product_boundary(env: Mapping[str, str]) -> dict[str, str]:
    source = os.environ.copy()
    source.update({str(key): str(value) for key, value in env.items()})
    safe_env, _runtime_boundary_issues = sanitized_product_runtime_env(source)
    return safe_env


def _run_context_cli_json(args: list[str], *, env: Mapping[str, str] | None = None, timeout: int = 15) -> Any:
    return _run_cli_json("across-context", args, env=env, timeout=timeout)


def _run_cli_json(command: str, args: list[str], *, env: Mapping[str, str] | None = None, timeout: int = 15) -> Any:
    source, _runtime_boundary_issues = sanitized_product_runtime_env(env if env is not None else os.environ)
    command_path = _resolve_command(command, source)
    if not command_path.is_file() or not os.access(command_path, os.X_OK):
        raise PluginLifecycleError(f"{command} plugin is not installed")
    plugin_id = command if command.startswith("across-") else command
    integrity_issues = _command_integrity_issues(command_path, ecosystem_plugin_root(source) / plugin_id, source)
    if integrity_issues:
        raise PluginLifecycleError(f"{command} plugin must be repaired because its runtime is not self-contained")
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
        raise PluginLifecycleError(f"{command} command failed")
    try:
        return json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise PluginLifecycleError(f"{command} returned invalid JSON") from exc


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.expanduser().resolve().relative_to(root.expanduser().resolve())
        return True
    except Exception:
        return False


def _contains_protected_user_reference(value: str) -> bool:
    return contains_protected_user_reference(value)


def _command_integrity_issues(command_path: Path, plugin_dir: Path, env: Mapping[str, str]) -> list[str]:
    issues: list[str] = []
    bin_dir = ecosystem_bin_dir(env)
    resolved = command_path.expanduser().resolve()
    if not (_is_relative_to(resolved, bin_dir) or _is_relative_to(resolved, plugin_dir)):
        issues.append("command is outside the Across plugin runtime directory")
    if _contains_protected_user_reference(str(resolved)):
        issues.append("command path references a protected user directory")
    try:
        if command_path.stat().st_size <= 64 * 1024:
            text = command_path.read_text(encoding="utf-8", errors="ignore")
            if _contains_protected_user_reference(text):
                issues.append("command wrapper references a protected user directory")
    except Exception:
        pass
    return issues


def _plugin_dir_integrity_issues(plugin_id: str, plugin_dir: Path) -> list[str]:
    if plugin_id != "across-orchestrator":
        return []
    issues: list[str] = []
    install_root = plugin_dir.expanduser().resolve()
    venv_root = (plugin_dir / "venv").expanduser().resolve()

    source_dir = plugin_dir / "source"
    if source_dir.exists():
        issues.append("source directory remains under plugin runtime")
        if (source_dir / "src" / "across_agents_assistant").exists() or any(
            path.name == "across_agents_assistant" for path in source_dir.rglob("across_agents_assistant")
        ):
            issues.append("stale Across Agents Assistant source tree remains under plugin runtime")

    for path in plugin_dir.rglob("across_agents_assistant"):
        if path.exists():
            issues.append("stale Across Agents Assistant source tree remains under plugin runtime")
            break

    for path in (plugin_dir / "venv").glob("lib/python*/site-packages/*.pth"):
        issues.extend(_pth_integrity_issues(path, venv_root))

    for path in (plugin_dir / "venv").glob("lib/python*/site-packages/*.dist-info/direct_url.json"):
        issues.extend(_direct_url_integrity_issues(path, install_root))

    return sorted(set(issues))


def _pth_integrity_issues(path: Path, venv_root: Path) -> list[str]:
    issues: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return issues
    for line in lines:
        value = line.strip()
        if not value or value.startswith("#") or value.startswith("import "):
            continue
        if _contains_protected_user_reference(value):
            issues.append(f"{path.name} references a protected user directory")
        candidate = Path(value).expanduser()
        if candidate.is_absolute() and not _is_relative_to(candidate, venv_root):
            issues.append(f"{path.name} adds import path outside plugin virtualenv")
    return issues


def _direct_url_integrity_issues(path: Path, install_root: Path) -> list[str]:
    issues: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return issues
    if not isinstance(payload, dict):
        return issues
    dir_info = payload.get("dir_info")
    if isinstance(dir_info, dict) and dir_info.get("editable"):
        issues.append(f"{path.name} records an editable install")
    url = str(payload.get("url") or "")
    if _contains_protected_user_reference(url):
        issues.append(f"{path.name} references a protected user directory")
    if url.startswith("file:"):
        parsed = urllib.parse.urlparse(url)
        local_path = Path(urllib.parse.unquote(parsed.path)).expanduser()
        if local_path.is_absolute() and not _is_relative_to(local_path, install_root):
            issues.append(f"{path.name} references local source outside plugin directory")
    return issues


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
