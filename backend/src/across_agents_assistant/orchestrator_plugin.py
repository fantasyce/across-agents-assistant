from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import atexit
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

from .paths import app_subdir, ecosystem_bin_dir, ecosystem_home, ecosystem_plugin_root


logger = logging.getLogger("across_agents_assistant.orchestrator_plugin")

REQUIRED_APP_GRADE_GATES = [
    "artifact_integrity",
    "workspace_hygiene",
    "security_privacy",
    "agent_mix",
    "static_web_smoke",
    "browser_e2e",
    "api_service",
    "cli_generic",
]

DEFAULT_RELEASE_REQUIRED_PROBES = [
    "static_web_smoke",
    "browser_e2e",
    "api_service",
    "cli_generic",
]

DEFAULT_ORCHESTRATOR_INSTALL_SOURCE = "git+https://github.com/fantasyce/across-orchestrator.git@v0.6.0"
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


def _python_search_path() -> str:
    env_path = os.environ.get("PATH") or ""
    extras = [
        str(Path.home() / ".local" / "bin"),
        "/opt/homebrew/bin",
        "/opt/homebrew/sbin",
        "/usr/local/bin",
        "/usr/local/sbin",
        "/usr/bin",
        "/bin",
    ]
    paths = [item for item in env_path.split(os.pathsep) if item]
    for item in extras:
        if item not in paths:
            paths.append(item)
    return os.pathsep.join(paths)


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

    configured = (explicit or os.environ.get("ACROSS_AGENTS_ORCHESTRATOR_PYTHON") or "").strip()
    if _is_executable_file(configured):
        return str(Path(configured).expanduser())

    sys_executable = str(getattr(sys, "executable", "") or "")
    sys_name = Path(sys_executable).name.lower()
    if not bool(getattr(sys, "frozen", False)) and "python" in sys_name and _is_executable_file(sys_executable):
        return sys_executable

    search_path = _python_search_path()
    candidate_names = [
        "python3.14",
        "python3.13",
        "python3.12",
        "python3.11",
        "python3.10",
        "python3",
    ]
    for name in candidate_names:
        resolved = shutil.which(name, path=search_path)
        if _is_executable_file(resolved):
            return str(Path(resolved).expanduser())

    fixed_paths = [
        Path.home() / ".local" / "bin" / "python3.11",
        Path.home() / ".local" / "bin" / "python3",
        Path("/opt/homebrew/bin/python3.11"),
        Path("/opt/homebrew/bin/python3"),
        Path("/usr/local/bin/python3.11"),
        Path("/usr/local/bin/python3"),
        Path("/usr/bin/python3"),
    ]
    for path in fixed_paths:
        if _is_executable_file(str(path)):
            return str(path)

    raise OrchestratorPluginUnavailable(
        "No Python 3 interpreter was found for installing Across Orchestrator. "
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
        plugin_home = (os.environ.get("ACROSS_AGENTS_ORCHESTRATOR_PLUGIN_HOME") or "").strip()
        install_source = (
            os.environ.get("ACROSS_AGENTS_ORCHESTRATOR_INSTALL_SOURCE")
            or DEFAULT_ORCHESTRATOR_INSTALL_SOURCE
        ).strip() or DEFAULT_ORCHESTRATOR_INSTALL_SOURCE
        return cls(
            mode=_normalize_mode(os.environ.get("ACROSS_AGENTS_ORCHESTRATOR_MODE")),
            endpoint=(os.environ.get("ACROSS_AGENTS_ORCHESTRATOR_ENDPOINT") or "").strip() or None,
            command=(os.environ.get("ACROSS_AGENTS_ORCHESTRATOR_COMMAND") or "across-orchestrator").strip()
            or "across-orchestrator",
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
        installed = self.command_path.is_file() and os.access(self.command_path, os.X_OK)
        wrapper_installed = self.wrapper_path.is_file() and os.access(self.wrapper_path, os.X_OK)
        status = "installed" if installed else str(state.get("status") or "not_installed")
        return {
            "plugin_id": ORCHESTRATOR_PLUGIN_ID,
            "status": status,
            "installed": installed,
            "wrapper_installed": wrapper_installed,
            "installable": True,
            "source": self.source,
            "install_dir": str(self.install_dir),
            "venv_dir": str(self.venv_dir),
            "command": str(self.command_path),
            "wrapper": str(self.wrapper_path),
            "manifest": str(self.manifest_path),
            "python": self.python_executable,
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
        command_path = self._resolve_command()
        install_status = self.install_status()
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
    ) -> Dict[str, Any]:
        self._ensure_external()
        deliverables = deliverables or ["README.md"]
        agent = agent or "demo"
        clean_task_types = _clean_task_types(task_types)
        if self._transport == "http":
            payload: Dict[str, Any] = {
                "goal": goal,
                "projectRoot": project_dir,
                "deliverables": deliverables,
                "agent": agent,
                "strictDependency": bool(strict_dependency),
            }
            if clean_task_types:
                payload["taskTypes"] = clean_task_types
            if subtasks:
                payload["subtasks"] = subtasks
            task = self._http_post("/tasks", payload)
        else:
            args = ["submit", goal, "--project", project_dir, "--agent", agent]
            for deliverable in deliverables:
                args.extend(["--deliverable", deliverable])
            for task_type in clean_task_types:
                args.extend(["--task-type", task_type])
            args.append("--json")
            task = self._cli_json(args)
        self.index.remember(task, transport=self._transport or "unknown", endpoint=self._endpoint)
        if self.config.auto_run:
            self.start_task_async(str(task.get("task_id") or ""))
        return task

    def submit_release_e2e_task(self, *, project_dir: str, run_label: Optional[str] = None) -> Dict[str, Any]:
        self._ensure_external()
        if self._transport == "http":
            payload = {"projectRoot": project_dir}
            if run_label:
                payload["runLabel"] = run_label
            task = self._http_post("/release-e2e", payload)
        else:
            args = ["submit-release-e2e", "--project", project_dir]
            if run_label:
                args.extend(["--run-label", run_label])
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
        if os.path.isabs(command) or os.sep in command:
            return command if os.path.isfile(command) and os.access(command, os.X_OK) else None
        managed_command = self.installer.command_path
        if managed_command.is_file() and os.access(managed_command, os.X_OK):
            return str(managed_command)
        if self.installer.wrapper_path.is_file() and os.access(self.installer.wrapper_path, os.X_OK):
            return str(self.installer.wrapper_path)
        env_path = self._env().get("PATH", "")
        return shutil.which(command, path=env_path)

    def _env(self) -> Dict[str, str]:
        env = _sanitize_python_child_env(os.environ.copy())
        extras = [
            str(ecosystem_bin_dir()),
            os.path.expanduser("~/.across_agents/plugins/bin"),
            os.path.expanduser("~/.local/bin"),
            os.path.expanduser("~/.npm-global/bin"),
            "/opt/homebrew/bin",
            "/opt/homebrew/sbin",
            "/usr/local/bin",
            "/usr/local/sbin",
        ]
        paths = [item for item in str(env.get("PATH") or "").split(os.pathsep) if item]
        for item in extras:
            if item not in paths:
                paths.append(item)
        env["PATH"] = os.pathsep.join(paths)
        env.setdefault("ACROSS_HOME", str(ecosystem_home()))
        env.setdefault("ACROSS_PLUGIN_HOME", str(ecosystem_plugin_root()))
        env.setdefault("ACROSS_BIN_HOME", str(ecosystem_bin_dir()))
        env.setdefault("ACROSS_ORCHESTRATOR_MEMORY_PROVIDER", "across-context")
        env.setdefault("ACROSS_CONTEXT_COMMAND", str(ecosystem_bin_dir() / "across-context"))
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
        for info_path in run_root.glob("aaa-*.json"):
            if info_path == current_info:
                continue
            try:
                payload = json.loads(info_path.read_text(encoding="utf-8"))
            except Exception:
                info_path.unlink(missing_ok=True)
                continue
            pid = int(payload.get("pid") or 0)
            if pid > 0 and self._is_orchestrator_sidecar_pid(pid):
                try:
                    os.kill(pid, 15)
                except ProcessLookupError:
                    pass
                except PermissionError:
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
    if not isinstance(card, dict):
        return {}
    return {
        "name": card.get("name"),
        "version": card.get("version"),
        "capabilities": card.get("capabilities"),
        "protocols": card.get("protocols"),
    }


def _status_progress(status: str) -> float:
    value = str(status or "pending").lower()
    if value == "completed":
        return 1.0
    if value == "running":
        return 0.5
    if value in {"failed", "cancelled"}:
        return 1.0
    return 0.0


def _app_status(status: str) -> str:
    value = str(status or "pending").lower()
    if value in {"pending", "running", "completed", "failed", "cancelled", "paused"}:
        return value
    return "pending"


def _subtask_to_app(subtask: Dict[str, Any], task_id: str) -> Dict[str, Any]:
    status = _app_status(str(subtask.get("status") or "pending"))
    return {
        "subtask_id": str(subtask.get("subtask_id") or subtask.get("id") or subtask.get("path") or ""),
        "description": str(subtask.get("goal") or subtask.get("description") or ""),
        "agent_id": str(subtask.get("agent") or subtask.get("agent_id") or "app-grade"),
        "priority": int(subtask.get("priority") or 1),
        "status": status,
        "progress": _status_progress(status),
        "dependencies": list(subtask.get("dependencies") or []),
        "output_file": subtask.get("path") or subtask.get("output_file"),
        "duration": subtask.get("duration"),
        "error_message": subtask.get("error"),
        "fix_plan": None,
        "wave_number": int(subtask.get("wave") or subtask.get("wave_number") or 1),
        "owner_decision": None,
        "waiting_on_dependencies": [],
        "blocked_reason": None,
        "running_for_seconds": None,
        "contract": {
            "task_id": task_id,
            "required_artifact": subtask.get("path"),
            "source": "across_orchestrator",
        },
    }


def _waves_from_subtasks(subtasks: List[Dict[str, Any]], task_id: str) -> List[Dict[str, Any]]:
    grouped: Dict[int, List[Dict[str, Any]]] = {}
    for subtask in subtasks:
        grouped.setdefault(int(subtask.get("wave_number") or 1), []).append(subtask)
    waves: List[Dict[str, Any]] = []
    for wave_number in sorted(grouped):
        items = grouped[wave_number]
        statuses = {item.get("status") for item in items}
        if statuses == {"completed"}:
            status = "completed"
            governance_status = "approved"
        elif "running" in statuses:
            status = "running"
            governance_status = "pending"
        elif "failed" in statuses:
            status = "failed"
            governance_status = "blocked"
        else:
            status = "pending"
            governance_status = "pending"
        waves.append(
            {
                "wave_id": f"external-wave-{task_id}-{wave_number}",
                "wave_number": wave_number,
                "subtasks": items,
                "status": status,
                "is_blocked": governance_status == "blocked",
                "governance_status": governance_status,
                "blocked_by_wave": None,
                "is_revalidating": False,
                "owner_decision": None,
            }
        )
    return waves


def _required_files(task: Dict[str, Any], evidence: Optional[Dict[str, Any]] = None) -> List[str]:
    app_grade = (evidence or {}).get("app_grade") if isinstance(evidence, dict) else None
    if isinstance(app_grade, dict) and app_grade.get("required_files"):
        return [str(item) for item in app_grade.get("required_files") or []]
    contract = task.get("contract") or {}
    return [str(item) for item in contract.get("requiredArtifacts") or task.get("deliverables") or []]


def _artifact_rows(task: Dict[str, Any], evidence: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    if evidence and isinstance(evidence.get("artifacts"), list):
        rows = []
        for item in evidence.get("artifacts") or []:
            path = str(item.get("path") or "")
            rows.append(
                {
                    "artifact_id": f"external-{path}",
                    "name": path,
                    "path": str(Path(task.get("project_root") or task.get("project_dir") or "") / path) if path else "",
                    "path_hint": path,
                    "status": "accepted" if item.get("present") else "missing",
                    "size": item.get("size"),
                    "sha256": item.get("sha256"),
                    "source": "across_orchestrator",
                }
            )
        return rows
    return [
        {
            "artifact_id": f"external-{path}",
            "name": path,
            "path": str(Path(task.get("project_root") or "") / path),
            "path_hint": path,
            "status": "expected",
            "source": "across_orchestrator",
        }
        for path in _required_files(task, evidence)
    ]


def _clean_task_types(task_types: Optional[List[Any]]) -> List[str]:
    clean: List[str] = []
    seen: set[str] = set()
    for item in task_types or []:
        value = str(item or "").strip().lower()
        if not value or value in seen:
            continue
        clean.append(value)
        seen.add(value)
    return clean


def _external_metadata(task: Dict[str, Any], evidence: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {}
    task_metadata = task.get("metadata")
    if isinstance(task_metadata, dict):
        metadata.update(task_metadata)
    contract = task.get("contract")
    if isinstance(contract, dict):
        for key in ("task_types", "delivery_mode"):
            if key in contract and key not in metadata:
                metadata[key] = contract[key]
    if isinstance(evidence, dict):
        evidence_metadata = evidence.get("metadata")
        if isinstance(evidence_metadata, dict):
            metadata.update(evidence_metadata)
        for key in ("task_types", "delivery_mode"):
            if key in evidence and key not in metadata:
                metadata[key] = evidence[key]
    return metadata


def _external_task_types(task: Dict[str, Any], evidence: Optional[Dict[str, Any]] = None) -> List[str]:
    metadata = _external_metadata(task, evidence)
    task_types = _clean_task_types(metadata.get("task_types") if isinstance(metadata.get("task_types"), list) else None)
    if task_types:
        return task_types
    if _is_app_grade(task):
        return ["functional", "artifact"]
    return ["artifact"]


def _external_delivery_mode(task: Dict[str, Any], evidence: Optional[Dict[str, Any]] = None) -> str:
    metadata = _external_metadata(task, evidence)
    explicit = str(metadata.get("delivery_mode") or "").strip().lower()
    if explicit:
        return explicit
    task_types = _external_task_types(task, evidence)
    if len(task_types) > 1:
        return "composite"
    return task_types[0] if task_types else "artifact"


def external_task_to_app_info(task: Dict[str, Any], evidence: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    task_id = str(task.get("task_id") or "")
    status = _app_status(str(task.get("status") or "pending"))
    subtasks = [_subtask_to_app(item, task_id) for item in task.get("subtasks") or []]
    completed = sum(1 for item in subtasks if item.get("status") == "completed")
    total = len(subtasks)
    required_files = _required_files(task, evidence)
    quality = evaluate_app_grade_quality(evidence or {"status": status, "contract": task.get("contract") or {}})
    artifacts = _artifact_rows(task, evidence)
    task_types = _external_task_types(task, evidence)
    delivery_mode = _external_delivery_mode(task, evidence)
    return {
        "task_id": task_id,
        "description": str(task.get("goal") or task.get("description") or ""),
        "status": status,
        "task_types": task_types,
        "delivery_mode": delivery_mode,
        "owner_delivery_contract": task.get("contract") or {},
        "owner_agent": task.get("agent") or "app-grade",
        "allowed_subtask_agents": sorted({str(item.get("agent") or "app-grade") for item in task.get("subtasks") or []}),
        "project_dir": task.get("project_root") or task.get("project_dir"),
        "subtasks": subtasks,
        "waves": _waves_from_subtasks(subtasks, task_id),
        "artifacts": artifacts,
        "artifact_versions": {item["name"]: 1 for item in artifacts if item.get("name")},
        "acceptance_records": [],
        "owner_session_id": None,
        "last_owner_decision": {
            "decision": "external_orchestrator",
            "delivery_quality": quality,
        },
        "can_handle_directly": False,
        "direct_response": None,
        "progress": completed / total if total else _status_progress(status),
        "completed_count": completed,
        "total_count": total,
        "created_at": float(task.get("created_at") or time.time()),
        "updated_at": float(task.get("updated_at") or time.time()),
        "error": task.get("error"),
        "requirement_manifest": {
            "task_id": task_id,
            "project_dir": task.get("project_root") or task.get("project_dir"),
            "deliverables": [
                {"path": path, "status": "accepted" if status == "completed" else "assigned"}
                for path in required_files
            ],
        },
        "quality_health": {
            "manifest_total": len(required_files),
            "manifest_accepted": len(required_files) if quality["status"] == "passed" else 0,
            "quality_gate": quality["status"],
            "delivery_quality": quality["status"],
            "delivery_quality_report": quality,
            "orchestration_health": "passed" if status == "completed" else status,
        },
        "delivery_report": {
            "status": quality["status"],
            "source": "across_orchestrator",
            "required_files": required_files,
            "checks": quality["checks"],
            "failures": quality["failures"],
        },
        "observability": {
            "orchestrator_plugin": {
                "implementation": "external",
                "source": "across_orchestrator",
            }
        },
    }


def external_task_to_summary(task: Dict[str, Any]) -> Dict[str, Any]:
    subtasks = task.get("subtasks") or []
    completed = sum(1 for item in subtasks if item.get("status") == "completed")
    total = len(subtasks)
    status = _app_status(str(task.get("status") or "pending"))
    return {
        "task_id": str(task.get("task_id") or ""),
        "description": str(task.get("goal") or task.get("description") or ""),
        "status": status,
        "progress": completed / total if total else _status_progress(status),
        "completed_count": completed,
        "total_count": total,
        "created_at": float(task.get("created_at") or time.time()),
        "updated_at": float(task.get("updated_at") or time.time()),
        "project_dir": task.get("project_root") or task.get("project_dir"),
        "owner_agent": task.get("agent") or "app-grade",
        "delivery_mode": _external_delivery_mode(task),
    }


def _is_app_grade(task: Dict[str, Any]) -> bool:
    return (task.get("contract") or {}).get("engine") == "app_grade_release_e2e"


def _status_is_passed(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"passed", "pass", "ok", "true", "success"}


def _gate_statuses(evidence: Dict[str, Any]) -> Dict[str, Any]:
    statuses: Dict[str, Any] = {}
    app_grade = evidence.get("app_grade") or {}
    quality_report = app_grade.get("quality_report") or evidence.get("quality") or {}
    for result in quality_report.get("gate_results") or quality_report.get("gateResults") or []:
        gate_id = result.get("adapter_id") or result.get("gate_id") or result.get("id") or result.get("name")
        if gate_id:
            statuses[str(gate_id)] = result.get("status") or result.get("passed")
    for probe in quality_report.get("probe_results") or quality_report.get("probeResults") or []:
        probe_id = probe.get("probe_type") or probe.get("adapter_id") or probe.get("id")
        if probe_id:
            statuses[str(probe_id)] = probe.get("status") or probe.get("passed")
    for key, value in (quality_report.get("gates") or {}).items():
        statuses[str(key)] = value
    return statuses


def _artifact_integrity_passed(evidence: Dict[str, Any], expected_files: List[str]) -> bool:
    app_grade = evidence.get("app_grade") or {}
    exact_files = [str(item) for item in app_grade.get("exact_files") or []]
    if expected_files and exact_files:
        return sorted(exact_files) == sorted(expected_files)
    artifacts = evidence.get("artifacts") or []
    present = {str(item.get("path")) for item in artifacts if item.get("present")}
    return all(path in present for path in expected_files)


def evaluate_app_grade_quality(
    evidence: Dict[str, Any],
    *,
    expected_files: Optional[List[str]] = None,
    required_probes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    evidence = evidence or {}
    app_grade = evidence.get("app_grade") or {}
    contract = evidence.get("contract") or {}
    expected = list(expected_files or app_grade.get("required_files") or contract.get("requiredArtifacts") or [])
    gate_statuses = _gate_statuses(evidence)
    checks: Dict[str, bool] = {}
    checks["artifact_integrity"] = _artifact_integrity_passed(evidence, expected)

    required_gates = list(REQUIRED_APP_GRADE_GATES)
    for gate in required_gates:
        if gate == "artifact_integrity":
            continue
        raw = gate_statuses.get(gate)
        if raw is None and gate == "static_web_smoke":
            raw = gate_statuses.get("static_web")
        checks[gate] = _status_is_passed(raw)

    probes = list(required_probes or DEFAULT_RELEASE_REQUIRED_PROBES)
    for probe in probes:
        if probe == "static_web" and "static_web_smoke" in checks:
            continue
        if probe not in checks:
            checks[probe] = _status_is_passed(gate_statuses.get(probe))

    delivery_quality = app_grade.get("delivery_quality") or (evidence.get("quality") or {}).get("status")
    delivery_quality_passed = True if delivery_quality in {None, ""} else _status_is_passed(delivery_quality)
    produced_files = [str(item) for item in app_grade.get("exact_files") or []]
    if not produced_files:
        produced_files = [str(item.get("path")) for item in evidence.get("artifacts") or [] if item.get("present")]

    failures = [f"{gate} did not pass" for gate, passed in checks.items() if not passed]
    if not delivery_quality_passed:
        failures.append(f"delivery_quality is {delivery_quality}")
    passed = all(checks.values()) and delivery_quality_passed
    score = 100 if passed else int(100 * sum(1 for ok in checks.values() if ok) / max(1, len(checks)))
    return {
        "status": "passed" if passed else "failed",
        "quality_gate": "passed" if passed else "failed",
        "delivery_quality": "passed" if passed else "failed",
        "quality_score": score,
        "checks": checks,
        "failures": failures,
        "produced_files": sorted(produced_files),
        "required_files": expected,
        "required_probes": probes,
        "gate_results": gate_statuses,
    }


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
    quality = evaluate_app_grade_quality(
        evidence,
        expected_files=expected_files,
        required_probes=required_probes,
    )
    status = "passed" if quality["status"] == "passed" and quality["quality_score"] >= min_quality_score else "failed"
    scenario = {
        "task_id": evidence.get("task_id") or "",
        "status": status,
        "quality_gate": quality["quality_gate"],
        "final_status": evidence.get("status") or "unknown",
        "quality_score": quality["quality_score"],
        "remediation_attempts": 0,
        "produced_files": quality["produced_files"],
        "checks": quality["checks"],
        "failures": quality["failures"],
    }
    return {
        "benchmark_id": benchmark_id,
        "benchmark_version": "external-orchestrator-1.0",
        "app_version": app_version,
        "status": status,
        "summary": {
            "scenario_count": 1,
            "passed_scenarios": 1 if status == "passed" else 0,
            "failed_scenarios": 0 if status == "passed" else 1,
            "min_quality_score": quality["quality_score"],
            "max_remediation_attempts": 0,
        },
        "scenarios": [scenario],
        "external_quality": quality,
        "policy": {
            "min_quality_score": min_quality_score,
            "max_remediation_attempts": max_remediation_attempts,
        },
    }


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
    expected = list(expected_files or (evidence.get("app_grade") or {}).get("required_files") or (evidence.get("contract") or {}).get("requiredArtifacts") or [])
    probes = list(required_probes or DEFAULT_RELEASE_REQUIRED_PROBES)
    benchmark = build_external_quality_benchmark(
        evidence,
        expected_files=expected,
        required_probes=probes,
        min_quality_score=min_quality_score,
        max_remediation_attempts=max_remediation_attempts,
        benchmark_id=benchmark_id,
        app_version=app_version,
    )
    return {
        "schema_version": "1.0",
        "app_version": app_version,
        "generated_at": time.time(),
        "task_id": evidence.get("task_id") or "",
        "description": evidence.get("goal"),
        "task_status": evidence.get("status") or "unknown",
        "task_types": ["functional", "artifact"],
        "delivery_mode": "composite",
        "project_dir": evidence.get("project_root"),
        "owner_agent": (evidence.get("contract") or {}).get("engine") or "app-grade",
        "allowed_subtask_agents": sorted({str(item.get("agent") or "app-grade") for item in evidence.get("subtasks") or []}),
        "delivery_contract": evidence.get("contract") or {},
        "requirement_manifest": {
            "task_id": evidence.get("task_id") or "",
            "project_dir": evidence.get("project_root"),
            "deliverables": [{"path": path, "status": "accepted"} for path in expected],
        },
        "last_owner_decision": {
            "decision": "external_orchestrator",
            "delivery_quality": benchmark.get("external_quality") or {},
        },
        "quality_health": {
            "quality_gate": benchmark["status"],
            "delivery_quality": benchmark["status"],
            "delivery_quality_report": benchmark.get("external_quality") or {},
        },
        "delivery_report": {
            "status": benchmark["status"],
            "source": "across_orchestrator",
            "checks": (benchmark.get("external_quality") or {}).get("checks", {}),
        },
        "observability": {"orchestrator_plugin": {"implementation": "external"}},
        "artifacts": evidence.get("artifacts") or [],
        "acceptance_records": [],
        "benchmark": benchmark,
        "audit": {
            "read_only": True,
            "repair_or_resume_triggered": False,
            "secrets_redacted": True,
            "expected_files": expected,
            "required_probes": probes,
        },
    }
