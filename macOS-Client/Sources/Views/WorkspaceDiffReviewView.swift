import SwiftUI

@MainActor
struct WorkspaceDiffReviewView: View {
    let files: [WorkspaceDiffFile]
    let comments: [AgentWorkspaceLineReviewCommentMetadata]
    let canComment: Bool
    let isSubmitting: Bool
    @Binding var selectedAnchor: WorkspaceDiffLineAnchor?
    @Binding var comment: String
    @ObservedObject var preferences: AppPreferences
    let onSubmit: () -> Void

    @Environment(\.colorScheme) private var colorScheme
    @FocusState private var commentIsFocused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(files) { file in
                VStack(alignment: .leading, spacing: 0) {
                    HStack(spacing: 7) {
                        Image(systemName: "doc.text")
                            .accessibilityHidden(true)
                        Text(file.path)
                            .font(.system(size: 10, weight: .semibold, design: .monospaced))
                            .lineLimit(1)
                            .truncationMode(.middle)
                        Spacer()
                        Text("\(file.lines.filter { $0.anchor != nil }.count)")
                            .font(.system(size: 9, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                    .padding(.horizontal, 9)
                    .frame(height: 32)
                    .background(AcrossTheme.panelFill(for: colorScheme))

                    ForEach(file.lines) { line in
                        diffLine(line)
                    }
                }
                .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.controlCornerRadius))
                .overlay {
                    RoundedRectangle(cornerRadius: AcrossTheme.Metrics.controlCornerRadius)
                        .stroke(AcrossTheme.separator(for: colorScheme), lineWidth: 1)
                }
            }

            if canComment, let selectedAnchor {
                anchoredCommentEditor(selectedAnchor)
            }

            if !comments.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text(preferences.text("workspace.comment.anchoredHistory"))
                        .font(.system(size: 10, weight: .semibold))
                    ForEach(comments) { item in
                        HStack(spacing: 8) {
                            Image(systemName: "text.bubble")
                                .foregroundStyle(.secondary)
                                .accessibilityHidden(true)
                            Text(item.displayText)
                                .font(.system(size: 9, design: .monospaced))
                            Spacer()
                            Text(item.side)
                                .font(.system(size: 8))
                                .foregroundStyle(.secondary)
                        }
                        .accessibilityElement(children: .combine)
                    }
                }
                .padding(9)
                .background(AcrossTheme.panelFill(for: colorScheme))
                .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.controlCornerRadius))
            }
        }
    }

    private func diffLine(_ line: WorkspaceDiffLine) -> some View {
        let isSelected = line.anchor == selectedAnchor
        return HStack(spacing: 0) {
            Text(line.oldLine.map(String.init) ?? "")
                .frame(width: 38, alignment: .trailing)
            Text(line.newLine.map(String.init) ?? "")
                .frame(width: 38, alignment: .trailing)
            Text(line.text)
                .frame(maxWidth: .infinity, alignment: .leading)
                .textSelection(.enabled)
            if let anchor = line.anchor, canComment {
                Button {
                    selectedAnchor = anchor
                    commentIsFocused = true
                } label: {
                    Image(systemName: isSelected ? "text.bubble.fill" : "text.bubble")
                        .frame(width: 24, height: 24)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(Text(String(format: preferences.text("workspace.comment.anchorLine"), anchor.displayText)))
                .help(String(format: preferences.text("workspace.comment.anchorLine"), anchor.displayText))
            } else {
                Color.clear.frame(width: 24, height: 24)
            }
        }
        .font(.system(size: 10, design: .monospaced))
        .padding(.horizontal, 7)
        .frame(minHeight: 26)
        .background(lineBackground(line.kind, isSelected: isSelected))
        .accessibilityElement(children: .contain)
    }

    private func anchoredCommentEditor(_ anchor: WorkspaceDiffLineAnchor) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(spacing: 7) {
                Label(anchor.displayText, systemImage: "scope")
                    .font(.system(size: 10, weight: .semibold, design: .monospaced))
                Spacer()
                Button {
                    selectedAnchor = nil
                } label: {
                    Image(systemName: "xmark")
                }
                .buttonStyle(.plain)
                .accessibilityLabel(Text(preferences.text("workspace.comment.clearAnchor")))
                .help(preferences.text("workspace.comment.clearAnchor"))
            }
            TextEditor(text: $comment)
                .font(.system(size: 11))
                .scrollContentBackground(.hidden)
                .padding(6)
                .frame(minHeight: 70)
                .background(AcrossTheme.recessedFill(for: colorScheme))
                .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.controlCornerRadius))
                .focused($commentIsFocused)
                .accessibilityLabel(Text(preferences.text("workspace.comment.inlineTitle")))
                .accessibilityHint(Text(anchor.displayText))
            HStack {
                Text(preferences.text("workspace.comment.inlineHint"))
                    .font(.system(size: 9))
                    .foregroundStyle(.secondary)
                Spacer()
                Button {
                    onSubmit()
                } label: {
                    Label(preferences.text("workspace.comment.relaunch"), systemImage: "arrow.clockwise.circle")
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(comment.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSubmitting)
                .keyboardShortcut(.return, modifiers: [.command])
            }
        }
        .padding(10)
        .background(AcrossTheme.panelFill(for: colorScheme))
        .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.cardCornerRadius))
        .overlay {
            RoundedRectangle(cornerRadius: AcrossTheme.Metrics.cardCornerRadius)
                .stroke(AcrossTheme.accent.opacity(0.55), lineWidth: 1)
        }
    }

    private func lineBackground(_ kind: WorkspaceDiffLineKind, isSelected: Bool) -> Color {
        if isSelected { return AcrossTheme.selectedFill(for: colorScheme) }
        switch kind {
        case .addition: return StatusPalette.tone(for: "success").foreground.opacity(0.08)
        case .deletion: return StatusPalette.tone(for: "error").foreground.opacity(0.08)
        case .context, .metadata: return AcrossTheme.recessedFill(for: colorScheme)
        }
    }
}
