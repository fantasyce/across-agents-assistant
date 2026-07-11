import SwiftUI
import AppKit

struct KeyEventHandler: NSViewRepresentable {
    var onKeyDown: (KeyEvent) -> Bool

    func makeNSView(context: Context) -> KeyEventView {
        let view = KeyEventView()
        view.onKeyDown = onKeyDown
        return view
    }

    func updateNSView(_ nsView: KeyEventView, context: Context) {
        nsView.onKeyDown = onKeyDown
    }
}

class KeyEventView: NSView {
    var onKeyDown: ((KeyEvent) -> Bool)?

    override var acceptsFirstResponder: Bool { true }

    override func keyDown(with event: NSEvent) {
        if event.modifierFlags.contains(.command) && event.keyCode == 13 {
            if let handler = onKeyDown {
                if handler(.close) {
                    return
                }
            }
        }
        super.keyDown(with: event)
    }

    override func performKeyEquivalent(with event: NSEvent) -> Bool {
        if event.modifierFlags.contains(.command) && event.keyCode == 13 {
            if let handler = onKeyDown {
                if handler(.close) {
                    return true
                }
            }
        }
        return super.performKeyEquivalent(with: event)
    }
}

enum KeyEvent {
    case close
}


