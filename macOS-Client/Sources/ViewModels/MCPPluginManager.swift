import Foundation
import Combine

enum MCPPluginConfigurationKind: String, Codable, Equatable {
    case none
    case directory
    case file
    case endpoint
}

struct MCPPlugin: Codable, Identifiable, Equatable {
    var id: String
    var name: String
    var description: String
    var command: String
    var args: [String]
    var env: [String: String]?
    var isEnabled: Bool
    var isBuiltIn: Bool
    var isReadOnly: Bool = false
    var configurationKind: MCPPluginConfigurationKind = .none

    // Status can be: "disconnected", "connecting", "connected", "error"
    var status: String = "disconnected"
    var errorMessage: String? = nil
    var implementationMode: String? = nil

    enum CodingKeys: String, CodingKey {
        case id, name, description, command, args, env, isEnabled, isBuiltIn, isReadOnly, configurationKind
    }

    init(
        id: String,
        name: String,
        description: String,
        command: String,
        args: [String],
        env: [String: String]? = nil,
        isEnabled: Bool,
        isBuiltIn: Bool,
        isReadOnly: Bool = false,
        configurationKind: MCPPluginConfigurationKind = .none,
        status: String = "disconnected",
        errorMessage: String? = nil,
        implementationMode: String? = nil
    ) {
        self.id = id
        self.name = name
        self.description = description
        self.command = command
        self.args = args
        self.env = env
        self.isEnabled = isEnabled
        self.isBuiltIn = isBuiltIn
        self.isReadOnly = isReadOnly
        self.configurationKind = configurationKind
        self.status = status
        self.errorMessage = errorMessage
        self.implementationMode = implementationMode
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        name = try container.decode(String.self, forKey: .name)
        description = try container.decode(String.self, forKey: .description)
        command = try container.decode(String.self, forKey: .command)
        args = try container.decode([String].self, forKey: .args)
        env = try container.decodeIfPresent([String: String].self, forKey: .env)
        isEnabled = try container.decode(Bool.self, forKey: .isEnabled)
        isBuiltIn = try container.decode(Bool.self, forKey: .isBuiltIn)
        isReadOnly = try container.decodeIfPresent(Bool.self, forKey: .isReadOnly) ?? false
        configurationKind = try container.decodeIfPresent(MCPPluginConfigurationKind.self, forKey: .configurationKind) ?? .none
    }

    var requiresConfiguration: Bool {
        configurationKind != .none
    }

    var configurationValue: String? {
        requiresConfiguration ? (args.last ?? "") : nil
    }

    var configurationPlaceholderKey: String {
        switch configurationKind {
        case .none:
            return "mcp.noConfigurationRequired"
        case .endpoint:
            return "mcp.endpointPlaceholder"
        case .directory, .file:
            return "mcp.noPath"
        }
    }

    var allowsDirectConfigurationEditing: Bool {
        configurationKind == .endpoint
    }

    var canBrowseConfiguration: Bool {
        configurationKind == .directory || configurationKind == .file
    }

    var canAutoConnectOnLaunch: Bool {
        guard isBuiltIn && isConfigurationComplete else { return false }
        // Local file, SQLite, and knowledge-base MCP servers only bind their
        // configured scope at startup; filesystem reads happen when tools run.
        // Keep custom RAG manual so launch does not open network endpoints.
        return id != "external_rag"
    }

    var isConfigurationComplete: Bool {
        guard requiresConfiguration else { return true }
        return !(args.last ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var implementationLabelKey: String? {
        switch implementationMode {
        case "external":
            return "mcp.implementation.external"
        case "builtin_compatibility":
            return "mcp.implementation.builtinCompatibility"
        case "standard_mcp":
            return "mcp.implementation.standard"
        default:
            return nil
        }
    }
}

class MCPPluginManager: ObservableObject {
    static let shared = MCPPluginManager()

    @Published var plugins: [MCPPlugin] = []

    private let userDefaultsKey = "across_agents_mcp_plugins"
    private let defaultEnabledMigrationKey = "across_agents_mcp_plugins_default_enabled_migration_v044"

    // MARK: - Built-in Plugin Helpers

    /// Returns the command to use for built-in plugins.
    /// In production (bundled backend exists), use the backend binary itself.
    /// In development, fall back to `python3`.
    private var builtInCommand: String {
        if let backendPath = AppDelegate.backendExecutablePath {
            return backendPath
        }
        return "python3"
    }

    /// Returns whether we are running in production mode (bundled backend binary exists).
    private var isProduction: Bool {
        AppDelegate.backendExecutablePath != nil
    }

    // Define the built-in plugins
    private var builtInPlugins: [MCPPlugin] {
        let cmd = builtInCommand
        let prod = isProduction
        let localKnowledgePath = Self.managedDirectoryPath("local-knowledge")
        let sqlitePath = LocalAppPaths.root.appendingPathComponent("assistant.db").path
        let filesystemPath = Self.managedDirectoryPath("workspace")
        return [
            MCPPlugin(
                id: "local_kb",
                name: "Local Knowledge Base",
                description: "Index and search a local wiki folder for fast, private personal memory.",
                command: cmd,
                args: prod ? ["mcp", "local_kb", "--dir", localKnowledgePath] : ["-m", "mcp_local_kb", "--dir", localKnowledgePath],
                isEnabled: true,
                isBuiltIn: true,
                configurationKind: .directory
            ),
            MCPPlugin(
                id: "external_rag",
                name: "Custom RAG Endpoint",
                description: "Connect to a self-hosted RAG service or enterprise knowledge-base API, such as Dify or AnythingLLM.",
                command: cmd,
                args: prod ? ["mcp", "external_rag", "--endpoint", ""] : ["-m", "mcp_external_rag", "--endpoint", ""],
                isEnabled: true,
                isBuiltIn: true,
                configurationKind: .endpoint
            ),
            MCPPlugin(
                id: "sqlite",
                name: "SQLite Database",
                description: "Allow AI to read and analyze a local SQLite database file.",
                command: cmd,
                args: prod ? ["mcp", "sqlite", "--db-path", sqlitePath] : ["-m", "mcp_sqlite", "--db-path", sqlitePath],
                isEnabled: true,
                isBuiltIn: true,
                configurationKind: .file
            ),
            MCPPlugin(
                id: "filesystem",
                name: "Local Filesystem",
                description: "Allow AI to access and edit folders you explicitly choose.",
                command: cmd,
                args: prod ? ["mcp", "filesystem", filesystemPath] : ["-m", "mcp_filesystem", filesystemPath],
                isEnabled: true,
                isBuiltIn: true,
                configurationKind: .directory
            ),
            MCPPlugin(
                id: "across_context",
                name: "Across Context",
                description: "Share durable local memory across configured coding agents through Across Context.",
                command: "across-context",
                args: ["mcp"],
                env: [
                    "ACROSS_AGENTS_ACROSS_CONTEXT_MODE": "external",
                    "ACROSS_HOME": LocalAppPaths.acrossRoot.path
                ],
                isEnabled: true,
                isBuiltIn: true,
                configurationKind: .none
            )
        ]
    }

    private static func managedDirectoryPath(_ name: String) -> String {
        let url = LocalAppPaths.root.appendingPathComponent(name, isDirectory: true)
        try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url.path
    }

    private init() {
        loadPlugins()

        // Wait a very short bit for the backend to fully start before connecting
        // enabled built-in plugins whose configuration is complete.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { [weak self] in
            self?.autoConnectConfiguredBuiltInPlugins()
        }
    }

    private func autoConnectConfiguredBuiltInPlugins() {
        for plugin in plugins where plugin.isEnabled && plugin.canAutoConnectOnLaunch {
            // Only connect if it's currently disconnected or error, to prevent overlapping the initial retry loops
            if plugin.status == "disconnected" || plugin.status == "error" {
                connectPlugin(id: plugin.id)
            }
        }
    }

    func loadPlugins() {
        let shouldApplyDefaultEnabledMigration = !UserDefaults.standard.bool(forKey: defaultEnabledMigrationKey)
        var shouldSaveMergedPlugins = shouldApplyDefaultEnabledMigration

        if let data = UserDefaults.standard.data(forKey: userDefaultsKey),
           let saved = try? JSONDecoder().decode([MCPPlugin].self, from: data) {

            // Merge saved state with built-ins (in case we added new built-ins in an app update)
            var merged = builtInPlugins

            for (index, builtIn) in merged.enumerated() {
                if let savedMatch = saved.first(where: { $0.id == builtIn.id }) {
                    let shouldForceDefaultEnabled = shouldApplyDefaultEnabledMigration && builtIn.isEnabled
                    merged[index].isEnabled = savedMatch.isEnabled || shouldForceDefaultEnabled
                    // Always use the built-in command (it may have changed in an app update, e.g. uvx -> python3)
                    merged[index].command = builtIn.command
                    // Always use the built-in env (it may have changed in an app update)
                    merged[index].env = builtIn.env
                    merged[index].configurationKind = builtIn.configurationKind
                    // Use built-in args structure, but preserve the last arg (the path) from saved state
                    if builtIn.requiresConfiguration && !savedMatch.args.isEmpty && !builtIn.args.isEmpty {
                        var newArgs = builtIn.args
                        var savedPath = savedMatch.args.last ?? ""
                        let builtInDefaultPath = builtIn.args.last ?? ""
                        if Self.isObsoleteAcrossHiddenPath(savedPath)
                            || Self.isObsoleteDocumentsDefaultPath(pluginId: builtIn.id, path: savedPath) {
                            savedPath = builtIn.args.last ?? ""
                            shouldSaveMergedPlugins = true
                        } else if savedPath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !builtInDefaultPath.isEmpty {
                            savedPath = builtInDefaultPath
                            shouldSaveMergedPlugins = true
                        }
                        newArgs[newArgs.count - 1] = savedPath
                        merged[index].args = newArgs
                    } else {
                        merged[index].args = builtIn.args
                    }
                }
            }

            // Add custom plugins from saved
            let customSaved = saved.filter { !$0.isBuiltIn }
            merged.append(contentsOf: customSaved)

            self.plugins = merged
            if shouldApplyDefaultEnabledMigration {
                UserDefaults.standard.set(true, forKey: defaultEnabledMigrationKey)
            }
            if shouldSaveMergedPlugins {
                savePlugins()
            }
        } else {
            self.plugins = builtInPlugins
            if shouldApplyDefaultEnabledMigration {
                UserDefaults.standard.set(true, forKey: defaultEnabledMigrationKey)
            }
        }
    }

    private static func isObsoleteAcrossHiddenPath(_ path: String) -> Bool {
        let expanded = (path as NSString).expandingTildeInPath
        let components = URL(fileURLWithPath: expanded).pathComponents
        let obsoleteNames = [".across_agents", ".across-context", ".across-orchestrator"]
        return components.contains { obsoleteNames.contains($0) }
    }

    private static func isObsoleteDocumentsDefaultPath(pluginId: String, path: String) -> Bool {
        let expanded = (path as NSString).expandingTildeInPath
        let documentsPath = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Documents", isDirectory: true)
            .standardizedFileURL
            .path
        let standardizedPath = URL(fileURLWithPath: expanded).standardizedFileURL.path

        switch pluginId {
        case "local_kb":
            return standardizedPath == URL(fileURLWithPath: documentsPath)
                .appendingPathComponent("mywiki", isDirectory: true)
                .standardizedFileURL
                .path
        case "filesystem":
            return standardizedPath == documentsPath
        default:
            return false
        }
    }

    func savePlugins() {
        if let data = try? JSONEncoder().encode(plugins) {
            UserDefaults.standard.set(data, forKey: userDefaultsKey)
        }
    }

    func updatePluginArgs(id: String, args: [String]) {
        if let index = plugins.firstIndex(where: { $0.id == id }) {
            plugins[index].args = args
            savePlugins()

            // Reconnect if it's already enabled
            if plugins[index].isEnabled {
                if plugins[index].isConfigurationComplete {
                    connectPlugin(id: id)
                } else {
                    disconnectPlugin(id: id)
                }
            }
        }
    }

    func togglePlugin(id: String) {
        if let index = plugins.firstIndex(where: { $0.id == id }) {
            plugins[index].isEnabled.toggle()
            savePlugins()

            if plugins[index].isEnabled {
                if plugins[index].isConfigurationComplete {
                    connectPlugin(id: id)
                } else {
                    updateStatus(id: id, status: "disconnected")
                }
            } else {
                disconnectPlugin(id: id)
            }
        }
    }

    func addCustomPlugin(plugin: MCPPlugin) {
        plugins.append(plugin)
        savePlugins()
        if plugin.isEnabled && plugin.isConfigurationComplete {
            connectPlugin(id: plugin.id)
        }
    }

    func removeCustomPlugin(id: String) {
        if let index = plugins.firstIndex(where: { $0.id == id }) {
            if plugins[index].isEnabled {
                disconnectPlugin(id: id)
            }
            plugins.remove(at: index)
            savePlugins()
        }
    }

    private func updateStatus(
        id: String,
        status: String,
        errorMessage: String? = nil,
        implementationMode: String? = nil
    ) {
        DispatchQueue.main.async {
            if let index = self.plugins.firstIndex(where: { $0.id == id }) {
                self.plugins[index].status = status
                self.plugins[index].errorMessage = errorMessage
                if let implementationMode {
                    self.plugins[index].implementationMode = implementationMode
                } else if status != "connected" {
                    self.plugins[index].implementationMode = nil
                }
            }
        }
    }

    // MARK: - API Calls to Python Backend

    struct MCPConnectRequest: Codable {
        let server_id: String
        let command: String
        let args: [String]
        let env: [String: String]?
        let allowed_paths: [String]?
        let readonly: Bool
    }

    struct MCPDisconnectRequest: Codable {
        let server_id: String
    }

    struct MCPConnectResponse: Codable {
        let status: String?
        let implementation: String?
        let connectionNote: String?

        enum CodingKeys: String, CodingKey {
            case status
            case implementation
            case connectionNote = "connection_note"
        }
    }

    private func connectPlugin(id: String, retryCount: Int = 0) {
        guard let plugin = plugins.first(where: { $0.id == id }) else { return }

        // Prevent concurrent connection attempts if we are already explicitly connecting,
        // EXCEPT when we are in the retry loop (where we intentionally want to try again)
        if retryCount == 0 && plugin.status == "connecting" {
            return
        }

        // Validation for plugins requiring user-supplied paths or endpoints.
        if plugin.requiresConfiguration {
            if !plugin.isConfigurationComplete {
                updateStatus(id: id, status: "disconnected")
                return
            }
        }

        updateStatus(id: id, status: "connecting")

        let req = MCPConnectRequest(
            server_id: plugin.id,
            command: plugin.command,
            args: plugin.args,
            env: plugin.env,
            allowed_paths: nil,
            readonly: plugin.isReadOnly
        )

        guard let url = URL(string: "http://backend/api/mcp/connect") else { return }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        do {
            request.httpBody = try JSONEncoder().encode(req)
        } catch {
            updateStatus(id: id, status: "error", errorMessage: "Failed to encode request")
            if let index = plugins.firstIndex(where: { $0.id == id }) {
                if !plugins[index].isBuiltIn {
                    plugins[index].isEnabled = false
                    savePlugins()
                }
            }
            return
        }

        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            if let error = error {
                if retryCount < 40 {
                    // Backend might still be starting up, retry after 0.5 seconds (up to 20 seconds total)
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                        self?.connectPlugin(id: id, retryCount: retryCount + 1)
                    }
                    return
                }
                self?.updateStatus(id: id, status: "error", errorMessage: "Network error: \(error.localizedDescription)")
                DispatchQueue.main.async {
                    if let index = self?.plugins.firstIndex(where: { $0.id == id }) {
                        // Do NOT auto-disable built-in plugins on network error, so they can retry on next launch
                        if !(self?.plugins[index].isBuiltIn ?? false) {
                            self?.plugins[index].isEnabled = false
                            self?.savePlugins()
                        }
                    }
                }
                return
            }

            if let httpResponse = response as? HTTPURLResponse, !(200...299).contains(httpResponse.statusCode) {
                // Try to parse error from backend
                var errorMsg = "HTTP \(httpResponse.statusCode)"
                if let data = data, let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any], let detail = json["detail"] as? String {
                    errorMsg = detail
                }
                self?.updateStatus(id: id, status: "error", errorMessage: errorMsg)
                DispatchQueue.main.async {
                    if let index = self?.plugins.firstIndex(where: { $0.id == id }) {
                        // Custom plugin HTTP failures likely indicate a broken command/configuration.
                        // Built-in plugins stay enabled so users can repair the path/endpoint in place.
                        if !(self?.plugins[index].isBuiltIn ?? false) {
                            self?.plugins[index].isEnabled = false
                            self?.savePlugins()
                        }
                    }
                }
                return
            }

            let connectResponse = data.flatMap { try? JSONDecoder().decode(MCPConnectResponse.self, from: $0) }
            self?.updateStatus(
                id: id,
                status: "connected",
                errorMessage: nil,
                implementationMode: connectResponse?.implementation
            )
        }.resume()
    }

    private func disconnectPlugin(id: String) {
        updateStatus(id: id, status: "disconnected")

        let req = MCPDisconnectRequest(server_id: id)
        guard let url = URL(string: "http://backend/api/mcp/disconnect") else { return }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONEncoder().encode(req)

        URLSession.shared.dataTask(with: request) { _, _, _ in
            // Ignore response for disconnect
        }.resume()
    }
}
