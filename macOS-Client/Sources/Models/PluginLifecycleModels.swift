import Foundation

struct PluginListResponse: Decodable {
    let plugins: [AcrossPluginStatus]
}

struct AcrossPluginStatus: Decodable, Identifiable, Equatable {
    let pluginId: String
    let displayName: String
    let kind: String
    let version: String?
    let status: String
    let installed: Bool
    let available: Bool
    let probe: Bool
    let manifestExists: Bool
    let manifestPath: String
    let command: String
    let commandExists: Bool
    let paths: AcrossPluginPaths
    let install: AcrossPluginInstallInfo?
    let lifecycle: AcrossPluginLifecycle?
    let compatibility: AcrossPluginCompatibility?
    let capabilities: [String: Bool]?

    var id: String { pluginId }

    enum CodingKeys: String, CodingKey {
        case pluginId = "plugin_id"
        case displayName = "display_name"
        case kind
        case version
        case status
        case installed
        case available
        case probe
        case manifestExists = "manifest_exists"
        case manifestPath = "manifest_path"
        case command
        case commandExists = "command_exists"
        case paths
        case install
        case lifecycle
        case compatibility
        case capabilities
    }

    var supportsAgentLoopRuntime: Bool {
        capabilities?["agentLoopRuntime"] == true
    }

    var supportsAgentLoopV2: Bool {
        capabilities?["agentLoopV2"] == true
    }

    var supportsCheckpoints: Bool {
        capabilities?["checkpoints"] == true
    }

    var supportsMemoryHooks: Bool {
        capabilities?["memoryHooks"] == true
    }

    var supportsDynamicLoopPlanning: Bool {
        capabilities?["dynamicLoopPlanning"] == true
    }

    var supportsRemediationDispatch: Bool {
        capabilities?["remediationDispatch"] == true
    }
}

struct AcrossPluginPaths: Decodable, Equatable {
    let home: String
    let plugin: String
    let bin: String
    let data: String
    let config: String
    let run: String
    let logs: String
    let cache: String
}

struct AcrossPluginInstallInfo: Decodable, Equatable {
    let installable: Bool?
    let command: String?
    let installDir: String?
    let source: String?

    enum CodingKeys: String, CodingKey {
        case installable
        case command
        case installDir = "install_dir"
        case source
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let camelContainer = try? decoder.container(keyedBy: PluginInstallCamelKeys.self)
        installable = try container.decodeIfPresent(Bool.self, forKey: .installable)
        command = try container.decodeIfPresent(String.self, forKey: .command)
        source = try container.decodeIfPresent(String.self, forKey: .source)
        installDir = try container.decodeIfPresent(String.self, forKey: .installDir)
            ?? (try camelContainer?.decodeIfPresent(String.self, forKey: .installDir))
    }

    private enum PluginInstallCamelKeys: String, CodingKey {
        case installDir
    }
}

struct AcrossPluginLifecycle: Decodable, Equatable {
    let actions: [String]
    let preservesDataOnUninstall: Bool?
    let installSource: String?

    enum CodingKeys: String, CodingKey {
        case actions
        case preservesDataOnUninstall
        case installSource
    }
}

struct AcrossPluginCompatibility: Decodable, Equatable {
    let requiredHostVersion: String?
    let pluginApiVersion: String?
    let compatiblePluginApiVersions: [String]?
}

struct PluginActionRequest: Encodable {
    let action: String
}

struct AcrossMemoryListResponse: Decodable {
    let memories: [AcrossMemoryEntry]
}

struct AcrossMemoryMutationResponse: Decodable {
    let memory: AcrossMemoryEntry
}

struct AcrossMemoryForgetResponse: Decodable {
    let forgotten: Bool
    let id: String
}

struct AcrossMemoryEntry: Decodable, Identifiable, Equatable {
    let id: String
    let scope: String
    let type: String
    let text: String
    let tags: [String]?
    let status: String
    let visibility: String?
    let projectName: String?
    let createdAt: String?
    let updatedAt: String?
}

struct AcrossMemoryRememberRequest: Encodable {
    let text: String
    let projectRoot: String?
    let scope: String
    let type: String
    let status: String
    let tags: [String]
}

struct AcrossMemoryStatusRequest: Encodable {
    let status: String
}

struct AgentLoopStartRequest: Encodable {
    let goal: String
    let projectDir: String?
    let agent: String
    let maxTurns: Int

    enum CodingKeys: String, CodingKey {
        case goal
        case projectDir = "project_dir"
        case agent
        case maxTurns = "max_turns"
    }
}

struct AgentLoopRunResponse: Decodable, Equatable {
    let loopId: String
    let goal: String
    let status: String
    let agent: String?
    let turnCount: Int?
    let checkpointCount: Int?
    let finalOutput: String?
    let steps: [AgentLoopStep]

    enum CodingKeys: String, CodingKey {
        case loopId = "loop_id"
        case goal
        case status
        case agent
        case turnCount = "turn_count"
        case checkpointCount = "checkpoint_count"
        case finalOutput = "final_output"
        case steps
    }
}

struct AgentLoopHealthResponse: Decodable, Equatable {
    let loopId: String
    let status: String
    let currentActionType: String?
    let currentStepId: String?
    let pendingApproval: AgentLoopPendingApproval?
    let lease: AgentLoopLeaseHealth?
    let detachedDispatchCount: Int?
    let recentFailureTypes: [String: Int]?
    let executableActions: [String]?
    let cancellationRequested: Bool?
    let cancelAckPending: Bool?

    enum CodingKeys: String, CodingKey {
        case loopId = "loop_id"
        case status
        case currentActionType = "current_action_type"
        case currentStepId = "current_step_id"
        case pendingApproval = "pending_approval"
        case lease
        case detachedDispatchCount = "detached_dispatch_count"
        case recentFailureTypes = "recent_failure_types"
        case executableActions = "executable_actions"
        case cancellationRequested = "cancellation_requested"
        case cancelAckPending = "cancel_ack_pending"
    }

    var recentFailureCount: Int {
        recentFailureTypes?.values.reduce(0, +) ?? 0
    }

    var hasStaleLease: Bool {
        lease?.expired == true
    }

    var needsAttention: Bool {
        hasStaleLease || cancellationRequested == true || cancelAckPending == true || recentFailureCount > 0
    }
}

struct AgentLoopPendingApproval: Decodable, Equatable {
    let stepId: String?
    let actionId: String?
    let actionType: String?
    let title: String?
    let approvalStatus: String?

    enum CodingKeys: String, CodingKey {
        case stepId = "step_id"
        case actionId = "action_id"
        case actionType = "action_type"
        case title
        case approvalStatus = "approval_status"
    }
}

struct AgentLoopLeaseHealth: Decodable, Equatable {
    let active: Bool?
    let leaseId: String?
    let leaseSeconds: Double?
    let heartbeatAt: Double?
    let expiresAt: Double?
    let remainingSeconds: Double?
    let expired: Bool?
    let renewalCount: Int?

    enum CodingKeys: String, CodingKey {
        case active
        case leaseId = "lease_id"
        case leaseSeconds = "lease_seconds"
        case heartbeatAt = "heartbeat_at"
        case expiresAt = "expires_at"
        case remainingSeconds = "remaining_seconds"
        case expired
        case renewalCount = "renewal_count"
    }
}

enum AgentLoopJSONValue: Decodable, Equatable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: AgentLoopJSONValue])
    case array([AgentLoopJSONValue])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([String: AgentLoopJSONValue].self) {
            self = .object(value)
        } else if let value = try? container.decode([AgentLoopJSONValue].self) {
            self = .array(value)
        } else {
            self = .null
        }
    }

    var stringValue: String? {
        switch self {
        case .string(let value):
            return value
        case .number(let value):
            return value.rounded() == value ? String(Int(value)) : String(value)
        case .bool(let value):
            return value ? "true" : "false"
        case .object, .array, .null:
            return nil
        }
    }
}

struct AgentLoopEventResponse: Decodable, Equatable {
    let type: String
    let loopId: String?
    let timestamp: Double?
    let payload: [String: AgentLoopJSONValue]?

    enum CodingKeys: String, CodingKey {
        case type
        case loopId = "loop_id"
        case timestamp
        case payload
    }

    var compactLabel: String {
        let event = type
            .replacingOccurrences(of: "loop.", with: "")
            .replacingOccurrences(of: ".", with: " ")
            .replacingOccurrences(of: "_", with: " ")
        if let detail = payloadDetail {
            return "\(event): \(detail)"
        }
        return event
    }

    private var payloadDetail: String? {
        for key in ["failure_type", "action_type", "status", "reason"] {
            if let value = payload?[key]?.stringValue, !value.isEmpty {
                return value.replacingOccurrences(of: "_", with: " ")
            }
        }
        return nil
    }
}

struct AgentLoopStep: Decodable, Equatable {
    let status: String?
    let action: AgentLoopAction?
}

struct AgentLoopAction: Decodable, Equatable {
    let actionId: String?
    let type: String?
    let requiresApproval: Bool?
    let approvalStatus: String?

    enum CodingKeys: String, CodingKey {
        case actionId = "action_id"
        case type
        case requiresApproval = "requires_approval"
        case approvalStatus = "approval_status"
    }
}
