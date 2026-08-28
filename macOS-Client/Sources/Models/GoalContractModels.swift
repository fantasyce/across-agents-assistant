import Foundation

enum GoalProjectionValue: Equatable, Hashable, Codable {
    case known(String)
    case unknown(String)

    private static let knownValues: Set<String> = [
        "confirmed", "needs_confirmation", "not_started", "running", "finished", "failed", "cancelled",
        "none", "partial", "satisfied", "stale", "pending", "passed", "waived", "not_required",
        "change_pending", "valid", "revalidation_required", "completed", "waiting_for_decision",
        "waiting_for_review", "waiting_for_evidence", "goal_needs_confirmation", "dependency_unsatisfied",
        "criterion_evidence_missing", "criterion_evidence_stale", "criterion_evidence_failed", "review_pending",
        "review_failed", "decision_pending", "lease_active", "execution_failed", "execution_cancelled",
        "execution_not_terminal"
    ]

    init(rawValue: String) {
        self = Self.knownValues.contains(rawValue) ? .known(rawValue) : .unknown(rawValue)
    }

    var rawValue: String {
        switch self {
        case .known(let value), .unknown(let value): value
        }
    }

    init(from decoder: Decoder) throws {
        self.init(rawValue: try decoder.singleValueContainer().decode(String.self))
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(rawValue)
    }
}

struct GoalContractEnvelope: Decodable, Equatable {
    let contract: GoalContract
    let projection: GoalStateProjection
    let pendingProposals: [GoalChangeProposal]
    let evidenceBindings: [GoalEvidenceBinding]
    let invalidations: [GoalInvalidation]

    enum CodingKeys: String, CodingKey {
        case contract, projection
        case pendingProposals = "pending_proposals"
        case evidenceBindings = "evidence_bindings"
        case invalidations
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        contract = try container.decode(GoalContract.self, forKey: .contract)
        projection = try container.decode(GoalStateProjection.self, forKey: .projection)
        pendingProposals = try container.decodeIfPresent([GoalChangeProposal].self, forKey: .pendingProposals) ?? []
        evidenceBindings = try container.decodeIfPresent([GoalEvidenceBinding].self, forKey: .evidenceBindings) ?? []
        invalidations = try container.decodeIfPresent([GoalInvalidation].self, forKey: .invalidations) ?? []
    }
}

struct GoalContract: Decodable, Equatable {
    let schemaVersion: String
    let goalId: String
    let revision: Int
    let taskId: String
    let statement: String
    let successOutcome: String
    let scope: GoalScope
    let acceptanceCriteria: [GoalAcceptanceCriterion]
    let dependencies: [String]
    let executionProfile: String
    let source: String
    let confirmedBy: String?
    let confirmedAt: String?
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case goalId = "goal_id"
        case revision
        case taskId = "task_id"
        case statement
        case successOutcome = "success_outcome"
        case scope
        case acceptanceCriteria = "acceptance_criteria"
        case dependencies
        case executionProfile = "execution_profile"
        case source
        case confirmedBy = "confirmed_by"
        case confirmedAt = "confirmed_at"
        case createdAt = "created_at"
    }
}

struct GoalScope: Decodable, Equatable {
    let includes: [String]
    let excludes: [String]
}

struct GoalAcceptanceCriterion: Decodable, Equatable, Identifiable {
    let criterionId: String
    let description: String
    let required: Bool
    let validatorKind: String
    let reviewPolicy: String
    let source: String
    var id: String { criterionId }

    enum CodingKeys: String, CodingKey {
        case criterionId = "criterion_id"
        case description, required
        case validatorKind = "validator_kind"
        case reviewPolicy = "review_policy"
        case source
    }
}

struct GoalStateProjection: Decodable, Equatable {
    let schemaVersion: String
    let goalId: String
    let goalRevision: Int
    let taskId: String
    let definitionState: GoalProjectionValue
    let executionState: GoalProjectionValue
    let evidenceState: GoalProjectionValue
    let reviewState: GoalProjectionValue
    let decisionState: GoalProjectionValue
    let validityState: GoalProjectionValue
    let criterionCoverage: [GoalCriterionCoverage]
    let reasonCodes: [GoalProjectionValue]
    let isComplete: Bool
    let displayState: GoalProjectionValue
    let authority: GoalProjectionAuthority

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case goalId = "goal_id"
        case goalRevision = "goal_revision"
        case taskId = "task_id"
        case definitionState = "definition_state"
        case executionState = "execution_state"
        case evidenceState = "evidence_state"
        case reviewState = "review_state"
        case decisionState = "decision_state"
        case validityState = "validity_state"
        case criterionCoverage = "criterion_coverage"
        case reasonCodes = "reason_codes"
        case isComplete = "is_complete"
        case displayState = "display_state"
        case authority
    }
}

struct GoalCriterionCoverage: Decodable, Equatable, Identifiable {
    let criterionId: String
    let required: Bool
    let evidenceState: GoalProjectionValue
    let reviewState: GoalProjectionValue
    let satisfied: Bool
    var id: String { criterionId }

    enum CodingKeys: String, CodingKey {
        case criterionId = "criterion_id"
        case required
        case evidenceState = "evidence_state"
        case reviewState = "review_state"
        case satisfied
    }
}

struct GoalProjectionAuthority: Decodable, Equatable {
    let goal: String
    let execution: String
    let evidence: String
    let decisions: String
}

struct GoalChangeProposal: Decodable, Equatable, Identifiable {
    let proposalId: String
    let goalId: String
    let baseGoalRevision: Int
    let proposedBy: String
    let reason: String
    let operations: [GoalProposalOperation]
    let impactSummary: GoalProposalImpactSummary
    let decisionState: String
    let createdAt: String
    var id: String { proposalId }

    enum CodingKeys: String, CodingKey {
        case proposalId = "proposal_id"
        case goalId = "goal_id"
        case baseGoalRevision = "base_goal_revision"
        case proposedBy = "proposed_by"
        case reason
        case operations
        case impactSummary = "impact_summary"
        case decisionState = "decision_state"
        case createdAt = "created_at"
    }
}

struct GoalProposalOperation: Decodable, Equatable, Identifiable {
    let op: String
    let path: String
    var id: String { "\(op):\(path)" }
}

struct GoalProposalImpactSummary: Decodable, Equatable {
    let goalIds: [String]
    let criterionIds: [String]
    let evidenceIds: [String]
    let requiresRevalidation: Bool

    enum CodingKeys: String, CodingKey {
        case goalIds = "goal_ids"
        case criterionIds = "criterion_ids"
        case evidenceIds = "evidence_ids"
        case requiresRevalidation = "requires_revalidation"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        goalIds = try container.decodeIfPresent([String].self, forKey: .goalIds) ?? []
        criterionIds = try container.decodeIfPresent([String].self, forKey: .criterionIds) ?? []
        evidenceIds = try container.decodeIfPresent([String].self, forKey: .evidenceIds) ?? []
        requiresRevalidation = try container.decodeIfPresent(Bool.self, forKey: .requiresRevalidation) ?? false
    }
}

struct GoalInvalidation: Decodable, Equatable, Identifiable {
    let invalidationId: String
    let goalId: String
    let fromRevision: Int
    let toRevision: Int?
    let criterionIds: [String]
    let reason: String
    let state: String
    var id: String { invalidationId }

    enum CodingKeys: String, CodingKey {
        case invalidationId = "invalidation_id"
        case goalId = "goal_id"
        case fromRevision = "from_revision"
        case toRevision = "to_revision"
        case criterionIds = "criterion_ids"
        case reason, state
    }
}

struct GoalEvidenceBinding: Decodable, Equatable, Identifiable {
    let evidenceId: String
    let goalRevision: Int
    let criterionIds: [String]
    let validator: GoalEvidenceValidator?
    let verdict: String
    let trustState: String
    var id: String { evidenceId }

    enum CodingKeys: String, CodingKey {
        case evidenceId = "evidence_id"
        case goalRevision = "goal_revision"
        case criterionIds = "criterion_ids"
        case validator, verdict
        case trustState = "trust_state"
    }
}

struct GoalEvidenceValidator: Decodable, Equatable {
    let validatorId: String
    let authority: String

    enum CodingKeys: String, CodingKey {
        case validatorId = "validator_id"
        case authority
    }
}

struct GoalProposalDecisionRequest: Encodable, Equatable {
    let decision: String
    let expectedRevision: Int
    let operationIndexes: [Int]
    let approverId: String
    let idempotencyKey: String

    enum CodingKeys: String, CodingKey {
        case decision
        case expectedRevision = "expected_revision"
        case operationIndexes = "operation_indexes"
        case approverId = "approver_id"
        case idempotencyKey = "idempotency_key"
    }
}

struct GoalRevalidationRequest: Encodable, Equatable {
    let expectedRevision: Int
    let criterionIds: [String]
    let reason: String
    let idempotencyKey: String

    enum CodingKeys: String, CodingKey {
        case expectedRevision = "expected_revision"
        case criterionIds = "criterion_ids"
        case reason
        case idempotencyKey = "idempotency_key"
    }
}

enum GoalTaskDetailState: Equatable {
    case loading
    case legacyEmpty
    case active(GoalProjectionValue)
    case stale
    case decisionRequired
    case error(String)
    case completed
}

enum GoalProjectionReducer {
    static func reduce(
        _ envelope: GoalContractEnvelope?,
        loading: Bool,
        error: String?
    ) -> GoalTaskDetailState {
        if loading { return .loading }
        if let error { return .error(error) }
        guard let envelope else { return .legacyEmpty }

        let projection = envelope.projection
        if projection.isComplete { return .completed }
        if projection.validityState.rawValue == "revalidation_required"
            || projection.evidenceState.rawValue == "stale" {
            return .stale
        }
        if projection.decisionState.rawValue == "change_pending"
            || projection.reasonCodes.contains(where: { $0.rawValue == "decision_pending" })
            || envelope.pendingProposals.contains(where: { $0.decisionState == "pending" }) {
            return .decisionRequired
        }
        if projection.evidenceState.rawValue == "failed" || projection.reviewState.rawValue == "failed" {
            return .error(projection.reasonCodes.first?.rawValue ?? "goal_validation_failed")
        }
        return .active(projection.displayState)
    }
}
