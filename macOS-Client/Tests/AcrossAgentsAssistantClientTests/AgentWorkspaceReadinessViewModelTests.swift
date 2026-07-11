import Foundation
import Testing
@testable import AcrossAgentsAssistantClient

struct AgentWorkspaceReadinessViewModelTests {
    @Test func refreshRequestIsReadOnlyAndTargetsBackendEndpoint() {
        let request = AgentWorkspaceReadinessViewModel.makeRequest(
            backendBase: URL(string: "http://backend")!,
            refresh: true
        )

        #expect(request.httpMethod == "GET")
        #expect(request.url?.absoluteString == "http://backend/api/agent-workspaces/readiness?refresh=true")
        #expect(request.value(forHTTPHeaderField: "Accept") == "application/json")
    }

    @MainActor
    @Test func loadDecodesReadinessSnapshot() async throws {
        let body = """
        {
          "schema_version": "agent-workspace-readiness/1.0",
          "status": "ready",
          "workspace_isolation": {
            "status": "ready",
            "supports_git_worktree": true,
            "can_create_isolated_workspaces": true
          },
          "agents": [
            {"agent_id": "codex", "status": "ready", "available": true}
          ],
          "routes": {
            "events": "/events",
            "diff": "/diff",
            "evidence": "/evidence"
          }
        }
        """.data(using: .utf8)!
        let response = HTTPURLResponse(
            url: URL(string: "http://backend/api/agent-workspaces/readiness")!,
            statusCode: 200,
            httpVersion: "HTTP/1.1",
            headerFields: nil
        )!
        let viewModel = AgentWorkspaceReadinessViewModel(dataLoader: { request in
            #expect(request.url?.path == "/api/agent-workspaces/readiness")
            return (body, response)
        })

        await viewModel.load()

        #expect(viewModel.errorMessage == nil)
        #expect(viewModel.snapshot?.readyAgentIds == ["codex"])
        #expect(viewModel.snapshot?.canCreateWorkspace == true)
    }

    @MainActor
    @Test func initialLoadRetriesTransientSocketFailures() async throws {
        let body = """
        {
          "status": "partial",
          "workspace_isolation": {"status": "not_implemented"},
          "agents": [],
          "routes": {}
        }
        """.data(using: .utf8)!
        let response = HTTPURLResponse(
            url: URL(string: "http://backend/api/agent-workspaces/readiness")!,
            statusCode: 200,
            httpVersion: "HTTP/1.1",
            headerFields: nil
        )!
        var calls = 0
        let viewModel = AgentWorkspaceReadinessViewModel(dataLoader: { _ in
            calls += 1
            if calls == 1 {
                throw URLError(.cannotConnectToHost)
            }
            return (body, response)
        })

        await viewModel.load(retryTransportFailures: 1)

        #expect(calls == 2)
        #expect(viewModel.snapshot?.status == .partial)
        #expect(viewModel.errorMessage == nil)
    }

    @MainActor
    @Test func loadSurfacesBackendDetailErrors() async throws {
        let body = #"{"detail":"readiness unavailable"}"#.data(using: .utf8)!
        let response = HTTPURLResponse(
            url: URL(string: "http://backend/api/agent-workspaces/readiness")!,
            statusCode: 503,
            httpVersion: "HTTP/1.1",
            headerFields: nil
        )!
        let viewModel = AgentWorkspaceReadinessViewModel(dataLoader: { _ in
            (body, response)
        })

        await viewModel.load(refresh: true)

        #expect(viewModel.snapshot == nil)
        #expect(viewModel.errorMessage == "readiness unavailable")
    }

    @MainActor
    @Test func failedRefreshClearsStaleSnapshot() async throws {
        let successBody = """
        {
          "schema_version": "agent-workspace-readiness/1.0",
          "status": "partial",
          "workspace_isolation": {"status": "not_implemented"},
          "agents": [{"agent_id": "codex", "status": "ready", "available": true}],
          "routes": {}
        }
        """.data(using: .utf8)!
        let successResponse = HTTPURLResponse(
            url: URL(string: "http://backend/api/agent-workspaces/readiness")!,
            statusCode: 200,
            httpVersion: "HTTP/1.1",
            headerFields: nil
        )!
        let failureResponse = HTTPURLResponse(
            url: URL(string: "http://backend/api/agent-workspaces/readiness")!,
            statusCode: 503,
            httpVersion: "HTTP/1.1",
            headerFields: nil
        )!
        var calls = 0
        let viewModel = AgentWorkspaceReadinessViewModel(dataLoader: { _ in
            calls += 1
            if calls == 1 {
                return (successBody, successResponse)
            }
            return (#"{"detail":"backend down"}"#.data(using: .utf8)!, failureResponse)
        })

        await viewModel.load()
        #expect(viewModel.snapshot?.readyAgentIds == ["codex"])

        await viewModel.load(refresh: true)

        #expect(viewModel.snapshot == nil)
        #expect(viewModel.errorMessage == "backend down")
    }

    @MainActor
    @Test func loadUsesHttpFallbackWhenBackendDetailIsMissing() async throws {
        let response = HTTPURLResponse(
            url: URL(string: "http://backend/api/agent-workspaces/readiness")!,
            statusCode: 502,
            httpVersion: "HTTP/1.1",
            headerFields: nil
        )!
        let viewModel = AgentWorkspaceReadinessViewModel(dataLoader: { _ in
            (Data("{}".utf8), response)
        })

        await viewModel.load()

        #expect(viewModel.snapshot == nil)
        #expect(viewModel.errorMessage == "HTTP 502")
    }

    @MainActor
    @Test func loadReportsNonHttpResponses() async throws {
        let response = URLResponse(
            url: URL(string: "http://backend/api/agent-workspaces/readiness")!,
            mimeType: "application/json",
            expectedContentLength: 0,
            textEncodingName: nil
        )
        let viewModel = AgentWorkspaceReadinessViewModel(dataLoader: { _ in
            (Data(), response)
        })

        await viewModel.load()

        #expect(viewModel.snapshot == nil)
        #expect(viewModel.errorMessage?.isEmpty == false)
    }

    @MainActor
    @Test func loadReportsInvalidJsonWithoutKeepingStaleErrors() async throws {
        let response = HTTPURLResponse(
            url: URL(string: "http://backend/api/agent-workspaces/readiness")!,
            statusCode: 200,
            httpVersion: "HTTP/1.1",
            headerFields: nil
        )!
        let viewModel = AgentWorkspaceReadinessViewModel(dataLoader: { _ in
            (Data("{".utf8), response)
        })

        await viewModel.load()

        #expect(viewModel.snapshot == nil)
        #expect(viewModel.errorMessage?.isEmpty == false)
    }
}
