import Foundation

enum AgentLoopTimelineMode: String, CaseIterable, Identifiable {
    case live
    case snapshot

    var id: String { rawValue }
    var followStream: Bool { self == .live }
}

enum AgentLoopTimelineSource: String, CaseIterable, Equatable {
    case live
    case snapshot
    case fallback
    case unavailable

    var isLive: Bool { self == .live }

    static var localizationKeys: [String] {
        allCases.map(\.localizationKey)
    }

    var localizationKey: String {
        switch self {
        case .live:
            return "plugins.loop.eventsLive"
        case .snapshot:
            return "plugins.loop.eventsSnapshot"
        case .fallback:
            return "plugins.loop.eventsFallback"
        case .unavailable:
            return "plugins.loop.eventsUnavailable"
        }
    }
}

@MainActor
final class PluginLifecycleViewModel: ObservableObject {
    @Published var plugins: [AcrossPluginStatus] = []
    @Published var memories: [AcrossMemoryEntry] = []
    @Published var agentLoopMemoryMetrics: AgentLoopMemoryMetricsResponse?
    @Published var memoryStatusFilter = "pending"
    @Published var newMemoryText = ""
    @Published var isLoadingPlugins = false
    @Published var isLoadingMemories = false
    @Published var isWorking = false
    @Published var isRunningAgentLoopProbe = false
    @Published var agentLoopProbe: AgentLoopRunResponse?
    @Published var agentLoopHealth: AgentLoopHealthResponse?
    @Published var agentLoopEvidenceSummary: AgentLoopEvidenceSummaryResponse?
    @Published var agentLoopTelemetry: AgentLoopTelemetryResponse?
    @Published var agentLoopEvents: [AgentLoopEventResponse] = []
    // Compatibility mirror for older tests/views; agentLoopTimelineSource is the source of truth.
    @Published private(set) var agentLoopEventsLive = false
    @Published var agentLoopTimelineMode: AgentLoopTimelineMode = .live
    @Published var agentLoopTimelineSource: AgentLoopTimelineSource?
    @Published var autopilotReview: AutopilotReviewResponse?
    @Published var autopilotCandidatePlan: AutopilotCandidatePlanResponse?
    @Published var isRunningAutopilotReview = false
    @Published var highlightedMemoryId: String?
    @Published var message: String?
    @Published var errorMessage: String?

    private let backendBase = "http://backend"

    var agentLoopMemoryCandidates: [AgentLoopEvidenceMemoryCandidate] {
        agentLoopEvidenceSummary?.memoryCandidates?.candidates ?? []
    }

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
            await loadAgentLoopMemoryMetrics()
        } catch {
            errorMessage = error.localizedDescription
            agentLoopMemoryMetrics = nil
        }
    }

    func loadAgentLoopMemoryMetrics() async {
        do {
            let url = URL(string: "\(backendBase)/api/memory/agent-loop-metrics")!
            let (data, response) = try await URLSession.shared.data(from: url)
            try Self.validate(response)
            agentLoopMemoryMetrics = try JSONDecoder().decode(AgentLoopMemoryMetricsResponse.self, from: data)
        } catch {
            agentLoopMemoryMetrics = nil
        }
    }

    func runAutopilotReview() async {
        isRunningAutopilotReview = true
        isWorking = true
        message = nil
        errorMessage = nil
        defer {
            isRunningAutopilotReview = false
            isWorking = false
        }

        do {
            let reviewURL = URL(string: "\(backendBase)/api/autopilot/review")!
            var reviewRequest = URLRequest(url: reviewURL)
            reviewRequest.httpMethod = "POST"
            reviewRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
            reviewRequest.httpBody = try JSONEncoder().encode(AutopilotReviewRequest(fetch: false, mode: "plugin-center"))
            let (reviewData, reviewResponse) = try await URLSession.shared.data(for: reviewRequest)
            try Self.validate(reviewResponse)
            autopilotReview = try JSONDecoder().decode(AutopilotReviewResponse.self, from: reviewData)

            let planURL = URL(string: "\(backendBase)/api/autopilot/candidate-plan")!
            var planRequest = URLRequest(url: planURL)
            planRequest.httpMethod = "POST"
            planRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
            planRequest.httpBody = try JSONEncoder().encode(
                AutopilotCandidatePlanRequest(
                    goal: "Review Across ecosystem and propose the next safe autonomous iteration",
                    targetProduct: "across-autopilot"
                )
            )
            let (planData, planResponse) = try await URLSession.shared.data(for: planRequest)
            try Self.validate(planResponse)
            autopilotCandidatePlan = try JSONDecoder().decode(AutopilotCandidatePlanResponse.self, from: planData)
            message = "Across Autopilot review generated"
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

    func focusMemoryCandidate(_ candidate: AgentLoopEvidenceMemoryCandidate) async {
        highlightedMemoryId = candidate.memoryId
        memoryStatusFilter = Self.memoryReviewStatusFilter(for: candidate)
        await loadMemories()
    }

    nonisolated static func memoryReviewStatusFilter(for candidate: AgentLoopEvidenceMemoryCandidate) -> String {
        let status = candidate.memoryStatus?.trimmingCharacters(in: .whitespacesAndNewlines)
        if let status, !status.isEmpty {
            return status
        }
        return "pending"
    }

    func runAgentLoopProbe() async {
        isRunningAgentLoopProbe = true
        isWorking = true
        message = nil
        errorMessage = nil
        agentLoopHealth = nil
        agentLoopEvidenceSummary = nil
        agentLoopTelemetry = nil
        agentLoopEvents = []
        agentLoopEventsLive = false
        agentLoopTimelineSource = nil
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
            let timelineMode = agentLoopTimelineMode
            let eventStreamTask: Task<[AgentLoopEventResponse], Error>? = timelineMode == .live
                ? Task { try await fetchAgentLoopEventStream(escapedLoopId: escaped, follow: true, liveUpdate: true) }
                : nil
            let runURL = URL(string: "\(backendBase)/api/orchestrator/loops/\(escaped)/run")!
            var runRequest = URLRequest(url: runURL)
            runRequest.httpMethod = "POST"
            let completed: AgentLoopRunResponse
            do {
                let (runData, runResponse) = try await URLSession.shared.data(for: runRequest)
                try Self.validate(runResponse)
                completed = try JSONDecoder().decode(AgentLoopRunResponse.self, from: runData)
            } catch {
                eventStreamTask?.cancel()
                throw error
            }
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

            let summaryURL = URL(string: "\(backendBase)/api/orchestrator/loops/\(escaped)/evidence-summary")!
            var summaryRequest = URLRequest(url: summaryURL)
            summaryRequest.httpMethod = "GET"
            do {
                let (summaryData, summaryResponse) = try await URLSession.shared.data(for: summaryRequest)
                try Self.validate(summaryResponse)
                agentLoopEvidenceSummary = try JSONDecoder().decode(AgentLoopEvidenceSummaryResponse.self, from: summaryData)
            } catch {
                agentLoopEvidenceSummary = nil
            }

            let telemetryURL = URL(string: "\(backendBase)/api/orchestrator/loops/\(escaped)/telemetry")!
            var telemetryRequest = URLRequest(url: telemetryURL)
            telemetryRequest.httpMethod = "GET"
            do {
                let (telemetryData, telemetryResponse) = try await URLSession.shared.data(for: telemetryRequest)
                try Self.validate(telemetryResponse)
                agentLoopTelemetry = try JSONDecoder().decode(AgentLoopTelemetryResponse.self, from: telemetryData)
            } catch {
                agentLoopTelemetry = nil
            }

            let eventResult = await fetchAgentLoopEvents(
                escapedLoopId: escaped,
                mode: timelineMode,
                streamTask: eventStreamTask
            )
            agentLoopEvents = eventResult.events
            agentLoopTimelineSource = eventResult.source
            agentLoopEventsLive = eventResult.source.isLive
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func fetchAgentLoopEvents(
        escapedLoopId: String,
        mode: AgentLoopTimelineMode,
        streamTask: Task<[AgentLoopEventResponse], Error>? = nil
    ) async -> (events: [AgentLoopEventResponse], source: AgentLoopTimelineSource) {
        if let streamTask {
            do {
                let events = try await streamTask.value
                let latestSequence = events.compactMap(\.sequence).max()
                let snapshot = (try? await fetchAgentLoopEventSnapshot(
                    escapedLoopId: escapedLoopId,
                    afterSequence: latestSequence
                )) ?? []
                let merged = Self.mergedAgentLoopEvents(events, snapshot)
                if !merged.isEmpty {
                    return (merged, events.isEmpty ? .snapshot : .live)
                }
            } catch {
                // Snapshot fetch below is the compatibility path for older AAA backends.
            }
        } else {
            do {
                let events = try await fetchAgentLoopEventStream(
                    escapedLoopId: escapedLoopId,
                    follow: mode.followStream,
                    liveUpdate: false
                )
                if !events.isEmpty || mode == .snapshot {
                    return (events, mode == .live ? .live : .snapshot)
                }
            } catch {
                // Snapshot fetch below is the compatibility path for older AAA backends.
            }
        }

        do {
            return (try await fetchAgentLoopEventSnapshot(escapedLoopId: escapedLoopId), .fallback)
        } catch {
            return ([], .unavailable)
        }
    }

    private func fetchAgentLoopEventSnapshot(
        escapedLoopId: String,
        afterSequence: Int? = nil
    ) async throws -> [AgentLoopEventResponse] {
        let eventsURL = Self.agentLoopEventsURL(
            backendBase: backendBase,
            escapedLoopId: escapedLoopId,
            afterSequence: afterSequence
        )
        var eventsRequest = URLRequest(url: eventsURL)
        eventsRequest.httpMethod = "GET"
        let (eventsData, eventsResponse) = try await URLSession.shared.data(for: eventsRequest)
        try Self.validate(eventsResponse)
        return try JSONDecoder().decode([AgentLoopEventResponse].self, from: eventsData)
    }

    private func fetchAgentLoopEventStream(
        escapedLoopId: String,
        follow: Bool,
        liveUpdate: Bool,
        afterSequence: Int? = nil
    ) async throws -> [AgentLoopEventResponse] {
        let eventsURL = Self.agentLoopEventStreamURL(
            backendBase: backendBase,
            escapedLoopId: escapedLoopId,
            follow: follow,
            afterSequence: afterSequence
        )
        var eventsRequest = URLRequest(url: eventsURL)
        eventsRequest.httpMethod = "GET"
        eventsRequest.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        eventsRequest.setValue("no-cache", forHTTPHeaderField: "Cache-Control")

        let (bytes, response) = try await URLSession.shared.bytes(for: eventsRequest)
        try Self.validate(response)

        var events: [AgentLoopEventResponse] = []
        var dataLines: [String] = []

        func flush() {
            let decoded = Self.decodeAgentLoopEventsFromSSEDataLines(dataLines)
            dataLines.removeAll()
            guard !decoded.isEmpty else { return }
            events = Self.mergedAgentLoopEvents(events, decoded)
            if liveUpdate {
                agentLoopEvents = Self.mergedAgentLoopEvents(agentLoopEvents, decoded)
                agentLoopEventsLive = true
                agentLoopTimelineSource = .live
            }
        }

        for try await rawLine in bytes.lines {
            try Task.checkCancellation()
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

    nonisolated static func agentLoopEventsURL(
        backendBase: String,
        escapedLoopId: String,
        afterSequence: Int? = nil
    ) -> URL {
        var components = URLComponents(string: "\(backendBase)/api/orchestrator/loops/\(escapedLoopId)/events")!
        if let afterSequence {
            components.queryItems = [URLQueryItem(name: "after_sequence", value: String(afterSequence))]
        }
        return components.url!
    }

    nonisolated static func agentLoopEventStreamURL(
        backendBase: String,
        escapedLoopId: String,
        follow: Bool,
        afterSequence: Int? = nil
    ) -> URL {
        var components = URLComponents(string: "\(backendBase)/api/orchestrator/loops/\(escapedLoopId)/events/stream")!
        var queryItems: [URLQueryItem] = []
        if follow {
            queryItems.append(URLQueryItem(name: "follow", value: "true"))
        }
        if let afterSequence {
            queryItems.append(URLQueryItem(name: "after_sequence", value: String(afterSequence)))
        }
        if !queryItems.isEmpty {
            components.queryItems = queryItems
        }
        return components.url!
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

    nonisolated static func decodeAgentLoopEventsFromSSEDataLines(_ dataLines: [String]) -> [AgentLoopEventResponse] {
        let payload = dataLines.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
        guard !payload.isEmpty, let data = payload.data(using: .utf8) else { return [] }
        let decoder = JSONDecoder()
        if let event = try? decoder.decode(AgentLoopEventResponse.self, from: data) {
            return [event]
        }
        if let batch = try? decoder.decode([AgentLoopEventResponse].self, from: data) {
            return batch
        }
        return []
    }

    nonisolated static func mergedAgentLoopEvents(
        _ current: [AgentLoopEventResponse],
        _ incoming: [AgentLoopEventResponse]
    ) -> [AgentLoopEventResponse] {
        var seen = Set(current.map(agentLoopEventIdentity))
        var merged = current
        for event in incoming {
            let identity = agentLoopEventIdentity(event)
            if seen.insert(identity).inserted {
                merged.append(event)
            }
        }
        return merged
    }

    private nonisolated static func agentLoopEventIdentity(_ event: AgentLoopEventResponse) -> String {
        if let eventId = event.eventId {
            return "event_id:\(eventId)"
        }
        if let sequence = event.sequence {
            return "sequence:\(sequence)"
        }
        return "\(event.type):\(event.timestamp ?? 0):\(event.compactLabel)"
    }

    private static func validate(_ response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
    }
}
