import SwiftUI
import AppKit

struct MacEditorView: NSViewRepresentable {
    @Binding var text: String
    @Binding var attachedFiles: [AttachedFile]
    var onSubmit: () -> Void
    var onNavigateHistory: ((Bool) -> Void)? = nil
    var font: NSFont = .systemFont(ofSize: 13)
    var textColor: NSColor = .textColor
    var accessibilityLabel: String = "Message"
    var needsResign: Bool = false

    func makeNSView(context: Context) -> EditorScrollView {
        let scrollView = EditorScrollView()
        scrollView.hasVerticalScroller = true
        scrollView.autohidesScrollers = true
        scrollView.drawsBackground = false

        let textView = CustomTextView()
        textView.delegate = context.coordinator
        textView.font = font
        textView.textColor = textColor
        // explicitly set typing attributes
        textView.typingAttributes[.font] = font
        textView.typingAttributes[.foregroundColor] = textColor
        textView.backgroundColor = .clear
        textView.isRichText = false
        textView.allowsUndo = true
        textView.autoresizingMask = [.width]
        textView.isVerticallyResizable = true
        textView.isHorizontallyResizable = false
        textView.textContainer?.widthTracksTextView = true
        textView.textContainerInset = NSSize(width: 0, height: 0)
        textView.setAccessibilityLabel(accessibilityLabel)
        textView.onSubmit = onSubmit
        textView.onNavigateHistory = onNavigateHistory
        textView.onAttachFiles = { files in
            context.coordinator.attachFiles(files)
        }

        scrollView.documentView = textView
        return scrollView
    }

    func updateNSView(_ scrollView: EditorScrollView, context: Context) {
        guard let textView = scrollView.documentView as? CustomTextView else { return }
        context.coordinator.parent = self
        textView.onSubmit = onSubmit
        textView.onNavigateHistory = onNavigateHistory
        textView.setAccessibilityLabel(accessibilityLabel)
        textView.onAttachFiles = { files in
            context.coordinator.attachFiles(files)
        }

        // Handle resign first responder request
        if needsResign {
            textView.window?.makeFirstResponder(nil)
            return
        }

        if textView.textColor != textColor {
            textView.textColor = textColor
        }

        // Avoid overwriting text during IME composition or if identical
        let cleanText = editorPlainText(text)
        if textView.string != cleanText {
            // Only update if not currently marked (IME typing) to prevent breaking IME
            if !textView.hasMarkedText() {
                textView.textStorage?.setAttributedString(NSAttributedString(
                    string: cleanText,
                    attributes: [
                        .font: font,
                        .foregroundColor: textColor
                    ]
                ))

                // IMPORTANT: Setting string clears typing attributes! We must restore them.
                textView.font = font
                textView.textColor = textColor

                textView.invalidateIntrinsicContentSize()
                if text.isEmpty {
                    textView.scrollToBeginningOfDocument(nil)
                }
            }
        }
    }

    private func editorPlainText(_ value: String) -> String {
        value.replacingOccurrences(of: "\u{FFFC}", with: "")
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(self)
    }

    class Coordinator: NSObject, NSTextViewDelegate {
        var parent: MacEditorView
        init(_ parent: MacEditorView) { self.parent = parent }

        func textDidChange(_ notification: Notification) {
            guard let textView = notification.object as? CustomTextView else { return }

            // Re-apply typing attributes in case they got lost when empty
            if textView.string.isEmpty || textView.typingAttributes[.font] == nil {
                textView.typingAttributes[.font] = parent.font
                textView.typingAttributes[.foregroundColor] = parent.textColor
            }

            parent.text = parent.editorPlainText(textView.string)

            textView.invalidateIntrinsicContentSize()
        }

        func attachFiles(_ files: [AttachedFile]) {
            guard !files.isEmpty else { return }
            parent.attachedFiles.append(contentsOf: files)
        }
    }
}

class EditorScrollView: NSScrollView {
    override var intrinsicContentSize: NSSize {
        return documentView?.intrinsicContentSize ?? super.intrinsicContentSize
    }
}

class CustomTextView: NSTextView {
    var onSubmit: (() -> Void)?
    var onNavigateHistory: ((Bool) -> Void)?
    var onAttachFiles: (([AttachedFile]) -> Void)?

    // Track if we are currently showing a history item
    var isShowingHistory: Bool = false

    override func didChangeText() {
        super.didChangeText()
        isShowingHistory = false
    }

    override var readablePasteboardTypes: [NSPasteboard.PasteboardType] {
        var types = super.readablePasteboardTypes
        types.append(AttachmentImageSupport.pngPasteboardType)
        types.append(.tiff)
        return types
    }

    override func validateUserInterfaceItem(_ item: NSValidatedUserInterfaceItem) -> Bool {
        if item.action == #selector(paste(_:)),
           AttachmentImageSupport.pngData(from: NSPasteboard.general) != nil {
            return true
        }
        return super.validateUserInterfaceItem(item)
    }

    override func performDragOperation(_ sender: NSDraggingInfo) -> Bool {
        if let urls = sender.draggingPasteboard.readObjects(forClasses: [NSURL.self], options: nil) as? [URL], !urls.isEmpty {
            return insertFiles(urls: urls, sender: sender)
        }
        return super.performDragOperation(sender)
    }

    override func paste(_ sender: Any?) {
        let pasteboard = NSPasteboard.general
        if insertImage(from: pasteboard) {
            return
        }
        if let urls = pasteboard.readObjects(forClasses: [NSURL.self], options: nil) as? [URL], !urls.isEmpty {
            _ = insertFiles(urls: urls, replacementRange: selectedRange())
            return
        }
        super.paste(sender)
    }

    private func insertFiles(urls: [URL], sender: NSDraggingInfo) -> Bool {
        let point = self.convert(sender.draggingLocation, from: nil)
        let characterIndex = self.characterIndexForInsertion(at: point)
        return insertFiles(urls: urls, replacementRange: NSRange(location: characterIndex, length: 0))
    }

    private func insertImage(from pasteboard: NSPasteboard) -> Bool {
        guard let pngData = AttachmentImageSupport.pngData(from: pasteboard) else { return false }

        let fileName = AttachmentImageSupport.pastedImageFileName()
        let fileURL = LocalAppPaths.screenshotAttachmentsDir.appendingPathComponent(fileName)
        do {
            try pngData.write(to: fileURL, options: .atomic)
        } catch {
            return false
        }

        let file = AttachedFile(
            name: fileName,
            path: fileURL.path,
            isFolder: false,
            kind: "image",
            mimeType: "image/png"
        )
        return insertAttachedFiles([file], replacementRange: selectedRange())
    }

    private func insertFiles(urls: [URL], replacementRange: NSRange) -> Bool {
        let files = urls.map { url in
            let standardizedUrl = url.standardizedFileURL
            let isDir = (try? standardizedUrl.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) ?? false
            return AttachedFile(name: standardizedUrl.lastPathComponent, path: standardizedUrl.path, isFolder: isDir)
        }
        return insertAttachedFiles(files, replacementRange: replacementRange)
    }

    private func insertAttachedFiles(_ files: [AttachedFile], replacementRange _: NSRange) -> Bool {
        guard !files.isEmpty else { return false }
        onAttachFiles?(files)
        return true
    }

    override var intrinsicContentSize: NSSize {
        guard let layoutManager = layoutManager, let textContainer = textContainer else {
            return super.intrinsicContentSize
        }
        layoutManager.ensureLayout(for: textContainer)
        let size = layoutManager.usedRect(for: textContainer).size
        // Ensure a stable minimum height so it doesn't jump slightly on first character
        // For size 13 font, the empty height is often 0 or very small, and 1 line is ~16
        // Setting min height to 18 provides a stable buffer
        let height = min(max(ceil(size.height), 18), 80) // 1 to ~5 lines
        return NSSize(width: NSView.noIntrinsicMetric, height: height)
    }

    override func invalidateIntrinsicContentSize() {
        super.invalidateIntrinsicContentSize()
        self.enclosingScrollView?.invalidateIntrinsicContentSize()
    }

    override func keyDown(with event: NSEvent) {
        // Handle IME confirmation (Marked Text)
        if self.hasMarkedText() {
            super.keyDown(with: event)
            return
        }

        // Tab moves through the surrounding composer controls. NSTextView's
        // default is to insert a tab, which traps keyboard and VoiceOver users
        // inside the work composer.
        if event.keyCode == 48 {
            if event.modifierFlags.contains(.shift) {
                window?.selectPreviousKeyView(self)
            } else {
                window?.selectNextKeyView(self)
            }
        // Enter key (36)
        } else if event.keyCode == 36 {
            if event.modifierFlags.contains(.shift) {
                // Shift+Enter -> Insert newline
                self.insertText("\n", replacementRange: self.selectedRange())
                self.invalidateIntrinsicContentSize()
            } else {
                // Enter without shift -> Submit
                onSubmit?()
            }
        } else if event.keyCode == 126 { // Up arrow
            if self.string.isEmpty || isShowingHistory {
                onNavigateHistory?(true)
                isShowingHistory = true
            } else {
                super.keyDown(with: event)
            }
            self.invalidateIntrinsicContentSize()
        } else if event.keyCode == 125 { // Down arrow
            if self.string.isEmpty || isShowingHistory {
                onNavigateHistory?(false)
                isShowingHistory = true
            } else {
                super.keyDown(with: event)
            }
            self.invalidateIntrinsicContentSize()
        } else {
            super.keyDown(with: event)
            self.invalidateIntrinsicContentSize()
        }
    }
}
