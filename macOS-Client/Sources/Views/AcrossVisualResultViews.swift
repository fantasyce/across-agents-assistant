import SwiftUI

struct AcrossTaskResultOverview: View {
    let task: TaskOrchestrationTaskDetail
    @ObservedObject var preferences: AppPreferences
    @ObservedObject var viewModel: TaskOrchestrationViewModel
    let allowsAcceptance: Bool
    let onOpenEvidence: () -> Void

    init(
        task: TaskOrchestrationTaskDetail,
        preferences: AppPreferences,
        viewModel: TaskOrchestrationViewModel,
        allowsAcceptance: Bool = true,
        onOpenEvidence: @escaping () -> Void
    ) {
        self.task = task
        _preferences = ObservedObject(wrappedValue: preferences)
        _viewModel = ObservedObject(wrappedValue: viewModel)
        self.allowsAcceptance = allowsAcceptance
        self.onOpenEvidence = onOpenEvidence
    }

    var body: some View {
        let decision = AcrossTaskResultDecision(task: task)
        AcrossVisualResultOverview(
            contract: AcrossVisualResultFactory.make(task: task),
            preferences: preferences,
            primaryActionTitle: primaryActionTitle(decision),
            primaryActionSystemImage: primaryActionSystemImage(decision),
            isPrimaryActionDisabled: viewModel.isAcceptingTask || viewModel.isRejectingTask,
            isPrimaryActionLoading: viewModel.isAcceptingTask || viewModel.isRejectingTask,
            onPrimaryAction: primaryAction(decision),
            destructiveActionTitle: decision.canAccept && decision.canReject
                ? preferences.text("tasks.review.reject")
                : nil,
            isDestructiveActionDisabled: viewModel.isAcceptingTask || viewModel.isRejectingTask,
            onDestructiveAction: decision.canAccept && decision.canReject
                ? { viewModel.rejectTaskResult(task.taskId) {} }
                : nil,
            secondaryActionTitle: decision.canInspectEvidence
                ? preferences.text("tasks.evidence.view")
                : nil,
            onSecondaryAction: decision.canInspectEvidence ? onOpenEvidence : nil
        )
    }

    private func primaryActionTitle(_ decision: AcrossTaskResultDecision) -> String? {
        if decision.canAccept && allowsAcceptance {
            return preferences.text("tasks.review.accept")
        }
        if decision.canReject && allowsAcceptance {
            return preferences.text("tasks.review.reject")
        }
        return nil
    }

    private func primaryActionSystemImage(_ decision: AcrossTaskResultDecision) -> String {
        decision.canReject ? "xmark" : "checkmark"
    }

    private func primaryAction(_ decision: AcrossTaskResultDecision) -> (() -> Void)? {
        if decision.canAccept && allowsAcceptance {
            return { viewModel.acceptTaskResult(task.taskId) {} }
        }
        if decision.canReject && allowsAcceptance {
            return { viewModel.rejectTaskResult(task.taskId) {} }
        }
        return nil
    }
}

struct AcrossVisualResultOverview: View {
    let contract: AcrossVisualResultContract
    @ObservedObject var preferences: AppPreferences

    private let primaryActionTitle: String?
    private let primaryActionSystemImage: String
    private let isPrimaryActionDisabled: Bool
    private let isPrimaryActionLoading: Bool
    private let onPrimaryAction: (() -> Void)?
    private let destructiveActionTitle: String?
    private let isDestructiveActionDisabled: Bool
    private let onDestructiveAction: (() -> Void)?
    private let secondaryActionTitle: String?
    private let secondaryActionSystemImage: String
    private let onSecondaryAction: (() -> Void)?

    init(
        contract: AcrossVisualResultContract,
        preferences: AppPreferences,
        primaryActionTitle: String? = nil,
        primaryActionSystemImage: String = "checkmark",
        isPrimaryActionDisabled: Bool = false,
        isPrimaryActionLoading: Bool = false,
        onPrimaryAction: (() -> Void)? = nil,
        destructiveActionTitle: String? = nil,
        isDestructiveActionDisabled: Bool = false,
        onDestructiveAction: (() -> Void)? = nil,
        secondaryActionTitle: String? = nil,
        secondaryActionSystemImage: String = "doc.text.magnifyingglass",
        onSecondaryAction: (() -> Void)? = nil
    ) {
        self.contract = contract
        _preferences = ObservedObject(wrappedValue: preferences)
        self.primaryActionTitle = primaryActionTitle
        self.primaryActionSystemImage = primaryActionSystemImage
        self.isPrimaryActionDisabled = isPrimaryActionDisabled
        self.isPrimaryActionLoading = isPrimaryActionLoading
        self.onPrimaryAction = onPrimaryAction
        self.destructiveActionTitle = destructiveActionTitle
        self.isDestructiveActionDisabled = isDestructiveActionDisabled
        self.onDestructiveAction = onDestructiveAction
        self.secondaryActionTitle = secondaryActionTitle
        self.secondaryActionSystemImage = secondaryActionSystemImage
        self.onSecondaryAction = onSecondaryAction
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            verdictHeader

            Text(preferences.text(guidanceKey))
                .font(.system(size: 13))
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            if !hasActions {
                Label(
                    preferences.text(contract.nextAction.titleKey),
                    systemImage: contract.nextAction.systemImage
                )
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(.secondary)
            }

        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(preferences.text("result.accessibility.summary"))
    }

    private var verdictHeader: some View {
        HStack(spacing: 12) {
            HStack(spacing: 12) {
                Image(systemName: contract.verdict.systemImage)
                    .font(.system(size: 25, weight: .semibold))
                    .foregroundStyle(stateColor(verdictState))
                    .frame(width: 32, height: 32)
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 3) {
                    Text(preferences.text(contract.verdict.titleKey))
                        .font(.system(size: 20, weight: .semibold))
                    if contract.verdict == .needsReview {
                        Label(
                            preferences.text("result.review.awaiting"),
                            systemImage: "hand.raised.fill"
                        )
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(stateColor(.partial))
                        .lineLimit(1)
                    } else {
                        AcrossEvidenceStateGlyph(state: verdictState, preferences: preferences)
                    }
                }
            }
            .accessibilityElement(children: .combine)

            Spacer(minLength: 16)

            if hasActions {
                actionRow
            }
        }
    }

    @ViewBuilder
    private var actionRow: some View {
        HStack(spacing: 8) {
            if let secondaryActionTitle, let onSecondaryAction {
                Button(action: onSecondaryAction) {
                    Label(secondaryActionTitle, systemImage: secondaryActionSystemImage)
                }
                .buttonStyle(.bordered)
                .focusable(true)
                .onKeyPress(.return) {
                    onSecondaryAction()
                    return .handled
                }
            }
            if let destructiveActionTitle, let onDestructiveAction {
                Button(role: .destructive, action: onDestructiveAction) {
                    Label(destructiveActionTitle, systemImage: "xmark")
                }
                .buttonStyle(.bordered)
                .disabled(isDestructiveActionDisabled)
                .focusable(true)
                .onKeyPress(.return) {
                    guard !isDestructiveActionDisabled else { return .ignored }
                    onDestructiveAction()
                    return .handled
                }
            }
            if let primaryActionTitle, let onPrimaryAction {
                Button(action: onPrimaryAction) {
                    if isPrimaryActionLoading {
                        ProgressView()
                            .controlSize(.small)
                            .accessibilityLabel(primaryActionTitle)
                    } else {
                        Label(primaryActionTitle, systemImage: primaryActionSystemImage)
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(isPrimaryActionDisabled || isPrimaryActionLoading)
                .focusable(true)
                .onKeyPress(.return) {
                    guard !isPrimaryActionDisabled, !isPrimaryActionLoading else { return .ignored }
                    onPrimaryAction()
                    return .handled
                }
            }
        }
        .controlSize(.regular)
    }

    private var hasActions: Bool {
        (primaryActionTitle != nil && onPrimaryAction != nil)
            || (destructiveActionTitle != nil && onDestructiveAction != nil)
            || (secondaryActionTitle != nil && onSecondaryAction != nil)
    }

    private var guidanceKey: String {
        "result.verdict.guidance.\(contract.verdict.rawValue)"
    }

    private var verdictState: AcrossEvidenceState {
        switch contract.verdict {
        case .ready: return .confirmed
        case .needsReview, .inProgress: return .partial
        case .blocked, .cancelled: return .blocked
        }
    }

}

struct AcrossTrustCompassView: View {
    let compass: AcrossTrustCompass
    @ObservedObject var preferences: AppPreferences

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(preferences.text("result.trust.title"))
                .font(.system(size: 11, weight: .semibold))
            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 240), spacing: 18)],
                spacing: 8
            ) {
                ForEach(AcrossTrustDimension.allCases) { dimension in
                    let state = compass.state(for: dimension)
                    HStack(spacing: 7) {
                        Image(systemName: dimension.systemImage)
                            .foregroundStyle(stateColor(state))
                            .accessibilityHidden(true)
                        Text(preferences.text(dimension.titleKey))
                            .font(.system(size: 11, weight: .medium))
                            .lineLimit(1)
                        Spacer(minLength: 8)
                        Label(
                            trustStateText(dimension: dimension, state: state),
                            systemImage: stateGlyph(state)
                        )
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(stateColor(state))
                        .lineLimit(1)
                    }
                    .frame(maxWidth: .infinity)
                    .accessibilityElement(children: .combine)
                    .accessibilityLabel(preferences.text(dimension.titleKey))
                    .accessibilityValue(trustStateText(dimension: dimension, state: state))
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(preferences.text("result.trust.title"))
    }

    private func trustStateText(
        dimension: AcrossTrustDimension,
        state: AcrossEvidenceState
    ) -> String {
        if dimension == .humanControl && state == .partial {
            return preferences.text("result.review.awaiting")
        }
        return preferences.text(state.accessibilityKey)
    }
}

struct AcrossEvidenceRouteView: View {
    let constellation: AcrossEvidenceConstellation
    @ObservedObject var preferences: AppPreferences

    private var routeNodes: [AcrossEvidenceNode] {
        constellation.nodes.filter { $0.kind != .memory && ($0.referenceCount > 0 || $0.state != .missing) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            Text(preferences.text("result.evidence.route"))
                .font(.system(size: 12, weight: .semibold))
            HStack(spacing: 6) {
                ForEach(Array(routeNodes.enumerated()), id: \.element.id) { index, node in
                    VStack(spacing: 4) {
                        Image(systemName: node.kind.systemImage)
                            .font(.system(size: 13, weight: .medium))
                            .foregroundStyle(stateColor(node.state))
                            .frame(width: 24, height: 24)
                            .background(stateColor(node.state).opacity(0.09))
                            .clipShape(Circle())
                            .accessibilityHidden(true)
                        Text(preferences.text(node.kind.titleKey))
                            .font(.system(size: 10, weight: .medium))
                            .lineLimit(1)
                    }
                    .frame(maxWidth: .infinity)
                    .accessibilityElement(children: .combine)
                    .accessibilityValue(preferences.text(node.state.accessibilityKey))
                    if index < routeNodes.count - 1 {
                        Image(systemName: "chevron.right")
                            .font(.system(size: 8, weight: .semibold))
                            .foregroundStyle(.tertiary)
                            .accessibilityHidden(true)
                    }
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(preferences.text("result.evidence.route"))
    }
}

struct AcrossLoopTrailView: View {
    let steps: [AcrossLoopTrailStep]
    @ObservedObject var preferences: AppPreferences

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(preferences.text("result.loop.title"))
                .font(.system(size: 12, weight: .semibold))
            HStack(spacing: 4) {
                ForEach(Array(steps.enumerated()), id: \.element.id) { index, step in
                    VStack(spacing: 5) {
                        Image(systemName: loopGlyph(step.state))
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundStyle(loopColor(step.state))
                            .accessibilityHidden(true)
                        Text(preferences.text(step.stage.titleKey))
                            .font(.system(size: 10, weight: .medium))
                    }
                    .frame(maxWidth: .infinity)
                    .accessibilityElement(children: .combine)
                    .accessibilityValue(preferences.text("result.loop.state.\(step.state.rawValue)"))
                    if index < steps.count - 1 {
                        Rectangle()
                            .fill(AcrossTheme.accent.opacity(0.22))
                            .frame(height: 1)
                            .accessibilityHidden(true)
                    }
                }
            }
        }
    }
}

struct AcrossEvidenceConstellationView: View {
    let constellation: AcrossEvidenceConstellation
    @ObservedObject var preferences: AppPreferences

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(preferences.text("result.evidence.constellation"))
                .font(.system(size: 12, weight: .semibold))
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 104), spacing: 8)], spacing: 8) {
                ForEach(constellation.nodes) { node in
                    HStack(spacing: 7) {
                        Image(systemName: node.kind.systemImage)
                            .foregroundStyle(stateColor(node.state))
                            .accessibilityHidden(true)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(preferences.text(node.kind.titleKey))
                                .font(.system(size: 11, weight: .medium))
                            Text(node.referenceCount == 0 ? "—" : "\(node.referenceCount)")
                                .font(.system(size: 10, design: .monospaced))
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                    }
                    .padding(8)
                    .background(Color.secondary.opacity(0.05))
                    .clipShape(RoundedRectangle(cornerRadius: 6))
                    .accessibilityElement(children: .combine)
                    .accessibilityValue(preferences.text(node.state.accessibilityKey))
                }
            }
        }
    }
}

struct AcrossAttentionStackView: View {
    let items: [AcrossAttentionItem]
    @ObservedObject var preferences: AppPreferences

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(preferences.text("result.attention.title"))
                .font(.system(size: 12, weight: .semibold))
            ForEach(items) { item in
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: attentionGlyph(item.priority))
                        .foregroundStyle(attentionColor(item.priority))
                        .accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(preferences.text(item.priority.titleKey))
                            .font(.system(size: 10, weight: .medium))
                            .foregroundStyle(.secondary)
                        Text(preferences.text(item.titleKey))
                            .font(.system(size: 11, weight: .medium))
                        if let detail = item.detail, !detail.isEmpty {
                            Text(localizedDetail(detail))
                                .font(.system(size: 10))
                                .foregroundStyle(.secondary)
                                .lineLimit(2)
                        }
                    }
                    Spacer()
                }
                .padding(8)
                .background(attentionColor(item.priority).opacity(0.07))
                .clipShape(RoundedRectangle(cornerRadius: 6))
                .accessibilityElement(children: .combine)
            }
        }
    }

    private func localizedDetail(_ detail: String) -> String {
        let key = "result.attention.detail.\(detail)"
        let localized = preferences.text(key)
        return localized == key ? detail : localized
    }
}

struct AcrossAttemptLensView: View {
    let lens: AcrossAttemptLens
    @ObservedObject var preferences: AppPreferences

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(preferences.text("result.attempt.title"))
                .font(.system(size: 12, weight: .semibold))
            ForEach(lens.changes) { change in
                HStack(spacing: 8) {
                    Image(systemName: attemptGlyph(change.state))
                        .foregroundStyle(attemptColor(change.state))
                        .accessibilityHidden(true)
                    Text(attemptTitle(change))
                        .font(.system(size: 11, weight: .medium))
                    Spacer()
                    Text(preferences.text("result.attempt.\(change.state.rawValue)"))
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(attemptColor(change.state))
                }
                .accessibilityElement(children: .combine)
            }
        }
    }

    private func attemptTitle(_ change: AcrossAttemptChange) -> String {
        let key = "result.attempt.dimension.\(change.id)"
        let localized = preferences.text(key)
        return localized == key ? change.title : localized
    }
}

struct AcrossDecisionMarkView: View {
    let mark: AcrossDecisionMark
    @ObservedObject var preferences: AppPreferences

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(preferences.text("result.decision.title"))
                    .font(.system(size: 12, weight: .semibold))
                Spacer()
                AcrossEvidenceStateGlyph(state: mark.state, preferences: preferences)
            }
            decisionRow("result.decision.scope", mark.scope)
            decisionRow("result.decision.proposer", mark.proposer)
            decisionRow("result.decision.approver", mark.approver)
            decisionRow("result.decision.hash", mark.evidenceHash)
        }
        .padding(10)
        .background(Color.secondary.opacity(0.05))
        .clipShape(RoundedRectangle(cornerRadius: 7))
        .accessibilityElement(children: .contain)
    }

    private func decisionRow(_ key: String, _ value: String?) -> some View {
        HStack {
            Text(preferences.text(key))
                .font(.system(size: 10))
                .foregroundStyle(.secondary)
            Spacer()
            Text(value?.isEmpty == false ? value! : preferences.text("result.unavailable"))
                .font(.system(size: 10, weight: .medium, design: value == mark.evidenceHash ? .monospaced : .default))
                .lineLimit(1)
                .truncationMode(.middle)
        }
    }
}

struct AcrossEvidenceStateGlyph: View {
    let state: AcrossEvidenceState
    @ObservedObject var preferences: AppPreferences

    var body: some View {
        Label(preferences.text(state.accessibilityKey), systemImage: stateGlyph(state))
            .font(.system(size: 10, weight: .semibold))
            .foregroundStyle(stateColor(state))
            .lineLimit(1)
    }
}

private func stateColor(_ state: AcrossEvidenceState) -> Color {
    switch state {
    case .confirmed: return Color(hex: "#248A3D")
    case .partial: return Color(hex: "#C47700")
    case .missing: return Color(hex: "#6E6E73")
    case .blocked: return Color(hex: "#D70015")
    }
}

private func stateGlyph(_ state: AcrossEvidenceState) -> String {
    switch state {
    case .confirmed: return "checkmark.circle.fill"
    case .partial: return "circle.lefthalf.filled"
    case .missing: return "minus.circle"
    case .blocked: return "xmark.octagon.fill"
    }
}

private func loopGlyph(_ state: AcrossLoopStageState) -> String {
    switch state {
    case .pending: return "circle"
    case .active: return "circle.dotted"
    case .complete: return "checkmark.circle.fill"
    case .blocked: return "xmark.octagon.fill"
    }
}

private func loopColor(_ state: AcrossLoopStageState) -> Color {
    switch state {
    case .pending: return .secondary
    case .active: return AcrossTheme.accent
    case .complete: return Color(hex: "#248A3D")
    case .blocked: return Color(hex: "#D70015")
    }
}

private func attentionGlyph(_ priority: AcrossAttentionPriority) -> String {
    switch priority {
    case .actNow: return "exclamationmark.circle.fill"
    case .inspectSoon: return "eye.circle"
    case .contextOnly: return "info.circle"
    }
}

private func attentionColor(_ priority: AcrossAttentionPriority) -> Color {
    switch priority {
    case .actNow: return Color(hex: "#D70015")
    case .inspectSoon: return Color(hex: "#C47700")
    case .contextOnly: return AcrossTheme.accent
    }
}

private func attemptGlyph(_ state: AcrossAttemptChangeState) -> String {
    switch state {
    case .improved: return "arrow.up.right.circle.fill"
    case .unchanged: return "equal.circle"
    case .regressed: return "arrow.down.right.circle.fill"
    case .introduced: return "plus.circle.fill"
    }
}

private func attemptColor(_ state: AcrossAttemptChangeState) -> Color {
    switch state {
    case .improved: return Color(hex: "#248A3D")
    case .unchanged: return .secondary
    case .regressed: return Color(hex: "#D70015")
    case .introduced: return AcrossTheme.accent
    }
}
