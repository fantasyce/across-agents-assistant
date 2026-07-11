import SwiftUI

struct WorkspaceOperationsView: View {
    @ObservedObject var operations: AgentWorkspaceOperationsViewModel
    @ObservedObject var preferences: AppPreferences
    let activeProjectPath: String?
    let onOpenReviewQueue: () -> Void

    @Environment(\.colorScheme) private var colorScheme
    @State private var selectedPane: WorkspacePaneKind = .output
    @State private var showsCreateSheet = false
    @ObservedObject private var repositoryStore = SecurityScopedRepositoryStore.shared

    var body: some View {
        VStack(spacing: 0) {
            commandBar
            Rectangle().fill(AcrossTheme.separator(for: colorScheme)).frame(height: 1)
            statusBanner
            content
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(AcrossTheme.canvasFill(for: colorScheme))
        .task(id: activeProjectPath) {
            await loadAuthorizedWorkspace()
        }
        .task(id: operations.pollingIdentity) {
            guard operations.selectedWorkspaceId != nil else { return }
            await operations.pollSelectedWorkspaceUntilStable()
        }
        .onChange(of: operations.workspace?.cleanup?.status) {
            if operations.workspace?.cleanup?.status == "completed" {
                repositoryStore.endAccess(owner: "workspace-lifecycle")
                operations.configureRepositoryAccess(nil)
            }
        }
        .sheet(isPresented: $showsCreateSheet) {
            WorkspaceCreateView(
                operations: operations,
                preferences: preferences,
                repositoryStore: repositoryStore
            )
                .environmentObject(preferences)
        }
    }

    private var commandBar: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(preferences.text("workspace.title"))
                    .font(.system(size: 16, weight: .semibold))
                Text(preferences.text("workspace.subtitle"))
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if let workspace = operations.workspace {
                StatusChip(status: workspace.status)
            } else if let readiness = operations.readiness {
                StatusChip(status: readiness.canCreateWorkspace ? "ready" : readiness.status.rawValue)
            }
            CommandToolbarButton(
                systemName: "person.crop.circle.badge.exclamationmark",
                accessibilityLabel: preferences.text("workspace.openReviewQueue"),
                help: preferences.text("workspace.openReviewQueue")
            ) {
                onOpenReviewQueue()
            }
            CommandToolbarButton(
                systemName: "arrow.clockwise",
                accessibilityLabel: preferences.text("workspace.refresh"),
                help: preferences.text("workspace.refresh"),
                isDisabled: operations.isLoading || operations.isPerformingAction
            ) {
                Task { await loadAuthorizedWorkspace(refreshReadiness: true) }
            }
            Button(preferences.text("workspace.start")) {
                showsCreateSheet = true
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.small)
            .disabled(operations.isPerformingAction)
            .keyboardShortcut("n", modifiers: [.command, .shift])
            .help(
                operations.readiness?.canCreateWorkspace == true
                    ? preferences.text("workspace.startHelp")
                    : preferences.text("workspace.startUnavailable")
            )
            .accessibilityHint(
                Text(
                    operations.readiness?.canCreateWorkspace == true
                        ? preferences.text("workspace.startHelp")
                        : preferences.text("workspace.startUnavailable")
                )
            )
        }
        .padding(.horizontal, 18)
        .frame(height: 58)
        .background(AcrossTheme.panelFill(for: colorScheme))
    }

    @ViewBuilder
    private var statusBanner: some View {
        if let error = operations.errorMessage {
            HStack(spacing: 8) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundStyle(StatusPalette.tone(for: "error").foreground)
                    .accessibilityHidden(true)
                Text(error)
                    .font(.system(size: 11))
                    .lineLimit(2)
                Spacer()
            }
            .padding(.horizontal, 16)
            .frame(minHeight: 34)
            .background(StatusPalette.tone(for: "error").foreground.opacity(0.1))
            .accessibilityElement(children: .combine)
        } else if let message = operations.actionMessage {
            HStack(spacing: 8) {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(StatusPalette.tone(for: "success").foreground)
                    .accessibilityHidden(true)
                Text(message).font(.system(size: 11))
                Spacer()
            }
            .padding(.horizontal, 16)
            .frame(minHeight: 34)
            .background(StatusPalette.tone(for: "success").foreground.opacity(0.1))
            .accessibilityElement(children: .combine)
        }
    }

    @ViewBuilder
    private var content: some View {
        if operations.isLoading && operations.readiness == nil && operations.workspaces.isEmpty {
            OperationalContentStateView(state: .loading, title: preferences.text("workspace.loading"))
        } else if operations.readiness == nil && operations.workspaces.isEmpty, let error = operations.errorMessage {
            OperationalContentStateView(
                state: .error(error),
                title: preferences.text("workspace.loadFailed"),
                retryTitle: preferences.text("system.retry")
            ) {
                Task { await loadAuthorizedWorkspace(refreshReadiness: true) }
            }
        } else if operations.workspaces.isEmpty {
            emptyWorkspaceState
        } else {
            workbench
        }
    }

    private var emptyWorkspaceState: some View {
        VStack(spacing: 16) {
            if let readiness = operations.readiness {
                workspaceMetrics(readiness: readiness, workspace: nil)
                    .padding(.horizontal, 16)
                if readiness.canCreateWorkspace {
                    OperationalContentStateView(
                        state: .disabled(preferences.text("workspace.noRuns.detail")),
                        title: preferences.text("workspace.noRuns")
                    )
                } else {
                    OperationalContentStateView(
                        state: .disabled(readiness.readinessIssues.joined(separator: ", ")),
                        title: preferences.text("workspace.unavailable")
                    )
                }
            } else {
                OperationalContentStateView(state: .empty, title: preferences.text("workspace.empty"))
            }
        }
        .padding(.vertical, 16)
    }

    private var workbench: some View {
        VStack(spacing: 0) {
            if let readiness = operations.readiness {
                workspaceMetrics(readiness: readiness, workspace: operations.workspace)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 12)
                Rectangle().fill(AcrossTheme.separator(for: colorScheme)).frame(height: 1)
            }
            HSplitView {
                workspaceList
                    .frame(minWidth: 210, idealWidth: 240, maxWidth: 290)
                WorkspaceCandidatePanes(
                    operations: operations,
                    preferences: preferences,
                    selectedPane: $selectedPane,
                    onOpenReviewQueue: onOpenReviewQueue
                )
                .frame(minWidth: 520, maxWidth: .infinity)
            }
        }
    }

    private var workspaceList: some View {
        VStack(spacing: 0) {
            HStack {
                Text(preferences.text("workspace.runs"))
                    .font(.system(size: 11, weight: .semibold))
                Spacer()
                Text("\(operations.workspaces.count)")
                    .font(.system(size: 10, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }
            .padding(.horizontal, 12)
            .frame(height: 44)
            .overlay(alignment: .bottom) {
                Rectangle().fill(AcrossTheme.separator(for: colorScheme)).frame(height: 1)
            }

            ScrollView {
                LazyVStack(spacing: 2) {
                    ForEach(operations.workspaces) { workspace in
                        Button {
                            Task {
                                do {
                                    try await operations.selectWorkspace(workspace.workspaceId)
                                } catch {
                                    operations.errorMessage = error.localizedDescription
                                }
                            }
                        } label: {
                            VStack(alignment: .leading, spacing: 6) {
                                HStack(spacing: 7) {
                                    Image(systemName: "square.3.layers.3d")
                                        .font(.system(size: 11, weight: .semibold))
                                        .foregroundStyle(StatusPalette.tone(for: workspace.status).foreground)
                                        .accessibilityHidden(true)
                                    Text(workspace.workflow ?? preferences.text("workspace.defaultWorkflow"))
                                        .font(.system(size: 11, weight: .semibold))
                                        .lineLimit(1)
                                    Spacer()
                                    StatusChip(status: workspace.status, label: "")
                                        .accessibilityHidden(true)
                                }
                                Text(workspace.repoRoot)
                                    .font(.system(size: 9, design: .monospaced))
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                                    .truncationMode(.middle)
                                HStack {
                                    Text(String(format: preferences.text("workspace.candidateCount"), workspace.candidates.count))
                                    Spacer()
                                    Text(String(workspace.workspaceId.suffix(8)))
                                }
                                .font(.system(size: 9))
                                .foregroundStyle(.secondary)
                            }
                            .padding(10)
                            .frame(maxWidth: .infinity, minHeight: 68, alignment: .leading)
                            .background(
                                operations.selectedWorkspaceId == workspace.workspaceId
                                    ? AcrossTheme.selectedFill(for: colorScheme)
                                    : Color.clear
                            )
                            .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.controlCornerRadius))
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel(Text(workspace.workflow ?? workspace.workspaceId))
                        .accessibilityValue(Text(StatusPalette.displayText(for: workspace.status)))
                        .padding(.horizontal, 6)
                    }
                }
                .padding(.vertical, 6)
            }
        }
        .background(AcrossTheme.panelFill(for: colorScheme))
    }

    private func workspaceMetrics(
        readiness: AgentWorkspaceReadinessSnapshot,
        workspace: AgentWorkspaceState?
    ) -> some View {
        let candidates = workspace?.candidates ?? []
        let changedFiles = candidates.reduce(0) { $0 + $1.comparison.changedFiles.count }
        let completed = candidates.filter { $0.status == "completed" }.count
        return LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: 8)], spacing: 8) {
            MetricTile(
                title: preferences.text("workspace.metric.agents"),
                value: workspace.map { "\($0.agentIds.count)" } ?? "\(readiness.readyAgentIds.count)/\(readiness.agents.count)",
                detail: preferences.text("workspace.metric.ready"),
                status: readiness.readyAgentIds.isEmpty ? "unavailable" : "ready",
                systemName: "person.2"
            )
            MetricTile(
                title: preferences.text("workspace.metric.candidates"),
                value: workspace.map { "\(completed)/\($0.candidates.count)" } ?? "-",
                detail: preferences.text("workspace.metric.completed"),
                status: workspace?.status ?? readiness.status.rawValue,
                systemName: "square.stack.3d.up"
            )
            MetricTile(
                title: preferences.text("workspace.metric.changes"),
                value: "\(changedFiles)",
                detail: preferences.text("workspace.metric.files"),
                status: changedFiles > 0 ? "ready" : "not_run",
                systemName: "arrow.triangle.branch"
            )
            MetricTile(
                title: preferences.text("workspace.metric.promotion"),
                value: StatusPalette.displayText(for: workspace?.promotion?.status),
                detail: preferences.text("workspace.metric.humanReview"),
                status: workspace?.promotion?.status ?? "not_run",
                systemName: "person.badge.shield.checkmark"
            )
        }
    }

    private func loadAuthorizedWorkspace(refreshReadiness: Bool = false) async {
        repositoryStore.restore()
        let path: String?
        if let selectedPath = repositoryStore.selectedPath,
           repositoryStore.beginAccess(owner: "workspace-lifecycle") {
            path = selectedPath
            operations.configureRepositoryAccess(repositoryStore.workspaceAccess)
        } else {
            path = nil
            operations.configureRepositoryAccess(nil)
        }
        await operations.load(activeProjectPath: path, refreshReadiness: refreshReadiness)
    }
}
