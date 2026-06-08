import SwiftUI
import AppKit

private enum CapabilityAgentKind {
    case local
    case cloud
}

private struct CapabilityAgentOption: Identifiable, Equatable {
    let id: String
    let name: String
    let iconName: String
    let kind: CapabilityAgentKind
    let isAvailable: Bool

    @MainActor
    func subtitle(preferences: AppPreferences) -> String {
        switch kind {
        case .local:
            return preferences.text(isAvailable ? "capabilities.agent.local.available" : "capabilities.agent.local.configurable")
        case .cloud:
            return preferences.text(isAvailable ? "capabilities.agent.cloud.available" : "capabilities.agent.cloud.configurable")
        }
    }
}

struct AgentCapabilitiesView: View {
    @ObservedObject var settingsViewModel: SettingsViewModel
    @EnvironmentObject private var appPreferences: AppPreferences
    @Environment(\.colorScheme) private var colorScheme

    @StateObject private var viewModel = AgentCapabilityViewModel()
    @StateObject private var mcpManager = MCPPluginManager.shared
    @State private var selectedAgentId: String?
    @State private var toolSearch = ""
    @State private var showCustomSkillEditor = false
    @State private var customSkillName = ""
    @State private var customSkillDescription = ""
    @State private var customSkillPromptHint = ""
    @State private var customSkillTags = ""
    @State private var nativeSkillIdentifier = ""
    @State private var nativeSkillName = ""
    @State private var nativeSkillDescription = ""
    @State private var nativeSkillBody = ""
    @State private var nativeSkillForce = false

    var onClose: (() -> Void)? = nil
    var embeddedInHub: Bool = false

    private var bgColor: Color { colorScheme == .dark ? .legacyBgDark : .legacyBgLight }
    private var headerColor: Color { colorScheme == .dark ? .legacyBgDark : .legacyBgLight }
    private var cardColor: Color { colorScheme == .dark ? Color(hex: "20222a") : .white }
    private var softColor: Color { colorScheme == .dark ? Color.white.opacity(0.055) : Color.black.opacity(0.04) }
    private var lineColor: Color { colorScheme == .dark ? Color.white.opacity(0.09) : Color.black.opacity(0.10) }
    private var textColor: Color { colorScheme == .dark ? .legacyTextDark : .legacyTextLight }
    private var accentColor: Color { colorScheme == .dark ? .legacyAccentDark : .legacyAccentLight }
    private var mcpColor: Color { colorScheme == .dark ? Color(hex: "38d88b") : Color(hex: "29a36a") }
    private var toolColor: Color { colorScheme == .dark ? Color(hex: "4da3ff") : Color(hex: "0a84ff") }

    private var agentOptions: [CapabilityAgentOption] {
        let local = settingsViewModel.localAgents.map { agent in
            CapabilityAgentOption(
                id: AgentIDs.normalized(agent.id) ?? agent.id,
                name: agent.name,
                iconName: agent.iconName,
                kind: .local,
                isAvailable: settingsViewModel.isLocalAgentAvailable(agent.id)
            )
        }
        let cloud = settingsViewModel.cloudLLMs.map { llm in
            CapabilityAgentOption(
                id: llm.id,
                name: llm.name,
                iconName: llm.iconName,
                kind: .cloud,
                isAvailable: settingsViewModel.isKeyConfigured(llm.id)
            )
        }
        return local + cloud
    }

    private var selectedAgent: CapabilityAgentOption? {
        guard let selectedAgentId else { return agentOptions.first }
        return agentOptions.first(where: { $0.id == selectedAgentId }) ?? agentOptions.first
    }

    private var selectedProfile: AgentCapabilityProfile? {
        guard let agent = selectedAgent else { return nil }
        return viewModel.profile(for: agent.id)
    }

    private var filteredTools: [AgentCapabilityToolSchema] {
        let query = toolSearch.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !query.isEmpty else { return viewModel.availableTools }
        return viewModel.availableTools.filter {
            $0.name.lowercased().contains(query)
                || ($0.description ?? "").lowercased().contains(query)
        }
    }

    private let skillColumns = Array(repeating: GridItem(.flexible(), spacing: 12), count: 2)
    private let toolColumns = Array(repeating: GridItem(.flexible(), spacing: 10), count: 2)

    var body: some View {
        VStack(spacing: 0) {
            if !embeddedInHub {
                standaloneHeader
                Divider().opacity(0.35)
            }

            ScrollView {
                VStack(alignment: .leading, spacing: SettingsHubPageLayout.sectionSpacing) {
                    titleRow

                    if let errorMessage = viewModel.errorMessage {
                        warningBanner(errorMessage)
                    }
                    if let nativeSkillMessage = viewModel.nativeSkillMessage {
                        warningBanner(nativeSkillMessage)
                    }

                    HStack(alignment: .top, spacing: 18) {
                        agentList
                            .frame(width: 246)

                        if let agent = selectedAgent, let profile = selectedProfile {
                            profileEditor(agent: agent, profile: profile)
                        } else {
                            emptyPanel
                        }
                    }
                }
                .padding(SettingsHubPageLayout.contentPadding)
                .frame(maxWidth: SettingsHubPageLayout.contentMaxWidth, alignment: .leading)
                .frame(maxWidth: .infinity)
            }
            .overlay {
                if viewModel.isLoading {
                    ProgressView()
                        .controlSize(.small)
                        .padding(18)
                        .background(cardColor)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                        .shadow(color: Color.black.opacity(0.14), radius: 18, x: 0, y: 8)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(bgColor)
        .background(
            Group {
                if !embeddedInHub {
                    VisualEffectView().ignoresSafeArea()
                }
            }
        )
        .ignoresSafeArea(.all, edges: embeddedInHub ? Edge.Set() : .top)
        .task {
            ensureSelectedAgent()
            await viewModel.load()
        }
        .sheet(isPresented: $showCustomSkillEditor) {
            customSkillEditorSheet
        }
        .onChange(of: agentOptions) {
            ensureSelectedAgent()
        }
    }

    private var standaloneHeader: some View {
        HStack {
            CustomTrafficLights(onClose: onClose)
            Spacer()
            Text(appPreferences.text("capabilities.title"))
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(textColor)
            Spacer()
            Spacer().frame(width: 50)
        }
        .padding(.horizontal, 16)
        .frame(height: 56)
        .background(
            ZStack {
                headerColor.opacity(colorScheme == .dark ? 0.84 : 0.96)
                WindowDragView().contentShape(Rectangle())
            }
        )
    }

    private var titleRow: some View {
        HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 5) {
                Text(appPreferences.text("capabilities.title"))
                    .font(.system(size: 28, weight: .bold))
                    .foregroundColor(textColor)
                Text(appPreferences.text("capabilities.subtitle"))
                    .font(.system(size: 13))
                    .foregroundColor(.secondary)
            }

            Spacer()

            Button {
                Task { await viewModel.load() }
            } label: {
                Image(systemName: "arrow.clockwise")
                    .font(.system(size: 13, weight: .semibold))
                    .frame(width: 32, height: 30)
            }
            .buttonStyle(.plain)
            .foregroundColor(textColor)
            .background(softColor)
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .help(appPreferences.text("settings.refresh"))
        }
    }

    private var agentList: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(appPreferences.text("capabilities.agents"))
                .font(.system(size: 12, weight: .bold))
                .foregroundColor(.secondary)
                .padding(.horizontal, 2)

            VStack(spacing: 8) {
                ForEach(agentOptions) { agent in
                    agentRow(agent)
                }
            }
        }
    }

    private func agentRow(_ agent: CapabilityAgentOption) -> some View {
        let isSelected = selectedAgent?.id == agent.id
        let profile = viewModel.profile(for: agent.id)
        let agentCard = viewModel.agentCard(for: agent.id)
        return Button {
            selectedAgentId = agent.id
        } label: {
            HStack(spacing: 10) {
                agentIcon(agent.iconName)
                    .frame(width: 32, height: 32)
                    .background((isSelected ? accentColor : Color.secondary).opacity(colorScheme == .dark ? 0.16 : 0.10))
                    .clipShape(RoundedRectangle(cornerRadius: 8))

                VStack(alignment: .leading, spacing: 3) {
                    Text(agent.name)
                        .font(.system(size: 13, weight: .bold))
                        .foregroundColor(textColor)
                        .lineLimit(1)
                    Text(agent.subtitle(preferences: appPreferences))
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                }

                Spacer(minLength: 8)

                if case .local = agent.kind,
                   let health = agentCard?.nativeSkillHealth,
                   health.total > 0 {
                    nativeHealthChip(health)
                }

                Text("\(AgentCapabilityCatalog.configuredCapabilityCount(profile))")
                    .font(.system(size: 11, weight: .bold, design: .rounded))
                    .foregroundColor(isSelected ? accentColor : .secondary)
                    .frame(width: 24, height: 22)
                    .background((isSelected ? accentColor : Color.secondary).opacity(0.10))
                    .clipShape(RoundedRectangle(cornerRadius: 7))
            }
            .padding(10)
            .background(isSelected ? accentColor.opacity(0.12) : cardColor)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(isSelected ? accentColor.opacity(0.35) : lineColor, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }

    private func nativeHealthChip(_ health: AgentCapabilityNativeSkillHealth) -> some View {
        HStack(spacing: 4) {
            Circle()
                .fill(health.unavailable == 0 ? Color(hex: "30d158") : Color(hex: "ff9f0a"))
                .frame(width: 5, height: 5)
            Text("\(health.available)/\(health.total)")
                .font(.system(size: 10, weight: .bold, design: .rounded))
                .foregroundColor(.secondary)
        }
        .padding(.horizontal, 6)
        .frame(height: 22)
        .background(softColor)
        .clipShape(RoundedRectangle(cornerRadius: 7))
        .help(appPreferences.text("capabilities.nativeSkills.health"))
    }

    private func profileEditor(agent: CapabilityAgentOption, profile: AgentCapabilityProfile) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            profileHeader(agent: agent, profile: profile)
            skillsSection(agentId: agent.id, profile: profile)
            if case .local = agent.kind {
                nativeSkillsSection(agent: agent)
            }
            pluginsSection(agentId: agent.id, profile: profile)
            toolsSection(agentId: agent.id, profile: profile)
            instructionsSection(agentId: agent.id, profile: profile)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func profileHeader(agent: CapabilityAgentOption, profile: AgentCapabilityProfile) -> some View {
        HStack(alignment: .center, spacing: 12) {
            agentIcon(agent.iconName)
                .frame(width: 38, height: 38)
                .background(accentColor.opacity(colorScheme == .dark ? 0.18 : 0.12))
                .clipShape(RoundedRectangle(cornerRadius: 10))

            VStack(alignment: .leading, spacing: 3) {
                Text(agent.name)
                    .font(.system(size: 18, weight: .bold))
                    .foregroundColor(textColor)
                Text(String(format: appPreferences.text("capabilities.configuredCount"), AgentCapabilityCatalog.configuredCapabilityCount(profile)))
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(.secondary)
            }

            Spacer()

            Button {
                viewModel.resetProfile(for: agent.id)
            } label: {
                Image(systemName: "arrow.uturn.backward")
                    .font(.system(size: 13, weight: .semibold))
                    .frame(width: 32, height: 30)
            }
            .buttonStyle(.plain)
            .foregroundColor(.secondary)
            .background(softColor)
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .help(appPreferences.text("capabilities.reset"))

            Button {
                Task { await viewModel.saveProfile(for: agent.id) }
            } label: {
                HStack(spacing: 7) {
                    if viewModel.isSaving {
                        ProgressView()
                            .controlSize(.mini)
                            .scaleEffect(0.65)
                    } else {
                        Image(systemName: "checkmark")
                            .font(.system(size: 12, weight: .bold))
                    }
                    Text(appPreferences.text("system.save"))
                        .font(.system(size: 12, weight: .bold))
                }
                .frame(minWidth: 78, minHeight: 30)
                .padding(.horizontal, 8)
            }
            .buttonStyle(.plain)
            .foregroundColor(textColor)
            .background(accentColor.opacity(0.18))
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(accentColor.opacity(0.34), lineWidth: 1)
            )
            .disabled(viewModel.isSaving)
        }
        .padding(14)
        .background(cardColor)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(lineColor, lineWidth: 1)
        )
    }

    private func skillsSection(agentId: String, profile: AgentCapabilityProfile) -> some View {
        capabilitySection(
            title: appPreferences.text("capabilities.skills"),
            iconName: "sparkles",
            tint: accentColor
        ) {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 8) {
                    Text(String(format: appPreferences.text("capabilities.customSkillCount"), viewModel.skillCatalog.filter(\.isCustom).count))
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(.secondary)
                    Spacer()
                    Button {
                        resetCustomSkillDraft()
                        showCustomSkillEditor = true
                    } label: {
                        HStack(spacing: 6) {
                            Image(systemName: "plus")
                                .font(.system(size: 11, weight: .bold))
                            Text(appPreferences.text("capabilities.addSkill"))
                                .font(.system(size: 11, weight: .bold))
                        }
                        .padding(.horizontal, 9)
                        .frame(height: 28)
                    }
                    .buttonStyle(.plain)
                    .foregroundColor(textColor)
                    .background(accentColor.opacity(0.16))
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                    .help(appPreferences.text("capabilities.addSkill"))
                }

                LazyVGrid(columns: skillColumns, spacing: 12) {
                    ForEach(viewModel.skillCatalog) { skill in
                        skillCard(skill, agentId: agentId, profile: profile)
                    }
                }
            }
        }
    }

    private func skillCard(
        _ skill: AgentSkillDefinition,
        agentId: String,
        profile: AgentCapabilityProfile
    ) -> some View {
        let isOn = profile.enabledSkillIds.contains(skill.id)
        return VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 8) {
                Image(systemName: iconForSkill(skill.id))
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(accentColor)
                    .frame(width: 26, height: 26)
                    .background(accentColor.opacity(0.13))
                    .clipShape(RoundedRectangle(cornerRadius: 7))

                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 5) {
                        Text(localizedSkillName(skill))
                            .font(.system(size: 12, weight: .bold))
                            .foregroundColor(textColor)
                            .lineLimit(1)
                        if skill.isCustom {
                            Text(appPreferences.text("capabilities.customSkill"))
                                .font(.system(size: 9, weight: .bold))
                                .foregroundColor(accentColor)
                                .padding(.horizontal, 5)
                                .frame(height: 16)
                                .background(accentColor.opacity(0.14))
                                .clipShape(RoundedRectangle(cornerRadius: 5))
                        }
                    }
                    Text(localizedSkillDescription(skill))
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                        .frame(height: 30, alignment: .topLeading)
                }

                Spacer(minLength: 4)

                if skill.isCustom {
                    Button {
                        Task { await viewModel.deleteCustomSkill(skill.id) }
                    } label: {
                        Image(systemName: "trash")
                            .font(.system(size: 11, weight: .semibold))
                            .frame(width: 22, height: 22)
                    }
                    .buttonStyle(.plain)
                    .foregroundColor(.secondary)
                    .background(softColor)
                    .clipShape(RoundedRectangle(cornerRadius: 6))
                    .help(appPreferences.text("capabilities.deleteSkill"))
                    .disabled(viewModel.isSaving)
                }

                Toggle("", isOn: Binding(
                    get: { isOn },
                    set: { viewModel.setSkill(skill.id, enabled: $0, for: agentId) }
                ))
                .labelsHidden()
                .toggleStyle(.switch)
                .controlSize(.mini)
            }
        }
        .padding(10)
        .frame(height: 78)
        .background(softColor)
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(isOn ? accentColor.opacity(0.30) : lineColor, lineWidth: 1)
        )
    }

    private func nativeSkillsSection(agent: CapabilityAgentOption) -> some View {
        let state = viewModel.nativeSkillState(for: agent.id)
        return capabilitySection(
            title: appPreferences.text("capabilities.nativeSkills"),
            iconName: "square.stack.3d.up.fill",
            tint: Color(hex: colorScheme == .dark ? "f0b35a" : "c77700")
        ) {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 8) {
                    Text(String(format: appPreferences.text("capabilities.nativeSkillCount"), state?.installedCount ?? 0))
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(.secondary)
                    if let state {
                        Text(localizedNativeMode(state.mode))
                            .font(.system(size: 10, weight: .bold))
                            .foregroundColor(.secondary)
                            .padding(.horizontal, 6)
                            .frame(height: 18)
                            .background(softColor)
                            .clipShape(RoundedRectangle(cornerRadius: 6))
                    }
                    Spacer()
                    Button {
                        Task { await viewModel.loadNativeSkills() }
                    } label: {
                        Image(systemName: "arrow.clockwise")
                            .font(.system(size: 11, weight: .bold))
                            .frame(width: 28, height: 26)
                    }
                    .buttonStyle(.plain)
                    .foregroundColor(textColor)
                    .background(softColor)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                    .help(appPreferences.text("settings.refresh"))
                }

                if let error = state?.error, !error.isEmpty {
                    inlineNativeMessage(error)
                }

                if let state, !state.skills.isEmpty {
                    LazyVGrid(columns: toolColumns, spacing: 10) {
                        ForEach(state.skills) { skill in
                            nativeSkillCard(skill, agent: agent, state: state)
                        }
                    }
                } else {
                    inlineNativeMessage(appPreferences.text("capabilities.nativeSkills.empty"))
                }

                nativeSkillInstallPanel(agent: agent, state: state)
            }
        }
    }

    private func nativeSkillCard(
        _ skill: NativeSkillDefinition,
        agent: CapabilityAgentOption,
        state: NativeSkillAgentState
    ) -> some View {
        HStack(spacing: 9) {
            Image(systemName: skillIconName(skill))
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(nativeSkillTint(skill))
                .frame(width: 28, height: 28)
                .background(nativeSkillTint(skill).opacity(0.13))
                .clipShape(RoundedRectangle(cornerRadius: 7))

            VStack(alignment: .leading, spacing: 2) {
                Text(skill.name)
                    .font(.system(size: 12, weight: .bold))
                    .foregroundColor(textColor)
                    .lineLimit(1)
                Text(nativeSkillMeta(skill))
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(skill.isActive ? .secondary : Color.orange)
                    .lineLimit(1)
            }

            Spacer(minLength: 4)

            if state.supportsUpdate && skill.supportsUpdate {
                Button {
                    Task { await viewModel.updateNativeSkill(skill.id, for: agent.id) }
                } label: {
                    Image(systemName: "arrow.triangle.2.circlepath")
                        .font(.system(size: 11, weight: .bold))
                        .frame(width: 24, height: 24)
                }
                .buttonStyle(.plain)
                .foregroundColor(.secondary)
                .background(softColor)
                .clipShape(RoundedRectangle(cornerRadius: 7))
                .disabled(viewModel.isNativeSkillWorking)
                .help(appPreferences.text("capabilities.nativeSkills.update"))
            }

            if state.supportsUninstall && skill.supportsUninstall {
                Button {
                    Task { await viewModel.uninstallNativeSkill(skill.id, for: agent.id) }
                } label: {
                    Image(systemName: "trash")
                        .font(.system(size: 11, weight: .bold))
                        .frame(width: 24, height: 24)
                }
                .buttonStyle(.plain)
                .foregroundColor(.secondary)
                .background(softColor)
                .clipShape(RoundedRectangle(cornerRadius: 7))
                .disabled(viewModel.isNativeSkillWorking)
                .help(appPreferences.text("capabilities.nativeSkills.uninstall"))
            }
        }
        .padding(10)
        .frame(height: 58)
        .background(softColor)
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(skill.isActive ? lineColor : Color.orange.opacity(0.30), lineWidth: 1)
        )
        .help(nativeSkillHelp(skill))
    }

    private func nativeSkillInstallPanel(agent: CapabilityAgentOption, state: NativeSkillAgentState?) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(appPreferences.text(agent.id == "claude" ? "capabilities.nativeSkills.create" : "capabilities.nativeSkills.install"))
                .font(.system(size: 12, weight: .bold))
                .foregroundColor(textColor)

            if agent.id == "claude" {
                HStack(spacing: 10) {
                    nativeSkillTextField(appPreferences.text("capabilities.skillName"), text: $nativeSkillName)
                    nativeSkillTextField(appPreferences.text("capabilities.skillDescription"), text: $nativeSkillDescription)
                }
                TextEditor(text: $nativeSkillBody)
                    .font(.system(size: 12))
                    .scrollContentBackground(.hidden)
                    .frame(height: 64)
                    .padding(8)
                    .background(softColor)
                    .clipShape(RoundedRectangle(cornerRadius: 9))
                    .overlay(
                        RoundedRectangle(cornerRadius: 9)
                            .stroke(lineColor, lineWidth: 1)
                    )
            } else {
                HStack(spacing: 10) {
                    nativeSkillTextField(appPreferences.text("capabilities.nativeSkills.identifier"), text: $nativeSkillIdentifier)
                    Toggle("", isOn: $nativeSkillForce)
                        .labelsHidden()
                        .toggleStyle(.switch)
                        .controlSize(.small)
                    Text(appPreferences.text("capabilities.nativeSkills.force"))
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(.secondary)
                }
            }

            HStack {
                Spacer()
                Button {
                    Task { await submitNativeSkillInstall(for: agent) }
                } label: {
                    HStack(spacing: 7) {
                        if viewModel.isNativeSkillWorking {
                            ProgressView()
                                .controlSize(.mini)
                                .scaleEffect(0.65)
                        } else {
                            Image(systemName: "square.and.arrow.down")
                                .font(.system(size: 11, weight: .bold))
                        }
                        Text(appPreferences.text("capabilities.nativeSkills.apply"))
                            .font(.system(size: 11, weight: .bold))
                    }
                    .frame(minWidth: 86, minHeight: 28)
                    .padding(.horizontal, 8)
                }
                .buttonStyle(.plain)
                .foregroundColor(textColor)
                .background(accentColor.opacity(isNativeSkillDraftValid(for: agent) ? 0.18 : 0.08))
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .disabled(!isNativeSkillDraftValid(for: agent) || viewModel.isNativeSkillWorking || state?.supportsInstall == false)
            }
        }
        .padding(10)
        .background(softColor)
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(lineColor, lineWidth: 1)
        )
    }

    private func nativeSkillTextField(_ placeholder: String, text: Binding<String>) -> some View {
        TextField(placeholder, text: text)
            .textFieldStyle(.plain)
            .font(.system(size: 12, weight: .medium))
            .foregroundColor(textColor)
            .padding(.horizontal, 10)
            .frame(height: 32)
            .background(softColor)
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(lineColor, lineWidth: 1)
            )
    }

    private func inlineNativeMessage(_ message: String) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "info.circle")
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(.secondary)
            Text(message)
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(.secondary)
                .lineLimit(2)
            Spacer()
        }
        .padding(10)
        .background(softColor)
        .clipShape(RoundedRectangle(cornerRadius: 9))
    }

    private func pluginsSection(agentId: String, profile: AgentCapabilityProfile) -> some View {
        capabilitySection(
            title: appPreferences.text("capabilities.plugins"),
            iconName: "square.grid.2x2",
            tint: mcpColor
        ) {
            LazyVGrid(columns: toolColumns, spacing: 10) {
                ForEach(mcpManager.plugins) { plugin in
                    pluginCard(plugin, agentId: agentId, profile: profile)
                }
            }
        }
    }

    private func pluginCard(
        _ plugin: MCPPlugin,
        agentId: String,
        profile: AgentCapabilityProfile
    ) -> some View {
        let isOn = profile.enabledPluginIds.contains(plugin.id)
        return HStack(spacing: 9) {
            Image(systemName: iconForPlugin(plugin.id))
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(mcpColor)
                .frame(width: 28, height: 28)
                .background(mcpColor.opacity(0.13))
                .clipShape(RoundedRectangle(cornerRadius: 7))

            VStack(alignment: .leading, spacing: 2) {
                Text(localizedPluginName(plugin))
                    .font(.system(size: 12, weight: .bold))
                    .foregroundColor(textColor)
                    .lineLimit(1)
                Text(localizedPluginStatus(plugin))
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(plugin.status == "connected" ? mcpColor : .secondary)
                    .lineLimit(1)
            }

            Spacer(minLength: 4)

            Toggle("", isOn: Binding(
                get: { isOn },
                set: { viewModel.setPlugin(plugin.id, enabled: $0, for: agentId) }
            ))
            .labelsHidden()
            .toggleStyle(.switch)
            .controlSize(.mini)
        }
        .padding(10)
        .frame(height: 58)
        .background(softColor)
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(isOn ? mcpColor.opacity(0.30) : lineColor, lineWidth: 1)
        )
    }

    private func toolsSection(agentId: String, profile: AgentCapabilityProfile) -> some View {
        capabilitySection(
            title: appPreferences.text("capabilities.tools"),
            iconName: "wrench.and.screwdriver.fill",
            tint: toolColor
        ) {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 8) {
                    Image(systemName: "magnifyingglass")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(.secondary)
                    TextField(appPreferences.text("capabilities.searchTools"), text: $toolSearch)
                        .textFieldStyle(.plain)
                        .font(.system(size: 12, weight: .medium))
                }
                .padding(.horizontal, 10)
                .frame(height: 32)
                .background(softColor)
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(lineColor, lineWidth: 1)
                )

                LazyVGrid(columns: toolColumns, spacing: 10) {
                    ForEach(filteredTools) { tool in
                        toolCard(tool, agentId: agentId, profile: profile)
                    }
                }
            }
        }
    }

    private func toolCard(
        _ tool: AgentCapabilityToolSchema,
        agentId: String,
        profile: AgentCapabilityProfile
    ) -> some View {
        let isOn = profile.enabledToolNames.contains(tool.name)
        return HStack(spacing: 8) {
            Image(systemName: capabilityIconForTool(tool.name))
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(toolColor)
                .frame(width: 26, height: 26)
                .background(toolColor.opacity(0.12))
                .clipShape(RoundedRectangle(cornerRadius: 7))

            VStack(alignment: .leading, spacing: 2) {
                Text(localizedToolName(tool.name, preferences: appPreferences))
                    .font(.system(size: 12, weight: .bold))
                    .foregroundColor(textColor)
                    .lineLimit(1)
                Text(tool.name)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundColor(.secondary.opacity(0.75))
                    .lineLimit(1)
                    .truncationMode(.middle)
            }

            Spacer(minLength: 4)

            Toggle("", isOn: Binding(
                get: { isOn },
                set: { viewModel.setTool(tool.name, enabled: $0, for: agentId) }
            ))
            .labelsHidden()
            .toggleStyle(.switch)
            .controlSize(.mini)
        }
        .padding(9)
        .frame(height: 54)
        .background(softColor)
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(isOn ? toolColor.opacity(0.30) : lineColor, lineWidth: 1)
        )
    }

    private func instructionsSection(agentId: String, profile: AgentCapabilityProfile) -> some View {
        capabilitySection(
            title: appPreferences.text("capabilities.instructions"),
            iconName: "text.alignleft",
            tint: accentColor
        ) {
            VStack(alignment: .leading, spacing: 10) {
                TextEditor(text: Binding(
                    get: { profile.customInstructions },
                    set: { viewModel.setCustomInstructions($0, for: agentId) }
                ))
                .font(.system(size: 12))
                .scrollContentBackground(.hidden)
                .frame(height: 82)
                .padding(8)
                .background(softColor)
                .clipShape(RoundedRectangle(cornerRadius: 10))
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .stroke(lineColor, lineWidth: 1)
                )

                HStack(spacing: 10) {
                    Toggle("", isOn: Binding(
                        get: { profile.strictToolScope },
                        set: { viewModel.setStrictToolScope($0, for: agentId) }
                    ))
                    .labelsHidden()
                    .toggleStyle(.switch)
                    .controlSize(.small)

                    VStack(alignment: .leading, spacing: 2) {
                        Text(appPreferences.text("capabilities.strictScope"))
                            .font(.system(size: 12, weight: .bold))
                            .foregroundColor(textColor)
                        Text(appPreferences.text("capabilities.strictScope.help"))
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                    }

                    Spacer()
                }
                .padding(10)
                .background(softColor)
                .clipShape(RoundedRectangle(cornerRadius: 10))
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .stroke(lineColor, lineWidth: 1)
                )
            }
        }
    }

    private func capabilitySection<Content: View>(
        title: String,
        iconName: String,
        tint: Color,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Image(systemName: iconName)
                    .font(.system(size: 13, weight: .bold))
                    .foregroundColor(tint)
                    .frame(width: 18)
                Text(title)
                    .font(.system(size: 14, weight: .bold))
                    .foregroundColor(tint)
                Spacer()
            }
            content()
        }
        .padding(14)
        .background(cardColor)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(lineColor, lineWidth: 1)
        )
    }

    private var emptyPanel: some View {
        VStack(spacing: 8) {
            Image(systemName: "sparkles.rectangle.stack")
                .font(.system(size: 22, weight: .semibold))
                .foregroundColor(accentColor)
            Text(appPreferences.text("capabilities.empty"))
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, minHeight: 180)
        .background(cardColor)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(lineColor, lineWidth: 1)
        )
    }

    private func warningBanner(_ message: String) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundColor(.orange)
            Text(message)
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(.secondary)
            Spacer()
            Button(appPreferences.text("system.retry")) {
                Task { await viewModel.load() }
            }
            .buttonStyle(.plain)
            .font(.system(size: 12, weight: .semibold))
            .foregroundColor(accentColor)
        }
        .padding(10)
        .background(cardColor)
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(lineColor, lineWidth: 1)
        )
    }

    private func ensureSelectedAgent() {
        if selectedAgentId == nil || !agentOptions.contains(where: { $0.id == selectedAgentId }) {
            selectedAgentId = agentOptions.first?.id
        }
    }

    private func agentIcon(_ iconName: String) -> some View {
        Group {
            if let nsImage = loadAgentIconSync(name: iconName, colorScheme: colorScheme) {
                Image(nsImage: nsImage)
                    .resizable()
                    .scaledToFit()
            } else {
                Image(systemName: "cpu")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundColor(accentColor)
            }
        }
    }

    private func localizedPluginName(_ plugin: MCPPlugin) -> String {
        let key = "mcp.plugin.\(plugin.id).name"
        let value = appPreferences.text(key)
        return value == key ? plugin.name : value
    }

    private func localizedPluginStatus(_ plugin: MCPPlugin) -> String {
        switch plugin.status {
        case "connected": return appPreferences.text("mcp.connected")
        case "connecting": return appPreferences.text("mcp.connecting")
        case "error": return appPreferences.text("mcp.failed")
        default:
            if !plugin.isEnabled {
                return appPreferences.text("mcp.disabled")
            }
            if plugin.requiresConfiguration && !plugin.isConfigurationComplete {
                return appPreferences.text("mcp.needsConfiguration")
            }
            return appPreferences.text("mcp.disconnected")
        }
    }

    private func iconForSkill(_ id: String) -> String {
        if id.contains("frontend") || id.contains("interaction") { return "rectangle.3.group.fill" }
        if id.contains("backend") || id.contains("data") { return "server.rack" }
        if id.contains("test") || id.contains("integration") { return "checkmark.seal.fill" }
        if id.contains("review") || id.contains("architecture") { return "doc.text.magnifyingglass" }
        if id.contains("devops") { return "shippingbox.fill" }
        if id.contains("macos") { return "macwindow" }
        return "sparkles"
    }

    private func iconForPlugin(_ id: String) -> String {
        if id == "filesystem" { return "folder.fill" }
        if id == "sqlite" { return "cylinder.split.1x2.fill" }
        if id == "local_kb" { return "book.closed.fill" }
        if id == "external_rag" { return "cloud.fill" }
        if id == "across_context" { return "memorychip.fill" }
        return "square.grid.2x2.fill"
    }

    private func capabilityIconForTool(_ name: String) -> String {
        if name.contains("file") || name.contains("directory") { return "folder.fill" }
        if name.contains("sqlite") { return "cylinder.split.1x2.fill" }
        if name.contains("browser") || name.contains("url") { return "safari.fill" }
        if name.contains("finder") { return "finder" }
        if name.contains("xcode") { return "hammer.fill" }
        if name.contains("screenshot") || name.contains("ocr") { return "camera.viewfinder" }
        if name.contains("note") { return "note.text" }
        if name.contains("email") { return "envelope.fill" }
        return "wrench.and.screwdriver.fill"
    }

    private func localizedSkillName(_ skill: AgentSkillDefinition) -> String {
        let key = "capabilities.skill.\(skill.id).name"
        let value = appPreferences.text(key)
        return value == key ? skill.name : value
    }

    private func localizedSkillDescription(_ skill: AgentSkillDefinition) -> String {
        let key = "capabilities.skill.\(skill.id).description"
        let value = appPreferences.text(key)
        return value == key ? skill.description : value
    }

    private func localizedNativeMode(_ mode: String) -> String {
        switch mode {
        case "directory": return appPreferences.text("capabilities.nativeSkills.mode.directory")
        case "cli": return appPreferences.text("capabilities.nativeSkills.mode.cli")
        default: return mode
        }
    }

    private func nativeSkillMeta(_ skill: NativeSkillDefinition) -> String {
        let source = skill.source ?? appPreferences.text("capabilities.nativeSkills.source.native")
        if !skill.isActive {
            if let reason = skill.unavailableReason, !reason.isEmpty {
                return "\(source) · \(appPreferences.text("capabilities.nativeSkills.unavailable")) · \(reason)"
            }
            return "\(source) · \(appPreferences.text("capabilities.nativeSkills.unavailable"))"
        }
        if let version = skill.version, !version.isEmpty {
            return "\(source) · \(skill.status) · \(version)"
        }
        return "\(source) · \(skill.status)"
    }

    private func nativeSkillHelp(_ skill: NativeSkillDefinition) -> String {
        var parts: [String] = []
        if let reason = skill.unavailableReason, !reason.isEmpty {
            parts.append(reason)
        } else {
            parts.append(nativeSkillMeta(skill))
        }
        if !skill.repairSuggestions.isEmpty {
            parts.append(skill.repairSuggestions.joined(separator: "\n"))
        }
        return parts.joined(separator: "\n")
    }

    private func skillIconName(_ skill: NativeSkillDefinition) -> String {
        if !skill.isActive {
            return "exclamationmark.triangle.fill"
        }
        return skill.managedByApp ? "sparkles.rectangle.stack.fill" : "shippingbox.fill"
    }

    private func nativeSkillTint(_ skill: NativeSkillDefinition) -> Color {
        if !skill.isActive {
            return Color.orange
        }
        return Color(hex: colorScheme == .dark ? "f0b35a" : "c77700")
    }

    private func submitNativeSkillInstall(for agent: CapabilityAgentOption) async {
        let request: NativeSkillInstallRequest
        if agent.id == "claude" {
            request = NativeSkillInstallRequest(
                identifier: nil,
                name: nativeSkillName.trimmingCharacters(in: .whitespacesAndNewlines),
                description: nativeSkillDescription.trimmingCharacters(in: .whitespacesAndNewlines),
                body: nativeSkillBody.trimmingCharacters(in: .whitespacesAndNewlines),
                scope: "user",
                projectDir: nil,
                sourcePath: nil,
                version: nil,
                force: nativeSkillForce
            )
        } else {
            request = NativeSkillInstallRequest(
                identifier: nativeSkillIdentifier.trimmingCharacters(in: .whitespacesAndNewlines),
                name: nil,
                description: nil,
                body: nil,
                scope: "user",
                projectDir: nil,
                sourcePath: nil,
                version: nil,
                force: nativeSkillForce
            )
        }
        await viewModel.installNativeSkill(for: agent.id, request: request)
        if viewModel.nativeSkillMessage == nil {
            resetNativeSkillDraft()
        }
    }

    private func isNativeSkillDraftValid(for agent: CapabilityAgentOption) -> Bool {
        if agent.id == "claude" {
            return !nativeSkillName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                && !nativeSkillDescription.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                && !nativeSkillBody.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        }
        return !nativeSkillIdentifier.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private func resetNativeSkillDraft() {
        nativeSkillIdentifier = ""
        nativeSkillName = ""
        nativeSkillDescription = ""
        nativeSkillBody = ""
        nativeSkillForce = false
    }

    private var customSkillEditorSheet: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text(appPreferences.text("capabilities.newSkill"))
                    .font(.system(size: 16, weight: .bold))
                    .foregroundColor(textColor)
                Spacer()
                Button {
                    showCustomSkillEditor = false
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 12, weight: .semibold))
                        .frame(width: 28, height: 28)
                }
                .buttonStyle(.plain)
                .foregroundColor(.secondary)
            }

            customSkillField(
                title: appPreferences.text("capabilities.skillName"),
                text: $customSkillName
            )
            customSkillField(
                title: appPreferences.text("capabilities.skillDescription"),
                text: $customSkillDescription
            )
            customSkillField(
                title: appPreferences.text("capabilities.skillPromptHint"),
                text: $customSkillPromptHint
            )
            customSkillField(
                title: appPreferences.text("capabilities.skillTags"),
                text: $customSkillTags,
                placeholder: appPreferences.text("capabilities.skillTags.placeholder")
            )

            HStack {
                Spacer()
                Button(appPreferences.text("system.cancel")) {
                    showCustomSkillEditor = false
                }
                .buttonStyle(.plain)
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(.secondary)
                .padding(.horizontal, 12)
                .frame(height: 32)
                .background(softColor)
                .clipShape(RoundedRectangle(cornerRadius: 8))

                Button {
                    Task {
                        await viewModel.createCustomSkill(
                            name: customSkillName.trimmingCharacters(in: .whitespacesAndNewlines),
                            description: customSkillDescription.trimmingCharacters(in: .whitespacesAndNewlines),
                            promptHint: customSkillPromptHint.trimmingCharacters(in: .whitespacesAndNewlines),
                            tags: parsedCustomSkillTags
                        )
                        if viewModel.errorMessage == nil {
                            resetCustomSkillDraft()
                            showCustomSkillEditor = false
                        }
                    }
                } label: {
                    if viewModel.isSaving {
                        ProgressView()
                            .controlSize(.mini)
                            .scaleEffect(0.7)
                            .frame(width: 74, height: 32)
                    } else {
                        Text(appPreferences.text("capabilities.createSkill"))
                            .font(.system(size: 12, weight: .bold))
                            .frame(minWidth: 74, minHeight: 32)
                    }
                }
                .buttonStyle(.plain)
                .foregroundColor(textColor)
                .background(accentColor.opacity(isCustomSkillDraftValid ? 0.20 : 0.08))
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .disabled(!isCustomSkillDraftValid || viewModel.isSaving)
            }
        }
        .padding(18)
        .frame(width: 460)
        .background(bgColor)
    }

    private func customSkillField(
        title: String,
        text: Binding<String>,
        placeholder: String = ""
    ) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(.secondary)
            TextField(placeholder, text: text)
                .textFieldStyle(.plain)
                .font(.system(size: 13))
                .foregroundColor(textColor)
                .padding(10)
                .background(softColor)
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(lineColor, lineWidth: 1)
                )
        }
    }

    private var parsedCustomSkillTags: [String] {
        customSkillTags
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
    }

    private var isCustomSkillDraftValid: Bool {
        !customSkillName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !customSkillDescription.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !customSkillPromptHint.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private func resetCustomSkillDraft() {
        customSkillName = ""
        customSkillDescription = ""
        customSkillPromptHint = ""
        customSkillTags = ""
    }
}
