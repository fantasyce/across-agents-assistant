import Foundation

func remoteGateAssert(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fatalError(message) }
}

@MainActor
func testRemoteRequestAndConfirmation() async throws {
    var draft = QualityGateRunDraft()
    draft.repoRoot = "/tmp/repository"
    draft.branch = "feature/remote-quality"
    draft.operationMode = .approvedRemoteDraftPR
    draft.ciIdleTimeoutSeconds = 1_200
    draft.ciMaxWallTimeoutSeconds = 8_400

    let request = try QualityGateViewModel.makeRunRequest(
        backendBase: URL(string: "http://backend")!,
        payload: draft.request()
    )
    let body = try JSONSerialization.jsonObject(with: request.httpBody ?? Data()) as? [String: Any]
    remoteGateAssert(body?["push_branch"] as? Bool == true, "Remote mode must explicitly request a branch push")
    remoteGateAssert(body?["approve_remote"] as? Bool == true, "Remote mode must carry one-run approval intent")
    remoteGateAssert(body?["draft_pr"] as? Bool == true, "Remote mode must stay draft-only")
    remoteGateAssert(body?["watch_ci"] as? Bool == true, "Remote mode must encode CI watch intent")
    remoteGateAssert(body?["ci_idle_timeout_seconds"] as? Int == 1_200, "CI idle timeout contract changed")
    remoteGateAssert(body?["ci_max_wall_timeout_seconds"] as? Int == 8_400, "CI wall timeout contract changed")
    remoteGateAssert(
        body?.keys.contains(where: {
            let key = $0.lowercased()
            return key.contains("token") || key.contains("credential") || key.contains("secret")
        }) == false,
        "Quality Gate UI must never send credentials"
    )

    var requestCount = 0
    let viewModel = QualityGateViewModel(dataLoader: { request in
        requestCount += 1
        let response = HTTPURLResponse(
            url: request.url!,
            statusCode: 200,
            httpVersion: "HTTP/1.1",
            headerFields: nil
        )!
        return (remoteGateFixture, response)
    })
    viewModel.draft = draft

    await viewModel.run()
    remoteGateAssert(viewModel.isRemoteConfirmationPresented, "Remote mode must stop at confirmation")
    remoteGateAssert(requestCount == 0, "Remote request escaped before confirmation")

    await viewModel.confirmRemoteRun()
    remoteGateAssert(requestCount == 1, "Confirmed remote request was not sent exactly once")
    remoteGateAssert(viewModel.result?.githubRemote?.pullRequest?.number == 42, "Draft PR receipt did not decode")
    remoteGateAssert(viewModel.result?.githubRemote?.verificationMode == "commit_status_fallback", "Verification fallback did not decode")
    remoteGateAssert(viewModel.result?.githubRemote?.ciWatch?.heartbeats.last?.pendingCount == 0, "CI heartbeat did not decode")
}

@MainActor
func testRecoverableTransportFailure() async {
    let viewModel = QualityGateViewModel(dataLoader: { _ in throw URLError(.timedOut) })
    viewModel.draft.repoRoot = "/tmp/repository"
    await viewModel.run()
    remoteGateAssert(viewModel.failure?.recoverable == true, "Transport timeout must remain recoverable")
    remoteGateAssert(viewModel.failure?.recoveryHint.contains("same repository and branch") == true, "Retry guidance lost idempotent context")
}

private let remoteGateFixture = Data("""
{
  "status": "completed",
  "repository": {"name": "fixture"},
  "base_ref": "main",
  "head_ref": "feature/remote-quality",
  "head_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "gate_verdict": "pass",
  "github_remote": {
    "schema_version": "across-autopilot-github-remote/1.0",
    "status": "completed",
    "mutation_performed": true,
    "remote_state_requires_reconciliation": false,
    "recoverable": true,
    "secret_material_persisted": false,
    "pull_request": {"number": 42, "url": "https://github.com/owner/repository/pull/42", "state": "OPEN", "draft": true},
    "ci_watch": {
      "status": "completed",
      "polls": 2,
      "heartbeats": [{"sequence": 2, "check_count": 2, "pending_count": 0}],
      "snapshot": {"mode": "github_actions", "status": "passed", "taxonomy": ["passed"], "counts": {"passed": 2}, "checks": []}
    },
    "operations": [{"id": "check_run", "status": "created", "verification_mode": "commit_status_fallback"}],
    "errors": []
  }
}
""".utf8)

@main
struct QualityGateRemoteBehavior {
    static func main() async throws {
        try await testRemoteRequestAndConfirmation()
        await testRecoverableTransportFailure()
        print("Quality Gate remote behavior checks passed.")
    }
}
