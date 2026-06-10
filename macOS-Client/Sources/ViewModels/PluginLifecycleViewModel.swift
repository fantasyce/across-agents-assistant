import Foundation

@MainActor
final class PluginLifecycleViewModel: ObservableObject {
    @Published var plugins: [AcrossPluginStatus] = []
    @Published var memories: [AcrossMemoryEntry] = []
    @Published var memoryStatusFilter = "pending"
    @Published var newMemoryText = ""
    @Published var isLoadingPlugins = false
    @Published var isLoadingMemories = false
    @Published var isWorking = false
    @Published var isRunningAgentLoopProbe = false
    @Published var agentLoopProbe: AgentLoopRunResponse?
    @Published var message: String?
    @Published var errorMessage: String?

    private let backendBase = "http://backend"

    func load(probe: Bool = false) async {
        await loadPlugins(probe: probe)
        await loadMemories()
    }

    func loadPlugins(probe: Bool = false) async {
        isLoadingPlugins = true
        errorMessage = nil
        defer { isLoadingPlugins = false }

        do {
            let url = URL(string: "\(backendBase)/api/plugins?probe=\(probe ? "true" : "false")")!
            let (data, response) = try await URLSession.shared.data(from: url)
            try Self.validate(response)
            plugins = try JSONDecoder().decode(PluginListResponse.self, from: data).plugins
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func runAction(_ action: String, for plugin: AcrossPluginStatus) async {
        isWorking = true
        message = nil
        errorMessage = nil
        defer { isWorking = false }

        do {
            let escaped = plugin.pluginId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? plugin.pluginId
            let url = URL(string: "\(backendBase)/api/plugins/\(escaped)/actions")!
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(PluginActionRequest(action: action))
            let (_, response) = try await URLSession.shared.data(for: request)
            try Self.validate(response)
            message = "\(plugin.displayName): \(action)"
            await loadPlugins(probe: action == "probe")
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func loadMemories() async {
        isLoadingMemories = true
        errorMessage = nil
        defer { isLoadingMemories = false }

        do {
            var components = URLComponents(string: "\(backendBase)/api/memory/memories")!
            if !memoryStatusFilter.isEmpty {
                components.queryItems = [URLQueryItem(name: "status", value: memoryStatusFilter)]
            }
            let (data, response) = try await URLSession.shared.data(from: components.url!)
            try Self.validate(response)
            let decoded = try JSONDecoder().decode(AcrossMemoryListResponse.self, from: data)
            memories = Array(decoded.memories.reversed())
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func rememberPendingMemory() async {
        let text = newMemoryText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        isWorking = true
        message = nil
        errorMessage = nil
        defer { isWorking = false }

        do {
            let url = URL(string: "\(backendBase)/api/memory/remember")!
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(
                AcrossMemoryRememberRequest(
                    text: text,
                    projectRoot: nil,
                    scope: "global",
                    type: "note",
                    status: "pending",
                    tags: ["aaa-ui"]
                )
            )
            let (_, response) = try await URLSession.shared.data(for: request)
            try Self.validate(response)
            newMemoryText = ""
            memoryStatusFilter = "pending"
            message = "Memory saved for review"
            await loadMemories()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func updateMemory(_ memory: AcrossMemoryEntry, status: String) async {
        isWorking = true
        message = nil
        errorMessage = nil
        defer { isWorking = false }

        do {
            let escaped = memory.id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? memory.id
            let url = URL(string: "\(backendBase)/api/memory/memories/\(escaped)/status")!
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(AcrossMemoryStatusRequest(status: status))
            let (_, response) = try await URLSession.shared.data(for: request)
            try Self.validate(response)
            message = "Memory marked \(status)"
            await loadMemories()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func forgetMemory(_ memory: AcrossMemoryEntry) async {
        isWorking = true
        message = nil
        errorMessage = nil
        defer { isWorking = false }

        do {
            let escaped = memory.id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? memory.id
            let url = URL(string: "\(backendBase)/api/memory/memories/\(escaped)/forget")!
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            let (_, response) = try await URLSession.shared.data(for: request)
            try Self.validate(response)
            message = "Memory forgotten"
            await loadMemories()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func runAgentLoopProbe() async {
        isRunningAgentLoopProbe = true
        isWorking = true
        message = nil
        errorMessage = nil
        defer {
            isRunningAgentLoopProbe = false
            isWorking = false
        }

        do {
            let startURL = URL(string: "\(backendBase)/api/orchestrator/loops")!
            var startRequest = URLRequest(url: startURL)
            startRequest.httpMethod = "POST"
            startRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
            startRequest.httpBody = try JSONEncoder().encode(
                AgentLoopStartRequest(
                    goal: "Plugin Center Agent Loop Probe",
                    projectDir: nil,
                    agent: "owner",
                    maxTurns: 8
                )
            )
            let (startData, startResponse) = try await URLSession.shared.data(for: startRequest)
            try Self.validate(startResponse)
            let started = try JSONDecoder().decode(AgentLoopRunResponse.self, from: startData)

            let escaped = started.loopId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? started.loopId
            let runURL = URL(string: "\(backendBase)/api/orchestrator/loops/\(escaped)/run")!
            var runRequest = URLRequest(url: runURL)
            runRequest.httpMethod = "POST"
            let (runData, runResponse) = try await URLSession.shared.data(for: runRequest)
            try Self.validate(runResponse)
            let completed = try JSONDecoder().decode(AgentLoopRunResponse.self, from: runData)
            agentLoopProbe = completed
            message = "Agent Loop Probe: \(completed.status)"
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private static func validate(_ response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
    }
}
