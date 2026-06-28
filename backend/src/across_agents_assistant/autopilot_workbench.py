from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

from .autopilot_trigger_manager import build_trigger_registry_summary


WORKBENCH_SCHEMA_VERSION = "across-aaa-autopilot-workbench/1.0"

WORKBENCH_ENDPOINTS: dict[str, str] = {
    "snapshot": "/api/autopilot/workbench",
    "refresh": "/api/autopilot/workbench/refresh",
    "registry": "/api/autopilot/registry",
    "trigger_queue": "/api/autopilot/triggers",
    "trigger_run": "/api/autopilot/triggers/run",
    "trigger_configs": "/api/autopilot/trigger-configs",
    "trigger_tick": "/api/autopilot/trigger-configs/tick",
    "trigger_scheduler": "/api/autopilot/trigger-scheduler",
    "trigger_scheduler_start": "/api/autopilot/trigger-scheduler/start",
    "trigger_scheduler_stop": "/api/autopilot/trigger-scheduler/stop",
    "self_iteration_plan": "/api/autopilot/self-iteration-plan",
    "self_iteration_plan_ensure": "/api/autopilot/self-iteration-plan/ensure",
    "runs": "/api/autopilot/runs",
    "promotion_review_template": "/api/autopilot/runs/{run_id}/promotion-review",
    "telemetry": "/api/autopilot/telemetry",
    "ops_dashboard": "/api/autopilot/ops-dashboard",
    "capability_registry": "/api/capability-registry",
    "capability_registry_health": "/api/capability-registry/health",
    "memory_pending": "/api/memory/memories?status=pending",
    "memory_metrics": "/api/memory/agent-loop-metrics",
    "ecosystem_roadmap": "/api/ecosystem/roadmap",
    "protocol_gateway": "/api/ecosystem/protocol-gateway",
    "tool_pack_registry": "/api/ecosystem/tool-packs",
    "trust_sandbox": "/api/ecosystem/trust-sandbox",
    "evaluation_telemetry": "/api/ecosystem/evaluation-telemetry",
    "context_packs": "/api/ecosystem/context-packs",
    "external_agents": "/api/ecosystem/external-agents",
    "agent_plugin_runtime": "/api/ecosystem/agent-plugins",
    "agent_interop_e2e": "/api/autopilot/agent-interop-e2e",
}


def build_autopilot_workbench_snapshot(
    *,
    plugins: list[Mapping[str, Any]] | None = None,
    registry: Mapping[str, Any] | None = None,
    trigger_queue: Mapping[str, Any] | None = None,
    trigger_registry: Mapping[str, Any] | None = None,
    trigger_scheduler: Mapping[str, Any] | None = None,
    self_iteration_plan: Mapping[str, Any] | None = None,
    runs: Mapping[str, Any] | None = None,
    telemetry: Mapping[str, Any] | None = None,
    ops_dashboard: Mapping[str, Any] | None = None,
    capability_registry: Mapping[str, Any] | None = None,
    registry_health: Mapping[str, Any] | None = None,
    agent_loop_memory_metrics: Mapping[str, Any] | None = None,
    pending_memories: list[Mapping[str, Any]] | None = None,
    ecosystem_roadmap: Mapping[str, Any] | None = None,
    agent_plugin_runtime: Mapping[str, Any] | None = None,
    agent_interop_e2e: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build the host-facing Autopilot Workbench snapshot.

    The payload is intentionally bounded and public: it should be safe for the
    macOS client, local logs, and deterministic E2E tests.
    """

    plugins_list = [_dict(item) for item in plugins or []]
    registry = _dict(registry)
    trigger_queue = _dict(trigger_queue)
    trigger_registry = _dict(trigger_registry)
    trigger_scheduler = _dict(trigger_scheduler)
    self_iteration_plan = _dict(self_iteration_plan)
    runs = _dict(runs)
    telemetry = _dict(telemetry)
    ops_dashboard = _dict(ops_dashboard)
    capability_registry = _dict(capability_registry)
    registry_health = _dict(registry_health)
    agent_loop_memory_metrics = _dict(agent_loop_memory_metrics)
    pending_memories_list = [_dict(item) for item in pending_memories or []]
    ecosystem_roadmap = _dict(ecosystem_roadmap)
    agent_plugin_runtime = _dict(agent_plugin_runtime)
    agent_interop_e2e = _dict(agent_interop_e2e)

    trigger_summary = build_trigger_registry_summary(trigger_registry)
    queued_triggers = _list(trigger_queue.get("items"))
    recent_runs = _list(runs.get("runs"))[:8]
    latest_runs = _latest_runs_by_spec(recent_runs)
    run_count = _first_int(
        runs.get("run_count"),
        telemetry.get("run_count"),
        _nested(telemetry, "runs", "total"),
        len(recent_runs),
    )
    completed_runs = _first_int(
        _nested(telemetry, "by_status", "completed"),
        _nested(telemetry, "runs", "completed"),
        _count_by_status(recent_runs, "completed"),
    )
    historical_failed_runs = _first_int(
        _nested(telemetry, "by_status", "failed"),
        _nested(telemetry, "runs", "failed"),
        _count_by_status(recent_runs, "failed"),
    )
    failed_runs = _count_by_status(list(latest_runs.values()), "failed") if latest_runs else historical_failed_runs
    historical_promotion_ready_count = _first_int(
        _mapping_size(telemetry.get("promotion_ready_by_spec")),
        sum(1 for item in recent_runs if _truthy(_dict(item).get("promotion_ready"))),
    )
    promotion_ready_count = (
        sum(1 for item in latest_runs.values() if _truthy(_dict(item).get("promotion_ready")))
        if latest_runs
        else historical_promotion_ready_count
    )
    capability_ready_count = _first_int(
        _nested(ops_dashboard, "summary", "capability_ready_count"),
        _count_ready_capabilities(capability_registry),
    )
    pending_memory_count = _first_int(
        _nested(agent_loop_memory_metrics, "totals", "pending_count"),
        len(pending_memories_list),
    )
    registry_health_status = str(registry_health.get("status") or _nested(ops_dashboard, "summary", "registry_health_status") or "unknown")
    self_iteration_status = str(self_iteration_plan.get("status") or _nested(ops_dashboard, "self_iteration_plan", "status") or "unknown")
    scheduler_running = bool(trigger_scheduler.get("running") or _nested(ops_dashboard, "trigger_scheduler", "running"))
    autopilot_plugin = _plugin_by_id(plugins_list, "across-autopilot")
    autopilot_available = autopilot_plugin.get("available") is True if autopilot_plugin else bool(registry)
    ops_status = str(ops_dashboard.get("status") or "unknown")

    summary = {
        "run_count": run_count,
        "completed_run_count": completed_runs,
        "failed_run_count": failed_runs,
        "historical_failed_run_count": historical_failed_runs,
        "pending_trigger_count": len(queued_triggers),
        "registered_trigger_count": int(trigger_summary.get("total") or 0),
        "active_trigger_count": int(trigger_summary.get("enabled") or 0),
        "scheduler_running": scheduler_running,
        "self_iteration_status": self_iteration_status,
        "capability_ready_count": capability_ready_count,
        "registry_health_status": registry_health_status,
        "pending_memory_count": pending_memory_count,
        "promotion_ready_count": promotion_ready_count,
        "historical_promotion_ready_count": historical_promotion_ready_count,
        "autopilot_available": autopilot_available,
        "ecosystem_route_count": _nested(ecosystem_roadmap, "summary", "route_count") or 0,
        "ecosystem_ready_route_count": _nested(ecosystem_roadmap, "summary", "ready_route_count") or 0,
        "external_agent_count": _nested(agent_plugin_runtime, "summary", "external_agent_count") or 0,
        "healthy_external_agent_count": _nested(agent_plugin_runtime, "summary", "healthy_external_agent_count") or 0,
        "agent_plugin_count": _nested(agent_plugin_runtime, "summary", "agent_plugin_count") or 0,
        "ready_agent_plugin_count": _nested(agent_plugin_runtime, "summary", "ready_agent_plugin_count") or 0,
        "agent_plugin_context_pack_count": _nested(agent_plugin_runtime, "summary", "context_pack_count") or 0,
        "agent_interop_e2e_status": str(agent_interop_e2e.get("status") or "not_run"),
    }
    status, reasons = _workbench_status(
        summary=summary,
        ops_status=ops_status,
        trigger_summary=trigger_summary,
    )
    sections = {
        "self_iteration": _section(
            "self_iteration",
            "Continuous Self-Iteration",
            "passed" if self_iteration_status == "active" else "attention",
            {
                "status": self_iteration_status,
                "ready": bool(self_iteration_plan.get("ready")),
                "spec": self_iteration_plan.get("spec"),
                "default_trigger_id": self_iteration_plan.get("default_trigger_id"),
            },
            _list(self_iteration_plan.get("readiness")),
            WORKBENCH_ENDPOINTS["self_iteration_plan"],
        ),
        "triggers": _section(
            "triggers",
            "Triggers",
            "passed" if not queued_triggers and (not trigger_summary.get("total") or scheduler_running) else "attention",
            {
                "registered": trigger_summary.get("total"),
                "active": trigger_summary.get("enabled"),
                "queued": len(queued_triggers),
                "scheduler_running": scheduler_running,
            },
            _bounded_trigger_items(trigger_registry, queued_triggers),
            WORKBENCH_ENDPOINTS["trigger_configs"],
        ),
        "runs": _section(
            "runs",
            "Recent Runs",
            "attention" if failed_runs else "passed",
            {
                "total": run_count,
                "completed": completed_runs,
                "failed": failed_runs,
                "historical_failed": historical_failed_runs,
            },
            _bounded_run_items(recent_runs),
            WORKBENCH_ENDPOINTS["runs"],
        ),
        "promotion": _section(
            "promotion",
            "Promotion Review",
            "attention" if promotion_ready_count else "passed",
            {
                "ready_count": promotion_ready_count,
                "historical_ready_count": historical_promotion_ready_count,
                "human_approval_required": True,
                "merge_release_blocked": True,
            },
            _promotion_items(recent_runs),
            WORKBENCH_ENDPOINTS["promotion_review_template"],
        ),
        "ops": _section(
            "ops",
            "Operations",
            ops_status if ops_status in {"passed", "attention", "failed"} else "unknown",
            _dict(ops_dashboard.get("summary")),
            _list(ops_dashboard.get("next_actions")),
            WORKBENCH_ENDPOINTS["ops_dashboard"],
        ),
        "capabilities": _section(
            "capabilities",
            "Capability Registry",
            "passed" if registry_health_status == "passed" and capability_ready_count >= 25 else "failed",
            {
                "ready_count": capability_ready_count,
                "registry_health_status": registry_health_status,
                "capability_count": _list_size(capability_registry.get("capabilities")),
            },
            _list(registry_health.get("checks"))[:8],
            WORKBENCH_ENDPOINTS["capability_registry"],
        ),
        "memory": _section(
            "memory",
            "Context Memory Review",
            "attention" if pending_memory_count else ("unavailable" if not agent_loop_memory_metrics and not pending_memories_list else "passed"),
            {
                "pending_count": pending_memory_count,
                "candidate_count": _nested(agent_loop_memory_metrics, "totals", "candidate_count"),
                "approved_count": _nested(agent_loop_memory_metrics, "totals", "approved_count"),
            },
            _bounded_memory_items(pending_memories_list),
            WORKBENCH_ENDPOINTS["memory_pending"],
        ),
        "protocols": _section(
            "protocols",
            "AAA Protocols",
            "passed" if autopilot_available else "failed",
            {
                "plugin_count": len(plugins_list),
                "available_plugin_count": sum(1 for item in plugins_list if item.get("available") is True),
            },
            _protocol_items(plugins_list),
            WORKBENCH_ENDPOINTS["snapshot"],
        ),
        "plugins": _section(
            "plugins",
            "Across Plugins",
            "passed" if autopilot_available else "failed",
            {
                "autopilot_available": autopilot_available,
                "plugin_count": len(plugins_list),
            },
            _bounded_plugin_items(plugins_list),
            "/api/plugins",
        ),
        "agent_plugins": _section(
            "agent_plugins",
            "Generic Agent Plugins",
            str(agent_plugin_runtime.get("status") or "unavailable"),
            _dict(agent_plugin_runtime.get("summary")),
            _agent_plugin_runtime_items(agent_plugin_runtime),
            WORKBENCH_ENDPOINTS["agent_plugin_runtime"],
        ),
        "agent_interop_e2e": _section(
            "agent_interop_e2e",
            "Agent Interop E2E Lab",
            "attention" if str(agent_interop_e2e.get("status") or "not_run") == "not_run" else str(agent_interop_e2e.get("status") or "unknown"),
            {
                "status": str(agent_interop_e2e.get("status") or "not_run"),
                "passed_count": _nested(agent_interop_e2e, "summary", "passed_count") or 0,
                "failed_count": _nested(agent_interop_e2e, "summary", "failed_count") or 0,
                "host_target_count": _nested(agent_interop_e2e, "summary", "host_target_count") or 0,
                "mcp_server_count": _nested(agent_interop_e2e, "summary", "mcp_server_count") or 0,
                "evidence_node_count": _nested(agent_interop_e2e, "summary", "evidence_node_count") or 0,
                "protocol_readiness_score": _nested(agent_interop_e2e, "summary", "protocol_readiness_score"),
                "market_readiness_status": _nested(agent_interop_e2e, "summary", "market_readiness_status"),
                "trust_receipt_status": _nested(agent_interop_e2e, "summary", "trust_receipt_status"),
                "frontier_interop_status": _nested(agent_interop_e2e, "summary", "frontier_interop_status"),
                "remote_mcp_template_status": _nested(agent_interop_e2e, "summary", "remote_mcp_template_status"),
                "a2a_delegation_status": _nested(agent_interop_e2e, "summary", "a2a_delegation_status"),
                "otel_span_count": _nested(agent_interop_e2e, "summary", "otel_span_count"),
                "eval_case_count": _nested(agent_interop_e2e, "summary", "eval_case_count"),
                "otlp_resource_span_count": _nested(agent_interop_e2e, "summary", "otlp_resource_span_count"),
            },
            _bounded_agent_interop_items(agent_interop_e2e),
            WORKBENCH_ENDPOINTS["agent_interop_e2e"],
        ),
    }
    sections.update(_ecosystem_sections(ecosystem_roadmap))
    return {
        "schema_version": WORKBENCH_SCHEMA_VERSION,
        "status": status,
        "generated_at": generated_at or _now(),
        "summary": summary,
        "status_reasons": reasons,
        "sections": sections,
        "actions": _actions(
            summary=summary,
            status_reasons=reasons,
            ops_dashboard=ops_dashboard,
            ecosystem_roadmap=ecosystem_roadmap,
        ),
        "endpoints": dict(WORKBENCH_ENDPOINTS),
    }


def _workbench_status(
    *,
    summary: Mapping[str, Any],
    ops_status: str,
    trigger_summary: Mapping[str, Any],
) -> tuple[str, list[str]]:
    failed_reasons: list[str] = []
    attention_reasons: list[str] = []
    if summary.get("autopilot_available") is not True:
        failed_reasons.append("across-autopilot is unavailable")
    if str(summary.get("registry_health_status") or "") == "failed":
        failed_reasons.append("capability registry health failed")
    if ops_status == "failed":
        failed_reasons.append("operations dashboard failed")
    if int(summary.get("capability_ready_count") or 0) < 25:
        failed_reasons.append("capability ready count is below release floor")
    if failed_reasons:
        return "failed", failed_reasons

    if int(summary.get("failed_run_count") or 0) > 0:
        attention_reasons.append("recent Autopilot runs failed")
    if int(summary.get("pending_memory_count") or 0) > 0:
        attention_reasons.append("Context has pending memory review items")
    if str(summary.get("agent_interop_e2e_status") or "") != "passed":
        attention_reasons.append("Agent interop E2E has not passed")
    if str(summary.get("self_iteration_status") or "") != "active":
        attention_reasons.append("continuous self-iteration is not active")
    if int(summary.get("registered_trigger_count") or 0) > 0 and summary.get("scheduler_running") is not True:
        attention_reasons.append("registered triggers exist but scheduler is stopped")
    if int(summary.get("pending_trigger_count") or 0) > 0:
        attention_reasons.append("queued triggers are waiting to run")
    if int(summary.get("promotion_ready_count") or 0) > 0:
        attention_reasons.append("promotion-ready candidates require human review")
    if ops_status == "attention":
        attention_reasons.append("operations dashboard requires attention")
    if int(trigger_summary.get("total") or 0) == 0:
        attention_reasons.append("no Autopilot triggers are registered")
    if attention_reasons:
        return "attention", attention_reasons
    return "passed", []


def _actions(
    *,
    summary: Mapping[str, Any],
    status_reasons: list[str],
    ops_dashboard: Mapping[str, Any],
    ecosystem_roadmap: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if summary.get("autopilot_available") is not True:
        actions.append(_action("repair_autopilot_plugin", "high", "Repair Across Autopilot plugin", "Autopilot is unavailable.", "/api/plugins/across-autopilot/actions"))
    if str(summary.get("self_iteration_status") or "") != "active":
        actions.append(_action("ensure_self_iteration_plan", "medium", "Ensure self-iteration plan", "Register or reactivate the default self-iteration trigger.", WORKBENCH_ENDPOINTS["self_iteration_plan_ensure"]))
    if int(summary.get("registered_trigger_count") or 0) > 0 and summary.get("scheduler_running") is not True:
        actions.append(_action("start_trigger_scheduler", "medium", "Start trigger scheduler", "Registered triggers need a running local scheduler.", WORKBENCH_ENDPOINTS["trigger_scheduler_start"]))
    if int(summary.get("pending_trigger_count") or 0) > 0:
        actions.append(_action("run_queued_trigger", "medium", "Run queued trigger", "One or more Autopilot triggers are waiting.", WORKBENCH_ENDPOINTS["trigger_run"]))
    if int(summary.get("pending_memory_count") or 0) > 0:
        actions.append(_action("review_pending_memory", "medium", "Review pending Context memory", "Context memory candidates require approval or rejection.", WORKBENCH_ENDPOINTS["memory_pending"]))
    if int(summary.get("promotion_ready_count") or 0) > 0:
        actions.append(_action("open_promotion_review", "high", "Review promotion candidate", "Promotion-ready output must remain human-gated.", WORKBENCH_ENDPOINTS["promotion_review_template"]))
    if str(summary.get("agent_interop_e2e_status") or "") != "passed":
        actions.append(_action("run_agent_interop_e2e", "high", "Run agent interop E2E", "Verify Context, Orchestrator, and Autopilot load through generic agent hosts.", WORKBENCH_ENDPOINTS["agent_interop_e2e"]))
    for item in _list(ops_dashboard.get("next_actions")):
        item_dict = _dict(item)
        action_id = str(item_dict.get("action") or "").strip()
        if not action_id or any(existing["id"] == action_id for existing in actions):
            continue
        actions.append(
            _action(
                action_id,
                str(item_dict.get("priority") or "low"),
                action_id.replace("_", " ").title(),
                str(item_dict.get("reason") or "Ops dashboard recommended this action."),
                None,
            )
        )
    for item in _list(_dict(ecosystem_roadmap).get("actions")):
        item_dict = _dict(item)
        action_id = str(item_dict.get("id") or "").strip()
        if not action_id or any(existing["id"] == action_id for existing in actions):
            continue
        actions.append(
            _action(
                action_id,
                str(item_dict.get("priority") or "medium"),
                str(item_dict.get("title") or action_id.replace("_", " ").title()),
                str(item_dict.get("reason") or "Ecosystem roadmap recommended this action."),
                item_dict.get("endpoint"),
            )
        )
    if not actions:
        actions.append(_action("continue_scheduled_e2e", "low", "Continue scheduled E2E", "Workbench status is healthy.", WORKBENCH_ENDPOINTS["snapshot"]))
    if status_reasons:
        actions[0]["status_reason_count"] = len(status_reasons)
    return actions[:8]


def _ecosystem_sections(ecosystem_roadmap: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    sections = _dict(ecosystem_roadmap.get("sections"))
    result: dict[str, dict[str, Any]] = {}
    for key in [
        "protocol_gateway",
        "tool_pack_registry",
        "trust_sandbox",
        "evaluation_telemetry",
        "context_packs",
        "external_agents",
        "agent_plugin_runtime",
    ]:
        section = _dict(sections.get(key))
        if section:
            result[key] = section
    return result


def _section(
    section_id: str,
    title: str,
    status: str,
    summary: Mapping[str, Any] | None,
    items: list[Any] | None,
    endpoint: str | None,
) -> dict[str, Any]:
    return {
        "id": section_id,
        "title": title,
        "status": status,
        "summary": dict(summary or {}),
        "items": _list(items)[:12],
        "endpoint": endpoint,
    }


def _action(action_id: str, priority: str, title: str, reason: str, endpoint: str | None) -> dict[str, Any]:
    payload = {
        "id": action_id,
        "priority": priority,
        "title": title,
        "reason": reason,
    }
    if endpoint:
        payload["endpoint"] = endpoint
    return payload


def _bounded_trigger_items(trigger_registry: Mapping[str, Any], queued_triggers: list[Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for record in _list(trigger_registry.get("triggers"))[:8]:
        record_dict = _dict(record)
        items.append(
            {
                "kind": "registered",
                "trigger_id": record_dict.get("trigger_id"),
                "spec": record_dict.get("spec"),
                "type": record_dict.get("type"),
                "enabled": record_dict.get("enabled"),
                "paused": record_dict.get("paused"),
                "enqueue_count": record_dict.get("enqueue_count"),
                "last_status": record_dict.get("last_status"),
            }
        )
    for record in queued_triggers[:4]:
        record_dict = _dict(record)
        items.append(
            {
                "kind": "queued",
                "trigger_id": record_dict.get("trigger_id"),
                "spec": record_dict.get("spec"),
                "status": record_dict.get("status"),
                "type": record_dict.get("type"),
            }
        )
    return items


def _bounded_run_items(runs: list[Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for record in runs[:8]:
        record_dict = _dict(record)
        run_id = record_dict.get("run_id") or record_dict.get("id")
        items.append(
            {
                "run_id": run_id,
                "spec_id": record_dict.get("spec_id") or record_dict.get("spec"),
                "status": record_dict.get("status"),
                "quality_status": record_dict.get("quality_status"),
                "promotion_ready": record_dict.get("promotion_ready"),
                "created_at": record_dict.get("created_at"),
                "promotion_review_endpoint": f"/api/autopilot/runs/{run_id}/promotion-review" if run_id else None,
            }
        )
    return items


def _promotion_items(runs: list[Any]) -> list[dict[str, Any]]:
    return [item for item in _bounded_run_items(runs) if _truthy(item.get("promotion_ready"))]


def _agent_plugin_runtime_items(agent_plugin_runtime: Mapping[str, Any]) -> list[dict[str, Any]]:
    sections = _dict(agent_plugin_runtime.get("sections"))
    items: list[dict[str, Any]] = []
    for section in sections.values():
        section_dict = _dict(section)
        items.append(
            {
                "id": section_dict.get("id"),
                "title": section_dict.get("title"),
                "status": section_dict.get("status"),
                "summary": section_dict.get("summary"),
            }
        )
    return items[:8]


def _bounded_agent_interop_items(agent_interop_e2e: Mapping[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for check in _list(agent_interop_e2e.get("checks"))[:8]:
        check_dict = _dict(check)
        items.append(
            {
                "id": check_dict.get("id"),
                "status": check_dict.get("status"),
                "summary": check_dict.get("summary"),
            }
        )
    return items


def _bounded_memory_items(memories: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for memory in memories[:8]:
        memory_dict = _dict(memory)
        items.append(
            {
                "id": memory_dict.get("id"),
                "scope": memory_dict.get("scope"),
                "type": memory_dict.get("type"),
                "status": memory_dict.get("status"),
                "project_name": memory_dict.get("project_name"),
                "updated_at": memory_dict.get("updated_at"),
            }
        )
    return items


def _protocol_items(plugins: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    plugin_ids = {str(item.get("plugin_id") or "") for item in plugins}
    return [
        {"id": "host-control-plane", "owner": "across-agents-assistant", "status": "passed", "endpoint": WORKBENCH_ENDPOINTS["snapshot"]},
        {"id": "agent-loop-runtime", "owner": "across-orchestrator", "status": "passed" if "across-orchestrator" in plugin_ids else "unknown", "endpoint": "/api/orchestrator/loops"},
        {"id": "autopilot-loop-spec", "owner": "across-autopilot", "status": "passed" if "across-autopilot" in plugin_ids else "unknown", "endpoint": WORKBENCH_ENDPOINTS["runs"]},
        {"id": "context-memory-review", "owner": "across-context", "status": "passed" if "across-context" in plugin_ids else "unknown", "endpoint": WORKBENCH_ENDPOINTS["memory_pending"]},
        {"id": "capability-registry", "owner": "across-agents-assistant", "status": "passed", "endpoint": WORKBENCH_ENDPOINTS["capability_registry"]},
    ]


def _bounded_plugin_items(plugins: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for plugin in plugins[:8]:
        plugin_dict = _dict(plugin)
        items.append(
            {
                "plugin_id": plugin_dict.get("plugin_id"),
                "display_name": plugin_dict.get("display_name"),
                "kind": plugin_dict.get("kind"),
                "version": plugin_dict.get("version"),
                "status": plugin_dict.get("status"),
                "installed": plugin_dict.get("installed"),
                "available": plugin_dict.get("available"),
            }
        )
    return items


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _nested(value: Mapping[str, Any], *path: str) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _first_int(*values: Any) -> int:
    for value in values:
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def _count_by_status(items: list[Any], status: str) -> int:
    return sum(1 for item in items if str(_dict(item).get("status") or "").lower() == status)


def _latest_runs_by_spec(runs: list[Any]) -> dict[str, Mapping[str, Any]]:
    latest: dict[str, Mapping[str, Any]] = {}
    for run in runs:
        run_dict = _dict(run)
        spec_id = str(run_dict.get("spec_id") or run_dict.get("spec") or run_dict.get("run_id") or "").strip()
        if not spec_id or spec_id in latest:
            continue
        latest[spec_id] = run_dict
    return latest


def _count_ready_capabilities(registry: Mapping[str, Any]) -> int:
    capabilities = registry.get("capabilities")
    if isinstance(capabilities, Mapping):
        values = capabilities.values()
    elif isinstance(capabilities, list):
        values = capabilities
    else:
        return 0
    return sum(1 for item in values if _dict(item).get("status") in {"ready", "passed", "available"} or _dict(item).get("available") is True)


def _plugin_by_id(plugins: list[Mapping[str, Any]], plugin_id: str) -> dict[str, Any]:
    for plugin in plugins:
        plugin_dict = _dict(plugin)
        if plugin_dict.get("plugin_id") == plugin_id:
            return plugin_dict
    return {}


def _mapping_size(value: Any) -> int:
    return len(value) if isinstance(value, Mapping) else 0


def _list_size(value: Any) -> int:
    if isinstance(value, Mapping):
        return len(value)
    if isinstance(value, list):
        return len(value)
    return 0


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "ready", "passed"}
    return bool(value)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
