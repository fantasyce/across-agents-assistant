from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from .runtime_boundary import expand_user, safe_runtime_override

COMPONENT_ID = "across-agents-assistant"


def _env_value(env: Mapping[str, str] | None, key: str) -> str | None:
    source = env if env is not None else os.environ
    value = source.get(key)
    if value and value.strip():
        return value
    return None


def _user_home(env: Mapping[str, str] | None = None) -> Path:
    home = _env_value(env, "HOME")
    return Path(home).expanduser() if home else Path.home()


def ecosystem_home(env: Mapping[str, str] | None = None) -> Path:
    override = safe_runtime_override("ACROSS_HOME", env)
    if override:
        return Path(expand_user(override, env)).resolve()
    return (_user_home(env) / ".across").resolve()


def ecosystem_bin_dir(env: Mapping[str, str] | None = None) -> Path:
    override = safe_runtime_override("ACROSS_BIN_HOME", env)
    if override:
        return Path(expand_user(override, env)).resolve()
    return ecosystem_home(env) / "bin"


def ecosystem_plugin_root(env: Mapping[str, str] | None = None) -> Path:
    override = safe_runtime_override("ACROSS_PLUGIN_HOME", env)
    if override:
        return Path(expand_user(override, env)).resolve()
    return ecosystem_home(env) / "plugins"


def ecosystem_component_dir(
    section: str,
    component_id: str = COMPONENT_ID,
    env: Mapping[str, str] | None = None,
) -> Path:
    return ecosystem_home(env) / section / component_id


def component_data_home(component_id: str = COMPONENT_ID, env: Mapping[str, str] | None = None) -> Path:
    return ecosystem_component_dir("data", component_id, env)


def component_config_home(component_id: str = COMPONENT_ID, env: Mapping[str, str] | None = None) -> Path:
    return ecosystem_component_dir("config", component_id, env)


def component_run_home(component_id: str = COMPONENT_ID, env: Mapping[str, str] | None = None) -> Path:
    return ecosystem_component_dir("run", component_id, env)


def component_logs_home(component_id: str = COMPONENT_ID, env: Mapping[str, str] | None = None) -> Path:
    return ecosystem_component_dir("logs", component_id, env)


def component_cache_home(component_id: str = COMPONENT_ID, env: Mapping[str, str] | None = None) -> Path:
    return ecosystem_component_dir("cache", component_id, env)


def app_home() -> Path:
    """Return the single app-owned local data root."""
    override = _app_home_override()
    if override:
        return Path(expand_user(override)).resolve()
    return component_data_home()


def _app_home_override(env: Mapping[str, str] | None = None) -> str | None:
    return safe_runtime_override("ACROSS_AGENTS_HOME", env)


def ensure_app_home() -> Path:
    root = app_home()
    root.mkdir(parents=True, exist_ok=True)
    return root


def app_subdir(name: str) -> Path:
    path = ensure_app_home() / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_file(name: str) -> Path:
    return ensure_app_home() / name


def log_dir() -> Path:
    path = app_subdir("logs") if _app_home_override() else component_logs_home()
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_dir() -> Path:
    path = app_subdir("run") if _app_home_override() else component_run_home()
    path.mkdir(parents=True, exist_ok=True)
    return path


def tmp_dir() -> Path:
    path = app_subdir("tmp") if _app_home_override() else component_cache_home() / "tmp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def backend_socket_path() -> str:
    return str(run_dir() / "across-agents.sock")


def speech_socket_path() -> str:
    return str(run_dir() / "speech_cli.sock")
