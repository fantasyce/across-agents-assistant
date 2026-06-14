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
