import Foundation

private func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fatalError(message) }
}

private func subtask(_ id: String, _ status: String) -> TaskOrchestrationSubtaskDetail {
    TaskOrchestrationSubtaskDetail(
        subtaskId: id,
        description: id,
        agentId: "auto",
        status: status,
        progress: status == "completed" ? 1 : 0.5,
        outputFile: nil,
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

private func task(_ status: String, subtasks: [TaskOrchestrationSubtaskDetail] = []) -> TaskOrchestrationTaskDetail {
    TaskOrchestrationTaskDetail(
        taskId: "work-state",
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

@main
struct UnifiedWorkStateBehavior {
    static func main() {
        check(TaskOrchestrationStateReducers.userPhase(for: task("decomposing")) == .understanding, "Decomposition must read as understanding")
        check(TaskOrchestrationStateReducers.userPhase(for: task("running", subtasks: [subtask("build", "running")])) == .working, "Active business work must read as working")
        check(TaskOrchestrationStateReducers.userPhase(for: task("running", subtasks: [subtask("build", "completed"), subtask("st-quality-build", "running")])) == .checking, "Quality remediation must read as checking")
        check(TaskOrchestrationStateReducers.userPhase(for: task("completed")) == .ready, "Clean completion must be ready")
        check(TaskOrchestrationStateReducers.userPhase(for: task("completed_with_failures")) == .needsAttention, "Partial completion must not be presented as ready")
        check(TaskOrchestrationStateReducers.userPhase(for: task("failed")) == .needsAttention, "Failure must remain visible")
        print("UnifiedWorkStateBehavior passed")
    }
}
