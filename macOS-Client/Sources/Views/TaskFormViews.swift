import SwiftUI
import AppKit

struct AgentOption {
    let id: String
    let name: String
    let isAvailable: Bool
    let iconName: String
    let isCloudLLM: Bool
}

struct TaskNewTaskForm: View {
    @ObservedObject var viewModel: TaskOrchestrationViewModel
    @ObservedObject var settingsVM: SettingsViewModel
    let defaultProjectPath: String?

    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    @ObservedObject private var repositoryStore = SecurityScopedRepositoryStore.shared
    @State private var taskDescription = ""
    @State private var selectedOwnerAgent = "auto"
    @State private var selectedSubtaskAgents: Set<String> = []
    @State private var useAllSubtaskAgents = true
    @State private var projectDir = ""
    @State private var strictDependency = true
    @State private var selectedDeliveryTaskTypes: Set<TaskOrchestrationViewModel.DeliveryTaskType> = []
    @State private var capabilityPreflight: AgentCapabilityPreflightResponse?
    @State private var isPreflightingCapabilities = false
    @State private var capabilityPreflightError: String?
    @State private var appliedSimpleStartDraftId: String?
    private let repositoryAccessOwner = "task-orchestration"

    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    private var trimmedTaskDescription: String {
        taskDescription.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var trimmedProjectDir: String {
        projectDir.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var projectDirectoryExists: Bool {
        guard !trimmedProjectDir.isEmpty else { return false }
        return repositoryStore.isAccessing
            && repositoryStore.selectedPath == trimmedProjectDir
            && SecurityScopedRepositoryStore.isDirectory(URL(fileURLWithPath: trimmedProjectDir))
    }

    private var missingSubmitRequirements: [String] {
        var missing: [String] = []
        if trimmedTaskDescription.isEmpty {
            missing.append(appPreferences.text("tasks.description"))
        }
        if selectedDeliveryTaskTypes.isEmpty {
            missing.append(appPreferences.text("tasks.deliveryType"))
        }
        if trimmedProjectDir.isEmpty {
            missing.append(appPreferences.text("tasks.projectDirectory"))
        } else if !projectDirectoryExists {
            missing.append(appPreferences.text("tasks.field.existingProjectDirectory"))
        }
        if !settingsVM.hasAnyAvailableAgents {
            missing.append(appPreferences.text("tasks.field.availableAgent"))
        }
        return missing
    }

    private var isSubmitDisabled: Bool {
        viewModel.isLoading || !missingSubmitRequirements.isEmpty
    }

    private var selectedTaskTypeValues: [String] {
        selectedDeliveryTaskTypes.map(\.rawValue).sorted()
    }

    private var selectedSubtaskAgentIds: [String] {
        if useAllSubtaskAgents {
            return availableSubtaskAgents.map(\.id).sorted()
        }
        return Array(selectedSubtaskAgents).sorted()
    }

    private var capabilityPreflightSignature: String {
        [
            trimmedTaskDescription,
            selectedOwnerAgent,
            selectedTaskTypeValues.joined(separator: ","),
            selectedSubtaskAgentIds.joined(separator: ",")
        ].joined(separator: "|")
    }

    private var submitHelpText: String {
        if viewModel.isLoading {
            return appPreferences.text("tasks.submitting.help")
        }
        if missingSubmitRequirements.isEmpty {
            return appPreferences.text("tasks.submit.help")
        }
        return String(format: appPreferences.text("tasks.missingFields"), missingSubmitRequirements.joined(separator: ", "))
    }

    private var availableOwnerAgents: [AgentOption] {
        var agents: [AgentOption] = [
            AgentOption(id: "auto", name: appPreferences.text("tasks.auto"), isAvailable: true, iconName: "wand.and.stars", isCloudLLM: false)
        ]
        for agent in settingsVM.availableLocalAgents {
            agents.append(AgentOption(id: agent.id, name: agent.name, isAvailable: true, iconName: agent.iconName, isCloudLLM: false))
        }
        for llm in settingsVM.availableCloudLLMs {
            agents.append(AgentOption(id: llm.id, name: llm.name, isAvailable: true, iconName: llm.iconName, isCloudLLM: true))
        }
        return agents
    }

    private var availableSubtaskAgents: [AgentOption] {
        var agents: [AgentOption] = []
        for agent in settingsVM.availableLocalAgents {
            agents.append(AgentOption(id: agent.id, name: agent.name, isAvailable: true, iconName: agent.iconName, isCloudLLM: false))
        }
        for llm in settingsVM.availableCloudLLMs {
            agents.append(AgentOption(id: llm.id, name: llm.name, isAvailable: true, iconName: llm.iconName, isCloudLLM: true))
        }
        return agents
    }

    private var normalizedDefaultProjectPath: String? {
        let trimmed = defaultProjectPath?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return trimmed.isEmpty ? nil : trimmed
    }

    private func applyDefaultProjectPathIfNeeded() {
        guard projectDir.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        repositoryStore.restore()
        if let selectedPath = repositoryStore.selectedPath,
           repositoryStore.beginAccess(owner: repositoryAccessOwner) {
            projectDir = selectedPath
        }
    }

    private func applySimpleStartDraftIfNeeded() {
        guard let draft = viewModel.simpleStartDraft else {
            appliedSimpleStartDraftId = nil
            return
        }
        guard appliedSimpleStartDraftId != draft.id else { return }

        taskDescription = draft.taskDescription
        selectedDeliveryTaskTypes = draft.deliveryTaskTypes
        applyDefaultProjectPathIfNeeded()
        selectedOwnerAgent = "auto"
        selectedSubtaskAgents.removeAll()
        useAllSubtaskAgents = true
        strictDependency = true
        appliedSimpleStartDraftId = draft.id
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                HStack {
                    Text(appPreferences.text("tasks.new"))
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(theme.primaryText)

                    Spacer()

                    Button(action: { viewModel.cancelCreate() }) {
                        Image(systemName: "xmark")
                            .font(.system(size: 12))
                            .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                }

                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        HStack(spacing: 2) {
                            Text(appPreferences.text("tasks.deliveryType"))
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(.secondary)
                            Text("*")
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(Color(hex: "#FF453A"))
                        }
                        if selectedDeliveryTaskTypes.count > 1 {
                            Text(appPreferences.text("tasks.composite"))
                                .font(.system(size: 10, weight: .medium))
                                .foregroundColor(AcrossTheme.accent)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(AcrossTheme.accent.opacity(0.16))
                                .cornerRadius(5)
                        }
                    }

                    HStack(spacing: 8) {
                        ForEach(TaskOrchestrationViewModel.DeliveryTaskType.allCases) { type in
                            Button(action: {
                                if selectedDeliveryTaskTypes.contains(type), selectedDeliveryTaskTypes.count > 1 {
                                    selectedDeliveryTaskTypes.remove(type)
                                } else {
                                    selectedDeliveryTaskTypes.insert(type)
                                }
                            }) {
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(deliveryTypeTitle(type))
                                        .font(.system(size: 12, weight: .semibold))
                                        .foregroundColor(theme.primaryText)
                                    Text(deliveryTypeSubtitle(type))
                                        .font(.system(size: 10))
                                        .foregroundColor(.secondary)
                                        .lineLimit(2)
                                }
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(10)
                                .background(selectedDeliveryTaskTypes.contains(type) ? AcrossTheme.accent.opacity(0.22) : theme.fieldBackground)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 8)
                                        .stroke(selectedDeliveryTaskTypes.contains(type) ? AcrossTheme.accent.opacity(0.65) : theme.divider, lineWidth: 1)
                                )
                                .cornerRadius(8)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }

                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: 2) {
                        Text(appPreferences.text("tasks.description"))
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(.secondary)
                        Text("*")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(Color(hex: "#FF453A"))
                    }

                    TextEditor(text: $taskDescription)
                        .font(.system(size: 13))
                        .foregroundColor(theme.primaryText)
                        .scrollContentBackground(.hidden)
                        .frame(minHeight: 80)
                        .padding(10)
                        .background(theme.fieldBackground)
                        .cornerRadius(8)
                }

                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: 2) {
                        Text(appPreferences.text("tasks.projectDirectory"))
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(.secondary)
                        Text("*")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(Color(hex: "#FF453A"))
                    }

                    HStack(spacing: 8) {
                        Text(projectDir.isEmpty ? appPreferences.text("workspace.notConfigured") : projectDir)
                            .font(.system(size: 13, design: .monospaced))
                            .foregroundStyle(projectDir.isEmpty ? Color.secondary : Color.primary)
                            .lineLimit(1)
                            .truncationMode(.middle)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, minHeight: 16, alignment: .leading)
                            .padding(10)
                            .background(theme.fieldBackground)
                            .cornerRadius(8)

                        Button(action: browseProjectDir) {
                            Image(systemName: "folder")
                                .font(.system(size: 13))
                                .foregroundColor(.secondary)
                                .frame(width: 36, height: 36)
                                .background(theme.fieldBackground)
                                .cornerRadius(8)
                        }
                        .buttonStyle(.plain)
                        .help(appPreferences.text("system.browse"))
                    }
                }

                VStack(alignment: .leading, spacing: 6) {
                    Text(appPreferences.text("tasks.ownerAgent"))
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.secondary)

                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            ForEach(availableOwnerAgents, id: \.id) { agent in
                                AgentIconChip(
                                    agent: agent,
                                    isSelected: selectedOwnerAgent == agent.id,
                                    onTap: { selectedOwnerAgent = agent.id }
                                )
                            }
                        }
                    }
                }

                VStack(alignment: .leading, spacing: 6) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(appPreferences.text("tasks.subtaskAgents"))
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(.secondary)

                        if useAllSubtaskAgents {
                            Text(appPreferences.text("tasks.autoUsesAll"))
                                .font(.system(size: 10))
                                .foregroundColor(.secondary.opacity(0.6))
                        }
                    }

                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            AgentIconChip(
                                agent: AgentOption(id: "auto", name: appPreferences.text("tasks.autoAllSubtask"), isAvailable: true, iconName: "wand.and.stars", isCloudLLM: false),
                                isSelected: useAllSubtaskAgents,
                                onTap: {
                                    useAllSubtaskAgents = true
                                    selectedSubtaskAgents.removeAll()
                                }
                            )
                            ForEach(availableSubtaskAgents, id: \.id) { agent in
                                AgentIconChip(
                                    agent: agent,
                                    isSelected: !useAllSubtaskAgents && selectedSubtaskAgents.contains(agent.id),
                                    onTap: {
                                        useAllSubtaskAgents = false
                                        if selectedSubtaskAgents.contains(agent.id) {
                                            selectedSubtaskAgents.remove(agent.id)
                                        } else {
                                            selectedSubtaskAgents.insert(agent.id)
                                        }
                                        if selectedSubtaskAgents.isEmpty {
                                            useAllSubtaskAgents = true
                                        }
                                    }
                                )
                            }
                        }
                    }
                }

                capabilityPreflightSection

                VStack(alignment: .leading, spacing: 6) {
                    Toggle(isOn: $strictDependency) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(appPreferences.text("tasks.strictDependency"))
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(.secondary)
                            Text(appPreferences.text("tasks.strictDependency.help"))
                                .font(.system(size: 10))
                                .foregroundColor(.secondary.opacity(0.6))
                        }
                    }
                    .toggleStyle(.switch)
                    .padding(.vertical, 4)
                }

                if let errorMessage = viewModel.errorMessage {
                    HStack(spacing: 6) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .font(.system(size: 11))
                            .foregroundColor(Color(hex: "#FF453A"))
                        Text(errorMessage)
                            .font(.system(size: 12))
                            .foregroundColor(Color(hex: "#FF453A"))
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color(hex: "#FF453A").opacity(0.1))
                    .cornerRadius(6)
                }

                HStack(spacing: 12) {
                    Button(action: { viewModel.cancelCreate() }) {
                        Text(appPreferences.text("system.cancel"))
                            .font(.system(size: 13, weight: .medium))
                            .foregroundColor(.secondary)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 10)
                            .background(theme.controlBackground)
                            .cornerRadius(8)
                    }
                    .buttonStyle(.plain)
                    .disabled(viewModel.isLoading)

                    Button(action: submitTask) {
                        HStack(spacing: 6) {
                            if viewModel.isLoading {
                                ProgressView()
                                    .controlSize(.mini)
                                    .scaleEffect(0.7)
                            }
                            Text(viewModel.isLoading ? appPreferences.text("system.submitting") : appPreferences.text("system.submit"))
                                .font(.system(size: 13, weight: .medium))
                        }
                        .foregroundColor(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 10)
                        .background(viewModel.isLoading ? AcrossTheme.accent.opacity(0.5) : AcrossTheme.accent)
                        .cornerRadius(8)
                    }
                    .buttonStyle(.plain)
                    .disabled(isSubmitDisabled)
                    .opacity(isSubmitDisabled ? 0.5 : 1)
                    .help(submitHelpText)
                    .overlay {
                        if isSubmitDisabled {
                            Color.clear
                                .contentShape(Rectangle())
                                .help(submitHelpText)
                        }
                    }
                }
                .padding(.top, 8)
            }
            .padding(20)
        }
        .onAppear {
            applyDefaultProjectPathIfNeeded()
            applySimpleStartDraftIfNeeded()
            if !availableOwnerAgents.contains(where: { $0.id == selectedOwnerAgent }) {
                selectedOwnerAgent = "auto"
            }
        }
        .onChange(of: viewModel.simpleStartDraft?.id) {
            applySimpleStartDraftIfNeeded()
        }
        .onChange(of: availableOwnerAgents.map(\.id)) {
            let ids = availableOwnerAgents.map(\.id)
            if !ids.contains(selectedOwnerAgent) {
                selectedOwnerAgent = "auto"
            }
        }
        .onChange(of: availableSubtaskAgents.map(\.id)) {
            let ids = availableSubtaskAgents.map(\.id)
            selectedSubtaskAgents = selectedSubtaskAgents.intersection(Set(ids))
            if selectedSubtaskAgents.isEmpty {
                useAllSubtaskAgents = true
            }
        }
        .task(id: capabilityPreflightSignature) {
            await refreshCapabilityPreflight()
        }
    }

    private func browseProjectDir() {
        guard let url = repositoryStore.chooseRepository(
            title: appPreferences.text("tasks.selectProjectDirectory"),
            message: appPreferences.text("workspace.create.repositoryPickerMessage"),
            prompt: appPreferences.text("workspace.create.chooseRepository")
        ) else { return }
        guard repositoryStore.beginAccess(owner: repositoryAccessOwner) else { return }
        projectDir = url.path
    }

    private func deliveryTypeTitle(_ type: TaskOrchestrationViewModel.DeliveryTaskType) -> String {
        switch type {
        case .functional:
            return appPreferences.text("tasks.deliveryType.functional")
        case .artifact:
            return appPreferences.text("tasks.deliveryType.artifact")
        }
    }

    private func deliveryTypeSubtitle(_ type: TaskOrchestrationViewModel.DeliveryTaskType) -> String {
        switch type {
        case .functional:
            return appPreferences.text("tasks.deliveryType.functional.subtitle")
        case .artifact:
            return appPreferences.text("tasks.deliveryType.artifact.subtitle")
        }
    }

    private func submitTask() {
        guard missingSubmitRequirements.isEmpty else {
            viewModel.errorMessage = submitHelpText
            return
        }

        let taskTypes = selectedTaskTypeValues
        let subtaskAgentIds = selectedSubtaskAgentIds

        Task {
            if let errorMessage = await settingsVM.ensureTaskSubmissionReady(
                ownerAgentId: selectedOwnerAgent,
                subtaskAgentIds: subtaskAgentIds
            ) {
                await MainActor.run {
                    viewModel.errorMessage = errorMessage
                }
                return
            }

            await MainActor.run {
                viewModel.submitTask(
                    description: trimmedTaskDescription,
                    taskTypes: taskTypes,
                    ownerAgent: selectedOwnerAgent,
                    allowedSubtaskAgents: subtaskAgentIds,
                    projectDir: trimmedProjectDir,
                    strictDependency: strictDependency
                )
            }
        }
    }

    private var capabilityPreflightSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Image(systemName: "sparkles.rectangle.stack")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundColor(AcrossTheme.accent)
                Text(appPreferences.text("tasks.capabilityPreflight"))
                    .font(.system(size: 12, weight: .bold))
                    .foregroundColor(theme.primaryText)
                Spacer()
                if isPreflightingCapabilities {
                    ProgressView()
                        .controlSize(.mini)
                        .scaleEffect(0.65)
                }
            }

            if let capabilityPreflight, let best = capabilityPreflight.bestSummary {
                HStack(alignment: .top, spacing: 10) {
                    AgentIdentityBadge(agentId: best.agentId, ownerAgentId: nil, size: 24)
                    VStack(alignment: .leading, spacing: 4) {
                        Text(String(format: appPreferences.text("tasks.capabilityPreflight.recommended"), displayAgentName(best.agentId)))
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(theme.primaryText)
                            .lineLimit(1)
                        Text(preflightMatchedSkillText(best))
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                            .lineLimit(2)
                        if !best.matchedNativeSkillIds.isEmpty {
                            Text(preflightNativeSkillText(best))
                                .font(.system(size: 11))
                                .foregroundColor(AcrossTheme.accent)
                                .lineLimit(2)
                        }
                        if !best.routingEvidence.isEmpty {
                            Text(preflightRoutingEvidenceText(best))
                                .font(.system(size: 11))
                                .foregroundColor(.secondary)
                                .lineLimit(2)
                        }
                    }
                    Spacer()
                    Text("\(best.score)")
                        .font(.system(size: 11, weight: .bold, design: .rounded))
                        .foregroundColor(AcrossTheme.accent)
                        .frame(width: 26, height: 22)
                        .background(AcrossTheme.accent.opacity(0.16))
                        .clipShape(RoundedRectangle(cornerRadius: 7))
                }

                if !best.nativeSkillRepairSuggestions.isEmpty {
                    Text(preflightRepairText(best))
                        .font(.system(size: 11))
                        .foregroundColor(.orange)
                        .fixedSize(horizontal: false, vertical: true)
                }

                if !best.warnings.isEmpty {
                    Text(best.warnings.joined(separator: " "))
                        .font(.system(size: 11))
                        .foregroundColor(.orange)
                        .fixedSize(horizontal: false, vertical: true)
                }

                if !capabilityPreflight.warnings.isEmpty {
                    Text(capabilityPreflight.warnings.joined(separator: " "))
                        .font(.system(size: 11))
                        .foregroundColor(.orange)
                        .fixedSize(horizontal: false, vertical: true)
                }
            } else if let capabilityPreflightError {
                Text(capabilityPreflightError)
                    .font(.system(size: 11))
                    .foregroundColor(Color(hex: "#FF453A"))
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                Text(appPreferences.text("tasks.capabilityPreflight.empty"))
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            }
        }
        .padding(10)
        .background(theme.fieldBackground)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(theme.divider, lineWidth: 1)
        )
    }

    private func refreshCapabilityPreflight() async {
        guard !trimmedTaskDescription.isEmpty, !selectedTaskTypeValues.isEmpty else {
            await MainActor.run {
                capabilityPreflight = nil
                capabilityPreflightError = nil
                isPreflightingCapabilities = false
            }
            return
        }

        try? await Task.sleep(nanoseconds: 450_000_000)
        guard !Task.isCancelled else { return }

        await MainActor.run {
            isPreflightingCapabilities = true
            capabilityPreflightError = nil
        }

        do {
            guard let url = URL(string: "http://backend/api/agent-capabilities/preflight") else {
                return
            }
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(
                AgentCapabilityPreflightRequest(
                    description: trimmedTaskDescription,
                    ownerAgent: selectedOwnerAgent,
                    allowedSubtaskAgents: selectedSubtaskAgentIds,
                    taskTypes: selectedTaskTypeValues
                )
            )

            let (data, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse,
                  (200...299).contains(httpResponse.statusCode) else {
                throw URLError(.badServerResponse)
            }
            let decoded = try JSONDecoder().decode(AgentCapabilityPreflightResponse.self, from: data)
            await MainActor.run {
                capabilityPreflight = decoded
                isPreflightingCapabilities = false
            }
        } catch {
            await MainActor.run {
                capabilityPreflight = nil
                capabilityPreflightError = error.localizedDescription
                isPreflightingCapabilities = false
            }
        }
    }

    private func preflightMatchedSkillText(_ summary: AgentCapabilityPreflightAgentSummary) -> String {
        guard !summary.matchedSkillIds.isEmpty else {
            return appPreferences.text("tasks.capabilityPreflight.noMatch")
        }
        let names = summary.matchedSkillIds.prefix(3).map(preflightSkillName)
        return String(format: appPreferences.text("tasks.capabilityPreflight.matched"), names.joined(separator: ", "))
    }

    private func preflightNativeSkillText(_ summary: AgentCapabilityPreflightAgentSummary) -> String {
        let names = summary.matchedNativeSkillIds.prefix(3).map(preflightSkillName)
        return String(format: appPreferences.text("tasks.capabilityPreflight.nativeMatched"), names.joined(separator: ", "))
    }

    private func preflightRepairText(_ summary: AgentCapabilityPreflightAgentSummary) -> String {
        let suggestions = summary.nativeSkillRepairSuggestions.prefix(2).joined(separator: " ")
        return String(format: appPreferences.text("tasks.capabilityPreflight.repair"), suggestions)
    }

    private func preflightRoutingEvidenceText(_ summary: AgentCapabilityPreflightAgentSummary) -> String {
        let items = summary.routingEvidence.prefix(3).map(preflightRoutingEvidenceItemText)
        return String(format: appPreferences.text("tasks.capabilityPreflight.routingEvidence"), items.joined(separator: ", "))
    }

    private func preflightRoutingEvidenceItemText(_ evidence: AgentCapabilityRoutingEvidence) -> String {
        let trimmedSkillName = evidence.skillName?.trimmingCharacters(in: .whitespacesAndNewlines)
        let name: String
        if let trimmedSkillName, !trimmedSkillName.isEmpty {
            name = trimmedSkillName
        } else {
            name = preflightSkillName(evidence.skillId ?? evidence.source ?? "")
        }
        let status = evidence.status?
            .replacingOccurrences(of: "_", with: " ")
            .replacingOccurrences(of: "-", with: " ")
        if let status, !status.isEmpty {
            return "\(name) \(status)"
        }
        if let reason = evidence.reason, !reason.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return "\(name): \(reason.replacingOccurrences(of: "_", with: " "))"
        }
        return name
    }

    private func preflightSkillName(_ skillId: String) -> String {
        let key = "capabilities.skill.\(skillId).name"
        let value = appPreferences.text(key)
        return value == key
            ? skillId
                .replacingOccurrences(of: "_", with: " ")
                .replacingOccurrences(of: "-", with: " ")
            : value
    }

    private func displayAgentName(_ agentId: String) -> String {
        let normalized = AgentIDs.normalized(agentId) ?? agentId
        if let local = settingsVM.localAgents.first(where: { (AgentIDs.normalized($0.id) ?? $0.id) == normalized }) {
            return local.name
        }
        if let cloud = settingsVM.cloudLLMs.first(where: { $0.id == normalized }) {
            return cloud.name
        }
        return normalized
    }
}
