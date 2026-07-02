from __future__ import annotations

from collections.abc import Iterable, Mapping, MutableMapping
from typing import Any
import re


AI_READY_CONTEXT_SCHEMA = "across-aaa-ai-ready-context/1.0"
DEFAULT_MAX_ITEMS_PER_CATEGORY = 3
DEFAULT_MAX_SUMMARY_CHARS = 280


_FIELD_PRIORITY: tuple[str, ...] = (
    "title",
    "summary",
    "goal",
    "rationale",
    "reason",
    "description",
    "excerpt",
    "path",
    "source_id",
    "id",
)

_SENSITIVE_FIELD_NAMES = {
    "content",
    "raw",
    "raw_text",
    "transcript",
    "prompt",
    "hidden_reasoning",
    "secret",
    "token",
    "password",
    "api_key",
    "apikey",
    "credential",
}

_CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "security_policy",
        (
            "approval",
            "audience",
            "credential",
            "oauth",
            "permission",
            "policy",
            "redact",
            "sandbox",
            "secret",
            "token",
        ),
    ),
    (
        "architecture",
        (
            "a2a",
            "adapter",
            "ag-ui",
            "api",
            "architecture",
            "boundary",
            "capability",
            "contract",
            "integration",
            "mcp",
            "otel",
            "plugin",
            "protocol",
            "skill",
        ),
    ),
    (
        "validation",
        (
            "check",
            "ci",
            "e2e",
            "evidence",
            "failure",
            "gate",
            "quality",
            "release",
            "repair",
            "test",
            "validation",
        ),
    ),
    (
        "user_experience",
        (
            "card",
            "docs",
            "evidence center",
            "onboarding",
            "setup",
            "task detail",
            "ui",
            "user",
            "workbench",
        ),
    ),
    (
        "operations",
        (
            "daemon",
            "health",
            "latency",
            "memory",
            "metrics",
            "queue",
            "retry",
            "scheduler",
            "telemetry",
            "trigger",
        ),
    ),
)

_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"), "[redacted-secret]"),
    (re.compile(r"\bghp_[A-Za-z0-9_]{8,}\b"), "[redacted-secret]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{8,}\b"), "[redacted-secret]"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}\b", re.IGNORECASE), "Bearer [redacted-secret]"),
    (
        re.compile(
            r"\b(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s,;]+",
            re.IGNORECASE,
        ),
        r"\1=[redacted-secret]",
    ),
    (re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"), "[redacted-email]"),
    (re.compile(r"/Users/[^/\s]+(?:/[^\s,;:]+)+"), "[redacted-local-path]"),
)


def synthesize_ai_ready_context(
    source_signals: Any = None,
    *,
    max_items_per_category: int = DEFAULT_MAX_ITEMS_PER_CATEGORY,
    max_summary_chars: int = DEFAULT_MAX_SUMMARY_CHARS,
) -> dict[str, Any]:
    """Convert source signals into a bounded, redacted context block."""

    categories = {category: [] for category, _ in _CATEGORY_KEYWORDS}
    categories["uncategorized"] = []
    counts = {category: 0 for category in categories}

    source_count = 0
    for index, signal in enumerate(_iter_signal_items(source_signals), start=1):
        source_count += 1
        summary = summarize_source_signal(signal, max_chars=max_summary_chars)
        category = classify_source_signal(signal)
        counts[category] = counts.get(category, 0) + 1
        if len(categories.setdefault(category, [])) < max_items_per_category:
            categories[category].append(
                {
                    "index": index,
                    "category": category,
                    "summary": summary,
                }
            )

    primary_category = _primary_category(counts)
    return {
        "schema_version": AI_READY_CONTEXT_SCHEMA,
        "source_count": source_count,
        "primary_category": primary_category,
        "category_counts": {key: value for key, value in counts.items() if value},
        "categories": {key: value for key, value in categories.items() if value},
        "limits": {
            "max_items_per_category": max_items_per_category,
            "max_summary_chars": max_summary_chars,
            "raw_sensitive_fields_excluded": sorted(_SENSITIVE_FIELD_NAMES),
        },
        "policy": {
            "bounded": True,
            "redacted": True,
            "raw_transcripts_excluded": True,
            "raw_secrets_excluded": True,
            "long_term_memory_safe": True,
        },
    }


def classify_source_signal(signal: Any) -> str:
    text = _normalize_whitespace(_signal_text(signal)).lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return category
    return "uncategorized"


def summarize_source_signal(signal: Any, *, max_chars: int = DEFAULT_MAX_SUMMARY_CHARS) -> str:
    text = _redact_text(_signal_text(signal))
    text = _normalize_whitespace(text)
    if not text:
        text = "No public summary fields were available."
    return _truncate(text, max_chars)


def render_ai_ready_context(context: Mapping[str, Any]) -> str:
    lines = [
        "AI-Ready Context",
        f"schema: {context.get('schema_version')}",
        f"sources: {context.get('source_count', 0)}",
        f"primary_category: {context.get('primary_category') or 'none'}",
    ]
    categories = context.get("categories")
    if isinstance(categories, Mapping):
        for category, items in categories.items():
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, Mapping):
                    continue
                lines.append(f"- {category}: {item.get('summary')}")
    return "\n".join(lines)


def attach_ai_ready_context(
    pack: MutableMapping[str, Any],
    source_signals: Any = None,
    *,
    max_items_per_category: int = DEFAULT_MAX_ITEMS_PER_CATEGORY,
    max_summary_chars: int = DEFAULT_MAX_SUMMARY_CHARS,
) -> MutableMapping[str, Any]:
    context = synthesize_ai_ready_context(
        source_signals,
        max_items_per_category=max_items_per_category,
        max_summary_chars=max_summary_chars,
    )
    pack["ai_ready_context"] = context
    pack["ai_ready_context_text"] = render_ai_ready_context(context)
    return pack


def _iter_signal_items(source_signals: Any) -> Iterable[Any]:
    if source_signals is None:
        return ()
    if isinstance(source_signals, Mapping):
        for key in ("signals", "sources", "items"):
            value = source_signals.get(key)
            if isinstance(value, Iterable) and not isinstance(value, (str, bytes, Mapping)):
                return tuple(value)
        return (source_signals,)
    if isinstance(source_signals, (str, bytes)):
        return (source_signals.decode("utf-8", errors="replace") if isinstance(source_signals, bytes) else source_signals,)
    if isinstance(source_signals, Iterable):
        return tuple(source_signals)
    return (source_signals,)


def _signal_text(signal: Any) -> str:
    if isinstance(signal, Mapping):
        parts: list[str] = []
        for field in _FIELD_PRIORITY:
            if field in signal:
                part = _safe_field_text(signal.get(field), field_name=field)
                if part:
                    parts.append(part)
        if parts:
            return " | ".join(parts)
        return " | ".join(
            _safe_field_text(value, field_name=str(key))
            for key, value in signal.items()
            if str(key).lower() not in _SENSITIVE_FIELD_NAMES
        )
    if isinstance(signal, bytes):
        return signal.decode("utf-8", errors="replace")
    if isinstance(signal, (str, int, float, bool)):
        return str(signal)
    return ""


def _safe_field_text(value: Any, *, field_name: str) -> str:
    if field_name.lower() in _SENSITIVE_FIELD_NAMES:
        return ""
    if isinstance(value, Mapping):
        nested = []
        for key in _FIELD_PRIORITY:
            if key in value:
                text = _safe_field_text(value.get(key), field_name=key)
                if text:
                    nested.append(text)
        return " ".join(nested)
    if isinstance(value, list):
        return " ".join(
            _safe_field_text(item, field_name=field_name)
            for item in value[:3]
        )
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return ""


def _redact_text(value: str) -> str:
    redacted = value
    for pattern, replacement in _SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _truncate(value: str, max_chars: int) -> str:
    limit = max(40, int(max_chars))
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "..."


def _primary_category(counts: Mapping[str, int]) -> str | None:
    positive = [(category, count) for category, count in counts.items() if count > 0]
    if not positive:
        return None
    return sorted(positive, key=lambda item: (-item[1], item[0]))[0][0]
