import Foundation

enum AgentIDs {
    static let openclaw = "openclaw"

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
        status: .notInstalled
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
        selectedModel: "gpt-5-codex",
        availableModels: ["gpt-5-codex", "gpt-5.1", "o3"]
    )
}
