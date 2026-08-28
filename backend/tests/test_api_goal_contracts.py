import copy
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

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
    refreshed = goals.get_goal("task-001")
    assert refreshed["invalidations"] == [request]
    coverage = {item["criterion_id"]: item for item in refreshed["projection"]["criterion_coverage"]}
    assert coverage["criterion-36bc8486dd50ddc0"]["evidence_state"] == "stale"
    assert refreshed["projection"]["validity_state"] == "revalidation_required"


def test_goal_revision_reuses_unaffected_evidence_and_marks_only_impacted_criterion_stale(monkeypatch, tmp_path):
    client, service = _client(monkeypatch, tmp_path)
    from across_agents_assistant.goal_contract.service import GoalContractService

    goals = GoalContractService(service)
    for index, criterion_id in enumerate(
        ["criterion-36bc8486dd50ddc0", "criterion-5691b86a398c721e"], start=1
    ):
        goals.record_direct_evidence(
            task_id="task-001",
            goal_revision=1,
            criterion_ids=[criterion_id],
            artifact_digests={f"artifact-{index}": f"{index}" * 64},
            validator_id="aaa-direct:test-suite",
            verdict="verified",
            input_fingerprint=f"{index + 2}" * 64,
            idempotency_key=f"revision-evidence-{index}",
        )
    proposal = {
        "schema_version": "across-goal-change-proposal/1.0",
        "proposal_id": "proposal-selective-revalidation",
        "goal_id": "goal-task-001",
        "base_goal_revision": 1,
        "proposed_by": "autopilot",
        "reason": "The test input fingerprint changed.",
        "operations": [{"op": "add", "path": "/scope/excludes/-", "value": "release-candidate"}],
        "impact_summary": {
            "goal_ids": ["goal-task-001"],
            "criterion_ids": ["criterion-36bc8486dd50ddc0"],
            "evidence_ids": [],
            "requires_revalidation": True,
        },
        "risk_summary": {"level": "medium", "reasons": ["input_change"]},
        "estimated_cost": {"unit": "agent_turns", "value": 1},
        "alternatives": [],
        "decision_state": "pending",
        "created_at": "2026-08-28T00:05:00Z",
    }
    assert client.post(
        "/api/tasks/task-001/goal/proposals",
        json={"proposal": proposal, "expected_revision": 1, "idempotency_key": "selective-create"},
    ).status_code == 200
    response = client.post(
        "/api/tasks/task-001/goal/proposals/proposal-selective-revalidation/decision",
        json={
            "decision": "accepted",
            "expected_revision": 1,
            "operation_indexes": [],
            "approver_id": "local-human",
            "idempotency_key": "selective-decision",
        },
    )
    assert response.status_code == 200, response.text

    refreshed = goals.get_goal("task-001")
    coverage = {item["criterion_id"]: item for item in refreshed["projection"]["criterion_coverage"]}
    assert coverage["criterion-36bc8486dd50ddc0"]["evidence_state"] == "stale"
    assert coverage["criterion-5691b86a398c721e"]["evidence_state"] == "verified"
    assert {item.get("reused_from_evidence_id") for item in refreshed["evidence_bindings"]} == {
        item["evidence_id"] for item in service.goal_contracts.list_evidence("goal-task-001", 1)
    }
    assert refreshed["invalidations"][0]["criterion_ids"] == ["criterion-36bc8486dd50ddc0"]


def test_completed_revalidation_creates_new_attempt_keeps_old_evidence_and_restores_validity(monkeypatch, tmp_path):
    _, service = _client(monkeypatch, tmp_path)
    from across_agents_assistant.goal_contract.service import GoalContractService

    goals = GoalContractService(service)
    old = goals.record_direct_evidence(
        task_id="task-001",
        goal_revision=1,
        criterion_ids=["criterion-36bc8486dd50ddc0"],
        artifact_digests={"report.json": "a" * 64},
        validator_id="aaa-direct:test-suite",
        verdict="verified",
        input_fingerprint="b" * 64,
        idempotency_key="revalidation-old-evidence",
    )
    invalidation = goals.request_revalidation(
        task_id="task-001",
        expected_revision=1,
        criterion_ids=["criterion-36bc8486dd50ddc0"],
        reason="source fingerprint changed",
        idempotency_key="revalidation-request",
    )
    result = goals.complete_revalidation(
        task_id="task-001",
        expected_revision=1,
        criterion_ids=["criterion-36bc8486dd50ddc0"],
        artifact_digests={"report.json": "c" * 64},
        validator_id="aaa-host:revalidation",
        verdict="verified",
        input_fingerprint="d" * 64,
        attempt={
            "schema_version": "across-goal-revalidation-attempt/1.0",
            "attempt_id": "revalidation-attempt-test-001",
            "attempt_number": 1,
            "criterion_ids": ["criterion-36bc8486dd50ddc0"],
            "changed_fingerprints": ["source fingerprint changed"],
            "supersedes_evidence_ids": [old["evidence_id"]],
            "preserved_evidence_ids": [],
            "state": "queued",
        },
        idempotency_key="revalidation-complete",
    )

    assert result["attempt"]["attempt_id"] == "revalidation-attempt-test-001"
    assert result["attempt"]["state"] == "completed"
    assert result["invalidation"]["invalidation_id"] == invalidation["invalidation_id"]
    assert result["invalidation"]["state"] == "completed"
    evidence = service.goal_contracts.list_evidence("goal-task-001", 1)
    assert [item["evidence_id"] for item in evidence][0] == old["evidence_id"]
    assert evidence[-1]["attempt_id"] == "revalidation-attempt-test-001"
    assert evidence[-1]["supersedes_evidence_ids"] == [old["evidence_id"]]
    refreshed = goals.get_goal("task-001")
    assert refreshed["projection"]["validity_state"] == "valid"
    assert refreshed["projection"]["criterion_coverage"][0]["evidence_state"] == "verified"


def test_goal_plugin_probe_api_preserves_managed_runtime_matrix(monkeypatch, tmp_path):
    import across_agents_assistant.goal_contract.api as goal_api

    client, _ = _client(monkeypatch, tmp_path)
    contract = _fixture("simple.json")
    observed = {}

    def fake_probe(value, *, allow_missing=False):
        observed["value"] = value
        observed["allow_missing"] = allow_missing
        return {"schema_version": "across-goal-contract-probe-matrix/1.0", "status": "passed"}

    monkeypatch.setattr(goal_api, "run_managed_goal_contract_probe", fake_probe)
    response = client.post(
        "/api/goal-contract/plugin-probe",
        json={"contract": contract, "allow_missing": False},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "passed"
    assert observed == {"value": contract, "allow_missing": False}


def test_revalidation_api_uses_orchestrator_attempt_and_restores_selected_criterion(monkeypatch, tmp_path):
    from fastapi import FastAPI
    import across_agents_assistant.goal_contract.api as goal_api
    from across_agents_assistant.goal_contract.api import install_goal_contract_routes
    from across_agents_assistant.goal_contract.service import GoalContractService

    service = PersistenceService(str(tmp_path / "revalidation-api.db"))
    service.goal_contracts.create_revision(_fixture("simple.json"), expected_revision=0)
    goals = GoalContractService(service)
    old = goals.record_direct_evidence(
        task_id="task-001",
        goal_revision=1,
        criterion_ids=["criterion-36bc8486dd50ddc0"],
        artifact_digests={"report.json": "a" * 64},
        validator_id="aaa-direct:test-suite",
        verdict="verified",
        input_fingerprint="b" * 64,
        idempotency_key="api-old-evidence",
    )
    goals.request_revalidation(
        task_id="task-001",
        expected_revision=1,
        criterion_ids=["criterion-36bc8486dd50ddc0"],
        reason="input changed",
        idempotency_key="api-pending-invalidation",
    )
    observed = {}

    def fake_attempt(payload):
        observed["payload"] = payload
        return {
            "schema_version": "across-goal-revalidation-attempt/1.0",
            "attempt_id": "revalidation-attempt-api",
            "attempt_number": 1,
            "criterion_ids": ["criterion-36bc8486dd50ddc0"],
            "changed_fingerprints": payload["changed_fingerprints"],
            "supersedes_evidence_ids": [old["evidence_id"]],
            "preserved_evidence_ids": [],
            "state": "queued",
        }

    async def verifier(task_id, revision, criterion_ids, attempt):
        observed["verification"] = (task_id, revision, criterion_ids, attempt["attempt_id"])
        return {
            "artifact_digests": {"report.json": "c" * 64},
            "validator_id": "aaa-host:goal-revalidation",
            "verdict": "verified",
            "input_fingerprint": "d" * 64,
        }

    monkeypatch.setattr(goal_api, "run_managed_goal_revalidation_attempt", fake_attempt)
    app = FastAPI()
    install_goal_contract_routes(app, service_provider=lambda: service, revalidation_verifier=verifier)
    client = TestClient(app)
    response = client.post(
        "/api/tasks/task-001/goal/revalidate",
        json={
            "expected_revision": 1,
            "criterion_ids": ["criterion-36bc8486dd50ddc0"],
            "reason": "User requested revalidation of stale criterion evidence",
            "idempotency_key": "api-complete-revalidation",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["attempt"]["state"] == "completed"
    assert response.json()["projection"]["validity_state"] == "valid"
    assert observed["verification"] == (
        "task-001", 1, ["criterion-36bc8486dd50ddc0"], "revalidation-attempt-api"
    )
    assert observed["payload"]["criterion_ids"] == ["criterion-36bc8486dd50ddc0"]
    replay = client.post(
        "/api/tasks/task-001/goal/revalidate",
        json={
            "expected_revision": 1,
            "criterion_ids": ["criterion-36bc8486dd50ddc0"],
            "reason": "User requested revalidation of stale criterion evidence",
            "idempotency_key": "api-complete-revalidation",
        },
    )
    assert replay.status_code == 200, replay.text
    assert replay.json() == response.json()


def test_human_criterion_review_reject_then_pass_is_audited_and_changes_projection(monkeypatch, tmp_path):
    client, service = _client(monkeypatch, tmp_path)
    from across_agents_assistant.goal_contract.service import GoalContractService

    goals = GoalContractService(service)
    goals.record_direct_evidence(
        task_id="task-001",
        goal_revision=1,
        criterion_ids=["criterion-5691b86a398c721e"],
        artifact_digests={"installed-app.png": "a" * 64},
        validator_id="aaa-host:installed-ui",
        verdict="verified",
        input_fingerprint="b" * 64,
        idempotency_key="human-review-evidence",
    )
    rejected = client.post(
        "/api/tasks/task-001/goal/reviews",
        json={
            "expected_revision": 1,
            "criterion_id": "criterion-5691b86a398c721e",
            "decision": "rejected",
            "reason": "The visible state needs a fix.",
            "reviewer_id": "human:local",
            "idempotency_key": "human-review-rejected",
        },
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["projection"]["review_state"] == "failed"
    assert rejected.json()["review"]["decision_receipt"]["purpose"] == "goal_criterion_review"

    passed = client.post(
        "/api/tasks/task-001/goal/reviews",
        json={
            "expected_revision": 1,
            "criterion_id": "criterion-5691b86a398c721e",
            "decision": "passed",
            "reason": "The corrected visible state now passes review.",
            "reviewer_id": "human:local",
            "idempotency_key": "human-review-passed",
        },
    )
    assert passed.status_code == 200, passed.text
    coverage = {
        item["criterion_id"]: item for item in passed.json()["projection"]["criterion_coverage"]
    }
    assert coverage["criterion-5691b86a398c721e"]["review_state"] == "passed"
    envelope = client.get("/api/tasks/task-001/goal").json()
    assert [item["status"] for item in envelope["reviews"]] == ["rejected", "passed"]


def test_task_result_acceptance_evidence_completes_submitted_goal(monkeypatch, tmp_path):
    import across_agents_assistant.api_server as api_server

    service = PersistenceService(str(tmp_path / "accepted-goal.db"))
    monkeypatch.setattr(api_server, "persistence", service)
    contract = api_server._create_submitted_goal_contract(
        task_id="task-accepted",
        statement="Build and verify the report",
        deliverables=["across-results/task-report.md"],
        execution_profile="orchestrated",
    )
    info = SimpleNamespace(
        status="completed",
        artifacts=[{"id": "task-report", "sha256": "a" * 64}],
        quality_health={"quality_gate": "passed", "delivery_quality": "passed"},
        delivery_report={"status": "passed"},
    )

    first = api_server._record_goal_acceptance_evidence("task-accepted", info)
    replay = api_server._record_goal_acceptance_evidence("task-accepted", info)

    assert first == replay
    result = api_server.GoalContractService(service).get_goal("task-accepted")
    assert result["projection"]["is_complete"] is True
    coverage = result["projection"]["criterion_coverage"]
    assert len(coverage) == 1
    assert coverage[0]["criterion_id"] == contract["acceptance_criteria"][0]["criterion_id"]
    assert coverage[0]["required"] is True
    assert coverage[0]["evidence_state"] == "verified"
    assert coverage[0]["review_state"] == "not_required"
    assert coverage[0]["satisfied"] is True
    assert len(result["evidence_bindings"]) == 1


def test_missing_orchestrator_runs_goal_tracked_direct_agent_task(monkeypatch, tmp_path):
    import across_agents_assistant.api_server as api_server
    from across_agents_assistant.task_api_models import AutoTaskRequest
    from across_agents_assistant.task_history.state import TaskState

    class MissingOrchestrator:
        def implementation_status(self, *, probe):
            return {"implementation": "external", "available": False, "connection_note": "not installed"}

    async def fake_chat(**_kwargs):
        return SimpleNamespace(text="Verified direct result")

    service = PersistenceService(str(tmp_path / "direct.db"))
    state = TaskState()
    state.set_persistence(service.tasks)
    monkeypatch.setattr(api_server, "persistence", service)
    monkeypatch.setattr(api_server, "_task_state", state)
    monkeypatch.setattr(api_server, "_task_persistence_initialized", True)
    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: MissingOrchestrator())
    monkeypatch.setattr(api_server, "_chat_with_model_capability", fake_chat)

    async def scenario():
        response = await api_server._submit_auto_orchestrated_task(
            AutoTaskRequest(
                description="Inspect the project and write a concise report",
                task_types=["artifact"],
                owner_agent="codex",
                project_dir=str(tmp_path),
            )
        )
        runner = api_server._direct_task_runners[response.task_id]
        await runner
        detail = await api_server.get_task(response.task_id)
        accepted = await api_server.accept_task_result(response.task_id)
        return response, state.get_task(response.task_id), detail, accepted

    response, task, detail, accepted = asyncio.run(scenario())
    assert response.implementation == "direct"
    assert response.external_task is False
    assert response.execution_route == "direct"
    assert task.status.value == "completed"
    assert task.direct_response == "Verified direct result"
    assert detail.status == "completed"
    assert detail.direct_response == "Verified direct result"
    assert accepted["review_status"] == "accepted"
    goal = service.goal_contracts.get_current(response.task_id)
    assert goal is not None
    assert goal["execution_profile"] == "direct"
    assert goal["confirmed_by"] == "local-human:work-submit"
    projection = api_server.GoalContractService(service).get_goal(response.task_id)["projection"]
    assert projection["is_complete"] is True


def test_explicit_workflow_pack_does_not_silently_degrade_without_orchestrator(monkeypatch, tmp_path):
    import across_agents_assistant.api_server as api_server
    from across_agents_assistant.task_api_models import AutoTaskRequest

    class MissingOrchestrator:
        def implementation_status(self, *, probe):
            return {"implementation": "external", "available": False, "connection_note": "not installed"}

    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: MissingOrchestrator())

    async def scenario():
        return await api_server._submit_auto_orchestrated_task(
            AutoTaskRequest(
                description="Run the requested workflow",
                task_types=["artifact"],
                project_dir=str(tmp_path),
                project_signals={"requested_workflow_id": "repo-quality-copilot"},
            )
        )

    try:
        asyncio.run(scenario())
        assert False, "explicit Workflow Pack should require its execution capabilities"
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 412
