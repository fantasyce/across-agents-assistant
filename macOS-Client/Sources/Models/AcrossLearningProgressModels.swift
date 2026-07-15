import Foundation
import Combine

enum AcrossLearningEventKind: String, Codable, CaseIterable, Equatable, Hashable {
    case agentInteraction = "agent_interaction"
    case voiceDraft = "voice_draft"
    case verifiedDelivery = "verified_delivery"
    case evidenceInspected = "evidence_inspected"
    case proposalReviewed = "proposal_reviewed"
    case memoryReviewed = "memory_reviewed"
    case qualityWorkflow = "quality_workflow"
    case repairedCheck = "repaired_check"
    case comparedAttempts = "compared_attempts"
    case releaseReadiness = "release_readiness"
    case supervisedLoop = "supervised_loop"
}

enum AcrossLearningEventOrigin: String, Codable, Equatable {
    case taskSummary = "task_summary"
    case userInteraction = "user_interaction"
    case migration
}

struct AcrossLearningEvent: Codable, Equatable, Hashable, Identifiable {
    let eventID: String
    let kind: AcrossLearningEventKind
    let sourceID: String
    let occurredAt: Date
    let origin: AcrossLearningEventOrigin

    var id: String { eventID }

    init(
        kind: AcrossLearningEventKind,
        sourceID: String,
        occurredAt: Date = Date(),
        origin: AcrossLearningEventOrigin = .userInteraction
    ) {
        let normalizedSource = sourceID.trimmingCharacters(in: .whitespacesAndNewlines)
        self.eventID = "\(kind.rawValue):\(normalizedSource)"
        self.kind = kind
        self.sourceID = normalizedSource
        self.occurredAt = occurredAt
        self.origin = origin
    }
}

struct AcrossLearningLedger: Codable, Equatable {
    static let currentSchemaVersion = 2

    var schemaVersion: Int
    var events: [AcrossLearningEvent]

    init(schemaVersion: Int = Self.currentSchemaVersion, events: [AcrossLearningEvent] = []) {
        self.schemaVersion = schemaVersion
        self.events = Self.deduplicated(events)
    }

    private enum CodingKeys: String, CodingKey {
        case schemaVersion
        case events
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(Int.self, forKey: .schemaVersion) ?? 1
        events = Self.deduplicated(
            try container.decodeIfPresent([AcrossLearningEvent].self, forKey: .events) ?? []
        )
    }

    mutating func record(_ newEvents: [AcrossLearningEvent]) -> Bool {
        let updated = Self.deduplicated(events + newEvents)
        guard updated != events else { return false }
        events = updated
        schemaVersion = Self.currentSchemaVersion
        return true
    }

    mutating func recompute(taskEvents: [AcrossLearningEvent]) -> Bool {
        let retained = events.filter { $0.origin != .taskSummary }
        let updated = Self.deduplicated(retained + taskEvents)
        guard updated != events else { return false }
        events = updated
        schemaVersion = Self.currentSchemaVersion
        return true
    }

    static func deduplicated(_ events: [AcrossLearningEvent]) -> [AcrossLearningEvent] {
        var values: [String: AcrossLearningEvent] = [:]
        for event in events where !event.sourceID.isEmpty {
            if let existing = values[event.eventID], existing.occurredAt <= event.occurredAt {
                continue
            }
            values[event.eventID] = event
        }
        return values.values.sorted {
            if $0.occurredAt == $1.occurredAt { return $0.eventID < $1.eventID }
            return $0.occurredAt < $1.occurredAt
        }
    }
}

@MainActor
final class AcrossLearningProgressStore: ObservableObject {
    static let shared = AcrossLearningProgressStore()

    @Published private(set) var ledger: AcrossLearningLedger
    @Published private(set) var recoveredCorruptState = false

    private let fileURL: URL
    private let fileManager: FileManager

    init(fileURL: URL? = nil, fileManager: FileManager = .default) {
        self.fileManager = fileManager
        self.fileURL = fileURL ?? Self.defaultFileURL(fileManager: fileManager)
        self.ledger = AcrossLearningLedger()
        load()
    }

    var events: [AcrossLearningEvent] { ledger.events }

    @discardableResult
    func record(_ events: [AcrossLearningEvent]) -> Bool {
        guard ledger.record(events) else { return false }
        persist()
        return true
    }

    @discardableResult
    func recompute(taskEvents: [AcrossLearningEvent]) -> Bool {
        guard ledger.recompute(taskEvents: taskEvents) else { return false }
        persist()
        return true
    }

    func reload() {
        load()
    }

    private func load() {
        guard fileManager.fileExists(atPath: fileURL.path) else {
            ledger = AcrossLearningLedger()
            recoveredCorruptState = false
            return
        }
        do {
            let data = try Data(contentsOf: fileURL)
            let decoder = JSONDecoder()
            decoder.dateDecodingStrategy = .iso8601
            let decoded = try decoder.decode(AcrossLearningLedger.self, from: data)
            guard decoded.schemaVersion <= AcrossLearningLedger.currentSchemaVersion else {
                throw CocoaError(.coderReadCorrupt)
            }
            ledger = AcrossLearningLedger(events: decoded.events)
            recoveredCorruptState = false
            if decoded.schemaVersion != AcrossLearningLedger.currentSchemaVersion {
                persist()
            }
        } catch {
            ledger = AcrossLearningLedger()
            recoveredCorruptState = true
        }
    }

    private func persist() {
        do {
            try fileManager.createDirectory(
                at: fileURL.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            encoder.dateEncodingStrategy = .iso8601
            let data = try encoder.encode(ledger)
            try data.write(to: fileURL, options: .atomic)
        } catch {
            // Progress is derived state. Keep the in-memory ledger and allow the
            // next source-event recomputation to repair persistence.
        }
    }

    private static func defaultFileURL(fileManager _: FileManager) -> URL {
        return LocalAppPaths.root
            .appendingPathComponent("learning-progress.json", isDirectory: false)
    }
}

enum AcrossMasteryLevel: String, Codable, CaseIterable, Equatable {
    case explorer
    case builder
    case reviewer
    case loopGuide = "loop_guide"

    var titleKey: String { "growth.level.\(rawValue)" }
}

enum AcrossLearningMissionKind: String, Codable, CaseIterable, Equatable, Identifiable {
    case talk
    case verifiedTask = "verified_task"
    case evidence
    case review
    case memory
    case workflow
    case repair
    case compare
    case release
    case loop

    var id: String { rawValue }
    var titleKey: String { "growth.mission.\(rawValue)" }
    var detailKey: String { "growth.mission.\(rawValue).detail" }
    var systemImage: String {
        switch self {
        case .talk: return "bubble.left.and.waveform"
        case .verifiedTask: return "checkmark.seal"
        case .evidence: return "doc.text.magnifyingglass"
        case .review: return "hand.raised"
        case .memory: return "memorychip"
        case .workflow: return "checklist"
        case .repair: return "wrench.and.screwdriver"
        case .compare: return "arrow.left.arrow.right"
        case .release: return "shippingbox"
        case .loop: return "arrow.triangle.2.circlepath"
        }
    }
}

struct AcrossLearningMission: Equatable, Identifiable {
    let kind: AcrossLearningMissionKind
    let requiredRole: AcrossProductCapabilityRole
    let eventKind: AcrossLearningEventKind
    let isAvailable: Bool
    let isComplete: Bool
    let isChallenge: Bool

    var id: AcrossLearningMissionKind { kind }
}

struct AcrossLearningProgressSnapshot: Equatable {
    let level: AcrossMasteryLevel
    let missions: [AcrossLearningMission]
    let completedEventKinds: Set<AcrossLearningEventKind>

    var recommendedMission: AcrossLearningMission? {
        missions.first { $0.isAvailable && !$0.isComplete && !$0.isChallenge }
            ?? missions.first { $0.isAvailable && !$0.isComplete }
    }
}

enum AcrossLearningProgressEngine {
    static func snapshot(
        events: [AcrossLearningEvent],
        capabilities: [AcrossProductCapability]
    ) -> AcrossLearningProgressSnapshot {
        let completedKinds = Set(events.map(\.kind))
        let availableRoles = Set(capabilities.filter(\.isVerified).map(\.role))
        let definitions: [(AcrossLearningMissionKind, AcrossProductCapabilityRole, AcrossLearningEventKind, Bool)] = [
            (.talk, .agent, .agentInteraction, false),
            (.verifiedTask, .agent, .verifiedDelivery, false),
            (.evidence, .workflows, .evidenceInspected, false),
            (.review, .workflows, .proposalReviewed, false),
            (.memory, .sharedMemory, .memoryReviewed, false),
            (.workflow, .workflows, .qualityWorkflow, false),
            (.repair, .workflows, .repairedCheck, false),
            (.compare, .workflows, .comparedAttempts, false),
            (.release, .workflows, .releaseReadiness, true),
            (.loop, .selfIteration, .supervisedLoop, true),
        ]
        let missions = definitions.map { kind, role, event, challenge in
            AcrossLearningMission(
                kind: kind,
                requiredRole: role,
                eventKind: event,
                isAvailable: availableRoles.contains(role),
                isComplete: completedKinds.contains(event),
                isChallenge: challenge
            )
        }
        let level: AcrossMasteryLevel
        switch completedKinds.count {
        case 0...1: level = .explorer
        case 2...4: level = .builder
        case 5...7: level = .reviewer
        default: level = .loopGuide
        }
        return AcrossLearningProgressSnapshot(
            level: level,
            missions: missions,
            completedEventKinds: completedKinds
        )
    }

    static func taskEvents(from tasks: [TaskOrchestrationTaskSummary]) -> [AcrossLearningEvent] {
        tasks.flatMap { task -> [AcrossLearningEvent] in
            let date = task.acceptedAt.map(Date.init(timeIntervalSince1970:)) ?? Date(timeIntervalSince1970: 0)
            var values: [AcrossLearningEvent] = []
            if ["accepted", "approved", "rejected"].contains(normalized(task.reviewStatus)) {
                values.append(AcrossLearningEvent(kind: .proposalReviewed, sourceID: task.taskId, occurredAt: date, origin: .taskSummary))
            }
            if ["accepted", "approved"].contains(normalized(task.reviewStatus)), task.status == "completed" {
                values.append(AcrossLearningEvent(kind: .verifiedDelivery, sourceID: task.taskId, occurredAt: date, origin: .taskSummary))
            }
            if task.status == "completed", task.totalCount > 0, task.completedCount == task.totalCount {
                values.append(AcrossLearningEvent(kind: .qualityWorkflow, sourceID: task.taskId, occurredAt: date, origin: .taskSummary))
            }
            return values
        }
    }

    private static func normalized(_ value: String) -> String {
        value.lowercased().filter(\.isLetter)
    }
}
