from types import SimpleNamespace

from fastapi.testclient import TestClient

import across_agents_assistant.api_server as api_server
from across_agents_assistant.api_server import app
from across_agents_assistant.capability_planner import build_task_capability_plan


def _plugin(plugin_id, *, capabilities, permissions=None, trust="verified"):
    return {
        "plugin_id": plugin_id,
        "display_name": plugin_id,
        "installed": True,
        "integrity_ok": True,
        "capabilities": capabilities,
        "permissions": permissions or {"filesystem": "read"},
        "trust": {"level": trust},
        "health": {"status": "ready"},
    }


def test_automatic_capability_plan_has_zero_user_decisions(monkeypatch):
    plugins = [_plugin("code-runtime", capabilities=[{"id": "task_execution"}])]
    monkeypatch.setattr(api_server, "discover_across_plugins", lambda **_: plugins)
    monkeypatch.setattr(api_server, "_known_provider_ids", lambda: ("openai",))
    monkeypatch.setattr(api_server, "_provider_has_backend_key", lambda provider_id: provider_id == "openai")
    monkeypatch.setattr(api_server, "load_llm_config", lambda: SimpleNamespace(primary_provider="openai"))

    response = TestClient(app).post(
        "/api/tasks/capability-plan",
        json={"user_goal": "Implement and test the requested code change", "project_signals": {}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "across-task-capability-plan/1.0"
    assert body["chosen_capabilities"][0]["capability"] == "task_execution"
    assert body["chosen_providers"] == ["openai"]
    assert body["required_user_decisions"] == []
    assert body["automatic"] is True


def test_ambiguous_capability_plan_requires_only_provider_selection():
    plugins = [
        _plugin("review-a", capabilities=["repository_review"]),
        _plugin("review-b", capabilities=["repository_review"]),
    ]

    plan = build_task_capability_plan(
        user_goal="Review this repository",
        project_signals={"required_capabilities": ["repository_review"]},
        plugins=plugins,
        configured_providers=["openai"],
        primary_provider="openai",
    )

    assert plan["chosen_capabilities"] == []
    assert [item["kind"] for item in plan["required_user_decisions"]] == ["ambiguous_capability"]
    assert plan["automatic"] is False


def test_risky_capability_plan_requires_explicit_approval():
    plugins = [
        _plugin(
            "deploy-runtime",
            capabilities=["deployment"],
            permissions={"filesystem": "write", "network": True, "execute": True},
        )
    ]

    plan = build_task_capability_plan(
        user_goal="Deploy this release to production",
        project_signals={"required_capabilities": ["deployment"]},
        plugins=plugins,
        configured_providers=["openai"],
        primary_provider="openai",
    )

    assert plan["chosen_capabilities"][0]["plugin_id"] == "deploy-runtime"
    assert [item["kind"] for item in plan["required_user_decisions"]] == ["risk_approval"]
    assert plan["automatic"] is False


def test_release_domain_language_does_not_imply_external_publication():
    plugins = [
        _plugin(
            "task-runtime",
            capabilities=["task_execution", "quality_gates"],
            permissions={"filesystem": "write", "execute": True},
        )
    ]

    plan = build_task_capability_plan(
        user_goal="Improve the accessible release dashboard and run its tests",
        project_signals={},
        plugins=plugins,
        configured_providers=["openai"],
        primary_provider="openai",
    )

    assert plan["required_user_decisions"] == []
    assert plan["automatic"] is True


def test_auto_task_forwards_automatic_capability_plan_as_metadata(monkeypatch, tmp_path):
    captured = {}
    plan = {
        "schema_version": "across-task-capability-plan/1.0",
        "goal": "Build the feature",
        "chosen_capabilities": [{"capability": "task_execution", "plugin_id": "across-orchestrator"}],
        "chosen_providers": ["openai"],
        "hidden_defaults": {},
        "required_user_decisions": [],
        "automatic": True,
    }

    class FakePlugin:
        def implementation_status(self, probe=True):
            return {"implementation": "external", "available": True}

        def submit_task(self, *, metadata=None, **kwargs):
            captured["metadata"] = metadata
            return {"task_id": "task-capability-plan", "status": "pending"}

    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: FakePlugin())
    monkeypatch.setattr(api_server, "_derive_auto_task_capability_plan", lambda req, **_: plan)

    response = TestClient(app).post(
        "/api/tasks/auto",
        json={
            "description": "Build the feature",
            "task_types": ["functional"],
            "project_dir": str(tmp_path),
        },
    )

    assert response.status_code == 200
    assert captured["metadata"]["capability_plan"] == plan
    assert captured["metadata"]["project_signals"] == {}
    assert captured["metadata"]["execution_contract"] == {
        "workflow_id": None,
        "route": "local",
        "phases": ["local-run"],
    }


def test_missing_autopilot_keeps_generic_orchestrator_tasks_usable(monkeypatch, tmp_path):
    captured = {}

    class MissingAutopilot:
        def resolve_workflow(self, goal, *, requested_workflow_id=None):
            raise OSError("Autopilot is not installed")

    class FakePlugin:
        def implementation_status(self, probe=True):
            return {"implementation": "external", "available": True}

        def submit_task(self, *, metadata=None, **kwargs):
            captured["metadata"] = metadata
            captured["submission"] = kwargs
            return {"task_id": "task-generic-without-autopilot", "status": "pending"}

    monkeypatch.setattr(api_server, "get_autopilot_client", lambda: MissingAutopilot())
    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: FakePlugin())
    monkeypatch.setattr(api_server, "discover_across_plugins", lambda **_: [])
    monkeypatch.setattr(api_server, "_known_provider_ids", lambda: ("openai",))
    monkeypatch.setattr(api_server, "_provider_has_backend_key", lambda provider_id: provider_id == "openai")
    monkeypatch.setattr(api_server, "load_llm_config", lambda: SimpleNamespace(primary_provider="openai"))

    response = TestClient(app).post(
        "/api/tasks/auto",
        json={
            "description": "Review this project and write README.md",
            "task_types": ["functional", "artifact"],
            "project_dir": str(tmp_path),
        },
    )

    assert response.status_code == 200
    assert response.json()["task_id"] == "task-generic-without-autopilot"
    assert captured["metadata"]["workflow_resolution"]["resolution_status"] == "unavailable"
    assert captured["metadata"]["capability_plan"]["workflow_status"]["status"] == "unavailable"
    assert captured["metadata"]["execution_contract"] == {
        "workflow_id": None,
        "route": "local",
        "phases": ["local-run"],
    }
    assert captured["submission"]["agent"] == "demo"


def test_explicit_workflow_requires_autopilot_instead_of_silent_generic_fallback(monkeypatch, tmp_path):
    submitted = False

    class MissingAutopilot:
        def resolve_workflow(self, goal, *, requested_workflow_id=None):
            raise OSError("Autopilot is not installed")

    class FakePlugin:
        def implementation_status(self, probe=True):
            return {"implementation": "external", "available": True}

        def submit_task(self, **kwargs):
            nonlocal submitted
            submitted = True
            return {"task_id": "unexpected", "status": "pending"}

    monkeypatch.setattr(api_server, "get_autopilot_client", lambda: MissingAutopilot())
    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: FakePlugin())
    monkeypatch.setattr(api_server, "discover_across_plugins", lambda **_: [])
    monkeypatch.setattr(api_server, "_known_provider_ids", lambda: ("openai",))
    monkeypatch.setattr(api_server, "_provider_has_backend_key", lambda provider_id: provider_id == "openai")
    monkeypatch.setattr(api_server, "load_llm_config", lambda: SimpleNamespace(primary_provider="openai"))

    response = TestClient(app).post(
        "/api/tasks/auto",
        json={
            "description": "Run the selected repository review pack",
            "task_types": ["functional", "artifact"],
            "project_dir": str(tmp_path),
            "project_signals": {"requested_workflow_id": "repo-quality-copilot"},
        },
    )

    assert response.status_code == 412
    assert response.json()["detail"]["code"] == "capability_decision_required"
    assert response.json()["detail"]["decision_ids"] == ["install_requested_workflow"]
    assert submitted is False


def test_generic_task_goal_can_resolve_and_dispatch_a_worker_workflow(monkeypatch, tmp_path):
    captured = {}
    resolution = {
        "schema_version": "across-workflow-resolution/1.0",
        "goal": "Explore a bounded interaction and return a report",
        "automatic": True,
        "selected_workflow": {
            "id": "remote-analysis-pack",
            "title": "Remote Analysis",
            "user_summary": "Explore the bounded interaction and return reviewable evidence.",
            "confidence": 0.92,
            "reason": "The task requests a bounded multi-subject analysis.",
            "execution": {
                "route": "worker",
                "phases": ["local-plan", "remote-run", "local-verify"],
            },
        },
        "candidates": [],
    }
    job_plan = {
        "schema_version": "across-workflow-worker-job-plan/1.0",
        "expected_outputs": ["report.md", "evidence.json"],
    }
    execution_plan = {
        "schema_version": "across-workflow-execution-plan/1.0",
        "workflow_id": "remote-analysis-pack",
        "execution_contract": {
            "route": "worker",
            "phases": ["local-plan", "remote-run", "local-verify"],
            "generated_by": "across-autopilot",
        },
        "deliverables": ["report.md", "evidence.json"],
        "subtasks": [{
            "id": "worker-execution",
            "description": "Execute the selected workflow on an approved Worker and return verified evidence.",
            "path": "report.md",
            "agent": "across-worker",
            "wave": 1,
            "priority": 1,
            "dependencies": [],
        }],
        "adapter": {"type": "worker"},
        "worker_job_plan": job_plan,
    }
    capability_plan = {
        "schema_version": "across-task-capability-plan/1.0",
        "goal": resolution["goal"],
        "chosen_capabilities": [],
        "chosen_providers": ["openai"],
        "hidden_defaults": {},
        "required_user_decisions": [],
        "automatic": True,
    }

    class FakeAutopilot:
        def resolve_workflow(self, goal, *, requested_workflow_id=None):
            captured["resolved_goal"] = goal
            captured["requested_workflow_id"] = requested_workflow_id
            return resolution

        def build_execution_plan(self, **kwargs):
            captured["execution_plan_request"] = kwargs
            return execution_plan

    class FakeBridge:
        def submit_workflow(self, **kwargs):
            captured["worker_submission"] = kwargs
            return {"job_id": "job-remote-analysis", "status": "queued"}

    class FakePlugin:
        def implementation_status(self, probe=True):
            return {"implementation": "external", "available": True}

        def submit_task(self, *, metadata=None, **kwargs):
            captured["metadata"] = metadata
            captured["parent_submission"] = kwargs
            return {"task_id": "task-generic-worker", "status": "pending"}

    monkeypatch.setattr(api_server, "get_autopilot_client", lambda: FakeAutopilot())
    monkeypatch.setattr(api_server, "get_worker_task_bridge", lambda: FakeBridge())
    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: FakePlugin())
    monkeypatch.setattr(api_server, "_derive_auto_task_capability_plan", lambda req, **_: capability_plan)

    response = TestClient(app).post(
        "/api/tasks/auto",
        json={
            "description": resolution["goal"],
            "task_types": ["functional", "artifact"],
            "project_dir": str(tmp_path),
        },
    )

    assert response.status_code == 200
    assert response.json()["execution_route"] == "worker"
    assert response.json()["worker_job_id"] == "job-remote-analysis"
    assert captured["requested_workflow_id"] is None
    assert captured["metadata"]["workflow_resolution"] == resolution
    assert captured["metadata"]["execution_contract"]["workflow_id"] == "remote-analysis-pack"
    assert captured["execution_plan_request"]["workflow_id"] == "remote-analysis-pack"
    assert captured["execution_plan_request"]["user_goal"] == resolution["goal"]
    assert captured["execution_plan_request"]["project_id"].startswith("aaa-plan-")
    assert captured["parent_submission"]["deliverables"] == ["report.md", "evidence.json"]
    assert captured["parent_submission"]["agent"] == "across-worker"
    assert captured["parent_submission"]["agent_adapters"] == {}
    assert captured["parent_submission"]["subtasks"] == [{
        "id": "worker-execution",
        "description": "Execute the selected workflow on an approved Worker and return verified evidence.",
        "path": "report.md",
        "agent": "across-worker",
        "wave": 1,
        "priority": 1,
        "dependencies": [],
    }]
    assert captured["worker_submission"]["job_plan"] == job_plan


def test_resolved_local_workflow_uses_autopilot_execution_plan_without_a_ui_preset(monkeypatch, tmp_path):
    across_home = tmp_path / "across-home"
    monkeypatch.setenv("ACROSS_HOME", str(across_home))
    captured = {}
    resolution = {
        "schema_version": "across-workflow-resolution/1.0",
        "goal": "检查这个代码仓库的质量并给出证据报告",
        "automatic": True,
        "selected_workflow": {
            "id": "repo-quality-copilot",
            "title": "Repository Quality Copilot",
            "confidence": 0.93,
            "reason": "Matched repository quality intent.",
            "execution": {"route": "local", "phases": ["local-run"]},
        },
        "candidates": [],
    }
    execution_plan = {
        "schema_version": "across-workflow-execution-plan/1.0",
        "workflow_id": "repo-quality-copilot",
        "execution_contract": {
            "route": "local",
            "phases": ["local-run"],
            "generated_by": "across-autopilot",
        },
        "deliverables": [
            "across-results/repo-quality-copilot/report.md",
            "across-results/repo-quality-copilot/evidence.json",
        ],
        "subtasks": [{
            "id": "workflow-pack-execution",
            "description": "Run the selected Workflow Pack.",
            "path": "across-results/repo-quality-copilot/report.md",
            "agent": "across-autopilot",
            "wave": 1,
            "priority": 1,
            "dependencies": [],
        }],
        "adapter": {
            "type": "autopilot-workflow",
            "workflow_id": "repo-quality-copilot",
            "loop_spec_id": "repo-quality-copilot",
        },
        "worker_job_plan": None,
    }
    capability_plan = {
        "chosen_providers": ["openai"],
        "required_user_decisions": [],
        "automatic": True,
    }

    class FakeAutopilot:
        def resolve_workflow(self, goal, *, requested_workflow_id=None):
            captured["requested_workflow_id"] = requested_workflow_id
            return resolution

        def build_execution_plan(self, **kwargs):
            captured["execution_plan_request"] = kwargs
            return execution_plan

    class FakePlugin:
        def implementation_status(self, probe=True):
            return {"implementation": "external", "available": True}

        def submit_task(self, *, metadata=None, **kwargs):
            captured["metadata"] = metadata
            captured["submission"] = kwargs
            return {"task_id": "task-local-workflow", "status": "pending"}

    monkeypatch.setattr(api_server, "get_autopilot_client", lambda: FakeAutopilot())
    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: FakePlugin())
    monkeypatch.setattr(api_server, "_derive_auto_task_capability_plan", lambda req, **_: capability_plan)

    response = TestClient(app).post(
        "/api/tasks/auto",
        json={
            "description": resolution["goal"],
            "task_types": ["functional", "artifact"],
            "project_dir": str(tmp_path),
        },
    )

    assert response.status_code == 200
    assert response.json()["execution_route"] == "local"
    assert captured["requested_workflow_id"] is None
    assert captured["submission"]["deliverables"] == execution_plan["deliverables"]
    assert captured["submission"]["subtasks"] == execution_plan["subtasks"]
    assert captured["submission"]["agent"] == "across-autopilot"
    adapter = captured["submission"]["agent_adapters"]["across-autopilot"]
    assert adapter["type"] == "command"
    assert "autopilot_workflow_adapter" in " ".join(adapter["command"])
    assert adapter["sandboxPolicy"]["execution"] == {
        "timeout_seconds": 300,
        "refresh_timeout_on_output": True,
        "max_wall_timeout_seconds": 3600,
    }
    assert adapter["sandboxPolicy"]["filesystem_policy"] == {
        "mode": "run_scoped",
        "runtime_state_roots": [
            str(across_home / "data" / "across-autopilot"),
            str(across_home / "data" / "across-context"),
        ],
    }
    assert captured["metadata"]["execution_plan"] == execution_plan


def test_auto_task_rejects_only_required_capability_decisions(monkeypatch):
    submitted = False
    plan = {
        "required_user_decisions": [{
            "id": "approve_risky_capabilities",
            "kind": "risk_approval",
            "required": True,
        }],
    }

    class FakePlugin:
        def implementation_status(self, probe=True):
            return {"implementation": "external", "available": True}

        def submit_task(self, **kwargs):
            nonlocal submitted
            submitted = True
            return {"task_id": "unexpected", "status": "pending"}

    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: FakePlugin())
    monkeypatch.setattr(api_server, "_derive_auto_task_capability_plan", lambda req, **_: plan)

    response = TestClient(app).post(
        "/api/tasks/auto",
        json={"description": "Deploy to production", "task_types": ["functional"]},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "capability_decision_required",
        "decision_ids": ["approve_risky_capabilities"],
    }
    assert submitted is False
