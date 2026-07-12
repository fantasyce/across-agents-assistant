import SwiftUI
import AppKit

struct TaskDetailPanel: View {
    @ObservedObject var viewModel: TaskOrchestrationViewModel
    @ObservedObject var settingsVM: SettingsViewModel
    let defaultProjectPath: String?

    @State private var isDescriptionExpanded = false
    @State private var isHealthExpanded = false
    @State private var isObservabilityExpanded = true
    @State private var taskPendingCancellationID: String?
    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    var body: some View {
        ZStack {
            switch viewModel.viewMode {
            case .empty:
                emptyStateView
            case .detail:
                if let task = viewModel.selectedTask {
                    taskDetailView(task: task)
                } else {
                    emptyStateView
                }
            case .createForm:
                TaskNewTaskForm(viewModel: viewModel, settingsVM: settingsVM, defaultProjectPath: defaultProjectPath)
            case .releaseCenter:
                ReleaseEvidenceCenterView(viewModel: viewModel)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(theme.panelBackground)
        .sheet(item: $viewModel.selectedEvidenceBundle, onDismiss: {
            viewModel.closeEvidenceBundle()
        }) { bundle in
            TaskEvidenceBundleSheet(
                bundle: bundle,
                isLoading: viewModel.isLoadingTaskEvidence,
                errorMessage: viewModel.taskEvidenceError,
                exportedURL: viewModel.exportedEvidenceBundleURL,
                onExport: { viewModel.exportTaskEvidenceBundle(bundle.taskId, releaseGate: bundle.usesReleaseE2EBenchmark) },
                onOpenExport: {
                    if let url = viewModel.exportedEvidenceBundleURL {
                        NSWorkspace.shared.activateFileViewerSelecting([url])
                    }
                }
            )
            .environmentObject(appPreferences)
        }
        .confirmationDialog(
            appPreferences.text("tasks.cancelConfirmTitle"),
            isPresented: Binding(
                get: { taskPendingCancellationID != nil },
                set: { if !$0 { taskPendingCancellationID = nil } }
            ),
            titleVisibility: .visible
        ) {
            Button(appPreferences.text("tasks.cancel"), role: .destructive) {
                if let taskID = taskPendingCancellationID {
                    viewModel.cancelTask(taskID)
                }
                taskPendingCancellationID = nil
            }
            Button(appPreferences.text("system.cancel"), role: .cancel) {
                taskPendingCancellationID = nil
            }
        } message: {
            Text(appPreferences.text("tasks.cancelConfirmMessage"))
        }
    }

    private var emptyStateView: some View {
        Group {
            if viewModel.isBackendUnavailable {
                VStack(spacing: 14) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 40, weight: .light))
                        .foregroundColor(Color(hex: "#FF9F0A").opacity(0.75))

                    Text(appPreferences.text("tasks.backendUnavailable.title"))
                        .font(.system(size: 14, weight: .medium))
                        .foregroundColor(.secondary)

                    Text(appPreferences.text("tasks.backendUnavailable.subtitle"))
                        .font(.system(size: 12))
                        .foregroundColor(.secondary.opacity(0.65))
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: 320)

                    if let message = viewModel.backendUnavailableMessage, !message.isEmpty {
                        Text(message)
                            .font(.system(size: 11))
                            .foregroundColor(.secondary.opacity(0.6))
                            .multilineTextAlignment(.center)
                            .frame(maxWidth: 360)
                    }

                    Button(action: { viewModel.loadTasks() }) {
                        HStack(spacing: 6) {
                            Image(systemName: "arrow.clockwise")
                            Text(appPreferences.text("tasks.backendUnavailable.retry"))
                        }
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.white)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                        .background(Color(hex: "#4D6BFE"))
                        .cornerRadius(8)
                    }
                    .buttonStyle(.plain)
                    .padding(.top, 4)
                }
            } else if viewModel.isOrchestratorPluginUnavailable {
                orchestratorPluginUnavailableView
            } else {
                SimpleStartWorkflowView(
                    viewModel: viewModel,
                    defaultProjectPath: defaultProjectPath
                )
            }
        }
    }

    private var orchestratorPluginUnavailableView: some View {
        VStack(spacing: 14) {
            Image(systemName: "puzzlepiece.extension")
                .font(.system(size: 40, weight: .light))
                .foregroundColor(AcrossTheme.accent.opacity(0.78))

            Text(appPreferences.text("tasks.orchestratorPlugin.title"))
                .font(.system(size: 15, weight: .semibold))
                .foregroundColor(theme.primaryText)

            Text(appPreferences.text("tasks.orchestratorPlugin.subtitle"))
                .font(.system(size: 12))
                .foregroundColor(.secondary.opacity(0.78))
                .multilineTextAlignment(.center)
                .frame(maxWidth: 420)

            Text(viewModel.orchestratorPluginUnavailableMessage)
                .font(.system(size: 11))
                .foregroundColor(.secondary.opacity(0.68))
                .multilineTextAlignment(.center)
                .frame(maxWidth: 460)

            if let installDir = viewModel.orchestratorPluginStatus?.install.installDir {
                Text(String(format: appPreferences.text("tasks.orchestratorPlugin.installDir"), installDir))
                    .font(.system(size: 10))
                    .foregroundColor(.secondary.opacity(0.58))
                    .lineLimit(2)
                    .truncationMode(.middle)
                    .frame(maxWidth: 460)
            }

            HStack(spacing: 10) {
                Button(action: { viewModel.installOrchestratorPlugin() }) {
                    HStack(spacing: 7) {
                        if viewModel.isInstallingOrchestratorPlugin {
                            ProgressView()
                                .controlSize(.mini)
                                .scaleEffect(0.72)
                        } else {
                            Image(systemName: "arrow.down.circle.fill")
                                .font(.system(size: 12, weight: .semibold))
                        }
                        Text(viewModel.isInstallingOrchestratorPlugin ? appPreferences.text("tasks.orchestratorPlugin.installing") : appPreferences.text("tasks.orchestratorPlugin.install"))
                    }
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(.white)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 9)
                    .background(viewModel.canInstallOrchestratorPlugin ? Color(hex: "#4D6BFE") : Color.secondary.opacity(0.35))
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                }
                .buttonStyle(.plain)
                .disabled(!viewModel.canInstallOrchestratorPlugin)

                Button(action: { viewModel.loadOrchestratorPluginStatus() }) {
                    HStack(spacing: 6) {
                        Image(systemName: "arrow.clockwise")
                        Text(appPreferences.text("tasks.orchestratorPlugin.retry"))
                    }
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(theme.strongText)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                    .background(theme.controlBackground)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                }
                .buttonStyle(.plain)
            }
            .padding(.top, 4)

            if viewModel.isLoadingOrchestratorPlugin {
                Text(appPreferences.text("tasks.loading"))
                    .font(.system(size: 10))
                    .foregroundColor(.secondary.opacity(0.65))
            }
        }
        .padding(28)
    }

    private func taskDetailView(task: TaskOrchestrationViewModel.TaskDetail) -> some View {
        VStack(spacing: 0) {
            taskHeaderView(task: task)

            Divider().opacity(0.5)

            ScrollView {
                VStack(spacing: 20) {
                    taskDescriptionSection(task: task)
                    qualityOverviewSection(task: task)
                    observabilitySection(task: task)

                    if !task.waves.isEmpty {
                        DAGVisualization(task: task, viewModel: viewModel)
                    } else if !task.subtasks.isEmpty {
                        SubtaskListView(task: task, viewModel: viewModel)
                    } else if task.status == "decomposing" {
                        // Decomposing: show loading or error based on timeout
                        // If task has error field, it means decomposition failed
                        let hasError = task.error != nil && !task.error!.isEmpty

                        VStack(spacing: 12) {
                            if hasError {
                                // Error state: show error message
                                Image(systemName: "exclamationmark.triangle.fill")
                                    .font(.system(size: 32))
                                    .foregroundColor(.orange)

                                Text(appPreferences.text("tasks.decompositionFailed"))
                                    .font(.system(size: 14, weight: .semibold))
                                    .foregroundColor(theme.primaryText)

                                Text(task.error ?? appPreferences.text("tasks.unknownError"))
                                    .font(.system(size: 12))
                                    .foregroundColor(.secondary)
                                    .multilineTextAlignment(.center)
                                    .padding(.horizontal)
                            } else {
                                // Normal loading state
                                ProgressView()
                                    .controlSize(.regular)

                                Text(appPreferences.text("tasks.decomposing"))
                                    .font(.system(size: 13))
                                    .foregroundColor(.secondary)

                                Text(appPreferences.text("tasks.decomposing.help"))
                                    .font(.system(size: 11))
                                    .foregroundColor(.secondary.opacity(0.7))
                            }
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.top, 40)
                    } else {
                        VStack(spacing: 12) {
                            Image(systemName: "doc.text")
                                .font(.system(size: 32))
                                .foregroundColor(.secondary.opacity(0.4))

                            Text(appPreferences.text("tasks.noSubtasks"))
                                .font(.system(size: 13))
                                .foregroundColor(.secondary)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.top, 40)
                    }

                    if !task.artifacts.isEmpty {
                        ArtifactFileList(artifacts: task.artifacts)
                    }
                }
                .padding(16)
            }
        }
    }

    private func taskHeaderView(task: TaskOrchestrationViewModel.TaskDetail) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(shortenedTaskTitle(task.description))
                .font(.system(size: 16, weight: .semibold))
                .foregroundColor(theme.primaryText)
                .lineLimit(1)

            HStack(spacing: 16) {
                HStack(spacing: 4) {
                    Circle()
                        .fill(statusColor(for: task.status))
                        .frame(width: 8, height: 8)
                    Text(localizedTaskStatus(task.status, preferences: appPreferences))
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                }

                if let ownerAgent = task.ownerAgent, !ownerAgent.isEmpty {
                    HStack(spacing: 4) {
                        AgentIdentityBadge(agentId: ownerAgent, ownerAgentId: nil, size: 18)
                        Text(ownerAgent)
                            .font(.system(size: 12))
                    }
                    .foregroundColor(.secondary)
                }

                if let projectDir = task.projectDir {
                    HStack(spacing: 4) {
                        Image(systemName: "folder")
                            .font(.system(size: 10))
                        Text(projectDir)
                            .font(.system(size: 11))
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }
                    .foregroundColor(.secondary.opacity(0.7))
                }

                if let decision = task.lastOwnerDecision,
                   let action = decision.recommendedAction,
                   action != "approve" {
                    HStack(spacing: 4) {
                        Image(systemName: "brain.head.profile")
                            .font(.system(size: 10))
                        Text(ownerDecisionText(decision))
                            .font(.system(size: 11))
                            .lineLimit(1)
                    }
                    .foregroundColor(Color(hex: "#ff9f0a"))
                }

                Spacer()

                HStack(spacing: 8) {
                    if task.status == "completed" || task.status == "completed_with_failures" || task.qualityHealth != nil || task.deliveryReport != nil {
                        Button(action: { viewModel.loadTaskEvidenceBundle(task.taskId, releaseGate: isReleaseE2ETask(task)) }) {
                            Image(systemName: "doc.text.magnifyingglass")
                                .font(.system(size: 12))
                                .foregroundColor(Color(hex: "#4d6bfe"))
                                .frame(width: 28, height: 28)
                                .background(Color(hex: "#4d6bfe").opacity(0.14))
                                .cornerRadius(6)
                        }
                        .buttonStyle(.plain)
                        .disabled(viewModel.isLoadingTaskEvidence)
                        .help(appPreferences.text("tasks.evidence.view"))

                        Button(action: { viewModel.exportTaskEvidenceBundle(task.taskId, releaseGate: isReleaseE2ETask(task)) }) {
                            Image(systemName: "square.and.arrow.down")
                                .font(.system(size: 12))
                                .foregroundColor(Color(hex: "#30d158"))
                                .frame(width: 28, height: 28)
                                .background(Color(hex: "#30d158").opacity(0.14))
                                .cornerRadius(6)
                        }
                        .buttonStyle(.plain)
                        .disabled(viewModel.isLoadingTaskEvidence)
                        .help(appPreferences.text("tasks.evidence.export"))
                    }

                    // Show restore only for host-local task rows; external tasks restore through Orchestrator.
                    if task.supportsHostLocalLifecycleControls
                        && TaskOrchestrationViewModel.ResumableTask.isRecoverableDisplayStatus(task.status) {
                        Button(action: { viewModel.restoreTask(task.taskId) }) {
                            Image(systemName: "arrow.counterclockwise")
                                .font(.system(size: 12))
                                .foregroundColor(Color(hex: "#ff9f0a"))
                                .frame(width: 28, height: 28)
                                .background(Color(hex: "#ff9f0a").opacity(0.15))
                                .cornerRadius(6)
                        }
                        .buttonStyle(.plain)
                        .help(appPreferences.text("tasks.restore"))
                    }

                    if task.supportsHostLocalLifecycleControls && task.status == "running" {
                        Button(action: { viewModel.pauseTask(task.taskId) }) {
                            Image(systemName: "pause.fill")
                                .font(.system(size: 12))
                                .foregroundColor(.secondary)
                                .frame(width: 28, height: 28)
                                .background(theme.controlBackground)
                                .cornerRadius(6)
                        }
                        .buttonStyle(.plain)
                        .help(appPreferences.text("tasks.pause"))
                    } else if task.supportsHostLocalLifecycleControls && task.status == "paused" {
                        Button(action: { viewModel.resumeTask(task.taskId) }) {
                            Image(systemName: "play.fill")
                                .font(.system(size: 12))
                                .foregroundColor(Color(hex: "#30d158"))
                                .frame(width: 28, height: 28)
                                .background(Color(hex: "#30d158").opacity(0.15))
                                .cornerRadius(6)
                        }
                        .buttonStyle(.plain)
                        .help(appPreferences.text("tasks.resume"))
                    }

                    // Issue 46: Redesigned cancel button with stop icon
                    if task.status != "completed"
                        && task.status != "completed_with_failures"
                        && task.status != "failed"
                        && task.status != "cancelled"
                        && task.supportsHostLocalLifecycleControls
                        && !TaskOrchestrationViewModel.ResumableTask.isRecoverableDisplayStatus(task.status) {
                        Button(action: { taskPendingCancellationID = task.taskId }) {
                            Image(systemName: "stop.fill")
                                .font(.system(size: 11, weight: .bold))
                                .foregroundColor(Color(hex: "#FF453A"))
                                .frame(width: 28, height: 28)
                                .background(Color(hex: "#FF453A").opacity(0.15))
                                .cornerRadius(6)
                        }
                        .buttonStyle(.plain)
                        .help(appPreferences.text("tasks.cancel"))
                    }
                }
            }

            if let notice = taskStatusNotice(for: task) {
                HStack(spacing: 6) {
                    Image(systemName: notice.icon)
                        .font(.system(size: 11))
                        .foregroundColor(notice.color)
                    Text(notice.message)
                        .font(.system(size: 12))
                        .foregroundColor(notice.color)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(notice.color.opacity(0.12))
                .cornerRadius(6)
            }

            if viewModel.isLoadingTaskEvidence || viewModel.taskEvidenceError != nil || viewModel.exportedEvidenceBundleURL != nil {
                HStack(spacing: 6) {
                    Image(systemName: viewModel.taskEvidenceError == nil ? "doc.badge.gearshape" : "exclamationmark.triangle.fill")
                        .font(.system(size: 11))
                        .foregroundColor(viewModel.taskEvidenceError == nil ? Color(hex: "#4d6bfe") : Color(hex: "#ff9f0a"))
                    Text(taskEvidenceStatusText)
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                    Spacer()
                    if let url = viewModel.exportedEvidenceBundleURL {
                        Button(action: { NSWorkspace.shared.activateFileViewerSelecting([url]) }) {
                            Text(appPreferences.text("tasks.evidence.openExport"))
                                .font(.system(size: 11, weight: .medium))
                                .foregroundColor(Color(hex: "#4d6bfe"))
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(theme.fieldBackground)
                .cornerRadius(6)
            }

            if task.status == "pending",
               let decision = task.lastOwnerDecision,
               (decision.blockedReason ?? "") == "waiting_for_keys" {
                HStack(spacing: 8) {
                    Image(systemName: "hourglass")
                        .font(.system(size: 14))
                        .foregroundColor(Color(hex: "#ff9f0a"))
                    VStack(alignment: .leading, spacing: 2) {
                        Text(appPreferences.text("tasks.waitingKey"))
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(Color(hex: "#ff9f0a"))
                        Text(appPreferences.text("tasks.waitingKey.help"))
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                    }
                    Spacer()
                    Button(action: {
                        Task {
                            await settingsVM.refreshBackendKeyStatus()
                            viewModel.selectTask(task.taskId)
                        }
                    }) {
                        Text(appPreferences.text("tasks.refreshKeys"))
                            .font(.system(size: 11, weight: .medium))
                            .foregroundColor(.white)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 5)
                            .background(Color(hex: "#ff9f0a"))
                            .cornerRadius(6)
                    }
                    .buttonStyle(.plain)
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color(hex: "#ff9f0a").opacity(0.1))
                .cornerRadius(6)
            }
        }
        .padding(16)
    }

    private var taskEvidenceStatusText: String {
        if viewModel.isLoadingTaskEvidence {
            return appPreferences.text("tasks.evidence.loading")
        }
        if let error = viewModel.taskEvidenceError, !error.isEmpty {
            return error
        }
        if let url = viewModel.exportedEvidenceBundleURL {
            return String(format: appPreferences.text("tasks.evidence.exported"), url.path)
        }
        return ""
    }

    private func isReleaseE2ETask(_ task: TaskOrchestrationViewModel.TaskDetail) -> Bool {
        task.description.contains("Release E2E scenario:")
            || task.description.contains("Scenario ID: cross_agent_full_delivery_v1")
    }

    private func taskDescriptionSection(task: TaskOrchestrationViewModel.TaskDetail) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Button(action: { isDescriptionExpanded.toggle() }) {
                HStack(spacing: 6) {
                        Text(appPreferences.text("tasks.description"))
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(theme.primaryText)

                    Image(systemName: "doc.text.fill")
                        .font(.system(size: 12))
                        .foregroundColor(Color(hex: "#4d6bfe"))

                    Image(systemName: isDescriptionExpanded ? "chevron.down" : "chevron.right")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.secondary)

                    Spacer()
                }
            }
            .buttonStyle(.plain)

            if isDescriptionExpanded {
                Text(task.description)
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                    .lineSpacing(4)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .transition(.opacity)
            }
        }
        .animation(.easeInOut(duration: 0.2), value: isDescriptionExpanded)
    }

    @ViewBuilder
    private func qualityOverviewSection(task: TaskOrchestrationViewModel.TaskDetail) -> some View {
        let report = task.deliveryReport
        let health = task.qualityHealth
        let deliveryQuality = health?.deliveryQuality ?? report?.qualityGate
        let orchestrationHealth = health?.orchestrationHealth
        let requiredTotal = report?.requiredTotal ?? health?.manifestRequired
        let acceptedTotal = report?.acceptedTotal ?? health?.manifestAccepted
        let finalQualityScore = report?.qualityReport?.finalQualityScore
        let hasQualityData = deliveryQuality != nil
            || orchestrationHealth != nil
            || report?.summary != nil
            || finalQualityScore != nil
            || requiredTotal != nil
            || task.hasOwnerDeliveryContract
            || task.hasRequirementManifest

        if hasQualityData {
            VStack(alignment: .leading, spacing: 10) {
                Button(action: { isHealthExpanded.toggle() }) {
                    HStack(spacing: 6) {
                        Text(appPreferences.text("tasks.deliveryHealth"))
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(theme.primaryText)
                        Image(systemName: "checkmark.seal.fill")
                            .font(.system(size: 12))
                            .foregroundColor(qualityColor(for: deliveryQuality ?? orchestrationHealth ?? "unknown"))
                        Image(systemName: isHealthExpanded ? "chevron.down" : "chevron.right")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(.secondary)
                        Spacer()
                    }
                }
                .buttonStyle(.plain)

                if isHealthExpanded {
                    HStack(spacing: 8) {
                        qualityMetricChip(
                            title: appPreferences.text("tasks.delivery"),
                            value: displayStatus(deliveryQuality ?? "not_started"),
                            status: deliveryQuality ?? "not_started"
                        )
                        qualityMetricChip(
                            title: appPreferences.text("tasks.orchestration"),
                            value: displayStatus(orchestrationHealth ?? "unknown"),
                            status: orchestrationHealth ?? "unknown"
                        )
                        if let requiredTotal {
                            qualityMetricChip(
                                title: appPreferences.text("tasks.required"),
                                value: "\(acceptedTotal ?? 0)/\(requiredTotal)",
                                status: (acceptedTotal ?? 0) >= requiredTotal ? "passed" : "partial"
                            )
                        }
                        if let finalQualityScore {
                            qualityMetricChip(
                                title: appPreferences.text("tasks.score"),
                                value: "\(finalQualityScore)",
                                status: finalQualityScore >= 80 ? "passed" : "partial"
                            )
                        }
                        if let deliveryMode = task.deliveryMode, deliveryMode != "external" {
                            qualityMetricChip(
                                title: appPreferences.text("tasks.mode"),
                                value: displayStatus(deliveryMode),
                                status: "neutral"
                            )
                        }
                    }

                    if let summary = report?.summary, !summary.isEmpty {
                        Text(summary)
                            .font(.system(size: 12))
                            .foregroundColor(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }

                    let issues = qualityIssueLines(task: task)
                    if !issues.isEmpty {
                        VStack(alignment: .leading, spacing: 5) {
                            ForEach(issues.prefix(4), id: \.self) { issue in
                                HStack(alignment: .top, spacing: 6) {
                                    Image(systemName: "exclamationmark.circle.fill")
                                        .font(.system(size: 10))
                                        .foregroundColor(Color(hex: "#ff9f0a"))
                                        .padding(.top, 2)
                                    Text(issue)
                                        .font(.system(size: 11))
                                        .foregroundColor(.secondary)
                                        .lineLimit(2)
                                }
                            }
                        }
                    }
                }
            }
            .animation(.easeInOut(duration: 0.2), value: isHealthExpanded)
        }
    }

    private func taskStatusNotice(for task: TaskOrchestrationViewModel.TaskDetail) -> TaskStatusNotice? {
        guard let rawError = task.error?.trimmingCharacters(in: .whitespacesAndNewlines), !rawError.isEmpty else {
            return nil
        }

        let lowercasedError = rawError.lowercased()
        let isRecovering = task.qualityHealth?.orchestrationHealth == "recovering"
            || !(task.qualityHealth?.activeRemediationSubtasks.isEmpty ?? true)
            || lowercasedError.contains("waiting for remediation")
            || lowercasedError.contains("await")

        if isRecovering && task.status != "failed" && task.status != "cancelled" {
            return TaskStatusNotice(
                icon: "arrow.triangle.2.circlepath",
                message: appPreferences.text("tasks.qualityRemediation"),
                color: Color(hex: "#ff9f0a")
            )
        }

        return TaskStatusNotice(
            icon: "exclamationmark.triangle.fill",
            message: rawError,
            color: Color(hex: "#FF453A")
        )
    }

    private func qualityMetricChip(title: String, value: String, status: String) -> some View {
        HStack(spacing: 5) {
            Circle()
                .fill(qualityColor(for: status))
                .frame(width: 6, height: 6)
            Text(title)
                .font(.system(size: 10, weight: .medium))
                .foregroundColor(.secondary)
            Text(value)
                .font(.system(size: 10, weight: .semibold))
                .foregroundColor(theme.strongText)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .background(theme.fieldBackground)
        .cornerRadius(6)
    }

    private func qualityIssueLines(task: TaskOrchestrationViewModel.TaskDetail) -> [String] {
        var lines: [String] = []
        let report = task.deliveryReport
        let health = task.qualityHealth

        lines.append(contentsOf: report?.missingRequired.map { String(format: appPreferences.text("tasks.missingDeliverable"), $0) } ?? [])
        lines.append(contentsOf: report?.failedConstraints.map { String(format: appPreferences.text("tasks.failedConstraint"), $0) } ?? [])
        lines.append(contentsOf: health?.deliveryQualityReport?.missingRequired.map { String(format: appPreferences.text("tasks.missingDeliverable"), $0) } ?? [])
        lines.append(contentsOf: health?.deliveryQualityReport?.failedConstraints.map { String(format: appPreferences.text("tasks.failedConstraint"), $0) } ?? [])
        lines.append(contentsOf: health?.terminalInconsistencies.map { String(format: appPreferences.text("tasks.terminalInconsistency"), $0) } ?? [])

        if report?.consistency?.terminalWithActiveRemediation == true {
            lines.append(appPreferences.text("tasks.terminalRemediation"))
        }
        if let qualityReport = report?.qualityReport {
            if let count = qualityReport.requiredFailedCount, count > 0 {
                lines.append(String(format: appPreferences.text("tasks.requiredGateFailures"), count))
            }
            if let count = qualityReport.manualRequiredCount, count > 0 {
                lines.append(String(format: appPreferences.text("tasks.manualGateChecks"), count))
            }
            if let count = qualityReport.skippedRequiredCount, count > 0 {
                lines.append(String(format: appPreferences.text("tasks.skippedGateChecks"), count))
            }
        }
        if !(health?.activeRemediationSubtasks.isEmpty ?? true) {
            lines.append(String(format: appPreferences.text("tasks.activeRemediation"), health?.activeRemediationSubtasks.joined(separator: ", ") ?? ""))
        }
        if let nextAction = report?.nextAction ?? health?.nextRepairAction, !nextAction.isEmpty {
            lines.append(String(format: appPreferences.text("tasks.nextRepair"), displayStatus(nextAction)))
        }

        return Array(NSOrderedSet(array: lines)) as? [String] ?? lines
    }

    @ViewBuilder
    private func observabilitySection(task: TaskOrchestrationViewModel.TaskDetail) -> some View {
        if let observability = task.observability,
           !observability.timeline.isEmpty || !observability.qualityGates.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                Button(action: { isObservabilityExpanded.toggle() }) {
                    HStack(spacing: 6) {
                        Text(appPreferences.text("tasks.observability"))
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(theme.primaryText)
                        Image(systemName: "point.3.connected.trianglepath.dotted")
                            .font(.system(size: 12))
                            .foregroundColor(Color(hex: "#4d6bfe"))
                        Image(systemName: isObservabilityExpanded ? "chevron.down" : "chevron.right")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(.secondary)
                        Spacer()
                    }
                }
                .buttonStyle(.plain)

                if isObservabilityExpanded {
                    if let mix = observability.agentMix,
                       !mix.actualAgents.isEmpty || !mix.localAgents.isEmpty || !mix.cloudAgents.isEmpty {
                        HStack(spacing: 8) {
                            qualityMetricChip(
                                title: appPreferences.text("tasks.observability.agents"),
                                value: "\(mix.actualAgents.count)",
                                status: mix.actualAgents.count >= 3 ? "passed" : "partial"
                            )
                            qualityMetricChip(
                                title: appPreferences.text("tasks.observability.local"),
                                value: "\(mix.localAgents.count)",
                                status: mix.localAgents.count >= 2 ? "passed" : "partial"
                            )
                            qualityMetricChip(
                                title: appPreferences.text("tasks.observability.cloud"),
                                value: "\(mix.cloudAgents.count)",
                                status: mix.cloudAgents.count >= 1 ? "passed" : "partial"
                            )
                            if let score = observability.qualityScore {
                                qualityMetricChip(
                                    title: appPreferences.text("tasks.score"),
                                    value: "\(score)",
                                    status: score >= 80 ? "passed" : "partial"
                                )
                            }
                        }
                    }

                    let passedGateCount = observability.qualityGates.filter { $0.status == "passed" }.count
                    if !observability.qualityGates.isEmpty {
                        HStack(spacing: 8) {
                            qualityMetricChip(
                                title: appPreferences.text("tasks.observability.gates"),
                                value: "\(passedGateCount)/\(observability.qualityGates.count)",
                                status: passedGateCount == observability.qualityGates.count ? "passed" : "partial"
                            )
                            if let remediation = observability.remediation, remediation.attempted {
                                qualityMetricChip(
                                    title: appPreferences.text("tasks.observability.remediation"),
                                    value: "\(remediation.attemptsByRequirement.values.reduce(0, +))",
                                    status: "partial"
                                )
                            }
                        }
                    }

                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(observability.timeline.prefix(8)) { event in
                            HStack(alignment: .top, spacing: 8) {
                                Circle()
                                    .fill(observabilityColor(for: event.kind, status: event.status))
                                    .frame(width: 7, height: 7)
                                    .padding(.top, 5)
                                VStack(alignment: .leading, spacing: 2) {
                                    HStack(spacing: 6) {
                                        Text(observabilityEventTitle(event))
                                            .font(.system(size: 11, weight: .semibold))
                                            .foregroundColor(theme.strongText)
                                            .lineLimit(1)
                                        if let agentId = event.agentId, !agentId.isEmpty {
                                            Text(agentId)
                                                .font(.system(size: 10, weight: .medium))
                                                .foregroundColor(.secondary)
                                                .padding(.horizontal, 6)
                                                .padding(.vertical, 2)
                                                .background(theme.fieldBackground)
                                                .cornerRadius(5)
                                        }
                                    }
                                    if let summary = event.summary, !summary.isEmpty {
                                        Text(summary)
                                            .font(.system(size: 10))
                                            .foregroundColor(.secondary)
                                            .lineLimit(2)
                                    }
                                }
                            }
                        }
                    }
                    .padding(10)
                    .background(theme.fieldBackground)
                    .cornerRadius(8)
                }
            }
            .animation(.easeInOut(duration: 0.2), value: isObservabilityExpanded)
        }
    }

    private func observabilityEventTitle(_ event: TaskOrchestrationViewModel.TaskObservability.TimelineEvent) -> String {
        if let label = event.label, !label.isEmpty {
            return label
        }
        return displayStatus(event.kind.replacingOccurrences(of: "_", with: " "))
    }

    private func observabilityColor(for kind: String, status: String?) -> Color {
        if kind.contains("failed") || status == "failed" {
            return Color(hex: "#FF453A")
        }
        if kind.contains("remediation") || kind.contains("revalidating") || status == "partial" {
            return Color(hex: "#ff9f0a")
        }
        if kind.contains("passed") || kind.contains("completed") || status == "completed" {
            return Color(hex: "#30d158")
        }
        return Color(hex: "#4d6bfe")
    }

    private func displayStatus(_ status: String) -> String {
        localizedTaskStatus(status, preferences: appPreferences)
    }

    private func qualityColor(for status: String) -> Color {
        switch status {
        case "passed", "healthy", "completed": return Color(hex: "#30d158")
        case "partial", "recovering", "completed_with_failures": return Color(hex: "#ff9f0a")
        case "failed", "inconsistent": return Color(hex: "#FF453A")
        case "not_started", "unknown", "neutral": return Color(hex: "#8e8e93")
        default: return Color(hex: "#8e8e93")
        }
    }

    private func statusColor(for status: String) -> Color {
        switch status {
        case "running": return Color(hex: "#4d6bfe")
        case "completed": return Color(hex: "#30d158")
        case "failed": return Color(hex: "#FF453A")
        case "completed_with_failures": return Color(hex: "#ff9f0a")
        case "paused": return Color(hex: "#ff9f0a")
        case "decomposing": return Color(hex: "#bf5af2")
        case "pending": return Color(hex: "#8e8e93")
        default: return Color(hex: "#8e8e93")
        }
    }

    private func shortenedTaskTitle(_ description: String) -> String {
        let maxChars = 80
        if description.count <= maxChars {
            return description
        }

        let truncated = String(description.prefix(maxChars))
        if let lastPeriod = truncated.lastIndex(of: ".") {
            let sentence = String(truncated[...lastPeriod])
            if sentence.count >= 20 {
                return sentence
            }
        }

        if let lastSpace = truncated.lastIndex(of: " ") {
            return String(truncated[...lastSpace]) + "..."
        }

        return truncated + "..."
    }
}
