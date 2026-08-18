import SwiftUI

struct AcrossTaskCapabilityPresentation: Equatable {
    let summaryLine: String?
    let requiredDecisions: [AcrossTaskCapabilityContract.Decision]
    let resultState: AcrossTaskCompactResultState?
    let evidenceLines: [String]

    init(
        task: TaskOrchestrationTaskDetail,
        capabilityContract: AcrossTaskCapabilityContract? = nil
    ) {
        if let capabilityContract, !capabilityContract.capabilitiesSelected.isEmpty {
            let count = capabilityContract.capabilitiesSelected.count
            summaryLine = "\(count) capabilit\(count == 1 ? "y" : "ies") selected; verification planned"
        } else if task.hasRequirementManifest {
            summaryLine = "Capabilities selected; verification planned"
        } else if task.qualityHealth != nil || task.deliveryReport != nil {
            summaryLine = "Verification in progress"
        } else {
            summaryLine = nil
        }

        requiredDecisions = capabilityContract?.requiredDecisions ?? []

        resultState = Self.resultState(for: task)
        evidenceLines = Self.evidenceLines(for: task)
    }

    private static func resultState(for task: TaskOrchestrationTaskDetail) -> AcrossTaskCompactResultState? {
        guard TaskOrchestrationStateReducers.isTerminalStatus(task.status) else { return nil }
        let missing = task.deliveryReport?.missingRequired.count
            ?? task.qualityHealth?.manifestMissing
            ?? 0
        let failedConstraints = task.deliveryReport?.failedConstraints.count
            ?? task.qualityHealth?.deliveryQualityReport?.failedConstraints.count
            ?? 0
        if ["failed", "cancelled", "blocked"].contains(task.status)
            || missing > 0
            || (task.error?.isEmpty == false && task.status != "completed_with_failures") {
            return .blocked
        }
        if failedConstraints > 0 || task.status == "completed_with_failures" || task.reviewStatus != "accepted" {
            return .needsReview
        }
        return .ready
    }

    private static func evidenceLines(for task: TaskOrchestrationTaskDetail) -> [String] {
        var lines: [String] = []
        if let accepted = task.deliveryReport?.acceptedTotal ?? task.qualityHealth?.manifestAccepted,
           let required = task.deliveryReport?.requiredTotal ?? task.qualityHealth?.manifestRequired {
            lines.append("\(accepted) of \(required) required checks verified")
        }
        if let quality = task.deliveryReport?.qualityGate ?? task.qualityHealth?.deliveryQuality,
           !quality.isEmpty {
            lines.append("Quality: \(AcrossCapabilitySource.humanized(quality))")
        }
        if !task.artifacts.isEmpty {
            lines.append("\(task.artifacts.count) artifact\(task.artifacts.count == 1 ? "" : "s") recorded")
        }
        if lines.isEmpty, TaskOrchestrationStateReducers.isTerminalStatus(task.status) {
            lines.append("Task status and execution evidence recorded")
        }
        return lines
    }
}

struct MinimalPageHeader<Actions: View>: View {
    let title: String
    let subtitle: String?
    let backLabel: String?
    let onBack: () -> Void
    private let actions: Actions
    @Environment(\.acrossWindowLayoutSize) private var windowLayoutSize

    init(
        title: String,
        subtitle: String? = nil,
        backLabel: String? = nil,
        onBack: @escaping () -> Void = {},
        @ViewBuilder actions: () -> Actions
    ) {
        self.title = title
        self.subtitle = subtitle
        self.backLabel = backLabel
        self.onBack = onBack
        self.actions = actions()
    }

    var body: some View {
        HStack(alignment: .center, spacing: 14) {
            if let backLabel {
                MinimalIconButton(
                    systemName: "chevron.left",
                    label: backLabel,
                    action: onBack
                )
            }

            VStack(alignment: .leading, spacing: 5) {
                Text(title)
                    .font(.system(size: windowLayoutSize == .expanded ? 32 : 28, weight: .bold))
                    .lineLimit(1)

                if let subtitle, !subtitle.isEmpty {
                    Text(subtitle)
                        .font(.system(size: windowLayoutSize == .expanded ? 14 : 13))
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
            }

            Spacer(minLength: 18)
            HStack(spacing: 8) {
                actions
            }
        }
    }
}

private struct MinimalPageContentFrameModifier: ViewModifier {
    let topPadding: CGFloat
    let bottomPadding: CGFloat
    @Environment(\.acrossWindowLayoutSize) private var windowLayoutSize

    func body(content: Content) -> some View {
        content
            .frame(
                maxWidth: windowLayoutSize == .expanded
                    ? SettingsHubPageLayout.expandedContentMaxWidth
                    : SettingsHubPageLayout.contentMaxWidth,
                alignment: .leading
            )
            .padding(
                .horizontal,
                windowLayoutSize == .expanded
                    ? SettingsHubPageLayout.expandedHorizontalContentPadding
                    : SettingsHubPageLayout.horizontalContentPadding
            )
            .padding(.top, topPadding)
            .padding(.bottom, bottomPadding)
            .frame(maxWidth: .infinity, alignment: .top)
    }
}

extension View {
    func minimalPageContentFrame(
        topPadding: CGFloat = SettingsHubPageLayout.topContentPadding,
        bottomPadding: CGFloat = SettingsHubPageLayout.contentPadding
    ) -> some View {
        modifier(MinimalPageContentFrameModifier(
            topPadding: topPadding,
            bottomPadding: bottomPadding
        ))
    }
}

struct MinimalWorkflowStatusLabel: View {
    let status: String
    let label: String?
    @EnvironmentObject private var preferences: AppPreferences

    init(status: String, label: String? = nil) {
        self.status = status
        self.label = label
    }

    var body: some View {
        Label {
            Text(label ?? preferences.statusText(status))
                .lineLimit(1)
        } icon: {
            Image(systemName: StatusPalette.systemImage(for: status))
                .accessibilityHidden(true)
        }
        .font(.caption)
        .foregroundStyle(StatusPalette.tone(for: status).foreground)
        .accessibilityElement(children: .combine)
    }
}

struct MinimalWorkflowStateView: View {
    enum State {
        case loading
        case empty
        case error
        case unavailable
    }

    let state: State
    let title: String
    let detail: String?
    let actionTitle: String?
    let action: (() -> Void)?

    init(
        state: State,
        title: String,
        detail: String? = nil,
        actionTitle: String? = nil,
        action: (() -> Void)? = nil
    ) {
        self.state = state
        self.title = title
        self.detail = detail
        self.actionTitle = actionTitle
        self.action = action
    }

    var body: some View {
        ContentUnavailableView {
            Label(title, systemImage: systemName)
        } description: {
            if let detail, !detail.isEmpty {
                Text(detail)
            }
        } actions: {
            if state == .loading {
                ProgressView()
                    .controlSize(.small)
            } else if let actionTitle, let action {
                Button(actionTitle, action: action)
                    .buttonStyle(.bordered)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var systemName: String {
        switch state {
        case .loading: return "arrow.triangle.2.circlepath"
        case .empty: return "tray"
        case .error: return "exclamationmark.triangle"
        case .unavailable: return "slash.circle"
        }
    }
}

struct MinimalSectionHeader: View {
    let title: String
    let detail: String?

    init(_ title: String, detail: String? = nil) {
        self.title = title
        self.detail = detail
    }

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title)
                .font(.subheadline.weight(.semibold))
            Spacer()
            if let detail, !detail.isEmpty {
                Text(detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
        }
        .padding(.vertical, 4)
    }
}

struct MinimalDisclosureRow<Label: View, Trailing: View, Content: View>: View {
    @Binding var isExpanded: Bool
    let accessibilityLabel: String
    @ViewBuilder let label: () -> Label
    @ViewBuilder let trailing: () -> Trailing
    @ViewBuilder let content: () -> Content

    @EnvironmentObject private var preferences: AppPreferences

    init(
        isExpanded: Binding<Bool>,
        accessibilityLabel: String,
        @ViewBuilder label: @escaping () -> Label,
        @ViewBuilder trailing: @escaping () -> Trailing,
        @ViewBuilder content: @escaping () -> Content
    ) {
        _isExpanded = isExpanded
        self.accessibilityLabel = accessibilityLabel
        self.label = label
        self.trailing = trailing
        self.content = content
    }

    var body: some View {
        VStack(alignment: .leading, spacing: isExpanded ? 8 : 0) {
            HStack(alignment: .center, spacing: 10) {
                Button {
                    isExpanded.toggle()
                } label: {
                    HStack(alignment: .center, spacing: 12) {
                        label()
                        Spacer(minLength: 12)
                        Image(systemName: isExpanded ? "chevron.down" : "chevron.right")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundStyle(.secondary)
                            .accessibilityHidden(true)
                    }
                    .frame(maxWidth: .infinity, minHeight: 34, alignment: .leading)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(accessibilityLabel)
                .accessibilityValue(
                    preferences.text(
                        isExpanded
                            ? "tasks.section.expanded"
                            : "tasks.section.collapsed"
                    )
                )

                trailing()
            }

            if isExpanded {
                content()
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

extension MinimalDisclosureRow where Trailing == EmptyView {
    init(
        isExpanded: Binding<Bool>,
        accessibilityLabel: String,
        @ViewBuilder label: @escaping () -> Label,
        @ViewBuilder content: @escaping () -> Content
    ) {
        self.init(
            isExpanded: isExpanded,
            accessibilityLabel: accessibilityLabel,
            label: label,
            trailing: { EmptyView() },
            content: content
        )
    }
}

struct MinimalDisclosureSection<Content: View>: View {
    let title: String
    let detail: String?
    @Binding var isExpanded: Bool
    private let content: Content

    init(
        title: String,
        detail: String? = nil,
        isExpanded: Binding<Bool>,
        @ViewBuilder content: () -> Content
    ) {
        self.title = title
        self.detail = detail
        _isExpanded = isExpanded
        self.content = content()
    }

    var body: some View {
        MinimalDisclosureRow(
            isExpanded: $isExpanded,
            accessibilityLabel: title
        ) {
            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(.primary)
                if let detail, !detail.isEmpty {
                    Text(detail)
                        .font(.system(size: 11))
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        } content: {
            content
        }
    }
}

struct MinimalKeyValueRow: View {
    let title: String
    let value: String
    let monospaced: Bool

    init(_ title: String, value: String, monospaced: Bool = false) {
        self.title = title
        self.value = value
        self.monospaced = monospaced
    }

    var body: some View {
        LabeledContent(title) {
            Text(value)
                .font(monospaced ? .system(.caption, design: .monospaced) : .caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.trailing)
                .textSelection(.enabled)
        }
        .font(.caption)
    }
}

struct MinimalNoticeBar: View {
    let message: String
    let status: String

    init(message: String, status: String) {
        self.message = message
        self.status = status
    }

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: StatusPalette.systemImage(for: status))
                .foregroundStyle(StatusPalette.tone(for: status).foreground)
                .accessibilityHidden(true)
            Text(message)
                .font(.caption)
                .lineLimit(2)
            Spacer(minLength: 8)
        }
        .padding(.horizontal, 12)
        .frame(minHeight: 32)
        .background(.quaternary.opacity(0.35))
        .overlay(alignment: .bottom) { Divider() }
        .accessibilityElement(children: .combine)
    }
}

struct MinimalIconButton: View {
    let systemName: String
    let label: String
    let isDisabled: Bool
    let action: () -> Void

    @State private var showsTooltip = false
    @State private var tooltipTask: Task<Void, Never>?

    init(
        systemName: String,
        label: String,
        isDisabled: Bool = false,
        action: @escaping () -> Void
    ) {
        self.systemName = systemName
        self.label = label
        self.isDisabled = isDisabled
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            Image(systemName: systemName)
                .font(.system(size: 13, weight: .semibold))
                .frame(width: 32, height: 30)
        }
        .buttonStyle(.plain)
        .focusEffectDisabled()
        .foregroundStyle(Color.primary)
        .background(Color(nsColor: .controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .opacity(isDisabled ? 0.45 : 1)
        .disabled(isDisabled)
        .accessibilityLabel(Text(label))
        .overlay(alignment: .bottomTrailing) {
            if showsTooltip {
                Text(label)
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(Color.primary)
                    .lineLimit(1)
                    .fixedSize()
                    .padding(.horizontal, 8)
                    .padding(.vertical, 5)
                    .background(Color(nsColor: .controlBackgroundColor))
                    .clipShape(RoundedRectangle(cornerRadius: 6))
                    .overlay {
                        RoundedRectangle(cornerRadius: 6)
                            .stroke(Color.secondary.opacity(0.22), lineWidth: 1)
                    }
                    .shadow(color: .black.opacity(0.18), radius: 6, x: 0, y: 3)
                    .offset(y: 36)
                    .allowsHitTesting(false)
                    .zIndex(100)
            }
        }
        .onHover(perform: updateTooltip)
        .onDisappear {
            tooltipTask?.cancel()
            tooltipTask = nil
            showsTooltip = false
        }
    }

    private func updateTooltip(isHovering: Bool) {
        tooltipTask?.cancel()
        tooltipTask = nil
        showsTooltip = false

        guard isHovering else { return }
        tooltipTask = Task { @MainActor in
            try? await Task.sleep(nanoseconds: 800_000_000)
            guard !Task.isCancelled else { return }
            showsTooltip = true
        }
    }
}

struct MinimalFloatingDrawer<Content: View>: View {
    let width: CGFloat
    private let content: Content

    @Environment(\.colorScheme) private var colorScheme

    init(width: CGFloat = 310, @ViewBuilder content: () -> Content) {
        self.width = width
        self.content = content()
    }

    var body: some View {
        content
            .frame(width: width)
            .frame(maxHeight: .infinity)
            .background(AcrossTheme.panelFill(for: colorScheme))
            .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.cardCornerRadius))
            .overlay {
                RoundedRectangle(cornerRadius: AcrossTheme.Metrics.cardCornerRadius)
                    .stroke(AcrossTheme.separator(for: colorScheme), lineWidth: 1)
            }
            .shadow(
                color: .black.opacity(colorScheme == .dark ? 0.28 : 0.14),
                radius: 18,
                y: 8
            )
    }
}
