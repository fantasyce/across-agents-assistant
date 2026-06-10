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

    var supportsCheckpoints: Bool {
        capabilities?["checkpoints"] == true
    }

    var supportsMemoryHooks: Bool {
        capabilities?["memoryHooks"] == true
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

struct AgentLoopStep: Decodable, Equatable {
    let action: AgentLoopAction?
}

struct AgentLoopAction: Decodable, Equatable {
    let type: String?
}
