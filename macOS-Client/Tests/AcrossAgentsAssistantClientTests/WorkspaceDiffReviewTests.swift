import Foundation
import Testing
@testable import AcrossAgentsAssistantClient

struct WorkspaceDiffReviewTests {
    @Test func unifiedDiffProducesStableOldAndNewLineAnchors() throws {
        let patch = """
        diff --git a/Sources/App.swift b/Sources/App.swift
        index 1111111..2222222 100644
        --- a/Sources/App.swift
        +++ b/Sources/App.swift
        @@ -10,2 +10,3 @@
         context
        -old value
        +new value
        +extra value
        """

        let file = try #require(WorkspaceUnifiedDiffParser.parse(patch).first)
        let anchored = file.lines.compactMap(\.anchor)

        #expect(file.path == "Sources/App.swift")
        #expect(anchored.count == 4)
        #expect(anchored[0].oldLine == 10)
        #expect(anchored[0].newLine == 10)
        #expect(anchored[1].side == "LEFT")
        #expect(anchored[1].oldLine == 11)
        #expect(anchored[2].side == "RIGHT")
        #expect(anchored[2].newLine == 11)
        #expect(anchored[3].newLine == 12)
    }

    @Test func anchoredCommentRequestUsesStructuredSnakeCasePayload() throws {
        let location = WorkspaceDiffLineAnchor(
            path: "Sources/App.swift",
            oldLine: nil,
            newLine: 42,
            side: "RIGHT",
            hunk: "@@ -40,2 +40,3 @@",
            lineText: "let value = 42"
        )
        let anchor = AgentWorkspaceReviewAnchor(
            baseSha: String(repeating: "a", count: 40),
            headSha: String(repeating: "b", count: 40),
            patchSha256: String(repeating: "c", count: 64)
        )
        let encoded = try JSONEncoder().encode(
            AgentWorkspaceLineReviewRequest(
                candidateId: "candidate-1",
                anchor: anchor,
                comments: [
                    AgentWorkspaceLineCommentRequest(
                        path: location.path,
                        side: location.side,
                        line: location.displayLine ?? 0,
                        startLine: location.displayLine,
                        body: "Validate this branch"
                    ),
                ],
                idempotencyKey: "review-1"
            )
        )
        let body = try #require(JSONSerialization.jsonObject(with: encoded) as? [String: Any])
        let encodedAnchor = try #require(body["anchor"] as? [String: Any])
        let comments = try #require(body["comments"] as? [[String: Any]])
        let encodedComment = try #require(comments.first)

        #expect(body["candidate_id"] as? String == "candidate-1")
        #expect(encodedAnchor["base_sha"] as? String == String(repeating: "a", count: 40))
        #expect(encodedAnchor["head_sha"] as? String == String(repeating: "b", count: 40))
        #expect(encodedAnchor["patch_sha256"] as? String == String(repeating: "c", count: 64))
        #expect(encodedComment["path"] as? String == "Sources/App.swift")
        #expect(encodedComment["line"] as? Int == 42)
        #expect(encodedComment["side"] as? String == "RIGHT")
        #expect(encodedComment["body"] as? String == "Validate this branch")
    }

    @Test func candidateRuntimeDecodesAccountAndRateLimitWhenReported() throws {
        let data = Data("""
        {
          "success": true,
          "provider": "openai",
          "model": "codex",
          "account": {
            "id": "account-1",
            "display_name": "Engineering",
            "plan": "team",
            "status": "ready"
          },
          "rate_limit": {
            "status": "healthy",
            "limit": 100,
            "remaining": 72,
            "requests_remaining": 18,
            "reset_at": "2026-07-11T10:30:00Z"
          }
        }
        """.utf8)

        let run = try JSONDecoder().decode(AgentWorkspaceCandidateRun.self, from: data)

        #expect(run.account?.displayName == "Engineering")
        #expect(run.account?.plan == "team")
        #expect(run.rateLimit?.remaining == 72)
        #expect(run.rateLimit?.requestsRemaining == 18)
    }
}
