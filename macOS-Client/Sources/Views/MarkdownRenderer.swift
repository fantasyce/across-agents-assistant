import SwiftUI

struct MarkdownRenderer {
    static func render(_ markdown: String) -> AttributedString {
        do {
            return try AttributedString(markdown, options: AttributedString.MarkdownParsingOptions(
                interpretedSyntax: .inlineOnlyPreservingWhitespace
            ))
        } catch {
            return AttributedString(markdown)
        }
    }

    static func renderWithCodeHighlighting(_ markdown: String) -> AttributedString {
        // Simple approach: render markdown first, then apply code styling
        let codeBlockPattern = "```([\\s\\S]*?)```"
        guard let regex = try? NSRegularExpression(pattern: codeBlockPattern, options: []) else {
            return render(markdown)
        }

        var result = AttributedString()
        var lastIndex = markdown.startIndex

        let matches = regex.matches(in: markdown, range: NSRange(markdown.startIndex..., in: markdown))

        for match in matches {
            guard let range = Range(match.range, in: markdown),
                  let codeRange = Range(match.range(at: 1), in: markdown) else { continue }

            // Add text before code block
            let textBefore = String(markdown[lastIndex..<range.lowerBound])
            result += AttributedString(textBefore)

            // Add code block with styling
            let code = String(markdown[codeRange])
            var codeAttr = AttributedString(code)
            if let monoFont = NSFont.monospacedSystemFont(ofSize: 12, weight: .regular) as Font? {
                codeAttr.font = monoFont
            }
            codeAttr.backgroundColor = Color.gray.opacity(0.15)
            result += codeAttr

            lastIndex = range.upperBound
        }

        // Add remaining text
        if lastIndex < markdown.endIndex {
            let remaining = String(markdown[lastIndex...])
            result += AttributedString(remaining)
        }

        return result
    }
}
