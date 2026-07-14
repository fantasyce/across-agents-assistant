import AppKit
import SwiftUI

enum AcrossTheme {
    enum Spacing {
        static let compact: CGFloat = 4
        static let control: CGFloat = 8
        static let content: CGFloat = 16
        static let section: CGFloat = 24
        static let page: CGFloat = 32
    }

    enum Metrics {
        static let controlCornerRadius: CGFloat = 8
        static let chipCornerRadius: CGFloat = 8
        static let cardCornerRadius: CGFloat = 12
        static let toolbarButtonSize = CGSize(width: 32, height: 30)
        static let sidebarWidth: CGFloat = 232
        static let inspectorWidth: CGFloat = 300
        static let rowMinHeight: CGFloat = 42
        static let hairlineOpacity = 0.12
    }

    static let accent = Color(nsColor: .systemBlue)

    static func canvasFill(for colorScheme: ColorScheme) -> Color {
        Color(nsColor: .windowBackgroundColor)
    }

    static func sidebarFill(for colorScheme: ColorScheme) -> Color {
        .clear
    }

    static func panelFill(for colorScheme: ColorScheme) -> Color {
        colorScheme == .dark ? Color(nsColor: .controlBackgroundColor) : Color(nsColor: .windowBackgroundColor)
    }

    static func recessedFill(for colorScheme: ColorScheme) -> Color {
        colorScheme == .dark ? Color.white.opacity(0.075) : Color.black.opacity(0.04)
    }

    static func separator(for colorScheme: ColorScheme) -> Color {
        colorScheme == .dark ? Color.white.opacity(0.14) : Color.black.opacity(0.10)
    }

    static func selectedFill(for colorScheme: ColorScheme) -> Color {
        accent.opacity(colorScheme == .dark ? 0.20 : 0.11)
    }

    static func hoverFill(for colorScheme: ColorScheme) -> Color {
        colorScheme == .dark ? Color.white.opacity(0.10) : Color.black.opacity(0.045)
    }

    static func focusRing(for colorScheme: ColorScheme) -> Color {
        accent.opacity(colorScheme == .dark ? 0.9 : 0.72)
    }
}

enum AcrossWindowLayoutSize: Equatable {
    case regular
    case expanded
}

private struct AcrossWindowLayoutSizeKey: EnvironmentKey {
    static let defaultValue: AcrossWindowLayoutSize = .regular
}

extension EnvironmentValues {
    var acrossWindowLayoutSize: AcrossWindowLayoutSize {
        get { self[AcrossWindowLayoutSizeKey.self] }
        set { self[AcrossWindowLayoutSizeKey.self] = newValue }
    }
}

enum AcrossStatusTone: String, CaseIterable {
    case success
    case warning
    case danger
    case info
    case neutral

    var foreground: Color {
        switch self {
        case .success:
            return Color(nsColor: .systemGreen)
        case .warning:
            return Color(nsColor: .systemOrange)
        case .danger:
            return Color(nsColor: .systemRed)
        case .info:
            return Color(nsColor: .systemBlue)
        case .neutral:
            return Color.secondary
        }
    }

    var background: Color {
        foreground.opacity(backgroundOpacity)
    }

    var backgroundOpacity: Double {
        switch self {
        case .neutral:
            return 0.08
        default:
            return 0.12
        }
    }

    var borderOpacity: Double {
        switch self {
        case .neutral:
            return 0.12
        default:
            return 0.22
        }
    }
}

enum StatusPalette {
    static func tone(for status: String?) -> AcrossStatusTone {
        switch normalized(status) {
        case "active", "available", "completed", "configured", "installed", "ok", "passed", "ready", "running", "success":
            return .success
        case "attention", "degraded", "manual_required", "missing", "needs_attention", "not_ready", "not_run", "partial", "paused", "pending", "unknown", "unavailable", "watch":
            return .warning
        case "blocked", "error", "failed", "failure", "invalid", "rejected", "timeout":
            return .danger
        case "disabled", "none", "not_applicable", "not_implemented", "skipped":
            return .neutral
        default:
            return .info
        }
    }

    static func systemImage(for status: String?) -> String {
        switch tone(for: status) {
        case .success:
            return "checkmark.circle.fill"
        case .warning:
            return "exclamationmark.triangle.fill"
        case .danger:
            return "xmark.octagon.fill"
        case .info:
            return "info.circle.fill"
        case .neutral:
            return "circle.dashed"
        }
    }

    static func displayText(for status: String?) -> String {
        let normalizedStatus = normalized(status)
        guard !normalizedStatus.isEmpty else { return "Unknown" }
        return normalizedStatus
            .split(separator: "_")
            .map { $0.prefix(1).uppercased() + $0.dropFirst() }
            .joined(separator: " ")
    }

    static func normalized(_ status: String?) -> String {
        (status ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .replacingOccurrences(of: "-", with: "_")
    }
}

struct StatusChip: View {
    let status: String
    var label: String?
    var toneOverride: AcrossStatusTone?

    private var tone: AcrossStatusTone {
        toneOverride ?? StatusPalette.tone(for: status)
    }

    private var title: String {
        label ?? StatusPalette.displayText(for: status)
    }

    var body: some View {
        HStack(spacing: 5) {
            Image(systemName: StatusPalette.systemImage(for: status))
                .font(.system(size: 10, weight: .semibold))
                .accessibilityHidden(true)

            Text(title)
                .font(.system(size: 11, weight: .semibold))
                .lineLimit(1)
        }
        .foregroundStyle(tone.foreground)
        .padding(.horizontal, 7)
        .padding(.vertical, 4)
        .background(tone.foreground.opacity(tone.backgroundOpacity))
        .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.chipCornerRadius))
        .overlay(
            RoundedRectangle(cornerRadius: AcrossTheme.Metrics.chipCornerRadius)
                .stroke(tone.foreground.opacity(tone.borderOpacity), lineWidth: 1)
        )
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text(title))
    }
}

struct CommandToolbarButton: View {
    let systemName: String
    let accessibilityLabel: String
    let help: String
    var isDisabled: Bool
    let action: () -> Void

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.isEnabled) private var isEnabled
    @FocusState private var isFocused: Bool

    init(
        systemName: String,
        accessibilityLabel: String,
        help: String,
        isDisabled: Bool = false,
        action: @escaping () -> Void
    ) {
        precondition(!accessibilityLabel.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        precondition(!help.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        self.systemName = systemName
        self.accessibilityLabel = accessibilityLabel
        self.help = help
        self.isDisabled = isDisabled
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            Image(systemName: systemName)
                .font(.system(size: 13, weight: .semibold))
                .frame(
                    width: AcrossTheme.Metrics.toolbarButtonSize.width,
                    height: AcrossTheme.Metrics.toolbarButtonSize.height
                )
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .foregroundStyle(isDisabled || !isEnabled ? Color.secondary : Color.primary)
        .background(isFocused ? AcrossTheme.selectedFill(for: colorScheme) : AcrossTheme.recessedFill(for: colorScheme))
        .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.controlCornerRadius))
        .overlay(
            RoundedRectangle(cornerRadius: AcrossTheme.Metrics.controlCornerRadius)
                .stroke(
                    isFocused ? AcrossTheme.focusRing(for: colorScheme) : AcrossTheme.separator(for: colorScheme),
                    lineWidth: 1
                )
        )
        .accessibilityLabel(Text(accessibilityLabel))
        .accessibilityHint(Text(help))
        .help(help)
        .disabled(isDisabled)
        .focused($isFocused)
    }
}
