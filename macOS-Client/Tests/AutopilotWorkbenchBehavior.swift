import Foundation

func assert(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() {
        fatalError(message)
    }
}

func testAutopilotWorkbenchSnapshotDecodesAttentionContract() throws {
    let json = """
    {
      "schema_version": "across-aaa-autopilot-workbench/1.0",
      "status": "attention",
      "generated_at": "2026-06-23T00:00:00Z",
      "summary": {
        "run_count": 2,
        "completed_run_count": 1,
        "failed_run_count": 1,
        "pending_trigger_count": 1,
        "registered_trigger_count": 2,
        "active_trigger_count": 1,
        "scheduler_running": false,
        "self_iteration_status": "active",
        "capability_ready_count": 42,
        "registry_health_status": "passed",
        "pending_memory_count": 1,
        "promotion_ready_count": 1,
        "autopilot_available": true,
        "ecosystem_route_count": 7,
        "ecosystem_ready_route_count": 5,
        "external_agent_count": 1,
        "healthy_external_agent_count": 1,
        "agent_plugin_count": 1,
        "ready_agent_plugin_count": 1,
        "agent_plugin_context_pack_count": 1,
        "agent_interop_e2e_status": "passed"
      },
      "status_reasons": ["registered triggers exist but scheduler is stopped"],
      "sections": {
        "promotion": {
          "id": "promotion",
          "title": "Promotion Review",
          "status": "attention",
          "summary": {"ready_count": 1, "human_approval_required": true},
          "items": [{"run_id": "run-ui", "status": "completed", "promotion_ready": true}],
          "endpoint": "/api/autopilot/runs/{run_id}/promotion-review"
        },
        "memory": {
          "id": "memory",
          "title": "Context Memory Review",
          "status": "attention",
          "summary": {"pending_count": 1},
          "items": [{"id": "mem-ui", "status": "pending"}],
          "endpoint": "/api/memory/memories?status=pending"
        },
        "protocol_gateway": {
          "id": "protocol_gateway",
          "title": "Protocol Gateway",
          "status": "passed",
          "summary": {"adapter_count": 6, "ready_adapter_count": 6},
          "items": [{"id": "agent_cards", "status": "passed"}],
          "endpoint": "/api/ecosystem/protocol-gateway"
        },
        "agent_interop_e2e": {
          "id": "agent_interop_e2e",
          "title": "Agent Interop E2E Lab",
          "status": "passed",
          "summary": {
            "passed_count": 11,
            "failed_count": 0,
            "protocol_readiness_score": 81,
            "frontier_interop_status": "passed",
            "remote_mcp_template_status": "passed",
            "a2a_delegation_status": "passed",
            "projection_status": "passed",
            "agui_projection_status": "passed",
            "async_task_status": "passed",
            "context_skills_bridge_status": "passed",
            "computer_use_sandbox_status": "passed",
            "local_agent_protocol_status": "passed",
            "otel_span_count": 21,
            "otlp_resource_span_count": 1,
            "eval_case_count": 5
          },
          "items": [{"id": "three_plugin_mcp_load", "status": "passed"}],
          "endpoint": "/api/autopilot/agent-interop-e2e"
        }
      },
      "actions": [
        {
          "id": "open_promotion_review",
          "priority": "high",
          "title": "Review promotion candidate",
          "reason": "Promotion-ready output must remain human-gated.",
          "endpoint": "/api/autopilot/runs/{run_id}/promotion-review"
        }
      ],
      "endpoints": {
        "snapshot": "/api/autopilot/workbench",
        "refresh": "/api/autopilot/workbench/refresh"
      }
    }
    """.data(using: .utf8)!

    let snapshot = try JSONDecoder().decode(AutopilotWorkbenchSnapshot.self, from: json)

    assert(snapshot.schemaVersion == "across-aaa-autopilot-workbench/1.0", "Workbench schema should decode")
    assert(snapshot.status == "attention", "Workbench status should decode")
    assert(snapshot.needsAttention, "Pending memories, failures, stopped scheduler, and promotion review should require attention")
    assert(snapshot.summary.runCount == 2, "Run count should decode from snake_case")
    assert(snapshot.summary.schedulerRunning == false, "Scheduler state should decode")
    assert(snapshot.summary.ecosystemRouteCount == 7, "Ecosystem route count should decode")
    assert(snapshot.summary.ecosystemReadyRouteCount == 5, "Ecosystem ready route count should decode")
    assert(snapshot.summary.agentPluginCount == 1, "Agent plugin count should decode")
    assert(snapshot.summary.readyAgentPluginCount == 1, "Ready agent plugin count should decode")
    assert(snapshot.summary.agentInteropE2EStatus == "passed", "Agent interop E2E status should decode")
    assert(snapshot.sections["promotion"]?.items.first?.objectValue?["run_id"]?.description == "run-ui", "Section item objects should decode")
    assert(snapshot.sections["protocol_gateway"]?.endpoint == "/api/ecosystem/protocol-gateway", "Protocol gateway section should decode")
    assert(snapshot.sections["agent_interop_e2e"]?.summary["passed_count"]?.description == "11", "Agent interop E2E section should decode")
    assert(snapshot.sections["agent_interop_e2e"]?.summary["frontier_interop_status"]?.description == "passed", "Agent interop frontier status should decode")
    assert(snapshot.sections["agent_interop_e2e"]?.summary["projection_status"]?.description == "passed", "Agent interop projection status should decode")
    assert(snapshot.sections["agent_interop_e2e"]?.summary["agui_projection_status"]?.description == "passed", "Agent interop AG-UI status should decode")
    assert(snapshot.sections["agent_interop_e2e"]?.summary["async_task_status"]?.description == "passed", "Agent interop async task status should decode")
    assert(snapshot.sections["agent_interop_e2e"]?.summary["otel_span_count"]?.description == "21", "Agent interop OTel span count should decode")
    assert(snapshot.sections["agent_interop_e2e"]?.summary["otlp_resource_span_count"]?.description == "1", "Agent interop OTLP resource span count should decode")
    assert(snapshot.actions.first?.id == "open_promotion_review", "Actions should decode")
    assert(snapshot.endpoints["refresh"] == "/api/autopilot/workbench/refresh", "Endpoint map should decode")
}

func testAutopilotWorkbenchSnapshotDecodesHealthyContract() throws {
    let json = """
    {
      "schema_version": "across-aaa-autopilot-workbench/1.0",
      "status": "passed",
      "summary": {
        "run_count": 1,
        "completed_run_count": 1,
        "failed_run_count": 0,
        "pending_trigger_count": 0,
        "registered_trigger_count": 1,
        "active_trigger_count": 1,
        "scheduler_running": true,
        "self_iteration_status": "active",
        "capability_ready_count": 42,
        "registry_health_status": "passed",
        "pending_memory_count": 0,
        "promotion_ready_count": 0,
        "autopilot_available": true,
        "ecosystem_route_count": 7,
        "ecosystem_ready_route_count": 7,
        "agent_plugin_count": 1,
        "ready_agent_plugin_count": 1,
        "agent_interop_e2e_status": "passed"
      },
      "status_reasons": [],
      "sections": {},
      "actions": [],
      "endpoints": {}
    }
    """.data(using: .utf8)!

    let snapshot = try JSONDecoder().decode(AutopilotWorkbenchSnapshot.self, from: json)

    assert(snapshot.status == "passed", "Healthy Workbench should decode passed status")
    assert(snapshot.needsAttention == false, "Healthy Workbench should not need attention")
    assert(snapshot.summary.selfIterationStatus == "active", "Self-iteration status should decode")
}

func testAutopilotEvidenceTargetKeepsRunAndRouteBoundTogether() {
    let target = AutopilotEvidenceTarget(
        runID: "run-beginner-1",
        evidenceRoute: "run://run-beginner-1/evidence"
    )

    assert(target?.runID == "run-beginner-1", "Evidence target should preserve the selected run")
    assert(
        target?.backendPath == "/api/autopilot/runs/run-beginner-1/evidence",
        "Evidence target should resolve to the run-specific evidence endpoint"
    )
    assert(
        AutopilotEvidenceTarget(
            runID: "run-beginner-1",
            evidenceRoute: "run://another-run/evidence"
        ) == nil,
        "A route for another run must never be accepted"
    )
    assert(
        AutopilotEvidenceTarget(
            runID: "run-beginner-1?redirect=other",
            evidenceRoute: "run://run-beginner-1?redirect=other/evidence"
        ) == nil,
        "Unsafe run identifiers must never become backend routes"
    )
}

@main
struct AutopilotWorkbenchBehavior {
    static func main() throws {
        try testAutopilotWorkbenchSnapshotDecodesAttentionContract()
        try testAutopilotWorkbenchSnapshotDecodesHealthyContract()
        testAutopilotEvidenceTargetKeepsRunAndRouteBoundTogether()
        print("AutopilotWorkbenchBehavior passed")
    }
}
