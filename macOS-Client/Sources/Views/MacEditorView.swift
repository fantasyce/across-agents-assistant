import SwiftUI
import AppKit

struct MacEditorView: NSViewRepresentable {
    @Binding var text: String
    var onSubmit: () -> Void
    var font: NSFont = .systemFont(ofSize: 13)
    
    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = NSScrollView()
        scrollView.hasVerticalScroller = true
        scrollView.autohidesScrollers = true
        scrollView.drawsBackground = false
        
        let textView = CustomTextView()
        textView.delegate = context.coordinator
        textView.font = font
        textView.backgroundColor = .clear
        textView.isRichText = false
        textView.allowsUndo = true
        textView.autoresizingMask = [.width]
        textView.isVerticallyResizable = true
        textView.isHorizontallyResizable = false
        textView.textContainer?.widthTracksTextView = true
        // Set text container inset so it matches standard TextField padding roughly
        textView.textContainerInset = NSSize(width: 0, height: 0)
        textView.onSubmit = onSubmit
        
        scrollView.documentView = textView
        return scrollView
    }
    
    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        guard let textView = scrollView.documentView as? CustomTextView else { return }
        if textView.string != text {
            textView.string = text
            textView.invalidateIntrinsicContentSize()
            // Scroll to end if we just cleared the text or appended
            if text.isEmpty {
                textView.scrollToBeginningOfDocument(nil)
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
        // Enter key without shift submits
        if event.keyCode == 36 && !event.modifierFlags.contains(.shift) {
            onSubmit?()
        } else {
            super.keyDown(with: event)
            self.invalidateIntrinsicContentSize()
        }
    }
}
