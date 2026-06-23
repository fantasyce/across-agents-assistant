from __future__ import annotations

import re
import time
from collections.abc import Iterable, Mapping
from collections import Counter
from typing import Any


REGISTRY_SCHEMA_VERSION = "across-unified-capability-registry/1.0"
REGISTRY_HEALTH_SCHEMA_VERSION = "across-unified-capability-registry-health/1.0"
AAA_PROVIDER_ID = "across-agents-assistant"
AUTOPILOT_PROVIDER_ID = "across-autopilot"

_AUTOPILOT_TOOL_PACK_IDS = {
    "trigger_ingestion",
    "continuous_self_iteration_plan",
    "loop_contract_validation",
    "runtime_policy_contract",
    "capability_preflight",
    "runtime_budget_enforcement",
    "git_repo_inspection",
    "repo_quality_inspection",
    "dependency_security_review",
    "license_policy_scan",
    "source_research_digest",
    "candidate_workspace",
    "model_target_admission",
    "model_generated_fallback_plan",
    "multi_candidate_comparison",
    "validation_harness",
    "candidate_diff_quality",
    "independent_review",
    "promotion_attestation",
    "evidence_integrity",
    "telemetry_rollup",
}


def build_unified_capability_registry(
    *,
    host_registry: Mapping[str, Any] | None = None,
    tool_schemas: Iterable[Mapping[str, Any]] | None = None,
    skill_catalog: Iterable[Mapping[str, Any]] | None = None,
    agent_configs: Mapping[str, Mapping[str, Any]] | None = None,
    active_agent: str | None = None,
    llm_config: Any | None = None,
    configured_provider_ids: Iterable[str] | None = None,
    plugins: Iterable[Mapping[str, Any]] | None = None,
    autopilot_capability_pack: Mapping[str, Any] | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    """Build a non-secret unified capability index across Across products.

    The registry is intentionally an indexing layer. It does not move execution
    ownership: AAA runtime tools still execute in AAA, and Autopilot Tool Packs
    still execute in Across Autopilot.
    """

    host_registry = dict(host_registry or {})
    agent_configs = dict(agent_configs or {})
    configured_provider_set = {
        str(provider_id)
        for provider_id in configured_provider_ids or []
        if str(provider_id or "").strip()
    }
    plugin_entries = [dict(plugin) for plugin in plugins or [] if isinstance(plugin, Mapping)]
    autopilot_pack = dict(autopilot_capability_pack or {})

    providers: list[dict[str, Any]] = [
        {
            "id": AAA_PROVIDER_ID,
            "kind": "host",
            "display_name": "Across Agents Assistant",
            "status": "available",
            "executor": AAA_PROVIDER_ID,
            "boundary": "host_runtime",
        }
    ]
    capabilities: list[dict[str, Any]] = []
    capability_ids: set[str] = set()

    for plugin in plugin_entries:
        plugin_id = _clean_text(plugin.get("plugin_id"))
        if not plugin_id:
            continue
        providers.append(
            {
                "id": plugin_id,
                "kind": "plugin",
                "display_name": _clean_text(plugin.get("display_name")) or plugin_id,
                "status": _clean_text(plugin.get("status")) or "unknown",
                "available": bool(plugin.get("available", False)),
                "installed": bool(plugin.get("installed", False)),
                "executor": plugin_id,
                "boundary": "plugin_runtime",
            }
        )
        _append_capability(
            capabilities,
            capability_ids,
            {
                "id": f"plugin.{_slug(plugin_id)}",
                "kind": "plugin",
                "owner": plugin_id,
                "provider": plugin_id,
                "executor": plugin_id,
                "display_name": _clean_text(plugin.get("display_name")) or plugin_id,
                "description": _clean_text(plugin.get("kind")),
                "status": _clean_text(plugin.get("status")) or "unknown",
                "risk_level": "medium",
                "boundary": "plugin_lifecycle",
                "user_callable": True,
                "loop_callable": bool(plugin.get("available", False)),
                "standalone_available": bool(plugin.get("available", False)),
                "requires_human_approval": False,
                "source_ref": "/api/plugins",
                "tags": ["plugin", _clean_text(plugin.get("kind"))],
            },
        )
        _append_plugin_capabilities(capabilities, capability_ids, plugin)

    for schema in tool_schemas or []:
        if not isinstance(schema, Mapping):
            continue
        name = _clean_text(schema.get("name"))
        if not name:
            continue
        risk = _normalize_risk(schema.get("risk_level"))
        _append_capability(
            capabilities,
            capability_ids,
            {
                "id": f"aaa.tool.{_slug(name)}",
                "kind": "tool",
                "owner": AAA_PROVIDER_ID,
                "provider": AAA_PROVIDER_ID,
                "executor": AAA_PROVIDER_ID,
                "name": name,
                "display_name": name,
                "description": _clean_text(schema.get("description")),
                "status": "available",
                "risk_level": risk,
                "boundary": "aaa_runtime_tool",
                "user_callable": True,
                "loop_callable": True,
                "standalone_available": True,
                "requires_human_approval": risk == "high",
                "source_ref": "/api/tools",
                "tags": ["tool"],
            },
        )

    for skill in skill_catalog or []:
        if not isinstance(skill, Mapping):
            continue
        skill_id = _clean_text(skill.get("id"))
        if not skill_id:
            continue
        _append_capability(
            capabilities,
            capability_ids,
            {
                "id": f"aaa.skill.{_slug(skill_id)}",
                "kind": "skill",
                "owner": AAA_PROVIDER_ID,
                "provider": AAA_PROVIDER_ID,
                "executor": "agent_prompt",
                "name": skill_id,
                "display_name": _clean_text(skill.get("name")) or skill_id,
                "description": _clean_text(skill.get("description")),
                "status": "available",
                "risk_level": "low",
                "boundary": "agent_profile_skill",
                "user_callable": False,
                "loop_callable": True,
                "standalone_available": False,
                "requires_human_approval": False,
                "source_ref": "/api/agent-capabilities",
                "tags": _clean_list(skill.get("tags")) or ["skill"],
            },
        )

    host_agents = [
        dict(agent)
        for agent in host_registry.get("agents", [])
        if isinstance(agent, Mapping)
    ]
    for agent in host_agents:
        agent_id = _clean_text(agent.get("agent_id"))
        if not agent_id:
            continue
        _append_capability(
            capabilities,
            capability_ids,
            {
                "id": f"aaa.agent.{_slug(agent_id)}",
                "kind": "agent",
                "owner": AAA_PROVIDER_ID,
                "provider": AAA_PROVIDER_ID,
                "executor": agent_id,
                "name": agent_id,
                "display_name": _clean_text(agent.get("display_name")) or agent_id,
                "description": _clean_text(agent.get("agent_type")),
                "status": "route_ready" if agent.get("capabilities") else "configured",
                "risk_level": "medium",
                "boundary": "agent_profile",
                "user_callable": True,
                "loop_callable": True,
                "standalone_available": True,
                "requires_human_approval": False,
                "source_ref": "/api/host/agent-capabilities",
                "tags": _clean_list(agent.get("capabilities")),
            },
        )

    models = _build_model_entries(
        llm_config=llm_config,
        agent_configs=agent_configs,
        configured_provider_ids=configured_provider_set,
        active_agent=active_agent,
    )
    for model in models:
        provider_id = model["provider"]
        if not any(provider.get("id") == provider_id for provider in providers):
            providers.append(
                {
                    "id": provider_id,
                    "kind": "model_provider",
                    "display_name": model.get("provider_display_name") or provider_id,
                    "status": "configured" if model.get("configured") else "not_configured",
                    "executor": "llm_gateway",
                    "boundary": "model_gateway",
                }
            )
        _append_capability(
            capabilities,
            capability_ids,
            {
                "id": f"aaa.model.{_slug(provider_id)}.{_slug(model['model'])}",
                "kind": "model",
                "owner": AAA_PROVIDER_ID,
                "provider": provider_id,
                "executor": "llm_gateway",
                "name": model["model"],
                "display_name": model.get("display_name") or model["model"],
                "description": model.get("provider_display_name"),
                "status": "configured" if model.get("configured") else "not_configured",
                "risk_level": "medium",
                "boundary": "model_selection",
                "user_callable": True,
                "loop_callable": True,
                "standalone_available": bool(model.get("configured")),
                "requires_human_approval": False,
                "source_ref": "/api/keys/status",
                "tags": ["model", provider_id],
            },
        )

    _append_autopilot_pack_capabilities(capabilities, capability_ids, autopilot_pack)

    kind_counts = dict(sorted(Counter(item.get("kind") or "unknown" for item in capabilities).items()))
    provider_counts = dict(sorted(Counter(item.get("provider") or "unknown" for item in capabilities).items()))
    return {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "owner": AAA_PROVIDER_ID,
        "generated_at": generated_at if generated_at is not None else time.time(),
        "security": {
            "secrets_included": False,
            "custom_instructions_included": False,
            "install_paths_included": False,
            "credential_fields_redacted": True,
            "execution_boundaries_preserved": True,
        },
        "integration_policy": {
            "unified_discovery_only": True,
            "frontend_pages_can_remain_separate": True,
            "frontend_page_boundaries": ["models", "capabilities", "mcp", "plugins", "tools", "settings"],
            "autopilot_remains_standalone_product": True,
        },
        "compatibility": {
            "schema_family": "across-unified-capability-registry",
            "schema_version": "1.0",
            "min_consumer_schema_version": "1.0",
            "compatible_with": ["across-autopilot-tool-pack-registry/1.0", "aaa-host-agent-capability-registry/1.0"],
            "required_fields": ["schema_version", "security", "providers", "capabilities", "models", "summary"],
        },
        "providers": _dedupe_by_id(providers),
        "capabilities": capabilities,
        "agents": host_agents,
        "models": models,
        "summary": {
            "provider_count": len(_dedupe_by_id(providers)),
            "capability_count": len(capabilities),
            "agent_count": len(host_agents),
            "model_count": len(models),
            "kind_counts": kind_counts,
            "provider_counts": provider_counts,
            "user_callable_count": sum(1 for item in capabilities if item.get("user_callable")),
            "loop_callable_count": sum(1 for item in capabilities if item.get("loop_callable")),
        },
    }


def evaluate_unified_capability_registry_health(registry: Mapping[str, Any]) -> dict[str, Any]:
    providers = _list_of_mappings(registry.get("providers"))
    capabilities = _list_of_mappings(registry.get("capabilities"))
    models = _list_of_mappings(registry.get("models"))
    provider_ids = {_clean_text(provider.get("id")) for provider in providers}
    capability_by_id = {
        _clean_text(capability.get("id")): capability
        for capability in capabilities
        if _clean_text(capability.get("id"))
    }
    fallback = capability_by_id.get("autopilot.tool_pack.model_generated_fallback_plan") or {}
    checks = [
        _health_check("schema_version", registry.get("schema_version") == REGISTRY_SCHEMA_VERSION),
        _health_check("non_secret", _dict(registry.get("security")).get("secrets_included") is False),
        _health_check("credential_redacted", _dict(registry.get("security")).get("credential_fields_redacted") is True),
        _health_check("boundaries_preserved", _dict(registry.get("security")).get("execution_boundaries_preserved") is True),
        _health_check("aaa_provider_present", AAA_PROVIDER_ID in provider_ids),
        _health_check("autopilot_provider_present", AUTOPILOT_PROVIDER_ID in provider_ids),
        _health_check("runtime_tool_present", any(capability.get("kind") == "tool" and capability.get("provider") == AAA_PROVIDER_ID for capability in capabilities)),
        _health_check("model_options_present", bool(models)),
        _health_check("autopilot_fallback_executor", fallback.get("executor") == AUTOPILOT_PROVIDER_ID),
        _health_check("autopilot_fallback_not_user_callable", fallback.get("user_callable") is False),
        _health_check("frontend_pages_separate", _dict(registry.get("integration_policy")).get("frontend_pages_can_remain_separate") is True),
    ]
    failed = [check for check in checks if check["status"] != "passed"]
    return {
        "schema_version": REGISTRY_HEALTH_SCHEMA_VERSION,
        "status": "passed" if not failed else "failed",
        "registry_schema_version": registry.get("schema_version"),
        "provider_count": len(providers),
        "capability_count": len(capabilities),
        "model_count": len(models),
        "checks": checks,
        "compatibility": _dict(registry.get("compatibility")),
    }


def _append_plugin_capabilities(
    capabilities: list[dict[str, Any]],
    capability_ids: set[str],
    plugin: Mapping[str, Any],
) -> None:
    plugin_id = _clean_text(plugin.get("plugin_id"))
    raw_capabilities = plugin.get("capabilities")
    if not plugin_id or not isinstance(raw_capabilities, Mapping):
        return
    for key, raw_value in sorted(raw_capabilities.items(), key=lambda item: str(item[0])):
        cap_id = _clean_text(key)
        if not cap_id:
            continue
        value = raw_value if isinstance(raw_value, Mapping) else {}
        _append_capability(
            capabilities,
            capability_ids,
            {
                "id": f"plugin.{_slug(plugin_id)}.capability.{_slug(cap_id)}",
                "kind": "plugin_capability",
                "owner": plugin_id,
                "provider": plugin_id,
                "executor": plugin_id,
                "name": cap_id,
                "display_name": _clean_text(value.get("name")) or cap_id,
                "description": _clean_text(value.get("description")),
                "status": "available" if plugin.get("available") else "unavailable",
                "risk_level": _normalize_risk(value.get("risk_level")),
                "boundary": "plugin_runtime",
                "user_callable": False,
                "loop_callable": bool(plugin.get("available", False)),
                "standalone_available": bool(plugin.get("available", False)),
                "requires_human_approval": False,
                "source_ref": "/api/plugins",
                "tags": ["plugin_capability", plugin_id],
            },
        )


def _append_autopilot_pack_capabilities(
    capabilities: list[dict[str, Any]],
    capability_ids: set[str],
    autopilot_pack: Mapping[str, Any],
) -> None:
    for item in autopilot_pack.get("ready", []) if isinstance(autopilot_pack, Mapping) else []:
        if not isinstance(item, Mapping):
            continue
        item_id = _clean_text(item.get("id"))
        if not item_id:
            continue
        executor = AUTOPILOT_PROVIDER_ID if item_id in _AUTOPILOT_TOOL_PACK_IDS else AAA_PROVIDER_ID
        kind = _pack_capability_kind(item)
        _append_capability(
            capabilities,
            capability_ids,
            {
                "id": f"autopilot.{kind}.{_slug(item_id)}",
                "kind": kind,
                "owner": executor,
                "provider": executor,
                "executor": executor,
                "name": item_id,
                "display_name": item_id,
                "description": _clean_text(item.get("layer")),
                "status": "ready",
                "risk_level": "medium",
                "boundary": _clean_text(item.get("form")) or "tool_pack",
                "user_callable": False,
                "loop_callable": True,
                "standalone_available": True,
                "requires_human_approval": False,
                "source_ref": "/api/autopilot/capability-packs",
                "entrypoint": _clean_text(item.get("entrypoint")),
                "reusable_by": _clean_list(item.get("reusable_by")),
                "tags": ["loop_engineering", _clean_text(item.get("layer"))],
            },
        )

    for item in autopilot_pack.get("skill_candidates", []) if isinstance(autopilot_pack, Mapping) else []:
        if not isinstance(item, Mapping):
            continue
        item_id = _clean_text(item.get("id"))
        if not item_id:
            continue
        _append_capability(
            capabilities,
            capability_ids,
            {
                "id": f"autopilot.skill_candidate.{_slug(item_id)}",
                "kind": "skill_candidate",
                "owner": AAA_PROVIDER_ID,
                "provider": AAA_PROVIDER_ID,
                "executor": "human_or_model_design",
                "name": item_id,
                "display_name": item_id,
                "description": _clean_text(item.get("why")),
                "status": "candidate",
                "risk_level": "low",
                "boundary": "not_executable_until_solidified",
                "user_callable": False,
                "loop_callable": False,
                "standalone_available": False,
                "requires_human_approval": False,
                "source_ref": "/api/autopilot/capability-packs",
                "tags": ["skill_candidate"],
            },
        )

    for item in autopilot_pack.get("validation_only", []) if isinstance(autopilot_pack, Mapping) else []:
        if not isinstance(item, Mapping):
            continue
        item_id = _clean_text(item.get("id"))
        if not item_id:
            continue
        _append_capability(
            capabilities,
            capability_ids,
            {
                "id": f"autopilot.validation_only.{_slug(item_id)}",
                "kind": "validation_only",
                "owner": AAA_PROVIDER_ID,
                "provider": AAA_PROVIDER_ID,
                "executor": "frontend_validation",
                "name": item_id,
                "display_name": item_id,
                "description": _clean_text(item.get("why")),
                "status": "validation_only",
                "risk_level": "low",
                "boundary": "not_product_capability",
                "user_callable": False,
                "loop_callable": False,
                "standalone_available": False,
                "requires_human_approval": False,
                "source_ref": "/api/autopilot/capability-packs",
                "tags": ["validation_only"],
            },
        )


def _build_model_entries(
    *,
    llm_config: Any | None,
    agent_configs: Mapping[str, Mapping[str, Any]],
    configured_provider_ids: set[str],
    active_agent: str | None,
) -> list[dict[str, Any]]:
    providers = list(getattr(llm_config, "providers", []) or [])
    entries: list[dict[str, Any]] = []
    for provider in providers:
        provider_id = _clean_text(getattr(provider, "provider_id", ""))
        if not provider_id:
            continue
        selected_model = _clean_text((agent_configs.get(provider_id) or {}).get("model"))
        provider_name = _clean_text(getattr(provider, "name", "")) or provider_id
        for model in list(getattr(provider, "models", []) or []):
            model_id = _clean_text(getattr(model, "model_id", ""))
            if not model_id:
                continue
            entries.append(
                {
                    "id": f"{provider_id}:{model_id}",
                    "provider": provider_id,
                    "provider_display_name": provider_name,
                    "model": model_id,
                    "display_name": _clean_text(getattr(model, "name", "")) or model_id,
                    "configured": provider_id in configured_provider_ids,
                    "selected_for_agent": selected_model == model_id,
                    "active_agent": active_agent == provider_id,
                    "selectable": True,
                    "supports_vision": bool(getattr(model, "supports_vision", False)),
                    "supports_function_calling": bool(getattr(model, "supports_function_calling", False)),
                    "max_tokens": int(getattr(model, "max_tokens", 0) or 0),
                }
            )
    return entries


def _append_capability(
    capabilities: list[dict[str, Any]],
    capability_ids: set[str],
    item: dict[str, Any],
) -> None:
    cap_id = _clean_text(item.get("id"))
    if not cap_id or cap_id in capability_ids:
        return
    cleaned = {
        key: value
        for key, value in item.items()
        if value is not None and value != "" and value != []
    }
    capability_ids.add(cap_id)
    capabilities.append(cleaned)


def _pack_capability_kind(item: Mapping[str, Any]) -> str:
    form = _clean_text(item.get("form")).lower()
    item_id = _clean_text(item.get("id"))
    if "tool_pack" in form or item_id in _AUTOPILOT_TOOL_PACK_IDS:
        return "tool_pack"
    if form.startswith("fixed_script"):
        return "fixed_script"
    if form == "api_registry":
        return "registry"
    if "host_model" in form:
        return "tool_pack"
    if form in {"cli_mcp_tool", "tool_pack_cli_mcp"}:
        return "tool"
    if form == "promotion_output":
        return "artifact"
    return "capability"


def _dedupe_by_id(items: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        item_id = _clean_text(item.get("id")) if isinstance(item, Mapping) else ""
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        result.append(dict(item))
    return result


def _normalize_risk(value: Any) -> str:
    risk = _clean_text(value).lower()
    return risk if risk in {"low", "medium", "high"} else "unknown"


def _health_check(id_: str, passed: bool) -> dict[str, str]:
    return {"id": id_, "status": "passed" if passed else "failed"}


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _clean_list(value: Any) -> list[str]:
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes, Mapping)):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _clean_text(item)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    return re.sub(r"\s+", " ", text)[:2000]


def _slug(value: Any) -> str:
    text = _clean_text(value).lower()
    text = re.sub(r"[^a-z0-9_.-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_.-")
    return text or "unknown"
