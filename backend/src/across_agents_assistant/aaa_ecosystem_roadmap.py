from __future__ import annotations

import time
from collections import Counter
from collections.abc import Mapping
from typing import Any


ECOSYSTEM_ROADMAP_SCHEMA_VERSION = "across-aaa-ecosystem-roadmap/1.0"

ROUTE_ENDPOINTS: dict[str, str] = {
    "roadmap": "/api/ecosystem/roadmap",
    "protocol_gateway": "/api/ecosystem/protocol-gateway",
    "tool_pack_registry": "/api/ecosystem/tool-packs",
    "trust_sandbox": "/api/ecosystem/trust-sandbox",
    "evaluation_telemetry": "/api/ecosystem/evaluation-telemetry",
    "context_packs": "/api/ecosystem/context-packs",
    "external_agents": "/api/ecosystem/external-agents",
    "agent_plugin_runtime": "/api/ecosystem/agent-plugins",
    "agent_cards": "/api/agent-cards",
    "mcp_safety": "/api/mcp/safety",
    "capability_registry": "/api/capability-registry",
    "capability_registry_health": "/api/capability-registry/health",
    "release_evaluation": "/api/release/evaluation",
    "autopilot_telemetry": "/api/autopilot/telemetry",
    "autopilot_ops": "/api/autopilot/ops-dashboard",
    "memory_pending": "/api/memory/memories?status=pending",
    "memory_metrics": "/api/memory/agent-loop-metrics",
}


def build_aaa_ecosystem_roadmap(
    *,
    plugins: list[Mapping[str, Any]] | None = None,
    capability_registry: Mapping[str, Any] | None = None,
    registry_health: Mapping[str, Any] | None = None,
    agent_cards: Mapping[str, Any] | None = None,
    mcp_safety: Mapping[str, Any] | None = None,
    autopilot_registry: Mapping[str, Any] | None = None,
    autopilot_runs: Mapping[str, Any] | None = None,
    autopilot_telemetry: Mapping[str, Any] | None = None,
    ops_dashboard: Mapping[str, Any] | None = None,
    release_evaluation: Mapping[str, Any] | None = None,
    memory_metrics: Mapping[str, Any] | None = None,
    pending_memories: list[Mapping[str, Any]] | None = None,
    agent_plugin_runtime: Mapping[str, Any] | None = None,
    agent_interop_e2e: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    plugins_list = [_dict(item) for item in plugins or []]
    capability_registry = _dict(capability_registry)
    registry_health = _dict(registry_health)
    agent_cards = _dict(agent_cards)
    mcp_safety = _dict(mcp_safety)
    autopilot_registry = _dict(autopilot_registry)
    autopilot_runs = _dict(autopilot_runs)
    autopilot_telemetry = _dict(autopilot_telemetry)
    ops_dashboard = _dict(ops_dashboard)
    release_evaluation = _dict(release_evaluation)
    memory_metrics = _dict(memory_metrics)
    pending_memories_list = [_dict(item) for item in pending_memories or []]
    agent_plugin_runtime = _dict(agent_plugin_runtime)
    agent_interop_e2e = _dict(agent_interop_e2e)

    sections = {
        "protocol_gateway": _protocol_gateway_section(
            plugins=plugins_list,
            capability_registry=capability_registry,
            registry_health=registry_health,
            agent_cards=agent_cards,
            autopilot_registry=autopilot_registry,
            memory_metrics=memory_metrics,
            mcp_safety=mcp_safety,
            agent_plugin_runtime=agent_plugin_runtime,
        ),
        "tool_pack_registry": _tool_pack_registry_section(
            capability_registry=capability_registry,
            registry_health=registry_health,
            ops_dashboard=ops_dashboard,
        ),
        "trust_sandbox": _trust_sandbox_section(
            registry_health=registry_health,
            mcp_safety=mcp_safety,
            ops_dashboard=ops_dashboard,
            agent_plugin_runtime=agent_plugin_runtime,
        ),
        "evaluation_telemetry": _evaluation_telemetry_section(
            autopilot_runs=autopilot_runs,
            autopilot_telemetry=autopilot_telemetry,
            ops_dashboard=ops_dashboard,
            release_evaluation=release_evaluation,
            agent_interop_e2e=agent_interop_e2e,
        ),
        "context_packs": _context_packs_section(
            memory_metrics=memory_metrics,
            pending_memories=pending_memories_list,
            agent_plugin_runtime=agent_plugin_runtime,
        ),
        "external_agents": _external_agents_section(
            plugins=plugins_list,
            agent_cards=agent_cards,
            capability_registry=capability_registry,
            agent_plugin_runtime=agent_plugin_runtime,
        ),
        "agent_plugin_runtime": _agent_plugin_runtime_section(
            agent_plugin_runtime=agent_plugin_runtime,
        ),
    }
    failed = [section for section in sections.values() if section["status"] == "failed"]
    attention = [section for section in sections.values() if section["status"] in {"attention", "unavailable", "unknown"}]
    status = "failed" if failed else "attention" if attention else "passed"
    actions = _actions(sections)
    return {
        "schema_version": ECOSYSTEM_ROADMAP_SCHEMA_VERSION,
        "status": status,
        "generated_at": generated_at or _now(),
        "summary": {
            "route_count": len(sections),
            "ready_route_count": sum(1 for section in sections.values() if section["status"] == "passed"),
            "attention_route_count": len(attention),
            "failed_route_count": len(failed),
            "action_count": len(actions),
        },
        "sections": sections,
        "actions": actions,
        "endpoints": dict(ROUTE_ENDPOINTS),
    }


def ecosystem_route_section(roadmap: Mapping[str, Any], route_id: str) -> dict[str, Any]:
    sections = _dict(roadmap.get("sections"))
    section = _dict(sections.get(route_id))
    if section:
        return section
    return _section(
        route_id,
        route_id.replace("_", " ").title(),
        "failed",
        {"reason": "unknown route"},
        [],
        ROUTE_ENDPOINTS.get(route_id),
    )


def _protocol_gateway_section(
    *,
    plugins: list[Mapping[str, Any]],
    capability_registry: Mapping[str, Any],
    registry_health: Mapping[str, Any],
    agent_cards: Mapping[str, Any],
    autopilot_registry: Mapping[str, Any],
    memory_metrics: Mapping[str, Any],
    mcp_safety: Mapping[str, Any],
    agent_plugin_runtime: Mapping[str, Any],
) -> dict[str, Any]:
    plugin_ids = {str(item.get("plugin_id") or "") for item in plugins}
    cards = _list(agent_cards.get("cards"))
    adapters = [
        _adapter("agent_cards", "A2A-like Agent Cards", bool(cards), ROUTE_ENDPOINTS["agent_cards"]),
        _adapter("capability_registry", "Unified Capability Registry", bool(capability_registry), ROUTE_ENDPOINTS["capability_registry"]),
        _adapter("orchestrator", "Across Orchestrator Agent Loop", "across-orchestrator" in plugin_ids, "/api/orchestrator/loops"),
        _adapter("autopilot", "Across Autopilot LoopSpec", bool(autopilot_registry) or "across-autopilot" in plugin_ids, "/api/autopilot/runs"),
        _adapter("context", "Across Context Memory", bool(memory_metrics) or "across-context" in plugin_ids, ROUTE_ENDPOINTS["memory_pending"]),
        _adapter("mcp", "MCP Safety Surface", bool(mcp_safety), ROUTE_ENDPOINTS["mcp_safety"]),
        _adapter(
            "agent_plugin_runtime",
            "Generic Agent Plugin Runtime",
            str(agent_plugin_runtime.get("status") or "") in {"passed", "attention"},
            ROUTE_ENDPOINTS["agent_plugin_runtime"],
        ),
    ]
    ready_count = sum(1 for item in adapters if item["status"] == "passed")
    required_ready = sum(1 for item in adapters if item["id"] != "mcp" and item["status"] == "passed")
    status = "passed" if required_ready >= 5 and registry_health.get("status") in {"passed", None} else "attention"
    return _section(
        "protocol_gateway",
        "Protocol Gateway",
        status,
        {
            "adapter_count": len(adapters),
            "ready_adapter_count": ready_count,
            "agent_card_count": len(cards),
            "registry_health_status": registry_health.get("status") or "unknown",
            "agent_plugin_downstream_status": agent_plugin_runtime.get("status") or "unknown",
        },
        adapters,
        ROUTE_ENDPOINTS["protocol_gateway"],
    )


def _tool_pack_registry_section(
    *,
    capability_registry: Mapping[str, Any],
    registry_health: Mapping[str, Any],
    ops_dashboard: Mapping[str, Any],
) -> dict[str, Any]:
    tool_packs = [
        item
        for item in _capabilities(capability_registry)
        if str(item.get("kind") or "").lower() == "tool_pack" or "tool_pack" in str(item.get("id") or "")
    ]
    ready = [
        item
        for item in tool_packs
        if item.get("available") is True or str(item.get("status") or "") in {"available", "ready", "passed"}
    ]
    status = "passed" if len(ready) >= 10 and registry_health.get("status") == "passed" else "attention"
    return _section(
        "tool_pack_registry",
        "Tool Pack Registry",
        status,
        {
            "tool_pack_count": len(tool_packs),
            "ready_tool_pack_count": len(ready),
            "required_floor": 10,
            "ops_capability_ready_count": _nested(ops_dashboard, "summary", "capability_ready_count"),
        },
        [_tool_pack_item(item) for item in tool_packs[:12]],
        ROUTE_ENDPOINTS["tool_pack_registry"],
    )


def _trust_sandbox_section(
    *,
    registry_health: Mapping[str, Any],
    mcp_safety: Mapping[str, Any],
    ops_dashboard: Mapping[str, Any],
    agent_plugin_runtime: Mapping[str, Any],
) -> dict[str, Any]:
    checks = [
        _check("credential_redaction", registry_health.get("status") == "passed", "Unified registry health includes non-secret and credential-redaction checks."),
        _check("human_promotion_gate", True, "Promotion review keeps merge, release, tag, and signing blocked until human approval."),
        _check("tool_permissions_endpoint", True, "Host tool permission and MCP safety endpoints expose bounded risk metadata."),
        _check("ops_gate_visibility", bool(ops_dashboard), "Ops dashboard is available for trigger, capability, and self-iteration gate visibility."),
        _check("mcp_safety_report", bool(mcp_safety), "MCP safety report is available when MCP contexts are configured."),
        _check("agent_plugin_trust_policy", bool(agent_plugin_runtime), "Generic agent plugin runtime reports trust policy, mutation boundary, and approval status."),
    ]
    failed_required = [item for item in checks[:4] if item["status"] != "passed"]
    # MCP and generic Agent plugins are optional integrations. Their absence is
    # visible in the item list but must not downgrade the required trust gates.
    status = "failed" if failed_required else "passed"
    return _section(
        "trust_sandbox",
        "Trust And Sandbox",
        status,
        {
            "required_check_count": 4,
            "passed_check_count": sum(1 for item in checks if item["status"] == "passed"),
            "promotion_merge_blocked": True,
            "release_signing_blocked": True,
        },
        checks,
        ROUTE_ENDPOINTS["trust_sandbox"],
    )


def _evaluation_telemetry_section(
    *,
    autopilot_runs: Mapping[str, Any],
    autopilot_telemetry: Mapping[str, Any],
    ops_dashboard: Mapping[str, Any],
    release_evaluation: Mapping[str, Any],
    agent_interop_e2e: Mapping[str, Any],
) -> dict[str, Any]:
    run_count = _first_int(autopilot_runs.get("run_count"), _nested(autopilot_telemetry, "runs", "total"), len(_list(autopilot_runs.get("runs"))))
    recent_runs = _list(autopilot_runs.get("runs"))
    latest_runs = _latest_runs_by_spec(recent_runs)
    historical_failed = _first_int(_nested(autopilot_telemetry, "runs", "failed"), _nested(autopilot_telemetry, "by_status", "failed"))
    latest_failed = _count_by_status(list(latest_runs.values()), "failed") if latest_runs else historical_failed
    ops_summary = _dict(ops_dashboard.get("summary"))
    failed = _first_int(ops_summary.get("current_failed"), ops_summary.get("failed"), latest_failed)
    resolved_failed = _first_int(ops_summary.get("resolved_failed"), max(latest_failed - failed, 0))
    readiness = str(release_evaluation.get("release_readiness") or "unknown")
    ops_status = str(ops_dashboard.get("status") or "unknown")
    evaluated = _first_int(release_evaluation.get("evaluated_task_count"))
    agent_interop_status = str(agent_interop_e2e.get("status") or "not_run")
    agent_interop_failed = _first_int(_nested(agent_interop_e2e, "summary", "failed_count"))
    interop_evidence_ready = agent_interop_status == "passed" and agent_interop_failed == 0
    release_evidence_ready = readiness in {"ready", "passed"} and evaluated > 0
    status = (
        "failed"
        if ops_status == "failed"
        else "attention"
        if failed or readiness == "blocked" or (run_count > 0 and not (release_evidence_ready or interop_evidence_ready))
        else "passed"
    )
    items = [
        {"id": "autopilot_runs", "status": "passed" if failed == 0 else "attention", "run_count": run_count, "failed": failed, "historical_failed": historical_failed, "latest_failed": latest_failed, "resolved_failed": resolved_failed, "endpoint": ROUTE_ENDPOINTS["autopilot_telemetry"]},
        {"id": "ops_dashboard", "status": ops_status, "endpoint": ROUTE_ENDPOINTS["autopilot_ops"]},
        {"id": "release_evaluation", "status": readiness, "evaluated_task_count": evaluated, "endpoint": ROUTE_ENDPOINTS["release_evaluation"]},
        {
            "id": "agent_interop_e2e",
            "status": agent_interop_status,
            "failed_count": agent_interop_failed,
            "endpoint": "/api/autopilot/agent-interop-e2e",
        },
    ]
    return _section(
        "evaluation_telemetry",
        "Eval And Telemetry",
        status,
        {
            "run_count": run_count,
            "failed_run_count": failed,
            "historical_failed_run_count": historical_failed,
            "latest_failed_run_count": latest_failed,
            "resolved_failed_run_count": resolved_failed,
            "ops_status": ops_status,
            "release_readiness": readiness,
            "evaluated_task_count": evaluated,
            "agent_interop_e2e_status": agent_interop_status,
        },
        items,
        ROUTE_ENDPOINTS["evaluation_telemetry"],
    )


def _context_packs_section(
    *,
    memory_metrics: Mapping[str, Any],
    pending_memories: list[Mapping[str, Any]],
    agent_plugin_runtime: Mapping[str, Any],
) -> dict[str, Any]:
    totals = _dict(memory_metrics.get("totals"))
    downstream_section = _dict(_nested(agent_plugin_runtime, "sections", "context_agent_packs"))
    downstream_context = _dict(downstream_section.get("summary"))
    downstream_items = _list(downstream_section.get("items"))
    pending_count = _first_int(totals.get("pending_count"), len(pending_memories))
    candidate_count = _first_int(totals.get("candidate_count"), len(pending_memories))
    groups = _memory_groups(pending_memories)
    items = [*groups]
    existing_ids = {str(item.get("id")) for item in items}
    for pack in downstream_items[:8]:
        pack_dict = _dict(pack)
        pack_id = str(pack_dict.get("id") or "")
        if not pack_id or pack_id in existing_ids:
            continue
        items.append(
            {
                "id": pack_id,
                "scope": pack_dict.get("scope"),
                "type": pack_dict.get("type"),
                "status": pack_dict.get("status") or "unknown",
                "count": _first_int(pack_dict.get("count")),
                "agent_plugin_id": pack_dict.get("agent_plugin_id"),
                "virtual": bool(pack_dict.get("virtual")),
                "ready_for_agent_loading": bool(pack_dict.get("ready_for_agent_loading")),
            }
        )
    status = "attention" if pending_count else "passed" if (memory_metrics or pending_memories or downstream_context or downstream_items) else "unavailable"
    return _section(
        "context_packs",
        "Context Pack / Memory OS",
        status,
        {
            "candidate_count": candidate_count,
            "pending_count": pending_count,
            "approved_count": _first_int(totals.get("approved_count")),
            "context_pack_count": _first_int(downstream_context.get("context_pack_count"), len(groups)),
            "agent_plugin_count": _first_int(downstream_context.get("agent_plugin_count")),
        },
        items,
        ROUTE_ENDPOINTS["context_packs"],
    )


def _external_agents_section(
    *,
    plugins: list[Mapping[str, Any]],
    agent_cards: Mapping[str, Any],
    capability_registry: Mapping[str, Any],
    agent_plugin_runtime: Mapping[str, Any],
) -> dict[str, Any]:
    cards = _list(agent_cards.get("cards"))
    providers = _list(capability_registry.get("providers"))
    available_plugins = [item for item in plugins if item.get("available") is True]
    downstream = _dict(_nested(agent_plugin_runtime, "sections", "orchestrator_external_agents"))
    downstream_items = _list(downstream.get("items"))
    status = "passed" if (cards and available_plugins) or downstream_items else "attention"
    items = [
        {
            "id": str(card.get("agent_id") or card.get("id") or ""),
            "name": card.get("name") or card.get("display_name"),
            "status": "passed",
            "capability_count": len(_list(card.get("capabilities"))),
            "endpoint": ROUTE_ENDPOINTS["agent_cards"],
        }
        for card in cards[:8]
        if isinstance(card, Mapping)
    ]
    for item in downstream_items[:8]:
        item_dict = _dict(item)
        if any(existing.get("id") == item_dict.get("id") for existing in items):
            continue
        items.append(
            {
                "id": item_dict.get("id"),
                "name": item_dict.get("name"),
                "status": item_dict.get("status") or "unknown",
                "capability_count": None,
                "endpoint": ROUTE_ENDPOINTS["agent_plugin_runtime"],
                "mutation_boundary": item_dict.get("mutation_boundary"),
            }
        )
    return _section(
        "external_agents",
        "External Agent Ecosystem",
        status,
        {
            "agent_card_count": len(cards),
            "provider_count": len(providers),
            "available_plugin_count": len(available_plugins),
            "registered_external_agent_count": _first_int(_nested(downstream, "summary", "agent_count"), len(downstream_items)),
        },
        items,
        ROUTE_ENDPOINTS["external_agents"],
    )


def _agent_plugin_runtime_section(*, agent_plugin_runtime: Mapping[str, Any]) -> dict[str, Any]:
    summary = _dict(agent_plugin_runtime.get("summary"))
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
    return _section(
        "agent_plugin_runtime",
        "Generic Agent Plugin Runtime",
        str(agent_plugin_runtime.get("status") or "unavailable"),
        {
            "downstream_count": _first_int(summary.get("downstream_count")),
            "downstream_ready_count": _first_int(summary.get("downstream_ready_count")),
            "agent_plugin_count": _first_int(summary.get("agent_plugin_count")),
            "external_agent_count": _first_int(summary.get("external_agent_count")),
            "ready_agent_plugin_count": _first_int(summary.get("ready_agent_plugin_count")),
            "context_pack_count": _first_int(summary.get("context_pack_count")),
        },
        items,
        ROUTE_ENDPOINTS["agent_plugin_runtime"],
    )


def _actions(sections: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for route_id, section in sections.items():
        status = str(section.get("status") or "unknown")
        if status == "passed":
            continue
        priority = "high" if status == "failed" else "medium"
        actions.append(
            {
                "id": f"advance_{route_id}",
                "priority": priority,
                "title": f"Advance {str(section.get('title') or route_id)}",
                "reason": f"{str(section.get('title') or route_id)} is {status}.",
                "endpoint": section.get("endpoint"),
            }
        )
    return actions[:8]


def _section(
    section_id: str,
    title: str,
    status: str,
    summary: Mapping[str, Any],
    items: list[Any],
    endpoint: str | None,
) -> dict[str, Any]:
    return {
        "id": section_id,
        "title": title,
        "status": status,
        "summary": dict(summary),
        "items": list(items)[:12],
        "endpoint": endpoint,
    }


def _adapter(adapter_id: str, title: str, ready: bool, endpoint: str) -> dict[str, Any]:
    return {
        "id": adapter_id,
        "title": title,
        "status": "passed" if ready else "attention",
        "endpoint": endpoint,
    }


def _tool_pack_item(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "display_name": item.get("display_name") or item.get("name"),
        "status": item.get("status") or ("ready" if item.get("available") else "unknown"),
        "provider": item.get("provider"),
        "executor": item.get("executor"),
        "requires_human_approval": item.get("requires_human_approval"),
        "source_ref": item.get("source_ref"),
    }


def _check(check_id: str, passed: bool, label: str) -> dict[str, Any]:
    return {"id": check_id, "status": "passed" if passed else "attention", "label": label}


def _memory_groups(pending_memories: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[tuple[str, str, str]] = Counter()
    for item in pending_memories:
        counter[
            (
                str(item.get("scope") or "unknown"),
                str(item.get("type") or "note"),
                str(item.get("status") or "pending"),
            )
        ] += 1
    return [
        {
            "id": f"{scope}:{memory_type}:{status}",
            "scope": scope,
            "type": memory_type,
            "status": status,
            "count": count,
            "endpoint": ROUTE_ENDPOINTS["memory_pending"],
        }
        for (scope, memory_type, status), count in sorted(counter.items())
    ][:12]


def _capabilities(registry: Mapping[str, Any]) -> list[dict[str, Any]]:
    capabilities = registry.get("capabilities")
    if isinstance(capabilities, Mapping):
        values = capabilities.values()
    elif isinstance(capabilities, list):
        values = capabilities
    else:
        values = []
    return [_dict(item) for item in values]


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


def _latest_runs_by_spec(runs: list[Any]) -> dict[str, Mapping[str, Any]]:
    latest: dict[str, Mapping[str, Any]] = {}
    for run in runs:
        run_dict = _dict(run)
        spec_id = str(run_dict.get("spec_id") or run_dict.get("spec") or run_dict.get("run_id") or "").strip()
        if not spec_id or spec_id in latest:
            continue
        latest[spec_id] = run_dict
    return latest


def _count_by_status(items: list[Any], status: str) -> int:
    return sum(1 for item in items if str(_dict(item).get("status") or "").lower() == status)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
