import Foundation
import Combine

struct MCPPlugin: Codable, Identifiable, Equatable {
    var id: String
    var name: String
    var description: String
    var command: String
    var args: [String]
    var isEnabled: Bool
    var isBuiltIn: Bool
    
    // Status can be: "disconnected", "connecting", "connected", "error"
    var status: String = "disconnected"
    var errorMessage: String? = nil
    
    enum CodingKeys: String, CodingKey {
        case id, name, description, command, args, isEnabled, isBuiltIn
    }
}

class MCPPluginManager: ObservableObject {
    static let shared = MCPPluginManager()
    
    @Published var plugins: [MCPPlugin] = []
    
    private let userDefaultsKey = "across_agents_mcp_plugins"
    
    // Define the built-in plugins
    private let builtInPlugins: [MCPPlugin] = [
        MCPPlugin(
            id: "sqlite",
            name: "SQLite Database",
            description: "允许 AI 读取和分析你的本地 SQLite 数据库文件。",
            command: "uvx",
            args: ["mcp-server-sqlite", "--db-path", ""], // Path to be filled by user
            isEnabled: false,
            isBuiltIn: true
        ),
        MCPPlugin(
            id: "filesystem",
            name: "本地文件系统",
            description: "允许 AI 访问并编辑你指定的文件夹。",
            command: "npx",
            args: ["-y", "@modelcontextprotocol/server-filesystem", ""], // Path to be filled by user
            isEnabled: false,
            isBuiltIn: true
        )
    ]
    
    private init() {
        loadPlugins()
    }
    
    func loadPlugins() {
        if let data = UserDefaults.standard.data(forKey: userDefaultsKey),
           let saved = try? JSONDecoder().decode([MCPPlugin].self, from: data) {
            
            // Merge saved state with built-ins (in case we added new built-ins in an app update)
            var merged = builtInPlugins
            
            for (index, builtIn) in merged.enumerated() {
                if let savedMatch = saved.first(where: { $0.id == builtIn.id }) {
                    merged[index].isEnabled = savedMatch.isEnabled
                    merged[index].args = savedMatch.args
                }
            }
            
            // Add custom plugins from saved
            let customSaved = saved.filter { !$0.isBuiltIn }
            merged.append(contentsOf: customSaved)
            
            self.plugins = merged
        } else {
            self.plugins = builtInPlugins
        }
        
        // Automatically connect enabled plugins on startup
        for plugin in plugins where plugin.isEnabled {
            connectPlugin(id: plugin.id)
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
            }
        }
    }
    
    // MARK: - API Calls to Python Backend
    
    struct MCPConnectRequest: Codable {
        let server_id: String
        let command: String
        let args: [String]
        let env: [String: String]?
    }
    
    struct MCPDisconnectRequest: Codable {
        let server_id: String
    }
    
    private func connectPlugin(id: String) {
        guard let plugin = plugins.first(where: { $0.id == id }) else { return }
        
        // Validation for built-in plugins requiring paths
        if plugin.isBuiltIn {
            let pathArg = plugin.args.last ?? ""
            if pathArg.isEmpty {
                updateStatus(id: id, status: "error", errorMessage: "请先配置路径")
                return
            }
        }
        
        updateStatus(id: id, status: "connecting")
        
        let req = MCPConnectRequest(
            server_id: plugin.id,
            command: plugin.command,
            args: plugin.args,
            env: nil // Extend later if needed
        )
        
        guard let url = URL(string: "http://127.0.0.1:8000/api/mcp/connect") else { return }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        do {
            request.httpBody = try JSONEncoder().encode(req)
        } catch {
            updateStatus(id: id, status: "error", errorMessage: "请求编码失败")
            return
        }
        
        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            if let error = error {
                self?.updateStatus(id: id, status: "error", errorMessage: "网络错误: \(error.localizedDescription)")
                return
            }
            
            if let httpResponse = response as? HTTPURLResponse, !(200...299).contains(httpResponse.statusCode) {
                // Try to parse error from backend
                var errorMsg = "HTTP \(httpResponse.statusCode)"
                if let data = data, let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any], let detail = json["detail"] as? String {
                    errorMsg = detail
                }
                self?.updateStatus(id: id, status: "error", errorMessage: errorMsg)
                return
            }
            
            self?.updateStatus(id: id, status: "connected", errorMessage: nil)
        }.resume()
    }
    
    private func disconnectPlugin(id: String) {
        updateStatus(id: id, status: "disconnected")
        
        let req = MCPDisconnectRequest(server_id: id)
        guard let url = URL(string: "http://127.0.0.1:8000/api/mcp/disconnect") else { return }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONEncoder().encode(req)
        
        URLSession.shared.dataTask(with: request) { _, _, _ in
            // Ignore response for disconnect
        }.resume()
    }
}
