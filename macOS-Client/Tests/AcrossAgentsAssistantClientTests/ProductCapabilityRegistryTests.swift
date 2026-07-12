import Testing
@testable import AcrossAgentsAssistantClient

struct ProductCapabilityRegistryTests {
    @Test func emptyHostKeepsOnlyGrowthVisible() {
        let snapshot = AcrossProductCapabilityRegistry.snapshot(
            sources: [],
            hasAvailableAgent: false,
            acceptedDeliveryCount: 0
        )

        #expect(snapshot.unlockedCapabilityCount == 0)
        #expect(snapshot.unlockedAchievementCount == 0)
        #expect(snapshot.unlockedSurfaces == [.achievements])
        #expect(!snapshot.isUnlocked(.agent))
    }

    @Test func unavailablePluginDoesNotUnlockItsCapability() {
        let snapshot = AcrossProductCapabilityRegistry.snapshot(
            sources: [
                AcrossCapabilitySource(pluginID: "across-context", available: false),
                AcrossCapabilitySource(pluginID: "across-orchestrator", available: true),
            ],
            hasAvailableAgent: true,
            acceptedDeliveryCount: 0
        )

        #expect(snapshot.isUnlocked(.agent))
        #expect(!snapshot.isUnlocked(.sharedMemory))
        #expect(snapshot.isUnlocked(.workflows))
        #expect(snapshot.unlockedSurfaces == [.qualityGate, .achievements])
    }

    @Test func declaredCapabilityAllowsFuturePluginContribution() {
        let snapshot = AcrossProductCapabilityRegistry.snapshot(
            sources: [
                AcrossCapabilitySource(
                    pluginID: "community-memory-provider",
                    available: true,
                    capabilities: ["sharedMemory": true]
                ),
            ],
            hasAvailableAgent: false,
            acceptedDeliveryCount: 0
        )

        #expect(snapshot.isUnlocked(.sharedMemory))
        #expect(snapshot.unlockedSurfaces == [.memory, .achievements])
    }

    @Test func completeEcosystemAndAcceptedDeliveryUnlockTruthfulAchievements() {
        let snapshot = AcrossProductCapabilityRegistry.snapshot(
            sources: [
                AcrossCapabilitySource(pluginID: "across-context", available: true),
                AcrossCapabilitySource(pluginID: "across-orchestrator", available: true),
                AcrossCapabilitySource(pluginID: "across-autopilot", available: true),
            ],
            hasAvailableAgent: true,
            acceptedDeliveryCount: 1
        )

        #expect(snapshot.unlockedCapabilityCount == AcrossProductCapabilityID.allCases.count)
        #expect(snapshot.unlockedAchievementCount == 7)
        #expect(snapshot.unlockedSurfaces == [.memory, .qualityGate, .autopilot, .achievements])
        #expect(snapshot.levelKey == "growth.level.deliverer")
    }

    @Test func deliveryMilestonesRemainVisibleAndUnlockProgressively() {
        let sources = [
            AcrossCapabilitySource(pluginID: "across-context", available: true),
            AcrossCapabilitySource(pluginID: "across-orchestrator", available: true),
            AcrossCapabilitySource(pluginID: "across-autopilot", available: true),
        ]
        let early = AcrossProductCapabilityRegistry.snapshot(
            sources: sources,
            hasAvailableAgent: true,
            acceptedDeliveryCount: 3
        )
        let advanced = AcrossProductCapabilityRegistry.snapshot(
            sources: sources,
            hasAvailableAgent: true,
            acceptedDeliveryCount: 10
        )

        #expect(early.achievements.count == AcrossAchievementID.allCases.count)
        #expect(early.achievements.first(where: { $0.id == .threeDeliveries })?.isUnlocked == true)
        #expect(early.achievements.first(where: { $0.id == .tenDeliveries })?.isUnlocked == false)
        #expect(advanced.achievements.first(where: { $0.id == .tenDeliveries })?.isUnlocked == true)
        #expect(advanced.achievements.first(where: { $0.id == .loopEngineeringMastery })?.isUnlocked == true)
        #expect(advanced.achievements.first(where: { $0.id == .twentyFiveDeliveries })?.isUnlocked == false)
    }
}
