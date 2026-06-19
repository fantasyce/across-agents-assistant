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
}

func testAgentLoopEventResponseDecodesNestedPayloads() throws {
    let json = """
    [
      {
        "type": "loop.next_action.selected",
        "loop_id": "loop-ui",
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
    assert(events[0].loopId == "loop-ui", "Event loop id should decode from snake_case")
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

@main
struct PluginLifecycleBehavior {
    static func main() throws {
        try testPluginStatusDecodesAgentLoopCapabilities()
        try testAgentLoopRunResponseDecodesProbeResult()
        try testAgentLoopHealthResponseDecodesProbeHealth()
        try testAgentLoopEventResponseDecodesNestedPayloads()
        print("PluginLifecycleBehavior passed")
    }
}
