import CryptoKit
import Foundation

struct AcrossExecutionPolicyContract: Decodable, Equatable {
    struct Role: Decodable, Equatable {
        let id: String
        let label: String
        let responsibility: String?
    }

    struct ModelPolicy: Decodable, Equatable {
        let provider: String?
        let model: String?
        let fallbackModels: [String]
        let required: Bool
        let hostOwnedCredentials: Bool
        let credentialsIncluded: Bool

        enum CodingKeys: String, CodingKey {
            case provider, model
            case fallbackModels = "fallback_models"
            case required
            case hostOwnedCredentials = "host_owned_credentials"
            case credentialsIncluded = "credentials_included"
        }
    }

    struct Budget: Decodable, Equatable {
        let maxModelCalls: Int
        let maxCandidateRepairs: Int
        let maxUSD: Double
        let maxRuntimeSeconds: Double

        enum CodingKeys: String, CodingKey {
            case maxModelCalls = "max_model_calls"
            case maxCandidateRepairs = "max_candidate_repairs"
            case maxUSD = "max_usd"
            case maxRuntimeSeconds = "max_runtime_seconds"
        }
    }

    struct Risk: Decodable, Equatable {
        let profile: String
        let reason: String
        let externalSideEffects: [String]

        enum CodingKeys: String, CodingKey {
            case profile, reason
            case externalSideEffects = "external_side_effects"
        }
    }

    struct Sandbox: Decodable, Equatable {
        let riskProfile: String
        let selectionReason: String
        let networkPolicy: String
        let filesystemPolicy: String
        let executionMode: String
        let externalSideEffectsBlocked: Bool

        enum CodingKeys: String, CodingKey {
            case riskProfile = "risk_profile"
            case selectionReason = "selection_reason"
            case networkPolicy = "network_policy"
            case filesystemPolicy = "filesystem_policy"
            case executionMode = "execution_mode"
            case externalSideEffectsBlocked = "external_side_effects_blocked"
        }
    }

    struct Approval: Decodable, Equatable {
        let required: Bool
        let renewedApprovalRequiredForReplay: Bool
        let proposerApproverSeparationRequired: Bool

        enum CodingKeys: String, CodingKey {
            case required
            case renewedApprovalRequiredForReplay = "renewed_approval_required_for_replay"
            case proposerApproverSeparationRequired = "proposer_approver_separation_required"
        }
    }

    let schemaVersion: String
    let runID: String?
    let role: Role
    let modelPolicy: ModelPolicy
    let budget: Budget
    let risk: Risk
    let sandbox: Sandbox
    let approval: Approval

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case runID = "run_id"
        case role
        case modelPolicy = "model_policy"
        case budget, risk, sandbox, approval
    }
}

struct AcrossRunComparisonContract: Decodable, Equatable {
    struct Snapshot: Decodable, Equatable {
        let runID: String
        let status: String
        let verdict: String

        enum CodingKeys: String, CodingKey {
            case runID = "run_id"
            case status, verdict
        }
    }

    struct ValueChange: Decodable, Equatable {
        let changed: Bool
        let before: OperationsJSONValue?
        let after: OperationsJSONValue?
    }

    struct CheckChange: Decodable, Equatable, Identifiable {
        let id: String
        let before: String
        let after: String
        let classification: String
    }

    struct ChecksChange: Decodable, Equatable {
        let changed: Bool
        let items: [CheckChange]
        let improved: [String]
        let regressed: [String]
    }

    struct SetChange: Decodable, Equatable {
        let changed: Bool
        let added: [String]
        let removed: [String]
        let retained: [String]
    }

    struct ObjectChange: Decodable, Equatable {
        let changed: Bool
    }

    struct BudgetItem: Decodable, Equatable, Identifiable {
        let id: String
        let before: OperationsJSONValue?
        let after: OperationsJSONValue?
        let delta: Double?
    }

    struct BudgetChange: Decodable, Equatable {
        let changed: Bool
        let items: [BudgetItem]
    }

    struct Changes: Decodable, Equatable {
        let verdict: ValueChange
        let checks: ChecksChange
        let evidence: SetChange
        let codeRevision: ValueChange
        let modelPolicy: ObjectChange
        let budget: BudgetChange

        enum CodingKeys: String, CodingKey {
            case verdict, checks, evidence, budget
            case codeRevision = "code_revision"
            case modelPolicy = "model_policy"
        }
    }

    let schemaVersion: String
    let baseline: Snapshot
    let candidate: Snapshot
    let changes: Changes
    let comparisonSHA256: String

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case baseline, candidate, changes
        case comparisonSHA256 = "comparison_sha256"
    }
}

struct AcrossReplayPlanContract: Decodable, Equatable {
    struct RenewedApproval: Decodable, Equatable {
        let required: Bool
        let verified: Bool
        let receiptID: String?

        enum CodingKeys: String, CodingKey {
            case required, verified
            case receiptID = "receipt_id"
        }
    }

    struct Execution: Decodable, Equatable {
        let performed: Bool
        let automaticExecutionAllowed: Bool
        let sideEffectsRepeated: Bool

        enum CodingKeys: String, CodingKey {
            case performed
            case automaticExecutionAllowed = "automatic_execution_allowed"
            case sideEffectsRepeated = "side_effects_repeated"
        }
    }

    let schemaVersion: String
    let status: String
    let mode: String
    let sourceSnapshotSHA256: String
    let externalSideEffects: [String]
    let renewedApproval: RenewedApproval
    let execution: Execution
    let blockedReasons: [String]
    let nextAction: String
    let planSHA256: String

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case status, mode
        case sourceSnapshotSHA256 = "source_snapshot_sha256"
        case externalSideEffects = "external_side_effects"
        case renewedApproval = "renewed_approval"
        case execution
        case blockedReasons = "blocked_reasons"
        case nextAction = "next_action"
        case planSHA256 = "plan_sha256"
    }
}

struct AcrossApprovalReceipt: Decodable, Equatable, Identifiable {
    let receiptID: String
    let sequence: Int
    let subjectType: String
    let subjectIDSHA256: String
    let subjectSHA256: String
    let scope: String
    let decision: String
    let proposerID: String
    let approverID: String
    let riskLevel: String
    let receiptHash: String
    let integrityStatus: String

    var id: String { receiptID }

    enum CodingKeys: String, CodingKey {
        case receiptID = "receipt_id"
        case sequence
        case subjectType = "subject_type"
        case subjectIDSHA256 = "subject_id_sha256"
        case subjectSHA256 = "subject_sha256"
        case scope, decision
        case proposerID = "proposer_id"
        case approverID = "approver_id"
        case riskLevel = "risk_level"
        case receiptHash = "receipt_hash"
        case integrityStatus = "integrity_status"
    }
}

struct AcrossApprovalReceiptChain: Decodable, Equatable {
    let schemaVersion: String
    let total: Int
    let receipts: [AcrossApprovalReceipt]
    let pageIntegrityStatus: String
    let chainIntegrityStatus: String
    let integrityStatus: String

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case total, receipts
        case pageIntegrityStatus = "page_integrity_status"
        case chainIntegrityStatus = "chain_integrity_status"
        case integrityStatus = "integrity_status"
    }
}

struct RunTrustContractPayloads {
    let policy: [String: Any]
    let comparison: [String: Any]?
    let replay: [String: Any]
}

@MainActor
final class RunTrustContractsViewModel: ObservableObject {
    typealias DataLoader = @Sendable (URLRequest) async throws -> (Data, URLResponse)

    @Published private(set) var policy: AcrossExecutionPolicyContract?
    @Published private(set) var comparison: AcrossRunComparisonContract?
    @Published private(set) var replayPlan: AcrossReplayPlanContract?
    @Published private(set) var receiptChain: AcrossApprovalReceiptChain?
    @Published private(set) var isLoading = false
    @Published private(set) var errorMessage: String?

    private let backendBaseURL: URL
    private let dataLoader: DataLoader
    private var taskID: String?

    init(
        backendBaseURL: URL = URL(string: "http://backend")!,
        dataLoader: @escaping DataLoader = { request in
            try await URLSession.shared.data(for: request)
        }
    ) {
        self.backendBaseURL = backendBaseURL
        self.dataLoader = dataLoader
    }

    func load(task: TaskOrchestrationTaskDetail, refresh: Bool = false) async {
        guard refresh || taskID != task.taskId else { return }
        taskID = task.taskId
        policy = nil
        comparison = nil
        replayPlan = nil
        receiptChain = nil
        errorMessage = nil
        isLoading = true
        defer { isLoading = false }

        let payloads = Self.payloads(task: task)
        var failures: [String] = []

        do {
            policy = try await post(
                path: "api/orchestrator/contracts/execution-policy",
                payload: payloads.policy,
                as: AcrossExecutionPolicyContract.self
            )
        } catch {
            failures.append(error.localizedDescription)
        }

        if let comparisonPayload = payloads.comparison {
            do {
                comparison = try await post(
                    path: "api/orchestrator/runs/compare",
                    payload: comparisonPayload,
                    as: AcrossRunComparisonContract.self
                )
            } catch {
                failures.append(error.localizedDescription)
            }
        }

        do {
            replayPlan = try await post(
                path: "api/orchestrator/runs/replay-plan",
                payload: payloads.replay,
                as: AcrossReplayPlanContract.self
            )
        } catch {
            failures.append(error.localizedDescription)
        }

        do {
            receiptChain = try await get(
                path: "api/approval-receipts?limit=100",
                as: AcrossApprovalReceiptChain.self
            )
        } catch {
            failures.append(error.localizedDescription)
        }

        errorMessage = failures.first
    }

    var attemptLens: AcrossAttemptLens? {
        guard let comparison else { return nil }
        var changes = comparison.changes.checks.items.map { item in
            AcrossAttemptChange(
                id: "check:\(item.id)",
                title: item.id,
                state: Self.attemptState(item.classification),
                evidenceReference: comparison.comparisonSHA256
            )
        }
        changes.append(contentsOf: [
            AcrossAttemptChange(
                id: "verdict",
                title: "Verdict",
                state: Self.attemptState(
                    changed: comparison.changes.verdict.changed,
                    before: comparison.changes.verdict.before?.displayText,
                    after: comparison.changes.verdict.after?.displayText
                ),
                evidenceReference: comparison.comparisonSHA256
            ),
            AcrossAttemptChange(
                id: "evidence",
                title: "Evidence",
                state: comparison.changes.evidence.changed ? .introduced : .unchanged,
                evidenceReference: comparison.comparisonSHA256
            ),
            AcrossAttemptChange(
                id: "code_revision",
                title: "Code revision",
                state: comparison.changes.codeRevision.changed ? .introduced : .unchanged,
                evidenceReference: comparison.comparisonSHA256
            ),
            AcrossAttemptChange(
                id: "model_policy",
                title: "Model policy",
                state: comparison.changes.modelPolicy.changed ? .introduced : .unchanged,
                evidenceReference: comparison.comparisonSHA256
            ),
            AcrossAttemptChange(
                id: "budget",
                title: "Budget",
                state: comparison.changes.budget.changed ? .introduced : .unchanged,
                evidenceReference: comparison.comparisonSHA256
            ),
        ])
        return AcrossAttemptLens(
            baselineAttemptID: comparison.baseline.runID,
            currentAttemptID: comparison.candidate.runID,
            changes: changes
        )
    }

    func decisionMark(for task: TaskOrchestrationTaskDetail) -> AcrossDecisionMark? {
        let subjectHash = Self.sha256(task.taskId)
        guard let receipt = receiptChain?.receipts.first(where: { $0.subjectIDSHA256 == subjectHash }) else {
            return nil
        }
        return AcrossDecisionMark(
            targetID: task.taskId,
            scope: receipt.scope,
            proposer: receipt.proposerID,
            approver: receipt.approverID,
            reversible: nil,
            evidenceHash: receipt.receiptHash,
            state: receipt.integrityStatus == "verified" ? .confirmed : .blocked
        )
    }

    nonisolated static func payloads(task: TaskOrchestrationTaskDetail) -> RunTrustContractPayloads {
        let remediation = task.observability?.remediation
        let repairCount = remediation?.attemptsByRequirement.values.max() ?? 0
        let maxRepairs = remediation?.maxAttempts ?? 0
        let actions = task.subtasks.map(\.description)
        let externalEffects = task.taskTypes.filter {
            ["merge", "publish", "release", "sign", "payment", "production", "push"].contains($0.lowercased())
        }
        let budget: [String: Any] = [
            "max_model_calls": 0,
            "max_candidate_repairs": maxRepairs,
            "max_runtime_seconds": 0,
            "max_usd": 0,
            "candidate_repairs": repairCount,
        ]
        let policy: [String: Any] = [
            "run_id": task.taskId,
            "role": task.ownerAgent ?? "worker",
            "responsibility": task.description,
            "model_policy": [:],
            "budget": budget,
            "actions": actions,
            "external_side_effects": externalEffects,
        ]
        let current = snapshot(
            task: task,
            runID: "\(task.taskId):current",
            status: task.status,
            verdict: AcrossVisualResultFactory.make(task: task).verdict.rawValue,
            budget: budget
        )

        let fixRounds = task.waves.flatMap { $0.fixRounds ?? [] }.sorted { $0.roundNumber < $1.roundNumber }
        let comparison: [String: Any]?
        if let firstRound = fixRounds.first {
            let baseline: [String: Any] = [
                "run_id": "\(task.taskId):repair-\(firstRound.roundNumber)",
                "status": firstRound.status,
                "verdict": firstRound.status,
                "checks": ["repair_round_\(firstRound.roundNumber)": firstRound.status],
                "evidence_ids": [],
                "model_policy": [:],
                "budget": [
                    "max_candidate_repairs": maxRepairs,
                    "candidate_repairs": max(0, firstRound.roundNumber - 1),
                ],
                "actions": [firstRound.fixDescription],
            ]
            comparison = ["baseline": baseline, "candidate": current]
        } else {
            comparison = nil
        }

        let replay: [String: Any] = [
            "source": current,
            "external_side_effects": externalEffects,
        ]
        return RunTrustContractPayloads(policy: policy, comparison: comparison, replay: replay)
    }

    private nonisolated static func snapshot(
        task: TaskOrchestrationTaskDetail,
        runID: String,
        status: String,
        verdict: String,
        budget: [String: Any]
    ) -> [String: Any] {
        let checks = (task.observability?.qualityGates ?? []).reduce(into: [String: String]()) {
            values, gate in
            values[gate.gateId.isEmpty ? gate.adapterId : gate.gateId] = gate.status
        }
        let evidenceIDs = Array(Set(
            task.artifacts.map(\.id)
                + (task.observability?.qualityGates.map { $0.gateId.isEmpty ? $0.adapterId : $0.gateId } ?? [])
        )).sorted()
        return [
            "run_id": runID,
            "status": status,
            "verdict": verdict,
            "checks": checks,
            "evidence_ids": evidenceIDs,
            "model_policy": [:],
            "budget": budget,
            "actions": task.subtasks.map(\.description),
        ]
    }

    private func post<Response: Decodable>(
        path: String,
        payload: [String: Any],
        as type: Response.Type
    ) async throws -> Response {
        var request = URLRequest(url: backendBaseURL.appendingPathComponent(path))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
        return try await fetch(request, as: type)
    }

    private func get<Response: Decodable>(path: String, as type: Response.Type) async throws -> Response {
        var request = URLRequest(url: URL(string: path, relativeTo: backendBaseURL)!.absoluteURL)
        request.httpMethod = "GET"
        return try await fetch(request, as: type)
    }

    private func fetch<Response: Decodable>(_ request: URLRequest, as type: Response.Type) async throws -> Response {
        let (data, response) = try await dataLoader(request)
        try OperationsHTTP.validate(response, data: data)
        return try JSONDecoder().decode(type, from: data)
    }

    private nonisolated static func attemptState(_ classification: String) -> AcrossAttemptChangeState {
        switch classification {
        case "improved": return .improved
        case "regressed", "removed": return .regressed
        case "introduced", "changed": return .introduced
        default: return .unchanged
        }
    }

    private nonisolated static func attemptState(
        changed: Bool,
        before: String?,
        after: String?
    ) -> AcrossAttemptChangeState {
        guard changed else { return .unchanged }
        let passing = Set(["ready", "verified", "passed", "completed"])
        if let after, passing.contains(after.lowercased()) { return .improved }
        if let before, passing.contains(before.lowercased()) { return .regressed }
        return .introduced
    }

    private nonisolated static func sha256(_ value: String) -> String {
        SHA256.hash(data: Data(value.utf8)).map { String(format: "%02x", $0) }.joined()
    }
}
