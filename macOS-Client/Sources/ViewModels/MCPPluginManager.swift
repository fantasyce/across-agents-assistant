import Foundation
import Combine

enum MCPPluginManifestImportError: LocalizedError {
    case manifestMissing
    case manifestInvalid
    case invalidServer(String)
    case reservedServer(String)
    case unsupportedEnvironment(String)
    case serverBusy(String)

    var errorDescription: String? {
        switch self {
        case .manifestMissing:
            return "The selected item does not contain an .mcp.json file."
        case .manifestInvalid:
            return "The MCP manifest is not valid JSON."
        case .invalidServer(let serverID):
            return "The MCP server \(serverID) is missing a valid command."
        case .reservedServer(let serverID):
            return "The MCP server id \(serverID) is reserved by AAA."
        case .unsupportedEnvironment(let serverID):
            return "The MCP server \(serverID) contains environment values that AAA will not store in preferences."
        case .serverBusy(let serverID):
            return "The MCP server \(serverID) is already being updated. Try again after the current connection finishes."
        }
    }
}

enum MCPPluginManifestImporter {
    private struct Manifest: Decodable {
        let mcpServers: [String: Server]
    }

    private struct Server: Decodable {
        let command: String
        let args: [String]?
        let env: [String: String]?
    }

    static func load(from selectedURL: URL) throws -> [MCPPlugin] {
        var isDirectory: ObjCBool = false
        guard FileManager.default.fileExists(atPath: selectedURL.path, isDirectory: &isDirectory) else {
            throw MCPPluginManifestImportError.manifestMissing
        }
        let manifestURL = isDirectory.boolValue
            ? selectedURL.appendingPathComponent(".mcp.json", isDirectory: false)
            : selectedURL
        guard FileManager.default.fileExists(atPath: manifestURL.path) else {
            throw MCPPluginManifestImportError.manifestMissing
        }
        let manifest: Manifest
        do {
            manifest = try JSONDecoder().decode(Manifest.self, from: Data(contentsOf: manifestURL))
        } catch {
            throw MCPPluginManifestImportError.manifestInvalid
        }
        return try manifest.mcpServers.keys.sorted().map { serverID in
            guard let server = manifest.mcpServers[serverID],
                  serverID.range(
                    of: "^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
                    options: .regularExpression
                  ) != nil,
                  !serverID.contains("__"),
                  !server.command.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                throw MCPPluginManifestImportError.invalidServer(serverID)
            }
            if !(server.env ?? [:]).isEmpty {
                throw MCPPluginManifestImportError.unsupportedEnvironment(serverID)
            }
            return MCPPlugin(
                id: serverID,
                name: serverID
                    .replacingOccurrences(of: "-", with: " ")
                    .replacingOccurrences(of: "_", with: " ")
                    .localizedCapitalized,
                description: "Imported local MCP server.",
                command: server.command,
                args: server.args ?? [],
                isEnabled: true,
                isBuiltIn: false,
                isReadOnly: true,
                configurationKind: .none
            )
        }
    }
}

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
        guard isConfigurationComplete else { return false }
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
    private var didStartDeferredAutoConnect = false
    private var deferredAutoConnectIDs: [String] = []
    private let autoConnectPriority = ["across_context", "filesystem", "sqlite", "local_kb"]
    private var activeConnectionTasks: [String: URLSessionDataTask] = [:]
    private var pendingRemovalIDs: Set<String> = []
    private var pendingReplacementRollbacks: [String: MCPPlugin] = [:]
    private var busyPluginIDs: Set<String> = []

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
    }

    /// Start optional MCP subprocesses only after Work has left its core
    /// bootstrap state. Connections are serialized so three packaged Python
    /// runtimes do not compete with the first usable window.
    func startAutoConnectAfterCoreReady() {
        DispatchQueue.main.async { [weak self] in
            guard let self, !self.didStartDeferredAutoConnect else { return }
            self.didStartDeferredAutoConnect = true
            let eligible = self.plugins.filter {
                $0.isEnabled
                    && $0.canAutoConnectOnLaunch
                    && ($0.status == "disconnected" || $0.status == "error")
            }
            let priority = Dictionary(uniqueKeysWithValues: self.autoConnectPriority.enumerated().map { ($1, $0) })
            self.deferredAutoConnectIDs = eligible
                .map(\.id)
                .sorted { (priority[$0] ?? Int.max) < (priority[$1] ?? Int.max) }
            self.connectNextDeferredPlugin()
        }
    }

    private func connectNextDeferredPlugin() {
        guard !deferredAutoConnectIDs.isEmpty else {
            StartupTelemetry.mark("mcp_autoconnect_complete")
            return
        }
        let id = deferredAutoConnectIDs.removeFirst()
        connectPlugin(id: id) { [weak self] in
            StartupTelemetry.mark("mcp_\(id)_complete")
            self?.connectNextDeferredPlugin()
        }
    }

    func loadPlugins() {
        let shouldApplyDefaultEnabledMigration = !AppUserDefaults.current.bool(forKey: defaultEnabledMigrationKey)
        var shouldSaveMergedPlugins = shouldApplyDefaultEnabledMigration

        if let data = AppUserDefaults.current.data(forKey: userDefaultsKey),
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
                        let runtimeRebasedPath = Self.rebasedBuiltInManagedPath(
                            pluginId: builtIn.id,
                            savedPath: savedPath,
                            builtInDefaultPath: builtInDefaultPath
                        )
                        if runtimeRebasedPath != savedPath {
                            savedPath = runtimeRebasedPath
                        } else if Self.isObsoleteAcrossHiddenPath(savedPath)
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
            let customSaved = saved.filter { !$0.isBuiltIn }.map { plugin -> MCPPlugin in
                var sanitized = plugin
                if !(sanitized.env ?? [:]).isEmpty {
                    sanitized.env = nil
                    shouldSaveMergedPlugins = true
                }
                return sanitized
            }
            merged.append(contentsOf: customSaved)

            self.plugins = merged
            if shouldApplyDefaultEnabledMigration {
                AppUserDefaults.current.set(true, forKey: defaultEnabledMigrationKey)
            }
            if shouldSaveMergedPlugins {
                savePlugins()
            }
        } else {
            self.plugins = builtInPlugins
            if shouldApplyDefaultEnabledMigration {
                AppUserDefaults.current.set(true, forKey: defaultEnabledMigrationKey)
            }
        }
    }

    private static func isObsoleteAcrossHiddenPath(_ path: String) -> Bool {
        let expanded = (path as NSString).expandingTildeInPath
        let components = URL(fileURLWithPath: expanded).pathComponents
        let obsoleteNames = [".across_agents", ".across-context", ".across-orchestrator"]
        return components.contains { obsoleteNames.contains($0) }
    }

    static func rebasedBuiltInManagedPath(
        pluginId: String,
        savedPath: String,
        builtInDefaultPath: String
    ) -> String {
        guard !savedPath.isEmpty, !builtInDefaultPath.isEmpty else { return savedPath }
        let expectedLeaf: String
        switch pluginId {
        case "local_kb": expectedLeaf = "local-knowledge"
        case "sqlite": expectedLeaf = "assistant.db"
        case "filesystem": expectedLeaf = "workspace"
        default: return savedPath
        }
        let saved = URL(fileURLWithPath: (savedPath as NSString).expandingTildeInPath).standardizedFileURL
        let current = URL(fileURLWithPath: (builtInDefaultPath as NSString).expandingTildeInPath).standardizedFileURL
        guard saved.path != current.path else { return savedPath }
        let suffix = ["data", "across-agents-assistant", expectedLeaf]
        guard saved.pathComponents.count >= suffix.count,
              Array(saved.pathComponents.suffix(suffix.count)) == suffix else {
            return savedPath
        }
        return builtInDefaultPath
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
        let sanitized = plugins.map { plugin -> MCPPlugin in
            guard !plugin.isBuiltIn else { return plugin }
            var custom = plugin
            custom.env = nil
            return custom
        }
        if let data = try? JSONEncoder().encode(sanitized) {
            AppUserDefaults.current.set(data, forKey: userDefaultsKey)
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

    func updateReadOnly(id: String, isReadOnly: Bool) {
        guard !busyPluginIDs.contains(id), !pendingRemovalIDs.contains(id) else { return }
        guard let index = plugins.firstIndex(where: { $0.id == id && !$0.isBuiltIn }) else { return }
        plugins[index].isReadOnly = isReadOnly
        savePlugins()
        if plugins[index].isEnabled && plugins[index].isConfigurationComplete {
            connectPlugin(id: id)
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

    @discardableResult
    func addCustomPlugin(plugin: MCPPlugin) -> Bool {
        guard !plugin.isBuiltIn else { return false }
        guard !busyPluginIDs.contains(plugin.id),
              !pendingRemovalIDs.contains(plugin.id) else { return false }
        if let index = plugins.firstIndex(where: { $0.id == plugin.id }) {
            guard !plugins[index].isBuiltIn else { return false }
            let wasEnabled = plugins[index].isEnabled
            let previous = plugins[index]
            plugins[index] = plugin
            if plugin.isEnabled && plugin.isConfigurationComplete {
                pendingReplacementRollbacks[plugin.id] = previous
                connectPlugin(id: plugin.id)
            } else if wasEnabled {
                savePlugins()
                disconnectPlugin(id: plugin.id)
            } else {
                savePlugins()
            }
            return true
        }
        plugins.append(plugin)
        savePlugins()
        if plugin.isEnabled && plugin.isConfigurationComplete {
            connectPlugin(id: plugin.id)
        }
        return true
    }

    @discardableResult
    func importPlugins(from selectedURL: URL) throws -> [String] {
        let imported = try MCPPluginManifestImporter.load(from: selectedURL)
        let builtInIDs = Set(plugins.filter(\.isBuiltIn).map(\.id))
        if let collision = imported.first(where: { builtInIDs.contains($0.id) }) {
            throw MCPPluginManifestImportError.reservedServer(collision.id)
        }
        if let busy = imported.first(where: {
            busyPluginIDs.contains($0.id) || pendingRemovalIDs.contains($0.id)
        }) {
            throw MCPPluginManifestImportError.serverBusy(busy.id)
        }
        for plugin in imported {
            guard addCustomPlugin(plugin: plugin) else {
                throw MCPPluginManifestImportError.serverBusy(plugin.id)
            }
        }
        return imported.map(\.id)
    }

    func removeCustomPlugin(id: String) {
        if let index = plugins.firstIndex(where: { $0.id == id && !$0.isBuiltIn }) {
            plugins[index].isEnabled = false
            plugins[index].status = "disconnecting"
            plugins[index].errorMessage = nil
            pendingRemovalIDs.insert(id)
            busyPluginIDs.insert(id)
            savePlugins()
            if activeConnectionTasks[id] == nil {
                performPendingRemoval(id: id)
            }
        }
    }

    private func performPendingRemoval(id: String) {
        guard pendingRemovalIDs.contains(id) else { return }
        disconnectPlugin(id: id, forget: true) { [weak self] success, errorMessage in
            guard let self else { return }
            DispatchQueue.main.async {
                guard self.pendingRemovalIDs.contains(id) else { return }
                if success {
                    self.pendingRemovalIDs.remove(id)
                    self.pendingReplacementRollbacks.removeValue(forKey: id)
                    self.busyPluginIDs.remove(id)
                    self.plugins.removeAll { $0.id == id && !$0.isBuiltIn }
                    self.savePlugins()
                } else if let index = self.plugins.firstIndex(where: { $0.id == id && !$0.isBuiltIn }) {
                    self.pendingRemovalIDs.remove(id)
                    self.busyPluginIDs.remove(id)
                    self.plugins[index].status = "error"
                    self.plugins[index].errorMessage = errorMessage ?? "Failed to remove MCP plugin"
                    self.savePlugins()
                }
            }
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

    func recordConnectionFailure(id: String, message: String) {
        // Keep the user's installation enabled. A missing executable or a
        // transient startup failure should remain visible and retryable on the
        // next launch instead of silently changing persisted intent.
        let applyFailure = {
            self.busyPluginIDs.remove(id)
            if let previous = self.pendingReplacementRollbacks.removeValue(forKey: id),
               let index = self.plugins.firstIndex(where: { $0.id == id && !$0.isBuiltIn }) {
                self.plugins[index] = previous
                self.plugins[index].status = "error"
                self.plugins[index].errorMessage = message
                self.savePlugins()
                return
            }
            if let index = self.plugins.firstIndex(where: { $0.id == id }) {
                self.plugins[index].status = "error"
                self.plugins[index].errorMessage = message
            }
        }
        if Thread.isMainThread {
            applyFailure()
        } else {
            DispatchQueue.main.async(execute: applyFailure)
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
        let forget: Bool
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

    private func connectPlugin(
        id: String,
        retryCount: Int = 0,
        lifecycleAlreadyClaimed: Bool = false,
        completion: (() -> Void)? = nil
    ) {
        guard !pendingRemovalIDs.contains(id) else {
            completion?()
            return
        }
        if !lifecycleAlreadyClaimed {
            guard !busyPluginIDs.contains(id) else {
                completion?()
                return
            }
            busyPluginIDs.insert(id)
        }
        guard let plugin = plugins.first(where: { $0.id == id }) else {
            busyPluginIDs.remove(id)
            completion?()
            return
        }

        // Validation for plugins requiring user-supplied paths or endpoints.
        if plugin.requiresConfiguration {
            if !plugin.isConfigurationComplete {
                busyPluginIDs.remove(id)
                updateStatus(id: id, status: "disconnected")
                completion?()
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

        guard let url = URL(string: "http://backend/api/mcp/connect") else {
            busyPluginIDs.remove(id)
            completion?()
            return
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        do {
            request.httpBody = try JSONEncoder().encode(req)
        } catch {
            recordConnectionFailure(id: id, message: "Failed to encode request")
            completion?()
            return
        }

        let task = URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            guard let self else { return }
            DispatchQueue.main.async {
                self.activeConnectionTasks[id] = nil
                if self.pendingRemovalIDs.contains(id) {
                    self.performPendingRemoval(id: id)
                    completion?()
                    return
                }

            if let error = error {
                if retryCount < 40 {
                    // Backend might still be starting up, retry after 0.5 seconds (up to 20 seconds total)
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                            self.connectPlugin(
                                id: id,
                                retryCount: retryCount + 1,
                                lifecycleAlreadyClaimed: true,
                                completion: completion
                            )
                    }
                    return
                }
                    self.recordConnectionFailure(id: id, message: "Network error: \(error.localizedDescription)")
                    completion?()
                return
            }

            if let httpResponse = response as? HTTPURLResponse, !(200...299).contains(httpResponse.statusCode) {
                // Try to parse error from backend
                var errorMsg = "HTTP \(httpResponse.statusCode)"
                if let data = data, let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any], let detail = json["detail"] as? String {
                    errorMsg = detail
                }
                    self.recordConnectionFailure(id: id, message: errorMsg)
                    completion?()
                return
            }

            let connectResponse = data.flatMap { try? JSONDecoder().decode(MCPConnectResponse.self, from: $0) }
                if self.pendingReplacementRollbacks.removeValue(forKey: id) != nil {
                    self.savePlugins()
                }
                self.busyPluginIDs.remove(id)
                self.updateStatus(
                id: id,
                status: "connected",
                errorMessage: nil,
                implementationMode: connectResponse?.implementation
            )
                completion?()
            }
        }
        activeConnectionTasks[id] = task
        task.resume()
    }

    private func disconnectPlugin(
        id: String,
        forget: Bool = false,
        completion: ((Bool, String?) -> Void)? = nil
    ) {
        if !forget {
            updateStatus(id: id, status: "disconnected")
        }

        let req = MCPDisconnectRequest(server_id: id, forget: forget)
        guard let url = URL(string: "http://backend/api/mcp/disconnect") else {
            completion?(false, "Invalid backend URL")
            return
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONEncoder().encode(req)

        URLSession.shared.dataTask(with: request) { _, response, error in
            if let error {
                completion?(false, error.localizedDescription)
                return
            }
            guard let httpResponse = response as? HTTPURLResponse,
                  (200...299).contains(httpResponse.statusCode) else {
                completion?(false, "Backend rejected MCP disconnect")
                return
            }
            completion?(true, nil)
        }.resume()
    }
}
