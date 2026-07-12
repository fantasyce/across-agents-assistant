import Foundation

@MainActor
final class AgentWorkspaceOperationsViewModel: ObservableObject {
    typealias DataLoader = (URLRequest) async throws -> (Data, URLResponse)

    nonisolated static let maximumDisplayedEvents = 200
    nonisolated static let maximumDisplayedEventCharacters = 65_536

    @Published var readiness: AgentWorkspaceReadinessSnapshot?
    @Published var workspaces: [AgentWorkspaceState] = []
    @Published var selectedWorkspaceId: String?
    @Published var workspace: AgentWorkspaceState?
    @Published var comparison: AgentWorkspaceComparisonResponse?
    @Published var events: [AgentWorkspaceEvent] = []
    @Published var selectedCandidateId: String?
    @Published var createDraft = AgentWorkspaceCreateDraft()
    @Published var repositoryAccess: AgentWorkspaceRepoAccess?
    @Published var isLoading = false
    @Published var isPerformingAction = false
    @Published var errorMessage: String?
    @Published var actionMessage: String?

    private let backendBase: URL
    private let dataLoader: DataLoader
    private var lastEventSequence: Int?

    init(
        backendBase: URL = URL(string: "http://backend")!,
        dataLoader: @escaping DataLoader = { request in try await URLSession.shared.data(for: request) }
    ) {
        self.backendBase = backendBase
        self.dataLoader = dataLoader
    }

    var contentState: OperationalContentState {
        if isLoading && readiness == nil && workspaces.isEmpty { return .loading }
        if let errorMessage, readiness == nil && workspaces.isEmpty { return .error(errorMessage) }
        if let workspace, workspace.isActive { return .active(workspace.status) }
        if let workspace, ["promoted", "cleaned"].contains(workspace.status) { return .success(workspace.status) }
        if workspaces.isEmpty { return readiness?.canCreateWorkspace == true ? .empty : .disabled(readiness?.readinessIssues.joined(separator: ", ") ?? "unavailable") }
        return .success(workspace?.status ?? "ready")
    }

    var selectedCandidate: AgentWorkspaceCandidate? {
        workspace?.candidates.first { $0.candidateId == selectedCandidateId }
    }

    var selectedComparisonCandidate: AgentWorkspaceComparisonCandidate? {
        comparison?.candidates.first { $0.candidateId == selectedCandidateId }
    }

    var pollingIdentity: String {
        "\(selectedWorkspaceId ?? "none"):\(workspace?.status ?? "none")"
    }

    var canCreateWorkspace: Bool {
        readiness?.canCreateWorkspace == true && createDraft.validationError == nil && !isPerformingAction
    }

    var reviewSignals: [HumanReviewSignal] {
        var signals: [HumanReviewSignal] = []
        if let workspace {
            for candidate in workspace.candidates
                where ["blocked", "cancelled", "completed", "failed", "interrupted"].contains(candidate.status)
                    && !candidate.evidence.blockingReasons.isEmpty
            {
                signals.append(contentsOf: candidate.evidence.blockingReasons.map { reason in
                    HumanReviewSignal(
                        id: "workspace-\(workspace.workspaceId)-\(candidate.candidateId)-\(reason)",
                        kind: .blockingGate,
                        title: reason.replacingOccurrences(of: "_", with: " "),
                        detail: candidate.agentId,
                        status: "blocked",
                        source: "Agent Workspace"
                    )
                })
            }
            if workspace.candidates.contains(where: { $0.canSelect }) && workspace.promotion?.status == "review_required" {
                signals.append(
                    HumanReviewSignal(
                        id: "workspace-promotion-\(workspace.workspaceId)",
                        kind: .promotion,
                        title: workspace.workflow ?? workspace.workspaceId,
                        detail: workspace.repoRoot,
                        status: "pending",
                        source: "Agent Workspace"
                    )
                )
            }
        }
        return signals
    }

    func configureProjectPath(_ path: String?) {
        let normalized = path?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if createDraft.repoRoot != normalized {
            createDraft.repoRoot = normalized
        }
    }

    func configureRepositoryAccess(_ access: AgentWorkspaceRepoAccess?) {
        repositoryAccess = access
    }

    func load(activeProjectPath: String?, refreshReadiness: Bool = false) async {
        configureProjectPath(activeProjectPath)
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        var readinessError: Error?
        do {
            readiness = try await fetch(
                Self.makeReadinessRequest(
                    backendBase: backendBase,
                    repoRoot: createDraft.repoRoot.nilIfEmpty,
                    selectedAgentIds: createDraft.selectedAgentIds.sorted(),
                    repoAccess: repositoryAccess,
                    refresh: refreshReadiness
                ),
                as: AgentWorkspaceReadinessSnapshot.self
            )
            applyDefaultAgents()
        } catch {
            readinessError = error
        }

        do {
            let listing = try await fetch(Self.makeListRequest(backendBase: backendBase), as: AgentWorkspaceListResponse.self)
            workspaces = listing.workspaces
            if let selectedWorkspaceId, workspaces.contains(where: { $0.workspaceId == selectedWorkspaceId }) {
                try await refreshSelectedWorkspace()
            } else if let preferred = workspaces.first(where: { createDraft.repoRoot.isEmpty || $0.repoRoot == createDraft.repoRoot }) ?? workspaces.first {
                try await selectWorkspace(preferred.workspaceId)
            } else {
                clearSelection()
            }
            if let readinessError {
                errorMessage = readinessError.localizedDescription
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func selectWorkspace(_ workspaceId: String) async throws {
        selectedWorkspaceId = workspaceId
        selectedCandidateId = nil
        events = []
        lastEventSequence = nil
        try await refreshSelectedWorkspace()
    }

    func refreshSelectedWorkspace() async throws {
        guard let selectedWorkspaceId else { return }
        let state = try await fetch(Self.makeWorkspaceRequest(backendBase: backendBase, workspaceId: selectedWorkspaceId), as: AgentWorkspaceState.self)
        workspace = state
        replaceWorkspace(state)
        comparison = try await fetch(Self.makeComparisonRequest(backendBase: backendBase, workspaceId: selectedWorkspaceId), as: AgentWorkspaceComparisonResponse.self)
        let eventBatch = try await fetch(
            Self.makeEventsRequest(backendBase: backendBase, workspaceId: selectedWorkspaceId, afterSequence: lastEventSequence),
            as: AgentWorkspaceEventsResponse.self
        )
        mergeEvents(eventBatch.events)
        lastEventSequence = max(lastEventSequence ?? 0, eventBatch.lastSequence)
        selectDefaultCandidate(in: state)
    }

    func pollSelectedWorkspaceUntilStable(intervalNanoseconds: UInt64 = 2_000_000_000) async {
        while !Task.isCancelled {
            do {
                try await refreshSelectedWorkspace()
            } catch {
                errorMessage = error.localizedDescription
                return
            }
            guard workspace?.isActive == true else { return }
            try? await Task.sleep(nanoseconds: intervalNanoseconds)
        }
    }

    func createWorkspace() async {
        await performAction(successMessage: "Workspace created") {
            let requestPayload = try self.createDraft.request(
                idempotencyKey: UUID().uuidString,
                repoAccess: self.repositoryAccess
            )
            let request = try Self.makeCreateRequest(backendBase: self.backendBase, payload: requestPayload)
            let state = try await self.fetch(request, as: AgentWorkspaceState.self)
            self.selectedWorkspaceId = state.workspaceId
            self.workspace = state
            self.events = []
            self.lastEventSequence = nil
            self.replaceWorkspace(state)
            try await self.refreshSelectedWorkspace()
        }
    }

    func cancel(reason: String? = "Cancelled from AAA operations workbench") async {
        guard let selectedWorkspaceId else { return }
        await performAction(successMessage: "Cancellation requested") {
            let request = try Self.makeActionRequest(
                backendBase: self.backendBase,
                workspaceId: selectedWorkspaceId,
                action: "cancel",
                method: "POST",
                body: AgentWorkspaceCancelRequest(reason: reason)
            )
            let state = try await self.fetch(request, as: AgentWorkspaceState.self)
            self.workspace = state
            self.replaceWorkspace(state)
            try await self.refreshSelectedWorkspace()
        }
    }

    func commentAndRelaunch(_ comment: String) async {
        guard let workspaceId = selectedWorkspaceId, let candidateId = selectedCandidateId else { return }
        let text = comment.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else {
            actionMessage = nil
            errorMessage = "Review comment is required."
            return
        }
        await performAction(successMessage: "Review feedback accepted; candidate relaunched") {
            let request = try Self.makeActionRequest(
                backendBase: self.backendBase,
                workspaceId: workspaceId,
                action: "comment",
                method: "POST",
                body: AgentWorkspaceCommentRequest(candidateId: candidateId, comment: text)
            )
            _ = try await self.fetch(request, as: AgentWorkspaceState.self)
            try await self.refreshSelectedWorkspace()
        }
    }

    func lineReviewAndRelaunch(_ comment: String, location: WorkspaceDiffLineAnchor) async {
        guard let workspaceId = selectedWorkspaceId,
              let candidateId = selectedCandidateId,
              let immutableAnchor = selectedComparisonCandidate?.comparison.reviewAnchor,
              let line = location.displayLine else {
            actionMessage = nil
            errorMessage = "Reload the candidate diff and select a reviewable line."
            return
        }
        let text = comment.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else {
            actionMessage = nil
            errorMessage = "Line review comment is required."
            return
        }
        await performAction(successMessage: "Line review accepted; candidate relaunched") {
            let body = AgentWorkspaceLineReviewRequest(
                candidateId: candidateId,
                anchor: immutableAnchor,
                comments: [
                    AgentWorkspaceLineCommentRequest(
                        path: location.path,
                        side: location.side,
                        line: line,
                        startLine: line,
                        body: text
                    ),
                ],
                idempotencyKey: UUID().uuidString
            )
            let request = try Self.makeActionRequest(
                backendBase: self.backendBase,
                workspaceId: workspaceId,
                action: "line-reviews",
                method: "POST",
                body: body
            )
            _ = try await self.fetch(request, as: AgentWorkspaceState.self)
            try await self.refreshSelectedWorkspace()
        }
    }

    func selectCandidate() async {
        guard let workspaceId = selectedWorkspaceId, let candidateId = selectedCandidateId else { return }
        await performAction(successMessage: "Candidate selected for promotion review") {
            let request = try Self.makeActionRequest(
                backendBase: self.backendBase,
                workspaceId: workspaceId,
                action: "select",
                method: "POST",
                body: AgentWorkspaceSelectRequest(candidateId: candidateId)
            )
            _ = try await self.fetch(request, as: AgentWorkspaceState.self)
            try await self.refreshSelectedWorkspace()
        }
    }

    func promote(approvedBy: String, confirmed: Bool) async {
        guard let workspaceId = selectedWorkspaceId, let candidateId = selectedCandidateId else { return }
        let identity = approvedBy.trimmingCharacters(in: .whitespacesAndNewlines)
        guard confirmed, !identity.isEmpty else {
            actionMessage = nil
            errorMessage = "Confirm promotion and provide the approving identity."
            return
        }
        await performAction(successMessage: "Candidate promoted") {
            let request = try Self.makeActionRequest(
                backendBase: self.backendBase,
                workspaceId: workspaceId,
                action: "promote",
                method: "POST",
                body: AgentWorkspacePromoteRequest(candidateId: candidateId, approved: true, approvedBy: identity)
            )
            _ = try await self.fetch(request, as: AgentWorkspaceState.self)
            try await self.refreshSelectedWorkspace()
        }
    }

    func cleanup() async {
        guard let workspaceId = selectedWorkspaceId else { return }
        await performAction(successMessage: "Isolated worktrees cleaned up") {
            let request = try Self.makeActionRequest(
                backendBase: self.backendBase,
                workspaceId: workspaceId,
                action: nil,
                method: "DELETE",
                body: Optional<AgentWorkspaceCancelRequest>.none
            )
            _ = try await self.fetch(request, as: AgentWorkspaceState.self)
            try await self.refreshSelectedWorkspace()
        }
    }

    func events(for candidateId: String?) -> [AgentWorkspaceEvent] {
        let matching = events.filter { candidateId == nil || $0.candidateId == candidateId }
        var selected: [AgentWorkspaceEvent] = []
        var characters = 0
        for event in matching.suffix(Self.maximumDisplayedEvents).reversed() {
            let eventCharacters = event.type.count + event.boundedSummary.count
            if !selected.isEmpty, characters + eventCharacters > Self.maximumDisplayedEventCharacters { break }
            selected.append(event)
            characters += eventCharacters
        }
        return selected.reversed()
    }

    nonisolated static func makeReadinessRequest(
        backendBase: URL,
        repoRoot: String?,
        selectedAgentIds: [String],
        repoAccess: AgentWorkspaceRepoAccess? = nil,
        refresh: Bool
    ) -> URLRequest {
        var components = URLComponents(url: backendBase.appendingPathComponent("api/agent-workspaces/readiness"), resolvingAgainstBaseURL: false)!
        var items: [URLQueryItem] = []
        if refresh { items.append(URLQueryItem(name: "refresh", value: "true")) }
        if let repoRoot { items.append(URLQueryItem(name: "repo_root", value: repoRoot)) }
        if let repoAccess {
            items.append(URLQueryItem(name: "repo_access_mode", value: repoAccess.mode))
            items.append(URLQueryItem(name: "security_scope_active", value: String(repoAccess.securityScopeActive)))
            if let grantId = repoAccess.grantId {
                items.append(URLQueryItem(name: "repo_access_grant_id", value: grantId))
            }
        }
        items.append(contentsOf: selectedAgentIds.map { URLQueryItem(name: "selected_agent_ids", value: $0) })
        components.queryItems = items.isEmpty ? nil : items
        return jsonRequest(url: components.url!, method: "GET")
    }

    nonisolated static func makeListRequest(backendBase: URL) -> URLRequest {
        jsonRequest(url: backendBase.appendingPathComponent("api/agent-workspaces"), method: "GET")
    }

    nonisolated static func makeWorkspaceRequest(backendBase: URL, workspaceId: String) -> URLRequest {
        jsonRequest(url: workspaceURL(backendBase: backendBase, workspaceId: workspaceId), method: "GET")
    }

    nonisolated static func makeComparisonRequest(backendBase: URL, workspaceId: String) -> URLRequest {
        jsonRequest(url: workspaceURL(backendBase: backendBase, workspaceId: workspaceId).appendingPathComponent("comparison"), method: "GET")
    }

    nonisolated static func makeEventsRequest(backendBase: URL, workspaceId: String, afterSequence: Int?) -> URLRequest {
        var components = URLComponents(url: workspaceURL(backendBase: backendBase, workspaceId: workspaceId).appendingPathComponent("events"), resolvingAgainstBaseURL: false)!
        if let afterSequence {
            components.queryItems = [URLQueryItem(name: "after_sequence", value: String(afterSequence))]
        }
        return jsonRequest(url: components.url!, method: "GET")
    }

    nonisolated static func makeCreateRequest(backendBase: URL, payload: AgentWorkspaceCreateRequest) throws -> URLRequest {
        try jsonRequest(url: backendBase.appendingPathComponent("api/agent-workspaces"), method: "POST", body: payload)
    }

    nonisolated static func makeActionRequest<Body: Encodable>(
        backendBase: URL,
        workspaceId: String,
        action: String?,
        method: String,
        body: Body?
    ) throws -> URLRequest {
        var url = workspaceURL(backendBase: backendBase, workspaceId: workspaceId)
        if let action { url.appendPathComponent(action) }
        return try jsonRequest(url: url, method: method, body: body)
    }

    private func fetch<Response: Decodable>(_ request: URLRequest, as type: Response.Type) async throws -> Response {
        let (data, response) = try await dataLoader(request)
        try OperationsHTTP.validate(response, data: data)
        return try JSONDecoder().decode(Response.self, from: data)
    }

    private func performAction(successMessage: String, operation: () async throws -> Void) async {
        isPerformingAction = true
        errorMessage = nil
        actionMessage = nil
        defer { isPerformingAction = false }
        do {
            try await operation()
            actionMessage = successMessage
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func applyDefaultAgents() {
        guard let readiness else { return }
        let available = Set(readiness.readyAgentIds)
        createDraft.selectedAgentIds = createDraft.selectedAgentIds.intersection(available)
        if createDraft.selectedAgentIds.isEmpty, let first = readiness.readyAgentIds.first {
            createDraft.selectedAgentIds = [first]
        }
    }

    private func selectDefaultCandidate(in state: AgentWorkspaceState) {
        if let selectedCandidateId, state.candidates.contains(where: { $0.candidateId == selectedCandidateId }) { return }
        selectedCandidateId = state.selectedCandidateId ?? state.candidates.first?.candidateId
    }

    private func replaceWorkspace(_ state: AgentWorkspaceState) {
        if let index = workspaces.firstIndex(where: { $0.workspaceId == state.workspaceId }) {
            workspaces[index] = state
        } else {
            workspaces.insert(state, at: 0)
        }
    }

    private func mergeEvents(_ incoming: [AgentWorkspaceEvent]) {
        var bySequence = Dictionary(uniqueKeysWithValues: events.map { ($0.sequence, $0) })
        for event in incoming { bySequence[event.sequence] = event }
        events = Array(bySequence.values.sorted { $0.sequence < $1.sequence }.suffix(Self.maximumDisplayedEvents))
    }

    private func clearSelection() {
        selectedWorkspaceId = nil
        selectedCandidateId = nil
        workspace = nil
        comparison = nil
        events = []
        lastEventSequence = nil
    }

    nonisolated private static func workspaceURL(backendBase: URL, workspaceId: String) -> URL {
        backendBase.appendingPathComponent("api/agent-workspaces").appendingPathComponent(workspaceId)
    }

    nonisolated private static func jsonRequest(url: URL, method: String) -> URLRequest {
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.timeoutInterval = 30
        return request
    }

    nonisolated private static func jsonRequest<Body: Encodable>(url: URL, method: String, body: Body?) throws -> URLRequest {
        var request = jsonRequest(url: url, method: method)
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(body)
        }
        return request
    }
}

private extension String {
    var nilIfEmpty: String? { isEmpty ? nil : self }
}
