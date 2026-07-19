import Foundation

@MainActor
final class WorkerControlViewModel: ObservableObject {
    typealias DataLoader = @Sendable (URLRequest) async throws -> (Data, URLResponse)

    @Published private(set) var snapshot: WorkerControlSnapshot?
    @Published private(set) var pairing: WorkerPairingResponse?
    @Published private(set) var isLoading = false
    @Published private(set) var isMutating = false
    @Published private(set) var errorMessage: String?
    @Published private(set) var actionMessage: String?
    @Published private(set) var verificationCodes: [String: String] = [:]

    private let backendBase: URL
    private let dataLoader: DataLoader

    init(
        backendBase: URL = URL(string: "http://backend")!,
        dataLoader: @escaping DataLoader = { request in try await URLSession.shared.data(for: request) }
    ) {
        self.backendBase = backendBase
        self.dataLoader = dataLoader
    }

    func load() async {
        guard !isLoading else { return }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let value = try await fetch(Self.makeSnapshotRequest(backendBase: backendBase), as: WorkerControlSnapshot.self)
            snapshot = value
            await loadVerificationCodes(for: value.pending)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func createPairing(displayName: String, platform: String) async {
        await mutate(success: "Pairing command created.") {
            let payload = WorkerPairingCreatePayload(
                ttlSeconds: 600,
                displayName: displayName.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty,
                platform: platform
            )
            self.pairing = try await self.fetch(
                Self.makeJSONRequest(
                    backendBase: self.backendBase,
                    path: "api/worker-control/pairings",
                    payload: payload
                ),
                as: WorkerPairingResponse.self
            )
        }
    }

    func approve(_ node: WorkerNode, verificationCode: String) async {
        await mutate(success: "Device approved.") {
            let payload = WorkerNodeApprovalPayload(verificationCode: verificationCode)
            _ = try await self.fetch(
                Self.makeJSONRequest(
                    backendBase: self.backendBase,
                    path: "api/worker-control/nodes/\(Self.pathComponent(node.nodeID))/approve",
                    payload: payload
                ),
                as: WorkerNode.self
            )
            await self.loadAfterMutation()
        }
    }

    func verificationCode(for node: WorkerNode) -> String? {
        verificationCodes[node.nodeID]
    }

    func action(_ action: String, node: WorkerNode) async {
        await mutate(success: action == "remove" ? "Device removed." : "Device action completed.") {
            let payload = WorkerNodeActionPayload(action: action, reason: "host_ui")
            _ = try await self.fetch(
                Self.makeJSONRequest(
                    backendBase: self.backendBase,
                    path: "api/worker-control/nodes/\(Self.pathComponent(node.nodeID))/actions",
                    payload: payload
                ),
                as: WorkerNodeActionResponse.self
            )
            await self.loadAfterMutation()
        }
    }

    func configureListener(enabled: Bool, bindHost: String, port: Int) async {
        await mutate(success: enabled ? "Direct listener configuration saved." : "Direct listener disabled.") {
            let payload = WorkerListenerPayload(enabled: enabled, bindHost: enabled ? bindHost : nil, port: enabled ? port : 0)
            _ = try await self.fetch(
                Self.makeJSONRequest(backendBase: self.backendBase, path: "api/worker-control/listener", payload: payload),
                as: WorkerListenerConfiguration.self
            )
            await self.loadAfterMutation()
        }
    }

    func configureRelay(enabled: Bool, endpoint: String) async {
        await mutate(success: enabled ? "Relay configuration saved." : "Relay disabled.") {
            let payload = WorkerRelayPayload(enabled: enabled, endpoint: enabled ? endpoint : nil)
            _ = try await self.fetch(
                Self.makeJSONRequest(backendBase: self.backendBase, path: "api/worker-control/relay", payload: payload),
                as: WorkerRelayConfiguration.self
            )
            await self.loadAfterMutation()
        }
    }

    nonisolated static func makeSnapshotRequest(backendBase: URL) -> URLRequest {
        var request = URLRequest(url: backendBase.appendingPathComponent("api/worker-control"))
        request.timeoutInterval = 15
        return request
    }

    nonisolated static func makeJSONRequest<Payload: Encodable>(backendBase: URL, path: String, payload: Payload) throws -> URLRequest {
        var request = URLRequest(url: backendBase.appendingPathComponent(path))
        request.httpMethod = "POST"
        request.timeoutInterval = 20
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(payload)
        return request
    }

    private func mutate(success: String, operation: () async throws -> Void) async {
        guard !isMutating else { return }
        isMutating = true
        errorMessage = nil
        actionMessage = nil
        defer { isMutating = false }
        do {
            try await operation()
            actionMessage = success
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func loadAfterMutation() async {
        if let value = try? await fetch(Self.makeSnapshotRequest(backendBase: backendBase), as: WorkerControlSnapshot.self) {
            snapshot = value
            await loadVerificationCodes(for: value.pending)
        }
    }

    private func loadVerificationCodes(for nodes: [WorkerNode]) async {
        var values: [String: String] = [:]
        for node in nodes {
            var request = URLRequest(
                url: backendBase
                    .appendingPathComponent("api/worker-control/nodes")
                    .appendingPathComponent(node.nodeID)
                    .appendingPathComponent("verification-code")
            )
            request.timeoutInterval = 10
            if let response = try? await fetch(request, as: WorkerHostVerificationResponse.self) {
                values[node.nodeID] = response.verificationCode
            }
        }
        verificationCodes = values
    }

    private func fetch<Response: Decodable>(_ request: URLRequest, as type: Response.Type) async throws -> Response {
        let (data, response) = try await dataLoader(request)
        try OperationsHTTP.validate(response, data: data)
        return try JSONDecoder().decode(type, from: data)
    }

    nonisolated private static func pathComponent(_ value: String) -> String {
        value.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? value
    }
}

private struct WorkerPairingCreatePayload: Encodable {
    let ttlSeconds: Int
    let displayName: String?
    let platform: String

    enum CodingKeys: String, CodingKey {
        case ttlSeconds = "ttl_seconds"
        case displayName = "display_name"
        case platform
    }
}

private struct WorkerNodeApprovalPayload: Encodable {
    let verificationCode: String
    enum CodingKeys: String, CodingKey { case verificationCode = "verification_code" }
}

private struct WorkerNodeActionPayload: Encodable {
    let action: String
    let reason: String
}

private struct WorkerListenerPayload: Encodable {
    let enabled: Bool
    let bindHost: String?
    let port: Int
    enum CodingKeys: String, CodingKey { case enabled, port; case bindHost = "bind_host" }
}

private struct WorkerRelayPayload: Encodable {
    let enabled: Bool
    let endpoint: String?
}

private struct WorkerNodeActionResponse: Decodable {
    let nodeID: String
    let action: String
    let removed: Bool
    enum CodingKeys: String, CodingKey { case nodeID = "node_id"; case action, removed }
}

private struct WorkerHostVerificationResponse: Decodable {
    let nodeID: String
    let verificationCode: String
    enum CodingKeys: String, CodingKey { case nodeID = "node_id"; case verificationCode = "verification_code" }
}

private extension String {
    var nilIfEmpty: String? { isEmpty ? nil : self }
}
