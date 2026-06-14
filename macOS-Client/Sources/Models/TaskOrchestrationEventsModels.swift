import Foundation

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
