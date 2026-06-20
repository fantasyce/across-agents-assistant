import Foundation

func assert(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() {
        fatalError(message)
    }
}

func testReleaseVerificationDecodeAndSummary() throws {
    let json = """
    {
      "schema_version": "1.0",
      "app_version": "0.4.0",
      "generated_at": "2026-05-31T12:00:00Z",
      "status": "ready",
      "startup": {
        "schema_version": "1.0",
        "app_version": "0.4.0",
        "generated_at": "2026-05-31T12:00:00Z",
        "status": "ready",
        "summary": {"status": "ready", "passed": 10, "warnings": 0, "failed": 0, "check_count": 10},
        "paths": {"app_home": "/tmp/a", "logs_dir": "/tmp/l", "run_dir": "/tmp/r", "tmp_dir": "/tmp/t", "evidence_dir": "/tmp/e", "socket_path": "/tmp/s", "database_path": "/tmp/db"},
        "runtime": {"pid": 1, "started_at": 1.0, "uptime_sec": 2.0, "known_tasks": 1, "persistence_initialized": true, "dispatcher_initialized": true},
        "keys": {"has_any_key": true, "providers": {"deepseek": "configured", "minimax": "not_configured"}, "readiness_blockers": []},
        "checks": []
      },
      "release_evaluation": {
        "release_readiness": "ready",
        "generated_at": 1780000000.0,
        "evaluated_task_count": 4,
        "terminal_task_count": 4,
        "passed_task_count": 4,
        "blocked_task_count": 0,
        "manual_task_count": 0,
        "skipped_task_count": 0,
        "pass_rate": 1.0,
        "top_risks": [],
        "recent_evaluations": [],
        "readiness_checks": [],
        "gate_breakdown": {},
        "stack_coverage": {},
        "agent_coverage": {}
      },
      "latest_release_e2e": {
        "task_id": "task-rc",
        "description": "Release E2E scenario: web api cli",
        "task_status": "completed",
        "project_dir": "/tmp/release",
        "updated_at": 20.0,
        "benchmark": {
          "benchmark_id": "task-task-rc-rc-verification-0.4.0",
          "benchmark_version": "1.0",
          "app_version": "0.4.0",
          "status": "passed",
          "summary": {"scenario_count": 1, "passed_scenarios": 1, "failed_scenarios": 0, "min_quality_score": 70, "max_remediation_attempts": 2},
          "scenarios": [
            {"task_id": "task-rc", "status": "passed", "quality_gate": "passed", "final_status": "completed", "quality_score": 91, "remediation_attempts": 1, "produced_files": ["README.md"], "checks": {"browser_e2e_passed": true}, "failures": []}
          ]
        },
        "summary": {"status": "passed", "quality_score": 91, "remediation_attempts": 1, "failed_scenarios": 0}
      },
      "pre_release_gates": [
        {"id": "backend_regression", "label": "Backend regression", "status": "configured", "source": "local", "command": "PYTHONPATH=backend/src backend/.venv/bin/python -m pytest backend/tests -q", "detail": "Backend regression", "paths": ["backend/tests"], "required": true, "readiness_impact": "required"},
        {
          "id": "github_live_e2e",
          "label": "GitHub Live E2E",
          "status": "passed",
          "source": "github_actions",
          "command": "gh workflow run \\\"Live E2E\\\" -f tier=all --ref main",
          "detail": "Manual workflow",
          "paths": [".github/workflows/live-e2e.yml"],
          "required": true,
          "readiness_impact": "manual",
          "evidence": {
            "schema_version": "1.0",
            "gate_id": "github_live_e2e",
            "status": "passed",
            "source": "github_actions",
            "summary": "GitHub Live E2E passed.",
            "tier": "all",
            "completed_at": "2026-06-20T01:05:00Z",
            "duration_seconds": 300,
            "run_url": "https://github.com/fantasyce/across-agents-assistant/actions/runs/123"
          }
        }
      ],
      "pre_release_gate_summary": {"total": 2, "passed": 1, "configured": 1, "manual_required": 0, "missing": 0, "failed": 0, "required_missing": 0, "required_manual": 0, "required_failed": 0},
      "pre_release_gate_missing_paths": [],
      "pre_release_gate_parse_errors": [
        {"evidence_path": "broken-gate-evidence.json", "error_type": "JSONDecodeError", "message": "Expecting property name"}
      ],
      "remediations": [],
      "report_files": {
        "directory": "/tmp/release-reports",
        "json_name": "rc-verification.json",
        "json_path": "/tmp/release-reports/rc-verification.json",
        "markdown_name": "rc-verification.md",
        "markdown_path": "/tmp/release-reports/rc-verification.md"
      },
      "audit": {
        "read_only": true,
        "repair_or_resume_triggered": false,
        "secrets_redacted": true,
        "expected_files": ["README.md", "web/index.html"],
        "required_probes": ["static_web_smoke", "browser_e2e"]
      }
    }
    """.data(using: .utf8)!

    let report = try JSONDecoder().decode(ReleaseVerificationReport.self, from: json)

    assert(report.id == "release-verification-2026-05-31T12:00:00Z", "Report id should be stable")
    assert(report.status == .ready, "Status should decode")
    assert(report.latestReleaseE2E?.taskId == "task-rc", "Latest Release E2E task should decode")
    assert(report.latestReleaseE2E?.summary.qualityScore == 91, "Quality score should decode")
    assert(report.latestReleaseE2E?.compactDescription == "Release E2E scenario: web api cli", "Compact description should use the first task line")
    assert(report.reportFiles.markdownPath.hasSuffix(".md"), "Markdown report path should decode")
    assert(report.audit.readOnly, "Audit should decode read-only flag")
    assert(report.audit.secretsRedacted, "Audit should decode redaction flag")
    assert(report.readyHeadline == "Ready · Release E2E passed · score 91", "Headline should summarize RC readiness")
    assert(report.preReleaseGates?.count == 2, "Pre-release gates should decode")
    assert(report.preReleaseGates?.last?.evidence?.runURL?.hasSuffix("/123") == true, "Gate evidence run URL should decode")
    assert(report.gateSummary.passed == 1, "Passed pre-release gate count should decode")
    assert(report.gateSummary.manualRequired == 0, "Manual pre-release gate count should decode")
    assert(report.preReleaseGateMissingPaths.isEmpty, "Missing gate paths should decode")
    assert(report.preReleaseGateParseErrors.first?.evidencePath == "broken-gate-evidence.json", "Gate parse errors should decode")
    assert(report.gateHeadline == "1 passed · 1 configured · 0 manual · 0 missing", "Gate headline should summarize pre-release gates")
}

func testReleaseVerificationAttentionSummaryWithoutE2E() throws {
    let json = """
    {
      "schema_version": "1.0",
      "app_version": "0.4.0",
      "generated_at": "2026-05-31T12:00:00Z",
      "status": "attention",
      "startup": {
        "schema_version": "1.0",
        "app_version": "0.4.0",
        "generated_at": "2026-05-31T12:00:00Z",
        "status": "ready",
        "summary": {"status": "ready", "passed": 10, "warnings": 0, "failed": 0, "check_count": 10},
        "paths": {"app_home": "/tmp/a", "logs_dir": "/tmp/l", "run_dir": "/tmp/r", "tmp_dir": "/tmp/t", "evidence_dir": "/tmp/e", "socket_path": "/tmp/s", "database_path": "/tmp/db"},
        "runtime": {"pid": 1, "started_at": 1.0, "uptime_sec": 2.0, "known_tasks": 1, "persistence_initialized": true, "dispatcher_initialized": true},
        "keys": {"has_any_key": true, "providers": {"deepseek": "configured"}, "readiness_blockers": []},
        "checks": []
      },
      "release_evaluation": {"release_readiness": "no_evidence", "evaluated_task_count": 0, "terminal_task_count": 0, "passed_task_count": 0, "blocked_task_count": 0, "manual_task_count": 0, "skipped_task_count": 0, "pass_rate": 0, "top_risks": [], "recent_evaluations": [], "readiness_checks": [], "gate_breakdown": {}, "stack_coverage": {}, "agent_coverage": {}},
      "latest_release_e2e": null,
      "remediations": ["Run the fixed Release E2E scenario from the frontend and wait for passing evidence."],
      "report_files": {"directory": "/tmp/release-reports", "json_name": "rc.json", "json_path": "/tmp/release-reports/rc.json", "markdown_name": "rc.md", "markdown_path": "/tmp/release-reports/rc.md"},
      "audit": {"read_only": true, "repair_or_resume_triggered": false, "secrets_redacted": true, "expected_files": [], "required_probes": []}
    }
    """.data(using: .utf8)!

    let report = try JSONDecoder().decode(ReleaseVerificationReport.self, from: json)

    assert(report.status == .attention, "Attention status should decode")
    assert(report.latestReleaseE2E == nil, "Missing latest Release E2E should decode as nil")
    assert(report.preReleaseGates == nil, "Older reports without gate evidence should remain decodable")
    assert(report.preReleaseGateMissingPaths.isEmpty, "Older reports without missing paths should default to empty")
    assert(report.preReleaseGateParseErrors.isEmpty, "Older reports without parse errors should default to empty")
    assert(report.gateSummary.total == 0, "Missing gate summary should default to empty")
    assert(report.readyHeadline == "Attention · Release E2E missing", "Headline should call out missing E2E evidence")
    assert(report.primaryRemediation?.contains("Release E2E") == true, "Primary remediation should be available")
}

func testReleaseVerificationCompactsLongTaskDescriptions() throws {
    let longDescription = """
    Release E2E scenario: Cross-Agent Full Delivery Gate
    Scenario ID: cross_agent_full_delivery_v1
    Build a dependency-free cross-agent operations console with a very long task prompt that should not dominate diagnostics UI.
    """
    let json = """
    {
      "task_id": "task-long",
      "description": "\(longDescription.replacingOccurrences(of: "\n", with: "\\n"))",
      "task_status": "completed",
      "project_dir": "/tmp/release",
      "updated_at": 20.0,
      "benchmark": {"benchmark_id": "b", "status": "passed", "summary": {"scenario_count": 1, "passed_scenarios": 1, "failed_scenarios": 0, "min_quality_score": 70, "max_remediation_attempts": 2}, "scenarios": []},
      "summary": {"status": "passed", "quality_score": 90, "remediation_attempts": 0, "failed_scenarios": 0}
    }
    """.data(using: .utf8)!

    let latest = try JSONDecoder().decode(ReleaseVerificationLatestE2E.self, from: json)

    assert(latest.compactDescription == "Release E2E scenario: Cross-Agent Full Delivery Gate", "Compact description should not include later prompt lines")
}

@main
struct ReleaseVerificationBehavior {
    static func main() {
        do {
            try testReleaseVerificationDecodeAndSummary()
            try testReleaseVerificationAttentionSummaryWithoutE2E()
            try testReleaseVerificationCompactsLongTaskDescriptions()
            print("ReleaseVerificationBehavior passed")
        } catch {
            fatalError("ReleaseVerificationBehavior failed: \(error)")
        }
    }
}
