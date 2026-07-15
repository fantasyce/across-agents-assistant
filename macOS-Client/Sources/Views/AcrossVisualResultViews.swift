import SwiftUI

struct AcrossVisualResultOverview: View {
    let contract: AcrossVisualResultContract
    @ObservedObject var preferences: AppPreferences

    @State private var showsDetails = false
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.accessibilityReduceMotion) private var systemReduceMotion

    private var reducesMotion: Bool { systemReduceMotion || preferences.reduceMotion }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            verdictHeader
            Divider()
            AcrossTrustCompassView(compass: contract.trustCompass, preferences: preferences)
            Divider()
            AcrossEvidenceRouteView(
                constellation: contract.evidenceConstellation,
                preferences: preferences
            )
            nextActionRow

            DisclosureGroup(isExpanded: $showsDetails) {
                VStack(alignment: .leading, spacing: 16) {
                    AcrossLoopTrailView(steps: contract.loopTrail, preferences: preferences)
                    AcrossEvidenceConstellationView(
                        constellation: contract.evidenceConstellation,
                        preferences: preferences
                    )
                    AcrossAttentionStackView(items: contract.attentionStack, preferences: preferences)
                    if let lens = contract.attemptLens {
                        AcrossAttemptLensView(lens: lens, preferences: preferences)
                    }
                    if let mark = contract.decisionMark {
                        AcrossDecisionMarkView(mark: mark, preferences: preferences)
                    }
                }
                .padding(.top, 12)
            } label: {
                Label(preferences.text("result.details"), systemImage: "slider.horizontal.3")
                    .font(.system(size: 12, weight: .medium))
            }
            .animation(reducesMotion ? nil : .easeOut(duration: 0.2), value: showsDetails)
        }
        .padding(16)
        .background(AcrossTheme.recessedFill(for: colorScheme))
        .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.cardCornerRadius, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AcrossTheme.Metrics.cardCornerRadius, style: .continuous)
                .stroke(AcrossTheme.separator(for: colorScheme), lineWidth: 1)
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(preferences.text("result.accessibility.summary"))
    }

    private var verdictHeader: some View {
        HStack(spacing: 10) {
            Group {
                if let trustSealIndex {
                    PixelAtlasReward(
                        atlas: .trustSeals,
                        index: trustSealIndex,
                        isUnlocked: true
                    )
                } else {
                    Image(systemName: contract.verdict.systemImage)
                        .font(.system(size: 22, weight: .semibold))
                        .foregroundStyle(stateColor(verdictState))
                        .symbolEffect(.appear, options: .nonRepeating, isActive: !reducesMotion)
                }
            }
            .frame(width: 46, height: 46)
            .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(preferences.text(contract.verdict.titleKey))
                    .font(.system(size: 18, weight: .semibold))
                Text(preferences.text("result.verdict.subtitle"))
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
            }
            Spacer()
            AcrossEvidenceStateGlyph(state: verdictState, preferences: preferences)
        }
        .accessibilityElement(children: .combine)
    }

    private var nextActionRow: some View {
        HStack(spacing: 10) {
            Image(systemName: contract.nextAction.systemImage)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(AcrossTheme.accent)
                .frame(width: 24, height: 24)
                .accessibilityHidden(true)
            Text(preferences.text("result.next.label"))
                .font(.system(size: 11, weight: .medium))
                .foregroundStyle(.secondary)
            Text(preferences.text(contract.nextAction.titleKey))
                .font(.system(size: 13, weight: .semibold))
            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background(AcrossTheme.accent.opacity(colorScheme == .dark ? 0.16 : 0.09))
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        .accessibilityElement(children: .combine)
    }

    private var verdictState: AcrossEvidenceState {
        switch contract.verdict {
        case .ready: return .confirmed
        case .needsReview, .inProgress: return .partial
        case .blocked, .cancelled: return .blocked
        }
    }

    private var trustSealIndex: Int? {
        switch contract.verdict {
        case .ready: return 0
        case .needsReview: return 1
        case .blocked, .cancelled: return 2
        case .inProgress: return nil
        }
    }
}

struct AcrossTrustCompassView: View {
    let compass: AcrossTrustCompass
    @ObservedObject var preferences: AppPreferences

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            Text(preferences.text("result.trust.title"))
                .font(.system(size: 12, weight: .semibold))
            HStack(spacing: 8) {
                ForEach(AcrossTrustDimension.allCases) { dimension in
                    let state = compass.state(for: dimension)
                    VStack(alignment: .leading, spacing: 6) {
                        HStack(spacing: 6) {
                            Image(systemName: dimension.systemImage)
                                .accessibilityHidden(true)
                            Text(preferences.text(dimension.titleKey))
                                .lineLimit(1)
                        }
                        .font(.system(size: 11, weight: .medium))
                        AcrossEvidenceStateGlyph(state: state, preferences: preferences)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(9)
                    .background(stateColor(state).opacity(0.08))
                    .clipShape(RoundedRectangle(cornerRadius: 7, style: .continuous))
                    .accessibilityElement(children: .combine)
                    .accessibilityLabel(preferences.text(dimension.titleKey))
                    .accessibilityValue(preferences.text(state.accessibilityKey))
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(preferences.text("result.trust.title"))
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
