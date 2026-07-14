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

enum AcrossProductCapabilityRole: String, Equatable {
    case agent
    case sharedMemory
    case workflows
    case selfIteration
    case extensionCapability
}

struct AcrossProductCapability: Identifiable, Equatable {
    let id: String
    let title: String
    let titleKey: String?
    let detail: String
    let detailKey: String?
    let systemImage: String
    let isVerified: Bool
    let sourcePluginID: String?
    let role: AcrossProductCapabilityRole
    let artworkIndex: Int?

    var isUnlocked: Bool { isVerified }
}

struct AcrossAchievement: Identifiable, Equatable {
    let id: String
    let title: String
    let titleKey: String?
    let systemImage: String
    let isUnlocked: Bool
    let artworkIndex: Int?
    let usesMilestoneArtwork: Bool
}

struct AcrossCapabilitySource: Equatable {
    let pluginID: String
    let displayName: String
    let available: Bool
    let capabilities: [String: Bool]
    let manifestCapabilities: [AcrossPluginCapabilityDescriptor]
    let manifestAchievements: [AcrossPluginAchievementDescriptor]

    init(
        pluginID: String,
        displayName: String? = nil,
        available: Bool,
        capabilities: [String: Bool] = [:],
        manifestCapabilities: [AcrossPluginCapabilityDescriptor] = [],
        manifestAchievements: [AcrossPluginAchievementDescriptor] = []
    ) {
        self.pluginID = pluginID
        self.displayName = displayName ?? Self.humanized(pluginID)
        self.available = available
        self.capabilities = capabilities
        self.manifestCapabilities = manifestCapabilities
        self.manifestAchievements = manifestAchievements
    }

    init(plugin: AcrossPluginStatus) {
        self.init(
            pluginID: plugin.pluginId,
            displayName: plugin.displayName,
            available: plugin.available,
            capabilities: plugin.capabilities ?? [:],
            manifestCapabilities: plugin.capabilityManifest?.capabilities ?? [],
            manifestAchievements: plugin.capabilityManifest?.achievements ?? []
        )
    }

    var verifiedCapabilities: [AcrossPluginCapabilityDescriptor] {
        if !manifestCapabilities.isEmpty {
            return manifestCapabilities.filter { $0.verified && !$0.id.isEmpty }
        }
        return capabilities
            .filter(\.value)
            .map { key, _ in
                AcrossPluginCapabilityDescriptor(
                    id: key,
                    displayName: Self.humanized(key),
                    verified: true
                )
            }
            .sorted { $0.id.localizedCaseInsensitiveCompare($1.id) == .orderedAscending }
    }

    static func humanized(_ value: String) -> String {
        let separated = value
            .replacingOccurrences(of: "_", with: " ")
            .replacingOccurrences(of: "-", with: " ")
            .replacingOccurrences(of: "([a-z0-9])([A-Z])", with: "$1 $2", options: .regularExpression)
        return separated
            .split(whereSeparator: \Character.isWhitespace)
            .map { $0.prefix(1).uppercased() + $0.dropFirst() }
            .joined(separator: " ")
    }
}

struct AcrossProductProgressSnapshot: Equatable {
    let capabilities: [AcrossProductCapability]
    let achievements: [AcrossAchievement]

    var unlockedCapabilityCount: Int { capabilities.filter(\.isVerified).count }
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

    func isUnlocked(_ role: AcrossProductCapabilityRole) -> Bool {
        capabilities.contains { $0.role == role && $0.isVerified }
    }
}

enum AcrossProductCapabilityRegistry {
    private static let roleAliases: [AcrossProductCapabilityRole: Set<String>] = [
        .sharedMemory: ["sharedmemory", "memoryhooks", "memory", "contextmemory", "contextretrieval"],
        .workflows: ["workflowexecution", "workflows", "qualitygates", "taskorchestration", "taskexecution"],
        .selfIteration: ["autonomousiteration", "selfiteration", "loopengineering", "agentloopruntime", "workflowsupervision", "repositoryreview"],
    ]

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
        let memorySource = source(for: .sharedMemory, in: sources)
        let workflowSource = source(for: .workflows, in: sources)
        let iterationSource = source(for: .selfIteration, in: sources)
        let capabilities = [
            builtInCapability(.agent, verified: hasAvailableAgent, source: nil, artworkIndex: 0),
            builtInCapability(.sharedMemory, verified: memorySource != nil, source: memorySource, artworkIndex: 1),
            builtInCapability(.workflows, verified: workflowSource != nil, source: workflowSource, artworkIndex: 2),
            builtInCapability(.selfIteration, verified: iterationSource != nil, source: iterationSource, artworkIndex: 3),
        ]
        let achievements = achievements(
            sources: sources,
            capabilities: capabilities,
            acceptedDeliveryCount: acceptedDeliveryCount
        )
        return AcrossProductProgressSnapshot(capabilities: capabilities, achievements: achievements)
    }

    private static func role(for capabilityID: String) -> AcrossProductCapabilityRole {
        let normalized = normalize(capabilityID)
        if let match = roleAliases.first(where: { $0.value.contains(normalized) })?.key {
            return match
        }
        return .extensionCapability
    }

    private static func source(
        for role: AcrossProductCapabilityRole,
        in sources: [AcrossCapabilitySource]
    ) -> AcrossCapabilitySource? {
        sources.first { source in
            guard source.available else { return false }
            if source.verifiedCapabilities.contains(where: { self.role(for: $0.id) == role }) {
                return true
            }
            switch role {
            case .sharedMemory: return source.pluginID == "across-context"
            case .workflows: return source.pluginID == "across-orchestrator"
            case .selfIteration: return source.pluginID == "across-autopilot"
            default: return false
            }
        }
    }

    private static func builtInCapability(
        _ role: AcrossProductCapabilityRole,
        verified: Bool,
        source: AcrossCapabilitySource?,
        artworkIndex: Int
    ) -> AcrossProductCapability {
        let localized = localizedKeys(for: role)
        let fallbackTitle: String
        switch role {
        case .agent: fallbackTitle = "Across Agents Assistant"
        case .sharedMemory: fallbackTitle = "Across Context"
        case .workflows: fallbackTitle = "Across Orchestrator"
        case .selfIteration: fallbackTitle = "Across Autopilot"
        case .extensionCapability: fallbackTitle = "Capability"
        }
        return AcrossProductCapability(
            id: "built-in:\(role.rawValue)",
            title: fallbackTitle,
            titleKey: localized.title,
            detail: source.map { "Verified by \($0.displayName)." } ?? fallbackTitle,
            detailKey: localized.detail,
            systemImage: systemImage(for: role),
            isVerified: verified,
            sourcePluginID: source?.pluginID,
            role: role,
            artworkIndex: artworkIndex
        )
    }

    private static func normalize(_ value: String) -> String {
        value.lowercased().filter(\.isLetter)
    }

    private static func localizedKeys(for role: AcrossProductCapabilityRole) -> (title: String?, detail: String?) {
        switch role {
        case .agent: return ("growth.capability.agent", "growth.capability.agent.detail")
        case .sharedMemory: return ("growth.capability.memory", "growth.capability.memory.detail")
        case .workflows: return ("growth.capability.workflows", "growth.capability.workflows.detail")
        case .selfIteration: return ("growth.capability.selfIteration", "growth.capability.selfIteration.detail")
        case .extensionCapability: return (nil, nil)
        }
    }

    private static func systemImage(for role: AcrossProductCapabilityRole) -> String {
        switch role {
        case .agent: return "cpu"
        case .sharedMemory: return "memorychip"
        case .workflows: return "checklist"
        case .selfIteration: return "arrow.triangle.2.circlepath"
        case .extensionCapability: return "checkmark.seal"
        }
    }

    private static func achievements(
        sources: [AcrossCapabilitySource],
        capabilities: [AcrossProductCapability],
        acceptedDeliveryCount: Int
    ) -> [AcrossAchievement] {
        let hasAgent = capabilities.contains { $0.role == .agent && $0.isVerified }
        let hasMemory = capabilities.contains { $0.role == .sharedMemory && $0.isVerified }
        let hasWorkflows = capabilities.contains { $0.role == .workflows && $0.isVerified }
        let hasSelfIteration = capabilities.contains { $0.role == .selfIteration && $0.isVerified }
        let hasCompleteEcosystem = capabilities.allSatisfy(\.isVerified)

        let baseStates: [(String, String, String, Bool, Int)] = [
            ("first-agent", "growth.achievement.firstAgent", "cpu", hasAgent, 0),
            ("memory-connected", "growth.achievement.memoryConnected", "memorychip", hasMemory, 1),
            ("workflow-connected", "growth.achievement.workflowConnected", "checklist", hasWorkflows, 2),
            ("self-iteration-connected", "growth.achievement.selfIterationConnected", "arrow.triangle.2.circlepath", hasSelfIteration, 3),
            ("first-delivery", "growth.achievement.firstAcceptedDelivery", "checkmark.seal", acceptedDeliveryCount > 0, 4),
            ("complete-ecosystem", "growth.achievement.completeEcosystem", "point.3.connected.trianglepath.dotted", hasCompleteEcosystem, 5),
        ]
        var values = baseStates.map { id, key, systemImage, unlocked, index in
            AcrossAchievement(
                id: id,
                title: AcrossCapabilitySource.humanized(id),
                titleKey: key,
                systemImage: systemImage,
                isUnlocked: unlocked,
                artworkIndex: index,
                usesMilestoneArtwork: false
            )
        }

        let milestoneStates: [(String, String, Bool, Int)] = [
            ("three-deliveries", "growth.achievement.threeDeliveries", acceptedDeliveryCount >= 3, 0),
            ("ten-deliveries", "growth.achievement.tenDeliveries", acceptedDeliveryCount >= 10, 1),
            ("twenty-five-deliveries", "growth.achievement.twentyFiveDeliveries", acceptedDeliveryCount >= 25, 2),
            ("agent-memory-synergy", "growth.achievement.agentMemorySynergy", hasAgent && hasMemory, 3),
            ("quality-operator", "growth.achievement.qualityOperator", acceptedDeliveryCount >= 3 && hasWorkflows, 4),
            ("loop-engineering-mastery", "growth.achievement.loopEngineeringMastery", acceptedDeliveryCount >= 10 && hasSelfIteration, 5),
        ]
        values.append(contentsOf: milestoneStates.map { id, key, unlocked, index in
            AcrossAchievement(
                id: id,
                title: AcrossCapabilitySource.humanized(id),
                titleKey: key,
                systemImage: "star",
                isUnlocked: unlocked,
                artworkIndex: index,
                usesMilestoneArtwork: true
            )
        })

        for source in sources where source.available {
            for achievement in source.manifestAchievements where achievement.earned && !achievement.id.isEmpty {
                values.append(AcrossAchievement(
                    id: "\(source.pluginID):\(achievement.id)",
                    title: achievement.displayName ?? AcrossCapabilitySource.humanized(achievement.id),
                    titleKey: nil,
                    systemImage: achievement.systemImage ?? "checkmark.seal",
                    isUnlocked: true,
                    artworkIndex: nil,
                    usesMilestoneArtwork: false
                ))
            }
        }

        var seen = Set<String>()
        return values.filter { seen.insert($0.id).inserted }
    }
}

struct AcrossTaskCapabilityContract: Decodable, Equatable {
    struct CapabilityChoice: Decodable, Equatable {
        let capability: String

        enum CodingKeys: String, CodingKey {
            case capability
            case id
            case name
        }

        init(from decoder: Decoder) throws {
            if let text = try? decoder.singleValueContainer().decode(String.self) {
                capability = text
                return
            }
            let container = try decoder.container(keyedBy: CodingKeys.self)
            capability = try container.decodeIfPresent(String.self, forKey: .capability)
                ?? container.decodeIfPresent(String.self, forKey: .id)
                ?? container.decodeIfPresent(String.self, forKey: .name)
                ?? ""
        }
    }

    struct Decision: Decodable, Equatable, Identifiable {
        let id: String
        let title: String
        let action: String?

        enum CodingKeys: String, CodingKey {
            case id
            case decisionId = "decision_id"
            case title
            case summary
            case prompt
            case action
            case recommendedAction = "recommended_action"
        }

        init(id: String, title: String, action: String? = nil) {
            self.id = id
            self.title = title
            self.action = action
        }

        init(from decoder: Decoder) throws {
            if let text = try? decoder.singleValueContainer().decode(String.self) {
                id = text
                title = AcrossCapabilitySource.humanized(text)
                action = nil
                return
            }
            let container = try decoder.container(keyedBy: CodingKeys.self)
            id = try container.decodeIfPresent(String.self, forKey: .id)
                ?? container.decodeIfPresent(String.self, forKey: .decisionId)
                ?? UUID().uuidString
            title = try container.decodeIfPresent(String.self, forKey: .title)
                ?? container.decodeIfPresent(String.self, forKey: .summary)
                ?? container.decodeIfPresent(String.self, forKey: .prompt)
                ?? AcrossCapabilitySource.humanized(id)
            action = try container.decodeIfPresent(String.self, forKey: .action)
                ?? container.decodeIfPresent(String.self, forKey: .recommendedAction)
        }
    }

    let capabilitiesSelected: [String]
    let verificationPlanned: Bool
    let requiredDecisions: [Decision]

    enum CodingKeys: String, CodingKey {
        case capabilitiesSelected = "capabilities_selected"
        case selectedCapabilities = "selected_capabilities"
        case chosenCapabilities = "chosen_capabilities"
        case verificationPlanned = "verification_planned"
        case verificationPlan = "verification_plan"
        case requiredDecisions = "required_decisions"
        case requiredUserDecisions = "required_user_decisions"
        case automatic
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let choices = (try? container.decode([CapabilityChoice].self, forKey: .chosenCapabilities)) ?? []
        capabilitiesSelected = (try? container.decode([String].self, forKey: .capabilitiesSelected))
            ?? (try? container.decode([String].self, forKey: .selectedCapabilities))
            ?? choices.map(\.capability).filter { !$0.isEmpty }
        verificationPlanned = (try container.decodeIfPresent(Bool.self, forKey: .verificationPlanned))
            ?? (((try? container.decode([String].self, forKey: .verificationPlan))?.isEmpty == false)
                || !choices.isEmpty)
        requiredDecisions = (try? container.decode([Decision].self, forKey: .requiredDecisions))
            ?? (try? container.decode([Decision].self, forKey: .requiredUserDecisions))
            ?? []
    }
}

enum AcrossTaskCompactResultState: String, Equatable {
    case ready
    case needsReview
    case blocked

    var title: String {
        switch self {
        case .ready: return "Ready"
        case .needsReview: return "Needs review"
        case .blocked: return "Blocked"
        }
    }

    var status: String {
        switch self {
        case .ready: return "success"
        case .needsReview: return "attention"
        case .blocked: return "error"
        }
    }
}
