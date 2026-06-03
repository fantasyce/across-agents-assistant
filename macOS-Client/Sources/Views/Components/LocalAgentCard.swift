import SwiftUI
import AppKit

struct LocalAgentCard: View {
    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences

    let agent: AgentConfig
    let detectionFeedback: AgentDetectionFeedback
    @Binding var isExpanded: Bool
    let onSave: (AgentConfig) -> Void
    let onAutoDetect: (String) -> Void

    @State private var selectedPath: String = ""
    @State private var selectedModel: String = ""
    var body: some View {
        VStack(spacing: 0) {
            AgentCard(
                iconName: agent.iconName,
                name: agent.name,
                statusText: statusText,
                isInstalled: agent.status == .installed,
                accentColor: Color(hex: "d97757"),
                isExpanded: isExpanded,
                onTap: { isExpanded.toggle() }
            )

            if isExpanded {
                VStack(alignment: .leading, spacing: 12) {
                    detailsContent
                }
                .padding(16)
                .background(panelColor)
                .cornerRadius(10)
                .padding(.top, 0)
                .onAppear {
                    selectedPath = agent.configuredPath ?? agent.executablePath ?? ""
                    selectedModel = agent.selectedModel ?? ""
                }
                .onChange(of: agent.configuredPath) { _, newValue in
                    selectedPath = newValue ?? agent.executablePath ?? ""
                }
                .onChange(of: agent.executablePath) { _, newValue in
                    if agent.configuredPath == nil {
                        selectedPath = newValue ?? ""
                    }
                }
                .onChange(of: agent.selectedModel) { _, newValue in
                    selectedModel = newValue ?? ""
                }
            }
        }
    }

    private var statusText: String {
        switch agent.status {
        case .installed:
            return agent.version ?? "v?.?.?"
        case .notInstalled:
            return appPreferences.text("models.status.notFound")
        case .notAuthenticated:
            return appPreferences.text("models.status.notAuthenticated")
        case .unavailable:
            return appPreferences.text("models.status.unavailable")
        case .invalidPath:
            return appPreferences.text("models.status.invalidPath")
        }
    }

    private var panelColor: Color {
        colorScheme == .dark ? Color(hex: "2c2c2e") : Color.white
    }

    private var fieldColor: Color {
        colorScheme == .dark ? Color(hex: "1c1c1e") : Color(hex: "f3f4f6")
    }

    private var valueTextColor: Color {
        colorScheme == .dark ? .white : .legacyTextLight
    }

    private var secondaryTextColor: Color {
        colorScheme == .dark ? Color(hex: "8e8e93") : Color(hex: "6b7280")
    }

    private var labelTextColor: Color {
        colorScheme == .dark ? Color(hex: "636366") : Color(hex: "6b7280")
    }

    private var warningBackground: Color {
        colorScheme == .dark ? Color(hex: "1c1c1e").opacity(0.5) : Color(hex: "fff7ed")
    }

    @ViewBuilder
    private var detailsContent: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let warning = warningMessage {
                HStack(spacing: 10) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundColor(Color(hex: "ff9f0a"))

                    Text(warning)
                        .font(.system(size: 12))
                        .foregroundColor(secondaryTextColor)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(12)
                .background(warningBackground)
                .cornerRadius(8)
            }

            VStack(alignment: .leading, spacing: 8) {
                Text(appPreferences.text("models.executablePath"))
                    .font(.system(size: 11))
                    .foregroundColor(labelTextColor)
                    .textCase(.uppercase)

                HStack(spacing: 8) {
                    TextField(appPreferences.text("models.autoDetectPath"), text: $selectedPath)
                        .textFieldStyle(.plain)
                        .font(.system(size: 13))
                        .foregroundColor(valueTextColor)
                        .padding(10)
                        .background(fieldColor)
                        .cornerRadius(8)

                    Button(action: chooseExecutable) {
                        Image(systemName: "folder")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundColor(valueTextColor.opacity(0.9))
                            .frame(width: 34, height: 34)
                            .background(fieldColor)
                            .cornerRadius(8)
                    }
                    .buttonStyle(.plain)
                    .help(appPreferences.text("models.chooseExecutable"))
                }

                if let detail = detectionDetail {
                    Text(detail)
                        .font(.system(size: 11))
                        .foregroundColor(secondaryTextColor)
                        .lineLimit(2)
                }

                detectionFeedbackView
            }

            VStack(alignment: .leading, spacing: 8) {
                Text(appPreferences.text("models.model"))
                    .font(.system(size: 11))
                    .foregroundColor(labelTextColor)
                    .textCase(.uppercase)

                if availableModels.isEmpty {
                    TextField(appPreferences.text("models.autoModel"), text: $selectedModel)
                        .textFieldStyle(.plain)
                        .font(.system(size: 13))
                        .foregroundColor(valueTextColor)
                        .padding(10)
                        .background(fieldColor)
                        .cornerRadius(8)
                } else {
                    Picker("", selection: $selectedModel) {
                        Text(appPreferences.text("models.autoModel")).tag("")
                        ForEach(availableModels, id: \.self) { model in
                            Text(model).tag(model)
                        }
                    }
                    .pickerStyle(.menu)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(10)
                    .background(fieldColor)
                    .cornerRadius(8)
                }
            }

            HStack(spacing: 10) {
                Button(appPreferences.text("system.cancel")) {
                    selectedPath = agent.configuredPath ?? agent.executablePath ?? ""
                    selectedModel = agent.selectedModel ?? ""
                    isExpanded = false
                }
                .buttonStyle(SecondaryButtonStyle())

                Button {
                    onAutoDetect(agent.id)
                } label: {
                    HStack(spacing: 6) {
                        if detectionFeedback == .detecting {
                            ProgressView()
                                .scaleEffect(0.55)
                                .frame(width: 12, height: 12)
                        } else {
                            Image(systemName: "magnifyingglass")
                                .font(.system(size: 12, weight: .semibold))
                        }
                        Text(detectionFeedback == .detecting ? appPreferences.text("models.detecting") : appPreferences.text("models.autoDetect"))
                    }
                }
                .buttonStyle(EmphasizedSecondaryButtonStyle())
                .disabled(detectionFeedback == .detecting)
                .help(appPreferences.text("models.detectAgent.help"))

                Button(appPreferences.text("system.save")) {
                    var updated = agent
                    let trimmed = selectedPath.trimmingCharacters(in: .whitespacesAndNewlines)
                    let model = selectedModel.trimmingCharacters(in: .whitespacesAndNewlines)
                    updated.configuredPath = trimmed.isEmpty ? nil : trimmed
                    updated.executablePath = trimmed.isEmpty ? nil : trimmed
                    updated.selectedModel = model.isEmpty ? nil : model
                    onSave(updated)
                    isExpanded = false
                }
                .buttonStyle(PrimaryButtonStyle(color: Color(hex: "d97757")))
            }
        }
    }

    @ViewBuilder
    private var detectionFeedbackView: some View {
        switch detectionFeedback {
        case .idle:
            EmptyView()
        case .detecting:
            feedbackRow(icon: "clock.arrow.circlepath", color: Color(hex: "ff9f0a"), text: appPreferences.text("models.detectingExecutable"))
        case .found(let path):
            feedbackRow(icon: "checkmark.circle.fill", color: Color(hex: "32d74b"), text: String(format: appPreferences.text("models.detected"), pathSuffix(path)))
        case .notFound(let message):
            feedbackRow(icon: "exclamationmark.circle.fill", color: Color(hex: "ff9f0a"), text: message ?? appPreferences.text("models.notFoundManual"))
        case .failed(let message):
            feedbackRow(icon: "xmark.circle.fill", color: Color(hex: "ff453a"), text: message)
        }
    }

    private func feedbackRow(icon: String, color: Color, text: String) -> some View {
        HStack(spacing: 7) {
            Image(systemName: icon)
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(color)
            Text(text)
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(secondaryTextColor)
                .lineLimit(2)
        }
        .padding(.top, 2)
    }

    private func pathSuffix(_ path: String?) -> String {
        guard let path, !path.isEmpty else { return "" }
        return String(format: appPreferences.text("models.detected.at"), path)
    }

    private var warningMessage: String? {
        if agent.status == .invalidPath {
            return agent.error ?? appPreferences.text("models.warning.invalidPath")
        }
        if agent.status == .unavailable {
            return agent.error ?? appPreferences.text("models.warning.unavailable")
        }
        if agent.id == "claude" && agent.status == .notAuthenticated {
            return appPreferences.text("models.warning.claudeAuth")
        }
        return nil
    }

    private var detectionDetail: String? {
        if let path = agent.executablePath, !path.isEmpty {
            if let method = agent.detectionMethod, !method.isEmpty {
                return String(format: appPreferences.text("models.detectedVia"), method, path)
            }
            return String(format: appPreferences.text("models.detectedPath"), path)
        }
        if let configured = agent.configuredPath, !configured.isEmpty {
            return String(format: appPreferences.text("models.configuredPath"), configured)
        }
        return appPreferences.text("models.noExecutable")
    }

    private var availableModels: [String] {
        var values = agent.availableModels ?? []
        if !selectedModel.isEmpty, !values.contains(selectedModel) {
            values.insert(selectedModel, at: 0)
        }
        return values
    }

    private func chooseExecutable() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.title = String(format: appPreferences.text("models.chooseExecutableTitle"), agent.name)
        panel.prompt = appPreferences.text("models.choose")
        if panel.runModal() == .OK, let url = panel.url {
            selectedPath = url.path
        }
    }
}

struct SecondaryButtonStyle: ButtonStyle {
    @Environment(\.colorScheme) private var colorScheme

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .medium))
            .foregroundColor(colorScheme == .dark ? Color(hex: "8e8e93") : Color(hex: "6b7280"))
            .frame(minWidth: 80)
            .padding(.vertical, 10)
            .padding(.horizontal, 16)
            .background(colorScheme == .dark ? Color(hex: "1c1c1e") : Color(hex: "f3f4f6"))
            .cornerRadius(8)
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(colorScheme == .dark ? Color(white: 1, opacity: 0.08) : Color.black.opacity(0.08), lineWidth: 1)
            )
            .contentShape(Rectangle())
    }
}

struct EmphasizedSecondaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.colorScheme) private var colorScheme

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .semibold))
            .foregroundColor(isEnabled
                ? (colorScheme == .dark ? .white : .legacyTextLight)
                : (colorScheme == .dark ? Color(hex: "8e8e93") : Color(hex: "9ca3af")))
            .frame(minWidth: 118)
            .padding(.vertical, 10)
            .padding(.horizontal, 16)
            .background(
                isEnabled
                    ? (colorScheme == .dark ? Color(hex: "3a3a3c") : Color(hex: "eef2ff")).opacity(configuration.isPressed ? 0.85 : 1)
                    : (colorScheme == .dark ? Color(hex: "1c1c1e") : Color(hex: "f3f4f6"))
            )
            .cornerRadius(8)
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(Color(hex: "d97757").opacity(isEnabled ? 0.45 : 0.12), lineWidth: 1)
            )
            .contentShape(Rectangle())
    }
}

struct PrimaryButtonStyle: ButtonStyle {
    let color: Color
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.colorScheme) private var colorScheme

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .medium))
            .foregroundColor(.white)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 10)
            .background(isEnabled ? color : (colorScheme == .dark ? Color(hex: "3a3a3c") : Color(hex: "c7c7cc")))
            .cornerRadius(8)
    }
}

struct DestructiveButtonStyle: ButtonStyle {
    @Environment(\.colorScheme) private var colorScheme

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .medium))
            .foregroundColor(Color(hex: "ff453a"))
            .frame(minWidth: 80)
            .padding(.vertical, 10)
            .padding(.horizontal, 16)
            .background(Color(hex: "ff453a").opacity(colorScheme == .dark ? 0.12 : 0.08))
            .cornerRadius(8)
            .contentShape(Rectangle())
    }
}
