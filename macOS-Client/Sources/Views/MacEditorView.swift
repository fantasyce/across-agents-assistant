import SwiftUI
import AppKit

struct MacEditorView: NSViewRepresentable {
    @Binding var text: String
    var onSubmit: () -> Void
    var font: NSFont = .systemFont(ofSize: 13)
    var textColor: NSColor = .textColor
    
    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = NSScrollView()
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
        
        scrollView.documentView = textView
        return scrollView
    }
    
    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        guard let textView = scrollView.documentView as? CustomTextView else { return }
        
        if textView.textColor != textColor {
            textView.textColor = textColor
        }
        
        // Avoid overwriting text during IME composition or if identical
        if textView.string != text {
            // Only update if not currently marked (IME typing) to prevent breaking IME
            if !textView.hasMarkedText() {
                textView.string = text
                
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
            textView.invalidateIntrinsicContentSize()
        }
    }
}

class CustomTextView: NSTextView {
    var onSubmit: (() -> Void)?
    
    override var intrinsicContentSize: NSSize {
        guard let layoutManager = layoutManager, let textContainer = textContainer else {
            return super.intrinsicContentSize
        }
        layoutManager.ensureLayout(for: textContainer)
        let size = layoutManager.usedRect(for: textContainer).size
        // font size 13 typically has ~16pt line height. 16 * 5 = 80
        let height = min(max(size.height, 16), 80)
        return NSSize(width: NSView.noIntrinsicMetric, height: height)
    }
    
    override func keyDown(with event: NSEvent) {
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
        } else {
            super.keyDown(with: event)
            self.invalidateIntrinsicContentSize()
        }
    }
}
