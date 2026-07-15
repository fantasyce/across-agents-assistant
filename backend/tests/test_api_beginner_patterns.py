import hashlib
import json

import pytest


def bounded_result(pattern_id: str, goal: str) -> dict:
    payload = {
        "schema_version": "across-no-key-demo-result/1.0",
        "pattern_id": pattern_id,
        "mission_id": "first_verified_task",
        "run_id": "run-api-fixture-1",
        "status": "completed",
        "verdict": "verified",
        "evidence_route": "run://run-api-fixture-1/evidence",
        "gates": [{"id": "fixture", "status": "passed", "required": True}],
        "policy": {
            "provider_key_used": False,
            "network_used": False,
            "model_calls": 0,
            "external_side_effects_performed": False,
        },
        "evidence_sha256": "a" * 64,
        "goal_sha256": hashlib.sha256(goal.encode("utf-8")).hexdigest(),
        "next_action": "Open the evidence.",
        "next_action_id": "inspect_evidence",
    }
    payload["result_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return payload


def test_autopilot_client_exposes_beginner_patterns_and_project_scoped_no_key_demo(monkeypatch, tmp_path):
    import across_agents_assistant.autopilot_client as client_module

    calls = []

    def fake_cli(args, **kwargs):
        calls.append((args, kwargs))
        if args[0] == "beginner-patterns":
            return {"schema_version": "across-beginner-workflow-pattern-registry/1.0", "patterns": []}
        if args[1] == "demo":
            return {"schema_version": "across-no-key-demo/1.0", "pattern_id": args[3]}
        return {
            "schema_version": "across-no-key-demo-result/1.0",
            "status": "completed",
            "policy": {"model_calls": 0, "network_used": False},
        }

    monkeypatch.setattr(client_module, "run_autopilot_cli_json", fake_cli)
    client = client_module.AutopilotClient(env={})

    assert client.beginner_patterns()["schema_version"] == "across-beginner-workflow-pattern-registry/1.0"
    assert client.no_key_demo()["schema_version"] == "across-no-key-demo/1.0"
    result = client.run_no_key_demo(
        str(tmp_path),
        "first-verified-task",
        user_goal="Explain the safest next step",
    )

    assert result["status"] == "completed"
    assert calls[-1][0] == [
        "beginner-pattern",
        "run",
        "--pattern",
        "first-verified-task",
        "--goal",
        "Explain the safest next step",
        "--json",
    ]
    assert calls[-1][1]["cwd"] == tmp_path.resolve()
    assert calls[-1][1]["allowed_returncodes"] == frozenset({0, 1})


def test_no_key_demo_returns_attention_result_instead_of_transport_error(monkeypatch, tmp_path):
    import across_agents_assistant.autopilot_client as client_module

    def fake_cli(args, **kwargs):
        assert kwargs["allowed_returncodes"] == frozenset({0, 1})
        return {
            "schema_version": "across-no-key-demo-result/1.0",
            "status": "failed",
            "verdict": "needs_attention",
            "gates": [{"id": "manifest_readable", "status": "failed", "required": True}],
        }

    monkeypatch.setattr(client_module, "run_autopilot_cli_json", fake_cli)
    result = client_module.AutopilotClient(env={}).run_no_key_demo(
        str(tmp_path), user_goal="Find the first risky gap"
    )

    assert result["status"] == "failed"
    assert result["verdict"] == "needs_attention"


@pytest.mark.asyncio
async def test_aaa_beginner_pattern_api_keeps_demo_zero_key_and_read_only(monkeypatch, tmp_path):
    import across_agents_assistant.api_server as api_server

    class FakeClient:
        def beginner_patterns(self):
            return {
                "schema_version": "across-beginner-workflow-pattern-registry/1.0",
                "status": "ready",
                "patterns": [{"id": "first-verified-task", "valid": True}],
            }

        def no_key_demo(self, pattern_id):
            return {
                "schema_version": "across-no-key-demo/1.0",
                "pattern_id": pattern_id,
                "requirements": {"provider_key": False, "network": False, "model_calls": 0},
            }

        def run_no_key_demo(self, project_root, pattern_id, *, user_goal):
            assert project_root == str(tmp_path.resolve())
            assert user_goal == "Tell me whether this project is ready"
            return bounded_result(pattern_id, user_goal)

    monkeypatch.setattr(api_server, "get_autopilot_client", lambda: FakeClient())

    registry = await api_server.get_beginner_workflow_patterns()
    demo = await api_server.get_no_key_demo()
    result = await api_server.run_no_key_demo(
        api_server.BeginnerNoKeyDemoRequest(
            project_dir=str(tmp_path),
            user_goal="  Tell me whether this project is ready  ",
        )
    )

    assert registry["status"] == "ready"
    assert demo["requirements"]["provider_key"] is False
    assert result["status"] == "completed"
    assert result["goal_sha256"] == hashlib.sha256(
        b"Tell me whether this project is ready"
    ).hexdigest()
    assert result["next_action_id"] == "inspect_evidence"
    assert result["policy"] == {
        "provider_key_used": False,
        "network_used": False,
        "model_calls": 0,
        "external_side_effects_performed": False,
    }


def test_beginner_request_rejects_blank_goal(tmp_path):
    from pydantic import ValidationError

    import across_agents_assistant.api_server as api_server

    with pytest.raises(ValidationError):
        api_server.BeginnerNoKeyDemoRequest(project_dir=str(tmp_path), user_goal=" \n ")


def test_beginner_request_rejects_missing_project_directory(tmp_path):
    from pydantic import ValidationError

    import across_agents_assistant.api_server as api_server

    with pytest.raises(ValidationError):
        api_server.BeginnerNoKeyDemoRequest(
            project_dir=str(tmp_path / "missing"),
            user_goal="Inspect this project safely",
        )


@pytest.mark.asyncio
async def test_beginner_api_rejects_result_not_bound_to_the_requested_goal(monkeypatch, tmp_path):
    import across_agents_assistant.api_server as api_server

    class FakeClient:
        def run_no_key_demo(self, project_root, pattern_id, *, user_goal):
            return {
                "schema_version": "across-no-key-demo-result/1.0",
                "pattern_id": pattern_id,
                "goal_sha256": "0" * 64,
                "next_action_id": "inspect_evidence",
            }

    monkeypatch.setattr(api_server, "get_autopilot_client", lambda: FakeClient())

    with pytest.raises(api_server.HTTPException) as raised:
        await api_server.run_no_key_demo(
            api_server.BeginnerNoKeyDemoRequest(
                project_dir=str(tmp_path),
                user_goal="My actual goal",
            )
        )

    assert raised.value.status_code == 502


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ("result_hash", "evidence_route", "network_policy"))
async def test_beginner_api_rejects_tampered_compact_result_envelope(
    monkeypatch,
    tmp_path,
    mutation,
):
    import across_agents_assistant.api_server as api_server

    goal = "Inspect this project safely"
    payload = bounded_result("first-verified-task", goal)
    if mutation == "result_hash":
        payload["result_sha256"] = "0" * 64
    elif mutation == "evidence_route":
        payload["evidence_route"] = "run://another-run/evidence"
    else:
        payload["policy"]["network_used"] = True

    class FakeClient:
        def run_no_key_demo(self, project_root, pattern_id, *, user_goal):
            return payload

    monkeypatch.setattr(api_server, "get_autopilot_client", lambda: FakeClient())

    with pytest.raises(api_server.HTTPException) as raised:
        await api_server.run_no_key_demo(
            api_server.BeginnerNoKeyDemoRequest(
                project_dir=str(tmp_path),
                user_goal=goal,
            )
        )

    assert raised.value.status_code == 502
