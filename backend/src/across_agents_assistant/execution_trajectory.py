"""Pure, read-only projection for public execution trajectories."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
import hmac
import json
import math
import re
import time
from typing import Any


TRAJECTORY_SCHEMA_VERSION = "across-execution-trajectory/1.0"
ORCHESTRATOR_RECEIPT_SCHEMA = "across-evidence-receipt/1.0"
WORKER_RECEIPT_SCHEMA = "across-worker-evidence/1.0"
TRAJECTORY_SOURCES = {
    "orchestrator_evidence",
    "worker_projection",
    "local_task_observability",
}
_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}")
_HEX_DIGEST = re.compile(r"[0-9a-f]{64}")


class TrajectoryProjectionError(ValueError):
    """Fixed public error for an invalid projector contract."""


_EVENT_PRESENTATION: dict[str, tuple[str, str, str, str]] = {
    "task.created": ("task", "created", "recorded", "Task created"),
    "task.started": ("task", "started", "running", "Task started"),
    "task.checkpoint": ("task", "checkpoint", "running", "Task checkpoint"),
    "task.completed": ("task", "completed", "succeeded", "Task completed"),
    "task.failed": ("task", "failed", "failed", "Task failed"),
    "task.blocked": ("task", "blocked", "blocked", "Task blocked"),
    "task.cancelled": ("task", "cancelled", "cancelled", "Task cancelled"),
    "contract.created": ("contract", "created", "recorded", "Contract created"),
    "contract.completed": ("contract", "completed", "succeeded", "Contract completed"),
    "loop.started": ("agent_loop", "started", "running", "Agent loop started"),
    "loop.checkpoint": ("agent_loop", "checkpoint", "running", "Agent loop checkpoint"),
    "loop.completed": ("agent_loop", "completed", "succeeded", "Agent loop completed"),
    "loop.failed": ("agent_loop", "failed", "failed", "Agent loop failed"),
    "subtask.started": ("subtask", "started", "running", "Subtask started"),
    "subtask.completed": ("subtask", "completed", "succeeded", "Subtask completed"),
    "subtask.failed": ("subtask", "failed", "failed", "Subtask failed"),
    "subtask.blocked": ("subtask", "blocked", "blocked", "Subtask blocked"),
    "subtask.cancelled": ("subtask", "cancelled", "cancelled", "Subtask cancelled"),
    "sandbox.created": ("sandbox", "created", "recorded", "Sandbox created"),
    "sandbox.completed": ("sandbox", "completed", "succeeded", "Sandbox completed"),
    "sandbox.failed": ("sandbox", "failed", "failed", "Sandbox failed"),
    "approval.created": ("approval", "created", "recorded", "Approval requested"),
    "approval.completed": ("approval", "completed", "succeeded", "Approval completed"),
    "approval.blocked": ("approval", "blocked", "blocked", "Approval blocked"),
    "quality.started": ("quality", "started", "running", "Quality check started"),
    "quality.completed": ("quality", "completed", "succeeded", "Quality check completed"),
    "quality.failed": ("quality", "failed", "failed", "Quality check failed"),
    "artifact.created": ("artifact", "created", "recorded", "Artifact recorded"),
    "artifact.completed": ("artifact", "completed", "succeeded", "Artifact completed"),
}


_LOCAL_PRESENTATION: dict[str, tuple[str, str, str, str, str]] = {
    "task_created": ("task.created", "task", "created", "recorded", "Task created"),
    "wave_approved": ("contract.completed", "contract", "completed", "succeeded", "Wave approved"),
    "wave_blocked": ("contract.blocked", "contract", "blocked", "blocked", "Wave blocked"),
    "wave_revalidating": ("contract.checkpoint", "contract", "checkpoint", "running", "Wave revalidating"),
    "wave_status": ("contract.checkpoint", "contract", "checkpoint", "running", "Wave status recorded"),
    "subtask_running": ("subtask.started", "subtask", "started", "running", "Subtask started"),
    "subtask_completed": ("subtask.completed", "subtask", "completed", "succeeded", "Subtask completed"),
    "subtask_failed": ("subtask.failed", "subtask", "failed", "failed", "Subtask failed"),
    "subtask_cancelled": ("subtask.cancelled", "subtask", "cancelled", "cancelled", "Subtask cancelled"),
    "quality_gate_passed": ("quality.completed", "quality", "completed", "succeeded", "Quality check completed"),
    "quality_gate_completed": ("quality.completed", "quality", "completed", "succeeded", "Quality check completed"),
    "quality_gate_failed": ("quality.failed", "quality", "failed", "failed", "Quality check failed"),
    "quality_gate_blocked": ("quality.blocked", "quality", "blocked", "blocked", "Quality check blocked"),
    "quality_gate_running": ("quality.started", "quality", "started", "running", "Quality check started"),
    "remediation_attempted": ("quality.checkpoint", "quality", "checkpoint", "recorded", "Remediation attempted"),
}


_STATUS_TOKENS = {
    "created": "recorded",
    "recorded": "recorded",
    "pending": "recorded",
    "queued": "recorded",
    "attempted": "recorded",
    "running": "running",
    "in_progress": "running",
    "revalidating": "running",
    "completed": "succeeded",
    "passed": "succeeded",
    "approved": "succeeded",
    "succeeded": "succeeded",
    "failed": "failed",
    "blocked": "blocked",
    "cancelled": "cancelled",
    "unknown": "unknown",
}


_TASK_STATUSES = {
    "pending",
    "queued",
    "running",
    "completed",
    "completed_with_failures",
    "failed",
    "blocked",
    "cancelled",
    "unknown",
}


def project_execution_trajectory(
    *,
    task_id: str,
    task_status: str,
    source: str,
    raw_events: Sequence[Any],
    raw_receipt: Any,
    offset: int,
    limit: int,
    generated_at: float | None = None,
) -> dict[str, Any]:
    """Return one closed, read-only public trajectory projection."""

    if (
        type(source) is not str
        or source not in TRAJECTORY_SOURCES
        or _safe_identifier(task_id) is None
        or type(offset) is not int
        or offset < 0
        or type(limit) is not int
        or not 1 <= limit <= 500
        or not isinstance(raw_events, (list, tuple))
    ):
        raise TrajectoryProjectionError("execution trajectory input is invalid")
    if generated_at is None:
        public_generated_at = time.time()
    elif _finite_number(generated_at) is None:
        raise TrajectoryProjectionError("execution trajectory input is invalid")
    else:
        public_generated_at = float(generated_at)

    receipt = verify_evidence_receipt(source=source, raw_receipt=raw_receipt)
    normalized: list[dict[str, Any]] = []
    omitted_count = 0
    for index, raw_event in enumerate(raw_events):
        if source == "local_task_observability":
            item = _normalize_local_event(raw_event, index=index, task_id=task_id)
        else:
            item = _normalize_external_event(raw_event, index=index, task_id=task_id)
        if item is None:
            omitted_count += 1
        else:
            normalized.append(item)

    deduplicated: dict[str, dict[str, Any]] = {}
    conflicting_duplicate_count = 0
    for item in normalized:
        event_id = item["event_id"]
        existing = deduplicated.get(event_id)
        if existing is None:
            deduplicated[event_id] = item
            continue
        if _public_event(existing) == _public_event(item):
            continue
        conflicting_duplicate_count += 1
        if _event_order(item) < _event_order(existing):
            deduplicated[event_id] = item

    full_items = sorted(deduplicated.values(), key=_event_public_order)
    public_items = [_public_event(item) for item in full_items]
    page_items = public_items[offset : offset + limit]
    total = len(public_items)
    end_offset = offset + len(page_items)
    has_more = end_offset < total
    next_offset = end_offset if has_more else None
    public_task_status = _public_task_status(task_status, public_items)

    timestamps_started = [
        float(item["timestamp"])
        for item in public_items
        if item.get("phase") == "started" and _finite_number(item.get("timestamp")) is not None
    ]
    timestamps_completed = [
        float(item["timestamp"])
        for item in public_items
        if item.get("category") == "task"
        and item.get("phase") in {"completed", "failed", "blocked", "cancelled"}
        and _finite_number(item.get("timestamp")) is not None
    ]
    event_integrity_state = (
        "degraded" if omitted_count or conflicting_duplicate_count else "clean"
    )

    return {
        "schema_version": TRAJECTORY_SCHEMA_VERSION,
        "generated_at": public_generated_at,
        "task_id": task_id,
        "task_status": public_task_status,
        "source": source,
        "summary": {
            "source_event_count": len(raw_events),
            "normalized_event_count": total,
            "first_sequence": public_items[0]["sequence"] if public_items else None,
            "last_sequence": public_items[-1]["sequence"] if public_items else None,
            "started_at": min(timestamps_started) if timestamps_started else None,
            "completed_at": max(timestamps_completed) if timestamps_completed else None,
            "terminal_status": public_task_status,
        },
        "page": {
            "offset": offset,
            "limit": limit,
            "returned": len(page_items),
            "total": total,
            "next_offset": next_offset,
            "has_more": has_more,
        },
        "receipt": receipt,
        "items": page_items,
        "audit": {
            "read_only": True,
            "mutations_triggered": False,
            "repair_or_resume_triggered": False,
            "secrets_redacted": True,
            "receipt_checked_before_redaction": True,
            "raw_payload_exposed": False,
            "event_integrity_state": event_integrity_state,
            "omitted_event_count": omitted_count,
            "conflicting_duplicate_count": conflicting_duplicate_count,
            "truncated": len(page_items) < total,
        },
    }


def verify_evidence_receipt(*, source: str, raw_receipt: Any) -> dict[str, Any]:
    """Verify one raw receipt and return its bounded public integrity state."""

    if raw_receipt is None:
        return _receipt_state("missing", "receipt_missing")
    if not isinstance(raw_receipt, Mapping):
        return _receipt_state("invalid", "receipt_malformed")
    schema = raw_receipt.get("schema_version")
    if source == "worker_projection":
        if schema != WORKER_RECEIPT_SCHEMA:
            return _receipt_state("unsupported", "unsupported_receipt_schema")
        return _classify_worker_receipt(raw_receipt)
    if schema != ORCHESTRATOR_RECEIPT_SCHEMA:
        return _receipt_state("unsupported", "unsupported_receipt_schema")
    return _classify_orchestrator_receipt(raw_receipt)


def _classify_orchestrator_receipt(raw_receipt: Mapping[str, Any]) -> dict[str, Any]:
    receipt = dict(raw_receipt)
    expected = receipt.pop("evidence_sha256", None)
    valid_expected = type(expected) is str and _HEX_DIGEST.fullmatch(expected) is not None
    actual = _canonical_digest(receipt, ensure_ascii=True)
    if not valid_expected or actual is None or not hmac.compare_digest(expected, actual):
        return _receipt_state(
            "invalid",
            "hash_mismatch" if valid_expected else "receipt_malformed",
            schema=ORCHESTRATOR_RECEIPT_SCHEMA,
            digest_field="evidence_sha256",
        )
    verdict = raw_receipt.get("verdict")
    public_verdict = verdict if verdict in {"ready", "blocked", "needs_review", "warning"} else "unknown"
    return _receipt_state(
        "hash_valid",
        "hash_matches_raw_receipt",
        schema=ORCHESTRATOR_RECEIPT_SCHEMA,
        digest_field="evidence_sha256",
        digest=expected,
        verdict=public_verdict,
    )


def _classify_worker_receipt(raw_receipt: Mapping[str, Any]) -> dict[str, Any]:
    receipt = dict(raw_receipt)
    expected = receipt.pop("receipt_hash", None)
    valid_expected = type(expected) is str and _HEX_DIGEST.fullmatch(expected) is not None
    actual = _canonical_digest(receipt, ensure_ascii=False)
    if not valid_expected or actual is None or not hmac.compare_digest(expected, actual):
        return _receipt_state(
            "invalid",
            "hash_mismatch" if valid_expected else "receipt_malformed",
            schema=WORKER_RECEIPT_SCHEMA,
            digest_field="receipt_hash",
        )
    public_verdict = "ready" if raw_receipt.get("terminal_state") == "completed" else "warning"
    return _receipt_state(
        "hash_valid",
        "hash_matches_raw_receipt",
        schema=WORKER_RECEIPT_SCHEMA,
        digest_field="receipt_hash",
        digest=expected,
        verdict=public_verdict,
    )


def _receipt_state(
    integrity_state: str,
    reason: str,
    *,
    schema: str | None = None,
    digest_field: str | None = None,
    digest: str | None = None,
    verdict: str = "warning",
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "integrity_state": integrity_state,
        "digest_algorithm": "sha256",
        "verdict": verdict,
        "reason": reason,
    }
    if schema is not None:
        result["schema_version"] = schema
    if digest_field is not None:
        result["digest_field"] = digest_field
    if digest is not None:
        result["digest"] = digest
    return result


def _canonical_digest(value: Mapping[str, Any], *, ensure_ascii: bool) -> str | None:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=ensure_ascii,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        return None
    return sha256(payload).hexdigest()


def _normalize_external_event(
    raw_event: Any,
    *,
    index: int,
    task_id: str,
) -> dict[str, Any] | None:
    if not isinstance(raw_event, Mapping):
        return None
    sequence = raw_event.get("sequence")
    timestamp = _finite_number(raw_event.get("timestamp"))
    event_id = _safe_identifier(raw_event.get("event_id"))
    event_type = _safe_identifier(raw_event.get("type"))
    if type(sequence) is not int or sequence < 0 or timestamp is None or event_id is None or event_type is None:
        return None
    category, phase, fallback_status, title = _EVENT_PRESENTATION.get(
        event_type,
        ("other", "other", "unknown", "Recorded event"),
    )
    item: dict[str, Any] = {
        "event_id": event_id,
        "sequence": sequence,
        "timestamp": timestamp,
        "event_type": event_type,
        "category": category,
        "phase": phase,
        "status": _status_token(raw_event.get("status"), fallback_status),
        "title": title,
        "scope_kind": "task",
        "scope_id": task_id,
        "_source_index": index,
    }
    _apply_scope(item, raw_event, category=category, task_id=task_id)
    actor = _safe_identifier(raw_event.get("agent")) or _safe_identifier(raw_event.get("actor"))
    if actor is not None:
        item["actor"] = actor
    refs = _safe_references(raw_event.get("evidence_refs"))
    if refs:
        item["evidence_refs"] = refs
    return item


def _normalize_local_event(
    raw_event: Any,
    *,
    index: int,
    task_id: str,
) -> dict[str, Any] | None:
    if not isinstance(raw_event, Mapping):
        return None
    kind = raw_event.get("kind")
    if type(kind) is not str or kind not in _LOCAL_PRESENTATION:
        return None
    event_type, category, phase, fallback_status, title = _LOCAL_PRESENTATION[kind]
    item: dict[str, Any] = {
        "event_id": f"local-{index + 1:06d}",
        "sequence": index + 1,
        "event_type": event_type,
        "category": category,
        "phase": phase,
        "status": _status_token(raw_event.get("status"), fallback_status),
        "title": title,
        "scope_kind": "task",
        "scope_id": task_id,
        "_source_index": index,
    }
    timestamp = _finite_number(raw_event.get("timestamp"))
    if timestamp is None:
        timestamp = _finite_number(raw_event.get("at"))
    if timestamp is not None:
        item["timestamp"] = timestamp
    _apply_scope(item, raw_event, category=category, task_id=task_id)
    actor = _safe_identifier(raw_event.get("agent_id"))
    if actor is not None:
        item["actor"] = actor
    return item


def _apply_scope(
    item: dict[str, Any],
    raw_event: Mapping[str, Any],
    *,
    category: str,
    task_id: str,
) -> None:
    candidates = {
        "agent_loop": ("loop", "loop_id"),
        "subtask": ("subtask", "subtask_id"),
        "sandbox": ("sandbox", "sandbox_id"),
        "approval": ("approval", "approval_id"),
        "quality": ("quality", "gate_id"),
        "artifact": ("artifact", "artifact_id"),
        "contract": ("contract", "contract_id"),
    }
    scope_kind, field = candidates.get(category, ("task", "task_id"))
    scope_id = _safe_identifier(raw_event.get(field))
    if category == "contract" and scope_id is None:
        wave_number = raw_event.get("wave_number")
        if type(wave_number) is int and wave_number >= 0:
            scope_kind, scope_id = "wave", str(wave_number)
    if scope_id is None:
        scope_kind, scope_id = "task", task_id
    item["scope_kind"] = scope_kind
    item["scope_id"] = scope_id


def _safe_identifier(value: Any) -> str | None:
    if type(value) is not str or _SAFE_IDENTIFIER.fullmatch(value) is None:
        return None
    return value


def _safe_references(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for raw in value[:32]:
        item = _safe_identifier(raw)
        if item is not None and item not in result:
            result.append(item)
    return result


def _finite_number(value: Any) -> float | None:
    if type(value) not in (int, float):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _status_token(value: Any, fallback: str) -> str:
    if type(value) is str:
        normalized = _STATUS_TOKENS.get(value.strip().lower())
        if normalized is not None:
            return normalized
    return fallback


def _public_event(item: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if key != "_source_index"}


def _event_order(item: Mapping[str, Any]) -> tuple[int, float, int]:
    timestamp = _finite_number(item.get("timestamp"))
    return (
        int(item["sequence"]),
        timestamp if timestamp is not None else math.inf,
        int(item["_source_index"]),
    )


def _event_public_order(item: Mapping[str, Any]) -> tuple[int, float, str]:
    timestamp = _finite_number(item.get("timestamp"))
    return (
        int(item["sequence"]),
        timestamp if timestamp is not None else math.inf,
        str(item["event_id"]),
    )


def _public_task_status(task_status: Any, items: Sequence[Mapping[str, Any]]) -> str:
    if type(task_status) is str:
        candidate = task_status.strip().lower()
        if candidate in _TASK_STATUSES:
            return candidate
    for item in reversed(items):
        if item.get("category") != "task":
            continue
        phase = item.get("phase")
        if phase == "completed":
            return "completed"
        if phase in {"failed", "blocked", "cancelled"}:
            return str(phase)
    return "unknown"
