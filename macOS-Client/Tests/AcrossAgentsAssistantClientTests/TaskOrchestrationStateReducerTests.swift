import Testing
@testable import AcrossAgentsAssistantClient

struct TaskOrchestrationStateReducerTests {
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
