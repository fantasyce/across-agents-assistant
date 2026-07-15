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
    assert captured["metadata"] == {"capability_plan": plan}


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
