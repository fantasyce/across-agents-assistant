import Foundation

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
    let reviewStatus: String
    let acceptedAt: Double?

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
        case reviewStatus = "review_status"
        case acceptedAt = "accepted_at"
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
        observability: TaskOrchestrationTaskObservability? = nil,
        reviewStatus: String = "pending",
        acceptedAt: Double? = nil
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
        self.reviewStatus = reviewStatus
        self.acceptedAt = acceptedAt
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
        reviewStatus = try container.decodeIfPresent(String.self, forKey: .reviewStatus) ?? "pending"
        acceptedAt = try container.decodeIfPresent(Double.self, forKey: .acceptedAt)
    }

    func replacing(
        status: String? = nil,
        subtasks: [TaskOrchestrationSubtaskDetail]? = nil,
        waves: [TaskOrchestrationWaveDetail]? = nil,
        artifacts: [TaskOrchestrationArtifact]? = nil,
        ownerSessionId: String? = nil,
        lastOwnerDecision: TaskOrchestrationOwnerDecisionSummary? = nil,
        reviewStatus: String? = nil,
        acceptedAt: Double? = nil
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
            observability: observability,
            reviewStatus: reviewStatus ?? self.reviewStatus,
            acceptedAt: acceptedAt ?? self.acceptedAt
        )
    }

    var supportsHostLocalLifecycleControls: Bool {
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
