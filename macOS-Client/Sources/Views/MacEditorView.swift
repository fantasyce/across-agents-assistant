import SwiftUI
import AppKit

struct MacEditorView: NSViewRepresentable {
    @Binding var text: String
    @Binding var attachedFiles: [AttachedFile]
    var onSubmit: () -> Void
    var onNavigateHistory: ((Bool) -> Void)? = nil
    var font: NSFont = .systemFont(ofSize: 13)
    var textColor: NSColor = .textColor
    
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
        textView.onSubmit = onSubmit
        textView.onNavigateHistory = onNavigateHistory
        
        scrollView.documentView = textView
        return scrollView
    }
    
    func updateNSView(_ scrollView: EditorScrollView, context: Context) {
        guard let textView = scrollView.documentView as? CustomTextView else { return }
        
        if textView.textColor != textColor {
            textView.textColor = textColor
        }
        
        // Avoid overwriting text during IME composition or if identical
        if textView.string != text {
            // Only update if not currently marked (IME typing) to prevent breaking IME
            if !textView.hasMarkedText() {
                // If there are attached files, we should rebuild the attributed string
                // But text already contains "\u{FFFC}" where attachments used to be.
                // Reconstructing it perfectly requires replacing "\u{FFFC}" with actual attachments.
                
                let newAttrStr = NSMutableAttributedString(string: text)
                var currentFileIndex = 0
                
                // Find all replacement characters and replace them with attachments
                let searchString = text as NSString
                var searchRange = NSRange(location: 0, length: searchString.length)
                
                while searchRange.location < searchString.length {
                    let foundRange = searchString.range(of: "\u{FFFC}", options: [], range: searchRange)
                    if foundRange.location == NSNotFound {
                        break
                    }
                    
                    if currentFileIndex < attachedFiles.count {
                        let file = attachedFiles[currentFileIndex]
                        let attachment = FileAttachment(file: file)
                        let attachmentString = NSAttributedString(attachment: attachment)
                        newAttrStr.replaceCharacters(in: foundRange, with: attachmentString)
                        currentFileIndex += 1
                        
                        // After replacement, the length of the string is the same (1 character for attachment)
                        searchRange.location = foundRange.location + 1
                        searchRange.length = searchString.length - searchRange.location
                    } else {
                        // More \u{FFFC} than attached files? Just remove or ignore.
                        break
                    }
                }
                
                textView.textStorage?.setAttributedString(newAttrStr)
                
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
            
            parent.text = textView.string
            
            // Extract attached files from text storage
            var extractedFiles: [AttachedFile] = []
            if let textStorage = textView.textStorage {
                textStorage.enumerateAttribute(.attachment, in: NSRange(location: 0, length: textStorage.length), options: []) { value, range, _ in
                    if let fileAttachment = value as? FileAttachment {
                        extractedFiles.append(fileAttachment.attachedFile)
                    }
                }
            }
            parent.attachedFiles = extractedFiles
            
            textView.invalidateIntrinsicContentSize()
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
    
    // Track if we are currently showing a history item
    var isShowingHistory: Bool = false
    
    override func didChangeText() {
        super.didChangeText()
        isShowingHistory = false
    }
    
    override func performDragOperation(_ sender: NSDraggingInfo) -> Bool {
        if let urls = sender.draggingPasteboard.readObjects(forClasses: [NSURL.self], options: nil) as? [URL], !urls.isEmpty {
            return insertFiles(urls: urls, sender: sender)
        }
        return super.performDragOperation(sender)
    }
    
    private func insertFiles(urls: [URL], sender: NSDraggingInfo) -> Bool {
        // Find drop location
        let point = self.convert(sender.draggingLocation, from: nil)
        let characterIndex = self.characterIndexForInsertion(at: point)
        
        let attrString = NSMutableAttributedString()
        
        for url in urls {
            let standardizedUrl = url.standardizedFileURL
            let isDir = (try? standardizedUrl.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) ?? false
            let file = AttachedFile(name: standardizedUrl.lastPathComponent, path: standardizedUrl.path, isFolder: isDir)
            
            let attachment = FileAttachment(file: file)
            let attachmentString = NSAttributedString(attachment: attachment)
            
            attrString.append(attachmentString)
            attrString.append(NSAttributedString(string: " ")) // Space after chip
        }
        
        // Apply styling
        let typingAttrs = self.typingAttributes
        attrString.addAttributes(typingAttrs, range: NSRange(location: 0, length: attrString.length))
        
        // Insert at drop location
        if let textStorage = self.textStorage {
            if self.shouldChangeText(in: NSRange(location: characterIndex, length: 0), replacementString: attrString.string) {
                textStorage.beginEditing()
                textStorage.insert(attrString, at: characterIndex)
                textStorage.endEditing()
                self.didChangeText() // Notify delegate
            }
        }
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
        
        // Enter key (36)
        if event.keyCode == 36 {
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
