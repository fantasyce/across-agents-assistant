import Foundation

enum TaskOrchestrationDeliveryTaskType: String, CaseIterable, Identifiable {
    case functional
    case artifact

    var id: String { rawValue }

    var title: String {
        switch self {
        case .functional: return "Functional"
        case .artifact: return "Artifact"
        }
    }

    var subtitle: String {
        switch self {
        case .functional: return "Validate behavior, tests, and runtime evidence"
        case .artifact: return "Validate deliverables, files, and content"
        }
    }
}

struct TaskOrchestrationAutoTaskSubmitResponse: Decodable {
    let taskId: String?
    let status: String?
    let message: String?
    let implementation: String?
    let externalTask: Bool?

    enum CodingKeys: String, CodingKey {
        case taskId = "task_id"
        case status
        case message
        case implementation
        case externalTask = "external_task"
    }
}

struct TaskOrchestrationTaskSummary: Identifiable, Codable {
    let taskId: String
    let description: String
    let status: String
    let progress: Double
    let completedCount: Int
    let totalCount: Int
    let projectDir: String?
    let ownerAgent: String?
    let deliveryMode: String?
    let externalTask: Bool

    var id: String { taskId }

    enum CodingKeys: String, CodingKey {
        case taskId = "task_id"
        case description
        case status
        case progress
        case completedCount = "completed_count"
        case totalCount = "total_count"
        case projectDir = "project_dir"
        case ownerAgent = "owner_agent"
        case deliveryMode = "delivery_mode"
        case externalTask = "external_task"
    }

    init(taskId: String, description: String, status: String, progress: Double, completedCount: Int, totalCount: Int, projectDir: String? = nil, ownerAgent: String? = nil, deliveryMode: String? = nil, externalTask: Bool = false) {
        self.taskId = taskId
        self.description = description
        self.status = status
        self.progress = progress
        self.completedCount = completedCount
        self.totalCount = totalCount
        self.projectDir = projectDir
        self.ownerAgent = ownerAgent
        self.deliveryMode = deliveryMode
        self.externalTask = externalTask
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        taskId = try container.decode(String.self, forKey: .taskId)
        description = try container.decode(String.self, forKey: .description)
        status = try container.decode(String.self, forKey: .status)
        progress = try container.decodeIfPresent(Double.self, forKey: .progress) ?? 0
        completedCount = try container.decodeIfPresent(Int.self, forKey: .completedCount) ?? 0
        totalCount = try container.decodeIfPresent(Int.self, forKey: .totalCount) ?? 0
        projectDir = try container.decodeIfPresent(String.self, forKey: .projectDir)
        ownerAgent = try container.decodeIfPresent(String.self, forKey: .ownerAgent)
        deliveryMode = try container.decodeIfPresent(String.self, forKey: .deliveryMode)
        externalTask = try container.decodeIfPresent(Bool.self, forKey: .externalTask) ?? false
    }
}

struct TaskOrchestrationTaskPageResponse: Decodable {
    let tasks: [TaskOrchestrationTaskSummary]
    let total: Int
    let limit: Int
    let offset: Int
    let hasMore: Bool

    enum CodingKeys: String, CodingKey {
        case tasks, total, limit, offset
        case hasMore = "has_more"
    }
}

struct TaskOrchestrationOrchestratorPluginStatus: Decodable {
    let runtime: Runtime
    let install: Install

    struct Runtime: Decodable {
        let mode: String
        let implementation: String
        let available: Bool
        let transport: String?
        let endpoint: String?
        let command: String?
        let connectionNote: String?

        enum CodingKeys: String, CodingKey {
            case mode, implementation, available, transport, endpoint, command
            case connectionNote = "connection_note"
        }
    }

    struct Install: Decodable {
        let status: String
        let installed: Bool
        let installable: Bool
        let source: String?
        let installDir: String?
        let command: String?
        let logs: [String]
        let error: String?

        enum CodingKeys: String, CodingKey {
            case status, installed, installable, source, command, logs, error
            case installDir = "install_dir"
        }

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            status = try container.decodeIfPresent(String.self, forKey: .status) ?? "unknown"
            installed = try container.decodeIfPresent(Bool.self, forKey: .installed) ?? false
            installable = try container.decodeIfPresent(Bool.self, forKey: .installable) ?? false
            source = try container.decodeIfPresent(String.self, forKey: .source)
            installDir = try container.decodeIfPresent(String.self, forKey: .installDir)
            command = try container.decodeIfPresent(String.self, forKey: .command)
            logs = (try? container.decode([String].self, forKey: .logs)) ?? []
            error = try container.decodeIfPresent(String.self, forKey: .error)
        }
    }
}

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
            failedConstraints = (try? container.decode([String].self, forKey: .failedConstraints)) ?? []
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
        failedConstraints = (try? container.decode([String].self, forKey: .failedConstraints)) ?? []
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

struct TaskOrchestrationTaskDetail: Decodable {
    let taskId: String
    let description: String
    let status: String
    let externalTask: Bool
    let taskTypes: [String]
    let deliveryMode: String?
    let hasOwnerDeliveryContract: Bool
    let ownerAgent: String?
    let allowedSubtaskAgents: [String]?
    let projectDir: String?
    let subtasks: [TaskOrchestrationSubtaskDetail]
    let waves: [TaskOrchestrationWaveDetail]
    let artifacts: [TaskOrchestrationArtifact]
    let artifactVersions: [String: Int]?
    let ownerSessionId: String?
    let lastOwnerDecision: TaskOrchestrationOwnerDecisionSummary?
    let error: String?
    let hasRequirementManifest: Bool
    let qualityHealth: TaskOrchestrationQualityHealth?
    let deliveryReport: TaskOrchestrationDeliveryReport?
    let observability: TaskOrchestrationTaskObservability?

    enum CodingKeys: String, CodingKey {
        case taskId = "task_id"
        case description
        case status
        case externalTask = "external_task"
        case taskTypes = "task_types"
        case deliveryMode = "delivery_mode"
        case ownerDeliveryContract = "owner_delivery_contract"
        case ownerAgent = "owner_agent"
        case allowedSubtaskAgents = "allowed_subtask_agents"
        case projectDir = "project_dir"
        case subtasks
        case waves
        case artifacts
        case artifactVersions = "artifact_versions"
        case ownerSessionId = "owner_session_id"
        case lastOwnerDecision = "last_owner_decision"
        case error
        case requirementManifest = "requirement_manifest"
        case qualityHealth = "quality_health"
        case deliveryReport = "delivery_report"
        case observability
    }

    init(
        taskId: String,
        description: String,
        status: String,
        externalTask: Bool = false,
        taskTypes: [String] = [],
        deliveryMode: String? = nil,
        hasOwnerDeliveryContract: Bool = false,
        ownerAgent: String?,
        allowedSubtaskAgents: [String]?,
        projectDir: String?,
        subtasks: [TaskOrchestrationSubtaskDetail],
        waves: [TaskOrchestrationWaveDetail],
        artifacts: [TaskOrchestrationArtifact],
        artifactVersions: [String: Int]?,
        ownerSessionId: String?,
        lastOwnerDecision: TaskOrchestrationOwnerDecisionSummary?,
        error: String?,
        hasRequirementManifest: Bool = false,
        qualityHealth: TaskOrchestrationQualityHealth? = nil,
        deliveryReport: TaskOrchestrationDeliveryReport? = nil,
        observability: TaskOrchestrationTaskObservability? = nil
    ) {
        self.taskId = taskId
        self.description = description
        self.status = status
        self.externalTask = externalTask
        self.taskTypes = taskTypes
        self.deliveryMode = deliveryMode
        self.hasOwnerDeliveryContract = hasOwnerDeliveryContract
        self.ownerAgent = ownerAgent
        self.allowedSubtaskAgents = allowedSubtaskAgents
        self.projectDir = projectDir
        self.subtasks = subtasks
        self.waves = waves
        self.artifacts = artifacts
        self.artifactVersions = artifactVersions
        self.ownerSessionId = ownerSessionId
        self.lastOwnerDecision = lastOwnerDecision
        self.error = error
        self.hasRequirementManifest = hasRequirementManifest
        self.qualityHealth = qualityHealth
        self.deliveryReport = deliveryReport
        self.observability = observability
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        taskId = try container.decode(String.self, forKey: .taskId)
        description = try container.decode(String.self, forKey: .description)
        status = try container.decode(String.self, forKey: .status)
        externalTask = try container.decodeIfPresent(Bool.self, forKey: .externalTask) ?? false
        taskTypes = (try? container.decode([String].self, forKey: .taskTypes)) ?? []
        deliveryMode = try container.decodeIfPresent(String.self, forKey: .deliveryMode)
        hasOwnerDeliveryContract = container.contains(.ownerDeliveryContract)
            && ((try? container.decodeNil(forKey: .ownerDeliveryContract)) == false)
        ownerAgent = try container.decodeIfPresent(String.self, forKey: .ownerAgent)
        allowedSubtaskAgents = try container.decodeIfPresent([String].self, forKey: .allowedSubtaskAgents)
        projectDir = try container.decodeIfPresent(String.self, forKey: .projectDir)
        subtasks = try container.decodeIfPresent([TaskOrchestrationSubtaskDetail].self, forKey: .subtasks) ?? []
        waves = try container.decodeIfPresent([TaskOrchestrationWaveDetail].self, forKey: .waves) ?? []
        artifacts = try container.decodeIfPresent([TaskOrchestrationArtifact].self, forKey: .artifacts) ?? []
        artifactVersions = try container.decodeIfPresent([String: Int].self, forKey: .artifactVersions)
        ownerSessionId = try container.decodeIfPresent(String.self, forKey: .ownerSessionId)
        lastOwnerDecision = try container.decodeIfPresent(TaskOrchestrationOwnerDecisionSummary.self, forKey: .lastOwnerDecision)
        error = try container.decodeIfPresent(String.self, forKey: .error)
        hasRequirementManifest = container.contains(.requirementManifest)
            && ((try? container.decodeNil(forKey: .requirementManifest)) == false)
        qualityHealth = try container.decodeIfPresent(TaskOrchestrationQualityHealth.self, forKey: .qualityHealth)
        deliveryReport = try container.decodeIfPresent(TaskOrchestrationDeliveryReport.self, forKey: .deliveryReport)
        observability = try container.decodeIfPresent(TaskOrchestrationTaskObservability.self, forKey: .observability)
    }

    func replacing(
        status: String? = nil,
        subtasks: [TaskOrchestrationSubtaskDetail]? = nil,
        waves: [TaskOrchestrationWaveDetail]? = nil,
        artifacts: [TaskOrchestrationArtifact]? = nil,
        ownerSessionId: String? = nil,
        lastOwnerDecision: TaskOrchestrationOwnerDecisionSummary? = nil
    ) -> TaskOrchestrationTaskDetail {
        TaskOrchestrationTaskDetail(
            taskId: taskId,
            description: description,
            status: status ?? self.status,
            externalTask: externalTask,
            taskTypes: taskTypes,
            deliveryMode: deliveryMode,
            hasOwnerDeliveryContract: hasOwnerDeliveryContract,
            ownerAgent: ownerAgent,
            allowedSubtaskAgents: allowedSubtaskAgents,
            projectDir: projectDir,
            subtasks: subtasks ?? self.subtasks,
            waves: waves ?? self.waves,
            artifacts: artifacts ?? self.artifacts,
            artifactVersions: artifactVersions,
            ownerSessionId: ownerSessionId ?? self.ownerSessionId,
            lastOwnerDecision: lastOwnerDecision ?? self.lastOwnerDecision,
            error: error,
            hasRequirementManifest: hasRequirementManifest,
            qualityHealth: qualityHealth,
            deliveryReport: deliveryReport,
            observability: observability
        )
    }

    var supportsLegacyLifecycleControls: Bool {
        !externalTask
    }
}

struct TaskOrchestrationOwnerDecisionSummary: Codable {
    let decision: String?
    let recommendedAction: String?
    let rootCauseScope: String?
    let rootCauseWave: Int?
    let preferredAgent: String?
    let blockedReason: String?

    enum CodingKeys: String, CodingKey {
        case decision
        case recommendedAction = "recommended_action"
        case rootCauseScope = "root_cause_scope"
        case rootCauseWave = "root_cause_wave"
        case preferredAgent = "preferred_agent"
        case blockedReason = "blocked_reason"
    }
}

struct TaskOrchestrationWaveDetail: Codable, Identifiable {
    let waveId: String
    let waveNumber: Int
    let subtasks: [TaskOrchestrationSubtaskDetail]
    let status: String
    let isBlocked: Bool
    let governanceStatus: String?
    let blockedByWave: Int?
    let isRevalidating: Bool
    let ownerDecision: TaskOrchestrationOwnerDecisionSummary?
    let fixRounds: [TaskOrchestrationFixRoundDetail]?

    var id: String { waveId }

    enum CodingKeys: String, CodingKey {
        case waveId = "wave_id"
        case waveNumber = "wave_number"
        case subtasks
        case status
        case isBlocked = "is_blocked"
        case governanceStatus = "governance_status"
        case blockedByWave = "blocked_by_wave"
        case isRevalidating = "is_revalidating"
        case ownerDecision = "owner_decision"
        case fixRounds = "fix_rounds"
    }
}

struct TaskOrchestrationSubtaskDetail: Codable, Identifiable {
    let subtaskId: String
    let description: String
    let agentId: String
    let status: String
    let progress: Double
    let outputFile: String?
    let duration: Double?
    let errorMessage: String?
    let fixPlan: String?
    let waveNumber: Int
    let ownerDecision: TaskOrchestrationOwnerDecisionSummary?
    let waitingOnDependencies: [String]
    let blockedReason: String?
    let runningForSeconds: Double?

    var id: String { subtaskId }

    enum CodingKeys: String, CodingKey {
        case subtaskId = "subtask_id"
        case description
        case agentId = "agent_id"
        case status
        case progress
        case outputFile = "output_file"
        case duration
        case errorMessage = "error_message"
        case fixPlan = "fix_plan"
        case waveNumber = "wave_number"
        case ownerDecision = "owner_decision"
        case waitingOnDependencies = "waiting_on_dependencies"
        case blockedReason = "blocked_reason"
        case runningForSeconds = "running_for_seconds"
    }
}

struct TaskOrchestrationFixRoundDetail: Codable, Identifiable {
    let roundNumber: Int
    let status: String
    let agentId: String
    let fixDescription: String

    var id: Int { roundNumber }

    enum CodingKeys: String, CodingKey {
        case roundNumber = "round_number"
        case status
        case agentId = "agent_id"
        case fixDescription = "fix_description"
    }
}

struct TaskOrchestrationArtifact: Codable, Identifiable {
    let id: String
    let fileName: String
    let filePath: String
    let fileSize: String
    let canonicalSubtaskId: String?
    let status: String?

    var ident: String { id }

    enum CodingKeys: String, CodingKey {
        case id
        case artifactId = "artifact_id"
        case fileName = "file_name"
        case name
        case filePath = "file_path"
        case contentRef = "content_ref"
        case normalizedContentRef = "normalized_content_ref"
        case fileSize = "file_size"
        case canonicalSubtaskId = "canonical_subtask_id"
        case status
    }

    init(
        id: String,
        fileName: String,
        filePath: String,
        fileSize: String,
        canonicalSubtaskId: String? = nil,
        status: String? = nil
    ) {
        self.id = id
        self.fileName = fileName
        self.filePath = filePath
        self.fileSize = fileSize
        self.canonicalSubtaskId = canonicalSubtaskId
        self.status = status
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decodeIfPresent(String.self, forKey: .id)
            ?? container.decodeIfPresent(String.self, forKey: .artifactId)
            ?? UUID().uuidString
        fileName = try container.decodeIfPresent(String.self, forKey: .fileName)
            ?? container.decodeIfPresent(String.self, forKey: .name)
            ?? "Unknown"
        filePath = try container.decodeIfPresent(String.self, forKey: .filePath)
            ?? container.decodeIfPresent(String.self, forKey: .contentRef)
            ?? container.decodeIfPresent(String.self, forKey: .normalizedContentRef)
            ?? ""
        fileSize = try container.decodeIfPresent(String.self, forKey: .fileSize) ?? "0 B"
        canonicalSubtaskId = try container.decodeIfPresent(String.self, forKey: .canonicalSubtaskId)
        status = try container.decodeIfPresent(String.self, forKey: .status)
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encode(fileName, forKey: .fileName)
        try container.encode(filePath, forKey: .filePath)
        try container.encode(fileSize, forKey: .fileSize)
        try container.encodeIfPresent(canonicalSubtaskId, forKey: .canonicalSubtaskId)
        try container.encodeIfPresent(status, forKey: .status)
    }
}

struct TaskOrchestrationResumableTask: Codable {
    let taskId: String
    let description: String
    let status: String
    let createdAt: TimeInterval
    let updatedAt: TimeInterval
    let projectDir: String?

    enum CodingKeys: String, CodingKey {
        case taskId = "task_id"
        case description
        case status
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case projectDir = "project_dir"
    }

    private static let terminalTaskStatuses: Set<String> = [
        "completed",
        "failed",
        "cancelled",
        "completed_with_failures"
    ]

    static func displayStatus(for resumable: TaskOrchestrationResumableTask) -> String {
        if terminalTaskStatuses.contains(resumable.status) {
            return resumable.status
        }
        return "suspended"
    }

    static func isRecoverableDisplayStatus(_ status: String) -> Bool {
        return status == "suspended" || status == "paused"
    }
}

enum TaskOrchestrationProgressEvent: Codable {
    case taskStarted(taskId: String)
    case taskCompleted(taskId: String)
    case taskFailed(taskId: String, error: String)
    case taskCompletedWithFailures(taskId: String)
    case taskPaused(taskId: String)
    case taskResumed(taskId: String)
    case taskCancelled(taskId: String)
    case subtaskUpdated(TaskOrchestrationSubtaskUpdate)
    case waveUpdated(TaskOrchestrationWaveUpdate)
    case artifactGenerated(TaskOrchestrationArtifactInfo)
    case taskStatusChanged(TaskOrchestrationTaskStatusUpdate)

    enum CodingKeys: String, CodingKey {
        case type, taskId, error, subtaskUpdate, waveUpdate, artifactInfo, taskStatusUpdate
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let type = try container.decode(String.self, forKey: .type)

        switch type {
        case "task_started":
            let taskId = try container.decode(String.self, forKey: .taskId)
            self = .taskStarted(taskId: taskId)
        case "task_completed":
            let taskId = try container.decode(String.self, forKey: .taskId)
            self = .taskCompleted(taskId: taskId)
        case "task_failed":
            let taskId = try container.decode(String.self, forKey: .taskId)
            let error = try container.decode(String.self, forKey: .error)
            self = .taskFailed(taskId: taskId, error: error)
        case "task_completed_with_failures":
            let taskId = try container.decode(String.self, forKey: .taskId)
            self = .taskCompletedWithFailures(taskId: taskId)
        case "task_paused":
            let taskId = try container.decode(String.self, forKey: .taskId)
            self = .taskPaused(taskId: taskId)
        case "task_resumed":
            let taskId = try container.decode(String.self, forKey: .taskId)
            self = .taskResumed(taskId: taskId)
        case "task_cancelled":
            let taskId = try container.decode(String.self, forKey: .taskId)
            self = .taskCancelled(taskId: taskId)
        case "subtask_updated":
            let update = try container.decode(TaskOrchestrationSubtaskUpdate.self, forKey: .subtaskUpdate)
            self = .subtaskUpdated(update)
        case "wave_updated":
            let update = try container.decode(TaskOrchestrationWaveUpdate.self, forKey: .waveUpdate)
            self = .waveUpdated(update)
        case "artifact_generated":
            let info = try container.decode(TaskOrchestrationArtifactInfo.self, forKey: .artifactInfo)
            self = .artifactGenerated(info)
        case "task_status_changed":
            // Backend sends a flat snapshot event rather than nesting it under
            // `taskStatusUpdate`, so decode from the top-level payload directly.
            let update = try TaskOrchestrationTaskStatusUpdate(from: decoder)
            self = .taskStatusChanged(update)
        case "heartbeat":
            self = .taskStarted(taskId: "")
        default:
            throw DecodingError.dataCorruptedError(forKey: .type, in: container, debugDescription: "Unknown event type: \(type)")
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)

        switch self {
        case .taskStarted(let taskId):
            try container.encode("task_started", forKey: .type)
            try container.encode(taskId, forKey: .taskId)
        case .taskCompleted(let taskId):
            try container.encode("task_completed", forKey: .type)
            try container.encode(taskId, forKey: .taskId)
        case .taskFailed(let taskId, let error):
            try container.encode("task_failed", forKey: .type)
            try container.encode(taskId, forKey: .taskId)
            try container.encode(error, forKey: .error)
        case .taskCompletedWithFailures(let taskId):
            try container.encode("task_completed_with_failures", forKey: .type)
            try container.encode(taskId, forKey: .taskId)
        case .taskPaused(let taskId):
            try container.encode("task_paused", forKey: .type)
            try container.encode(taskId, forKey: .taskId)
        case .taskResumed(let taskId):
            try container.encode("task_resumed", forKey: .type)
            try container.encode(taskId, forKey: .taskId)
        case .taskCancelled(let taskId):
            try container.encode("task_cancelled", forKey: .type)
            try container.encode(taskId, forKey: .taskId)
        case .subtaskUpdated(let update):
            try container.encode("subtask_updated", forKey: .type)
            try container.encode(update, forKey: .subtaskUpdate)
        case .waveUpdated(let update):
            try container.encode("wave_updated", forKey: .type)
            try container.encode(update, forKey: .waveUpdate)
        case .artifactGenerated(let info):
            try container.encode("artifact_generated", forKey: .type)
            try container.encode(info, forKey: .artifactInfo)
        case .taskStatusChanged(let update):
            try container.encode("task_status_changed", forKey: .type)
            try container.encode(update, forKey: .taskStatusUpdate)
        }
    }
}

struct TaskOrchestrationSubtaskUpdate: Codable {
    let subtaskId: String
    let status: String?
    let progress: Double?
    let duration: Double?
    let outputFile: String?
    let errorMessage: String?
    let fixPlan: String?
    let waveNumber: Int?
    let description: String?
    let agentId: String?
    let waitingOnDependencies: [String]?
    let blockedReason: String?
    let runningForSeconds: Double?

    enum CodingKeys: String, CodingKey {
        case subtaskId  // SSE uses camelCase from backend
        case status, progress, duration, outputFile, errorMessage, fixPlan, waveNumber
        case description, agentId
        case waitingOnDependencies, blockedReason, runningForSeconds
    }
}

struct TaskOrchestrationTaskStatusUpdate: Codable {
    let taskId: String
    let status: String
    let progress: Double
    let completedCount: Int
    let totalCount: Int
    let subtasks: [TaskOrchestrationSubtaskDetail]
    let waves: [TaskOrchestrationWaveDetail]
    let ownerSessionId: String?
    let lastOwnerDecision: TaskOrchestrationOwnerDecisionSummary?

    enum CodingKeys: String, CodingKey {
        case taskId = "task_id"
        case status
        case progress
        case completedCount = "completed_count"
        case totalCount = "total_count"
        case subtasks
        case waves
        case ownerSessionId = "owner_session_id"
        case lastOwnerDecision = "last_owner_decision"
    }
}

struct TaskOrchestrationWaveUpdate: Codable {
    let waveId: String
    let status: String?
    let isBlocked: Bool?
    let governanceStatus: String?
    let blockedByWave: Int?
    let isRevalidating: Bool?
    let ownerDecision: TaskOrchestrationOwnerDecisionSummary?
    let fixRounds: [TaskOrchestrationFixRoundDetail]?

    enum CodingKeys: String, CodingKey {
        case waveId = "wave_id"
        case status
        case isBlocked = "is_blocked"
        case governanceStatus = "governance_status"
        case blockedByWave = "blocked_by_wave"
        case isRevalidating = "is_revalidating"
        case ownerDecision = "owner_decision"
        case fixRounds = "fix_rounds"
    }
}

struct TaskOrchestrationArtifactInfo: Codable {
    let id: String
    let fileName: String
    let filePath: String
    let fileSize: String

    enum CodingKeys: String, CodingKey {
        case id
        case fileName = "file_name"
        case filePath = "file_path"
        case fileSize = "file_size"
    }

    init(id: String, fileName: String, filePath: String, fileSize: String) {
        self.id = id
        self.fileName = fileName
        self.filePath = filePath
        self.fileSize = fileSize
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        fileName = try container.decodeIfPresent(String.self, forKey: .fileName) ?? "Unknown"
        filePath = try container.decodeIfPresent(String.self, forKey: .filePath) ?? ""
        fileSize = try container.decodeIfPresent(String.self, forKey: .fileSize) ?? "0 B"
    }
}

struct TaskOrchestrationPollStatusResponse: Codable {
    let status: String
    let progress: Double
    let subtasks: [TaskOrchestrationPollSubtaskStatus]
    let waves: [TaskOrchestrationPollWaveStatus]?

    enum CodingKeys: String, CodingKey {
        case status, progress, subtasks, waves
    }
}

struct TaskOrchestrationPollSubtaskStatus: Codable {
    let subtask_id: String
    let description: String
    let agent_id: String
    let status: String
    let progress: Double
    let wave_number: Int
    let waiting_on_dependencies: [String]?
    let blocked_reason: String?
    let running_for_seconds: Double?

    enum CodingKeys: String, CodingKey {
        case subtask_id, description, agent_id, status, progress, wave_number
        case waiting_on_dependencies, blocked_reason, running_for_seconds
    }
}

struct TaskOrchestrationPollWaveStatus: Codable {
    let wave_id: String
    let wave_number: Int
    let status: String
    let is_blocked: Bool?
    let governance_status: String?
    let blocked_by_wave: Int?
    let is_revalidating: Bool?
    let owner_decision: TaskOrchestrationOwnerDecisionSummary?

    enum CodingKeys: String, CodingKey {
        case wave_id, wave_number, status, is_blocked, governance_status, blocked_by_wave, is_revalidating, owner_decision
    }
}
