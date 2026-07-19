import Foundation
import Testing
@testable import AcrossAgentsAssistantClient

struct VisualResultContractTests {
    @Test func completedReviewedTaskProducesEvidenceBackedReadyResult() throws {
        let task = try decodeTask("""
        {
          "task_id": "task-ready",
          "description": "Validate the release",
          "status": "completed",
          "project_dir": "/redacted/project",
          "subtasks": [{
            "subtask_id": "check",
            "description": "Run checks",
            "agent_id": "codex",
            "status": "completed",
            "progress": 1,
            "wave_number": 1
          }],
          "waves": [],
          "artifacts": [{
            "id": "report",
            "file_name": "report.md",
            "file_path": "report.md",
            "file_size": "2 KB"
          }],
          "owner_agent": "codex",
          "review_status": "accepted",
          "quality_health": {"delivery_quality": "passed", "orchestration_health": "healthy"},
          "observability": {
            "timeline": [],
            "quality_gates": [{
              "gate_id": "tests",
              "adapter_id": "pytest",
              "status": "passed",
              "required": true
            }]
          }
        }
        """)

        let result = AcrossVisualResultFactory.make(task: task)

        #expect(result.schemaVersion == AcrossVisualResultContract.currentSchemaVersion)
        #expect(result.verdict == .ready)
        #expect(result.trustCompass.state(for: .outcome) == .confirmed)
        #expect(result.trustCompass.state(for: .proof) == .confirmed)
        #expect(result.trustCompass.state(for: .safety) == .confirmed)
        #expect(result.trustCompass.state(for: .humanControl) == .confirmed)
        #expect(result.nextAction == .inspectEvidence)
        #expect(result.evidenceConstellation.nodes.first(where: { $0.kind == .artifact })?.referenceCount == 1)
        #expect(result.decisionMark?.state == .partial)
        #expect(result.decisionMark?.evidenceHash == nil)
    }

    @Test func failedTaskNeverFabricatesReadyStateOrNumericScore() throws {
        let task = try decodeTask("""
        {
          "task_id": "task-failed",
          "description": "Unsafe delivery",
          "status": "failed",
          "subtasks": [],
          "waves": [],
          "artifacts": [],
          "review_status": "pending",
          "delivery_report": {
            "quality_gate": "failed",
            "failed_constraints": ["required test failed"]
          }
        }
        """)

        let result = AcrossVisualResultFactory.make(task: task)
        let encoded = try JSONEncoder().encode(result)
        let json = String(decoding: encoded, as: UTF8.self)

        #expect(result.verdict == .blocked)
        #expect(result.trustCompass.state(for: .proof) == .blocked)
        #expect(result.trustCompass.state(for: .safety) == .blocked)
        #expect(result.nextAction == .repair)
        #expect(result.attentionStack.first?.priority == .actNow)
        #expect(!json.lowercased().contains("score"))
    }

    @Test func activeTaskUsesTheSameTypedContract() throws {
        let task = try decodeTask("""
        {
          "task_id": "task-running",
          "description": "Run checks",
          "status": "running",
          "subtasks": [],
          "waves": [],
          "artifacts": [],
          "review_status": "pending"
        }
        """)
        let result = AcrossVisualResultFactory.make(task: task)

        #expect(result.verdict == .inProgress)
        #expect(result.nextAction == .wait)
        #expect(result.loopTrail.map(\.stage) == AcrossLoopStage.allCases)
        #expect(result.trustCompass.sectors.count == 4)
    }

    @Test func provisionalBlockingEvidenceDoesNotMislabelAnActiveTask() throws {
        let task = try decodeTask("""
        {
          "task_id": "task-running-provisional-gate",
          "description": "Still producing final evidence",
          "status": "running",
          "subtasks": [],
          "waves": [],
          "artifacts": [],
          "review_status": "pending",
          "delivery_report": {
            "quality_gate": "failed",
            "failed_constraints": ["provisional gate"]
          }
        }
        """)

        let result = AcrossVisualResultFactory.make(task: task)

        #expect(result.verdict == .inProgress)
        #expect(result.nextAction == .wait)
    }

    @Test func pendingHumanDecisionIsGuidanceRatherThanAnError() throws {
        let task = try decodeTask("""
        {
          "task_id": "task-review",
          "description": "Review a verified delivery",
          "status": "completed",
          "subtasks": [],
          "waves": [],
          "artifacts": [{
            "id": "report",
            "file_name": "report.md",
            "file_path": "report.md",
            "file_size": "1 KB"
          }],
          "review_status": "pending",
          "quality_health": {"delivery_quality": "passed", "orchestration_health": "healthy"}
        }
        """)

        let result = AcrossVisualResultFactory.make(task: task)

        #expect(result.verdict == .needsReview)
        #expect(result.attentionStack.first(where: { $0.id == "review" })?.priority == .inspectSoon)
    }

    @Test func acceptedResultNeverReturnsToAwaitingConfirmationWhenAuxiliaryProofIsPartial() throws {
        let task = try decodeTask("""
        {
          "task_id": "task-accepted-partial-proof",
          "description": "Accepted remote delivery",
          "status": "completed",
          "subtasks": [],
          "waves": [],
          "artifacts": [{
            "id": "report",
            "file_name": "report.md",
            "file_path": "report.md",
            "file_size": "1 KB"
          }],
          "review_status": "accepted"
        }
        """)

        let result = AcrossVisualResultFactory.make(task: task)
        let decision = AcrossTaskResultDecision(task: task)

        #expect(result.trustCompass.state(for: .proof) == .partial)
        #expect(result.verdict == .ready)
        #expect(result.nextAction == .inspectEvidence)
        #expect(decision.isAccepted)
        #expect(!decision.canAccept)
        #expect(decision.canInspectEvidence)
    }

    @Test func currentSchemaDecodesAndUnknownSchemaFallsBack() throws {
        let contract = AcrossVisualResultContract(
            taskID: "task-1",
            verdict: .needsReview,
            trustCompass: AcrossTrustCompass(outcome: .confirmed, proof: .partial, safety: .confirmed, humanControl: .partial),
            loopTrail: [],
            evidenceConstellation: AcrossEvidenceConstellation(nodes: [], relations: []),
            attentionStack: [],
            nextAction: .reviewDecision
        )
        let data = try JSONEncoder().encode(contract)
        #expect(AcrossVisualResultDecodeResult.decode(data) == .result(contract))

        let unknown = Data("{\"schemaVersion\":99,\"taskID\":\"future\"}".utf8)
        #expect(AcrossVisualResultDecodeResult.decode(unknown) == .fallback(
            AcrossVisualResultFallback(
                verdict: .needsReview,
                titleKey: "result.fallback.unavailable",
                evidenceReference: nil
            )
        ))
    }

    @Test func attemptLensAndDecisionMarkRemainTypedAndEvidenceHonest() throws {
        let lens = AcrossAttemptLens(
            baselineAttemptID: "attempt-1",
            currentAttemptID: "attempt-2",
            changes: [
                AcrossAttemptChange(id: "tests", title: "Required tests", state: .improved, evidenceReference: "gate:tests"),
                AcrossAttemptChange(id: "budget", title: "Budget", state: .unchanged, evidenceReference: nil),
            ]
        )
        let mark = AcrossDecisionMark(
            targetID: "task-2",
            scope: "task_delivery",
            proposer: "codex",
            approver: nil,
            reversible: nil,
            evidenceHash: nil,
            state: .partial
        )
        let contract = AcrossVisualResultContract(
            taskID: "task-2",
            verdict: .needsReview,
            trustCompass: AcrossTrustCompass(outcome: .confirmed, proof: .confirmed, safety: .confirmed, humanControl: .partial),
            loopTrail: [],
            evidenceConstellation: AcrossEvidenceConstellation(nodes: [], relations: []),
            attentionStack: [],
            attemptLens: lens,
            decisionMark: mark,
            nextAction: .reviewDecision
        )
        let decoded = try JSONDecoder().decode(
            AcrossVisualResultContract.self,
            from: JSONEncoder().encode(contract)
        )

        #expect(decoded.attemptLens == lens)
        #expect(decoded.decisionMark == mark)
        #expect(decoded.decisionMark?.state != .confirmed)
    }

    private func decodeTask(_ json: String) throws -> TaskOrchestrationTaskDetail {
        try JSONDecoder().decode(TaskOrchestrationTaskDetail.self, from: Data(json.utf8))
    }
}
