import SwiftUI

struct InteractiveIconButton: View {
    let systemName: String
    let help: String
    var iconSize: CGFloat = 14
    var weight: Font.Weight = .regular
    var foregroundColor: Color = .secondary
    var frameSize: CGFloat = 24
    var isDisabled: Bool = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            InteractiveIconFrame(help: help, frameSize: frameSize, isDisabled: isDisabled) {
                Image(systemName: systemName)
                    .font(.system(size: iconSize, weight: weight))
                    .foregroundColor(foregroundColor)
            }
        }
        .buttonStyle(.plain)
        .focusEffectDisabled()
        .disabled(isDisabled)
        .accessibilityLabel(Text(help))
        .accessibilityHint(Text(help))
        .help(help)
    }
}

struct InteractiveAssetIconButton: View {
    let assetName: String
    let fallbackSystemName: String
    let help: String
    var iconSize: CGFloat = 14
    var foregroundColor: Color = .secondary
    var frameSize: CGFloat = 24
    var isDisabled: Bool = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            InteractiveIconFrame(help: help, frameSize: frameSize, isDisabled: isDisabled) {
                BundledTemplateIcon(
                    name: assetName,
                    fallbackSystemName: fallbackSystemName,
                    size: iconSize,
                    color: foregroundColor
                )
            }
        }
        .buttonStyle(.plain)
        .focusEffectDisabled()
        .disabled(isDisabled)
        .accessibilityLabel(Text(help))
        .accessibilityHint(Text(help))
        .help(help)
    }
}

struct InteractiveIconLabel: View {
    let systemName: String
    let help: String
    var iconSize: CGFloat = 14
    var weight: Font.Weight = .regular
    var foregroundColor: Color = .secondary
    var frameSize: CGFloat = 24
    var externalIsHovered: Bool? = nil

    var body: some View {
        InteractiveIconFrame(help: help, frameSize: frameSize, externalIsHovered: externalIsHovered) {
            Image(systemName: systemName)
                .font(.system(size: iconSize, weight: weight))
                .foregroundColor(foregroundColor)
        }
        .accessibilityLabel(Text(help))
        .help(help)
    }
}

struct InteractiveIconFrame<Content: View>: View {
    let help: String
    var frameSize: CGFloat
    var isDisabled: Bool = false
    var externalIsHovered: Bool? = nil
    @ViewBuilder let content: Content

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.isEnabled) private var isEnabled
    @State private var internalIsHovered = false

    private var hoverBackground: Color {
        colorScheme == .dark ? Color.white.opacity(0.09) : Color.black.opacity(0.06)
    }

    private var effectiveIsHovered: Bool {
        internalIsHovered || (externalIsHovered ?? false)
    }

    private var effectiveIsDisabled: Bool {
        isDisabled || !isEnabled
    }

    var body: some View {
        content
            .frame(width: frameSize, height: frameSize)
            .background(
                RoundedRectangle(cornerRadius: 6, style: .continuous)
                    .fill(effectiveIsHovered && !effectiveIsDisabled ? hoverBackground : Color.clear)
            )
            .opacity(effectiveIsDisabled ? 0.42 : 1)
            .contentShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
            .onHover { hovering in
                internalIsHovered = hovering
            }
            .animation(.easeOut(duration: 0.12), value: effectiveIsHovered)
    }
}
