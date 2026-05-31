import Foundation
import Combine

class TaskOrchestrationViewModel: ObservableObject {
    @Published var tasks: [TaskSummary] = []
    @Published var selectedTask: TaskDetail?
    @Published var viewMode: ViewMode = .empty
    @Published var isLoading = false
    @Published var isLoadingMoreTasks = false
    @Published var hasMoreTasks = false
    @Published var searchText = ""
    @Published var errorMessage: String?
    @Published var backendConnectionState: BackendConnectionState = .unknown
    @Published var releaseEvaluation: ReleaseEvaluationSummary?
    @Published var isLoadingReleaseEvaluation = false
    @Published var releaseEvaluationError: String?
    @Published var releaseE2EScenarios: [ReleaseE2EScenario] = []
    @Published var isStartingReleaseE2E = false
    @Published var releaseE2EError: String?
    @Published var selectedEvidenceBundle: TaskEvidenceBundle?
    @Published var isLoadingTaskEvidence = false
    @Published var taskEvidenceError: String?
    @Published var exportedEvidenceBundleURL: URL?
    private let taskPageSize = 50
    private var taskListOffset = 0

    enum ViewMode {
        case empty
        case detail
        case createForm
        case releaseCenter
    }

    enum BackendConnectionState: Equatable {
        case unknown
        case checking
        case connected
        case unavailable(String)
    }

    var isBackendUnavailable: Bool {
        if case .unavailable = backendConnectionState {
            return true
        }
        return false
    }

    var backendUnavailableMessage: String? {
        if case .unavailable(let message) = backendConnectionState {
            return message
        }
        return nil
    }

    enum DeliveryTaskType: String, CaseIterable, Identifiable {
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

    struct TaskSummary: Identifiable, Codable {
        let taskId: String
        let description: String
        let status: String
        let progress: Double
        let completedCount: Int
        let totalCount: Int
        let projectDir: String?
        let ownerAgent: String?
        let deliveryMode: String?

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
        }

        init(taskId: String, description: String, status: String, progress: Double, completedCount: Int, totalCount: Int, projectDir: String? = nil, ownerAgent: String? = nil, deliveryMode: String? = nil) {
            self.taskId = taskId
            self.description = description
            self.status = status
            self.progress = progress
            self.completedCount = completedCount
            self.totalCount = totalCount
            self.projectDir = projectDir
            self.ownerAgent = ownerAgent
            self.deliveryMode = deliveryMode
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
        }
    }

    struct TaskPageResponse: Decodable {
        let tasks: [TaskSummary]
        let total: Int
        let limit: Int
        let offset: Int
        let hasMore: Bool

        enum CodingKeys: String, CodingKey {
            case tasks, total, limit, offset
            case hasMore = "has_more"
        }
    }

    struct QualityHealth: Decodable {
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

    struct DeliveryReport: Decodable {
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

    struct TaskObservability: Decodable {
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

    struct TaskDetail: Decodable {
        let taskId: String
        let description: String
        let status: String
        let taskTypes: [String]
        let deliveryMode: String?
        let hasOwnerDeliveryContract: Bool
        let ownerAgent: String?
        let allowedSubtaskAgents: [String]?
        let projectDir: String?
        let subtasks: [SubtaskDetail]
        let waves: [WaveDetail]
        let artifacts: [Artifact]
        let artifactVersions: [String: Int]?
        let ownerSessionId: String?
        let lastOwnerDecision: OwnerDecisionSummary?
        let error: String?
        let hasRequirementManifest: Bool
        let qualityHealth: QualityHealth?
        let deliveryReport: DeliveryReport?
        let observability: TaskObservability?

        enum CodingKeys: String, CodingKey {
            case taskId = "task_id"
            case description
            case status
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
            taskTypes: [String] = [],
            deliveryMode: String? = nil,
            hasOwnerDeliveryContract: Bool = false,
            ownerAgent: String?,
            allowedSubtaskAgents: [String]?,
            projectDir: String?,
            subtasks: [SubtaskDetail],
            waves: [WaveDetail],
            artifacts: [Artifact],
            artifactVersions: [String: Int]?,
            ownerSessionId: String?,
            lastOwnerDecision: OwnerDecisionSummary?,
            error: String?,
            hasRequirementManifest: Bool = false,
            qualityHealth: QualityHealth? = nil,
            deliveryReport: DeliveryReport? = nil,
            observability: TaskObservability? = nil
        ) {
            self.taskId = taskId
            self.description = description
            self.status = status
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
            taskTypes = (try? container.decode([String].self, forKey: .taskTypes)) ?? []
            deliveryMode = try container.decodeIfPresent(String.self, forKey: .deliveryMode)
            hasOwnerDeliveryContract = container.contains(.ownerDeliveryContract)
                && ((try? container.decodeNil(forKey: .ownerDeliveryContract)) == false)
            ownerAgent = try container.decodeIfPresent(String.self, forKey: .ownerAgent)
            allowedSubtaskAgents = try container.decodeIfPresent([String].self, forKey: .allowedSubtaskAgents)
            projectDir = try container.decodeIfPresent(String.self, forKey: .projectDir)
            subtasks = try container.decodeIfPresent([SubtaskDetail].self, forKey: .subtasks) ?? []
            waves = try container.decodeIfPresent([WaveDetail].self, forKey: .waves) ?? []
            artifacts = try container.decodeIfPresent([Artifact].self, forKey: .artifacts) ?? []
            artifactVersions = try container.decodeIfPresent([String: Int].self, forKey: .artifactVersions)
            ownerSessionId = try container.decodeIfPresent(String.self, forKey: .ownerSessionId)
            lastOwnerDecision = try container.decodeIfPresent(OwnerDecisionSummary.self, forKey: .lastOwnerDecision)
            error = try container.decodeIfPresent(String.self, forKey: .error)
            hasRequirementManifest = container.contains(.requirementManifest)
                && ((try? container.decodeNil(forKey: .requirementManifest)) == false)
            qualityHealth = try container.decodeIfPresent(QualityHealth.self, forKey: .qualityHealth)
            deliveryReport = try container.decodeIfPresent(DeliveryReport.self, forKey: .deliveryReport)
            observability = try container.decodeIfPresent(TaskObservability.self, forKey: .observability)
        }
    }

    struct OwnerDecisionSummary: Codable {
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

    struct WaveDetail: Codable, Identifiable {
        let waveId: String
        let waveNumber: Int
        let subtasks: [SubtaskDetail]
        let status: String
        let isBlocked: Bool
        let governanceStatus: String?
        let blockedByWave: Int?
        let isRevalidating: Bool
        let ownerDecision: OwnerDecisionSummary?
        let fixRounds: [FixRoundDetail]?

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

    struct SubtaskDetail: Codable, Identifiable {
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
        let ownerDecision: OwnerDecisionSummary?
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

    struct FixRoundDetail: Codable, Identifiable {
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

    struct Artifact: Codable, Identifiable {
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

    struct ResumableTask: Codable {
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

        static func displayStatus(for resumable: ResumableTask) -> String {
            if terminalTaskStatuses.contains(resumable.status) {
                return resumable.status
            }
            return "suspended"
        }

        static func isRecoverableDisplayStatus(_ status: String) -> Bool {
            return status == "suspended" || status == "paused"
        }
    }

    enum ProgressEvent: Codable {
        case taskStarted(taskId: String)
        case taskCompleted(taskId: String)
        case taskFailed(taskId: String, error: String)
        case taskCompletedWithFailures(taskId: String)
        case taskPaused(taskId: String)
        case taskResumed(taskId: String)
        case taskCancelled(taskId: String)
        case subtaskUpdated(SubtaskUpdate)
        case waveUpdated(WaveUpdate)
        case artifactGenerated(ArtifactInfo)
        case taskStatusChanged(TaskStatusUpdate)

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
                let update = try container.decode(SubtaskUpdate.self, forKey: .subtaskUpdate)
                self = .subtaskUpdated(update)
            case "wave_updated":
                let update = try container.decode(WaveUpdate.self, forKey: .waveUpdate)
                self = .waveUpdated(update)
            case "artifact_generated":
                let info = try container.decode(ArtifactInfo.self, forKey: .artifactInfo)
                self = .artifactGenerated(info)
            case "task_status_changed":
                // Backend sends a flat snapshot event rather than nesting it under
                // `taskStatusUpdate`, so decode from the top-level payload directly.
                let update = try TaskStatusUpdate(from: decoder)
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

    struct SubtaskUpdate: Codable {
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

    struct TaskStatusUpdate: Codable {
        let taskId: String
        let status: String
        let progress: Double
        let completedCount: Int
        let totalCount: Int
        let subtasks: [SubtaskDetail]
        let waves: [WaveDetail]
        let ownerSessionId: String?
        let lastOwnerDecision: OwnerDecisionSummary?

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

    struct WaveUpdate: Codable {
        let waveId: String
        let status: String?
        let isBlocked: Bool?
        let governanceStatus: String?
        let blockedByWave: Int?
        let isRevalidating: Bool?
        let ownerDecision: OwnerDecisionSummary?
        let fixRounds: [FixRoundDetail]?

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

    struct ArtifactInfo: Codable {
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

    struct PollStatusResponse: Codable {
        let status: String
        let progress: Double
        let subtasks: [PollSubtaskStatus]
        let waves: [PollWaveStatus]?

        enum CodingKeys: String, CodingKey {
            case status, progress, subtasks, waves
        }
    }

    struct PollSubtaskStatus: Codable {
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

    struct PollWaveStatus: Codable {
        let wave_id: String
        let wave_number: Int
        let status: String
        let is_blocked: Bool?
        let governance_status: String?
        let blocked_by_wave: Int?
        let is_revalidating: Bool?
        let owner_decision: OwnerDecisionSummary?

        enum CodingKeys: String, CodingKey {
            case wave_id, wave_number, status, is_blocked, governance_status, blocked_by_wave, is_revalidating, owner_decision
        }
    }

    private var sseTask: Task<Void, Never>?
    private var reconnectAttempts = 0
    private let maxReconnectAttempts = 10
    private let reconnectDelay: UInt64 = 5_000_000_000
    private var pollingTask: Task<Void, Never>?
    // Initial polling: quickly detect whether the task leaves decomposing after submit.
    private var initialPollingTask: Task<Void, Never>?
    // SSE is a fast path. This full-detail poller is the consistency fallback
    // for bundled app runs where stream events can be missed or delayed.
    private var detailPollingTask: Task<Void, Never>?
    private let detailPollingInterval: UInt64 = 5_000_000_000
    private let terminalSettlePollLimit = 12

    private var baseURL: URL? {
        if let urlString = UserDefaults.standard.string(forKey: "serverURL") {
            return URL(string: urlString)
        }
        return URL(string: "http://backend")
    }

    func loadTasks() {
        loadTaskPage(reset: true)
        loadReleaseEvaluation()
        loadReleaseE2EScenarios()
    }

    func openReleaseCenter() {
        viewMode = .releaseCenter
        loadReleaseEvaluation()
    }

    func closeEvidenceBundle() {
        selectedEvidenceBundle = nil
        exportedEvidenceBundleURL = nil
        taskEvidenceError = nil
    }

    func loadReleaseEvaluation() {
        Task { @MainActor in
            guard let baseURL = baseURL else {
                releaseEvaluation = nil
                releaseEvaluationError = "Server URL not configured"
                return
            }

            isLoadingReleaseEvaluation = true
            releaseEvaluationError = nil

            do {
                let url = baseURL.appendingPathComponent("api/release/evaluation")
                var request = URLRequest(url: url)
                request.httpMethod = "GET"
                request.setValue("application/json", forHTTPHeaderField: "Accept")
                request.timeoutInterval = 10

                let (data, response) = try await URLSession.shared.data(for: request)
                guard let httpResponse = response as? HTTPURLResponse,
                      (200...299).contains(httpResponse.statusCode) else {
                    throw URLError(.badServerResponse)
                }

                releaseEvaluation = try JSONDecoder().decode(ReleaseEvaluationSummary.self, from: data)
                isLoadingReleaseEvaluation = false
            } catch {
                releaseEvaluation = nil
                releaseEvaluationError = error.localizedDescription
                isLoadingReleaseEvaluation = false
            }
        }
    }

    func loadTaskEvidenceBundle(_ taskId: String, releaseGate: Bool = false) {
        Task { @MainActor in
            guard let baseURL = baseURL else {
                taskEvidenceError = "Server URL not configured"
                return
            }

            isLoadingTaskEvidence = true
            taskEvidenceError = nil
            exportedEvidenceBundleURL = nil

            do {
                let data = try await Self.fetchEvidenceBundleData(baseURL: baseURL, taskId: taskId, releaseGate: releaseGate)
                selectedEvidenceBundle = try JSONDecoder().decode(TaskEvidenceBundle.self, from: data)
                isLoadingTaskEvidence = false
            } catch {
                taskEvidenceError = error.localizedDescription
                isLoadingTaskEvidence = false
            }
        }
    }

    func exportTaskEvidenceBundle(_ taskId: String, releaseGate: Bool = false) {
        Task { @MainActor in
            guard let baseURL = baseURL else {
                taskEvidenceError = "Server URL not configured"
                return
            }

            isLoadingTaskEvidence = true
            taskEvidenceError = nil

            do {
                let data = try await Self.fetchEvidenceBundleData(baseURL: baseURL, taskId: taskId, releaseGate: releaseGate)
                selectedEvidenceBundle = try JSONDecoder().decode(TaskEvidenceBundle.self, from: data)
                let exportURL = LocalAppPaths.evidenceExportsDir
                    .appendingPathComponent(TaskEvidenceBundle.exportFileName(taskId: taskId))
                let prettyData = Self.prettyPrintedJSONData(from: data) ?? data
                try prettyData.write(to: exportURL, options: [.atomic])
                exportedEvidenceBundleURL = exportURL
                isLoadingTaskEvidence = false
            } catch {
                taskEvidenceError = error.localizedDescription
                isLoadingTaskEvidence = false
            }
        }
    }

    private static func fetchEvidenceBundleData(baseURL: URL, taskId: String, releaseGate: Bool) async throws -> Data {
        var components = URLComponents(
            url: baseURL
            .appendingPathComponent("api/tasks")
            .appendingPathComponent(taskId)
            .appendingPathComponent("evidence-bundle"),
            resolvingAgainstBaseURL: false
        )
        if releaseGate {
            components?.queryItems = [
                URLQueryItem(name: "expected_files", value: TaskEvidenceBundle.releaseE2EExpectedFiles.joined(separator: ",")),
                URLQueryItem(name: "required_probes", value: TaskEvidenceBundle.releaseE2ERequiredProbes.joined(separator: ",")),
                URLQueryItem(name: "min_quality_score", value: "70"),
                URLQueryItem(name: "max_remediation_attempts", value: "2")
            ]
        }
        guard let url = components?.url else {
            throw URLError(.badURL)
        }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.timeoutInterval = 20

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            throw URLError(.badServerResponse)
        }
        return data
    }

    private static func prettyPrintedJSONData(from data: Data) -> Data? {
        guard let object = try? JSONSerialization.jsonObject(with: data),
              JSONSerialization.isValidJSONObject(object) else {
            return nil
        }
        return try? JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted, .sortedKeys])
    }

    func loadReleaseE2EScenarios() {
        Task { @MainActor in
            guard let baseURL = baseURL else {
                releaseE2EScenarios = []
                return
            }

            do {
                let url = baseURL.appendingPathComponent("api/release/e2e/scenarios")
                var request = URLRequest(url: url)
                request.httpMethod = "GET"
                request.setValue("application/json", forHTTPHeaderField: "Accept")
                request.timeoutInterval = 10

                let (data, response) = try await URLSession.shared.data(for: request)
                guard let httpResponse = response as? HTTPURLResponse,
                      (200...299).contains(httpResponse.statusCode) else {
                    return
                }

                releaseE2EScenarios = try JSONDecoder().decode(ReleaseE2EScenarioListResponse.self, from: data).scenarios
            } catch {
                releaseE2EScenarios = []
            }
        }
    }

    func startReleaseE2E() {
        Task { @MainActor in
            guard !isStartingReleaseE2E else { return }
            guard let baseURL = baseURL else {
                releaseE2EError = "Server URL not configured"
                return
            }

            isStartingReleaseE2E = true
            releaseE2EError = nil
            errorMessage = nil

            do {
                let url = baseURL.appendingPathComponent("api/release/e2e/tasks")
                var request = URLRequest(url: url)
                request.httpMethod = "POST"
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                request.setValue("application/json", forHTTPHeaderField: "Accept")

                let scenarioId = releaseE2EScenarios.first?.id ?? "cross_agent_full_delivery_v1"
                let runLabel = Self.releaseE2ERunLabel()
                request.httpBody = try JSONSerialization.data(withJSONObject: [
                    "scenario_id": scenarioId,
                    "run_label": runLabel
                ])

                let (data, response) = try await URLSession.shared.data(for: request)
                guard let httpResponse = response as? HTTPURLResponse else {
                    throw URLError(.badServerResponse)
                }

                guard (200...299).contains(httpResponse.statusCode) else {
                    releaseE2EError = Self.backendErrorMessage(from: data)
                        ?? "Failed to start release E2E (HTTP \(httpResponse.statusCode))"
                    isStartingReleaseE2E = false
                    return
                }

                let result = try JSONDecoder().decode(ReleaseE2ETaskResponse.self, from: data)
                viewMode = .detail
                selectTask(result.taskId)
                loadTasks()
                startInitialPolling(for: result.taskId)
                isStartingReleaseE2E = false
            } catch {
                releaseE2EError = error.localizedDescription
                isStartingReleaseE2E = false
            }
        }
    }

    private static func releaseE2ERunLabel() -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyyMMdd-HHmmss"
        return "ui-\(formatter.string(from: Date()))"
    }

    private static func backendErrorMessage(from data: Data) -> String? {
        guard !data.isEmpty else { return nil }
        if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let detail = json["detail"] {
            if let text = detail as? String, !text.isEmpty {
                return text
            }
            if let object = detail as? [String: Any] {
                var parts: [String] = []
                if let message = object["message"] as? String, !message.isEmpty {
                    parts.append(message)
                }
                if let missing = object["missing_providers"] as? [String], !missing.isEmpty {
                    parts.append("Missing: \(missing.joined(separator: ", "))")
                }
                if !parts.isEmpty {
                    return parts.joined(separator: " ")
                }
            }
        }
        return String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    func loadMoreTasks() {
        guard hasMoreTasks, !isLoadingMoreTasks else { return }
        loadTaskPage(reset: false)
    }

    private func loadTaskPage(reset: Bool) {
        Task { @MainActor in
            if reset {
                isLoading = true
                taskListOffset = 0
                hasMoreTasks = false
                backendConnectionState = .checking
            } else {
                isLoadingMoreTasks = true
            }
            errorMessage = nil

            guard let baseURL = baseURL else {
                errorMessage = "Server URL not configured"
                backendConnectionState = .unavailable("Server URL not configured")
                isLoading = false
                isLoadingMoreTasks = false
                return
            }

            for attempt in 0..<5 {
                do {
                    let offset = reset ? 0 : taskListOffset
                    var components = URLComponents(
                        url: baseURL.appendingPathComponent("api/tasks/page"),
                        resolvingAgainstBaseURL: false
                    )
                    components?.queryItems = [
                        URLQueryItem(name: "limit", value: "\(taskPageSize)"),
                        URLQueryItem(name: "offset", value: "\(offset)")
                    ]
                    guard let url = components?.url else {
                        throw URLError(.badURL)
                    }
                    var request = URLRequest(url: url)
                    request.httpMethod = "GET"
                    request.setValue("application/json", forHTTPHeaderField: "Accept")
                    request.timeoutInterval = 10

                    let (data, response) = try await URLSession.shared.data(for: request)

                    guard let httpResponse = response as? HTTPURLResponse,
                          (200...299).contains(httpResponse.statusCode) else {
                        throw URLError(.badServerResponse)
                    }

                    let decoder = JSONDecoder()
                    let page = try decoder.decode(TaskPageResponse.self, from: data)

                    if reset {
                        tasks = page.tasks
                    } else {
                        let existingIds = Set(tasks.map { $0.taskId })
                        tasks.append(contentsOf: page.tasks.filter { !existingIds.contains($0.taskId) })
                    }

                    taskListOffset = page.offset + page.tasks.count
                    hasMoreTasks = page.hasMore
                    backendConnectionState = .connected
                    isLoading = false
                    isLoadingMoreTasks = false
                    return
                } catch {
                    if attempt == 4 {
                        errorMessage = error.localizedDescription
                        backendConnectionState = .unavailable(error.localizedDescription)
                        isLoading = false
                        isLoadingMoreTasks = false
                        return
                    }

                    try? await Task.sleep(nanoseconds: 1_000_000_000)
                }
            }
        }
    }

    func selectTask(_ taskId: String) {
        Task { @MainActor in
            isLoading = true
            errorMessage = nil

            stopSSE()
            let summaryStatus = tasks.first(where: { $0.taskId == taskId })?.status
            let isSuspendedSummary = summaryStatus.map(ResumableTask.isRecoverableDisplayStatus) ?? false

            guard let baseURL = baseURL else {
                errorMessage = "Server URL not configured"
                isLoading = false
                return
            }

            do {
                let url = baseURL.appendingPathComponent("api/tasks/\(taskId)")
                var request = URLRequest(url: url)
                request.httpMethod = "GET"
                request.setValue("application/json", forHTTPHeaderField: "Accept")

                let (data, response) = try await URLSession.shared.data(for: request)

                guard let httpResponse = response as? HTTPURLResponse,
                      (200...299).contains(httpResponse.statusCode) else {
                    errorMessage = "Failed to load task details"
                    isLoading = false
                    return
                }

                let decoder = JSONDecoder()
                let decodedTaskDetail = try decoder.decode(TaskDetail.self, from: data)
                let taskDetail = isSuspendedSummary
                    ? TaskDetail(
                        taskId: decodedTaskDetail.taskId,
                        description: decodedTaskDetail.description,
                        status: "suspended",
                        taskTypes: decodedTaskDetail.taskTypes,
                        deliveryMode: decodedTaskDetail.deliveryMode,
                        hasOwnerDeliveryContract: decodedTaskDetail.hasOwnerDeliveryContract,
                        ownerAgent: decodedTaskDetail.ownerAgent,
                        allowedSubtaskAgents: decodedTaskDetail.allowedSubtaskAgents,
                        projectDir: decodedTaskDetail.projectDir,
                        subtasks: decodedTaskDetail.subtasks,
                        waves: decodedTaskDetail.waves,
                        artifacts: decodedTaskDetail.artifacts,
                        artifactVersions: decodedTaskDetail.artifactVersions,
                        ownerSessionId: decodedTaskDetail.ownerSessionId,
                        lastOwnerDecision: decodedTaskDetail.lastOwnerDecision,
                        error: decodedTaskDetail.error,
                        hasRequirementManifest: decodedTaskDetail.hasRequirementManifest,
                        qualityHealth: decodedTaskDetail.qualityHealth,
                        deliveryReport: decodedTaskDetail.deliveryReport
                    )
                    : decodedTaskDetail
                selectedTask = taskDetail
                viewMode = .detail
                isLoading = false

                if !isSuspendedSummary {
                    reconnectAttempts = 0
                    startSSE(for: taskId)
                    startDetailPolling(for: taskId)
                }
            } catch {
                print("Failed to decode task detail for \(taskId): \(error)")
                errorMessage = "Failed to load task detail: \(error.localizedDescription)"
                isLoading = false
            }
        }
    }

    func submitTask(
        description: String,
        taskTypes: [String],
        ownerAgent: String,
        allowedSubtaskAgents: [String] = [],
        projectDir: String?,
        strictDependency: Bool = true
    ) {
        Task { @MainActor in
            isLoading = true
            errorMessage = nil

            guard let baseURL = baseURL else {
                errorMessage = "Server URL not configured"
                isLoading = false
                return
            }

            do {
                let url = baseURL.appendingPathComponent("api/tasks/auto")
                var request = URLRequest(url: url)
                request.httpMethod = "POST"
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                request.setValue("application/json", forHTTPHeaderField: "Accept")

                var body: [String: Any] = [
                    "description": description,
                    "task_types": taskTypes,
                    "owner_agent": ownerAgent,
                    "allowed_subtask_agents": allowedSubtaskAgents
                ]

                if let projectDir = projectDir {
                    body["project_dir"] = projectDir
                }

                body["strict_dependency"] = strictDependency
                body["enable_wave_gate"] = true

                request.httpBody = try JSONSerialization.data(withJSONObject: body)

                let (data, response) = try await URLSession.shared.data(for: request)

                guard let httpResponse = response as? HTTPURLResponse else {
                    errorMessage = "Invalid response"
                    isLoading = false
                    return
                }

                if (200...299).contains(httpResponse.statusCode) {
                    let decoder = JSONDecoder()
                    let result = try decoder.decode([String: String].self, from: data)

                    if let newTaskId = result["task_id"] {
                        viewMode = .detail
                        selectTask(newTaskId)
                        loadTasks()
                        // P0-5: initial polling quickly detects whether the task leaves decomposing.
                        startInitialPolling(for: newTaskId)
                    } else {
                        viewMode = .empty
                    }
                } else {
                    // Try to parse error detail from response
                    if let errorJson = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                       let detail = errorJson["detail"] as? String {
                        errorMessage = detail
                    } else if let text = String(data: data, encoding: .utf8), !text.isEmpty {
                        errorMessage = text
                    } else {
                        errorMessage = "Failed to submit task (HTTP \(httpResponse.statusCode))"
                    }
                }

                isLoading = false
            } catch {
                errorMessage = error.localizedDescription
                isLoading = false
            }
        }
    }

    func pauseTask(_ taskId: String) {
        Task { @MainActor in
            errorMessage = nil

            guard let baseURL = baseURL else {
                errorMessage = "Server URL not configured"
                return
            }

            do {
                let url = baseURL.appendingPathComponent("api/tasks/\(taskId)/pause")
                var request = URLRequest(url: url)
                request.httpMethod = "POST"
                request.setValue("application/json", forHTTPHeaderField: "Accept")

                let (_, response) = try await URLSession.shared.data(for: request)

                guard let httpResponse = response as? HTTPURLResponse,
                      (200...299).contains(httpResponse.statusCode) else {
                    errorMessage = "Failed to pause task"
                    return
                }

                updateTaskStatus(taskId: taskId, status: "paused")
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }

    func resumeTask(_ taskId: String) {
        Task { @MainActor in
            errorMessage = nil

            guard let baseURL = baseURL else {
                errorMessage = "Server URL not configured"
                return
            }

            do {
                let url = baseURL.appendingPathComponent("api/tasks/\(taskId)/resume")
                var request = URLRequest(url: url)
                request.httpMethod = "POST"
                request.setValue("application/json", forHTTPHeaderField: "Accept")

                let (_, response) = try await URLSession.shared.data(for: request)

                guard let httpResponse = response as? HTTPURLResponse,
                      (200...299).contains(httpResponse.statusCode) else {
                    errorMessage = "Failed to resume task"
                    return
                }

                updateTaskStatus(taskId: taskId, status: "running")
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }

    func cancelTask(_ taskId: String) {
        Task { @MainActor in
            errorMessage = nil

            guard let baseURL = baseURL else {
                errorMessage = "Server URL not configured"
                return
            }

            do {
                let url = baseURL.appendingPathComponent("api/tasks/\(taskId)/cancel")
                var request = URLRequest(url: url)
                request.httpMethod = "POST"
                request.setValue("application/json", forHTTPHeaderField: "Accept")

                let (_, response) = try await URLSession.shared.data(for: request)

                guard let httpResponse = response as? HTTPURLResponse,
                      (200...299).contains(httpResponse.statusCode) else {
                    errorMessage = "Failed to cancel task"
                    return
                }

                stopSSE()
                updateTaskStatus(taskId: taskId, status: "cancelled")
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }

    // Issue 46: Restore a task from persistence
    func restoreTask(_ taskId: String) {
        Task { @MainActor in
            errorMessage = nil

            guard let baseURL = baseURL else {
                errorMessage = "Server URL not configured"
                return
            }

            do {
                let url = baseURL.appendingPathComponent("api/tasks/\(taskId)/restore")
                var request = URLRequest(url: url)
                request.httpMethod = "POST"
                request.setValue("application/json", forHTTPHeaderField: "Accept")

                let (data, response) = try await URLSession.shared.data(for: request)

                guard let httpResponse = response as? HTTPURLResponse else {
                    errorMessage = "Invalid response"
                    return
                }

                if httpResponse.statusCode == 409 {
                    errorMessage = "Another task is already running. Only one task can be active at a time."
                    return
                }

                guard (200...299).contains(httpResponse.statusCode) else {
                    errorMessage = "Failed to restore task"
                    return
                }

                let decoder = JSONDecoder()
                let restoredTask = try decoder.decode(TaskDetail.self, from: data)

                selectedTask = restoredTask
                viewMode = .detail
                reconnectAttempts = 0
                startSSE(for: taskId)
                startDetailPolling(for: taskId)
                loadTasks()
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }

    func enterCreateMode() {
        viewMode = .createForm
        selectedTask = nil
        stopSSE()
    }

    func cancelCreate() {
        errorMessage = nil
        isLoading = false
        if selectedTask != nil {
            viewMode = .detail
        } else {
            viewMode = .empty
        }
    }

    private func startSSE(for taskId: String) {
        guard let baseURL = baseURL else { return }

        sseTask = Task { @MainActor [weak self] in
            guard let self = self else { return }

            let url = baseURL.appendingPathComponent("api/tasks/\(taskId)/stream")
            var request = URLRequest(url: url)
            request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
            request.setValue("no-cache", forHTTPHeaderField: "Cache-Control")
            request.setValue("no", forHTTPHeaderField: "X-Accel-Buffering")

            do {
                let (bytes, response) = try await URLSession.shared.bytes(for: request)

                guard let httpResponse = response as? HTTPURLResponse,
                      (200...299).contains(httpResponse.statusCode) else {
                    self.handleSSEError(taskId: taskId)
                    return
                }

                var eventData = Data()

                for try await byte in bytes {
                    if byte == 10 {
                        let line = String(data: eventData, encoding: .utf8) ?? ""
                        eventData = Data()

                        if line.hasPrefix("id:") {
                            continue
                        } else if line.hasPrefix("data:") {
                            let jsonString = String(line.dropFirst(5)).trimmingCharacters(in: .whitespaces)
                            if let jsonData = jsonString.data(using: .utf8) {
                                do {
                                    let decoder = JSONDecoder()
                                    let event = try decoder.decode(ProgressEvent.self, from: jsonData)
                                    self.handleProgressEvent(event, taskId: taskId)
                                } catch {
                                    print("Failed to decode SSE event: \(error)")
                                }
                            }
                        }
                    } else if byte != 13 {
                        eventData.append(byte)
                    }
                }
            } catch {
                self.handleSSEError(taskId: taskId)
            }
        }
    }

    private func handleSSEError(taskId: String) {
        guard reconnectAttempts < maxReconnectAttempts else {
            print("Max SSE reconnect attempts reached for task \(taskId), starting polling fallback")
            startPollingFallback(for: taskId)
            return
        }

        reconnectAttempts += 1
        print("SSE disconnected for task \(taskId), reconnecting (attempt \(reconnectAttempts)/\(maxReconnectAttempts))...")

        Task { @MainActor in
            try? await Task.sleep(nanoseconds: reconnectDelay)
            startSSE(for: taskId)
        }
    }

    @MainActor
    private func handleProgressEvent(_ event: ProgressEvent, taskId: String) {
        guard var task = selectedTask, task.taskId == taskId else { return }

        switch event {
        case .taskCompleted:
            if let index = tasks.firstIndex(where: { $0.taskId == taskId }) {
                let counts = businessSubtaskProgress(in: task.waves.flatMap { $0.subtasks })
                tasks[index] = TaskSummary(
                    taskId: taskId,
                    description: task.description,
                    status: "completed",
                    progress: 1.0,
                    completedCount: counts.total,
                    totalCount: counts.total,
                    projectDir: task.projectDir,
                    ownerAgent: task.ownerAgent
                )
            }
            updateSelectedTaskStatus(taskId: taskId, status: "completed")
            Task { @MainActor [weak self] in
                _ = await self?.refreshSelectedTaskDetail(taskId: taskId)
            }
            stopSSE()

        case .taskFailed:
            if let index = tasks.firstIndex(where: { $0.taskId == taskId }) {
                let counts = businessSubtaskProgress(in: task.waves.flatMap { $0.subtasks })
                tasks[index] = TaskSummary(
                    taskId: taskId,
                    description: task.description,
                    status: "failed",
                    progress: tasks[index].progress,
                    completedCount: counts.completed,
                    totalCount: counts.total,
                    projectDir: task.projectDir,
                    ownerAgent: task.ownerAgent
                )
            }
            updateSelectedTaskStatus(taskId: taskId, status: "failed")
            Task { @MainActor [weak self] in
                _ = await self?.refreshSelectedTaskDetail(taskId: taskId)
            }
            stopSSE()

        case .taskCompletedWithFailures:
            if let index = tasks.firstIndex(where: { $0.taskId == taskId }) {
                let counts = businessSubtaskProgress(in: task.waves.flatMap { $0.subtasks })
                tasks[index] = TaskSummary(
                    taskId: taskId,
                    description: task.description,
                    status: "completed_with_failures",
                    progress: 1.0,
                    completedCount: counts.completed,
                    totalCount: counts.total,
                    projectDir: task.projectDir,
                    ownerAgent: task.ownerAgent
                )
            }
            updateSelectedTaskStatus(taskId: taskId, status: "completed_with_failures")
            Task { @MainActor [weak self] in
                _ = await self?.refreshSelectedTaskDetail(taskId: taskId)
            }
            stopSSE()

        case .taskStatusChanged(let update):
            let updatedTask = TaskDetail(
                taskId: task.taskId,
                description: task.description,
                status: update.status,
                ownerAgent: task.ownerAgent,
                allowedSubtaskAgents: task.allowedSubtaskAgents,
                projectDir: task.projectDir,
                subtasks: update.subtasks,
                waves: update.waves,
                artifacts: task.artifacts,
                artifactVersions: task.artifactVersions,
                ownerSessionId: update.ownerSessionId ?? task.ownerSessionId,
                lastOwnerDecision: update.lastOwnerDecision ?? task.lastOwnerDecision,
                error: task.error,
                hasRequirementManifest: task.hasRequirementManifest,
                qualityHealth: task.qualityHealth,
                deliveryReport: task.deliveryReport
            )
            selectedTask = updatedTask
            task = updatedTask

            if let index = tasks.firstIndex(where: { $0.taskId == taskId }) {
                tasks[index] = TaskSummary(
                    taskId: taskId,
                    description: task.description,
                    status: update.status,
                    progress: update.progress,
                    completedCount: update.completedCount,
                    totalCount: update.totalCount,
                    projectDir: task.projectDir,
                    ownerAgent: task.ownerAgent
                )
            }

        case .subtaskUpdated(let update):
            // With persistence, SSE includes full description and agentId for all subtasks.
            // If subtask is not in current waves (e.g., new fix subtask), we need to add it.
            var updatedWaves = task.waves
            var subtaskFound = false

            for (waveIndex, wave) in updatedWaves.enumerated() {
                if let subtaskIndex = wave.subtasks.firstIndex(where: { $0.subtaskId == update.subtaskId }) {
                    let subtask = wave.subtasks[subtaskIndex]

                    let updatedSubtask = SubtaskDetail(
                        subtaskId: subtask.subtaskId,
                        description: update.description ?? subtask.description,
                        agentId: update.agentId ?? subtask.agentId,
                        status: update.status ?? subtask.status,
                        progress: update.progress ?? subtask.progress,
                        outputFile: update.outputFile ?? subtask.outputFile,
                        duration: update.duration ?? subtask.duration,
                        errorMessage: update.errorMessage ?? subtask.errorMessage,
                        fixPlan: update.fixPlan ?? subtask.fixPlan,
                        waveNumber: subtask.waveNumber,
                        ownerDecision: subtask.ownerDecision,
                        waitingOnDependencies: update.waitingOnDependencies ?? subtask.waitingOnDependencies,
                        blockedReason: update.blockedReason ?? subtask.blockedReason,
                        runningForSeconds: update.runningForSeconds ?? subtask.runningForSeconds
                    )

                    let newSubtasks = wave.subtasks.enumerated().map { (idx, st) -> SubtaskDetail in
                        idx == subtaskIndex ? updatedSubtask : st
                    }
                    let updatedWave = WaveDetail(
                        waveId: wave.waveId,
                        waveNumber: wave.waveNumber,
                        subtasks: newSubtasks,
                        status: wave.status,
                        isBlocked: wave.isBlocked,
                        governanceStatus: wave.governanceStatus,
                        blockedByWave: wave.blockedByWave,
                        isRevalidating: wave.isRevalidating,
                        ownerDecision: wave.ownerDecision,
                        fixRounds: wave.fixRounds
                    )
                    updatedWaves[waveIndex] = updatedWave
                    subtaskFound = true
                    break
                }
            }

            // If subtask not found in existing waves (new fix subtask), add it to appropriate wave
            if !subtaskFound, let waveNumber = update.waveNumber {
                if let waveIndex = updatedWaves.firstIndex(where: { $0.waveNumber == waveNumber }) {
                    let newSubtask = SubtaskDetail(
                        subtaskId: update.subtaskId,
                        description: update.description ?? "Fix subtask",
                        agentId: update.agentId ?? "unknown",
                        status: update.status ?? "pending",
                        progress: update.progress ?? 0.0,
                        outputFile: update.outputFile,
                        duration: update.duration,
                        errorMessage: update.errorMessage,
                        fixPlan: update.fixPlan,
                        waveNumber: waveNumber,
                        ownerDecision: nil,
                        waitingOnDependencies: update.waitingOnDependencies ?? [],
                        blockedReason: update.blockedReason,
                        runningForSeconds: update.runningForSeconds
                    )
                    let wave = updatedWaves[waveIndex]
                    let newSubtasks = wave.subtasks + [newSubtask]
                    let updatedWave = WaveDetail(
                        waveId: wave.waveId,
                        waveNumber: wave.waveNumber,
                        subtasks: newSubtasks,
                        status: wave.status,
                        isBlocked: wave.isBlocked,
                        governanceStatus: wave.governanceStatus,
                        blockedByWave: wave.blockedByWave,
                        isRevalidating: wave.isRevalidating,
                        ownerDecision: wave.ownerDecision,
                        fixRounds: wave.fixRounds
                    )
                    updatedWaves[waveIndex] = updatedWave
                }
            }

            let counts = businessSubtaskProgress(in: updatedWaves.flatMap { $0.subtasks })
            let hasRunning = updatedWaves.flatMap { $0.subtasks }.contains { $0.status == "running" }
            let progress = counts.total > 0 ? Double(counts.completed) / Double(counts.total) : 0

            task = TaskDetail(
                taskId: task.taskId,
                description: task.description,
                status: hasRunning ? "running" : task.status,
                ownerAgent: task.ownerAgent,
                allowedSubtaskAgents: task.allowedSubtaskAgents,
                projectDir: task.projectDir,
                subtasks: task.subtasks,
                waves: updatedWaves,
                artifacts: task.artifacts,
                artifactVersions: task.artifactVersions,
                ownerSessionId: task.ownerSessionId,
                lastOwnerDecision: task.lastOwnerDecision,
                error: task.error,
                hasRequirementManifest: task.hasRequirementManifest,
                qualityHealth: task.qualityHealth,
                deliveryReport: task.deliveryReport
            )

            selectedTask = task

            if let index = tasks.firstIndex(where: { $0.taskId == taskId }) {
                tasks[index] = TaskSummary(
                    taskId: taskId,
                    description: task.description,
                    status: hasRunning ? "running" : tasks[index].status,
                    progress: progress,
                    completedCount: counts.completed,
                    totalCount: counts.total,
                    projectDir: task.projectDir,
                    ownerAgent: task.ownerAgent
                )
            }

        case .waveUpdated(let update):
            var updatedWaves = task.waves

            if let waveIndex = updatedWaves.firstIndex(where: { $0.waveId == update.waveId }) {
                let wave = updatedWaves[waveIndex]

                let updatedWave = WaveDetail(
                    waveId: wave.waveId,
                    waveNumber: wave.waveNumber,
                    subtasks: wave.subtasks,
                    status: update.status ?? wave.status,
                    isBlocked: update.isBlocked ?? wave.isBlocked,
                    governanceStatus: update.governanceStatus ?? wave.governanceStatus,
                    blockedByWave: update.blockedByWave ?? wave.blockedByWave,
                    isRevalidating: update.isRevalidating ?? wave.isRevalidating,
                    ownerDecision: update.ownerDecision ?? wave.ownerDecision,
                    fixRounds: update.fixRounds ?? wave.fixRounds
                )

                updatedWaves[waveIndex] = updatedWave

                task = TaskDetail(
                    taskId: task.taskId,
                    description: task.description,
                    status: task.status,
                    ownerAgent: task.ownerAgent,
                    allowedSubtaskAgents: task.allowedSubtaskAgents,
                    projectDir: task.projectDir,
                    subtasks: task.subtasks,
                    waves: updatedWaves,
                    artifacts: task.artifacts,
                    artifactVersions: task.artifactVersions,
                    ownerSessionId: task.ownerSessionId,
                    lastOwnerDecision: task.lastOwnerDecision,
                    error: task.error,
                    hasRequirementManifest: task.hasRequirementManifest,
                    qualityHealth: task.qualityHealth,
                    deliveryReport: task.deliveryReport
                )

                selectedTask = task
            }

        case .artifactGenerated(let info):
            let newArtifact = Artifact(
                id: info.id,
                fileName: info.fileName,
                filePath: info.filePath,
                fileSize: info.fileSize
            )

            var updatedArtifacts = task.artifacts
            if !updatedArtifacts.contains(where: { $0.id == info.id }) {
                updatedArtifacts.append(newArtifact)
            }

            task = TaskDetail(
                taskId: task.taskId,
                description: task.description,
                status: task.status,
                ownerAgent: task.ownerAgent,
                allowedSubtaskAgents: task.allowedSubtaskAgents,
                projectDir: task.projectDir,
                subtasks: task.subtasks,
                waves: task.waves,
                artifacts: updatedArtifacts,
                artifactVersions: task.artifactVersions,
                ownerSessionId: task.ownerSessionId,
                lastOwnerDecision: task.lastOwnerDecision,
                error: task.error,
                hasRequirementManifest: task.hasRequirementManifest,
                qualityHealth: task.qualityHealth,
                deliveryReport: task.deliveryReport
            )

            selectedTask = task

        default:
            break
        }
    }

    private func startPollingFallback(for taskId: String) {
        pollingTask?.cancel()
        pollingTask = Task { @MainActor [weak self] in
            guard let self = self else { return }
            while !Task.isCancelled {
                guard let baseURL = self.baseURL else { break }
                do {
                    let url = baseURL.appendingPathComponent("api/tasks/\(taskId)/status")
                    let (data, _) = try await URLSession.shared.data(from: url)
                    let statusData = try JSONDecoder().decode(PollStatusResponse.self, from: data)

                    if let currentTask = self.selectedTask, currentTask.taskId == taskId {
                        self.updateTaskFromPollResponse(currentTask, statusData)

                        if statusData.status == "running" || statusData.status == "pending" || statusData.status == "decomposing" {
                            self.reconnectAttempts = 0
                            self.startSSE(for: taskId)
                            return
                        }

                        let terminalStatuses = ["completed", "completed_with_failures", "failed", "cancelled"]
                        if terminalStatuses.contains(statusData.status) {
                            self.startDetailPolling(for: taskId)
                            return
                        }
                    }
                } catch {
                }

                try? await Task.sleep(nanoseconds: 10_000_000_000)
            }
        }
    }

    private func startDetailPolling(for taskId: String) {
        detailPollingTask?.cancel()
        detailPollingTask = Task { @MainActor [weak self] in
            guard let self = self else { return }
            var terminalStablePolls = 0

            while !Task.isCancelled {
                guard let currentTask = self.selectedTask, currentTask.taskId == taskId else {
                    return
                }

                let refreshedTask = await self.refreshSelectedTaskDetail(taskId: taskId)
                let latestTask = refreshedTask ?? currentTask
                if self.isTerminalStatus(latestTask.status) {
                    terminalStablePolls += 1
                } else {
                    terminalStablePolls = 0
                }

                if !self.shouldContinueDetailPolling(latestTask, terminalStablePolls: terminalStablePolls) {
                    return
                }

                try? await Task.sleep(nanoseconds: self.detailPollingInterval)
            }
        }
    }

    private func shouldContinueDetailPolling(_ task: TaskDetail, terminalStablePolls: Int) -> Bool {
        if !isTerminalStatus(task.status) {
            return true
        }
        if task.qualityHealth?.orchestrationHealth == "recovering" {
            return true
        }
        if !(task.qualityHealth?.activeRemediationSubtasks.isEmpty ?? true) {
            return true
        }
        if let nextAction = task.deliveryReport?.nextAction, !nextAction.isEmpty {
            return true
        }
        return terminalStablePolls < terminalSettlePollLimit
    }

    @MainActor
    private func refreshSelectedTaskDetail(taskId: String) async -> TaskDetail? {
        guard let baseURL = baseURL else { return nil }

        do {
            let url = baseURL.appendingPathComponent("api/tasks/\(taskId)")
            var request = URLRequest(url: url)
            request.httpMethod = "GET"
            request.setValue("application/json", forHTTPHeaderField: "Accept")

            let (data, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse,
                  (200...299).contains(httpResponse.statusCode) else {
                return nil
            }

            let taskDetail = try JSONDecoder().decode(TaskDetail.self, from: data)
            guard selectedTask?.taskId == taskId else { return taskDetail }

            selectedTask = taskDetail
            upsertTaskSummary(from: taskDetail)
            return taskDetail
        } catch {
            print("Failed to refresh selected task detail for \(taskId): \(error)")
            return nil
        }
    }

    private func upsertTaskSummary(from task: TaskDetail) {
        let counts = businessSubtaskProgress(in: task.subtasks)
        let progress = counts.total > 0
            ? Double(counts.completed) / Double(counts.total)
            : (isTerminalStatus(task.status) ? 1.0 : 0.0)
        let summary = TaskSummary(
            taskId: task.taskId,
            description: task.description,
            status: task.status,
            progress: progress,
            completedCount: counts.completed,
            totalCount: counts.total,
            projectDir: task.projectDir,
            ownerAgent: task.ownerAgent
        )

        if let index = tasks.firstIndex(where: { $0.taskId == task.taskId }) {
            tasks[index] = summary
        } else {
            tasks.insert(summary, at: 0)
        }
    }

    private func isTerminalStatus(_ status: String) -> Bool {
        ["completed", "completed_with_failures", "failed", "cancelled"].contains(status)
    }

    private func isOriginalBusinessSubtaskId(_ subtaskId: String) -> Bool {
        if subtaskId.hasSuffix("-decompose") { return false }
        if subtaskId.hasPrefix("st-quality-") { return false }
        if subtaskId.contains("-integration-fix") { return false }
        if subtaskId.range(of: "-(?:fix-[0-9]+|v[0-9]+)$", options: .regularExpression) != nil {
            return false
        }
        return true
    }

    private func businessSubtaskProgress(in subtasks: [SubtaskDetail]) -> (completed: Int, total: Int) {
        let businessSubtasks = subtasks.filter { isOriginalBusinessSubtaskId($0.subtaskId) }
        return (
            completed: businessSubtasks.filter { $0.status == "completed" }.count,
            total: businessSubtasks.count
        )
    }

    private func businessSubtaskProgress(in subtasks: [PollSubtaskStatus]) -> (completed: Int, total: Int) {
        let businessSubtasks = subtasks.filter { isOriginalBusinessSubtaskId($0.subtask_id) }
        return (
            completed: businessSubtasks.filter { $0.status == "completed" }.count,
            total: businessSubtasks.count
        )
    }

    @MainActor
    private func updateTaskFromPollResponse(_ task: TaskDetail, _ pollData: PollStatusResponse) {
        // With persistence, backend returns complete subtask data including fix subtasks.
        // Use poll data directly as the source of truth.
        let updatedSubtasks = pollData.subtasks.map { ps in
            let existingSubtask = task.subtasks.first(where: { $0.subtaskId == ps.subtask_id })

            return SubtaskDetail(
                subtaskId: ps.subtask_id,
                description: ps.description,
                agentId: ps.agent_id,
                status: ps.status,
                progress: ps.progress,
                outputFile: existingSubtask?.outputFile,
                duration: existingSubtask?.duration,
                errorMessage: existingSubtask?.errorMessage,
                fixPlan: existingSubtask?.fixPlan,
                waveNumber: ps.wave_number,
                ownerDecision: existingSubtask?.ownerDecision,
                waitingOnDependencies: ps.waiting_on_dependencies ?? existingSubtask?.waitingOnDependencies ?? [],
                blockedReason: ps.blocked_reason ?? existingSubtask?.blockedReason,
                runningForSeconds: ps.running_for_seconds ?? existingSubtask?.runningForSeconds
            )
        }

        let updatedWaves: [WaveDetail] = (pollData.waves ?? []).map { pw in
            let waveSubtasks = updatedSubtasks.filter { $0.waveNumber == pw.wave_number }
            let existingWave = task.waves.first(where: { $0.waveId == pw.wave_id })
            return WaveDetail(
                waveId: pw.wave_id,
                waveNumber: pw.wave_number,
                subtasks: waveSubtasks,
                status: pw.status,
                isBlocked: pw.is_blocked ?? existingWave?.isBlocked ?? false,
                governanceStatus: pw.governance_status ?? existingWave?.governanceStatus,
                blockedByWave: pw.blocked_by_wave ?? existingWave?.blockedByWave,
                isRevalidating: pw.is_revalidating ?? existingWave?.isRevalidating ?? false,
                ownerDecision: pw.owner_decision ?? existingWave?.ownerDecision,
                fixRounds: existingWave?.fixRounds
            )
        }

        if selectedTask?.taskId == task.taskId {
            selectedTask = TaskDetail(
                taskId: task.taskId,
                description: task.description,
                status: pollData.status,
                ownerAgent: task.ownerAgent,
                allowedSubtaskAgents: task.allowedSubtaskAgents,
                projectDir: task.projectDir,
                subtasks: updatedSubtasks,
                waves: updatedWaves,
                artifacts: task.artifacts,
                artifactVersions: task.artifactVersions,
                ownerSessionId: task.ownerSessionId,
                lastOwnerDecision: task.lastOwnerDecision,
                error: task.error,
                hasRequirementManifest: task.hasRequirementManifest,
                qualityHealth: task.qualityHealth,
                deliveryReport: task.deliveryReport
            )
        }

        if let index = tasks.firstIndex(where: { $0.taskId == task.taskId }) {
            let counts = businessSubtaskProgress(in: pollData.subtasks)
            tasks[index] = TaskSummary(
                taskId: task.taskId,
                description: task.description,
                status: pollData.status,
                progress: pollData.progress,
                completedCount: counts.completed,
                totalCount: counts.total,
                projectDir: task.projectDir,
                ownerAgent: task.ownerAgent
            )
        }
    }

    /// P0-5: Initial polling after task submission, checking every 2s for decomposing exit.
    /// Polls for up to 30 seconds (15 attempts), covering cases where the task switches
    /// to running before the SSE connection is established.
    private func startInitialPolling(for taskId: String) {
        initialPollingTask?.cancel()
        initialPollingTask = Task { @MainActor [weak self] in
            guard let self = self, let baseURL = self.baseURL else { return }
            for _ in 0..<15 {
                if Task.isCancelled { return }
                // Stop if SSE already pushed a non-decomposing status.
                if let task = self.selectedTask, task.taskId == taskId, task.status != "decomposing" {
                    return
                }
                do {
                    let url = baseURL.appendingPathComponent("api/tasks/\(taskId)")
                    let (data, _) = try await URLSession.shared.data(from: url)
                    let taskDetail = try JSONDecoder().decode(TaskDetail.self, from: data)
                    if taskDetail.status != "decomposing" {
                        // The task left decomposing; update selectedTask to trigger DAG display.
                        self.selectedTask = taskDetail
                        self.upsertTaskSummary(from: taskDetail)
                        return
                    }
                } catch {
                    // Ignore transient polling errors.
                }
                try? await Task.sleep(nanoseconds: 2_000_000_000)  // 2s
            }
        }
    }

    private func stopSSE() {
        sseTask?.cancel()
        sseTask = nil
        pollingTask?.cancel()
        pollingTask = nil
        initialPollingTask?.cancel()
        initialPollingTask = nil
        detailPollingTask?.cancel()
        detailPollingTask = nil
        reconnectAttempts = 0
    }

    private func updateSelectedTaskStatus(taskId: String, status: String) {
        guard let task = selectedTask, task.taskId == taskId else { return }
        selectedTask = TaskDetail(
            taskId: task.taskId,
            description: task.description,
            status: status,
            ownerAgent: task.ownerAgent,
            allowedSubtaskAgents: task.allowedSubtaskAgents,
            projectDir: task.projectDir,
            subtasks: task.subtasks,
            waves: task.waves,
            artifacts: task.artifacts,
            artifactVersions: task.artifactVersions,
            ownerSessionId: task.ownerSessionId,
            lastOwnerDecision: task.lastOwnerDecision,
            error: task.error,
            hasRequirementManifest: task.hasRequirementManifest,
            qualityHealth: task.qualityHealth,
            deliveryReport: task.deliveryReport
        )
    }

    private func updateTaskStatus(taskId: String, status: String) {
        if let task = selectedTask, task.taskId == taskId {
            selectedTask = TaskDetail(
                taskId: task.taskId,
                description: task.description,
                status: status,
                ownerAgent: task.ownerAgent,
                allowedSubtaskAgents: task.allowedSubtaskAgents,
                projectDir: task.projectDir,
                subtasks: task.subtasks,
                waves: task.waves,
                artifacts: task.artifacts,
                artifactVersions: task.artifactVersions,
                ownerSessionId: task.ownerSessionId,
                lastOwnerDecision: task.lastOwnerDecision,
                error: task.error,
                hasRequirementManifest: task.hasRequirementManifest,
                qualityHealth: task.qualityHealth,
                deliveryReport: task.deliveryReport
            )
        }

        if let index = tasks.firstIndex(where: { $0.taskId == taskId }) {
            let oldTask = tasks[index]
            tasks[index] = TaskSummary(
                taskId: taskId,
                description: oldTask.description,
                status: status,
                progress: oldTask.progress,
                completedCount: oldTask.completedCount,
                totalCount: oldTask.totalCount,
                projectDir: oldTask.projectDir,
                ownerAgent: oldTask.ownerAgent,
                deliveryMode: oldTask.deliveryMode
            )
        }
    }

    deinit {
        stopSSE()
    }
}
