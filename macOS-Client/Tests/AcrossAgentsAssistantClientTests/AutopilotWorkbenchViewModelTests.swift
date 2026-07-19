import Foundation
import Testing
@testable import AcrossAgentsAssistantClient

struct AutopilotWorkbenchViewModelTests {
    @MainActor
    @Test func firstLoadPersistsAndLaterInstancesReuseTheSnapshot() async throws {
        let cacheURL = try makeCacheURL()
        defer { try? FileManager.default.removeItem(at: cacheURL.deletingLastPathComponent()) }
        let response = successfulResponse()
        let body = snapshotBody(runCount: 1)
        var firstCalls = 0
        let first = AutopilotWorkbenchViewModel(
            cacheURL: cacheURL,
            dataLoader: { _ in
                firstCalls += 1
                return (body, response)
            }
        )

        await first.load()

        #expect(firstCalls == 1)
        #expect(first.snapshot?.summary.runCount == 1)
        #expect(FileManager.default.fileExists(atPath: cacheURL.path))
        let permissions = try #require(
            try FileManager.default.attributesOfItem(atPath: cacheURL.path)[.posixPermissions] as? NSNumber
        )
        #expect(permissions.intValue & 0o777 == 0o600)

        var laterCalls = 0
        let later = AutopilotWorkbenchViewModel(
            cacheURL: cacheURL,
            dataLoader: { _ in
                laterCalls += 1
                return (body, response)
            }
        )

        #expect(later.snapshot?.summary.runCount == 1)
        await later.load()
        #expect(laterCalls == 0)
    }

    @MainActor
    @Test func manualRefreshReplacesThePersistedSnapshot() async throws {
        let cacheURL = try makeCacheURL()
        defer { try? FileManager.default.removeItem(at: cacheURL.deletingLastPathComponent()) }
        let response = successfulResponse()
        var bodies = [snapshotBody(runCount: 1), snapshotBody(runCount: 2)]
        let viewModel = AutopilotWorkbenchViewModel(
            cacheURL: cacheURL,
            dataLoader: { request in
                #expect(request.url?.path == "/api/autopilot/workbench" || request.url?.path == "/api/autopilot/workbench/refresh")
                return (bodies.removeFirst(), response)
            }
        )

        await viewModel.load()
        await viewModel.load(refresh: true)

        #expect(viewModel.snapshot?.summary.runCount == 2)
        let persisted = try JSONDecoder().decode(
            AutopilotWorkbenchSnapshot.self,
            from: Data(contentsOf: cacheURL)
        )
        #expect(persisted.summary.runCount == 2)
    }

    @MainActor
    @Test func failedRefreshKeepsTheLastUsableSnapshot() async throws {
        let cacheURL = try makeCacheURL()
        defer { try? FileManager.default.removeItem(at: cacheURL.deletingLastPathComponent()) }
        try snapshotBody(runCount: 3).write(to: cacheURL, options: .atomic)
        let failure = HTTPURLResponse(
            url: URL(string: "http://backend/api/autopilot/workbench/refresh")!,
            statusCode: 503,
            httpVersion: "HTTP/1.1",
            headerFields: nil
        )!
        let viewModel = AutopilotWorkbenchViewModel(
            cacheURL: cacheURL,
            dataLoader: { _ in
                (Data(#"{"detail":"refresh unavailable"}"#.utf8), failure)
            }
        )

        #expect(viewModel.snapshot?.summary.runCount == 3)
        await viewModel.load(refresh: true)

        #expect(viewModel.snapshot?.summary.runCount == 3)
        #expect(viewModel.errorMessage == "refresh unavailable")
    }

    @MainActor
    @Test func ecosystemActionShowsInlineResultAndRefreshesTheSnapshot() async throws {
        let response = successfulResponse()
        var requests: [String] = []
        let viewModel = AutopilotWorkbenchViewModel(
            cacheURL: nil,
            dataLoader: { request in
                requests.append("\(request.httpMethod ?? "GET") \(request.url?.path ?? "")?\(request.url?.query ?? "")")
                if request.url?.path == "/api/ecosystem/agent-plugins" {
                    return (
                        Data(#"{"id":"agent_plugin_runtime","title":"Agent Plugins","status":"passed","summary":{},"items":[],"endpoint":"/api/ecosystem/agent-plugins"}"#.utf8),
                        response
                    )
                }
                return (snapshotBody(runCount: 1), response)
            }
        )
        let action = AutopilotWorkbenchAction(
            id: "advance_agent_plugin_runtime",
            priority: "medium",
            title: "Recheck Agent plugins",
            reason: "Probe the runtimes",
            endpoint: "/api/ecosystem/agent-plugins"
        )

        await viewModel.checkEcosystemAction(
            action,
            runningMessage: "Checking...",
            successMessage: "Passed",
            attentionMessage: "Needs attention",
            failureMessage: "Failed"
        )

        #expect(requests.first == "GET /api/ecosystem/agent-plugins?refresh=true")
        #expect(requests.last == "POST /api/autopilot/workbench/refresh?")
        #expect(viewModel.activeActionID == nil)
        #expect(viewModel.actionNotice == AutopilotWorkbenchActionNotice(
            actionID: "advance_agent_plugin_runtime",
            status: "passed",
            message: "Passed"
        ))
    }

    @MainActor
    @Test func agentInteropActionPollsBackgroundRunAndKeepsRowFeedback() async throws {
        let response = successfulResponse()
        var requests: [String] = []
        let viewModel = AutopilotWorkbenchViewModel(
            cacheURL: nil,
            dataLoader: { request in
                let key = "\(request.httpMethod ?? "GET") \(request.url?.path ?? "")"
                requests.append(key)
                if key == "POST /api/autopilot/agent-interop-e2e" {
                    return (
                        Data(#"{"status":"failed","summary":{"failed_count":2},"run_state":{"status":"running","failed_count":0}}"#.utf8),
                        response
                    )
                }
                if key == "GET /api/autopilot/agent-interop-e2e" {
                    return (
                        Data(#"{"status":"passed","summary":{"failed_count":0},"run_state":{"status":"passed","failed_count":0}}"#.utf8),
                        response
                    )
                }
                return (snapshotBody(runCount: 1), response)
            }
        )

        await viewModel.runAgentInteropE2E(
            successMessage: "Compatibility passed",
            failureMessage: "Compatibility failed: %d",
            runningMessage: "Checking compatibility...",
            actionID: "run_agent_interop_e2e",
            pollIntervalNanoseconds: 0,
            maxPollAttempts: 3
        )

        #expect(requests == [
            "POST /api/autopilot/agent-interop-e2e",
            "GET /api/autopilot/agent-interop-e2e",
            "POST /api/autopilot/workbench/refresh",
        ])
        #expect(viewModel.activeActionID == nil)
        #expect(viewModel.actionNotice == AutopilotWorkbenchActionNotice(
            actionID: "run_agent_interop_e2e",
            status: "passed",
            message: "Compatibility passed"
        ))
    }

    private func makeCacheURL() throws -> URL {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("autopilot-workbench-cache-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        return directory.appendingPathComponent("snapshot.json")
    }

    private func successfulResponse() -> HTTPURLResponse {
        HTTPURLResponse(
            url: URL(string: "http://backend/api/autopilot/workbench")!,
            statusCode: 200,
            httpVersion: "HTTP/1.1",
            headerFields: nil
        )!
    }

    private func snapshotBody(runCount: Int) -> Data {
        Data("""
        {
          "schema_version": "across-aaa-autopilot-workbench/1.0",
          "status": "passed",
          "summary": {
            "run_count": \(runCount),
            "completed_run_count": \(runCount),
            "failed_run_count": 0,
            "pending_trigger_count": 0,
            "registered_trigger_count": 0,
            "active_trigger_count": 0,
            "scheduler_running": false,
            "self_iteration_status": "not_configured",
            "capability_ready_count": 1,
            "registry_health_status": "passed",
            "pending_memory_count": 0,
            "promotion_ready_count": 0,
            "autopilot_available": true,
            "ecosystem_route_count": 0,
            "ecosystem_ready_route_count": 0,
            "agent_plugin_count": 0,
            "ready_agent_plugin_count": 0,
            "agent_interop_e2e_status": "not_run"
          },
          "status_reasons": [],
          "sections": {},
          "actions": [],
          "endpoints": {}
        }
        """.utf8)
    }
}
