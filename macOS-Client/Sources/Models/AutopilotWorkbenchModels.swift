import Foundation

struct AutopilotEvidenceTarget: Equatable, Hashable {
    let runID: String
    let evidenceRoute: String

    init?(runID rawRunID: String?, evidenceRoute rawEvidenceRoute: String?) {
        guard let runID = rawRunID?.trimmingCharacters(in: .whitespacesAndNewlines),
              let evidenceRoute = rawEvidenceRoute?.trimmingCharacters(in: .whitespacesAndNewlines),
              !runID.isEmpty,
              !evidenceRoute.isEmpty,
              runID.unicodeScalars.allSatisfy({
                  CharacterSet.alphanumerics.contains($0) || "-_.:".unicodeScalars.contains($0)
              }),
              evidenceRoute == "run://\(runID)/evidence"
                || evidenceRoute == "/api/autopilot/runs/\(runID)/evidence"
        else {
            return nil
        }
        self.runID = runID
        self.evidenceRoute = evidenceRoute
    }

    var backendPath: String {
        "/api/autopilot/runs/\(runID)/evidence"
    }
}

struct AutopilotWorkbenchSnapshot: Decodable, Equatable {
    let schemaVersion: String
    let status: String
    let generatedAt: String?
    let summary: AutopilotWorkbenchSummary
    let statusReasons: [String]
    let sections: [String: AutopilotWorkbenchSection]
    let actions: [AutopilotWorkbenchAction]
    let endpoints: [String: String]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case status
        case generatedAt = "generated_at"
        case summary
        case statusReasons = "status_reasons"
        case sections
        case actions
        case endpoints
    }

    var needsAttention: Bool {
        status != "passed"
            || summary.failedRunCount > 0
            || summary.pendingMemoryCount > 0
            || summary.pendingTriggerCount > 0
            || summary.promotionReadyCount > 0
            || !summary.schedulerRunning
            || summary.selfIterationStatus != "active"
            || summary.agentInteropE2EStatus != "passed"
    }
}

struct AutopilotWorkbenchSummary: Decodable, Equatable {
    let runCount: Int
    let completedRunCount: Int
    let failedRunCount: Int
    let pendingTriggerCount: Int
    let registeredTriggerCount: Int
    let activeTriggerCount: Int
    let schedulerRunning: Bool
    let selfIterationStatus: String
    let capabilityReadyCount: Int
    let registryHealthStatus: String
    let pendingMemoryCount: Int
    let promotionReadyCount: Int
    let autopilotAvailable: Bool
    let ecosystemRouteCount: Int
    let ecosystemReadyRouteCount: Int
    let externalAgentCount: Int
    let healthyExternalAgentCount: Int
    let agentPluginCount: Int
    let readyAgentPluginCount: Int
    let agentPluginContextPackCount: Int
    let agentInteropE2EStatus: String

    enum CodingKeys: String, CodingKey {
        case runCount = "run_count"
        case completedRunCount = "completed_run_count"
        case failedRunCount = "failed_run_count"
        case pendingTriggerCount = "pending_trigger_count"
        case registeredTriggerCount = "registered_trigger_count"
        case activeTriggerCount = "active_trigger_count"
        case schedulerRunning = "scheduler_running"
        case selfIterationStatus = "self_iteration_status"
        case capabilityReadyCount = "capability_ready_count"
        case registryHealthStatus = "registry_health_status"
        case pendingMemoryCount = "pending_memory_count"
        case promotionReadyCount = "promotion_ready_count"
        case autopilotAvailable = "autopilot_available"
        case ecosystemRouteCount = "ecosystem_route_count"
        case ecosystemReadyRouteCount = "ecosystem_ready_route_count"
        case externalAgentCount = "external_agent_count"
        case healthyExternalAgentCount = "healthy_external_agent_count"
        case agentPluginCount = "agent_plugin_count"
        case readyAgentPluginCount = "ready_agent_plugin_count"
        case agentPluginContextPackCount = "agent_plugin_context_pack_count"
        case agentInteropE2EStatus = "agent_interop_e2e_status"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        runCount = try container.decodeIfPresent(Int.self, forKey: .runCount) ?? 0
        completedRunCount = try container.decodeIfPresent(Int.self, forKey: .completedRunCount) ?? 0
        failedRunCount = try container.decodeIfPresent(Int.self, forKey: .failedRunCount) ?? 0
        pendingTriggerCount = try container.decodeIfPresent(Int.self, forKey: .pendingTriggerCount) ?? 0
        registeredTriggerCount = try container.decodeIfPresent(Int.self, forKey: .registeredTriggerCount) ?? 0
        activeTriggerCount = try container.decodeIfPresent(Int.self, forKey: .activeTriggerCount) ?? 0
        schedulerRunning = try container.decodeIfPresent(Bool.self, forKey: .schedulerRunning) ?? false
        selfIterationStatus = try container.decodeIfPresent(String.self, forKey: .selfIterationStatus) ?? "unknown"
        capabilityReadyCount = try container.decodeIfPresent(Int.self, forKey: .capabilityReadyCount) ?? 0
        registryHealthStatus = try container.decodeIfPresent(String.self, forKey: .registryHealthStatus) ?? "unknown"
        pendingMemoryCount = try container.decodeIfPresent(Int.self, forKey: .pendingMemoryCount) ?? 0
        promotionReadyCount = try container.decodeIfPresent(Int.self, forKey: .promotionReadyCount) ?? 0
        autopilotAvailable = try container.decodeIfPresent(Bool.self, forKey: .autopilotAvailable) ?? false
        ecosystemRouteCount = try container.decodeIfPresent(Int.self, forKey: .ecosystemRouteCount) ?? 0
        ecosystemReadyRouteCount = try container.decodeIfPresent(Int.self, forKey: .ecosystemReadyRouteCount) ?? 0
        externalAgentCount = try container.decodeIfPresent(Int.self, forKey: .externalAgentCount) ?? 0
        healthyExternalAgentCount = try container.decodeIfPresent(Int.self, forKey: .healthyExternalAgentCount) ?? 0
        agentPluginCount = try container.decodeIfPresent(Int.self, forKey: .agentPluginCount) ?? 0
        readyAgentPluginCount = try container.decodeIfPresent(Int.self, forKey: .readyAgentPluginCount) ?? 0
        agentPluginContextPackCount = try container.decodeIfPresent(Int.self, forKey: .agentPluginContextPackCount) ?? 0
        agentInteropE2EStatus = try container.decodeIfPresent(String.self, forKey: .agentInteropE2EStatus) ?? "not_run"
    }
}

struct AutopilotWorkbenchSection: Decodable, Equatable, Identifiable {
    let id: String
    let title: String
    let status: String
    let summary: [String: AutopilotWorkbenchJSONValue]
    let items: [AutopilotWorkbenchJSONValue]
    let endpoint: String?
}

struct AutopilotWorkbenchAction: Decodable, Equatable, Identifiable {
    let id: String
    let priority: String
    let title: String
    let reason: String
    let endpoint: String?
}

enum AutopilotWorkbenchJSONValue: Decodable, Equatable, CustomStringConvertible {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: AutopilotWorkbenchJSONValue])
    case array([AutopilotWorkbenchJSONValue])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Int.self) {
            self = .number(Double(value))
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([String: AutopilotWorkbenchJSONValue].self) {
            self = .object(value)
        } else if let value = try? container.decode([AutopilotWorkbenchJSONValue].self) {
            self = .array(value)
        } else {
            self = .null
        }
    }

    var description: String {
        switch self {
        case .string(let value):
            return value
        case .number(let value):
            return value.rounded() == value ? String(Int(value)) : String(value)
        case .bool(let value):
            return value ? "true" : "false"
        case .object(let value):
            return value
                .sorted { $0.key < $1.key }
                .map { "\($0.key)=\($0.value.description)" }
                .joined(separator: ", ")
        case .array(let value):
            return value.map(\.description).joined(separator: ", ")
        case .null:
            return "-"
        }
    }

    var objectValue: [String: AutopilotWorkbenchJSONValue]? {
        if case .object(let value) = self {
            return value
        }
        return nil
    }
}
