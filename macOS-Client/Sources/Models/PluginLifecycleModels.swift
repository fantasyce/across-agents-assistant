import Foundation

struct PluginListResponse: Decodable {
    let plugins: [AcrossPluginStatus]
}

struct AcrossPluginCapabilityManifest: Decodable, Equatable {
    let capabilities: [AcrossPluginCapabilityDescriptor]
    let achievements: [AcrossPluginAchievementDescriptor]

    enum CodingKeys: String, CodingKey {
        case capabilities
        case entries
        case ready
        case achievements
    }

    init(
        capabilities: [AcrossPluginCapabilityDescriptor],
        achievements: [AcrossPluginAchievementDescriptor] = []
    ) {
        self.capabilities = capabilities
        self.achievements = achievements
    }

    init(from decoder: Decoder) throws {
        if let entries = try? decoder.singleValueContainer().decode([AcrossPluginCapabilityDescriptor].self) {
            capabilities = entries
            achievements = []
            return
        }

        let container = try decoder.container(keyedBy: CodingKeys.self)
        capabilities = (try? container.decode([AcrossPluginCapabilityDescriptor].self, forKey: .capabilities))
            ?? (try? container.decode([AcrossPluginCapabilityDescriptor].self, forKey: .entries))
            ?? (try? container.decode([AcrossPluginCapabilityDescriptor].self, forKey: .ready))
            ?? []
        achievements = (try? container.decode([AcrossPluginAchievementDescriptor].self, forKey: .achievements)) ?? []
    }
}

struct AcrossPluginCapabilityDescriptor: Decodable, Equatable, Identifiable {
    let id: String
    let displayName: String?
    let summary: String?
    let systemImage: String?
    let category: String?
    let status: String?
    let verified: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case capabilityId = "capability_id"
        case name
        case displayName = "display_name"
        case title
        case summary
        case description
        case systemImage = "system_image"
        case icon
        case category
        case status
        case verified
        case available
        case enabled
    }

    init(
        id: String,
        displayName: String? = nil,
        summary: String? = nil,
        systemImage: String? = nil,
        category: String? = nil,
        status: String? = nil,
        verified: Bool
    ) {
        self.id = id
        self.displayName = displayName
        self.summary = summary
        self.systemImage = systemImage
        self.category = category
        self.status = status
        self.verified = verified
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decodeIfPresent(String.self, forKey: .id)
            ?? container.decodeIfPresent(String.self, forKey: .capabilityId)
            ?? ""
        displayName = try container.decodeIfPresent(String.self, forKey: .displayName)
            ?? container.decodeIfPresent(String.self, forKey: .title)
            ?? container.decodeIfPresent(String.self, forKey: .name)
        summary = try container.decodeIfPresent(String.self, forKey: .summary)
            ?? container.decodeIfPresent(String.self, forKey: .description)
        systemImage = try container.decodeIfPresent(String.self, forKey: .systemImage)
            ?? container.decodeIfPresent(String.self, forKey: .icon)
        category = try container.decodeIfPresent(String.self, forKey: .category)
        status = try container.decodeIfPresent(String.self, forKey: .status)
        let explicit = try container.decodeIfPresent(Bool.self, forKey: .verified)
            ?? container.decodeIfPresent(Bool.self, forKey: .available)
            ?? container.decodeIfPresent(Bool.self, forKey: .enabled)
        verified = explicit ?? ["ready", "verified", "passed", "available"].contains(status?.lowercased() ?? "")
    }
}

struct AcrossPluginAchievementDescriptor: Decodable, Equatable, Identifiable {
    let id: String
    let displayName: String?
    let summary: String?
    let systemImage: String?
    let earned: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case achievementId = "achievement_id"
        case name
        case displayName = "display_name"
        case title
        case summary
        case description
        case systemImage = "system_image"
        case icon
        case earned
        case unlocked
        case verified
    }

    init(
        id: String,
        displayName: String? = nil,
        summary: String? = nil,
        systemImage: String? = nil,
        earned: Bool
    ) {
        self.id = id
        self.displayName = displayName
        self.summary = summary
        self.systemImage = systemImage
        self.earned = earned
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decodeIfPresent(String.self, forKey: .id)
            ?? container.decodeIfPresent(String.self, forKey: .achievementId)
            ?? ""
        displayName = try container.decodeIfPresent(String.self, forKey: .displayName)
            ?? container.decodeIfPresent(String.self, forKey: .title)
            ?? container.decodeIfPresent(String.self, forKey: .name)
        summary = try container.decodeIfPresent(String.self, forKey: .summary)
            ?? container.decodeIfPresent(String.self, forKey: .description)
        systemImage = try container.decodeIfPresent(String.self, forKey: .systemImage)
            ?? container.decodeIfPresent(String.self, forKey: .icon)
        earned = try container.decodeIfPresent(Bool.self, forKey: .earned)
            ?? container.decodeIfPresent(Bool.self, forKey: .unlocked)
            ?? container.decodeIfPresent(Bool.self, forKey: .verified)
            ?? false
    }
}

struct AcrossPluginStatus: Decodable, Identifiable, Equatable {
    let pluginId: String
    let displayName: String
    let kind: String
    let version: String?
    let status: String
    let installed: Bool
    let available: Bool
    let integrityOkay: Bool
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
    let capabilityManifest: AcrossPluginCapabilityManifest?

    var id: String { pluginId }

    enum CodingKeys: String, CodingKey {
        case pluginId = "plugin_id"
        case displayName = "display_name"
        case kind
        case version
        case status
        case installed
        case available
        case integrityOkay = "integrity_ok"
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
        case capabilityManifest = "capability_manifest"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let camelContainer = try? decoder.container(keyedBy: CamelCodingKeys.self)
        pluginId = try container.decode(String.self, forKey: .pluginId)
        displayName = try container.decode(String.self, forKey: .displayName)
        kind = try container.decode(String.self, forKey: .kind)
        version = try container.decodeIfPresent(String.self, forKey: .version)
        status = try container.decode(String.self, forKey: .status)
        installed = try container.decode(Bool.self, forKey: .installed)
        available = try container.decode(Bool.self, forKey: .available)
        integrityOkay = try container.decodeIfPresent(Bool.self, forKey: .integrityOkay)
            ?? (status != "needs_repair" && available)
        probe = try container.decode(Bool.self, forKey: .probe)
        manifestExists = try container.decode(Bool.self, forKey: .manifestExists)
        manifestPath = try container.decode(String.self, forKey: .manifestPath)
        command = try container.decode(String.self, forKey: .command)
        commandExists = try container.decode(Bool.self, forKey: .commandExists)
        paths = try container.decode(AcrossPluginPaths.self, forKey: .paths)
        install = try container.decodeIfPresent(AcrossPluginInstallInfo.self, forKey: .install)
        lifecycle = try container.decodeIfPresent(AcrossPluginLifecycle.self, forKey: .lifecycle)
        compatibility = try container.decodeIfPresent(AcrossPluginCompatibility.self, forKey: .compatibility)
        let capabilityMap = try? container.decodeIfPresent([String: Bool].self, forKey: .capabilities)
        let capabilityNames = try? container.decodeIfPresent([String].self, forKey: .capabilities)
        let capabilityEntries = try? container.decodeIfPresent([AcrossPluginCapabilityDescriptor].self, forKey: .capabilities)
        if let capabilityMap {
            capabilities = capabilityMap
        } else if let capabilityNames {
            capabilities = Dictionary(uniqueKeysWithValues: capabilityNames.map { ($0, true) })
        } else if let capabilityEntries {
            capabilities = Dictionary(uniqueKeysWithValues: capabilityEntries.map { ($0.id, true) })
        } else {
            capabilities = nil
        }
        let declaredManifest = try container.decodeIfPresent(AcrossPluginCapabilityManifest.self, forKey: .capabilityManifest)
            ?? (try camelContainer?.decodeIfPresent(AcrossPluginCapabilityManifest.self, forKey: .capabilityManifest))
        if let declaredManifest {
            capabilityManifest = declaredManifest
        } else if let capabilityEntries {
            capabilityManifest = AcrossPluginCapabilityManifest(
                capabilities: capabilityEntries.map {
                    AcrossPluginCapabilityDescriptor(
                        id: $0.id,
                        displayName: $0.displayName,
                        summary: $0.summary,
                        systemImage: $0.systemImage,
                        category: $0.category,
                        status: $0.status,
                        verified: true
                    )
                }
            )
        } else {
            capabilityManifest = nil
        }
    }

    private enum CamelCodingKeys: String, CodingKey {
        case capabilityManifest
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

enum MemoryReviewTextFormatter {
    static func summary(for text: String, fallback: String = "Structured memory proposal") -> String {
        let compact = text
            .replacingOccurrences(of: "\n", with: " ")
            .replacingOccurrences(of: "\t", with: " ")
            .split(separator: " ", omittingEmptySubsequences: true)
            .joined(separator: " ")

        let looksStructured = compact.hasPrefix("{") || compact.hasPrefix("[")
        guard let data = compact.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data) else {
            return looksStructured ? fallback : String(compact.prefix(280))
        }

        var preferred: [String] = []
        var actions: [String] = []
        collect(object, preferred: &preferred, actions: &actions)

        if let value = preferred.first(where: { !$0.isEmpty }) {
            return String(value.prefix(280))
        }

        let uniqueActions = actions.reduce(into: [String]()) { result, action in
            let readable = action.replacingOccurrences(of: "_", with: " ")
            if !result.contains(readable) {
                result.append(readable)
            }
        }
        if !uniqueActions.isEmpty {
            return uniqueActions.prefix(5).joined(separator: "  ->  ")
        }
        return fallback
    }

    private static func collect(_ value: Any, preferred: inout [String], actions: inout [String]) {
        if let object = value as? [String: Any] {
            for key in ["summary", "title", "goal", "decision", "reason", "message", "text"] {
                if let text = object[key] as? String, !text.isEmpty {
                    preferred.append(text)
                }
            }
            if let action = object["action_type"] as? String, !action.isEmpty {
                actions.append(action)
            }
            for child in object.values {
                collect(child, preferred: &preferred, actions: &actions)
            }
        } else if let array = value as? [Any] {
            for child in array {
                collect(child, preferred: &preferred, actions: &actions)
            }
        }
    }
}

struct AgentLoopMemoryMetricsResponse: Decodable, Equatable {
    let schemaVersion: String?
    let candidateSchema: String?
    let totals: AgentLoopMemoryMetricsTotals?
    let byStatus: [String: Int]?
    let byScope: [String: Int]?
    let metrics: [AgentLoopMemoryMetric]?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case candidateSchema = "candidate_schema"
        case totals
        case byStatus
        case byScope
        case metrics
    }
}

struct AgentLoopMemoryMetricsTotals: Decodable, Equatable {
    let candidateCount: Int?
    let pendingCount: Int?
    let approvedCount: Int?
    let archivedCount: Int?
    let expiredCount: Int?
    let forgottenCount: Int?
    let duplicateReusedCount: Int?
    let deniedCount: Int?
    let sensitiveDeniedCount: Int?

    enum CodingKeys: String, CodingKey {
        case candidateCount = "candidate_count"
        case pendingCount = "pending_count"
        case approvedCount = "approved_count"
        case archivedCount = "archived_count"
        case expiredCount = "expired_count"
        case forgottenCount = "forgotten_count"
        case duplicateReusedCount = "duplicate_reused_count"
        case deniedCount = "denied_count"
        case sensitiveDeniedCount = "sensitive_denied_count"
    }
}

struct AgentLoopMemoryMetric: Decodable, Equatable {
    let schemaVersion: String?
    let metric: String?
    let value: Double?
    let unit: String?
    let dimensions: [String: AgentLoopJSONValue]?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case metric
        case legacyId = "id"
        case value
        case unit
        case dimensions
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion)
        metric = try container.decodeIfPresent(String.self, forKey: .metric)
            ?? (try container.decodeIfPresent(String.self, forKey: .legacyId))
        value = try container.decodeIfPresent(Double.self, forKey: .value)
        unit = try container.decodeIfPresent(String.self, forKey: .unit)
        dimensions = try container.decodeIfPresent([String: AgentLoopJSONValue].self, forKey: .dimensions)
    }

    var id: String? { metric }
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
    let cancellationCategory: String?
    let cancelAckPending: Bool?
    let budget: AgentLoopBudgetSummary?

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
        case cancellationCategory = "cancellation_category"
        case cancelAckPending = "cancel_ack_pending"
        case budget
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

struct AgentLoopEvidenceSummaryResponse: Decodable, Equatable {
    let schemaVersion: String?
    let loopId: String
    let status: String
    let eventAudit: AgentLoopEvidenceEventAudit?
    let routing: AgentLoopEvidenceRouting?
    let recovery: AgentLoopEvidenceRecovery?
    let memoryCandidates: AgentLoopEvidenceMemoryCandidates?
    let hostReleaseEvidence: AgentLoopHostReleaseEvidence?
    let budget: AgentLoopBudgetSummary?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case loopId = "loop_id"
        case status
        case eventAudit = "event_audit"
        case routing
        case recovery
        case memoryCandidates = "memory_candidates"
        case hostReleaseEvidence = "host_release_evidence"
        case budget
    }
}

struct AgentLoopEvidenceEventAudit: Decodable, Equatable {
    let eventCount: Int?
    let sequenceContiguous: Bool?
    let eventIdCoverage: Bool?
    let correlationIdCoverage: Bool?

    enum CodingKeys: String, CodingKey {
        case eventCount = "event_count"
        case sequenceContiguous = "sequence_contiguous"
        case eventIdCoverage = "event_id_coverage"
        case correlationIdCoverage = "correlation_id_coverage"
    }
}

struct AgentLoopEvidenceRouting: Decodable, Equatable {
    let schemaVersion: String?
    let routedActionCount: Int?
    let nonDefaultRouteCount: Int?
    let capabilityHintRouteCount: Int?
    let outcomes: [AgentLoopEvidenceRoutingOutcome]?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case routedActionCount = "routed_action_count"
        case nonDefaultRouteCount = "non_default_route_count"
        case capabilityHintRouteCount = "capability_hint_route_count"
        case outcomes
    }
}

struct AgentLoopEvidenceRoutingOutcome: Decodable, Equatable {
    let actionType: String?
    let status: String?
    let selectedAgent: String?
    let source: String?
    let matchedGate: String?
    let capabilityHint: String?
    let reason: String?
    let alternatives: [AgentLoopRoutingAlternative]?

    enum CodingKeys: String, CodingKey {
        case actionType = "action_type"
        case status
        case selectedAgent = "selected_agent"
        case source
        case matchedGate = "matched_gate"
        case capabilityHint = "capability_hint"
        case reason
        case alternatives
    }
}

struct AgentLoopRoutingAlternative: Decodable, Equatable {
    let agentId: String?
    let selected: Bool?
    let matched: Bool?
    let forbidden: Bool?
    let capabilityCount: Int?
    let matchedCapability: String?
    let reason: String?

    enum CodingKeys: String, CodingKey {
        case agentId = "agent_id"
        case selected
        case matched
        case forbidden
        case capabilityCount = "capability_count"
        case matchedCapability = "matched_capability"
        case reason
    }

    init(
        agentId: String?,
        selected: Bool?,
        matched: Bool? = nil,
        forbidden: Bool? = nil,
        capabilityCount: Int? = nil,
        matchedCapability: String? = nil,
        reason: String? = nil
    ) {
        self.agentId = agentId
        self.selected = selected
        self.matched = matched
        self.forbidden = forbidden
        self.capabilityCount = capabilityCount
        self.matchedCapability = matchedCapability
        self.reason = reason
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let legacy = try? decoder.container(keyedBy: LegacyCodingKeys.self)
        agentId = try container.decodeIfPresent(String.self, forKey: .agentId)
            ?? (try legacy?.decodeIfPresent(String.self, forKey: .agent))
        selected = try container.decodeIfPresent(Bool.self, forKey: .selected)
        matched = try container.decodeIfPresent(Bool.self, forKey: .matched)
        forbidden = try container.decodeIfPresent(Bool.self, forKey: .forbidden)
        capabilityCount = try container.decodeIfPresent(Int.self, forKey: .capabilityCount)
        matchedCapability = try container.decodeIfPresent(String.self, forKey: .matchedCapability)
        reason = try container.decodeIfPresent(String.self, forKey: .reason)
    }

    private enum LegacyCodingKeys: String, CodingKey {
        case agent
    }
}

struct AgentLoopEvidenceRecovery: Decodable, Equatable {
    let decisionCount: Int?
    let appliedCount: Int?
    let blockedCount: Int?
    let decisions: [AgentLoopEvidenceRecoveryDecision]?
    let recoveredSteps: [AgentLoopEvidenceRecoveredStep]?

    enum CodingKeys: String, CodingKey {
        case decisionCount = "decision_count"
        case appliedCount = "applied_count"
        case blockedCount = "blocked_count"
        case decisions
        case recoveredSteps = "recovered_steps"
    }
}

struct AgentLoopEvidenceRecoveryDecision: Decodable, Equatable {
    let eventId: String?
    let sequence: Int?
    let timestamp: Double?
    let correlationId: String?
    let stepId: String?
    let actionType: String?
    let failureType: String?
    let reason: String?
    let recoveryAction: String?
    let attempt: Int?
    let maxRetries: Int?
    let applied: Bool?
    let blockedReason: String?
    let source: String?

    enum CodingKeys: String, CodingKey {
        case eventId = "event_id"
        case sequence
        case timestamp
        case correlationId = "correlation_id"
        case stepId = "step_id"
        case actionType = "action_type"
        case failureType = "failure_type"
        case reason
        case recoveryAction = "recovery_action"
        case attempt
        case maxRetries = "max_retries"
        case applied
        case blockedReason = "blocked_reason"
        case source
    }
}

struct AgentLoopEvidenceRecoveredStep: Decodable, Equatable {
    let eventId: String?
    let sequence: Int?
    let timestamp: Double?
    let correlationId: String?
    let stepId: String?
    let actionType: String?
    let failureType: String?
    let recoveryAction: String?
    let attempt: Int?
    let recoveredFromStepId: String?
    let nextAction: String?
    let nextTurn: Int?

    enum CodingKeys: String, CodingKey {
        case eventId = "event_id"
        case sequence
        case timestamp
        case correlationId = "correlation_id"
        case stepId = "step_id"
        case actionType = "action_type"
        case failureType = "failure_type"
        case recoveryAction = "recovery_action"
        case attempt
        case recoveredFromStepId = "recovered_from_step_id"
        case nextAction = "next_action"
        case nextTurn = "next_turn"
    }
}

struct AgentLoopEvidenceMemoryCandidates: Decodable, Equatable {
    let candidateCount: Int?
    let candidates: [AgentLoopEvidenceMemoryCandidate]?

    enum CodingKeys: String, CodingKey {
        case candidateCount = "candidate_count"
        case candidates
    }
}

struct AgentLoopEvidenceMemoryCandidate: Decodable, Equatable {
    let stepId: String?
    let turn: Int?
    let status: String?
    let provider: String?
    let memoryStatus: String?
    let memoryId: String?

    enum CodingKeys: String, CodingKey {
        case stepId = "step_id"
        case turn
        case status
        case provider
        case memoryStatus = "memory_status"
        case memoryId = "memory_id"
    }
}

struct AgentLoopHostReleaseEvidence: Decodable, Equatable {
    let schemaVersion: String?
    let readiness: String?
    let loopStatus: String?
    let checks: [AgentLoopHostReleaseCheck]?
    let risks: [AgentLoopHostReleaseRisk]?
    let riskCount: Int?
    let nextActions: [String]?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case readiness
        case loopStatus = "loop_status"
        case checks
        case risks
        case riskCount = "risk_count"
        case nextActions = "next_actions"
    }
}

struct AgentLoopHostReleaseCheck: Decodable, Equatable {
    let id: String?
    let status: String?
    let summary: String?
    let routedActionCount: Int?
    let nonDefaultRouteCount: Int?
    let capabilityHintRouteCount: Int?
    let appliedCount: Int?
    let blockedCount: Int?
    let candidateCount: Int?
    let category: String?

    enum CodingKeys: String, CodingKey {
        case id
        case status
        case summary
        case routedActionCount = "routed_action_count"
        case nonDefaultRouteCount = "non_default_route_count"
        case capabilityHintRouteCount = "capability_hint_route_count"
        case appliedCount = "applied_count"
        case blockedCount = "blocked_count"
        case candidateCount = "candidate_count"
        case category
    }
}

struct AgentLoopHostReleaseRisk: Decodable, Equatable {
    let id: String?
    let severity: String?
    let summary: String?
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

struct AgentLoopBudgetSummary: Decodable, Equatable {
    let schemaVersion: String?
    let maxConcurrentLoops: Int?
    let maxTurnsPerLoop: Int?
    let turnsUsed: Int?
    let turnsRemaining: Int?
    let maxRuntimeSeconds: Double?
    let runtimeSeconds: Double?
    let runtimeRemainingMs: Int?
    let actionLeaseSeconds: Double?
    let timeoutCancelCategory: String?
    let budgetExceededCategory: String?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case maxConcurrentLoops = "max_concurrent_loops"
        case maxTurnsPerLoop = "max_turns_per_loop"
        case turnsUsed = "turns_used"
        case turnsRemaining = "turns_remaining"
        case maxRuntimeSeconds = "max_runtime_seconds"
        case runtimeSeconds = "runtime_seconds"
        case runtimeRemainingMs = "runtime_remaining_ms"
        case actionLeaseSeconds = "action_lease_seconds"
        case timeoutCancelCategory = "timeout_cancel_category"
        case budgetExceededCategory = "budget_exceeded_category"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let legacy = try? decoder.container(keyedBy: LegacyCodingKeys.self)
        schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion)
        maxConcurrentLoops = try container.decodeIfPresent(Int.self, forKey: .maxConcurrentLoops)
        maxTurnsPerLoop = try container.decodeIfPresent(Int.self, forKey: .maxTurnsPerLoop)
            ?? (try legacy?.decodeIfPresent(Int.self, forKey: .maxTurns))
        turnsUsed = try container.decodeIfPresent(Int.self, forKey: .turnsUsed)
            ?? (try legacy?.decodeIfPresent(Int.self, forKey: .turnCount))
        turnsRemaining = try container.decodeIfPresent(Int.self, forKey: .turnsRemaining)
            ?? (try legacy?.decodeIfPresent(Int.self, forKey: .remainingTurns))
        maxRuntimeSeconds = try container.decodeIfPresent(Double.self, forKey: .maxRuntimeSeconds)
        runtimeSeconds = try container.decodeIfPresent(Double.self, forKey: .runtimeSeconds)
        runtimeRemainingMs = try container.decodeIfPresent(Int.self, forKey: .runtimeRemainingMs)
        actionLeaseSeconds = try container.decodeIfPresent(Double.self, forKey: .actionLeaseSeconds)
        timeoutCancelCategory = try container.decodeIfPresent(String.self, forKey: .timeoutCancelCategory)
        budgetExceededCategory = try container.decodeIfPresent(String.self, forKey: .budgetExceededCategory)
    }

    var turnsLabel: String? {
        guard let used = turnsUsed, let max = maxTurnsPerLoop else { return nil }
        return "\(used)/\(max)"
    }

    private enum LegacyCodingKeys: String, CodingKey {
        case maxTurns = "max_turns"
        case turnCount = "turn_count"
        case remainingTurns = "remaining_turns"
    }
}

struct AgentLoopTelemetryResponse: Decodable, Equatable {
    let schemaVersion: String?
    let loopId: String
    let status: String
    let latestSequence: Int?
    let budget: AgentLoopBudgetSummary?
    let summary: AgentLoopTelemetrySummary?
    let metrics: [AgentLoopTelemetryMetric]?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case loopId = "loop_id"
        case status
        case latestSequence = "latest_sequence"
        case budget
        case summary
        case metrics
    }
}

struct AgentLoopTelemetrySummary: Decodable, Equatable {
    let durationMs: Int?
    let turnCount: Int?
    let eventCount: Int?
    let routingOutcomeCount: Int?
    let memoryCandidateCount: Int?
    let recoveryDecisionCount: Int?
    let cancelCategory: String?

    enum CodingKeys: String, CodingKey {
        case durationMs = "duration_ms"
        case turnCount = "turn_count"
        case eventCount = "event_count"
        case routingOutcomeCount = "routing_outcome_count"
        case memoryCandidateCount = "memory_candidate_count"
        case recoveryDecisionCount = "recovery_decision_count"
        case cancelCategory = "cancel_category"
    }
}

struct AgentLoopTelemetryMetric: Decodable, Equatable {
    let schemaVersion: String?
    let metric: String?
    let value: Double?
    let unit: String?
    let dimensions: [String: AgentLoopJSONValue]?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case metric
        case legacyId = "id"
        case value
        case unit
        case dimensions
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion)
        metric = try container.decodeIfPresent(String.self, forKey: .metric)
            ?? (try container.decodeIfPresent(String.self, forKey: .legacyId))
        value = try container.decodeIfPresent(Double.self, forKey: .value)
        unit = try container.decodeIfPresent(String.self, forKey: .unit)
        dimensions = try container.decodeIfPresent([String: AgentLoopJSONValue].self, forKey: .dimensions)
    }

    var id: String? { metric }
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
    let eventId: String?
    let sequence: Int?
    let type: String
    let loopId: String?
    let correlationId: String?
    let stepId: String?
    let actionId: String?
    let taskId: String?
    let subtaskId: String?
    let timestamp: Double?
    let payload: [String: AgentLoopJSONValue]?

    enum CodingKeys: String, CodingKey {
        case eventId = "event_id"
        case sequence
        case type
        case loopId = "loop_id"
        case correlationId = "correlation_id"
        case stepId = "step_id"
        case actionId = "action_id"
        case taskId = "task_id"
        case subtaskId = "subtask_id"
        case timestamp
        case payload
    }

    var sequenceLabel: String? {
        guard let sequence else { return nil }
        return "#\(sequence)"
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
