import AppKit
import SwiftUI

struct MinimalRunsOverviewView: View {
    @ObservedObject private var viewModel: TaskOrchestrationViewModel
    @ObservedObject private var preferences: AppPreferences
    @Binding private var showsRunHistory: Bool

    private let automaticallyLoads: Bool
    private let onStartWork: () -> Void

    @State private var searchText = ""
    @State private var showsInspector = false
    @State private var destination: RunDestination = .home
    @State private var taskPendingCancellationID: String?
    @State private var showsTaskDescription = false
    @State private var showsWaveDetails = false
    @State private var selectedWaveNumber: Int?
    @State private var showsArtifactDetails = false
    @State private var showsAllArtifacts = false
    @State private var showsObservabilityDetails = false
    @Environment(\.colorScheme) private var colorScheme

    init(
        viewModel: TaskOrchestrationViewModel,
        preferences: AppPreferences,
        showsRunHistory: Binding<Bool>,
        automaticallyLoads: Bool = true,
        onStartWork: @escaping () -> Void
    ) {
        self.viewModel = viewModel
        self.preferences = preferences
        _showsRunHistory = showsRunHistory
        self.automaticallyLoads = automaticallyLoads
        self.onStartWork = onStartWork
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
        .onChange(of: viewModel.selectedTask?.taskId) {
            showsTaskDescription = false
            showsWaveDetails = false
            selectedWaveNumber = nil
            showsArtifactDetails = false
            showsAllArtifacts = false
            showsObservabilityDetails = false
        }
        .sheet(item: $viewModel.selectedArtifactPreview) { preview in
            artifactPreviewSheet(preview)
        }
        .sheet(item: $viewModel.selectedEvidenceBundle, onDismiss: {
            viewModel.closeEvidenceBundle()
        }) { bundle in
            TaskEvidenceBundleSheet(
                bundle: bundle,
                resultContract: viewModel.selectedTask.map {
                    AcrossVisualResultFactory.make(task: $0)
                },
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
                },
                trajectory: viewModel.selectedExecutionTrajectory,
                isLoadingTrajectory: viewModel.isLoadingExecutionTrajectory,
                trajectoryErrorMessage: viewModel.executionTrajectoryError,
                exportedTrajectoryURL: viewModel.exportedExecutionTrajectoryURL,
                onLoadNextTrajectory: {
                    viewModel.loadNextTaskExecutionTrajectoryPage(bundle.taskId)
                },
                onExportTrajectory: {
                    viewModel.exportTaskExecutionTrajectory(bundle.taskId)
                },
                onOpenTrajectoryExport: {
                    if let url = viewModel.exportedExecutionTrajectoryURL {
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
    }

    @ViewBuilder
    private var headerActions: some View {
        switch destination {
        case .home:
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
                isDisabled: false
            ) {
                onStartWork()
            }
        case .tasks:
            if isShowingTaskDetail {
                if let task = viewModel.selectedTask {
                    lifecycleControls(task)
                }
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
        }
    }

    private var headerTitle: String {
        switch destination {
        case .home: return preferences.text("tasks.overview.title")
        case .tasks:
            return isShowingTaskDetail
                ? preferences.text("tasks.result.title")
                : preferences.text("tasks.overview.newTask")
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
        }
    }

    private var runOverview: some View {
        ZStack(alignment: .topLeading) {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    VStack(alignment: .leading, spacing: 6) {
                        HStack(spacing: 8) {
                            Image(systemName: "magnifyingglass")
                                .foregroundStyle(.secondary)
                                .accessibilityHidden(true)
                            TextField(preferences.text("tasks.search"), text: $searchText)
                                .textFieldStyle(.plain)
                                .accessibilityLabel(Text(preferences.text("tasks.search")))
                        }
                        .padding(.horizontal, 10)
                        .frame(height: 32)
                        .background(AcrossTheme.recessedFill(for: colorScheme))
                        .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.controlCornerRadius))

                        MinimalSectionHeader(
                            preferences.text("tasks.overview.recent"),
                            detail: viewModel.tasks.isEmpty ? nil : "\(filteredTasks.count)"
                        )

                        if viewModel.isLoading && viewModel.tasks.isEmpty {
                            ProgressView()
                                .controlSize(.small)
                                .frame(maxWidth: .infinity, minHeight: 72)
                        } else if filteredTasks.isEmpty {
                            Text(preferences.text("tasks.overview.recent.empty"))
                                .font(.callout)
                                .foregroundStyle(.secondary)
                                .frame(maxWidth: .infinity, minHeight: 72, alignment: .leading)
                        } else {
                            ForEach(filteredTasks) { task in
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

                            if viewModel.hasMoreTasks {
                                Button(preferences.text("tasks.loadMore")) {
                                    viewModel.loadMoreTasks()
                                }
                                .buttonStyle(.plain)
                                .font(.callout.weight(.medium))
                                .foregroundStyle(AcrossTheme.accent)
                                .disabled(viewModel.isLoadingMoreTasks)
                                .padding(.top, 6)
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
        HStack(alignment: .center, spacing: 9) {
            Image(systemName: StatusPalette.systemImage(for: task.status))
                .foregroundStyle(StatusPalette.tone(for: task.status).foreground)
                .frame(width: 16)
                .accessibilityHidden(true)
            Text(conciseTaskTitle(task.description))
                .font(.system(size: 13, weight: .medium))
                .lineLimit(1)
            Spacer(minLength: 12)
            Text(preferences.statusText(task.status))
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
        .padding(.vertical, 7)
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder
    private var runDetail: some View {
        switch viewModel.viewMode {
        case .createForm:
            emptyRunState
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
                state: .empty,
                title: preferences.text("tasks.overview.newTask"),
                detail: preferences.text("tasks.orchestratorPlugin.directFallback"),
                actionTitle: preferences.text("tasks.overview.newTask")
            ) {
                onStartWork()
            }
        } else {
            MinimalWorkflowStateView(
                state: .empty,
                title: preferences.text("tasks.overview.newTask"),
                detail: preferences.text("tasks.overview.newTask.detail"),
                actionTitle: preferences.text("tasks.overview.newTask")
            ) {
                onStartWork()
            }
        }
    }

    private func selectedRun(_ task: TaskOrchestrationViewModel.TaskDetail) -> some View {
        return ScrollView {
            VStack(spacing: 0) {
                VStack(alignment: .leading, spacing: 14) {
                    AcrossTaskResultOverview(
                        task: task,
                        preferences: preferences,
                        viewModel: viewModel,
                        onOpenEvidence: {
                            openEvidence(for: task)
                        }
                    )

                    if let qualityHealth = task.qualityHealth {
                        qualitySection(qualityHealth, report: task.deliveryReport)
                    }

                    if let remote = task.remoteExecution {
                        remoteExecutionRoute(remote)
                    }

                    MinimalDisclosureSection(
                        title: preferences.text("tasks.description"),
                        detail: conciseTaskTitle(task.description),
                        isExpanded: $showsTaskDescription
                    ) {
                        Text(task.description)
                            .font(.body)
                            .foregroundStyle(.secondary)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    if !task.waves.isEmpty {
                        waveSection(task.waves)
                    } else if !task.subtasks.isEmpty {
                        subtaskSection(task.subtasks)
                    } else if task.status == "decomposing" {
                        HStack(spacing: 8) {
                            ProgressView()
                                .controlSize(.small)
                            Text(task.error ?? preferences.text("tasks.decomposing"))
                                .font(.callout)
                        }
                    }

                    if !task.artifacts.isEmpty {
                        artifactSection(task.artifacts)
                    }

                    if let observability = task.observability,
                       !observability.timeline.isEmpty || !observability.qualityGates.isEmpty {
                        observabilitySection(observability)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .minimalPageContentFrame(topPadding: 12)
        }
    }

    private func openEvidence(for task: TaskOrchestrationViewModel.TaskDetail) {
        AcrossLearningProgressStore.shared.record([
            AcrossLearningEvent(kind: .evidenceInspected, sourceID: task.taskId)
        ])
        viewModel.loadTaskEvidenceBundle(
            task.taskId,
            releaseGate: isReleaseE2ETask(task)
        )
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
        let score = report?.qualityReport?.finalQualityScore.map(String.init) ?? "-"
        let delivery = preferences.statusText(health.deliveryQuality)
        let orchestration = preferences.statusText(health.orchestrationHealth)
        let hasIssue = !(health.deliveryQualityReport?.missingRequired ?? []).isEmpty
            || !(health.deliveryQualityReport?.failedConstraints ?? []).isEmpty
        let status = hasIssue ? "failed" : health.deliveryQuality

        return VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Image(systemName: StatusPalette.systemImage(for: status))
                    .foregroundStyle(StatusPalette.tone(for: status).foreground)
                    .accessibilityHidden(true)
                Text(
                    String(
                        format: preferences.text("tasks.delivery.summary"),
                        delivery,
                        orchestration,
                        score
                    )
                )
                .font(.system(size: 13, weight: .medium))
                Spacer(minLength: 0)
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel(
                "\(preferences.text("tasks.deliveryHealth")): \(delivery), \(orchestration), \(score)"
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
        MinimalDisclosureSection(
            title: preferences.text("tasks.waves"),
            detail: String(format: preferences.text("tasks.waves.summary"), waves.count),
            isExpanded: $showsWaveDetails
        ) {
            VStack(alignment: .leading, spacing: 10) {
                LazyVGrid(
                    columns: [GridItem(.adaptive(minimum: 132), spacing: 8)],
                    spacing: 8
                ) {
                    ForEach(waves) { wave in
                        Button {
                            selectedWaveNumber = selectedWaveNumber == wave.waveNumber
                                ? nil
                                : wave.waveNumber
                        } label: {
                            HStack(spacing: 7) {
                                Image(systemName: StatusPalette.systemImage(for: wave.status))
                                    .foregroundStyle(StatusPalette.tone(for: wave.status).foreground)
                                    .accessibilityHidden(true)
                                Text(String(format: preferences.text("tasks.waveNumber"), wave.waveNumber))
                                    .font(.system(size: 12, weight: .medium))
                                Spacer(minLength: 4)
                                Image(systemName: selectedWaveNumber == wave.waveNumber ? "chevron.up" : "chevron.down")
                                    .font(.system(size: 9, weight: .semibold))
                                    .foregroundStyle(.tertiary)
                                    .accessibilityHidden(true)
                            }
                            .padding(.horizontal, 10)
                            .frame(minHeight: 34)
                            .background(
                                selectedWaveNumber == wave.waveNumber
                                    ? AcrossTheme.accent.opacity(0.10)
                                    : Color.secondary.opacity(0.05)
                            )
                            .clipShape(RoundedRectangle(cornerRadius: 7, style: .continuous))
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel(
                            "\(String(format: preferences.text("tasks.waveNumber"), wave.waveNumber)), \(preferences.statusText(wave.status))"
                        )
                        .accessibilityValue(
                            selectedWaveNumber == wave.waveNumber
                                ? preferences.text("tasks.section.expanded")
                                : preferences.text("tasks.section.collapsed")
                        )
                    }
                }

                if let selectedWave = waves.first(where: { $0.waveNumber == selectedWaveNumber }) {
                    VStack(spacing: 0) {
                        ForEach(selectedWave.subtasks) { subtask in
                            subtaskRow(subtask)
                            if subtask.id != selectedWave.subtasks.last?.id {
                                Divider().opacity(0.45)
                            }
                        }
                    }
                    .padding(.horizontal, 2)
                }
            }
        }
    }

    private func subtaskSection(_ subtasks: [TaskOrchestrationSubtaskDetail]) -> some View {
        MinimalDisclosureSection(
            title: preferences.text("tasks.subtasksLabel"),
            detail: String(format: preferences.text("tasks.subtasks.summary"), subtasks.count),
            isExpanded: $showsWaveDetails
        ) {
            VStack(alignment: .leading, spacing: 0) {
                ForEach(subtasks) { subtask in
                    subtaskRow(subtask)
                    if subtask.id != subtasks.last?.id {
                        Divider().opacity(0.45)
                    }
                }
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
        MinimalDisclosureSection(
            title: preferences.text("tasks.artifacts"),
            detail: String(format: preferences.text("tasks.artifacts.summary"), artifacts.count),
            isExpanded: $showsArtifactDetails
        ) {
            VStack(alignment: .leading, spacing: 0) {
                ForEach(Array(visibleArtifacts(artifacts).enumerated()), id: \.element.id) { index, artifact in
                    Button {
                        viewModel.previewArtifact(artifact)
                    } label: {
                        HStack(spacing: 10) {
                            Image(systemName: "doc")
                                .foregroundStyle(.secondary)
                                .accessibilityHidden(true)
                            Text(artifact.fileName)
                                .font(.callout)
                                .lineLimit(1)
                            Spacer()
                            Text(artifact.fileSize)
                                .font(.caption.monospacedDigit())
                                .foregroundStyle(.secondary)
                            if viewModel.isLoadingArtifactPreview {
                                ProgressView()
                                    .controlSize(.small)
                            } else if artifact.filePath.hasPrefix("/api/workers/artifacts/") {
                                Image(systemName: "eye")
                                    .font(.system(size: 11))
                                    .foregroundStyle(.secondary)
                                    .accessibilityHidden(true)
                            }
                        }
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .disabled(!artifact.filePath.hasPrefix("/api/workers/artifacts/") || viewModel.isLoadingArtifactPreview)
                    .accessibilityLabel("\(preferences.text("tasks.artifacts")): \(artifact.fileName)")
                    .accessibilityHint(preferences.text("tasks.artifacts.previewHint"))
                    .padding(.vertical, 7)

                    if index < visibleArtifacts(artifacts).count - 1 {
                        Divider().opacity(0.35)
                    }
                }

                if artifacts.count > 8 {
                    Button {
                        showsAllArtifacts.toggle()
                    } label: {
                        Label(
                            showsAllArtifacts
                                ? preferences.text("tasks.artifacts.showLess")
                                : String(
                                    format: preferences.text("tasks.artifacts.showMore"),
                                    artifacts.count - 8
                                ),
                            systemImage: showsAllArtifacts ? "chevron.up" : "chevron.down"
                        )
                    }
                    .buttonStyle(.plain)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(AcrossTheme.accent)
                    .padding(.top, 8)
                }
            }
        }
    }

    private func visibleArtifacts(_ artifacts: [TaskOrchestrationArtifact]) -> [TaskOrchestrationArtifact] {
        showsAllArtifacts ? artifacts : Array(artifacts.prefix(8))
    }

    private func conciseTaskTitle(_ description: String) -> String {
        let firstLine = description
            .split(whereSeparator: \.isNewline)
            .first
            .map(String.init)?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            ?? description.trimmingCharacters(in: .whitespacesAndNewlines)
        guard firstLine.count > 72 else {
            return firstLine.isEmpty ? preferences.text("tasks.result.title") : firstLine
        }
        return String(firstLine.prefix(69)) + "…"
    }

    private func artifactPreviewSheet(_ preview: TaskOrchestrationViewModel.ArtifactPreview) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(spacing: 12) {
                Image(systemName: "doc.text")
                    .foregroundStyle(AcrossTheme.accent)
                Text(preview.fileName)
                    .font(.headline)
                Spacer()
                Button {
                    viewModel.closeArtifactPreview()
                } label: {
                    Image(systemName: "xmark")
                }
                .buttonStyle(.plain)
                .accessibilityLabel(preferences.text("settings.close"))
            }

            ScrollView {
                Text(preview.content)
                    .font(.system(.body, design: .monospaced))
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .padding(20)
        .frame(minWidth: 640, minHeight: 460)
    }

    private func observabilitySection(_ observability: TaskOrchestrationTaskObservability) -> some View {
        MinimalDisclosureSection(
            title: preferences.text("tasks.observability"),
            detail: String(
                format: preferences.text("tasks.observability.summary"),
                observability.timeline.count,
                observability.qualityGates.count
            ),
            isExpanded: $showsObservabilityDetails
        ) {
            VStack(alignment: .leading, spacing: 14) {
                if !observability.timeline.isEmpty {
                    Text(preferences.text("tasks.timeline"))
                        .font(.system(size: 12, weight: .semibold))
                }
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(observability.timeline) { event in
                        HStack(alignment: .top, spacing: 8) {
                            Image(systemName: StatusPalette.systemImage(for: event.status ?? "observed"))
                                .foregroundStyle(StatusPalette.tone(for: event.status ?? "observed").foreground)
                                .accessibilityHidden(true)
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

                if !observability.qualityGates.isEmpty {
                    Text(preferences.text("tasks.observability.gates"))
                        .font(.system(size: 12, weight: .semibold))
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(observability.qualityGates) { gate in
                            HStack {
                                Text(gate.adapterId)
                                    .font(.caption.monospaced())
                                    .lineLimit(1)
                                Spacer()
                                MinimalWorkflowStatusLabel(status: gate.status)
                            }
                        }
                    }
                }
            }
        }
    }

    private func remoteExecutionRoute(_ execution: TaskOrchestrationRemoteExecution) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "externaldrive.connected.to.line.below")
                .foregroundStyle(AcrossTheme.accent)
                .accessibilityHidden(true)
            Text(execution.nodeId ?? preferences.text("tasks.remoteExecution.waitingNode"))
                .font(.system(size: 12, weight: .medium))
                .lineLimit(1)
            Spacer(minLength: 12)
            Text(
                execution.phases
                    .map { preferences.text("tasks.remoteExecution.phase.\($0.id)") }
                    .joined(separator: "  ›  ")
            )
            .font(.system(size: 11))
            .foregroundStyle(.secondary)
            .lineLimit(1)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(preferences.text("tasks.remoteExecution.title"))
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
}
