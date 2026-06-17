from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import atexit
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.error
import urllib.request
import uuid

from .paths import app_subdir, ecosystem_bin_dir, ecosystem_home, ecosystem_plugin_root
from .runtime_boundary import (
    contains_protected_user_reference,
    expand_user,
    is_developer_mode,
    is_product_mode,
    safe_runtime_override,
    sanitized_product_runtime_env,
)
from .orchestrator_protocol import (
    DEFAULT_APP_GRADE_EXECUTOR_AGENTS,
    build_external_release_e2e_submission_payload as _protocol_build_external_release_e2e_submission_payload,
    build_external_task_submission_payload as _protocol_build_external_task_submission_payload,
    external_task_to_app_info as _protocol_external_task_to_app_info,
    external_task_to_summary as _protocol_external_task_to_summary,
    normalize_external_agent_ids as _protocol_normalize_external_agent_ids,
    _public_agent_card as _protocol_public_agent_card,
)
from .orchestrator_release_evidence import (
    build_external_quality_benchmark as _release_build_external_quality_benchmark,
    evaluate_app_grade_quality as _evaluate_app_grade_quality,
    external_evidence_to_app_bundle as _external_evidence_to_app_bundle_impl,
)


logger = logging.getLogger("across_agents_assistant.orchestrator_plugin")

DEFAULT_ORCHESTRATOR_INSTALL_SOURCE = "git+https://github.com/fantasyce/across-orchestrator.git@v0.6.9"
ORCHESTRATOR_PLUGIN_ID = "across-orchestrator"
ORCHESTRATOR_INSTALL_FAILED_PUBLIC_MESSAGE = (
    "Across Orchestrator plugin installation failed. See local backend logs for details."
)
ORCHESTRATOR_RUNTIME_UNAVAILABLE_PUBLIC_MESSAGE = "External Across Orchestrator runtime is unavailable."


class OrchestratorPluginError(RuntimeError):
    """Base error for external Across Orchestrator integration."""


class OrchestratorPluginUnavailable(OrchestratorPluginError):
    """Raised when external Orchestrator is required but unavailable."""


def _normalize_mode(value: Optional[str]) -> str:
    mode = str(value or "external").strip().lower().replace("-", "_")
    if mode == "external":
        return "external"
    return "external"


def _truthy(value: Optional[str], *, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _float_env(value: Optional[str], default: float) -> float:
    try:
        return max(0.1, float(value)) if value is not None else default
    except ValueError:
        return default


def _is_executable_file(path: Optional[str]) -> bool:
    if not path:
        return False
    candidate = Path(str(path)).expanduser()
    return candidate.is_file() and os.access(candidate, os.X_OK)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.expanduser().resolve().relative_to(root.expanduser().resolve())
        return True
    except Exception:
        return False


def _protected_user_reference_roots(env: Optional[Dict[str, str]] = None) -> List[Path]:
    source = env if env is not None else os.environ
    configured_home = str(source.get("HOME") or "").strip()
    home = Path(configured_home).expanduser() if configured_home else Path.home()
    return [home / "Documents", home / "Desktop", home / "Downloads"]


def _contains_protected_user_reference(value: str, env: Optional[Dict[str, str]] = None) -> bool:
    if contains_protected_user_reference(value, env):
        return True
    text = expand_user(str(value or ""), env)
    try:
        roots = _protected_user_reference_roots(env)
    except TypeError:
        roots = _protected_user_reference_roots()  # type: ignore[call-arg]
    return any(_references_path_root(text, root) for root in roots)


def _references_path_root(text: str, root: Path) -> bool:
    root_text = str(root)
    if not root_text:
        return False
    return bool(re.search(re.escape(root_text) + r"(?:/|$)", text))


def _allow_development_command_override(env: Optional[Dict[str, str]] = None) -> bool:
    return is_developer_mode(env)


def _is_blocked_product_path(value: str, env: Optional[Dict[str, str]] = None) -> bool:
    return is_product_mode(env) and not is_developer_mode(env) and _contains_protected_user_reference(value, env)


def _is_safe_python_executable(path: str, env: Optional[Dict[str, str]] = None) -> bool:
    if _is_blocked_product_path(path, env):
        return False
    if not _is_executable_file(path):
        return False
    return True


SUPPORTED_PYTHON_MIN_VERSION = (3, 11)
SUPPORTED_PYTHON_MAX_EXCLUSIVE_VERSION = (3, 14)


def _parse_python_version_text(value: str) -> Optional[tuple[int, int]]:
    match = re.search(r"Python\s+(\d+)\.(\d+)", value or "")
    if not match:
        match = re.search(r"python(\d+)\.(\d+)", value or "", re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _python_executable_version(path: str) -> Optional[tuple[int, int]]:
    version = _parse_python_version_text(Path(path).name)
    if version:
        return version
    try:
        completed = subprocess.run(
            [path, "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            check=False,
        )
    except Exception:
        return None
    return _parse_python_version_text(f"{completed.stdout}\n{completed.stderr}")


def _is_supported_python_executable(path: str, env: Optional[Dict[str, str]] = None) -> bool:
    if not _is_safe_python_executable(path, env):
        return False
    version = _python_executable_version(path)
    if version is None:
        return Path(path).name in {"python3", "python"}
    return SUPPORTED_PYTHON_MIN_VERSION <= version < SUPPORTED_PYTHON_MAX_EXCLUSIVE_VERSION


def _python_search_path(env: Optional[Dict[str, str]] = None) -> str:
    source = env if env is not None else os.environ
    env_path = source.get("PATH") or ""
    extras = [
        expand_user("~/.local/bin", source),
        "/opt/homebrew/bin",
        "/opt/homebrew/sbin",
        "/usr/local/bin",
        "/usr/local/sbin",
        "/usr/bin",
        "/bin",
    ]
    paths = []
    for item in env_path.split(os.pathsep):
        expanded_item = expand_user(item, source)
        if expanded_item and not _is_blocked_product_path(str(Path(expanded_item) / ".__across_probe__"), source):
            paths.append(expanded_item)
    for item in extras:
        if item not in paths:
            paths.append(item)
    return os.pathsep.join(paths)


def _which_executable(
    command: str,
    search_path: str,
    env: Optional[Dict[str, str]] = None,
    *,
    block_protected_user_path: bool = False,
) -> Optional[str]:
    source = env if env is not None else os.environ
    if os.path.isabs(command) or os.sep in command:
        if (
            _is_blocked_product_path(command, source)
            or (
                block_protected_user_path
                and not is_developer_mode(source)
                and _contains_protected_user_reference(command, source)
            )
        ):
            return None
        candidate = Path(expand_user(command, source))
        return str(candidate) if candidate.is_file() and os.access(candidate, os.X_OK) else None
    paths: list[str] = []
    for item in str(search_path or "").split(os.pathsep):
        if not item:
            continue
        expanded_item = expand_user(item, source)
        candidate = Path(expanded_item) / command
        if (
            _is_blocked_product_path(str(candidate), source)
            or (
                block_protected_user_path
                and not is_developer_mode(source)
                and _contains_protected_user_reference(str(candidate), source)
            )
        ):
            continue
        paths.append(expanded_item)
    return shutil.which(command, path=os.pathsep.join(paths))


def _sanitize_python_child_env(env: Dict[str, str]) -> Dict[str, str]:
    """Remove parent Python launcher state before spawning plugin runtimes.

    Packaged AAA backends are PyInstaller processes. If ``_PYI_*`` or
    ``__PYVENV_LAUNCHER__`` leak into a child venv Python process, that child can
    mis-detect itself as a PyInstaller child and hang during import/bootstrap.
    """

    clean = dict(env)
    for key in list(clean):
        if key.startswith("_PYI_"):
            clean.pop(key, None)
    for key in (
        "__PYVENV_LAUNCHER__",
        "PYTHONEXECUTABLE",
        "PYTHONHOME",
        "PYTHONPATH",
        "PYINSTALLER_RESET_ENVIRONMENT",
    ):
        clean.pop(key, None)
    return clean


def _resolve_python_executable(explicit: Optional[str] = None) -> str:
    """Find a real Python interpreter for plugin venv creation.

    In PyInstaller bundles ``sys.executable`` is the backend binary, not Python.
    Running ``backend -m venv`` starts another backend process and never creates
    the requested virtualenv, so packaged installs must discover Python
    explicitly.
    """

    source = os.environ
    configured = (explicit or source.get("ACROSS_AGENTS_ORCHESTRATOR_PYTHON") or "").strip()
    if _is_supported_python_executable(configured, source):
        return str(Path(configured).expanduser())

    sys_executable = str(getattr(sys, "executable", "") or "")
    sys_name = Path(sys_executable).name.lower()
    if (
        not bool(getattr(sys, "frozen", False))
        and "python" in sys_name
        and _is_supported_python_executable(sys_executable, source)
    ):
        return sys_executable

    search_path = _python_search_path(source)
    candidate_names = [
        "python3.11",
        "python3.12",
        "python3.13",
        "python3",
    ]
    for name in candidate_names:
        resolved = _which_executable(name, search_path, source)
        if _is_supported_python_executable(resolved or "", source):
            return str(Path(resolved).expanduser())

    fixed_paths = [
        Path.home() / ".local" / "bin" / "python3.11",
        Path("/opt/homebrew/bin/python3.11"),
        Path("/usr/local/bin/python3.11"),
        Path.home() / ".local" / "bin" / "python3",
        Path("/opt/homebrew/bin/python3"),
        Path("/usr/local/bin/python3"),
        Path("/usr/bin/python3"),
    ]
    for path in fixed_paths:
        if _is_supported_python_executable(str(path), source):
            return str(path)

    raise OrchestratorPluginUnavailable(
        "No supported Python 3.11-3.13 interpreter was found for installing Across Orchestrator. "
        "Set ACROSS_AGENTS_ORCHESTRATOR_PYTHON to a Python executable."
    )


@dataclass
class OrchestratorPluginConfig:
    mode: str = "external"
    endpoint: Optional[str] = None
    command: str = "across-orchestrator"
    registry_path: Optional[Path] = None
    plugin_home: Optional[Path] = None
    install_source: str = DEFAULT_ORCHESTRATOR_INSTALL_SOURCE
    connect_timeout: float = 5.0
    operation_timeout: float = 180.0
    auto_run: bool = True

    @classmethod
    def from_env(cls, registry_path: Optional[Path] = None) -> "OrchestratorPluginConfig":
        plugin_home = (safe_runtime_override("ACROSS_AGENTS_ORCHESTRATOR_PLUGIN_HOME") or "").strip()
        install_source = (
            safe_runtime_override("ACROSS_AGENTS_ORCHESTRATOR_INSTALL_SOURCE")
            or DEFAULT_ORCHESTRATOR_INSTALL_SOURCE
        ).strip() or DEFAULT_ORCHESTRATOR_INSTALL_SOURCE
        command = (safe_runtime_override("ACROSS_AGENTS_ORCHESTRATOR_COMMAND") or "across-orchestrator").strip()
        if not command:
            command = "across-orchestrator"
        return cls(
            mode=_normalize_mode(os.environ.get("ACROSS_AGENTS_ORCHESTRATOR_MODE")),
            endpoint=(os.environ.get("ACROSS_AGENTS_ORCHESTRATOR_ENDPOINT") or "").strip() or None,
            command=command,
            registry_path=registry_path,
            plugin_home=Path(plugin_home).expanduser() if plugin_home else None,
            install_source=install_source,
            connect_timeout=_float_env(os.environ.get("ACROSS_AGENTS_ORCHESTRATOR_CONNECT_TIMEOUT"), 5.0),
            operation_timeout=_float_env(os.environ.get("ACROSS_AGENTS_ORCHESTRATOR_OPERATION_TIMEOUT"), 180.0),
            auto_run=_truthy(os.environ.get("ACROSS_AGENTS_ORCHESTRATOR_AUTORUN"), default=True),
        )

    def normalized_mode(self) -> str:
        return _normalize_mode(self.mode)


class OrchestratorPluginInstaller:
    """Installs Across Orchestrator into an app-managed Python virtualenv."""

    def __init__(
        self,
        *,
        plugin_home: Optional[Path] = None,
        source: str = DEFAULT_ORCHESTRATOR_INSTALL_SOURCE,
        runner: Callable[..., Any] = subprocess.run,
        python_executable: Optional[str] = None,
        timeout: float = 900.0,
    ):
        self.plugin_home = Path(plugin_home).expanduser() if plugin_home else ecosystem_plugin_root()
        self.bin_dir = self.plugin_home.parent / "bin" if plugin_home else ecosystem_bin_dir()
        self.source = source or DEFAULT_ORCHESTRATOR_INSTALL_SOURCE
        self.runner = runner
        self.python_executable = _resolve_python_executable(python_executable)
        self.timeout = timeout
        self.install_dir = self.plugin_home / ORCHESTRATOR_PLUGIN_ID
        self.venv_dir = self.install_dir / "venv"
        self.command_path = self.venv_dir / "bin" / "across-orchestrator"
        self.wrapper_path = self.bin_dir / "across-orchestrator"
        self.manifest_path = self.install_dir / "manifest.json"
        self.state_path = self.install_dir / "install-state.json"

    def status(self) -> Dict[str, Any]:
        state = self._read_state()
        command_installed = self.command_path.is_file() and os.access(self.command_path, os.X_OK)
        wrapper_installed = self.wrapper_path.is_file() and os.access(self.wrapper_path, os.X_OK)
        integrity_issues = self._runtime_integrity_issues() if command_installed else []
        installed = command_installed and not integrity_issues
        status = "installed" if installed else str(state.get("status") or "not_installed")
        if command_installed and integrity_issues:
            status = "needs_repair"
        actual_source = self._actual_install_source()
        return {
            "plugin_id": ORCHESTRATOR_PLUGIN_ID,
            "status": status,
            "installed": installed,
            "wrapper_installed": wrapper_installed,
            "installable": True,
            "source": actual_source or str(state.get("source") or self.source),
            "install_dir": str(self.install_dir),
            "venv_dir": str(self.venv_dir),
            "command": str(self.command_path),
            "wrapper": str(self.wrapper_path),
            "manifest": str(self.manifest_path),
            "python": self.python_executable,
            "integrity_ok": not integrity_issues,
            "integrity_issues": integrity_issues,
            "logs": list(state.get("logs") or [])[-20:],
            "updated_at": state.get("updated_at"),
            "error": ORCHESTRATOR_INSTALL_FAILED_PUBLIC_MESSAGE if state.get("error") else None,
        }

    def install(self) -> Dict[str, Any]:
        logs: List[str] = []
        self.install_dir.mkdir(parents=True, exist_ok=True)
        logs.append(f"Using Python: {self.python_executable}")
        self._write_state({"status": "installing", "logs": logs, "updated_at": time.time()})

        try:
            self._remove_stale_runtime_artifacts(logs)
            self._run([self.python_executable, "-m", "venv", str(self.venv_dir)], logs, "Create virtualenv")
            venv_python = str(self.venv_dir / "bin" / "python")
            self._run([venv_python, "-m", "pip", "install", "--upgrade", "pip"], logs, "Upgrade pip")
            self._run([venv_python, "-m", "pip", "install", "--upgrade", self.source], logs, "Install Across Orchestrator")

            if not (self.command_path.is_file() and os.access(self.command_path, os.X_OK)):
                raise OrchestratorPluginError(
                    f"Across Orchestrator installed but executable was not found at {self.command_path}"
                )
            self._write_wrapper()
            self._write_manifest(logs)
            self._assert_runtime_self_contained()
            state = {
                "status": "installed",
                "logs": logs,
                "source": self.source,
                "command": str(self.command_path),
                "wrapper": str(self.wrapper_path),
                "manifest": str(self.manifest_path),
                "updated_at": time.time(),
            }
            self._write_state(state)
            return self.status()
        except Exception as exc:
            logger.exception("Across Orchestrator plugin installation failed")
            logs.append(ORCHESTRATOR_INSTALL_FAILED_PUBLIC_MESSAGE)
            self._write_state(
                {
                    "status": "failed",
                    "logs": logs,
                    "source": self.source,
                    "error": ORCHESTRATOR_INSTALL_FAILED_PUBLIC_MESSAGE,
                    "updated_at": time.time(),
                }
            )
            raise

    def _remove_stale_runtime_artifacts(self, logs: List[str]) -> None:
        stale_dirs = [
            (self.venv_dir, "Remove stale virtualenv"),
            (self.install_dir / "source", "Remove stale source checkout"),
            (self.install_dir / "src", "Remove stale source tree"),
            (self.install_dir / "build", "Remove stale build directory"),
        ]
        for path, label in stale_dirs:
            if path.exists():
                logs.append(label)
                shutil.rmtree(path)

    def uninstall(self) -> Dict[str, Any]:
        shutil.rmtree(self.install_dir, ignore_errors=True)
        try:
            self.wrapper_path.unlink()
        except FileNotFoundError:
            pass
        return {
            "plugin_id": ORCHESTRATOR_PLUGIN_ID,
            "status": "not_installed",
            "removed": True,
            "install_dir": str(self.install_dir),
            "wrapper": str(self.wrapper_path),
            "preserved_data": str(ecosystem_home() / "data" / ORCHESTRATOR_PLUGIN_ID),
        }

    def _run(self, args: List[str], logs: List[str], label: str) -> None:
        logs.append(label)
        completed = self.runner(
            args,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=self.timeout,
            env=self._env(),
            check=False,
        )
        stdout = str(getattr(completed, "stdout", "") or "").strip()
        stderr = str(getattr(completed, "stderr", "") or "").strip()
        if stdout:
            logs.append(stdout[-1000:])
        if stderr:
            logs.append(stderr[-1000:])
        if int(getattr(completed, "returncode", 1)) != 0:
            logger.warning("%s failed during Across Orchestrator plugin installation: %s", label, (stderr or stdout)[:1000])
            raise OrchestratorPluginError(f"{label} failed")

    def _read_state(self) -> Dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _write_state(self, payload: Dict[str, Any]) -> None:
        self.install_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.state_path)

    def _write_wrapper(self) -> None:
        self.bin_dir.mkdir(parents=True, exist_ok=True)
        script = "#!/bin/sh\nexec \"{}\" \"$@\"\n".format(str(self.command_path).replace('"', '\\"'))
        self.wrapper_path.write_text(script, encoding="utf-8")
        self.wrapper_path.chmod(0o755)

    def _assert_runtime_self_contained(self) -> None:
        issues = self._runtime_integrity_issues()
        if issues:
            raise OrchestratorPluginError("Across Orchestrator plugin runtime is not self-contained.")

    def _runtime_integrity_issues(self) -> List[str]:
        issues: List[str] = []
        install_root = self.install_dir.resolve()
        venv_root = self.venv_dir.resolve()

        for path in (self.wrapper_path, self.command_path, self.venv_dir / "pyvenv.cfg"):
            if path.exists():
                issues.extend(self._text_file_integrity_issues(path, install_root, venv_root))

        for path in self.venv_dir.glob("lib/python*/site-packages/*.pth"):
            issues.extend(self._pth_integrity_issues(path, install_root, venv_root))

        for path in self.venv_dir.glob("lib/python*/site-packages/*.dist-info/direct_url.json"):
            issues.extend(self._direct_url_integrity_issues(path, install_root, venv_root))

        issues.extend(self._source_tree_integrity_issues())

        return issues

    def _source_tree_integrity_issues(self) -> List[str]:
        issues: List[str] = []
        source_dir = self.install_dir / "source"
        if source_dir.exists():
            issues.append("source directory remains under plugin runtime")
            if (source_dir / "src" / "across_agents_assistant").exists() or any(
                path.name == "across_agents_assistant" for path in source_dir.rglob("across_agents_assistant")
            ):
                issues.append("stale Across Agents Assistant source tree remains under plugin runtime")

        for path in self.install_dir.rglob("across_agents_assistant"):
            if path.exists():
                issues.append("stale Across Agents Assistant source tree remains under plugin runtime")
                break

        return sorted(set(issues))

    def _text_file_integrity_issues(self, path: Path, install_root: Path, venv_root: Path) -> List[str]:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return []
        if _contains_protected_user_reference(text):
            return [f"{path.name} references a protected user directory"]
        return []

    def _pth_integrity_issues(self, path: Path, install_root: Path, venv_root: Path) -> List[str]:
        issues = self._text_file_integrity_issues(path, install_root, venv_root)
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            return issues
        for line in lines:
            value = line.strip()
            if not value or value.startswith("#") or value.startswith("import "):
                continue
            candidate = Path(value).expanduser()
            if candidate.is_absolute() and not _is_relative_to(candidate, venv_root):
                issues.append(f"{path.name} adds import path outside plugin virtualenv")
        return issues

    def _direct_url_integrity_issues(self, path: Path, install_root: Path, venv_root: Path) -> List[str]:
        issues: List[str] = []
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
        if url.startswith("file:"):
            parsed = urllib.parse.urlparse(url)
            local_path = Path(urllib.parse.unquote(parsed.path)).expanduser()
            if local_path.is_absolute() and not _is_relative_to(local_path, install_root):
                issues.append(f"{path.name} references local source outside plugin directory")
        return issues

    def _actual_install_source(self) -> Optional[str]:
        install_root = self.install_dir.resolve()
        patterns = (
            "lib/python*/site-packages/across_orchestrator*.dist-info/direct_url.json",
            "lib/python*/site-packages/across-orchestrator*.dist-info/direct_url.json",
        )
        for pattern in patterns:
            for path in sorted(self.venv_dir.glob(pattern)):
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

    def _write_manifest(self, logs: List[str]) -> None:
        try:
            completed = self.runner(
                [str(self.command_path), "plugin-manifest", "--json"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                env=self._env(),
                check=False,
            )
            if int(getattr(completed, "returncode", 1)) != 0:
                raise OrchestratorPluginError(str(getattr(completed, "stderr", "") or "").strip())
            manifest = json.loads(str(getattr(completed, "stdout", "") or "{}"))
        except Exception:
            logger.info("Plugin manifest probe failed; writing host manifest", exc_info=True)
            logs.append("Plugin manifest probe failed; writing host manifest.")
            manifest = {
                "schemaVersion": "1.0",
                "id": ORCHESTRATOR_PLUGIN_ID,
                "kind": "task-runtime",
                "entrypoints": {
                    "sidecar": {"command": str(self.wrapper_path), "args": ["serve", "--host", "127.0.0.1"]},
                    "cli": {"command": str(self.wrapper_path)},
                    "mcp": {"command": str(self.wrapper_path), "args": ["mcp"]},
                },
            }
        self.install_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    def _env(self) -> Dict[str, str]:
        env = _sanitize_python_child_env(os.environ.copy())
        env, _runtime_boundary_issues = sanitized_product_runtime_env(env)
        env.setdefault("ACROSS_HOME", str(ecosystem_home()))
        env.setdefault("ACROSS_PLUGIN_HOME", str(ecosystem_plugin_root()))
        env.setdefault("ACROSS_BIN_HOME", str(ecosystem_bin_dir()))
        return env


class OrchestratorTaskIndex:
    """Thin app-owned index of task ids that live in Across Orchestrator."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def _read(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": "1.0", "tasks": []}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"schema_version": "1.0", "tasks": []}
            payload.setdefault("schema_version", "1.0")
            payload.setdefault("tasks", [])
            return payload
        except Exception:
            return {"schema_version": "1.0", "tasks": []}

    def _write(self, payload: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)

    def remember(self, task: Dict[str, Any], *, transport: str, endpoint: Optional[str]) -> None:
        task_id = str(task.get("task_id") or "")
        if not task_id:
            return
        record = external_task_to_summary(task)
        record.update(
            {
                "implementation": "external",
                "source": "across_orchestrator",
                "transport": transport,
                "endpoint": endpoint,
            }
        )
        with self._lock:
            payload = self._read()
            tasks = [item for item in payload.get("tasks", []) if item.get("task_id") != task_id]
            tasks.insert(0, record)
            payload["tasks"] = tasks[:200]
            self._write(payload)

    def contains(self, task_id: str) -> bool:
        return any(item.get("task_id") == task_id for item in self.list_records())

    def list_records(self) -> List[Dict[str, Any]]:
        with self._lock:
            payload = self._read()
        return [dict(item) for item in payload.get("tasks", []) if isinstance(item, dict)]


class OrchestratorPluginManager:
    """Protocol client for the independent Across Orchestrator product."""

    def __init__(self, config: Optional[OrchestratorPluginConfig] = None):
        self.config = config or OrchestratorPluginConfig.from_env()
        registry_path = self.config.registry_path or app_subdir("orchestrator-plugin") / "tasks.json"
        self.index = OrchestratorTaskIndex(registry_path)
        self.installer = OrchestratorPluginInstaller(
            plugin_home=self.config.plugin_home,
            source=self.config.install_source,
            timeout=max(self.config.operation_timeout, 900.0),
        )
        self._transport: Optional[str] = None
        self._endpoint: Optional[str] = None
        self._sidecar_process: Optional[subprocess.Popen] = None
        self._sidecar_runtime_id = f"aaa-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        atexit.register(self.shutdown)

    def implementation_status(self, *, probe: bool = True) -> Dict[str, Any]:
        mode = self.config.normalized_mode()
        install_status = self.install_status()
        command_path = self._resolve_command() if install_status.get("integrity_ok", True) else None
        base: Dict[str, Any] = {
            "mode": mode,
            "implementation": "external",
            "available": False,
            "transport": None,
            "endpoint": self.config.endpoint,
            "command": self.config.command,
            "command_available": command_path is not None,
            "task_index_count": len(self.index.list_records()),
            "install": install_status,
            "connection_note": "External Across Orchestrator is required but no endpoint or executable was found.",
        }

        if install_status.get("integrity_ok") is False:
            return {
                **base,
                "implementation": "external",
                "available": False,
                "command_available": False,
                "connection_note": "Across Orchestrator plugin must be repaired because its runtime is not self-contained.",
                "error": "across-orchestrator plugin needs repair",
            }

        if self.config.endpoint:
            try:
                if probe:
                    self._http_get("/health")
                    card = self._http_get("/.well-known/agent-card.json")
                else:
                    card = {}
                self._transport = "http"
                self._endpoint = self.config.endpoint.rstrip("/")
                return {
                    **base,
                    "implementation": "external",
                    "available": True,
                    "transport": "http",
                    "endpoint": self._endpoint,
                    "agent_card": _public_agent_card(card),
                    "connection_note": "External Across Orchestrator HTTP runtime.",
                }
            except Exception as exc:
                logger.info("External Across Orchestrator HTTP runtime probe failed", exc_info=True)
                return {
                    **base,
                    "implementation": "external",
                    "available": False,
                    "transport": "http",
                    "connection_note": ORCHESTRATOR_RUNTIME_UNAVAILABLE_PUBLIC_MESSAGE,
                    "error": ORCHESTRATOR_RUNTIME_UNAVAILABLE_PUBLIC_MESSAGE,
                }

        if command_path:
            try:
                endpoint = self._ensure_sidecar(command_path) if probe else self._runtime_info_endpoint()
                if endpoint:
                    self._transport = "http"
                    self._endpoint = endpoint.rstrip("/")
                    card = self._http_get("/.well-known/agent-card.json") if probe else {}
                    return {
                        **base,
                        "implementation": "external",
                        "available": True,
                        "transport": "http",
                        "endpoint": self._endpoint,
                        "command": command_path,
                        "command_available": True,
                        "agent_card": _public_agent_card(card),
                        "connection_note": "External Across Orchestrator sidecar runtime.",
                    }
            except Exception:
                logger.info("External Across Orchestrator sidecar probe failed", exc_info=True)

            try:
                card = self._cli_json(["agent-card", "--json"]) if probe else {}
                self._transport = "cli"
                self._endpoint = None
                return {
                    **base,
                    "implementation": "external",
                    "available": True,
                    "transport": "cli",
                    "command": command_path,
                    "command_available": True,
                    "agent_card": _public_agent_card(card),
                    "connection_note": "External Across Orchestrator CLI runtime.",
                }
            except Exception as exc:
                logger.info("External Across Orchestrator CLI runtime probe failed", exc_info=True)
                return {
                    **base,
                    "implementation": "external",
                    "available": False,
                    "transport": "cli",
                    "command": command_path,
                    "connection_note": ORCHESTRATOR_RUNTIME_UNAVAILABLE_PUBLIC_MESSAGE,
                    "error": ORCHESTRATOR_RUNTIME_UNAVAILABLE_PUBLIC_MESSAGE,
                }

        return {
            **base,
            "implementation": "external",
            "available": False,
            "connection_note": "External Across Orchestrator is required but no endpoint or executable was found.",
            "error": "across-orchestrator not found",
        }

    def install_status(self) -> Dict[str, Any]:
        return self.installer.status()

    def install_plugin(self) -> Dict[str, Any]:
        status = self.installer.install()
        self._transport = None
        self._endpoint = None
        return status

    def uninstall_plugin(self) -> Dict[str, Any]:
        self.shutdown()
        status = self.installer.uninstall()
        self._transport = None
        self._endpoint = None
        return status

    def should_use_external(self) -> bool:
        status = self.implementation_status(probe=True)
        return status.get("implementation") == "external" and bool(status.get("available"))

    def is_external_task(self, task_id: str) -> bool:
        return self.index.contains(task_id)

    def submit_task(
        self,
        *,
        goal: str,
        project_dir: str,
        deliverables: Optional[List[str]] = None,
        agent: Optional[str] = None,
        subtasks: Optional[List[Dict[str, Any]]] = None,
        strict_dependency: bool = False,
        task_types: Optional[List[str]] = None,
        agent_adapters: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        self._ensure_external()
        deliverables = deliverables or ["README.md"]
        agent = agent or "demo"
        payload = _protocol_build_external_task_submission_payload(
            goal=goal,
            project_root=project_dir,
            deliverables=deliverables,
            agent=agent,
            strict_dependency=strict_dependency,
            task_types=task_types,
            subtasks=subtasks,
            agent_adapters=agent_adapters,
        )
        if self._transport == "http":
            task = self._http_post("/tasks", payload)
        else:
            args = ["submit", goal, "--project", project_dir, "--agent", agent]
            for deliverable in deliverables or ["README.md"]:
                args.extend(["--deliverable", deliverable])
            for task_type in payload.get("taskTypes", []):
                args.extend(["--task-type", task_type])
            if strict_dependency:
                args.append("--strict-dependency")
            if subtasks:
                args.extend([
                    "--subtasks-json",
                    json.dumps(subtasks, ensure_ascii=False, separators=(",", ":")),
                ])
            if agent_adapters:
                args.extend([
                    "--agent-adapters-json",
                    json.dumps(agent_adapters, ensure_ascii=False, separators=(",", ":")),
                ])
            args.append("--json")
            task = self._cli_json(args)
        self.index.remember(task, transport=self._transport or "unknown", endpoint=self._endpoint)
        if self.config.auto_run:
            self.start_task_async(str(task.get("task_id") or ""))
        return task

    def submit_release_e2e_task(
        self,
        *,
        project_dir: str,
        run_label: Optional[str] = None,
        allowed_subtask_agents: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        self._ensure_external()
        clean_agents = _protocol_normalize_external_agent_ids(allowed_subtask_agents)
        if self._transport == "http":
            payload = _protocol_build_external_release_e2e_submission_payload(
                project_root=project_dir,
                run_label=run_label,
                allowed_subtask_agents=allowed_subtask_agents,
            )
            task = self._http_post("/release-e2e", payload)
        else:
            args = ["submit-release-e2e", "--project", project_dir]
            if run_label:
                args.extend(["--run-label", run_label])
            for agent in clean_agents:
                args.extend(["--allowed-agent", agent])
            args.append("--json")
            task = self._cli_json(args)
        self.index.remember(task, transport=self._transport or "unknown", endpoint=self._endpoint)
        if self.config.auto_run:
            self.start_task_async(str(task.get("task_id") or ""))
        return task

    def start_task_async(self, task_id: str) -> None:
        if not task_id:
            return

        def _run() -> None:
            try:
                self.run_task(task_id)
            except Exception:
                # The status endpoint will expose the task as still pending if the
                # external runtime rejects the run. Avoid crashing the backend.
                return

        threading.Thread(target=_run, name=f"across-orchestrator-run-{task_id}", daemon=True).start()

    def run_task(self, task_id: str) -> Dict[str, Any]:
        self._ensure_external()
        if self._transport == "http":
            task = self._http_post(f"/tasks/{task_id}/run", {})
        else:
            task = self._cli_json(["run", task_id, "--json"])
        self.index.remember(task, transport=self._transport or "unknown", endpoint=self._endpoint)
        return task

    def get_task(self, task_id: str) -> Dict[str, Any]:
        self._ensure_external()
        if self._transport == "http":
            task = self._http_get(f"/tasks/{task_id}")
        else:
            task = self._cli_json(["status", task_id, "--json"])
        self.index.remember(task, transport=self._transport or "unknown", endpoint=self._endpoint)
        return task

    def get_events(self, task_id: str) -> List[Dict[str, Any]]:
        self._ensure_external()
        if self._transport == "http":
            events = self._http_get(f"/tasks/{task_id}/events")
        else:
            events = self._cli_json(["events", task_id, "--json"])
        return events if isinstance(events, list) else []

    def get_evidence_bundle(self, task_id: str) -> Dict[str, Any]:
        self._ensure_external()
        if self._transport == "http":
            return self._http_get(f"/tasks/{task_id}/evidence-bundle")
        return self._cli_json(["evidence", task_id, "--json"])

    def get_quality_benchmark(self, task_id: str) -> Dict[str, Any]:
        evidence = self.get_evidence_bundle(task_id)
        return build_external_quality_benchmark(evidence, benchmark_id=f"external-{task_id}-quality")

    def start_agent_loop(
        self,
        *,
        goal: str,
        project_dir: str,
        agent: str = "owner",
        max_turns: int = 8,
        memory_policy: Optional[Dict[str, Any]] = None,
        approval_policy: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self._ensure_external()
        payload = {
            "goal": goal,
            "projectRoot": project_dir,
            "agent": agent or "owner",
            "maxTurns": max_turns or 8,
        }
        if memory_policy:
            payload["memoryPolicy"] = memory_policy
        if approval_policy:
            payload["approvalPolicy"] = approval_policy
        if metadata:
            payload["metadata"] = metadata
        if self._transport == "http":
            return self._http_post("/loops", payload)
        args = [
            "loop-start",
            goal,
            "--project",
            project_dir,
            "--agent",
            agent or "owner",
            "--max-turns",
            str(max_turns or 8),
        ]
        if memory_policy:
            args.extend(["--memory-policy-json", json.dumps(memory_policy, sort_keys=True)])
        if approval_policy:
            args.extend(["--approval-policy-json", json.dumps(approval_policy, sort_keys=True)])
        if metadata:
            args.extend(["--metadata-json", json.dumps(metadata, sort_keys=True)])
        for action in (approval_policy or {}).get("requireApprovalFor") or []:
            args.extend(["--require-approval-for", str(action)])
        args.append("--json")
        return self._cli_json(args)

    def run_agent_loop(self, loop_id: str) -> Dict[str, Any]:
        self._ensure_external()
        if self._transport == "http":
            return self._http_post(f"/loops/{loop_id}/run", {})
        return self._cli_json(["loop-run", loop_id, "--json"])

    def approve_agent_loop_action(self, loop_id: str, action_id: str) -> Dict[str, Any]:
        self._ensure_external()
        if self._transport == "http":
            return self._http_post(f"/loops/{loop_id}/actions/{action_id}/approve", {})
        return self._cli_json(["loop-approve", loop_id, action_id, "--json"])

    def reject_agent_loop_action(self, loop_id: str, action_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
        self._ensure_external()
        if self._transport == "http":
            payload = {"reason": reason} if reason else {}
            return self._http_post(f"/loops/{loop_id}/actions/{action_id}/reject", payload)
        args = ["loop-reject", loop_id, action_id]
        if reason:
            args.extend(["--reason", reason])
        args.append("--json")
        return self._cli_json(args)

    def cancel_agent_loop(self, loop_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
        self._ensure_external()
        if self._transport == "http":
            payload = {"reason": reason} if reason else {}
            return self._http_post(f"/loops/{loop_id}/cancel", payload)
        args = ["loop-cancel", loop_id]
        if reason:
            args.extend(["--reason", reason])
        args.append("--json")
        return self._cli_json(args)

    def retry_agent_loop_step(self, loop_id: str, step_id: str) -> Dict[str, Any]:
        self._ensure_external()
        if self._transport == "http":
            return self._http_post(f"/loops/{loop_id}/steps/{step_id}/retry", {})
        return self._cli_json(["loop-retry", loop_id, step_id, "--json"])

    def get_agent_loop(self, loop_id: str) -> Dict[str, Any]:
        self._ensure_external()
        if self._transport == "http":
            return self._http_get(f"/loops/{loop_id}")
        return self._cli_json(["loop-status", loop_id, "--json"])

    def get_agent_loop_events(self, loop_id: str) -> List[Dict[str, Any]]:
        self._ensure_external()
        if self._transport == "http":
            events = self._http_get(f"/loops/{loop_id}/events")
        else:
            events = self._cli_json(["loop-events", loop_id, "--json"])
        return events if isinstance(events, list) else []

    def list_task_summaries(self) -> List[Dict[str, Any]]:
        summaries: List[Dict[str, Any]] = []
        for record in self.index.list_records():
            task_id = str(record.get("task_id") or "")
            if not task_id:
                continue
            try:
                task = self.get_task(task_id)
                summaries.append(external_task_to_summary(task))
            except Exception:
                fallback = dict(record)
                fallback["status"] = fallback.get("status") or "suspended"
                summaries.append(fallback)
        return summaries

    def _ensure_external(self) -> None:
        status = self.implementation_status(probe=True)
        if status.get("implementation") != "external" or not status.get("available"):
            raise OrchestratorPluginUnavailable(status.get("connection_note") or "Across Orchestrator is unavailable.")
        self._transport = str(status.get("transport") or self._transport or "")
        self._endpoint = status.get("endpoint") or self._endpoint

    def _resolve_command(self) -> Optional[str]:
        command = self.config.command
        if not command:
            return None
        env = self._env()
        if os.path.isabs(command) or os.sep in command:
            if _contains_protected_user_reference(command, env) and not _allow_development_command_override(env):
                return None
            return command if os.path.isfile(command) and os.access(command, os.X_OK) else None
        managed_command = self.installer.command_path
        if managed_command.is_file() and os.access(managed_command, os.X_OK):
            return str(managed_command)
        if self.installer.wrapper_path.is_file() and os.access(self.installer.wrapper_path, os.X_OK):
            return str(self.installer.wrapper_path)
        return _which_executable(command, env.get("PATH", ""), env, block_protected_user_path=True)

    def _env(self) -> Dict[str, str]:
        env = _sanitize_python_child_env(os.environ.copy())
        env, _runtime_boundary_issues = sanitized_product_runtime_env(env)
        extras = [
            str(ecosystem_bin_dir()),
            os.path.expanduser("~/.local/bin"),
            os.path.expanduser("~/.npm-global/bin"),
            "/opt/homebrew/bin",
            "/opt/homebrew/sbin",
            "/usr/local/bin",
            "/usr/local/sbin",
        ]
        paths = [expand_user(item, env) for item in str(env.get("PATH") or "").split(os.pathsep) if item]
        for item in extras:
            if item not in paths:
                paths.append(item)
        env["PATH"] = os.pathsep.join(paths)
        env.setdefault("ACROSS_HOME", str(ecosystem_home()))
        env.setdefault("ACROSS_PLUGIN_HOME", str(ecosystem_plugin_root()))
        env.setdefault("ACROSS_BIN_HOME", str(ecosystem_bin_dir()))
        env.setdefault("ACROSS_ORCHESTRATOR_MEMORY_PROVIDER", "across-context")
        env.setdefault("ACROSS_CONTEXT_COMMAND", str(ecosystem_bin_dir() / "across-context"))
        if is_product_mode(env):
            env.setdefault("ACROSS_ORCHESTRATOR_PRODUCT_MODE", "1")
        if is_developer_mode(env):
            env.setdefault("ACROSS_ORCHESTRATOR_DEVELOPER_MODE", "1")
        return env

    def shutdown(self) -> None:
        process = self._sidecar_process
        self._sidecar_process = None
        if not process or process.poll() is not None:
            self._unlink_sidecar_runtime_info()
            return
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        self._unlink_sidecar_runtime_info()

    def _unlink_sidecar_runtime_info(self) -> None:
        try:
            self._sidecar_runtime_info_path().unlink()
        except FileNotFoundError:
            pass

    def _sidecar_runtime_info_path(self) -> Path:
        return ecosystem_home() / "run" / ORCHESTRATOR_PLUGIN_ID / f"{self._sidecar_runtime_id}.json"

    def _runtime_info_endpoint(self) -> Optional[str]:
        path = self._sidecar_runtime_info_path()
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        endpoint = str(payload.get("endpoint") or "").strip()
        return endpoint or None

    def _ensure_sidecar(self, command_path: str) -> str:
        if self._endpoint:
            self._http_get("/health")
            return self._endpoint

        self._cleanup_stale_aaa_sidecars()

        endpoint = self._runtime_info_endpoint()
        if endpoint:
            self._endpoint = endpoint.rstrip("/")
            try:
                self._http_get("/health")
                return self._endpoint
            except Exception:
                self._endpoint = None

        if self._sidecar_process and self._sidecar_process.poll() is not None:
            self._sidecar_process = None

        runtime_info = self._sidecar_runtime_info_path()
        try:
            runtime_info.unlink()
        except FileNotFoundError:
            pass

        if self._sidecar_process is None:
            runtime_info.parent.mkdir(parents=True, exist_ok=True)
            self._sidecar_process = subprocess.Popen(
                [
                    command_path,
                    "serve",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "0",
                    "--runtime-id",
                    self._sidecar_runtime_id,
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self._env(),
                cwd="/",
            )

        deadline = time.time() + self.config.connect_timeout
        last_error: Optional[Exception] = None
        while time.time() < deadline:
            if self._sidecar_process and self._sidecar_process.poll() is not None:
                stdout, stderr = self._sidecar_process.communicate(timeout=1)
                self._sidecar_process = None
                detail = (stderr or stdout or "").strip()
                if detail:
                    logger.warning("Across Orchestrator sidecar exited before becoming healthy: %s", detail[:1000])
                raise OrchestratorPluginUnavailable("Across Orchestrator sidecar exited before becoming healthy.")
            endpoint = self._runtime_info_endpoint()
            if endpoint:
                self._endpoint = endpoint.rstrip("/")
                try:
                    self._http_get("/health")
                    return self._endpoint
                except Exception as exc:
                    logger.info("Across Orchestrator sidecar health check failed", exc_info=True)
                    last_error = exc
            time.sleep(0.1)
        if last_error is not None:
            logger.info("Across Orchestrator sidecar did not become healthy")
        raise OrchestratorPluginUnavailable("Across Orchestrator sidecar did not become healthy.")

    def _cleanup_stale_aaa_sidecars(self) -> None:
        run_root = ecosystem_home() / "run" / ORCHESTRATOR_PLUGIN_ID
        current_info = self._sidecar_runtime_info_path()
        if not run_root.exists():
            return
        for info_path in run_root.glob("*.json"):
            if info_path == current_info:
                continue
            try:
                payload = json.loads(info_path.read_text(encoding="utf-8"))
            except Exception:
                info_path.unlink(missing_ok=True)
                continue
            pid = int(payload.get("pid") or 0)
            if pid > 0 and self._is_orchestrator_sidecar_pid(pid):
                if not info_path.name.startswith("aaa-"):
                    continue
                try:
                    os.kill(pid, 15)
                except ProcessLookupError:
                    pass
                except PermissionError:
                    continue
            elif pid > 0 and self._pid_exists(pid):
                continue
            info_path.unlink(missing_ok=True)

    def _is_orchestrator_sidecar_pid(self, pid: int) -> bool:
        try:
            completed = subprocess.run(
                ["/bin/ps", "-p", str(pid), "-o", "command="],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=1,
                check=False,
            )
        except Exception:
            return False
        command = completed.stdout.strip()
        return "across-orchestrator" in command and " serve " in f" {command} "

    def _pid_exists(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    def _resolved_endpoint(self) -> str:
        endpoint = (self._endpoint or self.config.endpoint or "").rstrip("/")
        if not endpoint:
            raise OrchestratorPluginUnavailable("Across Orchestrator endpoint is not configured.")
        return endpoint

    def _http_get(self, path: str) -> Any:
        endpoint = self._resolved_endpoint()
        with urllib.request.urlopen(endpoint + path, timeout=self.config.connect_timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _http_post(self, path: str, payload: Dict[str, Any]) -> Any:
        endpoint = self._resolved_endpoint()
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            endpoint + path,
            data=data,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.operation_timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            logger.warning("Across Orchestrator HTTP request failed with %s: %s", exc.code, detail[:1000])
            raise OrchestratorPluginError(f"HTTP {exc.code}: Across Orchestrator request failed.") from exc

    def _cli_json(self, args: List[str]) -> Any:
        command = self._resolve_command()
        if not command:
            raise OrchestratorPluginUnavailable("across-orchestrator command is not installed or executable.")
        completed = subprocess.run(
            [command, *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=self.config.operation_timeout,
            env=self._env(),
            check=False,
        )
        if completed.returncode != 0:
            logger.warning(
                "Across Orchestrator CLI command failed with %s: %s",
                completed.returncode,
                (completed.stderr or completed.stdout or "").strip()[:1000],
            )
            raise OrchestratorPluginError("Across Orchestrator CLI command failed.")
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            logger.warning("Across Orchestrator CLI returned non-JSON output: %s", completed.stdout[:1000])
            raise OrchestratorPluginError("Across Orchestrator CLI returned non-JSON output.") from exc


def _public_agent_card(card: Any) -> Dict[str, Any]:
    return _protocol_public_agent_card(card)


def external_task_to_summary(task: Dict[str, Any]) -> Dict[str, Any]:
    return _protocol_external_task_to_summary(task)


def external_task_to_app_info(task: Dict[str, Any], evidence: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return _protocol_external_task_to_app_info(task, evidence=evidence)


def evaluate_app_grade_quality(
    evidence: Dict[str, Any],
    *,
    expected_files: Optional[List[str]] = None,
    required_probes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return _evaluate_app_grade_quality(
        evidence,
        expected_files=expected_files,
        required_probes=required_probes,
    )


def build_external_quality_benchmark(
    evidence: Dict[str, Any],
    *,
    expected_files: Optional[List[str]] = None,
    required_probes: Optional[List[str]] = None,
    min_quality_score: int = 70,
    max_remediation_attempts: int = 2,
    benchmark_id: str,
    app_version: Optional[str] = None,
) -> Dict[str, Any]:
    return _release_build_external_quality_benchmark(
        evidence,
        expected_files=expected_files,
        required_probes=required_probes,
        min_quality_score=min_quality_score,
        max_remediation_attempts=max_remediation_attempts,
        benchmark_id=benchmark_id,
        app_version=app_version,
    )


def external_evidence_to_app_bundle(
    evidence: Dict[str, Any],
    *,
    expected_files: Optional[List[str]] = None,
    required_probes: Optional[List[str]] = None,
    min_quality_score: int = 70,
    max_remediation_attempts: int = 2,
    benchmark_id: str,
    app_version: Optional[str] = None,
) -> Dict[str, Any]:
    return _external_evidence_to_app_bundle_impl(
        evidence,
        expected_files=expected_files,
        required_probes=required_probes,
        min_quality_score=min_quality_score,
        max_remediation_attempts=max_remediation_attempts,
        benchmark_id=benchmark_id,
        app_version=app_version,
    )
