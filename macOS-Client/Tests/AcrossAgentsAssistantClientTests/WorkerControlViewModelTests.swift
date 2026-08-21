import Foundation
import Testing
@testable import AcrossAgentsAssistantClient

struct WorkerControlViewModelTests {
    @Test func snapshotRequestIsReadOnlyAndUsesWorkerControlEndpoint() {
        let request = WorkerControlViewModel.makeSnapshotRequest(backendBase: URL(string: "http://backend")!)
        #expect(request.httpMethod == "GET")
        #expect(request.url?.absoluteString == "http://backend/api/worker-control")
    }

    @MainActor
    @Test func loadDecodesEmptyAndHealthyLocalOnlyState() async throws {
        let body = """
        {
          "schema_version": "across-aaa-worker-control/1.0",
          "nodes": [],
          "pending": [],
          "listener": {"enabled": false, "bind_host": null, "port": 0, "model_gateway_port": 0,
            "runtime": {"status": "stopped", "listener_running": false, "model_gateway_running": false,
              "last_error": null, "tls_minimum": null, "host_credentials_copied": false}},
          "relay": {"enabled": false, "endpoint": null, "status": "disabled"},
          "health": {
            "status": "ok", "node_count": 0, "online_count": 0, "pending_count": 0,
            "incompatible_count": 0, "listener_enabled": false, "relay_enabled": false
          },
          "recovery": null
        }
        """.data(using: .utf8)!
        let response = HTTPURLResponse(
            url: URL(string: "http://backend/api/worker-control")!,
            statusCode: 200,
            httpVersion: "HTTP/1.1",
            headerFields: nil
        )!
        let viewModel = WorkerControlViewModel(dataLoader: { request in
            #expect(request.url?.path == "/api/worker-control")
            return (body, response)
        })

        await viewModel.load()

        #expect(viewModel.errorMessage == nil)
        #expect(viewModel.snapshot?.health.status == "ok")
        #expect(viewModel.snapshot?.nodes.isEmpty == true)
        #expect(viewModel.snapshot?.listener.runtime?.status == "stopped")
        #expect(viewModel.snapshot?.listener.runtime?.hostCredentialsCopied == false)
    }

    @Test func workerStringsCoverEnglishAndChinese() {
        for key in [
            "workers.title", "workers.pending.title", "workers.nodes.title", "workers.add.title",
            "workers.connection.title", "workers.approve", "workers.revoke", "workers.state.online_idle",
            "workers.state.reconnecting", "workers.reconnecting",
            "workers.direct.runtime.running", "workers.direct.runtime.degraded", "workers.direct.error.start",
        ] {
            #expect(AppPreferences.localizedString(key, localeIdentifier: "en") != key)
            #expect(AppPreferences.localizedString(key, localeIdentifier: "zh-Hans") != key)
        }
    }

    @Test func recentlySeenOfflineWorkerIsPresentedAsReconnecting() {
        #expect(WorkerNode.presentationState(reportedState: "offline", lastSeenAt: 980, now: 1_000) == "reconnecting")
        #expect(WorkerNode.presentationState(reportedState: "offline", lastSeenAt: 900, now: 1_000) == "offline")
        #expect(WorkerNode.presentationState(reportedState: "revoked", lastSeenAt: 999, now: 1_000) == "revoked")
    }
}
