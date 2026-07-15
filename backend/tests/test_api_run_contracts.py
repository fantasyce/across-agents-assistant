import pytest


def test_orchestrator_plugin_contract_methods_use_http_and_cli_transports(monkeypatch, tmp_path):
    from across_agents_assistant.orchestrator_plugin import OrchestratorPluginConfig, OrchestratorPluginManager

    manager = OrchestratorPluginManager(OrchestratorPluginConfig(
        registry_path=tmp_path / "tasks.json",
        plugin_home=tmp_path / "plugin",
    ))
    calls = []
    manager._transport = "http"
    monkeypatch.setattr(manager, "_http_post", lambda path, payload: calls.append((path, payload)) or {"path": path})
    assert manager.build_execution_policy_contract({"role": "reviewer"})["path"] == "/contracts/execution-policy"
    assert manager.compare_run_snapshots({"baseline": {}, "candidate": {}})["path"] == "/runs/compare"
    assert manager.build_replay_plan({"source": {}})["path"] == "/runs/replay-plan"

    manager._transport = "cli"
    cli_calls = []
    monkeypatch.setattr(manager, "_cli_json", lambda args: cli_calls.append(args) or {"command": args[0]})
    assert manager.build_execution_policy_contract({})["command"] == "execution-policy"
    assert manager.compare_run_snapshots({})["command"] == "run-compare"
    assert manager.build_replay_plan({})["command"] == "replay-plan"
    manager.shutdown()


@pytest.mark.asyncio
async def test_aaa_contract_api_proxies_versioned_orchestrator_results(monkeypatch):
    import across_agents_assistant.api_server as api_server

    class FakeManager:
        def build_execution_policy_contract(self, payload):
            return {"schema_version": "across-execution-policy/1.0", "role": payload["role"]}

        def compare_run_snapshots(self, payload):
            return {"schema_version": "across-run-comparison/1.0", "summary": {"changed": True}}

        def build_replay_plan(self, payload):
            return {
                "schema_version": "across-replay-plan/1.0",
                "status": "blocked",
                "execution": {"performed": False},
                "next_action": "request_new_approval",
            }

    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: FakeManager())

    policy = await api_server.build_external_execution_policy({"role": "reviewer"})
    comparison = await api_server.compare_external_runs({"baseline": {}, "candidate": {}})
    replay = await api_server.build_external_replay_plan({"source": {}, "external_side_effects": ["push"]})

    assert policy["schema_version"] == "across-execution-policy/1.0"
    assert comparison["schema_version"] == "across-run-comparison/1.0"
    assert replay["schema_version"] == "across-replay-plan/1.0"
    assert replay["status"] == "blocked"
    assert replay["execution"]["performed"] is False


@pytest.mark.asyncio
async def test_aaa_replay_proxy_replaces_claimed_receipt_with_verified_local_receipt(monkeypatch, tmp_path):
    import across_agents_assistant.api_server as api_server
    from across_agents_assistant.persistence.service import PersistenceService

    snapshot_sha256 = "c" * 64
    service = PersistenceService(str(tmp_path / "replay-proxy.db"))
    receipt = service.record_approval_receipt(
        subject_type="run_snapshot",
        subject_id="replay:snapshot",
        subject_payload={},
        subject_sha256=snapshot_sha256,
        scope="replay_external_side_effects",
        decision="approved",
        proposer_id="agent-planner",
        approver_id="human-reviewer",
    )
    calls = []

    class FakeManager:
        def build_replay_plan(self, payload):
            calls.append(payload)
            return {"schema_version": "across-replay-plan/1.0", "status": "ready"}

    monkeypatch.setattr(api_server, "persistence", service)
    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: FakeManager())
    forged = {
        "receipt_id": receipt["receipt_id"],
        "integrity_status": "verified",
        "subject_sha256": "f" * 64,
        "decision": "approved",
    }

    await api_server.build_external_replay_plan({
        "source": {"run_id": "run-1"},
        "external_side_effects": ["push"],
        "renewed_approval": forged,
    })
    assert calls[-1]["renewed_approval"] == receipt

    calls.clear()
    await api_server.build_external_replay_plan({
        "source": {"run_id": "run-1"},
        "external_side_effects": ["push"],
        "renewed_approval": {**forged, "receipt_id": "missing-receipt"},
    })
    assert "renewed_approval" not in calls[-1]
