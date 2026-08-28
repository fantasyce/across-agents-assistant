import Testing
@testable import AcrossAgentsAssistantClient

struct WorkSubmissionModeTests {
    @Test func protectedDeliveryIsUsedWhenOrchestratorIsAvailable() {
        let mode = WorkSubmissionMode.resolve(
            automaticDeliveryProtection: true,
            orchestratorUnavailable: false
        )

        #expect(mode == .protectedDelivery)
        #expect(mode.usesProtectedDelivery)
        #expect(!mode.usesDirectAgent)
        #expect(!mode.showsOrchestratorUpgradeHint)
    }

    @Test func missingOrchestratorKeepsGoalTrackedDeliveryOnTheDirectRuntime() {
        let mode = WorkSubmissionMode.resolve(
            automaticDeliveryProtection: true,
            orchestratorUnavailable: true
        )

        #expect(mode == .directAgentFallback)
        #expect(mode.usesProtectedDelivery)
        #expect(!mode.usesDirectAgent)
        #expect(mode.showsOrchestratorUpgradeHint)
    }

    @Test func explicitDirectModeRemainsDirectWhenOrchestratorIsAvailable() {
        let mode = WorkSubmissionMode.resolve(
            automaticDeliveryProtection: false,
            orchestratorUnavailable: false
        )

        #expect(mode == .directAgent)
        #expect(mode.usesDirectAgent)
        #expect(!mode.showsOrchestratorUpgradeHint)
    }
}
