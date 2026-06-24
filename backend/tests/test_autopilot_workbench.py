from across_agents_assistant.autopilot_workbench import (
    WORKBENCH_SCHEMA_VERSION,
    build_autopilot_workbench_snapshot,
)


def _healthy_snapshot():
    return build_autopilot_workbench_snapshot(
        plugins=[
            {"plugin_id": "across-context", "available": True, "installed": True, "status": "installed"},
            {"plugin_id": "across-orchestrator", "available": True, "installed": True, "status": "installed"},
            {"plugin_id": "across-autopilot", "available": True, "installed": True, "status": "installed"},
        ],
        registry={"built_in": [{"id": "aaa-autonomous-self-iteration"}]},
        trigger_queue={"items": []},
        trigger_registry={
            "schema_version": "across-aaa-autopilot-trigger-registry/1.0",
            "triggers": [
                {
                    "trigger_id": "aaa-continuous-self-iteration-daily",
                    "spec": "aaa-autonomous-self-iteration",
                    "type": "cron",
                    "enabled": True,
                    "paused": False,
                }
            ],
        },
        trigger_scheduler={"running": True},
        self_iteration_plan={
            "status": "active",
            "ready": True,
            "spec": "aaa-autonomous-self-iteration",
            "default_trigger_id": "aaa-continuous-self-iteration-daily",
            "readiness": [{"id": "trigger_active", "status": "passed"}],
        },
        runs={"runs": [{"run_id": "run-1", "status": "completed", "quality_status": "passed"}]},
        telemetry={"runs": {"total": 1, "completed": 1, "failed": 0}, "promotion_ready_by_spec": {}},
        ops_dashboard={"status": "passed", "summary": {"capability_ready_count": 42}, "next_actions": []},
        capability_registry={"capabilities": [{"id": f"cap-{i}", "available": True} for i in range(42)]},
        registry_health={"status": "passed", "checks": [{"id": "registry", "status": "passed"}]},
        agent_loop_memory_metrics={"totals": {"candidate_count": 0, "pending_count": 0, "approved_count": 0}},
        pending_memories=[],
        ecosystem_roadmap={
            "summary": {"route_count": 7, "ready_route_count": 7},
            "sections": {
                "protocol_gateway": {
                    "id": "protocol_gateway",
                    "title": "Protocol Gateway",
                    "status": "passed",
                    "summary": {"adapter_count": 6},
                    "items": [],
                    "endpoint": "/api/ecosystem/protocol-gateway",
                }
            },
            "actions": [],
        },
        agent_plugin_runtime={
            "status": "passed",
            "summary": {
                "downstream_count": 3,
                "downstream_ready_count": 3,
                "agent_plugin_count": 1,
                "ready_agent_plugin_count": 1,
                "external_agent_count": 1,
                "healthy_external_agent_count": 1,
                "context_pack_count": 1,
            },
            "sections": {
                "orchestrator_external_agents": {"id": "orchestrator_external_agents", "title": "Orchestrator External Agent Registry", "status": "passed", "summary": {"agent_count": 1}},
                "autopilot_agent_plugin_runtime": {"id": "autopilot_agent_plugin_runtime", "title": "Autopilot Generic Agent Plugin Runtime", "status": "passed", "summary": {"agent_plugin_count": 1}},
                "context_agent_packs": {"id": "context_agent_packs", "title": "Context Agent Plugin Packs", "status": "passed", "summary": {"context_pack_count": 1}},
            },
        },
        generated_at="2026-06-23T00:00:00Z",
    )


def test_autopilot_workbench_snapshot_passed_contract():
    snapshot = _healthy_snapshot()

    assert snapshot["schema_version"] == WORKBENCH_SCHEMA_VERSION
    assert snapshot["status"] == "passed"
    assert snapshot["summary"]["run_count"] == 1
    assert snapshot["summary"]["registered_trigger_count"] == 1
    assert snapshot["summary"]["scheduler_running"] is True
    assert snapshot["summary"]["capability_ready_count"] == 42
    assert snapshot["sections"]["self_iteration"]["status"] == "passed"
    assert snapshot["sections"]["protocols"]["summary"]["plugin_count"] == 3
    assert snapshot["summary"]["ecosystem_route_count"] == 7
    assert snapshot["summary"]["agent_plugin_count"] == 1
    assert snapshot["summary"]["ready_agent_plugin_count"] == 1
    assert snapshot["sections"]["agent_plugins"]["status"] == "passed"
    assert snapshot["sections"]["protocol_gateway"]["status"] == "passed"
    assert snapshot["actions"][0]["id"] == "continue_scheduled_e2e"
    assert snapshot["endpoints"]["promotion_review_template"] == "/api/autopilot/runs/{run_id}/promotion-review"


def test_autopilot_workbench_snapshot_degrades_to_failed_with_actions():
    snapshot = build_autopilot_workbench_snapshot(
        plugins=[{"plugin_id": "across-autopilot", "available": False, "installed": False, "status": "not_installed"}],
        registry={},
        trigger_queue={"items": [{"trigger_id": "queued-1", "status": "queued"}]},
        trigger_registry={"triggers": []},
        trigger_scheduler={"running": False},
        self_iteration_plan={"status": "not_registered", "ready": False},
        runs={"runs": [{"run_id": "run-failed", "status": "failed", "quality_status": "failed", "promotion_ready": True}]},
        telemetry={"runs": {"total": 1, "completed": 0, "failed": 1}, "promotion_ready_by_spec": {"aaa": 1}},
        ops_dashboard={"status": "failed", "summary": {"capability_ready_count": 12}, "next_actions": []},
        capability_registry={"capabilities": []},
        registry_health={"status": "failed", "checks": [{"id": "registry", "status": "failed"}]},
        agent_loop_memory_metrics={"totals": {"candidate_count": 1, "pending_count": 1, "approved_count": 0}},
        pending_memories=[{"id": "mem-1", "status": "pending", "type": "note", "scope": "global"}],
    )

    assert snapshot["status"] == "failed"
    assert "across-autopilot is unavailable" in snapshot["status_reasons"]
    assert snapshot["summary"]["pending_trigger_count"] == 1
    assert snapshot["summary"]["promotion_ready_count"] == 1
    assert snapshot["sections"]["memory"]["status"] == "attention"
    assert snapshot["actions"][0]["id"] == "repair_autopilot_plugin"
    assert any(action["id"] == "review_pending_memory" for action in snapshot["actions"])
