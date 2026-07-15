import CryptoKit
import Foundation
import Testing
@testable import AcrossAgentsAssistantClient

private final class TrustRequestRecorder: @unchecked Sendable {
    private let lock = NSLock()
    private var paths: [String] = []

    func record(_ request: URLRequest) {
        lock.lock()
        paths.append(request.url?.path ?? "")
        lock.unlock()
    }

    func allPaths() -> [String] {
        lock.lock()
        defer { lock.unlock() }
        return paths
    }
}

struct RunTrustContractsTests {
    @Test func sourcePayloadBuildsComparisonOnlyFromRecordedRepairEvidence() throws {
        let task = try decodeTask(taskFixture)
        let payloads = RunTrustContractsViewModel.payloads(task: task)

        #expect(payloads.comparison != nil)
        #expect((payloads.policy["role"] as? String) == "codex")
        #expect((payloads.policy["model_policy"] as? [String: Any])?.isEmpty == true)
        #expect((payloads.policy["actions"] as? [String]) == ["Run checks"])
        let comparison = try #require(payloads.comparison)
        let baseline = try #require(comparison["baseline"] as? [String: Any])
        #expect((baseline["status"] as? String) == "failed")
        #expect((baseline["checks"] as? [String: String]) == ["repair_round_1": "failed"])
    }

    @Test @MainActor func packagedInspectorLoadsAllContractsAndBindsReceiptToTaskHash() async throws {
        let task = try decodeTask(taskFixture)
        let recorder = TrustRequestRecorder()
        let taskHash = SHA256.hash(data: Data(task.taskId.utf8))
            .map { String(format: "%02x", $0) }
            .joined()
        let viewModel = RunTrustContractsViewModel { request in
            recorder.record(request)
            let payload: String
            switch request.url?.path {
            case "/api/orchestrator/contracts/execution-policy":
                payload = policyFixture
            case "/api/orchestrator/runs/compare":
                payload = comparisonFixture
            case "/api/orchestrator/runs/replay-plan":
                payload = replayFixture
            case "/api/approval-receipts":
                payload = receiptFixture(subjectIDHash: taskHash)
            default:
                Issue.record("Unexpected path: \(request.url?.path ?? "nil")")
                payload = "{}"
            }
            return (
                Data(payload.utf8),
                HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            )
        }

        await viewModel.load(task: task)

        #expect(viewModel.errorMessage == nil)
        #expect(viewModel.policy?.role.id == "codex")
        #expect(viewModel.policy?.modelPolicy.model == nil)
        #expect(viewModel.attemptLens?.changes.contains(where: { $0.id == "model_policy" }) == true)
        #expect(viewModel.replayPlan?.execution.performed == false)
        #expect(viewModel.replayPlan?.execution.automaticExecutionAllowed == false)
        #expect(viewModel.decisionMark(for: task)?.state == .confirmed)
        #expect(Set(recorder.allPaths()) == Set([
            "/api/orchestrator/contracts/execution-policy",
            "/api/orchestrator/runs/compare",
            "/api/orchestrator/runs/replay-plan",
            "/api/approval-receipts",
        ]))
    }

    @Test @MainActor func taskWithoutRecordedRepairDoesNotFabricateAttemptLens() async throws {
        let task = try decodeTask(taskFixture.replacingOccurrences(of: fixRoundsFragment, with: "\"fix_rounds\": []"))
        #expect(RunTrustContractsViewModel.payloads(task: task).comparison == nil)
    }

    private func decodeTask(_ json: String) throws -> TaskOrchestrationTaskDetail {
        try JSONDecoder().decode(TaskOrchestrationTaskDetail.self, from: Data(json.utf8))
    }
}

private let fixRoundsFragment = """
"fix_rounds": [{
      "round_number": 1,
      "status": "failed",
      "agent_id": "codex",
      "fix_description": "Repair the failed check"
    }]
"""

private let taskFixture = """
{
  "task_id": "task-trust-1",
  "description": "Verify the project",
  "status": "completed",
  "task_types": ["functional"],
  "owner_agent": "codex",
  "subtasks": [{
    "subtask_id": "check",
    "description": "Run checks",
    "agent_id": "codex",
    "status": "completed",
    "progress": 1,
    "wave_number": 1,
    "waiting_on_dependencies": []
  }],
  "waves": [{
    "wave_id": "wave-1",
    "wave_number": 1,
    "subtasks": [],
    "status": "completed",
    "is_blocked": false,
    "is_revalidating": false,
    \(fixRoundsFragment)
  }],
  "artifacts": [{
    "id": "report",
    "file_name": "report.md",
    "file_path": "report.md",
    "file_size": "1 KB"
  }],
  "review_status": "accepted",
  "observability": {
    "timeline": [],
    "quality_gates": [{
      "gate_id": "tests",
      "adapter_id": "pytest",
      "status": "passed",
      "required": true
    }],
    "remediation": {
      "attempted": true,
      "attempts_by_requirement": {"tests": 1},
      "max_attempts": 2,
      "deterministic_repair_attempted": true
    }
  }
}
"""

private let policyFixture = """
{
  "schema_version":"across-execution-policy/1.0",
  "run_id":"task-trust-1",
  "role":{"id":"codex","label":"Codex"},
  "model_policy":{"fallback_models":[],"required":false,"host_owned_credentials":true,"credentials_included":false},
  "budget":{"max_model_calls":0,"max_candidate_repairs":2,"max_usd":0,"max_runtime_seconds":0},
  "risk":{"profile":"low","reason":"read-only or no side effects detected","external_side_effects":[]},
  "sandbox":{"risk_profile":"low","selection_reason":"read-only or no side effects detected","network_policy":"none","filesystem_policy":"read_only","execution_mode":"read_only","external_side_effects_blocked":true},
  "approval":{"required":false,"renewed_approval_required_for_replay":false,"proposer_approver_separation_required":false}
}
"""

private let comparisonFixture = """
{
  "schema_version":"across-run-comparison/1.0",
  "baseline":{"run_id":"task-trust-1:repair-1","status":"failed","verdict":"failed"},
  "candidate":{"run_id":"task-trust-1:current","status":"completed","verdict":"ready"},
  "changes":{
    "verdict":{"changed":true,"before":"failed","after":"ready"},
    "checks":{"changed":true,"items":[{"id":"tests","before":"failed","after":"passed","classification":"improved"}],"improved":["tests"],"regressed":[]},
    "evidence":{"changed":true,"added":["tests"],"removed":[],"retained":[]},
    "code_revision":{"changed":false},
    "model_policy":{"changed":false},
    "budget":{"changed":true,"items":[{"id":"candidate_repairs","before":0,"after":1,"delta":1}]}
  },
  "comparison_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}
"""

private let replayFixture = """
{
  "schema_version":"across-replay-plan/1.0",
  "status":"ready",
  "mode":"simulation",
  "source_snapshot_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "external_side_effects":[],
  "renewed_approval":{"required":false,"verified":false},
  "execution":{"performed":false,"automatic_execution_allowed":false,"side_effects_repeated":false},
  "blocked_reasons":[],
  "next_action":"review_simulation",
  "plan_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
}
"""

private func receiptFixture(subjectIDHash: String) -> String {
    """
    {
      "schema_version":"across-approval-receipt-chain/1.0",
      "total":1,
      "limit":100,
      "offset":0,
      "receipts":[{
        "schema_version":"across-approval-receipt/1.0",
        "receipt_id":"approval-1",
        "sequence":1,
        "subject_type":"task_result",
        "subject_id_sha256":"\(subjectIDHash)",
        "subject_sha256":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
        "scope":"task_result_review",
        "decision":"approved",
        "proposer_id":"agent",
        "approver_id":"human",
        "risk_level":"medium",
        "receipt_hash":"eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
        "integrity_status":"verified"
      }],
      "page_integrity_status":"verified",
      "chain_integrity_status":"verified",
      "integrity_status":"verified"
    }
    """
}
