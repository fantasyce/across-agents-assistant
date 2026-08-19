import Foundation
import Testing
@testable import AcrossAgentsAssistantClient

struct TaskOrchestrationStateReducerTests {
    @Test @MainActor
    func trajectoryFailureLeavesEvidenceStateUnchanged() async throws {
        let exportURL = URL(fileURLWithPath: "/tmp/existing-evidence.json")
        let viewModel = TaskOrchestrationViewModel(
            requestData: { _ in throw URLError(.cannotConnectToHost) },
            trajectoryExportsDirectory: FileManager.default.temporaryDirectory
        )
        viewModel.selectedEvidenceBundle = try makeEvidenceBundle()
        viewModel.taskEvidenceError = "existing evidence state"
        viewModel.exportedEvidenceBundleURL = exportURL

        await viewModel.loadTaskExecutionTrajectory("task-public").value

        #expect(viewModel.selectedEvidenceBundle?.taskId == "task-public")
        #expect(viewModel.taskEvidenceError == "existing evidence state")
        #expect(viewModel.exportedEvidenceBundleURL == exportURL)
        #expect(viewModel.executionTrajectoryError == "Execution trajectory is unavailable.")
        #expect(viewModel.selectedExecutionTrajectory == nil)
        #expect(!viewModel.isLoadingExecutionTrajectory)
    }

    @Test @MainActor
    func closingEvidenceClearsIndependentTrajectoryStateAndFencesLateResults() async throws {
        let gate = AsyncDataGate()
        let viewModel = TaskOrchestrationViewModel(
            requestData: { request in try await gate.response(for: request) },
            trajectoryExportsDirectory: FileManager.default.temporaryDirectory
        )
        viewModel.selectedEvidenceBundle = try makeEvidenceBundle()
        let request = viewModel.loadTaskExecutionTrajectory("task-public")
        await gate.waitUntilRequested()

        viewModel.closeEvidenceBundle()
        await gate.release(data: Self.makeTrajectoryData(taskId: "task-public", offset: 0, nextOffset: nil))
        await request.value

        #expect(viewModel.selectedEvidenceBundle == nil)
        #expect(viewModel.selectedExecutionTrajectory == nil)
        #expect(viewModel.executionTrajectoryError == nil)
        #expect(viewModel.exportedExecutionTrajectoryURL == nil)
        #expect(!viewModel.isLoadingExecutionTrajectory)
    }

    @Test @MainActor
    func nextTrajectoryPageUsesServerProvidedOffset() async throws {
        let requests = RequestRecorder()
        let viewModel = TaskOrchestrationViewModel(
            requestData: { request in
                let query = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.queryItems ?? []
                let offset = Int(query.first(where: { $0.name == "offset" })?.value ?? "0") ?? 0
                await requests.append(request.url!)
                return Self.httpResponse(
                    for: request,
                    data: Self.makeTrajectoryData(
                        taskId: "task-public",
                        offset: offset,
                        nextOffset: offset == 0 ? 7 : nil
                    )
                )
            },
            trajectoryExportsDirectory: FileManager.default.temporaryDirectory
        )

        await viewModel.loadTaskExecutionTrajectory("task-public", offset: 0, limit: 2).value
        await viewModel.loadNextTaskExecutionTrajectoryPage("task-public").value

        let urls = await requests.values
        #expect(urls.count == 2)
        #expect(URLComponents(url: urls[1], resolvingAgainstBaseURL: false)?.queryItems?.first(where: { $0.name == "offset" })?.value == "7")
        #expect(viewModel.selectedExecutionTrajectory?.page.offset == 7)
    }

    @Test @MainActor
    func trajectoryExportUsesDecodedPublicModelWithoutRefetching() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("trajectory-export-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let requests = RequestRecorder()
        let viewModel = TaskOrchestrationViewModel(
            requestData: { request in
                await requests.append(request.url!)
                return Self.httpResponse(
                    for: request,
                    data: Self.makeTrajectoryData(taskId: "task/private", offset: 0, nextOffset: nil)
                )
            },
            trajectoryExportsDirectory: directory
        )

        await viewModel.loadTaskExecutionTrajectory("task/private", limit: 2).value
        await viewModel.exportTaskExecutionTrajectory("task/private").value

        let requestCount = await requests.values.count
        #expect(requestCount == 1)
        let exportURL = try #require(viewModel.exportedExecutionTrajectoryURL)
        #expect(exportURL.lastPathComponent == "task-private-execution-trajectory.json")
        let exported = try Data(contentsOf: exportURL)
        let trajectory = try #require(viewModel.selectedExecutionTrajectory)
        #expect(exported == (try trajectory.prettyPublicJSON()))
        #expect(!String(decoding: exported, as: UTF8.self).contains("private_payload"))
    }

    @Test @MainActor
    func evidencePresentationDoesNotWaitForTrajectoryLoading() async throws {
        let gate = EvidenceThenTrajectoryGate(evidence: makeEvidenceBundleData())
        let viewModel = TaskOrchestrationViewModel(
            requestData: { request in try await gate.response(for: request) },
            trajectoryExportsDirectory: FileManager.default.temporaryDirectory
        )

        let evidenceLoad = viewModel.loadTaskEvidenceBundle("task-public")
        await gate.waitUntilTrajectoryRequested()

        #expect(viewModel.selectedEvidenceBundle?.taskId == "task-public")
        #expect(!viewModel.isLoadingTaskEvidence)
        #expect(viewModel.isLoadingExecutionTrajectory)
        #expect(viewModel.taskEvidenceError == nil)

        await gate.releaseTrajectory(
            data: Self.makeTrajectoryData(taskId: "task-public", offset: 0, nextOffset: nil, limit: 200)
        )
        await evidenceLoad.value
        for _ in 0..<100 where viewModel.selectedExecutionTrajectory == nil {
            await Task.yield()
        }
        #expect(viewModel.selectedExecutionTrajectory?.taskId == "task-public")
    }

    @Test func businessProgressIgnoresLifecycleAndRepairSubtasks() {
        let subtasks = [
            makeSubtask("build-api", status: "completed"),
            makeSubtask("worker-job", status: "completed_with_failures"),
            makeSubtask("task-decompose", status: "completed"),
            makeSubtask("st-quality-required", status: "completed"),
            makeSubtask("build-api-integration-fix-1", status: "completed"),
            makeSubtask("build-ui-v2", status: "completed"),
            makeSubtask("build-ui", status: "running")
        ]

        let counts = TaskOrchestrationStateReducers.businessProgress(in: subtasks)

        #expect(counts.completed == 2)
        #expect(counts.total == 3)
    }

    @Test func pollResponseMergeBuildsUpdatedDetailAndSummary() {
        let task = TaskOrchestrationTaskDetail(
            taskId: "task-1",
            description: "Ship release",
            status: "running",
            externalTask: true,
            taskTypes: ["functional", "artifact"],
            deliveryMode: "composite",
            hasOwnerDeliveryContract: true,
            ownerAgent: "claude",
            allowedSubtaskAgents: ["claude", "codex"],
            projectDir: "/tmp/project",
            subtasks: [makeSubtask("build-api", outputFile: "api/server.mjs")],
            waves: [
                TaskOrchestrationWaveDetail(
                    waveId: "wave-1",
                    waveNumber: 1,
                    subtasks: [makeSubtask("build-api", outputFile: "api/server.mjs")],
                    status: "running",
                    isBlocked: false,
                    governanceStatus: nil,
                    blockedByWave: nil,
                    isRevalidating: false,
                    ownerDecision: nil,
                    fixRounds: nil
                )
            ],
            artifacts: [],
            artifactVersions: nil,
            ownerSessionId: nil,
            lastOwnerDecision: nil,
            error: nil,
            hasRequirementManifest: true
        )
        let poll = TaskOrchestrationPollStatusResponse(
            status: "completed",
            progress: 1.0,
            subtasks: [
                TaskOrchestrationPollSubtaskStatus(
                    subtask_id: "build-api",
                    description: "Build API",
                    agent_id: "claude",
                    status: "completed",
                    progress: 1.0,
                    wave_number: 1,
                    waiting_on_dependencies: [],
                    blocked_reason: nil,
                    running_for_seconds: nil
                ),
                TaskOrchestrationPollSubtaskStatus(
                    subtask_id: "st-quality-required",
                    description: "Quality gate",
                    agent_id: "demo",
                    status: "completed",
                    progress: 1.0,
                    wave_number: 1,
                    waiting_on_dependencies: [],
                    blocked_reason: nil,
                    running_for_seconds: nil
                )
            ],
            waves: [
                TaskOrchestrationPollWaveStatus(
                    wave_id: "wave-1",
                    wave_number: 1,
                    status: "completed",
                    is_blocked: nil,
                    governance_status: "passed",
                    blocked_by_wave: nil,
                    is_revalidating: nil,
                    owner_decision: nil
                )
            ]
        )

        let result = TaskOrchestrationStateReducers.mergedPollResponse(task: task, pollData: poll)

        #expect(result.detail.status == "completed")
        #expect(result.detail.subtasks[0].outputFile == "api/server.mjs")
        #expect(result.detail.waves[0].governanceStatus == "passed")
        #expect(result.summary.completedCount == 1)
        #expect(result.summary.totalCount == 1)
        #expect(result.summary.ownerAgent == "claude")
        #expect(result.summary.externalTask)
    }

    @Test func userPhaseCompressesTechnicalStatesIntoFourUnderstandableSteps() {
        #expect(TaskOrchestrationStateReducers.userPhase(for: makeTask(status: "decomposing")) == .understanding)
        #expect(TaskOrchestrationStateReducers.userPhase(for: makeTask(
            status: "running",
            subtasks: [makeSubtask("build-ui", status: "running")]
        )) == .working)
        #expect(TaskOrchestrationStateReducers.userPhase(for: makeTask(
            status: "running",
            subtasks: [
                makeSubtask("build-ui", status: "completed"),
                makeSubtask("st-quality-ui", status: "running"),
            ]
        )) == .checking)
        #expect(TaskOrchestrationStateReducers.userPhase(for: makeTask(status: "completed")) == .ready)
        #expect(TaskOrchestrationStateReducers.userPhase(for: makeTask(status: "completed_with_failures")) == .needsAttention)
        #expect(TaskOrchestrationStateReducers.userPhase(for: makeTask(status: "failed")) == .needsAttention)
    }

    private func makeTask(
        status: String,
        subtasks: [TaskOrchestrationSubtaskDetail] = []
    ) -> TaskOrchestrationTaskDetail {
        TaskOrchestrationTaskDetail(
            taskId: "phase-task",
            description: "Build and verify a feature",
            status: status,
            ownerAgent: "auto",
            allowedSubtaskAgents: [],
            projectDir: "/tmp/project",
            subtasks: subtasks,
            waves: [],
            artifacts: [],
            artifactVersions: nil,
            ownerSessionId: nil,
            lastOwnerDecision: nil,
            error: nil
        )
    }

    private func makeEvidenceBundle() throws -> TaskEvidenceBundle {
        try JSONDecoder().decode(TaskEvidenceBundle.self, from: makeEvidenceBundleData())
    }

    private func makeEvidenceBundleData() -> Data {
        Data(
            """
            {
              "schema_version": "1.0",
              "task_id": "task-public",
              "task_status": "completed",
              "benchmark": {
                "benchmark_id": "benchmark",
                "status": "passed",
                "summary": {
                  "scenario_count": 0,
                  "passed_scenarios": 0,
                  "failed_scenarios": 0,
                  "min_quality_score": 0,
                  "max_remediation_attempts": 0
                },
                "scenarios": []
              },
              "audit": {
                "read_only": true,
                "repair_or_resume_triggered": false,
                "secrets_redacted": true,
                "expected_files": [],
                "required_probes": []
              }
            }
            """.utf8
        )
    }

    private static func makeTrajectoryData(
        taskId: String,
        offset: Int,
        nextOffset: Int?,
        limit: Int = 2
    ) -> Data {
        let next = nextOffset.map(String.init) ?? "null"
        return Data(
            """
            {
              "schema_version": "across-execution-trajectory/1.0",
              "generated_at": 10.0,
              "task_id": "\(taskId)",
              "task_status": "completed",
              "source": "orchestrator_evidence",
              "summary": {
                "source_event_count": 1,
                "normalized_event_count": 1,
                "first_sequence": 1,
                "last_sequence": 1,
                "started_at": null,
                "completed_at": 10.0,
                "terminal_status": "completed"
              },
              "page": {
                "offset": \(offset),
                "limit": \(limit),
                "returned": 1,
                "total": 1,
                "next_offset": \(next),
                "has_more": \(nextOffset == nil ? "false" : "true")
              },
              "receipt": {
                "integrity_state": "missing",
                "digest_algorithm": "sha256",
                "verdict": "warning",
                "reason": "receipt_missing"
              },
              "items": [{
                "event_id": "event-\(offset)",
                "sequence": 1,
                "timestamp": 10.0,
                "event_type": "task.completed",
                "category": "task",
                "phase": "completed",
                "status": "succeeded",
                "title": "Task completed",
                "scope_kind": "task",
                "scope_id": "\(taskId)",
                "private_payload": "must-not-export"
              }],
              "audit": {
                "read_only": true,
                "mutations_triggered": false,
                "repair_or_resume_triggered": false,
                "secrets_redacted": true,
                "receipt_checked_before_redaction": true,
                "raw_payload_exposed": false,
                "event_integrity_state": "clean",
                "omitted_event_count": 0,
                "conflicting_duplicate_count": 0,
                "truncated": false
              }
            }
            """.utf8
        )
    }

    private static func httpResponse(for request: URLRequest, data: Data) -> (Data, URLResponse) {
        (
            data,
            HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
        )
    }

    private func makeSubtask(
        _ id: String,
        status: String = "running",
        outputFile: String? = nil
    ) -> TaskOrchestrationSubtaskDetail {
        TaskOrchestrationSubtaskDetail(
            subtaskId: id,
            description: "Subtask \(id)",
            agentId: "claude",
            status: status,
            progress: status == "completed" ? 1.0 : 0.5,
            outputFile: outputFile,
            duration: nil,
            errorMessage: nil,
            fixPlan: nil,
            waveNumber: 1,
            ownerDecision: nil,
            waitingOnDependencies: [],
            blockedReason: nil,
            runningForSeconds: nil
        )
    }
}

private actor RequestRecorder {
    private(set) var values: [URL] = []

    func append(_ url: URL) {
        values.append(url)
    }
}

private actor AsyncDataGate {
    private var request: URLRequest?
    private var responseContinuation: CheckedContinuation<(Data, URLResponse), Error>?
    private var requestWaiters: [CheckedContinuation<Void, Never>] = []

    func response(for request: URLRequest) async throws -> (Data, URLResponse) {
        self.request = request
        let waiters = requestWaiters
        requestWaiters.removeAll()
        waiters.forEach { $0.resume() }
        return try await withCheckedThrowingContinuation { continuation in
            responseContinuation = continuation
        }
    }

    func waitUntilRequested() async {
        if request != nil { return }
        await withCheckedContinuation { continuation in
            requestWaiters.append(continuation)
        }
    }

    func release(data: Data) {
        guard let request, let continuation = responseContinuation else {
            fatalError("AsyncDataGate released before a request was waiting")
        }
        responseContinuation = nil
        continuation.resume(
            returning: (
                data,
                HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            )
        )
    }
}

private actor EvidenceThenTrajectoryGate {
    private let evidence: Data
    private var trajectoryRequest: URLRequest?
    private var trajectoryContinuation: CheckedContinuation<(Data, URLResponse), Error>?
    private var requestWaiters: [CheckedContinuation<Void, Never>] = []

    init(evidence: Data) {
        self.evidence = evidence
    }

    func response(for request: URLRequest) async throws -> (Data, URLResponse) {
        if request.url?.path.hasSuffix("/evidence-bundle") == true {
            return (
                evidence,
                HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            )
        }
        trajectoryRequest = request
        let waiters = requestWaiters
        requestWaiters.removeAll()
        waiters.forEach { $0.resume() }
        return try await withCheckedThrowingContinuation { continuation in
            trajectoryContinuation = continuation
        }
    }

    func waitUntilTrajectoryRequested() async {
        if trajectoryRequest != nil { return }
        await withCheckedContinuation { continuation in
            requestWaiters.append(continuation)
        }
    }

    func releaseTrajectory(data: Data) {
        guard let request = trajectoryRequest, let continuation = trajectoryContinuation else {
            fatalError("Trajectory response released before request")
        }
        trajectoryContinuation = nil
        continuation.resume(
            returning: (
                data,
                HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            )
        )
    }
}
