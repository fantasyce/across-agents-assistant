import AVFoundation
import SwiftUI
import AppKit

enum SettingsHubTab: String, CaseIterable, Identifiable {
    case diagnostics
    case experience
    case models
    case capabilities
    case plugins
    case workers
    case mcp
    case tools
    case settings

    var id: String { rawValue }

    var iconName: String {
        switch self {
        case .diagnostics: return "stethoscope"
        case .experience: return "waveform.and.person.filled"
        case .models: return "cpu"
        case .capabilities: return "sparkles.rectangle.stack"
        case .plugins: return "puzzlepiece"
        case .workers: return "desktopcomputer.and.macbook"
        case .mcp: return "square.grid.2x2"
        case .tools: return "wrench.and.screwdriver.fill"
        case .settings: return "gearshape"
        }
    }

    @MainActor
    func title(preferences: AppPreferences) -> String {
        switch self {
        case .diagnostics: return preferences.text("settings.systemHealth")
        case .experience: return preferences.text("settings.experience")
        case .models: return preferences.text("settings.agentsModels")
        case .capabilities: return preferences.text("settings.capabilities")
        case .plugins: return preferences.text("settings.plugins")
        case .workers: return preferences.text("workers.title")
        case .mcp: return preferences.text("settings.mcp")
        case .tools: return preferences.text("settings.toolPermissions")
        case .settings: return preferences.text("settings.preferences")
        }
    }
}

private enum SettingsHubCategory: String, CaseIterable, Identifiable {
    case general
    case agents
    case capabilities
    case plugins
    case workers
    case mcp
    case tools
    case diagnostics

    var id: String { rawValue }

    var iconName: String {
        switch self {
        case .general: return "gearshape"
        case .agents: return "cpu"
        case .capabilities: return "sparkles.rectangle.stack"
        case .plugins: return "puzzlepiece.extension"
        case .workers: return "desktopcomputer.and.macbook"
        case .mcp: return "square.grid.2x2"
        case .tools: return "wrench.and.screwdriver"
        case .diagnostics: return "stethoscope"
        }
    }

    @MainActor
    func title(preferences: AppPreferences) -> String {
        switch self {
        case .general: return preferences.text("settings.category.general")
        case .agents: return preferences.text("settings.agentsModels")
        case .capabilities: return preferences.text("settings.capabilities")
        case .plugins: return preferences.text("settings.plugins")
        case .workers: return preferences.text("workers.title")
        case .mcp: return preferences.text("settings.mcp")
        case .tools: return preferences.text("settings.toolPermissions")
        case .diagnostics: return preferences.text("settings.systemHealth")
        }
    }

    var canonicalTab: SettingsHubTab {
        switch self {
        case .general: return .settings
        case .agents: return .models
        case .capabilities: return .capabilities
        case .plugins: return .plugins
        case .workers: return .workers
        case .mcp: return .mcp
        case .tools: return .tools
        case .diagnostics: return .diagnostics
        }
    }
}

struct SettingsHubView: View {
    @ObservedObject var settingsViewModel: SettingsViewModel
    @ObservedObject var preferences: AppPreferences
    @State var selectedTab: SettingsHubTab
    @State private var selectedCapabilityAgentId: String?
    @FocusState private var focusedCategory: SettingsHubCategory?
    var onClose: (() -> Void)? = nil

    @Environment(\.colorScheme) private var colorScheme

    private var bgColor: Color { AcrossTheme.canvasFill(for: colorScheme) }

    private var selectedCategory: SettingsHubCategory {
        switch selectedTab {
        case .settings, .experience: return .general
        case .models: return .agents
        case .capabilities: return .capabilities
        case .plugins: return .plugins
        case .workers: return .workers
        case .mcp: return .mcp
        case .tools: return .tools
        case .diagnostics: return .diagnostics
        }
    }

    var body: some View {
        HStack(spacing: 0) {
            VStack(spacing: 0) {
                windowControls
                navigationSidebar
            }
            .frame(width: AcrossTheme.Metrics.sidebarWidth)
            .background(.bar)

            Rectangle()
                .fill(AcrossTheme.separator(for: colorScheme))
                .frame(width: 1)

            content
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(bgColor.ignoresSafeArea())
        .overlay(alignment: .topLeading) {
            HStack(spacing: 0) {
                Color.clear
                    .frame(width: AcrossTheme.Metrics.sidebarWidth, height: 30)
                    .allowsHitTesting(false)
                WindowDragView()
                    .frame(maxWidth: .infinity)
                    .frame(height: 30)
            }
        }
        .transaction { transaction in
            if preferences.reduceMotion {
                transaction.disablesAnimations = true
                transaction.animation = nil
            }
        }
        .focusEffectDisabled()
        .ignoresSafeArea(.all, edges: .top)
    }

    private var windowControls: some View {
        HStack {
            CustomTrafficLights(onClose: onClose)
                .frame(width: 120, alignment: .leading)
            Spacer()
        }
        .padding(.horizontal, 16)
        .frame(height: 56)
        .background(WindowDragView().contentShape(Rectangle()))
    }

    private var navigationSidebar: some View {
        ScrollView {
            VStack(spacing: 4) {
                ForEach(SettingsHubCategory.allCases) { category in
                    settingsNavigationRow(category)
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 10)
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(Text(preferences.text("settings.navigation")))
    }

    private func settingsNavigationRow(_ category: SettingsHubCategory) -> some View {
        let isSelected = selectedCategory == category
        let isFocused = focusedCategory == category
        return Button {
            selectedTab = category.canonicalTab
        } label: {
            HStack(spacing: 9) {
                Image(systemName: category.iconName)
                    .font(.system(size: 14, weight: .medium))
                    .frame(width: 20, height: 20)
                    .accessibilityHidden(true)
                Text(category.title(preferences: preferences))
                    .font(.system(size: 13, weight: isSelected ? .semibold : .regular))
                    .lineLimit(1)
                Spacer()
            }
            .foregroundStyle(isSelected ? AcrossTheme.accent : Color.primary)
            .padding(.horizontal, 10)
            .frame(maxWidth: .infinity, minHeight: 38, alignment: .leading)
            .background(
                isSelected
                    ? AcrossTheme.selectedFill(for: colorScheme)
                    : (isFocused ? AcrossTheme.hoverFill(for: colorScheme) : Color.clear)
            )
            .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.controlCornerRadius))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .focused($focusedCategory, equals: category)
        .focusEffectDisabled()
        .help(category.title(preferences: preferences))
        .accessibilityValue(Text(isSelected ? preferences.text("operations.selected") : ""))
    }

    @ViewBuilder
    private var content: some View {
        switch selectedCategory {
        case .general:
            GlobalPreferencesContent(preferences: preferences)
                .background(bgColor)
        case .agents:
            ModelSettingsView(
                viewModel: settingsViewModel,
                onClose: nil,
                embeddedInHub: true,
                onOpenCapabilities: { agentID in
                    selectedCapabilityAgentId = agentID
                    selectedTab = .capabilities
                }
            )
            .environmentObject(preferences)
        case .capabilities:
            AgentCapabilitiesView(
                settingsViewModel: settingsViewModel,
                initialAgentId: selectedCapabilityAgentId,
                onClose: nil,
                embeddedInHub: true
            )
            .environmentObject(preferences)
        case .plugins:
            PluginLifecycleView(onClose: nil, embeddedInHub: true)
                .environmentObject(preferences)
        case .workers:
            DevicesWorkersSettingsView()
                .environmentObject(preferences)
        case .mcp:
            MCPPreferencesView(onClose: nil, embeddedInHub: true)
                .environmentObject(preferences)
        case .tools:
            ToolPermissionsView(onClose: nil, embeddedInHub: true)
                .environmentObject(preferences)
        case .diagnostics:
            StartupDiagnosticsView(settingsViewModel: settingsViewModel)
                .environmentObject(preferences)
        }
    }
}

private enum PreferencesContentSection {
    case all
    case general
    case experience
}

private struct GlobalPreferencesContent: View {
    @ObservedObject var preferences: AppPreferences
    var section: PreferencesContentSection = .all
    @Environment(\.colorScheme) private var colorScheme
    @State private var availableVoices: [AVSpeechSynthesisVoice] = AVSpeechSynthesisVoice.speechVoices()
    @State private var isVoicePickerPresented = false

    private var textColor: Color { .primary }
    private var fieldColor: Color { Color(nsColor: .controlBackgroundColor) }
    private var accentColor: Color { AcrossTheme.accent }
    private let controlColumnWidth: CGFloat = 320

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 32) {
                MinimalSettingsPageHeader(
                    title: preferences.text(section == .experience ? "settings.experience" : "settings.title"),
                    subtitle: preferences.text(section == .experience ? "settings.experience.subtitle" : "settings.subtitle")
                )

                if section != .experience {
                    PreferenceSection(
                        title: preferences.text("settings.delivery.title"),
                        description: preferences.text("settings.delivery.subtitle")
                    ) {
                        settingRow(
                            title: preferences.text("work.automaticCheck"),
                            help: preferences.text("work.automaticCheck.help")
                        ) {
                            Toggle("", isOn: $preferences.automaticDeliveryProtection)
                                .labelsHidden()
                        }
                    }

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
                }

                if section != .general {
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
                            NSWorkspace.shared.open(LocalAppPaths.acrossRoot)
                        }
                    }
                    }
                }

            }
            .minimalPageContentFrame()
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
                .foregroundColor(Color(nsColor: .systemGreen))
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(Color(nsColor: .systemGreen).opacity(0.14))
                .cornerRadius(999)
        }
        .padding(12)
        .overlay(alignment: .bottom) { Divider() }
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
        .overlay(alignment: .bottom) { Divider() }
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
        MinimalSettingsSection(title: title, subtitle: description) {
            VStack(spacing: 0) {
                content()
            }
        }
    }
}
