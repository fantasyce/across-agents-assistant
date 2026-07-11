import Foundation
import Testing
@testable import AcrossAgentsAssistantClient

struct AgentWorkspaceReadinessTests {
    @Test func operationalStatusDecodesExplicitAccountAndRateLimit() throws {
        let payload = Data("""
        {
          "schema_version": "agent-workspace-readiness/1.0",
          "status": "ready",
          "workspace_isolation": {"status":"ready","supports_git_worktree":true,"can_create_isolated_workspaces":true},
          "agents": [{"agent_id":"codex","status":"ready","available":true}],
          "routes": {"events":"/events","diff":"/diff","evidence":"/evidence"},
          "agent_operational_status": [{
            "agent_id": "codex",
            "account": {"status":"known","id":"account-1","display_name":"Engineering"},
            "auth": {"status":"authenticated","authenticated":true,"method":"browser_login"},
            "model": {"status":"configured","id":"codex"},
            "provider": {"status":"known","id":"openai"},
            "usage": {"status":"known","window":"day","input_tokens":12,"output_tokens":3,"total_tokens":15,"requests":2},
            "rate_limit": {"status":"limited","remaining":8,"limit":10,"reset_at":"2030-01-01T00:00:00Z","retry_after_seconds":2.5}
          }]
        }
        """.utf8)

        let snapshot = try JSONDecoder().decode(AgentWorkspaceReadinessSnapshot.self, from: payload)
        let status = try #require(snapshot.operationalStatus(for: "codex"))

        #expect(status.account.displayName == "Engineering")
        #expect(status.rateLimit.remaining == 8)
        #expect(status.usage.totalTokens == 15)
    }

    @Test func readinessSnapshotKeepsMutationBlockedUntilRequiredRoutesExist() throws {
        let payload = """
        {
          "schema_version": "agent-workspace-readiness/1.0",
          "status": "ready",
          "repo_root": "/tmp/across",
          "prompt": "Review the repo",
          "selected_agent_ids": ["codex", "claude"],
          "execution_strategy": "parallel_worktrees",
          "workspace_isolation": {
            "status": "ready",
            "mode": "git_worktree",
            "supports_git_worktree": true,
            "can_create_isolated_workspaces": true
          },
          "agents": [
            {
              "agent_id": "codex",
              "display_name": "Codex",
              "status": "ready",
              "available": true,
              "supported_workspace_modes": ["git_worktree"]
            },
            {
              "agent_id": "claude",
              "display_name": "Claude Code",
              "status": "not_ready",
              "available": false,
              "missing_prerequisites": ["authentication"]
            }
          ],
          "routes": {
            "events": "/api/agent-workspaces/ws-1/events",
            "evidence": "/api/agent-workspaces/ws-1/evidence"
          }
        }
        """.data(using: .utf8)!

        let snapshot = try JSONDecoder().decode(AgentWorkspaceReadinessSnapshot.self, from: payload)

        #expect(snapshot.status == .ready)
        #expect(snapshot.readyAgentIds == ["codex"])
        #expect(snapshot.selectedReadyAgentIds == ["codex"])
        #expect(!snapshot.canCreateWorkspace)
        #expect(snapshot.readinessIssues == ["diff_route"])
    }

    @Test func readinessSnapshotAllowsWorkspaceWhenIsolationRoutesAndAgentAreReady() throws {
        let payload = """
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

        let snapshot = try JSONDecoder().decode(AgentWorkspaceReadinessSnapshot.self, from: payload)

        #expect(snapshot.workspaceIsolation.canCreateIsolatedWorkspaces)
        #expect(snapshot.canCreateWorkspace)
        #expect(snapshot.readinessIssues.isEmpty)
    }

    @Test func informationalPrerequisitesDoNotBlockWorkspaceReadiness() throws {
        let payload = """
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

        let snapshot = try JSONDecoder().decode(AgentWorkspaceReadinessSnapshot.self, from: payload)

        #expect(snapshot.missingPrerequisites == ["workspace_root_missing"])
        #expect(snapshot.canCreateWorkspace)
        #expect(snapshot.readinessIssues.isEmpty)
    }

    @Test func statusPaletteNormalizesReadinessStates() {
        #expect(StatusPalette.tone(for: "ready") == .success)
        #expect(StatusPalette.tone(for: "not_ready") == .warning)
        #expect(StatusPalette.tone(for: "blocked") == .danger)
        #expect(StatusPalette.tone(for: "not-implemented") == .neutral)
        #expect(StatusPalette.systemImage(for: "ready") == "checkmark.circle.fill")
        #expect(StatusPalette.displayText(for: "needs_attention") == "Needs Attention")
    }

    @Test func readinessSnapshotDecodesBackendPrerequisiteObjects() throws {
        let payload = """
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

        let snapshot = try JSONDecoder().decode(AgentWorkspaceReadinessSnapshot.self, from: payload)

        #expect(snapshot.generatedAt == "2026-07-10T00:00:00+00:00")
        #expect(snapshot.missingPrerequisites == ["no_available_local_agents", "workspace_root_missing"])
        #expect(snapshot.readyAgentIds == ["openclaw"])
        #expect(!snapshot.canCreateWorkspace)
    }
}
