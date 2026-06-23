from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
import json
import os
import sys
import time

from .llm_gateway.provider_registry import get_default_provider_definitions
from .paths import backend_socket_path, component_data_home
from .plugin_runtime import PluginLifecycleError, run_autopilot_cli_json

_SOURCE_MIRROR_ENV = {
    "across-agents-assistant": "ACROSS_AGENTS_ASSISTANT_SOURCE",
    "across-orchestrator": "ACROSS_ORCHESTRATOR_SOURCE",
    "across-context": "ACROSS_CONTEXT_SOURCE",
    "across-autopilot": "ACROSS_AUTOPILOT_SOURCE",
}
_DEFAULT_LONG_RUN_TIMEOUT_SECONDS = 1800


@dataclass(frozen=True)
class AutopilotClient:
    """Thin host-side client for the Across Autopilot plugin CLI."""

    env: Mapping[str, str] | None = None

    def registry(self) -> dict[str, Any]:
        return self._dict(["loop", "registry", "--json"])

    def validate_spec(self, spec: str) -> dict[str, Any]:
        return self._dict(["loop", "validate", "--spec", _required(spec, "spec"), "--json"])

    def dry_run(self, spec: str) -> dict[str, Any]:
        return self._dict(["loop", "dry-run", "--spec", _required(spec, "spec"), "--json"])

    def run(
        self,
        spec: str,
        *,
        trigger: str = "aaa-user",
        model_policy_overrides: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        args = ["loop", "run", "--spec", _required(spec, "spec"), "--trigger", trigger, "--json"]
        if model_policy_overrides:
            args.extend(["--model-overrides-json", json.dumps(model_policy_overrides, sort_keys=True)])
        return self._dict(args, timeout=_long_run_timeout_seconds(self.env))

    def enqueue_trigger(
        self,
        spec: str,
        *,
        trigger_type: str = "manual",
        payload: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
        not_before: str | None = None,
        source: str | None = "aaa",
        actor: str | None = "user",
    ) -> dict[str, Any]:
        args = [
            "loop",
            "enqueue-trigger",
            "--spec",
            _required(spec, "spec"),
            "--type",
            trigger_type or "manual",
            "--payload-json",
            json.dumps(dict(payload or {}), sort_keys=True),
            "--json",
        ]
        if idempotency_key:
            args.extend(["--idempotency-key", idempotency_key])
        if not_before:
            args.extend(["--not-before", not_before])
        if source:
            args.extend(["--source", source])
        if actor:
            args.extend(["--actor", actor])
        return self._dict(args)

    def trigger_queue(self) -> dict[str, Any]:
        return self._dict(["loop", "trigger-queue", "--json"])

    def run_trigger(self, trigger_id: str | None = None) -> dict[str, Any]:
        args = ["loop", "run-trigger", "--json"]
        if trigger_id:
            args.extend(["--trigger-id", trigger_id])
        return self._dict(args, timeout=_long_run_timeout_seconds(self.env))

    def status(self, run_id: str) -> dict[str, Any]:
        return self._dict(["loop", "status", "--run-id", _required(run_id, "run_id"), "--json"])

    def evidence(self, run_id: str) -> dict[str, Any]:
        return self._dict(["loop", "evidence", "--run-id", _required(run_id, "run_id"), "--json"])

    def events(self, run_id: str, *, after_sequence: int | None = None) -> dict[str, Any] | list[Any]:
        args = ["loop", "events", "--run-id", _required(run_id, "run_id"), "--json"]
        if after_sequence is not None:
            args.extend(["--after-sequence", str(after_sequence)])
        return self._json(args)

    def list_runs(self) -> dict[str, Any]:
        payload = self._json(["loop", "list", "--json"])
        if isinstance(payload, list):
            return {"runs": payload}
        if isinstance(payload, dict) and isinstance(payload.get("runs"), list):
            return payload
        raise PluginLifecycleError("Across Autopilot returned an unexpected JSON payload")

    def telemetry(self) -> dict[str, Any]:
        return self._dict(["loop", "telemetry", "--json"])

    def cancel(self, run_id: str, *, reason: str = "cancelled by host") -> dict[str, Any]:
        return self._dict(["loop", "cancel", "--run-id", _required(run_id, "run_id"), "--reason", reason, "--json"])

    def retry(self, run_id: str) -> dict[str, Any]:
        return self._dict(["loop", "retry", "--run-id", _required(run_id, "run_id"), "--json"], timeout=_long_run_timeout_seconds(self.env))

    def set_spec_paused(self, spec_id: str, paused: bool) -> dict[str, Any]:
        command = "pause" if paused else "resume"
        return self._dict(["loop", command, "--spec-id", _required(spec_id, "spec_id"), "--json"])

    def set_adapter_paused(self, adapter_id: str, paused: bool) -> dict[str, Any]:
        command = "pause" if paused else "resume"
        return self._dict(["adapter", command, "--adapter-id", _required(adapter_id, "adapter_id"), "--json"])

    def quarantine_output(self, run_id: str, output_id: str) -> dict[str, Any]:
        return self._dict([
            "loop",
            "quarantine-output",
            "--run-id",
            _required(run_id, "run_id"),
            "--output",
            _required(output_id, "output_id"),
            "--json",
        ])

    def _dict(self, args: list[str], *, timeout: int = 60) -> dict[str, Any]:
        payload = self._json(args, timeout=timeout)
        if not isinstance(payload, dict):
            raise PluginLifecycleError("Across Autopilot returned an unexpected JSON payload")
        return payload

    def _json(self, args: list[str], *, timeout: int = 60) -> Any:
        return run_autopilot_cli_json(args, env=self._runtime_env(), timeout=timeout)

    def _runtime_env(self) -> Mapping[str, str]:
        env = dict(os.environ)
        if self.env:
            env.update(dict(self.env))
        env.setdefault("ACROSS_AAA_HOST_MODEL_COMMAND", json.dumps(_host_model_command()))
        env.setdefault("ACROSS_AAA_HOST_RESEARCH_COMMAND", json.dumps(_host_research_command()))
        env.setdefault("ACROSS_AAA_HOST_CODE_COMMAND", json.dumps(_host_code_command()))
        env.setdefault("ACROSS_AAA_HOST_REVIEW_COMMAND", json.dumps(_host_review_command()))
        candidate_app_lifecycle_command = _candidate_app_lifecycle_command()
        if candidate_app_lifecycle_command:
            env.setdefault("ACROSS_AAA_CANDIDATE_APP_LIFECYCLE_COMMAND", json.dumps(candidate_app_lifecycle_command))
        env.setdefault("ACROSS_AAA_HOST_MODEL_PROVIDER", "minimax")
        env.setdefault("ACROSS_AAA_CANDIDATE_MODEL_LEASE_JSON", json.dumps(_candidate_model_lease_template(), sort_keys=True))
        _scrub_model_secret_env(env)
        _apply_source_mirror_env(env)
        src_root = str(Path(__file__).resolve().parents[1])
        env.setdefault("ACROSS_AAA_HOST_PYTHONPATH", src_root)
        existing_pythonpath = env.get("PYTHONPATH")
        if src_root and src_root not in str(existing_pythonpath or "").split(os.pathsep):
            env["PYTHONPATH"] = src_root if not existing_pythonpath else f"{src_root}{os.pathsep}{existing_pythonpath}"
        return env


def _required(value: str, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise PluginLifecycleError(f"Across Autopilot requires {name}")
    return text


def _long_run_timeout_seconds(env: Mapping[str, str] | None = None) -> int:
    merged = os.environ if env is None else {**os.environ, **dict(env)}
    raw = str(merged.get("ACROSS_AAA_AUTOPILOT_RUN_TIMEOUT_SECONDS") or "").strip()
    if not raw:
        return _DEFAULT_LONG_RUN_TIMEOUT_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_LONG_RUN_TIMEOUT_SECONDS
    return max(600, min(value, 7200))


def _host_model_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "autopilot-model-decision"]
    return [sys.executable, "-m", "across_agents_assistant.cli", "autopilot-model-decision"]


def _host_research_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "autopilot-research-decision"]
    return [sys.executable, "-m", "across_agents_assistant.cli", "autopilot-research-decision"]


def _host_code_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "autopilot-code-iteration"]
    return [sys.executable, "-m", "across_agents_assistant.cli", "autopilot-code-iteration"]


def _host_review_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "autopilot-review-decision"]
    return [sys.executable, "-m", "across_agents_assistant.cli", "autopilot-review-decision"]


def _candidate_model_lease_template() -> dict[str, Any]:
    issued_at_unix = int(time.time())
    return {
        "schema_version": "across-candidate-model-lease/1.0",
        "issuer": {"product": "across-agents-assistant", "role": "stable-a"},
        "transport": "host_command",
        "host_socket": backend_socket_path(),
        "host_http_url": str(os.environ.get("ACROSS_AAA_HOST_HTTP_URL") or "").strip(),
        "scopes": ["model.decide", "model.research", "model.code_patch", "model.review", "model.chat"],
        "commands": {
            "model_decision": _host_model_command(),
            "research_decision": _host_research_command(),
            "code_iteration": _host_code_command(),
            "review_decision": _host_review_command(),
        },
        "issued_at_unix": issued_at_unix,
        "ttl_seconds": 12 * 60 * 60,
        "expires_at_unix": issued_at_unix + (12 * 60 * 60),
        "policy": {
            "secrets_included": False,
            "raw_credentials_allowed": False,
            "candidate_may_store_raw_credentials": False,
            "source_mutation_allowed": False,
        },
    }


def _model_secret_env_names() -> set[str]:
    return {provider.api_key_env for provider in get_default_provider_definitions()}


def _scrub_model_secret_env(env: dict[str, str]) -> None:
    """Keep model credentials owned by AAA, not inherited by plugin processes."""
    for name in _model_secret_env_names():
        env.pop(name, None)


def _candidate_app_lifecycle_command() -> list[str] | None:
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        resources_dir = executable.parent.parent if executable.parent.name == "backend" else executable.parent
        script = resources_dir / "scripts" / "candidate_app_lifecycle.sh"
    else:
        script = Path(__file__).resolve().parents[3] / "scripts" / "candidate_app_lifecycle.sh"
    if script.exists():
        return ["bash", str(script)]
    return None


def _source_mirror_root(env: Mapping[str, str]) -> Path:
    explicit = str(env.get("ACROSS_AUTOPILOT_SOURCE_MIRRORS_DIR") or "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    return component_data_home("across-autopilot", env=env) / "source-mirrors"


def _apply_source_mirror_env(env: dict[str, str]) -> None:
    if str(env.get("ACROSS_AUTOPILOT_DISABLE_SOURCE_MIRRORS") or "").strip() in {"1", "true", "yes"}:
        return
    root = _source_mirror_root(env)
    active = []
    for repo_id, env_key in _SOURCE_MIRROR_ENV.items():
        if str(env.get(env_key) or "").strip():
            continue
        mirror = root / repo_id
        if (mirror / ".git").is_dir() or mirror.is_dir():
            env[env_key] = str(mirror)
            active.append(repo_id)
    if active:
        env["ACROSS_AUTOPILOT_SOURCE_MIRRORS_ACTIVE"] = ",".join(active)
