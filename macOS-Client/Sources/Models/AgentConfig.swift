import Foundation

enum AgentIDs {
    static let openclaw = "openclaw"
    static let opencode = "opencode"
    static let cursor = "cursor"

    static func normalized(_ id: String?) -> String? {
        guard let id else { return nil }
        return id
    }
}

enum AgentStatus: String, Codable {
    case installed
    case notInstalled = "not_found"
    case notAuthenticated = "not_authenticated"
    case unavailable
    case invalidPath = "invalid_path"
}

struct AgentConfig: Identifiable, Codable {
    let id: String
    var name: String
    var executablePath: String?
    var version: String?
    var status: AgentStatus
    var configuredPath: String? = nil
    var source: String? = nil
    var detectionMethod: String? = nil
    var error: String? = nil
    var candidatePaths: [String]? = nil
    var selectedModel: String? = nil
    var availableModels: [String]? = nil

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case executablePath = "executable_path"
        case version
        case status
        case configuredPath = "configured_path"
        case source
        case detectionMethod = "detection_method"
        case error
        case candidatePaths = "candidate_paths"
        case selectedModel = "selected_model"
        case availableModels = "available_models"
    }

    var iconName: String {
        "agent.\((AgentIDs.normalized(id) ?? id).lowercased())"
    }

    static let localAgent = AgentConfig(
        id: AgentIDs.openclaw,
        name: "OpenClaw",
        executablePath: nil,
        version: nil,
        status: .notInstalled,
        selectedModel: "sonnet",
        availableModels: ["sonnet", "opus", "claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"]
    )

    static let hermes = AgentConfig(
        id: "hermes",
        name: "Hermes",
        executablePath: nil,
        version: nil,
        status: .notInstalled
    )

    static let claude = AgentConfig(
        id: "claude",
        name: "Claude Code",
        executablePath: nil,
        version: nil,
        status: .notInstalled
    )

    static let codex = AgentConfig(
        id: "codex",
        name: "Codex",
        executablePath: nil,
        version: nil,
        status: .notInstalled,
        selectedModel: "gpt-5.5",
        availableModels: ["gpt-5.5", "gpt-5.4-mini", "o3", "gpt-5-codex"]
    )

    static let opencode = AgentConfig(
        id: AgentIDs.opencode,
        name: "OpenCode",
        executablePath: nil,
        version: nil,
        status: .notInstalled,
        availableModels: ["anthropic/claude-sonnet-4-5", "openai/gpt-5", "google/gemini-2.5-pro", "deepseek/deepseek-chat"]
    )

    static let cursor = AgentConfig(
        id: AgentIDs.cursor,
        name: "Cursor Agent",
        executablePath: nil,
        version: nil,
        status: .notInstalled,
        selectedModel: "auto",
        availableModels: ["auto", "gpt-5", "claude-sonnet-4.5", "claude-opus-4.1"]
    )
}
