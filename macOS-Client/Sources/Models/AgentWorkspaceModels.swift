import Foundation

enum AgentWorkspaceReadinessStatus: String, Codable, CaseIterable {
    case ready
    case partial
    case blocked
    case unavailable
    case unknown

    init(rawStatus: String?) {
        switch AgentWorkspaceReadinessStatus.normalized(rawStatus) {
        case "active", "available", "ok", "passed", "ready", "success":
            self = .ready
        case "attention", "degraded", "needs_attention", "not_ready", "not_run", "partial", "pending", "watch":
            self = .partial
        case "blocked", "error", "failed", "invalid", "missing", "timeout":
            self = .blocked
        case "disabled", "none", "not_applicable", "not_implemented", "skipped", "unavailable":
            self = .unavailable
        default:
            self = .unknown
        }
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        self.init(rawStatus: try? container.decode(String.self))
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(rawValue)
    }

    var allowsWorkspaceMutation: Bool {
        self == .ready
    }

    var isActionableReadiness: Bool {
        self == .ready || self == .partial
    }

    private static func normalized(_ status: String?) -> String {
        (status ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .replacingOccurrences(of: "-", with: "_")
    }
}

struct AgentWorkspaceReadinessSnapshot: Decodable, Equatable {
    let schemaVersion: String
    let status: AgentWorkspaceReadinessStatus
    let generatedAt: String?
    let repoRoot: String?
    let prompt: String?
    let selectedAgentIds: [String]
    let executionStrategy: String?
    let workspaceIsolation: AgentWorkspaceIsolationCapability
    let agents: [AgentWorkspaceAgentReadiness]
    let agentOperationalStatus: [AgentWorkspaceOperationalStatus]
    let routes: AgentWorkspaceReadinessRoutes
    let missingPrerequisites: [String]
    let unsupportedFeatures: [String]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case status
        case generatedAt = "generated_at"
        case repoRoot = "repo_root"
        case prompt
        case selectedAgentIds = "selected_agent_ids"
        case executionStrategy = "execution_strategy"
        case workspaceIsolation = "workspace_isolation"
        case agents
        case agentOperationalStatus = "agent_operational_status"
        case routes
        case missingPrerequisites = "missing_prerequisites"
        case unsupportedFeatures = "unsupported_features"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion) ?? "agent-workspace-readiness/1.0"
        status = try container.decodeIfPresent(AgentWorkspaceReadinessStatus.self, forKey: .status) ?? .unknown
        generatedAt = AgentWorkspaceDecoding.stringOrNumber(container, forKey: .generatedAt)
        repoRoot = try container.decodeIfPresent(String.self, forKey: .repoRoot)
        prompt = try container.decodeIfPresent(String.self, forKey: .prompt)
        selectedAgentIds = try container.decodeIfPresent([String].self, forKey: .selectedAgentIds) ?? []
        executionStrategy = try container.decodeIfPresent(String.self, forKey: .executionStrategy)
        workspaceIsolation = try container.decodeIfPresent(AgentWorkspaceIsolationCapability.self, forKey: .workspaceIsolation)
            ?? AgentWorkspaceIsolationCapability()
        agents = try container.decodeIfPresent([AgentWorkspaceAgentReadiness].self, forKey: .agents) ?? []
        agentOperationalStatus = try container.decodeIfPresent([AgentWorkspaceOperationalStatus].self, forKey: .agentOperationalStatus) ?? []
        routes = try container.decodeIfPresent(AgentWorkspaceReadinessRoutes.self, forKey: .routes)
            ?? AgentWorkspaceReadinessRoutes()
        missingPrerequisites = AgentWorkspaceDecoding.prerequisiteIds(container, forKey: .missingPrerequisites)
        unsupportedFeatures = try container.decodeIfPresent([String].self, forKey: .unsupportedFeatures) ?? []
    }

    var readyAgentIds: [String] {
        agents.filter(\.isUsable).map(\.agentId)
    }

    var selectedReadyAgentIds: [String] {
        guard !selectedAgentIds.isEmpty else {
            return readyAgentIds
        }
        let selected = Set(selectedAgentIds)
        return agents.filter { selected.contains($0.agentId) && $0.isUsable }.map(\.agentId)
    }

    func operationalStatus(for agentId: String) -> AgentWorkspaceOperationalStatus? {
        agentOperationalStatus.first { $0.agentId == agentId }
    }

    var canCreateWorkspace: Bool {
        status.allowsWorkspaceMutation
            && workspaceIsolation.canCreateIsolatedWorkspaces
            && routes.hasRequiredRoutes
            && !readyAgentIds.isEmpty
    }

    var readinessIssues: [String] {
        var issues: [String] = []
        if !workspaceIsolation.canCreateIsolatedWorkspaces {
            issues.append(contentsOf: workspaceIsolation.missingPrerequisites)
            if let reason = workspaceIsolation.reason, !reason.isEmpty {
                issues.append(reason)
            }
        }
        issues.append(contentsOf: routes.missingRoutes)
        if readyAgentIds.isEmpty {
            issues.append("no_ready_agents")
        }
        return Array(Set(issues)).sorted()
    }
}

struct AgentWorkspaceOperationalStatus: Decodable, Equatable, Identifiable {
    let agentId: String
    let account: AgentOperationalAccount
    let auth: AgentOperationalAuth
    let model: AgentOperationalNamedStatus
    let provider: AgentOperationalNamedStatus
    let usage: AgentOperationalUsage
    let rateLimit: AgentOperationalRateLimit

    var id: String { agentId }

    enum CodingKeys: String, CodingKey {
        case agentId = "agent_id"
        case account
        case auth
        case model
        case provider
        case usage
        case rateLimit = "rate_limit"
    }
}

struct AgentOperationalAccount: Decodable, Equatable {
    let status: String
    let id: String?
    let displayName: String?

    enum CodingKeys: String, CodingKey {
        case status
        case id
        case displayName = "display_name"
    }
}

struct AgentOperationalAuth: Decodable, Equatable {
    let status: String
    let authenticated: Bool?
    let method: String?
}

struct AgentOperationalNamedStatus: Decodable, Equatable {
    let status: String
    let id: String?
}

struct AgentOperationalUsage: Decodable, Equatable {
    let status: String
    let window: String?
    let inputTokens: Int?
    let outputTokens: Int?
    let totalTokens: Int?
    let requests: Int?

    enum CodingKeys: String, CodingKey {
        case status
        case window
        case inputTokens = "input_tokens"
        case outputTokens = "output_tokens"
        case totalTokens = "total_tokens"
        case requests
    }
}

struct AgentOperationalRateLimit: Decodable, Equatable {
    let status: String
    let limit: Int?
    let remaining: Int?
    let resetAt: String?
    let retryAfterSeconds: Double?

    enum CodingKeys: String, CodingKey {
        case status
        case limit
        case remaining
        case resetAt = "reset_at"
        case retryAfterSeconds = "retry_after_seconds"
    }
}

private enum AgentWorkspaceDecoding {
    static func stringOrNumber<Key: CodingKey>(_ container: KeyedDecodingContainer<Key>, forKey key: Key) -> String? {
        if let value = try? container.decode(String.self, forKey: key) {
            return value
        }
        if let value = try? container.decode(Double.self, forKey: key) {
            return String(value)
        }
        if let value = try? container.decode(Int.self, forKey: key) {
            return String(value)
        }
        return nil
    }

    static func prerequisiteIds<Key: CodingKey>(_ container: KeyedDecodingContainer<Key>, forKey key: Key) -> [String] {
        if let values = try? container.decode([String].self, forKey: key) {
            return values.filter { !$0.isEmpty }.sorted()
        }
        if let values = try? container.decode([AgentWorkspacePrerequisite].self, forKey: key) {
            return values.compactMap(\.id).filter { !$0.isEmpty }.sorted()
        }
        return []
    }
}

private struct AgentWorkspacePrerequisite: Decodable {
    let id: String?
}

struct AgentWorkspaceIsolationCapability: Decodable, Equatable {
    let status: AgentWorkspaceReadinessStatus
    let mode: String?
    let supportsGitWorktree: Bool
    let canCreateIsolatedWorkspaces: Bool
    let missingPrerequisites: [String]
    let reason: String?

    enum CodingKeys: String, CodingKey {
        case status
        case mode
        case supportsGitWorktree = "supports_git_worktree"
        case canCreateIsolatedWorkspaces = "can_create_isolated_workspaces"
        case missingPrerequisites = "missing_prerequisites"
        case reason
    }

    init(
        status: AgentWorkspaceReadinessStatus = .unknown,
        mode: String? = nil,
        supportsGitWorktree: Bool = false,
        canCreateIsolatedWorkspaces: Bool = false,
        missingPrerequisites: [String] = [],
        reason: String? = nil
    ) {
        self.status = status
        self.mode = mode
        self.supportsGitWorktree = supportsGitWorktree
        self.canCreateIsolatedWorkspaces = canCreateIsolatedWorkspaces
        self.missingPrerequisites = missingPrerequisites
        self.reason = reason
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        status = try container.decodeIfPresent(AgentWorkspaceReadinessStatus.self, forKey: .status) ?? .unknown
        mode = try container.decodeIfPresent(String.self, forKey: .mode)
        supportsGitWorktree = try container.decodeIfPresent(Bool.self, forKey: .supportsGitWorktree) ?? false
        canCreateIsolatedWorkspaces = try container.decodeIfPresent(Bool.self, forKey: .canCreateIsolatedWorkspaces)
            ?? (status == .ready && supportsGitWorktree)
        missingPrerequisites = try container.decodeIfPresent([String].self, forKey: .missingPrerequisites) ?? []
        reason = try container.decodeIfPresent(String.self, forKey: .reason)
    }
}

struct AgentWorkspaceAgentReadiness: Decodable, Equatable, Identifiable {
    var id: String { agentId }

    let agentId: String
    let displayName: String
    let agentType: String?
    let status: AgentWorkspaceReadinessStatus
    let available: Bool
    let supportedWorkspaceModes: [String]
    let missingPrerequisites: [String]
    let reason: String?

    enum CodingKeys: String, CodingKey {
        case agentId = "agent_id"
        case displayName = "display_name"
        case agentType = "agent_type"
        case status
        case available
        case supportedWorkspaceModes = "supported_workspace_modes"
        case missingPrerequisites = "missing_prerequisites"
        case reason
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        agentId = try container.decode(String.self, forKey: .agentId)
        displayName = try container.decodeIfPresent(String.self, forKey: .displayName) ?? agentId
        agentType = try container.decodeIfPresent(String.self, forKey: .agentType)
        status = try container.decodeIfPresent(AgentWorkspaceReadinessStatus.self, forKey: .status) ?? .unknown
        available = try container.decodeIfPresent(Bool.self, forKey: .available) ?? status.allowsWorkspaceMutation
        supportedWorkspaceModes = try container.decodeIfPresent([String].self, forKey: .supportedWorkspaceModes) ?? []
        missingPrerequisites = try container.decodeIfPresent([String].self, forKey: .missingPrerequisites) ?? []
        reason = try container.decodeIfPresent(String.self, forKey: .reason)
    }

    var isUsable: Bool {
        available && status.allowsWorkspaceMutation && missingPrerequisites.isEmpty
    }
}

struct AgentWorkspaceReadinessRoutes: Decodable, Equatable {
    let events: String?
    let diff: String?
    let evidence: String?
    let cancel: String?
    let comment: String?
    let promote: String?

    enum CodingKeys: String, CodingKey {
        case events
        case diff
        case evidence
        case cancel
        case comment
        case promote
    }

    init(
        events: String? = nil,
        diff: String? = nil,
        evidence: String? = nil,
        cancel: String? = nil,
        comment: String? = nil,
        promote: String? = nil
    ) {
        self.events = events
        self.diff = diff
        self.evidence = evidence
        self.cancel = cancel
        self.comment = comment
        self.promote = promote
    }

    var hasRequiredRoutes: Bool {
        events != nil && diff != nil && evidence != nil
    }

    var missingRoutes: [String] {
        [
            ("events", events),
            ("diff", diff),
            ("evidence", evidence),
        ]
            .compactMap { key, value in value == nil ? "\(key)_route" : nil }
    }
}
