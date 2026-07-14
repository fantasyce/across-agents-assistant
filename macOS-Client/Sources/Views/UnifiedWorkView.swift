import SwiftUI

struct UnifiedWorkEmptyState: View {
    let projectName: String?
    let recentTasks: [TaskOrchestrationTaskSummary]
    @ObservedObject var preferences: AppPreferences
    let onChooseProject: () -> Void
    let onOpenTask: (TaskOrchestrationTaskSummary) -> Void

    @Environment(\.acrossWindowLayoutSize) private var windowLayoutSize

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
            } else {
                Color.clear.frame(height: 18)
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
}

struct UnifiedDeliverySetupNotice: View {
    let isInstalling: Bool
    let canInstall: Bool
    let errorMessage: String?
    @ObservedObject var preferences: AppPreferences
    let onInstall: () -> Void
    let onUseDirectMode: () -> Void

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

            Button(preferences.text("work.setup.direct"), action: onUseDirectMode)
                .buttonStyle(.plain)
                .font(.system(size: 10, weight: .medium))

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
    let onAccept: () -> Void
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
                        taskSummary(task)
                        if TaskOrchestrationStateReducers.isTerminalStatus(task.status) {
                            resultSummary(task)
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

                            TaskDetailPanel(
                                viewModel: taskViewModel,
                                settingsVM: settingsViewModel,
                                defaultProjectPath: defaultProjectPath
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
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: StatusPalette.systemImage(for: presentation.resultState?.status ?? "attention"))
                    .font(.system(size: 18))
                    .foregroundStyle(StatusPalette.tone(for: presentation.resultState?.status ?? "attention").foreground)
                VStack(alignment: .leading, spacing: 4) {
                    Text(presentation.resultState?.title
                        ?? preferences.text("work.result.needsAttention"))
                        .font(.system(size: 16, weight: .semibold))
                    Text(resultDetail(task))
                        .font(.system(size: 12))
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            HStack(spacing: 10) {
                if !isAccepted, presentation.requiredDecisions.isEmpty {
                    if isSuccessful {
                        Button(action: onAccept) {
                            if taskViewModel.isAcceptingTask {
                                ProgressView().controlSize(.small)
                            } else {
                                Text(preferences.text("work.accept"))
                            }
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(taskViewModel.isAcceptingTask)
                    } else {
                        Button(preferences.text("work.repair"), action: onContinue)
                            .buttonStyle(.borderedProminent)
                    }
                }
                detailsButton
            }
        }
    }

    private var detailsButton: some View {
        Button {
            showsTechnicalDetails.toggle()
        } label: {
            Label(
                preferences.text(showsTechnicalDetails ? "work.details.hide" : "work.details"),
                systemImage: showsTechnicalDetails ? "chevron.up" : "chevron.down"
            )
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
}
