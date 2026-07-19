import SwiftUI

struct AgentCard: View {
    @Environment(\.colorScheme) private var colorScheme

    let iconName: String
    let name: String
    let statusText: String
    let isInstalled: Bool
    let accentColor: Color
    let isExpanded: Bool
    let onTap: () -> Void
    var isCloudLLM: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 12) {
                AgentIconView(name: iconName, size: 40, isCloudLLM: isCloudLLM)
                    .frame(width: 40, height: 40)

                VStack(alignment: .leading, spacing: 4) {
                    Text(name)
                        .font(.system(size: 14, weight: .medium))
                        .foregroundColor(titleColor)

                    HStack(spacing: 6) {
                        Circle()
                            .fill(statusColor)
                            .frame(width: 6, height: 6)

                        Text(statusText)
                            .font(.system(size: 11, weight: .regular, design: .monospaced))
                            .foregroundColor(statusTextColor)
                    }
                }

                Spacer()

                Image(systemName: "chevron.right")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(statusTextColor)
                    .rotationEffect(.degrees(isExpanded ? 90 : 0))
            }
            .padding(.leading, 24)
            .padding(.trailing, 12)
            .padding(.vertical, 12)
        }
        .background(cardBackground)
        .cornerRadius(12)
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(borderColor, lineWidth: 1)
        )
        .onTapGesture(perform: onTap)
    }

    private var statusColor: Color {
        isInstalled ? Color(hex: "30d158") : Color(hex: "ff9f0a")
    }

    private var cardBackground: Color {
        if isExpanded { return accentColor.opacity(colorScheme == .dark ? 0.18 : 0.10) }
        return colorScheme == .dark ? Color(hex: "242426") : Color.white
    }

    private var titleColor: Color {
        colorScheme == .dark ? .white : .legacyTextLight
    }

    private var statusTextColor: Color {
        colorScheme == .dark ? Color(hex: "636366") : Color(hex: "6b7280")
    }

    private var borderColor: Color {
        return colorScheme == .dark ? Color(white: 1, opacity: 0.08) : Color.black.opacity(0.08)
    }
}

struct AgentIconView: View {
    @Environment(\.colorScheme) private var colorScheme

    let name: String
    let size: CGFloat
    let isCloudLLM: Bool

    var body: some View {
        if let image = loadSVGImage(named: name) {
            let visualSize = agentIconVisualSize(name, containerSize: size)
            let visualCornerRadius = agentIconCornerRadius(name, visualSize: visualSize)
            if isDirectTemplateAgentIcon(name) {
                Image(nsImage: image)
                    .renderingMode(.template)
                    .resizable()
                    .scaledToFit()
                    .foregroundColor(colorScheme == .dark ? .white : .legacyTextLight)
                    .frame(width: visualSize, height: visualSize)
                    .clipShape(RoundedRectangle(cornerRadius: visualCornerRadius))
                    .frame(width: size, height: size)
                    .clipShape(RoundedRectangle(cornerRadius: size * 0.2))
            } else {
                Image(nsImage: image)
                    .resizable()
                    .scaledToFit()
                    .frame(width: visualSize, height: visualSize)
                    .clipShape(RoundedRectangle(cornerRadius: visualCornerRadius))
                    .frame(width: size, height: size)
                    .clipShape(RoundedRectangle(cornerRadius: size * 0.2))
            }
        } else {
            Text(iconInitial)
                .font(.system(size: size * 0.4, weight: .bold))
                .foregroundColor(colorScheme == .dark ? .white : .legacyTextLight)
                .frame(width: size, height: size)
                .background(iconBackground)
                .clipShape(RoundedRectangle(cornerRadius: size * 0.2))
        }
    }

    private var iconInitial: String {
        String(name.split(separator: ".").last ?? "").prefix(2).uppercased()
    }

    private var iconBackground: Color {
        colorScheme == .dark ? AcrossTheme.recessedFill(for: colorScheme) : Color(nsColor: .controlBackgroundColor)
    }

    private func loadSVGImage(named: String) -> NSImage? {
        loadAgentIconSync(name: named, colorScheme: colorScheme)
    }
}
