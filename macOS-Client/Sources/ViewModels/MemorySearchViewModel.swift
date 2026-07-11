import Foundation

@MainActor
final class MemorySearchViewModel: ObservableObject {
    typealias DataLoader = (URLRequest) async throws -> (Data, URLResponse)

    @Published var query = ""
    @Published var scope: MemorySearchScope = .ordinary
    @Published var mode = "hybrid"
    @Published var results: [AcrossMemoryEntry] = []
    @Published var mergedResults: [MemoryMergedResult] = []
    @Published var routeResults: [MemoryRouteResult] = []
    @Published var proposals: [MemoryDistillationProposal] = []
    @Published var resultCount = 0
    @Published var isSearching = false
    @Published var isImproving = false
    @Published var mutatingMemoryID: String?
    @Published var hasSearched = false
    @Published var hasImproved = false
    @Published var errorMessage: String?
    @Published var improveErrorMessage: String?
    @Published var mutationErrorMessage: String?
    @Published var actionMessage: String?

    private let backendBase: URL
    private let dataLoader: DataLoader

    init(
        backendBase: URL = URL(string: "http://backend")!,
        dataLoader: @escaping DataLoader = { request in try await URLSession.shared.data(for: request) }
    ) {
        self.backendBase = backendBase
        self.dataLoader = dataLoader
    }

    var contentState: OperationalContentState {
        if isSearching { return .loading }
        if let errorMessage { return .error(errorMessage) }
        if !hasSearched { return .disabled("search_required") }
        if mergedResults.isEmpty { return .empty }
        return .success("\(resultCount)")
    }

    var improveState: OperationalContentState {
        if isImproving { return .loading }
        if let improveErrorMessage { return .error(improveErrorMessage) }
        if !hasImproved { return .disabled("improve_required") }
        if proposals.isEmpty { return .empty }
        return .success("\(proposals.count)")
    }

    var isBusy: Bool { isSearching || isImproving || mutatingMemoryID != nil }

    func search(projectRoot: String?) async {
        let text = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else {
            errorMessage = "Enter something to search for."
            return
        }
        isSearching = true
        hasSearched = true
        errorMessage = nil
        actionMessage = nil
        defer { isSearching = false }
        do {
            let payload = MemoryMergedRetrieveRequest(
                query: text,
                routes: MemoryRetrievalRoute.allCases,
                projectRoot: projectRoot?.trimmedNilIfEmpty,
                allProjects: false,
                status: scope.requestStatus,
                reviewPending: scope.includesPending,
                limit: 50,
                includeRouteResults: true
            )
            let request = try Self.makeMergedRetrieveRequest(backendBase: backendBase, payload: payload)
            let (data, response) = try await dataLoader(request)
            try OperationsHTTP.validate(response, data: data)
            let decoded = try JSONDecoder().decode(MemoryMergedRetrieveResponse.self, from: data)
            mergedResults = decoded.results
            results = decoded.results.map(\.entry)
            routeResults = decoded.routeResults
            resultCount = decoded.resultCount
        } catch {
            mergedResults = []
            results = []
            routeResults = []
            resultCount = 0
            errorMessage = error.localizedDescription
        }
    }

    func improve(projectRoot: String?, sourceIDs: [String] = []) async {
        isImproving = true
        hasImproved = true
        improveErrorMessage = nil
        mutationErrorMessage = nil
        actionMessage = nil
        defer { isImproving = false }
        do {
            let payload = MemoryImproveRequest(
                projectRoot: projectRoot?.trimmedNilIfEmpty,
                allProjects: false,
                sourceIds: Array(Set(sourceIDs)).sorted(),
                similarityThreshold: 0.34,
                maxProposalLength: 420
            )
            let request = try Self.makeImproveRequest(backendBase: backendBase, payload: payload)
            let (data, response) = try await dataLoader(request)
            try OperationsHTTP.validate(response, data: data)
            let decoded = try JSONDecoder().decode(MemoryImproveResponse.self, from: data)
            proposals = decoded.proposals
            if proposals.isEmpty {
                actionMessage = decoded.duplicateProposalCount > 0
                    ? "Existing suggestions already cover these memories."
                    : "No suggestions were needed."
            } else {
                actionMessage = "\(proposals.count) suggestion\(proposals.count == 1 ? "" : "s") ready for review."
            }
        } catch {
            proposals = []
            improveErrorMessage = error.localizedDescription
        }
    }

    func approve(memoryID: String, projectRoot: String?) async {
        await mutate(memoryID: memoryID, successMessage: "Memory approved.") {
            try Self.makeApproveRequest(backendBase: backendBase, memoryID: memoryID)
        }
        guard mutationErrorMessage == nil else { return }
        proposals.removeAll { $0.id == memoryID }
        if hasSearched {
            await search(projectRoot: projectRoot)
            actionMessage = "Memory approved."
        }
    }

    func rollback(memoryID: String, projectRoot: String?) async {
        guard mutatingMemoryID == nil else { return }
        mutatingMemoryID = memoryID
        mutationErrorMessage = nil
        actionMessage = nil
        defer { mutatingMemoryID = nil }
        do {
            let request = try Self.makeRollbackRequest(backendBase: backendBase, memoryID: memoryID)
            let (data, response) = try await dataLoader(request)
            try OperationsHTTP.validate(response, data: data)
            let decoded = try JSONDecoder().decode(MemoryRollbackResponse.self, from: data)
            let restoredCount = decoded.restoredSourceIds.count
            let restoredMessage = restoredCount == 0
                ? "Combined memory removed."
                : "\(restoredCount) original \(restoredCount == 1 ? "memory" : "memories") restored."
            proposals.removeAll { $0.id == memoryID }
            if hasSearched {
                await search(projectRoot: projectRoot)
            }
            actionMessage = restoredMessage
        } catch {
            mutationErrorMessage = error.localizedDescription
        }
    }

    private func mutate(
        memoryID: String,
        successMessage: String,
        request: () throws -> URLRequest
    ) async {
        guard mutatingMemoryID == nil else { return }
        mutatingMemoryID = memoryID
        mutationErrorMessage = nil
        actionMessage = nil
        defer { mutatingMemoryID = nil }
        do {
            let (data, response) = try await dataLoader(try request())
            try OperationsHTTP.validate(response, data: data)
            actionMessage = successMessage
        } catch {
            mutationErrorMessage = error.localizedDescription
        }
    }

    nonisolated static func makeSearchRequest(backendBase: URL, payload: MemorySearchRequest) throws -> URLRequest {
        try makeJSONRequest(
            url: backendBase.appendingPathComponent("api/memory/search"),
            payload: payload,
            timeout: 20
        )
    }

    nonisolated static func makeMergedRetrieveRequest(
        backendBase: URL,
        payload: MemoryMergedRetrieveRequest
    ) throws -> URLRequest {
        try makeJSONRequest(
            url: backendBase.appendingPathComponent("api/memory/retrieve/merged"),
            payload: payload,
            timeout: 35
        )
    }

    nonisolated static func makeImproveRequest(
        backendBase: URL,
        payload: MemoryImproveRequest
    ) throws -> URLRequest {
        try makeJSONRequest(
            url: backendBase.appendingPathComponent("api/memory/improve"),
            payload: payload,
            timeout: 65
        )
    }

    nonisolated static func makeApproveRequest(backendBase: URL, memoryID: String) throws -> URLRequest {
        try makeJSONRequest(
            url: memoryURL(backendBase: backendBase, memoryID: memoryID).appendingPathComponent("status"),
            payload: MemoryStatusUpdateRequest(status: "active"),
            timeout: 20
        )
    }

    nonisolated static func makeRollbackRequest(backendBase: URL, memoryID: String) throws -> URLRequest {
        var request = URLRequest(
            url: backendBase
                .appendingPathComponent("api/memory/distilled")
                .appendingPathComponent(memoryID)
                .appendingPathComponent("rollback")
        )
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.timeoutInterval = 20
        return request
    }

    private nonisolated static func memoryURL(backendBase: URL, memoryID: String) -> URL {
        backendBase
            .appendingPathComponent("api/memory/memories")
            .appendingPathComponent(memoryID)
    }

    private nonisolated static func makeJSONRequest<Payload: Encodable>(
        url: URL,
        payload: Payload,
        timeout: TimeInterval
    ) throws -> URLRequest {
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = timeout
        request.httpBody = try JSONEncoder().encode(payload)
        return request
    }
}

private extension String {
    var trimmedNilIfEmpty: String? {
        let value = trimmingCharacters(in: .whitespacesAndNewlines)
        return value.isEmpty ? nil : value
    }
}
