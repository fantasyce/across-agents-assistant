from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import math

import pytest

from across_agents_assistant.execution_trajectory import (
    TrajectoryProjectionError,
    project_execution_trajectory,
)


def _event(
    event_id: str,
    sequence: int,
    event_type: str,
    *,
    timestamp: float | int | None = None,
    **extra: object,
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "sequence": sequence,
        "timestamp": float(sequence) if timestamp is None else timestamp,
        "type": event_type,
        "task_id": "task-trajectory",
        **extra,
    }


def _orchestrator_receipt(**extra: object) -> dict[str, object]:
    receipt: dict[str, object] = {
        "schema_version": "across-evidence-receipt/1.0",
        "verdict": "ready",
        **extra,
    }
    receipt["evidence_sha256"] = sha256(
        json.dumps(
            receipt,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return receipt


def _worker_receipt(**extra: object) -> dict[str, object]:
    receipt: dict[str, object] = {
        "schema_version": "across-worker-evidence/1.0",
        "terminal_state": "completed",
        **extra,
    }
    receipt["receipt_hash"] = sha256(
        json.dumps(
            receipt,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return receipt


def _project(
    *,
    raw_events: list[object],
    raw_receipt: object | None = None,
    source: str = "orchestrator_evidence",
    task_status: str = "completed",
    offset: int = 0,
    limit: int = 200,
    generated_at: float = 20.0,
) -> dict[str, object]:
    return project_execution_trajectory(
        task_id="task-trajectory",
        task_status=task_status,
        source=source,
        raw_events=raw_events,
        raw_receipt=raw_receipt,
        offset=offset,
        limit=limit,
        generated_at=generated_at,
    )


def test_orchestrator_receipt_is_verified_before_private_fields_are_redacted():
    private_path = "/Users/private/project"
    private_marker = "credential-private-marker"
    receipt = _orchestrator_receipt(private_path=private_path)

    result = _project(
        raw_receipt=receipt,
        raw_events=[
            _event(
                "event-1",
                1,
                "task.completed",
                payload={
                    "secret": private_marker,
                    "stdout": private_path,
                },
            )
        ],
    )

    encoded = json.dumps(result, sort_keys=True)
    assert result["receipt"] == {
        "schema_version": "across-evidence-receipt/1.0",
        "integrity_state": "hash_valid",
        "digest_algorithm": "sha256",
        "digest_field": "evidence_sha256",
        "digest": receipt["evidence_sha256"],
        "verdict": "ready",
        "reason": "hash_matches_raw_receipt",
    }
    assert result["items"] == [
        {
            "event_id": "event-1",
            "sequence": 1,
            "timestamp": 1.0,
            "event_type": "task.completed",
            "category": "task",
            "phase": "completed",
            "status": "succeeded",
            "title": "Task completed",
            "scope_kind": "task",
            "scope_id": "task-trajectory",
        }
    ]
    assert private_path not in encoded
    assert private_marker not in encoded
    assert '"payload":' not in encoded


def test_worker_receipt_uses_exact_worker_canonical_json_contract():
    receipt = _worker_receipt(summary="完成")
    ascii_digest = sha256(
        json.dumps(
            {key: value for key, value in receipt.items() if key != "receipt_hash"},
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert ascii_digest != receipt["receipt_hash"]

    result = _project(
        source="worker_projection",
        raw_receipt=receipt,
        raw_events=[_event("worker-1", 1, "task.completed")],
    )

    assert result["receipt"] == {
        "schema_version": "across-worker-evidence/1.0",
        "integrity_state": "hash_valid",
        "digest_algorithm": "sha256",
        "digest_field": "receipt_hash",
        "digest": receipt["receipt_hash"],
        "verdict": "ready",
        "reason": "hash_matches_raw_receipt",
    }


@pytest.mark.parametrize(
    ("receipt", "expected"),
    [
        (
            {
                "schema_version": "across-evidence-receipt/1.0",
                "evidence_sha256": "0" * 64,
                "verdict": "ready",
            },
            {
                "schema_version": "across-evidence-receipt/1.0",
                "integrity_state": "invalid",
                "digest_algorithm": "sha256",
                "digest_field": "evidence_sha256",
                "verdict": "warning",
                "reason": "hash_mismatch",
            },
        ),
        (
            {"schema_version": "private-future-schema/99", "private": "do-not-leak"},
            {
                "integrity_state": "unsupported",
                "digest_algorithm": "sha256",
                "verdict": "warning",
                "reason": "unsupported_receipt_schema",
            },
        ),
        (
            None,
            {
                "integrity_state": "missing",
                "digest_algorithm": "sha256",
                "verdict": "warning",
                "reason": "receipt_missing",
            },
        ),
    ],
)
def test_invalid_unsupported_and_missing_receipts_have_closed_public_states(
    receipt: object,
    expected: dict[str, object],
):
    result = _project(
        raw_receipt=receipt,
        raw_events=[_event("event-1", 1, "task.created")],
    )

    assert result["receipt"] == expected
    assert "do-not-leak" not in json.dumps(result, sort_keys=True)


def test_events_are_validated_deduplicated_sorted_then_paginated():
    second = _event("event-2", 2, "task.started")
    result = _project(
        raw_receipt=_orchestrator_receipt(),
        raw_events=[
            _event("event-3", 3, "task.completed"),
            second,
            _event("event-1", 1, "task.created"),
            deepcopy(second),
        ],
        limit=2,
    )

    assert [item["event_id"] for item in result["items"]] == ["event-1", "event-2"]
    assert result["summary"] == {
        "source_event_count": 4,
        "normalized_event_count": 3,
        "first_sequence": 1,
        "last_sequence": 3,
        "started_at": 2.0,
        "completed_at": 3.0,
        "terminal_status": "completed",
    }
    assert result["page"] == {
        "offset": 0,
        "limit": 2,
        "returned": 2,
        "total": 3,
        "next_offset": 2,
        "has_more": True,
    }
    assert result["audit"]["truncated"] is True


def test_conflicting_duplicate_keeps_earliest_public_tuple_and_only_counts_conflict():
    result = _project(
        raw_events=[
            _event("same-id", 9, "task.failed"),
            _event("same-id", 2, "task.started"),
            _event("event-3", 3, "task.completed"),
        ],
    )

    assert [item["event_type"] for item in result["items"]] == [
        "task.started",
        "task.completed",
    ]
    assert result["audit"]["event_integrity_state"] == "degraded"
    assert result["audit"]["conflicting_duplicate_count"] == 1
    assert result["audit"]["omitted_event_count"] == 0


def test_invalid_rows_are_omitted_without_leaking_values():
    private_marker = "private-invalid-row-marker"
    result = _project(
        raw_events=[
            _event("valid", 1, "task.created"),
            {
                "event_id": private_marker,
                "sequence": True,
                "timestamp": 2.0,
                "type": "task.started",
            },
            {
                "event_id": "bad-time",
                "sequence": 2,
                "timestamp": math.nan,
                "type": "task.started",
                "payload": private_marker,
            },
            {
                "event_id": "unsafe id with spaces",
                "sequence": 3,
                "timestamp": 3.0,
                "type": "task.completed",
            },
        ],
    )

    assert [item["event_id"] for item in result["items"]] == ["valid"]
    assert result["audit"]["omitted_event_count"] == 3
    assert result["audit"]["event_integrity_state"] == "degraded"
    assert private_marker not in json.dumps(result, sort_keys=True)


def test_local_timeline_uses_stable_position_ids_and_never_invents_timestamp():
    rows = [
        {
            "kind": "task_created",
            "status": "running",
            "at": 5.0,
            "label": "private-task-description",
            "summary": "private-summary",
        },
        {
            "kind": "subtask_completed",
            "status": "completed",
            "subtask_id": "sub-1",
            "agent_id": "agent-1",
            "label": "private-subtask-description",
        },
        {
            "kind": "quality_gate_passed",
            "status": "passed",
            "gate_id": "gate-1",
            "summary": "private-gate-output",
        },
    ]

    result = _project(
        source="local_task_observability",
        task_status="completed",
        raw_events=rows,
    )

    assert [item["event_id"] for item in result["items"]] == [
        "local-000001",
        "local-000002",
        "local-000003",
    ]
    assert result["items"][0]["timestamp"] == 5.0
    assert "timestamp" not in result["items"][1]
    assert result["items"][1]["scope_kind"] == "subtask"
    assert result["items"][1]["scope_id"] == "sub-1"
    assert result["items"][2]["scope_kind"] == "quality"
    assert result["items"][2]["scope_id"] == "gate-1"
    encoded = json.dumps(result, sort_keys=True)
    assert "private-task-description" not in encoded
    assert "private-summary" not in encoded
    assert "private-subtask-description" not in encoded
    assert "private-gate-output" not in encoded


def test_repeated_projection_is_identical_except_generated_at_and_never_mutates_inputs():
    events = [_event("event-1", 1, "task.completed", payload={"private": "marker"})]
    receipt = _orchestrator_receipt(private="marker")
    events_before = deepcopy(events)
    receipt_before = deepcopy(receipt)

    first = _project(raw_events=events, raw_receipt=receipt, generated_at=10.0)
    second = _project(raw_events=events, raw_receipt=receipt, generated_at=11.0)

    assert first.pop("generated_at") == 10.0
    assert second.pop("generated_at") == 11.0
    assert first == second
    assert events == events_before
    assert receipt == receipt_before


def test_large_snapshot_returns_only_the_requested_bounded_page():
    result = _project(
        raw_events=[
            _event(f"event-{index:04d}", index, "task.checkpoint")
            for index in range(1, 1201)
        ],
        offset=500,
        limit=200,
        task_status="running",
    )

    assert len(result["items"]) == 200
    assert result["items"][0]["event_id"] == "event-0501"
    assert result["items"][-1]["event_id"] == "event-0700"
    assert result["page"] == {
        "offset": 500,
        "limit": 200,
        "returned": 200,
        "total": 1200,
        "next_offset": 700,
        "has_more": True,
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"source": "private-source-marker"},
        {"offset": -1},
        {"offset": True},
        {"limit": 0},
        {"limit": 501},
        {"limit": 1.5},
    ],
)
def test_invalid_projector_contract_uses_one_fixed_public_error(overrides: dict[str, object]):
    arguments: dict[str, object] = {
        "task_id": "task-trajectory",
        "task_status": "completed",
        "source": "orchestrator_evidence",
        "raw_events": [],
        "raw_receipt": None,
        "offset": 0,
        "limit": 200,
        "generated_at": 10.0,
    }
    arguments.update(overrides)

    with pytest.raises(TrajectoryProjectionError) as captured:
        project_execution_trajectory(**arguments)

    assert str(captured.value) == "execution trajectory input is invalid"
    assert "private-source-marker" not in repr(captured.value)
