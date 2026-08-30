from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import threading
import urllib.parse
import uuid

from .managed_plugin_payloads import (
    ManagedPluginPayloadError,
    bundled_install_source,
    ensure_node_runtime,
    extract_plugin_source,
    plugin_payload,
)
from .paths import component_cache_home, ecosystem_bin_dir, ecosystem_home, ecosystem_plugin_root
from .runtime_boundary import (
    contains_protected_user_reference,
    expand_user,
    is_developer_mode,
    is_product_mode,
    sanitized_product_runtime_env,
)
from .goal_contract.protocol import normalize_goal_contract, stable_goal_hash


@dataclass(frozen=True)
class KnownAcrossPlugin:
    plugin_id: str
    display_name: str
    kind: str
    command: str
    install_command: str
    install_source_env: str | None = None
    default_install_source: str | None = None


KNOWN_PLUGINS: tuple[KnownAcrossPlugin, ...] = (
    KnownAcrossPlugin(
        plugin_id="across-context",
        display_name="Across Context",
        kind="memory-provider",
        command="across-context",
        install_command="across-context install host-plugin",
        install_source_env="ACROSS_AGENTS_CONTEXT_INSTALL_SOURCE",
        default_install_source="git+https://github.com/fantasyce/across-context.git#v0.12.0",
    ),
    KnownAcrossPlugin(
        plugin_id="across-orchestrator",
        display_name="Across Orchestrator",
        kind="task-runtime",
        command="across-orchestrator",
        install_command="python3 -m pip install git+https://github.com/fantasyce/across-orchestrator.git@v0.12.2",
        install_source_env="ACROSS_AGENTS_ORCHESTRATOR_INSTALL_SOURCE",
        default_install_source="git+https://github.com/fantasyce/across-orchestrator.git@v0.12.2",
    ),
    KnownAcrossPlugin(
        plugin_id="across-autopilot",
        display_name="Across Autopilot",
        kind="autonomous-workflow",
        command="across-autopilot",
        install_command="across-autopilot install host-plugin",
        install_source_env="ACROSS_AGENTS_AUTOPILOT_INSTALL_SOURCE",
        default_install_source="git+https://github.com/fantasyce/across-autopilot.git#v0.6.0",
    ),
)


class PluginLifecycleError(RuntimeError):
    """Raised when a plugin lifecycle action cannot be completed safely."""


_PLUGIN_RUNTIME_LOCKS: dict[str, threading.RLock] = {}
_PLUGIN_RUNTIME_LOCKS_GUARD = threading.Lock()
_PLUGIN_LIFECYCLE_LOCKS: dict[str, threading.RLock] = {}
_PLUGIN_LIFECYCLE_LOCKS_GUARD = threading.Lock()


def _managed_plugin_runtime_lock(plugin_id: str) -> threading.RLock:
    normalized = str(plugin_id or "").strip()
    if not normalized:
        raise ValueError("Managed plugin id is required")
    with _PLUGIN_RUNTIME_LOCKS_GUARD:
        return _PLUGIN_RUNTIME_LOCKS.setdefault(normalized, threading.RLock())


@contextmanager
def managed_plugin_runtime_guard(plugin_id: str) -> Iterator[None]:
    """Serialize one plugin's host lifecycle and CLI consumer calls."""
    with _managed_plugin_runtime_lock(plugin_id):
        yield


def _managed_plugin_lifecycle_lock(plugin_id: str) -> threading.RLock:
    normalized = str(plugin_id or "").strip()
    if not normalized:
        raise ValueError("Managed plugin id is required")
    with _PLUGIN_LIFECYCLE_LOCKS_GUARD:
        return _PLUGIN_LIFECYCLE_LOCKS.setdefault(normalized, threading.RLock())


@contextmanager
def managed_plugin_lifecycle_guard(plugin_id: str) -> Iterator[None]:
    """Serialize all quiesce, mutation, and recovery phases for one plugin."""
    with _managed_plugin_lifecycle_lock(plugin_id):
        yield


_CONTEXT_RETRIEVAL_ROUTES = frozenset(
    {"keyword", "embedding", "evidence_graph", "project_profile", "loop_recall"}
)
_CONTEXT_MEMORY_STATUSES = frozenset({"active", "pinned", "pending", "archived", "expired"})
_CONTEXT_MEMORY_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_PLUGIN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_COMMAND_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
_CAPABILITY_MANIFEST_SCHEMA = "across-capability-manifest/1.0"
_MANIFEST_FIELDS = (
    "id",
    "display_name",
    "version",
    "kind",
    "capabilities",
    "entrypoints",
    "permissions",
    "trust",
    "health",
    "contributed_workflows",
    "optional_ui",
)


class CapabilityManifestError(ValueError):
    """Raised when a discovered capability manifest is not safe to expose."""


def discover_across_plugins(
    *,
    plugin_ids: list[str] | None = None,
    probe: bool = False,
    env: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    requested = set(plugin_ids or [])
    source, _runtime_boundary_issues = sanitized_product_runtime_env(env if env is not None else os.environ)
    plugin_ids_to_inspect = [plugin.plugin_id for plugin in KNOWN_PLUGINS]
    plugin_root = ecosystem_plugin_root(source)
    try:
        candidates = sorted(plugin_root.iterdir(), key=lambda path: path.name)
    except OSError:
        candidates = []
    known_ids = set(plugin_ids_to_inspect)
    for candidate in candidates:
        if (
            candidate.name not in known_ids
            and _PLUGIN_ID_PATTERN.fullmatch(candidate.name)
            and candidate.is_dir()
            and not candidate.is_symlink()
            and (candidate / "manifest.json").is_file()
        ):
            plugin_ids_to_inspect.append(candidate.name)

    discovered: list[dict[str, Any]] = []
    for plugin_id in plugin_ids_to_inspect:
        if requested and plugin_id not in requested:
            continue
        try:
            discovered.append(inspect_across_plugin(plugin_id, probe=probe, env=source))
        except CapabilityManifestError:
            continue
    return discovered


def inspect_across_plugin(
    plugin_id: str,
    *,
    probe: bool = False,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    requested_plugin_id = str(plugin_id or "")
    if not _PLUGIN_ID_PATTERN.fullmatch(requested_plugin_id):
        raise ValueError("Unknown Across plugin")

    source, runtime_boundary_issues = sanitized_product_runtime_env(env if env is not None else os.environ)
    across_home = ecosystem_home(source)
    plugin_root = ecosystem_plugin_root(source)
    plugin = _known_plugin(requested_plugin_id)
    safe_plugin_id = _safe_installed_plugin_id(
        requested_plugin_id,
        plugin_root=plugin_root,
        managed_plugin=plugin,
    )
    plugin_dir = plugin_root / safe_plugin_id
    if not _is_relative_to(plugin_dir, plugin_root) or plugin_dir.is_symlink():
        raise CapabilityManifestError("Plugin manifest is invalid")
    manifest_path = plugin_dir / "manifest.json"
    raw_manifest = _read_json_file(manifest_path)
    if plugin is None and not raw_manifest:
        raise ValueError("Unknown Across plugin")
    manifest_validation_failed = plugin is not None and manifest_path.is_file() and not raw_manifest
    try:
        manifest = _normalize_capability_manifest(
            raw_manifest,
            plugin_id=safe_plugin_id,
            plugin_dir=plugin_dir,
            env=source,
            managed_plugin=plugin,
        ) if raw_manifest else _managed_default_manifest(plugin)
    except CapabilityManifestError:
        if plugin is None:
            raise
        manifest = _managed_default_manifest(plugin)
        manifest_validation_failed = True
    managed_payload = plugin_payload(safe_plugin_id, source) if plugin is not None else None
    manifest = _apply_host_managed_install_contract(manifest, managed_payload)
    command = plugin.command if plugin is not None else _manifest_command(manifest)
    command_path = _resolve_manifest_command(command, plugin_dir, source) if command else plugin_dir / "bin" / safe_plugin_id
    command_exists = command_path.is_file() and os.access(command_path, os.X_OK)
    integrity_issues = _plugin_dir_integrity_issues(safe_plugin_id, plugin_dir)
    if managed_payload is not None:
        integrity_issues.extend(
            _managed_node_plugin_payload_integrity_issues(
                safe_plugin_id,
                plugin_dir,
                managed_payload,
            )
        )
        integrity_issues.extend(
            _managed_native_plugin_payload_integrity_issues(
                safe_plugin_id,
                plugin_dir,
                managed_payload,
            )
        )
    if manifest_validation_failed:
        integrity_issues.append("manifest failed capability schema validation")
    if command_exists:
        integrity_issues.extend(_command_integrity_issues(command_path, plugin_dir, source))
    manifest_exists = bool(raw_manifest)
    status: dict[str, Any] | None = None

    if probe and command_exists and not integrity_issues:
        probed_manifest = _run_json([str(command_path), "plugin-manifest", "--json"], source)
        if probed_manifest:
            try:
                manifest = _normalize_capability_manifest(
                    probed_manifest,
                    plugin_id=safe_plugin_id,
                    plugin_dir=plugin_dir,
                    env=source,
                    managed_plugin=plugin,
                )
                manifest = _apply_host_managed_install_contract(manifest, managed_payload)
                manifest_exists = True
            except CapabilityManifestError:
                integrity_issues.append("probed manifest failed capability schema validation")
        status = _run_json([str(command_path), "plugin-status", "--json"], source)

    installed = manifest_exists or command_exists
    public_status = status or {}
    actual_install_source = _actual_install_source(plugin_dir, safe_plugin_id)
    configured_install_source = (
        bundled_install_source(safe_plugin_id, source)
        or (_install_source(plugin, source) if plugin is not None else None)
    )
    install_status = public_status.get("install") if isinstance(public_status.get("install"), dict) else None
    if install_status:
        install_payload = dict(install_status)
        install_payload.setdefault("source", actual_install_source or configured_install_source)
        install_payload.setdefault("install_dir", str(plugin_dir))
        install_payload.setdefault("installable", True)
    else:
        install_payload = {
            "installable": plugin is not None,
            "command": plugin.install_command if plugin is not None else None,
            "install_dir": str(plugin_dir),
            "source": actual_install_source or configured_install_source,
        }
    if managed_payload is not None:
        install_payload.pop("command", None)
        install_payload.update(
            {
                "host_managed": True,
                "strategy": "bundled-native" if managed_payload.get("runtime") == "native" else "bundled-node",
                "requires_external_tools": False,
                "source": configured_install_source,
            }
        )
    return {
        "plugin_id": safe_plugin_id,
        "display_name": str(manifest.get("display_name") or (plugin.display_name if plugin else safe_plugin_id)),
        "kind": str(manifest.get("kind") or (plugin.kind if plugin else "capability-provider")),
        "version": str(manifest.get("version") or ""),
        "status": "needs_repair" if integrity_issues else (public_status.get("status") or ("installed" if installed else "not_installed")),
        "installed": bool(public_status.get("installed", installed)),
        "available": bool(public_status.get("available", command_exists)) and not integrity_issues,
        "probe": bool(probe),
        "integrity_ok": not integrity_issues,
        "integrity_issues": integrity_issues,
        "runtime_boundary_issues": runtime_boundary_issues,
        "manifest": manifest,
        "capability_manifest": manifest,
        "capabilities": manifest.get("capabilities") or {},
        "compatibility": manifest.get("compatibility") or {},
        "permissions": manifest.get("permissions") or {},
        "diagnostics": manifest.get("diagnostics") or {},
        "trust": manifest.get("trust") or {},
        "health": manifest.get("health") or {},
        "contributed_workflows": manifest.get("contributed_workflows") or [],
        "optional_ui": manifest.get("optional_ui"),
        "lifecycle": public_status.get("lifecycle") or (_default_lifecycle(plugin) if plugin else {"actions": ["probe"]}),
        "manifest_path": str(manifest_path),
        "manifest_exists": manifest_exists,
        "command": str(public_status.get("command") or command_path),
        "command_exists": bool(public_status.get("commandExists", command_exists)),
        "paths": {
            "home": str(across_home),
            "plugin": str(plugin_dir),
            "bin": str(ecosystem_bin_dir(source)),
            "data": str(across_home / "data" / safe_plugin_id),
            "config": str(across_home / "config" / safe_plugin_id),
            "run": str(across_home / "run" / safe_plugin_id),
            "logs": str(across_home / "logs" / safe_plugin_id),
            "cache": str(across_home / "cache" / safe_plugin_id),
        },
        "install": install_payload,
    }


def _safe_installed_plugin_id(
    requested_plugin_id: str,
    *,
    plugin_root: Path,
    managed_plugin: KnownAcrossPlugin | None,
) -> str:
    """Return an identifier sourced from constants or a directory entry, never request text."""
    if managed_plugin is not None:
        return managed_plugin.plugin_id
    try:
        candidates = tuple(plugin_root.iterdir())
    except OSError:
        candidates = ()
    for candidate in candidates:
        if (
            candidate.name == requested_plugin_id
            and _PLUGIN_ID_PATTERN.fullmatch(candidate.name)
            and candidate.is_dir()
            and not candidate.is_symlink()
            and (candidate / "manifest.json").is_file()
        ):
            return candidate.name
    raise ValueError("Unknown Across plugin")


def run_context_plugin_lifecycle_action(
    action: str,
    *,
    env: Mapping[str, str] | None = None,
    runner: Any = subprocess.run,
) -> dict[str, Any]:
    with managed_plugin_lifecycle_guard("across-context"):
        with managed_plugin_runtime_guard("across-context"):
            normalized = _normalize_action(action)
            if normalized == "probe":
                return inspect_across_plugin("across-context", probe=True, env=env)
            if normalized in {"install", "repair", "upgrade"}:
                return _install_across_context(
                    env=env,
                    runner=runner,
                    force_reinstall=normalized in {"repair", "upgrade"},
                )
            if normalized == "uninstall":
                return _uninstall_managed_plugin("across-context", "across-context", env=env)
            raise PluginLifecycleError("Unsupported Across Context lifecycle action")


def run_autopilot_plugin_lifecycle_action(
    action: str,
    *,
    env: Mapping[str, str] | None = None,
    runner: Any = subprocess.run,
) -> dict[str, Any]:
    with managed_plugin_lifecycle_guard("across-autopilot"):
        with managed_plugin_runtime_guard("across-autopilot"):
            normalized = _normalize_action(action)
            if normalized == "probe":
                return inspect_across_plugin("across-autopilot", probe=True, env=env)
            if normalized in {"install", "repair", "upgrade"}:
                return _install_node_host_plugin(
                    "across-autopilot",
                    env=env,
                    runner=runner,
                    force_reinstall=normalized in {"repair", "upgrade"},
                )
            if normalized == "uninstall":
                return _uninstall_managed_plugin("across-autopilot", "across-autopilot", env=env)
            raise PluginLifecycleError("Unsupported Across Autopilot lifecycle action")


def run_autopilot_cli_json(
    args: list[str],
    *,
    env: Mapping[str, str] | None = None,
    timeout: int = 60,
    allowed_returncodes: frozenset[int] | None = None,
    cwd: str | Path | None = None,
) -> Any:
    return _run_cli_json(
        "across-autopilot",
        args,
        env=env,
        timeout=timeout,
        allowed_returncodes=allowed_returncodes,
        cwd=cwd,
    )


def run_managed_goal_contract_probe(
    contract: Mapping[str, Any] | None,
    *,
    env: Mapping[str, str] | None = None,
    allow_missing: bool = False,
) -> dict[str, Any]:
    if contract is None:
        return {
            "schema_version": "across-goal-contract-probe-matrix/1.0",
            "status": "legacy_without_goal",
            "goal_contract": None,
            "plugins": {},
            "missing_plugins": [],
        }
    normalized = normalize_goal_contract(contract)
    expected = {
        "schema_version": "across-goal-contract-probe/1.0",
        "goal_id": normalized["goal_id"],
        "goal_revision": normalized["revision"],
        "criterion_ids": sorted(item["criterion_id"] for item in normalized["acceptance_criteria"]),
        "evidence_hash": stable_goal_hash(normalized),
    }
    payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    results: dict[str, Any] = {}
    missing: list[str] = []
    for command in ("across-context", "across-orchestrator", "across-autopilot"):
        try:
            result = _run_cli_json(command, ["goal-contract", "--contract-json", payload, "--json"], env=env)
        except PluginLifecycleError as exc:
            if allow_missing and "not installed" in str(exc):
                missing.append(command)
                continue
            raise
        if result != expected:
            raise PluginLifecycleError(f"{command} returned a mismatched Goal Contract binding")
        results[command] = result
    return {
        "schema_version": "across-goal-contract-probe-matrix/1.0",
        "status": "passed" if not missing else "degraded",
        "goal_contract": expected,
        "plugins": results,
        "missing_plugins": missing,
    }


def _run_managed_goal_revalidation_phase(
    phase: str,
    payload: Mapping[str, Any],
    *,
    env: Mapping[str, str] | None = None,
    expected_schema: str,
) -> dict[str, Any]:
    encoded = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    result = _run_cli_json(
        "across-orchestrator",
        ["goal-revalidation", phase, "--payload-json", encoded, "--json"],
        env=env,
        timeout=15,
    )
    if not isinstance(result, dict) or result.get("schema_version") != expected_schema:
        raise PluginLifecycleError(f"Across Orchestrator returned an invalid revalidation {phase} response")
    return result


def run_managed_goal_revalidation_plan(
    payload: Mapping[str, Any], *, env: Mapping[str, str] | None = None
) -> dict[str, Any]:
    return _run_managed_goal_revalidation_phase(
        "plan",
        payload,
        env=env,
        expected_schema="across-goal-revalidation-plan/1.1",
    )


def run_managed_goal_revalidation_start(
    payload: Mapping[str, Any], *, env: Mapping[str, str] | None = None
) -> dict[str, Any]:
    result = _run_managed_goal_revalidation_phase(
        "start",
        payload,
        env=env,
        expected_schema="across-goal-revalidation-attempt/1.1",
    )
    if result.get("state") not in {"awaiting_host_evidence", "queued", "running"}:
        raise PluginLifecycleError("Across Orchestrator returned an invalid revalidation start state")
    return result


def run_managed_goal_revalidation_complete(
    payload: Mapping[str, Any], *, env: Mapping[str, str] | None = None
) -> dict[str, Any]:
    result = _run_managed_goal_revalidation_phase(
        "complete",
        payload,
        env=env,
        expected_schema="across-goal-revalidation-attempt/1.1",
    )
    if result.get("state") != "completed":
        raise PluginLifecycleError("Across Orchestrator did not complete the revalidation attempt")
    return result


def build_direct_goal_revalidation_attempt(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build the equivalent host-owned attempt when a Direct Agent has no Orchestrator."""
    graph = dict(payload.get("graph") or {})
    criteria = dict(graph.get("criteria") or {})
    selected = sorted(set(map(str, payload.get("criterion_ids") or ())))
    if not selected or not set(selected).issubset(set(map(str, criteria))):
        raise PluginLifecycleError("Direct Agent revalidation criteria are invalid")
    superseded = sorted({
        str(evidence_id)
        for criterion_id in selected
        for evidence_id in dict(criteria.get(criterion_id) or {}).get("evidence_ids") or ()
    })
    all_evidence = {
        str(evidence_id)
        for raw in criteria.values()
        for evidence_id in dict(raw or {}).get("evidence_ids") or ()
    }
    return {
        "schema_version": "across-goal-revalidation-attempt/1.1",
        "attempt_id": f"direct-revalidation-attempt-{uuid.uuid4().hex}",
        "attempt_number": max(0, int(payload.get("prior_attempt_number") or 0)) + 1,
        "goal_id": str(payload.get("goal_id") or ""),
        "goal_revision": int(payload.get("goal_revision") or 0),
        "task_id": str(payload.get("task_id") or ""),
        "criterion_ids": selected,
        "changed_fingerprints": sorted(set(map(str, payload.get("changed_fingerprints") or ()))),
        "supersedes_evidence_ids": superseded,
        "preserved_evidence_ids": sorted(all_evidence - set(superseded)),
        "execution_mode": "host_validation",
        "input_fingerprint": str(payload.get("input_fingerprint") or ""),
        "state": "awaiting_host_evidence",
        "job_ids": [],
    }


def list_context_memories(
    *,
    project_root: str | None = None,
    status: str | None = None,
    scope: str | None = None,
    type: str | None = None,
    env: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    args = ["list", "--json"]
    if project_root:
        args.extend(["--project", project_root])
    elif status == "pending":
        args.append("--all-projects")
    if status:
        args.extend(["--status", status])
    payload = _run_context_cli_json(args, env=env, timeout=15)
    memories = payload if isinstance(payload, list) else payload.get("memories", [])
    if not isinstance(memories, list):
        return []
    entries = [entry for entry in memories if isinstance(entry, dict)]
    if scope:
        entries = [entry for entry in entries if str(entry.get("scope") or "") == scope]
    if type:
        entries = [entry for entry in entries if str(entry.get("type") or "") == type]
    return entries


def search_context_memories(
    query: str,
    *,
    project_root: str | None = None,
    mode: str = "hybrid",
    status: str | None = None,
    limit: int = 10,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    text = str(query or "").strip()
    if not text:
        raise PluginLifecycleError("Across Context search query is required")
    normalized_mode = str(mode or "hybrid").strip().lower()
    if normalized_mode not in {"keyword", "semantic", "hybrid"}:
        raise PluginLifecycleError("Across Context search mode is invalid")
    bounded_limit = max(1, min(int(limit), 100))
    args = ["search", text, "--mode", normalized_mode, "--limit", str(bounded_limit), "--json"]
    if project_root:
        args.extend(["--project", project_root])
    if status:
        args.extend(["--status", status])
    if status == "pending":
        args.append("--review-pending")
    payload = _run_context_cli_json(args, env=env, timeout=15)
    if not isinstance(payload, dict):
        raise PluginLifecycleError("Across Context returned an unexpected search payload")
    return payload


def improve_context_memory(
    *,
    project_root: str | None = None,
    include_projects: bool = False,
    source_ids: list[str] | None = None,
    similarity_threshold: float = 0.34,
    max_proposal_length: int = 420,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    normalized_project_root = _normalize_context_project_root(project_root)
    if normalized_project_root and include_projects:
        raise PluginLifecycleError("Across Context improve scope is ambiguous")
    normalized_source_ids = _normalize_context_memory_ids(source_ids or [], allow_empty=True)
    try:
        normalized_threshold = float(similarity_threshold)
    except (TypeError, ValueError) as exc:
        raise PluginLifecycleError("Across Context similarity threshold is invalid") from exc
    if not 0.0 <= normalized_threshold <= 1.0:
        raise PluginLifecycleError("Across Context similarity threshold is invalid")
    try:
        normalized_max_length = int(max_proposal_length)
    except (TypeError, ValueError) as exc:
        raise PluginLifecycleError("Across Context proposal length is invalid") from exc
    if not 80 <= normalized_max_length <= 4_000:
        raise PluginLifecycleError("Across Context proposal length is invalid")

    args = [
        "improve",
        "run",
        "--similarity-threshold",
        format(normalized_threshold, ".6g"),
        "--max-proposal-length",
        str(normalized_max_length),
        "--json",
    ]
    if normalized_project_root:
        args.extend(["--project", normalized_project_root])
    elif include_projects:
        args.append("--all-projects")
    for source_id in normalized_source_ids:
        args.extend(["--source-id", source_id])
    payload = _run_context_cli_json(args, env=env, timeout=60)
    return _require_context_object_payload(payload, "improve")


def retrieve_context_memories_merged(
    query: str,
    *,
    routes: list[str] | None = None,
    project_root: str | None = None,
    include_projects: bool = False,
    status: str | None = None,
    review_pending: bool = False,
    limit: int = 10,
    include_route_results: bool = False,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    text = str(query or "").strip()
    if not text or len(text) > 10_000 or "\x00" in text:
        raise PluginLifecycleError("Across Context retrieval query is invalid")
    normalized_routes = _normalize_context_retrieval_routes(routes)
    normalized_project_root = _normalize_context_project_root(project_root)
    if normalized_project_root and include_projects:
        raise PluginLifecycleError("Across Context retrieval scope is ambiguous")
    normalized_status = str(status or "").strip().lower() or None
    if normalized_status not in _CONTEXT_MEMORY_STATUSES | {None}:
        raise PluginLifecycleError("Across Context memory status is invalid")
    if normalized_status == "pending" and not review_pending:
        raise PluginLifecycleError("Across Context pending retrieval requires explicit review")
    if review_pending and normalized_status != "pending":
        raise PluginLifecycleError("Across Context pending review requires pending status")
    try:
        bounded_limit = int(limit)
    except (TypeError, ValueError) as exc:
        raise PluginLifecycleError("Across Context retrieval limit is invalid") from exc
    if not 1 <= bounded_limit <= 100:
        raise PluginLifecycleError("Across Context retrieval limit is invalid")

    args = [
        "retrieve",
        text,
        "--routes",
        ",".join(normalized_routes),
        "--limit",
        str(bounded_limit),
        "--json",
    ]
    if normalized_project_root:
        args.extend(["--project", normalized_project_root])
    elif include_projects:
        args.append("--all-projects")
    if normalized_status:
        args.extend(["--status", normalized_status])
    if review_pending:
        args.append("--review-pending")
    if include_route_results:
        args.append("--include-route-results")
    payload = _run_context_cli_json(args, env=env, timeout=30)
    return _require_context_object_payload(payload, "merged retrieval")


def rollback_distilled_context_memory(
    memory_id: str,
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    normalized_id = _normalize_context_memory_ids([memory_id])[0]
    payload = _run_context_cli_json(
        ["improve", "rollback", normalized_id, "--json"],
        env=env,
        timeout=15,
    )
    return _require_context_object_payload(payload, "distilled memory rollback")


def _normalize_context_project_root(project_root: str | None) -> str | None:
    if project_root is None:
        return None
    normalized = str(project_root).strip()
    if not normalized or len(normalized) > 4_096 or "\x00" in normalized or not os.path.isabs(normalized):
        raise PluginLifecycleError("Across Context project root is invalid")
    return os.path.normpath(normalized)


def _normalize_context_memory_ids(memory_ids: list[str], *, allow_empty: bool = False) -> list[str]:
    if not memory_ids and not allow_empty:
        raise PluginLifecycleError("Across Context memory id is required")
    if len(memory_ids) > 100:
        raise PluginLifecycleError("Across Context source id limit exceeded")
    normalized: list[str] = []
    seen: set[str] = set()
    for value in memory_ids:
        memory_id = str(value or "").strip()
        if not _CONTEXT_MEMORY_ID_PATTERN.fullmatch(memory_id):
            raise PluginLifecycleError("Across Context memory id is invalid")
        if memory_id not in seen:
            seen.add(memory_id)
            normalized.append(memory_id)
    return normalized


def _normalize_context_retrieval_routes(routes: list[str] | None) -> list[str]:
    requested = routes or ["keyword", "embedding", "evidence_graph", "project_profile", "loop_recall"]
    if not isinstance(requested, list) or not requested or len(requested) > len(_CONTEXT_RETRIEVAL_ROUTES):
        raise PluginLifecycleError("Across Context retrieval routes are invalid")
    normalized: list[str] = []
    for value in requested:
        route = str(value or "").strip().lower()
        if route not in _CONTEXT_RETRIEVAL_ROUTES or route in normalized:
            raise PluginLifecycleError("Across Context retrieval routes are invalid")
        normalized.append(route)
    return normalized


def _require_context_object_payload(payload: Any, operation: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise PluginLifecycleError(f"Across Context returned an unexpected {operation} payload")
    return payload


def get_agent_loop_memory_metrics(
    *,
    project_root: str | None = None,
    all_projects: bool = True,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    args = ["loop-memory-metrics", "--json"]
    if project_root:
        args.extend(["--project", project_root])
    elif all_projects:
        args.append("--all-projects")
    payload = _run_context_cli_json(args, env=env, timeout=15)
    return payload if isinstance(payload, dict) else {}


def remember_context_memory(
    *,
    text: str,
    project_root: str | None = None,
    scope: str = "global",
    type: str = "note",
    status: str = "pending",
    tags: list[str] | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    args = ["remember", text, "--scope", scope, "--type", type, "--status", status, "--json"]
    if project_root:
        args.extend(["--project", project_root])
    for tag in tags or []:
        args.extend(["--tag", str(tag)])
    payload = _run_context_cli_json(args, env=env, timeout=15)
    memory = payload.get("memory") if isinstance(payload, dict) else None
    if not isinstance(memory, dict):
        raise PluginLifecycleError("Across Context did not return a memory record")
    return memory


def remember_worker_context_outcome(
    *,
    outcome: Mapping[str, Any],
    project_root: str | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    args = [
        "worker-memory",
        "remember",
        "--outcome-json",
        json.dumps(dict(outcome), ensure_ascii=False, separators=(",", ":")),
        "--json",
    ]
    if project_root:
        args.extend(["--project", project_root])
    payload = _run_context_cli_json(args, env=env, timeout=15)
    if not isinstance(payload, dict) or not payload.get("id"):
        raise PluginLifecycleError("Across Context did not return a Worker memory record")
    return payload


def update_context_memory_status(
    memory_id: str,
    status: str,
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    normalized_id = _normalize_context_memory_ids([memory_id])[0]
    normalized_status = str(status or "").strip().lower()
    if normalized_status not in _CONTEXT_MEMORY_STATUSES:
        raise PluginLifecycleError("Across Context memory status is invalid")
    if normalized_status == "active":
        payload = _run_context_cli_json(["approve", normalized_id, "--json"], env=env, timeout=15)
        if isinstance(payload, dict) and isinstance(payload.get("memory"), dict):
            return payload["memory"]
        if isinstance(payload, dict) and payload.get("proposal_id") == normalized_id:
            return {"id": normalized_id, **payload}
        raise PluginLifecycleError("Across Context memory was not found")
    payload = _run_context_cli_json(
        ["update-status", normalized_status, normalized_id, "--json"],
        env=env,
        timeout=15,
    )
    updated = payload.get("updated") if isinstance(payload, dict) else None
    if isinstance(updated, list) and updated:
        first = updated[0]
        if isinstance(first, dict):
            return first
    raise PluginLifecycleError("Across Context memory was not found")


def forget_context_memory(memory_id: str, *, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    payload = _run_context_cli_json(["forget", memory_id, "--json"], env=env, timeout=15)
    forgotten = 0
    if isinstance(payload, dict):
        forgotten = int(payload.get("forgotten") or 0)
    return {"forgotten": forgotten > 0, "id": memory_id}


def uninstall_managed_plugin(plugin_id: str, *, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    plugin = _known_plugin(plugin_id)
    if plugin is None:
        raise PluginLifecycleError("Unknown Across plugin")
    return _uninstall_managed_plugin(plugin.plugin_id, plugin.command, env=env)


def _known_plugin(plugin_id: str) -> KnownAcrossPlugin | None:
    return next((plugin for plugin in KNOWN_PLUGINS if plugin.plugin_id == plugin_id), None)


def _managed_default_manifest(plugin: KnownAcrossPlugin | None) -> dict[str, Any]:
    if plugin is None:
        raise CapabilityManifestError("Plugin manifest is invalid")
    return {
        "schema_version": _CAPABILITY_MANIFEST_SCHEMA,
        "id": plugin.plugin_id,
        "display_name": plugin.display_name,
        "version": "",
        "kind": plugin.kind,
        "capabilities": {},
        "entrypoints": {},
        "permissions": {},
        "trust": {"level": "first_party", "managed": True},
        "health": {},
        "contributed_workflows": [],
        "optional_ui": None,
    }


def _apply_host_managed_install_contract(
    manifest: Mapping[str, Any],
    payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    normalized = dict(manifest)
    if payload is None:
        return normalized
    strategy = "bundled-native" if payload.get("runtime") == "native" else "bundled-node"
    lifecycle = dict(normalized.get("lifecycle") or {})
    for action in ("install", "upgrade", "repair"):
        descriptor = dict(lifecycle.get(action) or {})
        descriptor.update(
            {
                "hostManaged": True,
                "strategy": strategy,
                "requiresExternalTools": False,
            }
        )
        lifecycle[action] = descriptor
    normalized["lifecycle"] = lifecycle
    return normalized


def _normalize_capability_manifest(
    payload: Mapping[str, Any],
    *,
    plugin_id: str,
    plugin_dir: Path,
    env: Mapping[str, str],
    managed_plugin: KnownAcrossPlugin | None,
) -> dict[str, Any]:
    schema = str(payload.get("schema_version") or payload.get("schemaVersion") or "").strip()
    manifest_id = str(payload.get("id") or "").strip()
    if manifest_id != plugin_id or not _PLUGIN_ID_PATTERN.fullmatch(manifest_id):
        raise CapabilityManifestError("Plugin manifest is invalid")
    if managed_plugin is None and schema != _CAPABILITY_MANIFEST_SCHEMA:
        raise CapabilityManifestError("Plugin manifest is invalid")

    aliases = {
        "display_name": "displayName",
        "contributed_workflows": "contributedWorkflows",
        "optional_ui": "optionalUI",
    }
    normalized: dict[str, Any] = dict(payload) if managed_plugin is not None else {}
    normalized["schema_version"] = _CAPABILITY_MANIFEST_SCHEMA
    for field in _MANIFEST_FIELDS:
        present = field in payload
        value = payload.get(field)
        if not present and field in aliases:
            present = aliases[field] in payload
            value = payload.get(aliases[field])
        if not present:
            if managed_plugin is None:
                raise CapabilityManifestError("Plugin manifest is invalid")
            value = _managed_manifest_default(field, managed_plugin)
        normalized[field] = value

    required_strings = ("id", "display_name", "kind") if managed_plugin is not None else ("id", "display_name", "version", "kind")
    if not all(str(normalized[field]).strip() for field in required_strings):
        raise CapabilityManifestError("Plugin manifest is invalid")
    if not isinstance(normalized["capabilities"], (Mapping, list)):
        raise CapabilityManifestError("Plugin manifest is invalid")
    if not isinstance(normalized["entrypoints"], Mapping):
        raise CapabilityManifestError("Plugin manifest is invalid")
    if not isinstance(normalized["permissions"], (Mapping, list)):
        raise CapabilityManifestError("Plugin manifest is invalid")
    if not isinstance(normalized["trust"], Mapping) or not isinstance(normalized["health"], Mapping):
        raise CapabilityManifestError("Plugin manifest is invalid")
    if not isinstance(normalized["contributed_workflows"], list):
        raise CapabilityManifestError("Plugin manifest is invalid")
    if normalized["optional_ui"] is not None and not isinstance(normalized["optional_ui"], Mapping):
        raise CapabilityManifestError("Plugin manifest is invalid")

    _validate_manifest_runtime_values(normalized["entrypoints"], plugin_dir=plugin_dir, env=env)
    if normalized["optional_ui"] is not None:
        _validate_manifest_runtime_values(normalized["optional_ui"], plugin_dir=plugin_dir, env=env)
    return normalized


def _managed_manifest_default(field: str, plugin: KnownAcrossPlugin) -> Any:
    defaults: dict[str, Any] = {
        "id": plugin.plugin_id,
        "display_name": plugin.display_name,
        "version": "",
        "kind": plugin.kind,
        "capabilities": {},
        "entrypoints": {},
        "permissions": {},
        "trust": {"level": "first_party", "managed": True},
        "health": {},
        "contributed_workflows": [],
        "optional_ui": None,
    }
    return defaults[field]


def _validate_manifest_runtime_values(value: Any, *, plugin_dir: Path, env: Mapping[str, str], key: str = "") -> None:
    if isinstance(value, Mapping):
        for child_key, child_value in value.items():
            _validate_manifest_runtime_values(child_value, plugin_dir=plugin_dir, env=env, key=str(child_key).lower())
        return
    if isinstance(value, list):
        for item in value:
            _validate_manifest_runtime_values(item, plugin_dir=plugin_dir, env=env, key=key)
        return
    if not isinstance(value, str):
        return
    if any(character in value for character in ("\x00", "\n", "\r")):
        raise CapabilityManifestError("Plugin manifest is invalid")
    if key == "command":
        _resolve_manifest_command(value, plugin_dir, env, validate_only=True)
    elif key in {"path", "cwd", "root", "executable"}:
        _validate_manifest_path(value, plugin_dir, env)
    elif key in {"args", "arguments"}:
        argument_value = value.split("=", 1)[-1]
        if argument_value.startswith(("/", "~")) or ".." in Path(argument_value).parts:
            _validate_manifest_path(argument_value, plugin_dir, env)


def _validate_manifest_path(value: str, plugin_dir: Path, env: Mapping[str, str]) -> Path:
    candidate = Path(expand_user(value, env))
    if not candidate.is_absolute():
        candidate = plugin_dir / candidate
    if ".." in Path(value).parts or not _is_relative_to(candidate, plugin_dir):
        raise CapabilityManifestError("Plugin manifest is invalid")
    return candidate


def _resolve_manifest_command(
    command: str,
    plugin_dir: Path,
    env: Mapping[str, str],
    *,
    validate_only: bool = False,
) -> Path:
    value = str(command or "").strip()
    if not value or re.search(r"[\s;&|`$<>]", value):
        raise CapabilityManifestError("Plugin manifest is invalid")
    if os.path.isabs(value) or value.startswith("~"):
        candidate = Path(expand_user(value, env))
        if not (
            _is_relative_to(candidate, plugin_dir)
            or _is_relative_to(candidate, ecosystem_bin_dir(env))
        ):
            raise CapabilityManifestError("Plugin manifest is invalid")
    elif os.sep in value:
        candidate = _validate_manifest_path(value, plugin_dir, env)
    else:
        if not _COMMAND_NAME_PATTERN.fullmatch(value) or Path(value).name != value:
            raise CapabilityManifestError("Plugin manifest is invalid")
        local_candidate = _existing_named_child(plugin_dir / "bin", value)
        shared_candidate = _existing_named_child(ecosystem_bin_dir(env), value)
        if local_candidate is not None:
            candidate = local_candidate
        elif shared_candidate is not None:
            candidate = shared_candidate
        elif value == plugin_dir.name:
            candidate = ecosystem_bin_dir(env) / plugin_dir.name
        else:
            raise CapabilityManifestError("Plugin manifest is invalid")
    if not (_is_relative_to(candidate, plugin_dir) or _is_relative_to(candidate, ecosystem_bin_dir(env))):
        raise CapabilityManifestError("Plugin manifest is invalid")
    if not validate_only and candidate.exists() and candidate.is_symlink():
        resolved = candidate.resolve()
        if not (_is_relative_to(resolved, plugin_dir) or _is_relative_to(resolved, ecosystem_bin_dir(env))):
            raise CapabilityManifestError("Plugin manifest is invalid")
    return candidate


def _existing_named_child(directory: Path, requested_name: str) -> Path | None:
    """Resolve a basename to a filesystem-owned directory entry."""
    try:
        children = tuple(directory.iterdir())
    except OSError:
        return None
    for child in children:
        if child.name == requested_name:
            return child
    return None


def _manifest_command(manifest: Mapping[str, Any]) -> str | None:
    entrypoints = manifest.get("entrypoints")
    if not isinstance(entrypoints, Mapping):
        return None
    for descriptor in entrypoints.values():
        if isinstance(descriptor, Mapping) and descriptor.get("command"):
            return str(descriptor["command"])
    return None


def _normalize_action(action: str) -> str:
    normalized = str(action or "").strip().lower().replace("-", "_")
    if normalized == "refresh":
        return "probe"
    if normalized in {"install", "upgrade", "repair", "uninstall", "probe"}:
        return normalized
    raise PluginLifecycleError("Unsupported plugin lifecycle action")


def _default_lifecycle(plugin: KnownAcrossPlugin) -> dict[str, Any]:
    return {
        "actions": ["probe", "install", "repair", "upgrade", "uninstall"],
        "preservesDataOnUninstall": True,
        "installSource": plugin.default_install_source,
    }


def _install_source(plugin: KnownAcrossPlugin, env: Mapping[str, str]) -> str | None:
    if plugin.install_source_env:
        configured = str(env.get(plugin.install_source_env) or "").strip()
        if configured:
            return configured
    return plugin.default_install_source


def _actual_install_source(plugin_dir: Path, plugin_id: str) -> str | None:
    normalized = plugin_id.replace("-", "_")
    dashed = plugin_id.replace("_", "-")
    patterns = {
        f"venv/lib/python*/site-packages/{normalized}*.dist-info/direct_url.json",
        f"venv/lib/python*/site-packages/{dashed}*.dist-info/direct_url.json",
    }
    install_root = plugin_dir.expanduser().resolve()
    for pattern in sorted(patterns):
        for path in sorted(plugin_dir.glob(pattern)):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            url = str(payload.get("url") or "").strip()
            if not url or _contains_protected_user_reference(url):
                continue
            if url.startswith("file:"):
                parsed = urllib.parse.urlparse(url)
                local_path = Path(urllib.parse.unquote(parsed.path)).expanduser()
                if not (local_path.is_absolute() and _is_relative_to(local_path, install_root)):
                    continue
            return url
    return None


def _resolve_command(command: str, env: Mapping[str, str]) -> Path:
    bin_path = ecosystem_bin_dir(env) / command
    if bin_path.exists():
        return bin_path
    for item in str(env.get("PATH") or "").split(os.pathsep):
        if not item:
            continue
        candidate = Path(expand_user(item, env)) / command
        if _is_blocked_product_path(str(candidate), env):
            continue
        if candidate.exists():
            return candidate
    return bin_path


def _is_blocked_product_path(value: str, env: Mapping[str, str]) -> bool:
    return is_product_mode(env) and not is_developer_mode(env) and contains_protected_user_reference(value, env)


def _which_runtime_command(command: str, env: Mapping[str, str]) -> str | None:
    if os.path.isabs(command) or os.sep in command:
        if _is_blocked_product_path(command, env):
            return None
        candidate = Path(expand_user(command, env))
        return str(candidate) if candidate.is_file() and os.access(candidate, os.X_OK) else None
    for item in str(env.get("PATH") or "").split(os.pathsep):
        if not item:
            continue
        candidate = Path(expand_user(item, env)) / command
        if _is_blocked_product_path(str(candidate), env):
            continue
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _install_across_context(
    *,
    env: Mapping[str, str] | None = None,
    runner: Any = subprocess.run,
    force_reinstall: bool = False,
) -> dict[str, Any]:
    source, _runtime_boundary_issues = sanitized_product_runtime_env(env if env is not None else os.environ)
    across_home = ecosystem_home(source)
    managed_payload = plugin_payload("across-context", source)
    command_path = _resolve_command("across-context", source)
    command_integrity_issues = (
        _command_integrity_issues(command_path, ecosystem_plugin_root(source) / "across-context", source)
        if command_path.is_file() and os.access(command_path, os.X_OK)
        else []
    )
    if (
        not force_reinstall
        and command_path.is_file()
        and os.access(command_path, os.X_OK)
        and not command_integrity_issues
        and (managed_payload is None or _managed_node_wrapper_is_current(command_path))
    ):
        _run_checked(
            [str(command_path), "install", "host-plugin", "--across-home", str(across_home)],
            source,
            runner=runner,
        )
        return inspect_across_plugin("across-context", probe=True, env=source)

    plugin = _known_plugin("across-context")
    if managed_payload is not None and plugin is not None:
        return _install_bundled_node_plugin(plugin, source, runner=runner)

    npm = _which_runtime_command("npm", source)
    if not npm:
        raise PluginLifecycleError("npm is required to install Across Context when no existing command is available")

    install_source = _install_source(plugin, source) if plugin else None
    if not install_source:
        raise PluginLifecycleError("Across Context install source is not configured")

    cache_dir = component_cache_home(env=source) / "plugin-installers" / "across-context"
    shutil.rmtree(cache_dir, ignore_errors=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    _run_checked([npm, "install", "--prefix", str(cache_dir), install_source], source, runner=runner, timeout=180)
    installed_command = cache_dir / "node_modules" / ".bin" / "across-context"
    if not installed_command.is_file():
        raise PluginLifecycleError("Across Context installed but its CLI command was not found")
    _run_checked(
        [str(installed_command), "install", "host-plugin", "--across-home", str(across_home)],
        source,
        runner=runner,
        timeout=60,
    )
    return inspect_across_plugin("across-context", probe=True, env=source)


def _install_node_host_plugin(
    plugin_id: str,
    *,
    env: Mapping[str, str] | None = None,
    runner: Any = subprocess.run,
    force_reinstall: bool = False,
) -> dict[str, Any]:
    plugin = _known_plugin(plugin_id)
    if plugin is None:
        raise PluginLifecycleError("Unknown Across plugin")

    source, _runtime_boundary_issues = sanitized_product_runtime_env(env if env is not None else os.environ)
    across_home = ecosystem_home(source)
    managed_payload = plugin_payload(plugin.plugin_id, source)
    command_path = _resolve_command(plugin.command, source)
    command_integrity_issues = (
        _command_integrity_issues(command_path, ecosystem_plugin_root(source) / plugin.plugin_id, source)
        if command_path.is_file() and os.access(command_path, os.X_OK)
        else []
    )
    if (
        not force_reinstall
        and command_path.is_file()
        and os.access(command_path, os.X_OK)
        and not command_integrity_issues
        and (managed_payload is None or _managed_node_wrapper_is_current(command_path))
    ):
        _run_checked(
            [str(command_path), "install", "host-plugin", "--across-home", str(across_home)],
            source,
            runner=runner,
            timeout=60,
        )
        return inspect_across_plugin(plugin.plugin_id, probe=True, env=source)

    if managed_payload is not None:
        return _install_bundled_node_plugin(plugin, source, runner=runner)

    npm = _which_runtime_command("npm", source)
    if not npm:
        raise PluginLifecycleError(f"npm is required to install {plugin.display_name} when no existing command is available")

    install_source = _install_source(plugin, source)
    if not install_source:
        raise PluginLifecycleError(f"{plugin.display_name} install source is not configured")

    cache_dir = component_cache_home(env=source) / "plugin-installers" / plugin.plugin_id
    shutil.rmtree(cache_dir, ignore_errors=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    _run_checked([npm, "install", "--prefix", str(cache_dir), install_source], source, runner=runner, timeout=180)
    installed_command = cache_dir / "node_modules" / ".bin" / plugin.command
    if not installed_command.is_file():
        raise PluginLifecycleError(f"{plugin.display_name} installed but its CLI command was not found")
    _run_checked(
        [str(installed_command), "install", "host-plugin", "--across-home", str(across_home)],
        source,
        runner=runner,
        timeout=60,
    )
    return inspect_across_plugin(plugin.plugin_id, probe=True, env=source)


def _install_bundled_node_plugin(
    plugin: KnownAcrossPlugin,
    env: Mapping[str, str],
    *,
    runner: Any = subprocess.run,
) -> dict[str, Any]:
    across_home = ecosystem_home(env)
    cache_dir = component_cache_home(env=env) / "plugin-installers" / plugin.plugin_id / "bundled"
    try:
        node = ensure_node_runtime(across_home, env)
        source_root = extract_plugin_source(plugin.plugin_id, cache_dir, env)
        payload = plugin_payload(plugin.plugin_id, env) or {}
        entrypoint = source_root / str(payload.get("entrypoint") or "src/cli.js")
        if not entrypoint.is_file():
            raise ManagedPluginPayloadError(f"Bundled {plugin.display_name} entrypoint is missing")
        _run_checked(
            [
                str(node),
                str(entrypoint),
                "install",
                "host-plugin",
                "--across-home",
                str(across_home),
            ],
            env,
            runner=runner,
            timeout=180,
        )
        _write_managed_node_plugin_marker(
            plugin.plugin_id,
            ecosystem_plugin_root(env) / plugin.plugin_id,
            payload,
        )
        wrapper = ecosystem_bin_dir(env) / plugin.command
        target = ecosystem_plugin_root(env) / plugin.plugin_id / str(payload.get("entrypoint") or "src/cli.js")
        _write_managed_node_wrapper(wrapper, node=node, target=target)
        status = inspect_across_plugin(plugin.plugin_id, probe=True, env=env)
        if not (status.get("installed") and status.get("available") and status.get("integrity_ok")):
            raise PluginLifecycleError(f"{plugin.display_name} did not become available after installation")
        return status
    except ManagedPluginPayloadError as exc:
        raise PluginLifecycleError(f"{plugin.display_name} bundled installer is invalid") from exc
    finally:
        shutil.rmtree(cache_dir, ignore_errors=True)


def _managed_node_plugin_marker(plugin_dir: Path) -> Path:
    return plugin_dir / ".across-managed-plugin.json"


def _managed_node_plugin_payload_integrity_issues(
    plugin_id: str,
    plugin_dir: Path,
    payload: Mapping[str, Any],
) -> list[str]:
    if str(payload.get("runtime") or "") != "node" or not plugin_dir.is_dir():
        return []
    expected = {
        "plugin_id": plugin_id,
        "version": str(payload.get("version") or ""),
        "commit": str(payload.get("commit") or ""),
        "sha256": str(payload.get("sha256") or "").lower(),
    }
    marker = _read_json_file(_managed_node_plugin_marker(plugin_dir))
    if not marker:
        return ["installed plugin payload provenance is missing; upgrade or repair the plugin"]
    if marker.get("schema_version") != "across-managed-plugin-install/1.0":
        return ["installed plugin payload provenance is invalid; upgrade or repair the plugin"]
    if any(str(marker.get(key) or "").lower() != value.lower() for key, value in expected.items()):
        return ["installed plugin payload differs from the bundled version; upgrade the plugin"]
    return []


def _managed_native_plugin_payload_integrity_issues(
    plugin_id: str,
    plugin_dir: Path,
    payload: Mapping[str, Any],
) -> list[str]:
    if str(payload.get("runtime") or "") != "native" or not plugin_dir.is_dir():
        return []
    expected_sha256 = str(payload.get("sha256") or "").lower()
    install_state = _read_json_file(plugin_dir / "install-state.json")
    if not install_state:
        return ["installed native plugin payload provenance is missing; upgrade or repair the plugin"]
    if str(install_state.get("runtime") or "") != "bundled_native":
        return ["installed native plugin payload provenance is invalid; upgrade or repair the plugin"]
    if str(install_state.get("sha256") or "").lower() != expected_sha256:
        return ["installed native plugin payload differs from the bundled version; upgrade the plugin"]
    executable = plugin_dir / "venv" / "bin" / plugin_dir.name
    if not executable.is_file() or not os.access(executable, os.X_OK):
        return ["installed native plugin executable is missing; repair the plugin"]
    if expected_sha256 and _sha256_file(executable) != expected_sha256:
        return ["installed native plugin executable checksum mismatch; repair the plugin"]
    return []


def _write_managed_node_plugin_marker(
    plugin_id: str,
    plugin_dir: Path,
    payload: Mapping[str, Any],
) -> None:
    if not plugin_dir.is_dir():
        raise PluginLifecycleError("Managed plugin installer did not create the plugin directory")
    marker = _managed_node_plugin_marker(plugin_dir)
    temporary = marker.with_name(f".{marker.name}.tmp-{uuid.uuid4().hex}")
    temporary.write_text(
        json.dumps(
            {
                "schema_version": "across-managed-plugin-install/1.0",
                "plugin_id": plugin_id,
                "version": str(payload.get("version") or ""),
                "commit": str(payload.get("commit") or ""),
                "sha256": str(payload.get("sha256") or "").lower(),
            },
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, marker)


def _write_managed_node_wrapper(command_path: Path, *, node: Path, target: Path) -> None:
    command_path.parent.mkdir(parents=True, exist_ok=True)
    node_relative = os.path.relpath(node, start=command_path.parent)
    target_relative = os.path.relpath(target, start=command_path.parent)
    script = (
        "#!/bin/sh\n"
        "SCRIPT_DIR=$(CDPATH= cd \"$(dirname \"$0\")\" && pwd)\n"
        f"exec \"$SCRIPT_DIR\"/{shlex.quote(node_relative)} "
        f"\"$SCRIPT_DIR\"/{shlex.quote(target_relative)} \"$@\"\n"
    )
    command_path.write_text(script, encoding="utf-8")
    command_path.chmod(0o755)


def _managed_node_wrapper_is_current(command_path: Path) -> bool:
    try:
        if command_path.stat().st_size > 64 * 1024:
            return False
        text = command_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    return "../runtimes/node-" in text and "/usr/bin/env node" not in text


def _uninstall_managed_plugin(plugin_id: str, command: str, *, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source, _runtime_boundary_issues = sanitized_product_runtime_env(env if env is not None else os.environ)
    plugin_dir = ecosystem_plugin_root(source) / plugin_id
    wrapper = ecosystem_bin_dir(source) / command
    shutil.rmtree(plugin_dir, ignore_errors=True)
    try:
        wrapper.unlink()
    except FileNotFoundError:
        pass
    return {
        "plugin_id": plugin_id,
        "status": "not_installed",
        "removed": True,
        "plugin_dir": str(plugin_dir),
        "wrapper": str(wrapper),
        "preserved_data": str(ecosystem_home(source) / "data" / plugin_id),
    }


def _run_checked(
    args: list[str],
    env: Mapping[str, str],
    *,
    runner: Any = subprocess.run,
    timeout: int = 900,
) -> None:
    safe_env = _child_env_with_product_boundary(env)
    safe_env.setdefault("ACROSS_HOME", str(ecosystem_home(safe_env)))
    safe_env.setdefault("ACROSS_PLUGIN_HOME", str(ecosystem_plugin_root(safe_env)))
    safe_env.setdefault("ACROSS_BIN_HOME", str(ecosystem_bin_dir(safe_env)))
    npm_cache = component_cache_home(env=safe_env) / "npm"
    npm_cache.mkdir(parents=True, exist_ok=True)
    safe_env.setdefault("NPM_CONFIG_CACHE", str(npm_cache))
    completed = runner(
        args,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        env=safe_env,
        check=False,
    )
    if int(getattr(completed, "returncode", 1)) != 0:
        raise PluginLifecycleError("Plugin lifecycle command failed")


def _safe_plugin_env(env: Mapping[str, str]) -> dict[str, str]:
    safe_env = _child_env_with_product_boundary(env)
    safe_env.setdefault("ACROSS_HOME", str(ecosystem_home(safe_env)))
    safe_env.setdefault("ACROSS_PLUGIN_HOME", str(ecosystem_plugin_root(safe_env)))
    safe_env.setdefault("ACROSS_BIN_HOME", str(ecosystem_bin_dir(safe_env)))
    return safe_env


def _child_env_with_product_boundary(env: Mapping[str, str]) -> dict[str, str]:
    source = os.environ.copy()
    source.update({str(key): str(value) for key, value in env.items()})
    safe_env, _runtime_boundary_issues = sanitized_product_runtime_env(source)
    return safe_env


def _run_context_cli_json(args: list[str], *, env: Mapping[str, str] | None = None, timeout: int = 15) -> Any:
    return _run_cli_json("across-context", args, env=env, timeout=timeout)


def _run_cli_json(
    command: str,
    args: list[str],
    *,
    env: Mapping[str, str] | None = None,
    timeout: int = 15,
    allowed_returncodes: frozenset[int] | None = None,
    cwd: str | Path | None = None,
) -> Any:
    with managed_plugin_runtime_guard(command):
        return _run_cli_json_unlocked(
            command,
            args,
            env=env,
            timeout=timeout,
            allowed_returncodes=allowed_returncodes,
            cwd=cwd,
        )


def _run_cli_json_unlocked(
    command: str,
    args: list[str],
    *,
    env: Mapping[str, str] | None = None,
    timeout: int = 15,
    allowed_returncodes: frozenset[int] | None = None,
    cwd: str | Path | None = None,
) -> Any:
    source, _runtime_boundary_issues = sanitized_product_runtime_env(env if env is not None else os.environ)
    command_path = _resolve_command(command, source)
    if not command_path.is_file() or not os.access(command_path, os.X_OK):
        raise PluginLifecycleError(f"{command} plugin is not installed")
    plugin_id = command if command.startswith("across-") else command
    integrity_issues = _command_integrity_issues(command_path, ecosystem_plugin_root(source) / plugin_id, source)
    if integrity_issues:
        raise PluginLifecycleError(f"{command} plugin must be repaired because its runtime is not self-contained")
    try:
        run_cwd = None
        if cwd is not None:
            run_cwd = Path(cwd).expanduser().resolve(strict=True)
            if not run_cwd.is_dir() or run_cwd.parent == run_cwd:
                raise PluginLifecycleError("Plugin command working directory is invalid")
        completed = subprocess.run(
            [str(command_path), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            env=_safe_plugin_env(source),
            cwd=str(run_cwd) if run_cwd else None,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise PluginLifecycleError(f"{command} command timed out") from None
    accepted = allowed_returncodes if allowed_returncodes is not None else frozenset({0})
    if completed.returncode not in accepted:
        stderr = str(completed.stderr or "").lower()
        if command == "across-context" and "not found" in stderr:
            raise PluginLifecycleError("Across Context memory was not found")
        raise PluginLifecycleError(f"{command} command failed")
    try:
        return json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise PluginLifecycleError(f"{command} returned invalid JSON") from exc


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        if path.stat().st_size > 1024 * 1024:
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.expanduser().resolve().relative_to(root.expanduser().resolve())
        return True
    except Exception:
        return False


def _contains_protected_user_reference(value: str) -> bool:
    return contains_protected_user_reference(value)


def _command_integrity_issues(command_path: Path, plugin_dir: Path, env: Mapping[str, str]) -> list[str]:
    issues: list[str] = []
    bin_dir = ecosystem_bin_dir(env)
    resolved = command_path.expanduser().resolve()
    if not (_is_relative_to(resolved, bin_dir) or _is_relative_to(resolved, plugin_dir)):
        issues.append("command is outside the Across plugin runtime directory")
    if _contains_protected_user_reference(str(resolved)):
        issues.append("command path references a protected user directory")
    try:
        if command_path.stat().st_size <= 64 * 1024:
            text = command_path.read_text(encoding="utf-8", errors="ignore")
            if _contains_protected_user_reference(text):
                issues.append("command wrapper references a protected user directory")
    except Exception:
        pass
    return issues


def _plugin_dir_integrity_issues(plugin_id: str, plugin_dir: Path) -> list[str]:
    if plugin_id != "across-orchestrator":
        return []
    issues: list[str] = []
    install_root = plugin_dir.expanduser().resolve()
    venv_root = (plugin_dir / "venv").expanduser().resolve()

    source_dir = plugin_dir / "source"
    if source_dir.exists():
        issues.append("source directory remains under plugin runtime")
        if (source_dir / "src" / "across_agents_assistant").exists() or any(
            path.name == "across_agents_assistant" for path in source_dir.rglob("across_agents_assistant")
        ):
            issues.append("stale Across Agents Assistant source tree remains under plugin runtime")

    for path in plugin_dir.rglob("across_agents_assistant"):
        if path.exists():
            issues.append("stale Across Agents Assistant source tree remains under plugin runtime")
            break

    for path in (plugin_dir / "venv").glob("lib/python*/site-packages/*.pth"):
        issues.extend(_pth_integrity_issues(path, venv_root))

    for path in (plugin_dir / "venv").glob("lib/python*/site-packages/*.dist-info/direct_url.json"):
        issues.extend(_direct_url_integrity_issues(path, install_root))

    return sorted(set(issues))


def _pth_integrity_issues(path: Path, venv_root: Path) -> list[str]:
    issues: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return issues
    for line in lines:
        value = line.strip()
        if not value or value.startswith("#") or value.startswith("import "):
            continue
        if _contains_protected_user_reference(value):
            issues.append(f"{path.name} references a protected user directory")
        candidate = Path(value).expanduser()
        if candidate.is_absolute() and not _is_relative_to(candidate, venv_root):
            issues.append(f"{path.name} adds import path outside plugin virtualenv")
    return issues


def _direct_url_integrity_issues(path: Path, install_root: Path) -> list[str]:
    issues: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return issues
    if not isinstance(payload, dict):
        return issues
    dir_info = payload.get("dir_info")
    if isinstance(dir_info, dict) and dir_info.get("editable"):
        issues.append(f"{path.name} records an editable install")
    url = str(payload.get("url") or "")
    if _contains_protected_user_reference(url):
        issues.append(f"{path.name} references a protected user directory")
    if url.startswith("file:"):
        parsed = urllib.parse.urlparse(url)
        local_path = Path(urllib.parse.unquote(parsed.path)).expanduser()
        if local_path.is_absolute() and not _is_relative_to(local_path, install_root):
            issues.append(f"{path.name} references local source outside plugin directory")
    return issues


def _run_json(args: list[str], env: Mapping[str, str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            args,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            env=_safe_plugin_env(env),
            check=False,
        )
        if completed.returncode != 0:
            return {}
        payload = json.loads(completed.stdout or "{}")
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}
