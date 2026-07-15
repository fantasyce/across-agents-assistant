import AppKit
import SwiftUI

struct MinimalRunsOverviewView: View {
    @ObservedObject private var viewModel: TaskOrchestrationViewModel
    @ObservedObject private var qualityGate: QualityGateViewModel
    @ObservedObject private var settingsViewModel: SettingsViewModel
    @ObservedObject private var preferences: AppPreferences
    @Binding private var showsRunHistory: Bool

    private let defaultProjectPath: String?
    private let automaticallyLoads: Bool
    private let onOpenReviewQueue: () -> Void

    @State private var searchText = ""
    @State private var showsInspector = false
    @State private var destination: RunDestination = .home
    @State private var taskPendingCancellationID: String?
    @State private var showsReleaseE2EConfirmation = false
    @Environment(\.colorScheme) private var colorScheme

    init(
        viewModel: TaskOrchestrationViewModel,
        qualityGate: QualityGateViewModel,
        settingsViewModel: SettingsViewModel,
        preferences: AppPreferences,
        showsRunHistory: Binding<Bool>,
        defaultProjectPath: String? = nil,
        automaticallyLoads: Bool = true,
        onOpenReviewQueue: @escaping () -> Void
    ) {
        self.viewModel = viewModel
        self.qualityGate = qualityGate
        self.settingsViewModel = settingsViewModel
        self.preferences = preferences
        _showsRunHistory = showsRunHistory
        self.defaultProjectPath = defaultProjectPath
        self.automaticallyLoads = automaticallyLoads
        self.onOpenReviewQueue = onOpenReviewQueue
    }

    var body: some View {
        VStack(spacing: 0) {
            MinimalPageHeader(
                title: headerTitle,
                subtitle: destination == .home ? preferences.text("tasks.overview.subtitle") : nil,
                backLabel: destination == .home ? nil : preferences.text("tasks.overview.back"),
                onBack: { destination = .home }
            ) {
                headerActions
            }
            .minimalPageContentFrame(bottomPadding: 8)

            if let errorMessage = viewModel.errorMessage, !errorMessage.isEmpty {
                MinimalNoticeBar(message: errorMessage, status: "error")
            } else if let evidenceError = viewModel.taskEvidenceError, !evidenceError.isEmpty {
                MinimalNoticeBar(message: evidenceError, status: "error")
            } else if let exportedURL = viewModel.exportedEvidenceBundleURL {
                MinimalNoticeBar(
                    message: String(
                        format: preferences.text("tasks.evidence.exported"),
                        exportedURL.path
                    ),
                    status: "success"
                )
            }

            centerContent
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(AcrossTheme.canvasFill(for: colorScheme))
        .environmentObject(preferences)
        .task {
            if automaticallyLoads {
                viewModel.loadTasks()
            }
        }
        .onExitCommand {
            if showsRunHistory {
                setRunHistoryVisible(false)
            }
        }
        .sheet(item: $viewModel.selectedEvidenceBundle, onDismiss: {
            viewModel.closeEvidenceBundle()
        }) { bundle in
            TaskEvidenceBundleSheet(
                bundle: bundle,
                isLoading: viewModel.isLoadingTaskEvidence,
                errorMessage: viewModel.taskEvidenceError,
                exportedURL: viewModel.exportedEvidenceBundleURL,
                onExport: {
                    viewModel.exportTaskEvidenceBundle(
                        bundle.taskId,
                        releaseGate: bundle.usesReleaseE2EBenchmark
                    )
                },
                onOpenExport: {
                    if let url = viewModel.exportedEvidenceBundleURL {
                        NSWorkspace.shared.activateFileViewerSelecting([url])
                    }
                }
            )
            .environmentObject(preferences)
        }
        .confirmationDialog(
            preferences.text("tasks.cancelConfirmTitle"),
            isPresented: Binding(
                get: { taskPendingCancellationID != nil },
                set: { if !$0 { taskPendingCancellationID = nil } }
            ),
            titleVisibility: .visible
        ) {
            Button(preferences.text("tasks.cancel"), role: .destructive) {
                if let taskID = taskPendingCancellationID {
                    viewModel.cancelTask(taskID)
                }
                taskPendingCancellationID = nil
            }
            Button(preferences.text("system.cancel"), role: .cancel) {
                taskPendingCancellationID = nil
            }
        } message: {
            Text(preferences.text("tasks.cancelConfirmMessage"))
        }
        .confirmationDialog(
            preferences.text("tasks.releaseE2E.confirmTitle"),
            isPresented: $showsReleaseE2EConfirmation,
            titleVisibility: .visible
        ) {
            Button(preferences.text("tasks.releaseE2E.run")) {
                viewModel.startReleaseE2E()
            }
            Button(preferences.text("system.cancel"), role: .cancel) {}
        } message: {
            Text(preferences.text("tasks.releaseE2E.confirmMessage"))
        }
    }

    @ViewBuilder
    private var headerActions: some View {
        switch destination {
        case .home:
            MinimalIconButton(
                systemName: "clock.arrow.circlepath",
                label: preferences.text("tasks.sidebar"),
                action: { setRunHistoryVisible(true) }
            )
            MinimalIconButton(
                systemName: "arrow.clockwise",
                label: preferences.text("tasks.overview.refresh"),
                isDisabled: viewModel.isLoading
            ) {
                viewModel.loadTasks()
            }
            MinimalIconButton(
                systemName: "plus",
                label: preferences.text("tasks.new"),
                isDisabled: viewModel.isOrchestratorPluginUnavailable
            ) {
                destination = .tasks
                viewModel.enterWorkflowPicker()
            }
        case .tasks:
            if isShowingTaskDetail {
                MinimalIconButton(
                    systemName: "sidebar.right",
                    label: preferences.text("tasks.inspector"),
                    action: { showsInspector.toggle() }
                )
                MinimalIconButton(
                    systemName: "arrow.clockwise",
                    label: preferences.text("tasks.overview.refresh"),
                    isDisabled: viewModel.isLoading
                ) {
                    viewModel.loadTasks()
                }
            }
        case .quality:
            MinimalIconButton(
                systemName: "play.fill",
                label: preferences.text("gate.run"),
                isDisabled: qualityGate.draft.validationError != nil || qualityGate.isRunning
            ) {
                Task { await qualityGate.run() }
            }
        case .release:
            MinimalIconButton(
                systemName: "arrow.clockwise",
                label: preferences.text("tasks.releaseEvaluation.refresh"),
                isDisabled: viewModel.isLoadingReleaseEvaluation
            ) {
                viewModel.loadReleaseEvaluation()
            }
            MinimalIconButton(
                systemName: "checklist.checked",
                label: preferences.text("tasks.releaseE2E.run"),
                isDisabled: viewModel.isStartingReleaseE2E || viewModel.isOrchestratorPluginUnavailable
            ) {
                showsReleaseE2EConfirmation = true
            }
        }
    }

    private var headerTitle: String {
        switch destination {
        case .home: return preferences.text("tasks.overview.title")
        case .tasks: return preferences.text("tasks.overview.newTask")
        case .quality: return preferences.text("tasks.overview.quality")
        case .release: return preferences.text("tasks.overview.release")
        }
    }

    private var isShowingTaskDetail: Bool {
        if case .detail = viewModel.viewMode { return true }
        return false
    }

    @ViewBuilder
    private var centerContent: some View {
        switch destination {
        case .home:
            runOverview
        case .tasks:
            taskWorkspace
        case .quality:
            QualityGateOperationsView(
                operations: qualityGate,
                preferences: preferences,
                activeProjectPath: defaultProjectPath,
                onOpenFullWorkflow: { destination = .tasks },
                onOpenReviewQueue: onOpenReviewQueue,
                showsCommandBar: false
            )
        case .release:
            releaseOverview
        }
    }

    private var runOverview: some View {
        ZStack(alignment: .topLeading) {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    VStack(alignment: .leading, spacing: 5) {
                        Text(preferences.text("tasks.overview.prompt"))
                            .font(.title3.weight(.semibold))
                    }

                    VStack(spacing: 0) {
                        runActionRow(
                            title: preferences.text("tasks.overview.newTask"),
                            detail: preferences.text("tasks.overview.newTask.detail"),
                            systemName: "plus.circle"
                        ) {
                            destination = .tasks
                            viewModel.enterWorkflowPicker()
                        }
                        Divider().padding(.leading, 42)
                        runActionRow(
                            title: preferences.text("tasks.overview.quality"),
                            detail: preferences.text("tasks.overview.quality.detail"),
                            systemName: "checkmark.shield"
                        ) {
                            destination = .quality
                        }
                        Divider().padding(.leading, 42)
                        runActionRow(
                            title: preferences.text("tasks.overview.release"),
                            detail: preferences.text("tasks.overview.release.detail"),
                            systemName: "shippingbox"
                        ) {
                            destination = .release
                            viewModel.loadReleaseEvaluation()
                        }
                    }

                    Divider()

                    VStack(alignment: .leading, spacing: 6) {
                        MinimalSectionHeader(
                            preferences.text("tasks.overview.recent"),
                            detail: viewModel.tasks.isEmpty ? nil : "\(viewModel.tasks.count)"
                        )

                        if viewModel.isLoading && viewModel.tasks.isEmpty {
                            ProgressView()
                                .controlSize(.small)
                                .frame(maxWidth: .infinity, minHeight: 72)
                        } else if viewModel.tasks.isEmpty {
                            Text(preferences.text("tasks.overview.recent.empty"))
                                .font(.callout)
                                .foregroundStyle(.secondary)
                                .frame(maxWidth: .infinity, minHeight: 72, alignment: .leading)
                        } else {
                            ForEach(viewModel.tasks.prefix(6)) { task in
                                Button {
                                    destination = .tasks
                                    viewModel.selectTask(task.taskId)
                                } label: {
                                    runRow(task)
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                        .contentShape(Rectangle())
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                }
                .minimalPageContentFrame(topPadding: 12)
            }

            if showsRunHistory {
                Color.black.opacity(0.001)
                    .contentShape(Rectangle())
                    .onTapGesture { setRunHistoryVisible(false) }
                    .accessibilityHidden(true)

                runHistoryDrawer
                    .padding(10)
                    .transition(.move(edge: .leading).combined(with: .opacity))
                    .zIndex(1)
            }
        }
        .clipped()
    }

    private func runActionRow(
        title: String,
        detail: String,
        systemName: String,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            HStack(spacing: 14) {
                Image(systemName: systemName)
                    .font(.system(size: 16, weight: .medium))
                    .foregroundStyle(.secondary)
                    .frame(width: 28, height: 28)
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 3) {
                    Text(title)
                        .font(.body.weight(.medium))
                        .foregroundStyle(.primary)
                    Text(detail)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                Spacer(minLength: 16)
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.tertiary)
                    .accessibilityHidden(true)
            }
            .padding(.vertical, 14)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private var taskWorkspace: some View {
        ZStack(alignment: .topLeading) {
            runDetail
                .inspector(isPresented: $showsInspector) {
                    runInspector
                        .inspectorColumnWidth(min: 250, ideal: 290, max: 370)
                }

            if showsRunHistory {
                Color.black.opacity(0.001)
                    .contentShape(Rectangle())
                    .onTapGesture { setRunHistoryVisible(false) }
                    .accessibilityHidden(true)

                runHistoryDrawer
                    .padding(10)
                    .transition(.move(edge: .leading).combined(with: .opacity))
                    .zIndex(1)
            }
        }
        .clipped()
    }

    @ViewBuilder
    private var releaseOverview: some View {
        if viewModel.isLoadingReleaseEvaluation && viewModel.releaseEvaluation == nil {
            MinimalWorkflowStateView(
                state: .loading,
                title: preferences.text("tasks.releaseEvaluation.refresh")
            )
        } else if let error = viewModel.releaseEvaluationError,
                  viewModel.releaseEvaluation == nil {
            MinimalWorkflowStateView(
                state: .error,
                title: preferences.text("tasks.releaseEvaluation"),
                detail: error,
                actionTitle: preferences.text("system.retry")
            ) {
                viewModel.loadReleaseEvaluation()
            }
        } else if let summary = viewModel.releaseEvaluation {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    HStack(spacing: 0) {
                        releaseValue(
                            preferences.text("tasks.releaseEvaluation.readiness"),
                            preferences.statusText(summary.releaseReadiness)
                        )
                        Divider().frame(height: 38)
                        releaseValue(
                            preferences.text("tasks.releaseEvaluation.passRate"),
                            "\(summary.passRatePercent)%"
                        )
                        Divider().frame(height: 38)
                        releaseValue(
                            preferences.text("tasks.releaseEvaluation.score"),
                            summary.averageFinalQualityScore.map(String.init) ?? "-"
                        )
                        Divider().frame(height: 38)
                        releaseValue(
                            preferences.text("tasks.releaseEvaluation.evidence"),
                            "\(summary.releaseEvidenceCount)"
                        )
                    }

                    if let recommendation = summary.recommendation, !recommendation.isEmpty {
                        Text(recommendation)
                            .font(.callout)
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                    }

                    Divider()

                    VStack(alignment: .leading, spacing: 4) {
                        MinimalSectionHeader(
                            preferences.text("tasks.releaseCenter.checklist"),
                            detail: "\(summary.readinessChecks.count)"
                        )
                        ForEach(summary.readinessChecks.prefix(8)) { check in
                            HStack(spacing: 10) {
                                Image(systemName: StatusPalette.systemImage(for: check.status))
                                    .foregroundStyle(StatusPalette.tone(for: check.status).foreground)
                                    .accessibilityHidden(true)
                                Text(check.label)
                                    .lineLimit(1)
                                Spacer()
                                Text(preferences.statusText(check.status))
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            .frame(minHeight: 34)
                            .help(check.message)
                            .accessibilityLabel(Text("\(check.label), \(preferences.statusText(check.status)), \(check.message)"))
                        }
                    }

                    if !summary.recentEvaluations.isEmpty {
                        Divider()
                        VStack(alignment: .leading, spacing: 4) {
                            MinimalSectionHeader(preferences.text("tasks.releaseCenter.recent"))
                            ForEach(summary.recentEvaluations.prefix(5)) { task in
                                Button {
                                    destination = .tasks
                                    viewModel.selectTask(task.taskId)
                                } label: {
                                    HStack(spacing: 10) {
                                        Image(systemName: StatusPalette.systemImage(for: task.status))
                                            .foregroundStyle(StatusPalette.tone(for: task.status).foreground)
                                        Text(task.description)
                                            .foregroundStyle(.primary)
                                            .lineLimit(1)
                                        Spacer()
                                        Text(task.finalQualityScore.map(String.init) ?? "-")
                                            .font(.caption.monospaced())
                                            .foregroundStyle(.secondary)
                                        Image(systemName: "chevron.right")
                                            .font(.caption)
                                            .foregroundStyle(.tertiary)
                                    }
                                    .frame(minHeight: 36)
                                    .contentShape(Rectangle())
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }

                    if let error = viewModel.releaseE2EError, !error.isEmpty {
                        MinimalNoticeBar(message: error, status: "error")
                    }
                }
                .minimalPageContentFrame(topPadding: 12)
            }
        } else {
            MinimalWorkflowStateView(
                state: .empty,
                title: preferences.text("tasks.releaseEvaluation.empty"),
                actionTitle: preferences.text("tasks.releaseEvaluation.refresh")
            ) {
                viewModel.loadReleaseEvaluation()
            }
        }
    }

    private func releaseValue(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.title3.weight(.semibold))
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 12)
    }

    private var filteredTasks: [TaskOrchestrationViewModel.TaskSummary] {
        let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { return viewModel.tasks }
        return viewModel.tasks.filter {
            $0.description.localizedCaseInsensitiveContains(query)
                || $0.taskId.localizedCaseInsensitiveContains(query)
                || $0.status.localizedCaseInsensitiveContains(query)
        }
    }

    private var taskSelection: Binding<String?> {
        Binding(
            get: { viewModel.selectedTask?.taskId },
            set: { taskId in
                guard let taskId else { return }
                if taskId != viewModel.selectedTask?.taskId {
                    viewModel.selectTask(taskId)
                }
                setRunHistoryVisible(false)
            }
        )
    }

    private var runHistoryDrawer: some View {
        MinimalFloatingDrawer {
            VStack(spacing: 0) {
                HStack(spacing: 8) {
                    Image(systemName: "magnifyingglass")
                        .foregroundStyle(.secondary)
                        .accessibilityHidden(true)
                    TextField(preferences.text("tasks.search"), text: $searchText)
                        .textFieldStyle(.plain)
                        .accessibilityLabel(Text(preferences.text("tasks.search")))
                    Button {
                        setRunHistoryVisible(false)
                    } label: {
                        Image(systemName: "xmark")
                            .frame(width: 28, height: 28)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .help(preferences.text("settings.close"))
                    .accessibilityLabel(Text(preferences.text("settings.close")))
                }
                .padding(.horizontal, 12)
                .frame(height: 44)

                Divider()
                runSidebar
            }
        }
    }

    private var runSidebar: some View {
        List(selection: taskSelection) {
            Section(preferences.text("tasks.sidebar")) {
                ForEach(filteredTasks) { task in
                    runRow(task)
                        .tag(task.taskId)
                }

                if searchText.isEmpty && viewModel.hasMoreTasks {
                    Button {
                        viewModel.loadMoreTasks()
                    } label: {
                        HStack {
                            if viewModel.isLoadingMoreTasks {
                                ProgressView()
                                    .controlSize(.mini)
                            } else {
                                Image(systemName: "chevron.down")
                                    .accessibilityHidden(true)
                            }
                            Text(
                                viewModel.isLoadingMoreTasks
                                    ? preferences.text("tasks.loading")
                                    : preferences.text("tasks.loadMore")
                            )
                        }
                        .frame(maxWidth: .infinity, alignment: .center)
                    }
                    .disabled(viewModel.isLoadingMoreTasks)
                }
            }
        }
        .listStyle(.inset)
        .overlay {
            if viewModel.isLoading && viewModel.tasks.isEmpty {
                ProgressView()
                    .controlSize(.small)
            }
        }
    }

    private func setRunHistoryVisible(_ isVisible: Bool) {
        withAnimation(preferences.reduceMotion ? nil : .easeOut(duration: 0.18)) {
            showsRunHistory = isVisible
        }
    }

    private func runRow(_ task: TaskOrchestrationViewModel.TaskSummary) -> some View {
        HStack(alignment: .top, spacing: 9) {
            Image(systemName: StatusPalette.systemImage(for: task.status))
                .foregroundStyle(StatusPalette.tone(for: task.status).foreground)
                .frame(width: 16)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 3) {
                Text(task.description)
                    .lineLimit(2)
                HStack(spacing: 6) {
                    Text(preferences.statusText(task.status))
                    if task.totalCount > 0 {
                        Text("\(task.completedCount)/\(task.totalCount)")
                    }
                    if let ownerAgent = task.ownerAgent {
                        Text(ownerAgent)
                    }
                }
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
            }
        }
        .padding(.vertical, 3)
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder
    private var runDetail: some View {
        switch viewModel.viewMode {
        case .createForm:
            TaskNewTaskForm(
                viewModel: viewModel,
                settingsVM: settingsViewModel,
                defaultProjectPath: defaultProjectPath
            )
        case .releaseCenter:
            emptyRunState
        case .detail:
            if let task = viewModel.selectedTask {
                selectedRun(task)
            } else {
                emptyRunState
            }
        case .empty:
            emptyRunState
        }
    }

    @ViewBuilder
    private var emptyRunState: some View {
        if viewModel.isBackendUnavailable {
            MinimalWorkflowStateView(
                state: .error,
                title: preferences.text("tasks.backendUnavailable.title"),
                detail: viewModel.backendUnavailableMessage
                    ?? preferences.text("tasks.backendUnavailable.subtitle"),
                actionTitle: preferences.text("tasks.backendUnavailable.retry")
            ) {
                viewModel.loadTasks()
            }
        } else if viewModel.isOrchestratorPluginUnavailable {
            MinimalWorkflowStateView(
                state: .unavailable,
                title: preferences.text("tasks.orchestratorPlugin.title"),
                detail: viewModel.orchestratorPluginUnavailableMessage,
                actionTitle: viewModel.canInstallOrchestratorPlugin
                    ? preferences.text("tasks.orchestratorPlugin.install")
                    : preferences.text("tasks.orchestratorPlugin.retry")
            ) {
                if viewModel.canInstallOrchestratorPlugin {
                    viewModel.installOrchestratorPlugin()
                } else {
                    viewModel.loadOrchestratorPluginStatus()
                }
            }
        } else {
            SimpleStartWorkflowView(
                viewModel: viewModel,
                defaultProjectPath: defaultProjectPath
            )
        }
    }

    private func selectedRun(_ task: TaskOrchestrationViewModel.TaskDetail) -> some View {
        ScrollView {
            VStack(spacing: 0) {
                runHeader(task)
                Divider()

                VStack(alignment: .leading, spacing: 16) {
                    AcrossVisualResultOverview(
                        contract: AcrossVisualResultFactory.make(task: task),
                        preferences: preferences
                    )

                    DisclosureGroup(preferences.text("tasks.description"), isExpanded: .constant(true)) {
                        Text(task.description)
                            .font(.body)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.top, 8)
                    }

                    if let qualityHealth = task.qualityHealth {
                        Divider()
                        qualitySection(qualityHealth, report: task.deliveryReport)
                    }

                    if !task.waves.isEmpty {
                        Divider()
                        waveSection(task.waves)
                    } else if !task.subtasks.isEmpty {
                        Divider()
                        subtaskSection(task.subtasks)
                    } else if task.status == "decomposing" {
                        Divider()
                        HStack(spacing: 8) {
                            ProgressView()
                                .controlSize(.small)
                            Text(task.error ?? preferences.text("tasks.decomposing"))
                                .font(.callout)
                        }
                    }

                    if !task.artifacts.isEmpty {
                        Divider()
                        artifactSection(task.artifacts)
                    }

                    if let observability = task.observability,
                       !observability.timeline.isEmpty || !observability.qualityGates.isEmpty {
                        Divider()
                        observabilitySection(observability)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .minimalPageContentFrame(topPadding: 12)
        }
    }

    private func runHeader(_ task: TaskOrchestrationViewModel.TaskDetail) -> some View {
        HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Text(task.taskId)
                    .font(.headline.monospaced())
                    .lineLimit(1)
                    .truncationMode(.middle)
                if let projectDir = task.projectDir {
                    Text(projectDir)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
            }
            Spacer(minLength: 10)
            MinimalWorkflowStatusLabel(status: task.status)

            if canShowEvidence(for: task) {
                MinimalIconButton(
                    systemName: "doc.text.magnifyingglass",
                    label: preferences.text("tasks.evidence.view"),
                    isDisabled: viewModel.isLoadingTaskEvidence
                ) {
                    AcrossLearningProgressStore.shared.record([
                        AcrossLearningEvent(kind: .evidenceInspected, sourceID: task.taskId)
                    ])
                    viewModel.loadTaskEvidenceBundle(
                        task.taskId,
                        releaseGate: isReleaseE2ETask(task)
                    )
                }
                MinimalIconButton(
                    systemName: "square.and.arrow.down",
                    label: preferences.text("tasks.evidence.export"),
                    isDisabled: viewModel.isLoadingTaskEvidence
                ) {
                    viewModel.exportTaskEvidenceBundle(
                        task.taskId,
                        releaseGate: isReleaseE2ETask(task)
                    )
                }
            }

            lifecycleControls(task)
        }
        .padding(.horizontal, 16)
        .frame(minHeight: 54)
    }

    @ViewBuilder
    private func lifecycleControls(_ task: TaskOrchestrationViewModel.TaskDetail) -> some View {
        if task.supportsHostLocalLifecycleControls
            && TaskOrchestrationViewModel.ResumableTask.isRecoverableDisplayStatus(task.status) {
            MinimalIconButton(
                systemName: "arrow.counterclockwise",
                label: preferences.text("tasks.restore")
            ) {
                viewModel.restoreTask(task.taskId)
            }
        }

        if task.supportsHostLocalLifecycleControls && task.status == "running" {
            MinimalIconButton(systemName: "pause.fill", label: preferences.text("tasks.pause")) {
                viewModel.pauseTask(task.taskId)
            }
        } else if task.supportsHostLocalLifecycleControls && task.status == "paused" {
            MinimalIconButton(systemName: "play.fill", label: preferences.text("tasks.resume")) {
                viewModel.resumeTask(task.taskId)
            }
        }

        if task.supportsHostLocalLifecycleControls && canCancel(task.status) {
            Button(role: .destructive) {
                taskPendingCancellationID = task.taskId
            } label: {
                Image(systemName: "stop.fill")
            }
            .buttonStyle(.borderless)
            .help(preferences.text("tasks.cancel"))
            .accessibilityLabel(Text(preferences.text("tasks.cancel")))
        }
    }

    private func qualitySection(
        _ health: TaskOrchestrationQualityHealth,
        report: TaskOrchestrationDeliveryReport?
    ) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            MinimalSectionHeader(preferences.text("tasks.deliveryHealth"))
            MinimalKeyValueRow(
                preferences.text("tasks.delivery"),
                value: preferences.statusText(health.deliveryQuality)
            )
            MinimalKeyValueRow(
                preferences.text("tasks.orchestration"),
                value: preferences.statusText(health.orchestrationHealth)
            )
            MinimalKeyValueRow(
                preferences.text("tasks.score"),
                value: report?.qualityReport?.finalQualityScore.map(String.init) ?? "-"
            )

            ForEach(health.deliveryQualityReport?.missingRequired ?? [], id: \.self) { item in
                Label(item, systemImage: "doc.badge.ellipsis")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            ForEach(health.deliveryQualityReport?.failedConstraints ?? [], id: \.self) { item in
                Label(item, systemImage: "xmark.octagon")
                    .font(.caption)
                    .foregroundStyle(StatusPalette.tone(for: "failed").foreground)
            }
            if let nextAction = health.nextRepairAction ?? report?.nextAction {
                Label(nextAction, systemImage: "wrench.and.screwdriver")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func waveSection(_ waves: [TaskOrchestrationWaveDetail]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            MinimalSectionHeader(preferences.text("tasks.waves"), detail: "\(waves.count)")
            ForEach(waves) { wave in
                DisclosureGroup {
                    VStack(spacing: 0) {
                        ForEach(wave.subtasks) { subtask in
                            subtaskRow(subtask)
                            if subtask.id != wave.subtasks.last?.id { Divider() }
                        }
                    }
                    .padding(.top, 6)
                } label: {
                    HStack {
                        Text(String(format: preferences.text("tasks.waveNumber"), wave.waveNumber))
                        Spacer()
                        MinimalWorkflowStatusLabel(status: wave.status)
                    }
                }
            }
        }
    }

    private func subtaskSection(_ subtasks: [TaskOrchestrationSubtaskDetail]) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            MinimalSectionHeader(preferences.text("tasks.subtasksLabel"), detail: "\(subtasks.count)")
            ForEach(subtasks) { subtask in
                subtaskRow(subtask)
                if subtask.id != subtasks.last?.id { Divider() }
            }
        }
    }

    private func subtaskRow(_ subtask: TaskOrchestrationSubtaskDetail) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: StatusPalette.systemImage(for: subtask.status))
                .foregroundStyle(StatusPalette.tone(for: subtask.status).foreground)
                .frame(width: 16)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 3) {
                Text(subtask.description)
                    .font(.callout)
                HStack(spacing: 8) {
                    Text(subtask.agentId)
                    if let duration = subtask.duration {
                        Text(String(format: "%.1fs", duration))
                    }
                    if let blockedReason = subtask.blockedReason {
                        Text(blockedReason)
                    }
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }
            Spacer()
            MinimalWorkflowStatusLabel(status: subtask.status)
        }
        .padding(.vertical, 7)
    }

    private func artifactSection(_ artifacts: [TaskOrchestrationArtifact]) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            MinimalSectionHeader(preferences.text("tasks.artifacts"), detail: "\(artifacts.count)")
            ForEach(artifacts) { artifact in
                HStack(spacing: 10) {
                    Image(systemName: "doc")
                        .foregroundStyle(.secondary)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(artifact.fileName)
                            .font(.callout)
                        Text(artifact.filePath)
                            .font(.caption.monospaced())
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }
                    Spacer()
                    Text(artifact.fileSize)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .padding(.vertical, 7)
                Divider()
            }
        }
    }

    private func observabilitySection(_ observability: TaskOrchestrationTaskObservability) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            MinimalSectionHeader(
                preferences.text("tasks.observability"),
                detail: observability.qualityScore.map(String.init)
            )
            DisclosureGroup(preferences.text("tasks.timeline")) {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(observability.timeline) { event in
                        HStack(alignment: .top, spacing: 8) {
                            Image(systemName: StatusPalette.systemImage(for: event.status ?? "observed"))
                                .foregroundStyle(StatusPalette.tone(for: event.status ?? "observed").foreground)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(event.label ?? event.kind)
                                    .font(.caption.weight(.medium))
                                if let summary = event.summary {
                                    Text(summary)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }
                .padding(.top, 8)
            }
            DisclosureGroup(preferences.text("tasks.observability.gates")) {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(observability.qualityGates) { gate in
                        HStack {
                            Text(gate.adapterId)
                                .font(.caption.monospaced())
                            Spacer()
                            MinimalWorkflowStatusLabel(status: gate.status)
                        }
                    }
                }
                .padding(.top, 8)
            }
        }
    }

    @ViewBuilder
    private var runInspector: some View {
        Form {
            if let task = viewModel.selectedTask {
                Section(preferences.text("tasks.runSection")) {
                    MinimalKeyValueRow(preferences.text("tasks.id"), value: task.taskId, monospaced: true)
                    MinimalKeyValueRow(preferences.text("tasks.status"), value: preferences.statusText(task.status))
                    MinimalKeyValueRow(
                        preferences.text("tasks.ownerAgent"),
                        value: task.ownerAgent ?? "-"
                    )
                    MinimalKeyValueRow(
                        preferences.text("tasks.projectDirectory"),
                        value: task.projectDir ?? "-",
                        monospaced: true
                    )
                    MinimalKeyValueRow(
                        preferences.text("tasks.mode"),
                        value: task.deliveryMode ?? "-"
                    )
                    MinimalKeyValueRow(preferences.text("tasks.runtime"), value: task.externalTask ? "Orchestrator" : "Host")
                }

                Section(preferences.text("tasks.countsSection")) {
                    MinimalKeyValueRow(preferences.text("tasks.waves"), value: "\(task.waves.count)")
                    MinimalKeyValueRow(preferences.text("tasks.subtasksLabel"), value: "\(task.subtasks.count)")
                    MinimalKeyValueRow(preferences.text("tasks.artifacts"), value: "\(task.artifacts.count)")
                }
            } else if let summary = viewModel.releaseEvaluation {
                Section(preferences.text("tasks.releaseEvaluation")) {
                    MinimalKeyValueRow(
                        preferences.text("tasks.releaseEvaluation.readiness"),
                        value: preferences.statusText(summary.releaseReadiness)
                    )
                    MinimalKeyValueRow(
                        preferences.text("tasks.releaseEvaluation.passRate"),
                        value: "\(summary.passRatePercent)%"
                    )
                    MinimalKeyValueRow(
                        preferences.text("tasks.releaseEvaluation.score"),
                        value: summary.averageFinalQualityScore.map(String.init) ?? "-"
                    )
                }
            } else {
                Text(preferences.text("tasks.none.subtitle"))
                    .foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
    }

    private func canShowEvidence(for task: TaskOrchestrationViewModel.TaskDetail) -> Bool {
        ["completed", "completed_with_failures"].contains(task.status)
            || task.qualityHealth != nil
            || task.deliveryReport != nil
    }

    private func canCancel(_ status: String) -> Bool {
        !["completed", "completed_with_failures", "failed", "cancelled", "suspended", "paused"]
            .contains(status)
    }

    private func isReleaseE2ETask(_ task: TaskOrchestrationViewModel.TaskDetail) -> Bool {
        task.description.contains("Release E2E scenario:")
            || task.description.contains("Scenario ID: cross_agent_full_delivery_v1")
    }
}

private enum RunDestination: String {
    case home
    case tasks
    case quality
    case release
}
