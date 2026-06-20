import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict, Any, Tuple
import asyncio
import logging
import os
from pathlib import Path
import subprocess
import shutil
import json
import time
import threading
import signal
import sys
import re
import uuid
from contextlib import asynccontextmanager

from .credentials.validation import is_usable_secret, normalize_secret

logger = logging.getLogger("across_agents_assistant")

# Issue 47: Global flag for graceful shutdown
_shutdown_requested = False


def _safe_error_message(operation: str) -> str:
    return f"{operation} failed. See local backend logs for details."


def _safe_http_500(operation: str, exc: Exception) -> HTTPException:
    logger.exception("%s failed", operation)
    return HTTPException(status_code=500, detail=_safe_error_message(operation))


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


def _sanitize_public_error_text(value: Any) -> Any:
    if value is None:
        return None
    text = str(value)
    if "Traceback (most recent call last)" in text or "\n  File " in text:
        return _safe_error_message("Internal operation")
    return re.sub(r"[\r\n\t]+", " ", text).strip()[:2000]


def _sanitize_public_payload(value: Any, key: str = "") -> Any:
    lowered = key.lower()
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
from .plugin_runtime import (
    PluginLifecycleError,
    discover_across_plugins,
    forget_context_memory,
    get_agent_loop_memory_metrics,
    inspect_across_plugin,
    list_context_memories,
    remember_context_memory,
    run_context_plugin_lifecycle_action,
    update_context_memory_status,
)

# Global task history state
_task_state = TaskState()
_task_persistence_initialized = False
_server_started_at = time.time()

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
    yield


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
        raise _safe_http_500("Connect MCP server", e)

class MCPDisconnectRequest(BaseModel):
    server_id: str

@app.post("/api/mcp/disconnect")
async def disconnect_mcp_server(req: MCPDisconnectRequest):
    """Disconnect an MCP server."""
    try:
        await mcp_manager.disconnect_server(req.server_id)
        return {"status": "success"}
    except Exception as e:
        raise _safe_http_500("Disconnect MCP server", e)

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
    return {
        "has_any_key": has_any_key,
        "providers": providers,
        "readiness_blockers": [] if has_any_key else ["api_keys"],
    }


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
        raise HTTPException(status_code=400, detail="Unsupported plugin lifecycle action")
    except HTTPException:
        raise
    except (PluginLifecycleError, OrchestratorPluginUnavailable):
        raise HTTPException(status_code=500, detail=_safe_error_message("Plugin lifecycle action"))
    except Exception as exc:
        raise _safe_http_500("Plugin lifecycle action", exc)


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
        raise _safe_http_500("List Across Context memories", exc)


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
        raise _safe_http_500("Get Across Context Agent Loop memory metrics", exc)


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
        raise _safe_http_500("Remember Across Context memory", exc)


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
        raise _safe_http_500("Update Across Context memory", exc)


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
        raise _safe_http_500("Forget Across Context memory", exc)


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
        raise _safe_http_500("Get chat history", e)

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
        raise _safe_http_500("List projects", e)

@app.post("/api/projects/blank", response_model=ProjectInfo)
async def create_blank_project(req: CreateBlankProjectRequest):
    try:
        project = persistence.create_blank_project(req.name)
        return _project_info_from_row(project)
    except Exception as e:
        raise _safe_http_500("Create blank project", e)

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
        raise _safe_http_500("Create folder project", e)

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
        raise _safe_http_500("Get task status", e)

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
        raise _safe_http_500("List sessions", e)

@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and all its messages (cascade)."""
    try:
        persistence.clear_session(session_id)
        return {"status": "success", "session_id": session_id}
    except Exception as e:
        raise _safe_http_500("Delete session", e)

@app.patch("/api/sessions/{session_id}/rename")
async def rename_session(session_id: str, req: RenameSessionRequest):
    """Rename a session."""
    try:
        persistence.rename_session(session_id, req.name)
        return {"status": "success", "session_id": session_id, "name": req.name}
    except Exception as e:
        raise _safe_http_500("Rename session", e)

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
        raise _safe_http_500("Pin session", e)

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


@app.get("/api/agent-cards")
async def export_agent_cards():
    """Export public, non-secret internal agent cards for orchestration audits."""
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
        raise _safe_http_500("List LLM providers", e)

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
        raise _safe_http_500("List LLM models", e)

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
        raise _safe_http_500("Switch LLM provider", e)

@app.get("/api/llm/status")
async def get_llm_status():
    """Get current LLM provider status."""
    try:
        gw = get_gateway()
        current = gw.get_current_provider_id()
        config = load_llm_config()
        provider = next((p for p in config.providers if p.provider_id == current), None)
        return {
            "current_provider": current,
            "provider_name": provider.name if provider else None,
            "available": gw.get_current_adapter().is_available() if gw.get_current_adapter() else False
        }
    except Exception as e:
        raise _safe_http_500("Get LLM status", e)

class LLMChatRequest(BaseModel):
    message: str
    system_prompt: Optional[str] = None
    context: Optional[Dict[str, str]] = None
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
        gw = get_gateway()
        response = await gw.chat(
            message=req.message,
            system_prompt=req.system_prompt,
            context=req.context,
            model=req.model,
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
        raise _safe_http_500("LLM chat", e)

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
        raise _safe_http_500("Cancel chat", e)



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

    Supports Claude Code and Hermes agents with streaming output.
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
        raise _safe_http_500("Get tool authorizations", e)

class RevokeRequest(BaseModel):
    tool_name: str

@app.post("/api/tools/authorizations/revoke")
async def revoke_tool_authorization(req: RevokeRequest):
    """Revoke the 'Always Allow' authorization for a specific tool"""
    try:
        persistence.set_tool_authorization(req.tool_name, False)
        return {"status": "success", "tool_name": req.tool_name}
    except Exception as e:
        raise _safe_http_500("Revoke tool authorization", e)

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
        raise _safe_http_500("List task summaries", e)


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
        rows = _collect_release_task_rows(
            safe_limit,
            task_state=_task_state,
            external_task_rows=lambda: get_orchestrator_plugin_manager().list_task_summaries(),
        )
        return _sanitize_public_payload(build_release_evaluation_summary(rows))
    except Exception as e:
        raise _safe_http_500("Get release evaluation", e)


@app.post("/api/release/verification")
async def run_release_verification():
    """Create a non-secret release-candidate verification report."""
    try:
        report = _build_release_verification_report(
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
            write_report_directory=app_subdir("release-reports"),
        )
        return _sanitize_public_payload(report)
    except Exception as e:
        raise _safe_http_500("Run release verification", e)

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
        raise _safe_http_500("Get task", e)

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
        raise _safe_http_500("List tasks", e)

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
        raise _safe_http_500("Get job", e)

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
        raise _safe_http_500("Cancel job", e)


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
        raise _safe_http_500("Get task status", e)


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
        raise _safe_http_500("Pause task", e)

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
        raise _safe_http_500("Resume task", e)

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
        raise _safe_http_500("Cancel task", e)


@app.get("/api/resumable_tasks", response_model=List[Dict[str, Any]])
async def get_resumable_tasks():
    """Get list of tasks that can be resumed from persistence.

    `/api/resumable_tasks` avoids the `/api/tasks/{task_id}` route conflict.
    """
    try:
        resumable = _task_state.get_resumable_tasks()
        return resumable
    except Exception as e:
        raise _safe_http_500("Get resumable tasks", e)


@app.post("/api/tasks/{task_id}/restore")
async def restore_task(task_id: str):
    """Reject in-process task restore; external orchestrator owns execution."""
    raise HTTPException(status_code=410, detail=_removed_in_app_orchestration_detail(task_id, "restore"))


if __name__ == "__main__":
    start_api_server()
