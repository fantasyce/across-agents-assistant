import Foundation

enum ExecutionTrajectoryTaskStatus: String, Codable, Equatable {
    case pending
    case queued
    case running
    case completed
    case completedWithFailures = "completed_with_failures"
    case failed
    case blocked
    case cancelled
    case unknown

    init(from decoder: Decoder) throws {
        let value = try decoder.singleValueContainer().decode(String.self)
        self = Self(rawValue: value) ?? .unknown
    }
}

enum ExecutionTrajectorySource: String, Codable, Equatable {
    case orchestratorEvidence = "orchestrator_evidence"
    case workerProjection = "worker_projection"
    case localTaskObservability = "local_task_observability"
    case unknown

    init(from decoder: Decoder) throws {
        let value = try decoder.singleValueContainer().decode(String.self)
        self = Self(rawValue: value) ?? .unknown
    }
}

enum ExecutionTrajectoryReceiptIntegrity: String, Codable, Equatable {
    case hashValid = "hash_valid"
    case invalid
    case unsupported
    case missing
    case unknown

    init(from decoder: Decoder) throws {
        let value = try decoder.singleValueContainer().decode(String.self)
        self = Self(rawValue: value) ?? .unknown
    }
}

enum ExecutionTrajectoryCategory: String, Codable, Equatable {
    case task
    case contract
    case agentLoop = "agent_loop"
    case subtask
    case sandbox
    case approval
    case quality
    case artifact
    case other
    case unknown

    init(from decoder: Decoder) throws {
        let value = try decoder.singleValueContainer().decode(String.self)
        self = Self(rawValue: value) ?? .unknown
    }
}

enum ExecutionTrajectoryPhase: String, Codable, Equatable {
    case created
    case started
    case checkpoint
    case completed
    case failed
    case blocked
    case cancelled
    case other
    case unknown

    init(from decoder: Decoder) throws {
        let value = try decoder.singleValueContainer().decode(String.self)
        self = Self(rawValue: value) ?? .unknown
    }
}

enum ExecutionTrajectoryItemStatus: String, Codable, Equatable {
    case recorded
    case running
    case succeeded
    case failed
    case blocked
    case cancelled
    case unknown

    init(from decoder: Decoder) throws {
        let value = try decoder.singleValueContainer().decode(String.self)
        self = Self(rawValue: value) ?? .unknown
    }
}

enum ExecutionTrajectoryEventIntegrity: String, Codable, Equatable {
    case clean
    case degraded
    case unknown

    init(from decoder: Decoder) throws {
        let value = try decoder.singleValueContainer().decode(String.self)
        self = Self(rawValue: value) ?? .unknown
    }
}

struct TaskExecutionTrajectorySummary: Codable, Equatable {
    let sourceEventCount: Int
    let normalizedEventCount: Int
    let firstSequence: Int?
    let lastSequence: Int?
    let startedAt: Double?
    let completedAt: Double?
    let terminalStatus: ExecutionTrajectoryTaskStatus

    enum CodingKeys: String, CodingKey {
        case sourceEventCount = "source_event_count"
        case normalizedEventCount = "normalized_event_count"
        case firstSequence = "first_sequence"
        case lastSequence = "last_sequence"
        case startedAt = "started_at"
        case completedAt = "completed_at"
        case terminalStatus = "terminal_status"
    }
}

struct TaskExecutionTrajectoryPage: Codable, Equatable {
    let offset: Int
    let limit: Int
    let returned: Int
    let total: Int
    let nextOffset: Int?
    let hasMore: Bool

    enum CodingKeys: String, CodingKey {
        case offset
        case limit
        case returned
        case total
        case nextOffset = "next_offset"
        case hasMore = "has_more"
    }
}

struct TaskExecutionTrajectoryReceipt: Codable, Equatable {
    let schemaVersion: String?
    let integrityState: ExecutionTrajectoryReceiptIntegrity
    let digestAlgorithm: String
    let digestField: String?
    let digest: String?
    let verdict: String
    let reason: String

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case integrityState = "integrity_state"
        case digestAlgorithm = "digest_algorithm"
        case digestField = "digest_field"
        case digest
        case verdict
        case reason
    }
}

struct TaskExecutionTrajectoryItem: Codable, Equatable, Identifiable {
    let eventId: String
    let sequence: Int
    let timestamp: Double?
    let eventType: String
    let category: ExecutionTrajectoryCategory
    let phase: ExecutionTrajectoryPhase
    let status: ExecutionTrajectoryItemStatus
    let title: String
    let scopeKind: String
    let scopeId: String
    let actor: String?
    let evidenceRefs: [String]?

    var id: String { eventId }

    enum CodingKeys: String, CodingKey {
        case eventId = "event_id"
        case sequence
        case timestamp
        case eventType = "event_type"
        case category
        case phase
        case status
        case title
        case scopeKind = "scope_kind"
        case scopeId = "scope_id"
        case actor
        case evidenceRefs = "evidence_refs"
    }
}

struct TaskExecutionTrajectoryAudit: Codable, Equatable {
    let readOnly: Bool
    let mutationsTriggered: Bool
    let repairOrResumeTriggered: Bool
    let secretsRedacted: Bool
    let receiptCheckedBeforeRedaction: Bool
    let rawPayloadExposed: Bool
    let eventIntegrityState: ExecutionTrajectoryEventIntegrity
    let omittedEventCount: Int
    let conflictingDuplicateCount: Int
    let truncated: Bool

    enum CodingKeys: String, CodingKey {
        case readOnly = "read_only"
        case mutationsTriggered = "mutations_triggered"
        case repairOrResumeTriggered = "repair_or_resume_triggered"
        case secretsRedacted = "secrets_redacted"
        case receiptCheckedBeforeRedaction = "receipt_checked_before_redaction"
        case rawPayloadExposed = "raw_payload_exposed"
        case eventIntegrityState = "event_integrity_state"
        case omittedEventCount = "omitted_event_count"
        case conflictingDuplicateCount = "conflicting_duplicate_count"
        case truncated
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        readOnly = try container.decode(Bool.self, forKey: .readOnly)
        mutationsTriggered = try container.decode(Bool.self, forKey: .mutationsTriggered)
        repairOrResumeTriggered = try container.decode(Bool.self, forKey: .repairOrResumeTriggered)
        secretsRedacted = try container.decode(Bool.self, forKey: .secretsRedacted)
        receiptCheckedBeforeRedaction = try container.decode(Bool.self, forKey: .receiptCheckedBeforeRedaction)
        rawPayloadExposed = try container.decode(Bool.self, forKey: .rawPayloadExposed)
        eventIntegrityState = try container.decode(ExecutionTrajectoryEventIntegrity.self, forKey: .eventIntegrityState)
        omittedEventCount = try container.decode(Int.self, forKey: .omittedEventCount)
        conflictingDuplicateCount = try container.decode(Int.self, forKey: .conflictingDuplicateCount)
        truncated = try container.decode(Bool.self, forKey: .truncated)

        guard
            readOnly,
            mutationsTriggered == false,
            repairOrResumeTriggered == false,
            secretsRedacted,
            receiptCheckedBeforeRedaction,
            rawPayloadExposed == false
        else {
            throw DecodingError.dataCorruptedError(
                forKey: .readOnly,
                in: container,
                debugDescription: "unsafe execution trajectory audit"
            )
        }
    }
}

struct TaskExecutionTrajectory: Codable, Equatable, Identifiable {
    static let currentSchemaVersion = "across-execution-trajectory/1.0"

    let schemaVersion: String
    let generatedAt: Double
    let taskId: String
    let taskStatus: ExecutionTrajectoryTaskStatus
    let source: ExecutionTrajectorySource
    let summary: TaskExecutionTrajectorySummary
    let page: TaskExecutionTrajectoryPage
    let receipt: TaskExecutionTrajectoryReceipt
    let items: [TaskExecutionTrajectoryItem]
    let audit: TaskExecutionTrajectoryAudit

    var id: String { taskId }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case generatedAt = "generated_at"
        case taskId = "task_id"
        case taskStatus = "task_status"
        case source
        case summary
        case page
        case receipt
        case items
        case audit
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decode(String.self, forKey: .schemaVersion)
        guard schemaVersion == Self.currentSchemaVersion else {
            throw DecodingError.dataCorruptedError(
                forKey: .schemaVersion,
                in: container,
                debugDescription: "unsupported execution trajectory schema"
            )
        }
        generatedAt = try container.decode(Double.self, forKey: .generatedAt)
        taskId = try container.decode(String.self, forKey: .taskId)
        taskStatus = try container.decode(ExecutionTrajectoryTaskStatus.self, forKey: .taskStatus)
        source = try container.decode(ExecutionTrajectorySource.self, forKey: .source)
        summary = try container.decode(TaskExecutionTrajectorySummary.self, forKey: .summary)
        page = try container.decode(TaskExecutionTrajectoryPage.self, forKey: .page)
        receipt = try container.decode(TaskExecutionTrajectoryReceipt.self, forKey: .receipt)
        items = try container.decode([TaskExecutionTrajectoryItem].self, forKey: .items)
        audit = try container.decode(TaskExecutionTrajectoryAudit.self, forKey: .audit)
    }

    func prettyPublicJSON() throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        return try encoder.encode(self)
    }

    static func exportFileName(taskId: String) -> String {
        let mapped = taskId.unicodeScalars.map { scalar -> Character in
            if CharacterSet.alphanumerics.contains(scalar) || scalar == "_" || scalar == "-" {
                return Character(String(scalar))
            }
            return "-"
        }
        let compact = String(mapped)
            .split(separator: "-", omittingEmptySubsequences: true)
            .joined(separator: "-")
        let safe = compact.isEmpty ? "task" : String(compact.prefix(96))
        return "\(safe)-execution-trajectory.json"
    }
}
