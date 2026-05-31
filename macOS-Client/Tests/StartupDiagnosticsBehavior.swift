import Foundation

func assert(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() {
        fatalError(message)
    }
}

func testStartupDiagnosticsDecodeAndSummaries() throws {
    let json = """
    {
      "schema_version": "1.0",
      "app_version": "0.4.0",
      "generated_at": "2026-05-31T12:00:00Z",
      "status": "attention",
      "summary": {"status": "attention", "passed": 8, "warnings": 1, "failed": 0, "check_count": 9},
      "paths": {
        "app_home": "/example-app-home",
        "logs_dir": "/example-app-home/logs",
        "run_dir": "/example-app-home/run",
        "tmp_dir": "/example-app-home/tmp",
        "evidence_dir": "/example-app-home/evidence",
        "socket_path": "/example-app-home/run/across-agents.sock",
        "database_path": "/example-app-home/assistant.db"
      },
      "runtime": {
        "pid": 123,
        "started_at": 1780000000.0,
        "uptime_sec": 42.5,
        "known_tasks": 3,
        "persistence_initialized": true,
        "orchestrator_initialized": false,
        "dispatcher_initialized": false
      },
      "keys": {
        "has_any_key": false,
        "providers": {"deepseek": "not_configured", "minimax": "not_configured"},
        "readiness_blockers": ["api_keys"]
      },
      "checks": [
        {"id": "backend_health", "title": "Backend process", "status": "passed", "detail": "Backend process is serving.", "remediation": null, "metadata": {"pid": 123}},
        {"id": "provider_keys", "title": "Cloud provider readiness", "status": "warning", "detail": "No key configured.", "remediation": "Configure at least one cloud LLM provider in Model Settings.", "metadata": {"providers": {"deepseek": "not_configured"}}}
      ]
    }
    """.data(using: .utf8)!

    let report = try JSONDecoder().decode(StartupDiagnosticsReport.self, from: json)

    assert(report.id == "startup-diagnostics-2026-05-31T12:00:00Z", "Diagnostics report id should be stable")
    assert(report.status == .attention, "Report status should decode")
    assert(report.summary.warnings == 1, "Warnings should decode")
    assert(report.warningChecks.map(\.id) == ["provider_keys"], "Warning checks should be filtered")
    assert(report.failedChecks.isEmpty, "Failed checks should be filtered")
    assert(report.readyHeadline == "Attention · 8 passed · 1 warning", "Headline should stay compact")
    assert(report.providerSummary == "DeepSeek: not configured · MiniMax: not configured", "Provider summary should be deterministic")
    assert(report.paths.evidenceDir.hasSuffix("/evidence"), "Evidence path should decode from snake case")
    assert(report.runtime.knownTasks == 3, "Runtime should decode from snake case")
    assert(report.checks[1].metadataString.contains("providers"), "Metadata should be printable for diagnostics details")
}

func testStartupDiagnosticsReadyHeadline() throws {
    let json = """
    {
      "schema_version": "1.0",
      "app_version": "0.4.0",
      "generated_at": "2026-05-31T12:00:00Z",
      "status": "ready",
      "summary": {"status": "ready", "passed": 9, "warnings": 0, "failed": 0, "check_count": 9},
      "paths": {"app_home": "/tmp/a", "logs_dir": "/tmp/l", "run_dir": "/tmp/r", "tmp_dir": "/tmp/t", "evidence_dir": "/tmp/e", "socket_path": "/tmp/s", "database_path": "/tmp/db"},
      "runtime": {"pid": 1, "started_at": 1.0, "uptime_sec": 2.0, "known_tasks": 0, "persistence_initialized": true, "orchestrator_initialized": true, "dispatcher_initialized": true},
      "keys": {"has_any_key": true, "providers": {"deepseek": "configured", "minimax": "not_configured"}, "readiness_blockers": []},
      "checks": []
    }
    """.data(using: .utf8)!

    let report = try JSONDecoder().decode(StartupDiagnosticsReport.self, from: json)

    assert(report.readyHeadline == "Ready · 9 passed", "Ready headline should omit empty warning and failed counts")
    assert(report.providerSummary == "DeepSeek: configured · MiniMax: not configured", "Provider summary should include known providers")
}

@main
struct StartupDiagnosticsBehavior {
    static func main() {
        do {
            try testStartupDiagnosticsDecodeAndSummaries()
            try testStartupDiagnosticsReadyHeadline()
            print("StartupDiagnosticsBehavior passed")
        } catch {
            fatalError("StartupDiagnosticsBehavior failed: \(error)")
        }
    }
}
