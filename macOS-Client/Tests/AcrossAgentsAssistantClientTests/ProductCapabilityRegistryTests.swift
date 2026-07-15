import Foundation
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

    @Test func lockedBuiltInRewardsKeepPixelArtworkVisible() {
        let snapshot = AcrossProductCapabilityRegistry.snapshot(
            sources: [],
            hasAvailableAgent: false,
            acceptedDeliveryCount: 0
        )

        #expect(snapshot.capabilities.count == 4)
        #expect(snapshot.capabilities.allSatisfy { $0.artworkIndex != nil })
        #expect(snapshot.capabilities.allSatisfy { !$0.isUnlocked })
        #expect(snapshot.achievements.count == 12)
        #expect(snapshot.achievements.allSatisfy { $0.artworkIndex != nil })
        #expect(snapshot.achievements.allSatisfy { !$0.isUnlocked })
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

    @Test func corePluginCapabilitiesDoNotUnlockSiblingProductSurfaces() {
        let snapshot = AcrossProductCapabilityRegistry.snapshot(
            sources: [
                AcrossCapabilitySource(
                    pluginID: "across-orchestrator",
                    available: true,
                    capabilities: [
                        "workflowExecution": true,
                        "repositoryReview": true,
                        "sharedMemory": true,
                    ]
                ),
            ],
            hasAvailableAgent: true,
            acceptedDeliveryCount: 0
        )

        #expect(!snapshot.isUnlocked(.sharedMemory))
        #expect(snapshot.isUnlocked(.workflows))
        #expect(!snapshot.isUnlocked(.selfIteration))
        #expect(snapshot.unlockedSurfaces == [.qualityGate, .achievements])
    }

    @Test func ecosystemComponentsStaySeparateFromTaskAchievements() {
        let snapshot = AcrossProductCapabilityRegistry.snapshot(
            sources: [
                AcrossCapabilitySource(pluginID: "across-context", available: true),
                AcrossCapabilitySource(pluginID: "across-orchestrator", available: true),
                AcrossCapabilitySource(pluginID: "across-autopilot", available: true),
            ],
            hasAvailableAgent: true,
            acceptedDeliveryCount: 1
        )

        #expect(snapshot.unlockedCapabilityCount == 4)
        #expect(snapshot.unlockedAchievementCount == 1)
        #expect(snapshot.unlockedSurfaces == [.memory, .qualityGate, .autopilot, .achievements])
        #expect(snapshot.levelKey == "growth.level.explorer")
        #expect(snapshot.achievements.first(where: { $0.id == "memory-connected" })?.isUnlocked == false)
        #expect(snapshot.achievements.first(where: { $0.id == "workflow-connected" })?.isUnlocked == false)
        #expect(snapshot.achievements.first(where: { $0.id == "self-iteration-connected" })?.isUnlocked == false)
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

        #expect(early.achievements.count == 12)
        #expect(early.achievements.first(where: { $0.id == "three-deliveries" })?.isUnlocked == true)
        #expect(early.achievements.first(where: { $0.id == "ten-deliveries" })?.isUnlocked == false)
        #expect(advanced.achievements.first(where: { $0.id == "ten-deliveries" })?.isUnlocked == true)
        #expect(advanced.achievements.first(where: { $0.id == "loop-engineering-mastery" })?.isUnlocked == false)
        #expect(advanced.achievements.first(where: { $0.id == "twenty-five-deliveries" })?.isUnlocked == false)
        #expect(early.achievements.allSatisfy { $0.artworkIndex != nil })
    }

    @Test func loopMasteryRequiresRealLoopAndReleaseEvents() {
        let snapshot = AcrossProductCapabilityRegistry.snapshot(
            sources: [AcrossCapabilitySource(pluginID: "across-autopilot", available: true)],
            hasAvailableAgent: true,
            learningEvents: [
                AcrossLearningEvent(kind: .supervisedLoop, sourceID: "loop-1"),
                AcrossLearningEvent(kind: .releaseReadiness, sourceID: "release-1"),
            ]
        )

        #expect(snapshot.achievements.first(where: { $0.id == "loop-engineering-mastery" })?.isUnlocked == true)
    }

    @Test func lowLevelPluginCapabilitiesAreNotPromotedToGrowthRowsOrAchievements() {
        let snapshot = AcrossProductCapabilityRegistry.snapshot(
            sources: [
                AcrossCapabilitySource(
                    pluginID: "community-security",
                    displayName: "Community Security",
                    available: true,
                    manifestCapabilities: [
                        AcrossPluginCapabilityDescriptor(
                            id: "dependency_audit",
                            displayName: "Dependency Audit",
                            summary: "Checks dependency provenance.",
                            verified: true
                        ),
                    ]
                ),
            ],
            hasAvailableAgent: false,
            acceptedDeliveryCount: 0
        )

        #expect(snapshot.capabilities.count == 4)
        #expect(snapshot.capabilities.allSatisfy { $0.role != .extensionCapability })
        #expect(snapshot.achievements.count == 12)
        #expect(snapshot.achievements.allSatisfy { !$0.id.hasPrefix("verified:") })
        #expect(snapshot.achievements.allSatisfy { !$0.isUnlocked })
    }

    @Test func explicitlyDeclaredEarnedAchievementRemainsVisible() {
        let snapshot = AcrossProductCapabilityRegistry.snapshot(
            sources: [
                AcrossCapabilitySource(
                    pluginID: "community-quality",
                    available: true,
                    manifestAchievements: [
                        AcrossPluginAchievementDescriptor(
                            id: "first-release-review",
                            displayName: "First Release Review",
                            earned: true
                        ),
                    ]
                ),
            ],
            hasAvailableAgent: false,
            acceptedDeliveryCount: 0
        )

        #expect(snapshot.achievements.count == 13)
        #expect(snapshot.achievements.first(where: {
            $0.id == "community-quality:first-release-review"
        })?.isUnlocked == true)
    }

    @Test func capabilityPlanDecodesBackendChoicesAndRequiredDecisions() throws {
        let data = Data("""
        {
          "chosen_capabilities": [
            {"capability": "quality_gates", "plugin_id": "across-orchestrator"}
          ],
          "required_user_decisions": [
            {
              "id": "approve_risky_capabilities",
              "prompt": "Approve consequential changes.",
              "required": true
            }
          ],
          "automatic": false
        }
        """.utf8)

        let contract = try JSONDecoder().decode(AcrossTaskCapabilityContract.self, from: data)
        #expect(contract.capabilitiesSelected == ["quality_gates"])
        #expect(contract.verificationPlanned)
        #expect(contract.requiredDecisions.map(\.id) == ["approve_risky_capabilities"])

        let task = TaskOrchestrationTaskDetail(
            taskId: "capability-plan",
            description: "Verify a release",
            status: "completed",
            ownerAgent: nil,
            allowedSubtaskAgents: nil,
            projectDir: nil,
            subtasks: [],
            waves: [],
            artifacts: [],
            artifactVersions: nil,
            ownerSessionId: nil,
            lastOwnerDecision: nil,
            error: nil
        )
        let automaticPresentation = AcrossTaskCapabilityPresentation(task: task)
        let decisionPresentation = AcrossTaskCapabilityPresentation(task: task, capabilityContract: contract)
        #expect(automaticPresentation.requiredDecisions.isEmpty)
        #expect(decisionPresentation.requiredDecisions.count == 1)
        #expect(decisionPresentation.summaryLine == "1 capability selected; verification planned")
        #expect(decisionPresentation.resultState == .needsReview)
    }
}
