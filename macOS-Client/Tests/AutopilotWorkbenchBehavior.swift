import Foundation

private let repositoryRoot = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)

private func source(_ relativePath: String) -> String {
    let url = repositoryRoot.appendingPathComponent(relativePath)
    guard let contents = try? String(contentsOf: url, encoding: .utf8) else {
        fatalError("Unable to read \(relativePath)")
    }
    return contents
}

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
            "schema_compatibility_status": "incompatible",
            "compatible_plugin_count": 2,
            "incompatible_plugin_count": 1,
            "portable_tool_count": 47,
            "otel_span_count": 21,
            "otlp_resource_span_count": 1,
            "eval_case_count": 5
          },
          "items": [{
            "id": "mcp_schema_finding_1",
            "status": "failed",
            "plugin_id": "across-orchestrator",
            "tool_name": "register_external_agent_plugin",
            "profile": "claude_desktop_portable",
            "code": "portable_keyword_unsupported",
            "severity": "error",
            "message": "This JSON Schema keyword is not in the Claude Desktop portable profile."
          }],
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
    assert(snapshot.sections["agent_interop_e2e"]?.summary["schema_compatibility_status"]?.description == "incompatible", "MCP schema compatibility status should decode")
    assert(snapshot.sections["agent_interop_e2e"]?.summary["compatible_plugin_count"]?.description == "2", "Compatible plugin count should decode")
    assert(snapshot.sections["agent_interop_e2e"]?.summary["incompatible_plugin_count"]?.description == "1", "Incompatible plugin count should decode")
    assert(snapshot.sections["agent_interop_e2e"]?.summary["portable_tool_count"]?.description == "47", "Portable tool count should decode")
    assert(snapshot.sections["agent_interop_e2e"]?.items.first?.objectValue?["code"]?.description == "portable_keyword_unsupported", "Fixed compatibility finding should decode")
    assert(snapshot.sections["agent_interop_e2e"]?.summary["otel_span_count"]?.description == "21", "Agent interop OTel span count should decode")
    assert(snapshot.sections["agent_interop_e2e"]?.summary["otlp_resource_span_count"]?.description == "1", "Agent interop OTLP resource span count should decode")
    assert(snapshot.actions.first?.id == "open_promotion_review", "Actions should decode")
    assert(snapshot.endpoints["refresh"] == "/api/autopilot/workbench/refresh", "Endpoint map should decode")
}

func testCompatibilityEvidenceReusesOneActionAndHasLocalizedPresentation() {
    let view = source("macOS-Client/Sources/Views/AutopilotWorkbenchView.swift")
    let viewModel = source("macOS-Client/Sources/ViewModels/AutopilotWorkbenchViewModel.swift")
    let preferences = source("macOS-Client/Sources/Models/AppPreferences.swift")

    assert(
        view.components(separatedBy: "case \"run_agent_interop_e2e\"").count - 1 == 1,
        "Workbench must keep exactly one Agent compatibility action"
    )
    assert(
        Set(viewModel.components(separatedBy: "\n").filter { $0.contains("/api/autopilot/agent-interop-e2e") })
            .allSatisfy { $0.contains("request(path:") },
        "Compatibility must reuse the existing interop endpoint"
    )
    for key in [
        "schema_compatibility_status",
        "compatible_plugin_count",
        "incompatible_plugin_count",
        "portable_tool_count",
    ] {
        assert(view.contains("\"\(key)\""), "Compatibility summary key \(key) must be prioritized")
        assert(
            preferences.components(separatedBy: "\"workbench.summary.\(key)\"").count - 1 == 2,
            "Compatibility summary key \(key) must have English and Chinese labels"
        )
    }
    assert(
        preferences.components(separatedBy: "\"workbench.finding.portable_keyword_unsupported\"").count - 1 == 2,
        "Portable-keyword finding must have English and Chinese labels"
    )
    assert(view.contains("workbench.summary.\\(key)"), "Workbench must localize dynamic summary keys")
    assert(view.contains("workbench.finding.\\(code)"), "Workbench must localize compatibility findings")
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

func testAutopilotWorkbenchTreatsUnusedOptionalCapabilitiesAsNeutral() throws {
    let json = """
    {
      "schema_version": "across-aaa-autopilot-workbench/1.0",
      "status": "passed",
      "summary": {
        "run_count": 0,
        "completed_run_count": 0,
        "failed_run_count": 0,
        "pending_trigger_count": 0,
        "registered_trigger_count": 0,
        "active_trigger_count": 0,
        "scheduler_running": false,
        "self_iteration_status": "not_configured",
        "capability_ready_count": 42,
        "registry_health_status": "passed",
        "pending_memory_count": 0,
        "promotion_ready_count": 0,
        "autopilot_available": true,
        "ecosystem_route_count": 7,
        "ecosystem_ready_route_count": 7,
        "agent_plugin_count": 0,
        "ready_agent_plugin_count": 0,
        "agent_interop_e2e_status": "not_run"
      },
      "status_reasons": [],
      "sections": {},
      "actions": [],
      "endpoints": {}
    }
    """.data(using: .utf8)!

    let snapshot = try JSONDecoder().decode(AutopilotWorkbenchSnapshot.self, from: json)

    assert(snapshot.needsAttention == false, "Unused optional capabilities must not create a false attention state")
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
        try testAutopilotWorkbenchTreatsUnusedOptionalCapabilitiesAsNeutral()
        testAutopilotEvidenceTargetKeepsRunAndRouteBoundTogether()
        testCompatibilityEvidenceReusesOneActionAndHasLocalizedPresentation()
        print("AutopilotWorkbenchBehavior passed")
    }
}
