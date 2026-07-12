import Foundation
import Combine

@MainActor
final class AcrossProductCapabilityStore: ObservableObject {
    static let shared = AcrossProductCapabilityStore()

    @Published private(set) var plugins: [AcrossPluginStatus] = []

    private init() {}

    func update(_ plugins: [AcrossPluginStatus]) {
        self.plugins = plugins
    }

    func clear() {
        plugins = []
    }
}

enum AcrossProductCapabilityID: String, CaseIterable, Identifiable {
    case agent
    case sharedMemory
    case workflows
    case selfIteration

    var id: String { rawValue }

    var titleKey: String {
        switch self {
        case .agent: return "growth.capability.agent"
        case .sharedMemory: return "growth.capability.memory"
        case .workflows: return "growth.capability.workflows"
        case .selfIteration: return "growth.capability.selfIteration"
        }
    }

    var detailKey: String {
        switch self {
        case .agent: return "growth.capability.agent.detail"
        case .sharedMemory: return "growth.capability.memory.detail"
        case .workflows: return "growth.capability.workflows.detail"
        case .selfIteration: return "growth.capability.selfIteration.detail"
        }
    }

    var systemName: String {
        switch self {
        case .agent: return "cpu"
        case .sharedMemory: return "memorychip"
        case .workflows: return "checklist"
        case .selfIteration: return "arrow.triangle.2.circlepath"
        }
    }
}

struct AcrossProductCapability: Identifiable, Equatable {
    let id: AcrossProductCapabilityID
    let isUnlocked: Bool
    let sourcePluginID: String?
}

enum AcrossAchievementID: String, CaseIterable, Identifiable {
    case firstAgent
    case memoryConnected
    case workflowConnected
    case selfIterationConnected
    case firstAcceptedDelivery
    case completeEcosystem
    case threeDeliveries
    case tenDeliveries
    case twentyFiveDeliveries
    case agentMemorySynergy
    case qualityOperator
    case loopEngineeringMastery

    var id: String { rawValue }
    var titleKey: String { "growth.achievement.\(rawValue)" }
}

struct AcrossAchievement: Identifiable, Equatable {
    let id: AcrossAchievementID
    let isUnlocked: Bool
}

struct AcrossCapabilitySource: Equatable {
    let pluginID: String
    let available: Bool
    let capabilities: [String: Bool]

    init(pluginID: String, available: Bool, capabilities: [String: Bool] = [:]) {
        self.pluginID = pluginID
        self.available = available
        self.capabilities = capabilities
    }

    init(plugin: AcrossPluginStatus) {
        self.init(
            pluginID: plugin.pluginId,
            available: plugin.available,
            capabilities: plugin.capabilities ?? [:]
        )
    }
}

struct AcrossProductProgressSnapshot: Equatable {
    let capabilities: [AcrossProductCapability]
    let achievements: [AcrossAchievement]

    var unlockedCapabilityCount: Int { capabilities.filter(\.isUnlocked).count }
    var unlockedAchievementCount: Int { achievements.filter(\.isUnlocked).count }

    var levelKey: String {
        switch unlockedCapabilityCount + unlockedAchievementCount {
        case 0: return "growth.level.starter"
        case 1...3: return "growth.level.explorer"
        case 4...6: return "growth.level.builder"
        default: return "growth.level.deliverer"
        }
    }

    var unlockedSurfaces: [OperationsWorkbenchSurface] {
        var surfaces: [OperationsWorkbenchSurface] = []
        if isUnlocked(.sharedMemory) { surfaces.append(.memory) }
        if isUnlocked(.workflows) { surfaces.append(.qualityGate) }
        if isUnlocked(.selfIteration) { surfaces.append(.autopilot) }
        surfaces.append(.achievements)
        return surfaces
    }

    func isUnlocked(_ id: AcrossProductCapabilityID) -> Bool {
        capabilities.first(where: { $0.id == id })?.isUnlocked == true
    }
}

enum AcrossProductCapabilityRegistry {
    static func snapshot(
        plugins: [AcrossPluginStatus],
        hasAvailableAgent: Bool,
        acceptedDeliveryCount: Int
    ) -> AcrossProductProgressSnapshot {
        snapshot(
            sources: plugins.map(AcrossCapabilitySource.init(plugin:)),
            hasAvailableAgent: hasAvailableAgent,
            acceptedDeliveryCount: acceptedDeliveryCount
        )
    }

    static func snapshot(
        sources: [AcrossCapabilitySource],
        hasAvailableAgent: Bool,
        acceptedDeliveryCount: Int
    ) -> AcrossProductProgressSnapshot {
        let context = source(
            in: sources,
            pluginID: "across-context",
            declaredCapabilities: ["sharedMemory"]
        )
        let orchestrator = source(
            in: sources,
            pluginID: "across-orchestrator",
            declaredCapabilities: ["workflowExecution"]
        )
        let autopilot = source(
            in: sources,
            pluginID: "across-autopilot",
            declaredCapabilities: ["autonomousIteration"]
        )

        let capabilities = [
            AcrossProductCapability(id: .agent, isUnlocked: hasAvailableAgent, sourcePluginID: nil),
            AcrossProductCapability(id: .sharedMemory, isUnlocked: context != nil, sourcePluginID: context?.pluginID),
            AcrossProductCapability(id: .workflows, isUnlocked: orchestrator != nil, sourcePluginID: orchestrator?.pluginID),
            AcrossProductCapability(id: .selfIteration, isUnlocked: autopilot != nil, sourcePluginID: autopilot?.pluginID),
        ]

        let allExtensionsAvailable = context != nil && orchestrator != nil && autopilot != nil
        let achievements = [
            AcrossAchievement(id: .firstAgent, isUnlocked: hasAvailableAgent),
            AcrossAchievement(id: .memoryConnected, isUnlocked: context != nil),
            AcrossAchievement(id: .workflowConnected, isUnlocked: orchestrator != nil),
            AcrossAchievement(id: .selfIterationConnected, isUnlocked: autopilot != nil),
            AcrossAchievement(id: .firstAcceptedDelivery, isUnlocked: acceptedDeliveryCount > 0),
            AcrossAchievement(id: .completeEcosystem, isUnlocked: allExtensionsAvailable),
            AcrossAchievement(id: .threeDeliveries, isUnlocked: acceptedDeliveryCount >= 3),
            AcrossAchievement(id: .tenDeliveries, isUnlocked: acceptedDeliveryCount >= 10),
            AcrossAchievement(id: .twentyFiveDeliveries, isUnlocked: acceptedDeliveryCount >= 25),
            AcrossAchievement(id: .agentMemorySynergy, isUnlocked: hasAvailableAgent && context != nil),
            AcrossAchievement(id: .qualityOperator, isUnlocked: orchestrator != nil && acceptedDeliveryCount >= 3),
            AcrossAchievement(id: .loopEngineeringMastery, isUnlocked: autopilot != nil && acceptedDeliveryCount >= 10),
        ]

        return AcrossProductProgressSnapshot(capabilities: capabilities, achievements: achievements)
    }

    private static func source(
        in sources: [AcrossCapabilitySource],
        pluginID: String,
        declaredCapabilities: [String]
    ) -> AcrossCapabilitySource? {
        sources.first { source in
            guard source.available else { return false }
            return source.pluginID == pluginID
                || declaredCapabilities.contains(where: { source.capabilities[$0] == true })
        }
    }
}
