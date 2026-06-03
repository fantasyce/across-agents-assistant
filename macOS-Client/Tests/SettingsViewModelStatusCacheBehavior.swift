import Combine
import Foundation

func assert(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() {
        fatalError(message)
    }
}

@main
struct SettingsViewModelStatusCacheBehavior {
    @MainActor
    static func main() {
        let vm = SettingsViewModel(bootstrapOnInit: false, loadPersisted: false)
        vm.localAgents = [.localAgent, .hermes, .claude, .codex]
        vm.cloudLLMs = [.deepSeek, .miniMax]
        vm.apiKeyStatusCache = [:]

        var publishCount = 0
        let cancellable = vm.objectWillChange.sink { _ in
            publishCount += 1
        }

        vm.applyBackendKeyStatuses(["deepseek": "configured", "minimax": "configured"])

        assert(vm.availableCloudLLMs.map(\.id) == ["deepseek", "minimax"], "backend key statuses should expose configured cloud LLMs")
        assert(vm.visibleAgentIds == ["deepseek", "minimax"], "visible agents should include configured cloud LLMs immediately")
        assert(vm.availabilityBootstrapState == .loading, "backend key statuses alone should not finish startup availability")
        assert(!vm.shouldShowRightSidebar, "right sidebar should stay hidden until full availability bootstrap completes")
        assert(publishCount > 0, "applying backend key statuses should publish UI updates")

        vm.completeBackendReadyAvailabilityBootstrap()
        assert(vm.availabilityBootstrapState == .ready, "startup availability should become ready after backend keys are refreshed without waiting for local agent detection")
        assert(vm.shouldShowRightSidebar, "right sidebar should appear once startup availability is complete and cloud LLMs are configured")

        let diagnosticsJSON = """
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
        let diagnostics = try! JSONDecoder().decode(StartupDiagnosticsReport.self, from: diagnosticsJSON)
        vm.startupDiagnosticsError = "old error"
        vm.applyStartupDiagnosticsReport(diagnostics)

        assert(vm.startupDiagnostics?.status == .ready, "startup diagnostics should be cached for the diagnostics page")
        assert(vm.startupDiagnosticsError == nil, "applying diagnostics should clear old errors")

        let releaseVerificationJSON = """
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
            "runtime": {"pid": 1, "started_at": 1.0, "uptime_sec": 2.0, "known_tasks": 1, "persistence_initialized": true, "orchestrator_initialized": true, "dispatcher_initialized": true},
            "keys": {"has_any_key": true, "providers": {"deepseek": "configured"}, "readiness_blockers": []},
            "checks": []
          },
          "release_evaluation": {"release_readiness": "ready", "evaluated_task_count": 1, "terminal_task_count": 1, "passed_task_count": 1, "blocked_task_count": 0, "manual_task_count": 0, "skipped_task_count": 0, "pass_rate": 1, "top_risks": [], "recent_evaluations": [], "readiness_checks": [], "gate_breakdown": {}, "stack_coverage": {}, "agent_coverage": {}},
          "latest_release_e2e": null,
          "remediations": [],
          "report_files": {"directory": "/tmp/release-reports", "json_name": "rc.json", "json_path": "/tmp/release-reports/rc.json", "markdown_name": "rc.md", "markdown_path": "/tmp/release-reports/rc.md"},
          "audit": {"read_only": true, "repair_or_resume_triggered": false, "secrets_redacted": true, "expected_files": [], "required_probes": []}
        }
        """.data(using: .utf8)!
        let releaseVerification = try! JSONDecoder().decode(ReleaseVerificationReport.self, from: releaseVerificationJSON)
        vm.releaseVerificationError = "old release error"
        vm.applyReleaseVerificationReport(releaseVerification)

        assert(vm.releaseVerificationReport?.status == .ready, "release verification report should be cached for the diagnostics page")
        assert(vm.releaseVerificationError == nil, "applying release verification should clear old errors")

        cancellable.cancel()
        print("SettingsViewModelStatusCacheBehavior passed")
    }
}
