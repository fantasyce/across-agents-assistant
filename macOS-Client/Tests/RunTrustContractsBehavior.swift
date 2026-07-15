import CryptoKit
import Foundation

@main
struct RunTrustContractsBehavior {
    @MainActor
    static func main() async throws {
        let task = try JSONDecoder().decode(
            TaskOrchestrationTaskDetail.self,
            from: Data(
                """
                {
                  "task_id":"task-trust-behavior",
                  "description":"Verify",
                  "status":"completed",
                  "owner_agent":"codex",
                  "task_types":["functional"],
                  "subtasks":[{"subtask_id":"check","description":"Run checks","agent_id":"codex","status":"completed","progress":1,"wave_number":1,"waiting_on_dependencies":[]}],
                  "waves":[{"wave_id":"wave-1","wave_number":1,"subtasks":[],"status":"completed","is_blocked":false,"is_revalidating":false,"fix_rounds":[{"round_number":1,"status":"failed","agent_id":"codex","fix_description":"Repair"}]}],
                  "artifacts":[],
                  "review_status":"accepted",
                  "observability":{"timeline":[],"quality_gates":[{"gate_id":"tests","adapter_id":"pytest","status":"passed","required":true}],"remediation":{"attempted":true,"attempts_by_requirement":{"tests":1},"max_attempts":2,"deterministic_repair_attempted":true}}
                }
                """.utf8
            )
        )
        let taskHash = SHA256.hash(data: Data(task.taskId.utf8))
            .map { String(format: "%02x", $0) }
            .joined()
        let viewModel = RunTrustContractsViewModel { request in
            let payload: String
            switch request.url?.path {
            case "/api/orchestrator/contracts/execution-policy":
                payload = policyJSON
            case "/api/orchestrator/runs/compare":
                payload = comparisonJSON
            case "/api/orchestrator/runs/replay-plan":
                payload = replayJSON
            case "/api/approval-receipts":
                payload = receiptsJSON(taskHash: taskHash)
            default:
                throw URLError(.badURL)
            }
            return (
                Data(payload.utf8),
                HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            )
        }

        await viewModel.load(task: task)

        precondition(viewModel.errorMessage == nil)
        precondition(viewModel.policy?.role.id == "codex")
        precondition(viewModel.policy?.modelPolicy.model == nil)
        precondition(viewModel.attemptLens?.changes.contains(where: { $0.id == "verdict" }) == true)
        precondition(viewModel.replayPlan?.execution.performed == false)
        precondition(viewModel.replayPlan?.execution.automaticExecutionAllowed == false)
        precondition(viewModel.replayPlan?.execution.sideEffectsRepeated == false)
        precondition(viewModel.receiptChain?.chainIntegrityStatus == "verified")
        precondition(viewModel.decisionMark(for: task)?.state == .confirmed)

        print("Run trust contract behavior checks passed.")
    }
}

private let policyJSON = """
{"schema_version":"across-execution-policy/1.0","run_id":"task-trust-behavior","role":{"id":"codex","label":"Codex"},"model_policy":{"fallback_models":[],"required":false,"host_owned_credentials":true,"credentials_included":false},"budget":{"max_model_calls":0,"max_candidate_repairs":2,"max_usd":0,"max_runtime_seconds":0},"risk":{"profile":"low","reason":"read only","external_side_effects":[]},"sandbox":{"risk_profile":"low","selection_reason":"read only","network_policy":"none","filesystem_policy":"read_only","execution_mode":"read_only","external_side_effects_blocked":true},"approval":{"required":false,"renewed_approval_required_for_replay":false,"proposer_approver_separation_required":false}}
"""

private let comparisonJSON = """
{"schema_version":"across-run-comparison/1.0","baseline":{"run_id":"before","status":"failed","verdict":"failed"},"candidate":{"run_id":"after","status":"completed","verdict":"ready"},"changes":{"verdict":{"changed":true,"before":"failed","after":"ready"},"checks":{"changed":true,"items":[{"id":"tests","before":"failed","after":"passed","classification":"improved"}],"improved":["tests"],"regressed":[]},"evidence":{"changed":true,"added":["tests"],"removed":[],"retained":[]},"code_revision":{"changed":false},"model_policy":{"changed":false},"budget":{"changed":false,"items":[]}},"comparison_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
"""

private let replayJSON = """
{"schema_version":"across-replay-plan/1.0","status":"ready","mode":"simulation","source_snapshot_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","external_side_effects":[],"renewed_approval":{"required":false,"verified":false},"execution":{"performed":false,"automatic_execution_allowed":false,"side_effects_repeated":false},"blocked_reasons":[],"next_action":"review_simulation","plan_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"}
"""

private func receiptsJSON(taskHash: String) -> String {
    """
    {"schema_version":"across-approval-receipt-chain/1.0","total":1,"receipts":[{"receipt_id":"approval-1","sequence":1,"subject_type":"task_result","subject_id_sha256":"\(taskHash)","subject_sha256":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd","scope":"task_result_review","decision":"approved","proposer_id":"agent","approver_id":"human","risk_level":"medium","receipt_hash":"eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee","integrity_status":"verified"}],"page_integrity_status":"verified","chain_integrity_status":"verified","integrity_status":"verified"}
    """
}
