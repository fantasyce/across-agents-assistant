import Foundation
import Testing
@testable import AcrossAgentsAssistantClient

struct GoalProjectionReducerTests {
    @Test func legacyTaskHasExplicitEmptyState() {
        #expect(GoalProjectionReducer.reduce(nil, loading: false, error: nil) == .legacyEmpty)
    }

    @Test func staleEvidenceTakesPriorityOverExecutionState() throws {
        let envelope = try decode(displayState: "revalidation_required", evidenceState: "stale", reasons: ["criterion_evidence_stale"])
        #expect(GoalProjectionReducer.reduce(envelope, loading: false, error: nil) == .stale)
    }

    @Test func pendingProposalRequiresDecision() throws {
        var json = GoalContractModelsTests.envelopeJSON(displayState: "waiting_for_decision", reasons: ["decision_pending"])
        json = json.replacingOccurrences(of: "\"pending_proposals\": []", with: "\"pending_proposals\": [{\"proposal_id\":\"proposal-1\",\"goal_id\":\"goal-1\",\"base_goal_revision\":2,\"proposed_by\":\"agent:planner\",\"reason\":\"Improve scope\",\"operations\":[],\"impact_summary\":{},\"risk_summary\":{},\"estimated_cost\":{},\"alternatives\":[],\"decision_state\":\"pending\",\"created_at\":\"2026-08-28T00:00:00Z\"}]")
        let envelope = try JSONDecoder().decode(GoalContractEnvelope.self, from: Data(json.utf8))
        #expect(GoalProjectionReducer.reduce(envelope, loading: false, error: nil) == .decisionRequired)
    }

    @Test func pendingReviewRemainsAnAuthoritativeActiveState() throws {
        let envelope = try decode(
            displayState: "waiting_for_review",
            evidenceState: "satisfied",
            reasons: ["review_pending"]
        )
        #expect(
            GoalProjectionReducer.reduce(envelope, loading: false, error: nil)
                == .active(.known("waiting_for_review"))
        )
    }

    @Test func failedRequiredCriterionIsErrorNotCompletion() throws {
        let envelope = try decode(displayState: "failed", evidenceState: "failed", reasons: ["criterion_evidence_failed"])
        #expect(GoalProjectionReducer.reduce(envelope, loading: false, error: nil) == .error("criterion_evidence_failed"))
    }

    @Test func completionComesOnlyFromAuthoritativeProjection() throws {
        let complete = try decode(displayState: "completed", evidenceState: "satisfied", reasons: [], complete: true)
        let merelyFinished = try decode(displayState: "finished", evidenceState: "satisfied", reasons: [], complete: false)
        #expect(GoalProjectionReducer.reduce(complete, loading: false, error: nil) == .completed)
        #expect(GoalProjectionReducer.reduce(merelyFinished, loading: false, error: nil) == .active(.known("finished")))
    }

    private func decode(
        displayState: String,
        evidenceState: String,
        reasons: [String],
        complete: Bool = false
    ) throws -> GoalContractEnvelope {
        var json = GoalContractModelsTests.envelopeJSON(displayState: displayState, evidenceState: evidenceState, reasons: reasons)
        if complete {
            json = json.replacingOccurrences(of: "\"is_complete\": false", with: "\"is_complete\": true")
        }
        return try JSONDecoder().decode(GoalContractEnvelope.self, from: Data(json.utf8))
    }
}
