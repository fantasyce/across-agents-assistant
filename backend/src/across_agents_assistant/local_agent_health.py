"""Shared local-agent readiness detection.

Executable discovery alone is not enough for local-agent routing: a CLI may be
installed but unable to complete a real invocation.  This module keeps one
cached probe result that the API and external Orchestrator bridge can trust.
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

from .agent_ids import CLAUDE_DESKTOP_AGENT_ID, LOCAL_AGENT_ID, normalize_agent_id
from .paths import data_file


LOCAL_AGENT_SPECS = {
    LOCAL_AGENT_ID: {
        "display_name": "OpenClaw",
        # OpenClaw is a first-class local agent; the old "local" alias is no
        # longer normalized or migrated.
        "executable": "openclaw",
        "version_args": ["--version"],
        # OpenClaw is gateway-backed. A synthetic agent message is slower,
        # may create sessions, and is not the documented readiness path.
        "probe_args": ["gateway", "status"],
        "probe_kind": "gateway_status",
        "candidate_dirs": ["/opt/homebrew/bin", "/usr/local/bin", "~/.cargo/bin"],
        "model_args": ["--model"],
        "default_models": [],
    },
    "hermes": {
        "display_name": "Hermes",
        "executable": "hermes",
        "version_args": ["version"],
        "probe_args": ["status"],
        "probe_kind": "hermes_status",
        "candidate_dirs": ["/opt/homebrew/bin", "/usr/local/bin", "~/.local/bin"],
        "model_args": ["--model"],
        "default_models": [],
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
        "model_args": ["--model"],
        "default_models": ["sonnet", "opus", "claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
    },
    CLAUDE_DESKTOP_AGENT_ID: {
        "display_name": "Claude Desktop",
        "executable": CLAUDE_DESKTOP_AGENT_ID,
        # Current desktop installs expose the task-capable Claude Code command as
        # `claude`; keep the AAA agent ID separate while sharing that contract.
        "executable_aliases": ["claude"],
        "version_args": ["--version"],
        "probe_args": None,
        "candidate_dirs": ["/opt/homebrew/bin", "/usr/local/bin", "~/.local/bin"],
        "model_args": ["--model"],
        "default_models": ["sonnet", "opus", "claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
    },
    "codex": {
        "display_name": "Codex",
        "executable": "codex",
        "version_args": ["--version"],
        # Codex non-interactive execution is real work. Treat installation and
        # auth/config validation as separate concerns from lightweight startup.
        "probe_args": None,
        "candidate_dirs": ["/Applications/Codex.app/Contents/Resources", "/opt/homebrew/bin", "/usr/local/bin", "~/.local/bin"],
        "model_args": ["--model"],
        "default_models": ["gpt-5.5", "gpt-5.4", "gpt-5.4-mini"],
    },
    "kimi": {
        "display_name": "Kimi Code",
        "executable": "kimi",
        "version_args": ["--version"],
        # Kimi Code -p starts a real agent run. Keep startup detection
        # lightweight and let task execution validate provider/auth state.
        "probe_args": None,
        "candidate_dirs": ["~/.kimi-code/bin", "/opt/homebrew/bin", "/usr/local/bin", "~/.local/bin"],
        "model_args": ["--model"],
        "default_models": ["minimax/MiniMax-M3"],
    },
    "opencode": {
        "display_name": "OpenCode",
        "executable": "opencode",
        "version_args": ["--version"],
        # opencode run is a real non-interactive agent invocation. Keep startup
        # detection lightweight and leave auth/model validation to the CLI run.
        "probe_args": None,
        "candidate_dirs": ["/opt/homebrew/bin", "/usr/local/bin", "~/.local/bin", "~/.bun/bin", "~/.cargo/bin"],
        "model_args": ["--model"],
        "default_models": ["anthropic/claude-sonnet-4-5", "openai/gpt-5", "google/gemini-2.5-pro", "deepseek/deepseek-chat"],
    },
    "cursor": {
        "display_name": "Cursor Agent",
        "executable": "cursor-agent",
        "version_args": ["--version"],
        # cursor-agent -p starts a real agent run, so installation detection
        # should not execute a prompt during Refresh All.
        "probe_args": None,
        "candidate_dirs": ["/opt/homebrew/bin", "/usr/local/bin", "~/.local/bin"],
        "model_args": ["--model"],
        "default_models": ["auto", "gpt-5", "claude-sonnet-4.5", "claude-opus-4.1"],
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
    configured_model: Optional[str] = None
    source: Optional[str] = None
    detection_method: Optional[str] = None
    candidate_paths: Optional[list[str]] = None
    default_models: Optional[list[str]] = None

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
            "configured_model": self.configured_model,
            "source": self.source,
            "detection_method": self.detection_method,
            "candidate_paths": self.candidate_paths or [],
            "default_models": self.default_models or [],
        }


_CACHE: Optional[tuple[float, Dict[str, LocalAgentHealth]]] = None
_CODEX_MODELS_CACHE: Optional[tuple[float, Dict[str, object]]] = None


def clear_local_agent_health_cache() -> None:
    global _CACHE, _CODEX_MODELS_CACHE
    _CACHE = None
    _CODEX_MODELS_CACHE = None


def list_local_agent_specs() -> Dict[str, Dict[str, object]]:
    """Return non-secret metadata for local agents supported by this build."""
    return {
        agent_id: {
            "id": agent_id,
            "display_name": str(spec.get("display_name") or agent_id),
            "executable": str(spec["executable"]),
            "configured_path": get_configured_agent_path(agent_id),
            "configured_model": get_configured_agent_model(agent_id),
            "default_models": list(spec.get("default_models") or []),
            "candidate_dirs": list(spec.get("candidate_dirs") or []),
        }
        for agent_id, spec in LOCAL_AGENT_SPECS.items()
    }


def get_configured_agent_path(agent_id: str) -> Optional[str]:
    agent_id = normalize_agent_id(agent_id) or agent_id
    if agent_id not in LOCAL_AGENT_SPECS:
        return None
    config = _load_local_agent_config()
    value = ((config.get("agents") or {}).get(agent_id) or {}).get("executable_path")
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def get_configured_agent_model(agent_id: str) -> Optional[str]:
    agent_id = normalize_agent_id(agent_id) or agent_id
    if agent_id not in LOCAL_AGENT_SPECS:
        return None
    config = _load_local_agent_config()
    value = ((config.get("agents") or {}).get(agent_id) or {}).get("model")
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


def save_configured_agent_model(agent_id: str, model: Optional[str]) -> None:
    agent_id = normalize_agent_id(agent_id) or agent_id
    if agent_id not in LOCAL_AGENT_SPECS:
        raise ValueError(f"Unknown local agent: {agent_id}")
    config = _load_local_agent_config()
    agents = config.setdefault("agents", {})
    agent_config = agents.setdefault(agent_id, {})
    model_value = (model or "").strip()
    if model_value:
        agent_config["model"] = model_value
    else:
        agent_config.pop("model", None)
    _save_local_agent_config(config)


def resolve_local_agent_executable(agent_id: str) -> Optional[str]:
    """Resolve the executable path using the same order as health detection."""
    agent_id = normalize_agent_id(agent_id) or agent_id
    spec = LOCAL_AGENT_SPECS.get(agent_id)
    if not spec:
        return None
    path, _, _, _ = _resolve_executable(agent_id, spec)
    return path


def discover_codex_models(*, force: bool = False, timeout: float = 12.0) -> Dict[str, object]:
    """Return the local Codex model registry without running an agent prompt."""
    global _CODEX_MODELS_CACHE
    ttl = float(os.environ.get("ACROSS_AGENTS_CODEX_MODEL_TTL", "300"))
    now = time.time()
    if not force and _CODEX_MODELS_CACHE and now - _CODEX_MODELS_CACHE[0] < ttl:
        return dict(_CODEX_MODELS_CACHE[1])

    executable = resolve_local_agent_executable("codex")
    if not executable:
        result: Dict[str, object] = {
            "available": False,
            "error": "codex executable was not found",
            "models": [],
            "available_models": [],
            "supported_api_models": [],
        }
        _CODEX_MODELS_CACHE = (now, result)
        return dict(result)

    try:
        completed = subprocess.run(
            [executable, "debug", "models"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        result = {
            "available": False,
            "error": f"codex debug models timed out after {timeout:g}s",
            "models": [],
            "available_models": [],
            "supported_api_models": [],
        }
        _CODEX_MODELS_CACHE = (now, result)
        return dict(result)
    except Exception as exc:
        result = {
            "available": False,
            "error": f"codex debug models failed: {exc}",
            "models": [],
            "available_models": [],
            "supported_api_models": [],
        }
        _CODEX_MODELS_CACHE = (now, result)
        return dict(result)

    output = (completed.stdout or "").strip()
    if completed.returncode != 0:
        first_line = ((completed.stderr or completed.stdout or "").strip().split("\n") or ["non-zero exit"])[0]
        result = {
            "available": False,
            "error": f"codex debug models exited {completed.returncode}: {first_line}",
            "models": [],
            "available_models": [],
            "supported_api_models": [],
        }
        _CODEX_MODELS_CACHE = (now, result)
        return dict(result)

    try:
        payload = json.loads(output[output.find("{"):]) if output.find("{") >= 0 else {}
    except json.JSONDecodeError as exc:
        result = {
            "available": False,
            "error": f"codex debug models returned invalid JSON: {exc}",
            "models": [],
            "available_models": [],
            "supported_api_models": [],
        }
        _CODEX_MODELS_CACHE = (now, result)
        return dict(result)

    models = payload.get("models") if isinstance(payload, dict) else []
    normalized = []
    for item in models if isinstance(models, list) else []:
        if not isinstance(item, dict):
            continue
        slug = str(item.get("slug") or "").strip()
        if not slug:
            continue
        normalized.append({
            "slug": slug,
            "display_name": str(item.get("display_name") or slug),
            "supported_in_api": item.get("supported_in_api"),
            "visibility": item.get("visibility"),
        })
    available_models = [item["slug"] for item in normalized]
    supported_api_models = [
        item["slug"]
        for item in normalized
        if item.get("supported_in_api") is not False
    ]
    result = {
        "available": True,
        "error": None,
        "models": normalized,
        "available_models": available_models,
        "supported_api_models": supported_api_models,
    }
    _CODEX_MODELS_CACHE = (now, result)
    return dict(result)


def codex_model_is_available(model: Optional[str]) -> Optional[bool]:
    """Return True/False when Codex model discovery is available, otherwise None."""
    text = str(model or "").strip()
    if not text or text.lower() in {"auto", "codex", "local-agent"}:
        return True
    registry = discover_codex_models()
    if not registry.get("available"):
        return None
    return text in set(str(item) for item in registry.get("available_models") or [])


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
    configured_model = get_configured_agent_model(agent_id)
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
            configured_model=configured_model,
            source=source,
            detection_method=method,
            candidate_paths=candidate_paths,
            default_models=list(spec.get("default_models") or []),
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
            configured_model=configured_model,
            source=source,
            detection_method=method,
            candidate_paths=candidate_paths,
            default_models=list(spec.get("default_models") or []),
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
            configured_model=configured_model,
            source=source,
            detection_method=method,
            candidate_paths=candidate_paths,
            default_models=list(spec.get("default_models") or []),
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
        configured_model=configured_model,
        source=source,
        detection_method=method,
        candidate_paths=candidate_paths,
        default_models=list(spec.get("default_models") or []),
    )


def _load_local_agent_config() -> Dict[str, object]:
    if not LOCAL_AGENT_CONFIG_FILE.exists():
        return {"agents": {}}
    try:
        with open(LOCAL_AGENT_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            agents = data.setdefault("agents", {})
            if isinstance(agents, dict):
                pruned_agents = {
                    agent_id: agent_config
                    for agent_id, agent_config in agents.items()
                    if agent_id in LOCAL_AGENT_SPECS
                }
                if pruned_agents != agents:
                    data["agents"] = pruned_agents
                    _save_local_agent_config(data)
            else:
                data["agents"] = {}
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

    executable_names = _executable_names(spec)
    for executable in executable_names:
        path = shutil.which(executable)
        if path:
            return path, "path", f"which {executable}", warning

    for candidate in _candidate_paths(spec):
        if _is_executable_file(candidate):
            return candidate, "candidate", "safe_candidate_path", warning

    executable = executable_names[0]
    return None, "configured" if configured else "not_found", "configured_path" if configured else f"which {executable}", warning


def _candidate_paths(spec: Dict[str, object]) -> list[str]:
    return [
        str(Path(_expand_path(str(directory))) / executable)
        for directory in list(spec.get("candidate_dirs") or [])
        for executable in _executable_names(spec)
    ]


def _existing_candidate_paths(spec: Dict[str, object]) -> list[str]:
    return [path for path in _candidate_paths(spec) if _is_executable_file(path)]


def _executable_names(spec: Dict[str, object]) -> list[str]:
    names: list[str] = []
    for value in [spec["executable"], *list(spec.get("executable_aliases") or [])]:
        name = str(value).strip()
        if name and name not in names:
            names.append(name)
    return names


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
