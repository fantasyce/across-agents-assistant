import Foundation

struct AgentSkillDefinition: Codable, Identifiable, Equatable {
    let id: String
    let name: String
    let description: String
    let promptHint: String
    let tags: [String]
    let source: String?

    var isCustom: Bool {
        source == "custom"
    }

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case description
        case promptHint = "prompt_hint"
        case tags
        case source
    }
}

struct AgentCapabilityToolSchema: Codable, Identifiable, Equatable {
    var id: String { name }
    let name: String
    let description: String?
    let riskLevel: String?

    enum CodingKeys: String, CodingKey {
        case name
        case description
        case riskLevel = "risk_level"
    }
}

struct AgentCapabilityNativeSkillHealth: Codable, Equatable {
    let available: Int
    let unavailable: Int
    let total: Int
}

struct AgentCapabilityAgentCard: Codable, Identifiable, Equatable {
    var id: String { agentId }
    let agentId: String
    let displayName: String
    let agentType: String
    let configuredSkillIds: [String]
    let configuredSkillNames: [String]
    let enabledPluginIds: [String]
    let enabledToolNames: [String]
    let strictToolScope: Bool
    let nativeSkillHealth: AgentCapabilityNativeSkillHealth?
    let warnings: [String]

    enum CodingKeys: String, CodingKey {
        case agentId = "agent_id"
        case displayName = "display_name"
        case agentType = "agent_type"
        case configuredSkillIds = "configured_skill_ids"
        case configuredSkillNames = "configured_skill_names"
        case enabledPluginIds = "enabled_plugin_ids"
        case enabledToolNames = "enabled_tool_names"
        case strictToolScope = "strict_tool_scope"
        case nativeSkillHealth = "native_skill_health"
        case warnings
    }
}

struct AgentCapabilityProfile: Codable, Identifiable, Equatable {
    var id: String { agentId }
    var agentId: String
    var enabledSkillIds: [String]
    var enabledPluginIds: [String]
    var enabledToolNames: [String]
    var customInstructions: String
    var strictToolScope: Bool

    enum CodingKeys: String, CodingKey {
        case agentId = "agent_id"
        case enabledSkillIds = "enabled_skill_ids"
        case enabledPluginIds = "enabled_plugin_ids"
        case enabledToolNames = "enabled_tool_names"
        case customInstructions = "custom_instructions"
        case strictToolScope = "strict_tool_scope"
    }

    static func defaultProfile(agentId: String) -> AgentCapabilityProfile {
        let normalized = AgentIDs.normalized(agentId) ?? agentId
        return AgentCapabilityProfile(
            agentId: normalized,
            enabledSkillIds: AgentCapabilityCatalog.defaultSkillIds(for: normalized),
            enabledPluginIds: AgentCapabilityCatalog.defaultPluginIds(for: normalized),
            enabledToolNames: [],
            customInstructions: "",
            strictToolScope: false
        )
    }

    mutating func setSkill(_ skillId: String, enabled: Bool) {
        enabledSkillIds = AgentCapabilityCatalog.setMembership(
            skillId,
            enabled: enabled,
            in: enabledSkillIds
        )
    }

    mutating func setPlugin(_ pluginId: String, enabled: Bool) {
        enabledPluginIds = AgentCapabilityCatalog.setMembership(
            pluginId,
            enabled: enabled,
            in: enabledPluginIds
        )
    }

    mutating func setTool(_ toolName: String, enabled: Bool) {
        enabledToolNames = AgentCapabilityCatalog.setMembership(
            toolName,
            enabled: enabled,
            in: enabledToolNames
        )
    }
}

struct AgentCapabilityListResponse: Decodable {
    let skills: [AgentSkillDefinition]
    let profiles: [String: AgentCapabilityProfile]
    let availableTools: [AgentCapabilityToolSchema]
    let nativeSkillAgents: [String: NativeSkillAgentState]
    let agentCards: [AgentCapabilityAgentCard]

    enum CodingKeys: String, CodingKey {
        case skills
        case profiles
        case availableTools = "available_tools"
        case nativeSkillAgents = "native_skill_agents"
        case agentCards = "agent_cards"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        skills = try container.decodeIfPresent([AgentSkillDefinition].self, forKey: .skills) ?? []
        profiles = try container.decodeIfPresent([String: AgentCapabilityProfile].self, forKey: .profiles) ?? [:]
        availableTools = try container.decodeIfPresent([AgentCapabilityToolSchema].self, forKey: .availableTools) ?? []
        nativeSkillAgents = try container.decodeIfPresent([String: NativeSkillAgentState].self, forKey: .nativeSkillAgents) ?? [:]
        agentCards = try container.decodeIfPresent([AgentCapabilityAgentCard].self, forKey: .agentCards) ?? []
    }
}

struct AgentCapabilityUpdateRequest: Encodable {
    let enabledSkillIds: [String]
    let enabledPluginIds: [String]
    let enabledToolNames: [String]
    let customInstructions: String
    let strictToolScope: Bool

    enum CodingKeys: String, CodingKey {
        case enabledSkillIds = "enabled_skill_ids"
        case enabledPluginIds = "enabled_plugin_ids"
        case enabledToolNames = "enabled_tool_names"
        case customInstructions = "custom_instructions"
        case strictToolScope = "strict_tool_scope"
    }

    init(profile: AgentCapabilityProfile) {
        enabledSkillIds = profile.enabledSkillIds
        enabledPluginIds = profile.enabledPluginIds
        enabledToolNames = profile.enabledToolNames
        customInstructions = profile.customInstructions
        strictToolScope = profile.strictToolScope
    }
}

struct AgentCapabilitySkillRequest: Encodable {
    let id: String?
    let name: String
    let description: String
    let promptHint: String
    let tags: [String]

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case description
        case promptHint = "prompt_hint"
        case tags
    }
}

struct AgentCapabilitySkillSaveResponse: Decodable {
    let status: String
    let skill: AgentSkillDefinition
}

struct HostAgentCapabilityRegistry: Codable, Equatable {
    let schemaVersion: String
    let generatedAt: Double?
    let security: HostAgentCapabilityRegistrySecurity
    let agents: [HostAgentCapabilityDescriptor]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case generatedAt = "generated_at"
        case security
        case agents
    }

    init(
        schemaVersion: String,
        generatedAt: Double? = nil,
        security: HostAgentCapabilityRegistrySecurity = HostAgentCapabilityRegistrySecurity(),
        agents: [HostAgentCapabilityDescriptor]
    ) {
        self.schemaVersion = schemaVersion
        self.generatedAt = generatedAt
        self.security = security
        self.agents = agents
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion) ?? "1.0"
        generatedAt = try container.decodeIfPresent(Double.self, forKey: .generatedAt)
        security = try container.decodeIfPresent(HostAgentCapabilityRegistrySecurity.self, forKey: .security)
            ?? HostAgentCapabilityRegistrySecurity()
        agents = try container.decodeIfPresent([HostAgentCapabilityDescriptor].self, forKey: .agents) ?? []
    }

    var routeReadyAgentCount: Int {
        agents.filter { !$0.capabilities.isEmpty }.count
    }

    var exportedCapabilityCount: Int {
        Set(agents.flatMap(\.capabilities)).count
    }

    func descriptor(for agentId: String) -> HostAgentCapabilityDescriptor? {
        let normalized = AgentIDs.normalized(agentId) ?? agentId
        return agents.first { $0.agentId == normalized }
    }

    func syncSummary(
        for profile: AgentCapabilityProfile,
        nativeSkillState: NativeSkillAgentState? = nil
    ) -> HostAgentCapabilityRegistrySyncSummary {
        guard let descriptor = descriptor(for: profile.agentId) else {
            return HostAgentCapabilityRegistrySyncSummary(
                agentId: profile.agentId,
                descriptor: nil,
                issues: [
                    HostAgentCapabilityRegistrySyncIssue(
                        titleKey: "capabilities.registryCheck.descriptor",
                        expected: [profile.agentId],
                        exported: []
                    )
                ]
            )
        }

        var issues: [HostAgentCapabilityRegistrySyncIssue] = []
        appendSyncIssue(
            titleKey: "capabilities.registryCheck.skills",
            expected: profile.enabledSkillIds,
            exported: descriptor.configuredSkillIds,
            to: &issues
        )
        appendSyncIssue(
            titleKey: "capabilities.registryCheck.plugins",
            expected: profile.enabledPluginIds,
            exported: descriptor.enabledPluginIds,
            to: &issues
        )
        appendSyncIssue(
            titleKey: "capabilities.registryCheck.tools",
            expected: profile.enabledToolNames,
            exported: descriptor.enabledToolNames,
            to: &issues
        )
        if let nativeSkillState {
            appendSyncIssue(
                titleKey: "capabilities.registryCheck.nativeSkills",
                expected: nativeSkillState.skills.filter(\.isActive).map(\.id),
                exported: descriptor.nativeSkillIds,
                to: &issues
            )
        }
        appendSyncIssue(
            titleKey: "capabilities.registryCheck.strictScope",
            expected: [profile.strictToolScope ? "enabled" : "disabled"],
            exported: [descriptor.strictToolScope ? "enabled" : "disabled"],
            to: &issues
        )

        return HostAgentCapabilityRegistrySyncSummary(
            agentId: profile.agentId,
            descriptor: descriptor,
            issues: issues
        )
    }
}

struct HostAgentCapabilityRegistrySyncSummary: Equatable {
    let agentId: String
    let descriptor: HostAgentCapabilityDescriptor?
    let issues: [HostAgentCapabilityRegistrySyncIssue]

    var isMissing: Bool {
        descriptor == nil
    }

    var isSynced: Bool {
        descriptor != nil && issues.isEmpty
    }
}

struct HostAgentCapabilityRegistrySyncIssue: Identifiable, Equatable {
    var id: String { titleKey }
    let titleKey: String
    let expected: [String]
    let exported: [String]
}

private func appendSyncIssue(
    titleKey: String,
    expected: [String],
    exported: [String],
    to issues: inout [HostAgentCapabilityRegistrySyncIssue]
) {
    let normalizedExpected = normalizedRegistryValues(expected)
    let normalizedExported = normalizedRegistryValues(exported)
    guard normalizedExpected != normalizedExported else { return }
    issues.append(
        HostAgentCapabilityRegistrySyncIssue(
            titleKey: titleKey,
            expected: normalizedExpected,
            exported: normalizedExported
        )
    )
}

private func normalizedRegistryValues(_ values: [String]) -> [String] {
    Array(
        Set(
            values
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty }
        )
    )
    .sorted { $0.localizedStandardCompare($1) == .orderedAscending }
}

struct HostAgentCapabilityRegistrySecurity: Codable, Equatable {
    let secretsIncluded: Bool
    let customInstructionsIncluded: Bool
    let installPathsIncluded: Bool
    let credentialFieldsRedacted: Bool

    enum CodingKeys: String, CodingKey {
        case secretsIncluded = "secrets_included"
        case customInstructionsIncluded = "custom_instructions_included"
        case installPathsIncluded = "install_paths_included"
        case credentialFieldsRedacted = "credential_fields_redacted"
    }

    init(
        secretsIncluded: Bool = false,
        customInstructionsIncluded: Bool = false,
        installPathsIncluded: Bool = false,
        credentialFieldsRedacted: Bool = true
    ) {
        self.secretsIncluded = secretsIncluded
        self.customInstructionsIncluded = customInstructionsIncluded
        self.installPathsIncluded = installPathsIncluded
        self.credentialFieldsRedacted = credentialFieldsRedacted
    }
}

struct HostAgentCapabilityDescriptor: Codable, Identifiable, Equatable {
    var id: String { agentId }
    let agentId: String
    let displayName: String
    let agentType: String
    let aliases: [String]
    let capabilities: [String]
    let configuredSkillIds: [String]
    let configuredSkillNames: [String]
    let enabledPluginIds: [String]
    let enabledToolNames: [String]
    let nativeSkillIds: [String]
    let strictToolScope: Bool
    let warnings: [String]

    enum CodingKeys: String, CodingKey {
        case agentId = "agent_id"
        case displayName = "display_name"
        case agentType = "agent_type"
        case aliases
        case capabilities
        case configuredSkillIds = "configured_skill_ids"
        case configuredSkillNames = "configured_skill_names"
        case enabledPluginIds = "enabled_plugin_ids"
        case enabledToolNames = "enabled_tool_names"
        case nativeSkillIds = "native_skill_ids"
        case strictToolScope = "strict_tool_scope"
        case warnings
    }

    init(
        agentId: String,
        displayName: String,
        agentType: String = "unknown",
        aliases: [String] = [],
        capabilities: [String] = [],
        configuredSkillIds: [String] = [],
        configuredSkillNames: [String] = [],
        enabledPluginIds: [String] = [],
        enabledToolNames: [String] = [],
        nativeSkillIds: [String] = [],
        strictToolScope: Bool = false,
        warnings: [String] = []
    ) {
        self.agentId = agentId
        self.displayName = displayName
        self.agentType = agentType
        self.aliases = aliases
        self.capabilities = capabilities
        self.configuredSkillIds = configuredSkillIds
        self.configuredSkillNames = configuredSkillNames
        self.enabledPluginIds = enabledPluginIds
        self.enabledToolNames = enabledToolNames
        self.nativeSkillIds = nativeSkillIds
        self.strictToolScope = strictToolScope
        self.warnings = warnings
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        agentId = try container.decode(String.self, forKey: .agentId)
        displayName = try container.decodeIfPresent(String.self, forKey: .displayName) ?? agentId
        agentType = try container.decodeIfPresent(String.self, forKey: .agentType) ?? "unknown"
        aliases = try container.decodeIfPresent([String].self, forKey: .aliases) ?? []
        capabilities = try container.decodeIfPresent([String].self, forKey: .capabilities) ?? []
        configuredSkillIds = try container.decodeIfPresent([String].self, forKey: .configuredSkillIds) ?? []
        configuredSkillNames = try container.decodeIfPresent([String].self, forKey: .configuredSkillNames) ?? []
        enabledPluginIds = try container.decodeIfPresent([String].self, forKey: .enabledPluginIds) ?? []
        enabledToolNames = try container.decodeIfPresent([String].self, forKey: .enabledToolNames) ?? []
        nativeSkillIds = try container.decodeIfPresent([String].self, forKey: .nativeSkillIds) ?? []
        strictToolScope = try container.decodeIfPresent(Bool.self, forKey: .strictToolScope) ?? false
        warnings = try container.decodeIfPresent([String].self, forKey: .warnings) ?? []
    }
}

struct AgentCapabilityPreflightRequest: Encodable {
    let description: String
    let ownerAgent: String
    let allowedSubtaskAgents: [String]
    let taskTypes: [String]

    enum CodingKeys: String, CodingKey {
        case description
        case ownerAgent = "owner_agent"
        case allowedSubtaskAgents = "allowed_subtask_agents"
        case taskTypes = "task_types"
    }
}

struct AgentCapabilityRoutingEvidence: Codable, Equatable {
    let source: String?
    let status: String?
    let skillId: String?
    let skillName: String?
    let reason: String?
    let repairSuggestions: [String]

    enum CodingKeys: String, CodingKey {
        case source
        case status
        case skillId = "skill_id"
        case skillName = "skill_name"
        case reason
        case repairSuggestions = "repair_suggestions"
    }

    init(
        source: String?,
        status: String?,
        skillId: String?,
        skillName: String?,
        reason: String?,
        repairSuggestions: [String] = []
    ) {
        self.source = source
        self.status = status
        self.skillId = skillId
        self.skillName = skillName
        self.reason = reason
        self.repairSuggestions = repairSuggestions
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        source = try container.decodeIfPresent(String.self, forKey: .source)
        status = try container.decodeIfPresent(String.self, forKey: .status)
        skillId = try container.decodeIfPresent(String.self, forKey: .skillId)
        skillName = try container.decodeIfPresent(String.self, forKey: .skillName)
        reason = try container.decodeIfPresent(String.self, forKey: .reason)
        repairSuggestions = try container.decodeIfPresent([String].self, forKey: .repairSuggestions) ?? []
    }
}

struct AgentCapabilityPreflightAgentSummary: Codable, Identifiable, Equatable {
    var id: String { agentId }
    let agentId: String
    let score: Int
    let matchedSkillIds: [String]
    let matchedNativeSkillIds: [String]
    let unavailableNativeSkillIds: [String]
    let nativeSkillRepairSuggestions: [String]
    let routingEvidence: [AgentCapabilityRoutingEvidence]
    let configuredCount: Int
    let warnings: [String]

    enum CodingKeys: String, CodingKey {
        case agentId = "agent_id"
        case score
        case matchedSkillIds = "matched_skill_ids"
        case matchedNativeSkillIds = "matched_native_skill_ids"
        case unavailableNativeSkillIds = "unavailable_native_skill_ids"
        case nativeSkillRepairSuggestions = "native_skill_repair_suggestions"
        case routingEvidence = "routing_evidence"
        case configuredCount = "configured_count"
        case warnings
    }

    init(
        agentId: String,
        score: Int,
        matchedSkillIds: [String],
        matchedNativeSkillIds: [String] = [],
        unavailableNativeSkillIds: [String] = [],
        nativeSkillRepairSuggestions: [String] = [],
        routingEvidence: [AgentCapabilityRoutingEvidence] = [],
        configuredCount: Int,
        warnings: [String]
    ) {
        self.agentId = agentId
        self.score = score
        self.matchedSkillIds = matchedSkillIds
        self.matchedNativeSkillIds = matchedNativeSkillIds
        self.unavailableNativeSkillIds = unavailableNativeSkillIds
        self.nativeSkillRepairSuggestions = nativeSkillRepairSuggestions
        self.routingEvidence = routingEvidence
        self.configuredCount = configuredCount
        self.warnings = warnings
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        agentId = try container.decode(String.self, forKey: .agentId)
        score = try container.decodeIfPresent(Int.self, forKey: .score) ?? 0
        matchedSkillIds = try container.decodeIfPresent([String].self, forKey: .matchedSkillIds) ?? []
        matchedNativeSkillIds = try container.decodeIfPresent([String].self, forKey: .matchedNativeSkillIds) ?? []
        unavailableNativeSkillIds = try container.decodeIfPresent([String].self, forKey: .unavailableNativeSkillIds) ?? []
        nativeSkillRepairSuggestions = try container.decodeIfPresent([String].self, forKey: .nativeSkillRepairSuggestions) ?? []
        routingEvidence = try container.decodeIfPresent([AgentCapabilityRoutingEvidence].self, forKey: .routingEvidence) ?? []
        configuredCount = try container.decodeIfPresent(Int.self, forKey: .configuredCount) ?? 0
        warnings = try container.decodeIfPresent([String].self, forKey: .warnings) ?? []
    }
}

struct AgentCapabilityPreflightResponse: Codable, Equatable {
    let selectedAgentIds: [String]
    let recommendedAgentIds: [String]
    let agentSummaries: [AgentCapabilityPreflightAgentSummary]
    let warnings: [String]
    let promptPreview: String

    enum CodingKeys: String, CodingKey {
        case selectedAgentIds = "selected_agent_ids"
        case recommendedAgentIds = "recommended_agent_ids"
        case agentSummaries = "agent_summaries"
        case warnings
        case promptPreview = "prompt_preview"
    }

    var bestRecommendedAgentId: String? {
        recommendedAgentIds.first
    }

    var bestSummary: AgentCapabilityPreflightAgentSummary? {
        guard let bestRecommendedAgentId else { return agentSummaries.first }
        return agentSummaries.first { $0.agentId == bestRecommendedAgentId } ?? agentSummaries.first
    }
}

struct NativeSkillDefinition: Codable, Identifiable, Equatable {
    let id: String
    let name: String
    let description: String?
    let status: String
    let source: String?
    let version: String?
    let path: String?
    let availability: String?
    let unavailableReason: String?
    let missingRequirements: [String]
    let repairSuggestions: [String]
    let managedByApp: Bool
    let supportsUpdate: Bool
    let supportsUninstall: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case description
        case status
        case source
        case version
        case path
        case availability
        case unavailableReason = "unavailable_reason"
        case missingRequirements = "missing_requirements"
        case repairSuggestions = "repair_suggestions"
        case managedByApp = "managed_by_app"
        case supportsUpdate = "supports_update"
        case supportsUninstall = "supports_uninstall"
    }

    init(
        id: String,
        name: String,
        description: String? = nil,
        status: String = "installed",
        source: String? = nil,
        version: String? = nil,
        path: String? = nil,
        availability: String? = nil,
        unavailableReason: String? = nil,
        missingRequirements: [String] = [],
        repairSuggestions: [String] = [],
        managedByApp: Bool = false,
        supportsUpdate: Bool = false,
        supportsUninstall: Bool = false
    ) {
        self.id = id
        self.name = name
        self.description = description
        self.status = status
        self.source = source
        self.version = version
        self.path = path
        self.availability = availability
        self.unavailableReason = unavailableReason
        self.missingRequirements = missingRequirements
        self.repairSuggestions = repairSuggestions
        self.managedByApp = managedByApp
        self.supportsUpdate = supportsUpdate
        self.supportsUninstall = supportsUninstall
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        name = try container.decode(String.self, forKey: .name)
        description = try container.decodeIfPresent(String.self, forKey: .description)
        status = try container.decodeIfPresent(String.self, forKey: .status) ?? "installed"
        source = try container.decodeIfPresent(String.self, forKey: .source)
        version = try container.decodeIfPresent(String.self, forKey: .version)
        path = try container.decodeIfPresent(String.self, forKey: .path)
        availability = try container.decodeIfPresent(String.self, forKey: .availability)
        unavailableReason = try container.decodeIfPresent(String.self, forKey: .unavailableReason)
        missingRequirements = try container.decodeIfPresent([String].self, forKey: .missingRequirements) ?? []
        repairSuggestions = try container.decodeIfPresent([String].self, forKey: .repairSuggestions) ?? []
        managedByApp = try container.decodeIfPresent(Bool.self, forKey: .managedByApp) ?? false
        supportsUpdate = try container.decodeIfPresent(Bool.self, forKey: .supportsUpdate) ?? false
        supportsUninstall = try container.decodeIfPresent(Bool.self, forKey: .supportsUninstall) ?? false
    }

    var isActive: Bool {
        let inactiveStatuses = ["disabled", "missing", "blocked", "unavailable", "not_ready", "error", "failed"]
        return !inactiveStatuses.contains(status.lowercased()) && availability?.lowercased() != "unavailable"
    }
}

struct NativeSkillAgentState: Codable, Identifiable, Equatable {
    var id: String { agentId }
    let agentId: String
    let displayName: String
    let mode: String
    let supportsCreate: Bool
    let supportsInstall: Bool
    let supportsUninstall: Bool
    let supportsUpdate: Bool
    let supportsCheck: Bool
    let skills: [NativeSkillDefinition]
    let error: String?

    enum CodingKeys: String, CodingKey {
        case agentId = "agent_id"
        case displayName = "display_name"
        case mode
        case supportsCreate = "supports_create"
        case supportsInstall = "supports_install"
        case supportsUninstall = "supports_uninstall"
        case supportsUpdate = "supports_update"
        case supportsCheck = "supports_check"
        case skills
        case error
    }

    var installedCount: Int {
        skills.filter(\.isActive).count
    }
}

struct NativeSkillListResponse: Decodable {
    let agents: [String: NativeSkillAgentState]
}

struct NativeSkillInstallRequest: Encodable {
    let identifier: String?
    let name: String?
    let description: String?
    let body: String?
    let scope: String
    let projectDir: String?
    let sourcePath: String?
    let version: String?
    let force: Bool

    enum CodingKeys: String, CodingKey {
        case identifier
        case name
        case description
        case body
        case scope
        case projectDir = "project_dir"
        case sourcePath = "source_path"
        case version
        case force
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encodeIfPresent(identifier, forKey: .identifier)
        try container.encodeIfPresent(name, forKey: .name)
        try container.encodeIfPresent(description, forKey: .description)
        try container.encodeIfPresent(body, forKey: .body)
        try container.encode(scope, forKey: .scope)
        try container.encodeIfPresent(projectDir, forKey: .projectDir)
        try container.encodeIfPresent(sourcePath, forKey: .sourcePath)
        try container.encodeIfPresent(version, forKey: .version)
        try container.encode(force, forKey: .force)
    }
}

struct NativeSkillMutationResponse: Decodable {
    let status: String
    let skill: NativeSkillDefinition
}

struct NativeSkillCheckResponse: Decodable {
    let status: String
    let result: NativeSkillCheckResult
}

struct NativeSkillCheckResult: Codable, Equatable {
    let agentId: String?
    let status: String?
    let output: String?
    let warnings: [String]?
    let checkedCount: Int?
    let command: [String]?

    enum CodingKeys: String, CodingKey {
        case agentId = "agent_id"
        case status
        case output
        case warnings
        case checkedCount = "checked_count"
        case command
    }
}

enum AgentCapabilityCatalog {
    private static let defaultSkillIdsByAgent: [String: [String]] = [
        "openclaw": ["general_execution", "macos_automation", "test_authoring"],
        "hermes": ["frontend_design", "interaction_design", "test_authoring"],
        "claude": ["architecture_review", "code_review", "test_strategy"],
        "codex": ["general_execution", "code_review", "test_authoring"],
        "opencode": ["general_execution", "code_review", "test_authoring"],
        "cursor": ["general_execution", "frontend_design", "code_review"],
        "openai": ["backend_api", "code_review"],
        "anthropic": ["backend_api", "code_review"],
        "deepseek": ["backend_api", "data_modeling", "code_review"],
        "minimax": ["devops_release", "integration_smoke", "test_strategy"],
        "bailian": ["backend_api", "code_review"],
        "moonshot": ["backend_api", "code_review"],
        "zhipu": ["backend_api", "code_review"],
        "volcengine": ["backend_api", "code_review"],
        "google": ["backend_api", "code_review"],
        "xai": ["backend_api", "code_review"],
        "mistral": ["backend_api", "code_review"],
        "groq": ["backend_api", "code_review"],
        "cohere": ["backend_api", "code_review"],
        "openrouter": ["backend_api", "code_review"],
        "together": ["backend_api", "code_review"],
        "fireworks": ["backend_api", "code_review"]
    ]

    static func defaultSkillIds(for agentId: String) -> [String] {
        defaultSkillIdsByAgent[AgentIDs.normalized(agentId) ?? agentId] ?? []
    }

    static func defaultPluginIds(for agentId: String) -> [String] {
        let normalized = AgentIDs.normalized(agentId) ?? agentId
        return defaultSkillIdsByAgent.keys.contains(normalized) ? ["across_context"] : []
    }

    static func configuredCapabilityCount(_ profile: AgentCapabilityProfile) -> Int {
        profile.enabledSkillIds.count
            + profile.enabledPluginIds.count
            + profile.enabledToolNames.count
            + (profile.customInstructions.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? 0 : 1)
    }

    static func setMembership(_ value: String, enabled: Bool, in values: [String]) -> [String] {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return values }
        var result = values.filter { $0 != trimmed }
        if enabled {
            result.append(trimmed)
        }
        return result
    }
}
