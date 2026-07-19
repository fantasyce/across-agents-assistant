import SwiftUI

struct MinimalProjectWorkspaceView: View {
    @ObservedObject private var operations: AgentWorkspaceOperationsViewModel
    @ObservedObject private var preferences: AppPreferences

    private let activeProjectPath: String?
    private let onOpenReviewQueue: () -> Void

    @ObservedObject private var repositoryStore = SecurityScopedRepositoryStore.shared
    @State private var selectedPane: WorkspacePaneKind = .output
    @State private var showsCreateSheet = false
    @State private var showsInspector = false
    @State private var reviewComment = ""
    @State private var selectedReviewAnchor: WorkspaceDiffLineAnchor?
    @State private var approvedBy = ""
    @State private var promotionConfirmed = false
    @State private var showsCancelConfirmation = false
    @State private var showsCleanupConfirmation = false
    @State private var showsChangedFiles = false
    @State private var showsDiff = false

    init(
        operations: AgentWorkspaceOperationsViewModel,
        preferences: AppPreferences,
        activeProjectPath: String?,
        onOpenReviewQueue: @escaping () -> Void
    ) {
        self.operations = operations
        self.preferences = preferences
        self.activeProjectPath = activeProjectPath
        self.onOpenReviewQueue = onOpenReviewQueue
    }

    var body: some View {
        VStack(spacing: 0) {
            MinimalPageHeader(
                title: preferences.text("workspace.title"),
                subtitle: repositoryStore.selectedPath
                    ?? (requiresRepositorySelection ? preferences.text("workspace.notConfigured") : activeProjectPath)
                    ?? preferences.text("workspace.subtitle")
            ) {
                if operations.workspace != nil {
                    MinimalIconButton(
                        systemName: "sidebar.right",
                        label: preferences.text("workspace.inspector"),
                        action: { showsInspector.toggle() }
                    )
                }
                MinimalIconButton(
                    systemName: "arrow.clockwise",
                    label: preferences.text("workspace.refresh"),
                    isDisabled: operations.isLoading || operations.isPerformingAction
                ) {
                    Task { await loadAuthorizedWorkspace(refreshReadiness: true) }
                }
                if requiresRepositorySelection || operations.readiness?.canCreateWorkspace == true {
                    Button(action: requiresRepositorySelection ? chooseRepository : { showsCreateSheet = true }) {
                        Label(
                            requiresRepositorySelection
                                ? preferences.text("workspace.create.chooseRepository")
                                : preferences.text("workspace.start"),
                            systemImage: requiresRepositorySelection ? "folder" : "plus"
                        )
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                    .disabled(operations.isPerformingAction)
                    .keyboardShortcut("n", modifiers: [.command, .shift])
                }
            }
            .minimalPageContentFrame(bottomPadding: 8)

            if let errorMessage = operations.errorMessage {
                MinimalNoticeBar(message: errorMessage, status: "error")
            } else if let actionMessage = operations.actionMessage {
                MinimalNoticeBar(message: actionMessage, status: "success")
            }

            content
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task(id: activeProjectPath) {
            await loadAuthorizedWorkspace()
        }
        .task(id: operations.pollingIdentity) {
            guard operations.selectedWorkspaceId != nil else { return }
            await operations.pollSelectedWorkspaceUntilStable()
        }
        .onChange(of: operations.selectedCandidateId) {
            reviewComment = ""
            selectedReviewAnchor = nil
            approvedBy = ""
            promotionConfirmed = false
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
        .confirmationDialog(
            preferences.text("workspace.cancelConfirmTitle"),
            isPresented: $showsCancelConfirmation,
            titleVisibility: .visible
        ) {
            Button(preferences.text("workspace.cancel"), role: .destructive) {
                Task { await operations.cancel() }
            }
            Button(preferences.text("system.cancel"), role: .cancel) {}
        } message: {
            Text(preferences.text("workspace.cancelConfirmMessage"))
        }
        .confirmationDialog(
            preferences.text("workspace.cleanupConfirmTitle"),
            isPresented: $showsCleanupConfirmation,
            titleVisibility: .visible
        ) {
            Button(preferences.text("workspace.cleanup"), role: .destructive) {
                Task { await operations.cleanup() }
            }
            Button(preferences.text("system.cancel"), role: .cancel) {}
        } message: {
            Text(preferences.text("workspace.cleanupConfirmMessage"))
        }
    }

    @ViewBuilder
    private var content: some View {
        if operations.isLoading && operations.readiness == nil && operations.workspaces.isEmpty {
            MinimalWorkflowStateView(
                state: .loading,
                title: preferences.text("workspace.loading")
            )
        } else if operations.readiness == nil && operations.workspaces.isEmpty,
                  let errorMessage = operations.errorMessage {
            MinimalWorkflowStateView(
                state: .error,
                title: preferences.text("workspace.loadFailed"),
                detail: errorMessage,
                actionTitle: preferences.text("system.retry")
            ) {
                Task { await loadAuthorizedWorkspace(refreshReadiness: true) }
            }
        } else if operations.workspaces.isEmpty {
            MinimalWorkflowStateView(
                state: requiresRepositorySelection || operations.readiness?.canCreateWorkspace == true
                    ? .empty
                    : .unavailable,
                title: requiresRepositorySelection
                    ? preferences.text("workspace.repositoryRequired.title")
                    : operations.readiness?.canCreateWorkspace == true
                        ? preferences.text("workspace.noRuns")
                        : preferences.text("workspace.notReady.title"),
                detail: requiresRepositorySelection
                    ? preferences.text("workspace.repositoryRequired.detail")
                    : operations.readiness?.readinessIssues
                        .map(localizedReadinessIssue)
                        .joined(separator: "\n")
                        ?? preferences.text("workspace.noRuns.detail"),
                actionTitle: requiresRepositorySelection
                    ? preferences.text("workspace.create.chooseRepository")
                    : operations.readiness?.canCreateWorkspace == true
                        ? preferences.text("workspace.start")
                        : nil,
                action: requiresRepositorySelection
                    ? chooseRepository
                    : operations.readiness?.canCreateWorkspace == true
                        ? { showsCreateSheet = true }
                        : nil
            )
        } else {
            workspaceSplitView
        }
    }

    private var workspaceSplitView: some View {
        HSplitView {
            List(selection: workspaceSelection) {
                Section(preferences.text("workspace.runs")) {
                    ForEach(operations.workspaces) { workspace in
                        workspaceRow(workspace)
                            .tag(workspace.workspaceId)
                    }
                }
            }
            .listStyle(.inset)
            .frame(minWidth: 180, idealWidth: 220, maxWidth: 280)

            candidateList
                .frame(minWidth: 160, idealWidth: 200, maxWidth: 260)

            candidateDetail
                .frame(minWidth: 420, maxWidth: .infinity)
                .inspector(isPresented: $showsInspector) {
                    workspaceInspector
                        .inspectorColumnWidth(min: 220, ideal: 260, max: 320)
                }
        }
    }

    private var workspaceSelection: Binding<String?> {
        Binding(
            get: { operations.selectedWorkspaceId },
            set: { workspaceId in
                guard let workspaceId, workspaceId != operations.selectedWorkspaceId else { return }
                Task {
                    do {
                        try await operations.selectWorkspace(workspaceId)
                    } catch {
                        operations.errorMessage = error.localizedDescription
                    }
                }
            }
        )
    }

    private var candidateSelection: Binding<String?> {
        Binding(
            get: { operations.selectedCandidateId },
            set: { operations.selectedCandidateId = $0 }
        )
    }

    private func workspaceRow(_ workspace: AgentWorkspaceState) -> some View {
        HStack(alignment: .top, spacing: 9) {
            Image(systemName: StatusPalette.systemImage(for: workspace.status))
                .foregroundStyle(StatusPalette.tone(for: workspace.status).foreground)
                .frame(width: 16)
                .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: 2) {
                Text(workspace.workflow ?? preferences.text("workspace.defaultWorkflow"))
                    .font(.body)
                    .lineLimit(1)
                Text(workspace.repoRoot)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
        }
        .padding(.vertical, 3)
        .accessibilityElement(children: .combine)
        .accessibilityValue(Text(preferences.statusText(workspace.status)))
    }

    @ViewBuilder
    private var candidateList: some View {
        if let workspace = operations.workspace {
            List(selection: candidateSelection) {
                Section {
                    MinimalKeyValueRow(
                        preferences.text("workspace.inspector.path"),
                        value: workspace.repoRoot,
                        monospaced: true
                    )
                    MinimalKeyValueRow(
                        preferences.text("workspace.inspector.strategy"),
                        value: workspace.executionStrategy ?? "-"
                    )
                }

                Section(String(format: preferences.text("workspace.candidateCount"), workspace.candidates.count)) {
                    ForEach(workspace.candidates) { candidate in
                        HStack(spacing: 9) {
                            AgentIdentityBadge(
                                agentId: candidate.agentId,
                                ownerAgentId: nil,
                                size: 22,
                                status: candidate.status
                            )
                            VStack(alignment: .leading, spacing: 2) {
                                Text(candidate.agentId)
                                    .lineLimit(1)
                                Text(String(format: preferences.text("workspace.attempt"), candidate.attempt))
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            Image(systemName: StatusPalette.systemImage(for: candidate.status))
                                .foregroundStyle(StatusPalette.tone(for: candidate.status).foreground)
                                .accessibilityHidden(true)
                        }
                        .tag(candidate.candidateId)
                        .accessibilityElement(children: .combine)
                        .accessibilityValue(Text(preferences.statusText(candidate.status)))
                    }
                }
            }
            .listStyle(.sidebar)
        } else {
            MinimalWorkflowStateView(
                state: .loading,
                title: preferences.text("workspace.loading")
            )
        }
    }

    @ViewBuilder
    private var candidateDetail: some View {
        if let candidate = operations.selectedCandidate {
            VStack(spacing: 0) {
                HStack(spacing: 10) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(candidate.agentId)
                            .font(.headline)
                        Text(candidate.candidateId)
                            .font(.caption.monospaced())
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }
                    Spacer()
                    MinimalWorkflowStatusLabel(status: candidate.status)
                    if operations.workspace?.canCancel == true {
                        Button(role: .destructive) {
                            showsCancelConfirmation = true
                        } label: {
                            Image(systemName: "stop.circle")
                        }
                        .buttonStyle(.borderless)
                        .disabled(operations.isPerformingAction)
                        .help(preferences.text("workspace.cancelHelp"))
                        .accessibilityLabel(Text(preferences.text("workspace.cancel")))
                    }
                }
                .padding(.horizontal, 16)
                .frame(minHeight: 52)

                Divider()

                Picker("", selection: $selectedPane) {
                    ForEach(WorkspacePaneKind.allCases) { pane in
                        Label(preferences.text(pane.localizationKey), systemImage: pane.systemName)
                            .tag(pane)
                    }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .padding(12)

                Divider()

                paneContent(candidate)
            }
        } else {
            MinimalWorkflowStateView(
                state: .empty,
                title: preferences.text("workspace.noCandidateSelected")
            )
        }
    }

    @ViewBuilder
    private func paneContent(_ candidate: AgentWorkspaceCandidate) -> some View {
        switch selectedPane {
        case .output:
            outputPane(candidate)
        case .toolCalls:
            toolCallsPane(candidate)
        case .changes:
            changesPane(candidate)
        case .providerUsage:
            providerPane(candidate)
        case .evidence:
            evidencePane(candidate)
        case .approval:
            approvalPane(candidate)
        }
    }

    private func outputPane(_ candidate: AgentWorkspaceCandidate) -> some View {
        let events = operations.events(for: candidate.candidateId)
        return Group {
            if events.isEmpty {
                MinimalWorkflowStateView(
                    state: candidate.status == "running" ? .loading : .empty,
                    title: preferences.text("workspace.output.empty")
                )
            } else {
                List(events) { event in
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text("#\(event.sequence)  \(event.type)")
                                .font(.caption.monospaced().weight(.semibold))
                            Spacer()
                            if let timestamp = event.timestamp {
                                Text(timestamp)
                                    .font(.caption2.monospaced())
                                    .foregroundStyle(.secondary)
                            }
                        }
                        if !event.boundedSummary.isEmpty {
                            Text(event.boundedSummary)
                                .font(.caption.monospaced())
                                .foregroundStyle(.secondary)
                                .textSelection(.enabled)
                        }
                    }
                    .padding(.vertical, 3)
                }
                .listStyle(.inset)
            }
        }
    }

    private func toolCallsPane(_ candidate: AgentWorkspaceCandidate) -> some View {
        let tools = candidate.run?.toolCalls ?? []
        return Group {
            if tools.isEmpty {
                MinimalWorkflowStateView(
                    state: candidate.status == "running" ? .loading : .empty,
                    title: preferences.text("workspace.tools.empty")
                )
            } else {
                List(Array(tools.prefix(100).enumerated()), id: \.offset) { index, tool in
                    Label {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(tool)
                                .font(.body.monospaced())
                            Text(String(format: preferences.text("workspace.tool.index"), index + 1))
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    } icon: {
                        Image(systemName: "wrench.and.screwdriver")
                            .foregroundStyle(.secondary)
                    }
                }
                .listStyle(.inset)
            }
        }
    }

    private func changesPane(_ candidate: AgentWorkspaceCandidate) -> some View {
        let comparison = operations.selectedComparisonCandidate?.comparison ?? candidate.comparison
        let diffText = operations.selectedComparisonCandidate?.diff
        return ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                MinimalSectionHeader(
                    preferences.text("workspace.pane.changes"),
                    detail: "+\(comparison.diff.insertions) / -\(comparison.diff.deletions)"
                )
                MinimalKeyValueRow(
                    preferences.text("workspace.changes.files"),
                    value: "\(comparison.diff.filesChanged)"
                )
                MinimalKeyValueRow(
                    preferences.text("workspace.changes.tests"),
                    value: "\(comparison.tests.completedCount)/\(comparison.tests.configuredCount)"
                )
                MinimalKeyValueRow(
                    preferences.text("workspace.changes.risk"),
                    value: preferences.statusText(comparison.risk.level)
                )

                MinimalDisclosureSection(
                    title: preferences.text("workspace.changes.files"),
                    detail: "\(comparison.changedFiles.count)",
                    isExpanded: $showsChangedFiles
                ) {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(comparison.changedFiles, id: \.self) { path in
                            Label(path, systemImage: "doc")
                                .font(.caption.monospaced())
                                .textSelection(.enabled)
                        }
                    }
                }

                if let diffText, !diffText.isEmpty {
                    MinimalDisclosureSection(
                        title: preferences.text("workspace.changes.diff"),
                        isExpanded: $showsDiff
                    ) {
                        WorkspaceDiffReviewView(
                            files: WorkspaceUnifiedDiffParser.parse(diffText),
                            comments: operations.workspace?.lineReviewBatches
                                .filter { $0.candidateId == candidate.candidateId }
                                .flatMap(\.comments) ?? [],
                            canComment: candidate.canCommentAndRelaunch,
                            isSubmitting: operations.isPerformingAction,
                            selectedAnchor: $selectedReviewAnchor,
                            comment: $reviewComment,
                            preferences: preferences
                        ) {
                            Task {
                                if let selectedReviewAnchor {
                                    await operations.lineReviewAndRelaunch(
                                        reviewComment,
                                        location: selectedReviewAnchor
                                    )
                                }
                                if operations.errorMessage == nil {
                                    reviewComment = ""
                                    selectedReviewAnchor = nil
                                }
                            }
                        }
                    }
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func providerPane(_ candidate: AgentWorkspaceCandidate) -> some View {
        let operational = operations.readiness?.operationalStatus(for: candidate.agentId)
        return Form {
            Section(preferences.text("workspace.pane.provider")) {
                MinimalKeyValueRow(
                    preferences.text("workspace.provider.provider"),
                    value: candidate.run?.provider ?? operational?.provider.id ?? "-"
                )
                MinimalKeyValueRow(
                    preferences.text("workspace.provider.model"),
                    value: candidate.run?.model ?? operational?.model.id ?? "-"
                )
                MinimalKeyValueRow(
                    preferences.text("workspace.provider.account"),
                    value: operational?.account.displayName
                        ?? operational?.account.id
                        ?? candidate.run?.account?.displayName
                        ?? candidate.run?.account?.id
                        ?? "-"
                )
            }

            Section {
                MinimalKeyValueRow(
                    preferences.text("workspace.provider.inputTokens"),
                    value: candidate.run?.usage?.inputTokens.map(String.init) ?? "-"
                )
                MinimalKeyValueRow(
                    preferences.text("workspace.provider.outputTokens"),
                    value: candidate.run?.usage?.outputTokens.map(String.init) ?? "-"
                )
                MinimalKeyValueRow(
                    preferences.text("workspace.provider.totalTokens"),
                    value: candidate.run?.usage?.totalTokens.map(String.init) ?? "-"
                )
                MinimalKeyValueRow(
                    preferences.text("workspace.provider.elapsed"),
                    value: candidate.run?.elapsedSeconds.map { String(format: "%.2fs", $0) } ?? "-"
                )
            }
        }
        .formStyle(.grouped)
    }

    private func evidencePane(_ candidate: AgentWorkspaceCandidate) -> some View {
        let comparison = operations.selectedComparisonCandidate?.comparison ?? candidate.comparison
        let evidence = operations.selectedComparisonCandidate?.evidence ?? candidate.evidence
        return List {
            Section(preferences.text("workspace.evidence.title")) {
                evidenceRow(preferences.text("workspace.approval.diff"), passed: evidence.diffValidated)
                evidenceRow(preferences.text("workspace.approval.tests"), passed: evidence.testsValidated)
                evidenceRow(preferences.text("workspace.evidence.gate"), passed: evidence.qualityGateValidated)
                evidenceRow(preferences.text("workspace.evidence.risk"), passed: evidence.riskValidated)
                evidenceRow(preferences.text("workspace.approval.conflicts"), passed: evidence.conflictsValidated)
            }

            if !evidence.blockingReasons.isEmpty {
                Section(preferences.text("workspace.evidence.blockers")) {
                    ForEach(evidence.blockingReasons, id: \.self) { reason in
                        Label(reason, systemImage: "exclamationmark.octagon")
                            .foregroundStyle(StatusPalette.tone(for: "blocked").foreground)
                    }
                }
            }

            Section(preferences.text("workspace.evidence.qualityGate")) {
                MinimalKeyValueRow(
                    "verdict",
                    value: comparison.qualityGate.gateVerdict ?? comparison.qualityGate.status
                )
                ForEach(comparison.qualityGate.findings) { finding in
                    Label(finding.summary ?? finding.id, systemImage: StatusPalette.systemImage(for: finding.state))
                        .foregroundStyle(StatusPalette.tone(for: finding.state).foreground)
                }
                ForEach(comparison.qualityGate.evidenceRoutes, id: \.self) { route in
                    Text(route)
                        .font(.caption.monospaced())
                        .textSelection(.enabled)
                }
            }

            if let links = candidate.run?.evidenceLinks, !links.isEmpty {
                Section(preferences.text("workspace.evidence.links")) {
                    ForEach(Array(links.prefix(100)), id: \.self) { link in
                        Text(link)
                            .font(.caption.monospaced())
                            .textSelection(.enabled)
                    }
                }
            }
        }
        .listStyle(.inset)
    }

    private func approvalPane(_ candidate: AgentWorkspaceCandidate) -> some View {
        let workspace = operations.workspace
        let isSelected = workspace?.selectedCandidateId == candidate.candidateId
        let canPromote = candidate.canSelect
            && isSelected
            && workspace?.promotion?.status != "promoted"

        return Form {
            Section(preferences.text("workspace.approval.title")) {
                evidenceRow(preferences.text("workspace.approval.diff"), passed: candidate.evidence.diffValidated)
                evidenceRow(preferences.text("workspace.approval.tests"), passed: candidate.evidence.testsValidated)
                evidenceRow(preferences.text("workspace.evidence.gate"), passed: candidate.evidence.qualityGateValidated)
                evidenceRow(preferences.text("workspace.approval.human"), passed: workspace?.promotion?.approved == true)
            }

            if candidate.canCommentAndRelaunch {
                Section(preferences.text("workspace.comment.title")) {
                    TextEditor(text: $reviewComment)
                        .font(.body)
                        .frame(minHeight: 76)
                        .accessibilityLabel(Text(preferences.text("workspace.comment.title")))
                    Button {
                        Task {
                            await operations.commentAndRelaunch(reviewComment)
                            if operations.errorMessage == nil { reviewComment = "" }
                        }
                    } label: {
                        Label(preferences.text("workspace.comment.relaunch"), systemImage: "arrow.clockwise.circle")
                    }
                    .disabled(
                        reviewComment.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                            || operations.isPerformingAction
                    )
                }
            }

            if candidate.canSelect && !isSelected {
                Section {
                    Button {
                        Task { await operations.selectCandidate() }
                    } label: {
                        Label(preferences.text("workspace.approval.select"), systemImage: "checkmark.circle")
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(operations.isPerformingAction)
                }
            }

            if isSelected {
                Section(preferences.text("workspace.approval.confirmTitle")) {
                    TextField(preferences.text("workspace.approval.identity"), text: $approvedBy)
                    Toggle(preferences.text("workspace.approval.confirm"), isOn: $promotionConfirmed)
                        .toggleStyle(.checkbox)
                    Button(role: .destructive) {
                        Task {
                            await operations.promote(
                                approvedBy: approvedBy,
                                confirmed: promotionConfirmed
                            )
                            if operations.errorMessage == nil { promotionConfirmed = false }
                        }
                    } label: {
                        Label(preferences.text("workspace.approval.promote"), systemImage: "arrow.up.circle.fill")
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(
                        !canPromote
                            || !promotionConfirmed
                            || approvedBy.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                            || operations.isPerformingAction
                    )
                }
            }

            Section {
                Button(preferences.text("workspace.openReviewQueue"), action: onOpenReviewQueue)
                if workspace?.canCleanup == true {
                    Button(role: .destructive) {
                        showsCleanupConfirmation = true
                    } label: {
                        Label(preferences.text("workspace.cleanup"), systemImage: "trash")
                    }
                    .disabled(operations.isPerformingAction)
                }
            }
        }
        .formStyle(.grouped)
    }

    private func evidenceRow(_ title: String, passed: Bool) -> some View {
        HStack {
            Label(
                title,
                systemImage: StatusPalette.systemImage(for: passed ? "passed" : "pending")
            )
            Spacer()
            Text(preferences.statusText(passed ? "passed" : "pending"))
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    private func localizedReadinessIssue(_ issue: String) -> String {
        switch issue {
        case "One or more host or request prerequisites are missing.":
            return preferences.text("workspace.readiness.hostPrerequisitesMissing")
        case "not_git_repository", "repository_not_ready":
            return preferences.text("workspace.readiness.notGitRepository")
        case "git_unavailable":
            return preferences.text("workspace.readiness.gitUnavailable")
        case "no_ready_agents":
            return preferences.text("workspace.readiness.noReadyAgents")
        default:
            let prefix = "selected_agent_"
            let suffix = "_unavailable"
            if issue.hasPrefix(prefix), issue.hasSuffix(suffix) {
                let agentID = issue
                    .dropFirst(prefix.count)
                    .dropLast(suffix.count)
                return String(
                    format: preferences.text("workspace.readiness.selectedAgentUnavailable"),
                    String(agentID)
                )
            }
            return issue.replacingOccurrences(of: "_", with: " ")
        }
    }

    @ViewBuilder
    private var workspaceInspector: some View {
        Form {
            if let workspace = operations.workspace {
                Section(preferences.text("workspace.inspector")) {
                    MinimalKeyValueRow(preferences.text("workspace.inspector.id"), value: workspace.workspaceId, monospaced: true)
                    MinimalKeyValueRow(
                        preferences.text("workspace.inspector.repository"),
                        value: workspace.repoRoot,
                        monospaced: true
                    )
                    MinimalKeyValueRow(preferences.text("workspace.inspector.branch"), value: workspace.baseBranch ?? "-")
                    MinimalKeyValueRow(preferences.text("workspace.inspector.baseSHA"), value: workspace.baseSha ?? "-", monospaced: true)
                    MinimalKeyValueRow(
                        preferences.text("workspace.inspector.strategy"),
                        value: workspace.executionStrategy ?? "-"
                    )
                }

                if let candidate = operations.selectedCandidate {
                    Section(preferences.text("workspace.inspector.agent")) {
                        MinimalKeyValueRow(
                            preferences.text("workspace.inspector.identity"),
                            value: candidate.agentId
                        )
                        MinimalKeyValueRow(
                            preferences.text("workspace.provider.status"),
                            value: preferences.statusText(candidate.status)
                        )
                        MinimalKeyValueRow(
                            preferences.text("workspace.changes.files"),
                            value: "\(candidate.comparison.changedFiles.count)"
                        )
                        MinimalKeyValueRow(
                            preferences.text("workspace.changes.risk"),
                            value: preferences.statusText(candidate.comparison.risk.level)
                        )
                    }
                }

                if let readiness = operations.readiness, !readiness.readinessIssues.isEmpty {
                    Section(preferences.text("workspace.inspector.blockers")) {
                        ForEach(readiness.readinessIssues, id: \.self) { issue in
                            Text(issue)
                                .font(.caption)
                        }
                    }
                }
            } else {
                Text(preferences.text("workspace.empty"))
                    .foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
    }

    private func loadAuthorizedWorkspace(refreshReadiness: Bool = false) async {
        repositoryStore.restore()
        let path: String?
        if let selectedPath = repositoryStore.selectedPath,
           repositoryStore.beginAccess(owner: "workspace-lifecycle") {
            path = selectedPath
            operations.configureRepositoryAccess(repositoryStore.workspaceAccess)
        } else {
            path = activeProjectPath
            operations.configureRepositoryAccess(nil)
        }
        await operations.load(activeProjectPath: path, refreshReadiness: refreshReadiness)
    }

    private var requiresRepositorySelection: Bool {
        guard operations.workspaces.isEmpty else { return false }
        if operations.createDraft.repoRoot.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return true
        }
        return operations.readiness?.readinessIssues.contains {
            ["not_git_repository", "repository_not_ready"].contains($0)
        } == true
    }

    private func chooseRepository() {
        guard let url = repositoryStore.chooseRepository(
            title: preferences.text("workspace.create.chooseRepository"),
            message: preferences.text("workspace.create.repositoryPickerMessage"),
            prompt: preferences.text("workspace.create.chooseRepository")
        ) else { return }
        guard repositoryStore.beginAccess(owner: "workspace-lifecycle") else { return }
        operations.configureProjectPath(url.path)
        operations.configureRepositoryAccess(repositoryStore.workspaceAccess)
        Task { await operations.load(activeProjectPath: url.path, refreshReadiness: true) }
    }
}
