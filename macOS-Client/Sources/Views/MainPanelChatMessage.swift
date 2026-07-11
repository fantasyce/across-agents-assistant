import SwiftUI

struct LegacyMessageBubble: View {
    let message: Message
    let userBgColor: Color
    let userTextColor: Color
    let agentTextColor: Color

    @State private var isHovered = false
    @State private var isCopied = false

    var body: some View {
        HStack(alignment: .bottom) {
            if message.isUser {
                Spacer(minLength: 40)
                VStack(alignment: .trailing, spacing: 4) {
                    bubbleContent

                    // The row for the copy button always exists to prevent layout shifts
                    copyButton
                        .opacity(isHovered ? 1 : 0)
                        .offset(x: 2)
                }
            } else {
                VStack(alignment: .leading, spacing: 4) {
                    bubbleContent

                    // The row for the copy button always exists to prevent layout shifts
                    copyButton
                        .opacity(isHovered ? 1 : 0)
                        .offset(x: -2)
                }
                Spacer(minLength: 40)
            }
        }
        .contentShape(Rectangle())
        .onHover { hovering in
            withAnimation(.easeInOut(duration: 0.1)) {
                isHovered = hovering
                if !hovering {
                    // Reset copied state when mouse leaves the message bubble
                    isCopied = false
                }
            }
        }
    }

    @MainActor
    private var bubbleContent: some View {
        VStack(alignment: message.isUser ? .trailing : .leading, spacing: 6) {
            if !message.content.isEmpty {
                if message.attachedFiles.isEmpty {
                    Text(MarkdownRenderer.renderWithCodeHighlighting(message.content))
                        .textSelection(.enabled)
                        .font(.system(size: 13))
                        .lineSpacing(4)
                } else {
                    mixedContent()
                        .textSelection(.enabled)
                        .font(.system(size: 13))
                        .lineSpacing(4)
                }
            } else if !message.attachedFiles.isEmpty {
                mixedContent()
                    .textSelection(.enabled)
                    .font(.system(size: 13))
                    .lineSpacing(4)
            }
        }
        .padding(.horizontal, message.isUser ? 12 : 0)
        .padding(.vertical, message.isUser ? 8 : 4)
        .background(message.isUser ? userBgColor : Color.clear)
        .foregroundColor(message.isUser ? userTextColor : agentTextColor)
        .clipShape(
            CustomRoundedCorners(
                topLeading: message.isUser ? 12 : 0,
                topTrailing: message.isUser ? 12 : 0,
                bottomLeading: message.isUser ? 12 : 0,
                bottomTrailing: 0
            )
        )
    }

    @MainActor
    private func mixedContent() -> Text {
        let components = message.content.components(separatedBy: "\u{FFFC}")
        var result = Text("")
        var fileIndex = 0

        let textColorToUse = message.isUser ? userTextColor : agentTextColor

        for (i, component) in components.enumerated() {
            result = result + Text(component)
            if i < components.count - 1 && fileIndex < message.attachedFiles.count {
                let file = message.attachedFiles[fileIndex]

                let renderer = ImageRenderer(content: AttachmentPreviewView(file: file, textColor: textColorToUse))
                renderer.scale = NSScreen.main?.backingScaleFactor ?? 2.0
                if let image = renderer.nsImage {
                    let isImagePreview = AttachmentImageSupport.isDisplayableImage(
                        mimeType: file.mimeType,
                        fileName: file.name
                    )
                    result = result + Text(Image(nsImage: image)).baselineOffset(isImagePreview ? -58 : -3)
                } else {
                    result = result + Text(" [\(file.name)] ")
                }

                fileIndex += 1
            }
        }

        // If there are leftover files that weren't represented by \u{FFFC} (shouldn't happen normally)
        while fileIndex < message.attachedFiles.count {
            let file = message.attachedFiles[fileIndex]
            let renderer = ImageRenderer(content: AttachmentPreviewView(file: file, textColor: textColorToUse))
            renderer.scale = NSScreen.main?.backingScaleFactor ?? 2.0
            if let image = renderer.nsImage {
                let isImagePreview = AttachmentImageSupport.isDisplayableImage(
                    mimeType: file.mimeType,
                    fileName: file.name
                )
                result = result + Text(" ") + Text(Image(nsImage: image)).baselineOffset(isImagePreview ? -58 : -3)
            }
            fileIndex += 1
        }

        return result
    }

    private var copyButton: some View {
        Button(action: {
            let pasteboard = NSPasteboard.general
            pasteboard.clearContents()
            pasteboard.setString(message.content, forType: .string)
            withAnimation {
                isCopied = true
            }
        }) {
            ZStack {
                Image(systemName: "doc.on.doc")
                    .font(.system(size: 10))
                    .opacity(isCopied ? 0 : 1)

                Image(systemName: "checkmark")
                    .font(.system(size: 10, weight: .bold))
                    .opacity(isCopied ? 1 : 0)
            }
            .foregroundColor(isCopied ? .green : .secondary)
            .frame(width: 14, height: 14) // Fixed frame to prevent layout shifts
            .padding(4)
            .background(Color.black.opacity(0.1))
            .cornerRadius(4)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(Text("Copy message"))
        .help("Copy message")
    }
}


