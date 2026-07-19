import Foundation
import Testing
@testable import AcrossAgentsAssistantClient

struct VNextOperationsAPITests {
    private let backendBase = URL(string: "http://backend")!

    @Test func workspaceCreateAndActionRequestsUseRealRoutesAndSnakeCaseBodies() throws {
        var draft = AgentWorkspaceCreateDraft()
        draft.repoRoot = "/repo"
        draft.prompt = "Review and improve"
        draft.selectedAgentIds = ["codex", "claude"]
        draft.qualityGateCIPath = "/tmp/ci.json"
        draft.qualityGateCIWaitSeconds = 120
        draft.qualityGateDraftPR = true
        let create = try AgentWorkspaceOperationsViewModel.makeCreateRequest(
            backendBase: backendBase,
            payload: draft.request(
                idempotencyKey: "request-1",
                repoAccess: AgentWorkspaceRepoAccess(
                    mode: "security_scoped",
                    securityScopeActive: true,
                    grantId: "grant-1"
                )
            )
        )
        let createData = try #require(create.httpBody)
        let createBody = try #require(try JSONSerialization.jsonObject(with: createData) as? [String: Any])

        #expect(create.httpMethod == "POST")
        #expect(create.url?.path == "/api/agent-workspaces")
        #expect(createBody["repo_root"] as? String == "/repo")
        #expect(createBody["execution_strategy"] as? String == "parallel_worktrees")
        #expect(createBody["agent_ids"] as? [String] == ["claude", "codex"])
        #expect((createBody["validation_commands"] as? [[String]]) == [["git", "diff", "--check"]])
        #expect(createBody["workflow"] as? String == "repo-quality-copilot")
        #expect(createBody["quality_gate_ci_path"] as? String == "/tmp/ci.json")
        #expect(createBody["quality_gate_ci_wait_seconds"] as? Int == 120)
        #expect(createBody["quality_gate_draft_pr"] as? Bool == true)
        let repoAccess = try #require(createBody["repo_access"] as? [String: Any])
        #expect(repoAccess["mode"] as? String == "security_scoped")
        #expect(repoAccess["security_scope_active"] as? Bool == true)
        #expect(repoAccess["grant_id"] as? String == "grant-1")
        #expect(repoAccess["bookmark_data"] == nil)

        let promote = try AgentWorkspaceOperationsViewModel.makeActionRequest(
            backendBase: backendBase,
            workspaceId: "aws-1",
            action: "promote",
            method: "POST",
            body: AgentWorkspacePromoteRequest(candidateId: "codex-1", approved: true, approvedBy: "reviewer")
        )
        let promoteData = try #require(promote.httpBody)
        let promoteBody = try #require(try JSONSerialization.jsonObject(with: promoteData) as? [String: Any])
        #expect(promote.url?.path == "/api/agent-workspaces/aws-1/promote")
        #expect(promoteBody["candidate_id"] as? String == "codex-1")
        #expect(promoteBody["approved"] as? Bool == true)
        #expect(promoteBody["approved_by"] as? String == "reviewer")

        let comment = try AgentWorkspaceOperationsViewModel.makeActionRequest(
            backendBase: backendBase,
            workspaceId: "aws-1",
            action: "comment",
            method: "POST",
            body: AgentWorkspaceCommentRequest(candidateId: "codex-1", comment: "Tighten validation")
        )
        let commentData = try #require(comment.httpBody)
        let commentBody = try #require(try JSONSerialization.jsonObject(with: commentData) as? [String: Any])
        #expect(comment.url?.path == "/api/agent-workspaces/aws-1/comment")
        #expect(commentBody["candidate_id"] as? String == "codex-1")
        #expect(commentBody["comment"] as? String == "Tighten validation")

        let lineReview = try AgentWorkspaceOperationsViewModel.makeActionRequest(
            backendBase: backendBase,
            workspaceId: "aws-1",
            action: "line-reviews",
            method: "POST",
            body: AgentWorkspaceLineReviewRequest(
                candidateId: "codex-1",
                anchor: AgentWorkspaceReviewAnchor(
                    baseSha: String(repeating: "a", count: 40),
                    headSha: String(repeating: "b", count: 40),
                    patchSha256: String(repeating: "c", count: 64)
                ),
                comments: [
                    AgentWorkspaceLineCommentRequest(
                        path: "Sources/App.swift",
                        side: "RIGHT",
                        line: 42,
                        startLine: 42,
                        body: "Tighten this condition"
                    ),
                ],
                idempotencyKey: "line-review-1"
            )
        )
        #expect(lineReview.url?.path == "/api/agent-workspaces/aws-1/line-reviews")

        let cleanup = try AgentWorkspaceOperationsViewModel.makeActionRequest(
            backendBase: backendBase,
            workspaceId: "aws-1",
            action: nil,
            method: "DELETE",
            body: Optional<AgentWorkspaceCancelRequest>.none
        )
        #expect(cleanup.httpMethod == "DELETE")
        #expect(cleanup.url?.path == "/api/agent-workspaces/aws-1")

        let events = AgentWorkspaceOperationsViewModel.makeEventsRequest(
            backendBase: backendBase,
            workspaceId: "aws-1",
            afterSequence: 9
        )
        #expect(events.url?.path == "/api/agent-workspaces/aws-1/events")
        let eventsURL = try #require(events.url)
        #expect(URLComponents(url: eventsURL, resolvingAgainstBaseURL: false)?.queryItems == [URLQueryItem(name: "after_sequence", value: "9")])
    }

    @Test func workspaceResponseDecodesCandidateRuntimeComparisonEvidenceAndActionContracts() throws {
        let state = try JSONDecoder().decode(AgentWorkspaceState.self, from: Data(workspaceJSON.utf8))
        let candidate = try #require(state.candidates.first)

        #expect(state.status == "review_ready")
        #expect(!state.isActive)
        #expect(state.canCleanup)
        #expect(candidate.run?.provider == "local")
        #expect(candidate.run?.model == "test-model")
        #expect(candidate.run?.usage?.totalTokens == 14)
        #expect(candidate.run?.toolCalls == ["read_file", "apply_patch"])
        #expect(candidate.comparison.changedFiles == ["Sources/App.swift"])
        #expect(candidate.comparison.tests.status == "passed")
        #expect(candidate.comparison.qualityGate.gateVerdict == "pass")
        #expect(candidate.evidence.readyForReview)
        #expect(candidate.canCommentAndRelaunch)
        #expect(candidate.canSelect)
    }

    @Test func workspaceEventsAndComparisonDecodeWithBoundedDiff() throws {
        let stateObject = try #require(try JSONSerialization.jsonObject(with: Data(workspaceJSON.utf8)) as? [String: Any])
        let candidate = try #require((stateObject["candidates"] as? [[String: Any]])?.first)
        var comparisonCandidate = candidate
        comparisonCandidate["selected"] = true
        comparisonCandidate["diff"] = String(repeating: "x", count: 70_000)
        let responseObject: [String: Any] = [
            "workspace_id": "aws-1",
            "base_sha": "base123",
            "status": "review_ready",
            "selected_candidate_id": "codex-1",
            "candidates": [comparisonCandidate],
        ]
        let comparisonData = try JSONSerialization.data(withJSONObject: responseObject)
        let comparison = try JSONDecoder().decode(AgentWorkspaceComparisonResponse.self, from: comparisonData)
        #expect(comparison.candidates.first?.diff?.count == 64_000)

        let events = try JSONDecoder().decode(
            AgentWorkspaceEventsResponse.self,
            from: Data("""
            {"workspace_id":"aws-1","workspace_status":"running","last_sequence":2,"events":[{"sequence":2,"timestamp":"now","type":"candidate.tool_calls.observed","workspace_id":"aws-1","candidate_id":"codex-1","data":{"count":2,"tools":["read_file","apply_patch"]}}]}
            """.utf8)
        )
        #expect(events.events.first?.candidateId == "codex-1")
        #expect(events.events.first?.boundedSummary.contains("read_file") == true)
    }

    @Test @MainActor func blockedQualityGateIsACompletedNormalResponse() async throws {
        let response = try #require(HTTPURLResponse(
            url: backendBase.appendingPathComponent("api/quality-gates/run"),
            statusCode: 200,
            httpVersion: nil,
            headerFields: ["Content-Type": "application/json"]
        ))
        let viewModel = QualityGateViewModel { request in
            #expect(request.httpMethod == "POST")
            let data = try #require(request.httpBody)
            let body = try #require(try JSONSerialization.jsonObject(with: data) as? [String: Any])
            #expect(body["branch"] as? String == "feature/quality")
            #expect(body["commit"] as? String == "abc123")
            #expect(body["max_repairs"] as? Int == 2)
            #expect(body["draft_pr"] as? Bool == true)
            return (Data(qualityGateJSON.utf8), response)
        }
        viewModel.draft.repoRoot = "/repo"
        viewModel.draft.branch = "feature/quality"
        viewModel.draft.commit = "abc123"
        viewModel.draft.maxRepairs = 2
        viewModel.draft.draftPR = true

        await viewModel.run()

        let result = try #require(viewModel.result)
        #expect(viewModel.errorMessage == nil)
        #expect(result.isBlocked)
        #expect(result.findings.first?.id == "dirty_tree")
        #expect(result.gitBinding?.expectedBranch == "feature/quality")
        #expect(result.checks?.commands.first?.status == "skipped")
        #expect(result.pushReceipt?.evidenceHash == String(repeating: "a", count: 64))
        #expect(result.ci?.taxonomy.contains("failed_test") == true)
        #expect(result.repairPlan?.actions.first?.execution == "planned_only")
        #expect(result.draftPR?.status == "blocked")
        #expect(result.githubReview?.checkRun?.conclusion == "failure")
        #expect(viewModel.contentState == .success("blocked"))
    }

    @Test func memorySearchDefaultsToOrdinaryAndRequiresExplicitPendingStatus() throws {
        let ordinary = try MemorySearchViewModel.makeSearchRequest(
            backendBase: backendBase,
            payload: MemorySearchRequest(query: "release evidence", projectRoot: "/repo", mode: "hybrid", status: MemorySearchScope.ordinary.requestStatus, limit: 20)
        )
        let pending = try MemorySearchViewModel.makeSearchRequest(
            backendBase: backendBase,
            payload: MemorySearchRequest(query: "release evidence", projectRoot: "/repo", mode: "hybrid", status: MemorySearchScope.pendingReview.requestStatus, limit: 20)
        )
        let ordinaryData = try #require(ordinary.httpBody)
        let pendingData = try #require(pending.httpBody)
        let ordinaryBody = try #require(try JSONSerialization.jsonObject(with: ordinaryData) as? [String: Any])
        let pendingBody = try #require(try JSONSerialization.jsonObject(with: pendingData) as? [String: Any])

        #expect(ordinary.url?.path == "/api/memory/search")
        #expect(ordinaryBody["status"] == nil)
        #expect(pendingBody["status"] as? String == "pending")
        #expect(MemorySearchScope.ordinary.requestStatus == nil)
        #expect(MemorySearchScope.pendingReview.requestStatus == "pending")

        let nested = try JSONDecoder().decode(
            MemorySearchResponse.self,
            from: Data("""
            {"results":[{"entry":{"id":"mem-1","scope":"project","type":"note","text":"Release evidence","status":"active"},"score":1.0}]}
            """.utf8)
        )
        #expect(nested.resultCount == 1)
        #expect(nested.results.first?.id == "mem-1")

        let merged = try MemorySearchViewModel.makeMergedRetrieveRequest(
            backendBase: backendBase,
            payload: MemoryMergedRetrieveRequest(
                query: "release evidence",
                routes: MemoryRetrievalRoute.allCases,
                projectRoot: "/repo",
                allProjects: false,
                status: nil,
                reviewPending: false,
                limit: 20,
                includeRouteResults: true
            )
        )
        let improved = try MemorySearchViewModel.makeImproveRequest(
            backendBase: backendBase,
            payload: MemoryImproveRequest(
                projectRoot: "/repo",
                allProjects: false,
                sourceIds: [],
                similarityThreshold: 0.34,
                maxProposalLength: 420
            )
        )
        let approved = try MemorySearchViewModel.makeApproveRequest(
            backendBase: backendBase,
            memoryID: "mem-proposal-1"
        )
        let rolledBack = try MemorySearchViewModel.makeRollbackRequest(
            backendBase: backendBase,
            memoryID: "mem-proposal-1"
        )

        #expect(merged.url?.path == "/api/memory/retrieve/merged")
        #expect(improved.url?.path == "/api/memory/improve")
        #expect(approved.url?.path == "/api/memory/memories/mem-proposal-1/status")
        #expect(rolledBack.url?.path == "/api/memory/distilled/mem-proposal-1/rollback")
        #expect(approved.httpMethod == "POST")
        #expect(rolledBack.httpMethod == "POST")
    }

    @Test func operationStateContractsCoverLoadingEmptyErrorActiveDisabledAndSuccess() {
        #expect(OperationalContentState.behaviorFixtures == [
            .loading,
            .empty,
            .error("error"),
            .active("active"),
            .disabled("disabled"),
            .success("success"),
        ])
        var invalidDraft = AgentWorkspaceCreateDraft()
        #expect(invalidDraft.validationError != nil)
        invalidDraft.repoRoot = "/repo"
        invalidDraft.selectedAgentIds = ["codex"]
        #expect(invalidDraft.validationError == nil)
    }

    private var workspaceJSON: String {
        """
        {
          "schema_version": "agent-workspace-state/1.0",
          "workspace_id": "aws-1",
          "status": "review_ready",
          "repo_root": "/repo",
          "base_sha": "base123",
          "execution_strategy": "parallel_worktrees",
          "workflow": "repo-quality-copilot",
          "agent_ids": ["codex"],
          "validation_commands": [["git", "diff", "--check"]],
          "selected_candidate_id": null,
          "cancel_requested": false,
          "promotion": {"status": "review_required", "approved": false, "candidate_id": null, "promoted_at": null},
          "cleanup": {"status": "retained", "completed_at": null},
          "candidates": [{
            "candidate_id": "codex-1",
            "agent_id": "codex",
            "status": "completed",
            "attempt": 1,
            "run": {
              "success": true,
              "provider": "local",
              "model": "test-model",
              "usage": {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14},
              "tool_calls": ["read_file", "apply_patch"],
              "evidence_links": ["/api/autopilot/runs/run-1/evidence"],
              "transcript_persisted": false
            },
            "comparison": {
              "changed_files": ["Sources/App.swift"],
              "diff": {"files_changed": 1, "insertions": 4, "deletions": 1, "binary_files": 0},
              "patch_available": true,
              "patch_sha256": "patch",
              "tests": {"status": "passed", "configured_count": 1, "completed_count": 1, "results": []},
              "quality_gate": {"required": true, "status": "passed", "gate_verdict": "pass", "findings": [], "evidence_routes": []},
              "risk": {"level": "low", "blocking": false, "findings": []},
              "conflicts": {"status": "not_checked", "checked_at": null}
            },
            "evidence": {
              "ready_for_review": true,
              "blocking_reasons": [],
              "human_approval_required": true,
              "diff_validated": true,
              "tests_validated": true,
              "quality_gate_validated": true,
              "risk_validated": true
            }
          }]
        }
        """
    }

    private var qualityGateJSON: String {
        """
        {
          "schema_version": "across-autopilot-gate-result/1.0",
          "status": "blocked",
          "repository": {"name": "fixture", "path": "/repo"},
          "base_ref": "main",
          "head_ref": "HEAD",
          "head_sha": "abc123",
          "dirty_tree": true,
          "findings": [{"id": "dirty_tree", "state": "blocked", "severity": "high", "summary": "Working tree is dirty.", "suggested_action": "Clean the tree.", "source_gate": "git_binding"}],
          "gate_verdict": "blocked",
          "evidence_hash": "\(String(repeating: "a", count: 64))",
          "pr_ready_summary": "Not PR-ready.",
          "git_binding": {"base_sha": "base", "head_sha": "abc123", "current_head_sha": "abc123", "branch": "feature/quality", "expected_branch": "feature/quality", "expected_commit": "abc123", "base_is_ancestor": true, "dirty_paths": ["file.swift"]},
          "checks": {"commands": [{"id": "tests", "category": "test", "status": "skipped", "reason": "preflight_blocked"}], "tools": [], "policies": {}},
          "push_receipt": {"schema_version": "across-autopilot-push-receipt/1.0", "gate_verdict": "blocked", "evidence_hash": "\(String(repeating: "a", count: 64))"},
          "ci": {"schema_version": "across-autopilot-ci-watch/1.0", "mode": "snapshot", "status": "failed", "taxonomy": ["passed", "failed_test"], "counts": {"passed": 0, "failed_test": 1}, "checks": [{"id": "tests", "name": "Tests", "status": "failed_test", "conclusion": "failure"}]},
          "repair_plan": {"status": "planned", "mutation_performed": false, "current_round": 0, "max_rounds": 2, "max_actions": 2, "actions": [{"id": "repair-test-1", "category": "test", "source_finding_ids": ["tests"], "suggested_action": "Fix tests", "remaining_rounds": 2, "execution": "planned_only", "command_source": "trusted_baseline_only"}]},
          "draft_pr": {"status": "blocked", "requested": true, "ready": false, "mutation_performed": false, "remote_mutation_allowed": false, "blocking_reasons": ["gate_verdict:blocked"]},
          "github_review": {"schema_version": "across-autopilot-github-review/1.0", "mutation_performed": false, "remote_mutation_allowed": false, "check_run": {"name": "Across Repository Push Gate", "external_id": "evidence", "head_sha": "abc123", "conclusion": "failure", "output": {"title": "Across gate: blocked", "summary": "Not PR-ready.", "text": "# Repository Push Gate"}}, "pr_comment": {"body": "# Repository Push Gate", "evidence_hash": "evidence"}}
        }
        """
    }
}
