from __future__ import annotations

from copy import deepcopy

import pytest

from across_agents_assistant.goal_contract.execution_evidence import build_execution_evidence_material
from across_agents_assistant.goal_contract.service import GoalContractService
from across_agents_assistant.persistence.goal_contract_store import GoalContractStoreError
from across_agents_assistant.persistence.service import PersistenceService


def _contract(*, task_id: str = "task-evidence", profile: str = "orchestrated") -> dict:
    return {
        "schema_version": "across-goal-contract/1.0",
        "goal_id": f"goal-{task_id}",
        "revision": 1,
        "task_id": task_id,
        "statement": "Deliver both verified reports.",
        "success_outcome": "Both reports are present and approved.",
        "scope": {"includes": ["reports/a.md", "reports/b.md"], "excludes": []},
        "acceptance_criteria": [
            {
                "criterion_id": "criterion-a",
                "description": "Deliver and verify reports/a.md",
                "required": True,
                "validator_kind": "task_result_review",
                "review_policy": "human",
                "source": "user_confirmed",
            },
            {
                "criterion_id": "criterion-b",
                "description": "Deliver and verify reports/b.md",
                "required": True,
                "validator_kind": "task_result_review",
                "review_policy": "human",
                "source": "user_confirmed",
            },
        ],
        "dependencies": [],
        "execution_profile": profile,
        "source": "user",
        "confirmed_by": "human:local",
        "confirmed_at": "2026-08-30T00:00:00Z",
        "created_at": "2026-08-30T00:00:00Z",
    }


def _orchestrated_task() -> dict:
    return {
        "task_id": "task-evidence",
        "status": "completed",
        "external_task": True,
        "delivery_mode": "external",
        "artifacts": [
            {"id": "external-reports/a.md", "sha256": "a" * 64},
            {"id": "external-reports/b.md", "sha256": "b" * 64},
        ],
        "quality_health": {"quality_gate": "passed", "delivery_quality": "passed"},
        "delivery_report": {"status": "passed"},
        "remote_execution": None,
    }


def test_execution_evidence_is_one_criterion_binding_and_preserves_real_executor():
    material = build_execution_evidence_material(_contract(), _orchestrated_task())

    assert [item["criterion_id"] for item in material] == ["criterion-a", "criterion-b"]
    assert all(item["executor"] == "across-orchestrator" for item in material)
    assert all(len(item["artifact_digests"]) == 1 for item in material)
    assert material[0]["artifact_digests"] != material[1]["artifact_digests"]
    assert all(item["validator_authority"] == "aaa-host" for item in material)


def test_direct_execution_evidence_uses_direct_attempt_without_claiming_an_artifact_file():
    contract = _contract(task_id="task-direct", profile="direct")
    contract["scope"]["includes"] = ["across-results/task-report.md"]
    contract["acceptance_criteria"] = [deepcopy(contract["acceptance_criteria"][0])]
    contract["acceptance_criteria"][0]["description"] = "Deliver and verify across-results/task-report.md"
    task = {
        "task_id": "task-direct",
        "status": "completed",
        "external_task": False,
        "delivery_mode": "direct",
        "artifacts": [],
        "direct_response": "Verified direct result",
        "quality_health": {},
        "delivery_report": {},
    }

    material = build_execution_evidence_material(contract, task)

    assert len(material) == 1
    assert material[0]["executor"] == "aaa-direct-agent"
    assert material[0]["attempt_id"].startswith("direct-attempt-")
    assert set(material[0]["artifact_digests"]) == {"direct-response"}


def test_invalid_runtime_receipt_fails_closed_instead_of_laundering_artifacts():
    material = build_execution_evidence_material(
        _contract(),
        _orchestrated_task(),
        runtime_evidence={"goal_execution_receipt": {"receipt_hash": "0" * 64}},
    )

    assert material == []


def test_result_review_requires_evidence_then_allows_reject_repair_and_later_pass(tmp_path):
    persistence = PersistenceService(str(tmp_path / "goal-evidence.db"))
    contract = _contract()
    contract["scope"]["includes"] = ["reports/a.md"]
    contract["acceptance_criteria"] = [contract["acceptance_criteria"][0]]
    persistence.goal_contracts.create_revision(contract, expected_revision=0)
    goals = GoalContractService(persistence)

    with pytest.raises(GoalContractStoreError, match="verified execution evidence") as missing:
        goals.record_result_review(
            task_id="task-evidence",
            expected_revision=1,
            decision="passed",
            reason="Looks good.",
            reviewer_id="human:local",
            basis_evidence_ids=[],
            attempt_id="attempt-1",
            idempotency_key="review-missing",
        )
    assert missing.value.code == "goal_evidence_missing"

    first_evidence = goals.record_execution_evidence(
        task_id="task-evidence",
        goal_revision=1,
        criterion_id="criterion-a",
        artifact_digests={"reports/a.md": "a" * 64},
        executor="across-orchestrator",
        run_id="run-1",
        attempt_id="attempt-1",
        validator_id="aaa-host:artifact-validator",
        validator_authority="aaa-host",
        verdict="verified",
        input_fingerprint="b" * 64,
        receipt_hash=None,
        idempotency_key="evidence-attempt-1",
    )
    rejected = goals.record_result_review(
        task_id="task-evidence",
        expected_revision=1,
        decision="rejected",
        reason="The first delivery is incomplete.",
        reviewer_id="human:local",
        basis_evidence_ids=[first_evidence["evidence_id"]],
        attempt_id="attempt-1",
        idempotency_key="review-attempt-1-reject",
    )
    second_evidence = goals.record_execution_evidence(
        task_id="task-evidence",
        goal_revision=1,
        criterion_id="criterion-a",
        artifact_digests={"reports/a.md": "c" * 64},
        executor="across-orchestrator",
        run_id="run-2",
        attempt_id="attempt-2",
        validator_id="aaa-host:artifact-validator",
        validator_authority="aaa-host",
        verdict="verified",
        input_fingerprint="d" * 64,
        receipt_hash=None,
        idempotency_key="evidence-attempt-2",
    )
    passed = goals.record_result_review(
        task_id="task-evidence",
        expected_revision=1,
        decision="passed",
        reason="The repaired delivery now satisfies the criterion.",
        reviewer_id="human:local",
        basis_evidence_ids=[second_evidence["evidence_id"]],
        attempt_id="attempt-2",
        idempotency_key="review-attempt-2-pass",
    )

    assert [rejected["review"]["status"], passed["review"]["status"]] == ["rejected", "passed"]
    assert passed["projection"]["is_complete"] is True
    assert [item["status"] for item in goals.get_goal("task-evidence")["reviews"]] == ["rejected", "passed"]
