import AppKit
import Testing
@testable import AcrossAgentsAssistantClient

struct AccessibleTextFieldTests {
    @MainActor
    @Test func accessibilityValueSetterSynchronizesStringValueAndBindingCallback() {
        let field = AXSynchronizedTextField()
        var capturedValue: String?
        field.onTextChange = { capturedValue = $0 }

        field.setAccessibilityValue("/tmp/across-ui-project")

        #expect(field.stringValue == "/tmp/across-ui-project")
        #expect(capturedValue == "/tmp/across-ui-project")
    }
}
