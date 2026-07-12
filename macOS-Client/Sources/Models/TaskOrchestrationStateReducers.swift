import Foundation

struct TaskOrchestrationProgressCounts: Equatable {
    let completed: Int
    let total: Int
}

struct TaskOrchestrationPollMergeResult {
    let detail: TaskOrchestrationTaskDetail
    let summary: TaskOrchestrationTaskSummary
}

enum TaskOrchestrationUserPhase: Equatable {
    case understanding
    case working
    case checking
    case ready
    case needsAttention
}

enum TaskOrchestrationStateReducers {
    private static let terminalStatuses: Set<String> = [
        "completed",
        "completed_with_failures",
        "failed",
        "cancelled"
    ]

    static func isTerminalStatus(_ status: String) -> Bool {
        terminalStatuses.contains(status)
    }

    static func userPhase(for task: TaskOrchestrationTaskDetail) -> TaskOrchestrationUserPhase {
        if isTerminalStatus(task.status) {
            return isSuccessfulDelivery(task) ? .ready : .needsAttention
        }

        let businessSubtasks = task.subtasks.filter { isOriginalBusinessSubtaskId($0.subtaskId) }
        if ["created", "decomposing"].contains(task.status) || businessSubtasks.isEmpty {
            return .understanding
        }

        let hasActiveBusinessWork = businessSubtasks.contains {
            ["pending", "dispatched", "running", "paused"].contains($0.status)
        }
        if hasActiveBusinessWork { return .working }

        let hasQualityWork = task.subtasks.contains { $0.subtaskId.hasPrefix("st-quality-") }
            || task.waves.contains(where: \.isRevalidating)
            || task.qualityHealth?.orchestrationHealth == "recovering"
            || !(task.qualityHealth?.activeRemediationSubtasks.isEmpty ?? true)
            || !(task.deliveryReport?.nextAction?.isEmpty ?? true)
        return hasQualityWork ? .checking : .working
    }

    static func isSuccessfulDelivery(_ task: TaskOrchestrationTaskDetail) -> Bool {
        guard task.status == "completed" else { return false }
        let health = task.qualityHealth
        let report = task.deliveryReport
        let gate = (report?.qualityGate ?? health?.qualityGate ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        let blockingGates = Set(["failed", "failure", "blocked", "error", "partial", "inconsistent"])
        let artifactFailure = task.artifacts.contains {
            ["missing", "rejected", "failed", "cancelled"].contains(($0.status ?? "").lowercased())
        }
        return !blockingGates.contains(gate)
            && report?.qualityReport?.canComplete != false
            && (report?.missingRequired.isEmpty ?? true)
            && (report?.failedConstraints.isEmpty ?? true)
            && (health?.terminalInconsistencies.isEmpty ?? true)
            && (health?.activeRemediationSubtasks.isEmpty ?? true)
            && (report?.nextAction?.isEmpty ?? true)
            && !artifactFailure
    }

    static func shouldContinueDetailPolling(
        _ task: TaskOrchestrationTaskDetail,
        terminalStablePolls: Int,
        settleLimit: Int
    ) -> Bool {
        if !isTerminalStatus(task.status) {
            return true
        }
        if task.qualityHealth?.orchestrationHealth == "recovering" {
            return true
        }
        if !(task.qualityHealth?.activeRemediationSubtasks.isEmpty ?? true) {
            return true
        }
        if let nextAction = task.deliveryReport?.nextAction, !nextAction.isEmpty {
            return true
        }
        return terminalStablePolls < settleLimit
    }

    static func businessProgress(in subtasks: [TaskOrchestrationSubtaskDetail]) -> TaskOrchestrationProgressCounts {
        let businessSubtasks = subtasks.filter { isOriginalBusinessSubtaskId($0.subtaskId) }
        return TaskOrchestrationProgressCounts(
            completed: businessSubtasks.filter { $0.status == "completed" }.count,
            total: businessSubtasks.count
        )
    }

    static func businessProgress(in subtasks: [TaskOrchestrationPollSubtaskStatus]) -> TaskOrchestrationProgressCounts {
        let businessSubtasks = subtasks.filter { isOriginalBusinessSubtaskId($0.subtask_id) }
        return TaskOrchestrationProgressCounts(
            completed: businessSubtasks.filter { $0.status == "completed" }.count,
            total: businessSubtasks.count
        )
    }

    static func taskSummary(from task: TaskOrchestrationTaskDetail) -> TaskOrchestrationTaskSummary {
        let counts = businessProgress(in: task.subtasks)
        let progress = counts.total > 0
            ? Double(counts.completed) / Double(counts.total)
            : (isTerminalStatus(task.status) ? 1.0 : 0.0)
        return TaskOrchestrationTaskSummary(
            taskId: task.taskId,
            description: task.description,
            status: task.status,
            progress: progress,
            completedCount: counts.completed,
            totalCount: counts.total,
            projectDir: task.projectDir,
            ownerAgent: task.ownerAgent,
            deliveryMode: task.deliveryMode,
            externalTask: task.externalTask,
            reviewStatus: task.reviewStatus,
            acceptedAt: task.acceptedAt
        )
    }

    static func mergedPollResponse(
        task: TaskOrchestrationTaskDetail,
        pollData: TaskOrchestrationPollStatusResponse
    ) -> TaskOrchestrationPollMergeResult {
        let updatedSubtasks = pollData.subtasks.map { ps in
            let existingSubtask = task.subtasks.first(where: { $0.subtaskId == ps.subtask_id })
            return TaskOrchestrationSubtaskDetail(
                subtaskId: ps.subtask_id,
                description: ps.description,
                agentId: ps.agent_id,
                status: ps.status,
                progress: ps.progress,
                outputFile: existingSubtask?.outputFile,
                duration: existingSubtask?.duration,
                errorMessage: existingSubtask?.errorMessage,
                fixPlan: existingSubtask?.fixPlan,
                waveNumber: ps.wave_number,
                ownerDecision: existingSubtask?.ownerDecision,
                waitingOnDependencies: ps.waiting_on_dependencies ?? existingSubtask?.waitingOnDependencies ?? [],
                blockedReason: ps.blocked_reason ?? existingSubtask?.blockedReason,
                runningForSeconds: ps.running_for_seconds ?? existingSubtask?.runningForSeconds
            )
        }

        let updatedWaves: [TaskOrchestrationWaveDetail] = (pollData.waves ?? []).map { pw in
            let waveSubtasks = updatedSubtasks.filter { $0.waveNumber == pw.wave_number }
            let existingWave = task.waves.first(where: { $0.waveId == pw.wave_id })
            return TaskOrchestrationWaveDetail(
                waveId: pw.wave_id,
                waveNumber: pw.wave_number,
                subtasks: waveSubtasks,
                status: pw.status,
                isBlocked: pw.is_blocked ?? existingWave?.isBlocked ?? false,
                governanceStatus: pw.governance_status ?? existingWave?.governanceStatus,
                blockedByWave: pw.blocked_by_wave ?? existingWave?.blockedByWave,
                isRevalidating: pw.is_revalidating ?? existingWave?.isRevalidating ?? false,
                ownerDecision: pw.owner_decision ?? existingWave?.ownerDecision,
                fixRounds: existingWave?.fixRounds
            )
        }

        let detail = task.replacing(
            status: pollData.status,
            subtasks: updatedSubtasks,
            waves: updatedWaves
        )
        let counts = businessProgress(in: pollData.subtasks)
        let summary = TaskOrchestrationTaskSummary(
            taskId: task.taskId,
            description: task.description,
            status: pollData.status,
            progress: pollData.progress,
            completedCount: counts.completed,
            totalCount: counts.total,
            projectDir: task.projectDir,
            ownerAgent: task.ownerAgent,
            deliveryMode: task.deliveryMode,
            externalTask: task.externalTask,
            reviewStatus: task.reviewStatus,
            acceptedAt: task.acceptedAt
        )
        return TaskOrchestrationPollMergeResult(detail: detail, summary: summary)
    }

    private static func isOriginalBusinessSubtaskId(_ subtaskId: String) -> Bool {
        if subtaskId.hasSuffix("-decompose") { return false }
        if subtaskId.hasPrefix("st-quality-") { return false }
        if subtaskId.contains("-integration-fix") { return false }
        if subtaskId.range(of: "-(?:fix-[0-9]+|v[0-9]+)$", options: .regularExpression) != nil {
            return false
        }
        return true
    }
}
