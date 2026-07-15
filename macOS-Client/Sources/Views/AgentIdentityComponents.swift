import AppKit
import SwiftUI

struct AgentIconChip: View {
    let agent: AgentOption
    let isSelected: Bool
    let onTap: () -> Void

    @Environment(\.colorScheme) private var colorScheme
    private let chipSize: CGFloat = 36

    var body: some View {
        Button(action: onTap) {
            if agent.id == "auto" {
                Image(systemName: "wand.and.stars")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundColor(isSelected ? .white : .secondary)
                    .frame(width: chipSize, height: chipSize)
                    .background(isSelected ? AcrossTheme.accent : AcrossTheme.recessedFill(for: colorScheme))
                    .cornerRadius(AcrossTheme.Metrics.controlCornerRadius)
            } else {
                AgentIconView(name: agent.iconName, size: chipSize, isCloudLLM: agent.isCloudLLM)
                    .frame(width: chipSize, height: chipSize)
                    .opacity(isSelected ? 1 : 0.72)
                    .overlay(alignment: .bottomTrailing) {
                        if isSelected {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundStyle(AcrossTheme.accent)
                                .background(Circle().fill(Color(nsColor: .windowBackgroundColor)))
                        }
                    }
            }
        }
        .buttonStyle(.plain)
        .focusEffectDisabled()
        .frame(width: chipSize, height: chipSize)
        .accessibilityLabel(Text(agent.name))
        .accessibilityValue(Text(isSelected ? "Selected" : "Not selected"))
        .help(agent.name)
    }
}

struct AgentIdentityBadge: View {
    let agentId: String
    let ownerAgentId: String?
    var size: CGFloat = 22
    var status: String? = nil

    @EnvironmentObject private var appPreferences: AppPreferences

    private var resolvedAgentId: String {
        let normalized = agentId.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if normalized.contains("owner"), let ownerAgentId, !ownerAgentId.isEmpty {
            return AgentIDs.normalized(ownerAgentId.lowercased()) ?? ownerAgentId.lowercased()
        }
        return AgentIDs.normalized(normalized) ?? normalized
    }

    private var isAuto: Bool {
        resolvedAgentId == "auto" || resolvedAgentId.isEmpty || resolvedAgentId == "owner"
    }

    private var isCloudLLM: Bool {
        [
            "openai", "anthropic", "deepseek", "minimax", "bailian", "moonshot",
            "zhipu", "volcengine", "google", "xai", "mistral", "groq", "cohere",
            "openrouter", "together", "fireworks", "agnes",
        ].contains(resolvedAgentId)
    }

    private var iconName: String {
        "agent.\(resolvedAgentId)"
    }

    private var displayName: String {
        switch resolvedAgentId {
        case "auto": return appPreferences.text("tasks.auto")
        case "openclaw": return "OpenClaw"
        case "hermes": return "Hermes"
        case "claude": return "Claude Code"
        case "claude-desktop": return "Claude Desktop"
        case "kimi": return "Kimi Code"
        case "deepseek": return "DeepSeek"
        case "minimax": return "MiniMax"
        case "agnes": return "Agnes"
        case "owner": return appPreferences.text("tasks.owner")
        case "": return appPreferences.text("tasks.unknownAgent")
        default: return resolvedAgentId
        }
    }

    var body: some View {
        HStack(spacing: 6) {
            Group {
                if isAuto {
                    Image(systemName: "wand.and.stars")
                        .font(.system(size: size * 0.5, weight: .semibold))
                        .foregroundColor(.white)
                        .frame(width: size, height: size)
                        .background(Color(nsColor: .systemOrange))
                        .clipShape(RoundedRectangle(cornerRadius: min(size * 0.22, 6)))
                } else {
                    AgentIconView(name: iconName, size: size, isCloudLLM: isCloudLLM)
                        .frame(width: size, height: size)
                }
            }

            if let status {
                Circle()
                    .fill(StatusPalette.tone(for: status).foreground)
                    .frame(width: 7, height: 7)
                    .overlay(Circle().stroke(Color(nsColor: .windowBackgroundColor), lineWidth: 1))
                    .accessibilityHidden(true)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text(displayName))
        .accessibilityValue(Text(status.map { StatusPalette.displayText(for: $0) } ?? ""))
        .help(displayName)
    }
}
