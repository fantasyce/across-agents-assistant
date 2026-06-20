from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping

from .paths import ecosystem_bin_dir
from .plugin_runtime import PluginLifecycleError
from .runtime_boundary import sanitized_product_runtime_env


def get_autopilot_status(*, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    return _run_autopilot_json(["status", "--json"], env=env)


def generate_autopilot_review(*, fetch: bool = False, mode: str = "host", env: Mapping[str, str] | None = None) -> dict[str, Any]:
    args = ["review", "--json", "--mode", mode]
    if fetch:
        args.append("--fetch")
    return _run_autopilot_json(args, env=env)


def create_autopilot_candidate_plan(
    *,
    goal: str,
    target_product: str = "across-autopilot",
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return _run_autopilot_json(
        [
            "candidate-plan",
            "--goal",
            goal,
            "--target-product",
            target_product,
            "--json",
        ],
        env=env,
    )


def _run_autopilot_json(args: list[str], *, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source, _runtime_boundary_issues = sanitized_product_runtime_env(env if env is not None else os.environ)
    command = _autopilot_command(source)
    if command is None:
        raise PluginLifecycleError("Across Autopilot plugin is not available")
    completed = subprocess.run(
        [str(command), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        env=dict(source),
        check=False,
    )
    if completed.returncode != 0:
        raise PluginLifecycleError("Across Autopilot command failed")
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise PluginLifecycleError("Across Autopilot returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise PluginLifecycleError("Across Autopilot returned a non-object JSON payload")
    return payload


def _autopilot_command(env: Mapping[str, str]) -> Path | None:
    configured = str(env.get("ACROSS_AUTOPILOT_COMMAND") or "").strip()
    if configured:
        path = Path(configured).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return path
    managed = ecosystem_bin_dir(env) / "across-autopilot"
    if managed.is_file() and os.access(managed, os.X_OK):
        return managed
    resolved = shutil.which("across-autopilot", path=str(env.get("PATH") or os.environ.get("PATH") or ""))
    if resolved:
        return Path(resolved)
    return None

