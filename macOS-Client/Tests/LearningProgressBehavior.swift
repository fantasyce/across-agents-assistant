import Foundation

@main
struct LearningProgressBehavior {
    @MainActor
    static func main() throws {
        let task = TaskOrchestrationTaskSummary(
            taskId: "accepted-task",
            description: "Verified delivery",
            status: "completed",
            progress: 1,
            completedCount: 2,
            totalCount: 2,
            reviewStatus: "accepted",
            acceptedAt: 100
        )
        let refreshedEvents = AcrossLearningProgressEngine.taskEvents(from: [task, task])
        let uniqueEvents = AcrossLearningLedger.deduplicated(refreshedEvents)
        precondition(uniqueEvents.count == 3)

        var ledger = AcrossLearningLedger()
        precondition(ledger.record(uniqueEvents))
        precondition(!ledger.record(uniqueEvents))

        let snapshot = AcrossProductCapabilityRegistry.snapshot(
            sources: [
                AcrossCapabilitySource(pluginID: "across-context", available: true),
                AcrossCapabilitySource(pluginID: "across-orchestrator", available: true),
                AcrossCapabilitySource(pluginID: "across-autopilot", available: true),
            ],
            hasAvailableAgent: true,
            learningEvents: []
        )
        precondition(snapshot.capabilities.filter(\.isVerified).count == 4)
        precondition(snapshot.achievements.count == 12)
        precondition(snapshot.achievements.allSatisfy { !$0.isUnlocked })
        precondition(snapshot.learning.level == .explorer)

        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("aaa-learning-behavior-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let ledgerURL = directory.appendingPathComponent("learning-progress.json")
        let persisted = AcrossLearningEvent(
            kind: .evidenceInspected,
            sourceID: "persisted-task",
            occurredAt: Date(timeIntervalSince1970: 100)
        )
        let writer = AcrossLearningProgressStore(fileURL: ledgerURL)
        precondition(writer.record([persisted]))
        let reader = AcrossLearningProgressStore(fileURL: ledgerURL)
        precondition(reader.events == [persisted])
        try Data("not-json".utf8).write(to: ledgerURL, options: .atomic)
        reader.reload()
        precondition(reader.events.isEmpty)
        precondition(reader.recoveredCorruptState)

        let legacy = """
        {
          "schemaVersion": 1,
          "events": [{
            "eventID": "evidence_inspected:legacy-task",
            "kind": "evidence_inspected",
            "sourceID": "legacy-task",
            "occurredAt": "1970-01-01T00:01:40Z",
            "origin": "user_interaction"
          }]
        }
        """
        try Data(legacy.utf8).write(to: ledgerURL, options: .atomic)
        reader.reload()
        precondition(reader.events.map(\.eventID) == ["evidence_inspected:legacy-task"])
        precondition(reader.ledger.schemaVersion == AcrossLearningLedger.currentSchemaVersion)

        print("Learning progress behavior checks passed.")
    }
}
