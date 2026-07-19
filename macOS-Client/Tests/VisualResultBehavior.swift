import Foundation

@main
struct VisualResultBehavior {
    static func main() throws {
        let readyTask = try JSONDecoder().decode(
            TaskOrchestrationTaskDetail.self,
            from: Data("""
            {
              "task_id": "visual-ready",
              "description": "Verify delivery",
              "status": "completed",
              "project_dir": "/redacted/project",
              "subtasks": [],
              "waves": [],
              "artifacts": [{"id":"report","file_name":"report.md","file_path":"report.md","file_size":"1 KB"}],
              "review_status": "accepted",
              "quality_health": {"delivery_quality":"passed","orchestration_health":"healthy"},
              "observability": {
                "timeline": [],
                "quality_gates": [{"gate_id":"tests","adapter_id":"swift","status":"passed","required":true}]
              }
            }
            """.utf8)
        )
        let result = AcrossVisualResultFactory.make(task: readyTask)
        precondition(result.verdict == .ready)
        precondition(result.trustCompass.sectors.count == 4)
        precondition(result.trustCompass.sectors.allSatisfy { $0.state == .confirmed })
        precondition(result.nextAction == .inspectEvidence)
        precondition(result.decisionMark?.evidenceHash == nil)
        precondition(result.decisionMark?.state == .partial)

        let acceptedWithPartialProof = try JSONDecoder().decode(
            TaskOrchestrationTaskDetail.self,
            from: Data("""
            {
              "task_id": "visual-accepted-partial",
              "description": "Accepted delivery with auxiliary evidence still partial",
              "status": "completed",
              "subtasks": [],
              "waves": [],
              "artifacts": [{"id":"report","file_name":"report.md","file_path":"report.md","file_size":"1 KB"}],
              "review_status": "accepted"
            }
            """.utf8)
        )
        let acceptedPartial = AcrossVisualResultFactory.make(task: acceptedWithPartialProof)
        let acceptedDecision = AcrossTaskResultDecision(task: acceptedWithPartialProof)
        precondition(acceptedPartial.trustCompass.state(for: .proof) == .partial)
        precondition(acceptedPartial.verdict == .ready)
        precondition(acceptedPartial.nextAction == .inspectEvidence)
        precondition(acceptedDecision.isAccepted)
        precondition(!acceptedDecision.canAccept)

        let blockedTask = try JSONDecoder().decode(
            TaskOrchestrationTaskDetail.self,
            from: Data("""
            {
              "task_id": "visual-blocked",
              "description": "Failed delivery",
              "status": "failed",
              "subtasks": [],
              "waves": [],
              "artifacts": [],
              "review_status": "pending",
              "delivery_report": {"quality_gate":"failed","failed_constraints":["tests failed"]}
            }
            """.utf8)
        )
        let blocked = AcrossVisualResultFactory.make(task: blockedTask)
        precondition(blocked.verdict == .blocked)
        precondition(blocked.trustCompass.state(for: .proof) == .blocked)
        precondition(blocked.trustCompass.state(for: .safety) == .blocked)
        precondition(blocked.nextAction == .repair)

        let runningTask = try JSONDecoder().decode(
            TaskOrchestrationTaskDetail.self,
            from: Data("""
            {
              "task_id": "visual-running",
              "description": "Still producing final evidence",
              "status": "running",
              "subtasks": [],
              "waves": [],
              "artifacts": [],
              "review_status": "pending",
              "delivery_report": {"quality_gate":"failed","failed_constraints":["provisional gate"]}
            }
            """.utf8)
        )
        let running = AcrossVisualResultFactory.make(task: runningTask)
        precondition(running.verdict == .inProgress)
        precondition(running.nextAction == .wait)

        let encoded = try JSONEncoder().encode(result)
        precondition(!String(decoding: encoded, as: UTF8.self).lowercased().contains("score"))
        precondition(AcrossVisualResultDecodeResult.decode(encoded) == .result(result))

        let future = Data("{\"schemaVersion\":99}".utf8)
        guard case .fallback(let fallback) = AcrossVisualResultDecodeResult.decode(future) else {
            preconditionFailure("unknown schemas must fall back")
        }
        precondition(fallback.titleKey == "result.fallback.unavailable")

        print("Visual result behavior checks passed.")
    }
}
