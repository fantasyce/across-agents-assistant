import Foundation
import Testing
@testable import AcrossAgentsAssistantClient

struct GoalContractModelsTests {
    @Test func decodesAuthoritativeProjectionAndPreservesUnknownFutureStates() throws {
        let envelope = try JSONDecoder().decode(
            GoalContractEnvelope.self,
            from: Data(Self.envelopeJSON(
                displayState: "future_wait_state",
                evidenceState: "future_evidence_state",
                reasons: ["future_reason_code"]
            ).utf8)
        )

        #expect(envelope.contract.goalId == "goal-1")
        #expect(envelope.contract.revision == 2)
        #expect(envelope.projection.displayState == .unknown("future_wait_state"))
        #expect(envelope.projection.evidenceState == .unknown("future_evidence_state"))
        #expect(envelope.projection.reasonCodes == [.unknown("future_reason_code")])
        #expect(envelope.projection.criterionCoverage.first?.criterionId == "criterion-1")
    }

    @Test func proposalAndRevalidationRequestsEncodeRevisionAndIdempotency() throws {
        let decision = GoalProposalDecisionRequest(
            decision: "accepted",
            expectedRevision: 3,
            operationIndexes: [0],
            approverId: "human:local",
            idempotencyKey: "decision-1"
        )
        let revalidation = GoalRevalidationRequest(
            expectedRevision: 3,
            criterionIds: ["criterion-1"],
            reason: "Source changed",
            idempotencyKey: "revalidate-1"
        )
        let review = GoalCriterionReviewRequest(
            expectedRevision: 3,
            criterionId: "criterion-1",
            decision: "passed",
            reason: "Fixed and verified",
            reviewerId: "human:local",
            idempotencyKey: "review-1"
        )

        let decisionObject = try #require(try JSONSerialization.jsonObject(with: JSONEncoder().encode(decision)) as? [String: Any])
        let revalidationObject = try #require(try JSONSerialization.jsonObject(with: JSONEncoder().encode(revalidation)) as? [String: Any])
        let reviewObject = try #require(try JSONSerialization.jsonObject(with: JSONEncoder().encode(review)) as? [String: Any])
        #expect(decisionObject["expected_revision"] as? Int == 3)
        #expect(decisionObject["idempotency_key"] as? String == "decision-1")
        #expect(revalidationObject["criterion_ids"] as? [String] == ["criterion-1"])
        #expect(revalidationObject["idempotency_key"] as? String == "revalidate-1")
        #expect(reviewObject["criterion_id"] as? String == "criterion-1")
        #expect(reviewObject["reviewer_id"] as? String == "human:local")
    }

    static func envelopeJSON(
        displayState: String = "running",
        evidenceState: String = "partial",
        reasons: [String] = ["criterion_evidence_missing"]
    ) -> String {
        let reasonJSON = reasons.map { "\"\($0)\"" }.joined(separator: ",")
        return """
        {
          "contract": {
            "schema_version": "across-goal-contract/1.0",
            "goal_id": "goal-1", "revision": 2, "task_id": "task-1",
            "statement": "Ship safely", "success_outcome": "Accepted release",
            "scope": {"includes": ["app"], "excludes": ["release"]},
            "acceptance_criteria": [{
              "criterion_id": "criterion-1", "description": "Tests pass", "required": true,
              "validator_kind": "test", "review_policy": "human", "source": "user"
            }],
            "dependencies": [], "execution_profile": "orchestrated", "source": "user",
            "confirmed_by": "human:local", "confirmed_at": "2026-08-28T00:00:00Z",
            "created_at": "2026-08-28T00:00:00Z"
          },
          "projection": {
            "schema_version": "across-goal-state-projection/1.0",
            "goal_id": "goal-1", "goal_revision": 2, "task_id": "task-1",
            "definition_state": "confirmed", "execution_state": "running",
            "evidence_state": "\(evidenceState)", "review_state": "pending",
            "decision_state": "none", "validity_state": "valid",
            "criterion_coverage": [{
              "criterion_id": "criterion-1", "required": true,
              "evidence_state": "missing", "review_state": "pending", "satisfied": false
            }],
            "reason_codes": [\(reasonJSON)], "is_complete": false,
            "display_state": "\(displayState)",
            "authority": {"goal": "aaa", "execution": "orchestrator_or_direct_agent", "evidence": "trusted_runtime", "decisions": "aaa"}
          },
          "pending_proposals": [], "evidence_bindings": []
        }
        """
    }
}
