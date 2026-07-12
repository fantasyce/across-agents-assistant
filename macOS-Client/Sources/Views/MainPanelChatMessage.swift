import SwiftUI

struct AssistantMessageRow: View {
    let message: Message
    let agentName: String
    @ObservedObject var preferences: AppPreferences

    @State private var isHovered = false
    @State private var isCopied = false
    @FocusState private var isCopyFocused: Bool

    private var isError: Bool {
        !message.isUser && message.content.hasPrefix("\u{26A0}\u{FE0F}")
    }

    private var displayContent: String {
        guard isError else { return message.content }
        return message.content
            .replacingOccurrences(of: "\u{26A0}\u{FE0F}", with: "", options: [.anchored])
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var roleTitle: String {
        if isError { return preferences.text("chat.error") }
        return message.isUser ? preferences.text("chat.you") : agentName
    }

    private var roleColor: Color {
        isError ? Color(nsColor: .systemRed) : .secondary
    }

    var body: some View {
        HStack(alignment: .top, spacing: 18) {
            Text(roleTitle)
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(roleColor)
                .lineLimit(2)
                .multilineTextAlignment(.trailing)
                .frame(width: 92, alignment: .trailing)
                .padding(.top, 2)

            HStack(alignment: .top, spacing: 10) {
                if isError {
                    Image(systemName: "exclamationmark.circle.fill")
                        .font(.system(size: 13))
                        .foregroundStyle(Color(nsColor: .systemRed))
                        .padding(.top, 2)
                        .accessibilityHidden(true)
                }

                messageContent
                    .font(.system(size: 13))
                    .lineSpacing(4)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(.trailing, 34)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(Rectangle())
        .overlay(alignment: .topTrailing) {
            copyButton
                .padding(.top, 13)
                .padding(.trailing, 8)
                .opacity(isHovered || isCopied || isCopyFocused ? 1 : 0)
        }
        .onHover { hovering in
            withAnimation(.easeOut(duration: 0.12)) {
                isHovered = hovering
                if !hovering {
                    isCopied = false
                }
            }
        }
    }

    @MainActor
    @ViewBuilder
    private var messageContent: some View {
        if !displayContent.isEmpty || !message.attachedFiles.isEmpty {
            if message.attachedFiles.isEmpty {
                Text(MarkdownRenderer.renderWithCodeHighlighting(displayContent))
                    .textSelection(.enabled)
            } else {
                mixedContent()
                    .textSelection(.enabled)
            }
        }
    }

    @MainActor
    private func mixedContent() -> Text {
        let components = displayContent.components(separatedBy: "\u{FFFC}")
        var result = Text("")
        var fileIndex = 0

        for (index, component) in components.enumerated() {
            result = result + Text(component)
            if index < components.count - 1 && fileIndex < message.attachedFiles.count {
                result = result + renderedAttachment(message.attachedFiles[fileIndex])
                fileIndex += 1
            }
        }

        while fileIndex < message.attachedFiles.count {
            result = result + Text(" ") + renderedAttachment(message.attachedFiles[fileIndex])
            fileIndex += 1
        }

        return result
    }

    @MainActor
    private func renderedAttachment(_ file: AttachedFile) -> Text {
        let renderer = ImageRenderer(content: MessageAttachmentPreview(file: file, textColor: .primary))
        renderer.scale = NSScreen.main?.backingScaleFactor ?? 2.0
        guard let image = renderer.nsImage else {
            return Text(" [\(file.name)] ")
        }

        let isImagePreview = AttachmentImageSupport.isDisplayableImage(
            mimeType: file.mimeType,
            fileName: file.name
        )
        return Text(Image(nsImage: image)).baselineOffset(isImagePreview ? -58 : -3)
    }

    private var copyButton: some View {
        Button {
            let pasteboard = NSPasteboard.general
            pasteboard.clearContents()
            pasteboard.setString(displayContent, forType: .string)
            withAnimation(.easeOut(duration: 0.12)) {
                isCopied = true
            }
        } label: {
            Image(systemName: isCopied ? "checkmark" : "doc.on.doc")
                .font(.system(size: 10, weight: .semibold))
                .foregroundStyle(isCopied ? Color(nsColor: .systemGreen) : Color.secondary)
                .frame(width: 24, height: 24)
                .background(
                    RoundedRectangle(cornerRadius: 6, style: .continuous)
                        .fill(Color(nsColor: .controlBackgroundColor))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 6, style: .continuous)
                        .stroke(Color(nsColor: .separatorColor), lineWidth: 0.5)
                )
        }
        .buttonStyle(.plain)
        .focused($isCopyFocused)
        .accessibilityLabel(Text(preferences.text("chat.copyMessage")))
        .help(preferences.text("chat.copyMessage"))
    }
}
