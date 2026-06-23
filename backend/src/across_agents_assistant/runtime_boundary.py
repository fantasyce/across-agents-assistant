from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping


PRODUCT_MODE_ENV = "ACROSS_AGENTS_PRODUCT_MODE"
DEVELOPER_MODE_ENV = "ACROSS_AGENTS_DEVELOPER_MODE"
DEVELOPMENT_RUNTIME_PATHS_ENV = "ACROSS_AGENTS_ALLOW_DEVELOPMENT_RUNTIME_PATHS"
PRODUCT_MODE_ENVS = (
    PRODUCT_MODE_ENV,
    "ACROSS_CONTEXT_PRODUCT_MODE",
    "ACROSS_ORCHESTRATOR_PRODUCT_MODE",
    "ACROSS_AUTOPILOT_PRODUCT_MODE",
)
DEVELOPER_MODE_ENVS = (
    DEVELOPER_MODE_ENV,
    DEVELOPMENT_RUNTIME_PATHS_ENV,
    "ACROSS_CONTEXT_DEVELOPER_MODE",
    "ACROSS_ORCHESTRATOR_DEVELOPER_MODE",
    "ACROSS_AUTOPILOT_DEVELOPER_MODE",
)

_TRUTHY_VALUES = {"1", "true", "yes", "on", "y"}
_PRODUCT_RUNTIME_OVERRIDE_NAMES = (
    "ACROSS_HOME",
    "ACROSS_PLUGIN_HOME",
    "ACROSS_BIN_HOME",
    "ACROSS_CONTEXT_COMMAND",
    "ACROSS_CONTEXT_HOME",
    "ACROSS_AUTOPILOT_COMMAND",
    "ACROSS_AUTOPILOT_HOME",
    "ACROSS_AGENTS_HOME",
    "ACROSS_AGENTS_DB_PATH",
    "ACROSS_AGENTS_BACKEND_DIR",
    "ACROSS_ORCHESTRATOR_HOME",
    "ACROSS_AGENTS_ORCHESTRATOR_COMMAND",
    "ACROSS_AGENTS_ORCHESTRATOR_PLUGIN_HOME",
    "ACROSS_AGENTS_CONTEXT_INSTALL_SOURCE",
    "ACROSS_AGENTS_ORCHESTRATOR_INSTALL_SOURCE",
    "ACROSS_AGENTS_AUTOPILOT_INSTALL_SOURCE",
)


def truthy(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    text = str(value).strip().lower()
    if not text:
        return default
    return text in _TRUTHY_VALUES


def is_product_mode(env: Mapping[str, str] | None = None) -> bool:
    source = env if env is not None else os.environ
    return any(truthy(source.get(name)) for name in PRODUCT_MODE_ENVS) or bool(getattr(sys, "frozen", False))


def is_developer_mode(env: Mapping[str, str] | None = None) -> bool:
    source = env if env is not None else os.environ
    return any(truthy(source.get(name)) for name in DEVELOPER_MODE_ENVS)


def user_home(env: Mapping[str, str] | None = None) -> Path:
    source = env if env is not None else os.environ
    configured = str(source.get("HOME") or "").strip()
    return Path(configured).expanduser() if configured else Path.home()


def expand_user(value: str, env: Mapping[str, str] | None = None) -> str:
    text = str(value or "")
    if text == "~":
        return str(user_home(env))
    if text.startswith("~/"):
        return str(user_home(env) / text[2:])
    return os.path.expanduser(text)


def default_across_home(env: Mapping[str, str] | None = None) -> Path:
    return (user_home(env) / ".across").resolve()


def protected_user_roots(env: Mapping[str, str] | None = None) -> list[Path]:
    home = user_home(env)
    return [home / "Documents", home / "Desktop", home / "Downloads"]


def contains_protected_user_reference(value: str, env: Mapping[str, str] | None = None) -> bool:
    text = expand_user(str(value or ""), env)
    if not text:
        return False
    if any(_references_path_root(text, root) for root in protected_user_roots(env)):
        return True
    return bool(re.search(r"(?:~|/Users/[^/]+)/(Documents|Desktop|Downloads)(?:/|$)", text))


def _references_path_root(text: str, root: Path) -> bool:
    root_text = str(root)
    if not root_text:
        return False
    return bool(re.search(re.escape(root_text) + r"(?:/|$)", text))


def product_runtime_override_allowed(name: str, value: str | None, env: Mapping[str, str] | None = None) -> bool:
    if not value or not str(value).strip():
        return False
    if not is_product_mode(env) or is_developer_mode(env):
        return True
    return not contains_protected_user_reference(str(value), env)


def safe_runtime_override(name: str, env: Mapping[str, str] | None = None) -> str | None:
    source = env if env is not None else os.environ
    value = str(source.get(name) or "").strip()
    if product_runtime_override_allowed(name, value, source):
        return value
    return None


def boundary_issue(name: str, value: str, reason: str = "protected user directory") -> dict[str, str]:
    return {"name": name, "value": value, "reason": reason}


def product_runtime_boundary_issues(env: Mapping[str, str] | None = None) -> list[dict[str, str]]:
    source = env if env is not None else os.environ
    if not is_product_mode(source) or is_developer_mode(source):
        return []
    issues: list[dict[str, str]] = []
    for name in _PRODUCT_RUNTIME_OVERRIDE_NAMES:
        value = str(source.get(name) or "").strip()
        if value and contains_protected_user_reference(value, source):
            issues.append(boundary_issue(name, value))
    return issues


def sanitized_product_runtime_env(env: Mapping[str, str] | None = None) -> tuple[dict[str, str], list[dict[str, str]]]:
    source = dict(env if env is not None else os.environ)
    product_mode = is_product_mode(source)
    developer_mode = is_developer_mode(source)
    if product_mode:
        source.setdefault(PRODUCT_MODE_ENV, "1")
        source.setdefault("ACROSS_CONTEXT_PRODUCT_MODE", "1")
        source.setdefault("ACROSS_ORCHESTRATOR_PRODUCT_MODE", "1")
        source.setdefault("ACROSS_AUTOPILOT_PRODUCT_MODE", "1")
    if developer_mode:
        source.setdefault(DEVELOPER_MODE_ENV, "1")
        source.setdefault("ACROSS_CONTEXT_DEVELOPER_MODE", "1")
        source.setdefault("ACROSS_ORCHESTRATOR_DEVELOPER_MODE", "1")
        source.setdefault("ACROSS_AUTOPILOT_DEVELOPER_MODE", "1")
    issues = product_runtime_boundary_issues(source)
    issue_names = {issue["name"] for issue in issues}
    for name in issue_names:
        source.pop(name, None)

    across_home = Path(expand_user(str(source.get("ACROSS_HOME") or default_across_home(source)), source)).resolve()
    source["ACROSS_HOME"] = str(across_home)
    if not str(source.get("ACROSS_PLUGIN_HOME") or "").strip():
        source["ACROSS_PLUGIN_HOME"] = str(across_home / "plugins")
    if not str(source.get("ACROSS_BIN_HOME") or "").strip():
        source["ACROSS_BIN_HOME"] = str(across_home / "bin")
    return source, issues
