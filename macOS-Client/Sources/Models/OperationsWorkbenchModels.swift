import Foundation

enum OperationsJSONValue: Codable, Equatable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: OperationsJSONValue])
    case array([OperationsJSONValue])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([String: OperationsJSONValue].self) {
            self = .object(value)
        } else {
            self = .array(try container.decode([OperationsJSONValue].self))
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let value): try container.encode(value)
        case .number(let value): try container.encode(value)
        case .bool(let value): try container.encode(value)
        case .object(let value): try container.encode(value)
        case .array(let value): try container.encode(value)
        case .null: try container.encodeNil()
        }
    }

    var displayText: String {
        switch self {
        case .string(let value): return value
        case .number(let value):
            return value.rounded() == value ? String(Int(value)) : String(value)
        case .bool(let value): return value ? "true" : "false"
        case .object(let value):
            return value.keys.sorted().map { "\($0)=\(value[$0]?.displayText ?? "-")" }.joined(separator: ", ")
        case .array(let value): return value.map(\.displayText).joined(separator: ", ")
        case .null: return "-"
        }
    }
}

enum OperationsWorkbenchSurface: String, CaseIterable, Identifiable {
    case workspaces
    case qualityGate
    case evidence
    case memory
    case autopilot
    case achievements
    case assist

    var id: String { rawValue }

    static let primary: [OperationsWorkbenchSurface] = [
        .assist,
    ]

    var localizationKey: String {
        switch self {
        case .workspaces: return "operations.workspaces"
        case .qualityGate: return "operations.qualityGate"
        case .evidence: return "operations.evidence"
        case .memory: return "operations.memory"
        case .autopilot: return "operations.autopilot"
        case .achievements: return "operations.achievements"
        case .assist: return "operations.assist"
        }
    }

    var systemName: String {
        switch self {
        case .workspaces: return "folder"
        case .qualityGate: return "play.circle"
        case .evidence: return "doc.text.magnifyingglass"
        case .memory: return "memorychip"
        case .autopilot: return "arrow.triangle.2.circlepath"
        case .achievements: return "flag.checkered"
        case .assist: return "checkmark.circle"
        }
    }
}

enum WorkspacePaneKind: String, CaseIterable, Identifiable, Hashable {
    case output
    case toolCalls
    case changes
    case providerUsage
    case evidence
    case approval

    var id: String { rawValue }

    var localizationKey: String {
        switch self {
        case .output: return "workspace.pane.output"
        case .toolCalls: return "workspace.pane.tools"
        case .changes: return "workspace.pane.changes"
        case .providerUsage: return "workspace.pane.provider"
        case .evidence: return "workspace.pane.evidence"
        case .approval: return "workspace.pane.approval"
        }
    }

    var systemName: String {
        switch self {
        case .output: return "terminal"
        case .toolCalls: return "wrench.and.screwdriver"
        case .changes: return "arrow.triangle.branch"
        case .providerUsage: return "gauge.with.dots.needle.50percent"
        case .evidence: return "doc.text.magnifyingglass"
        case .approval: return "person.badge.shield.checkmark"
        }
    }
}

struct WorkspaceLogChunk: Identifiable, Equatable {
    enum Stream: String, Equatable {
        case stdout
        case stderr
        case system
    }

    let id: UUID
    let stream: Stream
    let text: String
    let timestamp: String?

    init(id: UUID = UUID(), stream: Stream, text: String, timestamp: String? = nil) {
        self.id = id
        self.stream = stream
        self.text = text
        self.timestamp = timestamp
    }
}

struct BoundedWorkspaceLog: Equatable {
    private(set) var chunks: [WorkspaceLogChunk] = []
    private(set) var didTruncate = false
    let maxChunks: Int
    let maxCharacters: Int

    init(maxChunks: Int = 200, maxCharacters: Int = 64_000) {
        self.maxChunks = max(1, maxChunks)
        self.maxCharacters = max(256, maxCharacters)
    }

    var characterCount: Int {
        chunks.reduce(0) { $0 + $1.text.count }
    }

    mutating func append(_ chunk: WorkspaceLogChunk) {
        let boundedText = String(chunk.text.suffix(maxCharacters))
        if boundedText.count < chunk.text.count {
            didTruncate = true
        }
        chunks.append(
            WorkspaceLogChunk(
                id: chunk.id,
                stream: chunk.stream,
                text: boundedText,
                timestamp: chunk.timestamp
            )
        )

        while chunks.count > maxChunks || characterCount > maxCharacters {
            chunks.removeFirst()
            didTruncate = true
        }
    }
}

enum WorkspaceFixtureState: String, CaseIterable {
    case healthy
    case attention
    case failed

    var status: String {
        switch self {
        case .healthy: return "running"
        case .attention: return "attention"
        case .failed: return "failed"
        }
    }
}

enum WorkspaceVisualTheme: String, CaseIterable {
    case light
    case dark
}

enum WorkspaceVisualLocale: String, CaseIterable {
    case english = "en"
    case simplifiedChinese = "zh-Hans"
}

enum WorkspaceVisualState: String, CaseIterable {
    case loading
    case empty
    case error
    case blocked
    case success
}

struct WorkspaceVisualFixture: Identifiable, Equatable {
    let theme: WorkspaceVisualTheme
    let locale: WorkspaceVisualLocale
    let state: WorkspaceVisualState

    var id: String { "\(theme.rawValue)-\(locale.rawValue)-\(state.rawValue)" }

    static let completeMatrix: [WorkspaceVisualFixture] = WorkspaceVisualTheme.allCases.flatMap { theme in
        WorkspaceVisualLocale.allCases.flatMap { locale in
            WorkspaceVisualState.allCases.map { state in
                WorkspaceVisualFixture(theme: theme, locale: locale, state: state)
            }
        }
    }
}

enum OperationalContentState: Equatable {
    case loading
    case empty
    case error(String)
    case active(String)
    case disabled(String)
    case success(String)

    static let behaviorFixtures: [OperationalContentState] = [
        .loading,
        .empty,
        .error("error"),
        .active("active"),
        .disabled("disabled"),
        .success("success"),
    ]
}

enum OperationsRequestError: LocalizedError, Equatable {
    case invalidInput(String)
    case http(Int, String)
    case invalidResponse

    var errorDescription: String? {
        switch self {
        case .invalidInput(let message): return message
        case .http(_, let message): return message
        case .invalidResponse: return "The backend returned an invalid response."
        }
    }
}

enum OperationsHTTP {
    static func validate(_ response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse else {
            throw OperationsRequestError.invalidResponse
        }
        guard (200..<300).contains(http.statusCode) else {
            throw OperationsRequestError.http(http.statusCode, errorMessage(from: data) ?? "HTTP \(http.statusCode)")
        }
    }

    private static func errorMessage(from data: Data) -> String? {
        guard let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        if let detail = root["detail"] as? String, !detail.isEmpty {
            return detail
        }
        if let detail = root["detail"] as? [String: Any] {
            let code = detail["code"] as? String
            let message = detail["message"] as? String
            return [code, message].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: ": ").nilIfEmpty
        }
        return nil
    }
}

private extension String {
    var nilIfEmpty: String? { isEmpty ? nil : self }
}

struct WorkspacePaneFixture: Identifiable, Equatable {
    let id: String
    let kind: WorkspacePaneKind
    let title: String
    let detail: String
    let status: String
}

struct WorkspaceRunFixture: Equatable {
    let state: WorkspaceFixtureState
    let agentStatus: String
    let paneStates: [WorkspacePaneFixture]

    static func make(_ state: WorkspaceFixtureState) -> WorkspaceRunFixture {
        let common: [(WorkspacePaneKind, String)] = [
            (.output, "stdout / stderr"),
            (.toolCalls, "tool calls"),
            (.changes, "files and diff"),
            (.providerUsage, "provider and usage"),
            (.evidence, "evidence links"),
            (.approval, "approval and promotion"),
        ]
        return WorkspaceRunFixture(
            state: state,
            agentStatus: state.status,
            paneStates: common.map { kind, detail in
                WorkspacePaneFixture(
                    id: kind.rawValue,
                    kind: kind,
                    title: kind.rawValue,
                    detail: detail,
                    status: state.status
                )
            }
        )
    }
}

enum HumanReviewKind: String, CaseIterable, Identifiable {
    case promotion
    case pendingMemory
    case blockingGate
    case manualGate
    case skippedGate
    case permission
    case pluginRepair

    var id: String { rawValue }

    var priority: Int {
        switch self {
        case .blockingGate: return 0
        case .permission, .promotion: return 1
        case .manualGate, .pluginRepair: return 2
        case .pendingMemory: return 3
        case .skippedGate: return 4
        }
    }

    var localizationKey: String {
        "review.kind.\(rawValue)"
    }
}

struct HumanReviewSignal: Identifiable, Equatable {
    let id: String
    let kind: HumanReviewKind
    let title: String
    let detail: String
    let status: String
    let source: String

    var attentionSurface: OperationsWorkbenchSurface? {
        let normalizedSource = source.lowercased()
        switch kind {
        case .pendingMemory:
            return .memory
        case .permission:
            return normalizedSource == "assist" ? .assist : nil
        case .promotion, .blockingGate, .manualGate, .skippedGate:
            return normalizedSource.contains("agent loop") ? .autopilot : .qualityGate
        case .pluginRepair:
            return nil
        }
    }

    var needsSettingsAttention: Bool {
        switch kind {
        case .pluginRepair:
            return true
        case .permission:
            return source.lowercased() != "assist"
        case .promotion, .pendingMemory, .blockingGate, .manualGate, .skippedGate:
            return false
        }
    }
}

struct HumanReviewQueueSnapshot: Equatable {
    let items: [HumanReviewSignal]

    init(signals: [HumanReviewSignal]) {
        items = signals
            .filter { HumanReviewQueueSnapshot.needsReview($0) }
            .sorted {
                if $0.kind.priority == $1.kind.priority {
                    return $0.title.localizedCaseInsensitiveCompare($1.title) == .orderedAscending
                }
                return $0.kind.priority < $1.kind.priority
            }
    }

    var totalCount: Int { items.count }

    var blockingCount: Int {
        items.filter { $0.kind == .blockingGate || StatusPaletteKey.isBlocking($0.status) }.count
    }

    var attentionSurfaces: Set<OperationsWorkbenchSurface> {
        Set(items.compactMap(\.attentionSurface))
    }

    var needsSettingsAttention: Bool {
        items.contains(where: \.needsSettingsAttention)
    }

    func count(for kind: HumanReviewKind) -> Int {
        items.filter { $0.kind == kind }.count
    }

    private static func needsReview(_ signal: HumanReviewSignal) -> Bool {
        switch signal.kind {
        case .pendingMemory, .permission, .pluginRepair, .promotion,
             .blockingGate, .manualGate, .skippedGate:
            return !StatusPaletteKey.isResolved(signal.status)
        }
    }
}

private enum StatusPaletteKey {
    static func normalized(_ value: String) -> String {
        value
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .replacingOccurrences(of: "-", with: "_")
    }

    static func isResolved(_ value: String) -> Bool {
        ["approved", "completed", "configured", "installed", "passed", "ready", "resolved", "success"]
            .contains(normalized(value))
    }

    static func isBlocking(_ value: String) -> Bool {
        ["blocked", "error", "failed", "failure", "rejected", "timeout"]
            .contains(normalized(value))
    }
}

struct AcrossIconControlContract: Equatable {
    let id: String
    let accessibilityLabel: String
    let help: String

    var isValid: Bool {
        !id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !accessibilityLabel.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !help.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
}

enum OperationsFocusTarget: String, CaseIterable, Hashable {
    case primaryNavigation
    case workspaceList
    case agentList
    case panePicker
    case diffReview
    case inlineComment
    case inspector
    case reviewQueue
    case commandToolbar
    case assistComposer

    static let workspacePath: [OperationsFocusTarget] = [
        .primaryNavigation,
        .workspaceList,
        .agentList,
        .panePicker,
        .diffReview,
        .inlineComment,
        .inspector,
        .commandToolbar,
    ]

    static let reviewPath: [OperationsFocusTarget] = [
        .primaryNavigation,
        .reviewQueue,
        .inspector,
        .commandToolbar,
    ]
}

enum ApprovalDialogFocusTarget: String, CaseIterable, Hashable {
    case deny
    case allowOnce
    case alwaysAllow

    static let safeOrder: [ApprovalDialogFocusTarget] = [.deny, .allowOnce, .alwaysAllow]
}

struct ApprovalDialogAccessibilityContract: Equatable {
    let titleKey: String
    let initialFocus: ApprovalDialogFocusTarget
    let focusOrder: [ApprovalDialogFocusTarget]
    let escapeDecision: String

    static let standard = ApprovalDialogAccessibilityContract(
        titleKey: "approval.title",
        initialFocus: .deny,
        focusOrder: ApprovalDialogFocusTarget.safeOrder,
        escapeDecision: "reject"
    )

    var isValid: Bool {
        !titleKey.isEmpty
            && initialFocus == .deny
            && focusOrder == ApprovalDialogFocusTarget.safeOrder
            && Set(focusOrder).count == focusOrder.count
            && escapeDecision == "reject"
    }
}
