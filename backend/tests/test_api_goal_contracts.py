import copy
import json
from pathlib import Path

from fastapi.testclient import TestClient

from across_agents_assistant.persistence.service import PersistenceService


FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "goal-contract"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def _client(monkeypatch, tmp_path):
    import across_agents_assistant.api_server as api_server

    service = PersistenceService(str(tmp_path / "api.db"))
    service.goal_contracts.create_revision(_fixture("simple.json"), expected_revision=0)
    monkeypatch.setattr(api_server, "persistence", service)
    return TestClient(api_server.app), service


def test_goal_api_returns_authoritative_revision_coverage_and_reason_codes(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path)
    response = client.get("/api/tasks/task-001/goal")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["contract"]["revision"] == 1
    assert payload["projection"]["authority"]["goal"] == "aaa"
    assert payload["projection"]["is_complete"] is False
    assert payload["projection"]["reason_codes"] == [
        "criterion_evidence_missing",
        "review_pending",
    ]
    assert len(payload["projection"]["criterion_coverage"]) == 2


def test_unconfirmed_proposal_is_idempotent_and_blocks_completion_without_rewriting_goal(monkeypatch, tmp_path):
    client, service = _client(monkeypatch, tmp_path)
    proposal = _fixture("change-proposal.json")
    request = {"proposal": proposal, "expected_revision": 1, "idempotency_key": "proposal-1"}
    first = client.post("/api/tasks/task-001/goal/proposals", json=request)
    replay = client.post("/api/tasks/task-001/goal/proposals", json=request)
    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert service.goal_contracts.get_current("task-001")["revision"] == 1
    projection = client.get("/api/tasks/task-001/goal").json()["projection"]
    assert "decision_pending" in projection["reason_codes"]

    stale = copy.deepcopy(request)
    stale["proposal"]["proposal_id"] = "proposal-stale"
    stale["proposal"]["base_goal_revision"] = 0
    stale["expected_revision"] = 0
    response = client.post("/api/tasks/task-001/goal/proposals", json=stale)
    assert response.status_code == 409
    assert response.json()["detail"]["reason_code"] == "goal_revision_conflict"


def test_partial_acceptance_creates_revision_and_purpose_bound_receipt(monkeypatch, tmp_path):
    client, service = _client(monkeypatch, tmp_path)
    proposal = _fixture("change-proposal.json")
    assert client.post(
        "/api/tasks/task-001/goal/proposals",
        json={"proposal": proposal, "expected_revision": 1, "idempotency_key": "proposal-create"},
    ).status_code == 200

    decision_request = {
            "decision": "partially_accepted",
            "expected_revision": 1,
            "operation_indexes": [0],
            "approver_id": "local-human",
            "idempotency_key": "proposal-decision",
        }
    response = client.post(
        f"/api/tasks/task-001/goal/proposals/{proposal['proposal_id']}/decision",
        json=decision_request,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["contract"]["revision"] == 2
    assert payload["proposal"]["decision_state"] == "partially_accepted"
    assert payload["decision_receipt"]["purpose"] == "goal_change_decision"
    assert service.goal_contracts.get_current("task-001")["revision"] == 2
    replay = client.post(
        f"/api/tasks/task-001/goal/proposals/{proposal['proposal_id']}/decision",
        json=decision_request,
    )
    assert replay.status_code == 200
    assert replay.json() == payload


def test_direct_agent_evidence_uses_public_binding_schema_and_revalidation_is_append_only(monkeypatch, tmp_path):
    _, service = _client(monkeypatch, tmp_path)
    from across_agents_assistant.goal_contract.service import GoalContractService

    goals = GoalContractService(service)
    binding = goals.record_direct_evidence(
        task_id="task-001",
        goal_revision=1,
        criterion_ids=["criterion-36bc8486dd50ddc0"],
        artifact_digests={"report.json": "a" * 64},
        validator_id="aaa-direct:test-suite",
        verdict="verified",
        input_fingerprint="b" * 64,
        idempotency_key="direct-evidence-1",
    )
    assert binding["schema_version"] == "across-goal-evidence-binding/1.0"
    assert binding["run_id"].startswith("direct-run-")
    assert binding["attempt_id"].startswith("direct-attempt-")

    request = goals.request_revalidation(
        task_id="task-001",
        expected_revision=1,
        criterion_ids=["criterion-36bc8486dd50ddc0"],
        reason="source fingerprint changed",
        idempotency_key="revalidate-1",
    )
    assert request["schema_version"] == "across-goal-revalidation-request/1.0"
    assert service.goal_contracts.list_evidence("goal-task-001", 1)[0]["trust_state"] == "verified"
