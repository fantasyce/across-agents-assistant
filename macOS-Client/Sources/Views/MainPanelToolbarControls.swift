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
    }
}

struct InteractiveIconFrame<Content: View>: View {
    let help: String
    var frameSize: CGFloat
    var isDisabled: Bool = false
    var externalIsHovered: Bool? = nil
    @ViewBuilder let content: Content

    @Environment(\.colorScheme) private var colorScheme
    @State private var internalIsHovered = false
    @State private var showTooltip = false
    @State private var tooltipWorkItem: DispatchWorkItem?

    private var hoverBackground: Color {
        colorScheme == .dark ? Color.white.opacity(0.10) : Color.black.opacity(0.07)
    }

    private var borderColor: Color {
        colorScheme == .dark ? Color.white.opacity(0.08) : Color.black.opacity(0.05)
    }

    private var tooltipBackground: Color {
        colorScheme == .dark ? Color(hex: "2c2c2e") : Color(hex: "202124")
    }

    private var effectiveIsHovered: Bool {
        internalIsHovered || (externalIsHovered ?? false)
    }

    var body: some View {
        content
            .frame(width: frameSize, height: frameSize)
            .background(
                RoundedRectangle(cornerRadius: 7)
                    .fill(effectiveIsHovered && !isDisabled ? hoverBackground : Color.clear)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 7)
                    .stroke(effectiveIsHovered && !isDisabled ? borderColor : Color.clear, lineWidth: 1)
            )
            .opacity(isDisabled ? 0.45 : 1)
            .scaleEffect(effectiveIsHovered && !isDisabled ? 1.04 : 1.0)
            .animation(.easeInOut(duration: 0.12), value: effectiveIsHovered)
            .contentShape(RoundedRectangle(cornerRadius: 7))
            .onHover { hovering in
                internalIsHovered = hovering
            }
            .onChange(of: effectiveIsHovered) { _, hovering in
                updateTooltip(hovering)
            }
            .overlay {
                if showTooltip && !help.isEmpty && effectiveIsHovered && !isDisabled {
                    GeometryReader { proxy in
                        let frame = proxy.frame(in: .global)
                        let showBelow = shouldShowTooltipBelow(frame)
                        tooltipLabel
                            .position(
                                x: proxy.size.width / 2 + tooltipHorizontalOffset(for: frame),
                                y: showBelow ? proxy.size.height + 22 : -22
                            )
                    }
                    .frame(width: frameSize, height: frameSize)
                    .transition(.opacity.combined(with: .scale(scale: 0.96)))
                    .allowsHitTesting(false)
                    .zIndex(50)
                }
            }
            .zIndex(showTooltip ? 10_000 : (effectiveIsHovered ? 1 : 0))
    }

    private var tooltipLabel: some View {
        Text(help)
            .font(.system(size: 11, weight: .medium))
            .foregroundColor(.white)
            .lineLimit(1)
            .fixedSize(horizontal: true, vertical: false)
            .padding(.horizontal, 8)
            .padding(.vertical, 5)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(tooltipBackground)
                    .shadow(color: Color.black.opacity(0.18), radius: 8, y: 3)
            )
    }

    private func shouldShowTooltipBelow(_ frame: CGRect) -> Bool {
        frame.minY < 48
    }

    private func tooltipHorizontalOffset(for frame: CGRect) -> CGFloat {
        guard let screenFrame = NSScreen.main?.visibleFrame else { return 0 }
        let estimatedWidth = min(max(CGFloat(help.count) * 7 + 20, 72), 240)
        let margin: CGFloat = 10
        let leftOverflow = screenFrame.minX + margin - (frame.midX - estimatedWidth / 2)
        if leftOverflow > 0 {
            return leftOverflow
        }
        let rightOverflow = (frame.midX + estimatedWidth / 2) - (screenFrame.maxX - margin)
        if rightOverflow > 0 {
            return -rightOverflow
        }
        return 0
    }

    private func updateTooltip(_ hovering: Bool) {
        tooltipWorkItem?.cancel()
        tooltipWorkItem = nil

        guard hovering, !isDisabled, !help.isEmpty else {
            showTooltip = false
            return
        }

        let workItem = DispatchWorkItem {
            if effectiveIsHovered && !isDisabled {
                withAnimation(.easeInOut(duration: 0.12)) {
                    showTooltip = true
                }
            }
        }
        tooltipWorkItem = workItem
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0, execute: workItem)
    }
}

