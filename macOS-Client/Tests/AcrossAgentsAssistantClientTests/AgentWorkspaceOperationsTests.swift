import Foundation
import Testing
@testable import AcrossAgentsAssistantClient

struct AgentWorkspaceOperationsTests {
    @Test func createRequestEncodesBoundedOperationalContract() throws {
        var draft = AgentWorkspaceCreateDraft()
        draft.repoRoot = " /tmp/repository "
        draft.prompt = " Compare implementations and preserve evidence. "
        draft.selectedAgentIds = ["codex", "claude"]
        draft.qualityGateCIPath = " /tmp/ci.json "
        draft.qualityGateCIWaitSeconds = 90
        draft.qualityGateDraftPR = true

        let payload = try draft.request(idempotencyKey: "workspace-test-1")
        let object = try #require(
            JSONSerialization.jsonObject(with: JSONEncoder().encode(payload)) as? [String: Any]
        )

        #expect(object["repo_root"] as? String == "/tmp/repository")
        #expect(object["prompt"] as? String == "Compare implementations and preserve evidence.")
        #expect(object["agent_ids"] as? [String] == ["claude", "codex"])
        #expect(object["execution_strategy"] as? String == "parallel_worktrees")
        #expect((object["validation_commands"] as? [[String]]) == [["git", "diff", "--check"]])
        #expect(object["workflow"] as? String == "repo-quality-copilot")
        #expect(object["idempotency_key"] as? String == "workspace-test-1")
        #expect(object["quality_gate_ci_path"] as? String == "/tmp/ci.json")
        #expect(object["quality_gate_ci_wait_seconds"] as? Int == 90)
        #expect(object["quality_gate_draft_pr"] as? Bool == true)
    }

    @Test func workspaceStateDecodesRunComparisonUsageAndOutputMetadata() throws {
        let state = try JSONDecoder().decode(AgentWorkspaceState.self, from: Self.workspaceData(status: "review_ready"))
        let candidate = try #require(state.candidates.first)
        let validation = try #require(candidate.comparison.tests.results.first)

        #expect(state.workspaceId == "ws-1")
        #expect(candidate.run?.provider == "local")
        #expect(candidate.run?.model == "test-model")
        #expect(candidate.run?.usage?.totalTokens == 14)
        #expect(candidate.run?.toolCalls == ["read_file", "apply_patch"])
        #expect(candidate.comparison.changedFiles == ["Sources/Feature.swift"])
        #expect(validation.stdoutBytes == 12)
        #expect(validation.stderrBytes == 4)
        #expect(!validation.outputPersisted)
        #expect(candidate.evidence.readyForReview)
        #expect(!candidate.run!.transcriptPersisted)
    }

    @Test func lifecycleRequestBuildersUseCurrentRoutesAndBodies() throws {
        let backend = URL(string: "http://backend")!
        let cancel = try AgentWorkspaceOperationsViewModel.makeActionRequest(
            backendBase: backend,
            workspaceId: "ws-1",
            action: "cancel",
            method: "POST",
            body: AgentWorkspaceCancelRequest(reason: "human stop")
        )
        let comment = try AgentWorkspaceOperationsViewModel.makeActionRequest(
            backendBase: backend,
            workspaceId: "ws-1",
            action: "comment",
            method: "POST",
            body: AgentWorkspaceCommentRequest(candidateId: "candidate-1", comment: "Address the failing check")
        )
        let select = try AgentWorkspaceOperationsViewModel.makeActionRequest(
            backendBase: backend,
            workspaceId: "ws-1",
            action: "select",
            method: "POST",
            body: AgentWorkspaceSelectRequest(candidateId: "candidate-1")
        )
        let promote = try AgentWorkspaceOperationsViewModel.makeActionRequest(
            backendBase: backend,
            workspaceId: "ws-1",
            action: "promote",
            method: "POST",
            body: AgentWorkspacePromoteRequest(candidateId: "candidate-1", approved: true, approvedBy: "reviewer@example.com")
        )
        let cleanup = try AgentWorkspaceOperationsViewModel.makeActionRequest(
            backendBase: backend,
            workspaceId: "ws-1",
            action: nil,
            method: "DELETE",
            body: Optional<AgentWorkspaceCancelRequest>.none
        )

        #expect(cancel.url?.path == "/api/agent-workspaces/ws-1/cancel")
        #expect(comment.url?.path == "/api/agent-workspaces/ws-1/comment")
        #expect(select.url?.path == "/api/agent-workspaces/ws-1/select")
        #expect(promote.url?.path == "/api/agent-workspaces/ws-1/promote")
        #expect(cleanup.url?.path == "/api/agent-workspaces/ws-1")
        #expect(cleanup.httpMethod == "DELETE")

        let promoteData = try #require(promote.httpBody)
        let promoteBody = try #require(
            JSONSerialization.jsonObject(with: promoteData) as? [String: Any]
        )
        #expect(promoteBody["approved"] as? Bool == true)
        #expect(promoteBody["approved_by"] as? String == "reviewer@example.com")
        #expect(promoteBody["candidate_id"] as? String == "candidate-1")
    }

    @Test func readinessRequestCarriesActiveSecurityScopeMetadata() throws {
        let request = AgentWorkspaceOperationsViewModel.makeReadinessRequest(
            backendBase: URL(string: "http://backend")!,
            repoRoot: "/repo",
            selectedAgentIds: ["codex"],
            repoAccess: AgentWorkspaceRepoAccess(
                mode: "security_scoped",
                securityScopeActive: true,
                grantId: "grant-1"
            ),
            refresh: true
        )
        let url = try #require(request.url)
        let components = try #require(URLComponents(url: url, resolvingAgainstBaseURL: false))
        let values = Dictionary(uniqueKeysWithValues: (components.queryItems ?? []).map { ($0.name, $0.value ?? "") })

        #expect(values["repo_root"] == "/repo")
        #expect(values["repo_access_mode"] == "security_scoped")
        #expect(values["security_scope_active"] == "true")
        #expect(values["repo_access_grant_id"] == "grant-1")
    }

    @MainActor
    @Test func promotionRequiresConfirmationAndIdentityBeforePosting() async throws {
        var requests: [URLRequest] = []
        let viewModel = AgentWorkspaceOperationsViewModel(dataLoader: { request in
            requests.append(request)
            let path = request.url?.path ?? ""
            let data: Data
            if path.hasSuffix("/comparison") {
                data = Self.comparisonData
            } else if path.hasSuffix("/events") {
                data = Self.eventsData
            } else {
                data = Self.workspaceData(status: "promoted")
            }
            return (data, Self.okResponse(for: request.url!))
        })
        viewModel.selectedWorkspaceId = "ws-1"
        viewModel.selectedCandidateId = "candidate-1"

        await viewModel.promote(approvedBy: "", confirmed: false)
        #expect(requests.isEmpty)
        #expect(viewModel.errorMessage == "Confirm promotion and provide the approving identity.")

        await viewModel.promote(approvedBy: " reviewer@example.com ", confirmed: true)

        #expect(requests.first?.url?.path == "/api/agent-workspaces/ws-1/promote")
        let body = try #require(requests.first?.httpBody)
        let object = try #require(JSONSerialization.jsonObject(with: body) as? [String: Any])
        #expect(object["approved"] as? Bool == true)
        #expect(object["approved_by"] as? String == "reviewer@example.com")
        #expect(viewModel.workspace?.status == "promoted")
        #expect(viewModel.actionMessage == "Candidate promoted")
    }

    @MainActor
    @Test func displayedEventsEnforceCountAndCharacterBudgets() throws {
        let eventObjects: [[String: Any]] = (1...240).map { sequence in
            [
                "sequence": sequence,
                "timestamp": "2026-07-10T00:00:00Z",
                "type": "candidate.output.metadata",
                "workspace_id": "ws-1",
                "candidate_id": "candidate-1",
                "data": ["summary": String(repeating: "x", count: 1_000)],
            ]
        }
        let data = try JSONSerialization.data(withJSONObject: [
            "workspace_id": "ws-1",
            "workspace_status": "running",
            "events": eventObjects,
            "last_sequence": 240,
        ])
        let decoded = try JSONDecoder().decode(AgentWorkspaceEventsResponse.self, from: data)
        let viewModel = AgentWorkspaceOperationsViewModel()
        viewModel.events = decoded.events

        let visible = viewModel.events(for: "candidate-1")
        let renderedCharacters = visible.reduce(0) { $0 + $1.type.count + $1.boundedSummary.count }

        #expect(visible.count <= AgentWorkspaceOperationsViewModel.maximumDisplayedEvents)
        #expect(renderedCharacters <= AgentWorkspaceOperationsViewModel.maximumDisplayedEventCharacters)
        #expect(visible.last?.sequence == 240)
    }

    private static func okResponse(for url: URL) -> HTTPURLResponse {
        HTTPURLResponse(url: url, statusCode: 200, httpVersion: "HTTP/1.1", headerFields: nil)!
    }

    private static func workspaceData(status: String) -> Data {
        """
        {
          "schema_version": "agent-workspace/1.0",
          "workspace_id": "ws-1",
          "status": "\(status)",
          "repo_root": "/tmp/repository",
          "base_sha": "base123",
          "base_branch": "main",
          "agent_ids": ["codex"],
          "validation_commands": [["git", "diff", "--check"]],
          "selected_candidate_id": "candidate-1",
          "candidates": [
            {
              "candidate_id": "candidate-1",
              "agent_id": "codex",
              "status": "completed",
              "attempt": 1,
              "run": {
                "success": true,
                "output_bytes": 64,
                "output_sha256": "bbbb",
                "provider": "local",
                "model": "test-model",
                "usage": {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14},
                "tool_calls": ["read_file", "apply_patch"],
                "evidence_links": ["/api/evidence/1"],
                "transcript_persisted": false
              },
              "comparison": {
                "changed_files": ["Sources/Feature.swift"],
                "diff": {"files_changed": 1, "insertions": 4, "deletions": 1, "binary_files": 0},
                "patch_available": true,
                "patch_sha256": "aaaa",
                "tests": {
                  "status": "passed",
                  "configured_count": 1,
                  "completed_count": 1,
                  "results": [{
                    "index": 0,
                    "command": ["git", "diff", "--check"],
                    "status": "passed",
                    "exit_code": 0,
                    "elapsed_seconds": 0.2,
                    "stdout_bytes": 12,
                    "stderr_bytes": 4,
                    "output_persisted": false
                  }]
                },
                "quality_gate": {"required": false, "status": "not_requested", "findings": []},
                "risk": {"level": "low", "blocking": false, "findings": []},
                "conflicts": {"status": "clear"}
              },
              "evidence": {
                "changed_files_validated": true,
                "diff_validated": true,
                "tests_validated": true,
                "quality_gate_validated": true,
                "risk_validated": true,
                "conflicts_validated": true,
                "human_approval_required": true,
                "ready_for_review": true,
                "blocking_reasons": []
              }
            }
          ],
          "promotion": {"status": "promoted", "approved": true, "approved_by": "reviewer@example.com", "candidate_id": "candidate-1"},
          "cancel_requested": false,
          "cleanup": {"status": "retained"}
        }
        """.data(using: .utf8)!
    }

    private static let comparisonData = """
    {
      "workspace_id": "ws-1",
      "base_sha": "base123",
      "status": "promoted",
      "selected_candidate_id": "candidate-1",
      "candidates": [{
        "candidate_id": "candidate-1",
        "agent_id": "codex",
        "status": "completed",
        "selected": true,
        "comparison": {},
        "evidence": {"ready_for_review": true},
        "diff": "diff --git a/file b/file"
      }]
    }
    """.data(using: .utf8)!

    private static let eventsData = """
    {
      "workspace_id": "ws-1",
      "workspace_status": "promoted",
      "events": [{
        "sequence": 1,
        "timestamp": "2026-07-10T00:00:00Z",
        "type": "promotion.completed",
        "workspace_id": "ws-1",
        "candidate_id": "candidate-1",
        "data": {"patch_sha256": "aaaa"}
      }],
      "last_sequence": 1
    }
    """.data(using: .utf8)!
}
