import SwiftUI
import AppKit

struct SimpleStartWorkflowView: View {
    @ObservedObject var viewModel: TaskOrchestrationViewModel
    let defaultProjectPath: String?

    @State private var pluginTarget = ""
    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    private var normalizedProjectPath: String? {
        let trimmed = defaultProjectPath?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return trimmed.isEmpty ? nil : trimmed
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                VStack(alignment: .leading, spacing: 8) {
                    Text(appPreferences.text("tasks.simpleStart.title"))
                        .font(.system(size: 22, weight: .semibold))
                        .foregroundColor(theme.primaryText)
                        .fixedSize(horizontal: false, vertical: true)

                    Text(appPreferences.text("tasks.simpleStart.subtitle"))
                        .font(.system(size: 13))
                        .foregroundColor(theme.mutedText)
                        .fixedSize(horizontal: false, vertical: true)
                }

                VStack(spacing: 12) {
                    ForEach(SimpleStartWorkflowPreset.allCases) { preset in
                        SimpleStartWorkflowCard(
                            preset: preset,
                            projectPath: normalizedProjectPath,
                            targetText: preset == .pluginCompatibility ? $pluginTarget : .constant(""),
                            onStart: { startWorkflow(preset) }
                        )
                    }
                }

                HStack(spacing: 10) {
                    Button(action: { viewModel.enterCreateMode() }) {
                        HStack(spacing: 7) {
                            Image(systemName: "slider.horizontal.3")
                                .font(.system(size: 12, weight: .semibold))
                            Text(appPreferences.text("tasks.simpleStart.expert"))
                                .font(.system(size: 12, weight: .medium))
                        }
                        .foregroundColor(theme.primaryText)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .background(theme.controlBackground)
                        .cornerRadius(8)
                    }
                    .buttonStyle(.plain)
                    .help(appPreferences.text("tasks.simpleStart.expert.help"))

                    Text(appPreferences.text("tasks.simpleStart.boundary"))
                        .font(.system(size: 11))
                        .foregroundColor(theme.mutedText)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(32)
            .frame(maxWidth: 920, alignment: .leading)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
    }

    private func startWorkflow(_ preset: SimpleStartWorkflowPreset) {
        let target = preset == .pluginCompatibility ? pluginTarget : ""
        viewModel.startSimpleStartWorkflow(
            preset,
            target: target,
            projectDirectory: normalizedProjectPath
        )
    }
}

struct SimpleStartWorkflowCard: View {
    let preset: SimpleStartWorkflowPreset
    let projectPath: String?
    @Binding var targetText: String
    let onStart: () -> Void

    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    private var accent: Color { Color(hex: preset.accentHex) }

    private var projectText: String {
        if let projectPath, !projectPath.isEmpty {
            return String(format: appPreferences.text("tasks.simpleStart.project.active"), projectPath)
        }
        return appPreferences.text("tasks.simpleStart.project.next")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top, spacing: 14) {
                Image(systemName: preset.iconSystemName)
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(accent)
                    .frame(width: 38, height: 38)
                    .background(accent.opacity(0.12))
                    .cornerRadius(8)

                VStack(alignment: .leading, spacing: 5) {
                    Text(appPreferences.text(preset.titleKey))
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(theme.primaryText)
                        .fixedSize(horizontal: false, vertical: true)

                    Text(appPreferences.text(preset.subtitleKey))
                        .font(.system(size: 12))
                        .foregroundColor(theme.mutedText)
                        .lineLimit(3)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Spacer(minLength: 12)
            }

            if let placeholderKey = preset.targetPlaceholderKey {
                TextField(appPreferences.text(placeholderKey), text: $targetText)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(theme.primaryText)
                    .padding(9)
                    .background(theme.fieldBackground)
                    .cornerRadius(8)
            }

            HStack(spacing: 12) {
                Text(projectText)
                    .font(.system(size: 11))
                    .foregroundColor(theme.mutedText)
                    .lineLimit(1)
                    .truncationMode(.middle)

                Spacer(minLength: 12)

                Button(action: onStart) {
                    HStack(spacing: 7) {
                        Image(systemName: "play.fill")
                            .font(.system(size: 10, weight: .bold))
                        Text(appPreferences.text(preset.actionKey))
                            .font(.system(size: 12, weight: .semibold))
                    }
                    .foregroundColor(.white)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(accent)
                    .cornerRadius(8)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(theme.cardBackground)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(theme.divider, lineWidth: 1)
        )
        .cornerRadius(8)
    }
}

