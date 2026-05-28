"""Shared local-agent readiness detection.

Executable discovery alone is not enough for task orchestration: a CLI may be
installed but unable to complete a real invocation.  This module keeps one
cached probe result that the API, OwnerAgent, and dispatcher can all trust.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Optional

from .agent_ids import LEGACY_LOCAL_AGENT_ID, LOCAL_AGENT_ID, normalize_agent_id
from .paths import data_file


LOCAL_AGENT_SPECS = {
    LOCAL_AGENT_ID: {
        "display_name": "OpenClaw",
        # OpenClaw is a first-class local agent. Older installs may still
        # persist it as "local"; agent_ids.normalize_agent_id handles that.
        "executable": "openclaw",
        "version_args": ["--version"],
        # OpenClaw is gateway-backed. A synthetic agent message is slower,
        # may create sessions, and is not the documented readiness path.
        "probe_args": ["gateway", "status"],
        "probe_kind": "gateway_status",
        "candidate_dirs": ["/opt/homebrew/bin", "/usr/local/bin", "~/.cargo/bin"],
    },
    "hermes": {
        "display_name": "Hermes",
        "executable": "hermes",
        "version_args": ["version"],
        "probe_args": ["status"],
        "probe_kind": "hermes_status",
        "candidate_dirs": ["/opt/homebrew/bin", "/usr/local/bin", "~/.local/bin"],
    },
    "claude": {
        "display_name": "Claude Code",
        "executable": "claude",
        "version_args": ["--version"],
        # Do not run a real Claude prompt during app startup / Refresh All.
        # Claude Code can inspect the current workspace or request filesystem
        # permissions as part of a prompt run, which is too invasive for a
        # lightweight installed-agent check.
        "probe_args": None,
        "candidate_dirs": ["/opt/homebrew/bin", "/usr/local/bin", "~/.local/bin"],
    },
}

LOCAL_AGENT_CONFIG_FILE = data_file("local_agents.json")


@dataclass(frozen=True)
class LocalAgentHealth:
    agent_id: str
    found: bool
    available: bool
    status: str
    display_name: Optional[str] = None
    executable: Optional[str] = None
    path: Optional[str] = None
    version: Optional[str] = None
    error: Optional[str] = None
    configured_path: Optional[str] = None
    source: Optional[str] = None
    detection_method: Optional[str] = None
    candidate_paths: Optional[list[str]] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "found": self.found,
            "available": self.available,
            "status": self.status,
            "display_name": self.display_name,
            "executable": self.executable,
            "path": self.path,
            "version": self.version,
            "error": self.error,
            "configured_path": self.configured_path,
            "source": self.source,
            "detection_method": self.detection_method,
            "candidate_paths": self.candidate_paths or [],
        }


_CACHE: Optional[tuple[float, Dict[str, LocalAgentHealth]]] = None


def clear_local_agent_health_cache() -> None:
    global _CACHE
    _CACHE = None


def list_local_agent_specs() -> Dict[str, Dict[str, object]]:
    """Return non-secret metadata for local agents supported by this build."""
    return {
        agent_id: {
            "id": agent_id,
            "display_name": str(spec.get("display_name") or agent_id),
            "executable": str(spec["executable"]),
            "configured_path": get_configured_agent_path(agent_id),
            "candidate_dirs": list(spec.get("candidate_dirs") or []),
        }
        for agent_id, spec in LOCAL_AGENT_SPECS.items()
    }


def get_configured_agent_path(agent_id: str) -> Optional[str]:
    agent_id = normalize_agent_id(agent_id) or agent_id
    config = _load_local_agent_config()
    value = ((config.get("agents") or {}).get(agent_id) or {}).get("executable_path")
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def save_configured_agent_path(agent_id: str, executable_path: Optional[str]) -> None:
    agent_id = normalize_agent_id(agent_id) or agent_id
    if agent_id not in LOCAL_AGENT_SPECS:
        raise ValueError(f"Unknown local agent: {agent_id}")
    config = _load_local_agent_config()
    agents = config.setdefault("agents", {})
    agent_config = agents.setdefault(agent_id, {})
    path = (executable_path or "").strip()
    if path:
        agent_config["executable_path"] = path
    else:
        agent_config.pop("executable_path", None)
    _save_local_agent_config(config)
    clear_local_agent_health_cache()


def resolve_local_agent_executable(agent_id: str) -> Optional[str]:
    """Resolve the executable path using the same order as health detection."""
    agent_id = normalize_agent_id(agent_id) or agent_id
    spec = LOCAL_AGENT_SPECS.get(agent_id)
    if not spec:
        return None
    path, _, _, _ = _resolve_executable(agent_id, spec)
    return path


def refresh_login_shell_path() -> None:
    """Adopt the user's login shell PATH for GUI-launched backends."""
    try:
        path_result = subprocess.run(
            ["/bin/zsh", "-l", "-c", "echo $PATH"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if path_result.returncode == 0:
            path = path_result.stdout.strip().split("\n")[-1]
            if path:
                os.environ["PATH"] = path
    except Exception:
        pass


def detect_local_agents(*, force: bool = False) -> Dict[str, Dict[str, object]]:
    """Return cached readiness for every known local agent."""
    global _CACHE
    ttl = float(os.environ.get("ACROSS_AGENTS_LOCAL_AGENT_HEALTH_TTL", "300"))
    now = time.time()
    if not force and _CACHE and now - _CACHE[0] < ttl:
        return {agent_id: health.to_dict() for agent_id, health in _CACHE[1].items()}

    refresh_login_shell_path()
    detected: Dict[str, LocalAgentHealth] = {}
    with ThreadPoolExecutor(max_workers=len(LOCAL_AGENT_SPECS)) as executor:
        futures = {
            executor.submit(_detect_one, agent_id, spec): agent_id
            for agent_id, spec in LOCAL_AGENT_SPECS.items()
        }
        for future in as_completed(futures):
            agent_id = futures[future]
            try:
                detected[agent_id] = future.result()
            except Exception as exc:
                detected[agent_id] = LocalAgentHealth(
                    agent_id=agent_id,
                    found=False,
                    available=False,
                    status="unavailable",
                    error=f"health detection failed: {exc}",
                )
    _CACHE = (now, detected)
    return {agent_id: health.to_dict() for agent_id, health in detected.items()}


def is_local_agent_available(agent_id: str) -> bool:
    agent_id = normalize_agent_id(agent_id) or agent_id
    return bool((detect_local_agents().get(agent_id) or {}).get("available"))


def _detect_one(agent_id: str, spec: Dict[str, object]) -> LocalAgentHealth:
    executable = str(spec["executable"])
    configured_path = get_configured_agent_path(agent_id)
    path, source, method, config_warning = _resolve_executable(agent_id, spec)
    candidate_paths = _existing_candidate_paths(spec)
    if not path:
        return LocalAgentHealth(
            agent_id=agent_id,
            display_name=str(spec.get("display_name") or agent_id),
            executable=executable,
            found=False,
            available=False,
            status="invalid_path" if configured_path else "not_found",
            configured_path=configured_path,
            source=source,
            detection_method=method,
            candidate_paths=candidate_paths,
            error=config_warning,
        )

    version = _read_version(path, list(spec["version_args"]))
    probe_args = spec.get("probe_args")
    if probe_args is None:
        return LocalAgentHealth(
            agent_id=agent_id,
            display_name=str(spec.get("display_name") or agent_id),
            executable=executable,
            found=True,
            available=True,
            status="available",
            path=path,
            version=version,
            error=config_warning,
            configured_path=configured_path,
            source=source,
            detection_method=method,
            candidate_paths=candidate_paths,
        )
    probe = _run_probe(path, list(probe_args), str(spec.get("probe_kind") or "generic"))
    if probe is None:
        return LocalAgentHealth(
            agent_id=agent_id,
            display_name=str(spec.get("display_name") or agent_id),
            executable=executable,
            found=True,
            available=True,
            status="available",
            path=path,
            version=version,
            error=config_warning,
            configured_path=configured_path,
            source=source,
            detection_method=method,
            candidate_paths=candidate_paths,
        )
    if config_warning:
        probe = f"{config_warning}; {probe}"
    return LocalAgentHealth(
        agent_id=agent_id,
        display_name=str(spec.get("display_name") or agent_id),
        executable=executable,
        found=True,
        available=False,
        status="unavailable",
        path=path,
        version=version,
        error=probe,
        configured_path=configured_path,
        source=source,
        detection_method=method,
        candidate_paths=candidate_paths,
    )


def _load_local_agent_config() -> Dict[str, object]:
    if not LOCAL_AGENT_CONFIG_FILE.exists():
        return {"agents": {}}
    try:
        with open(LOCAL_AGENT_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("agents", {})
            agents = data.get("agents")
            if isinstance(agents, dict) and LEGACY_LOCAL_AGENT_ID in agents:
                agents.setdefault(LOCAL_AGENT_ID, agents[LEGACY_LOCAL_AGENT_ID])
                agents.pop(LEGACY_LOCAL_AGENT_ID, None)
                _save_local_agent_config(data)
            return data
    except Exception:
        pass
    return {"agents": {}}


def _save_local_agent_config(config: Dict[str, object]) -> None:
    LOCAL_AGENT_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = LOCAL_AGENT_CONFIG_FILE.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, LOCAL_AGENT_CONFIG_FILE)


def _resolve_executable(agent_id: str, spec: Dict[str, object]) -> tuple[Optional[str], str, str, Optional[str]]:
    configured = get_configured_agent_path(agent_id)
    warning = None
    if configured:
        expanded = _expand_path(configured)
        if _is_executable_file(expanded):
            return expanded, "configured", "configured_path", None
        warning = f"configured path is not executable: {configured}"

    executable = str(spec["executable"])
    path = shutil.which(executable)
    if path:
        return path, "path", f"which {executable}", warning

    for candidate in _candidate_paths(spec):
        if _is_executable_file(candidate):
            return candidate, "candidate", "safe_candidate_path", warning

    return None, "configured" if configured else "not_found", "configured_path" if configured else f"which {executable}", warning


def _candidate_paths(spec: Dict[str, object]) -> list[str]:
    executable = str(spec["executable"])
    return [
        str(Path(_expand_path(str(directory))) / executable)
        for directory in list(spec.get("candidate_dirs") or [])
    ]


def _existing_candidate_paths(spec: Dict[str, object]) -> list[str]:
    return [path for path in _candidate_paths(spec) if _is_executable_file(path)]


def _expand_path(path: str) -> str:
    return os.path.abspath(os.path.expanduser(os.path.expandvars(path)))


def _is_executable_file(path: str) -> bool:
    return os.path.isfile(path) and os.access(path, os.X_OK)


def _read_version(path: str, args: list[str]) -> Optional[str]:
    try:
        result = subprocess.run([path, *args], capture_output=True, text=True, timeout=10)
    except Exception:
        return None
    output = result.stdout.strip() or result.stderr.strip()
    return output.split("\n")[0].strip() if output else None


def _run_probe(path: str, args: list[str], probe_kind: str = "generic") -> Optional[str]:
    default_timeout = "6" if probe_kind == "generic" else "8"
    timeout = float(os.environ.get("ACROSS_AGENTS_LOCAL_AGENT_HEALTH_TIMEOUT", default_timeout))
    try:
        result = subprocess.run([path, *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return f"health probe timed out after {timeout:g}s"
    except Exception as exc:
        return f"health probe failed: {exc}"

    output = (result.stdout or "") + "\n" + (result.stderr or "")
    if result.returncode != 0:
        first_line = output.strip().split("\n")[0] if output.strip() else "non-zero exit"
        return f"health probe exited {result.returncode}: {first_line}"
    if not output.strip():
        return "health probe returned no output"
    if probe_kind == "gateway_status":
        normalized = output.lower()
        if "connectivity probe: ok" in normalized or "runtime: running" in normalized:
            if "connectivity probe: failed" not in normalized and "runtime: stopped" not in normalized:
                return None
        first_line = output.strip().split("\n")[0]
        return f"gateway not ready: {first_line}"
    if probe_kind == "hermes_status":
        normalized = output.lower()
        if "provider:" in normalized and ("configured" in normalized or "logged in" in normalized or "✓" in output):
            return None
        first_line = output.strip().split("\n")[0]
        return f"hermes not ready: {first_line}"
    return None
