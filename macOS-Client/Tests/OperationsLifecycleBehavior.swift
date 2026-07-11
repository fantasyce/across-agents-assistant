import Foundation

func lifecycleAssert(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fatalError(message) }
}

func testWorkspaceLifecycleContract() throws {
    var draft = AgentWorkspaceCreateDraft()
    draft.repoRoot = "/tmp/repository"
    draft.prompt = "Compare implementations"
    draft.selectedAgentIds = ["codex", "claude"]
    let create = try AgentWorkspaceOperationsViewModel.makeCreateRequest(
        backendBase: URL(string: "http://backend")!,
        payload: draft.request(idempotencyKey: "behavior-workspace")
    )
    let createBody = try JSONSerialization.jsonObject(with: create.httpBody ?? Data()) as? [String: Any]

    lifecycleAssert(create.httpMethod == "POST", "Workspace creation must use POST")
    lifecycleAssert(create.url?.path == "/api/agent-workspaces", "Workspace creation route changed")
    lifecycleAssert(createBody?["execution_strategy"] as? String == "parallel_worktrees", "Workspace isolation strategy changed")
    lifecycleAssert((createBody?["agent_ids"] as? [String])?.count == 2, "Workspace must encode selected agents")
    lifecycleAssert((createBody?["validation_commands"] as? [[String]]) == [["git", "diff", "--check"]], "Workspace validation argv default changed")

    let promote = try AgentWorkspaceOperationsViewModel.makeActionRequest(
        backendBase: URL(string: "http://backend")!,
        workspaceId: "ws-1",
        action: "promote",
        method: "POST",
        body: AgentWorkspacePromoteRequest(
            candidateId: "candidate-1",
            approved: true,
            approvedBy: "reviewer@example.com"
        )
    )
    let promoteBody = try JSONSerialization.jsonObject(with: promote.httpBody ?? Data()) as? [String: Any]
    lifecycleAssert(promote.url?.path == "/api/agent-workspaces/ws-1/promote", "Promotion route changed")
    lifecycleAssert(promoteBody?["approved"] as? Bool == true, "Promotion must encode explicit approval")
    lifecycleAssert(promoteBody?["approved_by"] as? String == "reviewer@example.com", "Promotion must encode reviewer identity")

    let decoded = try JSONDecoder().decode(AgentWorkspaceState.self, from: workspaceFixture)
    lifecycleAssert(decoded.candidates.first?.run?.provider == "local", "Workspace provider did not decode")
    lifecycleAssert(decoded.candidates.first?.run?.usage?.totalTokens == 14, "Workspace usage did not decode")
    lifecycleAssert(decoded.candidates.first?.comparison.tests.results.first?.stdoutBytes == 8, "stdout byte metadata did not decode")
    lifecycleAssert(decoded.candidates.first?.comparison.tests.results.first?.outputPersisted == false, "Workspace output persistence boundary changed")
}

func testQualityGateContract() throws {
    var draft = QualityGateRunDraft()
    draft.repoRoot = "/tmp/repository"
    draft.branch = "feature/quality"
    draft.commit = "abc123"
    draft.maxRepairs = 2
    draft.draftPR = true
    let request = try QualityGateViewModel.makeRunRequest(
        backendBase: URL(string: "http://backend")!,
        payload: draft.request()
    )
    let body = try JSONSerialization.jsonObject(with: request.httpBody ?? Data()) as? [String: Any]

    lifecycleAssert(request.httpMethod == "POST", "Quality gate must use POST")
    lifecycleAssert(request.url?.path == "/api/quality-gates/run", "Quality gate route changed")
    lifecycleAssert(body?["commit"] as? String == "abc123", "Quality gate commit binding was not encoded")
    lifecycleAssert(body?["max_repairs"] as? Int == 2, "Quality gate repair budget was not encoded")
    lifecycleAssert(body?["draft_pr"] as? Bool == true, "Quality gate draft PR request was not encoded")

    let result = try JSONDecoder().decode(QualityGateResult.self, from: blockedGateFixture)
    lifecycleAssert(result.isBlocked, "Blocked gate response must decode as a structured result")
    lifecycleAssert(result.findings.first?.state == "blocked", "Normalized findings did not decode")
    lifecycleAssert(result.ci?.taxonomy == ["passed", "failed_security"], "CI taxonomy did not decode")
    lifecycleAssert(result.repairPlan?.status == "planned", "Repair plan did not decode")
    lifecycleAssert(result.draftPR?.ready == false, "Blocked draft PR readiness did not decode")
}

func testMemorySearchExplicitness() throws {
    let backend = URL(string: "http://backend")!
    let ordinary = try MemorySearchViewModel.makeSearchRequest(
        backendBase: backend,
        payload: MemorySearchRequest(
            query: "release evidence",
            projectRoot: "/tmp/repository",
            mode: "hybrid",
            status: MemorySearchScope.ordinary.requestStatus,
            limit: 10
        )
    )
    let pending = try MemorySearchViewModel.makeSearchRequest(
        backendBase: backend,
        payload: MemorySearchRequest(
            query: "release evidence",
            projectRoot: "/tmp/repository",
            mode: "keyword",
            status: MemorySearchScope.pendingReview.requestStatus,
            limit: 10
        )
    )
    let ordinaryBody = try JSONSerialization.jsonObject(with: ordinary.httpBody ?? Data()) as? [String: Any]
    let pendingBody = try JSONSerialization.jsonObject(with: pending.httpBody ?? Data()) as? [String: Any]

    lifecycleAssert(ordinary.httpMethod == "POST", "Memory search must use POST")
    lifecycleAssert(ordinary.url?.path == "/api/memory/search", "Memory search route changed")
    lifecycleAssert(ordinaryBody?["status"] == nil, "Ordinary search must not include pending status")
    lifecycleAssert(pendingBody?["status"] as? String == "pending", "Pending review must be explicit")
    lifecycleAssert(!MemorySearchScope.ordinary.includesPending, "Ordinary scope must exclude pending memory")
    lifecycleAssert(MemorySearchScope.pendingReview.includesPending, "Pending scope must identify its review boundary")
}

func testRepositoryAccessAndLineReviewContracts() throws {
    var draft = AgentWorkspaceCreateDraft()
    draft.repoRoot = "/tmp/repository"
    draft.prompt = "Review a bounded change"
    draft.selectedAgentIds = ["codex"]
    let access = AgentWorkspaceRepoAccess(
        mode: "security_scoped",
        securityScopeActive: true,
        grantId: "grant-behavior"
    )
    let create = try AgentWorkspaceOperationsViewModel.makeCreateRequest(
        backendBase: URL(string: "http://backend")!,
        payload: draft.request(idempotencyKey: "access-behavior", repoAccess: access)
    )
    let createBody = try JSONSerialization.jsonObject(with: create.httpBody ?? Data()) as? [String: Any]
    let encodedAccess = createBody?["repo_access"] as? [String: Any]
    lifecycleAssert(encodedAccess?["mode"] as? String == "security_scoped", "Security-scoped mode was not encoded")
    lifecycleAssert(encodedAccess?["security_scope_active"] as? Bool == true, "Active scope was not encoded")
    lifecycleAssert(encodedAccess?["bookmark_data"] == nil, "Bookmark bytes must never leave Swift")

    let request = try AgentWorkspaceOperationsViewModel.makeActionRequest(
        backendBase: URL(string: "http://backend")!,
        workspaceId: "ws-1",
        action: "line-reviews",
        method: "POST",
        body: AgentWorkspaceLineReviewRequest(
            candidateId: "candidate-1",
            anchor: AgentWorkspaceReviewAnchor(
                baseSha: String(repeating: "a", count: 40),
                headSha: String(repeating: "b", count: 40),
                patchSha256: String(repeating: "c", count: 64)
            ),
            comments: [
                AgentWorkspaceLineCommentRequest(
                    path: "Sources/App.swift",
                    side: "RIGHT",
                    line: 12,
                    startLine: 12,
                    body: "Keep this branch bounded"
                ),
            ],
            idempotencyKey: "line-review-behavior"
        )
    )
    let body = try JSONSerialization.jsonObject(with: request.httpBody ?? Data()) as? [String: Any]
    let comments = body?["comments"] as? [[String: Any]]
    lifecycleAssert(request.url?.path == "/api/agent-workspaces/ws-1/line-reviews", "Line-review route changed")
    lifecycleAssert((body?["anchor"] as? [String: Any])?["patch_sha256"] as? String == String(repeating: "c", count: 64), "Immutable review anchor was not encoded")
    lifecycleAssert(comments?.first?["side"] as? String == "RIGHT", "Line-review side was not encoded")
    lifecycleAssert(comments?.first?["line"] as? Int == 12, "Line-review location was not encoded")
}

func testUnifiedDiffReviewParser() {
    let patch = """
    diff --git a/Sources/App.swift b/Sources/App.swift
    --- a/Sources/App.swift
    +++ b/Sources/App.swift
    @@ -10,2 +10,3 @@
     context
    -old value
    +new value
    +extra value
    """
    let anchors = WorkspaceUnifiedDiffParser.parse(patch).flatMap(\.lines).compactMap(\.anchor)
    lifecycleAssert(anchors.count == 4, "Every reviewable diff line needs an anchor")
    lifecycleAssert(anchors[1].side == "LEFT" && anchors[1].oldLine == 11, "Deleted-line anchor changed")
    lifecycleAssert(anchors[2].side == "RIGHT" && anchors[2].newLine == 11, "Added-line anchor changed")
    lifecycleAssert(anchors[3].newLine == 12, "Diff line advancement changed")
}

private let workspaceFixture = """
{
  "workspace_id": "ws-1",
  "status": "review_ready",
  "repo_root": "/tmp/repository",
  "agent_ids": ["codex"],
  "validation_commands": [["git", "diff", "--check"]],
  "candidates": [{
    "candidate_id": "candidate-1",
    "agent_id": "codex",
    "status": "completed",
    "attempt": 1,
    "run": {
      "provider": "local",
      "model": "test-model",
      "usage": {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14},
      "tool_calls": ["read_file"],
      "evidence_links": [],
      "transcript_persisted": false
    },
    "comparison": {
      "tests": {
        "status": "passed",
        "configured_count": 1,
        "completed_count": 1,
        "results": [{"index": 0, "command": ["git", "diff", "--check"], "status": "passed", "stdout_bytes": 8, "stderr_bytes": 0, "output_persisted": false}]
      }
    },
    "evidence": {"ready_for_review": true}
  }],
  "cancel_requested": false
}
""".data(using: .utf8)!

private let blockedGateFixture = """
{
  "schema_version": "across-autopilot-gate-result/1.0",
  "gate_verdict": "blocked",
  "evidence_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "findings": [{"id": "secret", "state": "blocked", "severity": "critical"}],
  "ci": {"status": "failed", "taxonomy": ["passed", "failed_security"], "counts": {}, "checks": []},
  "repair_plan": {"status": "planned", "actions": []},
  "draft_pr": {"status": "blocked", "requested": true, "ready": false, "mutation_performed": false, "remote_mutation_allowed": false}
}
""".data(using: .utf8)!

@main
struct OperationsLifecycleBehavior {
    static func main() throws {
        try testWorkspaceLifecycleContract()
        try testQualityGateContract()
        try testMemorySearchExplicitness()
        try testRepositoryAccessAndLineReviewContracts()
        testUnifiedDiffReviewParser()
        print("OperationsLifecycleBehavior passed")
    }
}
