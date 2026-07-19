import SwiftUI
import AppKit

struct ArtifactFileList: View {
    let artifacts: [TaskOrchestrationViewModel.Artifact]
    let onPreview: (TaskOrchestrationViewModel.Artifact) -> Void

    @State private var isArtifactsExpanded = false
    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    init(
        artifacts: [TaskOrchestrationViewModel.Artifact],
        onPreview: @escaping (TaskOrchestrationViewModel.Artifact) -> Void = { _ in }
    ) {
        self.artifacts = artifacts
        self.onPreview = onPreview
    }

    private var displayArtifacts: [TaskOrchestrationViewModel.Artifact] {
        var bestByPath: [String: (index: Int, artifact: TaskOrchestrationViewModel.Artifact)] = [:]

        for (index, artifact) in artifacts.enumerated() {
            let key = artifactDisplayKey(artifact)
            if let existing = bestByPath[key] {
                if shouldReplaceArtifact(existing.artifact, with: artifact) || artifactStatusRank(existing.artifact) == artifactStatusRank(artifact) {
                    bestByPath[key] = (index, artifact)
                }
            } else {
                bestByPath[key] = (index, artifact)
            }
        }

        return bestByPath.values
            .sorted { $0.index < $1.index }
            .map(\.artifact)
    }

    var body: some View {
        MinimalDisclosureSection(
            title: appPreferences.text("tasks.artifacts"),
            detail: "\(displayArtifacts.count)",
            isExpanded: $isArtifactsExpanded
        ) {
            VStack(spacing: 4) {
                ForEach(displayArtifacts) { artifact in
                    ArtifactRow(artifact: artifact) {
                        onPreview(artifact)
                    }
                }
            }
        }
    }

    private func artifactDisplayKey(_ artifact: TaskOrchestrationViewModel.Artifact) -> String {
        let path = artifact.filePath.trimmingCharacters(in: .whitespacesAndNewlines)
        if !path.isEmpty {
            return path
        }
        return artifact.fileName.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func shouldReplaceArtifact(
        _ current: TaskOrchestrationViewModel.Artifact,
        with candidate: TaskOrchestrationViewModel.Artifact
    ) -> Bool {
        artifactStatusRank(candidate) > artifactStatusRank(current)
    }

    private func artifactStatusRank(_ artifact: TaskOrchestrationViewModel.Artifact) -> Int {
        switch artifact.status?.lowercased() {
        case "accepted":
            return 5
        case "completed", "produced", "available":
            return 4
        case "pending", "running":
            return 3
        case nil:
            return 2
        case "rejected", "failed", "cancelled":
            return 1
        default:
            return 2
        }
    }
}

struct ArtifactRow: View {
    let artifact: TaskOrchestrationViewModel.Artifact
    let onPreview: () -> Void

    @State private var isHovered = false
    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    private var supportsPreview: Bool {
        artifact.filePath.hasPrefix("/api/workers/artifacts/")
    }

    var body: some View {
        Button {
            if supportsPreview {
                onPreview()
            } else {
                NSWorkspace.shared.selectFile(artifact.filePath, inFileViewerRootedAtPath: "")
            }
        } label: {
            HStack(spacing: 10) {
                SVGIconView(name: getFileIconName(fileName: artifact.fileName), size: 16)

                VStack(alignment: .leading, spacing: 2) {
                    Text(artifact.fileName)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(theme.strongText)

                    Text(artifact.filePath)
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }

                Spacer()

                Text(artifact.fileSize)
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)

                if supportsPreview {
                    Image(systemName: "eye")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                        .accessibilityHidden(true)
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(isHovered ? theme.hoverBackground : Color.clear)
        .cornerRadius(6)
        .contentShape(Rectangle())
        .onHover { hovering in
            withAnimation(.easeInOut(duration: 0.1)) {
                isHovered = hovering
            }
        }
        .accessibilityLabel(artifact.fileName)
        .accessibilityHint(
            supportsPreview
                ? appPreferences.text("tasks.artifacts.previewHint")
                : appPreferences.text("diagnostics.openPath")
        )
    }
}

struct TaskArtifactPreviewSheet: View {
    let preview: TaskOrchestrationViewModel.ArtifactPreview
    let onClose: () -> Void
    @EnvironmentObject private var appPreferences: AppPreferences

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(spacing: 12) {
                Image(systemName: "doc.text")
                    .foregroundStyle(AcrossTheme.accent)
                Text(preview.fileName)
                    .font(.headline)
                Spacer()
                Button(action: onClose) {
                    Image(systemName: "xmark")
                }
                .buttonStyle(.plain)
                .accessibilityLabel(appPreferences.text("settings.close"))
            }

            ScrollView {
                Text(preview.content)
                    .font(.system(.body, design: .monospaced))
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .padding(20)
        .frame(minWidth: 640, minHeight: 460)
    }
}
