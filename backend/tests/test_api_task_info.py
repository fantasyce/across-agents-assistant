"""Tests for TaskInfo API fields including requirement_manifest and artifact aliases."""

import os
import tempfile

import pytest

os.environ.setdefault("ACROSS_AGENTS_DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))

from across_agents_assistant.api_server import _task_to_info
from across_agents_assistant.task_history.models import (
    Artifact,
    RequirementDeliverable,
    RequirementManifest,
)
from across_agents_assistant.task_history.state import TaskState


def test_task_info_includes_requirement_manifest():
    state = TaskState()
    task = state.create_task("Create main.py", project_dir="/tmp/project")
    manifest = RequirementManifest.new(task.task_id, project_dir="/tmp/project")
    manifest.deliverables.append(
        RequirementDeliverable(
            requirement_id="req-main",
            artifact_type="api_service_source",
            path_hint="main.py",
        )
    )
    state.save_requirement_manifest(manifest)

    info = _task_to_info(task, state)
    payload = info.model_dump() if hasattr(info, "model_dump") else info.dict()

    assert payload["requirement_manifest"]["task_id"] == task.task_id
    assert payload["requirement_manifest"]["deliverables"][0]["path_hint"] == "main.py"


def test_task_info_exposes_observability_timeline_and_quality_evidence():
    from across_agents_assistant.task_history.models import JobStatus, SubTask, Wave

    state = TaskState()
    task = state.create_task(
        "Build release-quality Web/API/CLI evidence",
        project_dir="/tmp/project",
        task_types=["functional", "artifact"],
        delivery_mode="composite",
        owner_agent="auto",
        allowed_subtask_agents=["hermes", "deepseek", "openclaw"],
    )
    task.subtasks.extend([
        SubTask(
            subtask_id="st-web",
            description="Create web UI",
            agent_id="hermes",
            status=JobStatus.COMPLETED,
            progress=1.0,
            wave_number=1,
            task_id=task.task_id,
        ),
        SubTask(
            subtask_id="st-quality-browser",
            description="Repair browser E2E evidence",
            agent_id="openclaw",
            status=JobStatus.COMPLETED,
            progress=1.0,
            wave_number=2,
            task_id=task.task_id,
        ),
    ])
    task.waves.append(
        Wave(
            wave_id="wave-1",
            wave_number=1,
            task_id=task.task_id,
            subtasks=[task.subtasks[0]],
            status=JobStatus.COMPLETED,
            governance_status="approved",
        )
    )
    task.last_owner_decision = {
        "quality_remediation_attempts": {"probe_failure:probe-browser-e2e": 1},
        "delivery_quality": {
            "delivery_quality": "passed",
            "produced_required": ["web/index.html", "api/server.mjs"],
            "quality_report": {
                "quality_gate": "passed",
                "final_quality_score": 88,
                "gate_results": [
                    {
                        "gate_id": "gate-agent-mix",
                        "adapter_id": "agent_mix",
                        "status": "passed",
                        "required": True,
                        "evidence": {
                            "satisfied_constraints": [
                                {
                                    "id": "constraint-agent-mix",
                                    "evidence": {
                                        "actual_agents": ["hermes", "deepseek", "openclaw"],
                                        "local_agents": ["hermes", "openclaw"],
                                        "cloud_agents": ["deepseek"],
                                    },
                                }
                            ]
                        },
                    },
                    {
                        "gate_id": "probe-browser-e2e",
                        "adapter_id": "browser_e2e",
                        "status": "passed",
                        "required": True,
                        "summary": "browser ok",
                    },
                ],
            },
        },
    }

    payload = (_task_to_info(task, state).model_dump())

    observability = payload["observability"]
    assert observability["agent_mix"]["actual_agents"] == ["hermes", "deepseek", "openclaw"]
    assert observability["quality_gates"][0]["adapter_id"] == "agent_mix"
    assert observability["remediation"]["attempted"] is True
    timeline_kinds = [event["kind"] for event in observability["timeline"]]
    assert "task_created" in timeline_kinds
    assert "wave_approved" in timeline_kinds
    assert "subtask_completed" in timeline_kinds
    assert "quality_gate_passed" in timeline_kinds
    assert "remediation_attempted" in timeline_kinds


def test_persisted_task_info_exposes_observability_snapshot(tmp_path):
    from across_agents_assistant.api_server import _task_info_from_db

    task_dict = {
        "task_id": "task-observability-db",
        "description": "Historical quality task",
        "status": "completed",
        "project_dir": str(tmp_path),
        "task_types": ["functional"],
        "delivery_mode": "functional",
        "subtasks": [
            {
                "subtask_id": "st-api",
                "description": "Create API",
                "agent_id": "deepseek",
                "status": "completed",
                "progress": 1.0,
                "dependencies": [],
                "wave_number": 1,
            }
        ],
        "waves": [
            {
                "wave_id": "wave-1",
                "wave_number": 1,
                "status": "completed",
                "is_blocked": False,
                "governance_status": "approved",
            }
        ],
        "artifact_records": [],
        "acceptance_records": [],
        "last_owner_decision": {
            "delivery_quality": {
                "delivery_quality": "passed",
                "quality_report": {
                    "quality_gate": "passed",
                    "gate_results": [
                        {
                            "gate_id": "probe-api-service",
                            "adapter_id": "api_service",
                            "status": "passed",
                            "required": True,
                        }
                    ],
                },
            }
        },
        "created_at": 1.0,
        "updated_at": 2.0,
    }

    payload = _task_info_from_db(task_dict).model_dump()

    assert payload["observability"]["quality_gates"][0]["adapter_id"] == "api_service"
    assert payload["observability"]["timeline"][-1]["kind"] == "quality_gate_passed"


def test_list_tasks_includes_persisted_terminal_history(monkeypatch, tmp_path):
    import asyncio
    import across_agents_assistant.api_server as api_server

    task_id = "task-history-completed"

    class FakePersistence:
        def get_all_tasks(self):
            return [{
                "task_id": task_id,
                "description": "Create README.md",
                "status": "completed",
                "project_dir": str(tmp_path),
                "task_types": ["artifact"],
                "delivery_mode": "artifact",
                "created_at": 1.0,
                "updated_at": 2.0,
                "last_owner_decision": {},
            }]

        def get_full_task(self, requested_task_id):
            assert requested_task_id == task_id
            return {
                "task_id": task_id,
                "description": "Create README.md",
                "status": "completed",
                "project_dir": str(tmp_path),
                "task_types": ["artifact"],
                "delivery_mode": "artifact",
                "subtasks": [],
                "waves": [],
                "artifact_records": [],
                "acceptance_records": [],
                "last_owner_decision": {},
                "created_at": 1.0,
                "updated_at": 2.0,
            }

    class FakeState:
        _persistence = FakePersistence()

        def get_all_tasks(self):
            return []

    monkeypatch.setattr(api_server, "_task_state", FakeState())

    result = asyncio.run(api_server.list_tasks())

    assert len(result) == 1
    assert result[0].task_id == task_id
    assert result[0].status == "completed"


def test_task_page_route_returns_lightweight_summaries(monkeypatch, tmp_path):
    import asyncio
    import across_agents_assistant.api_server as api_server

    class FakePersistence:
        def get_task_summaries(self, *, limit=50, offset=0):
            assert limit == 50
            assert offset == 0
            return ([{
                "task_id": "task-page-1",
                "description": "Task page summary",
                "status": "completed",
                "progress": 1.0,
                "completed_count": 2,
                "total_count": 2,
                "created_at": 1.0,
                "updated_at": 2.0,
                "project_dir": str(tmp_path),
                "owner_agent": "auto",
                "delivery_mode": "artifact",
            }], 1)

        def get_full_task(self, _task_id):
            raise AssertionError("task page must not hydrate full task details")

    class FakeState:
        _persistence = FakePersistence()

        def get_all_tasks(self):
            return []

    monkeypatch.setattr(api_server, "_task_state", FakeState())

    result = asyncio.run(api_server.list_task_summaries())

    assert result.total == 1
    assert result.has_more is False
    assert result.tasks[0].task_id == "task-page-1"


def test_task_page_route_normalizes_passed_delivery_progress(monkeypatch, tmp_path):
    import asyncio
    import across_agents_assistant.api_server as api_server

    class FakePersistence:
        def get_task_summaries(self, *, limit=50, offset=0):
            return ([{
                "task_id": "task-page-quality-passed",
                "description": "Quality passed after remediation",
                "status": "completed",
                "progress": 0.2,
                "completed_count": 1,
                "total_count": 5,
                "created_at": 1.0,
                "updated_at": 2.0,
                "project_dir": str(tmp_path),
                "owner_agent": "owner",
                "delivery_mode": "functional",
                "last_owner_decision": {
                    "delivery_quality": {
                        "delivery_quality": "passed",
                        "produced_required": ["index.html", "styles.css", "app.js", "README.md"],
                    },
                },
            }], 1)

        def get_full_task(self, _task_id):
            raise AssertionError("task page must not hydrate full task details")

    class FakeState:
        _persistence = FakePersistence()

        def get_all_tasks(self):
            return []

    monkeypatch.setattr(api_server, "_task_state", FakeState())

    result = asyncio.run(api_server.list_task_summaries())

    assert result.tasks[0].status == "completed"
    assert result.tasks[0].progress == 1.0
    assert result.tasks[0].completed_count == 5
    assert result.tasks[0].total_count == 5


def test_task_stream_replays_persisted_task_snapshot(monkeypatch, tmp_path):
    import asyncio
    import json
    import across_agents_assistant.api_server as api_server

    task_id = "task-history-stream"

    class FakePersistence:
        def get_full_task(self, requested_task_id):
            assert requested_task_id == task_id
            return {
                "task_id": task_id,
                "description": "Historical task",
                "status": "completed",
                "project_dir": str(tmp_path),
                "task_types": ["functional"],
                "delivery_mode": "functional",
                "subtasks": [{
                    "subtask_id": "st-main",
                    "description": "Implement",
                    "agent_id": "local",
                    "status": "completed",
                    "progress": 1.0,
                    "dependencies": [],
                    "wave_number": 1,
                }],
                "waves": [{
                    "wave_id": "wave-1",
                    "wave_number": 1,
                    "status": "completed",
                    "is_blocked": False,
                }],
                "artifact_records": [],
                "acceptance_records": [],
                "last_owner_decision": {},
                "created_at": 1.0,
                "updated_at": 2.0,
            }

    class FakeState:
        _persistence = FakePersistence()

        def get_task(self, requested_task_id):
            assert requested_task_id == task_id
            return None

    async def read_events(response):
        events = []
        async for chunk in response.body_iterator:
            text = chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
            for line in text.splitlines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))
        return events

    monkeypatch.setattr(api_server, "_task_state", FakeState())
    monkeypatch.setattr(api_server, "_repair_task_dispatch_if_possible", lambda *args, **kwargs: None)

    response = asyncio.run(api_server.task_stream(task_id))
    events = asyncio.run(read_events(response))

    assert response.status_code == 200
    assert events[0]["type"] == "task_status_changed"
    assert events[0]["task_id"] == task_id
    assert events[0]["status"] == "completed"
    assert events[0]["subtasks"][0]["subtask_id"] == "st-main"
    assert events[-1] == {"type": "task_completed", "taskId": task_id}


def test_task_stream_unknown_task_still_returns_404(monkeypatch):
    import asyncio
    import across_agents_assistant.api_server as api_server

    class FakePersistence:
        def get_full_task(self, _task_id):
            return None

    class FakeState:
        _persistence = FakePersistence()

        def get_task(self, _task_id):
            return None

    monkeypatch.setattr(api_server, "_task_state", FakeState())
    monkeypatch.setattr(api_server, "_repair_task_dispatch_if_possible", lambda *args, **kwargs: None)

    with pytest.raises(api_server.HTTPException) as exc:
        asyncio.run(api_server.task_stream("task-missing"))

    assert exc.value.status_code == 404


def test_sessions_route_supports_pagination_metadata(monkeypatch):
    import asyncio
    import across_agents_assistant.api_server as api_server

    class FakePersistence:
        def list_sessions(self, *, limit=50, offset=0):
            assert limit == 2
            assert offset == 1
            return ([{
                "session_id": "sess-2",
                "created_at": "1.0",
                "updated_at": "2.0",
                "message_count": 3,
                "name": "Second",
                "first_user_message": "hello",
            }], 3)

    monkeypatch.setattr(api_server, "persistence", FakePersistence())

    result = asyncio.run(api_server.list_sessions(limit=2, offset=1))
    payload = result.model_dump() if hasattr(result, "model_dump") else result.dict()

    assert payload["total"] == 3
    assert payload["limit"] == 2
    assert payload["offset"] == 1
    assert payload["has_more"] is True
    assert payload["sessions"][0]["session_id"] == "sess-2"


def test_task_info_exposes_delivery_contract_and_task_types():
    class FakePersistence:
        def __init__(self):
            self.delivery_contracts = {}
        def save_task(self, _task):
            pass
        def get_artifact_records(self, _task_id):
            return []
        def get_acceptance_records(self, _task_id):
            return []
        def get_requirement_manifest(self, _task_id):
            return None
        def save_delivery_contract(self, contract):
            self.delivery_contracts[contract["task_id"]] = dict(contract)
        def get_delivery_contract(self, task_id):
            return self.delivery_contracts.get(task_id)

    state = TaskState()
    state.set_persistence(FakePersistence())
    task = state.create_task(
        "Build a todo tool",
        project_dir="/tmp/project",
        task_types=["functional", "artifact"],
        delivery_mode="composite",
    )
    state.save_delivery_contract({
        "contract_id": "delivery-contract-api",
        "task_id": task.task_id,
        "task_types": ["functional", "artifact"],
        "delivery_mode": "composite",
        "project_dir": "/tmp/project",
        "capabilities": [],
        "deliverables": [],
        "constraints": [],
        "acceptance_probes": [],
        "assumptions": [],
        "created_at": 1.0,
        "updated_at": 1.0,
    })

    info = _task_to_info(task, state)
    payload = info.model_dump() if hasattr(info, "model_dump") else info.dict()

    assert payload["task_types"] == ["functional", "artifact"]
    assert payload["delivery_mode"] == "composite"
    assert payload["owner_delivery_contract"]["contract_id"] == "delivery-contract-api"


def test_task_info_artifacts_include_client_aliases(tmp_path):
    class FakePersistence:
        def __init__(self):
            self.artifacts = []
        def save_artifact_record(self, record):
            self.artifacts.append(dict(record))
        def get_artifact_records(self, _task_id):
            return list(self.artifacts)
        def save_task(self, _t):
            pass
        def save_subtask(self, _st):
            pass
        def save_job(self, _j):
            pass
        def get_requirement_manifest(self, _tid):
            return None
        def save_requirement_manifest(self, _m):
            pass

    state = TaskState()
    state.set_persistence(FakePersistence())
    task = state.create_task("Create main.py", project_dir=str(tmp_path))

    file_path = tmp_path / "main.py"
    file_path.write_text("print('hello')\n")

    artifact = Artifact(
        artifact_id="art-1",
        artifact_type="job_output",
        produced_by="deepseek",
        task_id=task.task_id,
        subtask_id="st-main",
        content_ref=str(file_path),
        name="main.py",
        metadata={"file_size": "10 B", "normalized_content_ref": str(file_path)},
    )
    from across_agents_assistant.task_history.models import JobStatus
    artifact.status = JobStatus.COMPLETED.value
    state.save_artifact_record(artifact)

    info = _task_to_info(task, state)
    payload = info.model_dump() if hasattr(info, "model_dump") else info.dict()
    arts = payload.get("artifacts", [])
    assert len(arts) >= 1, f"No artifacts found in: {list(payload.keys())}"
    art = arts[0]
    assert art["id"] == "art-1"
    assert art["file_name"] == "main.py"
    assert art["file_path"].endswith("main.py")
    assert art["name"] == "main.py"
    assert art["artifact_id"] == "art-1"
    assert art["content_ref"].endswith("main.py")


def test_task_info_from_db_waiting_for_keys_has_quality_health():
    from across_agents_assistant.api_server import _task_info_from_db

    task_dict = {
        "task_id": "task-db-waiting",
        "description": "waiting task",
        "status": "pending",
        "error": "Waiting for API keys to sync before resuming decomposition.",
        "last_owner_decision": {
            "blocked_reason": "waiting_for_keys",
            "recoverable": True,
            "next_repair_action": "keys_synced",
        },
        "subtasks": [
            {
                "subtask_id": "task-db-waiting-decompose",
                "description": "decompose",
                "agent_id": "owner",
                "status": "pending",
                "wave_number": 0,
                "dependencies": [],
            }
        ],
        "waves": [
            {
                "wave_id": "wave-0",
                "wave_number": 0,
                "status": "pending",
                "governance_status": "not_applicable",
                "is_blocked": False,
            }
        ],
        "requirement_manifest": {
            "task_id": "task-db-waiting",
            "deliverables": [],
        },
        "task_types": ["functional"],
        "delivery_mode": "functional",
        "owner_delivery_contract": {
            "contract_id": "delivery-contract-db",
            "task_id": "task-db-waiting",
            "task_types": ["functional"],
            "delivery_mode": "functional",
        },
        "acceptance_records": [],
    }

    info = _task_info_from_db(task_dict)
    payload = info.model_dump() if hasattr(info, "model_dump") else info.dict()

    assert payload["status"] == "pending"
    assert payload["quality_health"]["readiness_blockers"] == ["api_keys"]
    assert payload["quality_health"]["quality_gate"] == "waiting"
    assert payload["quality_health"]["next_repair_action"] == "keys_synced"
    assert payload["quality_health"]["blocked_by_decomposition"] == ["task-db-waiting-decompose"]
    assert payload["task_types"] == ["functional"]
    assert payload["delivery_mode"] == "functional"
    assert payload["owner_delivery_contract"]["contract_id"] == "delivery-contract-db"


def test_task_info_from_db_manifest_missing_has_failed_quality_gate():
    from across_agents_assistant.api_server import _task_info_from_db

    task_dict = {
        "task_id": "task-db-quality",
        "description": "quality task",
        "status": "running",
        "last_owner_decision": {},
        "subtasks": [
            {
                "subtask_id": "st-main",
                "description": "create files",
                "agent_id": "local",
                "status": "completed",
                "wave_number": 1,
                "dependencies": [],
            }
        ],
        "waves": [
            {
                "wave_id": "wave-1",
                "wave_number": 1,
                "status": "completed",
                "governance_status": "approved",
                "is_blocked": False,
            }
        ],
        "requirement_manifest": {
            "task_id": "task-db-quality",
            "deliverables": [
                {"requirement_id": "req-main", "path_hint": "main.py", "required": True, "status": "accepted"},
                {"requirement_id": "req-readme", "path_hint": "README.md", "required": True, "status": "missing"},
            ],
        },
        "acceptance_records": [],
    }

    info = _task_info_from_db(task_dict)
    payload = info.model_dump() if hasattr(info, "model_dump") else info.dict()

    assert payload["requirement_manifest"]["deliverables"][1]["status"] == "missing"
    assert payload["quality_health"]["manifest_total"] == 2
    assert payload["quality_health"]["manifest_missing"] == 1
    assert payload["quality_health"]["quality_gate"] == "failed"
    assert payload["quality_health"]["next_repair_action"] == "quality_remediation"


def test_task_info_from_db_active_quality_remediation_is_awaited():
    from across_agents_assistant.api_server import _task_info_from_db

    task_dict = {
        "task_id": "task-db-quality-active",
        "description": "quality remediation active",
        "status": "running",
        "last_owner_decision": {
            "quality_remediation_attempts": {"req-readme": 1},
        },
        "subtasks": [
            {
                "subtask_id": "st-main",
                "description": "create files",
                "agent_id": "local",
                "status": "completed",
                "wave_number": 1,
                "dependencies": [],
            },
            {
                "subtask_id": "st-quality-1234",
                "description": "repair README.md",
                "agent_id": "local",
                "status": "running",
                "wave_number": 1,
                "dependencies": [],
            },
        ],
        "waves": [
            {
                "wave_id": "wave-1",
                "wave_number": 1,
                "status": "running",
                "governance_status": "approved",
                "is_blocked": False,
            }
        ],
        "requirement_manifest": {
            "task_id": "task-db-quality-active",
            "deliverables": [
                {"requirement_id": "req-readme", "path_hint": "README.md", "required": True, "status": "missing"},
            ],
        },
        "acceptance_records": [],
    }

    info = _task_info_from_db(task_dict)
    payload = info.model_dump() if hasattr(info, "model_dump") else info.dict()

    assert payload["quality_health"]["quality_gate"] == "failed"
    assert payload["quality_health"]["active_quality_remediation"] == ["st-quality-1234"]
    assert payload["quality_health"]["next_repair_action"] == "await_quality_remediation"
    assert payload["delivery_report"]["remediation"]["active_subtasks"] == ["st-quality-1234"]
    assert payload["delivery_report"]["next_action"] == "await_quality_remediation"


def test_persistence_full_task_includes_requirement_manifest_for_db_quality_health(tmp_path):
    from across_agents_assistant.api_server import _task_info_from_db
    from across_agents_assistant.persistence.database import Database
    from across_agents_assistant.persistence.task_persistence import TaskPersistenceService

    db = Database(str(tmp_path / "assistant.db"))
    db.init_schema()
    persistence = TaskPersistenceService(db)

    task_id = "task-persisted-quality"
    persistence.save_task({
        "task_id": task_id,
        "description": "persisted quality gate",
        "status": "running",
        "project_dir": str(tmp_path),
        "last_owner_decision": {},
    })
    persistence.save_subtask({
        "subtask_id": "st-main",
        "task_id": task_id,
        "description": "produce files",
        "agent_id": "local",
        "status": "completed",
        "wave_number": 1,
        "dependencies": [],
    })
    persistence.save_wave({
        "wave_id": "wave-1",
        "task_id": task_id,
        "wave_number": 1,
        "status": "completed",
        "governance_status": "approved",
    })
    persistence.save_requirement_manifest({
        "manifest_id": "manifest-persisted-quality",
        "task_id": task_id,
        "project_dir": str(tmp_path),
        "deliverables": [
            {"requirement_id": "req-main", "path_hint": "main.py", "required": True, "status": "accepted"},
            {"requirement_id": "req-readme", "path_hint": "README.md", "required": True, "status": "missing"},
        ],
        "quality_checks": [],
        "created_at": 1.0,
        "updated_at": 1.0,
    })

    full_task = persistence.get_full_task(task_id)
    assert full_task["requirement_manifest"]["deliverables"][1]["status"] == "missing"

    info = _task_info_from_db(full_task)
    payload = info.model_dump() if hasattr(info, "model_dump") else info.dict()

    assert payload["requirement_manifest"]["task_id"] == task_id
    assert payload["quality_health"]["manifest_total"] == 2
    assert payload["quality_health"]["manifest_missing"] == 1
    assert payload["quality_health"]["quality_gate"] == "failed"


def test_persistence_round_trips_delivery_contract_v2_fields(tmp_path):
    from across_agents_assistant.persistence.database import Database
    from across_agents_assistant.persistence.task_persistence import TaskPersistenceService

    db = Database(str(tmp_path / "assistant.db"))
    db.init_schema()
    persistence = TaskPersistenceService(db)

    task_id = "task-contract-v2"
    persistence.save_task({
        "task_id": task_id,
        "description": "contract v2",
        "status": "running",
        "project_dir": str(tmp_path),
    })
    persistence.save_delivery_contract({
        "contract_id": "delivery-contract-v2",
        "contract_version": "2.0",
        "task_id": task_id,
        "task_types": ["functional", "artifact"],
        "delivery_mode": "composite",
        "delivery_facets": ["source_project", "web_ui"],
        "technology_hypotheses": [{"stack": "native-web", "confidence": 0.8, "signals": ["HTML"]}],
        "capabilities": [{"id": "cap-frontend-loads", "required": True}],
        "deliverables": [],
        "deliverable_groups": [{"id": "group-web-ui", "kind": "frontend_source", "required": True}],
        "constraints": [],
        "acceptance_probes": [{"id": "probe-smoke", "probe_type": "static_web_smoke", "required": True}],
        "gate_plan": [{"id": "gate-browser-e2e", "gate_type": "browser_e2e", "required": False}],
        "assumptions": [],
        "project_dir": str(tmp_path),
        "created_at": 1.0,
        "updated_at": 2.0,
    })

    contract = persistence.get_delivery_contract(task_id)
    assert contract["contract_version"] == "2.0"
    assert contract["delivery_facets"] == ["source_project", "web_ui"]
    assert contract["technology_hypotheses"][0]["stack"] == "native-web"
    assert contract["deliverable_groups"][0]["id"] == "group-web-ui"
    assert contract["gate_plan"][0]["id"] == "gate-browser-e2e"

    full_task = persistence.get_full_task(task_id)
    assert full_task["owner_delivery_contract"]["deliverable_groups"][0]["id"] == "group-web-ui"


def test_task_summaries_use_business_subtask_counts(tmp_path):
    from across_agents_assistant.persistence.database import Database
    from across_agents_assistant.persistence.task_persistence import TaskPersistenceService

    db = Database(str(tmp_path / "assistant.db"))
    db.init_schema()
    persistence = TaskPersistenceService(db)

    task_id = "task-summary-counts"
    persistence.save_task({
        "task_id": task_id,
        "description": "summary counts",
        "status": "running",
        "progress": 0.99,
        "completed_count": 99,
        "total_count": 99,
        "created_at": 1.0,
        "updated_at": 2.0,
    })
    for subtask_id, status in [
        ("task-summary-counts-decompose", "completed"),
        ("st-main-a", "completed"),
        ("st-main-b", "failed"),
        ("st-main-b-fix-1", "completed"),
        ("st-main-b-v2", "completed"),
        ("st-quality-1234", "completed"),
        ("task-summary-counts-integration-fix-1", "completed"),
    ]:
        persistence.save_subtask({
            "subtask_id": subtask_id,
            "task_id": task_id,
            "description": subtask_id,
            "agent_id": "local",
            "status": status,
            "dependencies": [],
            "created_at": 1.0,
        })

    rows, total = persistence.get_task_summaries(limit=50, offset=0)

    assert total == 1
    assert rows[0]["completed_count"] == 1
    assert rows[0]["total_count"] == 2
    assert rows[0]["progress"] == 0.5


def test_db_quality_health_derives_delivery_quality_from_owner_contract(tmp_path):
    from across_agents_assistant.api_server import _build_quality_health_from_db

    (tmp_path / "README.md").write_text("# Done\n", encoding="utf-8")
    task_dict = {
        "task_id": "task-db-odc",
        "description": "Build README.md",
        "status": "completed",
        "project_dir": str(tmp_path),
        "last_owner_decision": {},
        "requirement_manifest": {
            "deliverables": [{"path_hint": "README.md", "required": True, "status": "produced"}]
        },
        "owner_delivery_contract": {
            "contract_id": "delivery-contract-db-fallback",
            "task_id": "task-db-odc",
            "task_types": ["artifact"],
            "delivery_mode": "artifact",
            "project_dir": str(tmp_path),
            "capabilities": [],
            "deliverables": [{"path_hint": "README.md", "artifact_type": "documentation", "required": True}],
            "constraints": [],
            "acceptance_probes": [],
        },
        "subtasks": [],
        "waves": [],
        "artifact_records": [],
        "acceptance_records": [],
    }

    health = _build_quality_health_from_db(task_dict)

    assert health["delivery_quality"] == "passed"
    assert health["quality_gate"] == "passed"
    assert health["orchestration_health"] == "healthy"
