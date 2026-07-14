import SwiftUI

struct SimpleStartWorkflowView: View {
    @ObservedObject var viewModel: TaskOrchestrationViewModel
    let defaultProjectPath: String?

    @State private var pluginTarget = ""
    @EnvironmentObject private var appPreferences: AppPreferences

    private var normalizedProjectPath: String? {
        let trimmed = defaultProjectPath?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return trimmed.isEmpty ? nil : trimmed
    }

    private var projectText: String {
        if let normalizedProjectPath {
            return String(
                format: appPreferences.text("tasks.simpleStart.project.active"),
                normalizedProjectPath
            )
        }
        return appPreferences.text("tasks.simpleStart.project.next")
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(appPreferences.text("tasks.simpleStart.title"))
                        .font(.title3.weight(.semibold))
                    Text(appPreferences.text("tasks.simpleStart.subtitle"))
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }

                Label(projectText, systemImage: "folder")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)

                Divider()

                VStack(spacing: 0) {
                    ForEach(SimpleStartWorkflowPreset.allCases) { preset in
                        SimpleStartWorkflowRow(
                            preset: preset,
                            targetText: preset == .pluginCompatibility ? $pluginTarget : .constant("")
                        ) {
                            startWorkflow(preset)
                        }

                        if preset != .releaseCaptain {
                            Divider().padding(.leading, 42)
                        }
                    }
                }

                Divider()

                Button {
                    viewModel.enterCreateMode()
                } label: {
                    Label(appPreferences.text("tasks.simpleStart.expert"), systemImage: "slider.horizontal.3")
                }
                .buttonStyle(.borderless)
                .help(appPreferences.text("tasks.simpleStart.expert.help"))
            }
            .minimalPageContentFrame(topPadding: 12)
        }
    }

    private func startWorkflow(_ preset: SimpleStartWorkflowPreset) {
        viewModel.startSimpleStartWorkflow(
            preset,
            target: preset == .pluginCompatibility ? pluginTarget : "",
            projectDirectory: normalizedProjectPath
        )
    }
}

private struct SimpleStartWorkflowRow: View {
    let preset: SimpleStartWorkflowPreset
    @Binding var targetText: String
    let onStart: () -> Void

    @EnvironmentObject private var appPreferences: AppPreferences

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            Image(systemName: preset.iconSystemName)
                .font(.system(size: 16, weight: .medium))
                .foregroundStyle(.secondary)
                .frame(width: 28, height: 28)
                .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: 6) {
                Text(appPreferences.text(preset.titleKey))
                    .font(.body.weight(.medium))
                Text(appPreferences.text(preset.subtitleKey))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)

                if let placeholderKey = preset.targetPlaceholderKey {
                    TextField(appPreferences.text(placeholderKey), text: $targetText)
                        .textFieldStyle(.roundedBorder)
                        .frame(maxWidth: 440)
                        .padding(.top, 2)
                }
            }

            Spacer(minLength: 16)

            Button(action: onStart) {
                Label(appPreferences.text(preset.actionKey), systemImage: "play.fill")
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
        }
        .padding(.vertical, 14)
        .contentShape(Rectangle())
    }
}
