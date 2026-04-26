import SwiftUI

struct MarkdownRenderer {
    static func render(_ markdown: String) -> AttributedString {
        // Simple markdown rendering - AttributedString has built-in markdown support
        return AttributedString(markdown)
    }

    static func renderWithCodeHighlighting(_ markdown: String) -> AttributedString {
        // First render the markdown
        let baseAttr = AttributedString(markdown)

        // For code highlighting, we need to manually find code blocks and style them
        // Simple approach: just return the base markdown-rendered string
        // Code block styling would require more complex attributed string manipulation

        return baseAttr
    }
}
