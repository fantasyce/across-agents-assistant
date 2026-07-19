import Foundation

struct AutopilotWorkbenchEnsureRequest: Encodable {
    let actor: String
}

struct AutopilotWorkbenchSchedulerRequest: Encodable {
    let intervalSeconds: Double

    enum CodingKeys: String, CodingKey {
        case intervalSeconds = "interval_seconds"
    }
}

struct AutopilotWorkbenchActionNotice: Equatable {
    let actionID: String
    let status: String
    let message: String
}

@MainActor
final class AutopilotWorkbenchViewModel: ObservableObject {
    typealias DataLoader = (URLRequest) async throws -> (Data, URLResponse)

    @Published var snapshot: AutopilotWorkbenchSnapshot?
    @Published var isLoading = false
    @Published var isWorking = false
    @Published var message: String?
    @Published var errorMessage: String?
    @Published private(set) var activeActionID: String?
    @Published private(set) var actionNotice: AutopilotWorkbenchActionNotice?

    private let backendBaseURL: URL
    private let cacheURL: URL?
    private let dataLoader: DataLoader

    init(
        backendBaseURL: URL = URL(string: "http://backend")!,
        cacheURL: URL? = LocalAppPaths.autopilotWorkbenchSnapshotCache,
        dataLoader: @escaping DataLoader = { request in
            try await URLSession.shared.data(for: request)
        }
    ) {
        self.backendBaseURL = backendBaseURL
        self.cacheURL = cacheURL
        self.dataLoader = dataLoader
        snapshot = cacheURL.flatMap(Self.cachedSnapshot(at:))
    }

    func load(refresh: Bool = false) async {
        if !refresh, snapshot != nil {
            return
        }

        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let path = refresh ? "/api/autopilot/workbench/refresh" : "/api/autopilot/workbench"
            let data = try await request(path: path, method: refresh ? "POST" : "GET")
            let decoded = try JSONDecoder().decode(AutopilotWorkbenchSnapshot.self, from: data)
            snapshot = decoded
            if let cacheURL {
                do {
                    try Self.persistSnapshot(data, at: cacheURL)
                } catch {
                    errorMessage = error.localizedDescription
                }
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func ensureSelfIterationPlan(
        successMessage: String = "Self-iteration plan ensured",
        actionID: String? = nil,
        runningMessage: String = "Preparing the Loop plan..."
    ) async {
        await runAction(message: successMessage, actionID: actionID, runningMessage: runningMessage) {
            try await request(
                path: "/api/autopilot/self-iteration-plan/ensure",
                method: "POST",
                body: AutopilotWorkbenchEnsureRequest(actor: "aaa-workbench")
            )
        }
    }

    func tickTriggers(
        successMessage: String = "Trigger tick completed",
        actionID: String? = nil,
        runningMessage: String = "Checking scheduled Loops..."
    ) async {
        await runAction(message: successMessage, actionID: actionID, runningMessage: runningMessage) {
            try await request(path: "/api/autopilot/trigger-configs/tick", method: "POST")
        }
    }

    func startScheduler(
        successMessage: String = "Trigger scheduler started",
        actionID: String? = nil,
        runningMessage: String = "Starting automatic Loop checks..."
    ) async {
        await runAction(message: successMessage, actionID: actionID, runningMessage: runningMessage) {
            try await request(
                path: "/api/autopilot/trigger-scheduler/start",
                method: "POST",
                body: AutopilotWorkbenchSchedulerRequest(intervalSeconds: 60)
            )
        }
    }

    func stopScheduler(
        successMessage: String = "Trigger scheduler stopped",
        actionID: String? = nil,
        runningMessage: String = "Pausing automatic Loop checks..."
    ) async {
        await runAction(message: successMessage, actionID: actionID, runningMessage: runningMessage) {
            try await request(path: "/api/autopilot/trigger-scheduler/stop", method: "POST")
        }
    }

    func runAgentInteropE2E(
        successMessage: String = "Agent interop E2E passed",
        failureMessage: String = "Agent interop E2E failed",
        runningMessage: String = "Checking Agent compatibility...",
        actionID: String? = nil,
        pollIntervalNanoseconds: UInt64 = 750_000_000,
        maxPollAttempts: Int = 320
    ) async {
        beginAction(actionID: actionID, runningMessage: runningMessage)
        defer { endAction() }

        do {
            var payload = try JSONDecoder().decode(
                AgentInteropActionResponse.self,
                from: try await request(path: "/api/autopilot/agent-interop-e2e", method: "POST")
            )
            var attempt = 0
            while payload.runState?.status == "running" {
                guard attempt < maxPollAttempts else {
                    throw NSError(
                        domain: "AutopilotWorkbench",
                        code: 2,
                        userInfo: [NSLocalizedDescriptionKey: failureMessage]
                    )
                }
                attempt += 1
                if pollIntervalNanoseconds > 0 {
                    try await Task.sleep(nanoseconds: pollIntervalNanoseconds)
                }
                payload = try JSONDecoder().decode(
                    AgentInteropActionResponse.self,
                    from: try await request(path: "/api/autopilot/agent-interop-e2e", method: "GET")
                )
            }
            guard payload.status == "passed", payload.runState?.status != "failed" else {
                let failedCount = max(payload.summary?.failedCount ?? 0, payload.runState?.failedCount ?? 0)
                let formatted = failureMessage.contains("%d")
                    ? String(format: failureMessage, failedCount)
                    : failureMessage
                throw NSError(
                    domain: "AutopilotWorkbench",
                    code: 1,
                    userInfo: [NSLocalizedDescriptionKey: formatted]
                )
            }
            await load(refresh: true)
            publishActionResult(actionID: actionID, status: "passed", message: successMessage)
        } catch {
            await load(refresh: true)
            publishActionResult(actionID: actionID, status: "failed", message: error.localizedDescription)
        }
    }

    func checkEcosystemAction(
        _ action: AutopilotWorkbenchAction,
        runningMessage: String,
        successMessage: String,
        attentionMessage: String,
        failureMessage: String
    ) async {
        guard let endpoint = action.endpoint,
              endpoint.hasPrefix("/api/ecosystem/"),
              !endpoint.contains("{")
        else {
            actionNotice = AutopilotWorkbenchActionNotice(
                actionID: action.id,
                status: "failed",
                message: failureMessage
            )
            return
        }

        beginAction(actionID: action.id, runningMessage: runningMessage)
        defer { endAction() }
        do {
            let separator = endpoint.contains("?") ? "&" : "?"
            let data = try await request(path: "\(endpoint)\(separator)refresh=true", method: "GET")
            let section = try JSONDecoder().decode(AutopilotWorkbenchSection.self, from: data)
            await load(refresh: true)
            switch section.status {
            case "passed", "ready", "active":
                publishActionResult(actionID: action.id, status: "passed", message: successMessage)
            case "failed", "blocked", "error":
                publishActionResult(actionID: action.id, status: "failed", message: failureMessage)
            default:
                publishActionResult(actionID: action.id, status: "attention", message: attentionMessage)
            }
        } catch {
            await load(refresh: true)
            publishActionResult(actionID: action.id, status: "failed", message: error.localizedDescription)
        }
    }

    func reportUnsupportedAction(actionID: String, message: String) {
        actionNotice = AutopilotWorkbenchActionNotice(
            actionID: actionID,
            status: "attention",
            message: message
        )
    }

    private func runAction(
        message successMessage: String,
        actionID: String? = nil,
        runningMessage: String = "Working...",
        validate: ((Data) throws -> Void)? = nil,
        _ action: () async throws -> Data
    ) async {
        beginAction(actionID: actionID, runningMessage: runningMessage)
        defer { endAction() }

        do {
            let data = try await action()
            try validate?(data)
            await load(refresh: true)
            publishActionResult(actionID: actionID, status: "passed", message: successMessage)
        } catch {
            let actionError = error.localizedDescription
            await load(refresh: true)
            publishActionResult(actionID: actionID, status: "failed", message: actionError)
        }
    }

    private func beginAction(actionID: String?, runningMessage: String) {
        isWorking = true
        activeActionID = actionID
        message = nil
        errorMessage = nil
        if let actionID {
            actionNotice = AutopilotWorkbenchActionNotice(
                actionID: actionID,
                status: "running",
                message: runningMessage
            )
        } else {
            actionNotice = nil
        }
    }

    private func endAction() {
        activeActionID = nil
        isWorking = false
    }

    private func publishActionResult(actionID: String?, status: String, message resultMessage: String) {
        if let actionID {
            actionNotice = AutopilotWorkbenchActionNotice(
                actionID: actionID,
                status: status,
                message: resultMessage
            )
        } else if status == "passed" {
            message = resultMessage
        } else {
            errorMessage = resultMessage
        }
    }

    @discardableResult
    private func request<T: Encodable>(path: String, method: String, body: T) async throws -> Data {
        var request = URLRequest(url: endpoint(path))
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(body)
        let (data, response) = try await dataLoader(request)
        try Self.validate(response: response, data: data)
        return data
    }

    @discardableResult
    private func request(path: String, method: String) async throws -> Data {
        var request = URLRequest(url: endpoint(path))
        request.httpMethod = method
        let (data, response) = try await dataLoader(request)
        try Self.validate(response: response, data: data)
        return data
    }

    private func endpoint(_ path: String) -> URL {
        URL(string: path, relativeTo: backendBaseURL)!.absoluteURL
    }

    nonisolated private static func cachedSnapshot(at url: URL) -> AutopilotWorkbenchSnapshot? {
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(AutopilotWorkbenchSnapshot.self, from: data)
    }

    nonisolated private static func persistSnapshot(_ data: Data, at url: URL) throws {
        let fileManager = FileManager.default
        try fileManager.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try data.write(to: url, options: .atomic)
        try fileManager.setAttributes(
            [.posixPermissions: 0o600],
            ofItemAtPath: url.path
        )
    }

    nonisolated static func validate(response: URLResponse, data: Data) throws {
        guard let httpResponse = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }
        guard (200..<300).contains(httpResponse.statusCode) else {
            if let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let detail = payload["detail"] as? String,
               !detail.isEmpty {
                throw NSError(domain: "AutopilotWorkbench", code: httpResponse.statusCode, userInfo: [NSLocalizedDescriptionKey: detail])
            }
            throw NSError(domain: "AutopilotWorkbench", code: httpResponse.statusCode, userInfo: [NSLocalizedDescriptionKey: "HTTP \(httpResponse.statusCode)"])
        }
    }
}

@MainActor
final class AutopilotEvidenceViewModel: ObservableObject {
    typealias DataLoader = @Sendable (URLRequest) async throws -> (Data, URLResponse)

    @Published private(set) var payload: AutopilotWorkbenchJSONValue?
    @Published private(set) var loadedTarget: AutopilotEvidenceTarget?
    @Published private(set) var isLoading = false
    @Published private(set) var errorMessage: String?

    private let backendBaseURL: URL
    private let dataLoader: DataLoader
    private var loadGeneration = 0

    init(
        backendBaseURL: URL = URL(string: "http://backend")!,
        dataLoader: @escaping DataLoader = { request in
            try await URLSession.shared.data(for: request)
        }
    ) {
        self.backendBaseURL = backendBaseURL
        self.dataLoader = dataLoader
    }

    func load(target: AutopilotEvidenceTarget?) async {
        loadGeneration += 1
        let generation = loadGeneration
        guard let target else {
            loadedTarget = nil
            payload = nil
            errorMessage = nil
            isLoading = false
            return
        }
        guard target != loadedTarget || payload == nil else { return }

        loadedTarget = target
        payload = nil
        errorMessage = nil
        isLoading = true
        defer {
            if loadGeneration == generation {
                isLoading = false
            }
        }

        do {
            var request = URLRequest(url: backendBaseURL.appendingPathComponent(target.backendPath))
            request.httpMethod = "GET"
            let (data, response) = try await dataLoader(request)
            guard loadGeneration == generation else { return }
            try AutopilotWorkbenchViewModel.validate(response: response, data: data)
            payload = try JSONDecoder().decode(AutopilotWorkbenchJSONValue.self, from: data)
        } catch {
            guard loadGeneration == generation else { return }
            errorMessage = error.localizedDescription
        }
    }
}

private struct AgentInteropActionResponse: Decodable {
    let status: String
    let summary: AgentInteropActionSummary?
    let runState: AgentInteropRunState?

    enum CodingKeys: String, CodingKey {
        case status
        case summary
        case runState = "run_state"
    }
}

private struct AgentInteropActionSummary: Decodable {
    let failedCount: Int

    enum CodingKeys: String, CodingKey {
        case failedCount = "failed_count"
    }
}

private struct AgentInteropRunState: Decodable {
    let status: String
    let failedCount: Int

    enum CodingKeys: String, CodingKey {
        case status
        case failedCount = "failed_count"
    }
}
