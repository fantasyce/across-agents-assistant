import SwiftUI

struct MinimalAssistantAgentPicker: View {
    let agents: [AgentModel]
    let selectedAgentID: String
    let title: String
    let isDisabled: Bool
    let onSelect: (String) -> Void

    var body: some View {
        Menu {
            ForEach(agents) { agent in
                Button {
                    onSelect(agent.id)
                } label: {
                    HStack {
                        Text(agent.name)
                        if agent.id == selectedAgentID {
                            Image(systemName: "checkmark")
                        }
                    }
                }
            }
        } label: {
            HStack(spacing: 5) {
                Text(title)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .frame(maxWidth: 150, alignment: .leading)
                Image(systemName: "chevron.up.chevron.down")
                    .font(.system(size: 8, weight: .semibold))
                    .foregroundStyle(.tertiary)
            }
            .font(.system(size: 11, weight: .medium))
            .foregroundStyle(.secondary)
            .padding(.horizontal, 7)
            .frame(height: 24)
            .contentShape(Rectangle())
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize(horizontal: true, vertical: false)
        .disabled(isDisabled || agents.isEmpty)
        .accessibilityLabel(Text(title))
        .help(title)
    }
}

struct MinimalAssistantAttachmentMenu: View {
    let screenshotOCRTitle: String
    let screenshotAttachmentTitle: String
    let fileAttachmentTitle: String
    let isDisabled: Bool
    let onScreenshotOCR: () -> Void
    let onScreenshotAttachment: () -> Void
    let onFileAttachment: () -> Void

    var body: some View {
        Menu {
            Button(action: onFileAttachment) {
                Label(fileAttachmentTitle, systemImage: "paperclip")
            }
            Divider()
            Button(action: onScreenshotAttachment) {
                Label(screenshotAttachmentTitle, systemImage: "photo.badge.plus")
            }
            Button(action: onScreenshotOCR) {
                Label(screenshotOCRTitle, systemImage: "camera.viewfinder")
            }
        } label: {
            InteractiveIconFrame(
                help: fileAttachmentTitle,
                frameSize: MainPanelIconMetrics.buttonSize,
                isDisabled: isDisabled
            ) {
                Image(systemName: "plus")
                    .font(.system(size: MainPanelIconMetrics.glyphSize, weight: .medium))
                    .foregroundStyle(.secondary)
            }
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .disabled(isDisabled)
        .accessibilityLabel(Text(fileAttachmentTitle))
        .help(fileAttachmentTitle)
    }
}

struct MinimalAssistantSendButton: View {
    let isProcessing: Bool
    let canSubmit: Bool
    let sendTitle: String
    let stopTitle: String
    let onSend: () -> Void
    let onStop: () -> Void

    @Environment(\.colorScheme) private var colorScheme
    @State private var isHovered = false

    private var isEnabled: Bool {
        isProcessing || canSubmit
    }

    private var fillColor: Color {
        if isProcessing {
            return Color(nsColor: .systemRed)
        }
        if canSubmit {
            return Color(nsColor: .controlAccentColor)
        }
        return colorScheme == .dark ? Color.white.opacity(0.10) : Color.black.opacity(0.08)
    }

    var body: some View {
        Button(action: isProcessing ? onStop : onSend) {
            Image(systemName: isProcessing ? "stop.fill" : "arrow.up")
                .font(.system(size: 12, weight: .bold))
                .foregroundStyle(isEnabled ? Color.white : Color.secondary)
                .frame(width: 30, height: 30)
                .background(
                    RoundedRectangle(cornerRadius: 7, style: .continuous)
                        .fill(fillColor.opacity(isHovered && isEnabled ? 0.82 : 1))
                )
                .contentShape(RoundedRectangle(cornerRadius: 7, style: .continuous))
        }
        .buttonStyle(.plain)
        .disabled(!isEnabled)
        .onHover { isHovered = $0 }
        .accessibilityLabel(Text(isProcessing ? stopTitle : sendTitle))
        .help(isProcessing ? stopTitle : sendTitle)
    }
}

struct MinimalAssistantVoiceControls: View {
    let isMuted: Bool
    let muteTitle: String
    let isDisabled: Bool
    let onToggleMute: () -> Void

    var body: some View {
        InteractiveIconButton(
            systemName: isMuted ? "speaker.slash.fill" : "speaker.wave.2",
            help: muteTitle,
            iconSize: MainPanelIconMetrics.glyphSize,
            foregroundColor: isMuted ? Color(nsColor: .systemRed) : .secondary,
            frameSize: MainPanelIconMetrics.buttonSize,
            isDisabled: isDisabled,
            action: onToggleMute
        )
    }
}
