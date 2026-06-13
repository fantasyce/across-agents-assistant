import Foundation
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

    @Test func externalTasksDoNotSupportLegacyLifecycleControls() throws {
        let payload = """
        {
          "task_id": "task-external",
          "description": "External task",
          "status": "running",
          "external_task": true,
          "subtasks": [],
          "waves": [],
          "artifacts": []
        }
        """.data(using: .utf8)!

        let task = try JSONDecoder().decode(TaskOrchestrationViewModel.TaskDetail.self, from: payload)

        #expect(task.externalTask)
        #expect(!task.supportsLegacyLifecycleControls)
    }

    @Test func taskDetailReplacementPreservesBoundaryMetadata() throws {
        let payload = """
        {
          "task_id": "task-external",
          "description": "External task",
          "status": "running",
          "external_task": true,
          "task_types": ["functional", "artifact"],
          "delivery_mode": "functional_artifact",
          "owner_delivery_contract": {"required": true},
          "subtasks": [],
          "waves": [],
          "artifacts": []
        }
        """.data(using: .utf8)!

        let task = try JSONDecoder().decode(TaskOrchestrationViewModel.TaskDetail.self, from: payload)
        let updated = task.replacing(status: "completed")

        #expect(updated.status == "completed")
        #expect(updated.externalTask)
        #expect(updated.taskTypes == ["functional", "artifact"])
        #expect(updated.deliveryMode == "functional_artifact")
        #expect(updated.hasOwnerDeliveryContract)
        #expect(!updated.supportsLegacyLifecycleControls)
    }

    @Test func taskSummaryDecodesExternalTaskMarker() throws {
        let payload = """
        {
          "task_id": "task-external",
          "description": "External task",
          "status": "running",
          "progress": 0.4,
          "completed_count": 1,
          "total_count": 3,
          "external_task": true
        }
        """.data(using: .utf8)!

        let summary = try JSONDecoder().decode(TaskOrchestrationViewModel.TaskSummary.self, from: payload)

        #expect(summary.externalTask)
    }
}
