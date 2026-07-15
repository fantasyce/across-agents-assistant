import SwiftUI

enum MinimalSettingsMetrics {
    static let contentMaxWidth: CGFloat = 980
    static let contentPadding: CGFloat = 28
    static let sectionSpacing: CGFloat = 28
    static let rowVerticalPadding: CGFloat = 10
}

struct MinimalSettingsWindowHeader: View {
    let title: String
    var onClose: (() -> Void)?

    var body: some View {
        HStack(spacing: 0) {
            CustomTrafficLights(onClose: onClose)
                .frame(width: 112, alignment: .leading)

            Spacer()

            Text(title)
                .font(.system(size: 13, weight: .semibold))

            Spacer()

            Color.clear.frame(width: 112, height: 1)
        }
        .padding(.horizontal, 16)
        .frame(height: 52)
        .background(
            ZStack {
                Color(nsColor: .windowBackgroundColor).opacity(0.92)
                WindowDragView().contentShape(Rectangle())
            }
        )
        .overlay(alignment: .bottom) {
            Divider()
        }
    }
}

struct MinimalSettingsPageHeader<Trailing: View>: View {
    let title: String
    let subtitle: String?
    @ViewBuilder let trailing: () -> Trailing
    @Environment(\.acrossWindowLayoutSize) private var windowLayoutSize

    init(
        title: String,
        subtitle: String? = nil,
        @ViewBuilder trailing: @escaping () -> Trailing
    ) {
        self.title = title
        self.subtitle = subtitle
        self.trailing = trailing
    }

    var body: some View {
        HStack(alignment: .center, spacing: 20) {
            VStack(alignment: .leading, spacing: 5) {
                Text(title)
                    .font(.system(size: windowLayoutSize == .expanded ? 32 : 28, weight: .bold))
                    .lineLimit(1)
                if let subtitle, !subtitle.isEmpty {
                    Text(subtitle)
                        .font(.system(size: windowLayoutSize == .expanded ? 14 : 13))
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            Spacer(minLength: 16)
            trailing()
        }
    }
}

extension MinimalSettingsPageHeader where Trailing == EmptyView {
    init(title: String, subtitle: String? = nil) {
        self.init(title: title, subtitle: subtitle) { EmptyView() }
    }
}

struct MinimalSettingsSection<Content: View>: View {
    let title: String
    let subtitle: String?
    @ViewBuilder let content: () -> Content

    init(
        title: String,
        subtitle: String? = nil,
        @ViewBuilder content: @escaping () -> Content
    ) {
        self.title = title
        self.subtitle = subtitle
        self.content = content
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.system(size: 13, weight: .semibold))
                if let subtitle, !subtitle.isEmpty {
                    Text(subtitle)
                        .font(.system(size: 11))
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            VStack(spacing: 0) {
                Divider()
                content()
                Divider()
            }
        }
    }
}

struct MinimalSettingsRow<Leading: View, Trailing: View>: View {
    let title: String
    let detail: String?
    @ViewBuilder let leading: () -> Leading
    @ViewBuilder let trailing: () -> Trailing

    init(
        title: String,
        detail: String? = nil,
        @ViewBuilder leading: @escaping () -> Leading,
        @ViewBuilder trailing: @escaping () -> Trailing
    ) {
        self.title = title
        self.detail = detail
        self.leading = leading
        self.trailing = trailing
    }

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            leading()
                .frame(width: 22, alignment: .center)

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.system(size: 12, weight: .medium))
                if let detail, !detail.isEmpty {
                    Text(detail)
                        .font(.system(size: 10))
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
            }

            Spacer(minLength: 16)
            trailing()
        }
        .padding(.vertical, MinimalSettingsMetrics.rowVerticalPadding)
        .contentShape(Rectangle())
    }
}

extension MinimalSettingsRow where Leading == EmptyView {
    init(
        title: String,
        detail: String? = nil,
        @ViewBuilder trailing: @escaping () -> Trailing
    ) {
        self.init(title: title, detail: detail, leading: { EmptyView() }, trailing: trailing)
    }
}

struct MinimalStatusLabel: View {
    let text: String
    let color: Color
    var systemImage: String? = nil

    var body: some View {
        HStack(spacing: 5) {
            if let systemImage {
                Image(systemName: systemImage)
                    .font(.system(size: 10, weight: .semibold))
            } else {
                Circle()
                    .fill(color)
                    .frame(width: 6, height: 6)
            }
            Text(text)
                .font(.system(size: 10, weight: .medium))
                .lineLimit(1)
        }
        .foregroundStyle(color)
    }
}

struct MinimalSettingsNotice: View {
    let text: String
    let color: Color
    var systemImage: String = "info.circle.fill"

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: systemImage)
                .foregroundStyle(color)
            Text(text)
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .padding(.vertical, 8)
    }
}
