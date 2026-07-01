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
            "platform_self_repair": {
                "enabled": True,
                "spec": "aaa-platform-self-repair",
                "queued_count": 0,
                "promotion_review_required": True,
            },
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
        agent_interop_e2e={
            "status": "passed",
            "summary": {
                "passed_count": 11,
                "failed_count": 0,
                "host_target_count": 5,
                "mcp_server_count": 3,
                "evidence_node_count": 21,
                "protocol_readiness_score": 75,
                "market_readiness_status": "passed",
                "trust_receipt_status": "passed",
                "frontier_interop_status": "passed",
                "remote_mcp_template_status": "passed",
                "a2a_delegation_status": "passed",
                "projection_status": "passed",
                "projection_count": 5,
                "agui_projection_status": "passed",
                "async_task_status": "passed",
                "context_skills_bridge_status": "passed",
                "computer_use_sandbox_status": "passed",
                "local_agent_protocol_status": "passed",
                "otel_span_count": 21,
                "eval_case_count": 5,
                "otlp_resource_span_count": 1,
            },
            "checks": [{"id": "three_plugin_mcp_load", "status": "passed", "summary": "tool_count=42"}],
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
    assert snapshot["summary"]["platform_self_repair_queued_count"] == 0
    assert snapshot["sections"]["self_iteration"]["status"] == "passed"
    assert snapshot["sections"]["self_iteration"]["summary"]["platform_self_repair"]["spec"] == "aaa-platform-self-repair"
    assert snapshot["sections"]["protocols"]["summary"]["plugin_count"] == 3
    assert snapshot["summary"]["ecosystem_route_count"] == 7
    assert snapshot["summary"]["agent_plugin_count"] == 1
    assert snapshot["summary"]["ready_agent_plugin_count"] == 1
    assert snapshot["summary"]["agent_interop_e2e_status"] == "passed"
    assert snapshot["sections"]["agent_plugins"]["status"] == "passed"
    assert snapshot["sections"]["agent_interop_e2e"]["status"] == "passed"
    assert snapshot["sections"]["agent_interop_e2e"]["summary"]["protocol_readiness_score"] == 75
    assert snapshot["sections"]["agent_interop_e2e"]["summary"]["market_readiness_status"] == "passed"
    assert snapshot["sections"]["agent_interop_e2e"]["summary"]["frontier_interop_status"] == "passed"
    assert snapshot["sections"]["agent_interop_e2e"]["summary"]["projection_status"] == "passed"
    assert snapshot["sections"]["agent_interop_e2e"]["summary"]["agui_projection_status"] == "passed"
    assert snapshot["sections"]["agent_interop_e2e"]["summary"]["async_task_status"] == "passed"
    assert snapshot["sections"]["agent_interop_e2e"]["summary"]["context_skills_bridge_status"] == "passed"
    assert snapshot["sections"]["agent_interop_e2e"]["summary"]["computer_use_sandbox_status"] == "passed"
    assert snapshot["sections"]["agent_interop_e2e"]["summary"]["local_agent_protocol_status"] == "passed"
    assert snapshot["sections"]["agent_interop_e2e"]["summary"]["otel_span_count"] == 21
    assert snapshot["sections"]["agent_interop_e2e"]["summary"]["eval_case_count"] == 5
    assert snapshot["sections"]["agent_interop_e2e"]["summary"]["otlp_resource_span_count"] == 1
    assert snapshot["sections"]["protocol_gateway"]["status"] == "passed"
    assert snapshot["actions"][0]["id"] == "continue_scheduled_e2e"
    assert snapshot["endpoints"]["promotion_review_template"] == "/api/autopilot/runs/{run_id}/promotion-review"


def test_autopilot_workbench_uses_latest_run_state_for_release_attention():
    snapshot = build_autopilot_workbench_snapshot(
        plugins=[
            {"plugin_id": "across-context", "available": True, "installed": True, "status": "installed"},
            {"plugin_id": "across-orchestrator", "available": True, "installed": True, "status": "installed"},
            {"plugin_id": "across-autopilot", "available": True, "installed": True, "status": "installed"},
        ],
        registry={"built_in": [{"id": "repo-quality-copilot"}]},
        trigger_queue={"items": []},
        trigger_registry={
            "triggers": [
                {
                    "trigger_id": "repo-quality-daily",
                    "spec": "repo-quality-copilot",
                    "type": "cron",
                    "enabled": True,
                    "paused": False,
                }
            ],
        },
        trigger_scheduler={"running": True},
        self_iteration_plan={"status": "active", "ready": True, "spec": "repo-quality-copilot"},
        runs={
            "runs": [
                {"run_id": "run-new", "spec_id": "repo-quality-copilot", "status": "completed", "quality_status": "passed"},
                {"run_id": "run-old", "spec_id": "repo-quality-copilot", "status": "failed", "quality_status": "failed", "promotion_ready": True},
            ],
            "run_count": 2,
        },
        telemetry={
            "runs": {"total": 2, "completed": 1, "failed": 1},
            "promotion_ready_by_spec": {"repo-quality-copilot": 1},
        },
        ops_dashboard={"status": "passed", "summary": {"capability_ready_count": 42}, "next_actions": []},
        capability_registry={"capabilities": [{"id": f"cap-{i}", "available": True} for i in range(42)]},
        registry_health={"status": "passed", "checks": [{"id": "registry", "status": "passed"}]},
        agent_loop_memory_metrics={"totals": {"candidate_count": 0, "pending_count": 0, "approved_count": 0}},
        pending_memories=[],
        ecosystem_roadmap={"summary": {"route_count": 7, "ready_route_count": 7}, "sections": {}, "actions": []},
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
            "sections": {},
        },
        agent_interop_e2e={"status": "passed", "summary": {"passed_count": 11, "failed_count": 0}, "checks": []},
    )

    assert snapshot["status"] == "passed"
    assert snapshot["summary"]["failed_run_count"] == 0
    assert snapshot["summary"]["historical_failed_run_count"] == 1
    assert snapshot["summary"]["promotion_ready_count"] == 0
    assert snapshot["summary"]["historical_promotion_ready_count"] == 1
    assert snapshot["sections"]["runs"]["status"] == "passed"
    assert snapshot["sections"]["promotion"]["status"] == "passed"


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
    assert snapshot["sections"]["agent_interop_e2e"]["status"] == "attention"
    assert snapshot["actions"][0]["id"] == "repair_autopilot_plugin"
    assert any(action["id"] == "run_agent_interop_e2e" for action in snapshot["actions"])
    assert any(action["id"] == "review_pending_memory" for action in snapshot["actions"])
