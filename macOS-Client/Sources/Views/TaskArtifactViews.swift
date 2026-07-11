import SwiftUI
import AppKit

struct ArtifactFileList: View {
    let artifacts: [TaskOrchestrationViewModel.Artifact]

    @State private var isArtifactsExpanded = false
    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

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
        VStack(alignment: .leading, spacing: 12) {
            Button(action: { isArtifactsExpanded.toggle() }) {
                HStack(spacing: 6) {
                    Text(appPreferences.text("tasks.artifacts"))
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(theme.primaryText)

                    Text("(\(displayArtifacts.count))")
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)

                    Image(systemName: "doc.on.doc.fill")
                        .font(.system(size: 12))
                        .foregroundColor(AcrossTheme.accent)

                    Image(systemName: isArtifactsExpanded ? "chevron.down" : "chevron.right")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.secondary)

                    Spacer()
                }
            }
            .buttonStyle(.plain)

            if isArtifactsExpanded {
                VStack(spacing: 4) {
                    ForEach(displayArtifacts) { artifact in
                        ArtifactRow(artifact: artifact)
                    }
                }
            }
        }
        .animation(.easeInOut(duration: 0.2), value: isArtifactsExpanded)
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

    @State private var isHovered = false
    @Environment(\.colorScheme) private var colorScheme
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    var body: some View {
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
        }
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
        .onTapGesture {
            NSWorkspace.shared.selectFile(artifact.filePath, inFileViewerRootedAtPath: "")
        }
    }
}
