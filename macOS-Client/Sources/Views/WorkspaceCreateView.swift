import SwiftUI

struct WorkspaceCreateView: View {
    @ObservedObject var operations: AgentWorkspaceOperationsViewModel
    @ObservedObject var preferences: AppPreferences
    @ObservedObject var repositoryStore: SecurityScopedRepositoryStore

    @Environment(\.dismiss) private var dismiss
    @Environment(\.colorScheme) private var colorScheme
    @FocusState private var focusedField: Field?
    private let repositoryAccessOwner = "workspace-lifecycle"

    private enum Field { case prompt; case workflow }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(preferences.text("workspace.create.title"))
                        .font(.system(size: 16, weight: .semibold))
                    Text(preferences.text("workspace.create.subtitle"))
                        .font(.system(size: 11))
                        .foregroundStyle(.secondary)
                }
                Spacer()
                CommandToolbarButton(
                    systemName: "xmark",
                    accessibilityLabel: preferences.text("system.cancel"),
                    help: preferences.text("system.cancel")
                ) { dismiss() }
            }
            .padding(.horizontal, 18)
            .frame(height: 58)
            .background(AcrossTheme.panelFill(for: colorScheme))

            Rectangle().fill(AcrossTheme.separator(for: colorScheme)).frame(height: 1)

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    formField(preferences.text("workspace.create.repository")) {
                        repositorySelector
                    }

                    formField(preferences.text("workspace.create.prompt")) {
                        TextEditor(text: $operations.createDraft.prompt)
                            .font(.system(size: 12))
                            .scrollContentBackground(.hidden)
                            .padding(6)
                            .frame(minHeight: 110)
                            .background(AcrossTheme.recessedFill(for: colorScheme))
                            .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.controlCornerRadius))
                            .focused($focusedField, equals: .prompt)
                            .accessibilityLabel(Text(preferences.text("workspace.create.prompt")))
                    }

                    formField(preferences.text("workspace.create.agents")) {
                        VStack(spacing: 4) {
                            ForEach(operations.readiness?.agents ?? []) { agent in
                                Toggle(isOn: agentBinding(agent)) {
                                    HStack(spacing: 8) {
                                        AgentIdentityBadge(
                                            agentId: agent.agentId,
                                            ownerAgentId: nil,
                                            size: 22,
                                            status: agent.status.rawValue
                                        )
                                        VStack(alignment: .leading, spacing: 1) {
                                            Text(agent.displayName)
                                                .font(.system(size: 11, weight: .semibold))
                                            Text(agent.reason ?? agent.agentType ?? preferences.text("workspace.agent.local"))
                                                .font(.system(size: 9))
                                                .foregroundStyle(.secondary)
                                                .lineLimit(1)
                                        }
                                        Spacer()
                                        StatusChip(status: agent.status.rawValue)
                                    }
                                }
                                .toggleStyle(.checkbox)
                                .disabled(!agent.isUsable || (!operations.createDraft.selectedAgentIds.contains(agent.agentId) && operations.createDraft.selectedAgentIds.count >= 4))
                                .accessibilityHint(Text(preferences.text("workspace.create.agentLimit")))
                                .padding(.vertical, 4)
                            }
                        }
                    }

                    formField(preferences.text("workspace.create.workflow")) {
                        TextField(preferences.text("workspace.create.workflow"), text: $operations.createDraft.workflow)
                            .textFieldStyle(.roundedBorder)
                            .focused($focusedField, equals: .workflow)
                    }

                    formField(preferences.text("workspace.create.validation")) {
                        VStack(alignment: .leading, spacing: 6) {
                            ForEach(operations.createDraft.validationCommands, id: \.self) { command in
                                Label(command.joined(separator: " "), systemImage: "checkmark.shield")
                                    .font(.system(size: 10, design: .monospaced))
                            }
                            Text(preferences.text("workspace.create.validation.detail"))
                                .font(.system(size: 9))
                                .foregroundStyle(.secondary)
                        }
                    }

                    formField(preferences.text("workspace.create.qualityGate")) {
                        VStack(alignment: .leading, spacing: 9) {
                            TextField(preferences.text("workspace.create.ciPath"), text: $operations.createDraft.qualityGateCIPath)
                                .textFieldStyle(.roundedBorder)
                                .accessibilityLabel(Text(preferences.text("workspace.create.ciPath")))
                            Stepper(value: $operations.createDraft.qualityGateCIWaitSeconds, in: 0...900, step: 10) {
                                HStack {
                                    Text(preferences.text("workspace.create.ciWait"))
                                    Spacer()
                                    Text(String(format: preferences.text("workspace.create.seconds"), operations.createDraft.qualityGateCIWaitSeconds))
                                        .font(.system(size: 10, weight: .semibold, design: .rounded))
                                }
                            }
                            .accessibilityLabel(Text(preferences.text("workspace.create.ciWait")))
                            Toggle(preferences.text("workspace.create.draftPR"), isOn: $operations.createDraft.qualityGateDraftPR)
                                .toggleStyle(.checkbox)
                        }
                        .font(.system(size: 11))
                    }

                    if let validationError = operations.createDraft.validationError {
                        Label(validationError, systemImage: "exclamationmark.triangle")
                            .font(.system(size: 10))
                            .foregroundStyle(StatusPalette.tone(for: "attention").foreground)
                    }
                    if repositoryStore.state.requiresReselection {
                        Label(repositoryAccessMessage, systemImage: "folder.badge.questionmark")
                            .font(.system(size: 10))
                            .foregroundStyle(StatusPalette.tone(for: "attention").foreground)
                            .accessibilityLabel(Text(repositoryAccessMessage))
                    }
                    if let error = operations.errorMessage {
                        Label(error, systemImage: "xmark.octagon")
                            .font(.system(size: 10))
                            .foregroundStyle(StatusPalette.tone(for: "error").foreground)
                    }
                }
                .padding(18)
            }

            Rectangle().fill(AcrossTheme.separator(for: colorScheme)).frame(height: 1)
            HStack {
                Text(String(format: preferences.text("workspace.create.selectedCount"), operations.createDraft.selectedAgentIds.count))
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
                Spacer()
                Button(preferences.text("system.cancel")) { dismiss() }
                    .buttonStyle(.bordered)
                Button(preferences.text("workspace.start")) {
                    operations.configureRepositoryAccess(repositoryStore.workspaceAccess)
                    Task {
                        await operations.createWorkspace()
                        if operations.errorMessage == nil { dismiss() }
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(!operations.canCreateWorkspace || !repositoryStore.isAccessing)
                .keyboardShortcut(.defaultAction)
            }
            .padding(.horizontal, 18)
            .frame(height: 54)
            .background(AcrossTheme.panelFill(for: colorScheme))
        }
        .frame(minWidth: 620, idealWidth: 680, minHeight: 620, idealHeight: 680)
        .onAppear {
            repositoryStore.restore()
            if let path = repositoryStore.selectedPath, repositoryStore.beginAccess(owner: repositoryAccessOwner) {
                operations.configureProjectPath(path)
                operations.configureRepositoryAccess(repositoryStore.workspaceAccess)
            } else {
                operations.configureProjectPath(nil)
                operations.configureRepositoryAccess(nil)
            }
            focusedField = .prompt
        }
    }

    private var repositorySelector: some View {
        HStack(spacing: 8) {
            Text(operations.createDraft.repoRoot.isEmpty ? preferences.text("workspace.notConfigured") : operations.createDraft.repoRoot)
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(operations.createDraft.repoRoot.isEmpty ? .secondary : .primary)
                .lineLimit(1)
                .truncationMode(.middle)
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
            Button {
                guard let url = repositoryStore.chooseRepository(
                    title: preferences.text("workspace.create.chooseRepository"),
                    message: preferences.text("workspace.create.repositoryPickerMessage"),
                    prompt: preferences.text("workspace.create.chooseRepository")
                ) else { return }
                guard repositoryStore.beginAccess(owner: repositoryAccessOwner) else { return }
                operations.configureProjectPath(url.path)
                operations.configureRepositoryAccess(repositoryStore.workspaceAccess)
                Task { await operations.load(activeProjectPath: url.path, refreshReadiness: true) }
            } label: {
                Label(preferences.text("workspace.create.chooseRepository"), systemImage: "folder")
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .keyboardShortcut("o", modifiers: [.command])
            .accessibilityHint(Text(preferences.text("workspace.create.chooseRepositoryHint")))
        }
        .padding(8)
        .background(AcrossTheme.recessedFill(for: colorScheme))
        .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.controlCornerRadius))
    }

    private var repositoryAccessMessage: String {
        switch repositoryStore.state {
        case .stale:
            return preferences.text("workspace.create.repositoryStale")
        case .failed:
            return preferences.text("workspace.create.repositoryFailed")
        default:
            return preferences.text("workspace.create.chooseRepositoryHint")
        }
    }

    private func formField<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            Text(title)
                .font(.system(size: 11, weight: .semibold))
            content()
        }
    }

    private func agentBinding(_ agent: AgentWorkspaceAgentReadiness) -> Binding<Bool> {
        Binding(
            get: { operations.createDraft.selectedAgentIds.contains(agent.agentId) },
            set: { selected in
                if selected {
                    guard operations.createDraft.selectedAgentIds.count < 4 else { return }
                    operations.createDraft.selectedAgentIds.insert(agent.agentId)
                } else {
                    operations.createDraft.selectedAgentIds.remove(agent.agentId)
                }
            }
        )
    }
}
