import Foundation

@MainActor
final class AgentWorkspaceReadinessViewModel: ObservableObject {
    typealias DataLoader = (URLRequest) async throws -> (Data, URLResponse)

    @Published var snapshot: AgentWorkspaceReadinessSnapshot?
    @Published var isLoading = false
    @Published var errorMessage: String?

    private let backendBase: URL
    private let dataLoader: DataLoader

    init(
        backendBase: URL = URL(string: "http://backend")!,
        dataLoader: @escaping DataLoader = { request in
            try await URLSession.shared.data(for: request)
        }
    ) {
        self.backendBase = backendBase
        self.dataLoader = dataLoader
    }

    func load(refresh: Bool = false, retryTransportFailures: Int = 0) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        let request = Self.makeRequest(backendBase: backendBase, refresh: refresh)
        for attempt in 0...max(0, retryTransportFailures) {
            do {
                let (data, response) = try await dataLoader(request)
                try Self.validate(response: response, data: data)
                snapshot = try JSONDecoder().decode(AgentWorkspaceReadinessSnapshot.self, from: data)
                return
            } catch {
                if attempt < retryTransportFailures, Self.isRetryableTransportError(error) {
                    try? await Task.sleep(nanoseconds: 700_000_000)
                    continue
                }
                snapshot = nil
                errorMessage = error.localizedDescription
                return
            }
        }
    }

    nonisolated static func isRetryableTransportError(_ error: Error) -> Bool {
        let nsError = error as NSError
        if nsError.domain == NSURLErrorDomain {
            return [
                URLError.cannotFindHost.rawValue,
                URLError.cannotConnectToHost.rawValue,
                URLError.networkConnectionLost.rawValue,
                URLError.notConnectedToInternet.rawValue,
                URLError.resourceUnavailable.rawValue,
                URLError.timedOut.rawValue,
            ].contains(nsError.code)
        }
        return nsError.domain.contains("Network.NWError") || nsError.domain == NSPOSIXErrorDomain
    }

    nonisolated static func makeRequest(backendBase: URL, refresh: Bool = false) -> URLRequest {
        var components = URLComponents(url: backendBase.appendingPathComponent("api/agent-workspaces/readiness"), resolvingAgainstBaseURL: false)!
        if refresh {
            components.queryItems = [URLQueryItem(name: "refresh", value: "true")]
        }
        var request = URLRequest(url: components.url!)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.timeoutInterval = refresh ? 20 : 10
        return request
    }

    nonisolated static func validate(response: URLResponse, data: Data) throws {
        guard let httpResponse = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }
        guard (200..<300).contains(httpResponse.statusCode) else {
            if let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let detail = payload["detail"] as? String,
               !detail.isEmpty {
                throw NSError(domain: "AgentWorkspaceReadiness", code: httpResponse.statusCode, userInfo: [NSLocalizedDescriptionKey: detail])
            }
            throw NSError(domain: "AgentWorkspaceReadiness", code: httpResponse.statusCode, userInfo: [NSLocalizedDescriptionKey: "HTTP \(httpResponse.statusCode)"])
        }
    }
}
