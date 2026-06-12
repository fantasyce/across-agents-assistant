from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

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
    override = _env_value(env, "ACROSS_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return (_user_home(env) / ".across").resolve()


def ecosystem_bin_dir(env: Mapping[str, str] | None = None) -> Path:
    override = _env_value(env, "ACROSS_BIN_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return ecosystem_home(env) / "bin"


def ecosystem_plugin_root(env: Mapping[str, str] | None = None) -> Path:
    override = _env_value(env, "ACROSS_PLUGIN_HOME")
    if override:
        return Path(override).expanduser().resolve()
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
    override = _env_value(None, "ACROSS_AGENTS_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return component_data_home()


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
    path = app_subdir("logs") if _env_value(None, "ACROSS_AGENTS_HOME") else component_logs_home()
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_dir() -> Path:
    path = app_subdir("run") if _env_value(None, "ACROSS_AGENTS_HOME") else component_run_home()
    path.mkdir(parents=True, exist_ok=True)
    return path


def tmp_dir() -> Path:
    path = app_subdir("tmp") if _env_value(None, "ACROSS_AGENTS_HOME") else component_cache_home() / "tmp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def backend_socket_path() -> str:
    return str(run_dir() / "across-agents.sock")


def speech_socket_path() -> str:
    return str(run_dir() / "speech_cli.sock")
