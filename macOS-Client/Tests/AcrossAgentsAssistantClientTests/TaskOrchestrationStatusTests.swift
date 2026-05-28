import Testing
@testable import AcrossAgentsAssistantClient

struct TaskOrchestrationStatusTests {
    @Test func displayStatusKeepsTerminalStatuses() {
        let completed = TaskOrchestrationViewModel.ResumableTask(
            taskId: "task-1",
            description: "done",
            status: "completed",
            createdAt: 1,
            updatedAt: 2,
            projectDir: nil
        )
        let failed = TaskOrchestrationViewModel.ResumableTask(
            taskId: "task-2",
            description: "failed",
            status: "failed",
            createdAt: 1,
            updatedAt: 2,
            projectDir: nil
        )
        let completedWithFailures = TaskOrchestrationViewModel.ResumableTask(
            taskId: "task-3",
            description: "partial",
            status: "completed_with_failures",
            createdAt: 1,
            updatedAt: 2,
            projectDir: nil
        )

        #expect(TaskOrchestrationViewModel.ResumableTask.displayStatus(for: completed) == "completed")
        #expect(TaskOrchestrationViewModel.ResumableTask.displayStatus(for: failed) == "failed")
        #expect(TaskOrchestrationViewModel.ResumableTask.displayStatus(for: completedWithFailures) == "completed_with_failures")
    }

    @Test func displayStatusMapsPausedToSuspended() {
        let paused = TaskOrchestrationViewModel.ResumableTask(
            taskId: "task-4",
            description: "paused",
            status: "paused",
            createdAt: 1,
            updatedAt: 2,
            projectDir: nil
        )

        #expect(TaskOrchestrationViewModel.ResumableTask.displayStatus(for: paused) == "suspended")
        #expect(TaskOrchestrationViewModel.ResumableTask.isRecoverableDisplayStatus("suspended"))
        #expect(TaskOrchestrationViewModel.ResumableTask.isRecoverableDisplayStatus("paused"))
        #expect(!TaskOrchestrationViewModel.ResumableTask.isRecoverableDisplayStatus("completed"))
    }
}
