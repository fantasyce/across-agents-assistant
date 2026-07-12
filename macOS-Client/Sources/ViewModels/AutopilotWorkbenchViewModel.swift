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

@MainActor
final class AutopilotWorkbenchViewModel: ObservableObject {
    @Published var snapshot: AutopilotWorkbenchSnapshot?
    @Published var isLoading = false
    @Published var isWorking = false
    @Published var message: String?
    @Published var errorMessage: String?

    private let backendBase = "http://backend"

    func load(refresh: Bool = false) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let path = refresh ? "/api/autopilot/workbench/refresh" : "/api/autopilot/workbench"
            let data = try await request(path: path, method: refresh ? "POST" : "GET")
            snapshot = try JSONDecoder().decode(AutopilotWorkbenchSnapshot.self, from: data)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func ensureSelfIterationPlan(successMessage: String = "Self-iteration plan ensured") async {
        await runAction(message: successMessage) {
            try await request(
                path: "/api/autopilot/self-iteration-plan/ensure",
                method: "POST",
                body: AutopilotWorkbenchEnsureRequest(actor: "aaa-workbench")
            )
        }
    }

    func tickTriggers(successMessage: String = "Trigger tick completed") async {
        await runAction(message: successMessage) {
            try await request(path: "/api/autopilot/trigger-configs/tick", method: "POST")
        }
    }

    func startScheduler(successMessage: String = "Trigger scheduler started") async {
        await runAction(message: successMessage) {
            try await request(
                path: "/api/autopilot/trigger-scheduler/start",
                method: "POST",
                body: AutopilotWorkbenchSchedulerRequest(intervalSeconds: 60)
            )
        }
    }

    func stopScheduler(successMessage: String = "Trigger scheduler stopped") async {
        await runAction(message: successMessage) {
            try await request(path: "/api/autopilot/trigger-scheduler/stop", method: "POST")
        }
    }

    func runAgentInteropE2E(
        successMessage: String = "Agent interop E2E passed",
        failureMessage: String = "Agent interop E2E failed"
    ) async {
        await runAction(message: successMessage, validate: { data in
            let payload = try JSONDecoder().decode(AgentInteropActionResponse.self, from: data)
            guard payload.status == "passed" else {
                throw NSError(
                    domain: "AutopilotWorkbench",
                    code: 1,
                    userInfo: [NSLocalizedDescriptionKey: failureMessage]
                )
            }
        }) {
            try await request(path: "/api/autopilot/agent-interop-e2e", method: "POST")
        }
    }

    private func runAction(
        message successMessage: String,
        validate: ((Data) throws -> Void)? = nil,
        _ action: () async throws -> Data
    ) async {
        isWorking = true
        message = nil
        errorMessage = nil
        defer { isWorking = false }

        do {
            let data = try await action()
            try validate?(data)
            message = successMessage
            await load(refresh: true)
        } catch {
            let actionError = error.localizedDescription
            await load(refresh: true)
            errorMessage = actionError
        }
    }

    @discardableResult
    private func request<T: Encodable>(path: String, method: String, body: T) async throws -> Data {
        var request = URLRequest(url: URL(string: "\(backendBase)\(path)")!)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(body)
        let (data, response) = try await URLSession.shared.data(for: request)
        try Self.validate(response: response, data: data)
        return data
    }

    @discardableResult
    private func request(path: String, method: String) async throws -> Data {
        var request = URLRequest(url: URL(string: "\(backendBase)\(path)")!)
        request.httpMethod = method
        let (data, response) = try await URLSession.shared.data(for: request)
        try Self.validate(response: response, data: data)
        return data
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

private struct AgentInteropActionResponse: Decodable {
    let status: String
}
