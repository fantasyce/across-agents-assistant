"""Non-secret operational status for local CLI agents.

The host deliberately distinguishes installation readiness from account and
provider state.  Missing telemetry is reported as ``unknown`` instead of being
inferred from a successful executable probe.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Mapping, Optional


STATUS_SCHEMA_VERSION = "local-agent-operational-status/1.0"


def build_operational_status(
    agent_id: str,
    health: Mapping[str, Any],
    capability: Mapping[str, Any],
) -> Dict[str, Any]:
    """Return a strict, credential-free status snapshot for one agent."""
    model_id = _safe_text(health.get("configured_model"))
    provider_id = _safe_text(health.get("provider"))
    account = health.get("account") if isinstance(health.get("account"), Mapping) else {}
    auth = health.get("auth") if isinstance(health.get("auth"), Mapping) else {}
    usage = health.get("usage") if isinstance(health.get("usage"), Mapping) else {}
    rate_limit = health.get("rate_limit") if isinstance(health.get("rate_limit"), Mapping) else {}
    capabilities = _safe_string_list(capability.get("capabilities"))

    authenticated = auth.get("authenticated")
    if not isinstance(authenticated, bool):
        authenticated = None

    return {
        "schema_version": STATUS_SCHEMA_VERSION,
        "agent_id": agent_id,
        "display_name": _safe_text(health.get("display_name")) or agent_id,
        "transport": "local_cli",
        "runtime": {
            "status": "available" if health.get("available") is True else "unavailable",
            "found": health.get("found") is True,
            "available": health.get("available") is True,
            "version": _safe_text(health.get("version")),
        },
        "account": {
            "status": _known_status(account, ("id", "display_name")),
            "id": _safe_text(account.get("id")),
            "display_name": _safe_text(account.get("display_name")),
        },
        "auth": {
            "status": _enum_status(auth.get("status"), {"authenticated", "unauthenticated", "expired", "unknown"}),
            "authenticated": authenticated,
            "method": _safe_text(auth.get("method")),
        },
        "model": {
            "status": "configured" if model_id else "unknown",
            "id": model_id,
        },
        "provider": {
            "status": "known" if provider_id else "unknown",
            "id": provider_id,
        },
        "usage": {
            "status": _known_status(usage, ("input_tokens", "output_tokens", "total_tokens", "requests")),
            "window": _safe_text(usage.get("window")),
            "input_tokens": _nonnegative_int(usage.get("input_tokens")),
            "output_tokens": _nonnegative_int(usage.get("output_tokens")),
            "total_tokens": _nonnegative_int(usage.get("total_tokens")),
            "requests": _nonnegative_int(usage.get("requests")),
        },
        "rate_limit": {
            "status": _enum_status(rate_limit.get("status"), {"available", "limited", "exhausted", "unknown"}),
            "remaining": _nonnegative_int(rate_limit.get("remaining")),
            "limit": _nonnegative_int(rate_limit.get("limit")),
            "reset_at": _safe_text(rate_limit.get("reset_at")),
            "retry_after_seconds": _nonnegative_number(rate_limit.get("retry_after_seconds")),
        },
        "capability": {
            "status": "known" if capabilities else "unknown",
            "items": capabilities,
            "strict_tool_scope": bool(capability.get("strict_tool_scope", False)),
        },
        "security": {
            "credentials_included": False,
            "raw_probe_output_included": False,
        },
    }


def _known_status(value: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    explicit = _enum_status(value.get("status"), {"known", "unknown"})
    if explicit != "unknown":
        return explicit
    return "known" if any(value.get(key) is not None for key in keys) else "unknown"


def _enum_status(value: Any, allowed: set[str]) -> str:
    text = str(value or "").strip().lower()
    return text if text in allowed else "unknown"


def _safe_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    lowered = text.lower()
    if (
        not text
        or len(text) > 200
        or any(marker in lowered for marker in ("token", "secret", "password", "bearer ", "private key"))
        or re.search(r"\b(?:sk-|ghp_|github_pat_|glpat-)[A-Za-z0-9_-]{6,}", text, re.IGNORECASE)
    ):
        return None
    return text


def _safe_string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    result: list[str] = []
    for item in value:
        text = _safe_text(item)
        if text and text not in result:
            result.append(text)
        if len(result) >= 200:
            break
    return result


def _nonnegative_int(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _nonnegative_number(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
        return float(value)
    return None
