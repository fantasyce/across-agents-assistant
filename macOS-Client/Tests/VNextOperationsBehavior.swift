import Foundation

func assert(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fatalError(message) }
}

func jsonObject(_ request: URLRequest) throws -> [String: Any] {
    try JSONSerialization.jsonObject(with: request.httpBody ?? Data()) as? [String: Any] ?? [:]
}

func testWorkspaceRequestsAndActions() throws {
    var draft = AgentWorkspaceCreateDraft()
    draft.repoRoot = "/repo"
    draft.prompt = "Review"
    draft.selectedAgentIds = ["codex"]
    let create = try AgentWorkspaceOperationsViewModel.makeCreateRequest(
        backendBase: URL(string: "http://backend")!,
        payload: draft.request(idempotencyKey: "behavior")
    )
    let body = try jsonObject(create)
    assert(create.url?.path == "/api/agent-workspaces", "Workspace create route must be real")
    assert(body["execution_strategy"] as? String == "parallel_worktrees", "Workspace strategy must be encoded")
    assert((body["validation_commands"] as? [[String]]) == [["git", "diff", "--check"]], "Safe validation default must be encoded")

    let select = try AgentWorkspaceOperationsViewModel.makeActionRequest(
        backendBase: URL(string: "http://backend")!,
        workspaceId: "aws-1",
        action: "select",
        method: "POST",
        body: AgentWorkspaceSelectRequest(candidateId: "candidate-1")
    )
    assert(select.url?.path == "/api/agent-workspaces/aws-1/select", "Candidate selection must use the select action")
}

func testBlockedGateDecoding() throws {
    let json = Data("""
    {
      "schema_version":"across-autopilot-gate-result/1.0",
      "repository":{"path":"/repo"},
      "findings":[{"id":"secret","state":"blocked","severity":"critical"}],
      "gate_verdict":"blocked",
      "checks":{"commands":[],"tools":[],"policies":{}},
      "git_binding":{"dirty_paths":[]},
      "ci":{"mode":"not_configured","status":"unavailable","taxonomy":["failed_test"],"counts":{},"checks":[]},
      "repair_plan":{"status":"not_needed","mutation_performed":false,"current_round":0,"max_rounds":2,"max_actions":0,"actions":[]},
      "draft_pr":{"status":"blocked","requested":true,"ready":false,"mutation_performed":false,"remote_mutation_allowed":false},
      "github_review":{"mutation_performed":false,"remote_mutation_allowed":false,"check_run":{"conclusion":"failure"}}
    }
    """.utf8)
    let result = try JSONDecoder().decode(QualityGateResult.self, from: json)
    assert(result.isBlocked, "Blocked normal responses must decode as results")
    assert(result.githubReview?.checkRun?.conclusion == "failure", "GitHub review payload must decode")
}

func testPendingMemoryIsExplicit() throws {
    let ordinary = try MemorySearchViewModel.makeSearchRequest(
        backendBase: URL(string: "http://backend")!,
        payload: MemorySearchRequest(query: "release", projectRoot: nil, mode: "hybrid", status: MemorySearchScope.ordinary.requestStatus, limit: 10)
    )
    let pending = try MemorySearchViewModel.makeSearchRequest(
        backendBase: URL(string: "http://backend")!,
        payload: MemorySearchRequest(query: "release", projectRoot: nil, mode: "hybrid", status: MemorySearchScope.pendingReview.requestStatus, limit: 10)
    )
    let ordinaryBody = try jsonObject(ordinary)
    let pendingBody = try jsonObject(pending)
    assert(ordinaryBody["status"] == nil, "Ordinary search must not request pending memory")
    assert(pendingBody["status"] as? String == "pending", "Pending review must send an explicit pending status")
    let response = try JSONDecoder().decode(
        MemorySearchResponse.self,
        from: Data("""
        {"results":[{"entry":{"id":"mem-1","scope":"global","type":"note","text":"Release","status":"active"}}]}
        """.utf8)
    )
    assert(response.results.first?.id == "mem-1", "Context search envelopes must decode to memory entries")
}

func testUIStateContracts() {
    assert(OperationalContentState.behaviorFixtures.count == 6, "All operational content states must remain covered")
    assert(OperationalContentState.behaviorFixtures.contains(.active("active")), "Active state is required")
    assert(OperationalContentState.behaviorFixtures.contains(.disabled("disabled")), "Disabled state is required")
    assert(OperationalContentState.behaviorFixtures.contains(.success("success")), "Success state is required")
}

@main
struct VNextOperationsBehavior {
    static func main() throws {
        try testWorkspaceRequestsAndActions()
        try testBlockedGateDecoding()
        try testPendingMemoryIsExplicit()
        testUIStateContracts()
        print("VNextOperationsBehavior passed")
    }
}
