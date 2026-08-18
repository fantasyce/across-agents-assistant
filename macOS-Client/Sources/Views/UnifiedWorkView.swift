import AppKit
import SwiftUI

struct UnifiedWorkEmptyState: View {
    let projectName: String?
    let projectPath: String?
    let recentTasks: [TaskOrchestrationTaskSummary]
    let isBeginnerMissionAvailable: Bool
    @ObservedObject var beginnerMission: BeginnerMissionViewModel
    let beginnerGoal: String
    let submissionErrorMessage: String?
    @ObservedObject var preferences: AppPreferences
    let onChooseProject: () -> Void
    let onRunBeginnerMission: (String) -> Void
    let onInstallBeginnerCapability: () -> Void
    let onOpenBeginnerEvidence: () -> Void
    let onOpenTask: (TaskOrchestrationTaskSummary) -> Void

    @Environment(\.acrossWindowLayoutSize) private var windowLayoutSize
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            Spacer(minLength: 40)

            VStack(alignment: .leading, spacing: 8) {
                Text(projectName == nil
                    ? preferences.text("work.chooseProject.title")
                    : preferences.text("work.empty.title"))
                    .font(.system(size: windowLayoutSize == .expanded ? 34 : 30, weight: .semibold))
                Text(projectName == nil
                    ? preferences.text("work.chooseProject.subtitle")
                    : String(format: preferences.text("work.empty.subtitle"), projectName ?? ""))
                    .font(.system(size: 14))
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if projectName == nil {
                Button(action: onChooseProject) {
                    Label(preferences.text("work.chooseProject.action"), systemImage: "folder")
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
            } else if let visualResult = currentBeginnerVisualResult {
                VStack(alignment: .leading, spacing: 10) {
                    if let requestedGoal = beginnerMission.requestedGoal {
                        Label(requestedGoal, systemImage: "scope")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                            .accessibilityLabel(
                                String(format: preferences.text("work.beginner.goalUsed"), requestedGoal)
                            )
                    }
                    AcrossVisualResultOverview(
                        contract: visualResult,
                        preferences: preferences
                    )
                    HStack {
                        Button {
                            onRunBeginnerMission(beginnerMission.requestedGoal ?? beginnerGoal)
                        } label: {
                            Label(preferences.text("work.beginner.runAgain"), systemImage: "arrow.clockwise")
                        }
                        .buttonStyle(.plain)
                        .disabled(beginnerMission.isRunning)

                        Spacer()

                        Button(action: onOpenBeginnerEvidence) {
                            Label(preferences.text("work.beginner.openEvidence"), systemImage: "doc.text.magnifyingglass")
                        }
                        .buttonStyle(.borderedProminent)
                    }
                    .font(.system(size: 11, weight: .medium))
                }
            } else {
                beginnerMissionCard
            }

            if let submissionErrorMessage, !submissionErrorMessage.isEmpty {
                MinimalNoticeBar(
                    message: localizedSubmissionError(submissionErrorMessage),
                    status: "attention"
                )
            }

            if !recentTasks.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text(preferences.text("work.recent"))
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(.secondary)
                        .padding(.top, 8)

                    ForEach(Array(recentTasks.prefix(3))) { task in
                        let isAccepted = task.reviewStatus == "accepted"
                        Button { onOpenTask(task) } label: {
                            HStack(spacing: 10) {
                                Image(systemName: isAccepted
                                    ? "checkmark.circle.fill"
                                    : (task.status == "completed"
                                        ? "checkmark.circle"
                                        : (TaskOrchestrationStateReducers.isTerminalStatus(task.status)
                                            ? "exclamationmark.circle"
                                            : "circle.dotted")))
                                    .foregroundStyle(isAccepted ? Color.green : Color.secondary)
                                Text(task.description)
                                    .font(.system(size: 12))
                                    .lineLimit(1)
                                Spacer()
                                Text(preferences.statusText(task.status))
                                    .font(.system(size: 10))
                                    .foregroundStyle(.secondary)
                                Image(systemName: "chevron.right")
                                    .font(.system(size: 9, weight: .semibold))
                                    .foregroundStyle(.tertiary)
                            }
                            .padding(.vertical, 8)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .overlay(alignment: .bottom) { Divider() }
                    }
                }
            }

            Spacer(minLength: 80)
        }
        .frame(maxWidth: windowLayoutSize == .expanded ? 860 : 720, alignment: .leading)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(.horizontal, windowLayoutSize == .expanded ? 56 : 44)
    }

    private var currentBeginnerVisualResult: AcrossVisualResultContract? {
        guard BeginnerMissionViewModel.normalizedProjectPath(projectPath) == beginnerMission.projectPath else {
            return nil
        }
        return beginnerMission.visualResult
    }

    private var beginnerMissionCard: some View {
        HStack(spacing: 14) {
            PixelAtlasReward(
                atlas: .journeyNodes,
                index: 1,
                isUnlocked: isBeginnerMissionAvailable
            )
            .frame(width: 54, height: 54)

            VStack(alignment: .leading, spacing: 4) {
                Text(preferences.text("work.beginner.title"))
                    .font(.system(size: 14, weight: .semibold))
                Label(
                    preferences.text("work.beginner.safety"),
                    systemImage: "lock.shield"
                )
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
                .lineLimit(1)

                if let goal = normalizedBeginnerGoal {
                    Label(goal, systemImage: "scope")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                        .accessibilityLabel(
                            String(format: preferences.text("work.beginner.goalUsed"), goal)
                        )
                } else {
                    Text(preferences.text("work.beginner.goalPrompt"))
                        .font(.system(size: 11))
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }

                if beginnerMission.errorMessage != nil {
                    Text(preferences.text("work.beginner.error"))
                        .font(.system(size: 10))
                        .foregroundStyle(.red)
                        .lineLimit(1)
                }
            }

            Spacer(minLength: 12)

            if isBeginnerMissionAvailable {
                Button {
                    if let goal = normalizedBeginnerGoal {
                        onRunBeginnerMission(goal)
                    }
                } label: {
                    if beginnerMission.isRunning {
                        ProgressView()
                            .controlSize(.small)
                    } else {
                        Label(preferences.text("work.beginner.run"), systemImage: "play.fill")
                    }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(beginnerMission.isRunning || projectPath == nil || normalizedBeginnerGoal == nil)
                .help(normalizedBeginnerGoal == nil
                    ? preferences.text("work.beginner.goalRequired")
                    : preferences.text("work.beginner.run"))
            } else {
                Button(action: onInstallBeginnerCapability) {
                    Label(preferences.text("work.beginner.install"), systemImage: "puzzlepiece.extension")
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
            }
        }
        .padding(14)
        .background(AcrossTheme.recessedFill(for: colorScheme))
        .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.cardCornerRadius, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AcrossTheme.Metrics.cardCornerRadius, style: .continuous)
                .stroke(AcrossTheme.separator(for: colorScheme), lineWidth: 1)
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(preferences.text("work.beginner.title"))
    }

    private var normalizedBeginnerGoal: String? {
        BeginnerMissionViewModel.normalizedGoal(beginnerGoal)
    }

    private func localizedSubmissionError(_ value: String) -> String {
        switch value {
        case "compatible_worker_workflow_required":
            return preferences.text("work.submit.remoteWorkflowRequired")
        case "External Across Orchestrator runtime is unavailable.":
            return preferences.text("work.submit.orchestratorUnavailable")
        default:
            return value
        }
    }
}

struct UnifiedDeliverySetupNotice: View {
    let isInstalling: Bool
    let canInstall: Bool
    let errorMessage: String?
    @ObservedObject var preferences: AppPreferences
    let onInstall: () -> Void

    var body: some View {
        HStack(alignment: .center, spacing: 10) {
            Image(systemName: "checkmark.shield")
                .foregroundStyle(.secondary)

            VStack(alignment: .leading, spacing: 2) {
                Text(preferences.text("work.setup.title"))
                    .font(.system(size: 11, weight: .semibold))
                Text(errorMessage?.isEmpty == false
                    ? errorMessage!
                    : preferences.text("work.setup.subtitle"))
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }

            Spacer(minLength: 8)

            Button(action: onInstall) {
                if isInstalling {
                    ProgressView().controlSize(.small)
                } else {
                    Text(preferences.text("work.setup.action"))
                }
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.small)
            .disabled(isInstalling || !canInstall)
        }
        .padding(10)
        .background(Color(nsColor: .controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
    }
}

struct UnifiedDeliveryView: View {
    let task: TaskOrchestrationTaskDetail?
    let isLoading: Bool
    let errorMessage: String?
    let capabilityContract: AcrossTaskCapabilityContract? = nil
    @ObservedObject var preferences: AppPreferences
    @ObservedObject var taskViewModel: TaskOrchestrationViewModel
    @ObservedObject var settingsViewModel: SettingsViewModel
    let defaultProjectPath: String?
    @Binding var showsTechnicalDetails: Bool
    let onBack: () -> Void
    let onChooseProject: () -> Void
    let onNewWork: () -> Void
    let onContinue: () -> Void

    private var phase: Int {
        guard let task else { return 0 }
        switch TaskOrchestrationStateReducers.userPhase(for: task) {
        case .understanding: return 0
        case .working: return 1
        case .checking: return 2
        case .ready, .needsAttention: return 3
        }
    }

    private var isSuccessful: Bool {
        guard let task else { return false }
        return TaskOrchestrationStateReducers.isSuccessfulDelivery(task)
    }

    private var isAccepted: Bool {
        task?.reviewStatus == "accepted"
    }

    private var progress: Double {
        guard let task else { return 0.05 }
        let counts = TaskOrchestrationStateReducers.businessProgress(in: task.subtasks)
        if counts.total > 0 {
            return min(1, max(0.05, Double(counts.completed) / Double(counts.total)))
        }
        return Double(phase + 1) / 4
    }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 28) {
                    statusHeader
                    phaseStrip

                    if let task {
                        if TaskOrchestrationStateReducers.isTerminalStatus(task.status) {
                            resultSummary(task)
                            taskSummary(task)
                        } else {
                            taskSummary(task)
                        }
                    } else if isLoading {
                        ProgressView(value: progress)
                            .progressViewStyle(.linear)
                    }

                    if let errorMessage, !errorMessage.isEmpty {
                        HStack(alignment: .top, spacing: 8) {
                            Image(systemName: "exclamationmark.circle")
                            Text(preferences.text("work.error.short"))
                                .fixedSize(horizontal: false, vertical: true)
                            Spacer()
                            detailsButton
                        }
                        .font(.system(size: 12))
                        .foregroundStyle(.secondary)
                    }

                    if showsTechnicalDetails, task != nil {
                        VStack(alignment: .leading, spacing: 12) {
                            Label(preferences.text("work.currentWorkflow"), systemImage: "point.3.connected.trianglepath.dotted")
                                .font(.system(size: 14, weight: .semibold))
                            Text(preferences.text("work.currentWorkflow.subtitle"))
                                .font(.system(size: 11))
                                .foregroundStyle(.secondary)

                            if let task {
                                RunTrustContractsView(
                                    task: task,
                                    preferences: preferences
                                )
                            }

                            TaskDetailPanel(
                                viewModel: taskViewModel,
                                settingsVM: settingsViewModel,
                                defaultProjectPath: defaultProjectPath,
                                showsResultOverview: false
                            )
                            .frame(minHeight: 560, maxHeight: 700)
                            .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                            .overlay {
                                RoundedRectangle(cornerRadius: 6, style: .continuous)
                                    .stroke(Color.secondary.opacity(0.18), lineWidth: 1)
                            }
                        }
                        .padding(.top, 8)
                        .id("current-workflow-details")
                    }
                }
                .minimalPageContentFrame()
            }
            .onChange(of: showsTechnicalDetails) {
                guard showsTechnicalDetails else { return }
                withAnimation(preferences.reduceMotion ? nil : .easeInOut(duration: 0.2)) {
                    proxy.scrollTo("current-workflow-details", anchor: .top)
                }
            }
        }
        .sheet(item: $taskViewModel.selectedEvidenceBundle, onDismiss: {
            taskViewModel.closeEvidenceBundle()
        }) { bundle in
            TaskEvidenceBundleSheet(
                bundle: bundle,
                resultContract: task.map { AcrossVisualResultFactory.make(task: $0) },
                isLoading: taskViewModel.isLoadingTaskEvidence,
                errorMessage: taskViewModel.taskEvidenceError,
                exportedURL: taskViewModel.exportedEvidenceBundleURL,
                onExport: {
                    taskViewModel.exportTaskEvidenceBundle(
                        bundle.taskId,
                        releaseGate: bundle.usesReleaseE2EBenchmark
                    )
                },
                onOpenExport: {
                    if let url = taskViewModel.exportedEvidenceBundleURL {
                        NSWorkspace.shared.activateFileViewerSelecting([url])
                    }
                }
            )
            .environmentObject(preferences)
        }
    }

    private var statusHeader: some View {
        MinimalPageHeader(title: headline, subtitle: subheadline) {
            MinimalIconButton(
                systemName: "chevron.left",
                label: preferences.text("work.back"),
                action: onBack
            )
            MinimalIconButton(
                systemName: "folder",
                label: preferences.text("project.useExisting"),
                action: onChooseProject
            )
            MinimalIconButton(
                systemName: "plus",
                label: preferences.text("work.new"),
                action: onNewWork
            )
        }
    }

    private var phaseStrip: some View {
        HStack(spacing: 0) {
            ForEach(Array(phaseTitles.enumerated()), id: \.offset) { index, title in
                VStack(alignment: .leading, spacing: 7) {
                    HStack(spacing: 0) {
                        Circle()
                            .fill(index <= phase ? AcrossTheme.accent : Color.secondary.opacity(0.2))
                            .frame(width: 8, height: 8)
                        if index < phaseTitles.count - 1 {
                            Rectangle()
                                .fill(index < phase ? AcrossTheme.accent.opacity(0.55) : Color.secondary.opacity(0.16))
                                .frame(height: 1)
                        }
                    }
                    Text(title)
                        .font(.system(size: 11, weight: index == phase ? .semibold : .regular))
                        .foregroundStyle(index <= phase ? Color.primary : Color.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(Text(phaseTitles[min(phase, phaseTitles.count - 1)]))
    }

    private func taskSummary(_ task: TaskOrchestrationTaskDetail) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(task.description)
                .font(.system(size: 15, weight: .medium))
                .lineLimit(4)
                .fixedSize(horizontal: false, vertical: true)

            if let summaryLine = AcrossTaskCapabilityPresentation(
                task: task,
                capabilityContract: capabilityContract
            ).summaryLine {
                Text(summaryLine)
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            ProgressView(value: progress)
                .progressViewStyle(.linear)

            HStack(spacing: 12) {
                let counts = TaskOrchestrationStateReducers.businessProgress(in: task.subtasks)
                if counts.total > 0 {
                    Text(String(format: preferences.text("work.progress"), counts.completed, counts.total))
                }
                if !task.artifacts.isEmpty {
                    Text(String(format: preferences.text("work.artifacts"), task.artifacts.count))
                }
            }
            .font(.system(size: 11))
            .foregroundStyle(.secondary)
        }
        .padding(.vertical, 18)
        .overlay(alignment: .top) { Divider() }
        .overlay(alignment: .bottom) { Divider() }
    }

    private func resultSummary(_ task: TaskOrchestrationTaskDetail) -> some View {
        let presentation = AcrossTaskCapabilityPresentation(
            task: task,
            capabilityContract: capabilityContract
        )
        return VStack(alignment: .leading, spacing: 16) {
            AcrossTaskResultOverview(
                task: task,
                preferences: preferences,
                viewModel: taskViewModel,
                allowsAcceptance: presentation.requiredDecisions.isEmpty,
                onOpenEvidence: {
                    taskViewModel.loadTaskEvidenceBundle(
                        task.taskId,
                        releaseGate: isReleaseE2ETask(task)
                    )
                }
            )

            if !isAccepted, !isSuccessful, presentation.requiredDecisions.isEmpty {
                Button(preferences.text("work.repair"), action: onContinue)
                    .buttonStyle(.borderedProminent)
            }

            HStack(spacing: 10) {
                detailsButton
            }
        }
    }

    private var detailsButton: some View {
        Button {
            showsTechnicalDetails.toggle()
        } label: {
            HStack(spacing: 8) {
                Text(preferences.text(showsTechnicalDetails ? "work.details.hide" : "work.details"))
                Spacer(minLength: 8)
                Image(systemName: showsTechnicalDetails ? "chevron.up" : "chevron.down")
                    .font(.system(size: 10, weight: .semibold))
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .foregroundStyle(.secondary)
    }

    private var headline: String {
        guard let task else { return preferences.text("work.phase.understanding.headline") }
        if TaskOrchestrationStateReducers.isTerminalStatus(task.status) {
            if isAccepted { return preferences.text("work.phase.accepted.headline") }
            return isSuccessful
                ? preferences.text("work.phase.done.headline")
                : preferences.text("work.phase.attention.headline")
        }
        switch phase {
        case 0: return preferences.text("work.phase.understanding.headline")
        case 1: return preferences.text("work.phase.building.headline")
        default: return preferences.text("work.phase.checking.headline")
        }
    }

    private var subheadline: String {
        if let task, TaskOrchestrationStateReducers.isTerminalStatus(task.status) {
            if isAccepted { return preferences.text("work.phase.accepted.subtitle") }
            return isSuccessful
                ? preferences.text("work.phase.done.successSubtitle")
                : preferences.text("work.phase.done.attentionSubtitle")
        }
        switch phase {
        case 0: return preferences.text("work.phase.understanding.subtitle")
        case 1: return preferences.text("work.phase.building.subtitle")
        case 2: return preferences.text("work.phase.checking.subtitle")
        default: return preferences.text("work.phase.done.subtitle")
        }
    }

    private var phaseTitles: [String] {
        [
            preferences.text("work.phase.understanding"),
            preferences.text("work.phase.building"),
            preferences.text("work.phase.checking"),
            preferences.text(isAccepted ? "work.result.accepted" : "work.phase.confirming"),
        ]
    }

    private func resultDetail(_ task: TaskOrchestrationTaskDetail) -> String {
        if isSuccessful {
            if isAccepted { return preferences.text("work.result.acceptedSummary") }
            return String(format: preferences.text("work.result.summary"), task.artifacts.count)
        }
        return preferences.text("work.result.failureSummary")
    }

    private func isReleaseE2ETask(_ task: TaskOrchestrationTaskDetail) -> Bool {
        task.description.contains("Release E2E scenario:")
            || task.description.contains("Scenario ID: cross_agent_full_delivery_v1")
    }
}
