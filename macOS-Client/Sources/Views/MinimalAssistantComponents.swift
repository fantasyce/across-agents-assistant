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
    let speechState: SpeechRecognitionState
    let localeIdentifier: String
    let voiceInputTitle: String
    let isMuted: Bool
    let muteTitle: String
    let isSpeechDisabled: Bool
    let reduceMotion: Bool
    let onToggleSpeechInput: () -> Void
    let onToggleMute: () -> Void

    var body: some View {
        HStack(spacing: 4) {
            MinimalAssistantSpeechButton(
                state: speechState,
                localeIdentifier: localeIdentifier,
                title: voiceInputTitle,
                isDisabled: isSpeechDisabled,
                reduceMotion: reduceMotion,
                action: onToggleSpeechInput
            )

            if let status = speechState.shortStatus(localeIdentifier: localeIdentifier) {
                Text(status)
                    .font(.system(size: 10, weight: .medium))
                    .foregroundStyle(speechStatusColor)
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
                    .accessibilityHidden(true)
                    .transition(.opacity)
            }

            InteractiveIconButton(
                systemName: isMuted ? "speaker.slash.fill" : "speaker.wave.2",
                help: muteTitle,
                iconSize: MainPanelIconMetrics.glyphSize,
                foregroundColor: isMuted ? Color(nsColor: .systemRed) : .secondary,
                frameSize: MainPanelIconMetrics.buttonSize,
                isDisabled: false,
                action: onToggleMute
            )
            .focusable(true)
        }
    }

    private var speechStatusColor: Color {
        switch speechState {
        case .denied, .failed, .inputDeviceLost:
            return Color(nsColor: .systemRed)
        case .unavailable:
            return Color(nsColor: .systemOrange)
        case .listening, .transcribing, .segmentTranscript, .retrying:
            return Color(nsColor: .controlAccentColor)
        default:
            return .secondary
        }
    }
}

private struct MinimalAssistantSpeechButton: View {
    let state: SpeechRecognitionState
    let localeIdentifier: String
    let title: String
    let isDisabled: Bool
    let reduceMotion: Bool
    let action: () -> Void

    @State private var pulse = false

    private var iconName: String {
        switch state {
        case .requestingPermission, .retrying, .transcribing:
            return "ellipsis"
        case .listening:
            return "waveform"
        case .segmentTranscript:
            return "checkmark"
        case .denied, .failed, .inputDeviceLost:
            return "mic.badge.xmark"
        case .unavailable:
            return "mic.slash"
        default:
            return "mic"
        }
    }

    private var foregroundColor: Color {
        switch state {
        case .denied, .failed, .inputDeviceLost:
            return Color(nsColor: .systemRed)
        case .unavailable:
            return Color(nsColor: .systemOrange)
        case .requestingPermission, .retrying, .listening, .transcribing, .segmentTranscript:
            return Color(nsColor: .controlAccentColor)
        default:
            return .secondary
        }
    }

    private var accessibilityLabel: String {
        if state.canFinishRecording {
            return localeIdentifier.lowercased().hasPrefix("zh") ? "结束语音输入" : "Finish voice input"
        }
        if case .transcribing = state {
            return localeIdentifier.lowercased().hasPrefix("zh") ? "正在识别整段语音" : "Transcribing the full recording"
        }
        if state.canRetry {
            return localeIdentifier.lowercased().hasPrefix("zh") ? "重试语音输入" : "Retry voice input"
        }
        return title
    }

    var body: some View {
        Button(action: action) {
            ZStack {
                if state.isActive {
                    Circle()
                        .fill(Color(nsColor: .controlAccentColor).opacity(reduceMotion ? 0.12 : 0.16))
                        .frame(width: 24, height: 24)
                        .scaleEffect(pulse ? 1.16 : 0.84)
                        .opacity(pulse ? 0.28 : 0.8)
                }

                Image(systemName: iconName)
                    .font(.system(size: MainPanelIconMetrics.glyphSize, weight: .medium))
                    .foregroundStyle(foregroundColor)
            }
            .frame(width: MainPanelIconMetrics.buttonSize, height: MainPanelIconMetrics.buttonSize)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(isDisabled || state == .transcribing || state.isTranscriptReady)
        .accessibilityLabel(Text(accessibilityLabel))
        .accessibilityValue(Text(state.accessibilityDetail(localeIdentifier: localeIdentifier)))
        .help(state.accessibilityDetail(localeIdentifier: localeIdentifier))
        .onAppear { updatePulse() }
        .onChange(of: state) { updatePulse() }
        .onChange(of: reduceMotion) { updatePulse() }
    }

    private func updatePulse() {
        pulse = false
        guard state.canFinishRecording, !reduceMotion else { return }
        withAnimation(.easeInOut(duration: 0.72).repeatForever(autoreverses: true)) {
            pulse = true
        }
    }
}
