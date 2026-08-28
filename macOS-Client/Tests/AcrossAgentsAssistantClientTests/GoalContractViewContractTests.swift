import Foundation
import Testing
@testable import AcrossAgentsAssistantClient

struct GoalContractViewContractTests {
    @Test func goalDetailsUseOneFlatNativeDisclosureSurface() throws {
        let goal = try source("macOS-Client/Sources/Views/GoalContractViews.swift")
        let task = try source("macOS-Client/Sources/Views/TaskDetailViews.swift")

        #expect(goal.contains("struct GoalContractSummaryView"))
        #expect(task.contains("GoalContractSummaryView("))
        #expect(goal.contains("MinimalDisclosureSection("))
        #expect(!goal.contains("DisclosureGroup"))
        #expect(!goal.contains("LinearGradient"))
        #expect(!goal.contains("AngularGradient"))
        #expect(!goal.contains("Color.blue"))
        #expect(!goal.contains("GoalProjectionReducer.reduce"))
    }

    @Test func governedControlsAreNamedConfirmedAndRevisionBound() throws {
        let goal = try source("macOS-Client/Sources/Views/GoalContractViews.swift")

        #expect(goal.contains("expectedRevision: envelope.contract.revision"))
        #expect(goal.contains("idempotencyKey: UUID().uuidString"))
        #expect(goal.contains(".confirmationDialog("))
        #expect(goal.contains(".accessibilityLabel("))
        #expect(goal.contains("Accept all changes"))
        #expect(goal.contains("Accept selected changes"))
        #expect(goal.contains("Reject changes"))
        #expect(goal.contains("Revalidate stale evidence"))
        #expect(goal.contains("Reject criterion review"))
        #expect(goal.contains("Pass criterion review"))
        #expect(goal.contains(".disabled(selectedOperationIndexes"))
    }

    @Test func everyGoalStateHasAnExplicitPresentation() throws {
        let goal = try source("macOS-Client/Sources/Views/GoalContractViews.swift")
        for marker in [
            "case .loading", "case .legacyEmpty", "case .active", "case .stale",
            "case .decisionRequired", "case .error", "case .completed"
        ] {
            #expect(goal.contains(marker))
        }
        #expect(goal.contains("criterionCoverage"))
        #expect(goal.contains("pendingProposals"))
        #expect(goal.contains("invalidations"))
    }

    @Test func goalStringsCoverEnglishAndChinese() {
        #expect(AppPreferences.localizedString("tasks.goal.title", localeIdentifier: "en") == "Goal and acceptance")
        #expect(AppPreferences.localizedString("tasks.goal.title", localeIdentifier: "zh-Hans") == "目标与验收")
        #expect(AppPreferences.localizedString("tasks.goal.revalidate", localeIdentifier: "zh-Hans").contains("重新验证"))
    }

    private func source(_ relativePath: String) throws -> String {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        return try String(contentsOf: root.appendingPathComponent(relativePath), encoding: .utf8)
    }
}
