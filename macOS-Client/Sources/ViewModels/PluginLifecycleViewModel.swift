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
    @Published var agentLoopHealth: AgentLoopHealthResponse?
    @Published var agentLoopEvents: [AgentLoopEventResponse] = []
    @Published var agentLoopEventsLive = false
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
        agentLoopHealth = nil
        agentLoopEvents = []
        agentLoopEventsLive = false
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

            let healthURL = URL(string: "\(backendBase)/api/orchestrator/loops/\(escaped)/health")!
            var healthRequest = URLRequest(url: healthURL)
            healthRequest.httpMethod = "GET"
            do {
                let (healthData, healthResponse) = try await URLSession.shared.data(for: healthRequest)
                try Self.validate(healthResponse)
                agentLoopHealth = try JSONDecoder().decode(AgentLoopHealthResponse.self, from: healthData)
            } catch {
                agentLoopHealth = nil
                message = "Agent Loop Probe: \(completed.status) (health unavailable)"
            }

            let eventResult = await fetchAgentLoopEvents(escapedLoopId: escaped)
            agentLoopEvents = eventResult.events
            agentLoopEventsLive = eventResult.live
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func fetchAgentLoopEvents(escapedLoopId: String) async -> (events: [AgentLoopEventResponse], live: Bool) {
        do {
            let events = try await fetchAgentLoopEventStream(escapedLoopId: escapedLoopId)
            if !events.isEmpty {
                return (events, true)
            }
        } catch {
            // Snapshot fetch below is the compatibility path for older AAA backends.
        }

        do {
            let eventsURL = URL(string: "\(backendBase)/api/orchestrator/loops/\(escapedLoopId)/events")!
            var eventsRequest = URLRequest(url: eventsURL)
            eventsRequest.httpMethod = "GET"
            let (eventsData, eventsResponse) = try await URLSession.shared.data(for: eventsRequest)
            try Self.validate(eventsResponse)
            let events = try JSONDecoder().decode([AgentLoopEventResponse].self, from: eventsData)
            return (events, false)
        } catch {
            return ([], false)
        }
    }

    private func fetchAgentLoopEventStream(escapedLoopId: String) async throws -> [AgentLoopEventResponse] {
        let eventsURL = URL(string: "\(backendBase)/api/orchestrator/loops/\(escapedLoopId)/events/stream")!
        var eventsRequest = URLRequest(url: eventsURL)
        eventsRequest.httpMethod = "GET"
        eventsRequest.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        eventsRequest.setValue("no-cache", forHTTPHeaderField: "Cache-Control")

        let (bytes, response) = try await URLSession.shared.bytes(for: eventsRequest)
        try Self.validate(response)

        var streamData = Data()
        for try await byte in bytes {
            streamData.append(byte)
        }
        let streamText = String(data: streamData, encoding: .utf8) ?? ""
        return Self.decodeAgentLoopEventsFromSSE(streamText)
    }

    nonisolated static func decodeAgentLoopEventsFromSSE(_ text: String) -> [AgentLoopEventResponse] {
        var events: [AgentLoopEventResponse] = []
        var dataLines: [String] = []
        let decoder = JSONDecoder()

        func flush() {
            let payload = dataLines.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
            dataLines.removeAll()
            guard !payload.isEmpty, let data = payload.data(using: .utf8) else { return }
            if let event = try? decoder.decode(AgentLoopEventResponse.self, from: data) {
                events.append(event)
            } else if let batch = try? decoder.decode([AgentLoopEventResponse].self, from: data) {
                events.append(contentsOf: batch)
            }
        }

        for rawLine in text.components(separatedBy: .newlines) {
            let line = rawLine.trimmingCharacters(in: CharacterSet(charactersIn: "\r"))
            if line.isEmpty {
                flush()
            } else if line.hasPrefix("data:") {
                dataLines.append(String(line.dropFirst(5)).trimmingCharacters(in: .whitespaces))
            }
        }
        flush()
        return events
    }

    private static func validate(_ response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
    }
}
