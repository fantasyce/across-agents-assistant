import Foundation
import Combine

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

    // Status can be: "disconnected", "connecting", "connected", "error"
    var status: String = "disconnected"
    var errorMessage: String? = nil

    enum CodingKeys: String, CodingKey {
        case id, name, description, command, args, env, isEnabled, isBuiltIn, isReadOnly
    }
}

class MCPPluginManager: ObservableObject {
    static let shared = MCPPluginManager()

    @Published var plugins: [MCPPlugin] = []

    private let userDefaultsKey = "across_agents_mcp_plugins"

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
        return [
            MCPPlugin(
                id: "local_kb",
                name: "Local Knowledge Base",
                description: "Index and search a local wiki folder for fast, private personal memory.",
                command: cmd,
                args: prod ? ["mcp", "local_kb", "--dir", ""] : ["-m", "mcp_local_kb", "--dir", ""],
                isEnabled: false,
                isBuiltIn: true
            ),
            MCPPlugin(
                id: "external_rag",
                name: "Custom RAG Endpoint",
                description: "Connect to a self-hosted RAG service or enterprise knowledge-base API, such as Dify or AnythingLLM.",
                command: cmd,
                args: prod ? ["mcp", "external_rag", "--endpoint", ""] : ["-m", "mcp_external_rag", "--endpoint", ""],
                isEnabled: false,
                isBuiltIn: true
            ),
            MCPPlugin(
                id: "sqlite",
                name: "SQLite Database",
                description: "Allow AI to read and analyze a local SQLite database file.",
                command: cmd,
                args: prod ? ["mcp", "sqlite", "--db-path", ""] : ["-m", "mcp_sqlite", "--db-path", ""],
                isEnabled: false,
                isBuiltIn: true
            ),
            MCPPlugin(
                id: "filesystem",
                name: "Local Filesystem",
                description: "Allow AI to access and edit folders you explicitly choose.",
                command: cmd,
                args: prod ? ["mcp", "filesystem", ""] : ["-m", "mcp_filesystem", ""],
                isEnabled: false,
                isBuiltIn: true
            )
        ]
    }

    private init() {
        loadPlugins()

        // Wait a very short bit for the backend to fully start before attempting connections
        // (The backend startup has been optimized so it should be ready much faster now)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { [weak self] in
            self?.autoConnectEnabledPlugins()
        }
    }

    private func autoConnectEnabledPlugins() {
        for plugin in plugins where plugin.isEnabled {
            // Only connect if it's currently disconnected or error, to prevent overlapping the initial retry loops
            if plugin.status == "disconnected" || plugin.status == "error" {
                connectPlugin(id: plugin.id)
            }
        }
    }

    func loadPlugins() {
        if let data = UserDefaults.standard.data(forKey: userDefaultsKey),
           let saved = try? JSONDecoder().decode([MCPPlugin].self, from: data) {

            // Merge saved state with built-ins (in case we added new built-ins in an app update)
            var merged = builtInPlugins

            for (index, builtIn) in merged.enumerated() {
                if let savedMatch = saved.first(where: { $0.id == builtIn.id }) {
                    merged[index].isEnabled = savedMatch.isEnabled
                    // Always use the built-in command (it may have changed in an app update, e.g. uvx -> python3)
                    merged[index].command = builtIn.command
                    // Always use the built-in env (it may have changed in an app update)
                    merged[index].env = builtIn.env
                    // Use built-in args structure, but preserve the last arg (the path) from saved state
                    if !savedMatch.args.isEmpty && !builtIn.args.isEmpty {
                        var newArgs = builtIn.args
                        let savedPath = savedMatch.args.last ?? ""
                        newArgs[newArgs.count - 1] = savedPath
                        merged[index].args = newArgs
                    }
                }
            }

            // Add custom plugins from saved
            let customSaved = saved.filter { !$0.isBuiltIn }
            merged.append(contentsOf: customSaved)

            self.plugins = merged
        } else {
            self.plugins = builtInPlugins
        }

        // Auto-connect enabled plugins on load
        for plugin in self.plugins where plugin.isEnabled {
            self.connectPlugin(id: plugin.id)
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
                connectPlugin(id: id)
            }
        }
    }

    func togglePlugin(id: String) {
        if let index = plugins.firstIndex(where: { $0.id == id }) {
            plugins[index].isEnabled.toggle()
            savePlugins()

            if plugins[index].isEnabled {
                connectPlugin(id: id)
            } else {
                disconnectPlugin(id: id)
            }
        }
    }

    func addCustomPlugin(plugin: MCPPlugin) {
        plugins.append(plugin)
        savePlugins()
        if plugin.isEnabled {
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

    private func updateStatus(id: String, status: String, errorMessage: String? = nil) {
        DispatchQueue.main.async {
            if let index = self.plugins.firstIndex(where: { $0.id == id }) {
                self.plugins[index].status = status
                self.plugins[index].errorMessage = errorMessage
                if status == "error" {
                    self.plugins[index].isEnabled = false // Auto disable on fail
                    self.savePlugins()
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

    private func connectPlugin(id: String, retryCount: Int = 0) {
        guard let plugin = plugins.first(where: { $0.id == id }) else { return }

        // Prevent concurrent connection attempts if we are already explicitly connecting,
        // EXCEPT when we are in the retry loop (where we intentionally want to try again)
        if retryCount == 0 && plugin.status == "connecting" {
            return
        }

        // Validation for built-in plugins requiring paths
        if plugin.isBuiltIn {
            let pathArg = plugin.args.last ?? ""
            if pathArg.isEmpty {
                updateStatus(id: id, status: "error", errorMessage: "Configure the required parameters first")
                if let index = plugins.firstIndex(where: { $0.id == id }) {
                    plugins[index].isEnabled = false
                    savePlugins()
                }
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
                plugins[index].isEnabled = false
                savePlugins()
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
                        // Configuration error (e.g. 500 from backend because invalid path), so disable it
                        self?.plugins[index].isEnabled = false
                        self?.savePlugins()
                    }
                }
                return
            }

            self?.updateStatus(id: id, status: "connected", errorMessage: nil)
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
