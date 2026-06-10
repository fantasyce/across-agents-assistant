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
        "checkpoints": true,
        "memoryHooks": true
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
    assert(plugin.supportsCheckpoints, "Orchestrator should decode checkpoint capability")
    assert(plugin.supportsMemoryHooks, "Orchestrator should decode memory hook capability")
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
        {"action": {"type": "memory_search"}},
        {"action": {"type": "task_dispatch"}},
        {"action": {"type": "quality_gate"}}
      ]
    }
    """.data(using: .utf8)!

    let loop = try JSONDecoder().decode(AgentLoopRunResponse.self, from: json)

    assert(loop.loopId == "loop-ui", "Loop id should decode from snake_case")
    assert(loop.status == "completed", "Loop status should decode")
    assert(loop.checkpointCount == 5, "Checkpoint count should decode")
    assert(loop.steps.map { $0.action?.type ?? "" } == ["memory_search", "task_dispatch", "quality_gate"], "Step action types should decode")
}

@main
struct PluginLifecycleBehavior {
    static func main() throws {
        try testPluginStatusDecodesAgentLoopCapabilities()
        try testAgentLoopRunResponseDecodesProbeResult()
        print("PluginLifecycleBehavior passed")
    }
}
