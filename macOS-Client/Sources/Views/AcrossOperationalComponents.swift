import SwiftUI

struct MetricTile: View {
    let title: String
    let value: String
    var detail: String? = nil
    var status: String = "unknown"
    var systemName: String? = nil

    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 6) {
                if let systemName {
                    Image(systemName: systemName)
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(StatusPalette.tone(for: status).foreground)
                        .accessibilityHidden(true)
                }
                Text(title)
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            Text(value)
                .font(.system(size: 18, weight: .semibold, design: .rounded))
                .foregroundStyle(.primary)
                .lineLimit(2)
                .minimumScaleFactor(0.72)
                .fixedSize(horizontal: false, vertical: true)

            if let detail, !detail.isEmpty {
                Text(detail)
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
        }
        .frame(maxWidth: .infinity, minHeight: 78, alignment: .leading)
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background(AcrossTheme.recessedFill(for: colorScheme))
        .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.controlCornerRadius))
        .overlay(
            RoundedRectangle(cornerRadius: AcrossTheme.Metrics.controlCornerRadius)
                .stroke(AcrossTheme.separator(for: colorScheme), lineWidth: 1)
        )
        .accessibilityElement(children: .combine)
    }
}

struct ActionRow: View {
    let systemName: String
    let title: String
    var detail: String? = nil
    var status: String = "unknown"
    var actionTitle: String? = nil
    var isDisabled: Bool = false
    var action: (() -> Void)? = nil

    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: systemName)
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(StatusPalette.tone(for: status).foreground)
                .frame(width: 20, height: 20)
                .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                if let detail, !detail.isEmpty {
                    Text(detail)
                        .font(.system(size: 11))
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
            }

            Spacer(minLength: 10)

            StatusChip(status: status)

            if let actionTitle, let action {
                Button(actionTitle, action: action)
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .disabled(isDisabled)
                    .accessibilityHint(Text(detail ?? title))
            }
        }
        .frame(maxWidth: .infinity, minHeight: AcrossTheme.Metrics.rowMinHeight, alignment: .leading)
        .padding(.horizontal, 10)
        .padding(.vertical, 7)
        .contentShape(Rectangle())
        .overlay(alignment: .bottom) {
            Rectangle()
                .fill(AcrossTheme.separator(for: colorScheme))
                .frame(height: 1)
        }
    }
}

struct EvidenceMetadata: Identifiable, Equatable {
    let key: String
    let value: String

    var id: String { key }
}

struct EvidencePanel<Content: View>: View {
    let title: String
    let summary: String
    var status: String
    var metadata: [EvidenceMetadata]
    @ViewBuilder let content: () -> Content

    @Environment(\.colorScheme) private var colorScheme

    init(
        title: String,
        summary: String,
        status: String,
        metadata: [EvidenceMetadata] = [],
        @ViewBuilder content: @escaping () -> Content
    ) {
        self.title = title
        self.summary = summary
        self.status = status
        self.metadata = metadata
        self.content = content
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 10) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(title)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(.primary)
                    Text(summary)
                        .font(.system(size: 11))
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer()
                StatusChip(status: status)
            }

            if !metadata.isEmpty {
                Grid(alignment: .leading, horizontalSpacing: 14, verticalSpacing: 5) {
                    ForEach(metadata) { item in
                        GridRow {
                            Text(item.key)
                                .font(.system(size: 10, weight: .medium))
                                .foregroundStyle(.secondary)
                            Text(item.value)
                                .font(.system(size: 10, design: .monospaced))
                                .foregroundStyle(.primary)
                                .lineLimit(1)
                                .textSelection(.enabled)
                        }
                    }
                }
            }

            content()
        }
        .padding(14)
        .background(AcrossTheme.panelFill(for: colorScheme))
        .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.cardCornerRadius))
        .overlay(
            RoundedRectangle(cornerRadius: AcrossTheme.Metrics.cardCornerRadius)
                .stroke(AcrossTheme.separator(for: colorScheme), lineWidth: 1)
        )
    }
}

struct InspectorPanel<Content: View, Toolbar: View>: View {
    let title: String
    var subtitle: String? = nil
    @ViewBuilder let toolbar: () -> Toolbar
    @ViewBuilder let content: () -> Content

    @Environment(\.colorScheme) private var colorScheme

    init(
        title: String,
        subtitle: String? = nil,
        @ViewBuilder toolbar: @escaping () -> Toolbar,
        @ViewBuilder content: @escaping () -> Content
    ) {
        self.title = title
        self.subtitle = subtitle
        self.toolbar = toolbar
        self.content = content
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 10) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(.system(size: 13, weight: .semibold))
                    if let subtitle, !subtitle.isEmpty {
                        Text(subtitle)
                            .font(.system(size: 10))
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }
                Spacer()
                toolbar()
            }
            .padding(.horizontal, 12)
            .frame(minHeight: 48)

            Rectangle()
                .fill(AcrossTheme.separator(for: colorScheme))
                .frame(height: 1)

            content()
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
        .background(AcrossTheme.panelFill(for: colorScheme))
        .overlay(alignment: .leading) {
            Rectangle()
                .fill(AcrossTheme.separator(for: colorScheme))
                .frame(width: 1)
        }
    }
}

struct TimelineRow: View {
    let systemName: String
    let title: String
    var detail: String? = nil
    var timestamp: String? = nil
    var status: String = "unknown"
    var isLast: Bool = false

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            VStack(spacing: 0) {
                Image(systemName: systemName)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(StatusPalette.tone(for: status).foreground)
                    .frame(width: 22, height: 22)
                    .background(StatusPalette.tone(for: status).foreground.opacity(0.11))
                    .clipShape(RoundedRectangle(cornerRadius: 5))
                    .accessibilityHidden(true)
                if !isLast {
                    Rectangle()
                        .fill(Color(nsColor: .separatorColor))
                        .frame(width: 1, height: 24)
                }
            }

            VStack(alignment: .leading, spacing: 3) {
                HStack {
                    Text(title)
                        .font(.system(size: 12, weight: .semibold))
                        .lineLimit(1)
                    Spacer()
                    if let timestamp {
                        Text(timestamp)
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(.secondary)
                    }
                }
                if let detail, !detail.isEmpty {
                    Text(detail)
                        .font(.system(size: 11))
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
            }
            .padding(.top, 2)
        }
        .accessibilityElement(children: .combine)
    }
}

struct OperationalContentStateView: View {
    let state: OperationalContentState
    let title: String
    var message: String? = nil
    var retryTitle: String? = nil
    var retry: (() -> Void)? = nil

    private var presentation: (icon: String, status: String, detail: String) {
        switch state {
        case .loading:
            return ("arrow.triangle.2.circlepath", "active", "")
        case .empty:
            return ("tray", "none", "")
        case .error(let detail):
            return ("exclamationmark.triangle", "failed", detail)
        case .active(let detail):
            return ("bolt.circle", "active", detail)
        case .disabled(let detail):
            return ("nosign", "disabled", detail)
        case .success(let detail):
            return ("checkmark.circle", "success", detail)
        }
    }

    var body: some View {
        VStack(spacing: 10) {
            if state == .loading {
                ProgressView()
                    .controlSize(.small)
            } else {
                Image(systemName: presentation.icon)
                    .font(.system(size: 22, weight: .medium))
                    .foregroundStyle(StatusPalette.tone(for: presentation.status).foreground)
                    .accessibilityHidden(true)
            }
            Text(title)
                .font(.system(size: 13, weight: .semibold))
                .multilineTextAlignment(.center)
            let detail = message ?? presentation.detail
            if !detail.isEmpty {
                Text(detail)
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 360)
            }
            if let retryTitle, let retry {
                Button(retryTitle, action: retry)
                    .buttonStyle(.bordered)
                    .controlSize(.small)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(24)
        .accessibilityElement(children: .combine)
    }
}
