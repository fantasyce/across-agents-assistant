import Foundation
import Testing
@testable import AcrossAgentsAssistantClient

struct LearningProgressTests {
    @Test func ledgerWritesAreIdempotentByVerifiedSourceEvent() {
        let event = AcrossLearningEvent(
            kind: .verifiedDelivery,
            sourceID: "task-1",
            occurredAt: Date(timeIntervalSince1970: 100)
        )
        var ledger = AcrossLearningLedger()

        let firstWrite = ledger.record([event])
        let duplicateWrite = ledger.record([event, event])
        #expect(firstWrite)
        #expect(!duplicateWrite)
        #expect(ledger.events == [event])
    }

    @Test func projectTaskRecomputationAccumulatesGlobalAchievements() {
        let manual = AcrossLearningEvent(kind: .evidenceInspected, sourceID: "task-1")
        let workspaceTask = AcrossLearningEvent(kind: .verifiedDelivery, sourceID: "workspace-task", origin: .taskSummary)
        let assistantTask = AcrossLearningEvent(kind: .qualityWorkflow, sourceID: "aaa-task", origin: .taskSummary)
        var ledger = AcrossLearningLedger(events: [manual])

        let recordedWorkspaceTask = ledger.recompute(taskEvents: [workspaceTask])
        let recordedAssistantTask = ledger.recompute(taskEvents: [assistantTask])
        let recordedDuplicate = ledger.recompute(taskEvents: [assistantTask])
        #expect(recordedWorkspaceTask)
        #expect(recordedAssistantTask)
        #expect(!recordedDuplicate)
        #expect(Set(ledger.events.map(\.eventID)) == Set([
            manual.eventID,
            workspaceTask.eventID,
            assistantTask.eventID,
        ]))
    }

    @MainActor
    @Test func localStoreSurvivesReloadAndRecoversCorruptDerivedState() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("aaa-learning-\(UUID().uuidString)", isDirectory: true)
        let url = directory.appendingPathComponent("learning-progress.json")
        defer { try? FileManager.default.removeItem(at: directory) }

        let event = AcrossLearningEvent(
            kind: .evidenceInspected,
            sourceID: "task-persisted",
            occurredAt: Date(timeIntervalSince1970: 1_000)
        )
        let writer = AcrossLearningProgressStore(fileURL: url)
        #expect(writer.record([event]))

        let reader = AcrossLearningProgressStore(fileURL: url)
        #expect(reader.events == [event])
        #expect(!reader.recoveredCorruptState)

        try Data("not-json".utf8).write(to: url, options: .atomic)
        reader.reload()
        #expect(reader.events.isEmpty)
        #expect(reader.recoveredCorruptState)
    }

    @MainActor
    @Test func schemaOneLedgerMigratesWithoutLosingEvents() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("aaa-learning-migration-\(UUID().uuidString)", isDirectory: true)
        let url = directory.appendingPathComponent("learning-progress.json")
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let legacy = """
        {
          "schemaVersion": 1,
          "events": [{
            "eventID": "evidence_inspected:task-legacy",
            "kind": "evidence_inspected",
            "sourceID": "task-legacy",
            "occurredAt": "1970-01-01T00:01:40Z",
            "origin": "user_interaction"
          }]
        }
        """
        try Data(legacy.utf8).write(to: url)

        let store = AcrossLearningProgressStore(fileURL: url)
        #expect(store.events.map(\.eventID) == ["evidence_inspected:task-legacy"])
        #expect(store.ledger.schemaVersion == AcrossLearningLedger.currentSchemaVersion)
    }

    @Test func taskEventsUseStableTaskIDsAndDoNotRewardRefreshes() {
        let task = TaskOrchestrationTaskSummary(
            taskId: "accepted-task",
            description: "Verified work",
            status: "completed",
            progress: 1,
            completedCount: 2,
            totalCount: 2,
            reviewStatus: "accepted",
            acceptedAt: 100
        )
        let first = AcrossLearningProgressEngine.taskEvents(from: [task])
        let refreshed = AcrossLearningProgressEngine.taskEvents(from: [task, task])

        #expect(Set(first.map(\.kind)) == Set([.verifiedDelivery, .proposalReviewed, .qualityWorkflow]))
        #expect(AcrossLearningLedger.deduplicated(refreshed).count == first.count)
    }

    @Test func capabilityPathIsOptionalAndLevelsComeOnlyFromUniqueLearningKinds() {
        let capabilities = [
            capability(.agent, verified: true),
            capability(.workflows, verified: true),
            capability(.sharedMemory, verified: false),
            capability(.selfIteration, verified: false),
        ]
        let events = [
            AcrossLearningEvent(kind: .verifiedDelivery, sourceID: "task-1"),
            AcrossLearningEvent(kind: .verifiedDelivery, sourceID: "task-2"),
            AcrossLearningEvent(kind: .evidenceInspected, sourceID: "task-1"),
        ]
        let progress = AcrossLearningProgressEngine.snapshot(events: events, capabilities: capabilities)

        #expect(progress.level == .builder)
        #expect(progress.missions.first(where: { $0.kind == .verifiedTask })?.isComplete == true)
        #expect(progress.missions.first(where: { $0.kind == .memory })?.isAvailable == false)
        #expect(progress.missions.first(where: { $0.kind == .loop })?.isChallenge == true)
    }

    @Test func installedComponentsNeverUnlockDuplicateAchievements() {
        let snapshot = AcrossProductCapabilityRegistry.snapshot(
            sources: [
                AcrossCapabilitySource(pluginID: "across-context", available: true),
                AcrossCapabilitySource(pluginID: "across-orchestrator", available: true),
                AcrossCapabilitySource(pluginID: "across-autopilot", available: true),
            ],
            hasAvailableAgent: true,
            learningEvents: []
        )

        #expect(snapshot.unlockedCapabilityCount == 4)
        #expect(snapshot.achievements.count == 12)
        #expect(snapshot.unlockedAchievementCount == 0)
        #expect(snapshot.learning.level == .explorer)
    }

    private func capability(
        _ role: AcrossProductCapabilityRole,
        verified: Bool
    ) -> AcrossProductCapability {
        AcrossProductCapability(
            id: role.rawValue,
            title: role.rawValue,
            titleKey: nil,
            detail: role.rawValue,
            detailKey: nil,
            systemImage: "circle",
            isVerified: verified,
            sourcePluginID: nil,
            role: role,
            artworkIndex: nil
        )
    }
}
