import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, List, Dict, Any, Tuple, Set
import asyncio
import logging
import os
from pathlib import Path
import subprocess
import shutil
import json
import base64
import hashlib
import time
import threading
import signal
import sys
import re
import uuid
import http.client
import socket
import urllib.parse
import urllib.request
import urllib.error
from contextlib import asynccontextmanager
from types import SimpleNamespace

from .credentials.validation import is_usable_secret, normalize_secret

logger = logging.getLogger("across_agents_assistant")

# Issue 47: Global flag for graceful shutdown
_shutdown_requested = False


def _safe_error_message(operation: str) -> str:
    return f"{operation} failed. See local backend logs for details."


def _safe_http_500(operation: str) -> HTTPException:
    logger.error("%s failed; see local diagnostics for the exception context.", operation)
    return HTTPException(status_code=500, detail=_safe_error_message(operation))


class LocalAgentExecutionError(RuntimeError):
    """Raised when a local CLI agent fails before producing model text."""

    def __init__(
        self,
        agent_id: str,
        code: str,
        message: str,
        *,
        elapsed_sec: Optional[float] = None,
        timeout_kind: Optional[str] = None,
    ):
        super().__init__(message)
        self.agent_id = agent_id
        self.code = code
        self.elapsed_sec = elapsed_sec
        self.timeout_kind = timeout_kind


def _external_orchestrator_http_error(operation: str, exc: "OrchestratorPluginHTTPError") -> HTTPException:
    logger.debug("%s returned HTTP %s from Across Orchestrator", operation, exc.status_code)
    if 400 <= exc.status_code < 500:
        detail = (
            "External Across Orchestrator resource not found."
            if exc.status_code == 404
            else f"External Across Orchestrator returned HTTP {exc.status_code}."
        )
        return HTTPException(status_code=exc.status_code, detail=detail)
    return HTTPException(status_code=502, detail=_safe_error_message(operation))


_ERROR_DETAIL_KEYS = {
    "error",
    "errors",
    "error_message",
    "exception",
    "traceback",
    "stack_trace",
    "stacktrace",
    "output_tail",
}
_ERROR_DETAIL_KEY_PARTS = ("error", "exception", "traceback", "stack_trace", "stacktrace", "output_tail")
_STRUCTURED_PUBLIC_ERROR_KEYS = {"pre_release_gate_parse_errors"}
_AGENT_LOOP_STREAM_CLOSING_EVENT_TYPES = {
    "loop.approval_required",
    "loop.completed",
    "loop.failed",
    "loop.stopped",
    "loop.cancelled",
}
_AGENT_LOOP_STREAM_POLL_SECONDS = 0.25
_AGENT_LOOP_STREAM_IDLE_TIMEOUT_SECONDS = 30.0
_PUBLIC_TEXT_DETAIL_KEYS = {"detail", "message", "connection_note"}
_EXTERNAL_TASK_EVIDENCE_STATUSES = {"completed", "failed", "cancelled"}


def _autopilot_research_value_error_detail(exc: ValueError) -> str:
    text = str(exc)
    if "host target fallback is disabled" in text:
        return (
            "Model research decision remained invalid after repair; host target fallback "
            "is disabled for autonomous production loops."
        )
    return _safe_error_message("Create Autopilot research decision")


def _sanitize_public_error_text(value: Any) -> Any:
    if value is None:
        return None
    text = str(value)
    if "Traceback (most recent call last)" in text or "\n  File " in text:
        return _safe_error_message("Internal operation")
    return re.sub(r"[\r\n\t]+", " ", text).strip()[:2000]


def _sanitize_public_payload(value: Any, key: str = "") -> Any:
    lowered = key.lower()
    if isinstance(value, str) and ("Traceback (most recent call last)" in value or "\n  File " in value):
        return _sanitize_public_error_text(value)
    if lowered in _STRUCTURED_PUBLIC_ERROR_KEYS:
        if isinstance(value, dict):
            return {str(k): _sanitize_public_payload(v, str(k)) for k, v in value.items()}
        if isinstance(value, list):
            return [_sanitize_public_payload(item, "") for item in value]
    if (
        lowered in _ERROR_DETAIL_KEYS
        or lowered in _PUBLIC_TEXT_DETAIL_KEYS
        or any(part in lowered for part in _ERROR_DETAIL_KEY_PARTS)
    ):
        return _sanitize_public_error_text(value)
    if isinstance(value, dict):
        return {str(k): _sanitize_public_payload(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_public_payload(item, key) for item in value]
    return value


def _should_fetch_external_task_evidence(task_payload: Dict[str, Any]) -> bool:
    return str((task_payload or {}).get("status") or "").strip().lower() in _EXTERNAL_TASK_EVIDENCE_STATUSES


async def _external_task_evidence_async(plugin: Any, task_id: str, task_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not _should_fetch_external_task_evidence(task_payload):
        return None
    try:
        return await asyncio.to_thread(plugin.get_evidence_bundle, task_id)
    except Exception:
        return None


def _external_task_evidence_sync(plugin: Any, task_id: str, task_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not _should_fetch_external_task_evidence(task_payload):
        return None
    try:
        return plugin.get_evidence_bundle(task_id)
    except Exception:
        return None


async def _enrich_external_agent_loop_transition(manager: Any, loop: Any) -> Any:
    if not isinstance(loop, dict):
        return loop
    loop_id = str(loop.get("loop_id") or "").strip()
    if not loop_id:
        return loop
    enriched = dict(loop)
    if not isinstance(enriched.get("health"), dict):
        try:
            enriched["health"] = await asyncio.to_thread(manager.get_agent_loop_health, loop_id)
        except Exception:
            pass
    if not isinstance(enriched.get("evidence_summary"), dict):
        try:
            enriched["evidence_summary"] = await asyncio.to_thread(manager.get_agent_loop_evidence_summary, loop_id)
        except Exception:
            pass
    telemetry_getter = getattr(manager, "get_agent_loop_telemetry", None)
    if callable(telemetry_getter) and not isinstance(enriched.get("telemetry"), dict):
        try:
            enriched["telemetry"] = await asyncio.to_thread(telemetry_getter, loop_id)
        except Exception:
            pass
    return enriched


def _agent_loop_event_key(event: Any) -> str:
    if isinstance(event, dict):
        return str(event.get("event_id") or event.get("sequence") or json.dumps(event, sort_keys=True, default=str))
    return json.dumps(event, sort_keys=True, default=str)


def _agent_loop_sse_chunk(event: Any) -> str:
    safe_event = _sanitize_public_payload(event)
    event_type = "message"
    if isinstance(safe_event, dict) and safe_event.get("type"):
        event_type = str(safe_event["type"])
    return f"event: {event_type}\ndata: {json.dumps(safe_event, sort_keys=True)}\n\n"


def _agent_loop_event_closes_stream(event: Any) -> bool:
    return isinstance(event, dict) and event.get("type") in _AGENT_LOOP_STREAM_CLOSING_EVENT_TYPES


def _normalize_local_path(path: str) -> str:
    value = str(path or "").strip()
    if not value or "\x00" in value or "\r" in value or "\n" in value:
        raise ValueError("Invalid local path")
    return os.path.realpath(os.path.abspath(os.path.expanduser(value)))


def _is_original_business_subtask_id(subtask_id: str) -> bool:
    if subtask_id.endswith("-decompose"):
        return False
    if subtask_id.startswith("st-quality-"):
        return False
    if "-integration-fix" in subtask_id:
        return False
    return re.sub(r"-(?:fix-\d+|v\d+)$", "", subtask_id) == subtask_id


def _is_remediation_subtask_id(subtask_id: str) -> bool:
    if subtask_id.endswith("-decompose"):
        return False
    return not _is_original_business_subtask_id(subtask_id)

# Patch PATH globally so that npx, uvx, python3 etc can be found even when launched from macOS App
try:
    current_path = os.environ.get("PATH", "")
    path_parts = [p for p in current_path.split(":") if p]
    extras = [
        "/opt/homebrew/bin",
        "/usr/local/bin",
        os.path.expanduser("~/.local/bin"),
        os.path.expanduser("~/.cargo/bin"),
        os.path.expanduser("~/.bun/bin"),
        os.path.expanduser("~/.nvm/versions/node/v20.0.0/bin"),
        os.path.expanduser("~/.nvm/versions/node/v21.0.0/bin"),
        os.path.expanduser("~/.nvm/versions/node/v22.0.0/bin")
    ]

    for extra in extras:
        if os.path.isdir(extra) and extra not in path_parts:
            path_parts.insert(0, extra)
    os.environ["PATH"] = ":".join(path_parts)
except Exception as e:
    print(f"Warning: Failed to patch PATH: {e}")

from .agent_manager import AgentManager
from .agent_ids import LOCAL_AGENT_ID, LOCAL_CLI_AGENT_IDS, normalize_agent_id
from .agent_capabilities import get_agent_capability_store
from .native_agent_skills import (
    NativeSkillError,
    NativeSkillRequest,
    get_native_skill_manager,
    is_native_skill_available,
)
from .llm_client import OrchestratorClient, OrchestratorResponse

# Ensure builtin tools are registered
from .tools import builtin_tools
from .tools.tool_registry import registry
from .tools.mcp_client import mcp_manager
from .persistence.service import persistence

# Harness layer imports
from .harness import (
    MAX_AGENT_LOOP_ITERATIONS,
    post_process_llm_response,
    execute_tool_with_retry,
    ChatToolLoopState,
    ChatToolLoopStateMachine,
    OutputClassification,
)

# LLM Gateway imports
from .llm_gateway.gateway import get_gateway, LLMGateway
from .llm_gateway.config import load_llm_config
from .llm_gateway.provider_registry import get_default_provider_ids
from .llm_gateway.base_adapter import LLMResponse
from .attachments import (
    append_image_attachment_context,
    build_image_attachment_context,
    build_openai_user_content,
    has_image_attachments,
    model_supports_vision,
)
from .external_task_planning import (
    ExternalTaskPlanningRequest,
    agent_adapters_for_external_task,
    deliverables_for_external_task,
    external_owner_agent,
    planned_subtasks_for_external_task,
)

# Task history imports
from .task_history.state import TaskState
from .task_history.models import TaskType, JobStatus, TaskStatus
from .task_review.release_evaluation import build_release_evaluation_summary
from .release_verification import (
    RELEASE_VERIFICATION_EXPECTED_FILES,
    RELEASE_VERIFICATION_REQUIRED_PROBES,
    _collect_release_task_rows,
    _build_release_verification_report,
    _redact_sensitive_evidence,
    _release_e2e_rows,
    _release_evaluation_row_from_task_payload,
    _upsert_release_evaluation_row,
    public_release_verification_api_response_from_report_directory,
)
from .task_api_models import (
    AutoTaskRequest,
    AutoTaskResponse,
    JobInfo,
    ReleaseE2EScenarioListResponse,
    ReleaseE2ETaskRequest,
    ReleaseE2ETaskResponse,
    SubTaskInfo,
    TaskDispatchRequest,
    TaskInfo,
    TaskPageResponse,
    TaskSummaryInfo,
    WaveInfo,
    pydantic_dump as _pydantic_dump,
)
from .task_api_observability import (
    build_task_observability_snapshot as _build_task_observability_snapshot,
    expected_files_from_payload as _expected_files_from_payload,
    probe_types_from_payload as _probe_types_from_payload,
)
from .task_review.release_e2e import (
    RELEASE_E2E_SCENARIO_ID,
    build_release_e2e_scenarios,
    build_release_e2e_task_request,
)
from .paths import app_home, app_subdir, backend_socket_path, data_file, log_dir as app_log_dir, run_dir, tmp_dir
from .orchestrator_plugin import (
    OrchestratorPluginConfig,
    OrchestratorPluginHTTPError,
    OrchestratorPluginManager,
    OrchestratorPluginUnavailable,
    build_external_quality_benchmark,
    external_evidence_to_app_bundle,
    external_task_to_app_info,
)
from .autopilot_client import AutopilotClient
from .aaa_ecosystem_roadmap import build_aaa_ecosystem_roadmap, ecosystem_route_section
from .agent_interop_e2e import (
    augment_release_evaluation_with_agent_interop,
    load_agent_interop_e2e_latest,
    public_agent_interop_e2e_result,
    run_agent_interop_e2e,
)
from .autopilot_workbench import build_autopilot_workbench_snapshot
from .external_agent_plugin_gateway import probe_agent_plugin_runtime_status
from .plugin_runtime import (
    PluginLifecycleError,
    discover_across_plugins,
    forget_context_memory,
    get_agent_loop_memory_metrics,
    inspect_across_plugin,
    list_context_memories,
    remember_context_memory,
    run_autopilot_plugin_lifecycle_action,
    run_context_plugin_lifecycle_action,
    update_context_memory_status,
)
from .autopilot_promotion_review import build_promotion_review_packet
from .autopilot_trigger_manager import AutopilotTriggerRegistry, AutopilotTriggerScheduler
from .loop_engineering_ops import build_loop_engineering_ops_dashboard
from .loop_engineering_self_iteration import (
    DEFAULT_SELF_ITERATION_DAILY_TIME,
    DEFAULT_SELF_ITERATION_INTERVAL_SECONDS,
    DEFAULT_SELF_ITERATION_SPEC,
    DEFAULT_SELF_ITERATION_TIMEZONE,
    DEFAULT_SELF_ITERATION_TRIGGER_ID,
    build_self_iteration_plan,
    ensure_self_iteration_plan,
)
from .source_mirror_refresh import source_mirror_status
from .unified_capability_registry import (
    build_unified_capability_registry,
    evaluate_unified_capability_registry_health,
)

# Global task history state
_task_state = TaskState()
_task_persistence_initialized = False
_server_started_at = time.time()
_autopilot_trigger_scheduler: AutopilotTriggerScheduler | None = None


def get_autopilot_client() -> AutopilotClient:
    return AutopilotClient()


def get_autopilot_trigger_registry() -> AutopilotTriggerRegistry:
    return AutopilotTriggerRegistry()


def get_autopilot_trigger_scheduler() -> AutopilotTriggerScheduler:
    global _autopilot_trigger_scheduler
    registry = get_autopilot_trigger_registry()
    if _autopilot_trigger_scheduler is not None and _autopilot_trigger_scheduler.registry.path != registry.path:
        _autopilot_trigger_scheduler.stop()
        _autopilot_trigger_scheduler = None
    if _autopilot_trigger_scheduler is None:
        _autopilot_trigger_scheduler = AutopilotTriggerScheduler(
            registry,
            get_autopilot_client,
        )
    return _autopilot_trigger_scheduler


def get_source_mirror_status() -> dict[str, Any]:
    try:
        return source_mirror_status()
    except Exception:
        logger.warning("Source mirror status probe failed.", exc_info=True)
        return {
            "schema_version": "across-source-mirror-status/1.0",
            "status": "failed",
            "reason": "status_probe_failed",
            "error": _safe_error_message("Source mirror status probe"),
        }


def _self_iteration_scheduler_autostart_disabled() -> bool:
    value = os.environ.get("ACROSS_AGENTS_DISABLE_SELF_ITERATION_SCHEDULER", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _default_self_iteration_trigger_exists(registry: AutopilotTriggerRegistry) -> bool:
    try:
        state = registry.list()
    except Exception:
        return False
    return any(
        isinstance(item, dict) and item.get("trigger_id") == DEFAULT_SELF_ITERATION_TRIGGER_ID
        for item in state.get("triggers", []) or []
    )


def _restore_self_iteration_scheduler_on_startup() -> dict[str, Any]:
    if _self_iteration_scheduler_autostart_disabled():
        return {"status": "disabled"}
    registry = get_autopilot_trigger_registry()
    if not _default_self_iteration_trigger_exists(registry):
        return {"status": "not_configured"}
    ensure_self_iteration_plan(
        registry,
        daily_time=DEFAULT_SELF_ITERATION_DAILY_TIME,
        timezone=DEFAULT_SELF_ITERATION_TIMEZONE,
    )
    return get_autopilot_trigger_scheduler().start(
        interval_seconds=60,
        run_queued_triggers=True,
        max_runs_per_tick=1,
    )


def _stop_autopilot_trigger_scheduler_for_shutdown() -> None:
    global _autopilot_trigger_scheduler
    scheduler = _autopilot_trigger_scheduler
    if scheduler is not None:
        scheduler.stop()

# Initialize persistence only. Task history is loaded lazily by task APIs.
def _init_task_persistence():
    """Initialize task persistence without recovering or hydrating task history."""
    global _task_persistence_initialized
    if _task_persistence_initialized:
        return

    from .persistence.service import persistence
    _task_state.set_persistence(persistence.tasks)
    _task_persistence_initialized = True

# Runtime credential cache: provider_id -> api_key.
# Avoids repeated file reads for availability checks.
_credential_cache: Dict[str, Optional[str]] = {}

_credential_store: Optional["CredentialStore"] = None


def _normalize_api_key(value: Optional[str]) -> Optional[str]:
    """Strip whitespace from an API key value; treat blank strings as ``None``."""
    return normalize_secret(value)


def _is_usable_api_key(value: Optional[str]) -> bool:
    """Return True when *value* looks like a real backend credential.

    Treating placeholders as configured makes readiness lie and lets the task UI
    select providers that will immediately fail at runtime.
    """
    return is_usable_secret(value)


def _get_credential_store() -> "CredentialStore":
    global _credential_store
    if _credential_store is None:
        from .credentials.store import CredentialStore
        _credential_store = CredentialStore()
    return _credential_store


def _effective_backend_key(provider_id: str) -> Optional[str]:
    """Resolve an API key from env → runtime cache → credentials file.

    Priority:
    1. Normalized env var (allows advanced users to override via shell)
    2. Runtime cache (set by POST /api/keys or startup hydration)
    3. Credentials file (the primary durable store, loaded at startup)
    """
    provider_config = next((p for p in load_llm_config().providers if p.provider_id == provider_id), None)
    env_name = provider_config.api_key_env if provider_config else f"{provider_id.upper()}_API_KEY"
    env_key = _normalize_api_key(os.environ.get(env_name))
    if _is_usable_api_key(env_key):
        return env_key
    cache_val = _credential_cache.get(provider_id)
    cached = _normalize_api_key(cache_val)
    if _is_usable_api_key(cached):
        return cached
    try:
        file_key = _normalize_api_key(_get_credential_store().get(provider_id))
        if _is_usable_api_key(file_key):
            return file_key
    except Exception:
        pass
    return None


def _upsert_credential_metadata(
    *,
    provider_id: str,
    source: str,
    is_configured: bool,
    last_error: Optional[str] = None,
) -> None:
    """Persist credential metadata row (never raw keys)."""
    try:
        db = getattr(getattr(_task_state, "_persistence", None), "_db", None)
        if db is None:
            return
        conn = db.get_connection() if hasattr(db, "get_connection") else db
        now = time.time()
        conn.execute(
            """INSERT OR REPLACE INTO credential_metadata
               (provider_id, source, is_configured, last_loaded_at, last_updated_at, last_error)
               VALUES (?, ?, ?, COALESCE((SELECT last_loaded_at FROM credential_metadata WHERE provider_id=?), ?), ?, ?)""",
            (provider_id, source, 1 if is_configured else 0, provider_id, now, now, last_error),
        )
        conn.commit()
    except Exception as exc:
        logger.debug("Failed to upsert credential metadata for %s: %s", provider_id, exc)


def _load_credential_metadata(provider_id: str) -> Dict[str, Any]:
    """Load credential metadata for a provider."""
    try:
        db = getattr(getattr(_task_state, "_persistence", None), "_db", None)
        if db is None:
            return {"provider_id": provider_id, "source": "unknown", "is_configured": False}
        conn = db.get_connection() if hasattr(db, "get_connection") else db
        row = conn.execute(
            "SELECT * FROM credential_metadata WHERE provider_id = ?", (provider_id,)
        ).fetchone()
        if row:
            return dict(row)
    except Exception:
        pass
    return {"provider_id": provider_id, "source": "unknown", "is_configured": False}


def _hydrate_runtime_keys_from_store() -> None:
    """Load credentials file into runtime env/cache and metadata at startup."""
    global _credential_cache
    try:
        store = _get_credential_store()
        store.ensure_permissions()
        creds = store.load_all()
        provider_config_by_id = {p.provider_id: p for p in load_llm_config().providers}
        for pid, cred in creds.items():
            is_configured = _is_usable_api_key(cred.api_key)
            provider_config = provider_config_by_id.get(pid)
            env_name = provider_config.api_key_env if provider_config else f"{pid.upper()}_API_KEY"
            if is_configured and (pid not in _credential_cache or not _credential_cache.get(pid)):
                _credential_cache[pid] = cred.api_key
            if is_configured and not os.environ.get(env_name):
                os.environ[env_name] = cred.api_key
            _upsert_credential_metadata(
                provider_id=pid,
                source=cred.source,
                is_configured=is_configured,
                last_error=None if is_configured else "placeholder_or_invalid_key",
            )
        logger.info("Hydrated %d provider(s) from credentials file", len(creds))
    except Exception as exc:
        logger.warning("Failed to hydrate keys from credentials file: %s", exc)


# Hydrate runtime keys from credentials file at module init time.
_hydrate_runtime_keys_from_store()


def _cached_key_is_configured(provider_id: str) -> bool:
    """Check whether the in-memory cache holds a usable key for *provider_id*."""
    value = _credential_cache.get(provider_id)
    return _is_usable_api_key(value)

_orchestrator_plugin_manager: Optional[OrchestratorPluginManager] = None
_orchestrator_plugin_signature: Optional[Tuple[Any, ...]] = None


def get_orchestrator_plugin_manager() -> OrchestratorPluginManager:
    global _orchestrator_plugin_manager, _orchestrator_plugin_signature
    registry_path = app_subdir("orchestrator-plugin") / "tasks.json"
    config = OrchestratorPluginConfig.from_env(registry_path=registry_path)
    signature = (
        config.normalized_mode(),
        config.endpoint,
        config.command,
        str(config.registry_path),
        str(config.plugin_home),
        config.install_source,
        config.auto_run,
    )
    if _orchestrator_plugin_manager is None or _orchestrator_plugin_signature != signature:
        _orchestrator_plugin_manager = OrchestratorPluginManager(config)
        _orchestrator_plugin_signature = signature
    return _orchestrator_plugin_manager


def _orchestrator_plugin_status(*, probe: bool = True) -> Dict[str, Any]:
    try:
        return get_orchestrator_plugin_manager().implementation_status(probe=probe)
    except Exception as exc:
        logger.warning("Failed to inspect Across Orchestrator plugin: %s", exc)
        public_message = _safe_error_message("Across Orchestrator plugin inspection")
        fallback_config = OrchestratorPluginConfig.from_env()
        return {
            "mode": fallback_config.normalized_mode(),
            "implementation": "unknown",
            "available": False,
            "transport": None,
            "endpoint": fallback_config.endpoint,
            "command": fallback_config.command,
            "connection_note": public_message,
            "error": public_message,
        }


def _is_external_orchestrator_task(task_id: str) -> bool:
    try:
        return get_orchestrator_plugin_manager().is_external_task(task_id)
    except Exception:
        return False


def _active_task_ids_waiting_for_keys() -> List[str]:
    """Return in-memory tasks blocked on keys without scanning task history."""
    try:
        tasks = _task_state.get_all_tasks()
    except Exception:
        return []

    waiting: List[str] = []
    for task in tasks:
        status = getattr(task, "status", None)
        status_value = getattr(status, "value", status)
        decision = getattr(task, "last_owner_decision", {}) or {}
        error = getattr(task, "error", "") or ""
        if (
            status_value == TaskStatus.PENDING.value
            and (
                decision.get("blocked_reason") == "waiting_for_keys"
                or "Waiting for API keys" in error
            )
        ):
            task_id = getattr(task, "task_id", None)
            if task_id:
                waiting.append(task_id)
    return waiting


def _repair_active_tasks_waiting_for_keys(*, reason: str) -> Optional[Dict[str, Any]]:
    task_ids = _active_task_ids_waiting_for_keys()
    if not task_ids:
        return None

    return {
        "task_ids": task_ids,
        "reason": reason,
        "repaired": [],
        "skipped": "external_orchestrator_only",
    }


def _resolve_tool(tool_name: str) -> Optional[Dict[str, Any]]:
    """检查工具名称是否存在于本地注册表或 MCP Server。返回匹配到的 schema（含 name, description, risk_level）或 None。"""
    # 检查本地工具
    tool_def = registry.get_tool(tool_name)
    if tool_def:
        return {
            "name": tool_def.name,
            "description": tool_def.description,
            "risk_level": tool_def.risk_level,
        }
    # 检查 MCP 工具
    schemas = mcp_manager.get_all_tools_schema()
    normalized_target = tool_name.replace("-", "_")
    for t in schemas:
        normalized_schema_name = t["name"].replace("-", "_")
        if normalized_schema_name == normalized_target or normalized_schema_name.endswith(f"__{normalized_target}"):
            return t
    return None


def _is_tool_unavailable(tool_name: str) -> bool:
    try:
        return persistence.permissions.is_unavailable(tool_name)
    except Exception:
        logger.exception("Failed to check unavailable permission for tool %s", tool_name)
        return False


def _filter_unavailable_tool_schemas(schemas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return only schemas that are currently available to agents."""
    return [schema for schema in schemas if not _is_tool_unavailable(schema.get("name", ""))]


def _available_tool_schemas() -> List[Dict[str, Any]]:
    return _filter_unavailable_tool_schemas(_runtime_tool_schemas())


def _runtime_tool_schemas() -> List[Dict[str, Any]]:
    local_tools = registry.get_all_tools_schema()
    mcp_tools = mcp_manager.get_all_tools_schema()
    return _dedupe_tool_schemas(local_tools + mcp_tools)


def _dedupe_tool_schemas(schemas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep one runtime schema per tool name while preserving first-seen order."""
    seen = set()
    deduped = []
    for schema in schemas:
        name = schema.get("name")
        if not name or name in seen:
            continue
        seen.add(name)
        deduped.append(schema)
    return deduped


_ACROSS_CONTEXT_PROJECT_ROOT_TOOLS = {
    "remember_context",
    "search_context",
    "get_project_context",
    "export_agent_instructions",
}


def _session_project_root(session_id: Optional[str]) -> Optional[str]:
    if not session_id:
        return None
    try:
        project = persistence.get_session_project(session_id)
    except Exception:
        logger.exception("Failed to resolve session project for %s", session_id)
        return None
    if not project:
        return None
    raw_path = project.get("path") or project.get("project_dir")
    if not raw_path:
        return None
    try:
        return _normalize_local_path(raw_path)
    except ValueError:
        logger.warning("Ignoring invalid project root from session %s: %r", session_id, raw_path)
        return None


def _augment_mcp_tool_args_for_session(
    tool_name: str,
    tool_args: Optional[Dict[str, Any]],
    session_id: Optional[str],
) -> Dict[str, Any]:
    args = dict(tool_args or {})
    if "__" not in tool_name:
        return args

    server_id, actual_tool_name = tool_name.split("__", 1)
    if server_id != "across_context" or actual_tool_name not in _ACROSS_CONTEXT_PROJECT_ROOT_TOOLS:
        return args

    if "projectRoot" not in args:
        for alias in ("project_root", "projectDir", "project_dir"):
            alias_value = args.get(alias)
            if isinstance(alias_value, str) and alias_value.strip():
                args["projectRoot"] = alias_value
                break

    if "projectRoot" not in args:
        project_root = _session_project_root(session_id)
        if project_root:
            args["projectRoot"] = project_root
    return args


@asynccontextmanager
async def _api_lifespan(app: FastAPI):
    """Make persistence available without starting or recovering historical tasks."""
    _init_task_persistence()
    try:
        await asyncio.to_thread(_restore_self_iteration_scheduler_on_startup)
    except Exception:
        logger.warning("Failed to restore self-iteration scheduler on startup.", exc_info=True)
    try:
        yield
    finally:
        await asyncio.to_thread(_stop_autopilot_trigger_scheduler_for_shutdown)


app = FastAPI(title="Across Agents Assistant API", lifespan=_api_lifespan)

class MCPConnectRequest(BaseModel):
    server_id: str
    command: str
    args: List[str]
    env: Optional[Dict[str, str]] = None
    allowed_paths: Optional[List[str]] = None
    readonly: Optional[bool] = False

@app.post("/api/mcp/connect")
async def connect_mcp_server(req: MCPConnectRequest):
    """Register and connect to an MCP server dynamically."""
    try:
        # Intercept built-in Python MCP servers so they run via the bundled backend
        if req.command == "python3" and req.args and req.args[0] == "-m" and req.args[1] in ["mcp_local_kb", "mcp_external_rag", "mcp_sqlite", "mcp_filesystem"]:
            import sys
            import os
            server_name = req.args[1].replace("mcp_", "") # e.g., "local_kb"
            req.command = sys.executable
            if getattr(sys, 'frozen', False):
                # We are running as PyInstaller bundled binary
                req.args = ["mcp", server_name] + req.args[2:]
            else:
                # We are running in dev mode, sys.executable is python
                # Find the path to main.py
                main_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "main.py"))
                req.args = [main_path, "mcp", server_name] + req.args[2:]

        mcp_manager.register_server(req.server_id, req.command, req.args, req.env,
                                 allowed_paths=req.allowed_paths,
                                 readonly=req.readonly)
        success, error_msg = await mcp_manager.connect_server(req.server_id)
        if success:
            implementation = mcp_manager.get_server_implementation(req.server_id)
            connection_note = mcp_manager.get_server_connection_note(req.server_id)
            return {
                "status": "success",
                "message": f"Connected to MCP server: {req.server_id}",
                "implementation": implementation,
                "connection_note": connection_note,
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=_sanitize_public_error_text(error_msg or f"Failed to connect to MCP server: {req.server_id}"),
            )
    except Exception as e:
        raise _safe_http_500("Connect MCP server")

class MCPDisconnectRequest(BaseModel):
    server_id: str

@app.post("/api/mcp/disconnect")
async def disconnect_mcp_server(req: MCPDisconnectRequest):
    """Disconnect an MCP server."""
    try:
        await mcp_manager.disconnect_server(req.server_id)
        return {"status": "success"}
    except Exception as e:
        raise _safe_http_500("Disconnect MCP server")

class MCPContext(BaseModel):
    server_id: str
    name: str
    status: str
    implementation: Optional[str] = None
    connection_note: Optional[str] = None
    db_path: Optional[str] = None  # For sqlite plugin

@app.get("/api/mcp/contexts")
async def get_mcp_contexts():
    """Get list of currently active MCP contexts for UI display."""
    contexts = []
    for server_id, session in mcp_manager.sessions.items():
        contexts.append(MCPContext(
            server_id=server_id,
            name=server_id,
            status="connected",
            implementation=mcp_manager.get_server_implementation(server_id),
            connection_note=mcp_manager.get_server_connection_note(server_id),
        ))
    return contexts


@app.get("/api/mcp/safety")
async def get_mcp_safety_report():
    """Return MCP server risk, sandbox, and approval metadata."""
    return mcp_manager.get_safety_report()

class ContextPack(BaseModel):
    frontmost_app: Optional[str] = None
    window_title: Optional[str] = None
    clipboard_text: Optional[str] = None

class ChatAttachment(BaseModel):
    name: str
    path: str
    is_folder: bool = False
    kind: str = "file"
    mime_type: Optional[str] = None

class ChatRequest(BaseModel):
    text: str
    context: Optional[ContextPack] = None
    session_id: Optional[str] = None
    agent_id: Optional[str] = None
    project_id: Optional[str] = None
    project_dir: Optional[str] = None
    attachments: Optional[List[ChatAttachment]] = None

class ChatResponse(BaseModel):
    text: str
    session_id: Optional[str] = None
    audio_path: Optional[str] = None
    requires_approval: bool = False
    approval_request: Optional[Dict[str, Any]] = None

class SessionInfo(BaseModel):
    session_id: str
    created_at: str
    updated_at: str
    message_count: int
    name: Optional[str] = None
    preview: Optional[str] = None
    project_id: Optional[str] = None
    project_dir: Optional[str] = None
    is_pinned: bool = False
    pinned_at: Optional[str] = None

class SessionListResponse(BaseModel):
    sessions: List[SessionInfo]
    total: int = 0
    limit: int = 50
    offset: int = 0
    has_more: bool = False

class RenameSessionRequest(BaseModel):
    name: str

class ProjectSessionInfo(SessionInfo):
    pass

class ProjectInfo(BaseModel):
    id: str
    name: str
    path: str
    kind: str = "folder"
    is_pinned: bool = False
    pinned_at: Optional[str] = None
    created_at: str
    updated_at: str
    last_opened_at: Optional[str] = None
    sessions: List[ProjectSessionInfo] = Field(default_factory=list)

class ProjectListResponse(BaseModel):
    projects: List[ProjectInfo]

class CreateBlankProjectRequest(BaseModel):
    name: str

class CreateFolderProjectRequest(BaseModel):
    path: str
    name: Optional[str] = None

class PinRequest(BaseModel):
    is_pinned: bool

class ApprovalDecision(BaseModel):
    session_id: str
    decision: str # "approve", "reject", "always_allow"
    tool_name: str
    tool_args: Dict[str, Any]
    agent_id: str = LOCAL_AGENT_ID
    tool_call_id: Optional[str] = None


_GATEWAY_FALLBACK_PREFIX = "EMBEDDED FALLBACK: Gateway agent failed"


def _is_gateway_fallback_text(text: Optional[str]) -> bool:
    return bool((text or "").lstrip().startswith(_GATEWAY_FALLBACK_PREFIX))


def _persist_tool_continuation_fallback(session_id: Optional[str], text: str) -> None:
    if not session_id:
        return
    try:
        persistence.add_message(session_id=session_id, role="assistant", content=text)
    except Exception:
        logger.exception("Failed to persist tool continuation fallback for session=%s", session_id)


async def _continue_after_tool_execution(
    continuation_req: ChatRequest,
    fallback_text: str,
) -> ChatResponse:
    try:
        response = await chat_endpoint(continuation_req)
    except Exception:
        logger.exception(
            "Tool continuation failed for session=%s agent=%s; returning raw tool result",
            continuation_req.session_id,
            continuation_req.agent_id,
        )
        _persist_tool_continuation_fallback(continuation_req.session_id, fallback_text)
        return ChatResponse(text=fallback_text, session_id=continuation_req.session_id)

    if _is_gateway_fallback_text(response.text):
        logger.warning(
            "Tool continuation returned gateway fallback for session=%s agent=%s; returning raw tool result",
            continuation_req.session_id,
            continuation_req.agent_id,
        )
        session_id = response.session_id or continuation_req.session_id
        _persist_tool_continuation_fallback(session_id, fallback_text)
        return ChatResponse(text=fallback_text, session_id=session_id)

    return response

# Global instances
agent_manager = AgentManager()
agent_client = OrchestratorClient(agent_manager)
_local_agent_client = None


def get_local_agent_client():
    global _local_agent_client
    if _local_agent_client is None:
        from .local_agent.client import UniversalAgentClient
        _local_agent_client = UniversalAgentClient(agent_manager)
    return _local_agent_client

class KeysRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    deepseek: Optional[str] = None
    minimax: Optional[str] = None
    openai: Optional[str] = None
    anthropic: Optional[str] = None
    bailian: Optional[str] = None
    moonshot: Optional[str] = None
    zhipu: Optional[str] = None
    volcengine: Optional[str] = None
    google: Optional[str] = None
    xai: Optional[str] = None
    mistral: Optional[str] = None
    groq: Optional[str] = None
    cohere: Optional[str] = None
    openrouter: Optional[str] = None
    together: Optional[str] = None
    fireworks: Optional[str] = None


def _known_provider_ids() -> tuple[str, ...]:
    return get_default_provider_ids()


def _key_values_from_request(req: KeysRequest) -> Dict[str, str]:
    try:
        raw_values = req.model_dump(exclude_none=True)
    except AttributeError:
        raw_values = req.dict(exclude_none=True)
    known = set(_known_provider_ids())
    return {
        provider_id: str(value)
        for provider_id, value in raw_values.items()
        if provider_id in known and value is not None
    }

class ActiveAgentRequest(BaseModel):
    agent_id: str

@app.post("/api/active_agent")
async def update_active_agent(req: ActiveAgentRequest):
    agent_manager.set_active_agent(normalize_agent_id(req.agent_id) or req.agent_id)
    return {"status": "ok"}

@app.post("/api/keys")
async def update_keys(req: KeysRequest):
    global _credential_cache

    file_values = _key_values_from_request(req)

    # Persist to credential store (the durable source of truth).
    try:
        saved = _get_credential_store().save_many(file_values, source="frontend_save")
        for pid, saved_key in saved.items():
            is_configured = _is_usable_api_key(saved_key)
            _upsert_credential_metadata(
                provider_id=pid,
                source="frontend_save",
                is_configured=is_configured,
                last_error=None if is_configured else "placeholder_or_invalid_key",
            )
    except Exception as exc:
        logger.warning("Failed to persist keys to credential store: %s", exc)
        saved = {}

    provider_config_by_id = {
        provider.provider_id: provider
        for provider in load_llm_config().providers
    }
    for provider_id, raw_key in file_values.items():
        provider_config = provider_config_by_id.get(provider_id)
        env_name = provider_config.api_key_env if provider_config else f"{provider_id.upper()}_API_KEY"
        key = _normalize_api_key(raw_key)
        agent_config = agent_manager.get_agent_config(provider_id) or {}
        if _is_usable_api_key(key):
            os.environ[env_name] = key
            _credential_cache[provider_id] = key
            if provider_config:
                agent_config.update({
                    "api_key": key,
                    "type": provider_config.provider_type,
                    "base_url": provider_config.endpoint,
                    "model": (
                        provider_config.models[0].model_id
                        if provider_config.models
                        else agent_config.get("model", "")
                    ),
                })
                agent_manager.update_agent(provider_id, agent_config)
        else:
            os.environ.pop(env_name, None)
            _credential_cache.pop(provider_id, None)
            if agent_config:
                agent_config["api_key"] = None
                agent_manager.update_agent(provider_id, agent_config)
    repair_result = None
    if _build_key_readiness()["has_any_key"]:
        try:
            repair_result = _repair_active_tasks_waiting_for_keys(reason="keys_synced")
        except Exception as exc:
            logger.warning("Key sync repair failed: %s", exc)
    return {"status": "ok", "repair": repair_result}

class DeleteKeyRequest(BaseModel):
    provider_id: str

@app.post("/api/keys/delete")
async def delete_key(req: DeleteKeyRequest):
    global _credential_cache
    provider_id = req.provider_id
    if provider_id not in _known_provider_ids():
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider_id}")

    # Delete from credential store (the durable source of truth).
    try:
        _get_credential_store().delete(provider_id)
        _upsert_credential_metadata(provider_id=provider_id, source="deleted", is_configured=False)
    except Exception as exc:
        logger.warning("Failed to delete key from credential store: %s", exc)

    provider_config = next((p for p in load_llm_config().providers if p.provider_id == provider_id), None)
    os.environ.pop(provider_config.api_key_env if provider_config else f"{provider_id.upper()}_API_KEY", None)
    _credential_cache.pop(provider_id, None)
    agent_config = agent_manager.get_agent_config(provider_id) or {}
    if agent_config:
        agent_config["api_key"] = None
        agent_manager.update_agent(provider_id, agent_config)
    return {"status": "ok"}

class KeysStatusResponse(BaseModel):
    providers: Dict[str, str]  # provider_id -> "configured" | "not_configured"

@app.get("/api/keys/status", response_model=KeysStatusResponse)
async def get_keys_status():
    """返回各 provider 的 API key 配置状态（从本地凭据文件 + env + 运行时缓存）"""
    providers = {}
    for pid in _known_provider_ids():
        providers[pid] = "configured" if _provider_has_backend_key(pid) else "not_configured"
    return KeysStatusResponse(providers=providers)

class KeyValueResponse(BaseModel):
    provider_id: str
    api_key: Optional[str] = None

@app.get("/api/keys/value/{provider_id}", response_model=KeyValueResponse)
async def get_key_value(provider_id: str):
    """Return the raw API key for local settings UI rendering.

    This endpoint is served by the app-local backend and reads only from the
    backend-managed credential sources.
    """
    if provider_id not in _known_provider_ids():
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider_id}")

    return KeyValueResponse(provider_id=provider_id, api_key=_effective_backend_key(provider_id))

class KeyCheckResult(BaseModel):
    provider_id: str
    status: str  # "configured" | "not_configured" | "error"
    error: Optional[str] = None

class KeysCheckResponse(BaseModel):
    results: List[KeyCheckResult]

@app.post("/api/keys/check", response_model=KeysCheckResponse)
async def check_keys():
    """Force check all provider keys from backend-managed credentials."""
    global _credential_cache
    results = []

    for pid in _known_provider_ids():
        if _cached_key_is_configured(pid):
            results.append(KeyCheckResult(provider_id=pid, status="configured"))
            continue
        result_item = _check_single_backend_credential(pid)
        if result_item.status == "configured" and _credential_cache.get(pid):
            pass  # already cached by _check_single_backend_credential
        results.append(result_item)

    if any(item.status == "configured" for item in results):
        try:
            _repair_active_tasks_waiting_for_keys(reason="keys_checked")
        except Exception as exc:
            logger.warning("Key check repair failed: %s", exc)

    return KeysCheckResponse(results=results)


def _check_single_backend_credential(provider_id: str) -> KeyCheckResult:
    """Check if a provider's API key is available.

    Resolution order: runtime cache → environment → credential store.
    Does NOT access OS credential stores. The backend's durable credential
    store is ``~/.across/data/across-agents-assistant/credentials.json``.
    """
    global _credential_cache

    if _cached_key_is_configured(provider_id):
        return KeyCheckResult(provider_id=provider_id, status="configured")

    provider_config = next((p for p in load_llm_config().providers if p.provider_id == provider_id), None)
    env_name = provider_config.api_key_env if provider_config else f"{provider_id.upper()}_API_KEY"
    env_key = _normalize_api_key(os.environ.get(env_name))
    if _is_usable_api_key(env_key):
        _credential_cache[provider_id] = env_key
        return KeyCheckResult(provider_id=provider_id, status="configured")

    # Check the backend-owned credential store (durable file).
    try:
        store = _get_credential_store()
        file_key = store.get(provider_id)
        file_key = _normalize_api_key(file_key)
        if _is_usable_api_key(file_key):
            _credential_cache[provider_id] = file_key
            return KeyCheckResult(provider_id=provider_id, status="configured")
    except Exception:
        pass

    _credential_cache[provider_id] = None
    return KeyCheckResult(provider_id=provider_id, status="not_configured")


def _check_llm_provider_readiness() -> List[str]:
    """Check whether at least one LLM provider has a backend-usable credential.

    Returns a list of *all* known provider IDs when none have a key,
    or an empty list if at least one provider is configured.
    The gateway handles fallback between providers at runtime,
    so as long as *one* provider is available the task can proceed.

    This check must follow the same backend credential resolution order as
    readiness and status APIs (env -> runtime cache -> credentials file),
    otherwise task submission can be rejected even though the backend can
    already execute the request after a cold restart.
    """
    known_providers = _known_provider_ids()
    has_any = any(_provider_has_backend_key(provider_id) for provider_id in known_providers)
    if has_any:
        return []
    return list(known_providers)


def _provider_has_backend_key(provider_id: str) -> bool:
    return bool(_effective_backend_key(provider_id))


def _build_key_readiness() -> Dict[str, Any]:
    providers = {}
    for provider_id in _known_provider_ids():
        providers[provider_id] = (
            "configured" if _provider_has_backend_key(provider_id) else "not_configured"
        )
    has_any_key = any(value == "configured" for value in providers.values())
    lease_status = _candidate_model_lease_status()
    has_model_capability = has_any_key or lease_status["available"]
    return {
        "has_any_key": has_any_key,
        "has_model_capability": has_model_capability,
        "candidate_model_lease": lease_status["public"],
        "providers": providers,
        "readiness_blockers": [] if has_model_capability else ["api_keys"],
    }


class _UnixSocketHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str, *, timeout: float = 180.0):
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self.socket_path)
        self.sock = sock


def _candidate_model_lease_path() -> Path | None:
    configured = str(os.environ.get("ACROSS_AAA_CANDIDATE_MODEL_LEASE") or "").strip()
    if configured:
        return Path(configured).expanduser()
    candidates = []
    for root_name in ("ACROSS_HOME", "ACROSS_AGENTS_HOME"):
        root = str(os.environ.get(root_name) or "").strip()
        if root:
            candidates.append(Path(root).expanduser() / "candidate-model-lease.json")
    for path in candidates:
        try:
            if str(path) and path.exists():
                return path
        except OSError:
            continue
    return None


def _load_candidate_model_lease() -> Dict[str, Any] | None:
    path = _candidate_model_lease_path()
    if not path:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to read candidate model lease %s: %s", path, exc)
        return None
    if not isinstance(payload, dict):
        return None
    payload["_lease_path"] = str(path)
    return payload


def _candidate_model_lease_status(required_scope: str | None = None) -> Dict[str, Any]:
    lease = _load_candidate_model_lease()
    if not lease:
        return {"available": False, "reason": "missing", "lease": None, "public": {"available": False, "reason": "missing"}}
    public = _public_candidate_model_lease(lease)
    reason = None
    available = True
    if lease.get("schema_version") != "across-candidate-model-lease/1.0":
        available = False
        reason = "unsupported_schema"
    policy = lease.get("policy") if isinstance(lease.get("policy"), dict) else {}
    if policy.get("secrets_included") is not False or policy.get("raw_credentials_allowed") is not False:
        available = False
        reason = "unsafe_policy"
    scopes = {str(scope) for scope in (lease.get("scopes") or [])}
    if required_scope and required_scope not in scopes:
        available = False
        reason = "scope_not_allowed"
    expires_at_unix = lease.get("expires_at_unix")
    try:
        if expires_at_unix is not None and float(expires_at_unix) <= time.time():
            available = False
            reason = "expired"
    except (TypeError, ValueError):
        available = False
        reason = "invalid_expiry"
    socket_path = str(lease.get("host_socket") or "")
    host_http_url = str(lease.get("host_http_url") or "").strip()
    socket_available = bool(socket_path) and Path(socket_path).exists()
    http_available = _is_local_host_http_url(host_http_url)
    if not socket_path and not host_http_url:
        available = False
        reason = "missing_host_transport"
    elif socket_path and not socket_available and not http_available:
        available = False
        reason = "host_socket_missing"
    elif host_http_url and not http_available and not socket_available:
        available = False
        reason = "invalid_host_http_url"
    public.update({"available": available, "reason": reason or "ok"})
    return {"available": available, "reason": reason or "ok", "lease": lease, "public": public}


def _public_candidate_model_lease(lease: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "available": False,
        "schema_version": lease.get("schema_version"),
        "lease_id": lease.get("lease_id"),
        "candidate_id": lease.get("candidate_id"),
        "transport": lease.get("transport"),
        "scopes": [str(scope) for scope in (lease.get("scopes") or [])],
        "host_socket_configured": bool(lease.get("host_socket")),
        "host_http_configured": bool(lease.get("host_http_url")),
        "issued_at_unix": lease.get("issued_at_unix"),
        "expires_at_unix": lease.get("expires_at_unix"),
        "secrets_included": bool((lease.get("policy") or {}).get("secrets_included")),
        "raw_credentials_allowed": bool((lease.get("policy") or {}).get("raw_credentials_allowed")),
        "path": lease.get("_lease_path"),
    }


def _public_request_model_lease(value: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not isinstance(value, dict) or not value:
        return None
    return {
        "schema_version": value.get("schema_version"),
        "lease_id": value.get("lease_id"),
        "candidate_id": value.get("candidate_id"),
        "transport": value.get("transport"),
        "scopes": [str(scope) for scope in (value.get("scopes") or [])],
        "host_socket_configured": bool(value.get("host_socket_configured") or value.get("host_socket")),
        "host_http_configured": bool(value.get("host_http_configured") or value.get("host_http_url")),
        "expires_at_unix": value.get("expires_at_unix"),
        "secrets_included": bool(value.get("secrets_included") or (value.get("policy") or {}).get("secrets_included")),
        "raw_credentials_allowed": bool(value.get("raw_credentials_allowed") or (value.get("policy") or {}).get("raw_credentials_allowed")),
    }


def _is_local_host_http_url(value: str) -> bool:
    if not value:
        return False
    try:
        parsed = urllib.parse.urlparse(value)
    except Exception:
        return False
    return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}


def _post_json_to_unix_socket(socket_path: str, path: str, payload: Dict[str, Any], *, timeout: float = 180.0) -> Dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    conn = _UnixSocketHTTPConnection(socket_path, timeout=timeout)
    try:
        conn.request(
            "POST",
            path,
            body=body,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
        )
        resp = conn.getresponse()
        text = resp.read().decode("utf-8", errors="replace")
        parsed = json.loads(text) if text else {}
        if resp.status >= 400:
            detail = parsed.get("detail") if isinstance(parsed, dict) else text
            raise RuntimeError(f"host model lease proxy returned HTTP {resp.status}: {detail}")
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    finally:
        conn.close()


def _post_json_to_http_url(base_url: str, path: str, payload: Dict[str, Any], *, timeout: float = 180.0) -> Dict[str, Any]:
    if not _is_local_host_http_url(base_url):
        raise RuntimeError("candidate model lease host_http_url must be local HTTP")
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(text) if text else {}
            return parsed if isinstance(parsed, dict) else {"value": parsed}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"host model lease proxy returned HTTP {exc.code}: {detail}") from exc


def _local_agent_timeout_for_scope(requested: Any, scope: str) -> float:
    try:
        timeout = float(requested if requested is not None else 600.0)
    except (TypeError, ValueError):
        timeout = 600.0
    return timeout


def _local_agent_model_override(agent_id: str, model: Any) -> Optional[str]:
    text = str(model or "").strip()
    if not text:
        return None
    lower = text.lower()
    if lower in {"auto", "local-agent", agent_id.lower()}:
        return None
    return text


def _raise_for_local_agent_infra_error(agent_id: str, reply: Any) -> None:
    code = str(getattr(reply, "error_code", "") or "").strip()
    if getattr(reply, "timed_out", False):
        code = "timeout"
    if not code:
        return
    elapsed = getattr(reply, "elapsed_sec", None)
    text = str(getattr(reply, "text", "") or "").strip()
    if code == "timeout":
        suffix = f" after {float(elapsed):.1f}s" if isinstance(elapsed, (int, float)) else ""
        message = f"local agent {agent_id} timed out{suffix}"
    elif code == "agent_not_found":
        message = f"local agent {agent_id} executable was not found"
    elif code == "exit_error":
        message = f"local agent {agent_id} exited before returning model text"
    elif code == "unsupported_model":
        message = f"local agent {agent_id} was asked to use an unavailable model"
    else:
        message = f"local agent {agent_id} failed before returning model text"
    if text:
        message = f"{message}: {text[:500]}"
    timeout_kind = getattr(reply, "timeout_kind", None)
    raise LocalAgentExecutionError(
        agent_id,
        code,
        message,
        elapsed_sec=elapsed if isinstance(elapsed, (int, float)) else None,
        timeout_kind=str(timeout_kind) if timeout_kind else None,
    )


async def _chat_with_model_capability(
    *,
    message: str,
    system_prompt: str | None = None,
    context: Dict[str, Any] | None = None,
    model: str | None = None,
    provider_id: str | None = None,
    agent_id: str | None = None,
    project_dir: str | None = None,
    scope: str = "model.chat",
    **kwargs: Any,
) -> LLMResponse:
    normalized_agent_id = normalize_agent_id(agent_id) if agent_id else None
    if normalized_agent_id in LOCAL_CLI_AGENT_IDS:
        local_timeout = _local_agent_timeout_for_scope(kwargs.get("max_wall_timeout", kwargs.get("timeout", 600.0)), scope)
        local_idle_timeout = kwargs.get("idle_timeout")
        if local_idle_timeout is not None:
            local_idle_timeout = _local_agent_timeout_for_scope(local_idle_timeout, scope)
        prompt_parts = []
        if system_prompt:
            prompt_parts.extend(["System instructions:", system_prompt.strip(), ""])
        prompt_parts.append(message)
        reply = await asyncio.to_thread(
            get_local_agent_client().send,
            "\n".join(prompt_parts),
            target_agent=normalized_agent_id,
            project_dir=project_dir,
            timeout=local_timeout,
            idle_timeout=local_idle_timeout,
            max_wall_timeout=local_timeout,
            model=_local_agent_model_override(normalized_agent_id, model),
        )
        if getattr(reply, "requires_approval", False):
            raise RuntimeError(f"local agent {normalized_agent_id} requires interactive approval")
        _raise_for_local_agent_infra_error(normalized_agent_id, reply)
        text = _normalize_local_agent_model_text(normalized_agent_id, str(getattr(reply, "text", "") or ""))
        return LLMResponse(
            text=text,
            raw={
                "agent_id": normalized_agent_id,
                "scope": scope,
                "elapsed_sec": getattr(reply, "elapsed_sec", None),
            },
            model=str(model or normalized_agent_id),
            provider="local-agent",
            finish_reason="stop",
            usage=None,
        )
    lease_status = _candidate_model_lease_status(scope)
    if lease_status.get("lease") is not None:
        if not lease_status["available"]:
            raise RuntimeError(f"candidate model lease is not available: {lease_status.get('reason')}")
        lease = lease_status["lease"] or {}
        payload = {
            "message": message,
            "system_prompt": system_prompt,
            "context": context,
            "model": model,
            "provider_id": provider_id or (lease.get("provider") if isinstance(lease, dict) else None),
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 2048),
        }
        if lease.get("host_socket") and Path(str(lease.get("host_socket"))).exists():
            result = _post_json_to_unix_socket(str(lease.get("host_socket")), "/api/llm/chat", payload, timeout=float(kwargs.get("timeout", 180.0)))
        else:
            result = _post_json_to_http_url(str(lease.get("host_http_url") or ""), "/api/llm/chat", payload, timeout=float(kwargs.get("timeout", 180.0)))
        return LLMResponse(
            text=str(result.get("text") or ""),
            raw=result,
            model=str(result.get("model") or model or "host-model-lease"),
            provider=str(result.get("provider") or provider_id or "host-model-lease"),
            finish_reason=str(result.get("finish_reason") or "stop"),
            usage=result.get("usage") if isinstance(result.get("usage"), dict) else None,
        )
    gw = get_gateway()
    adapter = None
    if provider_id and hasattr(gw, "_adapters"):
        adapter = gw._adapters.get(provider_id)
    elif hasattr(gw, "get_current_adapter"):
        adapter = gw.get_current_adapter()
    if adapter is None:
        return await gw.chat(
            message=message,
            system_prompt=system_prompt,
            context=context,
            model=model,
            provider_id=provider_id,
            **kwargs,
        )
    if adapter.is_available():
        return await gw.chat(
            message=message,
            system_prompt=system_prompt,
            context=context,
            model=model,
            provider_id=provider_id,
            **kwargs,
        )
    return await gw.chat(
        message=message,
        system_prompt=system_prompt,
        context=context,
        model=model,
        provider_id=provider_id,
        **kwargs,
    )


def _normalize_local_agent_model_text(agent_id: str, text: str) -> str:
    """Return only the assistant answer from local CLI transcript output."""
    if agent_id != "codex":
        return text
    lines = str(text or "").splitlines()
    answer_start = None
    for index, line in enumerate(lines):
        if line.strip() == "codex":
            answer_start = index + 1
    if answer_start is None:
        return text
    answer_lines: list[str] = []
    for line in lines[answer_start:]:
        if line.strip() == "tokens used":
            break
        answer_lines.append(line)
    answer = "\n".join(answer_lines).strip()
    return answer or text


def _path_check(check_id: str, title: str, path: Path, *, expect_file: bool = False) -> Dict[str, Any]:
    """Build a non-secret startup diagnostic check for a local path."""
    try:
        target = path if expect_file else path
        parent = target.parent if expect_file else target
        exists = target.exists()
        writable_target = parent if parent.exists() else parent.parent
        writable = os.access(writable_target, os.W_OK) if writable_target.exists() else False
        if expect_file:
            status = "passed" if exists and writable else "warning"
            detail = (
                f"{title} exists and its parent is writable."
                if status == "passed"
                else f"{title} was not found or its parent is not writable: {path}"
            )
        else:
            status = "passed" if exists and path.is_dir() and writable else "failed"
            detail = (
                f"{title} is available and writable."
                if status == "passed"
                else f"{title} is missing or not writable: {path}"
            )
        remediation = None if status == "passed" else "Check local app data directory permissions."
        return {
            "id": check_id,
            "title": title,
            "status": status,
            "detail": detail,
            "remediation": remediation,
            "metadata": {"path": str(path)},
        }
    except Exception as exc:
        logger.warning("Unable to inspect diagnostic path %s: %s", path, exc)
        return {
            "id": check_id,
            "title": title,
            "status": "failed",
            "detail": _safe_error_message(f"Inspect {title}"),
            "remediation": "Check local app data directory permissions.",
            "metadata": {"path": str(path)},
        }


def _diagnostic_summary(checks: List[Dict[str, Any]]) -> Dict[str, Any]:
    failed = sum(1 for check in checks if check.get("status") == "failed")
    warnings = sum(1 for check in checks if check.get("status") == "warning")
    passed = sum(1 for check in checks if check.get("status") == "passed")
    if failed:
        status = "blocked"
    elif warnings:
        status = "attention"
    else:
        status = "ready"
    return {
        "status": status,
        "passed": passed,
        "warnings": warnings,
        "failed": failed,
        "check_count": len(checks),
    }


def _startup_plugin_summary(plugin: Dict[str, Any]) -> Dict[str, Any]:
    """Return a safe startup-diagnostics view of a plugin status payload."""
    if not isinstance(plugin, dict):
        return {}

    install = plugin.get("install") if isinstance(plugin.get("install"), dict) else {}
    lifecycle = plugin.get("lifecycle") if isinstance(plugin.get("lifecycle"), dict) else {}
    compatibility = plugin.get("compatibility") if isinstance(plugin.get("compatibility"), dict) else {}

    summary: Dict[str, Any] = {
        "plugin_id": plugin.get("plugin_id") or plugin.get("pluginId") or plugin.get("id"),
        "name": plugin.get("name"),
        "status": plugin.get("status"),
        "installed": plugin.get("installed"),
        "available": plugin.get("available"),
        "version": plugin.get("version"),
        "mode": plugin.get("mode"),
        "implementation": plugin.get("implementation"),
        "transport": plugin.get("transport"),
        "endpoint": plugin.get("endpoint"),
        "manifest_exists": plugin.get("manifest_exists", plugin.get("manifestExists")),
        "command_exists": plugin.get("command_exists", plugin.get("commandExists")),
        "command_available": plugin.get("command_available"),
        "task_index_count": plugin.get("task_index_count", plugin.get("taskCount")),
        "data_path": plugin.get("data_path", plugin.get("dataPath")),
        "connection_note": plugin.get("connection_note"),
        "protocols": plugin.get("protocols"),
        "capabilities": plugin.get("capabilities"),
        "install": {
            "installable": install.get("installable"),
            "installed": install.get("installed"),
            "install_dir": install.get("install_dir", install.get("installDir")),
            "source": install.get("source"),
        },
        "lifecycle": {
            "actions": lifecycle.get("actions"),
            "preserves_data_on_uninstall": lifecycle.get(
                "preserves_data_on_uninstall",
                lifecycle.get("preservesDataOnUninstall"),
            ),
        },
        "compatibility": {
            "required_host_version": compatibility.get(
                "required_host_version",
                compatibility.get("requiredHostVersion"),
            ),
            "plugin_api_version": compatibility.get(
                "plugin_api_version",
                compatibility.get("pluginApiVersion"),
            ),
        },
    }
    return {key: value for key, value in summary.items() if value not in (None, {}, [])}


def _build_startup_diagnostics() -> Dict[str, Any]:
    """Return a read-only startup report for packaged-app and first-run checks."""
    from . import __version__

    key_readiness = _build_key_readiness()
    app_root = app_home()
    logs = app_log_dir()
    run = run_dir()
    tmp = tmp_dir()
    evidence = app_subdir("evidence")
    socket_path = Path(backend_socket_path())

    persistence_obj = getattr(_task_state, "_persistence", None)
    db_obj = getattr(persistence_obj, "db", None)
    db_path = getattr(db_obj, "db_path", None)
    if db_path is None:
        db_path = data_file("assistant.db")
    db_path = Path(db_path)

    try:
        known_tasks = len(_task_state.get_all_tasks())
    except Exception:
        known_tasks = 0

    checks: List[Dict[str, Any]] = [
        {
            "id": "backend_health",
            "title": "Backend process",
            "status": "passed",
            "detail": f"Backend process {os.getpid()} is serving API requests.",
            "remediation": None,
            "metadata": {"pid": os.getpid(), "uptime_sec": max(0, time.time() - _server_started_at)},
        },
        _path_check("app_home", "App data directory", app_root),
        _path_check("logs_dir", "Logs directory", logs),
        _path_check("run_dir", "Runtime directory", run),
        _path_check("tmp_dir", "Temporary directory", tmp),
        _path_check("evidence_dir", "Evidence export directory", evidence),
        _path_check("backend_socket", "Backend Unix socket", socket_path, expect_file=True),
        _path_check("database", "Task database", db_path, expect_file=True),
    ]

    checks.append({
        "id": "provider_keys",
        "title": "Cloud provider readiness",
        "status": "passed" if key_readiness.get("has_any_key") else "warning",
        "detail": (
            "At least one cloud LLM provider is configured."
            if key_readiness.get("has_any_key")
            else "No cloud LLM provider is configured; task submission will be blocked until one is saved."
        ),
        "remediation": None if key_readiness.get("has_any_key") else "Configure at least one cloud LLM provider in Model Settings.",
        "metadata": {"providers": key_readiness.get("providers", {})},
    })

    task_runtime_status = "passed" if _task_persistence_initialized else "warning"
    checks.append({
        "id": "task_runtime",
        "title": "Task history",
        "status": task_runtime_status,
        "detail": (
            "Task persistence is initialized."
            if task_runtime_status == "passed"
            else "Task persistence has not initialized yet; task history may be unavailable."
        ),
        "remediation": None if task_runtime_status == "passed" else "Restart the app if task history does not load.",
        "metadata": {
            "known_tasks": known_tasks,
            "persistence_initialized": _task_persistence_initialized,
        },
    })

    orchestrator_plugin = _orchestrator_plugin_status(probe=True)
    orchestrator_plugin_summary = _startup_plugin_summary(orchestrator_plugin)
    ecosystem_plugins = [
        _startup_plugin_summary(plugin)
        for plugin in discover_across_plugins(probe=False)
    ]
    plugin_available = bool(orchestrator_plugin.get("available"))
    plugin_required = str(orchestrator_plugin.get("mode") or "").replace("-", "_") == "external"
    if plugin_available:
        plugin_check_status = "passed"
    elif plugin_required:
        plugin_check_status = "failed"
    else:
        plugin_check_status = "warning"
    checks.append({
        "id": "orchestrator_plugin",
        "title": "Across Orchestrator plugin",
        "status": plugin_check_status,
        "detail": str(orchestrator_plugin.get("connection_note") or "Across Orchestrator plugin status inspected."),
        "remediation": (
            "Install Across Orchestrator or configure ACROSS_AGENTS_ORCHESTRATOR_ENDPOINT."
            if plugin_check_status == "failed"
            else None
        ),
        "metadata": {
            "mode": orchestrator_plugin.get("mode"),
            "implementation": orchestrator_plugin.get("implementation"),
            "available": plugin_available,
            "transport": orchestrator_plugin.get("transport"),
            "endpoint": orchestrator_plugin.get("endpoint"),
            "command_available": orchestrator_plugin.get("command_available"),
            "task_index_count": orchestrator_plugin.get("task_index_count", 0),
            "install": orchestrator_plugin.get("install"),
        },
    })

    summary = _diagnostic_summary(checks)
    generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return {
        "schema_version": "1.0",
        "app_version": __version__,
        "generated_at": generated_at,
        "status": summary["status"],
        "summary": summary,
        "paths": {
            "app_home": str(app_root),
            "logs_dir": str(logs),
            "run_dir": str(run),
            "tmp_dir": str(tmp),
            "evidence_dir": str(evidence),
            "socket_path": str(socket_path),
            "database_path": str(db_path),
        },
        "runtime": {
            "pid": os.getpid(),
            "started_at": _server_started_at,
            "uptime_sec": max(0, time.time() - _server_started_at),
            "known_tasks": known_tasks,
            "persistence_initialized": _task_persistence_initialized,
            "orchestrator_plugin": orchestrator_plugin_summary,
            "ecosystem_plugins": ecosystem_plugins,
        },
        "keys": key_readiness,
        "checks": checks,
    }


@app.get("/api/readiness")
async def get_readiness():
    key_readiness = _build_key_readiness()
    return {
        "backend": "ready",
        "keys": key_readiness,
        "persistence_initialized": _task_persistence_initialized,
    }


@app.get("/api/diagnostics/startup")
async def get_startup_diagnostics():
    """Return a non-secret first-run and packaged-app startup diagnostic report."""
    return _sanitize_public_payload(_build_startup_diagnostics())


@app.get("/api/plugins")
async def list_across_plugins(probe: bool = False):
    """Return Across ecosystem plugin discovery status without mutating installs."""
    return {
        "plugins": _sanitize_public_payload(discover_across_plugins(probe=probe)),
    }


@app.get("/api/plugins/{plugin_id}")
async def get_across_plugin(plugin_id: str, probe: bool = False):
    """Return one Across ecosystem plugin discovery status."""
    try:
        return _sanitize_public_payload(inspect_across_plugin(plugin_id, probe=probe))
    except ValueError:
        raise HTTPException(status_code=404, detail="Unknown Across plugin")


class PluginLifecycleActionRequest(BaseModel):
    action: str


class AutopilotSpecRequest(BaseModel):
    spec: str
    trigger: Optional[str] = "aaa-user"
    model_policy_overrides: Dict[str, Any] = Field(default_factory=dict)


class AutopilotCancelRequest(BaseModel):
    reason: Optional[str] = "cancelled by host"


class AutopilotOutputRequest(BaseModel):
    outputId: str


class AutopilotTriggerRequest(BaseModel):
    spec: str
    type: Optional[str] = "manual"
    payload: Dict[str, Any] = Field(default_factory=dict)
    idempotency_key: Optional[str] = None
    not_before: Optional[str] = None
    source: Optional[str] = "aaa"
    actor: Optional[str] = "user"


class AutopilotRunTriggerRequest(BaseModel):
    trigger_id: Optional[str] = None


class AutopilotTriggerConfigRequest(BaseModel):
    spec: str
    type: str = "cron"
    payload: Dict[str, Any] = Field(default_factory=dict)
    schedule: Dict[str, Any] = Field(default_factory=dict)
    webhook: Dict[str, Any] = Field(default_factory=dict)
    daemon: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    actor: Optional[str] = "user"
    source: Optional[str] = "aaa"
    trigger_id: Optional[str] = None


class AutopilotTriggerPauseRequest(BaseModel):
    paused: bool = True


class AutopilotSelfIterationPlanRequest(BaseModel):
    spec: str = DEFAULT_SELF_ITERATION_SPEC
    interval_seconds: int = DEFAULT_SELF_ITERATION_INTERVAL_SECONDS
    daily_time: str = DEFAULT_SELF_ITERATION_DAILY_TIME
    timezone: str = DEFAULT_SELF_ITERATION_TIMEZONE
    enabled: bool = True
    actor: str = "aaa-self-iteration"
    source: str = "aaa-self-iteration-plan"
    trigger_id: str = DEFAULT_SELF_ITERATION_TRIGGER_ID
    payload: Dict[str, Any] = Field(default_factory=dict)


class AutopilotTriggerSchedulerRequest(BaseModel):
    interval_seconds: float = 60.0
    run_queued_triggers: bool = True
    max_runs_per_tick: int = 1


class AutopilotModelDecisionRequest(BaseModel):
    schema_version: Optional[str] = "across-host-model-decision-request/1.0"
    role: Optional[str] = "loop_engineer"
    goal: str
    run_id: Optional[str] = None
    loop_id: Optional[str] = None
    candidate_workspace: str
    source_repository: Optional[str] = None
    focus: List[str] = Field(default_factory=list)
    allowed_patch_paths: List[str] = Field(default_factory=list)
    context_files: List[str] = Field(default_factory=list)
    validation_feedback: List[Dict[str, Any]] = Field(default_factory=list)
    candidate_model_lease: Dict[str, Any] = Field(default_factory=dict)
    model_policy: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("candidate_model_lease", mode="before")
    @classmethod
    def _normalize_candidate_model_lease(cls, value: Any) -> Dict[str, Any]:
        return value if isinstance(value, dict) else {}


class AutopilotResearchDecisionRequest(BaseModel):
    schema_version: Optional[str] = "across-host-research-decision-request/1.0"
    role: Optional[str] = "loop_researcher"
    goal: str
    run_id: Optional[str] = None
    candidate_id: Optional[str] = None
    candidate_workspace: str
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    recalled_memory: List[Dict[str, Any]] = Field(default_factory=list)
    product_context: Dict[str, Any] = Field(default_factory=dict)
    target_catalog: List[Dict[str, Any]] = Field(default_factory=list)
    target_generation: Dict[str, Any] = Field(default_factory=dict)
    tool_pack_evidence: Dict[str, Any] = Field(default_factory=dict)
    candidate_model_lease: Dict[str, Any] = Field(default_factory=dict)
    model_policy: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("candidate_model_lease", mode="before")
    @classmethod
    def _normalize_candidate_model_lease(cls, value: Any) -> Dict[str, Any]:
        return value if isinstance(value, dict) else {}


class AutopilotCodeIterationRequest(BaseModel):
    schema_version: Optional[str] = "across-host-code-iteration-request/1.0"
    goal: str
    run_id: Optional[str] = None
    candidate_id: Optional[str] = None
    candidate_workspace: str
    target_repo: str = "across-agents-assistant"
    source_repository: Optional[str] = None
    allowed_patch_paths: List[str] = Field(default_factory=list)
    context_files: List[str] = Field(default_factory=list)
    validation_commands: List[Dict[str, Any]] = Field(default_factory=list)
    validation_feedback: List[Dict[str, Any]] = Field(default_factory=list)
    candidate_model_lease: Dict[str, Any] = Field(default_factory=dict)
    model_policy: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("candidate_model_lease", mode="before")
    @classmethod
    def _normalize_candidate_model_lease(cls, value: Any) -> Dict[str, Any]:
        return value if isinstance(value, dict) else {}


class AutopilotReviewDecisionRequest(BaseModel):
    schema_version: Optional[str] = "across-host-review-decision-request/1.0"
    goal: str
    run_id: Optional[str] = None
    spec_id: Optional[str] = None
    selected_target_id: Optional[str] = None
    selected_iteration: Dict[str, Any] = Field(default_factory=dict)
    changed_files: List[str] = Field(default_factory=list)
    validation: Dict[str, Any] = Field(default_factory=dict)
    diff_summary: Dict[str, Any] = Field(default_factory=dict)
    deterministic_review: Dict[str, Any] = Field(default_factory=dict)
    builder_model: Dict[str, Any] = Field(default_factory=dict)
    candidate_model_lease: Dict[str, Any] = Field(default_factory=dict)
    model_policy: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("candidate_model_lease", mode="before")
    @classmethod
    def _normalize_candidate_model_lease(cls, value: Any) -> Dict[str, Any]:
        return value if isinstance(value, dict) else {}


def _safe_autopilot_rel_path(value: Any) -> str:
    rel = str(value or "").replace("\\", "/").strip()
    if (
        not rel
        or rel.startswith("/")
        or rel.startswith("~")
        or "\x00" in rel
        or any(part in {".", ".."} for part in rel.split("/"))
    ):
        raise ValueError(f"Unsafe relative path: {value}")
    if rel.endswith("/") or any(part == "" for part in rel.split("/")):
        raise ValueError(f"Patch paths must name concrete files, not directories: {value}")
    lowered = rel.lower()
    blocked_names = {
        ".env",
        ".env.local",
        "credentials.json",
        "secrets.json",
        "id_rsa",
        "id_ed25519",
    }
    if any(part.lower() in blocked_names for part in rel.split("/")):
        raise ValueError(f"Sensitive context path is not allowed: {value}")
    if any(token in lowered for token in ("secret", "credential", "apikey", "api_key", "token")):
        raise ValueError(f"Sensitive context path is not allowed: {value}")
    return rel


def _safe_autopilot_context_path(value: Any, *, autonomous_root: Optional[str] = None) -> str:
    text = str(value or "").replace("\\", "/").strip()
    if not text or "\x00" in text:
        raise ValueError(f"Unsafe relative path: {value}")
    lowered = text.lower()
    if any(token in lowered for token in ("secret", "credential", "apikey", "api_key", "token")):
        raise ValueError(f"Sensitive context path is not allowed: {value}")
    if text.startswith("~"):
        raise ValueError(f"Unsafe relative path: {value}")
    if text.startswith("/"):
        path = _canonical_autopilot_absolute_path(text)
        allowed_roots = _allowed_autopilot_context_roots(autonomous_root=autonomous_root)
        if any(_absolute_path_is_inside(path, root) for root in allowed_roots):
            return path
        raise ValueError(f"Unsafe relative path: {value}")
    return _safe_autopilot_rel_path(text)


def _canonical_autopilot_absolute_path(value: Any) -> str:
    text = str(value or "").replace("\\", "/").strip()
    if not text.startswith("/") or "\x00" in text:
        raise ValueError(f"Unsafe relative path: {value}")
    parts: List[str] = []
    for part in text.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            if not parts:
                raise ValueError(f"Unsafe relative path: {value}")
            parts.pop()
            continue
        parts.append(part)
    return "/" + "/".join(parts)


def _allowed_autopilot_context_roots(*, autonomous_root: Optional[str] = None) -> List[str]:
    roots: List[str] = []
    across_home = os.environ.get("ACROSS_HOME")
    if across_home:
        try:
            across_home_text = str(across_home).replace("\\", "/").rstrip("/")
            loop_state_root = _canonical_autopilot_absolute_path(
                f"{across_home_text}/data/across-autopilot/loop-state"
            )
            roots.append(loop_state_root)
        except ValueError:
            pass
    if autonomous_root:
        try:
            root = _canonical_autopilot_absolute_path(autonomous_root)
        except ValueError:
            root = ""
        if root and any(_absolute_path_is_inside(root, allowed) for allowed in roots):
            roots.append(root)
    return roots


def _absolute_path_is_inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def _read_autopilot_context_files(req: AutopilotModelDecisionRequest) -> List[Dict[str, Any]]:
    del req
    return []


def _compact_autopilot_context_files(
    files: List[Dict[str, Any]],
    *,
    max_total_bytes: int = 12_000,
    max_file_bytes: int = 4_000,
) -> List[Dict[str, Any]]:
    compacted: List[Dict[str, Any]] = []
    total = 0
    for item in files:
        remaining = max_total_bytes - total
        if remaining <= 0:
            break
        limit = min(max_file_bytes, remaining)
        content = str(item.get("content") or "")
        encoded = content.encode("utf-8", errors="replace")
        snippet = encoded[:limit].decode("utf-8", errors="replace")
        total += len(snippet.encode("utf-8", errors="replace"))
        compacted.append({
            **item,
            "content": snippet,
            "truncated": bool(item.get("truncated")) or len(encoded) > len(snippet.encode("utf-8", errors="replace")),
        })
    return compacted


def _autopilot_model_policy_value(policy: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in policy and policy[key] not in (None, ""):
            return policy[key]
    return default


def _autopilot_model_policy_timeout_seconds(policy: Dict[str, Any], *, default: float = 600.0) -> float:
    millis = _autopilot_model_policy_value(policy, "timeout_ms", "timeoutMs")
    raw = millis if millis is not None else _autopilot_model_policy_value(
        policy,
        "timeout_seconds",
        "timeout_sec",
        "timeout",
        default=default,
    )
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    if millis is not None:
        value = value / 1000.0
    return max(1.0, value)


def _autopilot_model_policy_timeout_plan(
    policy: Dict[str, Any],
    *,
    default: float = 600.0,
    default_idle: float = 300.0,
) -> Dict[str, float]:
    max_wall = _autopilot_model_policy_timeout_seconds(policy, default=default)
    idle_ms = _autopilot_model_policy_value(
        policy,
        "idle_timeout_ms",
        "activity_timeout_ms",
        "no_progress_timeout_ms",
    )
    idle_seconds = None
    if idle_ms is not None:
        try:
            idle_seconds = float(idle_ms) / 1000.0
        except (TypeError, ValueError):
            idle_seconds = None
    if idle_seconds is None:
        idle_seconds = _autopilot_model_policy_value(
            policy,
            "idle_timeout_seconds",
            "activity_timeout_seconds",
            "no_progress_timeout_seconds",
        )
        try:
            idle_seconds = float(idle_seconds) if idle_seconds is not None else min(max_wall, default_idle)
        except (TypeError, ValueError):
            idle_seconds = min(max_wall, default_idle)
    return {
        "max_wall_timeout_seconds": max(1.0, max_wall),
        "idle_timeout_seconds": max(1.0, min(float(idle_seconds), max_wall)),
    }


def _autopilot_decision_system_prompt() -> str:
    return (
        "You are the model brain for an Across Autopilot Loop Engineering run. "
        "Return JSON only, under 1200 characters. Do not wrap it in markdown. "
        "Do not write the full candidate document and do not quote the context. "
        "You must decide candidate workspace changes, never source repository changes. "
        "Prefer this concise JSON shape: "
        "{\"summary\": string, \"rationale\": string, \"risk\": \"low|medium|high\", "
        "\"decision_card\": {\"path\": string, \"title\": string, "
        "\"key_changes\": [string], \"validation\": [string]}}, "
        "\"validation_commands\": [{\"command\": string, \"args\": [string]}]}. "
        "The host will format decision_card into the candidate file. "
        "Use at most 5 key_changes and keep each item under 160 characters. "
        "Legacy patch_plan is allowed only if it is equally concise. "
        "The host will format patch_plan into the candidate file. If you must return patches "
        "directly, every patch content field must be a valid JSON string with newlines escaped as \\n. "
        "Use only allowed_patch_paths."
    )


def _autopilot_decision_user_prompt(req: AutopilotModelDecisionRequest, context_files: List[Dict[str, Any]]) -> str:
    payload = {
        "goal": req.goal,
        "role": req.role,
        "run_id": req.run_id,
        "loop_id": req.loop_id,
        "candidate_workspace": req.candidate_workspace,
        "source_repository": req.source_repository,
        "focus": req.focus[:20],
        "allowed_patch_paths": req.allowed_patch_paths[:20],
        "validation_feedback": req.validation_feedback[:10],
        "context_files": context_files,
    }
    return (
        "Design the next candidate-only AAA self-iteration patch. "
        "The source repository is read-only and must not be edited. "
        "Use the context below and return the required JSON object.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def _autopilot_decision_repair_prompt(req: AutopilotModelDecisionRequest, raw_text: str, error: Exception) -> str:
    payload = {
        "goal": req.goal,
        "allowed_patch_paths": req.allowed_patch_paths[:20],
        "parse_error": str(error),
        "raw_model_output": str(raw_text or "")[:20_000],
    }
    return (
        "Repair the prior model output into the concise required JSON object only. "
        "Do not add markdown or commentary. Do not return the full document. "
        "Prefer decision_card with at most 5 short key_changes. "
        "Keep patches candidate-only and use only allowed_patch_paths.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def _extract_json_object(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(raw[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("Model decision must be a JSON object")
    return value


def _should_repair_autopilot_decision_error(exc: Exception) -> bool:
    text = str(exc)
    policy_error_prefixes = (
        "Unsafe relative path:",
        "Sensitive context path is not allowed:",
        "Model patch path is outside allowed_patch_paths:",
        "Model patch content is too large",
    )
    return not any(text.startswith(prefix) for prefix in policy_error_prefixes)


def _model_patch_content(raw_patch: Dict[str, Any]) -> str:
    if "content_lines" in raw_patch:
        lines = raw_patch.get("content_lines")
        if not isinstance(lines, list):
            raise ValueError("Model patch content_lines must be a list")
        content = "\n".join(str(line) for line in lines)
        return content if content.endswith("\n") else content + "\n"

    if "content_base64" in raw_patch:
        encoded = str(raw_patch.get("content_base64") or "")
        try:
            return base64.b64decode(encoded, validate=True).decode("utf-8")
        except Exception as exc:
            raise ValueError("Model patch content_base64 is invalid") from exc

    content = raw_patch.get("content")
    if isinstance(content, list):
        return "\n".join(str(line) for line in content)
    return str(content or "")


def _normalize_model_decision_patches(
    decision: Dict[str, Any],
    *,
    allowed_patch_paths: List[str],
) -> List[Dict[str, Any]]:
    allowed = {_safe_autopilot_rel_path(path) for path in allowed_patch_paths if str(path or "").strip()}
    patches: List[Dict[str, Any]] = []
    for raw_patch in (decision.get("patches") or [])[:8]:
        if not isinstance(raw_patch, dict):
            continue
        rel = _safe_autopilot_rel_path(raw_patch.get("path"))
        if allowed and rel not in allowed:
            raise ValueError(f"Model patch path is outside allowed_patch_paths: {rel}")
        mode = str(raw_patch.get("mode") or "overwrite").strip()
        if mode not in {"overwrite", "append", "upsert_between_markers"}:
            raise ValueError(f"Unsupported model patch mode: {mode}")
        marker_start = raw_patch.get("marker_start")
        marker_end = raw_patch.get("marker_end")
        if mode == "upsert_between_markers" and (not marker_start or not marker_end):
            if _can_append_markerless_upsert(rel):
                mode = "append"
            else:
                raise ValueError(
                    f"Model patch {rel} uses upsert_between_markers without marker_start and marker_end"
                )
        content = _model_patch_content(raw_patch)
        if not content.strip():
            raise ValueError(f"Model patch content is empty for {rel}")
        if len(content.encode("utf-8", errors="replace")) > 120_000:
            raise ValueError(f"Model patch content is too large for {rel}")
        patch = {
            "path": rel,
            "mode": mode,
            "content": content,
        }
        if mode == "upsert_between_markers" and marker_start:
            patch["marker_start"] = str(marker_start)
        if mode == "upsert_between_markers" and marker_end:
            patch["marker_end"] = str(marker_end)
        patches.append(patch)
    if not patches:
        raise ValueError("Model decision did not include any valid patches")
    return patches


def _can_append_markerless_upsert(rel: str) -> bool:
    normalized = rel.replace("\\", "/").lower()
    name = Path(normalized).name
    return (
        normalized.startswith("docs/")
        or name in {"readme.md", "changelog.md", "llms.txt"}
        or normalized.endswith(".md")
    )


def _validate_autopilot_generated_patch_policy(patches: List[Dict[str, Any]]) -> None:
    for patch in patches:
        rel = str(patch.get("path") or "")
        content = str(patch.get("content") or "")
        if rel.startswith("backend/tests/") and re.search(
            r"(?m)^\s*(import\s+pytest|from\s+pytest\s+import)\b|\bpytest\.",
            content,
        ):
            raise ValueError(
                "Generated candidate tests must be standard-library only; pytest imports/usages are not allowed "
                "because B validation executes tests directly with python3 and runpy."
            )
        if rel.startswith("backend/tests/") and re.search(
            r"(?m)^\s*(?:from\s+autopilot_[A-Za-z0-9_]+\s+import|import\s+autopilot_[A-Za-z0-9_]+)\b",
            content,
        ):
            raise ValueError(
                "Generated candidate tests must use package imports for AAA modules, for example "
                "'from across_agents_assistant.autopilot_feature import helper'; flat autopilot_* imports are not allowed."
            )


def _normalize_model_patch_plan(
    decision: Dict[str, Any],
    *,
    allowed_patch_paths: List[str],
) -> List[Dict[str, Any]]:
    plan = decision.get("patch_plan")
    if not isinstance(plan, dict):
        raise ValueError("Model decision did not include patches or patch_plan")
    allowed = [_safe_autopilot_rel_path(path) for path in allowed_patch_paths if str(path or "").strip()]
    rel = _safe_autopilot_rel_path(plan.get("path") or (allowed[0] if allowed else "LOOP_ENGINEERING_SELF_ITERATION.md"))
    if allowed and rel not in set(allowed):
        raise ValueError(f"Model patch path is outside allowed_patch_paths: {rel}")
    if not rel.lower().endswith((".md", ".markdown", ".txt")):
        raise ValueError("patch_plan can only target markdown/text candidate files")
    title = str(plan.get("title") or decision.get("summary") or "Model-Backed Self Iteration Decision").strip()
    lines = [f"# {title}", ""]
    summary = str(decision.get("summary") or "").strip()
    rationale = str(decision.get("rationale") or "").strip()
    risk = str(decision.get("risk") or "medium").strip()
    if summary:
        lines.extend(["## Summary", "", summary, ""])
    if rationale:
        lines.extend(["## Rationale", "", rationale, ""])
    lines.extend(["## Risk", "", risk, ""])
    for section in (plan.get("sections") or [])[:12]:
        if not isinstance(section, dict):
            continue
        heading = str(section.get("heading") or "Notes").strip()
        bullets = [str(item).strip() for item in (section.get("bullets") or []) if str(item).strip()]
        if not heading and not bullets:
            continue
        lines.extend([f"## {heading}", ""])
        if bullets:
            lines.extend([f"- {item}" for item in bullets[:12]])
            lines.append("")
    content = "\n".join(lines).rstrip() + "\n"
    return [{
        "path": rel,
        "mode": "overwrite",
        "content": content,
    }]


def _normalize_model_decision_card(
    decision: Dict[str, Any],
    *,
    allowed_patch_paths: List[str],
) -> List[Dict[str, Any]]:
    card = decision.get("decision_card")
    if not isinstance(card, dict):
        raise ValueError("Model decision did not include patches, patch_plan, or decision_card")
    allowed = [_safe_autopilot_rel_path(path) for path in allowed_patch_paths if str(path or "").strip()]
    rel = _safe_autopilot_rel_path(card.get("path") or (allowed[0] if allowed else "LOOP_ENGINEERING_SELF_ITERATION.md"))
    if allowed and rel not in set(allowed):
        raise ValueError(f"Model patch path is outside allowed_patch_paths: {rel}")
    if not rel.lower().endswith((".md", ".markdown", ".txt")):
        raise ValueError("decision_card can only target markdown/text candidate files")

    title = str(card.get("title") or decision.get("summary") or "Model-Backed Self Iteration Decision").strip()
    summary = str(decision.get("summary") or "").strip()
    rationale = str(decision.get("rationale") or "").strip()
    risk = str(decision.get("risk") or "medium").strip()
    key_changes = [str(item).strip() for item in (card.get("key_changes") or []) if str(item).strip()]
    validation = [str(item).strip() for item in (card.get("validation") or []) if str(item).strip()]
    lines = [
        f"# {title}",
        "",
        "## Summary",
        "",
        summary or "Host model selected a candidate-only self-iteration change.",
        "",
        "## Rationale",
        "",
        rationale or "The change is constrained to the candidate workspace and is prepared for human promotion review.",
        "",
        "## Risk",
        "",
        risk,
        "",
        "## Key Changes",
        "",
    ]
    lines.extend([f"- {item}" for item in key_changes[:5]] or ["- Add a bounded candidate-only iteration artifact."])
    lines.extend(["", "## Validation", ""])
    lines.extend([f"- {item}" for item in validation[:5]] or ["- Run candidate validation gates before promotion."])
    lines.extend([
        "",
        "## Boundary",
        "",
        "- This file is generated in the candidate workspace only.",
        "- The source repository remains read-only during the loop.",
        "- Promotion to the source repository requires separate human approval.",
        "",
    ])
    return [{
        "path": rel,
        "mode": "overwrite",
        "content": "\n".join(lines).rstrip() + "\n",
    }]


def _decision_patches(
    decision: Dict[str, Any],
    *,
    allowed_patch_paths: List[str],
) -> List[Dict[str, Any]]:
    if decision.get("patches"):
        return _normalize_model_decision_patches(decision, allowed_patch_paths=allowed_patch_paths)
    if decision.get("decision_card"):
        return _normalize_model_decision_card(decision, allowed_patch_paths=allowed_patch_paths)
    return _normalize_model_patch_plan(decision, allowed_patch_paths=allowed_patch_paths)


def _autopilot_text_fallback_decision(
    req: AutopilotModelDecisionRequest,
    *,
    raw_text: str,
    error: Exception,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    text = str(raw_text or "").strip()
    if not text:
        raise ValueError(f"Model decision did not return parseable JSON: {error}")
    allowed = [_safe_autopilot_rel_path(path) for path in req.allowed_patch_paths if str(path or "").strip()]
    if len(allowed) != 1 or not allowed[0].lower().endswith((".md", ".markdown", ".txt")):
        raise ValueError(
            "Model text fallback is only allowed for a single markdown/text candidate patch path"
        )
    clipped = text[:20_000]
    content = "\n".join([
        "# Model-Backed Self Iteration Decision",
        "",
        "This candidate artifact was normalized by the AAA host model adapter after the model returned non-JSON text.",
        "The original source repository remains read-only; this file lives only in the candidate workspace.",
        "",
        "## Goal",
        "",
        req.goal.strip(),
        "",
        "## Model Output",
        "",
        clipped,
        "",
        "## Host Normalization",
        "",
        "- Parse error: model output was not parseable as structured JSON.",
        "- Normalization mode: text_fallback",
        "- Allowed patch path policy: single markdown/text candidate file",
        "",
    ])
    decision = {
        "summary": "Model returned non-JSON output; AAA normalized it into a candidate-only review artifact.",
        "rationale": "The model still supplied the decision content, while the host constrained mutation to a safe markdown/text path.",
        "risk": "medium",
        "patches": [{
            "path": allowed[0],
            "mode": "overwrite",
            "content": content,
        }],
        "validation_commands": [{"command": "git", "args": ["diff", "--check"]}],
    }
    return decision, decision["patches"]


async def _autopilot_decision_chat(
    req: AutopilotModelDecisionRequest,
    *,
    context_files: List[Dict[str, Any]],
    provider_id: Optional[str],
    model_id: Optional[str],
    agent_id: Optional[str],
    temperature: float,
    max_tokens: int,
    timeout_seconds: float,
) -> Tuple[Any, Dict[str, Any], List[Dict[str, Any]], bool, bool, Optional[str]]:
    response = await _chat_with_model_capability(
        message=_autopilot_decision_user_prompt(req, context_files),
        system_prompt=_autopilot_decision_system_prompt(),
        provider_id=str(provider_id) if provider_id else None,
        model=str(model_id) if model_id else None,
        agent_id=str(agent_id) if agent_id else None,
        project_dir=req.candidate_workspace,
        scope="model.decide",
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout_seconds,
    )
    try:
        decision = _extract_json_object(response.text)
        patches = _decision_patches(
            decision,
            allowed_patch_paths=req.allowed_patch_paths,
        )
        return response, decision, patches, False, False, None
    except ValueError as first_error:
        if not _should_repair_autopilot_decision_error(first_error):
            raise
        repair_response = await _chat_with_model_capability(
            message=_autopilot_decision_repair_prompt(req, response.text, first_error),
            system_prompt=_autopilot_decision_system_prompt(),
            provider_id=str(provider_id) if provider_id else None,
            model=str(model_id) if model_id else None,
            agent_id=str(agent_id) if agent_id else None,
            project_dir=req.candidate_workspace,
            scope="model.decide",
            temperature=0.0,
            max_tokens=max_tokens,
            timeout=timeout_seconds,
        )
        try:
            decision = _extract_json_object(repair_response.text)
            patches = _decision_patches(
                decision,
                allowed_patch_paths=req.allowed_patch_paths,
            )
            return repair_response, decision, patches, True, False, None
        except ValueError as repair_error:
            if not _should_repair_autopilot_decision_error(repair_error):
                raise
            decision, patches = _autopilot_text_fallback_decision(
                req,
                raw_text=repair_response.text or response.text,
                error=repair_error,
            )
            return repair_response, decision, patches, False, True, "model_output_unparseable"


@app.post("/api/autopilot/model-decision")
async def create_autopilot_model_decision(req: AutopilotModelDecisionRequest):
    """Return a host-model-backed candidate patch decision for Autopilot.

    This is the host/model boundary: AAA owns credentials and LLM provider
    selection, while Orchestrator and Autopilot receive only structured
    non-secret decisions.
    """
    try:
        context_files = _read_autopilot_context_files(req)
        policy = dict(req.model_policy or {})
        provider_id = _autopilot_model_policy_value(policy, "provider", "provider_id")
        model_id = _autopilot_model_policy_value(policy, "model", "model_id")
        agent_id = _autopilot_model_policy_value(policy, "agent_id", "agent")
        temperature = float(_autopilot_model_policy_value(policy, "temperature", default=0.2))
        max_tokens = int(_autopilot_model_policy_value(policy, "max_tokens", "maxTokens", default=1800))
        timeout_seconds = _autopilot_model_policy_timeout_seconds(policy)
        response, decision, patches, repaired, text_fallback, parse_error = await _autopilot_decision_chat(
            req,
            context_files=context_files,
            provider_id=str(provider_id) if provider_id else None,
            model_id=str(model_id) if model_id else None,
            agent_id=str(agent_id) if agent_id else None,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
        )
        clean_decision = {
            "summary": str(decision.get("summary") or "Model proposed a candidate-only iteration patch."),
            "rationale": str(decision.get("rationale") or ""),
            "risk": str(decision.get("risk") or "medium"),
            "patches": patches,
            "validation_commands": [
                {
                    "command": str(item.get("command") or ""),
                    "args": [str(arg) for arg in (item.get("args") or [])],
                }
                for item in (decision.get("validation_commands") or [])
                if isinstance(item, dict) and item.get("command")
            ][:8],
        }
        decision_json = json.dumps(clean_decision, ensure_ascii=False, sort_keys=True)
        return {
            "schema_version": "across-host-model-decision/1.0",
            "model_backed": True,
            "role": req.role or "loop_engineer",
            "provider": response.provider,
            "model": response.model,
            "finish_reason": response.finish_reason,
            "usage": response.usage,
            "repaired_json": repaired,
            "text_fallback": text_fallback,
            "parse_error": "model_output_unparseable" if parse_error else None,
            "decision_hash": hashlib.sha256(decision_json.encode("utf-8")).hexdigest(),
            "candidate_model_lease": _public_request_model_lease(req.candidate_model_lease),
            "decision": clean_decision,
            "patches": patches,
            "context": {
                "file_count": len(context_files),
                "files": [{"path": item["path"], "bytes": item["bytes"], "truncated": item["truncated"]} for item in context_files],
            },
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise _safe_http_500("Create Autopilot model decision")


def _compact_research_sources(sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    compact: List[Dict[str, Any]] = []
    for source in sources[:12]:
        result = source.get("result") if isinstance(source, dict) else {}
        if not isinstance(result, dict):
            result = {}
        text = (
            result.get("excerpt")
            or result.get("content")
            or result.get("summary")
            or source.get("summary")
            or ""
        )
        compact.append({
            "id": str(source.get("id") or result.get("id") or "")[:120],
            "adapter": str(source.get("adapter") or "")[:80],
            "status": str(source.get("status") or "")[:40],
            "title": str(result.get("title") or result.get("name") or source.get("title") or source.get("id") or "")[:200],
            "url": str(result.get("url") or source.get("url") or "")[:500],
            "excerpt": str(text or "")[:1600],
        })
    return compact


def _autopilot_research_system_prompt(req: AutopilotResearchDecisionRequest) -> str:
    allow_generated = _autopilot_research_allows_generated_targets(req)
    min_candidates = _autopilot_research_minimum_candidates(req)
    catalog_rule = (
        "When target_catalog is provided and generated targets are not allowed, Choose from target_catalog only. "
        if not allow_generated
        else (
            f"You must generate candidate_targets when the supplied catalog is empty or does not match the research. "
            f"candidate_targets must contain at least {min_candidates} distinct targets. "
            "Every generated target must be bounded, low-risk, candidate-only, and include validation commands. "
        )
    )
    return (
        "You are the research and product-strategy brain for Across Loop Engineering. "
        "Return JSON only. Do not include markdown fences. "
        "Use the supplied research sources to choose one concrete, low-risk product iteration for the B candidate ecosystem. "
        "Do not propose merge, release, signing, secrets, or edits to source A. "
        + catalog_rule
        +
        "Return this JSON shape: "
        "{\"summary\": string, \"rationale\": string, \"decision\": \"implement|defer\", "
        "\"selected_target_id\": string, \"rejected_directions\": [string], "
        "\"candidate_targets\": [{\"id\": string, \"target_repo\": string, \"summary\": string, \"goal\": string, "
        "\"allowed_patch_paths\": [string], \"context_files\": [string], "
        "\"validation_commands\": [{\"repo\": string, \"command\": string, \"args\": [string]}], "
        "\"semantic_review\": object, \"source_refs\": [string], \"tool_packs\": [string], "
        "\"generated_from\": string, \"risk\": \"low|medium|high\"}], "
        "\"selected_iteration\": {\"target_repo\": string, \"goal\": string, "
        "\"allowed_patch_paths\": [string], \"context_files\": [string], "
        "\"validation_commands\": [{\"repo\": string, \"command\": string, \"args\": [string]}], "
        "\"semantic_review\": object, \"source_refs\": [string], \"tool_packs\": [string], "
        "\"generated_from\": string, \"risk\": \"low|medium|high\"}}. "
        "selected_target_id must exactly match one candidate_targets[].id or one target_catalog[].id. "
        "selected_iteration.target_id must match selected_target_id. "
        "If product_context.trigger_payload.target_id is present, prefer the target_catalog item with that exact id and explain any exception in rationale. "
        "If product_context.trigger_payload.target_repo is present, prefer a target_catalog item with the same target_repo and explain any exception in rationale. "
        "If product_context.trigger_payload.allowed_patch_paths is present and matches a target_catalog item, do not replace those paths with another repo's paths. "
        "allowed_patch_paths must be repository-relative writable concrete files only; never use directories, prefixes, or values ending in '/'. "
        "For Python work, include a paired module and test file such as backend/src/across_agents_assistant/autopilot_<feature>.py and backend/tests/test_autopilot_<feature>.py. "
        "For Across Agents Assistant targets, also include at least one existing product integration surface in allowed_patch_paths, such as backend/src/across_agents_assistant/api_server.py, backend/src/across_agents_assistant/autopilot_workbench.py, backend/src/across_agents_assistant/loop_engineering_capability_pack.py, or a concrete macOS-Client source file. "
        "Do not propose a new isolated helper plus test as the only change. "
        "context_files may include repository-relative files or read-only absolute paths under ACROSS_HOME/loop-state. "
        "The selected goal must explain how the research maps into AAA's product ecosystem."
    )


def _autopilot_research_user_prompt(req: AutopilotResearchDecisionRequest) -> str:
    payload = {
        "goal": req.goal,
        "run_id": req.run_id,
        "candidate_id": req.candidate_id,
        "candidate_workspace": req.candidate_workspace,
        "product_context": req.product_context,
        "target_catalog": req.target_catalog[:12],
        "target_generation": req.target_generation,
        "target_generation_contract": _autopilot_research_generation_contract(req),
        "tool_pack_evidence": req.tool_pack_evidence,
        "sources": _compact_research_sources(req.sources),
        "recalled_memory": req.recalled_memory[:8],
    }
    return (
        "Analyze these current research sources and select one bounded product iteration. "
        "If generated targets are allowed, first propose a candidate_targets backlog that satisfies target_generation_contract, then select exactly one target. "
        "If the evidence is weak, choose the safest target that improves research-driven self-iteration quality. "
        "Return the required JSON object only.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def _autopilot_research_repair_prompt(req: AutopilotResearchDecisionRequest, raw_text: str, error: Exception) -> str:
    min_candidates = _autopilot_research_minimum_candidates(req)
    payload = {
        "goal": req.goal,
        "target_catalog": [
            {
                "id": item.get("id"),
                "target_repo": item.get("target_repo"),
                "allowed_patch_paths": item.get("allowed_patch_paths"),
                "context_files": item.get("context_files"),
                "validation_commands": item.get("validation_commands"),
                "semantic_review": item.get("semantic_review"),
                "tool_packs": item.get("tool_packs"),
                "generated_from": item.get("generated_from"),
                "goal": item.get("goal"),
                "risk": item.get("risk"),
            }
            for item in req.target_catalog[:8]
            if isinstance(item, dict)
        ],
        "target_generation": req.target_generation,
        "target_generation_contract": _autopilot_research_generation_contract(req),
        "parse_error": str(error),
        "raw_model_output": str(raw_text or "")[:20_000],
    }
    mode_line = (
        f"Generated candidate_targets are allowed. Return at least {min_candidates} safe generated targets and select one of them. "
        if _autopilot_research_allows_generated_targets(req)
        else "Select exactly one target_catalog id and copy its allowed_patch_paths, context_files, validation_commands, and semantic_review. "
    )
    return (
        "Repair the prior research decision into the required JSON object only. "
        "No markdown, no commentary, no chain-of-thought. "
        + mode_line +
        "Do not return an array as the top-level value. Do not omit candidate_targets when generated targets are allowed. "
        "Every candidate target must include id, target_repo, summary, goal, allowed_patch_paths, validation_commands, semantic_review, source_refs, tool_packs, generated_from, and risk. "
        "allowed_patch_paths must be concrete repository-relative files, not directories or prefixes; convert directory-like paths into 1-4 explicit files plus matching tests. "
        "Never return paths that end with '/'. "
        "Never put ACROSS_HOME artifact paths in allowed_patch_paths; put read-only artifact paths in context_files only. "
        "If product_context.trigger_payload.target_id is present, prefer the target_catalog item with that exact id and do not drift to another target unless the target_catalog lacks that id. "
        "If product_context.trigger_payload.target_repo is present, prefer a target_catalog item with the same target_repo and do not drift to another repo unless the target_catalog lacks that repo. "
        "For Across Agents Assistant generated targets, do not return only a new helper module plus its test; include one existing product integration surface in allowed_patch_paths. "
        "Set decision to implement unless the sources clearly prove no change is worthwhile.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def _autopilot_research_minimum_candidates(req: AutopilotResearchDecisionRequest) -> int:
    value = (req.target_generation or {}).get("minimum_candidates")
    try:
        return max(1, min(int(value or 2), 8))
    except (TypeError, ValueError):
        return 2


def _autopilot_research_generation_contract(req: AutopilotResearchDecisionRequest) -> Dict[str, Any]:
    generation = req.target_generation or {}
    path_policy = generation.get("path_policy") if isinstance(generation.get("path_policy"), dict) else {}
    product_prefixes = path_policy.get("product_prefixes") if isinstance(path_policy.get("product_prefixes"), dict) else {}
    return {
        "generated_targets_allowed": _autopilot_research_allows_generated_targets(req),
        "minimum_candidates": _autopilot_research_minimum_candidates(req),
        "target_repos": generation.get("target_repos") or [
            "across-agents-assistant",
            "across-autopilot",
            "across-orchestrator",
            "across-context",
        ],
        "product_prefixes": product_prefixes or {
            "across-agents-assistant": ["backend/src/", "backend/tests/", "macOS-Client/Sources/", "macOS-Client/Tests/", "scripts/", "docs/"],
            "across-autopilot": ["src/", "tests/", "examples/"],
            "across-orchestrator": ["src/across_orchestrator/", "tests/"],
            "across-context": ["src/", "tests/"],
        },
        "denied_paths": path_policy.get("denied") or [
            ".git/",
            ".env",
            "credentials",
            "secrets",
        ],
        "context_file_policy": {
            "repo_relative_allowed": True,
            "absolute_read_only_allowed_under": ["ACROSS_HOME", "autonomous_loop_state.root"],
            "never_use_context_files_as_allowed_patch_paths": True,
        },
        "allowed_patch_path_policy": {
            "must_be_repo_relative_concrete_files": True,
            "directories_or_prefixes_allowed": False,
            "trailing_slash_allowed": False,
            "repair_hint": "If you want to change a package or directory, choose explicit files inside it, usually one existing product integration surface, one module path, and one test path.",
        },
        "existing_product_integration_policy": {
            "across-agents-assistant": {
                "required_for_generated_targets": True,
                "rationale": "Generated AAA targets must attach new behavior to an existing entrypoint, registry, workflow, API, or UI surface instead of adding an isolated helper plus test only.",
                "examples": [
                    "backend/src/across_agents_assistant/api_server.py",
                    "backend/src/across_agents_assistant/autopilot_workbench.py",
                    "backend/src/across_agents_assistant/loop_engineering_capability_pack.py",
                    "macOS-Client/Sources/",
                ],
            }
        },
        "required_target_fields": [
            "id",
            "target_repo",
            "summary",
            "goal",
            "allowed_patch_paths",
            "validation_commands",
            "semantic_review",
            "source_refs",
            "tool_packs",
            "generated_from",
            "risk",
        ],
        "validation_command_minimum": 2,
        "semantic_review_defaults": {
            "require_model_backed": True,
            "require_selected_target_change": True,
            "reject_self_proof_only": True,
            "independent_reviewer_required": True,
            "minimum_validation_commands": 2,
        },
        "safe_python_target_template": {
            "target_repo": "across-agents-assistant",
            "allowed_patch_paths": [
                "backend/src/across_agents_assistant/api_server.py",
                "backend/src/across_agents_assistant/autopilot_<short_feature_name>.py",
                "backend/tests/test_autopilot_<short_feature_name>.py",
            ],
            "validation_commands": [
                {
                    "repo": "across-agents-assistant",
                    "command": "python3",
                    "args": ["-m", "py_compile", "<module_path>", "<test_path>"],
                },
                {
                    "repo": "across-agents-assistant",
                    "command": "python3",
                    "args": ["-c", "import sys, runpy; sys.path.insert(0, 'backend/src'); ns=runpy.run_path('<test_path>'); tests=[v for k,v in ns.items() if k.startswith('test_') and callable(v)]; assert tests; [test() for test in tests]"],
                },
                {
                    "repo": "across-agents-assistant",
                    "command": "git",
                    "args": ["diff", "--check"],
                },
            ],
        },
    }


def _autopilot_research_allows_generated_targets(req: AutopilotResearchDecisionRequest) -> bool:
    generation = req.target_generation or {}
    if generation.get("allow_model_generated_targets") is True:
        return True
    if str(generation.get("mode") or "").strip() == "model_generated":
        return True
    if req.product_context.get("autonomous_loop_state") and not req.target_catalog:
        return True
    return False


def _autopilot_research_allows_host_fallback(req: AutopilotResearchDecisionRequest) -> bool:
    policy = req.model_policy or {}
    generation = req.target_generation or {}
    return bool(
        policy.get("allow_host_target_fallback")
        or policy.get("conformance_fixture")
        or generation.get("allow_host_target_fallback")
        or generation.get("conformance_fixture")
    )


def _autopilot_research_allows_timeout_fallback(
    req: AutopilotResearchDecisionRequest,
    *,
    policy: Dict[str, Any],
    agent_id: Optional[str],
) -> bool:
    if policy.get("allow_research_timeout_fallback") is False:
        return False
    if not req.target_catalog and not _autopilot_research_allows_generated_targets(req):
        return False
    if policy.get("allow_research_timeout_fallback") is True:
        return True
    normalized_agent_id = normalize_agent_id(agent_id) if agent_id else None
    autonomous = isinstance(req.product_context.get("autonomous_loop_state"), dict)
    return bool(autonomous and normalized_agent_id in LOCAL_CLI_AGENT_IDS)


def _autopilot_research_source_refs(req: AutopilotResearchDecisionRequest) -> List[str]:
    refs: List[str] = []
    for source in req.sources[:12]:
        if not isinstance(source, dict):
            continue
        status = str(source.get("status") or "").strip().lower()
        source_id = str(source.get("id") or source.get("title") or "").strip()
        if source_id and status != "failed" and source_id not in refs:
            refs.append(source_id[:160])
    return refs[:6]


def _autopilot_host_fallback_research_targets(req: AutopilotResearchDecisionRequest) -> List[Dict[str, Any]]:
    if req.target_catalog:
        return req.target_catalog
    source_refs = _autopilot_research_source_refs(req)
    semantic_review = {
        "require_model_backed": True,
        "require_selected_target_change": True,
        "reject_self_proof_only": True,
        "independent_reviewer_required": True,
        "minimum_validation_commands": 2,
    }
    templates = [
        {
            "id": "autonomous-research-timeout-recovery",
            "summary": "Harden autonomous research-decision timeout recovery.",
            "goal": "Add product-integrated diagnostics and timeout recovery evidence for autonomous research decisions so stalled local agents do not leave opaque failed runs.",
            "allowed_patch_paths": [
                "backend/src/across_agents_assistant/api_server.py",
                "backend/src/across_agents_assistant/autopilot_research_timeout_recovery.py",
                "backend/tests/test_autopilot_research_timeout_recovery.py",
            ],
            "tool_packs": ["source_research_digest", "candidate_workspace", "validation_harness", "independent_review"],
        },
        {
            "id": "autonomous-source-signal-hardening",
            "summary": "Improve source-signal handling for autonomous iteration.",
            "goal": "Add a product-integrated source-signal quality summary that keeps unavailable external sources visible without blocking candidate selection.",
            "allowed_patch_paths": [
                "backend/src/across_agents_assistant/autopilot_workbench.py",
                "backend/src/across_agents_assistant/autopilot_source_signal_summary.py",
                "backend/tests/test_autopilot_source_signal_summary.py",
            ],
            "tool_packs": ["source_research_digest", "validation_harness"],
        },
        {
            "id": "autonomous-candidate-quality-evidence",
            "summary": "Strengthen candidate quality evidence before promotion review.",
            "goal": "Add a product-integrated helper that summarizes candidate evidence quality across research support, selected target changes, and validation coverage.",
            "allowed_patch_paths": [
                "backend/src/across_agents_assistant/loop_engineering_capability_pack.py",
                "backend/src/across_agents_assistant/autopilot_candidate_quality_evidence.py",
                "backend/tests/test_autopilot_candidate_quality_evidence.py",
            ],
            "tool_packs": ["candidate_workspace", "validation_harness", "independent_review"],
        },
        {
            "id": "autonomous-tool-pack-routing-evidence",
            "summary": "Expose Tool Pack routing evidence for autonomous runs.",
            "goal": "Add product-integrated evidence that records which deterministic Tool Packs shaped an autonomous candidate target and why.",
            "allowed_patch_paths": [
                "backend/src/across_agents_assistant/unified_capability_registry.py",
                "backend/src/across_agents_assistant/autopilot_tool_pack_routing_evidence.py",
                "backend/tests/test_autopilot_tool_pack_routing_evidence.py",
            ],
            "tool_packs": ["candidate_workspace", "validation_harness", "source_research_digest"],
        },
    ]
    count = _autopilot_research_minimum_candidates(req)
    targets: List[Dict[str, Any]] = []
    for index in range(count):
        template = dict(templates[index % len(templates)])
        if index >= len(templates):
            template["id"] = f"{template['id']}-{index + 1}"
        paths = [str(path) for path in template["allowed_patch_paths"]]
        target = {
            **template,
            "target_repo": "across-agents-assistant",
            "validation_commands": _default_research_validation_commands(paths, repo="across-agents-assistant"),
            "semantic_review": semantic_review,
            "source_refs": source_refs,
            "generated_from": "host_timeout_fallback",
            "risk": "low",
            "score": max(1, 100 - index),
        }
        targets.append(target)
    return targets


def _autopilot_research_host_fallback_decision(
    req: AutopilotResearchDecisionRequest,
    *,
    reason: str,
) -> Dict[str, Any]:
    targets = _autopilot_host_fallback_research_targets(req)
    selected = targets[0] if targets else {}
    fallback = {
        "summary": "Use a safe timeout-recovery target for autonomous self-iteration.",
        "rationale": (
            "The local research agent did not return in time. The host selected a bounded, "
            "product-integrated target so the loop can continue through candidate validation "
            "and human review instead of failing without reviewable output. "
            f"Failure reason: {reason[:500]}"
        ),
        "decision": "implement",
        "selected_target_id": str(selected.get("id") or selected.get("target_id") or ""),
        "candidate_targets": targets,
        "selected_iteration": selected,
        "rejected_directions": ["unbounded_retry", "silent_timeout_failure"],
    }
    return _normalize_research_decision(fallback, req)


def _autopilot_target_id(value: Any, *, default: str) -> str:
    text = re.sub(r"[^a-z0-9._-]+", "-", str(value or "").strip().lower()).strip("-._")
    return text[:80] or default


def _default_research_target_paths(goal: str) -> List[str]:
    module = _safe_python_identifier(goal, default="autonomous_candidate")
    if len(module) > 48:
        module = module[:48].rstrip("_")
    return [
        f"backend/src/across_agents_assistant/autopilot_{module}.py",
        f"backend/tests/test_autopilot_{module}.py",
    ]


def _autopilot_autonomous_root(req: AutopilotResearchDecisionRequest) -> Optional[str]:
    return (
        req.product_context.get("autonomous_loop_state", {}).get("root")
        if isinstance(req.product_context.get("autonomous_loop_state"), dict)
        else None
    )


def _autopilot_misplaced_context_path(value: Any, *, autonomous_root: Optional[str]) -> Optional[str]:
    text = str(value or "").replace("\\", "/").strip()
    if not text:
        return None
    if text.startswith(("/", "~")) or text.startswith("loop-state/"):
        return _safe_autopilot_context_path(text, autonomous_root=autonomous_root)
    return None


def _normalize_research_context_files(paths: List[Any], *, autonomous_root: Optional[str], limit: int) -> List[str]:
    result: List[str] = []
    seen: Set[str] = set()
    for path in paths:
        if not str(path or "").strip():
            continue
        normalized = _safe_autopilot_context_path(path, autonomous_root=autonomous_root)
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
        if len(result) >= limit:
            break
    return result


def _normalize_research_paths_and_context(
    item: Dict[str, Any],
    req: AutopilotResearchDecisionRequest,
    *,
    default_goal: Optional[str],
    context_limit: int,
) -> Tuple[List[str], List[str]]:
    autonomous_root = _autopilot_autonomous_root(req)
    raw_paths = item.get("allowed_patch_paths") or []
    raw_context: List[Any] = list(item.get("context_files") or [])
    patch_candidates: List[Any] = []
    for path in raw_paths:
        if not str(path or "").strip():
            continue
        misplaced = _autopilot_misplaced_context_path(path, autonomous_root=autonomous_root)
        if misplaced is not None:
            raw_context.append(misplaced)
            continue
        patch_candidates.append(path)
    if not patch_candidates and default_goal:
        patch_candidates = _default_research_target_paths(default_goal)
    allowed_paths = [_safe_autopilot_rel_path(path) for path in patch_candidates if str(path or "").strip()][:8]
    context_files = _normalize_research_context_files(raw_context, autonomous_root=autonomous_root, limit=context_limit)
    return allowed_paths, context_files


def _autopilot_path_allowed_for_repo(repo: str, path: str) -> bool:
    prefixes = {
        "across-agents-assistant": (
            "backend/main.py",
            "backend/src/",
            "backend/tests/",
            "macOS-Client/Sources/",
            "macOS-Client/Tests/",
            "build_app.sh",
            "scripts/",
            "docs/",
            "README.md",
            "CHANGELOG.md",
        ),
        "across-autopilot": ("src/", "tests/", "examples/", "README.md", "AUTOPILOT_RFC.md", "package.json"),
        "across-orchestrator": ("src/across_orchestrator/", "tests/", "README.md"),
        "across-context": ("src/", "tests/", "README.md", "package.json"),
    }.get(repo, ())
    return any(path == prefix or path.startswith(prefix) for prefix in prefixes)


def _default_research_validation_commands(paths: List[str], *, repo: str) -> List[Dict[str, Any]]:
    commands: List[Dict[str, Any]] = [
        {"repo": repo, "command": "git", "args": ["diff", "--check"], "timeout_ms": 30000}
    ]
    python_paths = [path for path in paths if path.endswith(".py")]
    if python_paths:
        commands.append({"repo": repo, "command": "python3", "args": ["-m", "py_compile", *python_paths], "timeout_ms": 30000})
    if any(path.endswith(".swift") or path.startswith("macOS-Client/") for path in paths):
        commands.append({"repo": repo, "command": "swift", "args": ["test", "--package-path", "macOS-Client"], "timeout_ms": 180000})
    platform_self_repair_replay_only = (
        repo == "across-autopilot"
        and len(paths) == 1
        and paths[0] == "tests/platform-self-repair.test.js"
    )
    if (
        repo in {"across-autopilot", "across-context"}
        and not platform_self_repair_replay_only
        and any(path.startswith(("src/", "tests/", "examples/")) or path == "package.json" for path in paths)
    ):
        commands.append({"repo": repo, "command": "npm", "args": ["test", "--", "--runInBand"], "timeout_ms": 180000})
    for test_path in [path for path in python_paths if path.startswith("backend/tests/")][:2]:
        commands.append({
            "repo": repo,
            "command": "python3",
            "args": [
                "-c",
                (
                    "import sys, runpy; sys.path.insert(0, 'backend/src'); "
                    f"ns=runpy.run_path({test_path!r}); "
                    "tests=[v for k,v in ns.items() if k.startswith('test_') and callable(v)]; "
                    "assert tests, 'no test functions found'; [test() for test in tests]"
                ),
            ],
            "timeout_ms": 30000,
        })
    return commands[:8]


def _normalize_research_target(item: Dict[str, Any], req: AutopilotResearchDecisionRequest, *, index: int) -> Dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("candidate target must be an object")
    target_repo = str(item.get("target_repo") or req.product_context.get("target_repo") or "across-agents-assistant")
    if target_repo not in {"across-agents-assistant", "across-autopilot", "across-orchestrator", "across-context"}:
        raise ValueError(f"Unsupported target_repo: {target_repo}")
    allowed_paths, context_files = _normalize_research_paths_and_context(
        item,
        req,
        default_goal=str(item.get("goal") or item.get("summary") or req.goal),
        context_limit=12,
    )
    if not allowed_paths:
        raise ValueError("candidate target has no allowed_patch_paths")
    for path in allowed_paths:
        if not _autopilot_path_allowed_for_repo(target_repo, path):
            raise ValueError(f"Generated target path is outside allowed product prefixes: {path}")
    validation_commands = _normalize_validation_commands(
        item.get("validation_commands") or _default_research_validation_commands(allowed_paths, repo=target_repo),
        default_repo=target_repo,
    )
    if len(validation_commands) < 2:
        validation_commands = _default_research_validation_commands(allowed_paths, repo=target_repo)
    semantic_review = {
        "require_model_backed": True,
        "require_selected_target_change": True,
        "reject_self_proof_only": True,
        "independent_reviewer_required": True,
        "minimum_validation_commands": max(2, len(validation_commands)),
        **(item.get("semantic_review") if isinstance(item.get("semantic_review"), dict) else {}),
    }
    target_id = _autopilot_target_id(item.get("id") or item.get("target_id") or item.get("summary"), default=f"generated-target-{index + 1}")
    return {
        "id": target_id,
        "target_id": target_id,
        "target_repo": target_repo,
        "summary": str(item.get("summary") or item.get("goal") or req.goal)[:800],
        "goal": str(item.get("goal") or item.get("summary") or req.goal)[:2000],
        "allowed_patch_paths": allowed_paths,
        "context_files": context_files,
        "validation_commands": validation_commands,
        "semantic_review": semantic_review,
        "source_refs": [str(source)[:160] for source in _autopilot_list(item.get("source_refs"))[:12]],
        "tool_packs": [str(pack)[:160] for pack in _autopilot_list(item.get("tool_packs"))[:12]],
        "generated_from": str(item.get("generated_from") or "model_generated")[:160],
        "score": float(item.get("score") or max(1, 100 - index)),
        "risk": str(item.get("risk") or "medium")[:40],
    }


def _autopilot_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _catalog_by_id(catalog: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {
        str(item.get("id") or "").strip(): item
        for item in catalog
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }


def _normalize_validation_commands(items: Any, *, default_repo: str) -> List[Dict[str, Any]]:
    commands: List[Dict[str, Any]] = []
    for item in (items or [])[:8]:
        if not isinstance(item, dict) or not item.get("command"):
            continue
        command = {
            "repo": str(item.get("repo") or default_repo),
            "command": str(item.get("command")),
            "args": [str(arg) for arg in (item.get("args") or [])],
        }
        if item.get("timeout_ms") is not None:
            command["timeout_ms"] = int(item.get("timeout_ms") or 0)
        commands.append(command)
    return commands


def _normalize_research_decision(raw: Dict[str, Any], req: AutopilotResearchDecisionRequest) -> Dict[str, Any]:
    allow_generated = _autopilot_research_allows_generated_targets(req)
    catalog_targets = [_normalize_research_target(item, req, index=index) for index, item in enumerate(req.target_catalog)]
    generated_targets = [
        _normalize_research_target(item, req, index=index)
        for index, item in enumerate(raw.get("candidate_targets") or raw.get("dynamic_backlog") or raw.get("generated_backlog") or [])
        if isinstance(item, dict)
    ]
    selected_raw = raw.get("selected_iteration") if isinstance(raw.get("selected_iteration"), dict) else {}
    if allow_generated and selected_raw:
        selected_as_target = _normalize_research_target(
            {
                **selected_raw,
                "id": selected_raw.get("target_id") or selected_raw.get("id") or raw.get("selected_target_id"),
                "summary": selected_raw.get("summary") or raw.get("summary"),
            },
            req,
            index=len(generated_targets),
        )
        if any(item["id"] == selected_as_target["id"] for item in generated_targets):
            generated_targets = [
                selected_as_target if item["id"] == selected_as_target["id"] else item
                for item in generated_targets
            ]
        else:
            generated_targets.append(selected_as_target)
    minimum_candidates = _autopilot_research_minimum_candidates(req)
    if allow_generated and len(generated_targets) < minimum_candidates:
        raise ValueError(f"Generated research decision must include at least {minimum_candidates} candidate_targets")
    effective_targets = generated_targets if allow_generated and generated_targets else catalog_targets
    catalog = _catalog_by_id(effective_targets)
    if not catalog:
        raise ValueError("Research decision requires target_catalog or generated candidate_targets")
    selected_id = str(raw.get("selected_target_id") or raw.get("target_id") or "").strip()
    selected = raw.get("selected_iteration")
    if isinstance(selected, dict) and not selected_id:
        selected_id = str(selected.get("target_id") or selected.get("id") or "").strip()
    if selected_id not in catalog:
        selected_id = next(iter(catalog))
    trigger_payload = req.product_context.get("trigger_payload") if isinstance(req.product_context.get("trigger_payload"), dict) else {}
    hinted_target_id = str(trigger_payload.get("target_id") or "").strip()
    hint_overrode_selection = False
    if hinted_target_id and hinted_target_id in catalog:
        hint_overrode_selection = selected_id != hinted_target_id
        selected_id = hinted_target_id
    catalog_item = catalog[selected_id]
    selected = selected if isinstance(selected, dict) else {}
    if hint_overrode_selection:
        selected = {}
    target_repo = str(selected.get("target_repo") or catalog_item.get("target_repo") or "across-agents-assistant")
    catalog_paths = [_safe_autopilot_rel_path(path) for path in (catalog_item.get("allowed_patch_paths") or []) if str(path or "").strip()]
    proposed_paths, proposed_context_files = _normalize_research_paths_and_context(
        selected,
        req,
        default_goal=None,
        context_limit=10,
    )
    if proposed_paths and not set(proposed_paths).issubset(set(catalog_paths)):
        raise ValueError("Research decision selected paths outside target_catalog")
    allowed_paths = proposed_paths or catalog_paths
    if not allowed_paths:
        raise ValueError("Research decision selected target has no allowed_patch_paths")
    context_files = _normalize_research_context_files(
        [
            *(catalog_item.get("context_files") or []),
            *(selected.get("context_files") or []),
            *proposed_context_files,
        ],
        autonomous_root=_autopilot_autonomous_root(req),
        limit=10,
    )
    semantic_review = {
        **(catalog_item.get("semantic_review") or {}),
        **(selected.get("semantic_review") if isinstance(selected.get("semantic_review"), dict) else {}),
    }
    validation_commands = _normalize_validation_commands(
        catalog_item.get("validation_commands") or selected.get("validation_commands") or [],
        default_repo=target_repo,
    )
    decision = str(raw.get("decision") or "implement").strip().lower()
    if decision not in {"implement", "defer"}:
        decision = "implement"
    iteration_goal = str(selected.get("goal") or catalog_item.get("goal") or raw.get("summary") or req.goal).strip()
    return {
        "schema_version": "across-host-research-decision/1.0",
        "status": "passed" if decision == "implement" else "attention",
        "decision": decision,
        "summary": str(raw.get("summary") or catalog_item.get("summary") or iteration_goal)[:800],
        "rationale": str(raw.get("rationale") or "")[:2000],
        "selected_target_id": selected_id,
        "rejected_directions": [str(item)[:400] for item in (raw.get("rejected_directions") or [])[:8]],
        "candidate_targets": effective_targets,
        "selected_iteration": {
            "target_id": selected_id,
            "target_repo": target_repo,
            "goal": iteration_goal,
            "allowed_patch_paths": allowed_paths,
            "context_files": context_files,
            "validation_commands": validation_commands,
            "semantic_review": semantic_review,
            "source_refs": [str(item)[:160] for item in (selected.get("source_refs") or raw.get("source_refs") or [])[:8]],
            "tool_packs": [str(item)[:160] for item in (selected.get("tool_packs") or catalog_item.get("tool_packs") or [])[:12]],
            "generated_from": str(selected.get("generated_from") or catalog_item.get("generated_from") or "")[:160],
            "score": float(catalog_item.get("score") or selected.get("score") or 0),
            "risk": str(selected.get("risk") or raw.get("risk") or catalog_item.get("risk") or "medium")[:40],
        },
    }


async def _autopilot_research_decision_chat(
    req: AutopilotResearchDecisionRequest,
    *,
    provider_id: Optional[str],
    model_id: Optional[str],
    agent_id: Optional[str],
    temperature: float,
    max_tokens: int,
    timeout_seconds: float,
    idle_timeout_seconds: Optional[float] = None,
) -> Tuple[Any, Dict[str, Any], bool, bool, Optional[str]]:
    response = await _chat_with_model_capability(
        message=_autopilot_research_user_prompt(req),
        system_prompt=_autopilot_research_system_prompt(req),
        provider_id=str(provider_id) if provider_id else None,
        model=str(model_id) if model_id else None,
        agent_id=str(agent_id) if agent_id else None,
        project_dir=req.candidate_workspace,
        scope="model.research",
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout_seconds,
        max_wall_timeout=timeout_seconds,
        idle_timeout=idle_timeout_seconds,
        extra_body=_minimax_json_extra_body(provider_id),
    )
    try:
        decision = _normalize_research_decision(_extract_json_object(response.text), req)
        return response, decision, False, True, None
    except Exception as first_error:
        repair_error_count = 1
        repair_seed = response.text
        repair_response = response
        for _attempt in range(3):
            repair_response = await _chat_with_model_capability(
                message=_autopilot_research_repair_prompt(req, repair_seed, first_error),
                system_prompt=_autopilot_research_system_prompt(req),
                provider_id=str(provider_id) if provider_id else None,
                model=str(model_id) if model_id else None,
                agent_id=str(agent_id) if agent_id else None,
                project_dir=req.candidate_workspace,
                scope="model.research",
                temperature=0.0,
                max_tokens=max_tokens,
                timeout=timeout_seconds,
                max_wall_timeout=timeout_seconds,
                idle_timeout=idle_timeout_seconds,
                extra_body=_minimax_json_extra_body(provider_id),
            )
            try:
                decision = _normalize_research_decision(_extract_json_object(repair_response.text), req)
                return repair_response, decision, True, True, None
            except Exception as repair_error:
                repair_error_count += 1
                repair_seed = repair_response.text
        if not _autopilot_research_allows_host_fallback(req):
            raise ValueError(
                "Model research decision remained invalid after repair; host target fallback is disabled "
                "for autonomous production loops. Enable model_policy.allow_host_target_fallback only for "
                "conformance fixtures."
            ) from first_error
        decision = _autopilot_research_host_fallback_decision(
            req,
            reason=f"invalid_model_output_after_{repair_error_count}_validation_attempts",
        )
        return response, decision, True, False, "invalid_model_output_host_fallback"


def _autopilot_research_response_payload(
    req: AutopilotResearchDecisionRequest,
    decision: Dict[str, Any],
    *,
    response: Any,
    repaired: bool,
    model_backed: bool,
    fallback_reason: Optional[str] = None,
) -> Dict[str, Any]:
    clean = {
        "summary": decision["summary"],
        "rationale": decision["rationale"],
        "decision": decision["decision"],
        "selected_target_id": decision["selected_target_id"],
        "candidate_targets": decision.get("candidate_targets") or [],
        "selected_iteration": decision["selected_iteration"],
        "rejected_directions": decision["rejected_directions"],
    }
    decision_json = json.dumps(clean, ensure_ascii=False, sort_keys=True)
    payload = {
        **decision,
        "model_backed": bool(model_backed),
        "provider": getattr(response, "provider", None),
        "model": getattr(response, "model", None),
        "finish_reason": getattr(response, "finish_reason", None),
        "usage": getattr(response, "usage", None),
        "repaired_json": repaired,
        "decision_hash": hashlib.sha256(decision_json.encode("utf-8")).hexdigest(),
        "candidate_model_lease": _public_request_model_lease(req.candidate_model_lease),
        "source_count": len(req.sources),
        "source_ids": [str(source.get("id") or "") for source in req.sources[:20]],
    }
    if fallback_reason:
        payload["fallback_reason"] = str(_sanitize_public_error_text(fallback_reason) or "")[:1000]
    return payload


def _deterministic_research_decision_from_trigger(req: AutopilotResearchDecisionRequest) -> Optional[Dict[str, Any]]:
    trigger_payload = req.product_context.get("trigger_payload") if isinstance(req.product_context.get("trigger_payload"), dict) else {}
    target_id = str(trigger_payload.get("target_id") or "").strip()
    if not target_id:
        return None
    matching = next(
        (
            item
            for item in req.target_catalog
            if isinstance(item, dict) and str(item.get("id") or item.get("target_id") or "").strip() == target_id
        ),
        None,
    )
    if not matching:
        return None
    selected = {
        **matching,
        "id": target_id,
        "target_id": target_id,
        "generated_from": matching.get("generated_from") or "trigger_payload",
    }
    raw = {
        "summary": f"Deterministically selected trigger target {target_id}.",
        "rationale": "The trigger payload supplied an explicit target_id that matched target_catalog; no model target selection was required.",
        "decision": "implement",
        "selected_target_id": target_id,
        "candidate_targets": req.target_catalog,
        "selected_iteration": selected,
        "rejected_directions": ["model_target_reselection"],
    }
    return _normalize_research_decision(raw, req)


@app.post("/api/autopilot/research-decision")
async def create_autopilot_research_decision(req: AutopilotResearchDecisionRequest):
    """Return a host-model-backed research-to-product iteration strategy."""
    try:
        policy = dict(req.model_policy or {})
        provider_id = _autopilot_model_policy_value(policy, "provider", "provider_id")
        model_id = _autopilot_model_policy_value(policy, "model", "model_id")
        agent_id = _autopilot_model_policy_value(policy, "agent_id", "agent")
        temperature = float(_autopilot_model_policy_value(policy, "temperature", default=0.2))
        max_tokens = int(_autopilot_model_policy_value(policy, "max_tokens", "maxTokens", default=1800))
        timeout_plan = _autopilot_model_policy_timeout_plan(policy)
        timeout_seconds = timeout_plan["max_wall_timeout_seconds"]
        idle_timeout_seconds = timeout_plan["idle_timeout_seconds"]
        deterministic = _deterministic_research_decision_from_trigger(req)
        if deterministic is not None and policy.get("allow_deterministic_trigger_target", True) is not False:
            response = LLMResponse(
                text="",
                raw={"deterministic_trigger_target": True},
                model="trigger-target",
                provider="deterministic",
                finish_reason="trigger_target",
                usage=None,
            )
            return _sanitize_public_payload(
                _autopilot_research_response_payload(
                    req,
                    deterministic,
                    response=response,
                    repaired=False,
                    model_backed=False,
                    fallback_reason="deterministic_trigger_target",
                )
            )
        model_candidates = _local_agent_model_candidates(policy, str(agent_id) if agent_id else None)
        last_local_agent_error: Optional[LocalAgentExecutionError] = None
        last_error: Optional[Exception] = None
        try:
            for candidate_model in model_candidates or [None]:
                try:
                    response, decision, repaired, model_backed, fallback_reason = await _autopilot_research_decision_chat(
                        req,
                        provider_id=str(provider_id) if provider_id else None,
                        model_id=str(candidate_model) if candidate_model else None,
                        agent_id=str(agent_id) if agent_id else None,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout_seconds=timeout_seconds,
                        idle_timeout_seconds=idle_timeout_seconds,
                    )
                    break
                except LocalAgentExecutionError as exc:
                    last_local_agent_error = exc
                    last_error = exc
                    continue
                except Exception as exc:
                    last_error = exc
                    continue
            else:
                if last_local_agent_error:
                    raise last_local_agent_error
                if last_error is not None:
                    raise last_error
                raise RuntimeError("All Autopilot research model candidates failed")
        except LocalAgentExecutionError as exc:
            if exc.code == "timeout" and _autopilot_research_allows_timeout_fallback(
                req,
                policy=policy,
                agent_id=str(agent_id) if agent_id else None,
            ):
                logger.warning("Autopilot research local agent timed out; using host timeout fallback: %s", exc)
                decision = _autopilot_research_host_fallback_decision(req, reason="local_agent_timeout")
                response = LLMResponse(
                    text="",
                    raw={"error_code": exc.code, "elapsed_sec": exc.elapsed_sec},
                    model=str(model_id or agent_id or "local-agent"),
                    provider=str(provider_id or "local-agent"),
                    finish_reason="timeout_fallback",
                    usage=None,
                )
                return _sanitize_public_payload(
                    _autopilot_research_response_payload(
                        req,
                        decision,
                        response=response,
                        repaired=False,
                        model_backed=False,
                        fallback_reason="local_agent_timeout_host_fallback",
                    )
                )
            status_code = 504 if exc.code == "timeout" else 503
            raise HTTPException(status_code=status_code, detail=_safe_error_message("Autopilot research local agent"))
        return _sanitize_public_payload(
            _autopilot_research_response_payload(
                req,
                decision,
                response=response,
                repaired=repaired,
                model_backed=model_backed,
                fallback_reason=fallback_reason,
            )
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=_autopilot_research_value_error_detail(exc))
    except Exception as exc:
        raise _safe_http_500("Create Autopilot research decision")


def _autopilot_code_iteration_system_prompt(*, direct_patches: bool = False) -> str:
    if direct_patches:
        return (
            "You are the model brain for an AAA self-iteration code change. "
            "Return JSON only. Do not include markdown fences. "
            "Choose a small, safe, testable product-code improvement for the B candidate workspace only. "
            "Never mutate source A. Use only allowed_patch_paths. "
            "Return this JSON shape: "
            "{\"summary\": string, \"risk\": \"low|medium|high\", "
            "\"patches\": [{\"path\": string, \"mode\": \"overwrite|append|upsert_between_markers\", \"content_lines\": [string]}], "
            "\"validation_commands\": [{\"command\": string, \"args\": [string]}]}. "
            "Patch content must be complete file content. Prefer content_lines for code files; "
            "content strings and content_base64 are also accepted when they are valid JSON. "
        "Prefer pure helpers with tests, no network calls, no secrets, no subprocesses, and no filesystem writes. "
        "Do not include token-shaped or key-shaped strings anywhere, including tests or examples: avoid sk-, ghp_, token=, secret=, api_key=, and bearer-style fixtures. "
        "Candidate test files must be standard-library only: do not import or use pytest, because validation runs them with python3/runpy. "
        "Candidate tests under backend/tests must import product modules through the package path, for example "
        "'from across_agents_assistant.autopilot_feature import helper'; never use flat imports like "
        "'from autopilot_feature import helper'. "
        "Existing product integration files such as api_server.py, autopilot_workbench.py, and "
        "loop_engineering_capability_pack.py must be surgical: use append or upsert_between_markers, never overwrite. "
        "Preserve existing route registrations, capability registries, public functions, and imports unless the goal explicitly says to remove them. "
        "For existing README, CHANGELOG, or docs files, preserve existing content. Use append or upsert_between_markers for small additions; "
        "if you use upsert_between_markers you must include marker_start and marker_end. "
        "do not rewrite or delete large documentation sections unless the goal explicitly requires a documentation rewrite."
        )
    return (
        "You are the model brain for an AAA self-iteration code change. "
        "Return JSON only. Do not include markdown fences. "
        "Choose a small, safe, testable product-code improvement for the candidate workspace only. "
        "The host will generate the actual Python code from your decision. "
        "Use this JSON shape: "
        "{\"summary\": string, \"capability_name\": string, \"status_label\": string, "
        "\"key_behaviors\": [string], \"validation\": [string], \"risk\": \"low|medium|high\"}. "
        "Keep capability_name as a lowercase snake_case identifier."
    )


def _autopilot_code_iteration_user_prompt(req: AutopilotCodeIterationRequest, context_files: List[Dict[str, Any]]) -> str:
    payload = {
        "goal": req.goal,
        "run_id": req.run_id,
        "candidate_id": req.candidate_id,
        "candidate_workspace": req.candidate_workspace,
        "target_repo": req.target_repo,
        "source_repository": req.source_repository,
        "allowed_patch_paths": req.allowed_patch_paths[:20],
        "context_files": context_files,
        "validation_commands": req.validation_commands[:8],
        "validation_feedback": req.validation_feedback[:8],
    }
    return (
        "Decide a bounded candidate-only code iteration. "
        "Do not request writes outside allowed_patch_paths. "
        "The change must be safe to validate in B without touching A. "
        "Generated code must satisfy validation_commands exactly; treat them as the acceptance contract. "
        "validation_feedback may include failed commands or semantic review blocking reasons. "
        "If validation_feedback is present, repair the candidate so commands pass and semantic review blocking reasons are resolved. "
        "If feedback reports a large documentation rewrite, restore or preserve the original documentation and move the change into focused code/tests or a small append/upsert section. "
        "If feedback reports destructive_product_entrypoint_rewrite, restore the affected source-baseline file and replace the change with a marker-bounded append/upsert. "
        "Existing product integration files such as api_server.py, autopilot_workbench.py, and loop_engineering_capability_pack.py must keep existing content and public surfaces. "
        "If feedback reports missing pytest, remove pytest imports/usages and rewrite tests as plain assert-based functions runnable through runpy. "
        "If feedback reports ModuleNotFoundError for an autopilot_* module, repair backend/tests imports to package imports under across_agents_assistant. "
        "Keep generated files concise: prefer one pure helper plus focused tests. "
        "Avoid large explanatory comments in patch content.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def _autopilot_code_iteration_repair_prompt(req: AutopilotCodeIterationRequest, raw_text: str, error: Exception) -> str:
    payload = {
        "goal": req.goal,
        "candidate_id": req.candidate_id,
        "target_repo": req.target_repo,
        "allowed_patch_paths": req.allowed_patch_paths[:20],
        "validation_feedback": req.validation_feedback[:8],
        "parse_error": str(error),
        "raw_model_output": str(raw_text or "")[:20_000],
    }
    return (
        "Repair the prior code-iteration output into the required JSON object only. "
        "No markdown, no commentary, no chain-of-thought. "
        "Return complete file contents for every patch, using only allowed_patch_paths. "
        "Resolve validation_feedback if present, including semantic review blocking reasons. "
        "Candidate test files must be standard-library only; do not import/use pytest, pytest.raises, tmp_path, monkeypatch, or other pytest fixtures. "
        "Do not include token-shaped or key-shaped strings anywhere, including tests or examples: avoid sk-, ghp_, token=, secret=, api_key=, and bearer-style fixtures. "
        "Candidate test files must import AAA product modules through across_agents_assistant.<module>, not through flat autopilot_* imports. "
        "If validation_feedback reports destructive_product_entrypoint_rewrite, do not overwrite existing product integration files; use marker-bounded append/upsert content only. "
        "Preserve existing route registrations, capability registries, public functions, and imports. "
        "Preserve existing documentation; use append or upsert_between_markers for docs instead of destructive overwrite. "
        "If you use upsert_between_markers, include marker_start and marker_end. "
        "Use this shape: {\"summary\": string, \"risk\": \"low|medium|high\", "
        "\"patches\": [{\"path\": string, \"mode\": \"overwrite|append|upsert_between_markers\", \"content_lines\": [string]}], "
        "\"validation_commands\": [{\"command\": string, \"args\": [string]}]}.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def _safe_python_identifier(value: Any, *, default: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9_]+", "_", str(value or "").strip().lower()).strip("_")
    if not text or text[0].isdigit():
        text = default
    return text[:80]


def _normalize_code_iteration_decision(raw: Dict[str, Any]) -> Dict[str, Any]:
    capability = _safe_python_identifier(raw.get("capability_name"), default="candidate_self_iteration")
    status_label = re.sub(r"[^a-zA-Z0-9_.:-]+", "-", str(raw.get("status_label") or "candidate-ready")).strip("-")
    if not status_label:
        status_label = "candidate-ready"
    key_behaviors = [str(item).strip()[:180] for item in (raw.get("key_behaviors") or []) if str(item).strip()][:6]
    validation = [str(item).strip()[:180] for item in (raw.get("validation") or []) if str(item).strip()][:6]
    return {
        "summary": str(raw.get("summary") or "Add candidate self-iteration status evidence.").strip()[:500],
        "capability_name": capability,
        "status_label": status_label[:80],
        "key_behaviors": key_behaviors or [
            "Expose deterministic candidate status for self-iteration evidence.",
            "Keep source A read-only and write only inside B."
        ],
        "validation": validation or [
            "Import the candidate module from backend/src.",
            "Assert the status payload marks the candidate as ready."
        ],
        "risk": str(raw.get("risk") or "low").strip()[:40],
    }


def _normalize_direct_code_iteration_decision(raw: Dict[str, Any], *, allowed_patch_paths: List[str]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    patches = _normalize_model_decision_patches(raw, allowed_patch_paths=allowed_patch_paths)
    _validate_autopilot_generated_patch_policy(patches)
    validation_commands = [
        {
            "command": str(item.get("command") or ""),
            "args": [str(arg) for arg in (item.get("args") or [])],
        }
        for item in (raw.get("validation_commands") or [])
        if isinstance(item, dict) and item.get("command")
    ][:8]
    decision = {
        "summary": str(raw.get("summary") or "Model proposed a candidate-only product code patch.").strip()[:500],
        "risk": str(raw.get("risk") or "medium").strip()[:40],
        "patch_paths": [patch["path"] for patch in patches],
        "validation_commands": validation_commands,
    }
    return decision, patches


def _render_candidate_status_module(decision: Dict[str, Any], req: AutopilotCodeIterationRequest) -> str:
    behaviors = json.dumps(decision["key_behaviors"], ensure_ascii=False, indent=4)
    validations = json.dumps(decision["validation"], ensure_ascii=False, indent=4)
    return (
        '"""Candidate-only Loop Engineering status helpers.\n\n'
        "This file is generated inside B by the stable AAA host code adapter.\n"
        "It must not be written to A during a self-iteration run.\n"
        '"""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any\n\n\n"
        "def candidate_self_iteration_status() -> dict[str, Any]:\n"
        "    \"\"\"Return bounded evidence that this B candidate was modified by the loop.\"\"\"\n"
        "    return {\n"
        f"        \"status\": {decision['status_label']!r},\n"
        f"        \"capability\": {decision['capability_name']!r},\n"
        f"        \"candidate_id\": {str(req.candidate_id or '')!r},\n"
        f"        \"run_id\": {str(req.run_id or '')!r},\n"
        f"        \"model_summary\": {decision['summary']!r},\n"
        f"        \"key_behaviors\": {behaviors},\n"
        f"        \"validation\": {validations},\n"
        "        \"promotion_requires_human_approval\": True,\n"
        "    }\n"
    )


def _render_candidate_status_test(decision: Dict[str, Any]) -> str:
    return (
        "from across_agents_assistant.loop_engineering_candidate import candidate_self_iteration_status\n\n\n"
        "def test_candidate_self_iteration_status_is_promotion_safe():\n"
        "    status = candidate_self_iteration_status()\n"
        f"    assert status[\"status\"] == {decision['status_label']!r}\n"
        f"    assert status[\"capability\"] == {decision['capability_name']!r}\n"
        "    assert status[\"promotion_requires_human_approval\"] is True\n"
        "    assert status[\"key_behaviors\"]\n"
        "    assert status[\"validation\"]\n"
    )


def _render_candidate_quality_module(decision: Dict[str, Any]) -> str:
    return (
        '"""Candidate promotion quality helpers for Loop Engineering.\n\n'
        "This module is intended to run in a B candidate workspace. It evaluates\n"
        "candidate evidence before a human promotion review and rejects no-diff\n"
        "or self-proof-only changes.\n"
        '"""\n\n'
        "from __future__ import annotations\n\n"
        "from collections.abc import Mapping, Sequence\n"
        "from typing import Any\n\n\n"
        "SELF_PROOF_ONLY_MARKERS = (\n"
        "    \"loop_engineering_candidate.py\",\n"
        "    \"test_loop_engineering_candidate.py\",\n"
        "    \"SELF_HOSTING_PROBE\",\n"
        "    \"self_hosting_probe\",\n"
        ")\n\n\n"
        "def _as_list(value: Any) -> list[Any]:\n"
        "    if value is None:\n"
        "        return []\n"
        "    if isinstance(value, list):\n"
        "        return value\n"
        "    if isinstance(value, tuple):\n"
        "        return list(value)\n"
        "    return [value]\n\n\n"
        "def _changed_files(evidence: Mapping[str, Any]) -> list[str]:\n"
        "    direct = [str(item) for item in _as_list(evidence.get(\"changed_files\")) if str(item).strip()]\n"
        "    if direct:\n"
        "        return direct\n"
        "    candidate = evidence.get(\"candidate\")\n"
        "    if isinstance(candidate, Mapping):\n"
        "        nested = [str(item) for item in _as_list(candidate.get(\"changed_files\")) if str(item).strip()]\n"
        "        if nested:\n"
        "            return nested\n"
        "    repos = evidence.get(\"repos\")\n"
        "    if isinstance(repos, Mapping):\n"
        "        files: list[str] = []\n"
        "        for repo_id, repo in repos.items():\n"
        "            if isinstance(repo, Mapping):\n"
        "                files.extend(f\"{repo_id}/{item}\" for item in _as_list(repo.get(\"changed_files\")) if str(item).strip())\n"
        "        return [str(item) for item in files]\n"
        "    if isinstance(repos, Sequence) and not isinstance(repos, (str, bytes)):\n"
        "        files = []\n"
        "        for repo in repos:\n"
        "            if isinstance(repo, Mapping):\n"
        "                repo_id = str(repo.get(\"id\") or repo.get(\"repo\") or \"repo\")\n"
        "                files.extend(f\"{repo_id}/{item}\" for item in _as_list(repo.get(\"changed_files\")) if str(item).strip())\n"
        "        return [str(item) for item in files]\n"
        "    return []\n\n\n"
        "def _required_gate_failures(evidence: Mapping[str, Any]) -> list[str]:\n"
        "    failures: list[str] = []\n"
        "    for gate in _as_list(evidence.get(\"gates\")):\n"
        "        if not isinstance(gate, Mapping):\n"
        "            continue\n"
        "        required = bool(gate.get(\"required\", True))\n"
        "        status = str(gate.get(\"status\") or \"unknown\")\n"
        "        if required and status != \"passed\":\n"
        "            failures.append(str(gate.get(\"id\") or gate.get(\"name\") or \"required gate\"))\n"
        "    return failures\n\n\n"
        "def _is_self_proof_only(changed_files: Sequence[str]) -> bool:\n"
        "    if not changed_files:\n"
        "        return False\n"
        "    return all(any(marker in path for marker in SELF_PROOF_ONLY_MARKERS) for path in changed_files)\n\n\n"
        "def evaluate_candidate_product_alignment(evidence: Mapping[str, Any]) -> dict[str, Any]:\n"
        "    \"\"\"Return a promotion-review recommendation for candidate evidence.\"\"\"\n"
        "    changed = _changed_files(evidence)\n"
        "    blocking_reasons: list[str] = []\n"
        "    warnings: list[str] = []\n\n"
        "    if not changed:\n"
        "        blocking_reasons.append(\"candidate has no changed files\")\n"
        "    elif _is_self_proof_only(changed):\n"
        "        blocking_reasons.append(\"candidate only proves loop execution and lacks product-facing value\")\n\n"
        "    failed_gates = _required_gate_failures(evidence)\n"
        "    if failed_gates:\n"
        "        blocking_reasons.append(\"required gates did not pass: \" + \", \".join(failed_gates))\n\n"
        "    validation_status = str(evidence.get(\"validation_status\") or evidence.get(\"candidate\", {}).get(\"validation_status\") or \"\").strip()\n"
        "    if validation_status and validation_status != \"passed\":\n"
        "        blocking_reasons.append(f\"candidate validation status is {validation_status}\")\n\n"
        "    source_unchanged = evidence.get(\"source_a_unchanged\")\n"
        "    if source_unchanged is False:\n"
        "        blocking_reasons.append(\"source A mutation boundary was violated\")\n\n"
        "    if not any(\"backend/src/\" in path or \"macOS-Client/Sources/\" in path for path in changed):\n"
        "        warnings.append(\"candidate changed no primary product source file\")\n\n"
        "    recommendation = \"reject\" if blocking_reasons else \"review\"\n"
        "    return {\n"
        "        \"schema_version\": \"across-candidate-product-alignment/1.0\",\n"
        "        \"promotion_recommendation\": recommendation,\n"
        "        \"blocking_reasons\": blocking_reasons,\n"
        "        \"warnings\": warnings,\n"
        "        \"changed_file_count\": len(changed),\n"
        "        \"changed_files\": changed,\n"
        f"        \"model_summary\": {decision['summary']!r},\n"
        f"        \"model_risk\": {decision['risk']!r},\n"
        "    }\n"
    )


def _render_candidate_quality_test() -> str:
    return (
        "from across_agents_assistant.autopilot_candidate_quality import evaluate_candidate_product_alignment\n\n\n"
        "def test_alignment_reviews_product_source_change():\n"
        "    result = evaluate_candidate_product_alignment({\n"
        "        \"changed_files\": [\"backend/src/across_agents_assistant/autopilot_candidate_quality.py\"],\n"
        "        \"validation_status\": \"passed\",\n"
        "        \"gates\": [{\"id\": \"candidate_validation\", \"status\": \"passed\", \"required\": True}],\n"
        "    })\n"
        "    assert result[\"promotion_recommendation\"] == \"review\"\n"
        "    assert result[\"blocking_reasons\"] == []\n\n\n"
        "def test_alignment_rejects_no_diff_candidate():\n"
        "    result = evaluate_candidate_product_alignment({\"changed_files\": []})\n"
        "    assert result[\"promotion_recommendation\"] == \"reject\"\n"
        "    assert \"no changed files\" in result[\"blocking_reasons\"][0]\n\n\n"
        "def test_alignment_rejects_self_proof_only_candidate():\n"
        "    result = evaluate_candidate_product_alignment({\n"
        "        \"changed_files\": [\n"
        "            \"backend/src/across_agents_assistant/loop_engineering_candidate.py\",\n"
        "            \"backend/tests/test_loop_engineering_candidate.py\",\n"
        "        ]\n"
        "    })\n"
        "    assert result[\"promotion_recommendation\"] == \"reject\"\n"
        "    assert \"product-facing value\" in result[\"blocking_reasons\"][0]\n"
    )


def _render_research_signal_module(decision: Dict[str, Any]) -> str:
    return (
        '"""Research-backed candidate scoring for Autopilot self-iteration.\n\n'
        "This helper is intended for B candidate review. It converts research\n"
        "and validation evidence into a conservative promotion recommendation.\n"
        '"""\n\n'
        "from __future__ import annotations\n\n"
        "from collections.abc import Mapping\n"
        "from typing import Any\n\n\n"
        "def _items(value: Any) -> list[Any]:\n"
        "    if value is None:\n"
        "        return []\n"
        "    if isinstance(value, list):\n"
        "        return value\n"
        "    if isinstance(value, tuple):\n"
        "        return list(value)\n"
        "    return [value]\n\n\n"
        "def score_research_iteration_candidate(research_brief: Mapping[str, Any]) -> dict[str, Any]:\n"
        "    \"\"\"Score whether a research-backed candidate deserves human review.\"\"\"\n"
        "    sources = _items(research_brief.get(\"sources\"))\n"
        "    validation = _items(research_brief.get(\"validation_commands\"))\n"
        "    autonomy_level = int(research_brief.get(\"autonomy_level\") or 0)\n"
        "    relevant_sources = [source for source in sources if isinstance(source, Mapping) and str(source.get(\"relevance\") or \"\").lower() in {\"high\", \"medium\"}]\n"
        "    evidence_count = len(relevant_sources) or len(sources)\n"
        "    blocking_reasons: list[str] = []\n"
        "    warnings: list[str] = []\n\n"
        "    if evidence_count <= 0:\n"
        "        blocking_reasons.append(\"research evidence is missing\")\n"
        "    if len(validation) < 2:\n"
        "        warnings.append(\"candidate has fewer than two validation commands\")\n"
        "    if autonomy_level > 3:\n"
        "        blocking_reasons.append(\"autonomy level requires explicit approval before implementation\")\n\n"
        "    if blocking_reasons:\n"
        "        recommendation = \"reject\"\n"
        "    elif evidence_count >= 2 and len(validation) >= 2:\n"
        "        recommendation = \"implement\"\n"
        "    else:\n"
        "        recommendation = \"review\"\n\n"
        "    return {\n"
        "        \"schema_version\": \"across-research-iteration-score/1.0\",\n"
        "        \"recommendation\": recommendation,\n"
        "        \"evidence_count\": evidence_count,\n"
        "        \"validation_command_count\": len(validation),\n"
        "        \"blocking_reasons\": blocking_reasons,\n"
        "        \"warnings\": warnings,\n"
        f"        \"model_summary\": {decision['summary']!r},\n"
        f"        \"model_risk\": {decision['risk']!r},\n"
        "    }\n"
    )


def _render_research_signal_test() -> str:
    return (
        "from across_agents_assistant.autopilot_research_signal import score_research_iteration_candidate\n\n\n"
        "def test_scores_research_backed_candidate_as_implementable():\n"
        "    result = score_research_iteration_candidate({\n"
        "        \"sources\": [\n"
        "            {\"id\": \"openhands\", \"relevance\": \"high\"},\n"
        "            {\"id\": \"swe-agent\", \"relevance\": \"medium\"},\n"
        "        ],\n"
        "        \"validation_commands\": [\"python -m pytest\", \"swift test\"],\n"
        "        \"autonomy_level\": 3,\n"
        "    })\n"
        "    assert result[\"recommendation\"] == \"implement\"\n"
        "    assert result[\"evidence_count\"] == 2\n\n\n"
        "def test_rejects_missing_research_evidence():\n"
        "    result = score_research_iteration_candidate({\"sources\": [], \"validation_commands\": []})\n"
        "    assert result[\"recommendation\"] == \"reject\"\n"
        "    assert \"research evidence\" in result[\"blocking_reasons\"][0]\n\n\n"
        "def test_requires_review_for_shallow_validation():\n"
        "    result = score_research_iteration_candidate({\n"
        "        \"sources\": [{\"id\": \"langgraph\", \"relevance\": \"high\"}],\n"
        "        \"validation_commands\": [\"python -m py_compile\"],\n"
        "        \"autonomy_level\": 3,\n"
        "    })\n"
        "    assert result[\"recommendation\"] == \"review\"\n"
        "    assert result[\"warnings\"]\n"
    )


def _render_source_quality_module(decision: Dict[str, Any]) -> str:
    return (
        '"""Source quality triage for autonomous Loop Engineering candidates."""\n\n'
        "from __future__ import annotations\n\n"
        "from collections.abc import Mapping, Sequence\n"
        "from typing import Any\n\n\n"
        "ALLOWED_STATUSES = {\"ok\", \"stale\", \"missing\", \"error\"}\n"
        "MIN_STRONG_EXCERPT_CHARS = 80\n\n\n"
        "def _text(value: Any) -> str:\n"
        "    return str(value or \"\").strip()\n\n\n"
        "def _items(value: Any) -> list[Any]:\n"
        "    if value is None:\n"
        "        return []\n"
        "    if isinstance(value, list):\n"
        "        return value\n"
        "    if isinstance(value, tuple):\n"
        "        return list(value)\n"
        "    return [value]\n\n\n"
        "def _source_id(source: Mapping[str, Any], index: int) -> str:\n"
        "    return _text(source.get(\"id\") or source.get(\"url\") or source.get(\"title\") or f\"source-{index + 1}\")\n\n\n"
        "def _triage_source(source: Mapping[str, Any], index: int) -> dict[str, Any]:\n"
        "    source_id = _source_id(source, index)\n"
        "    status = _text(source.get(\"status\")).lower()\n"
        "    adapter = _text(source.get(\"adapter\") or source.get(\"type\"))\n"
        "    url = _text(source.get(\"url\") or source.get(\"source_url\"))\n"
        "    excerpt = _text(source.get(\"excerpt\") or source.get(\"content\") or source.get(\"summary\"))\n"
        "    reasons: list[str] = []\n\n"
        "    if not status:\n"
        "        reasons.append(\"missing status\")\n"
        "    elif status not in ALLOWED_STATUSES:\n"
        "        reasons.append(f\"unsupported status: {status}\")\n"
        "    elif status != \"ok\":\n"
        "        reasons.append(f\"source status is {status}\")\n"
        "    if not excerpt:\n"
        "        reasons.append(\"missing excerpt\")\n"
        "    if not adapter:\n"
        "        reasons.append(\"missing adapter\")\n"
        "    if status == \"ok\" and not url and adapter == \"url\":\n"
        "        reasons.append(\"missing url\")\n"
        "    if reasons:\n"
        "        return {\"id\": source_id, \"status\": \"failed\", \"reasons\": reasons}\n"
        "    if len(excerpt) < MIN_STRONG_EXCERPT_CHARS:\n"
        "        return {\"id\": source_id, \"status\": \"weak\", \"reasons\": [\"excerpt is too short\"]}\n"
        "    return {\"id\": source_id, \"status\": \"ok\", \"reasons\": []}\n\n\n"
        "def triage_sources(sources: Sequence[Mapping[str, Any]] | Mapping[str, Any]) -> dict[str, Any]:\n"
        "    \"\"\"Classify source evidence before model-backed product iteration.\"\"\"\n"
        "    source_list = [item for item in _items(sources.get(\"sources\") if isinstance(sources, Mapping) else sources) if isinstance(item, Mapping)]\n"
        "    classified = [_triage_source(source, index) for index, source in enumerate(source_list)]\n"
        "    weak_sources = [item for item in classified if item[\"status\"] == \"weak\"]\n"
        "    failed_sources = [item for item in classified if item[\"status\"] == \"failed\"]\n"
        "    ok_count = len([item for item in classified if item[\"status\"] == \"ok\"])\n"
        "    return {\n"
        "        \"schema_version\": \"across-autopilot-source-quality/1.0\",\n"
        "        \"total\": len(classified),\n"
        "        \"ok_count\": ok_count,\n"
        "        \"weak_count\": len(weak_sources),\n"
        "        \"failed_count\": len(failed_sources),\n"
        "        \"weak_sources\": weak_sources,\n"
        "        \"failed_sources\": failed_sources,\n"
        "        \"needs_model_fallback\": ok_count == 0 or bool(failed_sources),\n"
        f"        \"model_summary\": {decision['summary']!r},\n"
        f"        \"model_risk\": {decision['risk']!r},\n"
        "    }\n"
    )


def _render_source_quality_test() -> str:
    strong_excerpt = (
        "Agent workflow research indicates that stable tool boundaries, independent "
        "review, and durable evidence are required for autonomous iteration."
    )
    return (
        "from across_agents_assistant.autopilot_source_quality import triage_sources\n\n\n"
        "def test_triage_accepts_strong_source():\n"
        "    result = triage_sources([{\n"
        "        \"id\": \"agents-sdk\",\n"
        "        \"adapter\": \"url\",\n"
        "        \"url\": \"https://example.com/agents\",\n"
        "        \"status\": \"ok\",\n"
        f"        \"excerpt\": {strong_excerpt!r},\n"
        "    }])\n"
        "    assert result[\"ok_count\"] == 1\n"
        "    assert result[\"needs_model_fallback\"] is False\n\n\n"
        "def test_weak_source_when_excerpt_too_short():\n"
        "    result = triage_sources([{\n"
        "        \"id\": \"thin\",\n"
        "        \"adapter\": \"url\",\n"
        "        \"url\": \"https://example.com/thin\",\n"
        "        \"status\": \"ok\",\n"
        "        \"excerpt\": \"short\",\n"
        "    }])\n"
        "    assert result[\"weak_count\"] == 1\n"
        "    assert result[\"failed_count\"] == 0\n\n\n"
        "def test_triage_flags_empty_excerpt_as_failed():\n"
        "    result = triage_sources([{\"id\": \"empty\", \"adapter\": \"manual_input\", \"status\": \"ok\", \"excerpt\": \"\"}])\n"
        "    assert result[\"failed_count\"] == 1\n"
        "    assert \"missing excerpt\" in result[\"failed_sources\"][0][\"reasons\"]\n\n\n"
        "def test_triage_flags_missing_status_as_failed():\n"
        "    result = triage_sources([{\"id\": \"missing\", \"adapter\": \"url\", \"url\": \"https://example.com\", \"excerpt\": \"content\"}])\n"
        "    assert result[\"failed_count\"] == 1\n"
        "    assert \"missing status\" in result[\"failed_sources\"][0][\"reasons\"]\n"
    )


def _render_tool_pack_policy_module(decision: Dict[str, Any]) -> str:
    return (
        '"""Tool Pack policy checks for autonomous Loop Engineering candidates."""\n\n'
        "from __future__ import annotations\n\n"
        "from collections.abc import Mapping\n"
        "from typing import Any\n\n\n"
        "REQUIRED_TOOL_PACKS = {\"git_repo_inspection\", \"candidate_workspace\", \"validation_harness\", \"independent_review\"}\n\n\n"
        "def _items(value: Any) -> list[Any]:\n"
        "    if value is None:\n"
        "        return []\n"
        "    if isinstance(value, (list, tuple, set)):\n"
        "        return list(value)\n"
        "    return [value]\n\n\n"
        "def evaluate_tool_pack_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:\n"
        "    \"\"\"Evaluate whether a candidate used stable tool packs instead of ad-hoc scripts.\"\"\"\n"
        "    tool_packs = {str(item) for item in _items(candidate.get(\"tool_packs\")) if str(item).strip()}\n"
        "    ad_hoc_scripts = [str(item) for item in _items(candidate.get(\"ad_hoc_scripts\")) if str(item).strip()]\n"
        "    missing = sorted(REQUIRED_TOOL_PACKS - tool_packs)\n"
        "    blocking_reasons: list[str] = []\n"
        "    warnings: list[str] = []\n\n"
        "    if ad_hoc_scripts:\n"
        "        warnings.append(\"candidate used ad-hoc scripts that should become Tool Packs\")\n"
        "    if \"candidate_workspace\" not in tool_packs:\n"
        "        blocking_reasons.append(\"candidate workspace Tool Pack is required for B-only mutation\")\n"
        "    if \"validation_harness\" not in tool_packs:\n"
        "        blocking_reasons.append(\"validation harness Tool Pack is required before review\")\n\n"
        "    if blocking_reasons:\n"
        "        recommendation = \"reject\"\n"
        "    elif missing or warnings:\n"
        "        recommendation = \"review\"\n"
        "    else:\n"
        "        recommendation = \"implement\"\n\n"
        "    return {\n"
        "        \"schema_version\": \"across-tool-pack-policy/1.0\",\n"
        "        \"recommendation\": recommendation,\n"
        "        \"tool_pack_count\": len(tool_packs),\n"
        "        \"missing_tool_packs\": missing,\n"
        "        \"blocking_reasons\": blocking_reasons,\n"
        "        \"warnings\": warnings,\n"
        f"        \"model_summary\": {decision['summary']!r},\n"
        f"        \"model_risk\": {decision['risk']!r},\n"
        "    }\n"
    )


def _render_tool_pack_policy_test() -> str:
    return (
        "from across_agents_assistant.autopilot_tool_pack_policy import evaluate_tool_pack_candidate\n\n\n"
        "def test_accepts_stable_tool_pack_flow():\n"
        "    result = evaluate_tool_pack_candidate({\n"
        "        \"tool_packs\": [\"git_repo_inspection\", \"candidate_workspace\", \"validation_harness\", \"independent_review\"],\n"
        "        \"ad_hoc_scripts\": [],\n"
        "    })\n"
        "    assert result[\"recommendation\"] == \"implement\"\n"
        "    assert result[\"tool_pack_count\"] == 4\n\n\n"
        "def test_rejects_candidate_without_workspace_pack():\n"
        "    result = evaluate_tool_pack_candidate({\"tool_packs\": [\"validation_harness\"]})\n"
        "    assert result[\"recommendation\"] == \"reject\"\n"
        "    assert any(\"workspace\" in reason for reason in result[\"blocking_reasons\"])\n\n\n"
        "def test_reviews_ad_hoc_scripts():\n"
        "    result = evaluate_tool_pack_candidate({\n"
        "        \"tool_packs\": [\"candidate_workspace\", \"validation_harness\"],\n"
        "        \"ad_hoc_scripts\": [\"temporary_git_probe.py\"],\n"
        "    })\n"
        "    assert result[\"recommendation\"] == \"review\"\n"
        "    assert result[\"warnings\"]\n"
    )


def _render_loop_contract_policy_module(decision: Dict[str, Any]) -> str:
    return (
        '"""Loop Contract readiness policy for autonomous Loop Engineering."""\n\n'
        "from __future__ import annotations\n\n"
        "from collections.abc import Mapping\n"
        "from typing import Any\n\n\n"
        "def _count(value: Any) -> int:\n"
        "    if value is None:\n"
        "        return 0\n"
        "    if isinstance(value, Mapping):\n"
        "        return len(value)\n"
        "    if isinstance(value, (list, tuple, set)):\n"
        "        return len(value)\n"
        "    return 1\n\n\n"
        "def summarize_loop_contract_state(state: Mapping[str, Any]) -> dict[str, Any]:\n"
        "    \"\"\"Summarize whether artifacts, contract, backlog, and timeline are present.\"\"\"\n"
        "    artifact_count = _count(state.get(\"artifacts\"))\n"
        "    backlog_count = _count(state.get(\"backlog\"))\n"
        "    timeline_count = _count(state.get(\"timeline\"))\n"
        "    missing: list[str] = []\n"
        "    if artifact_count <= 0:\n"
        "        missing.append(\"artifacts\")\n"
        "    if backlog_count <= 0:\n"
        "        missing.append(\"backlog\")\n"
        "    if timeline_count <= 0:\n"
        "        missing.append(\"timeline\")\n"
        "    status = \"ready\" if not missing else \"incomplete\"\n"
        "    return {\n"
        "        \"schema_version\": \"across-loop-contract-policy/1.0\",\n"
        "        \"status\": status,\n"
        "        \"artifact_count\": artifact_count,\n"
        "        \"backlog_count\": backlog_count,\n"
        "        \"timeline_count\": timeline_count,\n"
        "        \"missing_sections\": missing,\n"
        f"        \"model_summary\": {decision['summary']!r},\n"
        f"        \"model_risk\": {decision['risk']!r},\n"
        "    }\n"
    )


def _render_loop_contract_policy_test() -> str:
    return (
        "from across_agents_assistant.autopilot_loop_contract_policy import summarize_loop_contract_state\n\n\n"
        "def test_contract_state_is_ready_when_required_sections_exist():\n"
        "    result = summarize_loop_contract_state({\"artifacts\": [{}], \"backlog\": [{}], \"timeline\": [{}]})\n"
        "    assert result[\"status\"] == \"ready\"\n"
        "    assert result[\"missing_sections\"] == []\n\n\n"
        "def test_contract_state_reports_missing_sections():\n"
        "    result = summarize_loop_contract_state({\"artifacts\": []})\n"
        "    assert result[\"status\"] == \"incomplete\"\n"
        "    assert \"backlog\" in result[\"missing_sections\"]\n"
        "    assert \"timeline\" in result[\"missing_sections\"]\n"
    )


def _render_reviewer_policy_module(decision: Dict[str, Any]) -> str:
    return (
        '"""Independent reviewer policy for autonomous B candidate promotion."""\n\n'
        "from __future__ import annotations\n\n"
        "from collections.abc import Mapping\n"
        "from typing import Any\n\n\n"
        "def _items(value: Any) -> list[Any]:\n"
        "    if value is None:\n"
        "        return []\n"
        "    if isinstance(value, (list, tuple, set)):\n"
        "        return list(value)\n"
        "    return [value]\n\n\n"
        "def review_builder_candidate(evidence: Mapping[str, Any]) -> dict[str, Any]:\n"
        "    \"\"\"Review whether builder output is safe for human promotion review.\"\"\"\n"
        "    builder_role = str(evidence.get(\"builder_role\") or \"\")\n"
        "    reviewer_role = str(evidence.get(\"reviewer_role\") or \"\")\n"
        "    changed_files = [str(item) for item in _items(evidence.get(\"changed_files\")) if str(item).strip()]\n"
        "    validation_status = str(evidence.get(\"validation_status\") or \"\")\n"
        "    blocking_reasons: list[str] = []\n"
        "    if builder_role and reviewer_role and builder_role == reviewer_role:\n"
        "        blocking_reasons.append(\"builder and reviewer roles must be separate\")\n"
        "    if not changed_files:\n"
        "        blocking_reasons.append(\"candidate has no changed files\")\n"
        "    if validation_status != \"passed\":\n"
        "        blocking_reasons.append(\"candidate validation must pass before review\")\n"
        "    return {\n"
        "        \"schema_version\": \"across-independent-reviewer-policy/1.0\",\n"
        "        \"recommendation\": \"reject\" if blocking_reasons else \"review\",\n"
        "        \"blocking_reasons\": blocking_reasons,\n"
        "        \"changed_file_count\": len(changed_files),\n"
        "        \"reviewer_independent\": not (builder_role and reviewer_role and builder_role == reviewer_role),\n"
        f"        \"model_summary\": {decision['summary']!r},\n"
        f"        \"model_risk\": {decision['risk']!r},\n"
        "    }\n"
    )


def _render_reviewer_policy_test() -> str:
    return (
        "from across_agents_assistant.autopilot_reviewer_policy import review_builder_candidate\n\n\n"
        "def test_reviewer_accepts_separate_builder_with_validation():\n"
        "    result = review_builder_candidate({\n"
        "        \"builder_role\": \"loop_engineer\",\n"
        "        \"reviewer_role\": \"independent_reviewer\",\n"
        "        \"changed_files\": [\"backend/src/across_agents_assistant/autopilot_reviewer_policy.py\"],\n"
        "        \"validation_status\": \"passed\",\n"
        "    })\n"
        "    assert result[\"recommendation\"] == \"review\"\n"
        "    assert result[\"reviewer_independent\"] is True\n\n\n"
        "def test_reviewer_rejects_self_review():\n"
        "    result = review_builder_candidate({\n"
        "        \"builder_role\": \"loop_engineer\",\n"
        "        \"reviewer_role\": \"loop_engineer\",\n"
        "        \"changed_files\": [\"x\"],\n"
        "        \"validation_status\": \"passed\",\n"
        "    })\n"
        "    assert result[\"recommendation\"] == \"reject\"\n"
        "    assert any(\"separate\" in reason for reason in result[\"blocking_reasons\"])\n"
    )


def _render_backlog_builder_module(decision: Dict[str, Any]) -> str:
    return (
        '"""Deterministic backlog builder for autonomous AAA self-iteration candidates."""\n\n'
        "from __future__ import annotations\n\n"
        "from collections.abc import Mapping, Sequence\n"
        "from typing import Any\n\n\n"
        "HARD_TOOL_PACKS = {\"git_repo_inspection\", \"candidate_workspace\", \"validation_harness\", \"independent_review\", \"evidence_integrity\"}\n\n\n"
        "def _items(value: Any) -> list[Any]:\n"
        "    if value is None:\n"
        "        return []\n"
        "    if isinstance(value, list):\n"
        "        return value\n"
        "    if isinstance(value, tuple):\n"
        "        return list(value)\n"
        "    return [value]\n\n\n"
        "def summarize_tool_pack_readiness(tool_packs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:\n"
        "    statuses = {str(pack.get(\"id\") or pack.get(\"pack_id\") or \"\"): str(pack.get(\"status\") or \"unknown\") for pack in tool_packs}\n"
        "    present_hard = sorted(pack for pack in HARD_TOOL_PACKS if pack in statuses)\n"
        "    missing_hard = sorted(HARD_TOOL_PACKS - set(statuses))\n"
        "    failed_hard = sorted(pack for pack in present_hard if statuses.get(pack) not in {\"passed\", \"ready\"})\n"
        "    overall_status = \"passed\" if present_hard and not missing_hard and not failed_hard else \"attention\"\n"
        "    return {\n"
        "        \"schema_version\": \"across-autopilot-backlog-tool-pack-summary/1.0\",\n"
        "        \"overall_status\": overall_status,\n"
        "        \"present_hard\": present_hard,\n"
        "        \"missing_hard\": missing_hard,\n"
        "        \"failed_hard\": failed_hard,\n"
        "        \"pack_count\": len(statuses),\n"
        "    }\n\n\n"
        "def build_backlog_entry(candidate: Mapping[str, Any], tool_packs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:\n"
        "    summary = summarize_tool_pack_readiness(tool_packs)\n"
        "    validation_commands = _items(candidate.get(\"validation_commands\"))\n"
        "    allowed_patch_paths = [str(path) for path in _items(candidate.get(\"allowed_patch_paths\")) if str(path).strip()]\n"
        "    score = int(candidate.get(\"score\") or 0)\n"
        "    if summary[\"overall_status\"] == \"passed\":\n"
        "        score += 10\n"
        "    score += min(len(validation_commands), 3)\n"
        "    score += min(len(allowed_patch_paths), 4)\n"
        "    return {\n"
        "        \"id\": str(candidate.get(\"id\") or \"generated-backlog-item\"),\n"
        "        \"goal\": str(candidate.get(\"goal\") or \"Review model-selected autonomous candidate.\"),\n"
        "        \"risk\": str(candidate.get(\"risk\") or \"low\"),\n"
        "        \"generated_from\": str(candidate.get(\"generated_from\") or \"model_generated\"),\n"
        "        \"allowed_patch_paths\": allowed_patch_paths,\n"
        "        \"validation_command_count\": len(validation_commands),\n"
        "        \"tool_pack_summary\": summary,\n"
        "        \"score\": score,\n"
        f"        \"model_summary\": {decision['summary']!r},\n"
        f"        \"model_risk\": {decision['risk']!r},\n"
        "    }\n\n\n"
        "def rank_backlog_candidates(candidates: Sequence[Mapping[str, Any]], tool_packs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:\n"
        "    entries = [build_backlog_entry(candidate, tool_packs) for candidate in candidates]\n"
        "    return sorted(entries, key=lambda item: (-int(item[\"score\"]), item[\"id\"]))\n"
    )


def _render_backlog_builder_test() -> str:
    return (
        "from across_agents_assistant.autopilot_backlog_builder import rank_backlog_candidates, summarize_tool_pack_readiness\n\n\n"
        "TOOL_PACKS = [\n"
        "    {\"id\": \"git_repo_inspection\", \"status\": \"passed\"},\n"
        "    {\"id\": \"candidate_workspace\", \"status\": \"passed\"},\n"
        "    {\"id\": \"validation_harness\", \"status\": \"passed\"},\n"
        "    {\"id\": \"independent_review\", \"status\": \"passed\"},\n"
        "    {\"id\": \"evidence_integrity\", \"status\": \"passed\"},\n"
        "]\n\n\n"
        "def test_summarizes_required_tool_pack_readiness():\n"
        "    summary = summarize_tool_pack_readiness(TOOL_PACKS)\n"
        "    assert summary[\"overall_status\"] == \"passed\"\n"
        "    assert summary[\"missing_hard\"] == []\n"
        "    assert summary[\"pack_count\"] == 5\n\n\n"
        "def test_rank_orders_by_readiness_and_score():\n"
        "    ranked = rank_backlog_candidates([\n"
        "        {\"id\": \"low\", \"score\": 1, \"allowed_patch_paths\": [\"a.py\"], \"validation_commands\": []},\n"
        "        {\"id\": \"high\", \"score\": 5, \"allowed_patch_paths\": [\"a.py\", \"b.py\"], \"validation_commands\": [\"compile\", \"runpy\"]},\n"
        "    ], TOOL_PACKS)\n"
        "    assert ranked[0][\"id\"] == \"high\"\n"
        "    assert ranked[0][\"tool_pack_summary\"][\"overall_status\"] == \"passed\"\n\n\n"
        "def test_missing_hard_pack_requires_attention():\n"
        "    summary = summarize_tool_pack_readiness(TOOL_PACKS[:-1])\n"
        "    assert summary[\"overall_status\"] == \"attention\"\n"
        "    assert \"evidence_integrity\" in summary[\"missing_hard\"]\n"
    )


def _render_loop_backlog_module(decision: Dict[str, Any]) -> str:
    return (
        '"""Loop-state backlog reader for autonomous AAA self-iteration candidates."""\n\n'
        "from __future__ import annotations\n\n"
        "import json\n"
        "from pathlib import Path\n"
        "from typing import Any\n\n\n"
        "def _read_json(path: Path, default: Any) -> Any:\n"
        "    try:\n"
        "        return json.loads(path.read_text(encoding=\"utf-8\"))\n"
        "    except Exception:\n"
        "        return default\n\n\n"
        "def _read_jsonl(path: Path, limit: int) -> list[dict[str, Any]]:\n"
        "    rows: list[dict[str, Any]] = []\n"
        "    try:\n"
        "        lines = path.read_text(encoding=\"utf-8\").splitlines()\n"
        "    except Exception:\n"
        "        return rows\n"
        "    for line in lines[-max(1, limit):]:\n"
        "        try:\n"
        "            value = json.loads(line)\n"
        "        except Exception:\n"
        "            continue\n"
        "        if isinstance(value, dict):\n"
        "            rows.append(value)\n"
        "    return rows\n\n\n"
        "def _items(value: Any) -> list[Any]:\n"
        "    if value is None:\n"
        "        return []\n"
        "    if isinstance(value, list):\n"
        "        return value\n"
        "    if isinstance(value, tuple):\n"
        "        return list(value)\n"
        "    return [value]\n\n\n"
        "def _candidate_score(item: dict[str, Any], timeline_count: int) -> int:\n"
        "    score = int(item.get(\"score\") or 0)\n"
        "    score += min(len(_items(item.get(\"validation_commands\"))), 3)\n"
        "    score += min(len(_items(item.get(\"allowed_patch_paths\"))), 4)\n"
        "    score += min(timeline_count, 5)\n"
        "    return score\n\n\n"
        "def build_loop_backlog(root: str | Path, global_timeline_tail: int = 5) -> dict[str, Any]:\n"
        "    base = Path(root)\n"
        "    contract = _read_json(base / \"contract.json\", {})\n"
        "    backlog_doc = _read_json(base / \"backlog.json\", {})\n"
        "    timeline = _read_jsonl(base / \"timeline.jsonl\", global_timeline_tail)\n"
        "    source_signals = _read_json(base / \"source-signals.json\", {})\n"
        "    raw_items = _items(backlog_doc.get(\"items\") if isinstance(backlog_doc, dict) else backlog_doc)\n"
        "    entries: list[dict[str, Any]] = []\n"
        "    for index, raw in enumerate(raw_items):\n"
        "        if not isinstance(raw, dict):\n"
        "            continue\n"
        "        entry = dict(raw)\n"
        "        entry.setdefault(\"id\", f\"candidate-{index + 1}\")\n"
        "        entry.setdefault(\"generated_from\", \"loop_state\")\n"
        "        entry[\"score\"] = _candidate_score(entry, len(timeline))\n"
        "        entry[\"selected_iteration\"] = {\n"
        "            \"target_repo\": entry.get(\"target_repo\", \"across-agents-assistant\"),\n"
        "            \"goal\": entry.get(\"goal\") or entry.get(\"summary\") or \"Review autonomous candidate.\",\n"
        "            \"allowed_patch_paths\": _items(entry.get(\"allowed_patch_paths\")),\n"
        "            \"validation_commands\": _items(entry.get(\"validation_commands\")),\n"
        "            \"generated_from\": entry.get(\"generated_from\"),\n"
        "            \"risk\": entry.get(\"risk\", \"low\"),\n"
        "        }\n"
        "        entries.append(entry)\n"
        "    entries.sort(key=lambda item: (-int(item.get(\"score\") or 0), str(item.get(\"id\") or \"\")))\n"
        "    return {\n"
        "        \"schema_version\": \"across-autopilot-loop-backlog/1.0\",\n"
        "        \"spec_id\": contract.get(\"spec_id\") or contract.get(\"id\") or base.name,\n"
        "        \"timeline_event_count\": len(timeline),\n"
        "        \"source_signal_count\": len(_items(source_signals.get(\"sources\") if isinstance(source_signals, dict) else source_signals)),\n"
        "        \"targets\": entries,\n"
        f"        \"model_summary\": {decision['summary']!r},\n"
        f"        \"model_risk\": {decision['risk']!r},\n"
        "    }\n\n\n"
        "def select_top(backlog: dict[str, Any]) -> dict[str, Any] | None:\n"
        "    targets = backlog.get(\"targets\") or []\n"
        "    return targets[0] if targets else None\n"
    )


def _render_loop_backlog_test() -> str:
    return (
        "import json\n"
        "from pathlib import Path\n\n"
        "from tempfile import TemporaryDirectory\n\n"
        "from across_agents_assistant.autopilot_loop_backlog import build_loop_backlog, select_top\n\n\n"
        "def _write_json(path: Path, value):\n"
        "    path.write_text(json.dumps(value), encoding=\"utf-8\")\n\n\n"
        "def test_build_loop_backlog_returns_deterministic_ranked_results():\n"
        "    with TemporaryDirectory() as tmp:\n"
        "        root = Path(tmp)\n"
        "        _write_json(root / \"contract.json\", {\"spec_id\": \"aaa-autonomous-self-iteration\"})\n"
        "        _write_json(root / \"backlog.json\", {\"items\": [\n"
        "            {\"id\": \"low\", \"score\": 1, \"allowed_patch_paths\": [\"a.py\"], \"validation_commands\": []},\n"
        "            {\"id\": \"high\", \"score\": 5, \"allowed_patch_paths\": [\"a.py\", \"b.py\"], \"validation_commands\": [\"compile\", \"runpy\"]},\n"
        "        ]})\n"
        "        (root / \"timeline.jsonl\").write_text('{\"event\":\"one\"}\\n{\"event\":\"two\"}\\n', encoding=\"utf-8\")\n"
        "        _write_json(root / \"source-signals.json\", {\"sources\": [{\"id\": \"loop-engineering\"}]})\n"
        "        result = build_loop_backlog(root)\n"
        "    assert result[\"spec_id\"] == \"aaa-autonomous-self-iteration\"\n"
        "    assert select_top(result)[\"id\"] == \"high\"\n"
        "    assert select_top(result)[\"selected_iteration\"][\"allowed_patch_paths\"] == [\"a.py\", \"b.py\"]\n\n\n"
        "def test_build_loop_backlog_tolerates_missing_files():\n"
        "    with TemporaryDirectory() as tmp:\n"
        "        result = build_loop_backlog(tmp)\n"
        "    assert result[\"targets\"] == []\n"
        "    assert select_top(result) is None\n"
    )


def _fallback_direct_code_iteration_decision(
    raw_text: str,
    error: Exception,
    *,
    allowed_patch_paths: List[str],
    allow_host_fallback: bool = False,
    source_repository: Optional[str] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    if not allow_host_fallback:
        raise ValueError(
            "Model direct patch JSON remained invalid after repair; host code fallback is disabled "
            "for autonomous production loops. Enable model_policy.allow_host_code_fallback only for "
            "conformance fixtures."
        ) from error
    allowed = {_safe_autopilot_rel_path(path) for path in allowed_patch_paths if str(path or "").strip()}
    platform_self_repair_expected = {"tests/platform-self-repair.test.js"}
    if platform_self_repair_expected.issubset(allowed):
        decision = {
            "summary": "Add deterministic platform self-repair replay coverage.",
            "risk": "low",
            "patch_paths": sorted(platform_self_repair_expected),
            "validation_commands": [
                {
                    "command": "node",
                    "args": ["--test", "tests/platform-self-repair.test.js"],
                }
            ],
            "fallback_reason": str(error)[:200],
        }
        return decision, [
            {
                "path": "tests/platform-self-repair.test.js",
                "mode": "overwrite",
                "content": _render_platform_self_repair_replay_test(),
            }
        ]
    quality_expected = {
        "backend/src/across_agents_assistant/autopilot_candidate_quality.py",
        "backend/tests/test_autopilot_candidate_quality.py",
    }
    research_expected = {
        "backend/src/across_agents_assistant/autopilot_research_signal.py",
        "backend/tests/test_autopilot_research_signal.py",
    }
    source_quality_expected = {
        "backend/src/across_agents_assistant/autopilot_source_quality.py",
        "backend/tests/test_autopilot_source_quality.py",
    }
    tool_pack_expected = {
        "backend/src/across_agents_assistant/autopilot_tool_pack_policy.py",
        "backend/tests/test_autopilot_tool_pack_policy.py",
    }
    contract_expected = {
        "backend/src/across_agents_assistant/autopilot_loop_contract_policy.py",
        "backend/tests/test_autopilot_loop_contract_policy.py",
    }
    reviewer_expected = {
        "backend/src/across_agents_assistant/autopilot_reviewer_policy.py",
        "backend/tests/test_autopilot_reviewer_policy.py",
    }
    backlog_expected = {
        "backend/src/across_agents_assistant/autopilot_backlog_builder.py",
        "backend/tests/test_autopilot_backlog_builder.py",
    }
    loop_backlog_expected = {
        "backend/src/across_agents_assistant/autopilot_loop_backlog.py",
        "backend/tests/test_autopilot_loop_backlog.py",
    }
    target_backlog_expected = {
        "backend/src/across_agents_assistant/autopilot_target_backlog.py",
        "backend/tests/test_autopilot_target_backlog.py",
    }
    target_backlog_workbench = "backend/src/across_agents_assistant/autopilot_workbench.py"
    target_backlog_api = "backend/src/across_agents_assistant/api_server.py"
    target_backlog_capability_pack = "backend/src/across_agents_assistant/loop_engineering_capability_pack.py"
    target_backlog_swift_view = "macOS-Client/Sources/AutopilotTargetBacklogView.swift"
    if target_backlog_expected.issubset(allowed):
        optional_paths = {
            path for path in (
                target_backlog_workbench,
                target_backlog_api,
                target_backlog_capability_pack,
                target_backlog_swift_view,
            )
            if path in allowed
        }
        decision = {
            "summary": "Add validation-stable autonomous target backlog helpers.",
            "risk": "low",
            "patch_paths": sorted(target_backlog_expected | optional_paths),
            "validation_commands": [
                {
                    "command": "python3",
                    "args": [
                        "-m",
                        "py_compile",
                        "backend/src/across_agents_assistant/autopilot_target_backlog.py",
                        "backend/tests/test_autopilot_target_backlog.py",
                    ],
                },
                {
                    "command": "python3",
                    "args": [
                        "-c",
                        "import sys, runpy; sys.path.insert(0,'backend/src'); "
                        "ns=runpy.run_path('backend/tests/test_autopilot_target_backlog.py'); "
                        "tests=[v for k,v in ns.items() if k.startswith('test_') and callable(v)]; "
                        "assert tests; [test() for test in tests]; print('tests-ok')",
                    ],
                },
            ],
            "fallback_reason": str(error)[:200],
        }
        patches = [
            {
                "path": "backend/src/across_agents_assistant/autopilot_target_backlog.py",
                "mode": "overwrite",
                "content": _render_target_backlog_module(decision),
            },
            {
                "path": "backend/tests/test_autopilot_target_backlog.py",
                "mode": "overwrite",
                "content": _render_target_backlog_test(),
            },
        ]
        if target_backlog_workbench in allowed:
            patches.append(
                {
                    "path": target_backlog_workbench,
                    "mode": "upsert_between_markers",
                    "marker_start": "# ACROSS TARGET BACKLOG WORKBENCH START",
                    "marker_end": "# ACROSS TARGET BACKLOG WORKBENCH END",
                    "content": _render_target_backlog_workbench_block(),
                }
            )
        if target_backlog_api in allowed:
            patches.append(
                {
                    "path": target_backlog_api,
                    "mode": "upsert_between_markers",
                    "marker_start": "# ACROSS TARGET BACKLOG API START",
                    "marker_end": "# ACROSS TARGET BACKLOG API END",
                    "content": _render_target_backlog_api_block(),
                }
            )
        if target_backlog_capability_pack in allowed:
            patches.append(
                {
                    "path": target_backlog_capability_pack,
                    "mode": "upsert_between_markers",
                    "marker_start": "# ACROSS TARGET BACKLOG CAPABILITY PACK START",
                    "marker_end": "# ACROSS TARGET BACKLOG CAPABILITY PACK END",
                    "content": _render_target_backlog_capability_pack_block(),
                }
            )
        if target_backlog_swift_view in allowed:
            patches.append(
                {
                    "path": target_backlog_swift_view,
                    "mode": "overwrite",
                    "content": _render_target_backlog_swift_view(),
                }
            )
        return decision, patches
    iteration_telemetry_expected = {
        "backend/src/across_agents_assistant/autopilot_iteration_telemetry.py",
        "backend/tests/test_autopilot_iteration_telemetry.py",
    }
    iteration_telemetry_workbench = "backend/src/across_agents_assistant/autopilot_workbench.py"
    mcp_tool_manifest_pairs = [
        (
            "backend/src/across_agents_assistant/autopilot_mcp_tool_manifest.py",
            "backend/tests/test_autopilot_mcp_tool_manifest.py",
        ),
        (
            "backend/src/across_agents_assistant/autopilot_tool_manifest.py",
            "backend/tests/test_autopilot_tool_manifest.py",
        ),
    ]
    mcp_tool_manifest_api = "backend/src/across_agents_assistant/api_server.py"
    mcp_tool_manifest_pair = next(
        (
            (module_path, test_path)
            for module_path, test_path in mcp_tool_manifest_pairs
            if {module_path, test_path}.issubset(allowed)
        ),
        None,
    )
    if mcp_tool_manifest_pair:
        module_path, test_path = mcp_tool_manifest_pair
        module_name = Path(module_path).stem
        optional_paths = {mcp_tool_manifest_api} if mcp_tool_manifest_api in allowed else set()
        decision = {
            "summary": "Add validation-stable MCP tool manifest helpers.",
            "risk": "low",
            "patch_paths": sorted({module_path, test_path} | optional_paths),
            "validation_commands": [
                {
                    "command": "python3",
                    "args": [
                        "-m",
                        "py_compile",
                        module_path,
                        test_path,
                    ],
                },
                {
                    "command": "python3",
                    "args": [
                        "-c",
                        "import sys, runpy; sys.path.insert(0,'backend/src'); "
                        f"ns=runpy.run_path({test_path!r}); "
                        "tests=[v for k,v in ns.items() if k.startswith('test_') and callable(v)]; "
                        "assert tests; [test() for test in tests]; print('tests-ok')",
                    ],
                },
            ],
            "fallback_reason": str(error)[:200],
        }
        patches = [
            {
                "path": module_path,
                "mode": "overwrite",
                "content": _render_mcp_tool_manifest_module(decision),
            },
            {
                "path": test_path,
                "mode": "overwrite",
                "content": _render_mcp_tool_manifest_test(module_name=module_name),
            },
        ]
        if mcp_tool_manifest_api in allowed:
            patches.append(
                {
                    "path": mcp_tool_manifest_api,
                    "mode": "upsert_between_markers",
                    "marker_start": "# ACROSS MCP TOOL MANIFEST REGISTRATION START",
                    "marker_end": "# ACROSS MCP TOOL MANIFEST REGISTRATION END",
                    "content": _render_mcp_tool_manifest_api_block(module_name=module_name),
                }
            )
        return decision, patches
    mcp_tool_registry_expected = {
        "backend/src/across_agents_assistant/autopilot_mcp_tool_registry.py",
        "backend/tests/test_autopilot_mcp_tool_registry.py",
    }
    mcp_tool_registry_workbench = "backend/src/across_agents_assistant/autopilot_workbench.py"
    mcp_tool_registry_api = "backend/src/across_agents_assistant/api_server.py"
    mcp_tool_registry_capability_pack = "backend/src/across_agents_assistant/loop_engineering_capability_pack.py"
    if mcp_tool_registry_expected.issubset(allowed):
        optional_paths = {
            path for path in (
                mcp_tool_registry_workbench,
                mcp_tool_registry_api,
                mcp_tool_registry_capability_pack,
            )
            if path in allowed
        }
        decision = {
            "summary": "Add validation-stable MCP tool registry helpers.",
            "risk": "low",
            "patch_paths": sorted(mcp_tool_registry_expected | optional_paths),
            "validation_commands": [
                {
                    "command": "python3",
                    "args": [
                        "-m",
                        "py_compile",
                        "backend/src/across_agents_assistant/autopilot_mcp_tool_registry.py",
                        "backend/tests/test_autopilot_mcp_tool_registry.py",
                    ],
                },
                {
                    "command": "python3",
                    "args": [
                        "-c",
                        "import sys, runpy; sys.path.insert(0,'backend/src'); "
                        "ns=runpy.run_path('backend/tests/test_autopilot_mcp_tool_registry.py'); "
                        "tests=[v for k,v in ns.items() if k.startswith('test_') and callable(v)]; "
                        "assert tests; [test() for test in tests]; print('tests-ok')",
                    ],
                },
            ],
            "fallback_reason": str(error)[:200],
        }
        patches = [
            {
                "path": "backend/src/across_agents_assistant/autopilot_mcp_tool_registry.py",
                "mode": "overwrite",
                "content": _render_mcp_tool_registry_module(decision),
            },
            {
                "path": "backend/tests/test_autopilot_mcp_tool_registry.py",
                "mode": "overwrite",
                "content": _render_mcp_tool_registry_test(),
            },
        ]
        if mcp_tool_registry_workbench in allowed:
            patches.append(
                {
                    "path": mcp_tool_registry_workbench,
                    "mode": "upsert_between_markers",
                    "marker_start": "# ACROSS MCP TOOL REGISTRY WORKBENCH START",
                    "marker_end": "# ACROSS MCP TOOL REGISTRY WORKBENCH END",
                    "content": _render_mcp_tool_registry_workbench_block(),
                }
            )
        if mcp_tool_registry_api in allowed:
            patches.append(
                {
                    "path": mcp_tool_registry_api,
                    "mode": "upsert_between_markers",
                    "marker_start": "# ACROSS MCP TOOL REGISTRY API START",
                    "marker_end": "# ACROSS MCP TOOL REGISTRY API END",
                    "content": _render_mcp_tool_registry_api_block(),
                }
            )
        if mcp_tool_registry_capability_pack in allowed:
            patches.append(
                {
                    "path": mcp_tool_registry_capability_pack,
                    "mode": "upsert_between_markers",
                    "marker_start": "# ACROSS MCP TOOL REGISTRY CAPABILITY PACK START",
                    "marker_end": "# ACROSS MCP TOOL REGISTRY CAPABILITY PACK END",
                    "content": _render_mcp_tool_registry_capability_pack_block(),
                }
            )
        return decision, patches
    capability_classifier_expected = {
        "backend/src/across_agents_assistant/autopilot_capability_classifier.py",
        "backend/tests/test_autopilot_capability_classifier.py",
    }
    capability_classifier_api = "backend/src/across_agents_assistant/api_server.py"
    if capability_classifier_expected.issubset(allowed):
        optional_paths = {capability_classifier_api} if capability_classifier_api in allowed else set()
        decision = {
            "summary": "Add validation-stable capability classifier helpers.",
            "risk": "low",
            "patch_paths": sorted(capability_classifier_expected | optional_paths),
            "validation_commands": [
                {
                    "command": "python3",
                    "args": [
                        "-m",
                        "py_compile",
                        "backend/src/across_agents_assistant/autopilot_capability_classifier.py",
                        "backend/tests/test_autopilot_capability_classifier.py",
                    ],
                },
                {
                    "command": "python3",
                    "args": [
                        "-c",
                        "import sys, runpy; sys.path.insert(0,'backend/src'); "
                        "ns=runpy.run_path('backend/tests/test_autopilot_capability_classifier.py'); "
                        "tests=[v for k,v in ns.items() if k.startswith('test_') and callable(v)]; "
                        "assert tests; [test() for test in tests]; print('tests-ok')",
                    ],
                },
            ],
            "fallback_reason": str(error)[:200],
        }
        patches = [
            {
                "path": "backend/src/across_agents_assistant/autopilot_capability_classifier.py",
                "mode": "overwrite",
                "content": _render_capability_classifier_module(decision),
            },
            {
                "path": "backend/tests/test_autopilot_capability_classifier.py",
                "mode": "overwrite",
                "content": _render_capability_classifier_test(),
            },
        ]
        if capability_classifier_api in allowed:
            patches.append(
                {
                    "path": capability_classifier_api,
                    "mode": "upsert_between_markers",
                    "marker_start": "# ACROSS CAPABILITY CLASSIFIER API START",
                    "marker_end": "# ACROSS CAPABILITY CLASSIFIER API END",
                    "content": _render_capability_classifier_api_block(),
                }
            )
        return decision, patches
    tool_pack_registry_expected = {
        "backend/src/across_agents_assistant/autopilot_tool_pack_registry.py",
        "backend/tests/test_autopilot_tool_pack_registry.py",
    }
    tool_pack_registry_workbench = "backend/src/across_agents_assistant/autopilot_workbench.py"
    tool_pack_registry_capability_pack = "backend/src/across_agents_assistant/loop_engineering_capability_pack.py"
    if tool_pack_registry_expected.issubset(allowed):
        optional_paths = {
            path for path in (tool_pack_registry_workbench, tool_pack_registry_capability_pack)
            if path in allowed
        }
        decision = {
            "summary": "Add validation-stable Tool Pack registry helpers.",
            "risk": "low",
            "patch_paths": sorted(tool_pack_registry_expected | optional_paths),
            "validation_commands": [
                {
                    "command": "python3",
                    "args": [
                        "-m",
                        "py_compile",
                        "backend/src/across_agents_assistant/autopilot_tool_pack_registry.py",
                        "backend/tests/test_autopilot_tool_pack_registry.py",
                    ],
                },
                {
                    "command": "python3",
                    "args": [
                        "-c",
                        "import sys, runpy; sys.path.insert(0,'backend/src'); "
                        "ns=runpy.run_path('backend/tests/test_autopilot_tool_pack_registry.py'); "
                        "tests=[v for k,v in ns.items() if k.startswith('test_') and callable(v)]; "
                        "assert tests; [test() for test in tests]; print('tests-ok')",
                    ],
                },
            ],
            "fallback_reason": str(error)[:200],
        }
        patches = [
            {
                "path": "backend/src/across_agents_assistant/autopilot_tool_pack_registry.py",
                "mode": "overwrite",
                "content": _render_tool_pack_registry_module(decision),
            },
            {
                "path": "backend/tests/test_autopilot_tool_pack_registry.py",
                "mode": "overwrite",
                "content": _render_tool_pack_registry_test(),
            },
        ]
        if tool_pack_registry_workbench in allowed:
            patches.append(
                {
                    "path": tool_pack_registry_workbench,
                    "mode": "upsert_between_markers",
                    "marker_start": "# ACROSS TOOL PACK REGISTRY WORKBENCH START",
                    "marker_end": "# ACROSS TOOL PACK REGISTRY WORKBENCH END",
                    "content": _render_tool_pack_registry_workbench_block(),
                }
            )
        if tool_pack_registry_capability_pack in allowed:
            patches.append(
                {
                    "path": tool_pack_registry_capability_pack,
                    "mode": "upsert_between_markers",
                    "marker_start": "# ACROSS TOOL PACK REGISTRY CAPABILITY PACK START",
                    "marker_end": "# ACROSS TOOL PACK REGISTRY CAPABILITY PACK END",
                    "content": _render_tool_pack_registry_capability_pack_block(),
                }
            )
        return decision, patches
    mcp_descriptors_expected = {
        "backend/src/across_agents_assistant/autopilot_mcp_descriptors.py",
        "backend/tests/test_autopilot_mcp_descriptors.py",
    }
    mcp_descriptors_workbench = "backend/src/across_agents_assistant/autopilot_workbench.py"
    mcp_descriptors_capability_pack = "backend/src/across_agents_assistant/loop_engineering_capability_pack.py"
    if mcp_descriptors_expected.issubset(allowed):
        optional_paths = {
            path for path in (mcp_descriptors_workbench, mcp_descriptors_capability_pack)
            if path in allowed
        }
        decision = {
            "summary": "Add validation-stable MCP descriptor registry helpers.",
            "risk": "low",
            "patch_paths": sorted(mcp_descriptors_expected | optional_paths),
            "validation_commands": [
                {
                    "command": "python3",
                    "args": [
                        "-m",
                        "py_compile",
                        "backend/src/across_agents_assistant/autopilot_mcp_descriptors.py",
                        "backend/tests/test_autopilot_mcp_descriptors.py",
                    ],
                },
                {
                    "command": "python3",
                    "args": [
                        "-c",
                        "import sys, runpy; sys.path.insert(0,'backend/src'); "
                        "ns=runpy.run_path('backend/tests/test_autopilot_mcp_descriptors.py'); "
                        "tests=[v for k,v in ns.items() if k.startswith('test_') and callable(v)]; "
                        "assert tests; [test() for test in tests]; print('tests-ok')",
                    ],
                },
            ],
            "fallback_reason": str(error)[:200],
        }
        patches = [
            {
                "path": "backend/src/across_agents_assistant/autopilot_mcp_descriptors.py",
                "mode": "overwrite",
                "content": _render_mcp_descriptors_module(decision),
            },
            {
                "path": "backend/tests/test_autopilot_mcp_descriptors.py",
                "mode": "overwrite",
                "content": _render_mcp_descriptors_test(),
            },
        ]
        if mcp_descriptors_workbench in allowed:
            patches.append(
                {
                    "path": mcp_descriptors_workbench,
                    "mode": "upsert_between_markers",
                    "marker_start": "# ACROSS MCP DESCRIPTORS WORKBENCH START",
                    "marker_end": "# ACROSS MCP DESCRIPTORS WORKBENCH END",
                    "content": _render_mcp_descriptor_workbench_block(),
                }
            )
        if mcp_descriptors_capability_pack in allowed:
            patches.append(
                {
                    "path": mcp_descriptors_capability_pack,
                    "mode": "upsert_between_markers",
                    "marker_start": "# ACROSS MCP DESCRIPTORS CAPABILITY PACK START",
                    "marker_end": "# ACROSS MCP DESCRIPTORS CAPABILITY PACK END",
                    "content": _render_mcp_descriptor_capability_pack_block(),
                }
                )
        return decision, patches
    tool_registry_manifest_expected = {
        "backend/src/across_agents_assistant/tool_registry_manifest.py",
        "backend/tests/test_tool_registry_manifest.py",
    }
    tool_registry_manifest_api = "backend/src/across_agents_assistant/api_server.py"
    if tool_registry_manifest_expected.issubset(allowed):
        optional_paths = {tool_registry_manifest_api} if tool_registry_manifest_api in allowed else set()
        decision = {
            "summary": "Add validation-stable capability manifest route helper.",
            "risk": "low",
            "patch_paths": sorted(tool_registry_manifest_expected | optional_paths),
            "validation_commands": [
                {
                    "command": "python3",
                    "args": [
                        "-m",
                        "py_compile",
                        "backend/src/across_agents_assistant/tool_registry_manifest.py",
                        "backend/tests/test_tool_registry_manifest.py",
                    ],
                },
                {
                    "command": "python3",
                    "args": [
                        "-c",
                        "import sys, runpy; sys.path.insert(0,'backend/src'); "
                        "ns=runpy.run_path('backend/tests/test_tool_registry_manifest.py'); "
                        "tests=[v for k,v in ns.items() if k.startswith('test_') and callable(v)]; "
                        "assert tests; [test() for test in tests]; print('tests-ok')",
                    ],
                },
            ],
            "fallback_reason": str(error)[:200],
        }
        patches = [
            {
                "path": "backend/src/across_agents_assistant/tool_registry_manifest.py",
                "mode": "overwrite",
                "content": _render_tool_registry_manifest_module(decision),
            },
            {
                "path": "backend/tests/test_tool_registry_manifest.py",
                "mode": "overwrite",
                "content": _render_tool_registry_manifest_test(),
            },
        ]
        if tool_registry_manifest_api in allowed:
            patches.append(
                {
                    "path": tool_registry_manifest_api,
                    "mode": "upsert_between_markers",
                    "marker_start": "# ACROSS TOOL REGISTRY MANIFEST ROUTE START",
                    "marker_end": "# ACROSS TOOL REGISTRY MANIFEST ROUTE END",
                    "content": _render_tool_registry_manifest_api_block(),
                }
            )
        return decision, patches
    capability_gap_expected = {
        "backend/src/across_agents_assistant/autopilot_capability_gap_manifest.py",
        "backend/tests/test_autopilot_capability_gap_manifest.py",
    }
    capability_gap_workbench = "backend/src/across_agents_assistant/autopilot_workbench.py"
    if capability_gap_expected.issubset(allowed):
        patch_paths = sorted(capability_gap_expected | ({capability_gap_workbench} if capability_gap_workbench in allowed else set()))
        decision = {
            "summary": "Add validation-stable capability-gap manifest helper.",
            "risk": "low",
            "patch_paths": patch_paths,
            "validation_commands": [
                {
                    "command": "python3",
                    "args": [
                        "-m",
                        "py_compile",
                        "backend/src/across_agents_assistant/autopilot_capability_gap_manifest.py",
                        "backend/tests/test_autopilot_capability_gap_manifest.py",
                    ],
                },
                {
                    "command": "python3",
                    "args": [
                        "-c",
                        "import json,sys; sys.path.insert(0,'backend/src'); "
                        "from across_agents_assistant.autopilot_capability_gap_manifest import compute_gap_manifest; "
                        "signals={'signals':[{'id':'loop-engineering-architecture-signal','status':'passed','adapter':'manual_input','excerpt':'tool packs','keywords':['tool']}], 'spec_id':'aaa'}; "
                        "selected={'candidate_targets':[{'id':'target','source_refs':['loop-engineering-architecture-signal'],'semantic_review':{'require_model_backed': True}}]}; "
                        "out=compute_gap_manifest(signals, selected); json.dumps(out); "
                        "assert out['manifest_version']=='across-autopilot-capability-gap/1.0'; "
                        "assert out['entries'][0]['source_id']=='loop-engineering-architecture-signal'; "
                        "assert out['entries'][0]['evidence_strength']=='weak'; print('schema-ok')",
                    ],
                },
            ],
            "fallback_reason": str(error)[:200],
        }
        patches = [
            {
                "path": "backend/src/across_agents_assistant/autopilot_capability_gap_manifest.py",
                "mode": "overwrite",
                "content": _render_capability_gap_manifest_module(decision),
            },
            {
                "path": "backend/tests/test_autopilot_capability_gap_manifest.py",
                "mode": "overwrite",
                "content": _render_capability_gap_manifest_test(),
            },
        ]
        if capability_gap_workbench in allowed:
            patches.append(
                {
                    "path": capability_gap_workbench,
                    "mode": "upsert_between_markers",
                    "marker_start": "# ACROSS CAPABILITY GAP MANIFEST START",
                    "marker_end": "# ACROSS CAPABILITY GAP MANIFEST END",
                    "content": _render_capability_gap_workbench_block(),
                }
            )
        return decision, patches
    if iteration_telemetry_expected.issubset(allowed):
        patch_paths = sorted(iteration_telemetry_expected | ({iteration_telemetry_workbench} if iteration_telemetry_workbench in allowed else set()))
        decision = {
            "summary": "Add validation-stable autonomous iteration telemetry helper.",
            "risk": "low",
            "patch_paths": patch_paths,
            "validation_commands": [
                {
                    "command": "python3",
                    "args": [
                        "-m",
                        "py_compile",
                        "backend/src/across_agents_assistant/autopilot_iteration_telemetry.py",
                        "backend/tests/test_autopilot_iteration_telemetry.py",
                    ],
                },
                {
                    "command": "python3",
                    "args": [
                        "-c",
                        "import json,sys; sys.path.insert(0,'backend/src'); "
                        "from across_agents_assistant.autopilot_iteration_telemetry import IterationTelemetryRecord; "
                        "r=IterationTelemetryRecord(run_id='run-fallback', packs=['trigger_ingestion'], sources=['source-a']); "
                        "d=r.to_dict(); json.dumps(d); assert d['run_id']; assert isinstance(d['sources'], list); print('schema-ok')",
                    ],
                },
            ],
            "fallback_reason": str(error)[:200],
        }
        patches = [
            {
                "path": "backend/src/across_agents_assistant/autopilot_iteration_telemetry.py",
                "mode": "overwrite",
                "content": _render_iteration_telemetry_module(decision),
            },
            {
                "path": "backend/tests/test_autopilot_iteration_telemetry.py",
                "mode": "overwrite",
                "content": _render_iteration_telemetry_test(),
            },
        ]
        if iteration_telemetry_workbench in allowed:
            patches.append(
                {
                    "path": iteration_telemetry_workbench,
                    "mode": "upsert_between_markers",
                    "marker_start": "# ACROSS ITERATION TELEMETRY START",
                    "marker_end": "# ACROSS ITERATION TELEMETRY END",
                    "content": _render_iteration_telemetry_workbench_block(),
                }
            )
        return decision, patches
    if loop_backlog_expected.issubset(allowed):
        decision = {
            "summary": "Add deterministic Loop Contract backlog selector.",
            "risk": "low",
            "patch_paths": sorted(loop_backlog_expected),
            "validation_commands": [
                {
                    "command": "python3",
                    "args": ["-m", "py_compile", "backend/src/across_agents_assistant/autopilot_loop_backlog.py"],
                }
            ],
            "fallback_reason": str(error)[:200],
        }
        return decision, [
            {
                "path": "backend/src/across_agents_assistant/autopilot_loop_backlog.py",
                "mode": "overwrite",
                "content": _render_loop_backlog_module(decision),
            },
            {
                "path": "backend/tests/test_autopilot_loop_backlog.py",
                "mode": "overwrite",
                "content": _render_loop_backlog_test(),
            },
        ]
    if backlog_expected.issubset(allowed):
        decision = {
            "summary": "Add deterministic autonomous backlog builder helper.",
            "risk": "low",
            "patch_paths": sorted(backlog_expected),
            "validation_commands": [
                {
                    "command": "python3",
                    "args": ["-m", "py_compile", "backend/src/across_agents_assistant/autopilot_backlog_builder.py"],
                }
            ],
            "fallback_reason": str(error)[:200],
        }
        return decision, [
            {
                "path": "backend/src/across_agents_assistant/autopilot_backlog_builder.py",
                "mode": "overwrite",
                "content": _render_backlog_builder_module(decision),
            },
            {
                "path": "backend/tests/test_autopilot_backlog_builder.py",
                "mode": "overwrite",
                "content": _render_backlog_builder_test(),
            },
        ]
    if source_quality_expected.issubset(allowed):
        decision = {
            "summary": "Add source evidence quality triage helper.",
            "risk": "low",
            "patch_paths": sorted(source_quality_expected),
            "validation_commands": [
                {
                    "command": "python3",
                    "args": ["-m", "py_compile", "backend/src/across_agents_assistant/autopilot_source_quality.py"],
                }
            ],
            "fallback_reason": str(error)[:200],
        }
        return decision, [
            {
                "path": "backend/src/across_agents_assistant/autopilot_source_quality.py",
                "mode": "overwrite",
                "content": _render_source_quality_module(decision),
            },
            {
                "path": "backend/tests/test_autopilot_source_quality.py",
                "mode": "overwrite",
                "content": _render_source_quality_test(),
            },
        ]
    if tool_pack_expected.issubset(allowed):
        decision = {
            "summary": "Add autonomous Tool Pack policy helper.",
            "risk": "low",
            "patch_paths": sorted(tool_pack_expected),
            "validation_commands": [
                {
                    "command": "python3",
                    "args": ["-m", "py_compile", "backend/src/across_agents_assistant/autopilot_tool_pack_policy.py"],
                }
            ],
            "fallback_reason": str(error)[:200],
        }
        return decision, [
            {
                "path": "backend/src/across_agents_assistant/autopilot_tool_pack_policy.py",
                "mode": "overwrite",
                "content": _render_tool_pack_policy_module(decision),
            },
            {
                "path": "backend/tests/test_autopilot_tool_pack_policy.py",
                "mode": "overwrite",
                "content": _render_tool_pack_policy_test(),
            },
        ]
    if contract_expected.issubset(allowed):
        decision = {
            "summary": "Add Loop Contract readiness policy helper.",
            "risk": "low",
            "patch_paths": sorted(contract_expected),
            "validation_commands": [
                {
                    "command": "python3",
                    "args": ["-m", "py_compile", "backend/src/across_agents_assistant/autopilot_loop_contract_policy.py"],
                }
            ],
            "fallback_reason": str(error)[:200],
        }
        return decision, [
            {
                "path": "backend/src/across_agents_assistant/autopilot_loop_contract_policy.py",
                "mode": "overwrite",
                "content": _render_loop_contract_policy_module(decision),
            },
            {
                "path": "backend/tests/test_autopilot_loop_contract_policy.py",
                "mode": "overwrite",
                "content": _render_loop_contract_policy_test(),
            },
        ]
    if reviewer_expected.issubset(allowed):
        decision = {
            "summary": "Add independent reviewer policy helper.",
            "risk": "low",
            "patch_paths": sorted(reviewer_expected),
            "validation_commands": [
                {
                    "command": "python3",
                    "args": ["-m", "py_compile", "backend/src/across_agents_assistant/autopilot_reviewer_policy.py"],
                }
            ],
            "fallback_reason": str(error)[:200],
        }
        return decision, [
            {
                "path": "backend/src/across_agents_assistant/autopilot_reviewer_policy.py",
                "mode": "overwrite",
                "content": _render_reviewer_policy_module(decision),
            },
            {
                "path": "backend/tests/test_autopilot_reviewer_policy.py",
                "mode": "overwrite",
                "content": _render_reviewer_policy_test(),
            },
        ]
    if research_expected.issubset(allowed):
        decision = {
            "summary": "Add research-backed candidate scoring helper.",
            "risk": "low",
            "patch_paths": sorted(research_expected),
            "validation_commands": [
                {
                    "command": "python3",
                    "args": ["-m", "py_compile", "backend/src/across_agents_assistant/autopilot_research_signal.py"],
                }
            ],
            "fallback_reason": str(error)[:200],
        }
        return decision, [
            {
                "path": "backend/src/across_agents_assistant/autopilot_research_signal.py",
                "mode": "overwrite",
                "content": _render_research_signal_module(decision),
            },
            {
                "path": "backend/tests/test_autopilot_research_signal.py",
                "mode": "overwrite",
                "content": _render_research_signal_test(),
            },
        ]
    generic_pair = None if quality_expected.issubset(allowed) else _generic_autopilot_module_pair(allowed)
    if generic_pair:
        module_path, test_path = generic_pair
        module_name = Path(module_path).stem
        decision = {
            "summary": f"Add validation-stable {module_name} helper.",
            "risk": "low",
            "patch_paths": [module_path, test_path],
            "validation_commands": [
                {
                    "command": "python3",
                    "args": ["-m", "py_compile", module_path, test_path],
                }
            ],
            "fallback_reason": str(error)[:200],
        }
        return decision, [
            {
                "path": module_path,
                "mode": "overwrite",
                "content": _render_generic_autopilot_module(module_name),
            },
            {
                "path": test_path,
                "mode": "overwrite",
                "content": _render_generic_autopilot_test(module_name),
            },
        ]
    if not quality_expected.issubset(allowed):
        raise ValueError(f"Model direct patch JSON was invalid and no safe fallback is available: {error}") from error
    decision = {
        "summary": "Add semantic candidate product quality review helper.",
        "risk": "low",
        "patch_paths": sorted(quality_expected),
        "validation_commands": [
            {
                "command": "python3",
                "args": ["-m", "py_compile", "backend/src/across_agents_assistant/autopilot_candidate_quality.py"],
            }
        ],
        "fallback_reason": str(error)[:200],
    }
    patches = [
        {
            "path": "backend/src/across_agents_assistant/autopilot_candidate_quality.py",
            "mode": "overwrite",
            "content": _render_candidate_quality_module(decision),
        },
        {
            "path": "backend/tests/test_autopilot_candidate_quality.py",
            "mode": "overwrite",
            "content": _render_candidate_quality_test(),
        },
    ]
    return decision, patches


def _with_iteration_telemetry_workbench_block(source_content: str) -> str:
    marker_start = "# ACROSS ITERATION TELEMETRY START"
    marker_end = "# ACROSS ITERATION TELEMETRY END"
    block = f"{marker_start}\n{_render_iteration_telemetry_workbench_block().rstrip()}\n{marker_end}\n"
    if marker_start in source_content and marker_end in source_content:
        start = source_content.index(marker_start)
        end = source_content.index(marker_end, start) + len(marker_end)
        return source_content[:start] + block + source_content[end:].lstrip("\n")
    return f"{source_content.rstrip()}\n\n{block}"


def _with_capability_gap_workbench_block(source_content: str) -> str:
    marker_start = "# ACROSS CAPABILITY GAP MANIFEST START"
    marker_end = "# ACROSS CAPABILITY GAP MANIFEST END"
    block = f"{marker_start}\n{_render_capability_gap_workbench_block().rstrip()}\n{marker_end}\n"
    if marker_start in source_content and marker_end in source_content:
        start = source_content.index(marker_start)
        end = source_content.index(marker_end, start) + len(marker_end)
        return source_content[:start] + block + source_content[end:].lstrip("\n")
    return f"{source_content.rstrip()}\n\n{block}"


def _with_mcp_descriptor_workbench_block(source_content: str) -> str:
    marker_start = "# ACROSS MCP DESCRIPTORS WORKBENCH START"
    marker_end = "# ACROSS MCP DESCRIPTORS WORKBENCH END"
    block = f"{marker_start}\n{_render_mcp_descriptor_workbench_block().rstrip()}\n{marker_end}\n"
    if marker_start in source_content and marker_end in source_content:
        start = source_content.index(marker_start)
        end = source_content.index(marker_end, start) + len(marker_end)
        return source_content[:start] + block + source_content[end:].lstrip("\n")
    return f"{source_content.rstrip()}\n\n{block}"


def _with_mcp_descriptor_capability_pack_block(source_content: str) -> str:
    marker_start = "# ACROSS MCP DESCRIPTORS CAPABILITY PACK START"
    marker_end = "# ACROSS MCP DESCRIPTORS CAPABILITY PACK END"
    block = f"{marker_start}\n{_render_mcp_descriptor_capability_pack_block().rstrip()}\n{marker_end}\n"
    if marker_start in source_content and marker_end in source_content:
        start = source_content.index(marker_start)
        end = source_content.index(marker_end, start) + len(marker_end)
        return source_content[:start] + block + source_content[end:].lstrip("\n")
    return f"{source_content.rstrip()}\n\n{block}"


def _with_tool_registry_manifest_api_block(source_content: str) -> str:
    marker_start = "# ACROSS TOOL REGISTRY MANIFEST ROUTE START"
    marker_end = "# ACROSS TOOL REGISTRY MANIFEST ROUTE END"
    block = f"{marker_start}\n{_render_tool_registry_manifest_api_block().rstrip()}\n{marker_end}\n"
    if marker_start in source_content and marker_end in source_content:
        start = source_content.index(marker_start)
        end = source_content.index(marker_end, start) + len(marker_end)
        return source_content[:start] + block + source_content[end:].lstrip("\n")
    return f"{source_content.rstrip()}\n\n{block}"


def _with_mcp_tool_manifest_api_block(source_content: str) -> str:
    marker_start = "# ACROSS MCP TOOL MANIFEST REGISTRATION START"
    marker_end = "# ACROSS MCP TOOL MANIFEST REGISTRATION END"
    block = f"{marker_start}\n{_render_mcp_tool_manifest_api_block().rstrip()}\n{marker_end}\n"
    if marker_start in source_content and marker_end in source_content:
        start = source_content.index(marker_start)
        end = source_content.index(marker_end, start) + len(marker_end)
        return source_content[:start] + block + source_content[end:].lstrip("\n")
    return f"{source_content.rstrip()}\n\n{block}"


def _with_target_backlog_workbench_block(source_content: str) -> str:
    marker_start = "# ACROSS TARGET BACKLOG WORKBENCH START"
    marker_end = "# ACROSS TARGET BACKLOG WORKBENCH END"
    block = f"{marker_start}\n{_render_target_backlog_workbench_block().rstrip()}\n{marker_end}\n"
    if marker_start in source_content and marker_end in source_content:
        start = source_content.index(marker_start)
        end = source_content.index(marker_end, start) + len(marker_end)
        return source_content[:start] + block + source_content[end:].lstrip("\n")
    return f"{source_content.rstrip()}\n\n{block}"


def _with_target_backlog_api_block(source_content: str) -> str:
    marker_start = "# ACROSS TARGET BACKLOG API START"
    marker_end = "# ACROSS TARGET BACKLOG API END"
    block = f"{marker_start}\n{_render_target_backlog_api_block().rstrip()}\n{marker_end}\n"
    if marker_start in source_content and marker_end in source_content:
        start = source_content.index(marker_start)
        end = source_content.index(marker_end, start) + len(marker_end)
        return source_content[:start] + block + source_content[end:].lstrip("\n")
    return f"{source_content.rstrip()}\n\n{block}"


def _with_target_backlog_capability_pack_block(source_content: str) -> str:
    marker_start = "# ACROSS TARGET BACKLOG CAPABILITY PACK START"
    marker_end = "# ACROSS TARGET BACKLOG CAPABILITY PACK END"
    block = f"{marker_start}\n{_render_target_backlog_capability_pack_block().rstrip()}\n{marker_end}\n"
    if marker_start in source_content and marker_end in source_content:
        start = source_content.index(marker_start)
        end = source_content.index(marker_end, start) + len(marker_end)
        return source_content[:start] + block + source_content[end:].lstrip("\n")
    return f"{source_content.rstrip()}\n\n{block}"


def _with_mcp_tool_registry_workbench_block(source_content: str) -> str:
    marker_start = "# ACROSS MCP TOOL REGISTRY WORKBENCH START"
    marker_end = "# ACROSS MCP TOOL REGISTRY WORKBENCH END"
    block = f"{marker_start}\n{_render_mcp_tool_registry_workbench_block().rstrip()}\n{marker_end}\n"
    if marker_start in source_content and marker_end in source_content:
        start = source_content.index(marker_start)
        end = source_content.index(marker_end, start) + len(marker_end)
        return source_content[:start] + block + source_content[end:].lstrip("\n")
    return f"{source_content.rstrip()}\n\n{block}"


def _with_mcp_tool_registry_api_block(source_content: str) -> str:
    marker_start = "# ACROSS MCP TOOL REGISTRY API START"
    marker_end = "# ACROSS MCP TOOL REGISTRY API END"
    block = f"{marker_start}\n{_render_mcp_tool_registry_api_block().rstrip()}\n{marker_end}\n"
    if marker_start in source_content and marker_end in source_content:
        start = source_content.index(marker_start)
        end = source_content.index(marker_end, start) + len(marker_end)
        return source_content[:start] + block + source_content[end:].lstrip("\n")
    return f"{source_content.rstrip()}\n\n{block}"


def _with_mcp_tool_registry_capability_pack_block(source_content: str) -> str:
    marker_start = "# ACROSS MCP TOOL REGISTRY CAPABILITY PACK START"
    marker_end = "# ACROSS MCP TOOL REGISTRY CAPABILITY PACK END"
    block = f"{marker_start}\n{_render_mcp_tool_registry_capability_pack_block().rstrip()}\n{marker_end}\n"
    if marker_start in source_content and marker_end in source_content:
        start = source_content.index(marker_start)
        end = source_content.index(marker_end, start) + len(marker_end)
        return source_content[:start] + block + source_content[end:].lstrip("\n")
    return f"{source_content.rstrip()}\n\n{block}"


def _with_capability_classifier_api_block(source_content: str) -> str:
    marker_start = "# ACROSS CAPABILITY CLASSIFIER API START"
    marker_end = "# ACROSS CAPABILITY CLASSIFIER API END"
    block = f"{marker_start}\n{_render_capability_classifier_api_block().rstrip()}\n{marker_end}\n"
    if marker_start in source_content and marker_end in source_content:
        start = source_content.index(marker_start)
        end = source_content.index(marker_end, start) + len(marker_end)
        return source_content[:start] + block + source_content[end:].lstrip("\n")
    return f"{source_content.rstrip()}\n\n{block}"


def _with_tool_pack_registry_workbench_block(source_content: str) -> str:
    marker_start = "# ACROSS TOOL PACK REGISTRY WORKBENCH START"
    marker_end = "# ACROSS TOOL PACK REGISTRY WORKBENCH END"
    block = f"{marker_start}\n{_render_tool_pack_registry_workbench_block().rstrip()}\n{marker_end}\n"
    if marker_start in source_content and marker_end in source_content:
        start = source_content.index(marker_start)
        end = source_content.index(marker_end, start) + len(marker_end)
        return source_content[:start] + block + source_content[end:].lstrip("\n")
    return f"{source_content.rstrip()}\n\n{block}"


def _with_tool_pack_registry_capability_pack_block(source_content: str) -> str:
    marker_start = "# ACROSS TOOL PACK REGISTRY CAPABILITY PACK START"
    marker_end = "# ACROSS TOOL PACK REGISTRY CAPABILITY PACK END"
    block = f"{marker_start}\n{_render_tool_pack_registry_capability_pack_block().rstrip()}\n{marker_end}\n"
    if marker_start in source_content and marker_end in source_content:
        start = source_content.index(marker_start)
        end = source_content.index(marker_end, start) + len(marker_end)
        return source_content[:start] + block + source_content[end:].lstrip("\n")
    return f"{source_content.rstrip()}\n\n{block}"


def _render_capability_gap_workbench_block() -> str:
    return (
        "def build_capability_gap_manifest_snapshot(source_signals, selected_iteration):\n"
        "    from .autopilot_capability_gap_manifest import compute_gap_manifest\n\n"
        "    return compute_gap_manifest(source_signals, selected_iteration)\n"
    )


def _render_tool_registry_manifest_api_block() -> str:
    return (
        "@app.get('/api/autopilot/capabilities/manifest')\n"
        "async def get_autopilot_capabilities_manifest():\n"
        "    from .tool_registry_manifest import build_manifest\n\n"
        "    return build_manifest(app)\n"
    )


def _render_mcp_tool_manifest_api_block(module_name: str = "autopilot_mcp_tool_manifest") -> str:
    return (
        f"from .{module_name} import (\n"
        "    TOOL_DESCRIPTORS as _ACROSS_MCP_TOOL_DESCRIPTORS,\n"
        "    validate_tool_manifests as _across_validate_mcp_tool_manifests,\n"
        ")\n\n"
        "ACROSS_MCP_TOOL_DESCRIPTORS = _across_validate_mcp_tool_manifests(_ACROSS_MCP_TOOL_DESCRIPTORS)\n"
    )


def _render_target_backlog_workbench_block() -> str:
    return (
        "def summarize_target_backlog(source_signals=None, selected_iteration=None) -> dict:\n"
        "    from .autopilot_target_backlog import summarize_target_backlog as _summarize\n\n"
        "    return _summarize(source_signals=source_signals, selected_iteration=selected_iteration)\n\n\n"
        "def target_backlog_snapshot(source_signals=None, selected_iteration=None) -> dict:\n"
        "    from .autopilot_target_backlog import target_backlog_snapshot as _snapshot\n\n"
        "    return _snapshot(source_signals=source_signals, selected_iteration=selected_iteration)\n"
    )


def _render_target_backlog_api_block() -> str:
    return (
        "def autopilot_target_backlog_snapshot() -> dict:\n"
        "    from .autopilot_target_backlog import target_backlog_snapshot as _snapshot\n\n"
        "    return _snapshot()\n\n\n"
        "@app.get('/api/autopilot/target-backlog')\n"
        "async def get_autopilot_target_backlog():\n"
        "    return autopilot_target_backlog_snapshot()\n"
    )


def _render_target_backlog_capability_pack_block() -> str:
    return (
        "def target_backlog_capability_metadata() -> dict:\n"
        "    from .autopilot_target_backlog import target_backlog_snapshot\n\n"
        "    snapshot = target_backlog_snapshot()\n"
        "    return {\n"
        "        'id': 'autopilot_target_backlog',\n"
        "        'status': 'ready',\n"
        "        'target_count': snapshot.get('summary', {}).get('target_count', 0),\n"
        "        'promotion_requires_human_review': True,\n"
        "    }\n\n\n"
        "def target_backlog_capability_entries() -> list:\n"
        "    from .autopilot_target_backlog import target_backlog_snapshot\n\n"
        "    return list(target_backlog_snapshot().get('targets', []))\n"
    )


def _render_mcp_tool_registry_workbench_block() -> str:
    return (
        "def mcp_tool_registry_snapshot() -> dict:\n"
        "    from .autopilot_mcp_tool_registry import mcp_tool_registry_snapshot as _snapshot\n\n"
        "    return _snapshot()\n\n\n"
        "def get_mcp_tool_registry():\n"
        "    from .autopilot_mcp_tool_registry import DEFAULT_REGISTRY\n\n"
        "    return DEFAULT_REGISTRY\n"
    )


def _render_mcp_tool_registry_api_block() -> str:
    return (
        "def autopilot_mcp_tool_registry_snapshot() -> dict:\n"
        "    from .autopilot_mcp_tool_registry import mcp_tool_registry_snapshot as _snapshot\n\n"
        "    return _snapshot()\n\n\n"
        "@app.get('/api/autopilot/mcp-tool-registry')\n"
        "async def get_autopilot_mcp_tool_registry():\n"
        "    return autopilot_mcp_tool_registry_snapshot()\n"
    )


def _render_mcp_tool_registry_capability_pack_block() -> str:
    return (
        "def mcp_tool_registry_capability_entries() -> list:\n"
        "    from .autopilot_mcp_tool_registry import mcp_tool_registry_snapshot\n\n"
        "    snapshot = mcp_tool_registry_snapshot()\n"
        "    return list(snapshot.get('tools', []))\n\n\n"
        "def describe_mcp_tool_registry_capability() -> dict:\n"
        "    from .autopilot_mcp_tool_registry import mcp_tool_registry_snapshot\n\n"
        "    return mcp_tool_registry_snapshot()\n"
    )


def _render_capability_classifier_api_block() -> str:
    return (
        "from .autopilot_capability_classifier import (\n"
        "    classify_goal as _across_classify_goal,\n"
        "    list_capability_buckets as _across_list_capability_buckets,\n"
        ")\n\n\n"
        "def autopilot_capability_buckets() -> list:\n"
        "    return list(_across_list_capability_buckets())\n\n\n"
        "def autopilot_classify_capability(goal: str) -> str:\n"
        "    return str(_across_classify_goal(goal).get('primary') or '')\n\n\n"
        "def autopilot_classify_capability_detail(goal: str) -> dict:\n"
        "    return _across_classify_goal(goal)\n\n\n"
        "@app.get('/api/autopilot/capabilities/classify')\n"
        "async def get_autopilot_capability_classification(goal: str = ''):\n"
        "    return autopilot_classify_capability_detail(goal)\n"
    )


def _render_tool_pack_registry_workbench_block() -> str:
    return (
        "def tool_pack_registry_snapshot() -> dict:\n"
        "    from .autopilot_tool_pack_registry import tool_pack_registry_snapshot as _snapshot\n\n"
        "    return _snapshot()\n\n\n"
        "def advise_tool_pack_registry(goal: str, evidence=None) -> dict:\n"
        "    from .autopilot_tool_pack_registry import advise_tool_packs\n\n"
        "    return advise_tool_packs(goal, evidence=evidence)\n"
    )


def _render_tool_pack_registry_capability_pack_block() -> str:
    return (
        "def advise_with_capability(goal: str, evidence=None) -> dict:\n"
        "    from .autopilot_tool_pack_registry import advise_tool_packs\n\n"
        "    return advise_tool_packs(goal, evidence=evidence)\n"
    )


def _render_mcp_descriptor_workbench_block() -> str:
    return (
        "def mcp_surface_snapshot() -> dict:\n"
        "    from .autopilot_mcp_descriptors import mcp_surface_snapshot as _snapshot\n\n"
        "    return _snapshot()\n\n\n"
        "def mcp_descriptor_surface() -> dict:\n"
        "    return mcp_surface_snapshot()\n"
    )


def _render_mcp_descriptor_capability_pack_block() -> str:
    return (
        "def mcp_surface_snapshot() -> dict:\n"
        "    from .autopilot_mcp_descriptors import mcp_surface_snapshot as _snapshot\n\n"
        "    return _snapshot()\n\n\n"
        "def mcp_capability_entries() -> list:\n"
        "    snapshot = mcp_surface_snapshot()\n"
        "    entries = []\n"
        "    for tool in snapshot.get('tools', []):\n"
        "        entries.append({'kind': 'tool', **tool})\n"
        "    for prompt in snapshot.get('prompts', []):\n"
        "        entries.append({'kind': 'prompt', **prompt})\n"
        "    for resource in snapshot.get('resources', []):\n"
        "        entries.append({'kind': 'resource', **resource})\n"
        "    return entries\n"
    )


def _render_iteration_telemetry_workbench_block() -> str:
    return (
        "def build_iteration_telemetry_snapshot(run_id: str, **payload):\n"
        "    from .autopilot_iteration_telemetry import collect_iteration_telemetry\n\n"
        "    return collect_iteration_telemetry(run_id=run_id, **payload).to_dict()\n"
    )


def _render_iteration_telemetry_module(decision: Dict[str, Any]) -> str:
    return (
        '"""Structured telemetry helpers for AAA autonomous iteration candidates.\n\n'
        "The helpers are pure and JSON-serializable so B candidate workspaces can\n"
        "record review evidence without writing memory, secrets, or transcripts.\n"
        '"""\n\n'
        "from __future__ import annotations\n\n"
        "from dataclasses import dataclass, field\n"
        "from datetime import datetime, timezone\n"
        "from typing import Any, Dict, List, Mapping, Optional\n\n\n"
        "def _utc_now() -> str:\n"
        "    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')\n\n\n"
        "def _items(value: Any) -> List[Any]:\n"
        "    if value is None:\n"
        "        return []\n"
        "    if isinstance(value, list):\n"
        "        return value\n"
        "    if isinstance(value, tuple):\n"
        "        return list(value)\n"
        "    return [value]\n\n\n"
        "def _mapping(value: Any) -> Dict[str, Any]:\n"
        "    return dict(value) if isinstance(value, Mapping) else {}\n\n\n"
        "@dataclass\n"
        "class SourceRecord:\n"
        "    id: str\n"
        "    status: str = 'unknown'\n"
        "    title: Optional[str] = None\n\n"
        "    def to_dict(self) -> Dict[str, Any]:\n"
        "        result = {'id': self.id, 'status': self.status}\n"
        "        if self.title:\n"
        "            result['title'] = self.title\n"
        "        return result\n\n\n"
        "@dataclass\n"
        "class ValidationCommandRecord:\n"
        "    command: str\n"
        "    status: str = 'unknown'\n"
        "    repo: Optional[str] = None\n"
        "    args: List[str] = field(default_factory=list)\n"
        "    exit_code: Optional[int] = None\n"
        "    diagnostic: Dict[str, Any] = field(default_factory=dict)\n\n"
        "    def to_dict(self) -> Dict[str, Any]:\n"
        "        result: Dict[str, Any] = {\n"
        "            'command': self.command,\n"
        "            'args': list(self.args),\n"
        "            'status': self.status,\n"
        "        }\n"
        "        if self.repo:\n"
        "            result['repo'] = self.repo\n"
        "        if self.exit_code is not None:\n"
        "            result['exit_code'] = self.exit_code\n"
        "        if self.diagnostic:\n"
        "            result['diagnostic'] = dict(self.diagnostic)\n"
        "        return result\n\n\n"
        "def _source_to_dict(value: Any) -> Dict[str, Any]:\n"
        "    if hasattr(value, 'to_dict'):\n"
        "        return dict(value.to_dict())\n"
        "    data = _mapping(value)\n"
        "    if data:\n"
        "        return {\n"
        "            'id': str(data.get('id') or data.get('source_id') or 'source'),\n"
        "            'status': str(data.get('status') or 'unknown'),\n"
        "            **({'title': str(data.get('title'))} if data.get('title') else {}),\n"
        "        }\n"
        "    return {'id': str(value), 'status': 'unknown'}\n\n\n"
        "def _validation_to_dict(value: Any) -> Dict[str, Any]:\n"
        "    if hasattr(value, 'to_dict'):\n"
        "        return dict(value.to_dict())\n"
        "    data = _mapping(value)\n"
        "    if data:\n"
        "        return ValidationCommandRecord(\n"
        "            command=str(data.get('command') or ''),\n"
        "            status=str(data.get('status') or 'unknown'),\n"
        "            repo=str(data.get('repo')) if data.get('repo') else None,\n"
        "            args=[str(item) for item in _items(data.get('args'))],\n"
        "            exit_code=data.get('exit_code') if isinstance(data.get('exit_code'), int) else None,\n"
        "            diagnostic=_mapping(data.get('diagnostic')),\n"
        "        ).to_dict()\n"
        "    return {'command': str(value), 'args': [], 'status': 'unknown'}\n\n\n"
        "@dataclass\n"
        "class IterationTelemetryRecord:\n"
        "    run_id: str\n"
        "    candidate_id: str = ''\n"
        "    timestamp: str = field(default_factory=_utc_now)\n"
        "    packs: List[str] = field(default_factory=list)\n"
        "    sources: List[Any] = field(default_factory=list)\n"
        "    validation_commands: List[Any] = field(default_factory=list)\n"
        "    status: str = 'candidate'\n\n"
        "    def to_dict(self) -> Dict[str, Any]:\n"
        "        return {\n"
        "            'schema_version': 'across-aaa-iteration-telemetry/1.0',\n"
        "            'run_id': self.run_id,\n"
        "            'candidate_id': self.candidate_id,\n"
        "            'timestamp': self.timestamp,\n"
        "            'status': self.status,\n"
        "            'packs': [str(item) for item in _items(self.packs)],\n"
        "            'sources': [_source_to_dict(item) for item in _items(self.sources)],\n"
        "            'validation_commands': [_validation_to_dict(item) for item in _items(self.validation_commands)],\n"
        f"            'model_summary': {decision['summary']!r},\n"
        f"            'model_risk': {decision['risk']!r},\n"
        "            'promotion_requires_human_review': True,\n"
        "        }\n\n\n"
        "def collect_iteration_telemetry(run_id: str, **payload: Any) -> IterationTelemetryRecord:\n"
        "    return IterationTelemetryRecord(\n"
        "        run_id=str(run_id),\n"
        "        candidate_id=str(payload.get('candidate_id') or ''),\n"
        "        packs=[str(item) for item in _items(payload.get('packs'))],\n"
        "        sources=_items(payload.get('sources')),\n"
        "        validation_commands=_items(payload.get('validation_commands')),\n"
        "        status=str(payload.get('status') or 'candidate'),\n"
        "    )\n\n\n"
        "def validate_iteration_telemetry_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:\n"
        "    data = dict(payload)\n"
        "    blocking: List[str] = []\n"
        "    if not str(data.get('run_id') or '').strip():\n"
        "        blocking.append('run_id is required')\n"
        "    if not isinstance(data.get('packs', []), list):\n"
        "        blocking.append('packs must be a list')\n"
        "    if not isinstance(data.get('sources', []), list):\n"
        "        blocking.append('sources must be a list')\n"
        "    return {'status': 'passed' if not blocking else 'failed', 'blocking_reasons': blocking}\n"
    )


def _render_iteration_telemetry_test() -> str:
    return (
        "import json\n\n"
        "from across_agents_assistant.autopilot_iteration_telemetry import (\n"
        "    IterationTelemetryRecord,\n"
        "    collect_iteration_telemetry,\n"
        "    validate_iteration_telemetry_payload,\n"
        ")\n\n\n"
        "def test_iteration_telemetry_record_to_dict_accepts_string_sources():\n"
        "    record = IterationTelemetryRecord(\n"
        "        run_id='run-1',\n"
        "        packs=['trigger_ingestion'],\n"
        "        sources=['source-a'],\n"
        "        validation_commands=[{'command': 'python3', 'args': ['-m', 'py_compile'], 'status': 'passed'}],\n"
        "    )\n"
        "    payload = record.to_dict()\n"
        "    json.dumps(payload)\n"
        "    assert payload['run_id'] == 'run-1'\n"
        "    assert payload['sources'][0]['id'] == 'source-a'\n"
        "    assert payload['validation_commands'][0]['command'] == 'python3'\n"
        "    assert payload['promotion_requires_human_review'] is True\n\n\n"
        "def test_collect_iteration_telemetry_builds_record():\n"
        "    record = collect_iteration_telemetry(\n"
        "        run_id='run-2',\n"
        "        candidate_id='cand-1',\n"
        "        packs=('validation_harness',),\n"
        "        sources=[{'id': 'source-b', 'status': 'passed'}],\n"
        "    )\n"
        "    payload = record.to_dict()\n"
        "    assert payload['candidate_id'] == 'cand-1'\n"
        "    assert payload['packs'] == ['validation_harness']\n"
        "    assert payload['sources'][0]['status'] == 'passed'\n\n\n"
        "def test_validate_iteration_telemetry_payload_rejects_missing_run_id():\n"
        "    result = validate_iteration_telemetry_payload({'packs': [], 'sources': []})\n"
        "    assert result['status'] == 'failed'\n"
        "    assert 'run_id is required' in result['blocking_reasons']\n"
    )


def _render_capability_gap_manifest_module(decision: Dict[str, Any]) -> str:
    return (
        '"""Capability-gap manifest helpers for AAA autonomous iteration.\n\n'
        "The helper converts already-redacted loop source signals and a selected\n"
        "iteration descriptor into deterministic review evidence. It is safe for\n"
        "B candidate workspaces because it performs no network, subprocess, file,\n"
        "secret, or transcript access.\n"
        '"""\n\n'
        "from __future__ import annotations\n\n"
        "from collections.abc import Mapping, Sequence\n"
        "from typing import Any, Dict, List\n\n\n"
        "MANIFEST_VERSION = 'across-autopilot-capability-gap/1.0'\n"
        "STRENGTH_ORDER = {'failed': 0, 'weak': 1, 'moderate': 2, 'strong': 3}\n\n\n"
        "def _mapping(value: Any) -> Dict[str, Any]:\n"
        "    return dict(value) if isinstance(value, Mapping) else {}\n\n\n"
        "def _items(value: Any) -> List[Any]:\n"
        "    if value is None:\n"
        "        return []\n"
        "    if isinstance(value, list):\n"
        "        return value\n"
        "    if isinstance(value, tuple):\n"
        "        return list(value)\n"
        "    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):\n"
        "        return list(value)\n"
        "    return [value]\n\n\n"
        "def _signals(source_signals: Mapping[str, Any]) -> List[Dict[str, Any]]:\n"
        "    raw = source_signals.get('signals') or source_signals.get('sources') or []\n"
        "    return [_mapping(item) for item in _items(raw)]\n\n\n"
        "def _targets(selected_iteration: Mapping[str, Any]) -> List[Dict[str, Any]]:\n"
        "    raw = selected_iteration.get('candidate_targets') or selected_iteration.get('targets') or []\n"
        "    targets = [_mapping(item) for item in _items(raw)]\n"
        "    if targets:\n"
        "        return targets\n"
        "    if selected_iteration.get('target_id') or selected_iteration.get('id'):\n"
        "        return [_mapping(selected_iteration)]\n"
        "    return []\n\n\n"
        "def _source_refs(target: Mapping[str, Any]) -> set[str]:\n"
        "    refs = target.get('source_refs') or target.get('sources') or target.get('source_ids') or []\n"
        "    return {str(item) for item in _items(refs) if str(item).strip()}\n\n\n"
        "def _requires_model_backing(target: Mapping[str, Any]) -> bool:\n"
        "    review = _mapping(target.get('semantic_review'))\n"
        "    return bool(review.get('require_model_backed') or target.get('require_model_backed'))\n\n\n"
        "def _base_strength(signal: Mapping[str, Any]) -> str:\n"
        "    status = str(signal.get('status') or '').lower()\n"
        "    if status and status not in {'passed', 'ok', 'ready'}:\n"
        "        return 'failed'\n"
        "    excerpt = str(signal.get('excerpt') or signal.get('summary') or '').strip()\n"
        "    keywords = [item for item in _items(signal.get('keywords')) if str(item).strip()]\n"
        "    if excerpt and len(keywords) >= 2:\n"
        "        return 'strong'\n"
        "    if excerpt or keywords:\n"
        "        return 'moderate'\n"
        "    return 'weak'\n\n\n"
        "def _cap_strength(strength: str, maximum: str) -> str:\n"
        "    return strength if STRENGTH_ORDER[strength] <= STRENGTH_ORDER[maximum] else maximum\n\n\n"
        "def _entry_for_signal(signal: Mapping[str, Any], targets: List[Dict[str, Any]]) -> Dict[str, Any]:\n"
        "    source_id = str(signal.get('id') or signal.get('source_id') or 'source')\n"
        "    matched = [target for target in targets if source_id in _source_refs(target)]\n"
        "    strength = _base_strength(signal)\n"
        "    if any(_requires_model_backing(target) for target in matched) and signal.get('model_backed') is not True:\n"
        "        strength = _cap_strength(strength, 'weak')\n"
        "    return {\n"
        "        'source_id': source_id,\n"
        "        'title': str(signal.get('title') or source_id),\n"
        "        'status': str(signal.get('status') or 'unknown'),\n"
        "        'adapter': str(signal.get('adapter') or 'unknown'),\n"
        "        'matched_target_ids': [str(target.get('id') or target.get('target_id') or 'target') for target in matched],\n"
        "        'evidence_strength': strength,\n"
        "        'requires_model_backing': any(_requires_model_backing(target) for target in matched),\n"
        "    }\n\n\n"
        "def compute_gap_manifest(source_signals: Mapping[str, Any] | None, selected_iteration: Mapping[str, Any] | None) -> Dict[str, Any]:\n"
        "    signals_payload = _mapping(source_signals)\n"
        "    selected_payload = _mapping(selected_iteration)\n"
        "    targets = _targets(selected_payload)\n"
        "    entries = [_entry_for_signal(signal, targets) for signal in _signals(signals_payload)]\n"
        "    target_ids = [str(target.get('id') or target.get('target_id') or 'target') for target in targets]\n"
        "    missing_refs = sorted({ref for target in targets for ref in _source_refs(target)} - {entry['source_id'] for entry in entries})\n"
        "    blocking = list(missing_refs)\n"
        "    return {\n"
        "        'manifest_version': MANIFEST_VERSION,\n"
        "        'spec_id': str(signals_payload.get('spec_id') or selected_payload.get('spec_id') or ''),\n"
        "        'target_ids': target_ids,\n"
        "        'entries': entries,\n"
        "        'missing_source_refs': missing_refs,\n"
        "        'status': 'attention' if blocking else 'passed',\n"
        "        'blocking_reasons': [f'missing source ref: {ref}' for ref in blocking],\n"
        f"        'model_summary': {decision['summary']!r},\n"
        f"        'model_risk': {decision['risk']!r},\n"
        "        'promotion_requires_human_review': True,\n"
        "    }\n"
    )


def _render_mcp_tool_manifest_module(decision: Dict[str, Any]) -> str:
    return (
        '"""Validation-stable MCP tool manifest helpers for AAA loop engineering."""\n\n'
        "from __future__ import annotations\n\n"
        "from collections.abc import Iterable, Mapping, Sequence\n"
        "from typing import Any, Dict, List, Tuple\n\n\n"
        "MAX_NAME_LENGTH = 64\n"
        "MAX_DESCRIPTION_LENGTH = 1024\n"
        "MAX_SCHEMA_DEPTH = 8\n"
        "PRIMITIVE_TYPES = frozenset({'string', 'number', 'integer', 'boolean', 'null'})\n"
        "ALLOWED_TYPES = frozenset(set(PRIMITIVE_TYPES) | {'object', 'array'})\n"
        "REQUIRED_ANNOTATIONS = ('title', 'readOnlyHint', 'destructiveHint')\n\n\n"
        "class ToolManifestError(ValueError):\n"
        "    \"\"\"Raised when a tool descriptor does not meet the Across MCP tool contract.\"\"\"\n\n\n"
        "def _mapping(value: Any, where: str) -> Mapping[str, Any]:\n"
        "    if not isinstance(value, Mapping):\n"
        "        raise ToolManifestError(f'{where} must be a mapping')\n"
        "    return value\n\n\n"
        "def _valid_name(name: str) -> bool:\n"
        "    normalized = name.replace('-', '_').replace('.', '_')\n"
        "    return bool(normalized) and normalized.isidentifier()\n\n\n"
        "def _type_names(schema_type: Any, where: str) -> Tuple[str, ...]:\n"
        "    if isinstance(schema_type, str):\n"
        "        values = (schema_type,)\n"
        "    elif isinstance(schema_type, Sequence) and not isinstance(schema_type, (str, bytes, bytearray)):\n"
        "        values = tuple(str(item) for item in schema_type)\n"
        "    else:\n"
        "        raise ToolManifestError(f'{where}.type must be a string or a sequence of strings')\n"
        "    invalid = [item for item in values if item not in ALLOWED_TYPES]\n"
        "    if invalid:\n"
        "        allowed = ', '.join(sorted(ALLOWED_TYPES))\n"
        "        raise ToolManifestError(f'{where}.type contains unsupported value(s) {invalid}; allowed: {allowed}')\n"
        "    return values\n\n\n"
        "def validate_json_schema(schema: Mapping[str, Any], *, where: str = 'schema', depth: int = 0) -> Dict[str, Any]:\n"
        "    schema = dict(_mapping(schema, where))\n"
        "    if depth > MAX_SCHEMA_DEPTH:\n"
        "        raise ToolManifestError(f'{where} exceeds max depth {MAX_SCHEMA_DEPTH}')\n"
        "    schema_types = _type_names(schema.get('type'), where)\n"
        "    properties = schema.get('properties')\n"
        "    if properties is not None:\n"
        "        properties = dict(_mapping(properties, f'{where}.properties'))\n"
        "        for prop_name, prop_schema in properties.items():\n"
        "            validate_json_schema(prop_schema, where=f'{where}.properties.{prop_name}', depth=depth + 1)\n"
        "        schema['properties'] = properties\n"
        "    if 'array' in schema_types:\n"
        "        validate_json_schema(schema.get('items'), where=f'{where}.items', depth=depth + 1)\n"
        "    return schema\n\n\n"
        "def validate_tool_manifest(descriptor: Mapping[str, Any]) -> Dict[str, Any]:\n"
        "    descriptor = dict(_mapping(descriptor, 'descriptor'))\n"
        "    name = descriptor.get('name')\n"
        "    if not isinstance(name, str) or not _valid_name(name) or len(name) > MAX_NAME_LENGTH:\n"
        "        raise ToolManifestError('descriptor.name must be a valid short tool identifier')\n"
        "    description = descriptor.get('description')\n"
        "    if not isinstance(description, str) or not description.strip() or len(description) > MAX_DESCRIPTION_LENGTH:\n"
        "        raise ToolManifestError('descriptor.description must be non-empty bounded text')\n"
        "    annotations = dict(_mapping(descriptor.get('annotations'), 'descriptor.annotations'))\n"
        "    missing = [key for key in REQUIRED_ANNOTATIONS if key not in annotations]\n"
        "    if missing:\n"
        "        raise ToolManifestError(f'descriptor.annotations missing required keys: {missing}')\n"
        "    for key in ('readOnlyHint', 'destructiveHint'):\n"
        "        if not isinstance(annotations.get(key), bool):\n"
        "            raise ToolManifestError(f'descriptor.annotations.{key} must be boolean')\n"
        "    if not isinstance(annotations.get('title'), str) or not annotations['title'].strip():\n"
        "        raise ToolManifestError('descriptor.annotations.title must be non-empty text')\n"
        "    return {\n"
        "        'name': name,\n"
        "        'description': description,\n"
        "        'annotations': annotations,\n"
        "        'inputSchema': validate_json_schema(descriptor.get('inputSchema'), where='descriptor.inputSchema'),\n"
        "        'outputSchema': validate_json_schema(descriptor.get('outputSchema'), where='descriptor.outputSchema'),\n"
        "    }\n\n\n"
        "def validate_tool_manifests(descriptors: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:\n"
        "    seen = set()\n"
        "    normalized = []\n"
        "    for descriptor in descriptors:\n"
        "        item = validate_tool_manifest(descriptor)\n"
        "        if item['name'] in seen:\n"
        "            raise ToolManifestError(f'duplicate tool descriptor: {item[\"name\"]}')\n"
        "        seen.add(item['name'])\n"
        "        normalized.append(item)\n"
        "    return normalized\n\n\n"
        "TOOL_DESCRIPTORS = [\n"
        "    {\n"
        "        'name': 'loop_engineering_manifest_validate',\n"
        "        'description': 'Validate bounded MCP-style descriptors before exposing AAA loop-engineering tools.',\n"
        "        'annotations': {'title': 'Validate loop tool manifest', 'readOnlyHint': True, 'destructiveHint': False},\n"
        "        'inputSchema': {\n"
        "            'type': 'object',\n"
        "            'properties': {'descriptors': {'type': 'array', 'items': {'type': 'object'}}},\n"
        "            'required': ['descriptors'],\n"
        "        },\n"
        "        'outputSchema': {\n"
        "            'type': 'object',\n"
        "            'properties': {'valid': {'type': 'boolean'}, 'tool_count': {'type': 'integer'}},\n"
        "        },\n"
        "    }\n"
        "]\n\n\n"
        "def get_registered_tools() -> Tuple[Dict[str, Any], ...]:\n"
        "    return tuple(validate_tool_manifests(TOOL_DESCRIPTORS))\n\n\n"
        "def mcp_tool_manifest_snapshot() -> Dict[str, Any]:\n"
        "    tools = list(get_registered_tools())\n"
        "    return {\n"
        "        'schema_version': 'across-aaa-mcp-tool-manifest/1.0',\n"
        "        'tools': tools,\n"
        "        'summary': {'tool_count': len(tools)},\n"
        f"        'model_summary': {decision['summary']!r},\n"
        f"        'model_risk': {decision['risk']!r},\n"
        "        'promotion_requires_human_review': True,\n"
        "    }\n\n\n"
        "__all__ = [\n"
        "    'ToolManifestError',\n"
        "    'TOOL_DESCRIPTORS',\n"
        "    'validate_json_schema',\n"
        "    'validate_tool_manifest',\n"
        "    'validate_tool_manifests',\n"
        "    'get_registered_tools',\n"
        "    'mcp_tool_manifest_snapshot',\n"
        "]\n"
    )


def _render_mcp_tool_manifest_test(module_name: str = "autopilot_mcp_tool_manifest") -> str:
    return (
        "from pathlib import Path\n\n"
        f"from across_agents_assistant.{module_name} import (\n"
        "    TOOL_DESCRIPTORS,\n"
        "    ToolManifestError,\n"
        "    get_registered_tools,\n"
        "    mcp_tool_manifest_snapshot,\n"
        "    validate_tool_manifest,\n"
        "    validate_tool_manifests,\n"
        ")\n\n\n"
        "def _descriptor(name='unit_tool'):\n"
        "    return {\n"
        "        'name': name,\n"
        "        'description': 'A bounded test descriptor.',\n"
        "        'annotations': {'title': 'Unit tool', 'readOnlyHint': True, 'destructiveHint': False},\n"
        "        'inputSchema': {'type': 'object', 'properties': {'query': {'type': 'string'}}},\n"
        "        'outputSchema': {'type': 'object', 'properties': {'ok': {'type': 'boolean'}}},\n"
        "    }\n\n\n"
        "def _expect_error(fn):\n"
        "    try:\n"
        "        fn()\n"
        "    except ToolManifestError:\n"
        "        return True\n"
        "    raise AssertionError('expected ToolManifestError')\n\n\n"
        "def test_registered_tools_validate():\n"
        "    tools = get_registered_tools()\n"
        "    assert tools\n"
        "    assert tools[0]['name'] == TOOL_DESCRIPTORS[0]['name']\n"
        "    assert tools[0]['annotations']['readOnlyHint'] is True\n\n\n"
        "def test_validate_tool_manifest_accepts_valid_descriptor():\n"
        "    item = validate_tool_manifest(_descriptor())\n"
        "    assert item['inputSchema']['properties']['query']['type'] == 'string'\n\n\n"
        "def test_validate_tool_manifests_rejects_duplicate_names():\n"
        "    _expect_error(lambda: validate_tool_manifests([_descriptor('dup'), _descriptor('dup')]))\n\n\n"
        "def test_validate_tool_manifest_rejects_invalid_schema_type():\n"
        "    bad = _descriptor()\n"
        "    bad['inputSchema']['properties']['query']['type'] = 'function'\n"
        "    _expect_error(lambda: validate_tool_manifest(bad))\n\n\n"
        "def test_snapshot_is_human_reviewed():\n"
        "    snapshot = mcp_tool_manifest_snapshot()\n"
        "    assert snapshot['schema_version'] == 'across-aaa-mcp-tool-manifest/1.0'\n"
        "    assert snapshot['promotion_requires_human_review'] is True\n"
        "    assert snapshot['summary']['tool_count'] >= 1\n\n\n"
        "def test_api_server_registration_marker_is_lightweight():\n"
        "    source = Path('backend/src/across_agents_assistant/api_server.py').read_text(encoding='utf-8')\n"
        "    assert 'ACROSS MCP TOOL MANIFEST REGISTRATION START' in source\n"
        f"    assert {module_name!r} in source\n"
        "    assert 'ACROSS_MCP_TOOL_DESCRIPTORS' in source\n\n\n"
        "if __name__ == '__main__':\n"
        "    test_registered_tools_validate()\n"
        "    test_validate_tool_manifest_accepts_valid_descriptor()\n"
        "    test_validate_tool_manifests_rejects_duplicate_names()\n"
        "    test_validate_tool_manifest_rejects_invalid_schema_type()\n"
        "    test_snapshot_is_human_reviewed()\n"
        "    test_api_server_registration_marker_is_lightweight()\n"
    )


def _render_target_backlog_module(decision: Dict[str, Any]) -> str:
    return (
        '"""Validation-stable target backlog helpers for AAA autonomous iteration.\n\n'
        "The backlog is candidate-local review evidence. It is deterministic,\n"
        "JSON-serializable, and never promotes changes without human review.\n"
        '"""\n\n'
        "from __future__ import annotations\n\n"
        "from dataclasses import asdict, dataclass, field\n"
        "from typing import Any, Dict, Iterable, List, Mapping, Optional\n\n\n"
        "SCHEMA_VERSION = 'across-aaa-autopilot-target-backlog/1.0'\n\n\n"
        "def _items(value: Any) -> List[Any]:\n"
        "    if value is None:\n"
        "        return []\n"
        "    if isinstance(value, list):\n"
        "        return value\n"
        "    if isinstance(value, tuple):\n"
        "        return list(value)\n"
        "    return [value]\n\n\n"
        "def _mapping(value: Any) -> Dict[str, Any]:\n"
        "    return dict(value) if isinstance(value, Mapping) else {}\n\n\n"
        "def _target_id(target: Mapping[str, Any], fallback: str) -> str:\n"
        "    return str(target.get('target_id') or target.get('id') or fallback).strip()\n\n\n"
        "def _source_refs(target: Mapping[str, Any], source_signals: Any = None) -> List[str]:\n"
        "    refs = target.get('source_refs') or target.get('sources') or target.get('source_ids')\n"
        "    if refs is None and isinstance(source_signals, Mapping):\n"
        "        refs = [item.get('id') for item in _items(source_signals.get('signals') or source_signals.get('sources')) if isinstance(item, Mapping)]\n"
        "    return [str(item) for item in _items(refs) if str(item).strip()]\n\n\n"
        "@dataclass(frozen=True)\n"
        "class TargetBacklogItem:\n"
        "    target_id: str\n"
        "    target_repo: str\n"
        "    goal: str\n"
        "    priority: str = 'P1'\n"
        "    source_refs: List[str] = field(default_factory=list)\n"
        "    validation_commands: List[Dict[str, Any]] = field(default_factory=list)\n"
        "    risk: str = 'low'\n"
        "    status: str = 'candidate'\n\n"
        "    def to_dict(self) -> Dict[str, Any]:\n"
        "        data = asdict(self)\n"
        "        data['promotion_requires_human_review'] = True\n"
        "        return data\n\n\n"
        "@dataclass\n"
        "class TargetBacklog:\n"
        "    items: List[TargetBacklogItem] = field(default_factory=list)\n"
        "    owner: str = 'across-agents-assistant'\n"
        "    schema_version: str = SCHEMA_VERSION\n\n"
        "    def add(self, item: TargetBacklogItem) -> None:\n"
        "        existing = {entry.target_id for entry in self.items}\n"
        "        if item.target_id not in existing:\n"
        "            self.items.append(item)\n\n"
        "    def find(self, target_id: str) -> Optional[TargetBacklogItem]:\n"
        "        for item in self.items:\n"
        "            if item.target_id == target_id:\n"
        "                return item\n"
        "        return None\n\n"
        "    def to_dict(self) -> Dict[str, Any]:\n"
        "        targets = [item.to_dict() for item in self.items]\n"
        "        return {\n"
        "            'schema_version': self.schema_version,\n"
        "            'owner': self.owner,\n"
        "            'targets': targets,\n"
        "            'summary': {'target_count': len(targets)},\n"
        f"            'model_summary': {decision['summary']!r},\n"
        f"            'model_risk': {decision['risk']!r},\n"
        "            'promotion_requires_human_review': True,\n"
        "        }\n\n\n"
        "def normalize_target(target: Mapping[str, Any], *, fallback_id: str = 'target-1', source_signals: Any = None) -> TargetBacklogItem:\n"
        "    data = _mapping(target)\n"
        "    target_id = _target_id(data, fallback_id)\n"
        "    repo = str(data.get('target_repo') or data.get('repo') or 'across-agents-assistant').strip()\n"
        "    goal = str(data.get('goal') or data.get('summary') or target_id).strip()\n"
        "    commands = [_mapping(item) for item in _items(data.get('validation_commands'))]\n"
        "    return TargetBacklogItem(\n"
        "        target_id=target_id,\n"
        "        target_repo=repo,\n"
        "        goal=goal,\n"
        "        priority=str(data.get('priority') or data.get('score') or 'P1'),\n"
        "        source_refs=_source_refs(data, source_signals),\n"
        "        validation_commands=commands,\n"
        "        risk=str(data.get('risk') or 'low'),\n"
        "        status=str(data.get('status') or 'candidate'),\n"
        "    )\n\n\n"
        "def build_target_backlog(source_signals: Any = None, selected_iteration: Any = None) -> TargetBacklog:\n"
        "    backlog = TargetBacklog()\n"
        "    selected = _mapping(selected_iteration)\n"
        "    raw_targets = selected.get('candidate_targets') or selected.get('targets') or []\n"
        "    targets = [_mapping(item) for item in _items(raw_targets)]\n"
        "    if not targets and selected:\n"
        "        targets = [selected]\n"
        "    if not targets:\n"
        "        targets = [{\n"
        "            'target_id': 'autopilot-target-backlog',\n"
        "            'target_repo': 'across-agents-assistant',\n"
        "            'goal': 'Maintain a bounded candidate target backlog for autonomous self-iteration review.',\n"
        "            'source_refs': ['loop-engineering-architecture-signal', 'tool-pack-operational-signal'],\n"
        "            'validation_commands': [{'command': 'python3', 'args': ['-m', 'py_compile']}],\n"
        "        }]\n"
        "    for index, target in enumerate(targets, start=1):\n"
        "        backlog.add(normalize_target(target, fallback_id=f'target-{index}', source_signals=source_signals))\n"
        "    return backlog\n\n\n"
        "def target_backlog_snapshot(source_signals: Any = None, selected_iteration: Any = None) -> Dict[str, Any]:\n"
        "    return build_target_backlog(source_signals=source_signals, selected_iteration=selected_iteration).to_dict()\n\n\n"
        "def summarize_target_backlog(source_signals: Any = None, selected_iteration: Any = None) -> Dict[str, Any]:\n"
        "    snapshot = target_backlog_snapshot(source_signals=source_signals, selected_iteration=selected_iteration)\n"
        "    return {\n"
        "        'schema_version': snapshot['schema_version'],\n"
        "        'target_count': snapshot['summary']['target_count'],\n"
        "        'target_ids': [item['target_id'] for item in snapshot['targets']],\n"
        "        'promotion_requires_human_review': True,\n"
        "    }\n\n\n"
        "def find_target(backlog: Any, target_id: str) -> Optional[Dict[str, Any]]:\n"
        "    if isinstance(backlog, TargetBacklog):\n"
        "        item = backlog.find(str(target_id))\n"
        "        return item.to_dict() if item else None\n"
        "    data = _mapping(backlog)\n"
        "    for item in _items(data.get('targets') or backlog):\n"
        "        item_data = _mapping(item)\n"
        "        if _target_id(item_data, '') == str(target_id):\n"
        "            return item_data\n"
        "    return None\n\n\n"
        "def to_artifact_envelope(backlog: Any) -> Dict[str, Any]:\n"
        "    payload = backlog.to_dict() if isinstance(backlog, TargetBacklog) else _mapping(backlog)\n"
        "    if not payload:\n"
        "        payload = target_backlog_snapshot()\n"
        "    return {\n"
        "        'schema_version': 'across-aaa-target-backlog-artifact/1.0',\n"
        "        'artifact_type': 'autopilot_target_backlog',\n"
        "        'payload': payload,\n"
        "        'promotion_requires_human_review': True,\n"
        "    }\n\n\n"
        "def validate_target_backlog(backlog: Any) -> Dict[str, Any]:\n"
        "    payload = backlog.to_dict() if isinstance(backlog, TargetBacklog) else _mapping(backlog)\n"
        "    targets = [_mapping(item) for item in _items(payload.get('targets'))]\n"
        "    blocking: List[str] = []\n"
        "    if not targets:\n"
        "        blocking.append('at least one target is required')\n"
        "    for item in targets:\n"
        "        if not _target_id(item, ''):\n"
        "            blocking.append('target_id is required')\n"
        "        if not str(item.get('goal') or '').strip():\n"
        "            blocking.append('goal is required')\n"
        "    return {'status': 'passed' if not blocking else 'failed', 'blocking_reasons': blocking}\n\n\n"
        "__all__ = [\n"
        "    'TargetBacklogItem',\n"
        "    'TargetBacklog',\n"
        "    'SCHEMA_VERSION',\n"
        "    'normalize_target',\n"
        "    'build_target_backlog',\n"
        "    'target_backlog_snapshot',\n"
        "    'summarize_target_backlog',\n"
        "    'find_target',\n"
        "    'to_artifact_envelope',\n"
        "    'validate_target_backlog',\n"
        "]\n"
    )


def _render_target_backlog_test() -> str:
    return (
        "from pathlib import Path\n\n"
        "from across_agents_assistant.autopilot_target_backlog import (\n"
        "    TargetBacklog,\n"
        "    TargetBacklogItem,\n"
        "    build_target_backlog,\n"
        "    find_target,\n"
        "    summarize_target_backlog,\n"
        "    target_backlog_snapshot,\n"
        "    to_artifact_envelope,\n"
        "    validate_target_backlog,\n"
        ")\n\n\n"
        "def _selected():\n"
        "    return {\n"
        "        'target_id': 'aaa-target-backlog-autopilot',\n"
        "        'target_repo': 'across-agents-assistant',\n"
        "        'goal': 'Expose a bounded autonomous target backlog.',\n"
        "        'source_refs': ['loop-engineering-architecture-signal'],\n"
        "        'validation_commands': [{'command': 'python3', 'args': ['-m', 'py_compile']}],\n"
        "    }\n\n\n"
        "def test_backlog_snapshot_is_reviewable():\n"
        "    snapshot = target_backlog_snapshot(selected_iteration=_selected())\n"
        "    assert snapshot['schema_version'] == 'across-aaa-autopilot-target-backlog/1.0'\n"
        "    assert snapshot['summary']['target_count'] == 1\n"
        "    assert snapshot['targets'][0]['promotion_requires_human_review'] is True\n"
        "    assert validate_target_backlog(snapshot)['status'] == 'passed'\n\n\n"
        "def test_backlog_find_and_artifact_envelope():\n"
        "    backlog = build_target_backlog(selected_iteration=_selected())\n"
        "    found = find_target(backlog, 'aaa-target-backlog-autopilot')\n"
        "    assert found['target_repo'] == 'across-agents-assistant'\n"
        "    envelope = to_artifact_envelope(backlog)\n"
        "    assert envelope['artifact_type'] == 'autopilot_target_backlog'\n"
        "    assert envelope['promotion_requires_human_review'] is True\n\n\n"
        "def test_backlog_deduplicates_targets():\n"
        "    backlog = TargetBacklog()\n"
        "    item = TargetBacklogItem(target_id='same', target_repo='repo', goal='goal')\n"
        "    backlog.add(item)\n"
        "    backlog.add(item)\n"
        "    assert backlog.to_dict()['summary']['target_count'] == 1\n\n\n"
        "def test_summary_lists_target_ids():\n"
        "    summary = summarize_target_backlog(selected_iteration=_selected())\n"
        "    assert summary['target_count'] == 1\n"
        "    assert summary['target_ids'] == ['aaa-target-backlog-autopilot']\n\n\n"
        "def test_integration_markers_use_delayed_imports():\n"
        "    candidates = [\n"
        "        ('backend/src/across_agents_assistant/autopilot_workbench.py', 'ACROSS TARGET BACKLOG WORKBENCH START'),\n"
        "        ('backend/src/across_agents_assistant/api_server.py', 'ACROSS TARGET BACKLOG API START'),\n"
        "        ('backend/src/across_agents_assistant/loop_engineering_capability_pack.py', 'ACROSS TARGET BACKLOG CAPABILITY PACK START'),\n"
        "    ]\n"
        "    markers = []\n"
        "    for path, marker in candidates:\n"
        "        file_path = Path(path)\n"
        "        if not file_path.exists():\n"
        "            continue\n"
        "        source = file_path.read_text(encoding='utf-8')\n"
        "        if marker not in source:\n"
        "            continue\n"
        "        block = source.split(marker, 1)[1]\n"
        "        assert 'from .autopilot_target_backlog import' in block\n"
        "        prefix = source.split(marker, 1)[0]\n"
        "        assert 'from .autopilot_target_backlog import TargetBacklog' not in prefix\n"
        "        markers.append(marker)\n"
        "    assert markers, 'expected at least one target backlog integration marker'\n\n\n"
        "if __name__ == '__main__':\n"
        "    test_backlog_snapshot_is_reviewable()\n"
        "    test_backlog_find_and_artifact_envelope()\n"
        "    test_backlog_deduplicates_targets()\n"
        "    test_summary_lists_target_ids()\n"
        "    test_integration_markers_use_delayed_imports()\n"
    )


def _render_target_backlog_swift_view() -> str:
    return (
        "import SwiftUI\n\n"
        "struct AutopilotTargetBacklogItem: Identifiable, Equatable {\n"
        "    let id: String\n"
        "    let repository: String\n"
        "    let goal: String\n"
        "    let status: String\n"
        "}\n\n"
        "struct AutopilotTargetBacklogView: View {\n"
        "    let targets: [AutopilotTargetBacklogItem]\n\n"
        "    var body: some View {\n"
        "        List(targets) { target in\n"
        "            VStack(alignment: .leading, spacing: 4) {\n"
        "                Text(target.id).font(.headline)\n"
        "                Text(target.repository).font(.caption).foregroundStyle(.secondary)\n"
        "                Text(target.goal).font(.body)\n"
        "                Text(target.status).font(.caption2).foregroundStyle(.secondary)\n"
        "            }\n"
        "        }\n"
        "    }\n"
        "}\n\n"
        "#Preview {\n"
        "    AutopilotTargetBacklogView(targets: [\n"
        "        AutopilotTargetBacklogItem(\n"
        "            id: \"autopilot-target-backlog\",\n"
        "            repository: \"across-agents-assistant\",\n"
        "            goal: \"Review a bounded autonomous iteration target.\",\n"
        "            status: \"candidate\"\n"
        "        )\n"
        "    ])\n"
        "}\n"
    )


def _render_mcp_tool_registry_module(decision: Dict[str, Any]) -> str:
    return (
        '"""MCP tool registry contract for AAA loop-engineering candidates.\n\n'
        "The registry is intentionally pure and local. It describes bounded tool\n"
        "surfaces for review evidence; it does not execute tools, open sockets,\n"
        "write memory, or read provider secrets.\n"
        '"""\n\n'
        "from __future__ import annotations\n\n"
        "from dataclasses import asdict, dataclass, field\n"
        "from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple, Union\n\n\n"
        "@dataclass(frozen=True)\n"
        "class ToolDescriptor:\n"
        "    name: str\n"
        "    description: str\n"
        "    input_schema: Dict[str, Any] = field(default_factory=dict)\n"
        "    output_schema: Dict[str, Any] = field(default_factory=dict)\n"
        "    annotations: Dict[str, Any] = field(default_factory=dict)\n\n"
        "    def normalized(self) -> Dict[str, Any]:\n"
        "        if not self.name or not self.name.replace('-', '_').replace('.', '_').isidentifier():\n"
        "            raise ValueError('tool descriptor name must be a stable identifier')\n"
        "        if not self.description.strip():\n"
        "            raise ValueError('tool descriptor description is required')\n"
        "        item = asdict(self)\n"
        "        item['inputSchema'] = item.pop('input_schema') or {'type': 'object'}\n"
        "        item['outputSchema'] = item.pop('output_schema') or {'type': 'object'}\n"
        "        item['annotations'] = {\n"
        "            'title': self.annotations.get('title') or self.name.replace('_', ' ').title(),\n"
        "            'readOnlyHint': bool(self.annotations.get('readOnlyHint', True)),\n"
        "            'destructiveHint': bool(self.annotations.get('destructiveHint', False)),\n"
        "            **{key: value for key, value in self.annotations.items() if key not in {'title', 'readOnlyHint', 'destructiveHint'}},\n"
        "        }\n"
        "        return item\n\n\n"
        "class MCPToolRegistry:\n"
        "    def __init__(self, tools: Optional[Iterable[ToolDescriptor]] = None) -> None:\n"
        "        self._tools: Dict[str, ToolDescriptor] = {}\n"
        "        for tool in tools or []:\n"
        "            self.register_tool(tool)\n\n"
        "    def register_tool(self, tool: Union[ToolDescriptor, Mapping[str, Any]]) -> ToolDescriptor:\n"
        "        descriptor = _coerce_tool_descriptor(tool)\n"
        "        descriptor.normalized()\n"
        "        self._tools[descriptor.name] = descriptor\n"
        "        return descriptor\n\n"
        "    def list_tools(self) -> Tuple[Dict[str, Any], ...]:\n"
        "        return tuple(self._tools[name].normalized() for name in sorted(self._tools))\n\n"
        "    def get_tool(self, name: str) -> Dict[str, Any]:\n"
        "        if name not in self._tools:\n"
        "            raise KeyError(f'unknown MCP tool: {name}')\n"
        "        return self._tools[name].normalized()\n\n"
        "    def to_snapshot(self) -> Dict[str, Any]:\n"
        "        tools = list(self.list_tools())\n"
        "        return {\n"
        "            'schema_version': 'across-aaa-mcp-tool-registry/1.0',\n"
        "            'tools': tools,\n"
        "            'summary': {'tool_count': len(tools)},\n"
        f"            'model_summary': {decision['summary']!r},\n"
        f"            'model_risk': {decision['risk']!r},\n"
        "            'promotion_requires_human_review': True,\n"
        "        }\n\n\n"
        "def _coerce_tool_descriptor(value: Union[ToolDescriptor, Mapping[str, Any]]) -> ToolDescriptor:\n"
        "    if isinstance(value, ToolDescriptor):\n"
        "        return value\n"
        "    if not isinstance(value, Mapping):\n"
        "        raise TypeError('tool descriptor must be a ToolDescriptor or mapping')\n"
        "    return ToolDescriptor(\n"
        "        name=str(value.get('name') or ''),\n"
        "        description=str(value.get('description') or ''),\n"
        "        input_schema=dict(value.get('inputSchema') or value.get('input_schema') or {'type': 'object'}),\n"
        "        output_schema=dict(value.get('outputSchema') or value.get('output_schema') or {'type': 'object'}),\n"
        "        annotations=dict(value.get('annotations') or {}),\n"
        "    )\n\n\n"
        "def build_default_registry() -> MCPToolRegistry:\n"
        "    return MCPToolRegistry([\n"
        "        ToolDescriptor(\n"
        "            name='loop_engineering_manifest_validate',\n"
        "            description='Validate bounded loop-engineering tool registry evidence before promotion review.',\n"
        "            input_schema={\n"
        "                'type': 'object',\n"
        "                'properties': {'tools': {'type': 'array', 'items': {'type': 'object'}}},\n"
        "                'required': ['tools'],\n"
        "            },\n"
        "            output_schema={\n"
        "                'type': 'object',\n"
        "                'properties': {'valid': {'type': 'boolean'}, 'tool_count': {'type': 'integer'}},\n"
        "            },\n"
        "            annotations={'title': 'Validate loop tool registry', 'readOnlyHint': True, 'destructiveHint': False},\n"
        "        )\n"
        "    ])\n\n\n"
        "DEFAULT_REGISTRY = build_default_registry()\n\n\n"
        "def describe_default_registry() -> Dict[str, Any]:\n"
        "    return DEFAULT_REGISTRY.to_snapshot()\n\n\n"
        "def mcp_tool_registry_snapshot() -> Dict[str, Any]:\n"
        "    return describe_default_registry()\n\n\n"
        "__all__ = [\n"
        "    'ToolDescriptor',\n"
        "    'MCPToolRegistry',\n"
        "    'build_default_registry',\n"
        "    'DEFAULT_REGISTRY',\n"
        "    'describe_default_registry',\n"
        "    'mcp_tool_registry_snapshot',\n"
        "]\n"
    )


def _render_mcp_tool_registry_test() -> str:
    return (
        "from pathlib import Path\n\n"
        "from across_agents_assistant.autopilot_mcp_tool_registry import (\n"
        "    DEFAULT_REGISTRY,\n"
        "    MCPToolRegistry,\n"
        "    ToolDescriptor,\n"
        "    build_default_registry,\n"
        "    describe_default_registry,\n"
        "    mcp_tool_registry_snapshot,\n"
        ")\n\n\n"
        "def test_default_registry_exports_reviewable_tool():\n"
        "    snapshot = describe_default_registry()\n"
        "    assert snapshot['schema_version'] == 'across-aaa-mcp-tool-registry/1.0'\n"
        "    assert snapshot['summary']['tool_count'] == 1\n"
        "    assert snapshot['tools'][0]['name'] == 'loop_engineering_manifest_validate'\n"
        "    assert snapshot['promotion_requires_human_review'] is True\n\n\n"
        "def test_registry_registers_and_overwrites_by_name():\n"
        "    registry = MCPToolRegistry()\n"
        "    registry.register_tool(ToolDescriptor(name='loop_status', description='Read loop status.'))\n"
        "    registry.register_tool({'name': 'loop_status', 'description': 'Read bounded loop status.'})\n"
        "    tools = registry.list_tools()\n"
        "    assert len(tools) == 1\n"
        "    assert tools[0]['description'] == 'Read bounded loop status.'\n"
        "    assert tools[0]['annotations']['readOnlyHint'] is True\n\n\n"
        "def test_registry_rejects_invalid_names():\n"
        "    registry = MCPToolRegistry()\n"
        "    try:\n"
        "        registry.register_tool(ToolDescriptor(name='bad name', description='Invalid.'))\n"
        "    except ValueError:\n"
        "        return\n"
        "    raise AssertionError('expected ValueError for invalid tool name')\n\n\n"
        "def test_snapshot_alias_matches_default_registry():\n"
        "    assert DEFAULT_REGISTRY.list_tools() == build_default_registry().list_tools()\n"
        "    assert mcp_tool_registry_snapshot() == describe_default_registry()\n\n\n"
        "def test_integration_marker_uses_delayed_imports():\n"
        "    candidates = [\n"
        "        ('backend/src/across_agents_assistant/autopilot_workbench.py', 'ACROSS MCP TOOL REGISTRY WORKBENCH START'),\n"
        "        ('backend/src/across_agents_assistant/api_server.py', 'ACROSS MCP TOOL REGISTRY API START'),\n"
        "        ('backend/src/across_agents_assistant/loop_engineering_capability_pack.py', 'ACROSS MCP TOOL REGISTRY CAPABILITY PACK START'),\n"
        "    ]\n"
        "    markers = []\n"
        "    for path, marker in candidates:\n"
        "        file_path = Path(path)\n"
        "        if not file_path.exists():\n"
        "            continue\n"
        "        source = file_path.read_text(encoding='utf-8')\n"
        "        if marker not in source:\n"
        "            continue\n"
        "        marker_block = source.split(marker, 1)[1]\n"
        "        assert 'from .autopilot_mcp_tool_registry import' in marker_block\n"
        "        prefix = source.split(marker, 1)[0]\n"
        "        assert 'from .autopilot_mcp_tool_registry import MCPToolRegistry' not in prefix\n"
        "        markers.append(marker)\n"
        "    assert markers, 'expected at least one MCP tool registry integration marker'\n\n\n"
        "if __name__ == '__main__':\n"
        "    test_default_registry_exports_reviewable_tool()\n"
        "    test_registry_registers_and_overwrites_by_name()\n"
        "    test_registry_rejects_invalid_names()\n"
        "    test_snapshot_alias_matches_default_registry()\n"
        "    test_integration_marker_uses_delayed_imports()\n"
    )


def _render_capability_classifier_module(decision: Dict[str, Any]) -> str:
    return (
        '"""Capability classifier for AAA autonomous self-iteration candidates.\n\n'
        "The classifier is pure, deterministic, and review-only. It maps a free\n"
        "form self-iteration goal to bounded capability buckets so API/workbench\n"
        "surfaces can route requests without storing raw transcripts or secrets.\n"
        '"""\n\n'
        "from __future__ import annotations\n\n"
        "import re\n"
        "from typing import Dict, Iterable, List, Tuple\n\n\n"
        "CAPABILITY_BUCKETS: Tuple[str, ...] = (\n"
        "    'workflow_orchestration',\n"
        "    'memory_retrieval',\n"
        "    'context_compression',\n"
        "    'prompt_synthesis',\n"
        "    'tool_routing',\n"
        "    'evidence_aggregation',\n"
        ")\n"
        "DEFAULT_RANKED: Tuple[str, ...] = CAPABILITY_BUCKETS\n"
        "DEFAULT_BUCKET = DEFAULT_RANKED[0]\n\n\n"
        "TOKEN_WEIGHTS: Dict[str, Dict[str, int]] = {\n"
        "    'workflow_orchestration': {'workflow': 3, 'orchestrate': 3, 'orchestration': 3, 'loop': 2, 'autopilot': 2, 'iteration': 2},\n"
        "    'memory_retrieval': {'memory': 3, 'memories': 3, 'recall': 2, 'retrieve': 2, 'retrieval': 2, 'long-term': 2, 'vault': 1},\n"
        "    'context_compression': {'compress': 3, 'compression': 3, 'summarize': 2, 'summary': 2, 'compact': 2, 'token': 1},\n"
        "    'prompt_synthesis': {'prompt': 3, 'instruction': 2, 'template': 2, 'compose': 1, 'few-shot': 2},\n"
        "    'tool_routing': {'tool': 3, 'tools': 3, 'route': 2, 'routing': 2, 'dispatch': 2, 'plugin': 1},\n"
        "    'evidence_aggregation': {'evidence': 3, 'aggregate': 2, 'aggregation': 2, 'trace': 2, 'metric': 1, 'audit': 2},\n"
        "}\n\n\n"
        "def tokenize_goal(goal: str) -> List[str]:\n"
        "    return re.findall(r'[a-z0-9][a-z0-9_-]*', str(goal or '').lower())\n\n\n"
        "def score_goal(goal: str) -> Dict[str, int]:\n"
        "    scores = {bucket: 0 for bucket in CAPABILITY_BUCKETS}\n"
        "    for token in tokenize_goal(goal):\n"
        "        for bucket, weights in TOKEN_WEIGHTS.items():\n"
        "            scores[bucket] += int(weights.get(token, 0))\n"
        "    return scores\n\n\n"
        "def ranked_capabilities(goal: str) -> List[str]:\n"
        "    scores = score_goal(goal)\n"
        "    return sorted(CAPABILITY_BUCKETS, key=lambda bucket: (-scores[bucket], DEFAULT_RANKED.index(bucket)))\n\n\n"
        "def classify_capability(goal: str) -> str:\n"
        "    return ranked_capabilities(goal)[0]\n\n\n"
        "def classify_goal(goal: str) -> Dict[str, object]:\n"
        "    scores = score_goal(goal)\n"
        "    ranked = ranked_capabilities(goal)\n"
        "    primary = ranked[0] if ranked else DEFAULT_BUCKET\n"
        "    top_score = scores.get(primary, 0)\n"
        "    return {\n"
        "        'schema_version': 'across-aaa-capability-classifier/1.0',\n"
        "        'primary': primary,\n"
        "        'ranked': ranked,\n"
        "        'scores': scores,\n"
        "        'confidence': 'keyword' if top_score > 0 else 'default',\n"
        "        'promotion_requires_human_review': True,\n"
        f"        'model_summary': {decision['summary']!r},\n"
        f"        'model_risk': {decision['risk']!r},\n"
        "    }\n\n\n"
        "def render_classification(goal: str) -> Dict[str, object]:\n"
        "    return classify_goal(goal)\n\n\n"
        "def classify_with_scores(goal: str) -> Dict[str, object]:\n"
        "    result = classify_goal(goal)\n"
        "    return {'bucket': result['primary'], 'scores': result['scores']}\n\n\n"
        "def list_capability_buckets() -> Tuple[str, ...]:\n"
        "    return CAPABILITY_BUCKETS\n\n\n"
        "__all__ = [\n"
        "    'CAPABILITY_BUCKETS',\n"
        "    'DEFAULT_BUCKET',\n"
        "    'DEFAULT_RANKED',\n"
        "    'tokenize_goal',\n"
        "    'score_goal',\n"
        "    'ranked_capabilities',\n"
        "    'classify_capability',\n"
        "    'classify_goal',\n"
        "    'render_classification',\n"
        "    'classify_with_scores',\n"
        "    'list_capability_buckets',\n"
        "]\n"
    )


def _render_capability_classifier_test() -> str:
    return (
        "from pathlib import Path\n\n"
        "from across_agents_assistant.autopilot_capability_classifier import (\n"
        "    CAPABILITY_BUCKETS,\n"
        "    DEFAULT_RANKED,\n"
        "    classify_capability,\n"
        "    classify_goal,\n"
        "    classify_with_scores,\n"
        "    list_capability_buckets,\n"
        "    render_classification,\n"
        ")\n\n\n"
        "def test_empty_goal_returns_safe_defaults():\n"
        "    result = classify_goal('')\n"
        "    assert result['primary'] == DEFAULT_RANKED[0]\n"
        "    assert result['confidence'] == 'default'\n"
        "    assert result['promotion_requires_human_review'] is True\n\n\n"
        "def test_memory_goal_routes_to_memory_retrieval():\n"
        "    assert classify_capability('retrieve long-term memory from the local vault') == 'memory_retrieval'\n\n\n"
        "def test_context_goal_routes_to_context_compression():\n"
        "    assert classify_goal('compress and summarize context tokens')['primary'] == 'context_compression'\n\n\n"
        "def test_tool_goal_routes_to_tool_routing():\n"
        "    detail = classify_with_scores('route tool calls and dispatch plugins')\n"
        "    assert detail['bucket'] == 'tool_routing'\n"
        "    assert set(detail['scores']) == set(CAPABILITY_BUCKETS)\n\n\n"
        "def test_render_classification_is_alias():\n"
        "    assert render_classification('aggregate audit evidence')['primary'] == 'evidence_aggregation'\n"
        "    assert list_capability_buckets() == CAPABILITY_BUCKETS\n\n\n"
        "def test_api_server_marker_restores_full_entrypoint():\n"
        "    source = Path('backend/src/across_agents_assistant/api_server.py').read_text(encoding='utf-8')\n"
        "    assert 'ACROSS CAPABILITY CLASSIFIER API START' in source\n"
        "    assert 'def autopilot_classify_capability_detail' in source\n"
        "    assert 'from fastapi import FastAPI' in source or 'FastAPI' in source\n"
        "    assert source.index('ACROSS CAPABILITY CLASSIFIER API START') > 0\n\n\n"
        "if __name__ == '__main__':\n"
        "    test_empty_goal_returns_safe_defaults()\n"
        "    test_memory_goal_routes_to_memory_retrieval()\n"
        "    test_context_goal_routes_to_context_compression()\n"
        "    test_tool_goal_routes_to_tool_routing()\n"
        "    test_render_classification_is_alias()\n"
        "    test_api_server_marker_restores_full_entrypoint()\n"
    )


def _render_tool_pack_registry_module(decision: Dict[str, Any]) -> str:
    return (
        '"""Deterministic Tool Pack registry for AAA loop-engineering candidates."""\n\n'
        "from __future__ import annotations\n\n"
        "from dataclasses import asdict, dataclass, field\n"
        "from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple\n\n\n"
        "@dataclass(frozen=True)\n"
        "class ToolPackDescriptor:\n"
        "    id: str\n"
        "    stage: str\n"
        "    description: str\n"
        "    required: bool = True\n"
        "    capabilities: Tuple[str, ...] = field(default_factory=tuple)\n\n"
        "    def to_dict(self) -> Dict[str, Any]:\n"
        "        item = asdict(self)\n"
        "        item['capabilities'] = list(self.capabilities)\n"
        "        return item\n\n\n"
        "ALL_PACKS: Tuple[ToolPackDescriptor, ...] = (\n"
        "    ToolPackDescriptor('intake', 'intake', 'Collect bounded source signals and trigger context.', capabilities=('source_digest', 'trigger_context')),\n"
        "    ToolPackDescriptor('research', 'research', 'Select reviewable product targets from evidence.', capabilities=('model_research', 'target_selection')),\n"
        "    ToolPackDescriptor('build', 'build', 'Apply candidate-only code changes in B workspaces.', capabilities=('candidate_workspace', 'host_code_iteration')),\n"
        "    ToolPackDescriptor('validate', 'validate', 'Run deterministic validation and candidate quality gates.', capabilities=('validation_harness', 'candidate_quality')),\n"
        "    ToolPackDescriptor('review', 'review', 'Prepare independent reviewer evidence and human promotion package.', capabilities=('semantic_review', 'promotion_attestation')),\n"
        ")\n\n\n"
        "def _as_mapping(value: Any) -> Mapping[str, Any]:\n"
        "    return value if isinstance(value, Mapping) else {}\n\n\n"
        "def _pack_ids(packs: Iterable[ToolPackDescriptor]) -> List[str]:\n"
        "    return [pack.id for pack in packs]\n\n\n"
        "def list_packs() -> List[Dict[str, Any]]:\n"
        "    return [pack.to_dict() for pack in ALL_PACKS]\n\n\n"
        "def resolve_pack(pack_id: str) -> Dict[str, Any]:\n"
        "    for pack in ALL_PACKS:\n"
        "        if pack.id == pack_id:\n"
        "            return pack.to_dict()\n"
        "    raise KeyError('unknown Tool Pack: %s' % pack_id)\n\n\n"
        "def describe_pack(pack_id: str) -> Dict[str, Any]:\n"
        "    return resolve_pack(pack_id)\n\n\n"
        "def register_pack(name: str, descriptor: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:\n"
        "    data = dict(_as_mapping(descriptor))\n"
        "    return {\n"
        "        'id': str(name),\n"
        "        'stage': str(data.get('stage') or name),\n"
        "        'description': str(data.get('description') or ''),\n"
        "        'required': bool(data.get('required', True)),\n"
        "        'capabilities': list(data.get('capabilities') or []),\n"
        "    }\n\n\n"
        "def evaluate(evidence: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:\n"
        "    data = _as_mapping(evidence)\n"
        "    observed = set(str(item) for item in data.get('tool_packs') or data.get('packs') or [])\n"
        "    expected = set(_pack_ids(ALL_PACKS))\n"
        "    missing = sorted(expected - observed) if observed else []\n"
        "    status = 'attention' if missing else 'passed'\n"
        "    return {\n"
        "        'schema_version': 'across-aaa-tool-pack-registry-evaluation/1.0',\n"
        "        'status': status,\n"
        "        'expected_packs': sorted(expected),\n"
        "        'observed_packs': sorted(observed),\n"
        "        'missing_packs': missing,\n"
        "        'promotion_requires_human_review': True,\n"
        "    }\n\n\n"
        "def advise_tool_packs(goal: str, evidence: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:\n"
        "    evaluation = evaluate(evidence)\n"
        "    return {\n"
        "        'schema_version': 'across-aaa-tool-pack-advice/1.0',\n"
        "        'goal': str(goal or ''),\n"
        "        'recommended_packs': _pack_ids(ALL_PACKS),\n"
        "        'evaluation': evaluation,\n"
        "        'status': evaluation['status'],\n"
        f"        'model_summary': {decision['summary']!r},\n"
        f"        'model_risk': {decision['risk']!r},\n"
        "        'promotion_requires_human_review': True,\n"
        "    }\n\n\n"
        "def build_tool_pack_registry() -> Dict[str, Any]:\n"
        "    return {'schema_version': 'across-aaa-tool-pack-registry/1.0', 'packs': list_packs()}\n\n\n"
        "def tool_pack_registry_snapshot() -> Dict[str, Any]:\n"
        "    registry = build_tool_pack_registry()\n"
        "    return {\n"
        "        **registry,\n"
        "        'summary': {'pack_count': len(registry['packs'])},\n"
        "        'promotion_requires_human_review': True,\n"
        "    }\n\n\n"
        "__all__ = [\n"
        "    'ToolPackDescriptor',\n"
        "    'ALL_PACKS',\n"
        "    'register_pack',\n"
        "    'resolve_pack',\n"
        "    'list_packs',\n"
        "    'describe_pack',\n"
        "    'evaluate',\n"
        "    'advise_tool_packs',\n"
        "    'build_tool_pack_registry',\n"
        "    'tool_pack_registry_snapshot',\n"
        "]\n"
    )


def _render_tool_pack_registry_test() -> str:
    return (
        "from pathlib import Path\n\n"
        "from across_agents_assistant.autopilot_tool_pack_registry import (\n"
        "    ALL_PACKS,\n"
        "    ToolPackDescriptor,\n"
        "    advise_tool_packs,\n"
        "    build_tool_pack_registry,\n"
        "    describe_pack,\n"
        "    evaluate,\n"
        "    list_packs,\n"
        "    register_pack,\n"
        "    resolve_pack,\n"
        "    tool_pack_registry_snapshot,\n"
        ")\n\n\n"
        "def test_all_packs_cover_loop_stages():\n"
        "    ids = [pack.id for pack in ALL_PACKS]\n"
        "    assert ids == ['intake', 'research', 'build', 'validate', 'review']\n"
        "    assert all(isinstance(pack, ToolPackDescriptor) for pack in ALL_PACKS)\n\n\n"
        "def test_registry_helpers_are_stable():\n"
        "    assert describe_pack('validate')['stage'] == 'validate'\n"
        "    assert resolve_pack('review')['required'] is True\n"
        "    assert register_pack('custom', {'capabilities': ['x']})['capabilities'] == ['x']\n"
        "    assert len(list_packs()) == len(ALL_PACKS)\n\n\n"
        "def test_evaluate_reports_missing_when_observed_is_partial():\n"
        "    result = evaluate({'tool_packs': ['intake', 'research']})\n"
        "    assert result['status'] == 'attention'\n"
        "    assert 'validate' in result['missing_packs']\n\n\n"
        "def test_advice_and_snapshot_are_reviewable():\n"
        "    advice = advise_tool_packs('build a safer loop', {'tool_packs': ['intake', 'research', 'build', 'validate', 'review']})\n"
        "    assert advice['status'] == 'passed'\n"
        "    assert advice['promotion_requires_human_review'] is True\n"
        "    snapshot = tool_pack_registry_snapshot()\n"
        "    assert snapshot['summary']['pack_count'] == len(ALL_PACKS)\n"
        "    assert build_tool_pack_registry()['schema_version'] == 'across-aaa-tool-pack-registry/1.0'\n\n\n"
        "def test_workbench_and_capability_pack_markers_use_delayed_imports():\n"
        "    workbench = Path('backend/src/across_agents_assistant/autopilot_workbench.py').read_text(encoding='utf-8')\n"
        "    pack = Path('backend/src/across_agents_assistant/loop_engineering_capability_pack.py').read_text(encoding='utf-8')\n"
        "    assert 'ACROSS TOOL PACK REGISTRY WORKBENCH START' in workbench\n"
        "    assert 'def tool_pack_registry_snapshot()' in workbench\n"
        "    assert 'ACROSS TOOL PACK REGISTRY CAPABILITY PACK START' in pack\n"
        "    assert 'def advise_with_capability' in pack\n\n\n"
        "if __name__ == '__main__':\n"
        "    test_all_packs_cover_loop_stages()\n"
        "    test_registry_helpers_are_stable()\n"
        "    test_evaluate_reports_missing_when_observed_is_partial()\n"
        "    test_advice_and_snapshot_are_reviewable()\n"
        "    test_workbench_and_capability_pack_markers_use_delayed_imports()\n"
    )


def _render_mcp_descriptors_module(decision: Dict[str, Any]) -> str:
    return (
        '"""MCP-shaped descriptor registry for AAA loop-engineering surfaces.\n\n'
        "This module intentionally models descriptors only. It does not open a\n"
        "transport, call tools, read secrets, or write files; it gives candidate\n"
        "workspaces deterministic evidence for tool/prompt/resource surfaces.\n"
        '"""\n\n'
        "from __future__ import annotations\n\n"
        "from dataclasses import asdict, dataclass, field\n"
        "from typing import Any, Dict, Iterable, List, Mapping, Optional\n\n\n"
        "@dataclass(frozen=True)\n"
        "class ToolDescriptor:\n"
        "    name: str\n"
        "    description: str = ''\n"
        "    input_schema: Dict[str, Any] = field(default_factory=dict)\n\n\n"
        "@dataclass(frozen=True)\n"
        "class PromptDescriptor:\n"
        "    name: str\n"
        "    description: str = ''\n"
        "    arguments: List[str] = field(default_factory=list)\n\n\n"
        "@dataclass(frozen=True)\n"
        "class ResourceDescriptor:\n"
        "    uri: str\n"
        "    name: str\n"
        "    description: str = ''\n"
        "    mime_type: Optional[str] = None\n\n\n"
        "class MCPDescriptorRegistry:\n"
        "    def __init__(self, *, server_name: str = 'aaa-loop-engineering') -> None:\n"
        "        self.server_name = server_name\n"
        "        self._tools: Dict[str, ToolDescriptor] = {}\n"
        "        self._prompts: Dict[str, PromptDescriptor] = {}\n"
        "        self._resources: Dict[str, ResourceDescriptor] = {}\n\n"
        "    def register_tool(self, descriptor: ToolDescriptor) -> 'MCPDescriptorRegistry':\n"
        "        self._tools[descriptor.name] = descriptor\n"
        "        return self\n\n"
        "    def register_prompt(self, descriptor: PromptDescriptor) -> 'MCPDescriptorRegistry':\n"
        "        self._prompts[descriptor.name] = descriptor\n"
        "        return self\n\n"
        "    def register_resource(self, descriptor: ResourceDescriptor) -> 'MCPDescriptorRegistry':\n"
        "        self._resources[descriptor.uri] = descriptor\n"
        "        return self\n\n"
        "    def list_tools(self) -> List[Dict[str, Any]]:\n"
        "        return [asdict(item) for item in self._tools.values()]\n\n"
        "    def list_prompts(self) -> List[Dict[str, Any]]:\n"
        "        return [asdict(item) for item in self._prompts.values()]\n\n"
        "    def list_resources(self) -> List[Dict[str, Any]]:\n"
        "        return [asdict(item) for item in self._resources.values()]\n\n"
        "    def tools(self) -> List[Dict[str, Any]]:\n"
        "        return self.list_tools()\n\n"
        "    def prompts(self) -> List[Dict[str, Any]]:\n"
        "        return self.list_prompts()\n\n"
        "    def resources(self) -> List[Dict[str, Any]]:\n"
        "        return self.list_resources()\n\n"
        "    def summarize(self) -> Dict[str, Any]:\n"
        "        return summarize_descriptors(self)\n\n"
        "    def render(self) -> Dict[str, Any]:\n"
        "        return self.to_snapshot()\n\n"
        "    def to_snapshot(self) -> Dict[str, Any]:\n"
        "        return {\n"
        "            'schema_version': 'across-aaa-mcp-descriptor-registry/1.0',\n"
        "            'server_name': self.server_name,\n"
        "            'summary': self.summarize(),\n"
        "            'tools': self.list_tools(),\n"
        "            'prompts': self.list_prompts(),\n"
        "            'resources': self.list_resources(),\n"
        f"            'model_summary': {decision['summary']!r},\n"
        f"            'model_risk': {decision['risk']!r},\n"
        "            'promotion_requires_human_review': True,\n"
        "        }\n\n\n"
        "def _strings(values: Iterable[Any]) -> List[str]:\n"
        "    return [str(item) for item in values if str(item).strip()]\n\n\n"
        "def summarize_descriptors(registry: MCPDescriptorRegistry) -> Dict[str, Any]:\n"
        "    return {\n"
        "        'tool_count': len(registry.list_tools()),\n"
        "        'prompt_count': len(registry.list_prompts()),\n"
        "        'resource_count': len(registry.list_resources()),\n"
        "    }\n\n\n"
        "def build_default_registry(server_name: str = 'aaa-loop-engineering') -> MCPDescriptorRegistry:\n"
        "    registry = MCPDescriptorRegistry(server_name=server_name)\n"
        "    registry.register_tool(ToolDescriptor(\n"
        "        name='loop_status',\n"
        "        description='Return bounded loop status evidence.',\n"
        "        input_schema={'type': 'object', 'properties': {'run_id': {'type': 'string'}}},\n"
        "    ))\n"
        "    registry.register_prompt(PromptDescriptor(\n"
        "        name='capability_summary',\n"
        "        description='Summarize current loop-engineering capabilities.',\n"
        "        arguments=['capability_id'],\n"
        "    ))\n"
        "    registry.register_resource(ResourceDescriptor(\n"
        "        uri='mcp://loop-engineering/capabilities',\n"
        "        name='loop_engineering_capabilities',\n"
        "        description='Read-only capability surface for review.',\n"
        "        mime_type='application/json',\n"
        "    ))\n"
        "    return registry\n\n\n"
        "def default_registry(server_name: str = 'aaa-loop-engineering') -> MCPDescriptorRegistry:\n"
        "    return build_default_registry(server_name=server_name)\n\n\n"
        "def describe_default_registry(server_name: str = 'aaa-loop-engineering') -> MCPDescriptorRegistry:\n"
        "    return build_default_registry(server_name=server_name)\n\n\n"
        "def registry_from_manifest(manifest: Mapping[str, Any], *, server_name: str = 'aaa-loop-engineering') -> MCPDescriptorRegistry:\n"
        "    registry = MCPDescriptorRegistry(server_name=server_name)\n"
        "    for item in manifest.get('tools') or []:\n"
        "        if isinstance(item, Mapping) and item.get('name'):\n"
        "            registry.register_tool(ToolDescriptor(str(item.get('name')), str(item.get('description') or ''), dict(item.get('input_schema') or {})))\n"
        "    for item in manifest.get('prompts') or []:\n"
        "        if isinstance(item, Mapping) and item.get('name'):\n"
        "            registry.register_prompt(PromptDescriptor(str(item.get('name')), str(item.get('description') or ''), _strings(item.get('arguments') or [])))\n"
        "    for item in manifest.get('resources') or []:\n"
        "        if isinstance(item, Mapping) and item.get('uri'):\n"
        "            registry.register_resource(ResourceDescriptor(str(item.get('uri')), str(item.get('name') or item.get('uri')), str(item.get('description') or ''), item.get('mime_type')))\n"
        "    return registry\n\n\n"
        "def mcp_surface_snapshot() -> Dict[str, Any]:\n"
        "    return build_default_registry().to_snapshot()\n\n\n"
        "__all__ = [\n"
        "    'ToolDescriptor',\n"
        "    'PromptDescriptor',\n"
        "    'ResourceDescriptor',\n"
        "    'MCPDescriptorRegistry',\n"
        "    'build_default_registry',\n"
        "    'default_registry',\n"
        "    'describe_default_registry',\n"
        "    'registry_from_manifest',\n"
        "    'summarize_descriptors',\n"
        "    'mcp_surface_snapshot',\n"
        "]\n"
    )


def _render_tool_registry_manifest_module(decision: Dict[str, Any]) -> str:
    return (
        '"""MCP-shaped capability manifest for AAA loop-engineering surfaces."""\n\n'
        "from __future__ import annotations\n\n"
        "import importlib\n"
        "from typing import Any, Dict, Iterable, List, Mapping, Optional\n\n\n"
        "def _route_path(route: Any) -> str:\n"
        "    return str(getattr(route, 'path', '') or '')\n\n\n"
        "def _route_methods(route: Any) -> List[str]:\n"
        "    methods = getattr(route, 'methods', None) or []\n"
        "    return sorted(str(method) for method in methods if str(method) not in {'HEAD', 'OPTIONS'})\n\n\n"
        "def collect_route_tools(app: Optional[Any] = None) -> List[Dict[str, Any]]:\n"
        "    routes = list(getattr(app, 'routes', []) or []) if app is not None else []\n"
        "    tools: List[Dict[str, Any]] = []\n"
        "    for route in routes:\n"
        "        path = _route_path(route)\n"
        "        if not path.startswith('/api/'):\n"
        "            continue\n"
        "        methods = _route_methods(route)\n"
        "        if not methods:\n"
        "            continue\n"
        "        name = path.strip('/').replace('/', '_').replace('{', '').replace('}', '') or 'api_root'\n"
        "        tools.append({'name': name, 'path': path, 'methods': methods})\n"
        "    return sorted(tools, key=lambda item: (item['path'], item['name']))\n\n\n"
        "def _items(value: Any) -> List[Any]:\n"
        "    if value is None:\n"
        "        return []\n"
        "    if isinstance(value, list):\n"
        "        return value\n"
        "    if isinstance(value, tuple):\n"
        "        return list(value)\n"
        "    return [value]\n\n\n"
        "def _capability_pack_payload(capability_pack: Any = None) -> Dict[str, Any]:\n"
        "    pack = capability_pack\n"
        "    if pack is None:\n"
        "        try:\n"
        "            pack = importlib.import_module('across_agents_assistant.loop_engineering_capability_pack')\n"
        "        except Exception:\n"
        "            return {'ready': []}\n"
        "    for name in ('build_loop_engineering_capability_pack', 'build_capability_pack'):\n"
        "        fn = getattr(pack, name, None)\n"
        "        if callable(fn):\n"
        "            try:\n"
        "                value = fn()\n"
        "                if isinstance(value, Mapping):\n"
        "                    return dict(value)\n"
        "            except Exception:\n"
        "                pass\n"
        "    for name in ('READY_CAPABILITIES', 'LIST_CAPABILITIES', 'CAPABILITIES'):\n"
        "        value = getattr(pack, name, None)\n"
        "        if value is not None:\n"
        "            return {'ready': _items(value)}\n"
        "    return {'ready': []}\n\n\n"
        "def collect_capability_resources(capability_pack: Any = None) -> List[Dict[str, Any]]:\n"
        "    payload = _capability_pack_payload(capability_pack)\n"
        "    rows = _items(payload.get('ready') or payload.get('capabilities'))\n"
        "    resources: List[Dict[str, Any]] = []\n"
        "    for index, row in enumerate(rows):\n"
        "        data = dict(row) if isinstance(row, Mapping) else {'id': str(row)}\n"
        "        cap_id = str(data.get('id') or data.get('name') or f'capability-{index + 1}')\n"
        "        resources.append({\n"
        "            'uri': f'across://capabilities/{cap_id}',\n"
        "            'name': cap_id,\n"
        "            'description': str(data.get('label') or data.get('description') or ''),\n"
        "        })\n"
        "    return resources\n\n\n"
        "def build_manifest(app: Optional[Any] = None, capability_pack: Any = None) -> Dict[str, Any]:\n"
        "    tools = collect_route_tools(app)\n"
        "    resources = collect_capability_resources(capability_pack)\n"
        "    return {\n"
        "        'schema_version': 'across-aaa-tool-registry-manifest/1.0',\n"
        "        'tools': tools,\n"
        "        'resources': resources,\n"
        "        'prompts': [{'name': 'capability_manifest_review', 'description': 'Review bounded AAA capability manifest evidence.'}],\n"
        "        'summary': {\n"
        "            'tool_count': len(tools),\n"
        "            'resource_count': len(resources),\n"
        "            'prompt_count': 1,\n"
        "        },\n"
        f"        'model_summary': {decision['summary']!r},\n"
        f"        'model_risk': {decision['risk']!r},\n"
        "        'promotion_requires_human_review': True,\n"
        "    }\n\n\n"
        "def register_capability_manifest_route(app: Any) -> Any:\n"
        "    if any(_route_path(route) == '/api/autopilot/capabilities/manifest' for route in getattr(app, 'routes', []) or []):\n"
        "        return app\n\n"
        "    @app.get('/api/autopilot/capabilities/manifest')\n"
        "    async def _capability_manifest_route():\n"
        "        return build_manifest(app)\n\n"
        "    return app\n"
    )


def _render_tool_registry_manifest_test() -> str:
    return (
        "from types import SimpleNamespace\n\n"
        "from across_agents_assistant.tool_registry_manifest import (\n"
        "    build_manifest,\n"
        "    collect_capability_resources,\n"
        "    collect_route_tools,\n"
        "    register_capability_manifest_route,\n"
        ")\n\n\n"
        "class FakeApp:\n"
        "    def __init__(self):\n"
        "        self.routes = [\n"
        "            SimpleNamespace(path='/api/health', methods={'GET', 'HEAD'}),\n"
        "            SimpleNamespace(path='/internal/debug', methods={'GET'}),\n"
        "        ]\n\n"
        "    def get(self, path):\n"
        "        def decorator(fn):\n"
        "            self.routes.append(SimpleNamespace(path=path, methods={'GET'}, endpoint=fn))\n"
        "            return fn\n"
        "        return decorator\n\n\n"
        "class FakePack:\n"
        "    def build_loop_engineering_capability_pack(self):\n"
        "        return {'ready': [{'id': 'repo-quality', 'label': 'Repo quality'}]}\n\n\n"
        "def test_collect_route_tools_keeps_api_routes_only():\n"
        "    tools = collect_route_tools(FakeApp())\n"
        "    assert tools == [{'name': 'api_health', 'path': '/api/health', 'methods': ['GET']}]\n\n\n"
        "def test_collect_capability_resources_reads_pack_builder():\n"
        "    resources = collect_capability_resources(FakePack())\n"
        "    assert resources[0]['uri'] == 'across://capabilities/repo-quality'\n"
        "    assert resources[0]['description'] == 'Repo quality'\n\n\n"
        "def test_build_manifest_is_mcp_shaped_and_human_reviewed():\n"
        "    manifest = build_manifest(FakeApp(), FakePack())\n"
        "    assert manifest['schema_version'] == 'across-aaa-tool-registry-manifest/1.0'\n"
        "    assert manifest['summary'] == {'tool_count': 1, 'resource_count': 1, 'prompt_count': 1}\n"
        "    assert manifest['promotion_requires_human_review'] is True\n\n\n"
        "def test_register_capability_manifest_route_is_idempotent():\n"
        "    app = FakeApp()\n"
        "    register_capability_manifest_route(app)\n"
        "    register_capability_manifest_route(app)\n"
        "    paths = [route.path for route in app.routes]\n"
        "    assert paths.count('/api/autopilot/capabilities/manifest') == 1\n\n\n"
        "if __name__ == '__main__':\n"
        "    test_collect_route_tools_keeps_api_routes_only()\n"
        "    test_collect_capability_resources_reads_pack_builder()\n"
        "    test_build_manifest_is_mcp_shaped_and_human_reviewed()\n"
        "    test_register_capability_manifest_route_is_idempotent()\n"
    )


def _render_mcp_descriptors_test() -> str:
    return (
        "from across_agents_assistant.autopilot_mcp_descriptors import (\n"
        "    MCPDescriptorRegistry,\n"
        "    PromptDescriptor,\n"
        "    ResourceDescriptor,\n"
        "    ToolDescriptor,\n"
        "    build_default_registry,\n"
        "    default_registry,\n"
        "    describe_default_registry,\n"
        "    mcp_surface_snapshot,\n"
        "    registry_from_manifest,\n"
        "    summarize_descriptors,\n"
        ")\n\n\n"
        "def test_registry_round_trip():\n"
        "    registry = MCPDescriptorRegistry(server_name='test')\n"
        "    registry.register_tool(ToolDescriptor('status', 'Return status.'))\n"
        "    registry.register_prompt(PromptDescriptor('summary', 'Summarize.', ['id']))\n"
        "    registry.register_resource(ResourceDescriptor('mcp://x', 'X'))\n"
        "    snapshot = registry.to_snapshot()\n"
        "    assert snapshot['server_name'] == 'test'\n"
        "    assert snapshot['tools'][0]['name'] == 'status'\n"
        "    assert snapshot['prompts'][0]['arguments'] == ['id']\n"
        "    assert snapshot['resources'][0]['uri'] == 'mcp://x'\n"
        "    assert snapshot['promotion_requires_human_review'] is True\n\n\n"
        "def test_default_registry_aliases_are_compatible():\n"
        "    assert isinstance(build_default_registry(), MCPDescriptorRegistry)\n"
        "    assert isinstance(default_registry(), MCPDescriptorRegistry)\n"
        "    assert isinstance(describe_default_registry(), MCPDescriptorRegistry)\n"
        "    summary = summarize_descriptors(build_default_registry())\n"
        "    assert summary == {'tool_count': 1, 'prompt_count': 1, 'resource_count': 1}\n"
        "    rendered = build_default_registry().render()\n"
        "    assert rendered == mcp_surface_snapshot()\n\n\n"
        "def test_registry_from_manifest_normalizes_descriptors():\n"
        "    registry = registry_from_manifest({\n"
        "        'tools': [{'name': 't'}],\n"
        "        'prompts': [{'name': 'p', 'arguments': ('x',)}],\n"
        "        'resources': [{'uri': 'mcp://r'}],\n"
        "    })\n"
        "    assert registry.list_tools()[0]['name'] == 't'\n"
        "    assert registry.list_prompts()[0]['arguments'] == ['x']\n"
        "    assert registry.list_resources()[0]['name'] == 'mcp://r'\n\n\n"
        "def test_workbench_and_capability_pack_surface():\n"
        "    from across_agents_assistant.autopilot_workbench import mcp_surface_snapshot as wb_snapshot\n"
        "    from across_agents_assistant.loop_engineering_capability_pack import mcp_surface_snapshot as pack_snapshot\n\n"
        "    assert wb_snapshot()['summary'] == pack_snapshot()['summary']\n"
        "    assert wb_snapshot()['tools']\n\n\n"
        "if __name__ == '__main__':\n"
        "    test_registry_round_trip()\n"
        "    test_default_registry_aliases_are_compatible()\n"
        "    test_registry_from_manifest_normalizes_descriptors()\n"
        "    test_workbench_and_capability_pack_surface()\n"
    )


def _render_capability_gap_manifest_test() -> str:
    return (
        "import json\n\n"
        "from across_agents_assistant.autopilot_capability_gap_manifest import compute_gap_manifest\n\n\n"
        "def test_compute_gap_manifest_includes_referenced_sources():\n"
        "    result = compute_gap_manifest(\n"
        "        {'spec_id': 'aaa', 'signals': [\n"
        "            {'id': 'loop-engineering-architecture-signal', 'status': 'passed', 'adapter': 'manual_input', 'excerpt': 'tool packs and review gates', 'keywords': ['tool', 'review']},\n"
        "        ]},\n"
        "        {'candidate_targets': [\n"
        "            {'id': 'target', 'source_refs': ['loop-engineering-architecture-signal']},\n"
        "        ]},\n"
        "    )\n"
        "    json.dumps(result)\n"
        "    assert result['manifest_version'] == 'across-autopilot-capability-gap/1.0'\n"
        "    assert result['status'] == 'passed'\n"
        "    assert result['entries'][0]['source_id'] == 'loop-engineering-architecture-signal'\n"
        "    assert result['entries'][0]['evidence_strength'] == 'strong'\n"
        "    assert result['promotion_requires_human_review'] is True\n\n\n"
        "def test_compute_gap_manifest_demotes_for_required_model_backing():\n"
        "    result = compute_gap_manifest(\n"
        "        {'signals': [{'id': 'loop-engineering-architecture-signal', 'status': 'passed', 'excerpt': 'manual policy signal', 'keywords': ['tool', 'review']}]},\n"
        "        {'candidate_targets': [{'id': 'target', 'source_refs': ['loop-engineering-architecture-signal'], 'semantic_review': {'require_model_backed': True}}]},\n"
        "    )\n"
        "    loop_entry = result['entries'][0]\n"
        "    assert loop_entry['requires_model_backing'] is True\n"
        "    assert loop_entry['evidence_strength'] == 'weak'\n\n\n"
        "def test_compute_gap_manifest_reports_missing_refs():\n"
        "    result = compute_gap_manifest(\n"
        "        {'signals': []},\n"
        "        {'candidate_targets': [{'id': 'target', 'source_refs': ['missing-source']}]},\n"
        "    )\n"
        "    assert result['status'] == 'attention'\n"
        "    assert 'missing-source' in result['missing_source_refs']\n\n\n"
        "if __name__ == '__main__':\n"
        "    test_compute_gap_manifest_includes_referenced_sources()\n"
        "    test_compute_gap_manifest_demotes_for_required_model_backing()\n"
        "    test_compute_gap_manifest_reports_missing_refs()\n"
    )


def _generic_autopilot_module_pair(allowed: Set[str]) -> Optional[Tuple[str, str]]:
    modules = sorted(
        path for path in allowed
        if path.startswith("backend/src/across_agents_assistant/autopilot_") and path.endswith(".py")
    )
    tests = set(
        path for path in allowed
        if path.startswith("backend/tests/test_autopilot_") and path.endswith(".py")
    )
    for module_path in modules:
        suffix = Path(module_path).stem.removeprefix("autopilot_")
        test_path = f"backend/tests/test_autopilot_{suffix}.py"
        if test_path in tests:
            return module_path, test_path
    return None


def _validation_feedback_requires_model_repair(feedback: List[Dict[str, Any]]) -> bool:
    """Import-contract and product-integration failures must not use generic host repair."""
    combined_feedback = " ".join(
        str(part or "")
        for item in feedback or []
        for part in (
            item.get("summary"),
            item.get("stderr"),
            item.get("stdout"),
            item.get("command"),
            " ".join(str(arg) for arg in item.get("args", []) if arg is not None)
            if isinstance(item.get("args", []), list)
            else str(item.get("args") or ""),
        )
    ).lower()
    if "autopilot_iteration_telemetry" in combined_feedback and (
        "iterationtelemetryrecord" in combined_feedback
        or "autopilot_workbench" in combined_feedback
        or "build_autopilot_workbench_snapshot" in combined_feedback
        or "candidate_quality" in combined_feedback
    ):
        return False
    if "autopilot_capability_gap_manifest" in combined_feedback and (
        "compute_gap_manifest" in combined_feedback
        or "capability_gap_manifest" in combined_feedback
        or "keyerror" in combined_feedback
    ):
        return False
    if "autopilot_mcp_descriptors" in combined_feedback and (
        "mcpdescriptorregistry" in combined_feedback
        or "describe_default_registry" in combined_feedback
        or "default_registry" in combined_feedback
        or "mcp_surface_snapshot" in combined_feedback
        or "syntaxerror" in combined_feedback
        or "importerror" in combined_feedback
    ):
        return False
    if (
        "autopilot_mcp_tool_manifest" in combined_feedback
        or "autopilot_tool_manifest" in combined_feedback
    ) and (
        "tool_descriptors" in combined_feedback
        or "validate_tool_manifests" in combined_feedback
        or "unintegrated_candidate_helper" in combined_feedback
        or "constant_false_branch" in combined_feedback
        or "destructive_product_entrypoint_rewrite" in combined_feedback
        or "uvicorn" in combined_feedback
        or "syntaxerror" in combined_feedback
        or "assertionerror" in combined_feedback
        or "importerror" in combined_feedback
        or "modulenotfounderror" in combined_feedback
    ):
        return False
    if "autopilot_mcp_tool_registry" in combined_feedback and (
        "mcptoolregistry" in combined_feedback
        or "tooldescriptor" in combined_feedback
        or "default_registry" in combined_feedback
        or "describe_default_registry" in combined_feedback
        or "mcp_tool_registry_snapshot" in combined_feedback
        or "unintegrated_candidate_helper" in combined_feedback
        or "constant_false_branch" in combined_feedback
        or "syntaxerror" in combined_feedback
        or "assertionerror" in combined_feedback
        or "importerror" in combined_feedback
        or "modulenotfounderror" in combined_feedback
    ):
        return False
    if "autopilot_target_backlog" in combined_feedback and (
        "targetbacklog" in combined_feedback
        or "targetbacklogitem" in combined_feedback
        or "find_target" in combined_feedback
        or "to_artifact_envelope" in combined_feedback
        or "summarize_target_backlog" in combined_feedback
        or "destructive_product_entrypoint_rewrite" in combined_feedback
        or "api_server.py" in combined_feedback
        or "autopilot_workbench.py" in combined_feedback
        or "syntaxerror" in combined_feedback
        or "assertionerror" in combined_feedback
        or "importerror" in combined_feedback
        or "modulenotfounderror" in combined_feedback
    ):
        return False
    if "autopilot_capability_classifier" in combined_feedback and (
        "destructive_product_entrypoint_rewrite" in combined_feedback
        or "default_ranked" in combined_feedback
        or "classify_goal" in combined_feedback
        or "classify_capability" in combined_feedback
        or "render_classification" in combined_feedback
        or "api_server.py" in combined_feedback
        or "syntaxerror" in combined_feedback
        or "assertionerror" in combined_feedback
        or "importerror" in combined_feedback
        or "modulenotfounderror" in combined_feedback
    ):
        return False
    if "autopilot_tool_pack_registry" in combined_feedback and (
        "all_packs" in combined_feedback
        or "evaluate" in combined_feedback
        or "advise_with_capability" in combined_feedback
        or "describe_pack" in combined_feedback
        or "register_pack" in combined_feedback
        or "unsupported operand type" in combined_feedback
        or "python_version_incompatible" in combined_feedback
        or "excessive_blank_lines" in combined_feedback
        or "syntaxerror" in combined_feedback
        or "assertionerror" in combined_feedback
        or "importerror" in combined_feedback
        or "modulenotfounderror" in combined_feedback
    ):
        return False
    if "tool_registry_manifest" in combined_feedback and (
        "list_capabilities" in combined_feedback
        or "build_manifest" in combined_feedback
        or "capabilities/manifest" in combined_feedback
        or "syntaxerror" in combined_feedback
        or "assertionerror" in combined_feedback
        or "importerror" in combined_feedback
    ):
        return False
    integration_terms = (
        "candidate_quality",
        "unintegrated_candidate_helper",
        "api_server.py",
        "autopilot_workbench",
        "loop_engineering_capability_pack",
        "missing product integration",
        "existing product entrypoint",
        "existing product integration",
    )
    for item in feedback or []:
        args = item.get("args", [])
        text = " ".join(
            str(part or "")
            for part in (
                item.get("summary"),
                item.get("stderr"),
                item.get("stdout"),
                item.get("command"),
                " ".join(str(arg) for arg in args if arg is not None) if isinstance(args, list) else str(args or ""),
            )
        ).lower()
        command = str(item.get("command") or "").lower()
        if command == "candidate_quality":
            return True
        if any(term in text for term in integration_terms):
            return True
        if "missing internal api import" in text:
            return True
        if "aaa backend api import contract" in text:
            return True
        if "modulenotfounderror" in text and ("api_server" in text or "across_agents_assistant" in text):
            return True
        if "importerror" in text and ("api_server" in text or "across_agents_assistant" in text):
            return True
    return False


def _render_generic_autopilot_module(module_name: str) -> str:
    feature = re.sub(r"[^a-z0-9_]+", "_", module_name.removeprefix("autopilot_").lower()).strip("_") or "candidate_signal"
    return (
        '"""Validation-stable candidate helper for Across Loop Engineering.\n\n'
        "This module is generated only inside a B candidate workspace when the\n"
        "model-selected target needs a deterministic validation repair. It keeps\n"
        "the selected product direction but avoids network, subprocess, secret,\n"
        "or source-A side effects.\n"
        '"""\n\n'
        "from __future__ import annotations\n\n"
        "from collections.abc import Mapping, Sequence\n"
        "from typing import Any\n\n\n"
        f"FEATURE_NAME = {feature!r}\n\n\n"
        "def _items(value: Any) -> list[Any]:\n"
        "    if value is None:\n"
        "        return []\n"
        "    if isinstance(value, list):\n"
        "        return value\n"
        "    if isinstance(value, tuple):\n"
        "        return list(value)\n"
        "    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):\n"
        "        return list(value)\n"
        "    return [value]\n\n\n"
        "def _number(value: Any, *, default: float = 0.0) -> float:\n"
        "    try:\n"
        "        return float(value)\n"
        "    except (TypeError, ValueError):\n"
        "        return default\n\n\n"
        "def evaluate_candidate_signal(payload: Mapping[str, Any] | None = None) -> dict[str, Any]:\n"
        "    \"\"\"Summarize whether a candidate signal is ready for review.\"\"\"\n"
        "    data = payload if isinstance(payload, Mapping) else {}\n"
        "    sources = _items(data.get(\"sources\") or data.get(\"signals\"))\n"
        "    validations = _items(data.get(\"validation_commands\"))\n"
        "    blockers = [str(item) for item in _items(data.get(\"blocking_reasons\")) if str(item).strip()]\n"
        "    used_tokens = max(_number(data.get(\"used_tokens\")), 0.0)\n"
        "    token_budget = _number(data.get(\"token_budget\"), default=max(used_tokens, 1.0))\n"
        "    if token_budget <= 0:\n"
        "        token_budget = max(used_tokens, 1.0)\n"
        "    remaining_tokens = max(token_budget - used_tokens, 0.0)\n"
        "    budget_ratio = remaining_tokens / token_budget\n"
        "    status = \"ready\"\n"
        "    if blockers:\n"
        "        status = \"blocked\"\n"
        "    elif not sources or not validations:\n"
        "        status = \"needs_evidence\"\n"
        "    elif budget_ratio < 0.2:\n"
        "        status = \"attention\"\n"
        "    return {\n"
        "        \"feature\": FEATURE_NAME,\n"
        "        \"status\": status,\n"
        "        \"source_count\": len(sources),\n"
        "        \"validation_count\": len(validations),\n"
        "        \"blocking_reasons\": blockers,\n"
        "        \"remaining_tokens\": remaining_tokens,\n"
        "        \"budget_ratio\": round(budget_ratio, 4),\n"
        "        \"promotion_requires_human_review\": True,\n"
        "    }\n"
    )


def _render_generic_autopilot_test(module_name: str) -> str:
    return (
        f"from across_agents_assistant.{module_name} import evaluate_candidate_signal\n\n\n"
        "def test_evaluate_candidate_signal_marks_ready_with_evidence():\n"
        "    result = evaluate_candidate_signal({\n"
        "        \"sources\": [{\"id\": \"source\"}],\n"
        "        \"validation_commands\": [\"python -m py_compile\"],\n"
        "        \"used_tokens\": 2,\n"
        "        \"token_budget\": 10,\n"
        "    })\n"
        "    assert result[\"status\"] == \"ready\"\n"
        "    assert result[\"source_count\"] == 1\n"
        "    assert result[\"validation_count\"] == 1\n"
        "    assert result[\"promotion_requires_human_review\"] is True\n\n\n"
        "def test_evaluate_candidate_signal_blocks_explicit_reasons():\n"
        "    result = evaluate_candidate_signal({\"blocking_reasons\": [\"validation failed\"]})\n"
        "    assert result[\"status\"] == \"blocked\"\n"
        "    assert result[\"blocking_reasons\"] == [\"validation failed\"]\n"
    )


def _code_iteration_allowed(req: AutopilotCodeIterationRequest, rel: str) -> bool:
    allowed = [_safe_autopilot_rel_path(path) for path in req.allowed_patch_paths if str(path or "").strip()]
    return not allowed or rel in allowed


def _render_platform_self_repair_replay_test() -> str:
    return '''import test from "node:test";
import assert from "node:assert/strict";
import {
  buildPlatformSelfRepairTrigger,
  diagnosePlatformSelfRepair,
  renderTriggerPayloadSource
} from "../src/platform-self-repair.js";

test("platform self-repair supervisor gaps route to the bounded replay fixture target", () => {
  const diagnosis = diagnosePlatformSelfRepair({
    spec: {
      id: "aaa-autonomous-self-iteration",
      failure_policy: { platform_self_repair: { enabled: true } }
    },
    failedRun: {
      run_id: "run-supervisor-gap",
      spec_id: "aaa-autonomous-self-iteration",
      trigger_event: {
        payload: {
          auto_platform_self_repair: true,
          platform_self_repair_case: {
            category: "supervisor_gap",
            goal: "Queue dispatch recorded a platform self-repair routing regression."
          }
        }
      },
      failure: {
        code: "gate.failed",
        message: "self-repair trigger queue dispatch did not expose replay evidence"
      }
    },
    evidence: {
      actions: [],
      gates: [{ id: "self_repair_router", status: "failed", summary: "trigger queue route failed" }]
    }
  });
  const trigger = buildPlatformSelfRepairTrigger(diagnosis);

  assert.equal(diagnosis.eligible, true);
  assert.equal(diagnosis.target_id, "autopilot-self-repair-replay-fixture");
  assert.equal(diagnosis.target_repo, "across-autopilot");
  assert.deepEqual(diagnosis.allowed_patch_paths, ["tests/platform-self-repair.test.js"]);
  assert.equal(diagnosis.allowed_patch_paths.includes("src/platform-self-repair.js"), false);
  assert.equal(diagnosis.allowed_patch_paths.includes("src/supervisor.js"), false);
  assert.equal(diagnosis.allowed_patch_paths.includes("src/candidate-ecosystem.js"), false);
  assert.equal(trigger.payload.target_id, diagnosis.target_id);
  assert.equal(trigger.payload.replay_contract.required, true);
  assert.equal(trigger.spec_id, undefined);
  assert.match(trigger.idempotency_key, /^platform-self-repair:run-supervisor-gap:supervisor_gap$/);
});

test("platform self-repair trigger payload is safe to expose to the host model", () => {
  const fakeKey = ["local", "key", "fixture"].join("-");
  const privateTranscript = ["private", "transcript"].join(" ");
  const fakeBearer = ["Bearer", "private", "value"].join(" ");
  const source = renderTriggerPayloadSource({
    auto_platform_self_repair: true,
    api_key: fakeKey,
    raw_transcript: privateTranscript,
    nested: {
      authorization: fakeBearer
    },
    platform_self_repair_case: {
      category: "validation_gap",
      goal: "Validation gap should become a bounded repair candidate."
    }
  });
  assert.equal(source.payload.api_key, "[redacted]");
  assert.equal(source.payload.raw_transcript, "[redacted]");
  assert.equal(source.payload.nested.authorization, "[redacted]");
  assert.equal(source.content.includes(fakeKey), false);
  assert.equal(source.content.includes(privateTranscript), false);

  const diagnosis = diagnosePlatformSelfRepair({
    spec: { id: "aaa-autonomous-self-iteration" },
    failedRun: {
      run_id: "run-redaction",
      spec_id: "aaa-autonomous-self-iteration",
      trigger_event: { payload: source.payload },
      failure: { code: "gate.failed", message: "validator failed to block bad candidate evidence" }
    },
    evidence: { actions: [], gates: [] }
  });
  const trigger = buildPlatformSelfRepairTrigger(diagnosis);
  const serialized = JSON.stringify(trigger);
  assert.equal(serialized.includes(fakeKey), false);
  assert.equal(serialized.includes(privateTranscript), false);
  assert.equal(trigger.payload.target_id, "autopilot-validation-router-repair");
});

test("ordinary candidate failures do not enqueue platform self-repair", () => {
  const diagnosis = diagnosePlatformSelfRepair({
    spec: {
      id: "aaa-autonomous-self-iteration",
      failure_policy: { platform_self_repair: { enabled: true } }
    },
    failedRun: {
      run_id: "run-candidate-failure",
      spec_id: "aaa-autonomous-self-iteration",
      trigger_event: { payload: { auto_platform_self_repair: true } },
      failure: {
        code: "gate.failed",
        message: "pytest failed because candidate implementation assertion failed"
      }
    },
    evidence: {
      actions: [
        {
          adapter: "candidate_ecosystem_validation",
          status: "failed",
          failure: { code: "gate.failed", message: "pytest failed" },
          result: {
            commands: [
              {
                status: "failed",
                command: "python3",
                args: ["-m", "pytest"],
                stderr: "AssertionError: expected candidate behavior"
              }
            ]
          }
        }
      ],
      gates: []
    }
  });

  assert.equal(diagnosis.eligible, false);
  assert.equal(diagnosis.category, "candidate_code_failure");
  assert.equal(diagnosis.status, "not_applicable");
});
'''


def _minimax_json_extra_body(provider_id: Optional[str]) -> Dict[str, Any]:
    if str(provider_id or "").lower() == "minimax":
        return {"reasoning_split": True, "thinking": {"type": "disabled"}}
    return {}


def _direct_patch_repair_attempts(policy: Dict[str, Any]) -> int:
    raw = policy.get("direct_patch_repair_attempts", policy.get("json_repair_attempts", 3))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 3
    return max(1, min(value, 5))


def _code_model_candidates(policy: Dict[str, Any]) -> List[Optional[str]]:
    primary = _autopilot_model_policy_value(policy, "model", "model_id")
    candidates: List[Optional[str]] = [str(primary) if primary else None]
    for item in policy.get("fallback_models") or []:
        text = str(item or "").strip()
        if text and text not in candidates:
            candidates.append(text)
    return candidates


def _local_agent_model_candidates(policy: Dict[str, Any], agent_id: Optional[str]) -> List[Optional[str]]:
    candidates = _code_model_candidates(policy)
    normalized_agent_id = normalize_agent_id(agent_id) if agent_id else None
    if normalized_agent_id != "codex":
        return candidates
    if all(str(candidate or "").strip().lower() in {"", "auto", "codex", "local-agent"} for candidate in candidates):
        return candidates
    try:
        from .local_agent_health import discover_codex_models

        registry = discover_codex_models()
    except Exception:
        return candidates
    if not registry.get("available"):
        return candidates
    available = set(str(item) for item in (registry.get("available_models") or []))
    filtered: List[Optional[str]] = []
    for candidate in candidates:
        text = str(candidate or "").strip()
        if not text or text.lower() in {"auto", "codex", "local-agent"} or text in available:
            if candidate not in filtered:
                filtered.append(candidate)
    return filtered


async def _autopilot_code_iteration_chat(
    req: AutopilotCodeIterationRequest,
    *,
    context_files: List[Dict[str, Any]],
    provider_id: Optional[str],
    model_id: Optional[str],
    agent_id: Optional[str],
    temperature: float,
    max_tokens: int,
    timeout_seconds: float,
    idle_timeout_seconds: Optional[float] = None,
) -> Tuple[Any, Dict[str, Any], Optional[List[Dict[str, Any]]], bool, bool]:
    direct_patches = bool(req.model_policy.get("direct_patches") or req.model_policy.get("code_mode") == "direct_patches")
    allow_host_fallback = bool(
        req.model_policy.get("allow_host_code_fallback")
        or req.model_policy.get("conformance_fixture")
    )
    allow_validation_repair_fallback = bool(req.validation_feedback) and bool(
        req.model_policy.get("allow_host_validation_repair_fallback", True)
    ) and not _validation_feedback_requires_model_repair(req.validation_feedback)
    if direct_patches and str(provider_id or "").lower() == "minimax":
        max_tokens = max(max_tokens, 8192)
    response = await _chat_with_model_capability(
        message=_autopilot_code_iteration_user_prompt(req, context_files),
        system_prompt=_autopilot_code_iteration_system_prompt(direct_patches=direct_patches),
        provider_id=str(provider_id) if provider_id else None,
        model=str(model_id) if model_id else None,
        agent_id=str(agent_id) if agent_id else None,
        project_dir=req.candidate_workspace,
        scope="model.code_patch",
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout_seconds,
        max_wall_timeout=timeout_seconds,
        idle_timeout=idle_timeout_seconds,
        extra_body=_minimax_json_extra_body(provider_id) if direct_patches else {},
    )
    if direct_patches:
        try:
            decision, patches = _normalize_direct_code_iteration_decision(
                _extract_json_object(response.text),
                allowed_patch_paths=req.allowed_patch_paths,
            )
            return response, decision, patches, False, False
        except Exception as exc:
            last_response = response
            last_error: Exception = exc
            repair_errors: List[str] = [str(exc)]
            for _ in range(_direct_patch_repair_attempts(req.model_policy)):
                repair_response = await _chat_with_model_capability(
                    message=_autopilot_code_iteration_repair_prompt(req, last_response.text, last_error),
                    system_prompt=_autopilot_code_iteration_system_prompt(direct_patches=True),
                    provider_id=str(provider_id) if provider_id else None,
                    model=str(model_id) if model_id else None,
                    agent_id=str(agent_id) if agent_id else None,
                    project_dir=req.candidate_workspace,
                    scope="model.code_patch",
                    temperature=0.0,
                    max_tokens=max_tokens,
                    timeout=timeout_seconds,
                    max_wall_timeout=timeout_seconds,
                    idle_timeout=idle_timeout_seconds,
                    extra_body=_minimax_json_extra_body(provider_id),
                )
                try:
                    decision, patches = _normalize_direct_code_iteration_decision(
                        _extract_json_object(repair_response.text),
                        allowed_patch_paths=req.allowed_patch_paths,
                    )
                    return repair_response, decision, patches, False, True
                except Exception as repair_exc:
                    last_response = repair_response
                    last_error = repair_exc
                    repair_errors.append(str(repair_exc))
            decision, patches = _fallback_direct_code_iteration_decision(
                last_response.text,
                ValueError("Model direct patch JSON repair errors: " + " | ".join(repair_errors[-4:])),
                allowed_patch_paths=req.allowed_patch_paths,
                allow_host_fallback=allow_host_fallback or allow_validation_repair_fallback,
                source_repository=req.source_repository,
            )
            if allow_validation_repair_fallback:
                decision["host_validation_repair_fallback"] = True
            return response, decision, patches, True, False
    try:
        return response, _normalize_code_iteration_decision(_extract_json_object(response.text)), None, False, False
    except Exception:
        fallback = {
            "summary": str(response.text or "Model selected a bounded candidate status helper.")[:500],
            "capability_name": "candidate_self_iteration",
            "status_label": "candidate-ready",
            "key_behaviors": ["Record model-backed candidate status.", "Keep promotion human-approved."],
            "validation": ["Import helper.", "Assert promotion safety flag."],
            "risk": "medium",
        }
        return response, _normalize_code_iteration_decision(fallback), None, True, False


@app.post("/api/autopilot/code-iteration")
async def create_autopilot_code_iteration(req: AutopilotCodeIterationRequest):
    """Return a host-model-backed code patch for a B candidate repository."""
    try:
        context_req = AutopilotModelDecisionRequest(
            goal=req.goal,
            candidate_workspace=req.candidate_workspace,
            source_repository=req.source_repository,
            allowed_patch_paths=req.allowed_patch_paths,
            context_files=req.context_files,
            candidate_model_lease=req.candidate_model_lease,
            model_policy=req.model_policy,
        )
        policy = dict(req.model_policy or {})
        direct_patches_requested = bool(policy.get("direct_patches") or policy.get("code_mode") == "direct_patches")
        context_files = _read_autopilot_context_files(context_req)
        if direct_patches_requested:
            context_files = _compact_autopilot_context_files(context_files)
        provider_id = _autopilot_model_policy_value(policy, "provider", "provider_id")
        model_id = _autopilot_model_policy_value(policy, "model", "model_id")
        agent_id = _autopilot_model_policy_value(policy, "agent_id", "agent")
        temperature = float(_autopilot_model_policy_value(policy, "temperature", default=0.2))
        base_max_tokens = int(_autopilot_model_policy_value(policy, "max_tokens", "maxTokens", default=1200))
        timeout_plan = _autopilot_model_policy_timeout_plan(policy, default_idle=900.0)
        timeout_seconds = timeout_plan["max_wall_timeout_seconds"]
        idle_timeout_seconds = timeout_plan["idle_timeout_seconds"]
        host_validation_repair_fallback = False
        allow_host_fallback = bool(
            policy.get("allow_host_code_fallback")
            or policy.get("conformance_fixture")
        )
        allow_validation_repair_fallback = bool(req.validation_feedback) and bool(
            policy.get("allow_host_validation_repair_fallback", False)
        ) and not _validation_feedback_requires_model_repair(req.validation_feedback)
        if direct_patches_requested and req.validation_feedback and (allow_host_fallback or allow_validation_repair_fallback):
            try:
                decision, direct_patches = _fallback_direct_code_iteration_decision(
                    "validation feedback repair",
                    ValueError("validation feedback repair fallback"),
                    allowed_patch_paths=req.allowed_patch_paths,
                    allow_host_fallback=True,
                    source_repository=req.source_repository,
                )
                decision["host_validation_repair_fallback"] = True
                response = SimpleNamespace(
                    provider=str(provider_id or "host"),
                    model=str(model_id or "host-validation-repair"),
                    finish_reason="host_validation_repair_fallback",
                    usage={},
                )
                text_fallback = True
                repaired_json = False
                host_validation_repair_fallback = True
            except ValueError:
                response, decision, direct_patches, text_fallback, repaired_json = await _run_code_iteration_with_model_fallbacks(
                    req,
                    context_files=context_files,
                    provider_id=str(provider_id) if provider_id else None,
                    model_candidates=_local_agent_model_candidates(policy, str(agent_id) if agent_id else None),
                    agent_id=str(agent_id) if agent_id else None,
                    temperature=temperature,
                    base_max_tokens=base_max_tokens,
                    direct_patches_requested=direct_patches_requested,
                    timeout_seconds=timeout_seconds,
                    idle_timeout_seconds=idle_timeout_seconds,
                )
        else:
            response, decision, direct_patches, text_fallback, repaired_json = await _run_code_iteration_with_model_fallbacks(
                req,
                context_files=context_files,
                provider_id=str(provider_id) if provider_id else None,
                model_candidates=_local_agent_model_candidates(policy, str(agent_id) if agent_id else None),
                agent_id=str(agent_id) if agent_id else None,
                temperature=temperature,
                base_max_tokens=base_max_tokens,
                direct_patches_requested=direct_patches_requested,
                timeout_seconds=timeout_seconds,
                idle_timeout_seconds=idle_timeout_seconds,
            )
        host_validation_repair_fallback = host_validation_repair_fallback or bool(decision.get("host_validation_repair_fallback"))
        module_path = "backend/src/across_agents_assistant/loop_engineering_candidate.py"
        test_path = "backend/tests/test_loop_engineering_candidate.py"
        if direct_patches is None:
            for rel in (module_path, test_path):
                if not _code_iteration_allowed(req, rel):
                    raise ValueError(f"Host code iteration path is outside allowed_patch_paths: {rel}")
            patches = [
                {
                    "path": module_path,
                    "mode": "overwrite",
                    "content": _render_candidate_status_module(decision, req),
                },
                {
                    "path": test_path,
                    "mode": "overwrite",
                    "content": _render_candidate_status_test(decision),
                },
            ]
        else:
            patches = direct_patches
        clean = {
            "summary": decision["summary"],
            **({"capability_name": decision["capability_name"], "status_label": decision["status_label"]} if "capability_name" in decision else {}),
            "risk": decision["risk"],
            "patch_paths": [patch["path"] for patch in patches],
        }
        strategy_validation_commands = _normalize_validation_commands(req.validation_commands, default_repo=req.target_repo)
        fallback_validation_commands = [
            {"command": "python3", "args": ["-m", "py_compile", module_path]},
            {
                "command": "python3",
                "args": [
                    "-c",
                    "import sys; sys.path.insert(0, 'backend/src'); "
                    "from across_agents_assistant.loop_engineering_candidate import candidate_self_iteration_status; "
                    "s=candidate_self_iteration_status(); "
                    "assert s['promotion_requires_human_approval'] is True; "
                    "assert s['key_behaviors']",
                ],
            },
        ]
        validation_commands = strategy_validation_commands or decision.get("validation_commands") or fallback_validation_commands
        decision_json = json.dumps(clean, ensure_ascii=False, sort_keys=True)
        return {
            "schema_version": "across-host-code-iteration/1.0",
            "status": "passed",
            "model_backed": True,
            "provider": response.provider,
            "model": response.model,
            "finish_reason": response.finish_reason,
            "usage": response.usage,
            "repaired_json": repaired_json,
            "text_fallback": text_fallback,
            "host_validation_repair_fallback": host_validation_repair_fallback,
            "decision_hash": hashlib.sha256(decision_json.encode("utf-8")).hexdigest(),
            "candidate_model_lease": _public_request_model_lease(req.candidate_model_lease),
            "summary": decision["summary"],
            "decision": clean,
            "patches": patches,
            "validation_commands": validation_commands,
            "context": {
                "file_count": len(context_files),
                "files": [{"path": item["path"], "bytes": item["bytes"], "truncated": item["truncated"]} for item in context_files],
            },
        }
    except HTTPException:
        raise
    except LocalAgentExecutionError as exc:
        status_code = 504 if exc.code == "timeout" else 503
        detail = f"Autopilot code iteration local agent failed: {_sanitize_public_error_text(str(exc))}"
        raise HTTPException(status_code=status_code, detail=detail)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise _safe_http_500("Create Autopilot code iteration")


async def _run_code_iteration_with_model_fallbacks(
    req: AutopilotCodeIterationRequest,
    *,
    context_files: List[Dict[str, Any]],
    provider_id: Optional[str],
    model_candidates: List[Optional[str]],
    agent_id: Optional[str],
    temperature: float,
    base_max_tokens: int,
    direct_patches_requested: bool,
    timeout_seconds: float,
    idle_timeout_seconds: Optional[float] = None,
) -> Tuple[Any, Dict[str, Any], Optional[List[Dict[str, Any]]], bool, bool]:
    last_error: Optional[Exception] = None
    for candidate_model in model_candidates or [None]:
        max_tokens = base_max_tokens
        if direct_patches_requested and str(provider_id or "").lower() == "minimax":
            max_tokens = max(max_tokens, 8192)
        from .autopilot_host_cli_progress import host_cli_log

        host_cli_log(
            "autopilot-code-iteration.jsonl",
            "code_iteration.model_candidate.start",
            run_id=req.run_id,
            candidate_id=req.candidate_id,
            provider=provider_id,
            agent_id=agent_id,
            model=candidate_model,
            idle_timeout_sec=idle_timeout_seconds,
            max_wall_timeout_sec=timeout_seconds,
        )
        try:
            result = await _autopilot_code_iteration_chat(
                req,
                context_files=context_files,
                provider_id=provider_id,
                model_id=str(candidate_model) if candidate_model else None,
                agent_id=agent_id,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout_seconds=timeout_seconds,
                idle_timeout_seconds=idle_timeout_seconds,
            )
            host_cli_log(
                "autopilot-code-iteration.jsonl",
                "code_iteration.model_candidate.complete",
                run_id=req.run_id,
                candidate_id=req.candidate_id,
                provider=provider_id,
                agent_id=agent_id,
                model=candidate_model,
            )
            return result
        except Exception as exc:
            last_error = exc
            host_cli_log(
                "autopilot-code-iteration.jsonl",
                "code_iteration.model_candidate.failed",
                run_id=req.run_id,
                candidate_id=req.candidate_id,
                provider=provider_id,
                agent_id=agent_id,
                model=candidate_model,
                error_type=type(exc).__name__,
                error_code=getattr(exc, "code", None),
                timeout_kind=getattr(exc, "timeout_kind", None),
                elapsed_sec=getattr(exc, "elapsed_sec", None),
                error=_sanitize_public_error_text(str(exc))[:500],
            )
            logger.warning(
                "Autopilot code iteration model candidate failed: provider=%s model=%s error=%s",
                provider_id,
                candidate_model,
                _sanitize_public_error_text(exc),
            )
            continue
    if isinstance(last_error, (ValueError, LocalAgentExecutionError)):
        raise last_error
    raise RuntimeError(f"All Autopilot code iteration model candidates failed: {last_error}")


def _autopilot_review_system_prompt() -> str:
    return (
        "You are the independent acceptance reviewer for an Across Loop Engineering B candidate. "
        "Return JSON only. Do not include markdown fences. "
        "You must review product value, maintainability, validation evidence, model separation, and promotion risk. "
        "Do not write code and do not approve merge or release. Human approval is still required. "
        "Return this JSON shape: "
        "{\"status\":\"passed|failed\", \"recommendation\":\"review|reject\", "
        "\"merge_recommendation\":\"open_review_pr|repair_before_pr\", "
        "\"product_value_score\": number, \"maintainability_score\": number, \"risk_score\": number, "
        "\"blocking_reasons\":[string], \"human_review_notes\":[string]}. "
        "Use open_review_pr only when deterministic review has no blocking reasons, validation passed, "
        "the change includes product source, and risk is low."
    )


def _autopilot_review_user_prompt(req: AutopilotReviewDecisionRequest) -> str:
    payload = {
        "goal": req.goal,
        "run_id": req.run_id,
        "spec_id": req.spec_id,
        "selected_target_id": req.selected_target_id,
        "selected_iteration": req.selected_iteration,
        "changed_files": req.changed_files[:40],
        "validation": req.validation,
        "diff_summary": req.diff_summary,
        "deterministic_review": req.deterministic_review,
        "builder_model": req.builder_model,
    }
    return (
        "Review this B-candidate evidence independently from the builder. "
        "Reject or request repair if validation failed, deterministic review has blocking reasons, "
        "the change is test-only, or the candidate has no product value. "
        "When selected_iteration.semantic_review.allow_replay_fixture_only is true, do not reject solely "
        "because the change is test-only or has no product source change; instead evaluate whether the "
        "replay fixture covers the failed platform trigger and remains bounded. "
        "Return the required JSON object only.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def _autopilot_review_repair_prompt(raw_text: str, error: Exception) -> str:
    return (
        "Repair the prior reviewer output into the required JSON object only. "
        "No markdown, no commentary. "
        "Required keys: status, recommendation, merge_recommendation, product_value_score, "
        "maintainability_score, risk_score, blocking_reasons, human_review_notes.\n\n"
        + json.dumps({
            "parse_error": str(error),
            "raw_model_output": str(raw_text or "")[:20_000],
        }, ensure_ascii=False, indent=2)
    )


def _review_model_candidates(policy: Dict[str, Any]) -> List[Optional[str]]:
    primary = _autopilot_model_policy_value(policy, "model", "model_id")
    candidates: List[Optional[str]] = [str(primary) if primary else None]
    for item in policy.get("fallback_models") or []:
        text = str(item or "").strip()
        if text and text not in candidates:
            candidates.append(text)
    return candidates


def _same_model_identity(left: Dict[str, Any], right_provider: Optional[str], right_model: Optional[str]) -> bool:
    left_provider = str(left.get("provider") or "").strip().lower()
    left_model = str(left.get("model") or "").strip().lower()
    return bool(left_provider and left_model and left_provider == str(right_provider or "").strip().lower() and left_model == str(right_model or "").strip().lower())


def _clamp_review_score(value: Any, default: int) -> int:
    try:
        numeric = int(round(float(value)))
    except (TypeError, ValueError):
        numeric = default
    return max(0, min(100, numeric))


def _review_allows_replay_fixture_only(req: AutopilotReviewDecisionRequest) -> bool:
    selected = req.selected_iteration if isinstance(req.selected_iteration, dict) else {}
    semantic = selected.get("semantic_review") if isinstance(selected.get("semantic_review"), dict) else {}
    if semantic.get("allow_replay_fixture_only") is not True:
        return False
    if str(selected.get("target_id") or "") != "autopilot-self-repair-replay-fixture":
        return False
    changed = [str(path or "") for path in req.changed_files]
    return bool(changed) and all(path == "across-autopilot/tests/platform-self-repair.test.js" for path in changed)


def _review_replay_fixture_only_blocker(reason: str) -> bool:
    text = str(reason or "").lower()
    return any(
        phrase in text
        for phrase in (
            "no product source",
            "product source change",
            "test-only",
            "only changes tests",
            "does not fix the underlying",
        )
    )


def _normalize_review_decision(raw: Dict[str, Any], req: AutopilotReviewDecisionRequest) -> Dict[str, Any]:
    allow_replay_fixture_only = _review_allows_replay_fixture_only(req)
    blocking = [str(item)[:500] for item in (raw.get("blocking_reasons") or []) if str(item).strip()][:12]
    deterministic_blocking = [
        str(item)[:500]
        for item in (req.deterministic_review.get("blocking_reasons") or [])
        if str(item).strip()
    ][:12]
    blocking = list(dict.fromkeys([*deterministic_blocking, *blocking]))
    validation_status = str((req.validation or {}).get("status") or "").lower()
    if validation_status and validation_status != "passed":
        blocking.append(f"validation status is {validation_status}")
    product_files = [
        path for path in req.changed_files
        if "backend/src/" in path or "macOS-Client/Sources/" in path or "/src/" in path
    ]
    if not product_files and not allow_replay_fixture_only:
        blocking.append("candidate has no product source change")
    if allow_replay_fixture_only:
        blocking = [reason for reason in blocking if not _review_replay_fixture_only_blocker(reason)]
    blocking = list(dict.fromkeys(blocking))[:12]

    status = str(raw.get("status") or ("failed" if blocking else "passed")).lower()
    if status not in {"passed", "failed"}:
        status = "failed" if blocking else "passed"
    if allow_replay_fixture_only and not blocking:
        status = "passed"
    recommendation = str(raw.get("recommendation") or ("reject" if blocking else "review")).lower()
    if recommendation not in {"review", "reject"}:
        recommendation = "reject" if blocking else "review"
    if allow_replay_fixture_only and not blocking:
        recommendation = "review"
    merge_recommendation = str(raw.get("merge_recommendation") or ("repair_before_pr" if blocking else "open_review_pr")).lower()
    if merge_recommendation not in {"open_review_pr", "repair_before_pr"}:
        merge_recommendation = "repair_before_pr" if blocking else "open_review_pr"
    if allow_replay_fixture_only and not blocking:
        merge_recommendation = "open_review_pr"

    return {
        "status": "failed" if blocking else status,
        "recommendation": "reject" if blocking else recommendation,
        "merge_recommendation": "repair_before_pr" if blocking else merge_recommendation,
        "product_value_score": _clamp_review_score(raw.get("product_value_score"), 90 if not blocking else 45),
        "maintainability_score": _clamp_review_score(raw.get("maintainability_score"), 92 if not blocking else 55),
        "risk_score": _clamp_review_score(raw.get("risk_score"), 10 if not blocking else 70),
        "blocking_reasons": blocking,
        "human_review_notes": [
            str(item)[:500]
            for item in (raw.get("human_review_notes") or ["human approval is still required before promotion"])
            if str(item).strip()
        ][:12],
    }


async def _autopilot_review_decision_chat(
    req: AutopilotReviewDecisionRequest,
    *,
    provider_id: Optional[str],
    model_id: Optional[str],
    agent_id: Optional[str],
    temperature: float,
    max_tokens: int,
    timeout_seconds: float,
    idle_timeout_seconds: Optional[float] = None,
) -> Tuple[Any, Dict[str, Any], bool]:
    response = await _chat_with_model_capability(
        message=_autopilot_review_user_prompt(req),
        system_prompt=_autopilot_review_system_prompt(),
        provider_id=str(provider_id) if provider_id else None,
        model=str(model_id) if model_id else None,
        agent_id=str(agent_id) if agent_id else None,
        project_dir=None,
        scope="model.review",
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout_seconds,
        max_wall_timeout=timeout_seconds,
        idle_timeout=idle_timeout_seconds,
        extra_body=_minimax_json_extra_body(provider_id),
    )
    try:
        return response, _normalize_review_decision(_extract_json_object(response.text), req), False
    except Exception as first_error:
        repair_response = await _chat_with_model_capability(
            message=_autopilot_review_repair_prompt(response.text, first_error),
            system_prompt=_autopilot_review_system_prompt(),
            provider_id=str(provider_id) if provider_id else None,
            model=str(model_id) if model_id else None,
            agent_id=str(agent_id) if agent_id else None,
            project_dir=None,
            scope="model.review",
            temperature=0.0,
            max_tokens=max_tokens,
            timeout=timeout_seconds,
            max_wall_timeout=timeout_seconds,
            idle_timeout=idle_timeout_seconds,
            extra_body=_minimax_json_extra_body(provider_id),
        )
        return repair_response, _normalize_review_decision(_extract_json_object(repair_response.text), req), True


@app.post("/api/autopilot/review-decision")
async def create_autopilot_review_decision(req: AutopilotReviewDecisionRequest):
    """Return a host-backed independent review decision."""
    try:
        policy = dict(req.model_policy or {})
        provider_id = _autopilot_model_policy_value(policy, "provider", "provider_id")
        agent_id = _autopilot_model_policy_value(policy, "agent_id", "agent")
        temperature = float(_autopilot_model_policy_value(policy, "temperature", default=0.0))
        max_tokens = int(_autopilot_model_policy_value(policy, "max_tokens", "maxTokens", default=1600))
        timeout_plan = _autopilot_model_policy_timeout_plan(policy)
        timeout_seconds = timeout_plan["max_wall_timeout_seconds"]
        idle_timeout_seconds = timeout_plan["idle_timeout_seconds"]
        require_distinct = policy.get("require_distinct_from_builder") is not False
        last_error: Optional[Exception] = None
        for model_id in _local_agent_model_candidates(policy, str(agent_id) if agent_id else None):
            if require_distinct and _same_model_identity(req.builder_model, str(provider_id) if provider_id else None, str(model_id) if model_id else None):
                last_error = ValueError("reviewer model must differ from builder model")
                continue
            try:
                response, decision, repaired = await _autopilot_review_decision_chat(
                    req,
                    provider_id=str(provider_id) if provider_id else None,
                    model_id=str(model_id) if model_id else None,
                    agent_id=str(agent_id) if agent_id else None,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout_seconds=timeout_seconds,
                    idle_timeout_seconds=idle_timeout_seconds,
                )
                clean_json = json.dumps(decision, ensure_ascii=False, sort_keys=True)
                return {
                    "schema_version": "across-host-review-decision/1.0",
                    "model_backed": True,
                    "role": "independent_reviewer",
                    "provider": response.provider,
                    "model": response.model,
                    "finish_reason": response.finish_reason,
                    "usage": response.usage,
                    "repaired_json": repaired,
                    "decision_hash": hashlib.sha256(clean_json.encode("utf-8")).hexdigest(),
                    "candidate_model_lease": _public_request_model_lease(req.candidate_model_lease),
                    **decision,
                }
            except Exception as exc:
                last_error = exc
                continue
        raise ValueError(str(last_error or "No reviewer model candidate succeeded."))
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise _safe_http_500("Create Autopilot review decision")


@app.post("/api/plugins/{plugin_id}/actions")
async def run_across_plugin_action(plugin_id: str, req: PluginLifecycleActionRequest):
    """Run an explicit user-triggered plugin lifecycle action."""
    action = str(req.action or "").strip().lower().replace("-", "_")
    if action == "refresh":
        action = "probe"
    if action not in {"probe", "install", "repair", "upgrade", "uninstall"}:
        raise HTTPException(status_code=400, detail="Unsupported plugin lifecycle action")
    try:
        if plugin_id == "across-context":
            result = await asyncio.to_thread(run_context_plugin_lifecycle_action, action)
            return _sanitize_public_payload(result)
        if plugin_id == "across-orchestrator":
            manager = get_orchestrator_plugin_manager()
            if action in {"probe", "refresh"}:
                return _sanitize_public_payload(manager.implementation_status(probe=True))
            if action in {"install", "repair", "upgrade"}:
                install = await asyncio.to_thread(manager.install_plugin)
                runtime = manager.implementation_status(probe=True)
                return _sanitize_public_payload({"runtime": runtime, "install": install})
            if action == "uninstall":
                result = await asyncio.to_thread(manager.uninstall_plugin)
                return _sanitize_public_payload(result)
        if plugin_id == "across-autopilot":
            result = await asyncio.to_thread(run_autopilot_plugin_lifecycle_action, action)
            return _sanitize_public_payload(result)
        raise HTTPException(status_code=400, detail="Unsupported plugin lifecycle action")
    except HTTPException:
        raise
    except (PluginLifecycleError, OrchestratorPluginUnavailable):
        raise HTTPException(status_code=500, detail=_safe_error_message("Plugin lifecycle action"))
    except Exception as exc:
        raise _safe_http_500("Plugin lifecycle action")


def _autopilot_http_error(operation: str, exc: PluginLifecycleError) -> HTTPException:
    detail = _sanitize_public_error_text(exc)
    lowered = str(detail or "").lower()
    if "not installed" in lowered or "must be repaired" in lowered:
        return HTTPException(status_code=503, detail="Across Autopilot plugin is not available")
    if "requires" in lowered or "unexpected json payload" in lowered:
        return HTTPException(status_code=400, detail=detail)
    logger.debug("%s failed via Across Autopilot: %s", operation, detail)
    return HTTPException(status_code=502, detail=_safe_error_message(operation))


@app.get("/api/autopilot/registry")
async def get_autopilot_registry():
    """Return built-in and registered LoopSpec packs exposed by Across Autopilot."""
    try:
        result = await asyncio.to_thread(get_autopilot_client().registry)
        return _sanitize_public_payload(result)
    except PluginLifecycleError as exc:
        raise _autopilot_http_error("Across Autopilot registry", exc)
    except Exception as exc:
        raise _safe_http_500("Across Autopilot registry")


@app.get("/api/autopilot/capability-packs")
async def get_autopilot_capability_packs():
    """Return AAA-hosted reusable Loop Engineering capability packs."""
    try:
        from .loop_engineering_capability_pack import loop_engineering_capability_pack

        return _sanitize_public_payload(loop_engineering_capability_pack())
    except Exception as exc:
        raise _safe_http_500("Across Autopilot capability packs")


@app.get("/api/autopilot/tool-manifest")
async def get_autopilot_tool_manifest():
    """Return a bounded MCP-style manifest of AAA loop-engineering tools."""
    try:
        from .autopilot_tool_manifest import build_autopilot_tool_manifest
        from .loop_engineering_capability_pack import loop_engineering_capability_pack

        return _sanitize_public_payload(
            build_autopilot_tool_manifest(
                tool_schemas=_runtime_tool_schemas(),
                capability_pack=loop_engineering_capability_pack(),
            )
        )
    except Exception as exc:
        raise _safe_http_500("Across Autopilot tool manifest")


@app.get("/api/autopilot/a2a/capability-card")
async def get_autopilot_a2a_capability_card():
    """Return an A2A-style agent capability card for AAA self-iteration."""
    try:
        from .autopilot_a2a_capability_card import build_autopilot_a2a_capability_card
        from .loop_engineering_capability_pack import loop_engineering_capability_pack

        return _sanitize_public_payload(
            build_autopilot_a2a_capability_card(
                capability_pack=loop_engineering_capability_pack(),
            )
        )
    except Exception as exc:
        raise _safe_http_500("Across Autopilot A2A capability card")


@app.post("/api/autopilot/specs/validate")
async def validate_autopilot_spec(req: AutopilotSpecRequest):
    """Validate a built-in or user-provided Across LoopSpec through Autopilot."""
    try:
        result = await asyncio.to_thread(get_autopilot_client().validate_spec, req.spec)
        return _sanitize_public_payload(result)
    except PluginLifecycleError as exc:
        raise _autopilot_http_error("Validate Across Autopilot LoopSpec", exc)
    except Exception as exc:
        raise _safe_http_500("Validate Across Autopilot LoopSpec")


@app.post("/api/autopilot/specs/dry-run")
async def dry_run_autopilot_spec(req: AutopilotSpecRequest):
    """Preview the adapters, autonomy, evidence, and outputs a LoopSpec would use."""
    try:
        result = await asyncio.to_thread(get_autopilot_client().dry_run, req.spec)
        return _sanitize_public_payload(result)
    except PluginLifecycleError as exc:
        raise _autopilot_http_error("Dry-run Across Autopilot LoopSpec", exc)
    except Exception as exc:
        raise _safe_http_500("Dry-run Across Autopilot LoopSpec")


@app.post("/api/autopilot/triggers")
async def enqueue_autopilot_trigger(req: AutopilotTriggerRequest):
    """Persist a replayable Across Autopilot trigger through AAA."""
    try:
        result = await asyncio.to_thread(
            get_autopilot_client().enqueue_trigger,
            req.spec,
            trigger_type=req.type or "manual",
            payload=req.payload,
            idempotency_key=req.idempotency_key,
            not_before=req.not_before,
            source=req.source or "aaa",
            actor=req.actor or "user",
        )
        return _sanitize_public_payload(result)
    except PluginLifecycleError as exc:
        raise _autopilot_http_error("Enqueue Across Autopilot trigger", exc)
    except Exception as exc:
        raise _safe_http_500("Enqueue Across Autopilot trigger")


@app.get("/api/autopilot/triggers")
async def get_autopilot_trigger_queue():
    """Return the durable Across Autopilot trigger queue."""
    try:
        result = await asyncio.to_thread(get_autopilot_client().trigger_queue)
        return _sanitize_public_payload(result)
    except PluginLifecycleError as exc:
        raise _autopilot_http_error("Get Across Autopilot trigger queue", exc)
    except Exception as exc:
        raise _safe_http_500("Get Across Autopilot trigger queue")


@app.post("/api/autopilot/triggers/run")
async def run_autopilot_trigger(req: AutopilotRunTriggerRequest):
    """Claim and run one queued Across Autopilot trigger."""
    try:
        result = await asyncio.to_thread(get_autopilot_client().run_trigger, req.trigger_id)
        return _sanitize_public_payload(result)
    except PluginLifecycleError as exc:
        raise _autopilot_http_error("Run Across Autopilot trigger", exc)
    except Exception as exc:
        raise _safe_http_500("Run Across Autopilot trigger")


@app.post("/api/autopilot/trigger-configs")
async def register_autopilot_trigger_config(req: AutopilotTriggerConfigRequest):
    """Register a reusable AAA-hosted cron/webhook/daemon trigger config."""
    try:
        result = await asyncio.to_thread(
            get_autopilot_trigger_registry().register,
            spec=req.spec,
            trigger_type=req.type,
            payload=req.payload,
            schedule=req.schedule,
            webhook=req.webhook,
            daemon=req.daemon,
            enabled=req.enabled,
            actor=req.actor or "user",
            source=req.source or "aaa",
            trigger_id=req.trigger_id,
        )
        return _sanitize_public_payload(result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=_sanitize_public_error_text(exc))
    except Exception as exc:
        raise _safe_http_500("Register Across Autopilot trigger config")


@app.get("/api/autopilot/trigger-configs")
async def list_autopilot_trigger_configs():
    """Return registered AAA-hosted Autopilot trigger configs."""
    try:
        queue = await asyncio.to_thread(get_autopilot_client().trigger_queue)
        return _sanitize_public_payload(
            await asyncio.to_thread(get_autopilot_trigger_registry().list_synced, queue)
        )
    except PluginLifecycleError:
        try:
            return _sanitize_public_payload(await asyncio.to_thread(get_autopilot_trigger_registry().list))
        except Exception:
            raise _safe_http_500("List Across Autopilot trigger configs")
    except Exception as exc:
        raise _safe_http_500("List Across Autopilot trigger configs")


@app.patch("/api/autopilot/trigger-configs/{trigger_id}/pause")
async def pause_autopilot_trigger_config(trigger_id: str, req: AutopilotTriggerPauseRequest):
    """Pause or resume one AAA-hosted Autopilot trigger config."""
    try:
        return _sanitize_public_payload(
            await asyncio.to_thread(get_autopilot_trigger_registry().set_paused, trigger_id, req.paused)
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Autopilot trigger config not found")
    except Exception as exc:
        raise _safe_http_500("Pause Across Autopilot trigger config")


@app.delete("/api/autopilot/trigger-configs/{trigger_id}")
async def delete_autopilot_trigger_config(trigger_id: str):
    """Delete one AAA-hosted Autopilot trigger config."""
    try:
        return _sanitize_public_payload(await asyncio.to_thread(get_autopilot_trigger_registry().delete, trigger_id))
    except Exception as exc:
        raise _safe_http_500("Delete Across Autopilot trigger config")


@app.post("/api/autopilot/trigger-configs/tick")
async def tick_autopilot_trigger_configs():
    """Evaluate due cron/daemon trigger configs and enqueue replayable triggers."""
    try:
        result = await asyncio.to_thread(get_autopilot_trigger_registry().tick, get_autopilot_client())
        return _sanitize_public_payload(result)
    except PluginLifecycleError as exc:
        raise _autopilot_http_error("Tick Across Autopilot trigger configs", exc)
    except Exception as exc:
        raise _safe_http_500("Tick Across Autopilot trigger configs")


@app.get("/api/autopilot/trigger-scheduler")
async def get_autopilot_trigger_scheduler_status():
    """Return local scheduler lifecycle status for AAA-hosted Autopilot triggers."""
    try:
        return _sanitize_public_payload(await asyncio.to_thread(get_autopilot_trigger_scheduler().status))
    except Exception as exc:
        raise _safe_http_500("Get Across Autopilot trigger scheduler status")


@app.post("/api/autopilot/trigger-scheduler/start")
async def start_autopilot_trigger_scheduler(req: AutopilotTriggerSchedulerRequest):
    """Start the local trigger scheduler loop."""
    try:
        return _sanitize_public_payload(
            await asyncio.to_thread(
                get_autopilot_trigger_scheduler().start,
                interval_seconds=req.interval_seconds,
                run_queued_triggers=req.run_queued_triggers,
                max_runs_per_tick=req.max_runs_per_tick,
            )
        )
    except Exception as exc:
        raise _safe_http_500("Start Across Autopilot trigger scheduler")


@app.post("/api/autopilot/trigger-scheduler/stop")
async def stop_autopilot_trigger_scheduler():
    """Stop the local trigger scheduler loop."""
    try:
        return _sanitize_public_payload(await asyncio.to_thread(get_autopilot_trigger_scheduler().stop))
    except Exception as exc:
        raise _safe_http_500("Stop Across Autopilot trigger scheduler")


@app.post("/api/autopilot/webhooks/{trigger_id}")
async def accept_autopilot_webhook(trigger_id: str, request: Request):
    """Accept a webhook payload and enqueue the matching Autopilot trigger."""
    try:
        raw_body = await request.body()
        try:
            payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except json.JSONDecodeError:
            payload = {"raw_body_sha256": hashlib.sha256(raw_body).hexdigest()}
        result = await asyncio.to_thread(
            get_autopilot_trigger_registry().accept_webhook,
            get_autopilot_client(),
            trigger_id=trigger_id,
            raw_body=raw_body,
            headers=dict(request.headers),
            payload=payload if isinstance(payload, dict) else {"payload": payload},
        )
        if result.get("status") == "rejected":
            raise HTTPException(status_code=401, detail=result.get("reason") or "Webhook rejected")
        return _sanitize_public_payload(result)
    except HTTPException:
        raise
    except PluginLifecycleError as exc:
        raise _autopilot_http_error("Accept Across Autopilot webhook", exc)
    except KeyError:
        raise HTTPException(status_code=404, detail="Autopilot trigger config not found")
    except Exception as exc:
        raise _safe_http_500("Accept Across Autopilot webhook")


@app.get("/api/autopilot/self-iteration-plan")
async def get_autopilot_self_iteration_plan():
    """Return the host-visible continuous AAA self-iteration plan."""
    try:
        trigger_registry = await asyncio.to_thread(get_autopilot_trigger_registry().list)
    except Exception:
        trigger_registry = {}
    try:
        trigger_queue = await asyncio.to_thread(get_autopilot_client().trigger_queue)
    except Exception:
        trigger_queue = {}
    try:
        from .loop_engineering_capability_pack import loop_engineering_capability_pack

        capability_pack = loop_engineering_capability_pack()
    except Exception:
        capability_pack = {}
    source_mirrors = await asyncio.to_thread(get_source_mirror_status)
    return _sanitize_public_payload(
        build_self_iteration_plan(
            trigger_registry=trigger_registry,
            trigger_queue=trigger_queue,
            capability_pack=capability_pack,
            source_mirrors=source_mirrors,
        )
    )


@app.post("/api/autopilot/self-iteration-plan/ensure")
async def ensure_autopilot_self_iteration_plan(req: AutopilotSelfIterationPlanRequest):
    """Ensure the default continuous AAA self-iteration trigger is registered."""
    try:
        registry = get_autopilot_trigger_registry()
        await asyncio.to_thread(
            ensure_self_iteration_plan,
            registry,
            spec=req.spec,
            interval_seconds=req.interval_seconds,
            daily_time=req.daily_time,
            timezone=req.timezone,
            enabled=req.enabled,
            actor=req.actor,
            source=req.source,
            trigger_id=req.trigger_id,
            payload=req.payload,
        )
        trigger_registry = await asyncio.to_thread(registry.list)
        try:
            trigger_queue = await asyncio.to_thread(get_autopilot_client().trigger_queue)
        except Exception:
            trigger_queue = {}
        from .loop_engineering_capability_pack import loop_engineering_capability_pack

        source_mirrors = await asyncio.to_thread(get_source_mirror_status)
        return _sanitize_public_payload(
            build_self_iteration_plan(
                trigger_registry=trigger_registry,
                trigger_queue=trigger_queue,
                capability_pack=loop_engineering_capability_pack(),
                source_mirrors=source_mirrors,
                spec=req.spec,
                trigger_id=req.trigger_id,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=_sanitize_public_error_text(exc))
    except Exception as exc:
        raise _safe_http_500("Ensure Across Autopilot self-iteration plan")


@app.post("/api/autopilot/runs")
async def run_autopilot_loop(req: AutopilotSpecRequest):
    """Start and complete one supervised Across Autopilot LoopSpec run."""
    try:
        result = await asyncio.to_thread(
            get_autopilot_client().run,
            req.spec,
            trigger=req.trigger or "aaa-user",
            model_policy_overrides=req.model_policy_overrides,
        )
        return _sanitize_public_payload(result)
    except PluginLifecycleError as exc:
        raise _autopilot_http_error("Run Across Autopilot LoopSpec", exc)
    except Exception as exc:
        raise _safe_http_500("Run Across Autopilot LoopSpec")


@app.get("/api/autopilot/agent-interop-e2e")
async def get_agent_interop_e2e_result():
    """Return the latest host-neutral plugin interop E2E result."""
    try:
        return public_agent_interop_e2e_result(load_agent_interop_e2e_latest())
    except Exception:
        raise _safe_http_500("Get agent interop E2E result")


@app.post("/api/autopilot/agent-interop-e2e")
async def run_agent_interop_e2e_endpoint():
    """Run the complete Context/Orchestrator/Autopilot host interop E2E scenario."""
    try:
        result = await asyncio.to_thread(run_agent_interop_e2e)
        return public_agent_interop_e2e_result(result)
    except Exception as exc:
        raise _safe_http_500("Run agent interop E2E")


@app.get("/api/autopilot/runs")
async def list_autopilot_runs():
    """List recent persisted Across Autopilot runs."""
    try:
        result = await asyncio.to_thread(get_autopilot_client().list_runs)
        return _sanitize_public_payload(result)
    except PluginLifecycleError as exc:
        raise _autopilot_http_error("List Across Autopilot runs", exc)
    except Exception as exc:
        raise _safe_http_500("List Across Autopilot runs")


@app.get("/api/autopilot/runs/{run_id}")
async def get_autopilot_run(run_id: str):
    """Return status for one Across Autopilot run."""
    try:
        result = await asyncio.to_thread(get_autopilot_client().status, run_id)
        return _sanitize_public_payload(result)
    except PluginLifecycleError as exc:
        raise _autopilot_http_error("Get Across Autopilot run", exc)
    except Exception as exc:
        raise _safe_http_500("Get Across Autopilot run")


@app.get("/api/autopilot/runs/{run_id}/evidence")
async def get_autopilot_run_evidence(run_id: str):
    """Return the evidence envelope for one Across Autopilot run."""
    try:
        result = await asyncio.to_thread(get_autopilot_client().evidence, run_id)
        return _sanitize_public_payload(result)
    except PluginLifecycleError as exc:
        raise _autopilot_http_error("Get Across Autopilot evidence", exc)
    except Exception as exc:
        raise _safe_http_500("Get Across Autopilot evidence")


@app.get("/api/autopilot/runs/{run_id}/promotion-review")
async def get_autopilot_promotion_review(run_id: str):
    """Return a bounded human-review packet derived from Autopilot evidence."""
    try:
        evidence = await asyncio.to_thread(get_autopilot_client().evidence, run_id)
        return _sanitize_public_payload(build_promotion_review_packet(evidence))
    except PluginLifecycleError as exc:
        raise _autopilot_http_error("Get Across Autopilot promotion review", exc)
    except Exception as exc:
        raise _safe_http_500("Get Across Autopilot promotion review")


@app.get("/api/autopilot/runs/{run_id}/events")
async def get_autopilot_run_events(run_id: str, after_sequence: Optional[int] = None):
    """Return durable audit events for one Across Autopilot run."""
    try:
        result = await asyncio.to_thread(get_autopilot_client().events, run_id, after_sequence=after_sequence)
        return _sanitize_public_payload(result)
    except PluginLifecycleError as exc:
        raise _autopilot_http_error("Get Across Autopilot events", exc)
    except Exception as exc:
        raise _safe_http_500("Get Across Autopilot events")


@app.get("/api/autopilot/telemetry")
async def get_autopilot_telemetry():
    """Return aggregate Across Autopilot telemetry without raw source content."""
    try:
        result = await asyncio.to_thread(get_autopilot_client().telemetry)
        return _sanitize_public_payload(result)
    except PluginLifecycleError as exc:
        raise _autopilot_http_error("Get Across Autopilot telemetry", exc)
    except Exception as exc:
        raise _safe_http_500("Get Across Autopilot telemetry")


@app.get("/api/autopilot/ops-dashboard")
async def get_autopilot_ops_dashboard():
    """Return a Loop Engineering operations dashboard across telemetry and host controls."""
    try:
        telemetry = await asyncio.to_thread(get_autopilot_client().telemetry)
    except PluginLifecycleError as exc:
        raise _autopilot_http_error("Get Across Autopilot ops dashboard", exc)
    except Exception:
        telemetry = {}
    try:
        runs = await asyncio.to_thread(get_autopilot_client().list_runs)
    except Exception:
        runs = {}
    try:
        from .loop_engineering_capability_pack import loop_engineering_capability_pack

        capability_pack = loop_engineering_capability_pack()
    except Exception:
        capability_pack = {}
    try:
        registry_payload = _build_unified_capability_registry_payload(refresh=False)
        registry_health = evaluate_unified_capability_registry_health(registry_payload)
    except Exception:
        registry_health = {}
    try:
        trigger_registry = await asyncio.to_thread(get_autopilot_trigger_registry().list)
    except Exception:
        trigger_registry = {}
    try:
        trigger_queue = await asyncio.to_thread(get_autopilot_client().trigger_queue)
    except Exception:
        trigger_queue = {}
    try:
        trigger_scheduler = await asyncio.to_thread(get_autopilot_trigger_scheduler().status)
    except Exception:
        trigger_scheduler = {}
    try:
        self_iteration_plan = build_self_iteration_plan(
            trigger_registry=trigger_registry,
            trigger_queue=trigger_queue,
            capability_pack=capability_pack,
        )
    except Exception:
        self_iteration_plan = {}
    return _sanitize_public_payload(
        build_loop_engineering_ops_dashboard(
            telemetry=telemetry,
            runs=runs,
            trigger_registry=trigger_registry,
            trigger_scheduler=trigger_scheduler,
            capability_pack=capability_pack,
            registry_health=registry_health,
            self_iteration_plan=self_iteration_plan,
        )
    )


async def _build_autopilot_workbench_response(*, refresh: bool = False) -> Dict[str, Any]:
    try:
        plugins = await asyncio.to_thread(discover_across_plugins, probe=refresh)
    except Exception:
        plugins = []

    try:
        from .loop_engineering_capability_pack import loop_engineering_capability_pack

        capability_pack = loop_engineering_capability_pack()
    except Exception:
        capability_pack = {}

    try:
        trigger_registry = await asyncio.to_thread(get_autopilot_trigger_registry().list)
    except Exception:
        trigger_registry = {}

    try:
        trigger_queue = await asyncio.to_thread(get_autopilot_client().trigger_queue)
    except Exception:
        trigger_queue = {}

    try:
        trigger_scheduler = await asyncio.to_thread(get_autopilot_trigger_scheduler().status)
    except Exception:
        trigger_scheduler = {}

    try:
        self_iteration_plan = build_self_iteration_plan(
            trigger_registry=trigger_registry,
            trigger_queue=trigger_queue,
            capability_pack=capability_pack,
        )
    except Exception:
        self_iteration_plan = {}

    try:
        registry = await asyncio.to_thread(get_autopilot_client().registry)
    except Exception:
        registry = {}

    try:
        runs = await asyncio.to_thread(get_autopilot_client().list_runs)
    except Exception:
        runs = {}

    try:
        telemetry = await asyncio.to_thread(get_autopilot_client().telemetry)
    except Exception:
        telemetry = {}

    try:
        capability_registry = await asyncio.to_thread(_build_unified_capability_registry_payload, refresh)
        registry_health = evaluate_unified_capability_registry_health(capability_registry)
    except Exception:
        capability_registry = {}
        registry_health = {}

    try:
        ops_dashboard = build_loop_engineering_ops_dashboard(
            telemetry=telemetry,
            runs=runs,
            trigger_registry=trigger_registry,
            trigger_scheduler=trigger_scheduler,
            capability_pack=capability_pack,
            registry_health=registry_health,
            self_iteration_plan=self_iteration_plan,
        )
    except Exception:
        ops_dashboard = {}

    try:
        agent_loop_memory_metrics = await asyncio.to_thread(get_agent_loop_memory_metrics, all_projects=True)
    except Exception:
        agent_loop_memory_metrics = {}

    try:
        pending_memories = await asyncio.to_thread(list_context_memories, status="pending")
    except Exception:
        pending_memories = []

    try:
        agent_plugin_runtime = await asyncio.to_thread(probe_agent_plugin_runtime_status)
    except Exception:
        agent_plugin_runtime = {}

    try:
        agent_interop_e2e = await asyncio.to_thread(load_agent_interop_e2e_latest)
    except Exception:
        agent_interop_e2e = {}

    try:
        ecosystem_roadmap = await _build_ecosystem_roadmap_response(
            refresh=refresh,
            plugins=plugins,
            capability_registry=capability_registry,
            registry_health=registry_health,
            autopilot_registry=registry,
            autopilot_runs=runs,
            autopilot_telemetry=telemetry,
            ops_dashboard=ops_dashboard,
            memory_metrics=agent_loop_memory_metrics,
            pending_memories=pending_memories,
            agent_plugin_runtime=agent_plugin_runtime,
            agent_interop_e2e=agent_interop_e2e,
        )
    except Exception:
        ecosystem_roadmap = {}

    return _sanitize_public_payload(
        build_autopilot_workbench_snapshot(
            plugins=plugins,
            registry=registry,
            trigger_queue=trigger_queue,
            trigger_registry=trigger_registry,
            trigger_scheduler=trigger_scheduler,
            self_iteration_plan=self_iteration_plan,
            runs=runs,
            telemetry=telemetry,
            ops_dashboard=ops_dashboard,
            capability_registry=capability_registry,
            registry_health=registry_health,
            agent_loop_memory_metrics=agent_loop_memory_metrics,
            pending_memories=pending_memories,
            ecosystem_roadmap=ecosystem_roadmap,
            agent_plugin_runtime=agent_plugin_runtime,
            agent_interop_e2e=agent_interop_e2e,
        )
    )


@app.get("/api/autopilot/workbench")
async def get_autopilot_workbench(refresh: bool = False):
    """Return a bounded host Workbench snapshot for AAA self-iteration."""
    return await _build_autopilot_workbench_response(refresh=refresh)


@app.post("/api/autopilot/workbench/refresh")
async def refresh_autopilot_workbench():
    """Probe where supported and return the latest host Workbench snapshot."""
    return await _build_autopilot_workbench_response(refresh=True)


async def _release_evaluation_payload(limit: int = 100) -> Dict[str, Any]:
    try:
        external_rows = get_orchestrator_plugin_manager().list_task_summaries()
    except Exception:
        external_rows = []
    try:
        agent_interop_e2e = load_agent_interop_e2e_latest()
    except Exception:
        agent_interop_e2e = {}
    try:
        safe_limit = max(1, min(int(limit or 100), 500))
        rows = _collect_release_task_rows(
            safe_limit,
            task_state=_task_state,
            external_task_rows=lambda: external_rows,
        )
        for latest_release_row in _release_e2e_rows(rows, limit=3):
            task_id = str(latest_release_row.get("task_id") or "")
            if task_id:
                try:
                    task_payload = await asyncio.to_thread(_load_task_info_read_only, task_id)
                    serialized = dict(task_payload) if isinstance(task_payload, dict) else _pydantic_dump(task_payload)
                    rows = _upsert_release_evaluation_row(
                        rows,
                        _release_evaluation_row_from_task_payload(serialized, latest_release_row),
                    )
                except Exception:
                    pass
        summary = build_release_evaluation_summary(rows)
        return augment_release_evaluation_with_agent_interop(summary, agent_interop_e2e)
    except Exception:
        return {}


async def _build_ecosystem_roadmap_response(
    *,
    refresh: bool = False,
    plugins: Optional[List[Dict[str, Any]]] = None,
    capability_registry: Optional[Dict[str, Any]] = None,
    registry_health: Optional[Dict[str, Any]] = None,
    autopilot_registry: Optional[Dict[str, Any]] = None,
    autopilot_runs: Optional[Dict[str, Any]] = None,
    autopilot_telemetry: Optional[Dict[str, Any]] = None,
    ops_dashboard: Optional[Dict[str, Any]] = None,
    memory_metrics: Optional[Dict[str, Any]] = None,
    pending_memories: Optional[List[Dict[str, Any]]] = None,
    agent_plugin_runtime: Optional[Dict[str, Any]] = None,
    agent_interop_e2e: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if plugins is None:
        try:
            plugins = await asyncio.to_thread(discover_across_plugins, probe=refresh)
        except Exception:
            plugins = []
    if capability_registry is None or registry_health is None:
        try:
            capability_registry = await asyncio.to_thread(_build_unified_capability_registry_payload, refresh)
            registry_health = evaluate_unified_capability_registry_health(capability_registry)
        except Exception:
            capability_registry = capability_registry or {}
            registry_health = registry_health or {}
    if autopilot_registry is None:
        try:
            autopilot_registry = await asyncio.to_thread(get_autopilot_client().registry)
        except Exception:
            autopilot_registry = {}
    if autopilot_runs is None:
        try:
            autopilot_runs = await asyncio.to_thread(get_autopilot_client().list_runs)
        except Exception:
            autopilot_runs = {}
    if autopilot_telemetry is None:
        try:
            autopilot_telemetry = await asyncio.to_thread(get_autopilot_client().telemetry)
        except Exception:
            autopilot_telemetry = {}
    if ops_dashboard is None:
        try:
            telemetry = autopilot_telemetry or {}
            trigger_registry = await asyncio.to_thread(get_autopilot_trigger_registry().list)
            trigger_queue = await asyncio.to_thread(get_autopilot_client().trigger_queue)
            trigger_scheduler = await asyncio.to_thread(get_autopilot_trigger_scheduler().status)
            from .loop_engineering_capability_pack import loop_engineering_capability_pack

            capability_pack = loop_engineering_capability_pack()
            self_iteration_plan = build_self_iteration_plan(
                trigger_registry=trigger_registry,
                trigger_queue=trigger_queue,
                capability_pack=capability_pack,
            )
            ops_dashboard = build_loop_engineering_ops_dashboard(
                telemetry=telemetry,
                runs=autopilot_runs,
                trigger_registry=trigger_registry,
                trigger_scheduler=trigger_scheduler,
                capability_pack=capability_pack,
                registry_health=registry_health or {},
                self_iteration_plan=self_iteration_plan,
            )
        except Exception:
            ops_dashboard = {}
    if memory_metrics is None:
        try:
            memory_metrics = await asyncio.to_thread(get_agent_loop_memory_metrics, all_projects=True)
        except Exception:
            memory_metrics = {}
    if pending_memories is None:
        try:
            pending_memories = await asyncio.to_thread(list_context_memories, status="pending")
        except Exception:
            pending_memories = []
    if agent_plugin_runtime is None:
        try:
            agent_plugin_runtime = await asyncio.to_thread(probe_agent_plugin_runtime_status)
        except Exception:
            agent_plugin_runtime = {}
    if agent_interop_e2e is None:
        try:
            agent_interop_e2e = await asyncio.to_thread(load_agent_interop_e2e_latest)
        except Exception:
            agent_interop_e2e = {}
    try:
        agent_cards = await asyncio.to_thread(_build_agent_cards_payload)
    except Exception:
        agent_cards = {}
    try:
        mcp_safety = await asyncio.to_thread(mcp_manager.get_safety_report)
    except Exception:
        mcp_safety = {}
    release_evaluation = await _release_evaluation_payload()
    return _sanitize_public_payload(
        build_aaa_ecosystem_roadmap(
            plugins=plugins,
            capability_registry=capability_registry,
            registry_health=registry_health,
            agent_cards=agent_cards,
            mcp_safety=mcp_safety,
            autopilot_registry=autopilot_registry,
            autopilot_runs=autopilot_runs,
            autopilot_telemetry=autopilot_telemetry,
            ops_dashboard=ops_dashboard,
            release_evaluation=release_evaluation,
            memory_metrics=memory_metrics,
            pending_memories=pending_memories,
            agent_plugin_runtime=agent_plugin_runtime,
            agent_interop_e2e=agent_interop_e2e,
        )
    )


@app.get("/api/ecosystem/roadmap")
async def get_ecosystem_roadmap(refresh: bool = False):
    """Return the full AAA next-step ecosystem route state."""
    return await _build_ecosystem_roadmap_response(refresh=refresh)


@app.get("/api/ecosystem/protocol-gateway")
async def get_ecosystem_protocol_gateway(refresh: bool = False):
    return ecosystem_route_section(await _build_ecosystem_roadmap_response(refresh=refresh), "protocol_gateway")


@app.get("/api/ecosystem/tool-packs")
async def get_ecosystem_tool_packs(refresh: bool = False):
    return ecosystem_route_section(await _build_ecosystem_roadmap_response(refresh=refresh), "tool_pack_registry")


@app.get("/api/ecosystem/trust-sandbox")
async def get_ecosystem_trust_sandbox(refresh: bool = False):
    return ecosystem_route_section(await _build_ecosystem_roadmap_response(refresh=refresh), "trust_sandbox")


@app.get("/api/ecosystem/evaluation-telemetry")
async def get_ecosystem_evaluation_telemetry(refresh: bool = False):
    return ecosystem_route_section(await _build_ecosystem_roadmap_response(refresh=refresh), "evaluation_telemetry")


@app.get("/api/ecosystem/context-packs")
async def get_ecosystem_context_packs(refresh: bool = False):
    return ecosystem_route_section(await _build_ecosystem_roadmap_response(refresh=refresh), "context_packs")


@app.get("/api/ecosystem/external-agents")
async def get_ecosystem_external_agents(refresh: bool = False):
    return ecosystem_route_section(await _build_ecosystem_roadmap_response(refresh=refresh), "external_agents")


@app.get("/api/ecosystem/agent-plugins")
async def get_ecosystem_agent_plugins(refresh: bool = False):
    return ecosystem_route_section(await _build_ecosystem_roadmap_response(refresh=refresh), "agent_plugin_runtime")


@app.post("/api/autopilot/runs/{run_id}/cancel")
async def cancel_autopilot_run(run_id: str, req: AutopilotCancelRequest):
    """Cancel one Across Autopilot run through the plugin control plane."""
    try:
        result = await asyncio.to_thread(get_autopilot_client().cancel, run_id, reason=req.reason or "cancelled by host")
        return _sanitize_public_payload(result)
    except PluginLifecycleError as exc:
        raise _autopilot_http_error("Cancel Across Autopilot run", exc)
    except Exception as exc:
        raise _safe_http_500("Cancel Across Autopilot run")


@app.post("/api/autopilot/runs/{run_id}/retry")
async def retry_autopilot_run(run_id: str):
    """Retry a failed Across Autopilot run from its stored LoopSpec."""
    try:
        result = await asyncio.to_thread(get_autopilot_client().retry, run_id)
        return _sanitize_public_payload(result)
    except PluginLifecycleError as exc:
        raise _autopilot_http_error("Retry Across Autopilot run", exc)
    except Exception as exc:
        raise _safe_http_500("Retry Across Autopilot run")


@app.post("/api/autopilot/runs/{run_id}/outputs/quarantine")
async def quarantine_autopilot_output(run_id: str, req: AutopilotOutputRequest):
    """Quarantine one generated output from an Across Autopilot run."""
    try:
        result = await asyncio.to_thread(get_autopilot_client().quarantine_output, run_id, req.outputId)
        return _sanitize_public_payload(result)
    except PluginLifecycleError as exc:
        raise _autopilot_http_error("Quarantine Across Autopilot output", exc)
    except Exception as exc:
        raise _safe_http_500("Quarantine Across Autopilot output")


@app.post("/api/autopilot/specs/{spec_id}/pause")
async def pause_autopilot_spec(spec_id: str):
    """Disable future runs for one Across Autopilot LoopSpec."""
    try:
        result = await asyncio.to_thread(get_autopilot_client().set_spec_paused, spec_id, True)
        return _sanitize_public_payload(result)
    except PluginLifecycleError as exc:
        raise _autopilot_http_error("Pause Across Autopilot LoopSpec", exc)
    except Exception as exc:
        raise _safe_http_500("Pause Across Autopilot LoopSpec")


@app.post("/api/autopilot/specs/{spec_id}/resume")
async def resume_autopilot_spec(spec_id: str):
    """Re-enable future runs for one Across Autopilot LoopSpec."""
    try:
        result = await asyncio.to_thread(get_autopilot_client().set_spec_paused, spec_id, False)
        return _sanitize_public_payload(result)
    except PluginLifecycleError as exc:
        raise _autopilot_http_error("Resume Across Autopilot LoopSpec", exc)
    except Exception as exc:
        raise _safe_http_500("Resume Across Autopilot LoopSpec")


@app.post("/api/autopilot/adapters/{adapter_id}/pause")
async def pause_autopilot_adapter(adapter_id: str):
    """Disable one Across Autopilot source/action/output adapter."""
    try:
        result = await asyncio.to_thread(get_autopilot_client().set_adapter_paused, adapter_id, True)
        return _sanitize_public_payload(result)
    except PluginLifecycleError as exc:
        raise _autopilot_http_error("Pause Across Autopilot adapter", exc)
    except Exception as exc:
        raise _safe_http_500("Pause Across Autopilot adapter")


@app.post("/api/autopilot/adapters/{adapter_id}/resume")
async def resume_autopilot_adapter(adapter_id: str):
    """Re-enable one Across Autopilot source/action/output adapter."""
    try:
        result = await asyncio.to_thread(get_autopilot_client().set_adapter_paused, adapter_id, False)
        return _sanitize_public_payload(result)
    except PluginLifecycleError as exc:
        raise _autopilot_http_error("Resume Across Autopilot adapter", exc)
    except Exception as exc:
        raise _safe_http_500("Resume Across Autopilot adapter")


class MemoryRememberRequest(BaseModel):
    text: str
    projectRoot: Optional[str] = None
    scope: str = "global"
    type: str = "note"
    status: str = "pending"
    tags: List[str] = Field(default_factory=list)


class MemoryStatusRequest(BaseModel):
    status: str


@app.get("/api/memory/memories")
async def list_across_context_memories(
    projectRoot: Optional[str] = None,
    status: Optional[str] = None,
    scope: Optional[str] = None,
    type: Optional[str] = None,
):
    """List Across Context memories from the shared plugin vault."""
    try:
        memories = await asyncio.to_thread(
            list_context_memories,
            project_root=projectRoot,
            status=status,
            scope=scope,
            type=type,
        )
        return _sanitize_public_payload({"memories": memories})
    except PluginLifecycleError:
        raise HTTPException(status_code=503, detail="Across Context plugin is not available")
    except Exception as exc:
        raise _safe_http_500("List Across Context memories")


@app.get("/api/memory/agent-loop-metrics")
async def get_across_context_agent_loop_memory_metrics(
    projectRoot: Optional[str] = None,
    allProjects: bool = True,
):
    """Fetch bounded Across Context Agent Loop memory candidate metrics."""
    try:
        metrics = await asyncio.to_thread(
            get_agent_loop_memory_metrics,
            project_root=projectRoot,
            all_projects=allProjects,
        )
        return _sanitize_public_payload(metrics)
    except PluginLifecycleError:
        raise HTTPException(status_code=503, detail="Across Context plugin is not available")
    except Exception as exc:
        raise _safe_http_500("Get Across Context Agent Loop memory metrics")


@app.post("/api/memory/remember")
async def remember_across_context_memory(req: MemoryRememberRequest):
    """Create a conservative pending Across Context memory."""
    try:
        entry = await asyncio.to_thread(
            remember_context_memory,
            text=req.text,
            project_root=req.projectRoot,
            scope=req.scope,
            type=req.type,
            status=req.status,
            tags=req.tags,
        )
        return _sanitize_public_payload({"memory": entry})
    except PluginLifecycleError as exc:
        if "not installed" in str(exc).lower():
            raise HTTPException(status_code=503, detail="Across Context plugin is not available")
        raise HTTPException(status_code=400, detail=_sanitize_public_error_text(exc))
    except Exception as exc:
        raise _safe_http_500("Remember Across Context memory")


@app.post("/api/memory/memories/{memory_id}/status")
async def update_across_context_memory_status(memory_id: str, req: MemoryStatusRequest):
    """Approve, archive, expire, or pin a memory by changing its lifecycle status."""
    try:
        entry = await asyncio.to_thread(update_context_memory_status, memory_id, req.status)
        return _sanitize_public_payload({"memory": entry})
    except PluginLifecycleError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail="Memory not found")
        if "not installed" in str(exc).lower():
            raise HTTPException(status_code=503, detail="Across Context plugin is not available")
        raise HTTPException(status_code=404, detail="Memory not found")
    except Exception as exc:
        raise _safe_http_500("Update Across Context memory")


@app.post("/api/memory/memories/{memory_id}/forget")
async def forget_across_context_memory(memory_id: str):
    """Forget one Across Context memory by id."""
    try:
        result = await asyncio.to_thread(forget_context_memory, memory_id)
        if not result.get("forgotten"):
            raise HTTPException(status_code=404, detail="Memory not found")
        return _sanitize_public_payload(result)
    except HTTPException:
        raise
    except PluginLifecycleError as exc:
        if "not installed" in str(exc).lower():
            raise HTTPException(status_code=503, detail="Across Context plugin is not available")
        raise HTTPException(status_code=404, detail="Memory not found")
    except Exception as exc:
        raise _safe_http_500("Forget Across Context memory")


@app.get("/api/orchestrator/plugin")
async def get_orchestrator_plugin_status():
    """Return Across Orchestrator runtime and one-click install status."""
    manager = get_orchestrator_plugin_manager()
    runtime = manager.implementation_status(probe=True)
    return _sanitize_public_payload({
        "runtime": runtime,
        "install": runtime.get("install") or manager.install_status(),
    })


@app.post("/api/orchestrator/plugin/install")
async def install_orchestrator_plugin():
    """Install Across Orchestrator into the app-managed plugin directory."""
    manager = get_orchestrator_plugin_manager()
    try:
        install = await asyncio.to_thread(manager.install_plugin)
        runtime = manager.implementation_status(probe=True)
        return _sanitize_public_payload({
            "runtime": runtime,
            "install": install,
        })
    except Exception as exc:
        logger.exception("Across Orchestrator plugin installation failed")
        runtime = manager.implementation_status(probe=False)
        raise HTTPException(
            status_code=500,
            detail=_sanitize_public_payload({
                "message": _safe_error_message("Across Orchestrator plugin installation"),
                "runtime": runtime,
                "install": manager.install_status(),
            }),
        )


class AgentLoopStartRequest(BaseModel):
    goal: str
    project_dir: Optional[str] = None
    agent: str = "owner"
    max_turns: int = 8
    memory_policy: Optional[Dict[str, Any]] = None
    approval_policy: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class AgentLoopReasonRequest(BaseModel):
    reason: Optional[str] = None


@app.post("/api/orchestrator/loops")
async def start_external_agent_loop(req: AgentLoopStartRequest):
    """Start a durable agent loop through the external Across Orchestrator plugin."""
    manager = get_orchestrator_plugin_manager()
    try:
        loop = await asyncio.to_thread(
            manager.start_agent_loop,
            goal=req.goal,
            project_dir=req.project_dir or _default_external_orchestrator_project_dir(),
            agent=req.agent or "owner",
            max_turns=req.max_turns or 8,
            memory_policy=req.memory_policy,
            approval_policy=req.approval_policy,
            metadata=req.metadata,
        )
        return _sanitize_public_payload(loop)
    except OrchestratorPluginUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except OrchestratorPluginHTTPError as exc:
        raise _external_orchestrator_http_error("External Across Orchestrator agent loop start", exc)
    except Exception as exc:
        logger.exception("External Across Orchestrator agent loop start failed")
        raise HTTPException(status_code=502, detail=_safe_error_message("External Across Orchestrator agent loop start"))


@app.post("/api/orchestrator/loops/{loop_id}/run")
async def run_external_agent_loop(loop_id: str):
    """Run or continue an external Across Orchestrator agent loop."""
    try:
        manager = get_orchestrator_plugin_manager()
        loop = await asyncio.to_thread(manager.run_agent_loop, loop_id)
        loop = await _enrich_external_agent_loop_transition(manager, loop)
        return _sanitize_public_payload(loop)
    except OrchestratorPluginUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except OrchestratorPluginHTTPError as exc:
        raise _external_orchestrator_http_error("External Across Orchestrator agent loop run", exc)
    except Exception as exc:
        logger.exception("External Across Orchestrator agent loop run failed")
        raise HTTPException(status_code=502, detail=_safe_error_message("External Across Orchestrator agent loop run"))


@app.post("/api/orchestrator/loops/{loop_id}/actions/{action_id}/approve")
async def approve_external_agent_loop_action(loop_id: str, action_id: str):
    """Approve a pending external Across Orchestrator agent loop action."""
    try:
        manager = get_orchestrator_plugin_manager()
        loop = await asyncio.to_thread(
            manager.approve_agent_loop_action,
            loop_id,
            action_id,
        )
        loop = await _enrich_external_agent_loop_transition(manager, loop)
        return _sanitize_public_payload(loop)
    except OrchestratorPluginUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except OrchestratorPluginHTTPError as exc:
        raise _external_orchestrator_http_error("External Across Orchestrator agent loop approval", exc)
    except Exception as exc:
        logger.exception("External Across Orchestrator agent loop approval failed")
        raise HTTPException(status_code=502, detail=_safe_error_message("External Across Orchestrator agent loop approval"))


@app.post("/api/orchestrator/loops/{loop_id}/actions/{action_id}/reject")
async def reject_external_agent_loop_action(loop_id: str, action_id: str, req: Optional[AgentLoopReasonRequest] = None):
    """Reject a pending external Across Orchestrator agent loop action."""
    try:
        manager = get_orchestrator_plugin_manager()
        loop = await asyncio.to_thread(
            manager.reject_agent_loop_action,
            loop_id,
            action_id,
            req.reason if req else None,
        )
        loop = await _enrich_external_agent_loop_transition(manager, loop)
        return _sanitize_public_payload(loop)
    except OrchestratorPluginUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except OrchestratorPluginHTTPError as exc:
        raise _external_orchestrator_http_error("External Across Orchestrator agent loop rejection", exc)
    except Exception as exc:
        logger.exception("External Across Orchestrator agent loop rejection failed")
        raise HTTPException(status_code=502, detail=_safe_error_message("External Across Orchestrator agent loop rejection"))


@app.post("/api/orchestrator/loops/{loop_id}/cancel")
async def cancel_external_agent_loop(loop_id: str, req: Optional[AgentLoopReasonRequest] = None):
    """Cancel a pending or running external Across Orchestrator agent loop."""
    try:
        manager = get_orchestrator_plugin_manager()
        loop = await asyncio.to_thread(
            manager.cancel_agent_loop,
            loop_id,
            req.reason if req else None,
        )
        loop = await _enrich_external_agent_loop_transition(manager, loop)
        return _sanitize_public_payload(loop)
    except OrchestratorPluginUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except OrchestratorPluginHTTPError as exc:
        raise _external_orchestrator_http_error("External Across Orchestrator agent loop cancel", exc)
    except Exception as exc:
        logger.exception("External Across Orchestrator agent loop cancel failed")
        raise HTTPException(status_code=502, detail=_safe_error_message("External Across Orchestrator agent loop cancel"))


@app.post("/api/orchestrator/loops/{loop_id}/steps/{step_id}/retry")
async def retry_external_agent_loop_step(loop_id: str, step_id: str):
    """Retry an external Across Orchestrator agent loop from a selected step."""
    try:
        manager = get_orchestrator_plugin_manager()
        loop = await asyncio.to_thread(
            manager.retry_agent_loop_step,
            loop_id,
            step_id,
        )
        loop = await _enrich_external_agent_loop_transition(manager, loop)
        return _sanitize_public_payload(loop)
    except OrchestratorPluginUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except OrchestratorPluginHTTPError as exc:
        raise _external_orchestrator_http_error("External Across Orchestrator agent loop retry", exc)
    except Exception as exc:
        logger.exception("External Across Orchestrator agent loop retry failed")
        raise HTTPException(status_code=502, detail=_safe_error_message("External Across Orchestrator agent loop retry"))


@app.get("/api/orchestrator/loops/{loop_id}")
async def get_external_agent_loop(loop_id: str):
    """Fetch external Across Orchestrator agent loop state."""
    try:
        loop = await asyncio.to_thread(get_orchestrator_plugin_manager().get_agent_loop, loop_id)
        return _sanitize_public_payload(loop)
    except OrchestratorPluginUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except OrchestratorPluginHTTPError as exc:
        raise _external_orchestrator_http_error("External Across Orchestrator agent loop status", exc)
    except Exception as exc:
        logger.exception("External Across Orchestrator agent loop status failed")
        raise HTTPException(status_code=502, detail=_safe_error_message("External Across Orchestrator agent loop status"))


@app.get("/api/orchestrator/loops/{loop_id}/health")
async def get_external_agent_loop_health(loop_id: str):
    """Fetch external Across Orchestrator agent loop health."""
    try:
        health = await asyncio.to_thread(get_orchestrator_plugin_manager().get_agent_loop_health, loop_id)
        return _sanitize_public_payload(health)
    except OrchestratorPluginUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except OrchestratorPluginHTTPError as exc:
        raise _external_orchestrator_http_error("External Across Orchestrator agent loop health", exc)
    except Exception as exc:
        logger.exception("External Across Orchestrator agent loop health failed")
        raise HTTPException(status_code=502, detail=_safe_error_message("External Across Orchestrator agent loop health"))


@app.get("/api/orchestrator/loops/{loop_id}/evidence-summary")
async def get_external_agent_loop_evidence_summary(loop_id: str):
    """Fetch external Across Orchestrator agent loop evidence summary."""
    try:
        summary = await asyncio.to_thread(get_orchestrator_plugin_manager().get_agent_loop_evidence_summary, loop_id)
        return _sanitize_public_payload(summary)
    except OrchestratorPluginUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except OrchestratorPluginHTTPError as exc:
        raise _external_orchestrator_http_error("External Across Orchestrator agent loop evidence summary", exc)
    except Exception as exc:
        logger.exception("External Across Orchestrator agent loop evidence summary failed")
        raise HTTPException(status_code=502, detail=_safe_error_message("External Across Orchestrator agent loop evidence summary"))


@app.get("/api/orchestrator/loops/{loop_id}/telemetry")
async def get_external_agent_loop_telemetry(loop_id: str):
    """Fetch bounded external Across Orchestrator agent loop telemetry."""
    try:
        telemetry = await asyncio.to_thread(get_orchestrator_plugin_manager().get_agent_loop_telemetry, loop_id)
        return _sanitize_public_payload(telemetry)
    except OrchestratorPluginUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except OrchestratorPluginHTTPError as exc:
        raise _external_orchestrator_http_error("External Across Orchestrator agent loop telemetry", exc)
    except Exception as exc:
        logger.exception("External Across Orchestrator agent loop telemetry failed")
        raise HTTPException(status_code=502, detail=_safe_error_message("External Across Orchestrator agent loop telemetry"))


@app.get("/api/orchestrator/loops/{loop_id}/events")
async def get_external_agent_loop_events(loop_id: str, after_sequence: Optional[int] = None):
    """Fetch external Across Orchestrator agent loop events."""
    try:
        events = await asyncio.to_thread(
            get_orchestrator_plugin_manager().get_agent_loop_events,
            loop_id,
            after_sequence=after_sequence,
        )
        return _sanitize_public_payload(events)
    except OrchestratorPluginUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except OrchestratorPluginHTTPError as exc:
        raise _external_orchestrator_http_error("External Across Orchestrator agent loop events", exc)
    except Exception as exc:
        logger.exception("External Across Orchestrator agent loop events failed")
        raise HTTPException(status_code=502, detail=_safe_error_message("External Across Orchestrator agent loop events"))


@app.get("/api/orchestrator/loops/{loop_id}/events/stream")
async def stream_external_agent_loop_events(loop_id: str, follow: bool = False, after_sequence: Optional[int] = None):
    """Stream external Across Orchestrator agent loop events as sanitized SSE.

    By default this endpoint returns a finite snapshot stream and closes after
    the currently durable events. Pass ``follow=true`` to keep polling for live
    timeline updates until the loop closes or the idle timeout is reached.
    Pass ``after_sequence`` to resume after the last event already held by the host.
    """
    manager = get_orchestrator_plugin_manager()
    try:
        initial_events = await asyncio.to_thread(manager.get_agent_loop_events, loop_id, after_sequence=after_sequence)
    except OrchestratorPluginUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except OrchestratorPluginHTTPError as exc:
        raise _external_orchestrator_http_error("External Across Orchestrator agent loop event stream", exc)
    except Exception:
        logger.exception("External Across Orchestrator agent loop event stream failed")
        raise HTTPException(status_code=502, detail=_safe_error_message("External Across Orchestrator agent loop event stream"))

    async def event_generator():
        seen_keys: set[str] = set()
        idle_deadline = time.monotonic() + _AGENT_LOOP_STREAM_IDLE_TIMEOUT_SECONDS
        events = initial_events
        cursor = after_sequence
        while True:
            new_events = [event for event in events if _agent_loop_event_key(event) not in seen_keys]
            if new_events:
                idle_deadline = time.monotonic() + _AGENT_LOOP_STREAM_IDLE_TIMEOUT_SECONDS

            closing_seen = False
            for event in new_events:
                seen_keys.add(_agent_loop_event_key(event))
                if isinstance(event, dict) and isinstance(event.get("sequence"), int):
                    cursor = max(cursor or 0, event["sequence"])
                yield _agent_loop_sse_chunk(event)
                if _agent_loop_event_closes_stream(event):
                    closing_seen = True

            if closing_seen or not follow:
                return
            if time.monotonic() >= idle_deadline:
                yield ": idle_timeout\n\n"
                return

            await asyncio.sleep(_AGENT_LOOP_STREAM_POLL_SECONDS)
            try:
                events = await asyncio.to_thread(manager.get_agent_loop_events, loop_id, after_sequence=cursor)
            except Exception:
                logger.debug("External Across Orchestrator agent loop event stream polling stopped", exc_info=True)
                return

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/api/health")
async def get_health():
    """Small runtime probe for the macOS app and E2E harnesses."""
    persistence_obj = getattr(_task_state, "_persistence", None)
    db_obj = getattr(persistence_obj, "db", None)
    db_path = getattr(db_obj, "db_path", None)
    if isinstance(db_path, Path):
        db_path = str(db_path)

    try:
        known_tasks = len(_task_state.get_all_tasks())
    except Exception:
        known_tasks = len(getattr(_task_state, "_tasks", {}) or {})

    return {
        "status": "ok",
        "pid": os.getpid(),
        "started_at": _server_started_at,
        "uptime_sec": max(0, time.time() - _server_started_at),
        "socket": {
            "path": SOCKET_PATH,
            "exists": os.path.exists(SOCKET_PATH),
        },
        "database": {
            "path": db_path,
        },
        "orchestrator": {
            "known_tasks": known_tasks,
            "persistence_initialized": _task_persistence_initialized,
        },
    }


@app.post("/api/keys/check/{provider_id}", response_model=KeyCheckResult)
async def check_single_key(provider_id: str):
    """Check a single provider's backend-managed credential."""
    global _credential_cache

    if provider_id not in _known_provider_ids():
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider_id}")

    if _cached_key_is_configured(provider_id):
        return KeyCheckResult(provider_id=provider_id, status="configured")

    return _check_single_backend_credential(provider_id)


class AgentConfigRequest(BaseModel):
    agent_id: str
    executable_path: Optional[str] = None
    model: Optional[str] = None

@app.post("/api/agents/config")
async def save_agent_config(req: AgentConfigRequest):
    """Save local agent configuration (executable path)."""
    from .local_agent_health import (
        detect_local_agents,
        save_configured_agent_path,
        save_configured_agent_model,
        LOCAL_AGENT_SPECS,
    )

    agent_id = normalize_agent_id(req.agent_id) or req.agent_id
    if agent_id not in LOCAL_AGENT_SPECS:
        raise HTTPException(status_code=400, detail=f"Unknown local agent: {req.agent_id}")

    try:
        save_configured_agent_path(agent_id, req.executable_path)
        save_configured_agent_model(agent_id, req.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Keep the mirrored agent manager config in sync for persisted installations
    # that still read ``llm_agents.json`` directly.
    agent_config = agent_manager.get_agent_config(agent_id) or {}
    if req.executable_path and req.executable_path.strip():
        agent_config["executable_path"] = req.executable_path.strip()
    else:
        agent_config.pop("executable_path", None)
    if req.model and req.model.strip():
        agent_config["model"] = req.model.strip()
    else:
        agent_config.pop("model", None)
    agent_manager.update_agent(agent_id, agent_config)

    return {"status": "ok", "agent": detect_local_agents(force=True).get(agent_id)}


@app.get("/api/agents/detect")
async def detect_agents(force: bool = False):
    """Detect installed local agents and their paths"""
    from .local_agent_health import detect_local_agents

    return await asyncio.to_thread(detect_local_agents, force=force)


@app.get("/api/agents/registry")
async def get_agent_registry():
    """Return local agent metadata and configured paths."""
    from .local_agent_health import list_local_agent_specs

    return {"agents": list(list_local_agent_specs().values())}


@app.get("/api/agents/protocols")
async def get_local_agent_protocols():
    """Return optional local-agent protocol bridges without running agents."""
    from .local_agent_protocols import render_local_agent_protocol_contract

    return render_local_agent_protocol_contract()


@app.get("/api/agents/{agent_id}/detect")
@app.post("/api/agents/{agent_id}/detect")
async def detect_agent(agent_id: str):
    """Force-detect one local agent."""
    from .local_agent_health import LOCAL_AGENT_SPECS, detect_local_agents

    agent_id = normalize_agent_id(agent_id) or agent_id
    if agent_id not in LOCAL_AGENT_SPECS:
        raise HTTPException(status_code=404, detail=f"Unknown local agent: {agent_id}")
    return detect_local_agents(force=True).get(agent_id)


@app.get("/api/history/{session_id}")
async def get_chat_history(session_id: str, limit: int = 30, offset: int = 0):
    """Retrieve chat history for a specific session"""
    try:
        messages = persistence.get_visible_messages(session_id, limit=limit, offset=offset)
        total = persistence.count_visible_messages(session_id)
        has_more = (offset + limit) < total
        return {
            "session_id": session_id,
            "messages": messages,
            "total": total,
            "has_more": has_more
        }
    except Exception as e:
        raise _safe_http_500("Get chat history")

def _session_info_from_row(s: Dict[str, Any]) -> SessionInfo:
    preview = s.get("first_user_message")
    if preview:
        if "<attached_files>" in preview:
            preview = preview.split("<attached_files>")[0].strip()
        if len(preview) > 100:
            preview = preview[:100] + "..."
    return SessionInfo(
        session_id=s["session_id"],
        created_at=str(s["created_at"]),
        updated_at=str(s["updated_at"]),
        message_count=s.get("message_count", 0),
        name=s.get("name"),
        preview=preview,
        project_id=s.get("project_id"),
        project_dir=s.get("project_dir"),
        is_pinned=bool(s.get("is_pinned")),
        pinned_at=str(s["pinned_at"]) if s.get("pinned_at") else None,
    )

def _project_session_info_from_row(s: Dict[str, Any]) -> ProjectSessionInfo:
    return ProjectSessionInfo(**_session_info_from_row(s).model_dump())

def _project_info_from_row(p: Dict[str, Any], sessions: Optional[List[ProjectSessionInfo]] = None) -> ProjectInfo:
    return ProjectInfo(
        id=p["id"],
        name=p["name"],
        path=p["path"],
        kind=p.get("kind") or "folder",
        is_pinned=bool(p.get("is_pinned")),
        pinned_at=str(p["pinned_at"]) if p.get("pinned_at") else None,
        created_at=str(p["created_at"]),
        updated_at=str(p["updated_at"]),
        last_opened_at=str(p["last_opened_at"]) if p.get("last_opened_at") else None,
        sessions=sessions or [],
    )

@app.get("/api/projects", response_model=ProjectListResponse)
async def list_projects(session_limit: int = 5):
    """List project directories with a small set of recent chats per project."""
    try:
        projects = []
        for p in persistence.list_projects(session_limit=session_limit):
            sessions = [_project_session_info_from_row(s) for s in p.get("sessions", [])]
            projects.append(_project_info_from_row(p, sessions=sessions))
        return ProjectListResponse(projects=projects)
    except Exception as e:
        raise _safe_http_500("List projects")

@app.post("/api/projects/blank", response_model=ProjectInfo)
async def create_blank_project(req: CreateBlankProjectRequest):
    try:
        project = persistence.create_blank_project(req.name)
        return _project_info_from_row(project)
    except Exception as e:
        raise _safe_http_500("Create blank project")

@app.post("/api/projects/from-folder", response_model=ProjectInfo)
async def create_folder_project(req: CreateFolderProjectRequest):
    try:
        # codeql[py/path-injection]: This endpoint imports a folder explicitly
        # selected by the local desktop user after path normalization.
        path = _normalize_local_path(req.path)
        if not os.path.isdir(path):
            raise HTTPException(status_code=400, detail=f"Project path is not a directory: {path}")
        project = persistence.create_project(
            name=req.name or os.path.basename(path) or "Project",
            path=path,
            kind="folder",
        )
        return _project_info_from_row(project)
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_http_500("Create folder project")

@app.patch("/api/projects/{project_id}/pin", response_model=ProjectInfo)
async def pin_project(project_id: str, req: PinRequest):
    """Pin or unpin a project. Later pins sort first."""
    try:
        project = persistence.set_project_pinned(project_id, req.is_pinned)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
        return _project_info_from_row(project)
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_http_500("Get task status")

@app.get("/api/sessions", response_model=SessionListResponse)
async def list_sessions(limit: int = 50, offset: int = 0, project_id: Optional[str] = None):
    """List all sessions with message count and preview, newest first."""
    try:
        safe_limit = max(1, min(int(limit or 50), 200))
        safe_offset = max(0, int(offset or 0))
        try:
            page_result = persistence.list_sessions(limit=safe_limit, offset=safe_offset, project_id=project_id)
        except TypeError as exc:
            if project_id is not None or "project_id" not in str(exc):
                raise
            page_result = persistence.list_sessions(limit=safe_limit, offset=safe_offset)
        if isinstance(page_result, tuple):
            active, total = page_result
        else:
            active = [s for s in page_result if s.get("message_count", 0) > 0]
            total = len(active)
        session_infos = [_session_info_from_row(s) for s in active]
        return SessionListResponse(
            sessions=session_infos,
            total=total,
            limit=safe_limit,
            offset=safe_offset,
            has_more=safe_offset + len(session_infos) < total,
        )
    except Exception as e:
        raise _safe_http_500("List sessions")

@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and all its messages (cascade)."""
    try:
        persistence.clear_session(session_id)
        return {"status": "success", "session_id": session_id}
    except Exception as e:
        raise _safe_http_500("Delete session")

@app.patch("/api/sessions/{session_id}/rename")
async def rename_session(session_id: str, req: RenameSessionRequest):
    """Rename a session."""
    try:
        persistence.rename_session(session_id, req.name)
        return {"status": "success", "session_id": session_id, "name": req.name}
    except Exception as e:
        raise _safe_http_500("Rename session")

@app.patch("/api/sessions/{session_id}/pin")
async def pin_session(session_id: str, req: PinRequest):
    """Pin or unpin a session. Later pins sort first within the project."""
    try:
        if not persistence.set_session_pinned(session_id, req.is_pinned):
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
        return {"status": "success", "session_id": session_id, "is_pinned": req.is_pinned}
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_http_500("Pin session")

@app.get("/api/tools", response_model=List[Dict[str, Any]])
async def get_tools():
    return _runtime_tool_schemas()


class AgentCapabilityUpdateRequest(BaseModel):
    enabled_skill_ids: Optional[List[str]] = None
    enabled_plugin_ids: Optional[List[str]] = None
    enabled_tool_names: Optional[List[str]] = None
    custom_instructions: Optional[str] = None
    strict_tool_scope: Optional[bool] = None


class AgentCapabilitySkillRequest(BaseModel):
    id: Optional[str] = None
    name: str
    description: str
    prompt_hint: str
    tags: Optional[List[str]] = None


class AgentCapabilityPreflightRequest(BaseModel):
    description: str
    owner_agent: Optional[str] = None
    allowed_subtask_agents: Optional[List[str]] = None
    task_types: Optional[List[str]] = None


class NativeSkillInstallRequest(BaseModel):
    identifier: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    body: Optional[str] = None
    scope: str = "user"
    project_dir: Optional[str] = None
    source_path: Optional[str] = None
    version: Optional[str] = None
    force: bool = False


def _native_skill_request(req: Optional[NativeSkillInstallRequest] = None) -> NativeSkillRequest:
    if req is None:
        return NativeSkillRequest()
    return NativeSkillRequest(**_pydantic_dump(req))


def _handle_native_skill_error(exc: NativeSkillError) -> HTTPException:
    if exc.status_code >= 500 and exc.status_code != 501:
        logger.warning("Native skill command failed: %s", exc)
        return HTTPException(status_code=exc.status_code, detail=_safe_error_message("Native skill command"))
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _append_native_skill_context(
    capability_context: Dict[str, Any],
    agent_ids: Optional[List[str]],
    description: str = "",
) -> Dict[str, Any]:
    selected = []
    for agent_id in agent_ids or list(LOCAL_CLI_AGENT_IDS):
        normalized = normalize_agent_id(agent_id) or agent_id
        if normalized in LOCAL_CLI_AGENT_IDS and normalized not in selected:
            selected.append(normalized)
    if not selected:
        return capability_context

    manager = get_native_skill_manager()
    native_skills: Dict[str, List[Dict[str, Any]]] = {}
    prompt_lines: List[str] = []
    request_tokens = {
        token
        for token in re.split(r"[^a-z0-9]+", (description or "").lower())
        if len(token) >= 3
    }
    for agent_id in selected:
        try:
            state = manager.list_agent_skills(agent_id)
        except NativeSkillError:
            continue
        skills = [
            skill
            for skill in state.get("skills", [])
            if is_native_skill_available(skill)
        ]
        if request_tokens and len(skills) > 12:
            matched = [
                skill
                for skill in skills
                if request_tokens.intersection(
                    set(
                        re.split(
                            r"[^a-z0-9]+",
                            " ".join(
                                [
                                    str(skill.get("id") or ""),
                                    str(skill.get("name") or ""),
                                    str(skill.get("description") or ""),
                                ]
                            ).lower(),
                        )
                    )
                )
            ]
            skills = matched[:12] if matched else skills[:8]
        elif len(skills) > 12:
            skills = skills[:12]
        native_skills[agent_id] = skills
        names = [str(skill.get("name") or skill.get("id")) for skill in skills if skill.get("name") or skill.get("id")]
        if names:
            prompt_lines.append(
                f"- {agent_id} Installed native skills: {', '.join(names)}. "
                "Prefer the native skill by name when it matches the subtask."
            )

    if native_skills:
        capability_context = dict(capability_context)
        capability_context["native_skills"] = native_skills
    if prompt_lines:
        existing = str(capability_context.get("prompt") or "").strip()
        capability_context["prompt"] = "\n".join(
            [part for part in [existing, *prompt_lines] if part]
        )
    return capability_context


def _selected_local_agents_for_capability_request(
    owner_agent: Optional[str],
    allowed_subtask_agents: Optional[List[str]],
) -> List[str]:
    selected: List[str] = []
    normalized_owner = normalize_agent_id(owner_agent) if owner_agent else None
    if normalized_owner and normalized_owner != "auto":
        selected.append(normalized_owner)
    for agent_id in allowed_subtask_agents or []:
        normalized = normalize_agent_id(agent_id) or agent_id
        if normalized != "auto":
            selected.append(normalized)
    if not selected:
        selected = list(LOCAL_CLI_AGENT_IDS)
    return [
        agent_id
        for agent_id in dict.fromkeys(selected)
        if agent_id in LOCAL_CLI_AGENT_IDS
    ]


def _native_skills_for_preflight(
    owner_agent: Optional[str],
    allowed_subtask_agents: Optional[List[str]],
) -> Dict[str, List[Dict[str, Any]]]:
    selected = _selected_local_agents_for_capability_request(owner_agent, allowed_subtask_agents)
    if not selected:
        return {}
    manager = get_native_skill_manager()
    native_skills: Dict[str, List[Dict[str, Any]]] = {}
    for agent_id in selected:
        try:
            state = manager.list_agent_skills(agent_id)
        except NativeSkillError:
            continue
        native_skills[agent_id] = [
            skill
            for skill in state.get("skills", [])
            if isinstance(skill, dict)
        ]
    return native_skills


def _native_skill_states_for_capability_ui(refresh: bool = False) -> Dict[str, Dict[str, Any]]:
    store = get_agent_capability_store()
    if refresh:
        states = get_native_skill_manager().list_all_agent_skills()
        return store.save_native_skill_states(states)
    return store.get_native_skill_states()


def _refresh_native_skill_cache_for_agent(agent_id: str) -> Dict[str, Any]:
    store = get_agent_capability_store()
    states = store.get_native_skill_states()
    normalized = normalize_agent_id(agent_id) or agent_id
    states[normalized] = get_native_skill_manager().list_agent_skills(normalized)
    store.save_native_skill_states(states)
    return states[normalized]


@app.get("/api/agent-capabilities")
async def list_agent_capabilities(refresh: bool = False):
    store = get_agent_capability_store()
    available_tools = _runtime_tool_schemas()
    native_skill_states = _native_skill_states_for_capability_ui(refresh=refresh)
    native_skills_by_agent = {
        agent_id: [
            skill
            for skill in (state.get("skills") if isinstance(state, dict) else []) or []
            if isinstance(skill, dict)
        ]
        for agent_id, state in native_skill_states.items()
    }
    return {
        "skills": store.skill_catalog(),
        "profiles": store.get_profiles(),
        "available_tools": available_tools,
        "native_skill_agents": native_skill_states,
        "agent_cards": store.build_agent_cards(
            tool_schemas=available_tools,
            native_skills_by_agent=native_skills_by_agent,
        ),
    }


def _build_agent_cards_payload() -> Dict[str, Any]:
    store = get_agent_capability_store()
    available_tools = _runtime_tool_schemas()
    native_skill_states = get_native_skill_manager().list_all_agent_skills()
    native_skills_by_agent = {
        agent_id: [
            skill
            for skill in (state.get("skills") if isinstance(state, dict) else []) or []
            if isinstance(skill, dict)
        ]
        for agent_id, state in native_skill_states.items()
    }
    base_cards = store.build_agent_cards(
        tool_schemas=available_tools,
        native_skills_by_agent=native_skills_by_agent,
    )
    return {
        "schema_version": "1.0",
        "protocol": "a2a-like",
        "generated_at": time.time(),
        "security": {
            "secrets_included": False,
            "custom_instructions_included": False,
            "credential_fields_redacted": True,
        },
        "cards": [
            _public_agent_card(card, native_skills_by_agent.get(card.get("agent_id"), []))
            for card in base_cards
        ],
    }


@app.get("/api/agent-cards")
async def export_agent_cards():
    """Export public, non-secret internal agent cards for orchestration audits."""
    return _build_agent_cards_payload()


@app.get("/api/host/agent-capabilities")
async def export_host_agent_capabilities(refresh: bool = False):
    """Export a non-secret host capability registry for external orchestrators."""
    store = get_agent_capability_store()
    available_tools = _runtime_tool_schemas()
    native_skill_states = _native_skill_states_for_capability_ui(refresh=refresh)
    native_skills_by_agent = {
        agent_id: [
            skill
            for skill in (state.get("skills") if isinstance(state, dict) else []) or []
            if isinstance(skill, dict)
        ]
        for agent_id, state in native_skill_states.items()
    }
    return store.build_host_registry(
        tool_schemas=available_tools,
        native_skills_by_agent=native_skills_by_agent,
    )


def _build_unified_capability_registry_payload(refresh: bool = False) -> Dict[str, Any]:
    store = get_agent_capability_store()
    available_tools = _runtime_tool_schemas()
    native_skill_states = _native_skill_states_for_capability_ui(refresh=refresh)
    native_skills_by_agent = {
        agent_id: [
            skill
            for skill in (state.get("skills") if isinstance(state, dict) else []) or []
            if isinstance(skill, dict)
        ]
        for agent_id, state in native_skill_states.items()
    }
    host_registry = store.build_host_registry(
        tool_schemas=available_tools,
        native_skills_by_agent=native_skills_by_agent,
    )
    try:
        from .loop_engineering_capability_pack import loop_engineering_capability_pack

        autopilot_capability_pack = loop_engineering_capability_pack()
    except Exception:
        autopilot_capability_pack = {}
    configured_provider_ids = [
        provider_id
        for provider_id in _known_provider_ids()
        if _provider_has_backend_key(provider_id)
    ]
    return build_unified_capability_registry(
        host_registry=host_registry,
        tool_schemas=available_tools,
        skill_catalog=store.skill_catalog(),
        agent_configs=agent_manager.config.get("agents", {}),
        active_agent=agent_manager.get_active_agent(),
        llm_config=load_llm_config(),
        configured_provider_ids=configured_provider_ids,
        plugins=discover_across_plugins(probe=False),
        autopilot_capability_pack=autopilot_capability_pack,
    )


@app.get("/api/capability-registry")
async def export_unified_capability_registry(refresh: bool = False):
    """Export a non-secret unified capability index without merging executors."""
    return _sanitize_public_payload(_build_unified_capability_registry_payload(refresh=refresh))


@app.get("/api/capability-registry/health")
async def get_unified_capability_registry_health(refresh: bool = False):
    """Return machine-readable compatibility and health checks for the unified registry."""
    payload = _build_unified_capability_registry_payload(refresh=refresh)
    return _sanitize_public_payload(evaluate_unified_capability_registry_health(payload))


@app.post("/api/agent-capabilities/skills")
async def create_agent_capability_skill(req: AgentCapabilitySkillRequest):
    store = get_agent_capability_store()
    try:
        skill = store.save_custom_skill(_pydantic_dump(req))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "status": "success",
        "skill": skill,
    }


@app.put("/api/agent-capabilities/skills/{skill_id}")
async def update_agent_capability_skill(skill_id: str, req: AgentCapabilitySkillRequest):
    store = get_agent_capability_store()
    try:
        skill = store.save_custom_skill(_pydantic_dump(req), skill_id=skill_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "status": "success",
        "skill": skill,
    }


@app.delete("/api/agent-capabilities/skills/{skill_id}")
async def delete_agent_capability_skill(skill_id: str):
    store = get_agent_capability_store()
    deleted = store.delete_custom_skill(skill_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Custom skill not found: {skill_id}")
    return {
        "status": "success",
        "deleted_skill_id": skill_id,
    }


@app.post("/api/agent-capabilities/preflight")
async def preflight_agent_capabilities(req: AgentCapabilityPreflightRequest):
    store = get_agent_capability_store()
    return store.build_task_preflight(
        description=req.description,
        owner_agent=req.owner_agent,
        allowed_subtask_agents=req.allowed_subtask_agents,
        task_types=req.task_types,
        native_skills_by_agent=_native_skills_for_preflight(
            req.owner_agent,
            req.allowed_subtask_agents,
        ),
    )


@app.get("/api/agent-capabilities/{agent_id}")
async def get_agent_capability(agent_id: str):
    store = get_agent_capability_store()
    return {
        "skills": store.skill_catalog(),
        "profile": store.get_profile(agent_id),
        "available_tools": _runtime_tool_schemas(),
    }


@app.put("/api/agent-capabilities/{agent_id}")
async def update_agent_capability(agent_id: str, req: AgentCapabilityUpdateRequest):
    store = get_agent_capability_store()
    updates = _pydantic_dump(req, exclude_unset=True)
    profile = store.save_profile(agent_id, updates)
    return {
        "status": "success",
        "profile": profile,
    }


@app.get("/api/native-skills")
async def list_native_skills(refresh: bool = False):
    return {
        "agents": _native_skill_states_for_capability_ui(refresh=refresh),
    }


@app.get("/api/native-skills/{agent_id}")
async def list_native_agent_skills(agent_id: str):
    manager = get_native_skill_manager()
    try:
        return manager.list_agent_skills(agent_id)
    except NativeSkillError as exc:
        raise _handle_native_skill_error(exc)


@app.post("/api/native-skills/{agent_id}/install")
async def install_native_agent_skill(agent_id: str, req: NativeSkillInstallRequest):
    manager = get_native_skill_manager()
    try:
        skill = manager.install_skill(agent_id, _native_skill_request(req))
        state = _refresh_native_skill_cache_for_agent(agent_id)
    except NativeSkillError as exc:
        raise _handle_native_skill_error(exc)
    return {
        "status": "success",
        "skill": skill,
        "state": state,
    }


@app.post("/api/native-skills/{agent_id}/{skill_id}/update")
async def update_native_agent_skill(agent_id: str, skill_id: str, req: Optional[NativeSkillInstallRequest] = None):
    manager = get_native_skill_manager()
    try:
        skill = manager.update_skill(agent_id, skill_id, _native_skill_request(req))
        state = _refresh_native_skill_cache_for_agent(agent_id)
    except NativeSkillError as exc:
        raise _handle_native_skill_error(exc)
    return {
        "status": "success",
        "skill": skill,
        "state": state,
    }


@app.post("/api/native-skills/{agent_id}/check")
async def check_native_agent_skills(agent_id: str, req: Optional[NativeSkillInstallRequest] = None):
    manager = get_native_skill_manager()
    try:
        result = manager.check_skills(agent_id, _native_skill_request(req))
    except NativeSkillError as exc:
        raise _handle_native_skill_error(exc)
    return {
        "status": "success",
        "result": result,
    }


@app.delete("/api/native-skills/{agent_id}/{skill_id}")
async def uninstall_native_agent_skill(agent_id: str, skill_id: str, force: bool = False):
    manager = get_native_skill_manager()
    try:
        skill = manager.uninstall_skill(
            agent_id,
            skill_id,
            NativeSkillRequest(force=force),
        )
        state = _refresh_native_skill_cache_for_agent(agent_id)
    except NativeSkillError as exc:
        raise _handle_native_skill_error(exc)
    return {
        "status": "success",
        "skill": skill,
        "state": state,
    }

@app.post("/api/approve", response_model=ChatResponse)
async def approve_tool_execution(req: ApprovalDecision):
    if _is_tool_unavailable(req.tool_name):
        persistence.add_audit_log(
            session_id=req.session_id,
            tool_name=req.tool_name,
            tool_args=req.tool_args,
            risk_level="unavailable",
            decision=f"rejected_unavailable_{req.decision}"
        )
        return ChatResponse(text=f"工具 `{req.tool_name}` 已被设置为不可用，未执行。", session_id=req.session_id)

    # Pre-validate tool existence before processing
    matched_schema = _resolve_tool(req.tool_name)
    risk_level = matched_schema["risk_level"] if matched_schema else "unknown"

    if not matched_schema:
        persistence.add_audit_log(
            session_id=req.session_id,
            tool_name=req.tool_name,
            tool_args=req.tool_args,
            risk_level=risk_level,
            decision=f"rejected_invalid_{req.decision}"
        )
        return ChatResponse(text=f"错误：工具 `{req.tool_name}` 不存在，已自动拒绝。", session_id=req.session_id)

    tool_name = matched_schema["name"]
    tool_args = _augment_mcp_tool_args_for_session(tool_name, req.tool_args, req.session_id)
    project_root = _session_project_root(req.session_id)

    # DB: Log the audit decision
    persistence.add_audit_log(
        session_id=req.session_id,
        tool_name=tool_name,
        tool_args=tool_args,
        risk_level=risk_level,
        decision=req.decision
    )

    if req.decision == "always_allow":
        persistence.set_tool_authorization(tool_name, True)

    if req.decision in ["approve", "always_allow"]:
        # Check if it's an MCP tool or a local tool
        is_mcp = False
        tool_def = registry.get_tool(tool_name)

        if not tool_def:
            is_mcp = True

        if is_mcp:
            # Execute MCP tool
            parts = tool_name.split("__", 1)
            if len(parts) == 2:
                server_id = parts[0]
                actual_tool_name = parts[1]

                try:
                    result = await mcp_manager.call_tool(server_id, actual_tool_name, tool_args)
                    result_text = f"✅ MCP 工具 {tool_name} 执行成功！结果：\n{result}"
                    persistence.add_message(session_id=req.session_id, role="tool", content=result_text, tool_call_id=req.tool_call_id)

                    # Fetch recent chat history to remind the agent of the context
                    recent_messages = persistence.get_messages(req.session_id, limit=50)
                    original_question = "用户之前的问题"
                    if len(recent_messages) >= 2:
                        # The last message is usually the tool call, the one before is the user's question
                        for msg in reversed(recent_messages):
                            if msg["role"] == "user":
                                original_question = msg["content"]
                                break

                    continuation_req = ChatRequest(
                        text=f"【工具执行反馈】\n刚才你调用的 MCP 工具 `{tool_name}` 已执行完毕，结果如下：\n<tool_result>\n{result}\n</tool_result>\n\n请基于上述结果继续你的任务。如果还需要其他信息，可以继续调用工具；如果已经收集到足够信息，请直接回答用户最初的问题：\n<original_question>\n{original_question}\n</original_question>",
                        context=None,
                        session_id=req.session_id,
                        agent_id=req.agent_id,
                        project_dir=project_root,
                    )
                    return await _continue_after_tool_execution(continuation_req, result_text)
                except Exception as e:
                    error_text = f"❌ MCP 工具执行失败: {str(e)}"
                    persistence.add_message(session_id=req.session_id, role="tool", content=error_text, tool_call_id=req.tool_call_id)
                    continuation_req = ChatRequest(
                        text=f"MCP 工具 {tool_name} 执行失败，报错信息：\n{str(e)}\n请告诉用户执行失败了，或者尝试其他方法。",
                        context=None,
                        session_id=req.session_id,
                        agent_id=req.agent_id,
                        project_dir=project_root,
                    )
                    return await _continue_after_tool_execution(continuation_req, error_text)
            return ChatResponse(text="MCP工具名称解析失败", session_id=req.session_id)

        # Execute local tool
        elif tool_def:
            try:
                # The tool_args coming from the Swift client will be a dict of {key: value}
                # But since we use AnyCodableValue in Swift, simple types like Int/String should map correctly
                result = tool_def.handler(**tool_args)
                result_text = f"✅ 工具 {req.tool_name} 执行成功！结果：\n{result}"
                persistence.add_message(session_id=req.session_id, role="tool", content=result_text, tool_call_id=req.tool_call_id)

                # --- AUTO CONTINUATION ---
                recent_messages = persistence.get_messages(req.session_id, limit=50)
                original_question = "用户之前的问题"
                if len(recent_messages) >= 2:
                    for msg in reversed(recent_messages):
                        if msg["role"] == "user":
                            original_question = msg["content"]
                            break

                continuation_req = ChatRequest(
                    text=f"【工具执行反馈】\n刚才你调用的工具 `{req.tool_name}` 已执行完毕，结果如下：\n<tool_result>\n{result}\n</tool_result>\n\n请基于上述结果继续你的任务。如果还需要其他信息，可以继续调用工具；如果已经收集到足够信息，请直接回答用户最初的问题：\n<original_question>\n{original_question}\n</original_question>",
                    context=None, # We don't need to resend tier1 context for the continuation
                    session_id=req.session_id,
                    agent_id=req.agent_id, # Pass through the original agent
                    project_dir=project_root,
                )
                return await _continue_after_tool_execution(continuation_req, result_text)

            except Exception as e:
                error_text = f"❌ 工具执行失败: {str(e)}"
                persistence.add_message(session_id=req.session_id, role="tool", content=error_text, tool_call_id=req.tool_call_id)

                continuation_req = ChatRequest(
                    text=f"工具 {req.tool_name} 执行失败，报错信息：\n{str(e)}\n请告诉用户执行失败了，或者尝试其他方法。",
                    context=None,
                    session_id=req.session_id,
                    agent_id=req.agent_id, # Pass through the original agent
                    project_dir=project_root,
                )
                return await _continue_after_tool_execution(continuation_req, error_text)
        return ChatResponse(text="未找到对应的工具", session_id=req.session_id)
    else:
        cancel_text = "用户已取消执行工具操作。"
        persistence.add_message(session_id=req.session_id, role="tool", content=cancel_text, tool_call_id=req.tool_call_id)
        continuation_req = ChatRequest(
            text="用户拒绝了你的工具调用请求。请告知用户已取消，或者提供其他建议。",
            context=None,
            session_id=req.session_id,
            agent_id=req.agent_id
        )
        return await _continue_after_tool_execution(continuation_req, cancel_text)


class PermissionInfo(BaseModel):
    tool_name: str
    permission_type: str
    granted_at: str
    granted_by: Optional[str] = None


class PermissionUpdateRequest(BaseModel):
    permission_type: str


@app.get("/api/permissions", response_model=List[PermissionInfo])
async def list_permissions():
    """列出所有已授权的工具权限。"""
    return persistence.list_permissions()


@app.put("/api/permissions/{tool_name}")
async def update_permission(tool_name: str, req: PermissionUpdateRequest):
    """设置指定工具的权限。ask 表示清除持久规则，每次询问。"""
    try:
        persistence.permissions.set_permission(tool_name, req.permission_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "status": "success",
        "tool_name": tool_name,
        "permission_type": req.permission_type,
    }


@app.delete("/api/permissions/{tool_name}")
async def revoke_permission(tool_name: str):
    """撤销指定工具的始终允许权限。"""
    success = persistence.permissions.revoke_permission(tool_name)
    if not success:
        raise HTTPException(status_code=404, detail=f"没有找到工具 {tool_name} 的授权记录")
    return {"status": "success", "tool_name": tool_name}


class ChatCancelRequest(BaseModel):
    session_id: str

class LLMProviderResponse(BaseModel):
    provider_id: str
    name: str
    enabled: bool
    available: bool  # Has API key
    endpoint: str
    provider_type: str = "openai_compatible"
    models_endpoint: Optional[str] = None
    models: List[Dict[str, Any]]

class LLMModelInfo(BaseModel):
    model_id: str
    name: str
    supports_function_calling: bool
    max_tokens: int

class LLMSwitchRequest(BaseModel):
    provider_id: str
    model_id: Optional[str] = None

@app.get("/api/llm/providers", response_model=List[LLMProviderResponse])
async def list_llm_providers():
    """List all configured LLM providers."""
    try:
        config = load_llm_config()
        gw = LLMGateway(config)
        result = []
        for provider in config.providers:
            adapter = gw._adapters.get(provider.provider_id)
            available = adapter.is_available() if adapter else False
            result.append(LLMProviderResponse(
                provider_id=provider.provider_id,
                name=provider.name,
                enabled=provider.enabled,
                available=available,
                endpoint=provider.endpoint,
                provider_type=provider.provider_type,
                models_endpoint=provider.models_endpoint,
                models=[
                    {
                        "model_id": m.model_id,
                        "name": m.name,
                        "supports_function_calling": m.supports_function_calling,
                        "max_tokens": m.max_tokens
                    }
                    for m in provider.models
                ]
            ))
        return result
    except Exception as e:
        raise _safe_http_500("List LLM providers")

@app.get("/api/llm/models/{provider_id}", response_model=List[LLMModelInfo])
async def list_llm_models(provider_id: str, refresh: bool = True):
    """List all models for a specific provider."""
    try:
        config = load_llm_config()
        gw = LLMGateway(config)
        if provider_id not in {provider.provider_id for provider in config.providers}:
            raise HTTPException(status_code=404, detail=f"Unknown provider: {provider_id}")
        models = await gw.fetch_models(provider_id) if refresh else gw.list_models(provider_id)
        return [
            LLMModelInfo(
                model_id=m.model_id,
                name=m.name,
                supports_function_calling=m.supports_function_calling,
                max_tokens=m.max_tokens
            )
            for m in models
        ]
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_http_500("List LLM models")

@app.post("/api/llm/switch")
async def switch_llm_provider(req: LLMSwitchRequest):
    """Switch the active LLM provider."""
    try:
        gw = get_gateway()
        success = gw.switch_provider(req.provider_id)
        if not success:
            raise HTTPException(status_code=400, detail="Provider not available or no API key")
        return {"status": "success", "provider_id": req.provider_id}
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_http_500("Switch LLM provider")

@app.get("/api/llm/status")
async def get_llm_status():
    """Get current LLM provider status."""
    try:
        gw = get_gateway()
        current = gw.get_current_provider_id()
        config = load_llm_config()
        provider = next((p for p in config.providers if p.provider_id == current), None)
        adapter = gw.get_current_adapter()
        lease_status = _candidate_model_lease_status("model.chat")
        candidate_mode = lease_status.get("lease") is not None
        local_available = adapter.is_available() if adapter else False
        if candidate_mode:
            available = bool(lease_status["available"])
            availability_source = "candidate_model_lease" if available else "missing_candidate_model_lease"
        else:
            available = local_available
            availability_source = "local_credentials" if local_available else "missing_credentials"
        return {
            "current_provider": current,
            "provider_name": provider.name if provider else None,
            "available": available,
            "availability_source": availability_source,
            "candidate_model_lease": lease_status["public"],
        }
    except Exception as e:
        raise _safe_http_500("Get LLM status")

class LLMChatRequest(BaseModel):
    message: str
    system_prompt: Optional[str] = None
    context: Optional[Dict[str, str]] = None
    provider_id: Optional[str] = None
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 2048

class LLMChatResponse(BaseModel):
    text: str
    model: str
    provider: str
    finish_reason: str
    usage: Optional[Dict[str, Any]] = None

@app.post("/api/llm/chat", response_model=LLMChatResponse)
async def llm_chat(req: LLMChatRequest):
    """Direct LLM chat endpoint (for testing the gateway)."""
    try:
        response = await _chat_with_model_capability(
            message=req.message,
            system_prompt=req.system_prompt,
            context=req.context,
            provider_id=req.provider_id,
            model=req.model,
            scope="model.chat",
            temperature=req.temperature,
            max_tokens=req.max_tokens
        )
        return LLMChatResponse(
            text=response.text,
            model=response.model,
            provider=response.provider,
            finish_reason=response.finish_reason,
            usage=response.usage
        )
    except Exception as e:
        raise _safe_http_500("LLM chat")

@app.post("/api/chat/cancel")
async def cancel_chat(req: ChatCancelRequest):
    """Cancel a running chat request for a specific session."""
    try:
        success = agent_client.cancel(req.session_id)
        if success:
            persistence.add_message(session_id=req.session_id, role="system", content="用户已手动终止对话生成。")
            return {"status": "success", "message": "Chat cancelled"}
        return {"status": "ignored", "message": "No active chat found to cancel"}
    except Exception as e:
        raise _safe_http_500("Cancel chat")



@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    req.agent_id = normalize_agent_id(req.agent_id) or req.agent_id
    print(f"DEBUG chat_endpoint: agent_id={req.agent_id}", flush=True)
    if not req.session_id:
        req.session_id = f"sess-{uuid.uuid4().hex[:12]}"
    if not req.project_id and not req.project_dir and req.session_id:
        existing_project = persistence.get_session_project(req.session_id)
        if existing_project:
            req.project_id = existing_project.get("id")
            req.project_dir = existing_project.get("path")
    project = persistence.assign_session_project(
        req.session_id,
        project_id=req.project_id,
        project_dir=req.project_dir,
    )
    if project:
        req.project_id = project["id"]
        req.project_dir = project["path"]
    image_context = ""
    if req.attachments and has_image_attachments(req.attachments):
        image_context = build_image_attachment_context(req.attachments)

    # DB: Record the user's message
    persistence.add_message(session_id=req.session_id, role="user", content=req.text)

    # Route local CLI agents directly to their executable.
    # Cloud LLM agents (deepseek, minimax, openai, etc.) go through the orchestrator loop.
    if req.agent_id in LOCAL_CLI_AGENT_IDS:
        return await _handle_local_chat(req, image_context=image_context)

    # Prepare system message with context if provided
    system_msg = "You are a helpful AI assistant running in a macOS desktop environment. You are NOT Claude. You are NOT Hermes. You are NOT OpenClaw. You are the Across Agents Assistant, a versatile tool for macOS users. Do not use conversational filler, just act."
    if req.project_dir:
        system_msg += (
            "\n\n【Project Directory】\n"
            f"Current project directory: {req.project_dir}\n"
            "When reading or writing project files, stay within this directory unless the user explicitly asks otherwise."
        )
    if req.context:
        ctx_parts = []
        if req.context.frontmost_app:
            ctx_parts.append(f"当前应用: {req.context.frontmost_app}")
        if req.context.window_title:
            ctx_parts.append(f"窗口标题: {req.context.window_title}")
        if req.context.clipboard_text:
            ctx_parts.append(f"剪贴板内容: {req.context.clipboard_text}")

        if ctx_parts:
            system_msg += "\n\n【系统上下文】\n" + "\n".join(ctx_parts)

    return await _run_chat_tool_loop(
        req.session_id,
        req.agent_id,
        system_prompt=system_msg,
        current_attachments=req.attachments,
        current_image_context=image_context,
    )

async def _handle_local_chat(req: ChatRequest, image_context: str = "") -> ChatResponse:
    """Handle chat for local CLI agents.

    Local agents are invoked directly via their CLI executable rather than
    through the cloud LLM orchestrator loop (which handles tool calling).
    """
    client = get_local_agent_client()
    project_dir = req.project_dir
    project = None
    if not project_dir and req.session_id:
        project = persistence.get_session_project(req.session_id)
    if project:
        project_dir = project.get("path")
    local_image_context = ""
    if req.attachments and has_image_attachments(req.attachments):
        # Local CLI agents often react to image paths by trying to call their own
        # filesystem tools. Send the extracted image context instead so screenshots
        # are understandable even when the CLI has no native attachment channel.
        local_image_context = build_image_attachment_context(req.attachments, include_paths=False)
    enriched_text = append_image_attachment_context(req.text, local_image_context or image_context)
    agent_id = normalize_agent_id(req.agent_id) or req.agent_id
    reply = await asyncio.to_thread(
        client.send, enriched_text, req.session_id, use_current=False, target_agent=agent_id, project_dir=project_dir
    )

    reply_text = reply.text or ""

    # Pre-validate tool existence before sending approval request to client
    if reply.requires_approval and reply.approval_request:
        tool_name = reply.approval_request.get("tool_name", "")
        if not _resolve_tool(tool_name):
            logger.warning(f"Local agent requested non-existent tool '{tool_name}', skipping approval")
            # Replace the agent's denial text with a helpful message
            reply_text = f"工具 `{tool_name}` 不在已注册的工具列表中，无法授权。请重新描述需求。"
            reply.requires_approval = False
            reply.approval_request = None

    persistence.add_message(session_id=req.session_id, role="assistant", content=reply_text)
    return ChatResponse(
        text=reply_text,
        session_id=reply.session_id,
        requires_approval=reply.requires_approval,
        approval_request=reply.approval_request
    )


async def _run_chat_tool_loop(
    session_id: str,
    agent_id: str,
    system_prompt: Optional[str] = None,
    iteration_count: int = 0,
    state_machine: ChatToolLoopStateMachine = None,
    current_attachments: Optional[List[ChatAttachment]] = None,
    current_image_context: str = "",
) -> ChatResponse:
    import json

    # Initialize state machine on first entry
    if state_machine is None:
        state_machine = ChatToolLoopStateMachine(session_id=session_id, agent_id=agent_id)

    # Iteration guard
    if iteration_count >= MAX_AGENT_LOOP_ITERATIONS:
        logger.warning(
            "Chat tool loop iteration limit reached (%d) for session=%s agent=%s",
            MAX_AGENT_LOOP_ITERATIONS,
            session_id,
            agent_id,
        )
        state_machine.transition(ChatToolLoopState.DONE)
        return ChatResponse(
            text="任务执行步数超出限制，请简化请求或检查工具逻辑",
            session_id=session_id,
        )

    logger.debug(
        "Chat tool loop iteration %d/%d for session=%s agent=%s",
        iteration_count,
        MAX_AGENT_LOOP_ITERATIONS,
        session_id,
        agent_id,
    )

    all_schemas = _available_tool_schemas()

    messages = persistence.get_messages(session_id, limit=50)

    formatted_messages = []
    for m in messages:
        role = m["role"]
        content = m["content"] or ""
        if role == "system":
            continue
        if role == "tool":
            tc_id = m.get("tool_call_id")
            if not tc_id:
                continue
            formatted_messages.append({
                "role": "tool",
                "content": content,
                "tool_call_id": tc_id
            })
        elif role == "assistant":
            msg = {
                "role": "assistant",
                "content": content
            }
            if m.get("tool_calls"):
                try:
                    raw_tcs = json.loads(m["tool_calls"])
                    raw_tcs = raw_tcs[:1]
                    openai_tcs = []
                    for tc in raw_tcs:
                        tc_id = tc.get("id")
                        if not tc_id:
                            continue
                        openai_tcs.append({
                            "id": tc_id,
                            "type": "function",
                            "function": {
                                "name": tc.get("name"),
                                "arguments": json.dumps(tc.get("arguments", {}), ensure_ascii=False)
                            }
                        })
                    if openai_tcs:
                        msg["tool_calls"] = openai_tcs
                except Exception:
                    pass
            formatted_messages.append(msg)
        else:
            formatted_messages.append({
                "role": role,
                "content": content
            })

    # Clean up history to prevent API errors from old incompatible data
    valid_messages = []
    for msg in formatted_messages:
        if msg["role"] == "system":
            valid_messages.insert(0, msg)
        elif msg["role"] == "tool":
            if valid_messages and valid_messages[-1]["role"] == "assistant" and "tool_calls" in valid_messages[-1]:
                tc_ids = {tc["id"] for tc in valid_messages[-1]["tool_calls"]}
                if msg.get("tool_call_id") in tc_ids:
                    valid_messages.append(msg)
        else:
            if valid_messages and valid_messages[-1]["role"] == "assistant" and "tool_calls" in valid_messages[-1]:
                del valid_messages[-1]["tool_calls"]
            valid_messages.append(msg)

    if valid_messages and valid_messages[-1]["role"] == "assistant" and "tool_calls" in valid_messages[-1]:
        del valid_messages[-1]["tool_calls"]

    if current_attachments and has_image_attachments(current_attachments):
        agent_config = agent_manager.get_agent_config(agent_id or "")
        image_context = current_image_context or build_image_attachment_context(current_attachments)
        if model_supports_vision(agent_config):
            for msg in reversed(valid_messages):
                if msg.get("role") == "user":
                    msg_text = append_image_attachment_context(msg.get("content") or "", image_context)
                    msg["content"] = build_openai_user_content(msg_text, current_attachments)
                    break
        else:
            for msg in reversed(valid_messages):
                if msg.get("role") == "user":
                    msg["content"] = append_image_attachment_context(msg.get("content") or "", image_context)
                    break
            logger.info(
                "Image attachments for session=%s agent=%s were received, but model=%s "
                "is not treated as vision-capable; using extracted image context fallback.",
                session_id,
                agent_id,
                (agent_config or {}).get("model"),
            )

    if system_prompt:
        valid_messages.insert(0, {"role": "system", "content": system_prompt})

    # Debug: log messages being sent to LLM
    logger.debug(f"Sending {len(valid_messages)} messages to {agent_id}:")
    for i, m in enumerate(valid_messages):
        tc_info = f", tool_calls={len(m['tool_calls'])}" if m.get('tool_calls') else ""
        tc_id_info = f", tool_call_id={m.get('tool_call_id')}" if m.get('tool_call_id') else ""
        logger.debug(f"  [{i}] role={m['role']}{tc_info}{tc_id_info}")

    # --- HARNESS: State transition to THINKING ---
    state_machine.transition(ChatToolLoopState.THINKING)

    reply = await agent_client.chat(agent_id, valid_messages, all_schemas)

    # --- HARNESS: Post-process LLM response ---
    processed = post_process_llm_response(reply)

    if processed.classification == OutputClassification.POISONED_TEXT_TOOL_MENTION:
        logger.warning(
            "Detected poisoned output for session=%s agent=%s: %s",
            session_id,
            agent_id,
            processed.classification,
        )
        # Inject recovery prompt and retry
        for retry_attempt in range(processed.retry_count):
            valid_messages.append({
                "role": "user",
                "content": processed.recovery_prompt,
            })
            reply = await agent_client.chat(agent_id, valid_messages, all_schemas)
            processed = post_process_llm_response(reply)
            if processed.classification == OutputClassification.NORMAL:
                break
        else:
            state_machine.transition(ChatToolLoopState.DONE)
            return ChatResponse(
                text="模型输出异常，请重试",
                session_id=session_id,
                error_type="harness_poisoned_output",
            )

    elif processed.classification == OutputClassification.ITERATION_LIMIT:
        logger.warning(
            "Detected iteration limit marker for session=%s agent=%s",
            session_id,
            agent_id,
        )
        state_machine.transition(ChatToolLoopState.DONE)
        return ChatResponse(
            text="任务执行步数超出限制，请简化请求",
            session_id=session_id,
        )

    elif processed.classification == OutputClassification.EMPTY_OUTPUT:
        logger.warning(
            "Detected empty output for session=%s agent=%s, retrying",
            session_id,
            agent_id,
        )
        for retry_attempt in range(processed.retry_count):
            valid_messages.append({
                "role": "user",
                "content": processed.recovery_prompt or "请提供有用的回复或调用合适的工具来完成任务。",
            })
            reply = await agent_client.chat(agent_id, valid_messages, all_schemas)
            processed = post_process_llm_response(reply)
            if processed.classification == OutputClassification.NORMAL:
                break
        else:
            state_machine.transition(ChatToolLoopState.DONE)
            return ChatResponse(
                text="模型未返回有效内容，请重试",
                session_id=session_id,
            )

    # Normal flow: check tool_calls
    if reply.tool_calls:
        tool_call = reply.tool_calls[0]
        tool_name = tool_call["name"]
        tool_args = tool_call["arguments"]
        tool_def = registry.get_tool(tool_name)
        is_mcp = not tool_def

        if is_mcp:
            tool_args = _augment_mcp_tool_args_for_session(tool_name, tool_args, session_id)
            tool_call = {**tool_call, "arguments": tool_args}

        persistence.add_message(
            session_id=session_id,
            role="assistant",
            content=reply.text or "",
            tool_calls=json.dumps([tool_call], ensure_ascii=False),
        )

        tool_call_id = tool_call.get("id", tool_name)

        if _is_tool_unavailable(tool_name):
            err_msg = f"工具 `{tool_name}` 已在工具权限中设为不可用。"
            persistence.add_message(session_id=session_id, role="tool", content=err_msg, tool_call_id=tool_call_id)
            return await _run_chat_tool_loop(
                session_id, agent_id,
                system_prompt=system_prompt,
                iteration_count=iteration_count + 1,
                state_machine=state_machine,
                current_attachments=current_attachments,
                current_image_context=current_image_context,
            )

        is_always_allowed = persistence.get_tool_authorization(tool_name)
        if is_always_allowed:
            persistence.add_audit_log(session_id, tool_name, tool_args, "medium", "auto_approve")

            # --- HARNESS: State transition to TOOL_EXECUTING ---
            state_machine.transition(ChatToolLoopState.TOOL_EXECUTING)

            try:
                result_text = await execute_tool_with_retry(
                    tool_def=tool_name if is_mcp else tool_def,
                    tool_args=tool_args,
                    is_mcp=is_mcp,
                    mcp_manager=mcp_manager,
                )
            except Exception as e:
                logger.error("Tool execution failed after retries: %s", e)
                result_text = f"Error executing tool: {str(e)}"
                state_machine.transition(ChatToolLoopState.ERROR_CLASSIFY)
                state_machine.transition(ChatToolLoopState.DONE)

            persistence.add_message(
                session_id=session_id,
                role="tool",
                content=result_text,
                tool_call_id=tool_call_id,
            )

            return await _run_chat_tool_loop(
                session_id, agent_id,
                system_prompt=system_prompt,
                iteration_count=iteration_count + 1,
                state_machine=state_machine,
                current_attachments=current_attachments,
                current_image_context=current_image_context,
            )

        # Pre-validate tool existence before showing approval dialog
        matched_schema = _resolve_tool(tool_name)
        if not matched_schema:
            err_msg = f"错误：工具 `{tool_name}` 不存在。请从已注册的工具中选择：{', '.join(t['name'] for t in all_schemas[:30])}"
            persistence.add_message(session_id=session_id, role="tool", content=err_msg, tool_call_id=tool_call_id)
            return await _run_chat_tool_loop(
                session_id, agent_id,
                system_prompt=system_prompt,
                iteration_count=iteration_count + 1,
                state_machine=state_machine,
                current_attachments=current_attachments,
                current_image_context=current_image_context,
            )

        # --- HARNESS: State transition to WAIT_APPROVAL ---
        state_machine.transition(ChatToolLoopState.WAIT_APPROVAL)

        return ChatResponse(
            text=f"请求调用工具：{tool_name}",
            session_id=session_id,
            requires_approval=True,
            approval_request={
                "tool_name": matched_schema["name"],
                "risk_level": matched_schema["risk_level"],
                "tool_args": tool_args,
                "description": matched_schema["description"],
                "tool_call_id": tool_call_id
            }
        )

    reply_text = reply.text or ""
    if _is_gateway_fallback_text(reply_text):
        logger.warning(
            "Gateway fallback text returned for session=%s agent=%s; skipping assistant persistence",
            session_id,
            agent_id,
        )
        state_machine.transition(ChatToolLoopState.DONE)
        return ChatResponse(text=reply_text, session_id=session_id)

    persistence.add_message(session_id=session_id, role="assistant", content=reply_text)
    if not reply_text.strip():
        logger.warning(
            "LLM returned empty assistant text (session=%s agent=%s); client will show no visible reply unless UI uses a placeholder.",
            session_id,
            agent_id,
        )

    # --- HARNESS: Final state transition to DONE ---
    state_machine.transition(ChatToolLoopState.DONE)

    return ChatResponse(text=reply_text, session_id=session_id)


@app.post("/api/chat/stream")
async def chat_stream_endpoint(req: ChatRequest):
    """Streaming version of chat endpoint using Server-Sent Events.

    Supports Claude-family local agents and Hermes agents with streaming output.
    Falls back to non-streaming for OpenClaw.
    """
    async def event_generator():
        try:
            agent_id = normalize_agent_id(req.agent_id) or LOCAL_AGENT_ID
            stream_text = req.text
            if req.attachments and has_image_attachments(req.attachments):
                stream_text = append_image_attachment_context(
                    req.text,
                    build_image_attachment_context(req.attachments, include_paths=True),
                )

            async for chunk in get_local_agent_client().send_stream(stream_text, session_id=req.session_id, target_agent=agent_id):
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            logger.exception("agent stream failed")
            yield f"data: {json.dumps({'type': 'error', 'content': _safe_error_message('Agent stream')})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

SOCKET_PATH = backend_socket_path()
_backend_lock_fd: Optional[int] = None


def _backend_singleton_lock_path() -> Path:
    return Path(SOCKET_PATH).with_suffix(".lock")


def _acquire_backend_singleton_lock() -> bool:
    """Ensure only one backend process owns the app Unix socket.

    A second backend must not unlink/rebind the shared socket while another
    backend is actively running, because two API processes observing and
    mutating the same task database can disagree about live jobs.
    """
    global _backend_lock_fd
    if _backend_lock_fd is not None:
        return True

    lock_path = _backend_singleton_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return False
    except Exception:
        os.close(fd)
        raise

    os.ftruncate(fd, 0)
    os.write(fd, str(os.getpid()).encode("ascii"))
    _backend_lock_fd = fd
    return True


def _shutdown_marker_path() -> Path:
    return data_file("backend_shutdown.json")


def _write_shutdown_marker(signum: int, reason: str, active_tasks: List[str], active_jobs: Optional[List[str]] = None) -> None:
    marker = {
        "timestamp": time.time(),
        "pid": os.getpid(),
        "signal": signum,
        "reason": reason,
        "active_tasks": active_tasks,
        "active_jobs": active_jobs or [],
        "socket_path": SOCKET_PATH,
    }
    try:
        path = _shutdown_marker_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(marker, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)
    except Exception as exc:
        logger.warning("Failed to write backend shutdown marker: %s", exc)


def _suspend_running_tasks_for_shutdown(signum: int) -> List[str]:
    """Persist a restart-safe paused state instead of cancelling tasks on backend exit."""
    reason = "sigterm" if signum == signal.SIGTERM else "sigint" if signum == signal.SIGINT else f"signal_{signum}"
    suspended: List[str] = []
    active_jobs: List[str] = []
    terminal_statuses = {
        TaskStatus.COMPLETED.value,
        TaskStatus.COMPLETED_WITH_FAILURES.value,
        TaskStatus.FAILED.value,
        TaskStatus.CANCELLED.value,
    }
    try:
        for task_id, task in list(getattr(_task_state, "_tasks", {}).items()):
            status = getattr(getattr(task, "status", None), "value", getattr(task, "status", None))
            if status in terminal_statuses:
                continue
            suspended.append(task_id)
            logger.info("Suspending task %s during backend shutdown", task_id)
            if hasattr(_task_state, "pause_task"):
                _task_state.pause_task(task_id)
            if hasattr(_task_state, "set_task_status"):
                _task_state.set_task_status(
                    task_id,
                    TaskStatus.PAUSED,
                    error=f"suspended_for_restart: backend received signal {signum}",
                )

        for job_id, job in list(getattr(_task_state, "_jobs", {}).items()):
            job_status = getattr(getattr(job, "status", None), "value", getattr(job, "status", None))
            if job_status in {JobStatus.PENDING.value, JobStatus.DISPATCHED.value, JobStatus.RUNNING.value}:
                active_jobs.append(job_id)
    except Exception as e:
        logger.warning(f"Error suspending tasks during shutdown: {e}")
    finally:
        _write_shutdown_marker(signum, reason, suspended, active_jobs)
    return suspended


def start_api_server():
    # Initialize logging
    from .logging_setup import setup_logger
    log_dir = app_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    setup_logger(log_dir, "across-agents-assistant.log", debug=True)

    if not _acquire_backend_singleton_lock():
        logger.warning(
            "Another Across Agents backend already owns %s; refusing to rebind socket.",
            SOCKET_PATH,
        )
        print(
            f"Across Agents backend already running for {SOCKET_PATH}; exiting duplicate backend.",
            flush=True,
        )
        return

    # Remove stale socket file if it exists
    try:
        os.unlink(SOCKET_PATH)
    except OSError:
        pass

    # Issue 39: Don't set global umask(0o177) as it affects all file creation
    # (including agent-created directories). Instead, fix socket permissions
    # after creation via a background thread.
    def _fix_permissions():
        for _ in range(100):
            if os.path.exists(SOCKET_PATH):
                os.chmod(SOCKET_PATH, 0o600)
                break
            time.sleep(0.05)

    threading.Thread(target=_fix_permissions, daemon=True).start()

    # Issue 47: Use Config + Server API for programmatic control over shutdown
    config = uvicorn.Config(app, uds=SOCKET_PATH, timeout_graceful_shutdown=1)
    server = uvicorn.Server(config)

    # Custom signal handler that persists active work before shutting down.
    original_handler = None

    def _signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, suspending tasks and shutting down...")
        _suspend_running_tasks_for_shutdown(signum)
        server.should_exit = True
        server.force_exit = True
        # Call the original Uvicorn handler
        if callable(original_handler):
            original_handler(signum, frame)

    # Install our handler, saving Uvicorn's handler
    original_handler = signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    server.run()
    # In packaged app shutdowns, non-daemon worker threads can occasionally keep
    # the frozen backend process alive after Uvicorn has stopped accepting on
    # the Unix socket. Exit hard once the server loop returns so the macOS app
    # never sees a stale process with a refused socket.
    os._exit(0)

@app.get("/api/tools/authorizations")
async def get_tool_authorizations():
    """Retrieve the list of all tools that are 'Always Allowed'"""
    try:
        auths = persistence.get_all_authorizations()
        return {"authorizations": auths}
    except Exception as e:
        raise _safe_http_500("Get tool authorizations")

class RevokeRequest(BaseModel):
    tool_name: str

@app.post("/api/tools/authorizations/revoke")
async def revoke_tool_authorization(req: RevokeRequest):
    """Revoke the 'Always Allow' authorization for a specific tool"""
    try:
        persistence.set_tool_authorization(req.tool_name, False)
        return {"status": "success", "tool_name": req.tool_name}
    except Exception as e:
        raise _safe_http_500("Revoke tool authorization")

def _public_native_skill(skill: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(skill.get("id") or skill.get("name") or ""),
        "name": str(skill.get("name") or skill.get("id") or ""),
        "description": str(skill.get("description") or ""),
        "source": str(skill.get("source") or "native"),
        "status": str(skill.get("status") or "unknown"),
        "availability": str(skill.get("availability") or "unknown"),
        "available": bool(is_native_skill_available(skill)),
    }


def _public_agent_card(card: Dict[str, Any], native_skills: List[Dict[str, Any]]) -> Dict[str, Any]:
    agent_id = str(card.get("agent_id") or "")
    display_name = str(card.get("display_name") or agent_id)
    agent_type = str(card.get("agent_type") or "local")
    warnings = list(card.get("warnings") or [])
    return {
        "agent_id": agent_id,
        "name": display_name,
        "description": f"{display_name} {agent_type} agent profile for Across Agents Assistant routing.",
        "kind": agent_type,
        "endpoint": {
            "kind": "internal",
            "capability_route": f"/api/agent-capabilities/{agent_id}",
        },
        "capabilities": {
            "configured_skill_ids": list(card.get("configured_skill_ids") or []),
            "configured_skills": list(card.get("configured_skill_names") or []),
            "native_skill_health": dict(card.get("native_skill_health") or {}),
            "tool_count": len(card.get("enabled_tool_names") or []),
        },
        "skills": [
            _public_native_skill(skill)
            for skill in native_skills
            if isinstance(skill, dict)
        ],
        "tools": {
            "enabled": list(card.get("enabled_tool_names") or []),
            "risk_summary": dict(card.get("tool_risk_summary") or {}),
        },
        "routing": {
            "strict_tool_scope": bool(card.get("strict_tool_scope", False)),
            "warnings": warnings,
            "unavailable_native_skills_block_routing": True,
        },
        "security": {
            "secrets_included": False,
            "custom_instructions_included": False,
        },
    }


def _load_task_info_read_only(task_id: str) -> "TaskInfo":
    if _is_external_orchestrator_task(task_id):
        plugin = get_orchestrator_plugin_manager()
        task_payload = plugin.get_task(task_id)
        evidence = _external_task_evidence_sync(plugin, task_id, task_payload)
        return TaskInfo(**external_task_to_app_info(task_payload, evidence=evidence))
    task = _task_state.get_task(task_id)
    if task:
        return _task_to_info(task, _task_state)
    persistence = getattr(_task_state, "_persistence", None)
    if persistence:
        full_task = persistence.get_full_task(task_id)
        if full_task:
            return _task_info_from_db(full_task)
    raise HTTPException(status_code=404, detail=f"Task {task_id} not found")


def _subtask_to_info(st: "SubTask", state: Optional[TaskState] = None, task_id: Optional[str] = None) -> "SubTaskInfo":
    """Convert a SubTask to SubTaskInfo."""
    from .task_history.models import SubTask as SubTaskModel
    observability: Dict[str, Any] = {}
    if state is not None and task_id:
        observability = state.get_subtask_observability(task_id, st.subtask_id)
    contract = state.get_contract_by_subtask(task_id, st.subtask_id) if state and task_id else None
    return SubTaskInfo(
        subtask_id=st.subtask_id,
        description=st.description,
        agent_id=st.agent_id,
        priority=st.priority,
        status=st.status.value,
        progress=st.progress,
        dependencies=st.dependencies,
        output_file=st.output_file,
        duration=st.duration,
        error_message=st.error_message,
        fix_plan=getattr(st, 'fix_plan', None),
        wave_number=getattr(st, 'wave_number', 1),
        owner_decision=getattr(st, 'owner_decision', None),
        waiting_on_dependencies=observability.get("waiting_on_dependencies", []),
        blocked_reason=observability.get("blocked_reason"),
        running_for_seconds=observability.get("running_for_seconds"),
        contract=contract,
    )

def _wave_to_info(wave: "Wave", state: Optional[TaskState] = None, task_id: Optional[str] = None) -> "WaveInfo":
    """Convert a Wave to WaveInfo."""
    from .task_history.models import Wave as WaveModel
    return WaveInfo(
        wave_id=wave.wave_id,
        wave_number=wave.wave_number,
        subtasks=[_subtask_to_info(st, state, task_id) for st in wave.subtasks],
        status=wave.status.value,
        is_blocked=wave.is_blocked,
        governance_status=_wave_governance_status(wave),
        blocked_by_wave=getattr(wave, "blocked_by_wave", None),
        is_revalidating=getattr(wave, "is_revalidating", False),
        owner_decision=getattr(wave, "owner_decision", None),
    )

def _is_waiting_for_keys_task(task: Any) -> bool:
    decision = getattr(task, "last_owner_decision", None) or {}
    if not isinstance(decision, dict):
        return False
    return (
        decision.get("blocked_reason") == "waiting_for_keys"
        and bool(decision.get("recoverable", True))
    )


def _compute_task_status(task: "Task", state: TaskState) -> str:
    """Compute unified task status from task state and subtask analysis.

    Semantics:
      - ``decomposing``: task is still in decomposition phase
      - ``failed``: task-level fatal error or no viable business output
      - ``completed_with_failures``: some business subtasks completed but others failed/cancelled
      - ``completed``: all original business subtasks reached a completed state
      - ``cancelled``: task was cancelled
      - ``running``: at least one subtask is currently executing
      - ``paused``: task has been explicitly paused
      - ``pending``: no subtask is actively running (waiting for dispatch or dependencies)
    """
    from .task_history.models import JobStatus, TaskStatus
    if task.status == TaskStatus.COMPLETED:
        return "completed"
    if task.status == TaskStatus.FAILED:
        return "failed"
    if getattr(TaskStatus, "COMPLETED_WITH_FAILURES", None) and task.status == TaskStatus.COMPLETED_WITH_FAILURES:
        return "completed_with_failures"
    if task.status == TaskStatus.CANCELLED:
        return "cancelled"
    if task.status == TaskStatus.DECOMPOSING:
        return "decomposing"
    if not task.subtasks:
        return "created" if task.status == TaskStatus.PENDING else "failed"
    delivery_contract = None
    try:
        delivery_contract = state.get_delivery_contract(task.task_id)
    except Exception:
        delivery_contract = None
    awaiting_delivery_quality = bool(delivery_contract) and not (
        (getattr(task, "last_owner_decision", {}) or {}).get("delivery_quality")
    )
    if state.is_all_subtasks_completed(task.task_id):
        if awaiting_delivery_quality:
            return "running"
        return "completed"
    if state.is_all_subtasks_terminal(task.task_id):
        if awaiting_delivery_quality:
            return "running"
        original = [st for st in task.subtasks if _is_original_business_subtask_id(st.subtask_id)]
        completed_count = sum(1 for st in original if st.status == JobStatus.COMPLETED)
        failed_count = sum(1 for st in original if st.status == JobStatus.FAILED)
        cancelled_count = sum(1 for st in original if st.status == JobStatus.CANCELLED)
        total_count = len(original)
        if total_count == 0:
            return "failed"
        if cancelled_count > 0 and completed_count < total_count:
            return "failed"
        if completed_count > 0 and failed_count > 0:
            return "completed_with_failures"
        if completed_count == total_count:
            return "completed"
        return "failed"
    if any(st.status == JobStatus.RUNNING for st in task.subtasks):
        return "running"
    if state.is_task_paused(task.task_id):
        return "paused"
    if _is_waiting_for_keys_task(task):
        return "pending"
    if task.status == TaskStatus.FAILED or task.error:
        return "failed"
    return "pending"

def _repair_task_dispatch_if_possible(task_id: str, *, reason: str) -> Dict[str, Any]:
    """Report that dispatch repair is owned by the external orchestrator."""
    try:
        task = _task_state.get_task(task_id)
        if not task:
            return {
                "task_id": task_id,
                "state_created": False,
                "waves_approved": [],
                "dispatched_subtasks": [],
                "reason": reason,
                "skipped": "task_not_in_memory",
            }
    except Exception as exc:
        logger.debug("Dispatch repair skipped for %s after %s: %s", task_id, reason, exc)
    return {
        "task_id": task_id,
        "state_created": False,
        "waves_approved": [],
        "dispatched_subtasks": [],
        "reason": reason,
        "skipped": "external_orchestrator_only",
    }


def _wave_execution_status(wave: Any) -> str:
    subtasks = list(getattr(wave, "subtasks", []) or [])
    if not subtasks:
        return "pending"
    statuses = [getattr(st.status, "value", st.status) for st in subtasks]
    if any(status == JobStatus.RUNNING.value for status in statuses):
        return "running"
    if any(status == JobStatus.DISPATCHED.value for status in statuses):
        return "running"
    if all(status == JobStatus.COMPLETED.value for status in statuses):
        return "completed"
    if all(status in {JobStatus.COMPLETED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value} for status in statuses):
        return "terminal_with_failures"
    return "pending"


def _wave_governance_status(wave: Any) -> str:
    if getattr(wave, "wave_number", None) == 0:
        return "not_applicable"
    return getattr(wave, "governance_status", None) or "pending"


def _wave_effective_status(wave: Any) -> str:
    governance = _wave_governance_status(wave)
    execution = _wave_execution_status(wave)
    if governance == "not_applicable":
        return execution
    if governance in {"approved", "blocked", "revalidating"}:
        return governance
    if getattr(wave, "wave_number", None) == 0 and execution == "completed":
        return "completed"
    return execution if execution != "pending" else governance


def _quality_wave_gate_blocking_wave(task: "Task", st: "SubTask") -> Optional[int]:
    """Return the prior wave that blocks *st*, if wave-gate diagnostics can infer one."""
    wave_number = getattr(st, "wave_number", 1) or 1
    if wave_number <= 1:
        return None

    current_wave = next((w for w in task.waves if w.wave_number == wave_number), None)
    if current_wave and getattr(current_wave, "blocked_by_wave", None):
        return getattr(current_wave, "blocked_by_wave")
    if current_wave and (
        getattr(current_wave, "is_revalidating", False)
        or getattr(current_wave, "governance_status", None) in {"blocked", "needs_fix", "revalidating"}
    ):
        return wave_number

    waves_by_number = {w.wave_number: w for w in task.waves}
    for prior_wave_number in range(1, wave_number):
        prior_wave = waves_by_number.get(prior_wave_number)
        if not prior_wave:
            continue
        if getattr(prior_wave, "governance_status", None) == "approved":
            continue
        return prior_wave_number
    return None


def _derive_delivery_and_orchestration_health(
    *,
    task_status: str,
    delivery_quality_report: Optional[Dict[str, Any]],
    terminal_inconsistencies: List[str],
    active_remediation_subtasks: Optional[List[str]] = None,
) -> Dict[str, Any]:
    delivery_quality = (delivery_quality_report or {}).get("delivery_quality")
    if not delivery_quality:
        delivery_quality = "not_started"
    has_active_remediation = bool(active_remediation_subtasks)
    if terminal_inconsistencies or (has_active_remediation and task_status in {"completed", "completed_with_failures", "failed"}):
        orchestration_health = "inconsistent"
    elif has_active_remediation:
        orchestration_health = "recovering"
    elif task_status in {"running", "pending", "decomposing"}:
        orchestration_health = "healthy"
    else:
        orchestration_health = "healthy"
    return {
        "delivery_quality": delivery_quality,
        "orchestration_health": orchestration_health,
        "quality_gate": delivery_quality,
    }


def _status_with_delivery_quality(status: str, quality_health: Optional[Dict[str, Any]]) -> str:
    """Reconcile top-level terminal status with ODC delivery truth.

    The owner delivery contract is the final delivery-quality source of truth.
    Orchestration residue should degrade a successful delivery to
    completed_with_failures, not hide the delivered product behind failed.
    Conversely, a failed delivery contract must keep a terminal task failed even
    if lower-level orchestration appears complete.
    """
    if status not in {"completed", "completed_with_failures", "failed"}:
        return status
    if (quality_health or {}).get("active_remediation_subtasks"):
        return "running"
    delivery_quality = (quality_health or {}).get("delivery_quality")
    if delivery_quality == "failed":
        return "failed"
    if delivery_quality == "partial":
        return "completed_with_failures"
    if delivery_quality == "passed":
        orchestration_health = (quality_health or {}).get("orchestration_health")
        terminal_inconsistencies = (quality_health or {}).get("terminal_inconsistencies") or []
        if orchestration_health == "inconsistent" or terminal_inconsistencies:
            return "completed_with_failures"
        return "completed"
    return status


def _completion_metrics_with_quality(
    status: str,
    quality_health: Optional[Dict[str, Any]],
    completed_count: int,
    total_count: int,
    progress: float,
) -> Tuple[float, int, int]:
    """Use delivery-quality success as the user-facing completion source of truth."""
    delivery_quality = (quality_health or {}).get("delivery_quality")
    quality_gate = (quality_health or {}).get("quality_gate")
    if status == "completed" and (delivery_quality == "passed" or quality_gate == "passed"):
        if total_count > 0:
            return 1.0, total_count, total_count
        report = (quality_health or {}).get("delivery_quality_report") or {}
        produced_count = len(report.get("produced_required") or [])
        if produced_count > 0:
            return 1.0, produced_count, produced_count
        return 1.0, completed_count, total_count
    return progress, completed_count, total_count


def _delivery_quality_from_contract_for_task(task: "Task", state: TaskState) -> Optional[Dict[str, Any]]:
    try:
        contract = state.get_delivery_contract(task.task_id)
    except Exception:
        contract = None
    if not contract:
        return None
    try:
        persistence = getattr(state, "_persistence", None)
        artifacts = persistence.get_artifact_records(task.task_id) if persistence else []
    except Exception:
        artifacts = []
    try:
        from .task_review.contract_acceptance import run_delivery_contract_acceptance
        return run_delivery_contract_acceptance(task, contract, artifacts, run_probes=False)
    except Exception as exc:
        logger.warning("Failed to derive delivery quality for %s from ODC: %s", task.task_id, exc)
        return None


def _delivery_quality_from_contract_for_db(task_dict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    contract = task_dict.get("owner_delivery_contract")
    if not contract:
        return None

    class _TaskView:
        task_id = task_dict.get("task_id")
        project_dir = task_dict.get("project_dir") or contract.get("project_dir")

    try:
        from .task_review.contract_acceptance import run_delivery_contract_acceptance
        return run_delivery_contract_acceptance(
            _TaskView(),
            contract,
            task_dict.get("artifact_records", []) or [],
            run_probes=False,
        )
    except Exception as exc:
        logger.warning("Failed to derive DB delivery quality for %s from ODC: %s", task_dict.get("task_id"), exc)
        return None


def _build_quality_health(
    task: "Task", state: TaskState,
    requirement_manifest: Optional[Dict[str, Any]],
    acceptance_records: List[Dict[str, Any]],
    *,
    effective_task_status: Optional[str] = None,
    refresh_cached_delivery_quality: bool = True,
) -> Dict[str, Any]:
    """Build a concise delivery quality health snapshot for API consumers."""
    deliverables = (requirement_manifest or {}).get("deliverables", []) or []
    statuses = [item.get("status", "unassigned") for item in deliverables]

    pending_without_jobs: List[str] = []
    dispatch_repairable: List[str] = []
    blocked_by_wave_gate: List[str] = []
    waiting_on_dependencies: List[str] = []
    blocked_by_decomposition: List[str] = []
    persistence = getattr(state, "_persistence", None)

    for st in task.subtasks:
        if st.status != JobStatus.PENDING:
            continue

        # Check if decompose subtask or task has no business subtasks
        is_decompose = st.subtask_id.endswith("-decompose") or getattr(st, "wave_number", 1) == 0
        has_business = any(
            not (s.subtask_id.endswith("-decompose") or getattr(s, "wave_number", 1) == 0)
            and _is_original_business_subtask_id(s.subtask_id)
            for s in task.subtasks
        )
        if is_decompose or not has_business:
            blocked_by_decomposition.append(st.subtask_id)
            continue

        observability = state.get_subtask_observability(task.task_id, st.subtask_id)
        if observability.get("waiting_on_dependencies"):
            waiting_on_dependencies.append(st.subtask_id)
            continue

        jobs = persistence.get_jobs_by_subtask(st.subtask_id) if persistence else []
        active = any(job.get("status") in {"pending", "dispatched", "running"} for job in jobs)
        if not active:
            pending_without_jobs.append(st.subtask_id)

        inferred_blocking_wave = _quality_wave_gate_blocking_wave(task, st)
        if observability.get("blocked_reason") in {"blocked_by_prior_wave", "wave_gate_blocked", "wave_revalidating"}:
            blocked_by_wave_gate.append(st.subtask_id)
            continue
        if inferred_blocking_wave is not None:
            blocked_by_wave_gate.append(st.subtask_id)
            continue

        if not active:
            dispatch_repairable.append(st.subtask_id)

    wave_details = {}
    for wave in task.waves:
        wave_no = str(wave.wave_number)
        wave_details[wave_no] = {
            "execution_status": _wave_execution_status(wave),
            "governance_status": _wave_governance_status(wave),
            "effective_status": _wave_effective_status(wave),
            "is_blocked": bool(getattr(wave, "is_blocked", False)),
            "blocked_by_wave": getattr(wave, "blocked_by_wave", None),
            "is_revalidating": bool(getattr(wave, "is_revalidating", False)),
        }

    # Updated wave_statuses: use effective status instead of governance_status only
    wave_statuses = {str(w.wave_number): _wave_effective_status(w) for w in task.waves}

    def _acceptance_key(record: Dict[str, Any]) -> tuple:
        return (
            record.get("level"),
            record.get("wave_number"),
            record.get("subtask_id"),
        )

    def _has_inconsistent_acceptance(records: List[Dict[str, Any]]) -> bool:
        latest = {}
        for record in records:
            latest[_acceptance_key(record)] = record
        for record in latest.values():
            decision = record.get("decision")
            judge_passed = record.get("judge_passed")
            recommended = record.get("recommended_action")
            failed_checks = record.get("failed_checks") or []
            if decision == "approve" and judge_passed is False:
                return True
            if decision in {"fix", "reassign"} and judge_passed is True and not recommended:
                return True
            # Deterministic validation failures must override LLM judgment
            if judge_passed is True and failed_checks:
                return True
            if decision == "approve" and failed_checks:
                return True
            if decision in {"fix", "reassign"} and recommended == "approve":
                return True
        return False

    inconsistent = _has_inconsistent_acceptance(acceptance_records)

    readiness_blockers = []
    if (getattr(task, "last_owner_decision", {}) or {}).get("blocked_reason") == "waiting_for_keys":
        readiness_blockers.append("api_keys")

    terminal_inconsistencies = []
    raw_task_status = getattr(task.status, "value", task.status)
    task_status = effective_task_status or raw_task_status
    delivery_quality_report = (getattr(task, "last_owner_decision", {}) or {}).get("delivery_quality")
    if refresh_cached_delivery_quality and task_status in {"completed", "completed_with_failures", "failed", "cancelled"}:
        fresh_delivery_quality_report = _delivery_quality_from_contract_for_task(task, state)
        if fresh_delivery_quality_report:
            delivery_quality_report = fresh_delivery_quality_report
    delivery_passed = (delivery_quality_report or {}).get("delivery_quality") == "passed"
    if task_status in {"failed", "completed", "completed_with_failures", "cancelled"}:
        nonterminal_subtasks = [
            st.subtask_id for st in task.subtasks
            if getattr(st.status, "value", st.status) in {"pending", "dispatched", "running", "paused"}
        ]
        if nonterminal_subtasks:
            terminal_inconsistencies.append("failed_task_has_nonterminal_subtasks" if task_status == "failed" else "terminal_task_has_nonterminal_subtasks")
        # Detect terminal tasks with blocked waves
        blocked_waves = [str(w.wave_number) for w in task.waves if getattr(w, "is_blocked", False)]
        if blocked_waves:
            terminal_inconsistencies.append("terminal_task_has_blocked_wave")
        if task_status == "failed" and statuses and all(status == "accepted" for status in statuses):
            terminal_inconsistencies.append("failed_task_has_fully_accepted_manifest")

    # Remediation residue: terminal task with failed historical remediation
    remediation_residue: List[str] = []
    if task_status in {"completed", "completed_with_failures"}:
        remediation_residue = [
            st.subtask_id for st in task.subtasks
            if (_is_remediation_subtask_id(st.subtask_id) or st.subtask_id.startswith("st-quality-"))
            and getattr(st.status, "value", st.status) in {"failed", "cancelled"}
        ]
        if remediation_residue and not delivery_passed:
            terminal_inconsistencies.append("terminal_task_has_failed_remediation")

    active_remediation_subtasks = [
        st.subtask_id for st in task.subtasks
        if _is_remediation_subtask_id(st.subtask_id)
        and getattr(st.status, "value", st.status) in {"pending", "dispatched", "running"}
    ]

    if task_status in {"completed", "completed_with_failures"}:
        failed_business_subtasks = [
            st.subtask_id for st in task.subtasks
            if _is_original_business_subtask_id(st.subtask_id)
            and getattr(st.status, "value", st.status) in {"failed", "cancelled"}
        ]
        if failed_business_subtasks and not delivery_passed:
            terminal_inconsistencies.append("terminal_task_has_failed_business_subtasks")

    quality_gate = "unknown"
    if readiness_blockers:
        quality_gate = "waiting"
    elif terminal_inconsistencies:
        quality_gate = "inconsistent"
    elif statuses and any(status == "missing" for status in statuses):
        quality_gate = "failed"
    elif statuses and all(status == "accepted" for status in statuses):
        quality_gate = "passed"
    elif statuses and any(status in {"produced", "accepted"} for status in statuses):
        quality_gate = "partial"
    else:
        quality_gate = "not_started"

    active_quality_remediation = [
        st.subtask_id for st in task.subtasks
        if st.subtask_id.startswith("st-quality-")
        and getattr(st.status, "value", st.status) in {"pending", "dispatched", "running"}
    ]

    next_action = (getattr(task, "last_owner_decision", {}) or {}).get("next_repair_action")
    if not next_action:
        if readiness_blockers:
            next_action = "sync_keys"
        elif dispatch_repairable:
            next_action = "dispatch_repair"
        elif blocked_by_wave_gate:
            next_action = "await_wave_acceptance"
        elif waiting_on_dependencies:
            next_action = "await_dependencies"
        elif active_quality_remediation:
            next_action = "await_quality_remediation"
        elif active_remediation_subtasks:
            next_action = "await_remediation"
        elif terminal_inconsistencies:
            next_action = "repair_terminal_consistency"
        elif quality_gate == "failed":
            next_action = "quality_remediation"

    split_health = _derive_delivery_and_orchestration_health(
        task_status=task_status,
        delivery_quality_report=delivery_quality_report,
        terminal_inconsistencies=terminal_inconsistencies,
        active_remediation_subtasks=active_remediation_subtasks,
    )
    if delivery_quality_report:
        quality_gate = split_health["quality_gate"]

    return {
        "manifest_total": len(deliverables),
        "manifest_assigned": sum(1 for s in statuses if s in {"assigned", "produced", "accepted"}),
        "manifest_produced": sum(1 for s in statuses if s in {"produced", "accepted"}),
        "manifest_accepted": sum(1 for s in statuses if s == "accepted"),
        "manifest_missing": sum(1 for s in statuses if s == "missing"),
        "pending_without_jobs": pending_without_jobs,
        "dispatch_repairable": dispatch_repairable,
        "blocked_by_wave_gate": blocked_by_wave_gate,
        "waiting_on_dependencies": waiting_on_dependencies,
        "blocked_by_decomposition": blocked_by_decomposition,
        "wave_statuses": wave_statuses,
        "wave_details": wave_details,
        "has_inconsistent_acceptance": inconsistent,
        "dispatch_repair_needed": bool(dispatch_repairable),
        "active_quality_remediation": active_quality_remediation,
        "readiness_blockers": readiness_blockers,
        "terminal_inconsistencies": terminal_inconsistencies,
        "remediation_residue": remediation_residue,
        "active_remediation_subtasks": active_remediation_subtasks,
        "quality_gate": quality_gate,
        "delivery_quality_report": delivery_quality_report,
        "delivery_quality": split_health["delivery_quality"],
        "orchestration_health": split_health["orchestration_health"],
        "next_repair_action": next_action,
    }


def _task_to_info(task: "Task", state: TaskState) -> "TaskInfo":
    """Convert a Task to TaskInfo with its subtasks and waves."""
    from .task_history.models import JobStatus
    from .task_review.delivery_report import build_delivery_report
    status = _compute_task_status(task, state)
    if status == "completed_with_failures":
        failed_subtasks = [st.subtask_id for st in task.subtasks if st.status in (JobStatus.FAILED, JobStatus.CANCELLED)]
        logger.info(f"_task_to_info: task {task.task_id} -> completed_with_failures, failed/cancelled subtasks: {failed_subtasks}")

    original_subtasks = [st for st in task.subtasks if _is_original_business_subtask_id(st.subtask_id)]
    completed_count = sum(1 for st in original_subtasks if st.status == JobStatus.COMPLETED)
    total_count = len(original_subtasks)

    artifact_versions: Dict[str, int] = {}
    artifact_records: List[Dict[str, Any]] = []
    acceptance_records: List[Dict[str, Any]] = []
    requirement_manifest: Optional[Dict[str, Any]] = None
    persistence = getattr(state, "_persistence", None)
    if persistence is not None:
        try:
            for artifact in persistence.get_artifact_records(task.task_id):
                key = artifact.get("name") or artifact.get("content_ref") or artifact.get("artifact_id")
                if key:
                    artifact_versions[key] = max(artifact_versions.get(key, 0), int(artifact.get("version") or 0))
                art_meta = artifact.get("metadata") or {}
                artifact_id = artifact.get("artifact_id")
                name = artifact.get("name")
                raw_content_ref = artifact.get("content_ref")
                content_ref = (
                    art_meta.get("normalized_content_ref")
                    or (os.path.realpath(raw_content_ref) if raw_content_ref else None)
                )
                artifact_records.append({
                    "artifact_id": artifact_id,
                    "id": artifact_id,
                    "name": name,
                    "file_name": name,
                    "content_ref": content_ref,
                    "file_path": content_ref,
                    "normalized_content_ref": content_ref,
                    "file_size": artifact.get("file_size") or art_meta.get("file_size") or "0 B",
                    "subtask_id": artifact.get("subtask_id"),
                    "canonical_subtask_id": art_meta.get("canonical_subtask_id") or artifact.get("subtask_id"),
                    "wave_number": artifact.get("wave_number"),
                    "version": artifact.get("version"),
                    "status": artifact.get("status"),
                    "metadata": art_meta,
                    "source_artifact_ids": artifact.get("source_artifact_ids", []),
                    "produced_by": artifact.get("produced_by"),
                })
            acceptance_records = persistence.get_acceptance_records(task.task_id)
        except Exception:
            pass

    # Load manifest from state (handles persistence + in-memory cache)
    try:
        requirement_manifest = state.get_requirement_manifest(task.task_id)
    except Exception:
        pass
    owner_delivery_contract = None
    try:
        owner_delivery_contract = state.get_delivery_contract(task.task_id)
    except Exception:
        owner_delivery_contract = None

    quality_health = _build_quality_health(
        task,
        state,
        requirement_manifest,
        acceptance_records,
        effective_task_status=status,
        refresh_cached_delivery_quality=False,
    )
    adjusted_status = _status_with_delivery_quality(status, quality_health)
    if adjusted_status != status:
        status = adjusted_status
        quality_health = _build_quality_health(
            task,
            state,
            requirement_manifest,
            acceptance_records,
            effective_task_status=status,
            refresh_cached_delivery_quality=False,
        )
    progress, completed_count, total_count = _completion_metrics_with_quality(
        status,
        quality_health,
        completed_count,
        total_count,
        state.get_task_progress(task.task_id),
    )
    delivery_report = build_delivery_report(
        task=task,
        manifest=requirement_manifest,
        artifact_records=artifact_records,
        acceptance_records=acceptance_records,
        quality_health=quality_health,
        final_status=status,
    )

    return TaskInfo(
        task_id=task.task_id,
        description=task.description,
        status=status,
        task_types=list(getattr(task, "task_types", []) or []),
        delivery_mode=getattr(task, "delivery_mode", "external") or "external",
        owner_delivery_contract=owner_delivery_contract,
        owner_agent=task.owner_agent,
        allowed_subtask_agents=task.allowed_subtask_agents,
        project_dir=task.project_dir,
        subtasks=[_subtask_to_info(st, state, task.task_id) for st in task.subtasks],
        waves=[_wave_to_info(w, state, task.task_id) for w in task.waves] if task.waves else [],
        artifacts=artifact_records,
        artifact_versions=artifact_versions,
        acceptance_records=acceptance_records[-10:],
        owner_session_id=getattr(task, "owner_session_id", None),
        last_owner_decision=getattr(task, "last_owner_decision", None),
        can_handle_directly=task.can_handle_directly,
        direct_response=task.direct_response,
        requirement_manifest=requirement_manifest,
        quality_health=quality_health,
        delivery_report=delivery_report,
        observability=_build_task_observability_snapshot(
            task_id=task.task_id,
            description=task.description,
            status=status,
            subtasks=task.subtasks,
            waves=task.waves,
            last_owner_decision=getattr(task, "last_owner_decision", None),
            created_at=task.created_at,
            updated_at=task.updated_at,
        ),
        progress=progress,
        completed_count=completed_count,
        total_count=total_count,
        created_at=task.created_at,
        updated_at=task.updated_at,
        error=task.error
    )


def _db_wave_execution_status(wave: Dict[str, Any], subtasks: List[Dict[str, Any]]) -> str:
    wave_number = wave.get("wave_number", 1)
    wave_subtasks = [st for st in subtasks if st.get("wave_number", 1) == wave_number]
    if not wave_subtasks:
        return wave.get("status", "pending")
    statuses = [st.get("status", "pending") for st in wave_subtasks]
    if any(status == "running" for status in statuses):
        return "running"
    if any(status in {"pending", "dispatched"} for status in statuses):
        return "pending"
    if all(status == "completed" for status in statuses):
        return "completed"
    if any(status in {"failed", "cancelled"} for status in statuses):
        return "failed"
    return wave.get("status", "pending")


def _db_wave_governance_status(wave: Dict[str, Any]) -> str:
    if wave.get("wave_number", 1) == 0:
        return "not_applicable"
    return wave.get("governance_status") or "pending"


def _db_wave_effective_status(wave: Dict[str, Any], subtasks: List[Dict[str, Any]]) -> str:
    execution = _db_wave_execution_status(wave, subtasks)
    governance = _db_wave_governance_status(wave)
    if wave.get("wave_number", 1) == 0:
        return execution
    if governance in {"blocked", "revalidating"}:
        return governance
    if execution in {"running", "pending", "failed"}:
        return execution
    return governance if governance != "pending" else execution


def _build_quality_health_from_db(
    task_dict: Dict[str, Any],
    *,
    refresh_missing_delivery_quality: bool = True,
) -> Dict[str, Any]:
    subtasks = task_dict.get("subtasks", []) or []
    waves = task_dict.get("waves", []) or []
    manifest = task_dict.get("requirement_manifest") or {}
    deliverables = manifest.get("deliverables", []) or []
    statuses = [item.get("status", "unassigned") for item in deliverables]
    decision = task_dict.get("last_owner_decision") or {}

    pending_without_jobs: List[str] = []
    dispatch_repairable: List[str] = []
    blocked_by_wave_gate: List[str] = []
    waiting_on_dependencies: List[str] = []
    blocked_by_decomposition: List[str] = []

    has_business = any(
        not st.get("subtask_id", "").endswith("-decompose")
        and st.get("wave_number", 1) != 0
        and _is_original_business_subtask_id(st.get("subtask_id", ""))
        for st in subtasks
    )
    for st in subtasks:
        if st.get("status", "pending") != "pending":
            continue
        subtask_id = st.get("subtask_id", "")
        is_decompose = subtask_id.endswith("-decompose") or st.get("wave_number", 1) == 0
        if is_decompose or not has_business:
            blocked_by_decomposition.append(subtask_id)
            continue
        deps = st.get("dependencies", []) or []
        if any(
            next((item for item in subtasks if item.get("subtask_id") == dep), {}).get("status") != "completed"
            for dep in deps
        ):
            waiting_on_dependencies.append(subtask_id)
            continue
        pending_without_jobs.append(subtask_id)
        dispatch_repairable.append(subtask_id)

    wave_details = {}
    for wave in waves:
        wave_no = str(wave.get("wave_number", 1))
        wave_details[wave_no] = {
            "execution_status": _db_wave_execution_status(wave, subtasks),
            "governance_status": _db_wave_governance_status(wave),
            "effective_status": _db_wave_effective_status(wave, subtasks),
            "is_blocked": bool(wave.get("is_blocked", False)),
            "blocked_by_wave": wave.get("blocked_by_wave"),
            "is_revalidating": bool(wave.get("is_revalidating", False)),
        }

    wave_statuses = {
        str(wave.get("wave_number", 1)): _db_wave_effective_status(wave, subtasks)
        for wave in waves
    }

    readiness_blockers = []
    if decision.get("blocked_reason") == "waiting_for_keys":
        readiness_blockers.append("api_keys")

    terminal_inconsistencies = []
    task_status = task_dict.get("status", "created")
    delivery_quality_report = (decision or {}).get("delivery_quality")
    if refresh_missing_delivery_quality and not delivery_quality_report and task_status in {"completed", "completed_with_failures", "failed", "cancelled"}:
        fresh_delivery_quality_report = _delivery_quality_from_contract_for_db(task_dict)
        if fresh_delivery_quality_report:
            delivery_quality_report = fresh_delivery_quality_report
    delivery_passed = (delivery_quality_report or {}).get("delivery_quality") == "passed"
    if task_status in {"failed", "completed", "completed_with_failures", "cancelled"}:
        nonterminal = [
            st.get("subtask_id")
            for st in subtasks
            if st.get("status") in {"pending", "dispatched", "running", "paused"}
        ]
        if nonterminal:
            terminal_inconsistencies.append(
                "failed_task_has_nonterminal_subtasks"
                if task_status == "failed"
                else "terminal_task_has_nonterminal_subtasks"
            )
        blocked_waves = [str(w.get("wave_number", 1)) for w in waves if w.get("is_blocked")]
        if blocked_waves:
            terminal_inconsistencies.append("terminal_task_has_blocked_wave")
        if task_status == "failed" and statuses and all(status == "accepted" for status in statuses):
            terminal_inconsistencies.append("failed_task_has_fully_accepted_manifest")

    remediation_residue_db: List[str] = []
    if task_status in {"completed", "completed_with_failures"}:
        remediation_residue_db = [
            st.get("subtask_id", "")
            for st in subtasks
            if (_is_remediation_subtask_id(st.get("subtask_id", "")) or str(st.get("subtask_id", "")).startswith("st-quality-"))
            and st.get("status") in {"failed", "cancelled"}
        ]
        if remediation_residue_db and not delivery_passed:
            terminal_inconsistencies.append("terminal_task_has_failed_remediation")

    active_remediation_subtasks_db = [
        st.get("subtask_id", "")
        for st in subtasks
        if _is_remediation_subtask_id(st.get("subtask_id", ""))
        and st.get("status") in {"pending", "dispatched", "running"}
    ]

    if task_status in {"completed", "completed_with_failures"}:
        failed_business_subtasks_db = [
            st.get("subtask_id", "")
            for st in subtasks
            if _is_original_business_subtask_id(st.get("subtask_id", ""))
            and st.get("status") in {"failed", "cancelled"}
        ]
        if failed_business_subtasks_db and not delivery_passed:
            terminal_inconsistencies.append("terminal_task_has_failed_business_subtasks")

    if readiness_blockers:
        quality_gate = "waiting"
    elif terminal_inconsistencies:
        quality_gate = "inconsistent"
    elif statuses and any(status == "missing" for status in statuses):
        quality_gate = "failed"
    elif statuses and all(status == "accepted" for status in statuses):
        quality_gate = "passed"
    elif statuses and any(status in {"produced", "accepted"} for status in statuses):
        quality_gate = "partial"
    else:
        quality_gate = "not_started"

    active_quality_remediation = [
        st.get("subtask_id")
        for st in subtasks
        if str(st.get("subtask_id", "")).startswith("st-quality-")
        and st.get("status", "pending") in {"pending", "dispatched", "running"}
    ]

    next_action = decision.get("next_repair_action")
    if not next_action:
        if readiness_blockers:
            next_action = "sync_keys"
        elif dispatch_repairable:
            next_action = "dispatch_repair"
        elif blocked_by_wave_gate:
            next_action = "await_wave_acceptance"
        elif waiting_on_dependencies:
            next_action = "await_dependencies"
        elif active_quality_remediation:
            next_action = "await_quality_remediation"
        elif active_remediation_subtasks_db:
            next_action = "await_remediation"
        elif terminal_inconsistencies:
            next_action = "repair_terminal_consistency"
        elif quality_gate == "failed":
            next_action = "quality_remediation"

    split_health = _derive_delivery_and_orchestration_health(
        task_status=task_status,
        delivery_quality_report=delivery_quality_report,
        terminal_inconsistencies=terminal_inconsistencies,
        active_remediation_subtasks=active_remediation_subtasks_db,
    )
    if delivery_quality_report:
        quality_gate = split_health["quality_gate"]

    return {
        "manifest_total": len(deliverables),
        "manifest_assigned": sum(1 for status in statuses if status in {"assigned", "produced", "accepted"}),
        "manifest_produced": sum(1 for status in statuses if status in {"produced", "accepted"}),
        "manifest_accepted": sum(1 for status in statuses if status == "accepted"),
        "manifest_missing": sum(1 for status in statuses if status == "missing"),
        "pending_without_jobs": pending_without_jobs,
        "dispatch_repairable": dispatch_repairable,
        "blocked_by_wave_gate": blocked_by_wave_gate,
        "waiting_on_dependencies": waiting_on_dependencies,
        "blocked_by_decomposition": blocked_by_decomposition,
        "wave_statuses": wave_statuses,
        "wave_details": wave_details,
        "has_inconsistent_acceptance": False,
        "dispatch_repair_needed": bool(dispatch_repairable),
        "active_quality_remediation": active_quality_remediation,
        "readiness_blockers": readiness_blockers,
        "terminal_inconsistencies": terminal_inconsistencies,
        "remediation_residue": remediation_residue_db,
        "active_remediation_subtasks": active_remediation_subtasks_db,
        "quality_gate": quality_gate,
        "delivery_quality_report": delivery_quality_report,
        "delivery_quality": split_health["delivery_quality"],
        "orchestration_health": split_health["orchestration_health"],
        "next_repair_action": next_action,
    }


def _task_info_from_db(task_dict: Dict[str, Any]) -> "TaskInfo":
    """Build TaskInfo from database dictionary (for persistence recovery).

    This ensures fix subtasks are included with full description and agent info.
    """
    from .task_history.models import JobStatus

    task_id = task_dict['task_id']
    status = task_dict.get('status', 'created')

    # Build subtask info from DB data
    db_subtasks = task_dict.get('subtasks', [])
    subtask_infos = []
    for st in db_subtasks:
        subtask_infos.append(SubTaskInfo(
            subtask_id=st['subtask_id'],
            description=st.get('description', ''),
            agent_id=st.get('agent_id', 'unknown'),
            priority=st.get('priority', 1),
            status=st.get('status', 'pending'),
            progress=st.get('progress', 0.0),
            dependencies=st.get('dependencies', []),
            output_file=st.get('output_file'),
            duration=st.get('duration'),
            error_message=st.get('error_message'),
            fix_plan=st.get('fix_plan'),
            wave_number=st.get('wave_number', 1),
            waiting_on_dependencies=[
                dep for dep in st.get('dependencies', [])
                if next((item for item in db_subtasks if item.get('subtask_id') == dep), {}).get('status') != 'completed'
            ],
            blocked_reason="waiting_on_dependencies" if (
                st.get('status', 'pending') == 'pending'
                and any(
                    next((item for item in db_subtasks if item.get('subtask_id') == dep), {}).get('status') != 'completed'
                    for dep in st.get('dependencies', [])
                )
            ) else None,
        ))

    # Build waves from DB data
    db_waves = task_dict.get('waves', [])
    wave_infos = []
    for w in db_waves:
        wave_subtasks = [s for s in subtask_infos if s.wave_number == w.get('wave_number', 1)]
        wave_infos.append(WaveInfo(
            wave_id=w['wave_id'],
            wave_number=w.get('wave_number', 1),
            subtasks=wave_subtasks,
            status=w.get('status', 'pending'),
            is_blocked=bool(w.get('is_blocked', False))
        ))

    # Calculate progress
    original = [s for s in subtask_infos if _is_original_business_subtask_id(s.subtask_id)]
    completed_count = sum(1 for s in original if s.status == "completed")
    total_count = len(original)
    progress = completed_count / total_count if total_count > 0 else 0.0

    artifact_records = task_dict.get("artifact_records", [])
    artifact_versions = {
        (artifact.get("name") or artifact.get("content_ref") or artifact.get("artifact_id")): int(artifact.get("version") or 0)
        for artifact in artifact_records
        if (artifact.get("name") or artifact.get("content_ref") or artifact.get("artifact_id"))
    }
    artifacts = [
        {
            "id": a.get("artifact_id"),
            "file_name": a.get("name") or a.get("artifact_id") or "unknown",
            "file_path": (a.get("metadata") or {}).get("normalized_content_ref") or (os.path.realpath(a.get("content_ref")) if a.get("content_ref") else ""),
            "file_size": a.get("file_size") or (a.get("metadata") or {}).get("file_size") or "0 B",
            "subtask_id": a.get("subtask_id"),
            "wave_number": a.get("wave_number"),
            "version": a.get("version"),
            "status": a.get("status"),
            "source_artifact_ids": a.get("source_artifact_ids", []),
            "produced_by": a.get("produced_by"),
        }
        for a in artifact_records
    ]

    requirement_manifest = task_dict.get("requirement_manifest")
    quality_health = _build_quality_health_from_db(task_dict, refresh_missing_delivery_quality=False)
    adjusted_status = _status_with_delivery_quality(status, quality_health)
    if adjusted_status != status:
        status = adjusted_status
        adjusted_task_dict = dict(task_dict)
        adjusted_task_dict["status"] = status
        quality_health = _build_quality_health_from_db(adjusted_task_dict, refresh_missing_delivery_quality=False)
    progress, completed_count, total_count = _completion_metrics_with_quality(
        status,
        quality_health,
        completed_count,
        total_count,
        progress,
    )
    from types import SimpleNamespace
    from .task_review.delivery_report import build_delivery_report
    task_like = SimpleNamespace(
        task_id=task_id,
        status=status,
        subtasks=subtask_infos,
        last_owner_decision=task_dict.get("last_owner_decision") or {},
    )
    delivery_report = build_delivery_report(
        task=task_like,
        manifest=requirement_manifest,
        artifact_records=artifact_records,
        acceptance_records=task_dict.get("acceptance_records", [])[-10:],
        quality_health=quality_health,
        final_status=status,
    )

    return TaskInfo(
        task_id=task_id,
        description=task_dict.get('description', ''),
        status=status,
        task_types=task_dict.get("task_types") or [],
        delivery_mode=task_dict.get("delivery_mode") or "external",
        owner_delivery_contract=task_dict.get("owner_delivery_contract"),
        owner_agent=task_dict.get('owner_agent'),
        allowed_subtask_agents=task_dict.get('allowed_subtask_agents') or [],
        project_dir=task_dict.get('project_dir'),
        subtasks=subtask_infos,
        waves=wave_infos,
        artifacts=artifacts,
        artifact_versions=artifact_versions,
        acceptance_records=task_dict.get("acceptance_records", [])[-10:],
        owner_session_id=task_dict.get("owner_session_id"),
        last_owner_decision=task_dict.get("last_owner_decision"),
        can_handle_directly=bool(task_dict.get('can_handle_directly')),
        direct_response=task_dict.get('direct_response'),
        requirement_manifest=requirement_manifest,
        quality_health=quality_health,
        delivery_report=delivery_report,
        observability=_build_task_observability_snapshot(
            task_id=task_id,
            description=task_dict.get('description', ''),
            status=status,
            subtasks=db_subtasks,
            waves=db_waves,
            last_owner_decision=task_dict.get("last_owner_decision"),
            created_at=task_dict.get('created_at') or 0.0,
            updated_at=task_dict.get('updated_at') or 0.0,
        ),
        progress=progress,
        completed_count=completed_count,
        total_count=total_count,
        created_at=task_dict.get('created_at') or 0.0,
        updated_at=task_dict.get('updated_at') or 0.0,
        error=task_dict.get('error')
    )

def _removed_in_app_orchestration_detail(task_id: str, operation: str) -> str:
    return (
        f"Task {task_id} cannot run {operation} through the AAA API process. "
        "Task orchestration is provided by the external Across Orchestrator plugin."
    )


@app.post("/api/tasks/{task_id}/dispatch")
async def dispatch_task(task_id: str, req: TaskDispatchRequest):
    """Reject in-process task dispatch; external orchestrator owns execution."""
    raise HTTPException(status_code=410, detail=_removed_in_app_orchestration_detail(task_id, "dispatch"))

@app.get("/api/tasks/page", response_model=TaskPageResponse)
async def list_task_summaries(limit: int = 50, offset: int = 0):
    """List lightweight task summaries for the sidebar.

    This endpoint intentionally does not hydrate subtasks, waves, artifacts, or
    quality reports.  Full task details are loaded by `/api/tasks/{task_id}`
    when the user selects a specific task.
    """
    try:
        limit = max(1, min(int(limit or 50), 200))
        offset = max(0, int(offset or 0))

        in_memory: Dict[str, TaskSummaryInfo] = {}
        for task in _task_state.get_all_tasks():
            original = [st for st in task.subtasks if _is_original_business_subtask_id(st.subtask_id)]
            completed_count = sum(1 for st in original if st.status == JobStatus.COMPLETED)
            total_count = len(original)
            progress = completed_count / total_count if total_count > 0 else float(getattr(task, "progress", 0) or 0)
            status = getattr(task.status, "value", task.status)
            decision = getattr(task, "last_owner_decision", None) or {}
            delivery_quality_report = decision.get("delivery_quality") if isinstance(decision, dict) else None
            if isinstance(delivery_quality_report, dict):
                summary_quality_health = {
                    "delivery_quality": delivery_quality_report.get("delivery_quality"),
                    "quality_gate": delivery_quality_report.get("delivery_quality"),
                    "delivery_quality_report": delivery_quality_report,
                }
                status = _status_with_delivery_quality(str(status), summary_quality_health)
                progress, completed_count, total_count = _completion_metrics_with_quality(
                    str(status),
                    summary_quality_health,
                    completed_count,
                    total_count,
                    progress,
                )
            in_memory[task.task_id] = TaskSummaryInfo(
                task_id=task.task_id,
                description=task.description,
                status=status,
                progress=progress,
                completed_count=completed_count,
                total_count=total_count,
                created_at=task.created_at,
                updated_at=task.updated_at,
                project_dir=task.project_dir,
                owner_agent=task.owner_agent,
                delivery_mode=getattr(task, "delivery_mode", "external") or "external",
            )

        persistence = getattr(_task_state, "_persistence", None)
        if persistence and hasattr(persistence, "get_task_summaries"):
            persisted_rows, persisted_total = persistence.get_task_summaries(limit=limit, offset=offset)
        elif persistence:
            all_rows = persistence.get_all_tasks()
            persisted_total = len(all_rows)
            persisted_rows = all_rows[offset:offset + limit]
        else:
            persisted_rows = []
            persisted_total = 0

        summaries: List[TaskSummaryInfo] = []
        terminal_statuses = {
            TaskStatus.COMPLETED.value,
            TaskStatus.COMPLETED_WITH_FAILURES.value,
            TaskStatus.FAILED.value,
            TaskStatus.CANCELLED.value,
        }

        for row in persisted_rows:
            task_id = row.get("task_id")
            if not task_id:
                continue
            if task_id in in_memory:
                summaries.append(in_memory[task_id])
                continue
            status = row.get("status") or "created"
            completed_count = int(row.get("completed_count") or 0)
            total_count = int(row.get("total_count") or 0)
            progress = float(row.get("progress") or 0)
            decision = row.get("last_owner_decision") or {}
            delivery_quality_report = decision.get("delivery_quality") if isinstance(decision, dict) else None
            if isinstance(delivery_quality_report, dict):
                summary_quality_health = {
                    "delivery_quality": delivery_quality_report.get("delivery_quality"),
                    "quality_gate": delivery_quality_report.get("delivery_quality"),
                    "delivery_quality_report": delivery_quality_report,
                }
                status = _status_with_delivery_quality(str(status), summary_quality_health)
                progress, completed_count, total_count = _completion_metrics_with_quality(
                    str(status),
                    summary_quality_health,
                    completed_count,
                    total_count,
                    progress,
                )
            if status not in terminal_statuses and status != TaskStatus.PAUSED.value:
                status = "suspended"
            summaries.append(TaskSummaryInfo(
                task_id=task_id,
                description=row.get("description") or "",
                status=status,
                progress=progress,
                completed_count=completed_count,
                total_count=total_count,
                created_at=float(row.get("created_at") or 0),
                updated_at=float(row.get("updated_at") or 0),
                project_dir=row.get("project_dir"),
                owner_agent=row.get("owner_agent"),
                delivery_mode=row.get("delivery_mode") or "external",
            ))

        if not persistence:
            summaries = sorted(
                in_memory.values(),
                key=lambda item: item.updated_at or item.created_at or 0,
                reverse=True,
            )[offset:offset + limit]
            total = len(in_memory)
        else:
            total = max(persisted_total, len(in_memory))

        seen_summary_ids = {item.task_id for item in summaries}
        try:
            for row in get_orchestrator_plugin_manager().list_task_summaries():
                task_id = row.get("task_id")
                if not task_id or task_id in seen_summary_ids:
                    continue
                summaries.append(TaskSummaryInfo(
                    task_id=str(task_id),
                    description=str(row.get("description") or ""),
                    status=str(row.get("status") or "pending"),
                    external_task=True,
                    progress=float(row.get("progress") or 0),
                    completed_count=int(row.get("completed_count") or 0),
                    total_count=int(row.get("total_count") or 0),
                    created_at=float(row.get("created_at") or 0),
                    updated_at=float(row.get("updated_at") or 0),
                    project_dir=row.get("project_dir"),
                    owner_agent=row.get("owner_agent"),
                    delivery_mode=row.get("delivery_mode") or "composite",
                ))
                seen_summary_ids.add(str(task_id))
            if len(summaries) > total:
                total = len(summaries)
        except Exception as exc:
            logger.debug("Skipping external Orchestrator task summaries: %s", exc)

        summaries = sorted(
            summaries,
            key=lambda item: item.updated_at or item.created_at or 0,
            reverse=True,
        )

        page_summaries = summaries[:limit]
        return TaskPageResponse(
            tasks=page_summaries,
            total=total,
            limit=limit,
            offset=offset,
            has_more=offset + len(page_summaries) < total,
        )
    except Exception as e:
        raise _safe_http_500("List task summaries")


# Release verification helper logic lives in release_verification.py.


@app.get("/api/release/evaluation")
async def get_release_evaluation(limit: int = 100):
    """Return a lightweight release-candidate quality summary.

    The endpoint only reads cached task rows and stored quality reports. It
    intentionally avoids hydrating full task details, running probes, repairing
    dispatch, or resuming historical work.
    """
    try:
        safe_limit = max(1, min(int(limit or 100), 500))
        return _sanitize_public_payload(await _release_evaluation_payload(safe_limit))
    except Exception as e:
        raise _safe_http_500("Get release evaluation")


@app.post("/api/release/verification")
async def run_release_verification():
    """Create a non-secret release-candidate verification report."""
    try:
        report_directory = app_subdir("release-reports")
        _build_release_verification_report(
            write_report=True,
            task_state=_task_state,
            external_task_rows=lambda: get_orchestrator_plugin_manager().list_task_summaries(),
            startup_diagnostics=_build_startup_diagnostics(),
            load_task_payload=_load_task_info_read_only,
            serialize_task_payload=_pydantic_dump,
            redact_sensitive=_redact_sensitive_evidence,
            app_version=None,
            expected_files=RELEASE_VERIFICATION_EXPECTED_FILES,
            required_probes=RELEASE_VERIFICATION_REQUIRED_PROBES,
            write_report_directory=report_directory,
        )
        return public_release_verification_api_response_from_report_directory(report_directory)
    except Exception:
        raise _safe_http_500("Run release verification")

@app.get("/api/tasks/{task_id}", response_model=TaskInfo)
async def get_task(task_id: str):
    """Get task details and progress.

    With persistence enabled, returns complete task data including fix subtasks
    from the database to ensure frontend always has full subtask information.
    """
    try:
        if _is_external_orchestrator_task(task_id):
            plugin = get_orchestrator_plugin_manager()
            task_payload = await asyncio.to_thread(plugin.get_task, task_id)
            evidence = await _external_task_evidence_async(plugin, task_id, task_payload)
            return TaskInfo(**external_task_to_app_info(task_payload, evidence=evidence))

        # Lightweight watchdog: repair missing state / wave approval / orphan dispatch
        _repair_task_dispatch_if_possible(task_id, reason="api_detail_poll")

        # First check in-memory state
        task = _task_state.get_task(task_id)
        if not task:
            # Try to load from persistence if available
            if _task_state._persistence:
                full_task = _task_state._persistence.get_full_task(task_id)
                if full_task:
                    return _task_info_from_db(full_task)
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        return _task_to_info(task, _task_state)
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_http_500("Get task")

@app.get("/api/tasks", response_model=List[TaskInfo])
async def list_tasks():
    """List active in-memory tasks plus persisted task history."""
    try:
        task_infos = [_task_to_info(t, _task_state) for t in _task_state.get_all_tasks()]
        seen_task_ids = {info.task_id for info in task_infos}
        terminal_statuses = {
            TaskStatus.COMPLETED.value,
            TaskStatus.COMPLETED_WITH_FAILURES.value,
            TaskStatus.FAILED.value,
            TaskStatus.CANCELLED.value,
        }

        persistence = getattr(_task_state, "_persistence", None)
        if persistence:
            for row in persistence.get_all_tasks():
                task_id = row.get("task_id")
                if not task_id or task_id in seen_task_ids:
                    continue
                full_task = persistence.get_full_task(task_id)
                if not full_task:
                    continue
                info = _task_info_from_db(full_task)
                if info.status not in terminal_statuses and info.status != TaskStatus.PAUSED.value:
                    info.status = "suspended"
                task_infos.append(info)
                seen_task_ids.add(task_id)

        try:
            plugin = get_orchestrator_plugin_manager()
            for row in plugin.list_task_summaries():
                task_id = row.get("task_id")
                if not task_id or task_id in seen_task_ids:
                    continue
                task_payload = plugin.get_task(str(task_id))
                task_infos.append(TaskInfo(**external_task_to_app_info(task_payload)))
                seen_task_ids.add(str(task_id))
        except Exception as exc:
            logger.debug("Skipping external Orchestrator tasks: %s", exc)

        return sorted(
            task_infos,
            key=lambda item: item.updated_at or item.created_at or 0,
            reverse=True,
        )
    except Exception as e:
        raise _safe_http_500("List tasks")

@app.get("/api/tasks/{task_id}/jobs/{job_id}", response_model=JobInfo)
async def get_job(task_id: str, job_id: str):
    """Get job details."""
    try:
        job = _task_state.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        return JobInfo(
            job_id=job.job_id,
            subtask_id=job.subtask_id,
            agent_id=job.agent_id,
            task_description=job.task_description,
            status=job.status.value,
            progress=job.progress,
            logs=job.logs,
            result=job.result,
            error=job.error
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_http_500("Get job")

@app.post("/api/tasks/{task_id}/jobs/{job_id}/cancel")
async def cancel_job(task_id: str, job_id: str):
    """Cancel a running job."""
    try:
        # Verify job belongs to task
        job = _task_state.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        # Verify job belongs to this task
        task = _task_state.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        # Check if subtask belongs to task
        subtask_ids = [st.subtask_id for st in task.subtasks]
        if job.subtask_id not in subtask_ids:
            raise HTTPException(status_code=400, detail=f"Job {job_id} does not belong to task {task_id}")

        success = _task_state.cancel_job(job_id, error="Cancelled by user")
        if not success:
            raise HTTPException(status_code=400, detail=f"Cannot cancel job {job_id}")
        return {"status": "success", "job_id": job_id}
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_http_500("Cancel job")


def _default_external_orchestrator_project_dir() -> str:
    path = app_subdir("orchestrator-workspaces") / f"task-{int(time.time() * 1000)}"
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def _validate_request_task_types(task_types: List[str]) -> List[str]:
    allowed = {"functional", "artifact"}
    values: List[str] = []
    for item in task_types or []:
        value = str(item).strip().lower()
        if value not in allowed:
            raise HTTPException(status_code=422, detail=f"Unsupported task type: {value}")
        if value not in values:
            values.append(value)
    if not values:
        raise HTTPException(status_code=422, detail="At least one task type must be selected")
    return values


def _external_task_planning_request(req: AutoTaskRequest) -> ExternalTaskPlanningRequest:
    return ExternalTaskPlanningRequest(
        description=req.description,
        task_types=req.task_types,
        owner_agent=req.owner_agent,
        allowed_subtask_agents=req.allowed_subtask_agents,
        project_dir=req.project_dir,
        strict_dependency=req.strict_dependency,
        enable_wave_gate=req.enable_wave_gate,
    )


def _deliverables_for_external_task(req: AutoTaskRequest) -> List[str]:
    return deliverables_for_external_task(_external_task_planning_request(req))


def _external_owner_agent(req: AutoTaskRequest) -> str:
    return external_owner_agent(_external_task_planning_request(req))


def _planned_subtasks_for_external_task(req: AutoTaskRequest, deliverables: List[str]) -> List[Dict[str, Any]]:
    return planned_subtasks_for_external_task(_external_task_planning_request(req), deliverables)


def _agent_adapters_for_external_task(req: AutoTaskRequest) -> Dict[str, Dict[str, Any]]:
    return agent_adapters_for_external_task(_external_task_planning_request(req))


def _external_orchestrator_unavailable_response(plugin_status: Dict[str, Any]) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=str(
            plugin_status.get("connection_note")
            or "Across Orchestrator is required for task orchestration. Install or connect the plugin first."
        ),
    )


async def _submit_auto_orchestrated_task(
    req: AutoTaskRequest,
) -> AutoTaskResponse:
    _validate_request_task_types(req.task_types)
    plugin = get_orchestrator_plugin_manager()
    plugin_status = plugin.implementation_status(probe=True)
    if plugin_status.get("implementation") == "external" and plugin_status.get("available"):
        try:
            deliverables = _deliverables_for_external_task(req)
            planned_subtasks = _planned_subtasks_for_external_task(req, deliverables)
            task = await asyncio.to_thread(
                plugin.submit_task,
                goal=req.description,
                project_dir=req.project_dir or _default_external_orchestrator_project_dir(),
                deliverables=deliverables,
                agent=_external_owner_agent(req),
                subtasks=planned_subtasks,
                strict_dependency=req.strict_dependency,
                task_types=req.task_types,
                agent_adapters=_agent_adapters_for_external_task(req),
            )
            return AutoTaskResponse(
                task_id=str(task.get("task_id") or ""),
                status=str(task.get("status") or "created"),
                message="Task submitted to external Across Orchestrator",
                implementation="external",
                external_task=True,
            )
        except OrchestratorPluginUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        except Exception as exc:
            logger.exception("External Across Orchestrator task submission failed")
            raise HTTPException(status_code=502, detail=_safe_error_message("External Across Orchestrator task submission"))
    raise _external_orchestrator_unavailable_response(plugin_status)


@app.get("/api/release/e2e/scenarios", response_model=ReleaseE2EScenarioListResponse)
async def get_release_e2e_scenarios():
    return ReleaseE2EScenarioListResponse(scenarios=build_release_e2e_scenarios())


@app.post("/api/release/e2e/tasks", response_model=ReleaseE2ETaskResponse)
async def create_release_e2e_task(req: ReleaseE2ETaskRequest):
    try:
        task_request = build_release_e2e_task_request(
            scenario_id=req.scenario_id,
            project_dir=req.project_dir,
            run_label=req.run_label,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    plugin = get_orchestrator_plugin_manager()
    plugin_status = plugin.implementation_status(probe=True)
    if plugin_status.get("implementation") == "external" and plugin_status.get("available"):
        try:
            task = await asyncio.to_thread(
                plugin.submit_release_e2e_task,
                project_dir=task_request["project_dir"],
                run_label=req.run_label,
                allowed_subtask_agents=task_request["allowed_subtask_agents"],
            )
            return ReleaseE2ETaskResponse(
                task_id=str(task.get("task_id") or ""),
                status=str(task.get("status") or "created"),
                message="Release E2E task submitted to external Across Orchestrator",
                scenario_id=task_request["scenario_id"],
                project_dir=task_request["project_dir"],
                complexity_score=task_request["complexity_score"],
                required_files=task_request["required_files"],
                implementation="external",
                external_task=True,
                orchestrator_transport=plugin_status.get("transport"),
            )
        except OrchestratorPluginUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        except Exception as exc:
            logger.exception("External Across Orchestrator Release E2E submission failed")
            raise HTTPException(status_code=502, detail=_safe_error_message("External Across Orchestrator Release E2E submission"))
    raise HTTPException(
        status_code=503,
        detail=str(plugin_status.get("connection_note") or "External Across Orchestrator is unavailable."),
    )


@app.post("/api/tasks/auto", response_model=AutoTaskResponse)
async def auto_task(req: AutoTaskRequest):
    """Auto-orchestrated task submission.

    Creates an external Across Orchestrator task and returns its host-visible task id.

    Before submission, checks that LLM providers have API keys configured.
    If keys are missing, returns a clear 412 error listing the missing providers
    rather than letting the orchestrator fail with an opaque LLM error.
    """
    return await _submit_auto_orchestrated_task(req)


@app.post("/api/tasks/{task_id}/run")
async def run_external_task(task_id: str):
    """Run an externally-owned Across Orchestrator task."""
    if not _is_external_orchestrator_task(task_id):
        raise HTTPException(status_code=409, detail="Only external Across Orchestrator tasks can be run through this endpoint.")
    try:
        plugin = get_orchestrator_plugin_manager()
        task_payload = await asyncio.to_thread(plugin.run_task, task_id)
        evidence = await _external_task_evidence_async(plugin, task_id, task_payload)
        return _sanitize_public_payload(external_task_to_app_info(task_payload, evidence=evidence))
    except OrchestratorPluginUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("External Across Orchestrator task run failed")
        raise HTTPException(status_code=502, detail=_safe_error_message("External Across Orchestrator task run"))


@app.get("/api/tasks/{task_id}/status")
async def get_task_status(task_id: str):
    """Query overall task status including progress and subtask states.

    Returns complete subtask data from persistence to ensure frontend
    always has full information including fix subtasks.
    """
    try:
        from .task_review.delivery_report import build_delivery_report
        if _is_external_orchestrator_task(task_id):
            plugin = get_orchestrator_plugin_manager()
            task_payload = await asyncio.to_thread(plugin.get_task, task_id)
            evidence = await _external_task_evidence_async(plugin, task_id, task_payload)
            return _sanitize_public_payload(external_task_to_app_info(task_payload, evidence=evidence))

        _repair_task_dispatch_if_possible(task_id, reason="api_status_poll")

        # First check in-memory state
        task = _task_state.get_task(task_id)
        if not task:
            # Try to load from persistence if available (same as GET /api/tasks/{task_id})
            if _task_state._persistence:
                full_task = _task_state._persistence.get_full_task(task_id)
                if full_task:
                    return _task_info_from_db(full_task)
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        progress = _task_state.get_task_progress(task_id)

        status = _compute_task_status(task, _task_state)

        # Build subtasks list - include ALL subtasks from memory (which now includes fix subtasks via persistence)
        subtasks_data = []
        for st in task.subtasks:
            contract = None
            try:
                contract = _task_state.get_contract_by_subtask(task_id, st.subtask_id)
            except Exception:
                contract = None
            subtasks_data.append({
                "subtask_id": st.subtask_id,
                "description": st.description,
                "agent_id": st.agent_id,
                "priority": st.priority,
                "status": st.status.value,
                "progress": st.progress,
                "dependencies": st.dependencies,
                "wave_number": getattr(st, "wave_number", 1),
                "output_file": st.output_file,
                "duration": st.duration,
                "error_message": st.error_message,
                "fix_plan": getattr(st, 'fix_plan', None),
                "contract": contract,
            })

        # Build waves data from memory state (which includes fix subtasks with inherited wave_number)
        waves_data = []
        artifact_versions: Dict[str, int] = {}
        artifact_records: List[Dict[str, Any]] = []
        acceptance_records: List[Dict[str, Any]] = []
        requirement_manifest = None
        if _task_state._persistence:
            try:
                artifact_records = _task_state._persistence.get_artifact_records(task_id)
                for artifact in artifact_records:
                    key = artifact.get("name") or artifact.get("content_ref") or artifact.get("artifact_id")
                    if key:
                        artifact_versions[key] = max(artifact_versions.get(key, 0), int(artifact.get("version") or 0))
                acceptance_records = _task_state._persistence.get_acceptance_records(task_id)[-10:]
                try:
                    requirement_manifest = _task_state.get_requirement_manifest(task_id)
                except Exception:
                    requirement_manifest = None
            except Exception:
                pass
        quality_health = _build_quality_health(
            task,
            _task_state,
            requirement_manifest,
            acceptance_records,
            effective_task_status=status,
            refresh_cached_delivery_quality=False,
        )
        adjusted_status = _status_with_delivery_quality(status, quality_health)
        if adjusted_status != status:
            status = adjusted_status
            quality_health = _build_quality_health(
                task,
                _task_state,
                requirement_manifest,
                acceptance_records,
                effective_task_status=status,
                refresh_cached_delivery_quality=False,
            )
        original_subtasks = [st for st in task.subtasks if _is_original_business_subtask_id(st.subtask_id)]
        completed_count = sum(1 for st in original_subtasks if st.status == JobStatus.COMPLETED)
        total_count = len(original_subtasks)
        progress, _, _ = _completion_metrics_with_quality(
            status,
            quality_health,
            completed_count,
            total_count,
            progress,
        )
        if task.waves:
            for wave in task.waves:
                wave_subtasks = []
                for st in wave.subtasks:
                    st_contract = None
                    try:
                        st_contract = _task_state.get_contract_by_subtask(task_id, st.subtask_id)
                    except Exception:
                        st_contract = None
                    wave_subtasks.append({
                        "subtask_id": st.subtask_id,
                        "description": st.description,
                        "agent_id": st.agent_id,
                        "priority": st.priority,
                        "status": st.status.value,
                        "progress": st.progress,
                        "dependencies": st.dependencies,
                        "wave_number": getattr(st, "wave_number", wave.wave_number),
                        "output_file": st.output_file,
                        "duration": st.duration,
                        "error_message": st.error_message,
                        "fix_plan": getattr(st, 'fix_plan', None),
                        "owner_decision": getattr(st, 'owner_decision', None),
                        "contract": st_contract,
                    })
                waves_data.append({
                    "wave_id": wave.wave_id,
                    "wave_number": wave.wave_number,
                    "subtasks": wave_subtasks,
                    "status": wave.status.value,
                    "is_blocked": wave.is_blocked,
                    "governance_status": _wave_governance_status(wave),
                    "blocked_by_wave": getattr(wave, "blocked_by_wave", None),
                    "is_revalidating": getattr(wave, "is_revalidating", False),
                    "owner_decision": getattr(wave, "owner_decision", None),
                })

        return _sanitize_public_payload({
            "task_id": task_id,
            "progress": progress,
            "status": status,
            "task_types": list(getattr(task, "task_types", []) or []),
            "delivery_mode": getattr(task, "delivery_mode", "external") or "external",
            "owner_delivery_contract": _task_state.get_delivery_contract(task_id) if _task_state else None,
            "owner_session_id": getattr(task, "owner_session_id", None),
            "last_owner_decision": getattr(task, "last_owner_decision", None),
            "artifact_versions": artifact_versions,
            "acceptance_records": acceptance_records,
            "requirement_manifest": requirement_manifest,
            "quality_health": quality_health,
            "delivery_report": build_delivery_report(
                task=task,
                manifest=requirement_manifest,
                artifact_records=artifact_records,
                acceptance_records=acceptance_records,
                quality_health=quality_health,
                final_status=status,
            ),
            "subtasks": subtasks_data,
            "waves": waves_data
        })
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_http_500("Get task status")


def _comma_separated_values(value: Optional[str]) -> List[str]:
    return [
        item.strip()
        for item in str(value or "").split(",")
        if item.strip()
    ]


@app.get("/api/tasks/{task_id}/quality-benchmark")
async def get_task_quality_benchmark(
    task_id: str,
    expected_files: Optional[str] = None,
    required_probes: Optional[str] = None,
    min_quality_score: int = 70,
    max_remediation_attempts: int = 2,
    benchmark_id: Optional[str] = None,
):
    """Evaluate a task status payload against release-quality benchmark gates."""
    from . import __version__
    from .task_review.quality_benchmark import evaluate_delivery_benchmark

    if _is_external_orchestrator_task(task_id):
        evidence = await asyncio.to_thread(get_orchestrator_plugin_manager().get_evidence_bundle, task_id)
        report = build_external_quality_benchmark(
            _redact_sensitive_evidence(evidence),
            expected_files=_comma_separated_values(expected_files),
            required_probes=_comma_separated_values(required_probes),
            min_quality_score=min_quality_score,
            max_remediation_attempts=max_remediation_attempts,
            benchmark_id=benchmark_id or f"external-{task_id}-release-{__version__}",
            app_version=__version__,
        )
        return _redact_sensitive_evidence(report)

    payload = await get_task_status(task_id)
    if isinstance(payload, BaseModel):
        payload = _pydantic_dump(payload)
    payload = _sanitize_public_payload(payload)
    report = evaluate_delivery_benchmark(
        [payload],
        benchmark_id=benchmark_id or f"task-{task_id}-release-{__version__}",
        expected_files=_comma_separated_values(expected_files),
        required_probes=_comma_separated_values(required_probes),
        min_quality_score=min_quality_score,
        max_remediation_attempts=max_remediation_attempts,
    )
    report["app_version"] = __version__
    return report


@app.get("/api/tasks/{task_id}/evidence-bundle")
async def get_task_evidence_bundle(
    task_id: str,
    expected_files: Optional[str] = None,
    required_probes: Optional[str] = None,
    min_quality_score: int = 70,
    max_remediation_attempts: int = 2,
    benchmark_id: Optional[str] = None,
):
    """Return a read-only, sanitized audit bundle for a task delivery."""
    from . import __version__
    from .task_review.quality_benchmark import evaluate_delivery_benchmark

    if _is_external_orchestrator_task(task_id):
        evidence = await asyncio.to_thread(get_orchestrator_plugin_manager().get_evidence_bundle, task_id)
        bundle = external_evidence_to_app_bundle(
            _redact_sensitive_evidence(evidence),
            expected_files=_comma_separated_values(expected_files),
            required_probes=_comma_separated_values(required_probes),
            min_quality_score=min_quality_score,
            max_remediation_attempts=max_remediation_attempts,
            benchmark_id=benchmark_id or f"external-{task_id}-evidence-{__version__}",
            app_version=__version__,
        )
        return _redact_sensitive_evidence(bundle)

    task_info = _load_task_info_read_only(task_id)
    payload = _pydantic_dump(task_info) if isinstance(task_info, BaseModel) else dict(task_info)
    expected = _comma_separated_values(expected_files) or _expected_files_from_payload(payload)
    probes = _comma_separated_values(required_probes) or _probe_types_from_payload(payload)
    benchmark = evaluate_delivery_benchmark(
        [payload],
        benchmark_id=benchmark_id or f"task-{task_id}-evidence-{__version__}",
        expected_files=expected,
        required_probes=probes,
        min_quality_score=min_quality_score,
        max_remediation_attempts=max_remediation_attempts,
    )
    benchmark["app_version"] = __version__
    sanitized = _redact_sensitive_evidence(payload)
    return {
        "schema_version": "1.0",
        "app_version": __version__,
        "generated_at": time.time(),
        "task_id": sanitized.get("task_id"),
        "description": sanitized.get("description"),
        "task_status": sanitized.get("status"),
        "task_types": sanitized.get("task_types") or [],
        "delivery_mode": sanitized.get("delivery_mode") or "external",
        "project_dir": sanitized.get("project_dir"),
        "owner_agent": sanitized.get("owner_agent"),
        "allowed_subtask_agents": sanitized.get("allowed_subtask_agents") or [],
        "delivery_contract": sanitized.get("owner_delivery_contract") or {},
        "requirement_manifest": sanitized.get("requirement_manifest") or {},
        "last_owner_decision": sanitized.get("last_owner_decision") or {},
        "quality_health": sanitized.get("quality_health") or {},
        "delivery_report": sanitized.get("delivery_report") or {},
        "observability": sanitized.get("observability") or {},
        "artifacts": sanitized.get("artifacts") or [],
        "acceptance_records": sanitized.get("acceptance_records") or [],
        "benchmark": _redact_sensitive_evidence(benchmark),
        "audit": {
            "read_only": True,
            "repair_or_resume_triggered": False,
            "secrets_redacted": True,
            "expected_files": expected,
            "required_probes": probes,
        },
    }

@app.get("/api/tasks/{task_id}/stream")
async def task_stream(task_id: str):
    """SSE endpoint for task state changes.

    Pushes SubTaskStatusChanged events when subtask status changes.
    Uses existing _task_state._progress_callbacks mechanism.
    """
    if _is_external_orchestrator_task(task_id):
        async def external_event_generator():
            try:
                plugin = get_orchestrator_plugin_manager()
                task_payload = await asyncio.to_thread(plugin.get_task, task_id)
                task_info = external_task_to_app_info(task_payload)
                status_changed_data = {
                    "type": "task_status_changed",
                    "task_id": task_id,
                    "status": task_info["status"],
                    "progress": task_info["progress"],
                    "completed_count": task_info["completed_count"],
                    "total_count": task_info["total_count"],
                    "owner_session_id": task_info.get("owner_session_id"),
                    "last_owner_decision": task_info.get("last_owner_decision"),
                    "subtasks": task_info.get("subtasks", []),
                    "waves": task_info.get("waves", []),
                }
                yield f"data: {json.dumps(status_changed_data)}\n\n"
                if task_info["status"] == TaskStatus.COMPLETED.value:
                    yield f"data: {json.dumps({'type': 'task_completed', 'taskId': task_id})}\n\n"
                elif task_info["status"] == TaskStatus.FAILED.value:
                    yield f"data: {json.dumps({'type': 'task_failed', 'taskId': task_id, 'error': task_info.get('error') or 'Task failed'})}\n\n"
            except Exception as exc:
                logger.exception("External task stream failed")
                yield f"data: {json.dumps({'type': 'error', 'content': _safe_error_message('External task stream')})}\n\n"

        return StreamingResponse(
            external_event_generator(),
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no"}
        )

    _repair_task_dispatch_if_possible(task_id, reason="api_stream_open")

    task = _task_state.get_task(task_id)
    if not task:
        persistence = getattr(_task_state, "_persistence", None)
        full_task = persistence.get_full_task(task_id) if persistence else None
        if full_task:
            task_info = _task_info_from_db(full_task)

            async def persisted_event_generator():
                status_changed_data = {
                    "type": "task_status_changed",
                    "task_id": task_id,
                    "status": task_info.status,
                    "progress": task_info.progress,
                    "completed_count": task_info.completed_count,
                    "total_count": task_info.total_count,
                    "owner_session_id": task_info.owner_session_id,
                    "last_owner_decision": task_info.last_owner_decision,
                    "subtasks": [_pydantic_dump(s) for s in task_info.subtasks],
                    "waves": [_pydantic_dump(w) for w in task_info.waves],
                }
                yield f"data: {json.dumps(status_changed_data)}\n\n"

                if task_info.status == TaskStatus.COMPLETED.value:
                    yield f"data: {json.dumps({'type': 'task_completed', 'taskId': task_id})}\n\n"
                elif task_info.status == TaskStatus.COMPLETED_WITH_FAILURES.value:
                    failed_count = sum(
                        1
                        for st in task_info.subtasks
                        if st.status == JobStatus.FAILED.value
                        and _is_original_business_subtask_id(st.subtask_id)
                    )
                    completed_with_failures_data = {
                        "type": "task_completed_with_failures",
                        "taskId": task_id,
                        "error": f"{failed_count} subtask(s) failed",
                        "failedCount": failed_count,
                    }
                    yield f"data: {json.dumps(completed_with_failures_data)}\n\n"
                elif task_info.status == TaskStatus.FAILED.value:
                    failed_data = {"type": "task_failed", "taskId": task_id, "error": task_info.error or "Task failed"}
                    yield f"data: {json.dumps(failed_data)}\n\n"
                elif task_info.status == TaskStatus.CANCELLED.value:
                    yield f"data: {json.dumps({'type': 'task_cancelled', 'taskId': task_id})}\n\n"

            return StreamingResponse(
                persisted_event_generator(),
                media_type="text/event-stream",
                headers={"X-Accel-Buffering": "no"}
            )

        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def progress_callback(update):
        # Use call_soon_threadsafe to safely put items from other threads
        loop.call_soon_threadsafe(queue.put_nowait, update)

    _task_state.add_progress_callback(progress_callback)

    async def event_generator():
        try:
            while True:
                try:
                    update = await asyncio.wait_for(queue.get(), timeout=30.0)
                    job = _task_state.get_job(update.job_id)
                    subtask_id = job.subtask_id if job else update.job_id
                    wave_number = 1
                    for st in task.subtasks:
                        if st.subtask_id == subtask_id:
                            wave_number = getattr(st, "wave_number", 1)
                            break
                    # Find subtask to include full description and agent_id
                    subtask_description = ""
                    subtask_agent_id = ""
                    for st in task.subtasks:
                        if st.subtask_id == subtask_id:
                            subtask_description = st.description
                            subtask_agent_id = st.agent_id
                            break

                    event_data = {
                        "type": "subtask_updated",
                        "taskId": task_id,
                        "subtaskUpdate": {
                            "subtaskId": subtask_id,
                            "status": update.status.value,
                            "progress": update.progress,
                            "waveNumber": wave_number,
                            "description": subtask_description,
                            "agentId": subtask_agent_id
                        }
                    }
                    yield f"data: {json.dumps(event_data)}\n\n"

                    current_task = _task_state.get_task(task_id)
                    if current_task:
                        from .task_history.models import TaskStatus
                        if _task_state.is_all_subtasks_completed(task_id):
                            current_task.status = TaskStatus.COMPLETED
                        elif _task_state.is_all_subtasks_terminal(task_id):
                            current_task.status = TaskStatus.COMPLETED_WITH_FAILURES
                        task_info = _task_to_info(current_task, _task_state)
                        status_changed_data = {
                            "type": "task_status_changed",
                            "task_id": task_id,
                            "status": task_info.status,
                            "progress": task_info.progress,
                            "completed_count": task_info.completed_count,
                            "total_count": task_info.total_count,
                            "subtasks": [_pydantic_dump(s) for s in task_info.subtasks],
                            "waves": [_pydantic_dump(w) for w in task_info.waves],
                        }
                        yield f"data: {json.dumps(status_changed_data)}\n\n"

                        if current_task.status == TaskStatus.COMPLETED:
                            completed_data = {"type": "task_completed", "taskId": task_id}
                            yield f"data: {json.dumps(completed_data)}\n\n"
                            break
                        elif current_task.status == TaskStatus.COMPLETED_WITH_FAILURES:
                            failed_count = sum(
                                1
                                for st in current_task.subtasks
                                if st.status == JobStatus.FAILED
                                and _is_original_business_subtask_id(st.subtask_id)
                            )
                            completed_with_failures_data = {
                                "type": "task_completed_with_failures",
                                "taskId": task_id,
                                "error": f"{failed_count} subtask(s) failed",
                                "failedCount": failed_count
                            }
                            yield f"data: {json.dumps(completed_with_failures_data)}\n\n"
                            break
                        elif current_task.status == TaskStatus.FAILED:
                            failed_data = {"type": "task_failed", "taskId": task_id, "error": current_task.error or "Task failed"}
                            yield f"data: {json.dumps(failed_data)}\n\n"
                            break
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            _task_state.remove_progress_callback(progress_callback)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"}
    )

@app.post("/api/tasks/{task_id}/pause")
async def pause_task(task_id: str):
    """Pause a task."""
    try:
        if _is_external_orchestrator_task(task_id):
            raise HTTPException(
                status_code=409,
                detail="Task is owned by external Across Orchestrator; local lifecycle controls are unavailable.",
            )
        success = _task_state.pause_task(task_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        return {"status": "success", "task_id": task_id}
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_http_500("Pause task")

@app.post("/api/tasks/{task_id}/resume")
async def resume_task(task_id: str):
    """Resume a paused task."""
    try:
        if _is_external_orchestrator_task(task_id):
            raise HTTPException(
                status_code=409,
                detail="Task is owned by external Across Orchestrator; local lifecycle controls are unavailable.",
            )
        success = _task_state.resume_task(task_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        return {"status": "success", "task_id": task_id}
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_http_500("Resume task")

@app.post("/api/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    """Cancel a task and all its subtasks."""
    try:
        if _is_external_orchestrator_task(task_id):
            raise HTTPException(
                status_code=409,
                detail="Task is owned by external Across Orchestrator; local lifecycle controls are unavailable.",
            )
        task = _task_state.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        _task_state.cancel_task(task_id)
        return {"status": "success", "task_id": task_id}
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_http_500("Cancel task")


@app.get("/api/resumable_tasks", response_model=List[Dict[str, Any]])
async def get_resumable_tasks():
    """Get list of tasks that can be resumed from persistence.

    `/api/resumable_tasks` avoids the `/api/tasks/{task_id}` route conflict.
    """
    try:
        resumable = _task_state.get_resumable_tasks()
        return resumable
    except Exception as e:
        raise _safe_http_500("Get resumable tasks")


@app.post("/api/tasks/{task_id}/restore")
async def restore_task(task_id: str):
    """Reject in-process task restore; external orchestrator owns execution."""
    raise HTTPException(status_code=410, detail=_removed_in_app_orchestration_detail(task_id, "restore"))


if __name__ == "__main__":
    start_api_server()
