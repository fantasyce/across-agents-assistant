from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
import json
import os
import sys
import time

from .llm_gateway.provider_registry import get_default_provider_definitions
from .beginner_study_artifacts import persist_beginner_study_result
from .loop_engineering_retention import RetentionPolicy, run_retention
from .paths import backend_socket_path, component_data_home
from .plugin_runtime import PluginLifecycleError, run_autopilot_cli_json
from .source_mirror_refresh import refresh_source_mirrors, source_mirror_refresh_required
from .task_review.quality_gates import sanitize_remote_gate_evidence

_SOURCE_MIRROR_ENV = {
    "across-agents-assistant": "ACROSS_AGENTS_ASSISTANT_SOURCE",
    "across-orchestrator": "ACROSS_ORCHESTRATOR_SOURCE",
    "across-context": "ACROSS_CONTEXT_SOURCE",
    "across-autopilot": "ACROSS_AUTOPILOT_SOURCE",
}
_DEFAULT_LONG_RUN_TIMEOUT_SECONDS = 7200
_DEFAULT_GITHUB_CI_MAX_WALL_TIMEOUT_SECONDS = 7200
_REMOTE_GATE_TIMEOUT_BUFFER_SECONDS = 120
_MAX_GATE_COMMAND_TIMEOUT_SECONDS = 18_000
_TRIGGER_PREPARATION_LEASE_MS = 5 * 60 * 1000
_REMOTE_GATE_CREDENTIAL_ENV_KEY_PARTS = ("TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "API_KEY")


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

    def beginner_patterns(self) -> dict[str, Any]:
        return self._dict(["beginner-patterns", "--json"])

    def resolve_workflow(
        self,
        user_goal: str,
        *,
        requested_workflow_id: str | None = None,
    ) -> dict[str, Any]:
        args = [
            "workflow-pack",
            "resolve",
            "--goal",
            _required(user_goal, "user_goal"),
            "--json",
        ]
        if requested_workflow_id:
            args.extend(["--pack", _required(requested_workflow_id, "requested_workflow_id")])
        return self._dict(args)

    def build_worker_job_plan(
        self,
        *,
        workflow_id: str,
        user_goal: str,
        project_id: str,
        live_model: bool,
    ) -> dict[str, Any]:
        return self._dict([
            "workflow-pack",
            "worker-job-plan",
            "--pack",
            _required(workflow_id, "workflow_id"),
            "--goal",
            _required(user_goal, "user_goal"),
            "--project-id",
            _required(project_id, "project_id"),
            "--live-model",
            "true" if live_model else "false",
            "--json",
        ])

    def build_execution_plan(
        self,
        *,
        workflow_id: str,
        user_goal: str,
        project_id: str,
        live_model: bool,
    ) -> dict[str, Any]:
        return self._dict([
            "workflow-pack",
            "execution-plan",
            "--pack",
            _required(workflow_id, "workflow_id"),
            "--goal",
            _required(user_goal, "user_goal"),
            "--project-id",
            _required(project_id, "project_id"),
            "--live-model",
            "true" if live_model else "false",
            "--json",
        ])

    def no_key_demo(self, pattern_id: str = "first-verified-task") -> dict[str, Any]:
        return self._dict([
            "beginner-pattern", "demo", "--pattern", _required(pattern_id, "pattern_id"), "--json"
        ])

    def run_no_key_demo(
        self,
        project_root: str,
        pattern_id: str = "first-verified-task",
        *,
        user_goal: str,
    ) -> dict[str, Any]:
        root = Path(_required(project_root, "project_root")).expanduser().resolve(strict=True)
        if not root.is_dir() or root.parent == root:
            raise ValueError("project_root must be an existing project directory")
        result = self._dict(
            [
                "beginner-pattern",
                "run",
                "--pattern",
                _required(pattern_id, "pattern_id"),
                "--goal",
                _required(user_goal, "user_goal"),
                "--json",
            ],
            timeout=_long_run_timeout_seconds(self.env),
            # A read-only assessment may legitimately return 1 when it finds a
            # blocking gate. The JSON is still the product result the beginner
            # needs to inspect, not a transport or plugin failure.
            allowed_returncodes=frozenset({0, 1}),
            cwd=root,
        )
        persist_beginner_study_result(result, env=self._runtime_env())
        return result

    def gate(
        self,
        repo_root: str,
        *,
        base_ref: str | None = None,
        head_ref: str | None = None,
        branch: str | None = None,
        commit: str | None = None,
        ci_path: str | None = None,
        ci_wait_seconds: int = 0,
        draft_pr: bool = False,
        push_branch: bool = False,
        approve_remote: bool = False,
        watch_ci: bool | None = None,
        ci_idle_timeout_seconds: int | None = None,
        ci_max_wall_timeout_seconds: int | None = None,
        max_repairs: int = 0,
        timeout: int = 900,
    ) -> dict[str, Any]:
        """Run the managed Autopilot repository gate through the host boundary."""
        root = Path(_required(repo_root, "repo_root")).expanduser().resolve()
        if not root.is_dir():
            raise ValueError("repo_root must be an existing directory")
        repairs = int(max_repairs)
        if repairs < 0 or repairs > 10:
            raise ValueError("max_repairs must be between 0 and 10")

        args = ["gate", "--repo", str(root)]
        if base_ref:
            args.extend(["--base-ref", _required(base_ref, "base_ref")])
        if head_ref:
            args.extend(["--head-ref", _required(head_ref, "head_ref")])
        if branch:
            args.extend(["--branch", _required(branch, "branch")])
        if commit:
            args.extend(["--commit", _required(commit, "commit")])
        if ci_path:
            ci_file = Path(ci_path).expanduser().resolve()
            if not ci_file.is_file():
                raise ValueError("ci_path must be an existing file")
            args.extend(["--ci-path", str(ci_file)])
        ci_wait = int(ci_wait_seconds)
        if ci_wait < 0 or ci_wait > 900:
            raise ValueError("ci_wait_seconds must be between 0 and 900")
        if ci_wait:
            args.extend(["--ci-wait-seconds", str(ci_wait)])
        if draft_pr:
            args.append("--draft-pr")
        if push_branch:
            args.append("--push-branch")
        if approve_remote:
            args.append("--approve-remote")
        if watch_ci is not None:
            args.extend(["--watch-ci", "true" if watch_ci else "false"])
        idle_timeout = _optional_bounded_int(
            ci_idle_timeout_seconds,
            "ci_idle_timeout_seconds",
            minimum=1,
            maximum=7_200,
        )
        max_wall_timeout = _optional_bounded_int(
            ci_max_wall_timeout_seconds,
            "ci_max_wall_timeout_seconds",
            minimum=1,
            maximum=14_400,
        )
        if idle_timeout is not None and max_wall_timeout is not None and idle_timeout > max_wall_timeout:
            raise ValueError("ci_idle_timeout_seconds must not exceed ci_max_wall_timeout_seconds")
        if idle_timeout is not None:
            args.extend(["--ci-idle-timeout-ms", str(idle_timeout * 1_000)])
        if max_wall_timeout is not None:
            args.extend(["--ci-max-wall-timeout-ms", str(max_wall_timeout * 1_000)])
        if repairs:
            args.extend(["--max-repairs", str(repairs)])
        args.append("--json")

        command_timeout = max(30, min(int(timeout), _MAX_GATE_COMMAND_TIMEOUT_SECONDS))
        if approve_remote and watch_ci is not False:
            ci_wall_seconds = max_wall_timeout or _DEFAULT_GITHUB_CI_MAX_WALL_TIMEOUT_SECONDS
            command_timeout = max(command_timeout, ci_wall_seconds + _REMOTE_GATE_TIMEOUT_BUFFER_SECONDS)
        payload = self._dict(
            args,
            timeout=command_timeout,
            allowed_returncodes=frozenset({0, 2}),
        )
        if payload.get("schema_version") != "across-autopilot-gate-result/1.0":
            raise PluginLifecycleError("Across Autopilot returned an incompatible gate result")
        runtime_env = self._runtime_env()
        return sanitize_remote_gate_evidence(
            payload,
            sensitive_values=_remote_gate_sensitive_values(runtime_env),
        )

    def run(
        self,
        spec: str,
        *,
        trigger: str = "aaa-user",
        model_policy_overrides: Mapping[str, Any] | None = None,
        project_root: str | Path | None = None,
    ) -> dict[str, Any]:
        retention_required = self._candidate_retention_required(spec)
        self._refresh_source_mirrors_if_needed(spec)
        args = ["loop", "run", "--spec", _required(spec, "spec"), "--trigger", trigger, "--json"]
        if model_policy_overrides:
            args.extend(["--model-overrides-json", json.dumps(model_policy_overrides, sort_keys=True)])
        try:
            return self._dict(
                args,
                timeout=_long_run_timeout_seconds(self.env),
                cwd=project_root,
            )
        finally:
            if retention_required:
                self._run_candidate_retention()

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
        claim_args = ["loop", "claim-trigger", "--json"]
        if trigger_id:
            claim_args.extend(["--trigger-id", trigger_id])
        claim_args.extend(["--lease-ms", str(_TRIGGER_PREPARATION_LEASE_MS)])
        claimed = self._dict(claim_args)
        claimed_trigger = claimed.get("trigger") if isinstance(claimed, Mapping) else None
        if claimed.get("status") != "claimed" or not isinstance(claimed_trigger, Mapping):
            return claimed
        claimed_trigger_id = str(claimed_trigger.get("trigger_id") or "").strip()
        if not claimed_trigger_id:
            raise PluginLifecycleError("Across Autopilot claimed a trigger without an identifier")
        spec = (
            claimed_trigger.get("spec_snapshot")
            or claimed_trigger.get("spec_source")
            or claimed_trigger.get("spec_id")
            or claimed_trigger.get("spec")
        )
        retention_required = self._candidate_retention_required(spec)
        try:
            self._refresh_source_mirrors_if_needed(spec)
        except Exception:
            self._release_claimed_trigger(claimed_trigger_id)
            raise
        args = ["loop", "run-claimed-trigger", "--trigger-id", claimed_trigger_id, "--json"]
        result: dict[str, Any] | None = None
        try:
            result = self._dict(args, timeout=_long_run_timeout_seconds(self.env))
            return result
        finally:
            if retention_required or self._candidate_retention_required(_spec_from_run_result(result)):
                self._run_candidate_retention()

    def _release_claimed_trigger(self, trigger_id: str) -> dict[str, Any] | None:
        try:
            return self._dict([
                "loop",
                "release-trigger",
                "--trigger-id",
                trigger_id,
                "--code",
                "source_mirror_refresh_failed",
                "--message",
                "Required source preparation failed; the trigger will retry automatically.",
                "--retry-after-ms",
                "300000",
                "--json",
            ])
        except Exception:
            # The claim lease remains the final crash-recovery boundary if the
            # explicit release command itself is unavailable.
            return None

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
        try:
            run = self.status(run_id)
        except Exception:
            run = {}
        self._refresh_source_mirrors_if_needed(run.get("spec_id") or run.get("spec") or None)
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

    def _dict(
        self,
        args: list[str],
        *,
        timeout: int = 60,
        allowed_returncodes: frozenset[int] | None = None,
        cwd: str | Path | None = None,
    ) -> dict[str, Any]:
        payload = self._json(args, timeout=timeout, allowed_returncodes=allowed_returncodes, cwd=cwd)
        if not isinstance(payload, dict):
            raise PluginLifecycleError("Across Autopilot returned an unexpected JSON payload")
        return payload

    def _json(
        self,
        args: list[str],
        *,
        timeout: int = 60,
        allowed_returncodes: frozenset[int] | None = None,
        cwd: str | Path | None = None,
    ) -> Any:
        kwargs: dict[str, Any] = {"env": self._runtime_env(), "timeout": timeout}
        if allowed_returncodes is not None:
            kwargs["allowed_returncodes"] = allowed_returncodes
        if cwd is not None:
            kwargs["cwd"] = cwd
        return run_autopilot_cli_json(args, **kwargs)

    def _refresh_source_mirrors_if_needed(self, spec: Any) -> dict[str, Any] | None:
        if not source_mirror_refresh_required(spec, self.env):
            return None
        try:
            return refresh_source_mirrors(self.env)
        except Exception as exc:
            if isinstance(exc, PluginLifecycleError):
                raise
            payload = getattr(exc, "payload", None)
            detail = json.dumps(payload, sort_keys=True)[:1000] if payload else str(exc)
            raise PluginLifecycleError(f"Across source mirror refresh failed: {detail}") from exc

    def _refresh_source_mirrors_for_trigger(self, trigger_id: str | None) -> dict[str, Any] | None:
        spec = self._queued_trigger_spec(trigger_id)
        return self._refresh_source_mirrors_if_needed(spec)

    def _queued_trigger_spec(self, trigger_id: str | None) -> Any:
        try:
            queue = self.trigger_queue()
        except Exception:
            return None
        items = [item for item in queue.get("items", []) or [] if isinstance(item, Mapping)]
        selected = None
        if trigger_id:
            selected = next((item for item in items if str(item.get("trigger_id") or "") == trigger_id), None)
        else:
            selected = next((item for item in items if item.get("status") in {None, "pending", "queued"}), None)
        if not selected:
            return None
        return selected.get("spec_snapshot") or selected.get("spec_source") or selected.get("spec_id") or selected.get("spec")

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
        env.setdefault("ACROSS_AAA_HOST_MODEL_PROVIDER", "local-agent")
        env.setdefault("ACROSS_AAA_CANDIDATE_MODEL_LEASE_JSON", json.dumps(_candidate_model_lease_template(), sort_keys=True))
        _scrub_model_secret_env(env)
        _apply_source_mirror_env(env)
        src_root = str(Path(__file__).resolve().parents[1])
        env.setdefault("ACROSS_AAA_HOST_PYTHONPATH", src_root)
        existing_pythonpath = env.get("PYTHONPATH")
        if src_root and src_root not in str(existing_pythonpath or "").split(os.pathsep):
            env["PYTHONPATH"] = src_root if not existing_pythonpath else f"{src_root}{os.pathsep}{existing_pythonpath}"
        return env

    def _candidate_retention_required(self, spec: Any) -> bool:
        env = self._runtime_env()
        if not _candidate_retention_enabled(env):
            return False
        probe_env = dict(env)
        probe_env["ACROSS_AAA_SOURCE_MIRROR_REFRESH"] = "auto"
        return source_mirror_refresh_required(spec, probe_env)

    def _run_candidate_retention(self) -> dict[str, Any] | None:
        env = self._runtime_env()
        if not _candidate_retention_enabled(env):
            return None
        try:
            return run_retention(
                across_home=env.get("ACROSS_HOME"),
                runtime_home_root=env.get("ACROSS_CANDIDATE_HOME_ROOT"),
                policy=RetentionPolicy(
                    max_age_days=_retention_int(env, "ACROSS_AAA_CANDIDATE_RETENTION_MAX_AGE_DAYS", 7, 1, 365),
                    keep_latest=_retention_int(env, "ACROSS_AAA_CANDIDATE_RETENTION_KEEP_LATEST", 2, 1, 50),
                    delete_beyond_keep_latest=_retention_bool(
                        env,
                        "ACROSS_AAA_CANDIDATE_RETENTION_DELETE_BEYOND_KEEP_LATEST",
                        True,
                    ),
                    apply=True,
                    include_promotion_ready=False,
                    include_source_mirrors=False,
                    prune_trigger_queue=True,
                ),
            )
        except Exception:
            return None


def _required(value: str, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise PluginLifecycleError(f"Across Autopilot requires {name}")
    return text


def _optional_bounded_int(value: int | None, name: str, *, minimum: int, maximum: int) -> int | None:
    if value is None:
        return None
    parsed = int(value)
    if parsed < minimum or parsed > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return parsed


def _remote_gate_sensitive_values(env: Mapping[str, str]) -> tuple[str, ...]:
    return tuple(
        str(value)
        for name, value in env.items()
        if value and any(part in str(name).upper() for part in _REMOTE_GATE_CREDENTIAL_ENV_KEY_PARTS)
    )


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


def _candidate_retention_enabled(env: Mapping[str, str]) -> bool:
    raw = str(env.get("ACROSS_AAA_CANDIDATE_RETENTION") or "1").strip().lower()
    return raw not in {"0", "false", "no", "off", "disabled"}


def _retention_bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    raw = str(env.get(key) or "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on", "enabled"}:
        return True
    if raw in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


def _retention_int(env: Mapping[str, str], key: str, default: int, minimum: int, maximum: int) -> int:
    raw = str(env.get(key) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(value, maximum))


def _spec_from_run_result(result: Mapping[str, Any] | None) -> Any:
    if not isinstance(result, Mapping):
        return None
    for value in (result.get("spec_id"), result.get("spec")):
        if value:
            return value
    run = result.get("run")
    if isinstance(run, Mapping):
        for value in (run.get("spec_id"), run.get("spec")):
            if value:
                return value
    trigger = result.get("trigger")
    if isinstance(trigger, Mapping):
        for value in (trigger.get("spec_id"), trigger.get("spec")):
            if value:
                return value
    evidence = result.get("evidence")
    if isinstance(evidence, Mapping):
        for value in (evidence.get("spec_id"), evidence.get("spec")):
            if value:
                return value
    return None


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
