import Foundation

struct TaskOrchestrationQualityHealth: Decodable {
    struct DeliveryQualityReport: Decodable {
        let missingRequired: [String]
        let failedConstraints: [String]

        enum CodingKeys: String, CodingKey {
            case missingRequired = "missing_required"
            case failedConstraints = "failed_constraints"
        }

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            missingRequired = (try? container.decode([String].self, forKey: .missingRequired)) ?? []
            failedConstraints = Self.decodeStrings(container, forKey: .failedConstraints)
        }

        private static func decodeStrings(
            _ container: KeyedDecodingContainer<CodingKeys>,
            forKey key: CodingKeys
        ) -> [String] {
            if let strings = try? container.decode([String].self, forKey: key) { return strings }
            if let values = try? container.decode([OperationsJSONValue].self, forKey: key) {
                return values.map(\.displayText)
            }
            return []
        }
    }

    let deliveryQuality: String?
    let orchestrationHealth: String?
    let qualityGate: String?
    let nextRepairAction: String?
    let manifestRequired: Int?
    let manifestAccepted: Int?
    let manifestMissing: Int?
    let terminalInconsistencies: [String]
    let activeRemediationSubtasks: [String]
    let deliveryQualityReport: DeliveryQualityReport?

    enum CodingKeys: String, CodingKey {
        case deliveryQuality = "delivery_quality"
        case orchestrationHealth = "orchestration_health"
        case qualityGate = "quality_gate"
        case nextRepairAction = "next_repair_action"
        case manifestRequired = "manifest_required"
        case manifestTotal = "manifest_total"
        case manifestAccepted = "manifest_accepted"
        case manifestMissing = "manifest_missing"
        case terminalInconsistencies = "terminal_inconsistencies"
        case activeRemediationSubtasks = "active_remediation_subtasks"
        case deliveryQualityReport = "delivery_quality_report"
    }

    init(
        deliveryQuality: String? = nil,
        orchestrationHealth: String? = nil,
        qualityGate: String? = nil,
        nextRepairAction: String? = nil,
        manifestRequired: Int? = nil,
        manifestAccepted: Int? = nil,
        manifestMissing: Int? = nil,
        terminalInconsistencies: [String] = [],
        activeRemediationSubtasks: [String] = [],
        deliveryQualityReport: DeliveryQualityReport? = nil
    ) {
        self.deliveryQuality = deliveryQuality
        self.orchestrationHealth = orchestrationHealth
        self.qualityGate = qualityGate
        self.nextRepairAction = nextRepairAction
        self.manifestRequired = manifestRequired
        self.manifestAccepted = manifestAccepted
        self.manifestMissing = manifestMissing
        self.terminalInconsistencies = terminalInconsistencies
        self.activeRemediationSubtasks = activeRemediationSubtasks
        self.deliveryQualityReport = deliveryQualityReport
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        deliveryQuality = try container.decodeIfPresent(String.self, forKey: .deliveryQuality)
        orchestrationHealth = try container.decodeIfPresent(String.self, forKey: .orchestrationHealth)
        qualityGate = try container.decodeIfPresent(String.self, forKey: .qualityGate)
        nextRepairAction = try container.decodeIfPresent(String.self, forKey: .nextRepairAction)
        manifestRequired = try container.decodeIfPresent(Int.self, forKey: .manifestRequired)
            ?? container.decodeIfPresent(Int.self, forKey: .manifestTotal)
        manifestAccepted = try container.decodeIfPresent(Int.self, forKey: .manifestAccepted)
        manifestMissing = try container.decodeIfPresent(Int.self, forKey: .manifestMissing)
        terminalInconsistencies = (try? container.decode([String].self, forKey: .terminalInconsistencies)) ?? []
        activeRemediationSubtasks = (try? container.decode([String].self, forKey: .activeRemediationSubtasks)) ?? []
        deliveryQualityReport = try container.decodeIfPresent(DeliveryQualityReport.self, forKey: .deliveryQualityReport)
    }
}

struct TaskOrchestrationDeliveryReport: Decodable {
    struct Consistency: Decodable {
        let terminalWithActiveRemediation: Bool?
        let hasMissingRequired: Bool?
        let hasFailedConstraints: Bool?

        enum CodingKeys: String, CodingKey {
            case terminalWithActiveRemediation = "terminal_with_active_remediation"
            case hasMissingRequired = "has_missing_required"
            case hasFailedConstraints = "has_failed_constraints"
        }
    }

    struct QualityReport: Decodable {
        let qualityGate: String?
        let canComplete: Bool?
        let generatedQualityScore: Int?
        let finalQualityScore: Int?
        let requiredFailedCount: Int?
        let manualRequiredCount: Int?
        let skippedRequiredCount: Int?

        enum CodingKeys: String, CodingKey {
            case qualityGate = "quality_gate"
            case canComplete = "can_complete"
            case generatedQualityScore = "generated_quality_score"
            case finalQualityScore = "final_quality_score"
            case requiredFailedCount = "required_failed_count"
            case manualRequiredCount = "manual_required_count"
            case skippedRequiredCount = "skipped_required_count"
        }
    }

    let qualityGate: String?
    let finalStatus: String?
    let summary: String?
    let requiredTotal: Int?
    let acceptedTotal: Int?
    let missingRequired: [String]
    let failedConstraints: [String]
    let nextAction: String?
    let consistency: Consistency?
    let qualityReport: QualityReport?

    enum CodingKeys: String, CodingKey {
        case qualityGate = "quality_gate"
        case finalStatus = "final_status"
        case summary
        case requiredTotal = "required_total"
        case acceptedTotal = "accepted_total"
        case missingRequired = "missing_required"
        case failedConstraints = "failed_constraints"
        case nextAction = "next_action"
        case consistency
        case qualityReport = "quality_report"
    }

    init(
        qualityGate: String? = nil,
        finalStatus: String? = nil,
        summary: String? = nil,
        requiredTotal: Int? = nil,
        acceptedTotal: Int? = nil,
        missingRequired: [String] = [],
        failedConstraints: [String] = [],
        nextAction: String? = nil,
        consistency: Consistency? = nil,
        qualityReport: QualityReport? = nil
    ) {
        self.qualityGate = qualityGate
        self.finalStatus = finalStatus
        self.summary = summary
        self.requiredTotal = requiredTotal
        self.acceptedTotal = acceptedTotal
        self.missingRequired = missingRequired
        self.failedConstraints = failedConstraints
        self.nextAction = nextAction
        self.consistency = consistency
        self.qualityReport = qualityReport
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        qualityGate = try container.decodeIfPresent(String.self, forKey: .qualityGate)
        finalStatus = try container.decodeIfPresent(String.self, forKey: .finalStatus)
        summary = try container.decodeIfPresent(String.self, forKey: .summary)
        requiredTotal = try container.decodeIfPresent(Int.self, forKey: .requiredTotal)
        acceptedTotal = try container.decodeIfPresent(Int.self, forKey: .acceptedTotal)
        missingRequired = (try? container.decode([String].self, forKey: .missingRequired)) ?? []
        if let strings = try? container.decode([String].self, forKey: .failedConstraints) {
            failedConstraints = strings
        } else if let values = try? container.decode([OperationsJSONValue].self, forKey: .failedConstraints) {
            failedConstraints = values.map(\.displayText)
        } else {
            failedConstraints = []
        }
        nextAction = try container.decodeIfPresent(String.self, forKey: .nextAction)
        consistency = try container.decodeIfPresent(Consistency.self, forKey: .consistency)
        qualityReport = try container.decodeIfPresent(QualityReport.self, forKey: .qualityReport)
    }
}

struct TaskOrchestrationTaskObservability: Decodable {
    struct TimelineEvent: Decodable, Identifiable {
        let kind: String
        let label: String?
        let status: String?
        let agentId: String?
        let subtaskId: String?
        let gateId: String?
        let waveNumber: Int?
        let summary: String?

        var id: String {
            [kind, agentId, subtaskId, gateId, waveNumber.map(String.init)]
                .compactMap { $0 }
                .joined(separator: ":")
        }

        enum CodingKeys: String, CodingKey {
            case kind, label, status, summary
            case agentId = "agent_id"
            case subtaskId = "subtask_id"
            case gateId = "gate_id"
            case waveNumber = "wave_number"
        }
    }

    struct QualityGate: Decodable, Identifiable {
        let gateId: String
        let adapterId: String
        let status: String
        let required: Bool
        let summary: String?

        var id: String { gateId.isEmpty ? adapterId : gateId }

        enum CodingKeys: String, CodingKey {
            case gateId = "gate_id"
            case adapterId = "adapter_id"
            case status, required, summary
        }
    }

    struct AgentMix: Decodable {
        let actualAgents: [String]
        let localAgents: [String]
        let cloudAgents: [String]

        enum CodingKeys: String, CodingKey {
            case actualAgents = "actual_agents"
            case localAgents = "local_agents"
            case cloudAgents = "cloud_agents"
        }
    }

    struct Remediation: Decodable {
        let attempted: Bool
        let attemptsByRequirement: [String: Int]
        let maxAttempts: Int?
        let deterministicRepairAttempted: Bool

        enum CodingKeys: String, CodingKey {
            case attempted
            case attemptsByRequirement = "attempts_by_requirement"
            case maxAttempts = "max_attempts"
            case deterministicRepairAttempted = "deterministic_repair_attempted"
        }
    }

    let timeline: [TimelineEvent]
    let qualityGates: [QualityGate]
    let agentMix: AgentMix?
    let remediation: Remediation?
    let qualityScore: Int?

    enum CodingKeys: String, CodingKey {
        case timeline
        case qualityGates = "quality_gates"
        case agentMix = "agent_mix"
        case remediation
        case qualityScore = "quality_score"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        timeline = (try? container.decode([TimelineEvent].self, forKey: .timeline)) ?? []
        qualityGates = (try? container.decode([QualityGate].self, forKey: .qualityGates)) ?? []
        agentMix = try container.decodeIfPresent(AgentMix.self, forKey: .agentMix)
        remediation = try container.decodeIfPresent(Remediation.self, forKey: .remediation)
        qualityScore = try container.decodeIfPresent(Int.self, forKey: .qualityScore)
    }
}
