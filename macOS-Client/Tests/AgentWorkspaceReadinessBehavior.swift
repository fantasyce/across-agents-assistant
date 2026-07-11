import Foundation

func assert(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() {
        fatalError(message)
    }
}

func testAgentWorkspaceReadinessBlocksMutationWithoutDiffRoute() throws {
    let json = """
    {
      "schema_version": "agent-workspace-readiness/1.0",
      "status": "ready",
      "repo_root": "/tmp/across",
      "selected_agent_ids": ["codex", "claude"],
      "execution_strategy": "parallel_worktrees",
      "workspace_isolation": {
        "status": "ready",
        "mode": "git_worktree",
        "supports_git_worktree": true,
        "can_create_isolated_workspaces": true
      },
      "agents": [
        {"agent_id": "codex", "display_name": "Codex", "status": "ready", "available": true},
        {"agent_id": "claude", "display_name": "Claude Code", "status": "not_ready", "available": false, "missing_prerequisites": ["authentication"]}
      ],
      "routes": {
        "events": "/api/agent-workspaces/ws-1/events",
        "evidence": "/api/agent-workspaces/ws-1/evidence"
      }
    }
    """.data(using: .utf8)!

    let snapshot = try JSONDecoder().decode(AgentWorkspaceReadinessSnapshot.self, from: json)

    assert(snapshot.status == .ready, "Readiness status should normalize to ready")
    assert(snapshot.readyAgentIds == ["codex"], "Only usable agents should be ready")
    assert(snapshot.selectedReadyAgentIds == ["codex"], "Selected readiness should intersect selected and usable agents")
    assert(snapshot.canCreateWorkspace == false, "Workspace mutation should stay blocked without diff route")
    assert(snapshot.readinessIssues == ["diff_route"], "Missing route should be explicit")
}

func testAgentWorkspaceReadinessAllowsMutationWhenGreen() throws {
    let json = """
    {
      "status": "passed",
      "workspace_isolation": {
        "status": "passed",
        "supports_git_worktree": true
      },
      "agents": [
        {"agent_id": "codex", "status": "passed", "available": true}
      ],
      "routes": {
        "events": "/events",
        "diff": "/diff",
        "evidence": "/evidence"
      }
    }
    """.data(using: .utf8)!

    let snapshot = try JSONDecoder().decode(AgentWorkspaceReadinessSnapshot.self, from: json)

    assert(snapshot.workspaceIsolation.canCreateIsolatedWorkspaces, "Ready git worktree capability should allow isolation")
    assert(snapshot.canCreateWorkspace, "Green readiness should allow workspace creation")
    assert(snapshot.readinessIssues.isEmpty, "Green readiness should not report issues")
}

func testInformationalPrerequisitesDoNotBlockMutation() throws {
    let json = """
    {
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
      },
      "missing_prerequisites": [
        {"id": "workspace_root_missing", "severity": "info"}
      ]
    }
    """.data(using: .utf8)!

    let snapshot = try JSONDecoder().decode(AgentWorkspaceReadinessSnapshot.self, from: json)

    assert(snapshot.missingPrerequisites == ["workspace_root_missing"], "Info prerequisites should still decode for audit display")
    assert(snapshot.canCreateWorkspace, "Info prerequisites should not block workspace creation")
    assert(snapshot.readinessIssues.isEmpty, "Info prerequisites should not be reported as readiness blockers")
}

func testStatusPaletteNormalizesWorkspaceStates() {
    assert(StatusPalette.tone(for: "ready") == .success, "Ready should map to success")
    assert(StatusPalette.tone(for: "not_ready") == .warning, "Not ready should map to warning")
    assert(StatusPalette.tone(for: "blocked") == .danger, "Blocked should map to danger")
    assert(StatusPalette.tone(for: "not-implemented") == .neutral, "Not implemented should map to neutral")
    assert(StatusPalette.systemImage(for: "ready") == "checkmark.circle.fill", "Ready icon should be stable")
    assert(StatusPalette.displayText(for: "needs_attention") == "Needs Attention", "Display text should be readable")
}

func testAgentWorkspaceReadinessDecodesBackendPrerequisiteObjects() throws {
    let json = """
    {
      "schema_version": "agent-workspace-readiness/1.0",
      "generated_at": "2026-07-10T00:00:00+00:00",
      "status": "partial",
      "workspace_isolation": {
        "status": "not_implemented",
        "supports_git_worktree": false,
        "can_create_isolated_workspaces": false,
        "missing_prerequisites": ["workspace_mutation_not_enabled"]
      },
      "agents": [
        {"agent_id": "openclaw", "display_name": "OpenClaw", "status": "ready", "available": true}
      ],
      "routes": {},
      "missing_prerequisites": [
        {"id": "workspace_root_missing", "severity": "info"},
        {"id": "no_available_local_agents", "severity": "error"}
      ]
    }
    """.data(using: .utf8)!

    let snapshot = try JSONDecoder().decode(AgentWorkspaceReadinessSnapshot.self, from: json)

    assert(snapshot.generatedAt == "2026-07-10T00:00:00+00:00", "Backend timestamp should decode as a string")
    assert(snapshot.missingPrerequisites == ["no_available_local_agents", "workspace_root_missing"], "Object prerequisites should decode to ids")
    assert(snapshot.readyAgentIds == ["openclaw"], "Backend agents should decode to ready ids")
    assert(snapshot.canCreateWorkspace == false, "Readiness-only backend payload must not allow mutation")
}

func testAgentWorkspaceReadinessViewModelBuildsRefreshRequest() {
    let request = AgentWorkspaceReadinessViewModel.makeRequest(
        backendBase: URL(string: "http://backend")!,
        refresh: true
    )

    assert(request.httpMethod == "GET", "Readiness request should be read-only")
    assert(request.url?.absoluteString == "http://backend/api/agent-workspaces/readiness?refresh=true", "Refresh request should set the backend query")
    assert(request.value(forHTTPHeaderField: "Accept") == "application/json", "Readiness request should ask for JSON")
}

@MainActor
func testAgentWorkspaceReadinessViewModelLoadsSnapshot() async throws {
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
    var capturedURL: URL?
    let viewModel = AgentWorkspaceReadinessViewModel(dataLoader: { request in
        capturedURL = request.url
        return (body, response)
    })

    await viewModel.load()

    assert(capturedURL?.path == "/api/agent-workspaces/readiness", "ViewModel should call the readiness endpoint")
    assert(viewModel.errorMessage == nil, "Successful load should clear error")
    assert(viewModel.snapshot?.readyAgentIds == ["codex"], "Successful load should decode usable agents")
    assert(viewModel.snapshot?.canCreateWorkspace == true, "Green payload should allow workspace creation")
}

@MainActor
func testAgentWorkspaceReadinessViewModelReportsBackendErrors() async throws {
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

    assert(viewModel.snapshot == nil, "Failed load should not create a snapshot")
    assert(viewModel.errorMessage == "readiness unavailable", "Backend detail should surface in the ViewModel")
}

@MainActor
func testAgentWorkspaceReadinessViewModelUsesHttpFallbackErrors() async throws {
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

    assert(viewModel.snapshot == nil, "Failed HTTP fallback should not create a snapshot")
    assert(viewModel.errorMessage == "HTTP 502", "HTTP fallback should include the status code")
}

@main
struct AgentWorkspaceReadinessBehavior {
    static func main() async throws {
        try testAgentWorkspaceReadinessBlocksMutationWithoutDiffRoute()
        try testAgentWorkspaceReadinessAllowsMutationWhenGreen()
        try testInformationalPrerequisitesDoNotBlockMutation()
        testStatusPaletteNormalizesWorkspaceStates()
        try testAgentWorkspaceReadinessDecodesBackendPrerequisiteObjects()
        testAgentWorkspaceReadinessViewModelBuildsRefreshRequest()
        try await testAgentWorkspaceReadinessViewModelLoadsSnapshot()
        try await testAgentWorkspaceReadinessViewModelReportsBackendErrors()
        try await testAgentWorkspaceReadinessViewModelUsesHttpFallbackErrors()
        print("AgentWorkspaceReadinessBehavior passed")
    }
}
