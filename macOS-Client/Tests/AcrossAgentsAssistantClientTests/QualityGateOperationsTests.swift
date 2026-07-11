import Foundation
import Testing
@testable import AcrossAgentsAssistantClient

struct QualityGateOperationsTests {
    @Test func runRequestEncodesCurrentBackendContract() throws {
        var draft = QualityGateRunDraft()
        draft.repoRoot = " /tmp/repository "
        draft.baseRef = "main"
        draft.headRef = "HEAD"
        draft.branch = "feature/quality"
        draft.commit = "abc123"
        draft.ciPath = "/tmp/ci.json"
        draft.ciWaitSeconds = 120
        draft.maxRepairs = 2
        draft.draftPR = true

        let request = try QualityGateViewModel.makeRunRequest(
            backendBase: URL(string: "http://backend")!,
            payload: draft.request()
        )
        let requestData = try #require(request.httpBody)
        let object = try #require(
            JSONSerialization.jsonObject(with: requestData) as? [String: Any]
        )

        #expect(request.httpMethod == "POST")
        #expect(request.url?.path == "/api/quality-gates/run")
        #expect(object["repo_root"] as? String == "/tmp/repository")
        #expect(object["base_ref"] as? String == "main")
        #expect(object["head_ref"] as? String == "HEAD")
        #expect(object["branch"] as? String == "feature/quality")
        #expect(object["commit"] as? String == "abc123")
        #expect(object["ci_path"] as? String == "/tmp/ci.json")
        #expect(object["ci_wait_seconds"] as? Int == 120)
        #expect(object["max_repairs"] as? Int == 2)
        #expect(object["draft_pr"] as? Bool == true)
        #expect(object["timeout_seconds"] as? Int == 900)
        #expect(object["push_branch"] == nil)
        #expect(object["approve_remote"] == nil)
        #expect(object["watch_ci"] == nil)
        #expect(object.keys.contains(where: { $0.lowercased().contains("token") }) == false)
    }

    @Test func approvedRemoteRequestCarriesExplicitIntentTimeoutsAndNoCredentials() throws {
        var draft = QualityGateRunDraft()
        draft.repoRoot = "/tmp/repository"
        draft.operationMode = .approvedRemoteDraftPR
        draft.branch = "feature/remote-quality"
        draft.watchCI = true
        draft.ciIdleTimeoutSeconds = 1_200
        draft.ciMaxWallTimeoutSeconds = 8_400

        let payload = try draft.request()
        let request = try QualityGateViewModel.makeRunRequest(
            backendBase: URL(string: "http://backend")!,
            payload: payload
        )
        let data = try #require(request.httpBody)
        let object = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])

        #expect(object["draft_pr"] as? Bool == true)
        #expect(object["push_branch"] as? Bool == true)
        #expect(object["approve_remote"] as? Bool == true)
        #expect(object["watch_ci"] as? Bool == true)
        #expect(object["ci_idle_timeout_seconds"] as? Int == 1_200)
        #expect(object["ci_max_wall_timeout_seconds"] as? Int == 8_400)
        #expect(request.timeoutInterval == 8_580)
        #expect(object.keys.contains(where: { key in
            let normalized = key.lowercased()
            return normalized.contains("token") || normalized.contains("credential") || normalized.contains("secret")
        }) == false)
    }

    @Test func remoteModeRejectsUnsafeBranchAndInvalidTimeoutRelationship() {
        var draft = QualityGateRunDraft()
        draft.repoRoot = "/tmp/repository"
        draft.operationMode = .approvedRemoteDraftPR
        draft.branch = "main"
        #expect(draft.validationError?.contains("feature branch") == true)

        draft.branch = "feature/remote-quality"
        draft.ciIdleTimeoutSeconds = 1_000
        draft.ciMaxWallTimeoutSeconds = 900
        #expect(draft.validationError?.contains("cannot exceed") == true)
    }

    @Test func blockedResultDecodesAsCompleteStructuredEvidence() throws {
        let result = try JSONDecoder().decode(QualityGateResult.self, from: Self.blockedResultData)

        #expect(result.isBlocked)
        #expect(result.gateVerdict == "blocked")
        #expect(result.findings.first?.state == "blocked")
        #expect(result.gitBinding?.expectedCommit == "abc123")
        #expect(result.pushReceipt?.evidenceHash == String(repeating: "a", count: 64))
        #expect(result.ci?.taxonomy.contains("failed_security") == true)
        #expect(result.ci?.watcher?.mode == "snapshot_file")
        #expect(result.repairPlan?.status == "planned")
        #expect(result.draftPR?.status == "blocked")
        #expect(result.draftPR?.mutationPerformed == false)
    }

    @MainActor
    @Test func viewModelKeepsBlockedHTTP200AsResultInsteadOfTransportError() async {
        let viewModel = QualityGateViewModel(dataLoader: { request in
            #expect(request.httpMethod == "POST")
            #expect(request.url?.path == "/api/quality-gates/run")
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 200,
                httpVersion: "HTTP/1.1",
                headerFields: nil
            )!
            return (Self.blockedResultData, response)
        })
        viewModel.draft.repoRoot = "/tmp/repository"

        await viewModel.run()

        #expect(viewModel.errorMessage == nil)
        #expect(viewModel.result?.gateVerdict == "blocked")
        #expect(viewModel.contentState == .success("blocked"))
        #expect(viewModel.reviewSignals.first?.kind == .blockingGate)
    }

    @MainActor
    @Test func remoteModeRequiresConfirmationBeforeSendingAndThenDecodesReceipt() async throws {
        var requestCount = 0
        let viewModel = QualityGateViewModel(dataLoader: { request in
            requestCount += 1
            let data = try #require(request.httpBody)
            let body = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
            #expect(body["approve_remote"] as? Bool == true)
            #expect(body["push_branch"] as? Bool == true)
            let response = try #require(HTTPURLResponse(
                url: request.url!,
                statusCode: 200,
                httpVersion: "HTTP/1.1",
                headerFields: nil
            ))
            return (Self.remoteResultData, response)
        })
        viewModel.draft.repoRoot = "/tmp/repository"
        viewModel.draft.operationMode = .approvedRemoteDraftPR
        viewModel.draft.branch = "feature/remote-quality"

        await viewModel.run()
        #expect(viewModel.isRemoteConfirmationPresented)
        #expect(requestCount == 0)
        #expect(viewModel.result == nil)

        await viewModel.confirmRemoteRun()
        #expect(requestCount == 1)
        #expect(viewModel.isRemoteConfirmationPresented == false)
        #expect(viewModel.result?.githubRemote?.pullRequest?.number == 42)
        #expect(viewModel.result?.githubRemote?.verificationMode == "commit_status_fallback")
        #expect(viewModel.result?.githubRemote?.ciWatch?.heartbeats.last?.pendingCount == 0)
        #expect(viewModel.result?.githubRemote?.recoverable == true)
    }

    @MainActor
    @Test func transportTimeoutIsExposedAsRecoverableWithoutLosingRetryContext() async {
        let viewModel = QualityGateViewModel(dataLoader: { _ in
            throw URLError(.timedOut)
        })
        viewModel.draft.repoRoot = "/tmp/repository"

        await viewModel.run()

        #expect(viewModel.failure?.recoverable == true)
        #expect(viewModel.failure?.recoveryHint.contains("same repository and branch") == true)
        #expect(viewModel.result == nil)
    }

    @Test func activityStatusSeparatesActiveIdleAndMaximumWallBoundaries() {
        var activity = QualityGateRunActivity(
            remote: true,
            startedAt: Date(),
            elapsedSeconds: 29,
            idleTimeoutSeconds: 30,
            maxWallTimeoutSeconds: 60
        )
        #expect(activity.status == .active)
        activity.elapsedSeconds = 30
        #expect(activity.status == .idle)
        activity.elapsedSeconds = 60
        #expect(activity.status == .maxWallExceeded)
    }

    private static let blockedResultData = """
    {
      "schema_version": "across-autopilot-gate-result/1.0",
      "status": "completed",
      "repository": {"name": "fixture", "path": "/tmp/repository"},
      "base_ref": "main",
      "head_ref": "HEAD",
      "head_sha": "abc123",
      "dirty_tree": false,
      "findings": [{
        "id": "secret",
        "state": "blocked",
        "severity": "critical",
        "summary": "A secret pattern requires review.",
        "suggested_action": "Remove the secret.",
        "owner": "fixture",
        "source_gate": "secret"
      }],
      "gate_verdict": "blocked",
      "evidence_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "pr_ready_summary": "Not PR-ready: blocking findings remain.",
      "checks": {
        "commands": [{"id": "lint", "category": "lint", "status": "passed", "argv": ["swift", "test"]}],
        "tools": [],
        "policies": {"secrets": "required"}
      },
      "git_binding": {
        "base_sha": "base123",
        "head_sha": "abc123",
        "current_head_sha": "abc123",
        "branch": "feature/quality",
        "expected_branch": "feature/quality",
        "expected_commit": "abc123",
        "base_is_ancestor": true,
        "dirty_paths": []
      },
      "push_receipt": {
        "schema_version": "across-autopilot-push-receipt/1.0",
        "repository": {"name": "fixture"},
        "base_ref": "main",
        "head_ref": "HEAD",
        "head_sha": "abc123",
        "dirty_tree": false,
        "gate_verdict": "blocked",
        "evidence_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "pr_ready_summary": "Not PR-ready: blocking findings remain."
      },
      "ci": {
        "schema_version": "across-autopilot-ci-watch/1.0",
        "mode": "snapshot",
        "status": "failed",
        "taxonomy": ["passed", "failed_security"],
        "counts": {"passed": 1, "failed_security": 1},
        "checks": [{"id": "codeql", "name": "CodeQL", "category": "security", "status": "failed_security", "required": true}],
        "watcher": {"mode": "snapshot_file", "status": "observed", "max_wait_seconds": 0, "deterministic_snapshot": true}
      },
      "repair_plan": {
        "status": "planned",
        "mutation_performed": false,
        "current_round": 0,
        "max_rounds": 2,
        "max_actions": 2,
        "actions": [{
          "id": "repair-security-1",
          "category": "security",
          "source_finding_ids": ["secret"],
          "suggested_action": "Remove the secret.",
          "remaining_rounds": 2,
          "execution": "planned_only",
          "command_source": "trusted_baseline_only"
        }]
      },
      "draft_pr": {
        "status": "blocked",
        "requested": true,
        "ready": false,
        "mutation_performed": false,
        "remote_mutation_allowed": false,
        "blocking_reasons": ["gate_verdict:blocked"]
      }
    }
    """.data(using: .utf8)!

    private static let remoteResultData = """
    {
      "schema_version": "across-autopilot-gate-result/1.0",
      "status": "completed",
      "repository": {"name": "fixture", "path": "/tmp/repository"},
      "base_ref": "main",
      "head_ref": "feature/remote-quality",
      "head_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "dirty_tree": false,
      "findings": [],
      "gate_verdict": "pass",
      "github_remote": {
        "schema_version": "across-autopilot-github-remote/1.0",
        "status": "completed",
        "mutation_performed": true,
        "remote_state_requires_reconciliation": false,
        "recoverable": true,
        "secret_material_persisted": false,
        "authorization": {
          "requested": true,
          "allowed": true,
          "repository": "owner/repository",
          "host": "github.com",
          "push_requested": true,
          "push_ref": "refs/heads/feature/remote-quality",
          "approval_token_verified": true,
          "credential_present": true,
          "secret_material_included": false
        },
        "branch_push": {
          "status": "created",
          "mutation_performed": true,
          "resumed": false,
          "reconciled": true,
          "source_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
          "target_ref": "refs/heads/feature/remote-quality",
          "remote_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        },
        "pull_request": {
          "number": 42,
          "url": "https://github.com/owner/repository/pull/42",
          "state": "OPEN",
          "draft": true,
          "head_ref": "feature/remote-quality",
          "base_ref": "main"
        },
        "ci_watch": {
          "status": "completed",
          "polls": 3,
          "heartbeats": [{
            "sequence": 3,
            "observed_at": "2026-07-11T10:00:00.000Z",
            "check_count": 2,
            "pending_count": 0,
            "snapshot_sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
          }],
          "snapshot": {
            "mode": "github_actions",
            "status": "passed",
            "taxonomy": ["passed"],
            "counts": {"passed": 2},
            "checks": [],
            "watcher": {
              "mode": "github_actions_poll",
              "status": "completed",
              "polls": 3,
              "heartbeat_refresh": true,
              "idle_timeout_ms": 900000,
              "max_wall_timeout_ms": 7200000,
              "elapsed_ms": 15000,
              "last_heartbeat_at": "2026-07-11T10:00:00.000Z"
            }
          },
          "failure_summaries": []
        },
        "operations": [{
          "id": "check_run",
          "status": "created",
          "mutation_performed": true,
          "resumed": false,
          "verification_mode": "commit_status_fallback",
          "attempts": 1
        }],
        "errors": [],
        "audit_hash": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
      }
    }
    """.data(using: .utf8)!
}
