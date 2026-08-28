import Foundation
import Combine

private enum GoalActionError: Error {
    case rejected(String)
}

class TaskOrchestrationViewModel: ObservableObject {
    @Published var tasks: [TaskSummary] = []
    @Published var selectedTask: TaskDetail?
    @Published var selectedGoalContract: GoalContractEnvelope?
    @Published var goalTaskState: GoalTaskDetailState = .legacyEmpty
    @Published var isLoadingGoalContract = false
    @Published var goalContractError: String?
    @Published var viewMode: ViewMode = .empty
    @Published var isLoading = false
    @Published var isSubmittingTask = false
    @Published var isAcceptingTask = false
    @Published var isRejectingTask = false
    @Published var isLoadingMoreTasks = false
    @Published var hasMoreTasks = false
    @Published var searchText = ""
    @Published var errorMessage: String?
    @Published var backendConnectionState: BackendConnectionState = .unknown
    @Published var releaseEvaluation: ReleaseEvaluationSummary?
    @Published var isLoadingReleaseEvaluation = false
    @Published var releaseEvaluationError: String?
    @Published var releaseE2EScenarios: [ReleaseE2EScenario] = []
    @Published var isStartingReleaseE2E = false
    @Published var releaseE2EError: String?
    @Published var selectedEvidenceBundle: TaskEvidenceBundle?
    @Published var isLoadingTaskEvidence = false
    @Published var taskEvidenceError: String?
    @Published var exportedEvidenceBundleURL: URL?
    @Published var selectedExecutionTrajectory: TaskExecutionTrajectory?
    @Published var isLoadingExecutionTrajectory = false
    @Published var executionTrajectoryError: String?
    @Published var exportedExecutionTrajectoryURL: URL?
    @Published var selectedArtifactPreview: ArtifactPreview?
    @Published var isLoadingArtifactPreview = false
    @Published var orchestratorPluginStatus: OrchestratorPluginStatus?
    @Published var isLoadingOrchestratorPlugin = false
    @Published var isInstallingOrchestratorPlugin = false
    @Published var orchestratorPluginError: String?
    private let taskPageSize = 50
    private var taskListOffset = 0
    private var projectDirectoryFilter: String?
    private var taskListRequestGeneration = 0
    private var trajectoryRequestGeneration = 0
    private var goalRequestGeneration = 0
    private let requestData: (URLRequest) async throws -> (Data, URLResponse)
    private let trajectoryExportsDirectory: URL

    init(
        requestData: @escaping (URLRequest) async throws -> (Data, URLResponse) = { request in
            try await URLSession.shared.data(for: request)
        },
        trajectoryExportsDirectory: URL? = nil
    ) {
        self.requestData = requestData
        self.trajectoryExportsDirectory = trajectoryExportsDirectory ?? LocalAppPaths.evidenceExportsDir
    }

    enum ViewMode {
        case empty
        case detail
        case createForm
        case releaseCenter
    }

    enum BackendConnectionState: Equatable {
        case unknown
        case checking
        case connected
        case unavailable(String)
    }

    var isBackendUnavailable: Bool {
        if case .unavailable = backendConnectionState {
            return true
        }
        return false
    }

    var backendUnavailableMessage: String? {
        if case .unavailable(let message) = backendConnectionState {
            return message
        }
        return nil
    }

    var isOrchestratorPluginUnavailable: Bool {
        guard let runtime = orchestratorPluginStatus?.runtime else { return false }
        return runtime.implementation == "external" && runtime.available == false
    }

    var orchestratorPluginUnavailableMessage: String {
        if let error = orchestratorPluginError, !error.isEmpty {
            return error
        }
        if let note = orchestratorPluginStatus?.runtime.connectionNote, !note.isEmpty {
            return note
        }
        return "Across Orchestrator is required for task orchestration."
    }

    var canInstallOrchestratorPlugin: Bool {
        orchestratorPluginStatus?.install.installable == true && !isInstallingOrchestratorPlugin
    }

    typealias DeliveryTaskType = TaskOrchestrationDeliveryTaskType
    typealias AutoTaskSubmitResponse = TaskOrchestrationAutoTaskSubmitResponse
    typealias TaskSummary = TaskOrchestrationTaskSummary
    typealias TaskPageResponse = TaskOrchestrationTaskPageResponse
    typealias TaskReviewResponse = TaskOrchestrationTaskReviewResponse
    typealias OrchestratorPluginStatus = TaskOrchestrationOrchestratorPluginStatus
    typealias QualityHealth = TaskOrchestrationQualityHealth
    typealias DeliveryReport = TaskOrchestrationDeliveryReport
    typealias TaskObservability = TaskOrchestrationTaskObservability
    typealias TaskDetail = TaskOrchestrationTaskDetail
    typealias OwnerDecisionSummary = TaskOrchestrationOwnerDecisionSummary
    typealias WaveDetail = TaskOrchestrationWaveDetail
    typealias SubtaskDetail = TaskOrchestrationSubtaskDetail
    typealias FixRoundDetail = TaskOrchestrationFixRoundDetail
    typealias ArtifactInfo = TaskOrchestrationArtifactInfo
    typealias Artifact = TaskOrchestrationArtifact
    typealias ResumableTask = TaskOrchestrationResumableTask
    typealias ProgressEvent = TaskOrchestrationProgressEvent
    typealias SubtaskUpdate = TaskOrchestrationSubtaskUpdate
    typealias TaskStatusUpdate = TaskOrchestrationTaskStatusUpdate
    typealias WaveUpdate = TaskOrchestrationWaveUpdate
    typealias PollStatusResponse = TaskOrchestrationPollStatusResponse
    typealias PollSubtaskStatus = TaskOrchestrationPollSubtaskStatus
    typealias PollWaveStatus = TaskOrchestrationPollWaveStatus

    struct ArtifactPreview: Identifiable, Equatable {
        let id: String
        let fileName: String
        let content: String
    }

    private var sseTask: Task<Void, Never>?
    private var reconnectAttempts = 0
    private let maxReconnectAttempts = 10
    private let reconnectDelay: UInt64 = 5_000_000_000
    private var pollingTask: Task<Void, Never>?
    // Initial polling: quickly detect whether the task leaves decomposing after submit.
    private var initialPollingTask: Task<Void, Never>?
    // SSE is a fast path. This full-detail poller is the consistency fallback
    // for bundled app runs where stream events can be missed or delayed.
    private var detailPollingTask: Task<Void, Never>?
    private let detailPollingInterval: UInt64 = 5_000_000_000
    private let terminalSettlePollLimit = 12

    private var baseURL: URL? {
        if let urlString = AppUserDefaults.current.string(forKey: "serverURL") {
            return URL(string: urlString)
        }
        return URL(string: "http://backend")
    }

    func previewArtifact(_ artifact: Artifact) {
        Task { @MainActor in
            guard !isLoadingArtifactPreview else { return }
            guard let baseURL else {
                taskEvidenceError = "Server URL not configured"
                return
            }
            let reference = artifact.filePath.trimmingCharacters(in: .whitespacesAndNewlines)
            guard reference.hasPrefix("/api/workers/artifacts/") else {
                taskEvidenceError = "This artifact is not available for in-app preview."
                return
            }

            isLoadingArtifactPreview = true
            taskEvidenceError = nil
            defer { isLoadingArtifactPreview = false }

            do {
                let relativePath = String(reference.drop(while: { $0 == "/" }))
                var request = URLRequest(url: baseURL.appendingPathComponent(relativePath))
                request.setValue("text/plain, text/markdown, application/json", forHTTPHeaderField: "Accept")
                request.timeoutInterval = 30
                let (data, response) = try await URLSession.shared.data(for: request)
                guard let httpResponse = response as? HTTPURLResponse,
                      (200...299).contains(httpResponse.statusCode) else {
                    throw URLError(.badServerResponse)
                }

                let content: String
                if artifact.fileName.lowercased().hasSuffix(".json"),
                   let value = try? JSONSerialization.jsonObject(with: data),
                   let formatted = try? JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted, .sortedKeys]),
                   let text = String(data: formatted, encoding: .utf8) {
                    content = text
                } else if let text = String(data: data, encoding: .utf8) {
                    content = text
                } else {
                    throw URLError(.cannotDecodeContentData)
                }

                selectedArtifactPreview = ArtifactPreview(
                    id: artifact.id,
                    fileName: artifact.fileName,
                    content: content
                )
            } catch {
                taskEvidenceError = "Unable to preview \(artifact.fileName)."
            }
        }
    }

    func closeArtifactPreview() {
        selectedArtifactPreview = nil
    }

    func loadTasks() {
        loadOrchestratorPluginStatus()
        loadTaskPage(reset: true)
        loadReleaseEvaluation()
        loadReleaseE2EScenarios()
    }

    func updateProjectDirectoryFilter(_ directory: String?, reload: Bool = true) {
        let normalizedDirectory = normalizedProjectDirectory(directory)
        guard normalizedDirectory != projectDirectoryFilter else { return }
        projectDirectoryFilter = normalizedDirectory
        tasks = []
        taskListOffset = 0
        hasMoreTasks = false

        if let selectedTask,
           !projectDirectory(selectedTask.projectDir, belongsTo: normalizedDirectory) {
            enterWorkflowPicker()
        }

        if reload {
            loadTaskPage(reset: true)
        }
    }

    private func normalizedProjectDirectory(_ directory: String?) -> String? {
        guard let directory = directory?.trimmingCharacters(in: .whitespacesAndNewlines),
              !directory.isEmpty else { return nil }
        return URL(fileURLWithPath: directory)
            .standardizedFileURL
            .resolvingSymlinksInPath()
            .path
    }

    private func projectDirectory(_ directory: String?, belongsTo projectRoot: String?) -> Bool {
        guard let projectRoot else { return directory == nil }
        guard let directory = normalizedProjectDirectory(directory) else { return false }
        return directory == projectRoot || directory.hasPrefix(projectRoot + "/")
    }

    func acceptTaskResult(_ taskId: String, onAccepted: @escaping () -> Void) {
        Task { @MainActor in
            guard !isAcceptingTask else { return }
            guard selectedTask?.taskId == taskId else { return }
            isAcceptingTask = true
            errorMessage = nil

            guard let baseURL else {
                errorMessage = "Server URL not configured"
                isAcceptingTask = false
                return
            }

            do {
                let url = baseURL.appendingPathComponent("api/tasks/\(taskId)/accept")
                var request = URLRequest(url: url)
                request.httpMethod = "POST"
                request.setValue("application/json", forHTTPHeaderField: "Accept")
                let (data, response) = try await URLSession.shared.data(for: request)
                guard let httpResponse = response as? HTTPURLResponse,
                      (200...299).contains(httpResponse.statusCode) else {
                    let detail = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["detail"] as? String
                    throw NSError(
                        domain: "TaskReview",
                        code: (response as? HTTPURLResponse)?.statusCode ?? -1,
                        userInfo: [NSLocalizedDescriptionKey: detail ?? "Unable to accept this result"]
                    )
                }

                let review = try JSONDecoder().decode(TaskReviewResponse.self, from: data)
                if let task = selectedTask, task.taskId == review.taskId {
                    selectedTask = task.replacing(
                        reviewStatus: review.reviewStatus,
                        acceptedAt: review.acceptedAt
                    )
                }
                tasks = tasks.map { summary in
                    guard summary.taskId == review.taskId else { return summary }
                    return TaskSummary(
                        taskId: summary.taskId,
                        description: summary.description,
                        status: summary.status,
                        progress: summary.progress,
                        completedCount: summary.completedCount,
                        totalCount: summary.totalCount,
                        projectDir: summary.projectDir,
                        ownerAgent: summary.ownerAgent,
                        deliveryMode: summary.deliveryMode,
                        externalTask: summary.externalTask,
                        reviewStatus: review.reviewStatus,
                        acceptedAt: review.acceptedAt
                    )
                }
                isAcceptingTask = false
                onAccepted()
            } catch {
                errorMessage = error.localizedDescription
                isAcceptingTask = false
            }
        }
    }

    func rejectTaskResult(_ taskId: String, onRejected: @escaping () -> Void) {
        Task { @MainActor in
            guard !isRejectingTask else { return }
            guard selectedTask?.taskId == taskId else { return }
            isRejectingTask = true
            errorMessage = nil

            guard let baseURL else {
                errorMessage = "Server URL not configured"
                isRejectingTask = false
                return
            }

            do {
                let url = baseURL.appendingPathComponent("api/tasks/\(taskId)/reject")
                var request = URLRequest(url: url)
                request.httpMethod = "POST"
                request.setValue("application/json", forHTTPHeaderField: "Accept")
                let (data, response) = try await URLSession.shared.data(for: request)
                guard let httpResponse = response as? HTTPURLResponse,
                      (200...299).contains(httpResponse.statusCode) else {
                    let detail = Self.backendErrorMessage(from: data)
                    throw NSError(
                        domain: "TaskReview",
                        code: (response as? HTTPURLResponse)?.statusCode ?? -1,
                        userInfo: [NSLocalizedDescriptionKey: detail ?? "Unable to reject this result"]
                    )
                }

                let review = try JSONDecoder().decode(TaskReviewResponse.self, from: data)
                if let task = selectedTask, task.taskId == review.taskId {
                    selectedTask = task.replacing(
                        reviewStatus: review.reviewStatus,
                        acceptedAt: review.acceptedAt
                    )
                }
                tasks = tasks.map { summary in
                    guard summary.taskId == review.taskId else { return summary }
                    return TaskSummary(
                        taskId: summary.taskId,
                        description: summary.description,
                        status: summary.status,
                        progress: summary.progress,
                        completedCount: summary.completedCount,
                        totalCount: summary.totalCount,
                        projectDir: summary.projectDir,
                        ownerAgent: summary.ownerAgent,
                        deliveryMode: summary.deliveryMode,
                        externalTask: summary.externalTask,
                        reviewStatus: review.reviewStatus,
                        acceptedAt: review.acceptedAt
                    )
                }
                isRejectingTask = false
                onRejected()
            } catch {
                errorMessage = error.localizedDescription
                isRejectingTask = false
            }
        }
    }

    func loadOrchestratorPluginStatus() {
        Task { @MainActor in
            guard let baseURL = baseURL else {
                orchestratorPluginError = "Server URL not configured"
                return
            }

            isLoadingOrchestratorPlugin = true
            orchestratorPluginError = nil

            do {
                let url = baseURL.appendingPathComponent("api/orchestrator/plugin")
                var request = URLRequest(url: url)
                request.httpMethod = "GET"
                request.setValue("application/json", forHTTPHeaderField: "Accept")
                request.timeoutInterval = 15

                let (data, response) = try await URLSession.shared.data(for: request)
                guard let httpResponse = response as? HTTPURLResponse,
                      (200...299).contains(httpResponse.statusCode) else {
                    orchestratorPluginError = Self.backendErrorMessage(from: data) ?? "Failed to load Across Orchestrator status"
                    isLoadingOrchestratorPlugin = false
                    return
                }

                orchestratorPluginStatus = try JSONDecoder().decode(OrchestratorPluginStatus.self, from: data)
                isLoadingOrchestratorPlugin = false
            } catch {
                orchestratorPluginError = error.localizedDescription
                isLoadingOrchestratorPlugin = false
            }
        }
    }

    func installOrchestratorPlugin() {
        Task { @MainActor in
            guard !isInstallingOrchestratorPlugin else { return }
            guard let baseURL = baseURL else {
                orchestratorPluginError = "Server URL not configured"
                return
            }

            isInstallingOrchestratorPlugin = true
            orchestratorPluginError = nil

            do {
                let url = baseURL.appendingPathComponent("api/orchestrator/plugin/install")
                var request = URLRequest(url: url)
                request.httpMethod = "POST"
                request.setValue("application/json", forHTTPHeaderField: "Accept")
                request.timeoutInterval = 900

                let (data, response) = try await URLSession.shared.data(for: request)
                guard let httpResponse = response as? HTTPURLResponse else {
                    throw URLError(.badServerResponse)
                }
                guard (200...299).contains(httpResponse.statusCode) else {
                    orchestratorPluginError = Self.backendErrorMessage(from: data) ?? "Failed to install Across Orchestrator"
                    isInstallingOrchestratorPlugin = false
                    return
                }

                orchestratorPluginStatus = try JSONDecoder().decode(OrchestratorPluginStatus.self, from: data)
                isInstallingOrchestratorPlugin = false
                loadTasks()
            } catch {
                orchestratorPluginError = error.localizedDescription
                isInstallingOrchestratorPlugin = false
            }
        }
    }

    func openReleaseCenter() {
        viewMode = .releaseCenter
        loadReleaseEvaluation()
    }

    func closeEvidenceBundle() {
        trajectoryRequestGeneration += 1
        selectedEvidenceBundle = nil
        exportedEvidenceBundleURL = nil
        taskEvidenceError = nil
        selectedExecutionTrajectory = nil
        isLoadingExecutionTrajectory = false
        executionTrajectoryError = nil
        exportedExecutionTrajectoryURL = nil
    }

    @discardableResult
    func loadTaskExecutionTrajectory(
        _ taskId: String,
        offset: Int = 0,
        limit: Int = 200
    ) -> Task<Void, Never> {
        Task { @MainActor in
            await performTaskExecutionTrajectoryLoad(taskId, offset: offset, limit: limit)
        }
    }

    @discardableResult
    func loadNextTaskExecutionTrajectoryPage(_ taskId: String) -> Task<Void, Never> {
        Task { @MainActor in
            guard
                let trajectory = selectedExecutionTrajectory,
                trajectory.taskId == taskId,
                trajectory.page.hasMore,
                let nextOffset = trajectory.page.nextOffset
            else { return }
            await performTaskExecutionTrajectoryLoad(
                taskId,
                offset: nextOffset,
                limit: trajectory.page.limit
            )
        }
    }

    @MainActor
    private func performTaskExecutionTrajectoryLoad(
        _ taskId: String,
        offset: Int,
        limit: Int
    ) async {
        trajectoryRequestGeneration += 1
        let generation = trajectoryRequestGeneration
        if selectedExecutionTrajectory?.taskId != taskId || offset == 0 {
            selectedExecutionTrajectory = nil
            exportedExecutionTrajectoryURL = nil
        }
        isLoadingExecutionTrajectory = true
        executionTrajectoryError = nil

        guard offset >= 0, (1...500).contains(limit), let baseURL else {
            if generation == trajectoryRequestGeneration {
                isLoadingExecutionTrajectory = false
                executionTrajectoryError = "Execution trajectory is unavailable."
            }
            return
        }

        do {
            let request = try Self.executionTrajectoryRequest(
                baseURL: baseURL,
                taskId: taskId,
                offset: offset,
                limit: limit
            )
            let (data, response) = try await requestData(request)
            guard generation == trajectoryRequestGeneration else { return }
            guard let httpResponse = response as? HTTPURLResponse,
                  (200...299).contains(httpResponse.statusCode) else {
                throw URLError(.badServerResponse)
            }
            let trajectory = try JSONDecoder().decode(TaskExecutionTrajectory.self, from: data)
            guard
                trajectory.taskId == taskId,
                trajectory.page.offset == offset,
                trajectory.page.limit == limit
            else {
                throw URLError(.cannotParseResponse)
            }
            guard generation == trajectoryRequestGeneration else { return }
            selectedExecutionTrajectory = trajectory
            isLoadingExecutionTrajectory = false
        } catch {
            guard generation == trajectoryRequestGeneration else { return }
            isLoadingExecutionTrajectory = false
            executionTrajectoryError = "Execution trajectory is unavailable."
        }
    }

    @discardableResult
    func exportTaskExecutionTrajectory(_ taskId: String) -> Task<Void, Never> {
        Task { @MainActor in
            guard let trajectory = selectedExecutionTrajectory, trajectory.taskId == taskId else {
                executionTrajectoryError = "Execution trajectory is unavailable."
                return
            }
            do {
                try FileManager.default.createDirectory(
                    at: trajectoryExportsDirectory,
                    withIntermediateDirectories: true
                )
                let exportURL = trajectoryExportsDirectory
                    .appendingPathComponent(TaskExecutionTrajectory.exportFileName(taskId: taskId))
                try trajectory.prettyPublicJSON().write(to: exportURL, options: [.atomic])
                exportedExecutionTrajectoryURL = exportURL
                executionTrajectoryError = nil
            } catch {
                executionTrajectoryError = "Execution trajectory export failed."
            }
        }
    }

    private static func executionTrajectoryRequest(
        baseURL: URL,
        taskId: String,
        offset: Int,
        limit: Int
    ) throws -> URLRequest {
        var components = URLComponents(
            url: baseURL
                .appendingPathComponent("api/tasks")
                .appendingPathComponent(taskId)
                .appendingPathComponent("execution-trajectory"),
            resolvingAgainstBaseURL: false
        )
        components?.queryItems = [
            URLQueryItem(name: "offset", value: String(offset)),
            URLQueryItem(name: "limit", value: String(limit)),
        ]
        guard let url = components?.url else {
            throw URLError(.badURL)
        }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.timeoutInterval = 20
        return request
    }

    func loadReleaseEvaluation() {
        Task { @MainActor in
            guard let baseURL = baseURL else {
                releaseEvaluation = nil
                releaseEvaluationError = "Server URL not configured"
                return
            }

            isLoadingReleaseEvaluation = true
            releaseEvaluationError = nil

            do {
                let url = baseURL.appendingPathComponent("api/release/evaluation")
                var request = URLRequest(url: url)
                request.httpMethod = "GET"
                request.setValue("application/json", forHTTPHeaderField: "Accept")
                request.timeoutInterval = 10

                let (data, response) = try await URLSession.shared.data(for: request)
                guard let httpResponse = response as? HTTPURLResponse,
                      (200...299).contains(httpResponse.statusCode) else {
                    throw URLError(.badServerResponse)
                }

                releaseEvaluation = try JSONDecoder().decode(ReleaseEvaluationSummary.self, from: data)
                isLoadingReleaseEvaluation = false
            } catch {
                releaseEvaluation = nil
                releaseEvaluationError = error.localizedDescription
                isLoadingReleaseEvaluation = false
            }
        }
    }

    @discardableResult
    func loadTaskEvidenceBundle(_ taskId: String, releaseGate: Bool = false) -> Task<Void, Never> {
        Task { @MainActor in
            guard let baseURL = baseURL else {
                taskEvidenceError = "Server URL not configured"
                return
            }

            isLoadingTaskEvidence = true
            taskEvidenceError = nil
            exportedEvidenceBundleURL = nil
            trajectoryRequestGeneration += 1
            selectedExecutionTrajectory = nil
            isLoadingExecutionTrajectory = false
            executionTrajectoryError = nil
            exportedExecutionTrajectoryURL = nil

            do {
                let data = try await Self.fetchEvidenceBundleData(
                    baseURL: baseURL,
                    taskId: taskId,
                    releaseGate: releaseGate,
                    requestData: requestData
                )
                selectedEvidenceBundle = try JSONDecoder().decode(TaskEvidenceBundle.self, from: data)
                isLoadingTaskEvidence = false
                await performTaskExecutionTrajectoryLoad(taskId, offset: 0, limit: 200)
            } catch {
                taskEvidenceError = error.localizedDescription
                isLoadingTaskEvidence = false
            }
        }
    }

    func exportTaskEvidenceBundle(_ taskId: String, releaseGate: Bool = false) {
        Task { @MainActor in
            guard let baseURL = baseURL else {
                taskEvidenceError = "Server URL not configured"
                return
            }

            isLoadingTaskEvidence = true
            taskEvidenceError = nil

            do {
                let data = try await Self.fetchEvidenceBundleData(
                    baseURL: baseURL,
                    taskId: taskId,
                    releaseGate: releaseGate,
                    requestData: requestData
                )
                selectedEvidenceBundle = try JSONDecoder().decode(TaskEvidenceBundle.self, from: data)
                let exportURL = LocalAppPaths.evidenceExportsDir
                    .appendingPathComponent(TaskEvidenceBundle.exportFileName(taskId: taskId))
                let prettyData = Self.prettyPrintedJSONData(from: data) ?? data
                try prettyData.write(to: exportURL, options: [.atomic])
                exportedEvidenceBundleURL = exportURL
                isLoadingTaskEvidence = false
            } catch {
                taskEvidenceError = error.localizedDescription
                isLoadingTaskEvidence = false
            }
        }
    }

    private static func fetchEvidenceBundleData(
        baseURL: URL,
        taskId: String,
        releaseGate: Bool,
        requestData: (URLRequest) async throws -> (Data, URLResponse)
    ) async throws -> Data {
        var components = URLComponents(
            url: baseURL
            .appendingPathComponent("api/tasks")
            .appendingPathComponent(taskId)
            .appendingPathComponent("evidence-bundle"),
            resolvingAgainstBaseURL: false
        )
        if releaseGate {
            components?.queryItems = [
                URLQueryItem(name: "expected_files", value: TaskEvidenceBundle.releaseE2EExpectedFiles.joined(separator: ",")),
                URLQueryItem(name: "required_probes", value: TaskEvidenceBundle.releaseE2ERequiredProbes.joined(separator: ",")),
                URLQueryItem(name: "min_quality_score", value: "70"),
                URLQueryItem(name: "max_remediation_attempts", value: "2")
            ]
        }
        guard let url = components?.url else {
            throw URLError(.badURL)
        }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.timeoutInterval = 20

        let (data, response) = try await requestData(request)
        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            throw URLError(.badServerResponse)
        }
        return data
    }

    private static func prettyPrintedJSONData(from data: Data) -> Data? {
        guard let object = try? JSONSerialization.jsonObject(with: data),
              JSONSerialization.isValidJSONObject(object) else {
            return nil
        }
        return try? JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted, .sortedKeys])
    }

    func loadReleaseE2EScenarios() {
        Task { @MainActor in
            guard let baseURL = baseURL else {
                releaseE2EScenarios = []
                return
            }

            do {
                let url = baseURL.appendingPathComponent("api/release/e2e/scenarios")
                var request = URLRequest(url: url)
                request.httpMethod = "GET"
                request.setValue("application/json", forHTTPHeaderField: "Accept")
                request.timeoutInterval = 10

                let (data, response) = try await URLSession.shared.data(for: request)
                guard let httpResponse = response as? HTTPURLResponse,
                      (200...299).contains(httpResponse.statusCode) else {
                    return
                }

                releaseE2EScenarios = try JSONDecoder().decode(ReleaseE2EScenarioListResponse.self, from: data).scenarios
            } catch {
                releaseE2EScenarios = []
            }
        }
    }

    func startReleaseE2E() {
        Task { @MainActor in
            guard !isStartingReleaseE2E else { return }
            guard !isOrchestratorPluginUnavailable else {
                releaseE2EError = orchestratorPluginUnavailableMessage
                return
            }
            guard let baseURL = baseURL else {
                releaseE2EError = "Server URL not configured"
                return
            }

            isStartingReleaseE2E = true
            releaseE2EError = nil
            errorMessage = nil

            do {
                let url = baseURL.appendingPathComponent("api/release/e2e/tasks")
                var request = URLRequest(url: url)
                request.httpMethod = "POST"
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                request.setValue("application/json", forHTTPHeaderField: "Accept")

                let scenarioId = releaseE2EScenarios.first?.id ?? "cross_agent_full_delivery_v1"
                let runLabel = Self.releaseE2ERunLabel()
                request.httpBody = try JSONSerialization.data(withJSONObject: [
                    "scenario_id": scenarioId,
                    "run_label": runLabel
                ])

                let (data, response) = try await URLSession.shared.data(for: request)
                guard let httpResponse = response as? HTTPURLResponse else {
                    throw URLError(.badServerResponse)
                }

                guard (200...299).contains(httpResponse.statusCode) else {
                    releaseE2EError = Self.backendErrorMessage(from: data)
                        ?? "Failed to start release E2E (HTTP \(httpResponse.statusCode))"
                    isStartingReleaseE2E = false
                    return
                }

                let result = try JSONDecoder().decode(ReleaseE2ETaskResponse.self, from: data)
                viewMode = .detail
                selectTask(result.taskId)
                loadTasks()
                startInitialPolling(for: result.taskId)
                isStartingReleaseE2E = false
            } catch {
                releaseE2EError = error.localizedDescription
                isStartingReleaseE2E = false
            }
        }
    }

    private static func releaseE2ERunLabel() -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyyMMdd-HHmmss"
        return "ui-\(formatter.string(from: Date()))"
    }

    private static func backendErrorMessage(from data: Data) -> String? {
        guard !data.isEmpty else { return nil }
        if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let detail = json["detail"] {
            if let text = detail as? String, !text.isEmpty {
                return text
            }
            if let object = detail as? [String: Any] {
                var parts: [String] = []
                if let message = object["message"] as? String, !message.isEmpty {
                    parts.append(message)
                }
                if let missing = object["missing_providers"] as? [String], !missing.isEmpty {
                    parts.append("Missing: \(missing.joined(separator: ", "))")
                }
                if !parts.isEmpty {
                    return parts.joined(separator: " ")
                }
            }
        }
        return String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    func loadMoreTasks() {
        guard hasMoreTasks, !isLoadingMoreTasks else { return }
        loadTaskPage(reset: false)
    }

    private func loadTaskPage(reset: Bool) {
        taskListRequestGeneration += 1
        let requestGeneration = taskListRequestGeneration
        let requestedProjectDirectory = projectDirectoryFilter
        Task { @MainActor in
            if reset {
                isLoading = true
                taskListOffset = 0
                hasMoreTasks = false
                backendConnectionState = .checking
            } else {
                isLoadingMoreTasks = true
            }
            errorMessage = nil

            guard let baseURL = baseURL else {
                errorMessage = "Server URL not configured"
                backendConnectionState = .unavailable("Server URL not configured")
                isLoading = false
                isLoadingMoreTasks = false
                return
            }

            for attempt in 0..<5 {
                do {
                    let offset = reset ? 0 : taskListOffset
                    var components = URLComponents(
                        url: baseURL.appendingPathComponent("api/tasks/page"),
                        resolvingAgainstBaseURL: false
                    )
                    var queryItems = [
                        URLQueryItem(name: "limit", value: "\(taskPageSize)"),
                        URLQueryItem(name: "offset", value: "\(offset)")
                    ]
                    if let requestedProjectDirectory {
                        queryItems.append(URLQueryItem(name: "project_dir", value: requestedProjectDirectory))
                    }
                    components?.queryItems = queryItems
                    guard let url = components?.url else {
                        throw URLError(.badURL)
                    }
                    var request = URLRequest(url: url)
                    request.httpMethod = "GET"
                    request.setValue("application/json", forHTTPHeaderField: "Accept")
                    request.timeoutInterval = 10

                    let (data, response) = try await URLSession.shared.data(for: request)

                    guard let httpResponse = response as? HTTPURLResponse,
                          (200...299).contains(httpResponse.statusCode) else {
                        throw URLError(.badServerResponse)
                    }

                    let decoder = JSONDecoder()
                    let page = try decoder.decode(TaskPageResponse.self, from: data)
                    guard requestGeneration == taskListRequestGeneration,
                          requestedProjectDirectory == projectDirectoryFilter else { return }

                    if reset {
                        tasks = page.tasks
                    } else {
                        let existingIds = Set(tasks.map { $0.taskId })
                        tasks.append(contentsOf: page.tasks.filter { !existingIds.contains($0.taskId) })
                    }

                    taskListOffset = page.offset + page.tasks.count
                    hasMoreTasks = page.hasMore
                    backendConnectionState = .connected
                    isLoading = false
                    isLoadingMoreTasks = false
                    return
                } catch {
                    guard requestGeneration == taskListRequestGeneration else { return }
                    if attempt == 4 {
                        errorMessage = error.localizedDescription
                        backendConnectionState = .unavailable(error.localizedDescription)
                        isLoading = false
                        isLoadingMoreTasks = false
                        return
                    }

                    try? await Task.sleep(nanoseconds: 1_000_000_000)
                }
            }
        }
    }

    func selectTask(_ taskId: String) {
        Task { @MainActor in
            isLoading = true
            errorMessage = nil

            stopSSE()
            clearGoalContract()
            let summaryStatus = tasks.first(where: { $0.taskId == taskId })?.status
            let isSuspendedSummary = summaryStatus.map(ResumableTask.isRecoverableDisplayStatus) ?? false

            guard let baseURL = baseURL else {
                errorMessage = "Server URL not configured"
                isLoading = false
                return
            }

            do {
                let url = baseURL.appendingPathComponent("api/tasks/\(taskId)")
                var request = URLRequest(url: url)
                request.httpMethod = "GET"
                request.setValue("application/json", forHTTPHeaderField: "Accept")

                let (data, response) = try await URLSession.shared.data(for: request)

                guard let httpResponse = response as? HTTPURLResponse,
                      (200...299).contains(httpResponse.statusCode) else {
                    errorMessage = "Failed to load task details"
                    isLoading = false
                    return
                }

                let decoder = JSONDecoder()
                let decodedTaskDetail = try decoder.decode(TaskDetail.self, from: data)
                let taskDetail = isSuspendedSummary
                    ? decodedTaskDetail.replacing(status: "suspended")
                    : decodedTaskDetail
                selectedTask = taskDetail
                viewMode = .detail
                isLoading = false
                loadGoalContract(taskId)

                if !isSuspendedSummary {
                    reconnectAttempts = 0
                    startSSE(for: taskId)
                    startDetailPolling(for: taskId)
                }
            } catch {
                print("Failed to decode task detail for \(taskId): \(error)")
                errorMessage = "Failed to load task detail: \(error.localizedDescription)"
                isLoading = false
            }
        }
    }

    func submitTask(
        description: String,
        taskTypes: [String],
        ownerAgent: String,
        allowedSubtaskAgents: [String] = [],
        projectDir: String?,
        strictDependency: Bool = true,
        onCompletion: ((Bool) -> Void)? = nil
    ) {
        Task { @MainActor in
            guard !isSubmittingTask else { return }
            guard !isOrchestratorPluginUnavailable else {
                errorMessage = orchestratorPluginUnavailableMessage
                onCompletion?(false)
                return
            }
            isSubmittingTask = true
            isLoading = true
            errorMessage = nil

            guard let baseURL = baseURL else {
                errorMessage = "Server URL not configured"
                isSubmittingTask = false
                isLoading = false
                onCompletion?(false)
                return
            }

            do {
                let url = baseURL.appendingPathComponent("api/tasks/auto")
                var request = URLRequest(url: url)
                request.httpMethod = "POST"
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                request.setValue("application/json", forHTTPHeaderField: "Accept")
                request.timeoutInterval = 60

                var body: [String: Any] = [
                    "description": description,
                    "task_types": taskTypes,
                    "owner_agent": ownerAgent,
                    "allowed_subtask_agents": allowedSubtaskAgents
                ]

                if let projectDir = projectDir {
                    body["project_dir"] = projectDir
                }

                body["strict_dependency"] = strictDependency
                body["enable_wave_gate"] = true

                request.httpBody = try JSONSerialization.data(withJSONObject: body)

                let (data, response) = try await URLSession.shared.data(for: request)

                guard let httpResponse = response as? HTTPURLResponse else {
                    errorMessage = "Invalid response"
                    isSubmittingTask = false
                    isLoading = false
                    return
                }

                if (200...299).contains(httpResponse.statusCode) {
                    let decoder = JSONDecoder()
                    let result = try decoder.decode(AutoTaskSubmitResponse.self, from: data)
                    if let newTaskId = result.taskId {
                        viewMode = .detail
                        selectTask(newTaskId)
                        loadTasks()
                        // P0-5: initial polling quickly detects whether the task leaves decomposing.
                        startInitialPolling(for: newTaskId)
                        onCompletion?(true)
                    } else {
                        viewMode = .empty
                        onCompletion?(false)
                    }
                } else {
                    // Try to parse error detail from response
                    if let errorJson = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                       let detail = errorJson["detail"] as? [String: Any],
                       let decisionIDs = detail["decision_ids"] as? [String],
                       decisionIDs.contains("compatible_worker_workflow_required") {
                        errorMessage = "compatible_worker_workflow_required"
                    } else if let errorJson = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                              let detail = errorJson["detail"] as? String {
                        errorMessage = detail
                    } else if let text = String(data: data, encoding: .utf8), !text.isEmpty {
                        errorMessage = text
                    } else {
                        errorMessage = "Failed to submit task (HTTP \(httpResponse.statusCode))"
                    }
                    onCompletion?(false)
                }

                isSubmittingTask = false
                isLoading = false
            } catch {
                errorMessage = error.localizedDescription
                isSubmittingTask = false
                isLoading = false
                onCompletion?(false)
            }
        }
    }

    func pauseTask(_ taskId: String) {
        Task { @MainActor in
            errorMessage = nil

            guard let baseURL = baseURL else {
                errorMessage = "Server URL not configured"
                return
            }

            do {
                let url = baseURL.appendingPathComponent("api/tasks/\(taskId)/pause")
                var request = URLRequest(url: url)
                request.httpMethod = "POST"
                request.setValue("application/json", forHTTPHeaderField: "Accept")

                let (_, response) = try await URLSession.shared.data(for: request)

                guard let httpResponse = response as? HTTPURLResponse,
                      (200...299).contains(httpResponse.statusCode) else {
                    errorMessage = "Failed to pause task"
                    return
                }

                updateTaskStatus(taskId: taskId, status: "paused")
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }

    func resumeTask(_ taskId: String) {
        Task { @MainActor in
            errorMessage = nil

            guard let baseURL = baseURL else {
                errorMessage = "Server URL not configured"
                return
            }

            do {
                let url = baseURL.appendingPathComponent("api/tasks/\(taskId)/resume")
                var request = URLRequest(url: url)
                request.httpMethod = "POST"
                request.setValue("application/json", forHTTPHeaderField: "Accept")

                let (_, response) = try await URLSession.shared.data(for: request)

                guard let httpResponse = response as? HTTPURLResponse,
                      (200...299).contains(httpResponse.statusCode) else {
                    errorMessage = "Failed to resume task"
                    return
                }

                updateTaskStatus(taskId: taskId, status: "running")
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }

    func cancelTask(_ taskId: String) {
        Task { @MainActor in
            errorMessage = nil

            guard let baseURL = baseURL else {
                errorMessage = "Server URL not configured"
                return
            }

            do {
                let url = baseURL.appendingPathComponent("api/tasks/\(taskId)/cancel")
                var request = URLRequest(url: url)
                request.httpMethod = "POST"
                request.setValue("application/json", forHTTPHeaderField: "Accept")

                let (_, response) = try await URLSession.shared.data(for: request)

                guard let httpResponse = response as? HTTPURLResponse,
                      (200...299).contains(httpResponse.statusCode) else {
                    errorMessage = "Failed to cancel task"
                    return
                }

                stopSSE()
                updateTaskStatus(taskId: taskId, status: "cancelled")
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }

    // Restore a task from persistence through the current task API.
    func restoreTask(_ taskId: String) {
        Task { @MainActor in
            errorMessage = nil

            guard let baseURL = baseURL else {
                errorMessage = "Server URL not configured"
                return
            }

            do {
                let url = baseURL.appendingPathComponent("api/tasks/\(taskId)/restore")
                var request = URLRequest(url: url)
                request.httpMethod = "POST"
                request.setValue("application/json", forHTTPHeaderField: "Accept")

                let (data, response) = try await URLSession.shared.data(for: request)

                guard let httpResponse = response as? HTTPURLResponse else {
                    errorMessage = "Invalid response"
                    return
                }

                if httpResponse.statusCode == 409 {
                    errorMessage = "Another task is already running. Only one task can be active at a time."
                    return
                }

                guard (200...299).contains(httpResponse.statusCode) else {
                    errorMessage = "Failed to restore task"
                    return
                }

                let decoder = JSONDecoder()
                let restoredTask = try decoder.decode(TaskDetail.self, from: data)

                selectedTask = restoredTask
                viewMode = .detail
                reconnectAttempts = 0
                startSSE(for: taskId)
                startDetailPolling(for: taskId)
                loadTasks()
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }

    func enterCreateMode() {
        guard !isOrchestratorPluginUnavailable else {
            errorMessage = orchestratorPluginUnavailableMessage
            viewMode = .empty
            return
        }
        viewMode = .createForm
        selectedTask = nil
        clearGoalContract()
        stopSSE()
    }

    func enterWorkflowPicker() {
        errorMessage = nil
        selectedTask = nil
        clearGoalContract()
        viewMode = .empty
        stopSSE()
    }

    func cancelCreate() {
        errorMessage = nil
        isLoading = false
        if selectedTask != nil {
            viewMode = .detail
        } else {
            viewMode = .empty
        }
    }

    private func startSSE(for taskId: String) {
        guard let baseURL = baseURL else { return }

        sseTask = Task { @MainActor [weak self] in
            guard let self = self else { return }

            let url = baseURL.appendingPathComponent("api/tasks/\(taskId)/stream")
            var request = URLRequest(url: url)
            request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
            request.setValue("no-cache", forHTTPHeaderField: "Cache-Control")
            request.setValue("no", forHTTPHeaderField: "X-Accel-Buffering")

            do {
                let (bytes, response) = try await URLSession.shared.bytes(for: request)

                guard let httpResponse = response as? HTTPURLResponse,
                      (200...299).contains(httpResponse.statusCode) else {
                    self.handleSSEError(taskId: taskId)
                    return
                }

                var eventData = Data()

                for try await byte in bytes {
                    if byte == 10 {
                        let line = String(data: eventData, encoding: .utf8) ?? ""
                        eventData = Data()

                        if line.hasPrefix("id:") {
                            continue
                        } else if line.hasPrefix("data:") {
                            let jsonString = String(line.dropFirst(5)).trimmingCharacters(in: .whitespaces)
                            if let jsonData = jsonString.data(using: .utf8) {
                                do {
                                    let decoder = JSONDecoder()
                                    let event = try decoder.decode(ProgressEvent.self, from: jsonData)
                                    self.handleProgressEvent(event, taskId: taskId)
                                } catch {
                                    print("Failed to decode SSE event: \(error)")
                                }
                            }
                        }
                    } else if byte != 13 {
                        eventData.append(byte)
                    }
                }
            } catch {
                self.handleSSEError(taskId: taskId)
            }
        }
    }

    private func handleSSEError(taskId: String) {
        guard reconnectAttempts < maxReconnectAttempts else {
            print("Max SSE reconnect attempts reached for task \(taskId), starting polling fallback")
            startPollingFallback(for: taskId)
            return
        }

        reconnectAttempts += 1
        print("SSE disconnected for task \(taskId), reconnecting (attempt \(reconnectAttempts)/\(maxReconnectAttempts))...")

        Task { @MainActor in
            try? await Task.sleep(nanoseconds: reconnectDelay)
            startSSE(for: taskId)
        }
    }

    @MainActor
    private func handleProgressEvent(_ event: ProgressEvent, taskId: String) {
        guard var task = selectedTask, task.taskId == taskId else { return }

        switch event {
        case .taskCompleted:
            if let index = tasks.firstIndex(where: { $0.taskId == taskId }) {
                let counts = businessSubtaskProgress(in: task.waves.flatMap { $0.subtasks })
                tasks[index] = TaskSummary(
                    taskId: taskId,
                    description: task.description,
                    status: "completed",
                    progress: 1.0,
                    completedCount: counts.total,
                    totalCount: counts.total,
                    projectDir: task.projectDir,
                    ownerAgent: task.ownerAgent,
                    deliveryMode: task.deliveryMode,
                    externalTask: task.externalTask
                )
            }
            updateSelectedTaskStatus(taskId: taskId, status: "completed")
            Task { @MainActor [weak self] in
                _ = await self?.refreshSelectedTaskDetail(taskId: taskId)
            }
            stopSSE()

        case .taskFailed:
            if let index = tasks.firstIndex(where: { $0.taskId == taskId }) {
                let counts = businessSubtaskProgress(in: task.waves.flatMap { $0.subtasks })
                tasks[index] = TaskSummary(
                    taskId: taskId,
                    description: task.description,
                    status: "failed",
                    progress: tasks[index].progress,
                    completedCount: counts.completed,
                    totalCount: counts.total,
                    projectDir: task.projectDir,
                    ownerAgent: task.ownerAgent,
                    deliveryMode: task.deliveryMode,
                    externalTask: task.externalTask
                )
            }
            updateSelectedTaskStatus(taskId: taskId, status: "failed")
            Task { @MainActor [weak self] in
                _ = await self?.refreshSelectedTaskDetail(taskId: taskId)
            }
            stopSSE()

        case .taskCompletedWithFailures:
            if let index = tasks.firstIndex(where: { $0.taskId == taskId }) {
                let counts = businessSubtaskProgress(in: task.waves.flatMap { $0.subtasks })
                tasks[index] = TaskSummary(
                    taskId: taskId,
                    description: task.description,
                    status: "completed_with_failures",
                    progress: 1.0,
                    completedCount: counts.completed,
                    totalCount: counts.total,
                    projectDir: task.projectDir,
                    ownerAgent: task.ownerAgent,
                    deliveryMode: task.deliveryMode,
                    externalTask: task.externalTask
                )
            }
            updateSelectedTaskStatus(taskId: taskId, status: "completed_with_failures")
            Task { @MainActor [weak self] in
                _ = await self?.refreshSelectedTaskDetail(taskId: taskId)
            }
            stopSSE()

        case .taskStatusChanged(let update):
            let updatedTask = task.replacing(
                status: update.status,
                subtasks: update.subtasks,
                waves: update.waves,
                ownerSessionId: update.ownerSessionId,
                lastOwnerDecision: update.lastOwnerDecision,
                qualityHealth: update.qualityHealth,
                deliveryReport: update.deliveryReport,
                remoteExecution: update.remoteExecution
            )
            selectedTask = updatedTask
            task = updatedTask

            if let index = tasks.firstIndex(where: { $0.taskId == taskId }) {
                tasks[index] = TaskSummary(
                    taskId: taskId,
                    description: task.description,
                    status: update.status,
                    progress: update.progress,
                    completedCount: update.completedCount,
                    totalCount: update.totalCount,
                    projectDir: task.projectDir,
                    ownerAgent: task.ownerAgent,
                    deliveryMode: task.deliveryMode,
                    externalTask: task.externalTask
                )
            }

        case .subtaskUpdated(let update):
            // With persistence, SSE includes full description and agentId for all subtasks.
            // If subtask is not in current waves (e.g., new fix subtask), we need to add it.
            var updatedWaves = task.waves
            var subtaskFound = false

            for (waveIndex, wave) in updatedWaves.enumerated() {
                if let subtaskIndex = wave.subtasks.firstIndex(where: { $0.subtaskId == update.subtaskId }) {
                    let subtask = wave.subtasks[subtaskIndex]

                    let updatedSubtask = SubtaskDetail(
                        subtaskId: subtask.subtaskId,
                        description: update.description ?? subtask.description,
                        agentId: update.agentId ?? subtask.agentId,
                        status: update.status ?? subtask.status,
                        progress: update.progress ?? subtask.progress,
                        outputFile: update.outputFile ?? subtask.outputFile,
                        duration: update.duration ?? subtask.duration,
                        errorMessage: update.errorMessage ?? subtask.errorMessage,
                        fixPlan: update.fixPlan ?? subtask.fixPlan,
                        waveNumber: subtask.waveNumber,
                        ownerDecision: subtask.ownerDecision,
                        waitingOnDependencies: update.waitingOnDependencies ?? subtask.waitingOnDependencies,
                        blockedReason: update.blockedReason ?? subtask.blockedReason,
                        runningForSeconds: update.runningForSeconds ?? subtask.runningForSeconds
                    )

                    let newSubtasks = wave.subtasks.enumerated().map { (idx, st) -> SubtaskDetail in
                        idx == subtaskIndex ? updatedSubtask : st
                    }
                    let updatedWave = WaveDetail(
                        waveId: wave.waveId,
                        waveNumber: wave.waveNumber,
                        subtasks: newSubtasks,
                        status: wave.status,
                        isBlocked: wave.isBlocked,
                        governanceStatus: wave.governanceStatus,
                        blockedByWave: wave.blockedByWave,
                        isRevalidating: wave.isRevalidating,
                        ownerDecision: wave.ownerDecision,
                        fixRounds: wave.fixRounds
                    )
                    updatedWaves[waveIndex] = updatedWave
                    subtaskFound = true
                    break
                }
            }

            // If subtask not found in existing waves (new fix subtask), add it to appropriate wave
            if !subtaskFound, let waveNumber = update.waveNumber {
                if let waveIndex = updatedWaves.firstIndex(where: { $0.waveNumber == waveNumber }) {
                    let newSubtask = SubtaskDetail(
                        subtaskId: update.subtaskId,
                        description: update.description ?? "Fix subtask",
                        agentId: update.agentId ?? "unknown",
                        status: update.status ?? "pending",
                        progress: update.progress ?? 0.0,
                        outputFile: update.outputFile,
                        duration: update.duration,
                        errorMessage: update.errorMessage,
                        fixPlan: update.fixPlan,
                        waveNumber: waveNumber,
                        ownerDecision: nil,
                        waitingOnDependencies: update.waitingOnDependencies ?? [],
                        blockedReason: update.blockedReason,
                        runningForSeconds: update.runningForSeconds
                    )
                    let wave = updatedWaves[waveIndex]
                    let newSubtasks = wave.subtasks + [newSubtask]
                    let updatedWave = WaveDetail(
                        waveId: wave.waveId,
                        waveNumber: wave.waveNumber,
                        subtasks: newSubtasks,
                        status: wave.status,
                        isBlocked: wave.isBlocked,
                        governanceStatus: wave.governanceStatus,
                        blockedByWave: wave.blockedByWave,
                        isRevalidating: wave.isRevalidating,
                        ownerDecision: wave.ownerDecision,
                        fixRounds: wave.fixRounds
                    )
                    updatedWaves[waveIndex] = updatedWave
                }
            }

            let counts = businessSubtaskProgress(in: updatedWaves.flatMap { $0.subtasks })
            let hasRunning = updatedWaves.flatMap { $0.subtasks }.contains { $0.status == "running" }
            let progress = counts.total > 0 ? Double(counts.completed) / Double(counts.total) : 0

            task = task.replacing(
                status: hasRunning ? "running" : task.status,
                waves: updatedWaves
            )

            selectedTask = task

            if let index = tasks.firstIndex(where: { $0.taskId == taskId }) {
                tasks[index] = TaskSummary(
                    taskId: taskId,
                    description: task.description,
                    status: hasRunning ? "running" : tasks[index].status,
                    progress: progress,
                    completedCount: counts.completed,
                    totalCount: counts.total,
                    projectDir: task.projectDir,
                    ownerAgent: task.ownerAgent,
                    deliveryMode: task.deliveryMode,
                    externalTask: task.externalTask
                )
            }

        case .waveUpdated(let update):
            var updatedWaves = task.waves

            if let waveIndex = updatedWaves.firstIndex(where: { $0.waveId == update.waveId }) {
                let wave = updatedWaves[waveIndex]

                let updatedWave = WaveDetail(
                    waveId: wave.waveId,
                    waveNumber: wave.waveNumber,
                    subtasks: wave.subtasks,
                    status: update.status ?? wave.status,
                    isBlocked: update.isBlocked ?? wave.isBlocked,
                    governanceStatus: update.governanceStatus ?? wave.governanceStatus,
                    blockedByWave: update.blockedByWave ?? wave.blockedByWave,
                    isRevalidating: update.isRevalidating ?? wave.isRevalidating,
                    ownerDecision: update.ownerDecision ?? wave.ownerDecision,
                    fixRounds: update.fixRounds ?? wave.fixRounds
                )

                updatedWaves[waveIndex] = updatedWave

                task = task.replacing(waves: updatedWaves)

                selectedTask = task
            }

        case .artifactGenerated(let info):
            let newArtifact = Artifact(
                id: info.id,
                fileName: info.fileName,
                filePath: info.filePath,
                fileSize: info.fileSize
            )

            var updatedArtifacts = task.artifacts
            if !updatedArtifacts.contains(where: { $0.id == info.id }) {
                updatedArtifacts.append(newArtifact)
            }

            task = task.replacing(artifacts: updatedArtifacts)

            selectedTask = task

        default:
            break
        }
    }

    private func startPollingFallback(for taskId: String) {
        pollingTask?.cancel()
        pollingTask = Task { @MainActor [weak self] in
            guard let self = self else { return }
            while !Task.isCancelled {
                guard let baseURL = self.baseURL else { break }
                do {
                    let url = baseURL.appendingPathComponent("api/tasks/\(taskId)/status")
                    let (data, _) = try await URLSession.shared.data(from: url)
                    let statusData = try JSONDecoder().decode(PollStatusResponse.self, from: data)

                    if let currentTask = self.selectedTask, currentTask.taskId == taskId {
                        self.updateTaskFromPollResponse(currentTask, statusData)

                        if statusData.status == "running" || statusData.status == "pending" || statusData.status == "decomposing" {
                            self.reconnectAttempts = 0
                            self.startSSE(for: taskId)
                            return
                        }

                        let terminalStatuses = ["completed", "completed_with_failures", "failed", "cancelled"]
                        if terminalStatuses.contains(statusData.status) {
                            self.startDetailPolling(for: taskId)
                            return
                        }
                    }
                } catch {
                }

                try? await Task.sleep(nanoseconds: 10_000_000_000)
            }
        }
    }

    private func startDetailPolling(for taskId: String) {
        detailPollingTask?.cancel()
        detailPollingTask = Task { @MainActor [weak self] in
            guard let self = self else { return }
            var terminalStablePolls = 0

            while !Task.isCancelled {
                guard let currentTask = self.selectedTask, currentTask.taskId == taskId else {
                    return
                }

                let refreshedTask = await self.refreshSelectedTaskDetail(taskId: taskId)
                let latestTask = refreshedTask ?? currentTask
                if self.isTerminalStatus(latestTask.status) {
                    terminalStablePolls += 1
                } else {
                    terminalStablePolls = 0
                }

                if !self.shouldContinueDetailPolling(latestTask, terminalStablePolls: terminalStablePolls) {
                    return
                }

                try? await Task.sleep(nanoseconds: self.detailPollingInterval)
            }
        }
    }

    private func shouldContinueDetailPolling(_ task: TaskDetail, terminalStablePolls: Int) -> Bool {
        TaskOrchestrationStateReducers.shouldContinueDetailPolling(
            task,
            terminalStablePolls: terminalStablePolls,
            settleLimit: terminalSettlePollLimit
        )
    }

    @MainActor
    private func refreshSelectedTaskDetail(taskId: String) async -> TaskDetail? {
        guard let baseURL = baseURL else { return nil }

        do {
            let url = baseURL.appendingPathComponent("api/tasks/\(taskId)")
            var request = URLRequest(url: url)
            request.httpMethod = "GET"
            request.setValue("application/json", forHTTPHeaderField: "Accept")

            let (data, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse,
                  (200...299).contains(httpResponse.statusCode) else {
                return nil
            }

            let taskDetail = try JSONDecoder().decode(TaskDetail.self, from: data)
            guard selectedTask?.taskId == taskId else { return taskDetail }

            selectedTask = taskDetail
            upsertTaskSummary(from: taskDetail)
            loadGoalContract(taskId)
            return taskDetail
        } catch {
            print("Failed to refresh selected task detail for \(taskId): \(error)")
            return nil
        }
    }

    func clearGoalContract() {
        goalRequestGeneration += 1
        selectedGoalContract = nil
        isLoadingGoalContract = false
        goalContractError = nil
        goalTaskState = .legacyEmpty
    }

    @discardableResult
    func loadGoalContract(_ taskId: String) -> Task<Void, Never> {
        Task { @MainActor in
            await performGoalContractLoad(taskId)
        }
    }

    @MainActor
    private func performGoalContractLoad(_ taskId: String) async {
        goalRequestGeneration += 1
        let generation = goalRequestGeneration
        selectedGoalContract = nil
        isLoadingGoalContract = true
        goalContractError = nil
        goalTaskState = .loading

        guard let baseURL else {
            applyGoalContractFailure("Goal details are unavailable.", generation: generation)
            return
        }

        do {
            let request = Self.goalRequest(baseURL: baseURL, taskId: taskId)
            let (data, response) = try await requestData(request)
            guard generation == goalRequestGeneration else { return }
            guard let httpResponse = response as? HTTPURLResponse else {
                throw URLError(.badServerResponse)
            }
            if httpResponse.statusCode == 404 {
                selectedGoalContract = nil
                isLoadingGoalContract = false
                goalTaskState = .legacyEmpty
                return
            }
            guard (200...299).contains(httpResponse.statusCode) else {
                throw URLError(.badServerResponse)
            }
            let envelope = try JSONDecoder().decode(GoalContractEnvelope.self, from: data)
            guard envelope.contract.taskId == taskId,
                  envelope.projection.taskId == taskId,
                  generation == goalRequestGeneration else { return }
            selectedGoalContract = envelope
            isLoadingGoalContract = false
            goalTaskState = GoalProjectionReducer.reduce(envelope, loading: false, error: nil)
        } catch {
            guard generation == goalRequestGeneration else { return }
            applyGoalContractFailure("Goal details are unavailable.", generation: generation)
        }
    }

    @discardableResult
    func decideGoalProposal(
        taskId: String,
        proposalId: String,
        decision: String,
        expectedRevision: Int,
        operationIndexes: [Int] = [],
        approverId: String = "human:local",
        idempotencyKey: String = UUID().uuidString
    ) -> Task<Void, Never> {
        Task { @MainActor in
            let body = GoalProposalDecisionRequest(
                decision: decision,
                expectedRevision: expectedRevision,
                operationIndexes: operationIndexes,
                approverId: approverId,
                idempotencyKey: idempotencyKey
            )
            await performGoalMutation(
                path: "api/tasks/\(taskId)/goal/proposals/\(proposalId)/decision",
                taskId: taskId,
                body: body
            )
        }
    }

    @discardableResult
    func requestGoalRevalidation(
        taskId: String,
        expectedRevision: Int,
        criterionIds: [String],
        reason: String,
        idempotencyKey: String = UUID().uuidString
    ) -> Task<Void, Never> {
        Task { @MainActor in
            let body = GoalRevalidationRequest(
                expectedRevision: expectedRevision,
                criterionIds: criterionIds,
                reason: reason,
                idempotencyKey: idempotencyKey
            )
            await performGoalMutation(
                path: "api/tasks/\(taskId)/goal/revalidate",
                taskId: taskId,
                body: body
            )
        }
    }

    @MainActor
    private func performGoalMutation<Body: Encodable>(path: String, taskId: String, body: Body) async {
        guard let baseURL else {
            goalContractError = "Goal action is unavailable."
            goalTaskState = .error("Goal action is unavailable.")
            return
        }
        do {
            var request = URLRequest(url: baseURL.appendingPathComponent(path))
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue("application/json", forHTTPHeaderField: "Accept")
            request.httpBody = try JSONEncoder().encode(body)
            let (data, response) = try await requestData(request)
            guard let httpResponse = response as? HTTPURLResponse,
                  (200...299).contains(httpResponse.statusCode) else {
                let message = Self.backendErrorMessage(from: data) ?? "Goal action was rejected."
                throw GoalActionError.rejected(message)
            }
            await performGoalContractLoad(taskId)
        } catch {
            let message: String
            if case GoalActionError.rejected(let detail) = error {
                message = detail
            } else {
                message = "Goal action is unavailable."
            }
            goalContractError = message
            goalTaskState = .error(message)
        }
    }

    private static func goalRequest(baseURL: URL, taskId: String) -> URLRequest {
        var request = URLRequest(url: baseURL.appendingPathComponent("api/tasks/\(taskId)/goal"))
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        return request
    }

    @MainActor
    private func applyGoalContractFailure(_ message: String, generation: Int) {
        guard generation == goalRequestGeneration else { return }
        isLoadingGoalContract = false
        goalContractError = message
        goalTaskState = GoalProjectionReducer.reduce(nil, loading: false, error: message)
    }

    private func upsertTaskSummary(from task: TaskDetail) {
        let summary = TaskOrchestrationStateReducers.taskSummary(from: task)

        if let index = tasks.firstIndex(where: { $0.taskId == task.taskId }) {
            tasks[index] = summary
        } else {
            tasks.insert(summary, at: 0)
        }
    }

    private func isTerminalStatus(_ status: String) -> Bool {
        TaskOrchestrationStateReducers.isTerminalStatus(status)
    }

    private func businessSubtaskProgress(in subtasks: [SubtaskDetail]) -> (completed: Int, total: Int) {
        let counts = TaskOrchestrationStateReducers.businessProgress(in: subtasks)
        return (completed: counts.completed, total: counts.total)
    }

    private func businessSubtaskProgress(in subtasks: [PollSubtaskStatus]) -> (completed: Int, total: Int) {
        let counts = TaskOrchestrationStateReducers.businessProgress(in: subtasks)
        return (completed: counts.completed, total: counts.total)
    }

    @MainActor
    private func updateTaskFromPollResponse(_ task: TaskDetail, _ pollData: PollStatusResponse) {
        let result = TaskOrchestrationStateReducers.mergedPollResponse(task: task, pollData: pollData)

        if selectedTask?.taskId == task.taskId {
            selectedTask = result.detail
        }

        if let index = tasks.firstIndex(where: { $0.taskId == task.taskId }) {
            tasks[index] = result.summary
        }
    }

    /// P0-5: Initial polling after task submission, checking every 2s for decomposing exit.
    /// Polls for up to 30 seconds (15 attempts), covering cases where the task switches
    /// to running before the SSE connection is established.
    private func startInitialPolling(for taskId: String) {
        initialPollingTask?.cancel()
        initialPollingTask = Task { @MainActor [weak self] in
            guard let self = self, let baseURL = self.baseURL else { return }
            for _ in 0..<15 {
                if Task.isCancelled { return }
                // Stop if SSE already pushed a non-decomposing status.
                if let task = self.selectedTask, task.taskId == taskId, task.status != "decomposing" {
                    return
                }
                do {
                    let url = baseURL.appendingPathComponent("api/tasks/\(taskId)")
                    let (data, _) = try await URLSession.shared.data(from: url)
                    let taskDetail = try JSONDecoder().decode(TaskDetail.self, from: data)
                    if taskDetail.status != "decomposing" {
                        // The task left decomposing; update selectedTask to trigger DAG display.
                        self.selectedTask = taskDetail
                        self.upsertTaskSummary(from: taskDetail)
                        return
                    }
                } catch {
                    // Ignore transient polling errors.
                }
                try? await Task.sleep(nanoseconds: 2_000_000_000)  // 2s
            }
        }
    }

    private func stopSSE() {
        sseTask?.cancel()
        sseTask = nil
        pollingTask?.cancel()
        pollingTask = nil
        initialPollingTask?.cancel()
        initialPollingTask = nil
        detailPollingTask?.cancel()
        detailPollingTask = nil
        reconnectAttempts = 0
    }

    private func updateSelectedTaskStatus(taskId: String, status: String) {
        guard let task = selectedTask, task.taskId == taskId else { return }
        selectedTask = task.replacing(status: status)
    }

    private func updateTaskStatus(taskId: String, status: String) {
        if let task = selectedTask, task.taskId == taskId {
            selectedTask = task.replacing(status: status)
        }

        if let index = tasks.firstIndex(where: { $0.taskId == taskId }) {
            let oldTask = tasks[index]
            tasks[index] = TaskSummary(
                taskId: taskId,
                description: oldTask.description,
                status: status,
                progress: oldTask.progress,
                completedCount: oldTask.completedCount,
                totalCount: oldTask.totalCount,
                projectDir: oldTask.projectDir,
                ownerAgent: oldTask.ownerAgent,
                deliveryMode: oldTask.deliveryMode,
                externalTask: oldTask.externalTask
            )
        }
    }

    deinit {
        stopSSE()
    }
}
