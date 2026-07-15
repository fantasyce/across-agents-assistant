from __future__ import annotations

from collections import defaultdict
import re
from typing import Any, Mapping, Sequence


PLAN_SCHEMA_VERSION = "across-task-capability-plan/1.0"

_MANAGED_CAPABILITIES = {
    "across-context": ("context_retrieval", "memory"),
    "across-orchestrator": ("task_execution", "quality_gates"),
    "across-autopilot": ("workflow_supervision", "repository_review"),
}
_CAPABILITY_TERMS = {
    "context_retrieval": ("context", "memory", "history", "recall"),
    "memory": ("memory", "remember", "context"),
    "task_execution": ("build", "implement", "fix", "test", "code", "task"),
    "quality_gates": ("quality", "test", "release", "verify", "readiness"),
    "workflow_supervision": ("workflow", "loop", "supervise", "automatic", "autonomous"),
    "repository_review": ("repository", "repo", "review", "release", "quality"),
}
_RISK_PERMISSION_TERMS = frozenset({"write", "execute", "network", "secret", "credential", "delete", "publish", "deploy"})
_MATERIAL_RISK_PATTERNS = (
    re.compile(r"\b(?:deploy|publish|promote|merge|sign)\b.{0,48}\b(?:production|public|remote|github|app\s*store|release|main)\b"),
    re.compile(r"\brelease\b.{0,32}\b(?:to|into|on)\b.{0,32}\b(?:production|public|remote|github|app\s*store)\b"),
    re.compile(r"\b(?:delete|remove|rotate|revoke)\b.{0,40}\b(?:data|files?|credentials?|secrets?|keys?|tokens?|deployment|production)\b"),
    re.compile(r"\b(?:payment|credential|secret|private\s*key|api\s*key)\b.{0,32}\b(?:write|change|use|send|expose|rotate|delete)\b"),
)


def build_task_capability_plan(
    *,
    user_goal: str,
    project_signals: Mapping[str, Any] | None,
    plugins: Sequence[Mapping[str, Any]],
    configured_providers: Sequence[str],
    primary_provider: str | None = None,
) -> dict[str, Any]:
    goal = str(user_goal or "").strip()
    if not goal:
        raise ValueError("A user goal is required")
    signals = dict(project_signals or {})
    goal_terms = set(re.findall(r"[a-z0-9_]+", goal.lower()))
    requested = _strings(signals.get("required_capabilities"))

    candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for plugin in plugins:
        health = plugin.get("health") if isinstance(plugin.get("health"), Mapping) else {}
        health_status = str(health.get("status") or "").lower()
        if (
            not bool(plugin.get("integrity_ok", True))
            or not bool(plugin.get("installed", True))
            or plugin.get("available") is False
            or health_status in {"failed", "unhealthy", "unavailable"}
        ):
            continue
        for capability in _plugin_capabilities(plugin):
            candidates[capability].append(_capability_choice(plugin, capability))

    required = requested or _infer_required_capabilities(goal_terms, candidates)
    chosen: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    for capability in required:
        choices = sorted(candidates.get(capability, []), key=lambda choice: (*_choice_rank(choice), str(choice["plugin_id"])))
        if not choices:
            decisions.append({
                "id": f"provide_{capability}",
                "kind": "missing_capability",
                "prompt": f"Choose how to provide the required {capability} capability.",
                "options": [],
                "required": True,
            })
            continue
        best_rank = _choice_rank(choices[0])
        tied = [choice for choice in choices if _choice_rank(choice) == best_rank]
        if len(tied) > 1:
            decisions.append({
                "id": f"select_{capability}_provider",
                "kind": "ambiguous_capability",
                "prompt": f"Select the provider for {capability}.",
                "options": [choice["plugin_id"] for choice in tied],
                "required": True,
            })
            continue
        chosen.append(choices[0])

    provider_ids = _dedupe(list(configured_providers))
    preferred_provider = str(signals.get("preferred_provider") or primary_provider or "").strip()
    chosen_providers = ([preferred_provider] if preferred_provider in provider_ids else provider_ids[:1])
    if not chosen_providers:
        decisions.append({
            "id": "configure_model_provider",
            "kind": "missing_provider",
            "prompt": "Configure a model provider for this task.",
            "options": [],
            "required": True,
        })

    risky = [choice for choice in chosen if _is_risky_choice(choice, goal)]
    if risky:
        decisions.append({
            "id": "approve_risky_capabilities",
            "kind": "risk_approval",
            "prompt": "Approve the capabilities that can make consequential changes.",
            "options": _dedupe([choice["plugin_id"] for choice in risky]),
            "required": True,
        })

    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "goal": goal,
        "chosen_capabilities": chosen,
        "chosen_providers": chosen_providers,
        "hidden_defaults": {
            "provider_selection": "primary_then_first_configured",
            "capability_selection": "healthy_highest_trust_then_plugin_id",
            "approval_mode": "ask_only_for_material_risk_or_true_ambiguity",
        },
        "required_user_decisions": decisions,
        "automatic": not decisions,
    }


def _plugin_capabilities(plugin: Mapping[str, Any]) -> list[str]:
    raw = plugin.get("capabilities")
    values: list[str] = []
    if isinstance(raw, Mapping):
        values.extend(str(key) for key, enabled in raw.items() if enabled is not False and enabled is not None)
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, Mapping):
                value = item.get("id") or item.get("name")
            else:
                value = item
            if value:
                values.append(str(value))
    values.extend(_MANAGED_CAPABILITIES.get(str(plugin.get("plugin_id") or ""), ()))
    return _dedupe(_normalize_id(value) for value in values if value)


def _infer_required_capabilities(goal_terms: set[str], candidates: Mapping[str, list[dict[str, Any]]]) -> list[str]:
    matches: list[str] = []
    for capability in candidates:
        terms = set(_CAPABILITY_TERMS.get(capability, ())) | set(capability.split("_"))
        if goal_terms & terms:
            matches.append(capability)
    if matches:
        return sorted(matches)
    for fallback in ("task_execution", "workflow_supervision"):
        if fallback in candidates:
            return [fallback]
    return sorted(candidates)[:1]


def _capability_choice(plugin: Mapping[str, Any], capability: str) -> dict[str, Any]:
    trust = plugin.get("trust") if isinstance(plugin.get("trust"), Mapping) else {}
    permissions = plugin.get("permissions") if isinstance(plugin.get("permissions"), (Mapping, list)) else {}
    health = plugin.get("health") if isinstance(plugin.get("health"), Mapping) else {}
    return {
        "capability": capability,
        "plugin_id": str(plugin.get("plugin_id") or plugin.get("id") or ""),
        "display_name": str(plugin.get("display_name") or plugin.get("plugin_id") or ""),
        "trust": dict(trust),
        "permissions": permissions,
        "health": dict(health),
    }


def _choice_rank(choice: Mapping[str, Any]) -> tuple[int, int]:
    trust = choice.get("trust") if isinstance(choice.get("trust"), Mapping) else {}
    level = str(trust.get("level") or "unverified").lower()
    trust_rank = {"first_party": 0, "verified": 1, "trusted": 1, "local": 2, "unverified": 3}.get(level, 3)
    permissions = " ".join(_flatten_strings(choice.get("permissions"))).lower()
    risk_count = sum(term in permissions for term in _RISK_PERMISSION_TERMS)
    return trust_rank, risk_count


def _is_risky_choice(choice: Mapping[str, Any], goal: str) -> bool:
    if not any(pattern.search(goal.lower()) for pattern in _MATERIAL_RISK_PATTERNS):
        return False
    permissions = " ".join(_flatten_strings(choice.get("permissions"))).lower()
    return any(term in permissions for term in _RISK_PERMISSION_TERMS)


def _flatten_strings(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        result: list[str] = []
        for key, child in value.items():
            result.append(str(key))
            result.extend(_flatten_strings(child))
        return result
    if isinstance(value, list):
        result = []
        for child in value:
            result.extend(_flatten_strings(child))
        return result
    return [str(value)]


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _dedupe(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
