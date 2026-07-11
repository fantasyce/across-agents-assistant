import Foundation

enum QualityGateRunActivityStatus: String, Equatable {
    case active
    case idle
    case maxWallExceeded = "max_wall_exceeded"
}

struct QualityGateRunActivity: Equatable {
    let remote: Bool
    let startedAt: Date
    var elapsedSeconds: Int
    let idleTimeoutSeconds: Int
    let maxWallTimeoutSeconds: Int

    var status: QualityGateRunActivityStatus {
        if elapsedSeconds >= maxWallTimeoutSeconds { return .maxWallExceeded }
        if elapsedSeconds >= idleTimeoutSeconds { return .idle }
        return .active
    }
}

struct QualityGateRunFailure: Equatable {
    let message: String
    let recoverable: Bool
    let recoveryHint: String
}

@MainActor
final class QualityGateViewModel: ObservableObject {
    typealias DataLoader = (URLRequest) async throws -> (Data, URLResponse)

    @Published var draft = QualityGateRunDraft()
    @Published var result: QualityGateResult?
    @Published var isRunning = false
    @Published var errorMessage: String?
    @Published var failure: QualityGateRunFailure?
    @Published var isRemoteConfirmationPresented = false
    @Published var runActivity: QualityGateRunActivity?

    private let backendBase: URL
    private let dataLoader: DataLoader
    private var activityTask: Task<Void, Never>?

    init(
        backendBase: URL = URL(string: "http://backend")!,
        dataLoader: @escaping DataLoader = { request in try await URLSession.shared.data(for: request) }
    ) {
        self.backendBase = backendBase
        self.dataLoader = dataLoader
    }

    var contentState: OperationalContentState {
        if isRunning { return .loading }
        if let errorMessage { return .error(errorMessage) }
        guard let result else { return draft.validationError == nil ? .empty : .disabled(draft.validationError ?? "unavailable") }
        return .success(result.gateVerdict)
    }

    var reviewSignals: [HumanReviewSignal] {
        guard let result else { return [] }
        return result.findings.compactMap { finding in
            guard !["pass", "passed", "no_op"].contains(finding.state) else { return nil }
            return HumanReviewSignal(
                id: "quality-gate-\(finding.id)",
                kind: result.isBlocked ? .blockingGate : .manualGate,
                title: finding.summary ?? finding.id,
                detail: finding.suggestedAction ?? finding.sourceGate ?? "Repository quality gate",
                status: finding.state,
                source: "Quality Gate"
            )
        }
    }

    func configureProjectPath(_ path: String?) {
        let normalized = path?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if draft.repoRoot != normalized { draft.repoRoot = normalized }
    }

    func run() async {
        if draft.operationMode.requiresRemoteConfirmation {
            isRemoteConfirmationPresented = true
            return
        }
        await executeRun(remoteApproved: false)
    }

    func confirmRemoteRun() async {
        guard draft.operationMode.requiresRemoteConfirmation else {
            isRemoteConfirmationPresented = false
            await executeRun(remoteApproved: false)
            return
        }
        isRemoteConfirmationPresented = false
        await executeRun(remoteApproved: true)
    }

    func cancelRemoteConfirmation() {
        isRemoteConfirmationPresented = false
    }

    private func executeRun(remoteApproved: Bool) async {
        guard !draft.operationMode.requiresRemoteConfirmation || remoteApproved else { return }
        isRunning = true
        errorMessage = nil
        failure = nil
        result = nil
        startActivity(remote: remoteApproved)
        defer {
            activityTask?.cancel()
            activityTask = nil
            isRunning = false
        }
        do {
            let request = try Self.makeRunRequest(backendBase: backendBase, payload: draft.request())
            let (data, response) = try await dataLoader(request)
            try OperationsHTTP.validate(response, data: data)
            result = try JSONDecoder().decode(QualityGateResult.self, from: data)
        } catch {
            errorMessage = error.localizedDescription
            failure = Self.failure(for: error)
        }
    }

    private func startActivity(remote: Bool) {
        let idleTimeout = remote ? draft.ciIdleTimeoutSeconds : max(30, draft.timeoutSeconds)
        let maxWallTimeout = remote ? draft.ciMaxWallTimeoutSeconds : max(30, draft.timeoutSeconds)
        runActivity = QualityGateRunActivity(
            remote: remote,
            startedAt: Date(),
            elapsedSeconds: 0,
            idleTimeoutSeconds: idleTimeout,
            maxWallTimeoutSeconds: maxWallTimeout
        )
        activityTask?.cancel()
        activityTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 1_000_000_000)
                guard !Task.isCancelled, let self, var activity = self.runActivity else { return }
                activity.elapsedSeconds = max(0, Int(Date().timeIntervalSince(activity.startedAt)))
                self.runActivity = activity
            }
        }
    }

    private nonisolated static func failure(for error: Error) -> QualityGateRunFailure {
        let message = error.localizedDescription
        let normalized = message.lowercased()
        let recoverable = error is URLError || [
            "timeout", "timed out", "connection", "temporarily", "unavailable", "network", "eof", "tls"
        ].contains(where: normalized.contains)
        return QualityGateRunFailure(
            message: message,
            recoverable: recoverable,
            recoveryHint: recoverable
                ? "Retry with the same repository and branch. Remote operations are idempotent and will reconcile existing state."
                : "Review the trusted repository policy and local gate findings before retrying."
        )
    }

    nonisolated static func makeRunRequest(backendBase: URL, payload: QualityGateRunRequest) throws -> URLRequest {
        var request = URLRequest(url: backendBase.appendingPathComponent("api/quality-gates/run"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let remoteWallSeconds = Double(payload.ciMaxWallTimeoutSeconds ?? 0)
        // The host reserves 120 seconds after CI's wall budget for final GitHub
        // reconciliation. Keep a small transport margin beyond that boundary.
        request.timeoutInterval = max(TimeInterval(payload.timeoutSeconds + 15), remoteWallSeconds + 180)
        request.httpBody = try JSONEncoder().encode(payload)
        return request
    }
}
