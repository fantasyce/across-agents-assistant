import Foundation

func assert(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() {
        fatalError(message)
    }
}

func testPluginStatusDecodesAgentLoopCapabilities() throws {
    let json = """
    {
      "plugin_id": "across-orchestrator",
      "display_name": "Across Orchestrator",
      "kind": "task-runtime",
      "version": "0.5.0",
      "status": "installed",
      "installed": true,
      "available": true,
      "probe": true,
      "manifest_exists": true,
      "manifest_path": "/tmp/manifest.json",
      "command": "/tmp/across-orchestrator",
      "command_exists": true,
      "capabilities": {
        "agentLoopRuntime": true,
        "agentLoopV2": true,
        "checkpoints": true,
        "memoryHooks": true,
        "dynamicLoopPlanning": true,
        "remediationDispatch": true
      },
      "paths": {
        "home": "/tmp/across",
        "plugin": "/tmp/across/plugins/across-orchestrator",
        "bin": "/tmp/across/bin",
        "data": "/tmp/across/data/across-orchestrator",
        "config": "/tmp/across/config/across-orchestrator",
        "run": "/tmp/across/run/across-orchestrator",
        "logs": "/tmp/across/logs/across-orchestrator",
        "cache": "/tmp/across/cache/across-orchestrator"
      },
      "install": {"installable": true, "command": "install", "install_dir": "/tmp/install"},
      "lifecycle": {"actions": ["install"], "preservesDataOnUninstall": true},
      "compatibility": {"requiredHostVersion": ">=0.6.0"}
    }
    """.data(using: .utf8)!

    let plugin = try JSONDecoder().decode(AcrossPluginStatus.self, from: json)

    assert(plugin.supportsAgentLoopRuntime, "Orchestrator should decode agent loop runtime capability")
    assert(plugin.supportsAgentLoopV2, "Orchestrator should decode agent loop v2 capability")
    assert(plugin.supportsCheckpoints, "Orchestrator should decode checkpoint capability")
    assert(plugin.supportsMemoryHooks, "Orchestrator should decode memory hook capability")
    assert(plugin.supportsDynamicLoopPlanning, "Orchestrator should decode dynamic loop planning capability")
    assert(plugin.supportsRemediationDispatch, "Orchestrator should decode remediation dispatch capability")
}

func testAgentLoopRunResponseDecodesProbeResult() throws {
    let json = """
    {
      "loop_id": "loop-ui",
      "goal": "Plugin Center Agent Loop Probe",
      "status": "completed",
      "agent": "owner",
      "turn_count": 5,
      "checkpoint_count": 5,
      "final_output": "Agent loop completed",
      "steps": [
        {"status": "completed", "action": {"type": "memory_search"}},
        {"status": "completed", "action": {"action_id": "action-ui", "type": "task_dispatch", "requires_approval": true, "approval_status": "approved"}},
        {"status": "completed", "action": {"type": "quality_gate"}}
      ]
    }
    """.data(using: .utf8)!

    let loop = try JSONDecoder().decode(AgentLoopRunResponse.self, from: json)

    assert(loop.loopId == "loop-ui", "Loop id should decode from snake_case")
    assert(loop.status == "completed", "Loop status should decode")
    assert(loop.checkpointCount == 5, "Checkpoint count should decode")
    assert(loop.steps.map { $0.action?.type ?? "" } == ["memory_search", "task_dispatch", "quality_gate"], "Step action types should decode")
    assert(loop.steps[1].status == "completed", "Step status should decode")
    assert(loop.steps[1].action?.actionId == "action-ui", "Action id should decode")
    assert(loop.steps[1].action?.requiresApproval == true, "Action approval requirement should decode")
    assert(loop.steps[1].action?.approvalStatus == "approved", "Action approval status should decode")
}

func testAgentLoopHealthResponseDecodesProbeHealth() throws {
    let json = """
    {
      "schema_version": "0.1",
      "loop_id": "loop-ui",
      "status": "awaiting_approval",
      "current_action_type": "task_dispatch",
      "current_step_id": "step-ui",
      "pending_approval": {
        "step_id": "step-ui",
        "action_id": "action-ui",
        "action_type": "task_dispatch",
        "title": "Dispatch work through host adapter",
        "approval_status": "pending"
      },
      "lease": {
        "active": true,
        "lease_id": "lease-ui",
        "lease_seconds": 300,
        "heartbeat_at": 1700000000,
        "expires_at": 1700000300,
        "remaining_seconds": 240,
        "expired": false,
        "renewal_count": 1
      },
      "detached_dispatch_count": 0,
      "recent_failure_types": {"quality_failed": 1},
      "executable_actions": ["approve", "reject", "cancel"],
      "cancellation_requested": false,
      "cancellation_category": "shutdown",
      "cancel_ack_pending": false
    }
    """.data(using: .utf8)!

    let health = try JSONDecoder().decode(AgentLoopHealthResponse.self, from: json)

    assert(health.loopId == "loop-ui", "Health loop id should decode from snake_case")
    assert(health.currentActionType == "task_dispatch", "Current action should decode")
    assert(health.pendingApproval?.actionId == "action-ui", "Pending approval should decode")
    assert(health.lease?.active == true, "Lease active flag should decode")
    assert(health.lease?.remainingSeconds == 240, "Lease remaining seconds should decode")
    assert(health.recentFailureTypes?["quality_failed"] == 1, "Failure type counts should decode")
    assert(health.executableActions == ["approve", "reject", "cancel"], "Executable actions should decode")
    assert(health.cancellationCategory == "shutdown", "Cancellation category should decode")
    assert(health.recentFailureCount == 1, "Health should summarize recent failure counts")
    assert(health.hasStaleLease == false, "Active non-expired lease should not be stale")
    assert(health.needsAttention == true, "Recent failures should mark loop health as attention-worthy")
}

func testAgentLoopEvidenceSummaryDecodesAuditAndRouting() throws {
    let json = """
    {
      "schema_version": "0.1",
      "loop_id": "loop-ui",
      "status": "completed",
      "event_audit": {
        "event_count": 12,
        "sequence_contiguous": true,
        "event_id_coverage": true,
        "correlation_id_coverage": true
      },
      "routing": {
        "routed_action_count": 2,
        "non_default_route_count": 2,
        "capability_hint_route_count": 1,
        "outcomes": [
          {
            "action_type": "task_dispatch",
            "status": "completed",
            "selected_agent": "builder",
            "source": "metadata.agentCapabilityHints.preferred.task_dispatch",
            "capability_hint": "implementation"
          }
        ]
      },
      "recovery": {
        "decision_count": 1,
        "applied_count": 1,
        "blocked_count": 0,
        "decisions": [
          {
            "event_id": "loop-event-recovery-1",
            "sequence": 8,
            "correlation_id": "step:step-failed",
            "step_id": "step-failed",
            "action_type": "task_dispatch",
            "failure_type": "adapter_error",
            "recovery_action": "retry",
            "attempt": 1,
            "max_retries": 1,
            "applied": true,
            "source": "metadata.recoveryPolicy.byFailureType.adapter_error"
          }
        ],
        "recovered_steps": [
          {
            "event_id": "loop-event-recovered-1",
            "sequence": 9,
            "correlation_id": "step:step-retry",
            "step_id": "step-retry",
            "action_type": "task_dispatch",
            "failure_type": "adapter_error",
            "recovery_action": "retry",
            "attempt": 1,
            "recovered_from_step_id": "step-failed",
            "next_action": "task_dispatch",
            "next_turn": 2
          }
        ]
      },
      "memory_candidates": {
        "candidate_count": 1,
        "candidates": [
          {
            "step_id": "step-memory",
            "turn": 3,
            "status": "completed",
            "provider": "across-context",
            "memory_status": "pending",
            "memory_id": "memory-ui"
          }
        ]
      }
    }
    """.data(using: .utf8)!

    let summary = try JSONDecoder().decode(AgentLoopEvidenceSummaryResponse.self, from: json)

    assert(summary.schemaVersion == "0.1", "Evidence summary schema should decode")
    assert(summary.loopId == "loop-ui", "Evidence summary loop id should decode")
    assert(summary.eventAudit?.eventCount == 12, "Evidence event count should decode")
    assert(summary.eventAudit?.sequenceContiguous == true, "Evidence audit sequence coverage should decode")
    assert(summary.routing?.capabilityHintRouteCount == 1, "Capability hint route count should decode")
    assert(summary.routing?.outcomes?.first?.selectedAgent == "builder", "Routing outcome agent should decode")
    assert(summary.recovery?.appliedCount == 1, "Recovery applied count should decode")
    assert(summary.recovery?.decisions?.first?.recoveryAction == "retry", "Recovery decision action should decode")
    assert(summary.recovery?.decisions?.first?.failureType == "adapter_error", "Recovery decision failure type should decode")
    assert(summary.recovery?.decisions?.first?.applied == true, "Recovery decision applied flag should decode")
    assert(summary.recovery?.recoveredSteps?.first?.nextAction == "task_dispatch", "Recovered step next action should decode")
    assert(summary.recovery?.recoveredSteps?.first?.recoveredFromStepId == "step-failed", "Recovered step source should decode")
    assert(summary.memoryCandidates?.candidateCount == 1, "Memory candidate count should decode")
    assert(summary.memoryCandidates?.candidates?.first?.provider == "across-context", "Memory candidate provider should decode")
    assert(summary.memoryCandidates?.candidates?.first?.memoryStatus == "pending", "Memory candidate status should decode")
    assert(summary.memoryCandidates?.candidates?.first?.memoryId == "memory-ui", "Memory candidate id should decode")
    if let candidate = summary.memoryCandidates?.candidates?.first {
        assert(PluginLifecycleViewModel.memoryReviewStatusFilter(for: candidate) == "pending", "Memory candidate review filter should use memory status")
    } else {
        assert(false, "Memory candidate should be present")
    }
    let missingStatusCandidate = AgentLoopEvidenceMemoryCandidate(
        stepId: "step-missing-status",
        turn: 4,
        status: "completed",
        provider: "across-context",
        memoryStatus: " ",
        memoryId: nil
    )
    assert(
        PluginLifecycleViewModel.memoryReviewStatusFilter(for: missingStatusCandidate) == "pending",
        "Memory candidate review filter should fall back to pending"
    )
}

func testAgentLoopEventResponseDecodesNestedPayloads() throws {
    let json = """
    [
      {
        "event_id": "loop-event-audit-1",
        "sequence": 7,
        "type": "loop.next_action.selected",
        "loop_id": "loop-ui",
        "correlation_id": "step:step-ui",
        "step_id": "step-ui",
        "action_id": "action-ui",
        "timestamp": 1700000000.25,
        "payload": {
          "action_type": "task_dispatch",
          "turn": 2,
          "metadata": {"detached": false},
          "hints": ["approval", 3, null]
        }
      },
      {
        "type": "loop.failed",
        "loop_id": "loop-ui",
        "timestamp": 1700000001,
        "payload": {"failure_type": "quality_failed"}
      }
    ]
    """.data(using: .utf8)!

    let events = try JSONDecoder().decode([AgentLoopEventResponse].self, from: json)

    assert(events.count == 2, "Loop events should decode as an array")
    assert(events[0].eventId == "loop-event-audit-1", "Event id should decode from snake_case")
    assert(events[0].sequence == 7, "Event sequence should decode")
    assert(events[0].sequenceLabel == "#7", "Event sequence should have a compact label")
    assert(events[0].loopId == "loop-ui", "Event loop id should decode from snake_case")
    assert(events[0].correlationId == "step:step-ui", "Event correlation id should decode from snake_case")
    assert(events[0].stepId == "step-ui", "Event step id should decode from snake_case")
    assert(events[0].actionId == "action-ui", "Event action id should decode from snake_case")
    assert(events[0].timestamp == 1700000000.25, "Event timestamp should decode")
    assert(events[0].payload?["turn"]?.stringValue == "2", "Numeric payload values should expose compact strings")
    assert(events[0].compactLabel == "next action selected: task dispatch", "Action payload should be summarized")
    assert(events[1].compactLabel == "failed: quality failed", "Failure payload should be summarized")

    if case .object(let metadata)? = events[0].payload?["metadata"] {
        assert(metadata["detached"]?.stringValue == "false", "Nested object payload should decode")
    } else {
        fatalError("Nested object payload should be preserved")
    }

    if case .array(let hints)? = events[0].payload?["hints"] {
        assert(hints.count == 3, "Array payload should decode")
    } else {
        fatalError("Array payload should be preserved")
    }
}

func testAgentLoopEventResponseDecodesSSEStream() throws {
    let stream = """
    event: loop.started
    data: {"event_id":"loop-event-sse-1","sequence":1,"type":"loop.started","loop_id":"loop-ui","correlation_id":"loop:loop-ui","payload":{"status":"running"}}

    event: loop.completed
    data: {"event_id":"loop-event-sse-2","sequence":2,"type":"loop.completed","loop_id":"loop-ui","correlation_id":"loop:loop-ui","payload":{"status":"completed"}}

    """

    let events = PluginLifecycleViewModel.decodeAgentLoopEventsFromSSE(stream)

    assert(events.count == 2, "SSE stream should decode two loop events")
    assert(events[0].eventId == "loop-event-sse-1", "SSE stream should decode event id")
    assert(events[1].sequenceLabel == "#2", "SSE stream should decode sequence labels")
    assert(events[1].correlationId == "loop:loop-ui", "SSE stream should decode correlation id")
    assert(events[0].compactLabel == "started: running", "Started SSE event should summarize status")
    assert(events[1].compactLabel == "completed: completed", "Completed SSE event should summarize status")
}

func testAgentLoopEventMergingDeduplicatesStreamUpdates() throws {
    let first = PluginLifecycleViewModel.decodeAgentLoopEventsFromSSEDataLines([
        "{\"event_id\":\"loop-event-sse-1\",\"sequence\":1,\"type\":\"loop.started\",\"loop_id\":\"loop-ui\",\"payload\":{\"status\":\"running\"}}"
    ])
    let second = PluginLifecycleViewModel.decodeAgentLoopEventsFromSSEDataLines([
        "{\"event_id\":\"loop-event-sse-1\",\"sequence\":1,\"type\":\"loop.started\",\"loop_id\":\"loop-ui\",\"payload\":{\"status\":\"running\"}}"
    ])
    let third = PluginLifecycleViewModel.decodeAgentLoopEventsFromSSEDataLines([
        "{\"event_id\":\"loop-event-sse-2\",\"sequence\":2,\"type\":\"loop.completed\",\"loop_id\":\"loop-ui\",\"payload\":{\"status\":\"completed\"}}"
    ])

    let merged = PluginLifecycleViewModel.mergedAgentLoopEvents(
        PluginLifecycleViewModel.mergedAgentLoopEvents(first, second),
        third
    )

    assert(merged.count == 2, "Live stream updates should deduplicate repeated events")
    assert(merged[0].sequenceLabel == "#1", "Merged stream should preserve first event")
    assert(merged[1].sequenceLabel == "#2", "Merged stream should append new events")
}

@main
struct PluginLifecycleBehavior {
    static func main() throws {
        try testPluginStatusDecodesAgentLoopCapabilities()
        try testAgentLoopRunResponseDecodesProbeResult()
        try testAgentLoopHealthResponseDecodesProbeHealth()
        try testAgentLoopEvidenceSummaryDecodesAuditAndRouting()
        try testAgentLoopEventResponseDecodesNestedPayloads()
        try testAgentLoopEventResponseDecodesSSEStream()
        try testAgentLoopEventMergingDeduplicatesStreamUpdates()
        print("PluginLifecycleBehavior passed")
    }
}
