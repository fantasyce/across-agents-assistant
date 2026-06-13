import AppKit
import SwiftUI

final class AXSynchronizedTextField: NSTextField {
    var onTextChange: ((String) -> Void)?

    override func accessibilityValue() -> String? {
        stringValue
    }

    override func setAccessibilityValue(_ accessibilityValue: Any?) {
        super.setAccessibilityValue(accessibilityValue)
        guard let value = Self.string(fromAccessibilityValue: accessibilityValue) else {
            return
        }
        if stringValue != value {
            stringValue = value
        }
        onTextChange?(value)
    }

    private static func string(fromAccessibilityValue value: Any?) -> String? {
        if let string = value as? String {
            return string
        }
        if let string = value as? NSString {
            return string as String
        }
        if let attributedString = value as? NSAttributedString {
            return attributedString.string
        }
        return nil
    }
}

struct AccessibleTextField: NSViewRepresentable {
    let placeholder: String
    @Binding var text: String
    var textColor: NSColor = .labelColor
    var font: NSFont = .systemFont(ofSize: 13)

    func makeCoordinator() -> Coordinator {
        Coordinator(text: $text)
    }

    func makeNSView(context: Context) -> AXSynchronizedTextField {
        let field = AXSynchronizedTextField()
        field.isBordered = false
        field.isBezeled = false
        field.drawsBackground = false
        field.focusRingType = .none
        field.lineBreakMode = .byTruncatingMiddle
        field.delegate = context.coordinator
        field.placeholderString = placeholder
        field.stringValue = text
        field.textColor = textColor
        field.font = font
        field.onTextChange = { value in
            context.coordinator.updateText(value)
        }
        return field
    }

    func updateNSView(_ field: AXSynchronizedTextField, context: Context) {
        context.coordinator.text = $text
        field.placeholderString = placeholder
        field.textColor = textColor
        field.font = font
        field.onTextChange = { value in
            context.coordinator.updateText(value)
        }
        if field.stringValue != text {
            field.stringValue = text
        }
    }

    final class Coordinator: NSObject, NSTextFieldDelegate {
        var text: Binding<String>

        init(text: Binding<String>) {
            self.text = text
        }

        func controlTextDidChange(_ notification: Notification) {
            guard let field = notification.object as? NSTextField else {
                return
            }
            updateText(field.stringValue)
        }

        func controlTextDidEndEditing(_ notification: Notification) {
            guard let field = notification.object as? NSTextField else {
                return
            }
            updateText(field.stringValue)
        }

        func updateText(_ value: String) {
            if text.wrappedValue != value {
                text.wrappedValue = value
            }
        }
    }
}
