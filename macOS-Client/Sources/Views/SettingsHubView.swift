import AVFoundation
import SwiftUI
import AppKit

enum SettingsHubTab: String, CaseIterable, Identifiable {
    case diagnostics
    case workbench
    case models
    case capabilities
    case mcp
    case plugins
    case tools
    case settings

    var id: String { rawValue }

    static let groupedNavigation: [SettingsHubTab] = [
        .diagnostics,
        .models,
        .capabilities,
        .plugins,
        .tools,
        .settings,
    ]

    var iconName: String {
        switch self {
        case .diagnostics: return "stethoscope"
        case .workbench: return "point.3.connected.trianglepath.dotted"
        case .models: return "cpu"
        case .capabilities: return "sparkles.rectangle.stack"
        case .mcp: return "square.grid.2x2"
        case .plugins: return "puzzlepiece"
        case .tools: return "wrench.and.screwdriver.fill"
        case .settings: return "gearshape"
        }
    }

    @MainActor
    func title(preferences: AppPreferences) -> String {
        switch self {
        case .diagnostics: return preferences.text("settings.systemHealth")
        case .workbench: return preferences.text("settings.workbench")
        case .models: return preferences.text("settings.agentsModels")
        case .capabilities: return preferences.text("settings.capabilities")
        case .mcp: return preferences.text("settings.mcp")
        case .plugins: return preferences.text("settings.pluginsMCP")
        case .tools: return preferences.text("settings.toolPermissions")
        case .settings: return preferences.text("settings.preferences")
        }
    }
}

struct SettingsHubView: View {
    @ObservedObject var settingsViewModel: SettingsViewModel
    @ObservedObject var preferences: AppPreferences
    @State var selectedTab: SettingsHubTab
    var onClose: (() -> Void)? = nil

    @Environment(\.colorScheme) private var colorScheme

    private var bgColor: Color { AcrossTheme.canvasFill(for: colorScheme) }

    private var normalizedSelection: SettingsHubTab {
        selectedTab == .mcp ? .plugins : selectedTab
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Rectangle()
                .fill(AcrossTheme.separator(for: colorScheme))
                .frame(height: 1)
            HStack(spacing: 0) {
                navigationSidebar
                    .frame(width: AcrossTheme.Metrics.sidebarWidth)
                Rectangle()
                    .fill(AcrossTheme.separator(for: colorScheme))
                    .frame(width: 1)
                content
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(VisualEffectView().ignoresSafeArea())
        .transaction { transaction in
            if preferences.reduceMotion {
                transaction.disablesAnimations = true
                transaction.animation = nil
            }
        }
        .ignoresSafeArea(.all, edges: .top)
    }

    private var header: some View {
        HStack(spacing: 0) {
            CustomTrafficLights(onClose: onClose)
                .frame(width: 120, alignment: .leading)

            Spacer()

            Text(preferences.text("settings.title"))
                .font(.system(size: 14, weight: .semibold))

            Spacer()

            Spacer().frame(width: 120)
        }
        .padding(.horizontal, 16)
        .frame(height: 56)
        .background(
            ZStack {
                AcrossTheme.panelFill(for: colorScheme)
                WindowDragView().contentShape(Rectangle())
            }
        )
    }

    private var navigationSidebar: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(preferences.text("settings.navigation"))
                .font(.system(size: 10, weight: .semibold))
                .foregroundStyle(.secondary)
                .padding(.horizontal, 14)
                .padding(.top, 14)
                .padding(.bottom, 6)

            ForEach(SettingsHubTab.groupedNavigation) { tab in
                Button {
                    selectedTab = tab
                } label: {
                    HStack(spacing: 9) {
                        Image(systemName: tab.iconName)
                            .font(.system(size: 12, weight: .semibold))
                            .frame(width: 18, height: 18)
                            .accessibilityHidden(true)
                        Text(tab.title(preferences: preferences))
                            .font(.system(size: 12, weight: normalizedSelection == tab ? .semibold : .medium))
                            .lineLimit(2)
                        Spacer()
                    }
                    .foregroundStyle(normalizedSelection == tab ? AcrossTheme.accent : Color.primary)
                    .padding(.horizontal, 9)
                    .frame(maxWidth: .infinity, minHeight: 36, alignment: .leading)
                    .background(normalizedSelection == tab ? AcrossTheme.selectedFill(for: colorScheme) : Color.clear)
                    .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.controlCornerRadius))
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .padding(.horizontal, 8)
                .help(tab.title(preferences: preferences))
            }

            Spacer()
        }
        .background(AcrossTheme.sidebarFill(for: colorScheme))
        .accessibilityElement(children: .contain)
        .accessibilityLabel(Text(preferences.text("settings.navigation")))
    }

    @ViewBuilder
    private var content: some View {
        switch selectedTab {
        case .diagnostics:
            StartupDiagnosticsView(settingsViewModel: settingsViewModel)
                .environmentObject(preferences)
        case .workbench:
            AutopilotWorkbenchView()
                .environmentObject(preferences)
        case .models:
            ModelSettingsView(viewModel: settingsViewModel, onClose: nil, embeddedInHub: true)
                .environmentObject(preferences)
        case .capabilities:
            AgentCapabilitiesView(settingsViewModel: settingsViewModel, onClose: nil, embeddedInHub: true)
                .environmentObject(preferences)
        case .mcp:
            MCPPreferencesView(onClose: nil, embeddedInHub: true)
                .environmentObject(preferences)
        case .plugins:
            PluginsAndMCPSettingsView()
                .environmentObject(preferences)
        case .tools:
            ToolPermissionsView(onClose: nil, embeddedInHub: true)
                .environmentObject(preferences)
        case .settings:
            GlobalPreferencesContent(preferences: preferences)
                .background(bgColor)
        }
    }
}

private enum PluginsAndMCPSection: String, CaseIterable, Identifiable {
    case plugins
    case mcp

    var id: String { rawValue }
}

private struct PluginsAndMCPSettingsView: View {
    @EnvironmentObject private var preferences: AppPreferences
    @Environment(\.colorScheme) private var colorScheme
    @State private var section: PluginsAndMCPSection = .plugins

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Picker("", selection: $section) {
                    Text(preferences.text("settings.plugins")).tag(PluginsAndMCPSection.plugins)
                    Text(preferences.text("settings.mcp")).tag(PluginsAndMCPSection.mcp)
                }
                .labelsHidden()
                .pickerStyle(.segmented)
                .frame(width: 260)
                .accessibilityLabel(Text(preferences.text("settings.pluginsMCP")))
                Spacer()
            }
            .padding(.horizontal, SettingsHubPageLayout.contentPadding)
            .frame(height: 50)
            .background(AcrossTheme.panelFill(for: colorScheme))
            .overlay(alignment: .bottom) {
                Rectangle()
                    .fill(AcrossTheme.separator(for: colorScheme))
                    .frame(height: 1)
            }

            switch section {
            case .plugins:
                PluginLifecycleView(onClose: nil, embeddedInHub: true)
                    .environmentObject(preferences)
            case .mcp:
                MCPPreferencesView(onClose: nil, embeddedInHub: true)
                    .environmentObject(preferences)
            }
        }
        .background(AcrossTheme.canvasFill(for: colorScheme))
    }
}

private struct GlobalPreferencesContent: View {
    @ObservedObject var preferences: AppPreferences
    @Environment(\.colorScheme) private var colorScheme
    @State private var availableVoices: [AVSpeechSynthesisVoice] = AVSpeechSynthesisVoice.speechVoices()
    @State private var isVoicePickerPresented = false

    private var textColor: Color { .primary }
    private var cardColor: Color { AcrossTheme.panelFill(for: colorScheme) }
    private var fieldColor: Color { AcrossTheme.recessedFill(for: colorScheme) }
    private var accentColor: Color { AcrossTheme.accent }
    private let controlColumnWidth: CGFloat = 320

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 32) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(preferences.text("settings.title"))
                        .font(.system(size: 24, weight: .bold))
                        .foregroundColor(textColor)
                    Text(preferences.text("settings.subtitle"))
                        .font(.system(size: 13))
                        .foregroundColor(.secondary)
                }
                .padding(.top, 2)

                PreferenceSection(
                    title: preferences.text("section.appearance"),
                    description: preferences.text("appearance.scheme.help")
                ) {
                    settingRow(
                        title: preferences.text("language.mode"),
                        help: preferences.text("language.mode.help")
                    ) {
                        Picker("", selection: $preferences.languageMode) {
                            ForEach(AppLanguageMode.allCases) { mode in
                                Text(mode.title(preferences: preferences)).tag(mode)
                            }
                        }
                        .labelsHidden()
                        .frame(width: 190, alignment: .trailing)
                    }

                    settingRow(
                        title: preferences.text("appearance.scheme"),
                        help: preferences.text("appearance.scheme.help")
                    ) {
                        Picker("", selection: $preferences.colorSchemeMode) {
                            ForEach(AppColorSchemeMode.allCases) { mode in
                                Text(mode.title(preferences: preferences)).tag(mode)
                            }
                        }
                        .labelsHidden()
                        .frame(width: 170, alignment: .trailing)
                    }

                    settingRow(
                        title: preferences.text("appearance.reduceMotion"),
                        help: preferences.text("appearance.reduceMotion.help")
                    ) {
                        Toggle("", isOn: $preferences.reduceMotion)
                            .labelsHidden()
                    }
                }

                PreferenceSection(
                    title: preferences.text("section.voice"),
                    description: preferences.text("voice.source.help")
                ) {
                    voiceSummary
                    settingRow(
                        title: preferences.text("voice.source"),
                        help: preferences.text("voice.source.help")
                    ) {
                        Picker("", selection: $preferences.voiceSource) {
                            ForEach(AppVoiceSource.allCases) { source in
                                Text(source.title(preferences: preferences)).tag(source)
                            }
                        }
                        .labelsHidden()
                        .frame(width: 176, alignment: .trailing)
                    }

                    if preferences.voiceSource == .chosenVoice {
                        settingRow(title: preferences.text("voice.source.choose"), help: preferences.text("voice.source.help")) {
                            Button {
                                isVoicePickerPresented.toggle()
                            } label: {
                                HStack(spacing: 8) {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(selectedVoiceLabel)
                                            .font(.system(size: 12, weight: .semibold))
                                            .foregroundColor(textColor)
                                            .lineLimit(1)
                                        Text(selectedVoiceDetail)
                                            .font(.system(size: 10))
                                            .foregroundColor(.secondary)
                                            .lineLimit(1)
                                    }
                                    Spacer(minLength: 12)
                                    Image(systemName: "chevron.up.chevron.down")
                                        .font(.system(size: 10, weight: .semibold))
                                        .foregroundColor(.secondary)
                                }
                                .frame(width: 260)
                                .padding(.horizontal, 10)
                                .padding(.vertical, 8)
                                .background(fieldColor)
                                .clipShape(RoundedRectangle(cornerRadius: 7))
                                .overlay(
                                    RoundedRectangle(cornerRadius: 7)
                                        .stroke(Color.secondary.opacity(0.14), lineWidth: 1)
                                )
                            }
                            .buttonStyle(.plain)
                            .disabled(availableVoices.isEmpty)
                            .popover(isPresented: $isVoicePickerPresented, arrowEdge: .bottom) {
                                VoicePickerPopover(
                                    voices: availableVoices,
                                    selectedIdentifier: preferences.chosenVoiceIdentifier,
                                    accentColor: accentColor,
                                    onSelect: { voice in
                                        preferences.chosenVoiceIdentifier = voice.identifier
                                        isVoicePickerPresented = false
                                    }
                                )
                            }
                        }
                    }

                    settingRow(
                        title: preferences.text("voice.autoRead"),
                        help: preferences.text("voice.autoRead.help")
                    ) {
                        Toggle("", isOn: $preferences.autoReadReplies)
                            .labelsHidden()
                    }

                    settingRow(title: preferences.text("voice.rate"), help: preferences.text("voice.rate")) {
                        Slider(value: $preferences.speechRate, in: 0.35...0.65)
                            .frame(width: 180)
                    }

                    settingRow(title: preferences.text("voice.volume"), help: preferences.text("voice.volume")) {
                        Slider(value: $preferences.speechVolume, in: 0.2...1.0)
                            .frame(width: 180)
                    }

                    settingRow(title: preferences.text("voice.openSettings"), help: preferences.text("voice.source.help")) {
                        HStack(spacing: 8) {
                            Button(preferences.text("voice.test")) { testVoice() }
                            Button(preferences.text("voice.openSettings")) { openVoiceSettings() }
                            Button(preferences.text("voice.refresh")) { refreshVoices() }
                        }
                    }
                }

                PreferenceSection(
                    title: preferences.text("section.conversation"),
                    description: preferences.text("conversation.defaultProject.help")
                ) {
                    settingRow(
                        title: preferences.text("conversation.rememberAgent"),
                        help: preferences.text("conversation.rememberAgent.help")
                    ) {
                        Toggle("", isOn: $preferences.rememberLastAgent)
                            .labelsHidden()
                    }
                    settingRow(
                        title: preferences.text("conversation.defaultProject"),
                        help: preferences.text("conversation.defaultProject.help")
                    ) {
                        Picker("", selection: $preferences.defaultProjectMode) {
                            ForEach(AppDefaultProjectMode.allCases) { mode in
                                Text(mode.title(preferences: preferences)).tag(mode)
                            }
                        }
                        .labelsHidden()
                        .frame(width: 190, alignment: .trailing)
                    }
                }

                PreferenceSection(
                    title: preferences.text("section.privacy"),
                    description: preferences.text("privacy.activeApp.help")
                ) {
                    settingRow(
                        title: preferences.text("privacy.activeApp"),
                        help: preferences.text("privacy.activeApp.help")
                    ) {
                        Toggle("", isOn: $preferences.includeActiveAppContext)
                            .labelsHidden()
                    }
                    settingRow(
                        title: preferences.text("privacy.browser"),
                        help: preferences.text("privacy.browser.help")
                    ) {
                        Toggle("", isOn: $preferences.includeBrowserContext)
                            .labelsHidden()
                            .disabled(true)
                    }
                    settingRow(title: preferences.text("privacy.openData"), help: "~/.across") {
                        Button(preferences.text("privacy.openData")) {
                            NSWorkspace.shared.open(URL(fileURLWithPath: NSHomeDirectory()).appendingPathComponent(".across"))
                        }
                    }
                }

                PreferenceSection(
                    title: preferences.text("section.advanced"),
                    description: preferences.text("advanced.socket")
                ) {
                    settingRow(title: preferences.text("advanced.socket"), help: "~/.across/run/across-agents-assistant/across-agents.sock") {
                        Text(preferences.text("system.ready"))
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundColor(Color(hex: "30d158"))
                    }
                    settingRow(title: preferences.text("advanced.logs"), help: "~/.across/logs/across-agents-assistant") {
                        Button(preferences.text("advanced.openLogs")) {
                            NSWorkspace.shared.open(LocalAppPaths.logsDir)
                        }
                    }
                }
            }
            .padding(SettingsHubPageLayout.contentPadding)
            .frame(maxWidth: SettingsHubPageLayout.contentMaxWidth, alignment: .leading)
            .frame(maxWidth: .infinity)
        }
    }

    private var voiceSummary: some View {
        HStack(spacing: 14) {
            Image(systemName: "speaker.wave.2.fill")
                .font(.system(size: 15, weight: .semibold))
                .foregroundColor(accentColor)
                .frame(width: 34, height: 34)
                .background(accentColor.opacity(0.16))
                .cornerRadius(8)

            VStack(alignment: .leading, spacing: 4) {
                Text(currentVoiceName)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(textColor)
                Text("\(currentVoiceLanguage) · \(currentVoiceQuality)")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            }
            Spacer()
            Text(preferences.text("voice.available"))
                .font(.system(size: 10, weight: .semibold))
                .foregroundColor(Color(hex: "30d158"))
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(Color(hex: "30d158").opacity(0.14))
                .cornerRadius(999)
        }
        .padding(12)
        .background(cardColor)
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color.secondary.opacity(0.14), lineWidth: 1)
        )
    }

    private var currentVoice: AVSpeechSynthesisVoice? {
        TTSEngine.voiceForSpeech(
            voiceSource: preferences.voiceSource,
            chosenVoiceIdentifier: preferences.chosenVoiceIdentifier,
            fallbackLanguage: preferences.resolvedLocaleIdentifier
        )
    }

    private var currentVoiceName: String {
        currentVoice?.name ?? preferences.text("voice.noVoices")
    }

    private var currentVoiceLanguage: String {
        currentVoice?.language ?? preferences.resolvedLocaleIdentifier
    }

    private var currentVoiceQuality: String {
        guard let voice = currentVoice else { return "" }
        return speechVoiceQualityTitle(voice)
    }

    private var selectedManualVoice: AVSpeechSynthesisVoice? {
        guard !availableVoices.isEmpty else { return nil }
        if let identifier = preferences.chosenVoiceIdentifier,
           let voice = availableVoices.first(where: { $0.identifier == identifier }) {
            return voice
        }
        return availableVoices.first
    }

    private var selectedVoiceLabel: String {
        selectedManualVoice?.name ?? preferences.text("voice.noVoices")
    }

    private var selectedVoiceDetail: String {
        guard let voice = selectedManualVoice else { return preferences.text("voice.noVoices") }
        return "\(voice.language) · \(speechVoiceQualityTitle(voice))"
    }

    private func settingRow<Control: View>(
        title: String,
        help: String,
        @ViewBuilder control: () -> Control
    ) -> some View {
        HStack(alignment: .center, spacing: 18) {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(textColor)
                Text(help)
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                    .lineLimit(2)
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            HStack(spacing: 0) {
                Spacer(minLength: 0)
                control()
            }
                .frame(width: controlColumnWidth, alignment: .trailing)
        }
        .padding(12)
        .background(cardColor)
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color.secondary.opacity(0.14), lineWidth: 1)
        )
    }

    private func refreshVoices() {
        availableVoices = AVSpeechSynthesisVoice.speechVoices()
        if preferences.voiceSource == .chosenVoice,
           let chosen = preferences.chosenVoiceIdentifier,
           !availableVoices.contains(where: { $0.identifier == chosen }) {
            preferences.chosenVoiceIdentifier = availableVoices.first?.identifier
        }
    }

    private func testVoice() {
        let sample = preferences.resolvedLocaleIdentifier == "zh-Hans"
            ? "你好，这是 Across Agents Assistant 的朗读测试。"
            : "Hello, this is the Across Agents Assistant voice test."
        TTSEngine.shared.speak(
            sample,
            voiceSource: preferences.voiceSource,
            chosenVoiceIdentifier: preferences.chosenVoiceIdentifier,
            fallbackLanguage: preferences.resolvedLocaleIdentifier,
            rate: preferences.speechRate,
            volume: preferences.speechVolume
        )
    }

    private func openVoiceSettings() {
        let candidates = [
            "x-apple.systempreferences:com.apple.preference.universalaccess",
            "x-apple.systempreferences:com.apple.preference.speech"
        ]
        for raw in candidates {
            if let url = URL(string: raw), NSWorkspace.shared.open(url) {
                return
            }
        }
        NSWorkspace.shared.open(URL(fileURLWithPath: "/System/Applications/System Settings.app"))
    }
}

private struct VoicePickerPopover: View {
    let voices: [AVSpeechSynthesisVoice]
    let selectedIdentifier: String?
    let accentColor: Color
    let onSelect: (AVSpeechSynthesisVoice) -> Void

    private let rowHeight: CGFloat = 42
    private let maxHeight: CGFloat = 340

    private var popoverHeight: CGFloat {
        min(maxHeight, max(72, CGFloat(voices.count) * rowHeight + 16))
    }

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 2) {
                ForEach(voices, id: \.identifier) { voice in
                    voiceRow(voice)
                }
            }
            .padding(8)
        }
        .frame(width: 326, height: popoverHeight)
    }

    private func voiceRow(_ voice: AVSpeechSynthesisVoice) -> some View {
        let isSelected = voice.identifier == selectedIdentifier
        return Button {
            onSelect(voice)
        } label: {
            HStack(spacing: 9) {
                Image(systemName: "checkmark")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundColor(accentColor)
                    .opacity(isSelected ? 1 : 0)
                    .frame(width: 14)
                VStack(alignment: .leading, spacing: 2) {
                    Text(voice.name)
                        .font(.system(size: 12, weight: isSelected ? .semibold : .regular))
                        .lineLimit(1)
                    Text("\(voice.language) · \(speechVoiceQualityTitle(voice))")
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                }
                Spacer(minLength: 8)
            }
            .padding(.horizontal, 8)
            .frame(height: rowHeight, alignment: .center)
            .background(isSelected ? accentColor.opacity(0.16) : Color.clear)
            .clipShape(RoundedRectangle(cornerRadius: 7))
        }
        .buttonStyle(.plain)
    }
}

private func speechVoiceQualityTitle(_ voice: AVSpeechSynthesisVoice) -> String {
    switch voice.quality {
    case .premium: return "Premium"
    case .enhanced: return "Enhanced"
    default: return "Compact"
    }
}

private struct PreferenceSection<Content: View>: View {
    let title: String
    let description: String
    @ViewBuilder let content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(title)
                .font(.system(size: 14, weight: .bold))
                .padding(.leading, 12)
            VStack(spacing: 10) {
                content()
            }
        }
    }
}
