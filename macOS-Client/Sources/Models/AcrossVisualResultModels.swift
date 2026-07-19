import Foundation

enum AcrossEvidenceState: String, Codable, CaseIterable, Equatable {
    case confirmed
    case partial
    case missing
    case blocked

    var accessibilityKey: String { "result.state.\(rawValue)" }
}

enum AcrossTrustDimension: String, Codable, CaseIterable, Equatable, Identifiable {
    case outcome
    case proof
    case safety
    case humanControl = "human_control"

    var id: String { rawValue }
    var titleKey: String { "result.trust.\(rawValue)" }
    var systemImage: String {
        switch self {
        case .outcome: return "checkmark.seal"
        case .proof: return "doc.text.magnifyingglass"
        case .safety: return "shield.lefthalf.filled"
        case .humanControl: return "hand.raised"
        }
    }
}

struct AcrossTrustSector: Codable, Equatable, Identifiable {
    let dimension: AcrossTrustDimension
    let state: AcrossEvidenceState

    var id: AcrossTrustDimension { dimension }
}

struct AcrossTrustCompass: Codable, Equatable {
    let sectors: [AcrossTrustSector]

    init(outcome: AcrossEvidenceState, proof: AcrossEvidenceState, safety: AcrossEvidenceState, humanControl: AcrossEvidenceState) {
        sectors = [
            AcrossTrustSector(dimension: .outcome, state: outcome),
            AcrossTrustSector(dimension: .proof, state: proof),
            AcrossTrustSector(dimension: .safety, state: safety),
            AcrossTrustSector(dimension: .humanControl, state: humanControl),
        ]
    }

    func state(for dimension: AcrossTrustDimension) -> AcrossEvidenceState {
        sectors.first(where: { $0.dimension == dimension })?.state ?? .missing
    }
}

enum AcrossRunVerdict: String, Codable, Equatable {
    case ready
    case needsReview = "needs_review"
    case blocked
    case inProgress = "in_progress"
    case cancelled

    var titleKey: String { "result.verdict.\(rawValue)" }
    var systemImage: String {
        switch self {
        case .ready: return "checkmark.seal.fill"
        case .needsReview: return "hand.raised.fill"
        case .blocked: return "exclamationmark.octagon.fill"
        case .inProgress: return "circle.dotted.circle.fill"
        case .cancelled: return "xmark.circle.fill"
        }
    }
}

enum AcrossLoopStage: String, Codable, CaseIterable, Equatable, Identifiable {
    case goal
    case prepare
    case execute
    case verify
    case decide
    case remember

    var id: String { rawValue }
    var titleKey: String { "result.loop.\(rawValue)" }
}

enum AcrossLoopStageState: String, Codable, Equatable {
    case pending
    case active
    case complete
    case blocked
}

struct AcrossLoopTrailStep: Codable, Equatable, Identifiable {
    let stage: AcrossLoopStage
    let state: AcrossLoopStageState
    var id: AcrossLoopStage { stage }
}

enum AcrossEvidenceNodeKind: String, Codable, CaseIterable, Equatable, Identifiable {
    case source
    case action
    case check
    case artifact
    case approval
    case memory

    var id: String { rawValue }
    var titleKey: String { "result.evidence.\(rawValue)" }
    var systemImage: String {
        switch self {
        case .source: return "folder"
        case .action: return "bolt"
        case .check: return "checkmark.shield"
        case .artifact: return "shippingbox"
        case .approval: return "person.crop.circle.badge.checkmark"
        case .memory: return "memorychip"
        }
    }
}

struct AcrossEvidenceNode: Codable, Equatable, Identifiable {
    let kind: AcrossEvidenceNodeKind
    let state: AcrossEvidenceState
    let referenceCount: Int

    var id: AcrossEvidenceNodeKind { kind }
}

struct AcrossEvidenceRelation: Codable, Equatable, Identifiable {
    let from: AcrossEvidenceNodeKind
    let to: AcrossEvidenceNodeKind
    let relation: String

    var id: String { "\(from.rawValue):\(relation):\(to.rawValue)" }
}

struct AcrossEvidenceConstellation: Codable, Equatable {
    let nodes: [AcrossEvidenceNode]
    let relations: [AcrossEvidenceRelation]
}

enum AcrossAttentionPriority: String, Codable, Equatable {
    case actNow = "act_now"
    case inspectSoon = "inspect_soon"
    case contextOnly = "context_only"

    var titleKey: String { "result.attention.\(rawValue)" }
}

struct AcrossAttentionItem: Codable, Equatable, Identifiable {
    let id: String
    let priority: AcrossAttentionPriority
    let titleKey: String
    let detail: String?
}

enum AcrossAttemptChangeState: String, Codable, Equatable {
    case improved
    case unchanged
    case regressed
    case introduced
}

struct AcrossAttemptChange: Codable, Equatable, Identifiable {
    let id: String
    let title: String
    let state: AcrossAttemptChangeState
    let evidenceReference: String?
}

struct AcrossAttemptLens: Codable, Equatable {
    let baselineAttemptID: String
    let currentAttemptID: String
    let changes: [AcrossAttemptChange]
}

struct AcrossDecisionMark: Codable, Equatable {
    let targetID: String
    let scope: String
    let proposer: String?
    let approver: String?
    let reversible: Bool?
    let evidenceHash: String?
    let state: AcrossEvidenceState
}

enum AcrossNextAction: String, Codable, Equatable {
    case wait
    case inspectEvidence = "inspect_evidence"
    case reviewDecision = "review_decision"
    case repair
    case retry
    case startAnother = "start_another"

    var titleKey: String { "result.next.\(rawValue)" }
    var systemImage: String {
        switch self {
        case .wait: return "clock"
        case .inspectEvidence: return "doc.text.magnifyingglass"
        case .reviewDecision: return "person.crop.circle.badge.questionmark"
        case .repair: return "wrench.and.screwdriver"
        case .retry: return "arrow.clockwise"
        case .startAnother: return "plus.circle"
        }
    }
}

struct AcrossVisualResultContract: Codable, Equatable {
    static let currentSchemaVersion = 1

    let schemaVersion: Int
    let taskID: String
    let verdict: AcrossRunVerdict
    let trustCompass: AcrossTrustCompass
    let loopTrail: [AcrossLoopTrailStep]
    let evidenceConstellation: AcrossEvidenceConstellation
    let attentionStack: [AcrossAttentionItem]
    let attemptLens: AcrossAttemptLens?
    let decisionMark: AcrossDecisionMark?
    let nextAction: AcrossNextAction

    init(
        schemaVersion: Int = Self.currentSchemaVersion,
        taskID: String,
        verdict: AcrossRunVerdict,
        trustCompass: AcrossTrustCompass,
        loopTrail: [AcrossLoopTrailStep],
        evidenceConstellation: AcrossEvidenceConstellation,
        attentionStack: [AcrossAttentionItem],
        attemptLens: AcrossAttemptLens? = nil,
        decisionMark: AcrossDecisionMark? = nil,
        nextAction: AcrossNextAction
    ) {
        self.schemaVersion = schemaVersion
        self.taskID = taskID
        self.verdict = verdict
        self.trustCompass = trustCompass
        self.loopTrail = loopTrail
        self.evidenceConstellation = evidenceConstellation
        self.attentionStack = attentionStack
        self.attemptLens = attemptLens
        self.decisionMark = decisionMark
        self.nextAction = nextAction
    }
}

struct AcrossVisualResultFallback: Equatable {
    let verdict: AcrossRunVerdict
    let titleKey: String
    let evidenceReference: String?
}

enum AcrossVisualResultDecodeResult: Equatable {
    case result(AcrossVisualResultContract)
    case fallback(AcrossVisualResultFallback)

    static func decode(_ data: Data) -> AcrossVisualResultDecodeResult {
        let version = (try? JSONSerialization.jsonObject(with: data))
            .flatMap { $0 as? [String: Any] }?["schemaVersion"] as? Int
        guard version == AcrossVisualResultContract.currentSchemaVersion,
              let contract = try? JSONDecoder().decode(AcrossVisualResultContract.self, from: data) else {
            return .fallback(AcrossVisualResultFallback(
                verdict: .needsReview,
                titleKey: "result.fallback.unavailable",
                evidenceReference: nil
            ))
        }
        return .result(contract)
    }
}

enum AcrossVisualResultFactory {
    static func make(task: TaskOrchestrationTaskDetail) -> AcrossVisualResultContract {
        let outcome = outcomeState(task)
        let proof = proofState(task)
        let safety = safetyState(task)
        let humanControl = humanControlState(task)
        let compass = AcrossTrustCompass(
            outcome: outcome,
            proof: proof,
            safety: safety,
            humanControl: humanControl
        )
        let verdict = verdict(task, compass: compass)
        return AcrossVisualResultContract(
            taskID: task.taskId,
            verdict: verdict,
            trustCompass: compass,
            loopTrail: loopTrail(task),
            evidenceConstellation: evidenceConstellation(task, compass: compass),
            attentionStack: attentionStack(task, compass: compass),
            decisionMark: decisionMark(task, humanControl: humanControl),
            nextAction: nextAction(task, verdict: verdict)
        )
    }

    private static func outcomeState(_ task: TaskOrchestrationTaskDetail) -> AcrossEvidenceState {
        switch task.status {
        case "completed": return .confirmed
        case "completed_with_failures": return .partial
        case "failed": return .blocked
        case "cancelled": return .blocked
        case "running", "decomposing", "pending", "paused": return .partial
        default: return .missing
        }
    }

    private static func proofState(_ task: TaskOrchestrationTaskDetail) -> AcrossEvidenceState {
        let gates = task.observability?.qualityGates ?? []
        let requiredGates = gates.filter(\.required)
        if hasBlockingQualityStatus(task) { return .blocked }
        if requiredGates.contains(where: { normalized($0.status).contains("fail") }) {
            return .blocked
        }
        let failed = qualityIssues(task)
        if !failed.isEmpty { return .blocked }
        let passedRequired = !requiredGates.isEmpty && requiredGates.allSatisfy {
            ["pass", "passed", "complete", "completed"].contains(normalized($0.status))
        }
        if passedRequired && !task.artifacts.isEmpty { return .confirmed }
        if !gates.isEmpty || !task.artifacts.isEmpty || task.deliveryReport != nil || task.qualityHealth != nil {
            return .partial
        }
        return .missing
    }

    private static func safetyState(_ task: TaskOrchestrationTaskDetail) -> AcrossEvidenceState {
        if hasBlockingQualityStatus(task) { return .blocked }
        if !qualityIssues(task).isEmpty { return .blocked }
        if let report = task.deliveryReport?.qualityReport,
           (report.manualRequiredCount ?? 0) > 0 || (report.skippedRequiredCount ?? 0) > 0 {
            return .partial
        }
        switch task.status {
        case "completed": return task.qualityHealth == nil && task.deliveryReport == nil ? .missing : .confirmed
        case "failed", "completed_with_failures": return .partial
        case "cancelled": return .confirmed
        default: return .partial
        }
    }

    private static func humanControlState(_ task: TaskOrchestrationTaskDetail) -> AcrossEvidenceState {
        switch normalized(task.reviewStatus) {
        case "accepted", "approved", "rejected": return .confirmed
        case "pending", "waiting", "needsreview": return .partial
        default: return .missing
        }
    }

    private static func verdict(_ task: TaskOrchestrationTaskDetail, compass: AcrossTrustCompass) -> AcrossRunVerdict {
        if task.status == "cancelled" { return .cancelled }
        if task.status == "failed" { return .blocked }
        // Quality evidence can be partial or temporarily negative while a run
        // is still producing its final gates.  A non-terminal task must remain
        // visibly in progress; only a terminal result may be presented as
        // blocked and actionable.
        if !["completed", "completed_with_failures"].contains(task.status) { return .inProgress }
        let reviewStatus = normalized(task.reviewStatus)
        if reviewStatus == "rejected" { return .blocked }
        if compass.sectors.contains(where: { $0.state == .blocked }) { return .blocked }
        // A recorded human acceptance is the terminal review decision. Missing
        // or partial auxiliary evidence may still be inspected, but it must not
        // put an accepted result back into an "awaiting confirmation" state.
        if ["accepted", "approved"].contains(reviewStatus) { return .ready }
        if compass.sectors.allSatisfy({ $0.state == .confirmed }) { return .ready }
        return .needsReview
    }

    private static func nextAction(_ task: TaskOrchestrationTaskDetail, verdict: AcrossRunVerdict) -> AcrossNextAction {
        switch verdict {
        case .ready: return .inspectEvidence
        case .needsReview:
            return normalized(task.reviewStatus) == "pending" ? .reviewDecision : .inspectEvidence
        case .blocked: return task.status == "failed" ? .repair : .retry
        case .inProgress: return .wait
        case .cancelled: return .startAnother
        }
    }

    private static func loopTrail(_ task: TaskOrchestrationTaskDetail) -> [AcrossLoopTrailStep] {
        let terminal = ["completed", "completed_with_failures", "failed", "cancelled"].contains(task.status)
        let failed = task.status == "failed"
        let hasExecution = !task.subtasks.isEmpty || !task.waves.isEmpty || terminal
        let hasVerification = task.deliveryReport != nil || task.qualityHealth != nil || !(task.observability?.qualityGates.isEmpty ?? true)
        let reviewed = ["accepted", "approved", "rejected"].contains(normalized(task.reviewStatus))
        return [
            AcrossLoopTrailStep(stage: .goal, state: .complete),
            AcrossLoopTrailStep(stage: .prepare, state: hasExecution ? .complete : .active),
            AcrossLoopTrailStep(stage: .execute, state: failed ? .blocked : (terminal ? .complete : (hasExecution ? .active : .pending))),
            AcrossLoopTrailStep(stage: .verify, state: failed && hasVerification ? .blocked : (hasVerification ? (terminal ? .complete : .active) : .pending)),
            AcrossLoopTrailStep(stage: .decide, state: reviewed ? .complete : (terminal ? .active : .pending)),
            AcrossLoopTrailStep(stage: .remember, state: .pending),
        ]
    }

    private static func evidenceConstellation(
        _ task: TaskOrchestrationTaskDetail,
        compass: AcrossTrustCompass
    ) -> AcrossEvidenceConstellation {
        let actionCount = max(task.subtasks.count, task.observability?.timeline.count ?? 0)
        let checkCount = task.observability?.qualityGates.count ?? 0
        let approvalCount = ["accepted", "approved", "rejected"].contains(normalized(task.reviewStatus)) ? 1 : 0
        let nodes = [
            AcrossEvidenceNode(kind: .source, state: task.projectDir == nil ? .missing : .confirmed, referenceCount: task.projectDir == nil ? 0 : 1),
            AcrossEvidenceNode(kind: .action, state: actionCount > 0 ? .confirmed : .missing, referenceCount: actionCount),
            AcrossEvidenceNode(kind: .check, state: compass.state(for: .proof), referenceCount: checkCount),
            AcrossEvidenceNode(kind: .artifact, state: task.artifacts.isEmpty ? .missing : .confirmed, referenceCount: task.artifacts.count),
            AcrossEvidenceNode(kind: .approval, state: compass.state(for: .humanControl), referenceCount: approvalCount),
            AcrossEvidenceNode(kind: .memory, state: .missing, referenceCount: 0),
        ]
        let present = Set(nodes.filter { $0.referenceCount > 0 }.map(\.kind))
        let ordered: [AcrossEvidenceNodeKind] = [.source, .action, .check, .artifact, .approval, .memory]
        let relations = Array(zip(ordered, ordered.dropFirst())).compactMap { pair -> AcrossEvidenceRelation? in
            let (from, to) = pair
            guard present.contains(from), present.contains(to) else { return nil }
            return AcrossEvidenceRelation(from: from, to: to, relation: "supports")
        }
        return AcrossEvidenceConstellation(nodes: nodes, relations: relations)
    }

    private static func attentionStack(
        _ task: TaskOrchestrationTaskDetail,
        compass: AcrossTrustCompass
    ) -> [AcrossAttentionItem] {
        var items: [AcrossAttentionItem] = []
        if compass.sectors.contains(where: { $0.state == .blocked }) {
            items.append(AcrossAttentionItem(id: "blocked", priority: .actNow, titleKey: "result.attention.resolveBlocked", detail: qualityIssues(task).first))
        }
        if normalized(task.reviewStatus) == "pending" && ["completed", "completed_with_failures"].contains(task.status) {
            items.append(AcrossAttentionItem(id: "review", priority: .inspectSoon, titleKey: "result.attention.reviewDelivery", detail: nil))
        }
        if compass.state(for: .proof) == .missing {
            items.append(AcrossAttentionItem(id: "proof", priority: .inspectSoon, titleKey: "result.attention.addProof", detail: nil))
        }
        if items.isEmpty {
            items.append(AcrossAttentionItem(id: "context", priority: .contextOnly, titleKey: "result.attention.noAction", detail: nil))
        }
        return items
    }

    private static func decisionMark(
        _ task: TaskOrchestrationTaskDetail,
        humanControl: AcrossEvidenceState
    ) -> AcrossDecisionMark? {
        guard ["completed", "completed_with_failures", "failed", "cancelled"].contains(task.status) else { return nil }
        return AcrossDecisionMark(
            targetID: task.taskId,
            scope: "task_delivery",
            proposer: task.ownerAgent,
            approver: nil,
            reversible: nil,
            evidenceHash: nil,
            state: humanControl == .confirmed ? .partial : humanControl
        )
    }

    private static func qualityIssues(_ task: TaskOrchestrationTaskDetail) -> [String] {
        var values = task.deliveryReport?.missingRequired ?? []
        values += task.deliveryReport?.failedConstraints ?? []
        values += task.qualityHealth?.deliveryQualityReport?.missingRequired ?? []
        values += task.qualityHealth?.deliveryQualityReport?.failedConstraints ?? []
        values += task.qualityHealth?.terminalInconsistencies ?? []
        return values
    }

    private static func hasBlockingQualityStatus(_ task: TaskOrchestrationTaskDetail) -> Bool {
        let values = [
            task.deliveryReport?.qualityGate,
            task.deliveryReport?.finalStatus,
            task.qualityHealth?.deliveryQuality,
            task.qualityHealth?.orchestrationHealth,
            task.qualityHealth?.qualityGate,
        ]
        let blocking = ["failed", "failure", "blocked", "error", "inconsistent"]
        return values.compactMap { $0 }.contains { value in
            blocking.contains(where: { normalized(value).contains($0) })
        }
    }

    private static func normalized(_ value: String) -> String {
        value.lowercased().filter(\.isLetter)
    }
}

struct AcrossTaskResultDecision {
    let isTerminal: Bool
    let isAccepted: Bool
    let isRejected: Bool
    let canAccept: Bool
    let canInspectEvidence: Bool

    init(task: TaskOrchestrationTaskDetail) {
        let status = task.status.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let review = task.reviewStatus
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .replacingOccurrences(of: "_", with: "")
            .replacingOccurrences(of: "-", with: "")
            .replacingOccurrences(of: " ", with: "")
        isTerminal = ["completed", "completed_with_failures", "failed", "cancelled"].contains(status)
        isAccepted = ["accepted", "approved"].contains(review)
        isRejected = review == "rejected"
        canAccept = status == "completed" && !isAccepted && !isRejected
        canInspectEvidence = ["completed", "completed_with_failures"].contains(status)
            || task.qualityHealth != nil
            || task.deliveryReport != nil
    }
}
