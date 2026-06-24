import SwiftUI
import AppKit

private struct TaskStatusNotice {
    let icon: String
    let message: String
    let color: Color
}

private struct TaskTheme {
    let colorScheme: ColorScheme

    var background: Color { colorScheme == .dark ? .legacyBgDark : .legacyBgLight }
    var headerBackground: Color { background }
    var panelBackground: Color { colorScheme == .dark ? Color(hex: "#2c2c2e") : .legacyBgLight }
    var cardBackground: Color { colorScheme == .dark ? Color(hex: "#1C1C1E") : Color.white }
    var fieldBackground: Color { colorScheme == .dark ? Color.white.opacity(0.06) : Color.black.opacity(0.045) }
    var hoverBackground: Color { colorScheme == .dark ? Color.white.opacity(0.06) : Color.black.opacity(0.045) }
    var subtleBackground: Color { colorScheme == .dark ? Color.white.opacity(0.03) : Color.white }
    var controlBackground: Color { colorScheme == .dark ? Color.white.opacity(0.08) : Color.black.opacity(0.055) }
    var divider: Color { colorScheme == .dark ? Color.white.opacity(0.08) : Color.black.opacity(0.08) }
    var primaryText: Color { colorScheme == .dark ? .white : .legacyTextLight }
    var strongText: Color { colorScheme == .dark ? Color.white.opacity(0.9) : .legacyTextLight }
    var bodyText: Color { colorScheme == .dark ? Color.white.opacity(0.85) : .legacyTextLight }
    var mutedText: Color { colorScheme == .dark ? Color(hex: "#c9c9cf") : Color(hex: "#6b7280") }
}

struct TaskOrchestrationView: View {
    @ObservedObject var viewModel: TaskOrchestrationViewModel
    @ObservedObject var settingsVM: SettingsViewModel
    var onClose: (() -> Void)? = nil

    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                CustomTrafficLights(onClose: onClose)

                Spacer()

                Text(appPreferences.text("tasks.title"))
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(theme.primaryText)

                Spacer()

                Spacer().frame(width: 50)
            }
            .padding(.horizontal, 16)
            .frame(height: 56)
            .background(
                ZStack {
                    theme.headerBackground
                    WindowDragView()
                        .contentShape(Rectangle())
                }
            )

            Divider().opacity(0.5)

            HStack(spacing: 0) {
                TaskListSidebar(viewModel: viewModel)
                    .frame(width: 240)

                Rectangle()
                    .fill(theme.divider)
                    .frame(width: 1)

                TaskDetailPanel(viewModel: viewModel, settingsVM: settingsVM)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(theme.background.ignoresSafeArea())
        .ignoresSafeArea(.all, edges: .top)
        .onAppear {
            viewModel.loadTasks()
        }
    }
}

struct TaskListSidebar: View {
    @ObservedObject var viewModel: TaskOrchestrationViewModel
    @State private var searchText = ""

    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    private var filteredTasks: [TaskOrchestrationViewModel.TaskSummary] {
        if searchText.isEmpty {
            return viewModel.tasks
        }
        return viewModel.tasks.filter { $0.description.localizedCaseInsensitiveContains(searchText) }
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(appPreferences.text("tasks.sidebar"))
                    .font(.system(size: 10, weight: .semibold))
                    .tracking(0.8)
                    .foregroundColor(.secondary.opacity(0.6))
                    .frame(maxWidth: .infinity, alignment: .leading)

                Button(action: { viewModel.enterCreateMode() }) {
                    Image(systemName: "plus.circle.fill")
                        .font(.system(size: 14))
                        .foregroundColor(viewModel.isOrchestratorPluginUnavailable ? .secondary.opacity(0.5) : Color(hex: "#B58AE3"))
                }
                .buttonStyle(.plain)
                .disabled(viewModel.isOrchestratorPluginUnavailable)
                .help(appPreferences.text("tasks.new"))
            }
            .padding(.horizontal, 16)
            .padding(.top, 12)
            .padding(.bottom, 8)

            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)

                TextField(appPreferences.text("tasks.search"), text: $searchText)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(theme.primaryText)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(theme.fieldBackground)
            .cornerRadius(6)
            .padding(.horizontal, 12)

            ReleaseEvaluationCard(
                summary: viewModel.releaseEvaluation,
                isLoading: viewModel.isLoadingReleaseEvaluation,
                errorMessage: viewModel.releaseEvaluationError,
                isStartingE2E: viewModel.isStartingReleaseE2E,
                e2eErrorMessage: viewModel.releaseE2EError,
                isOrchestratorUnavailable: viewModel.isOrchestratorPluginUnavailable,
                onRefresh: { viewModel.loadReleaseEvaluation() },
                onOpenCenter: { viewModel.openReleaseCenter() },
                onRunE2E: { viewModel.startReleaseE2E() }
            )
            .padding(.horizontal, 12)
            .padding(.top, 10)

            if viewModel.isBackendUnavailable {
                BackendUnavailableBanner(
                    message: viewModel.backendUnavailableMessage,
                    onRetry: { viewModel.loadTasks() }
                )
                .padding(.horizontal, 12)
                .padding(.top, 10)
            }

            ScrollView {
                LazyVStack(spacing: 2) {
                    ForEach(filteredTasks) { task in
                        TaskRowView(
                            task: task,
                            isSelected: viewModel.selectedTask?.taskId == task.taskId,
                            onTap: { viewModel.selectTask(task.taskId) }
                        )
                    }

                    if searchText.isEmpty && viewModel.hasMoreTasks {
                        Button(action: { viewModel.loadMoreTasks() }) {
                            HStack(spacing: 6) {
                                if viewModel.isLoadingMoreTasks {
                                    ProgressView()
                                        .controlSize(.mini)
                                        .scaleEffect(0.7)
                                } else {
                                    Image(systemName: "chevron.down")
                                        .font(.system(size: 10, weight: .semibold))
                                }
                                Text(viewModel.isLoadingMoreTasks ? appPreferences.text("tasks.loading") : appPreferences.text("tasks.loadMore"))
                                    .font(.system(size: 11, weight: .medium))
                            }
                            .foregroundColor(.secondary)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 10)
                        }
                        .buttonStyle(.plain)
                        .disabled(viewModel.isLoadingMoreTasks)
                    }
                }
                .padding(.vertical, 8)
            }

            Spacer()
        }
        .frame(maxHeight: .infinity)
        .background(theme.background)
    }
}

struct ReleaseEvaluationCard: View {
    let summary: ReleaseEvaluationSummary?
    let isLoading: Bool
    let errorMessage: String?
    let isStartingE2E: Bool
    let e2eErrorMessage: String?
    let isOrchestratorUnavailable: Bool
    let onRefresh: () -> Void
    let onOpenCenter: () -> Void
    let onRunE2E: () -> Void

    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 7) {
                Circle()
                    .fill(readinessColor(summary?.releaseReadiness ?? "no_evidence"))
                    .frame(width: 7, height: 7)

                Text(appPreferences.text("tasks.releaseEvaluation"))
                    .font(.system(size: 10, weight: .semibold))
                    .tracking(0.5)
                    .foregroundColor(.secondary.opacity(0.75))

                Spacer()

                if isLoading {
                    ProgressView()
                        .controlSize(.mini)
                        .scaleEffect(0.65)
                }

                Button(action: onOpenCenter) {
                    Image(systemName: "chart.line.uptrend.xyaxis")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(.secondary.opacity(0.8))
                        .frame(width: 20, height: 20)
                }
                .buttonStyle(.plain)
                .help(appPreferences.text("tasks.releaseEvaluation.open"))

                Button(action: onRefresh) {
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(.secondary.opacity(0.8))
                        .frame(width: 20, height: 20)
                }
                .buttonStyle(.plain)
                .help(appPreferences.text("tasks.releaseEvaluation.refresh"))
            }

            if let summary {
                HStack(spacing: 8) {
                    releaseMetric(
                        appPreferences.text("tasks.releaseEvaluation.readiness"),
                        localizedReadiness(summary.releaseReadiness)
                    )
                    releaseMetric(
                        appPreferences.text("tasks.releaseEvaluation.passRate"),
                        "\(summary.passRatePercent)%"
                    )
                    releaseMetric(
                        appPreferences.text("tasks.releaseEvaluation.score"),
                        summary.averageFinalQualityScore.map(String.init) ?? "-"
                    )
                }

                HStack(spacing: 8) {
                    releaseMetric(
                        appPreferences.text("tasks.releaseEvaluation.trend"),
                        localizedTrend(summary.qualityTrend?.direction ?? "no_data")
                    )
                    releaseMetric(
                        appPreferences.text("tasks.releaseEvaluation.delta"),
                        summary.trendDeltaText
                    )
                    releaseMetric(
                        appPreferences.text("tasks.releaseEvaluation.agentMix"),
                        agentMixText(summary.agentMixSummary)
                    )
                }

                HStack(spacing: 8) {
                    Text(String(format: appPreferences.text("tasks.releaseEvaluation.evaluated"), summary.evaluatedTaskCount))
                        .font(.system(size: 10, weight: .medium))
                        .foregroundColor(.secondary)
                    if summary.totalRemediationCount > 0 {
                        Text(String(format: appPreferences.text("tasks.releaseEvaluation.remediations"), summary.totalRemediationCount))
                            .font(.system(size: 10, weight: .medium))
                            .foregroundColor(Color(hex: "#ff9f0a"))
                    }
                }

                if !summary.readinessChecks.isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(summary.readinessChecks.prefix(2)) { check in
                            HStack(alignment: .top, spacing: 5) {
                                Circle()
                                    .fill(checkColor(check.status))
                                    .frame(width: 6, height: 6)
                                    .padding(.top, 4)
                                Text(check.message)
                                    .font(.system(size: 9))
                                    .foregroundColor(.secondary)
                                    .lineLimit(2)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                }

                if let latest = summary.recentEvaluations.first {
                    HStack(spacing: 8) {
                        Text(String(format: appPreferences.text("tasks.releaseEvaluation.latest"), shortTaskId(latest.taskId)))
                            .font(.system(size: 9, weight: .medium))
                            .foregroundColor(.secondary)
                            .lineLimit(1)
                        Text(latest.benchmarkStatus ?? latest.qualityGate ?? "-")
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundColor(checkColor(latest.benchmarkStatus ?? latest.qualityGate ?? "unknown"))
                            .lineLimit(1)
                        if let auditTrace = latest.auditTrace {
                            Text(String(format: appPreferences.text("tasks.releaseEvaluation.probes"), auditTrace.passedProbeCount, auditTrace.failedProbeCount))
                                .font(.system(size: 9, weight: .medium))
                                .foregroundColor(.secondary)
                                .lineLimit(1)
                        }
                    }
                }

                if let risk = summary.primaryRiskMessage, !risk.isEmpty {
                    Text(risk)
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                }
            } else {
                Text(errorMessage?.isEmpty == false ? errorMessage! : appPreferences.text("tasks.releaseEvaluation.empty"))
                    .font(.system(size: 10))
                    .foregroundColor(errorMessage == nil ? .secondary : Color(hex: "#ff9f0a"))
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Divider()
                .opacity(0.45)

            Button(action: onRunE2E) {
                HStack(spacing: 7) {
                    Image(systemName: "checklist.checked")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(Color(hex: "#B58AE3"))

                    VStack(alignment: .leading, spacing: 2) {
                        Text(isStartingE2E ? appPreferences.text("tasks.releaseE2E.starting") : appPreferences.text("tasks.releaseE2E.run"))
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundColor(theme.strongText)
                            .lineLimit(1)
                        Text(appPreferences.text("tasks.releaseE2E.help"))
                            .font(.system(size: 9))
                            .foregroundColor(.secondary.opacity(0.75))
                            .lineLimit(1)
                    }

                    Spacer()

                    if isStartingE2E {
                        ProgressView()
                            .controlSize(.mini)
                            .scaleEffect(0.65)
                    } else {
                        Image(systemName: "arrow.right")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundColor(.secondary.opacity(0.75))
                    }
                }
                .padding(8)
                .background(theme.hoverBackground)
                .clipShape(RoundedRectangle(cornerRadius: 6))
            }
            .buttonStyle(.plain)
            .disabled(isStartingE2E || isOrchestratorUnavailable)
            .opacity(isOrchestratorUnavailable ? 0.65 : 1)
            .help(appPreferences.text("tasks.releaseE2E.help"))

            if let e2eErrorMessage, !e2eErrorMessage.isEmpty {
                Text(e2eErrorMessage)
                    .font(.system(size: 9))
                    .foregroundColor(Color(hex: "#ff9f0a"))
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(10)
        .background(theme.fieldBackground)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(theme.divider, lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private func releaseMetric(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(.system(size: 9, weight: .medium))
                .foregroundColor(.secondary.opacity(0.75))
                .lineLimit(1)
            Text(value)
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(theme.strongText)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func localizedReadiness(_ readiness: String) -> String {
        appPreferences.text("tasks.releaseEvaluation.readiness.\(readiness)")
    }

    private func localizedTrend(_ trend: String) -> String {
        appPreferences.text("tasks.releaseEvaluation.trend.\(trend)")
    }

    private func agentMixText(_ mix: ReleaseEvaluationAgentMixSummary?) -> String {
        guard let mix else { return "-" }
        return "\(mix.localAgentCount)L/\(mix.cloudAgentCount)C"
    }

    private func shortTaskId(_ taskId: String) -> String {
        if taskId.count <= 12 { return taskId }
        return String(taskId.prefix(12))
    }

    private func checkColor(_ status: String) -> Color {
        switch status {
        case "passed", "ready":
            return Color(hex: "#30d158")
        case "failed", "blocked":
            return Color(hex: "#FF453A")
        default:
            return Color(hex: "#ff9f0a")
        }
    }

    private func readinessColor(_ readiness: String) -> Color {
        switch readiness {
        case "ready":
            return Color(hex: "#30d158")
        case "attention":
            return Color(hex: "#ff9f0a")
        case "blocked":
            return Color(hex: "#FF453A")
        default:
            return Color(hex: "#8e8e93")
        }
    }
}

struct ReleaseEvidenceCenterView: View {
    @ObservedObject var viewModel: TaskOrchestrationViewModel

    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(appPreferences.text("tasks.releaseCenter.title"))
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(theme.primaryText)
                    Text(appPreferences.text("tasks.releaseCenter.subtitle"))
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                }

                Spacer()

                Button(action: { viewModel.loadReleaseEvaluation() }) {
                    Label(appPreferences.text("tasks.releaseEvaluation.refresh"), systemImage: "arrow.clockwise")
                        .font(.system(size: 12, weight: .medium))
                }
                .buttonStyle(.plain)

                Button(action: { viewModel.startReleaseE2E() }) {
                    Label(
                        viewModel.isStartingReleaseE2E ? appPreferences.text("tasks.releaseE2E.starting") : appPreferences.text("tasks.releaseE2E.run"),
                        systemImage: "checklist.checked"
                    )
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(Color(hex: "#B58AE3"))
                }
                .buttonStyle(.plain)
                .disabled(viewModel.isStartingReleaseE2E)
            }
            .padding(16)

            Divider().opacity(0.5)

            if let summary = viewModel.releaseEvaluation {
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        releaseCenterOverview(summary)
                        releaseCenterChecklist(summary)
                        releaseCenterCoverage(summary)
                        releaseCenterRecentTasks(summary)
                    }
                    .padding(16)
                }
            } else {
                VStack(spacing: 12) {
                    if viewModel.isLoadingReleaseEvaluation {
                        ProgressView()
                    } else {
                        Image(systemName: "chart.line.uptrend.xyaxis")
                            .font(.system(size: 32))
                            .foregroundColor(.secondary.opacity(0.4))
                    }
                    Text(viewModel.releaseEvaluationError ?? appPreferences.text("tasks.releaseEvaluation.empty"))
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .background(theme.panelBackground)
    }

    private func releaseCenterOverview(_ summary: ReleaseEvaluationSummary) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(appPreferences.text("tasks.releaseCenter.overview"))
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(theme.primaryText)

            HStack(spacing: 8) {
                releaseCenterMetric(
                    appPreferences.text("tasks.releaseEvaluation.readiness"),
                    localizedReadiness(summary.releaseReadiness),
                    summary.releaseReadiness
                )
                releaseCenterMetric(appPreferences.text("tasks.releaseEvaluation.passRate"), "\(summary.passRatePercent)%", summary.passRate >= 1 ? "passed" : "partial")
                releaseCenterMetric(appPreferences.text("tasks.releaseEvaluation.score"), summary.averageFinalQualityScore.map(String.init) ?? "-", (summary.averageFinalQualityScore ?? 0) >= 80 ? "passed" : "partial")
                releaseCenterMetric(appPreferences.text("tasks.releaseEvaluation.trend"), localizedTrend(summary.qualityTrend?.direction ?? "no_data"), summary.qualityTrend?.direction == "regressing" ? "failed" : "passed")
                releaseCenterMetric(appPreferences.text("tasks.releaseCenter.repairs"), "\(summary.totalRemediationCount)", summary.totalRemediationCount == 0 ? "passed" : "partial")
            }

            if let recommendation = summary.recommendation, !recommendation.isEmpty {
                Text(recommendation)
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if !summary.topRisks.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text(appPreferences.text("tasks.releaseCenter.risks"))
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(theme.strongText)
                    ForEach(summary.topRisks.prefix(4)) { risk in
                        HStack(alignment: .top, spacing: 7) {
                            Circle()
                                .fill(statusColor(risk.severity == "high" ? "failed" : "partial"))
                                .frame(width: 7, height: 7)
                                .padding(.top, 5)
                            Text(risk.message)
                                .font(.system(size: 11))
                                .foregroundColor(.secondary)
                                .lineLimit(2)
                        }
                    }
                }
            }
        }
        .padding(14)
        .background(theme.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private func releaseCenterChecklist(_ summary: ReleaseEvaluationSummary) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(appPreferences.text("tasks.releaseCenter.checklist"))
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(theme.primaryText)

            ForEach(summary.readinessChecks) { check in
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: iconName(for: check.status))
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(statusColor(check.status))
                        .frame(width: 18)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(check.label)
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(theme.strongText)
                        Text(check.message)
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    Spacer()
                }
                .padding(10)
                .background(theme.fieldBackground)
                .clipShape(RoundedRectangle(cornerRadius: 6))
            }
        }
        .padding(14)
        .background(theme.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private func releaseCenterCoverage(_ summary: ReleaseEvaluationSummary) -> some View {
        HStack(alignment: .top, spacing: 12) {
            coveragePanel(
                title: appPreferences.text("tasks.releaseCenter.probeCoverage"),
                rows: coverageRows(summary.probeCoverage)
            )
            coveragePanel(
                title: appPreferences.text("tasks.releaseCenter.stackCoverage"),
                rows: sortedRows(summary.stackCoverage)
            )
            coveragePanel(
                title: appPreferences.text("tasks.releaseCenter.agentCoverage"),
                rows: sortedRows(summary.agentCoverage)
            )
        }
    }

    private func releaseCenterRecentTasks(_ summary: ReleaseEvaluationSummary) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(appPreferences.text("tasks.releaseCenter.recent"))
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(theme.primaryText)

            ForEach(summary.recentEvaluations) { task in
                HStack(alignment: .top, spacing: 10) {
                    Circle()
                        .fill(statusColor(task.benchmarkStatus ?? task.qualityGate ?? task.status))
                        .frame(width: 8, height: 8)
                        .padding(.top, 5)

                    VStack(alignment: .leading, spacing: 4) {
                        HStack(spacing: 8) {
                            Text(shortTaskId(task.taskId))
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundColor(theme.strongText)
                            Text(task.benchmarkStatus ?? task.qualityGate ?? task.status)
                                .font(.system(size: 10, weight: .medium))
                                .foregroundColor(statusColor(task.benchmarkStatus ?? task.qualityGate ?? task.status))
                            if let score = task.finalQualityScore {
                                Text("score \(score)")
                                    .font(.system(size: 10, weight: .medium))
                                    .foregroundColor(.secondary)
                            }
                        }
                        Text(task.description)
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                            .lineLimit(2)
                        if let audit = task.auditTrace {
                            Text(String(format: appPreferences.text("tasks.releaseEvaluation.probes"), audit.passedProbeCount, audit.failedProbeCount))
                                .font(.system(size: 10))
                                .foregroundColor(.secondary.opacity(0.8))
                        }
                    }

                    Spacer()

                    Button(action: { viewModel.loadTaskEvidenceBundle(task.taskId, releaseGate: isReleaseE2ETaskDescription(task.description)) }) {
                        Image(systemName: "doc.text.magnifyingglass")
                            .font(.system(size: 12))
                            .foregroundColor(Color(hex: "#4d6bfe"))
                            .frame(width: 26, height: 26)
                            .background(Color(hex: "#4d6bfe").opacity(0.12))
                            .clipShape(RoundedRectangle(cornerRadius: 6))
                    }
                    .buttonStyle(.plain)
                    .help(appPreferences.text("tasks.evidence.view"))

                    Button(action: { viewModel.selectTask(task.taskId) }) {
                        Image(systemName: "arrow.right")
                            .font(.system(size: 11, weight: .bold))
                            .foregroundColor(.secondary)
                            .frame(width: 26, height: 26)
                            .background(theme.fieldBackground)
                            .clipShape(RoundedRectangle(cornerRadius: 6))
                    }
                    .buttonStyle(.plain)
                    .help(appPreferences.text("tasks.releaseCenter.openTask"))
                }
                .padding(10)
                .background(theme.fieldBackground)
                .clipShape(RoundedRectangle(cornerRadius: 8))
            }
        }
        .padding(14)
        .background(theme.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private func releaseCenterMetric(_ title: String, _ value: String, _ status: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.system(size: 10, weight: .medium))
                .foregroundColor(.secondary)
            Text(value)
                .font(.system(size: 16, weight: .semibold))
                .foregroundColor(theme.strongText)
                .lineLimit(1)
            Rectangle()
                .fill(statusColor(status))
                .frame(height: 2)
                .clipShape(RoundedRectangle(cornerRadius: 1))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(theme.fieldBackground)
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    private func coveragePanel(title: String, rows: [(String, String)]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(theme.strongText)
            if rows.isEmpty {
                Text("-")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            } else {
                ForEach(rows.prefix(8), id: \.0) { row in
                    HStack {
                        Text(row.0)
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                            .lineLimit(1)
                        Spacer()
                        Text(row.1)
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundColor(theme.strongText)
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .topLeading)
        .padding(14)
        .background(theme.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private func coverageRows(_ coverage: ReleaseEvaluationProbeCoverage?) -> [(String, String)] {
        guard let coverage else { return [] }
        let required = coverage.requiredProbeTypes.map { probe in
            let passed = coverage.passed[probe] ?? 0
            let failed = coverage.failed[probe] ?? 0
            let manual = coverage.manualRequired[probe] ?? 0
            return (probe, "\(passed)P \(failed)F \(manual)M")
        }
        let extra = coverage.passed.keys
            .filter { !coverage.requiredProbeTypes.contains($0) }
            .sorted()
            .map { ($0, "\(coverage.passed[$0] ?? 0)P") }
        return required + extra
    }

    private func sortedRows(_ values: [String: Int]) -> [(String, String)] {
        values
            .sorted { left, right in
                if left.value == right.value { return left.key < right.key }
                return left.value > right.value
            }
            .map { ($0.key, "\($0.value)") }
    }

    private func localizedReadiness(_ readiness: String) -> String {
        appPreferences.text("tasks.releaseEvaluation.readiness.\(readiness)")
    }

    private func localizedTrend(_ trend: String) -> String {
        appPreferences.text("tasks.releaseEvaluation.trend.\(trend)")
    }

    private func shortTaskId(_ taskId: String) -> String {
        if taskId.count <= 12 { return taskId }
        return String(taskId.prefix(12))
    }

    private func isReleaseE2ETaskDescription(_ description: String) -> Bool {
        description.contains("Release E2E scenario:")
            || description.contains("Scenario ID: cross_agent_full_delivery_v1")
    }

    private func iconName(for status: String) -> String {
        switch status {
        case "passed", "ready": return "checkmark.circle.fill"
        case "failed", "blocked": return "xmark.octagon.fill"
        default: return "exclamationmark.circle.fill"
        }
    }

    private func statusColor(_ status: String) -> Color {
        switch status {
        case "passed", "ready", "completed": return Color(hex: "#30d158")
        case "failed", "blocked": return Color(hex: "#FF453A")
        default: return Color(hex: "#ff9f0a")
        }
    }
}

struct TaskEvidenceBundleSheet: View {
    let bundle: TaskEvidenceBundle
    let isLoading: Bool
    let errorMessage: String?
    let exportedURL: URL?
    let onExport: () -> Void
    let onOpenExport: () -> Void

    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(appPreferences.text("tasks.evidence.title"))
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(theme.primaryText)
                    Text(bundle.taskId)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(.secondary)
                }

                Spacer()

                Button(action: onExport) {
                    Label(appPreferences.text("tasks.evidence.export"), systemImage: "square.and.arrow.down")
                        .font(.system(size: 12, weight: .medium))
                }
                .buttonStyle(.plain)
                .disabled(isLoading)

                if exportedURL != nil {
                    Button(action: onOpenExport) {
                        Label(appPreferences.text("tasks.evidence.openExport"), systemImage: "folder")
                            .font(.system(size: 12, weight: .medium))
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(16)

            Divider().opacity(0.5)

            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    HStack(spacing: 8) {
                        evidenceMetric(appPreferences.text("tasks.delivery"), bundle.taskStatus, bundle.taskStatus)
                        evidenceMetric(appPreferences.text("tasks.score"), "\(bundle.benchmark.summary.minQualityScore)", bundle.benchmark.status)
                        evidenceMetric(appPreferences.text("tasks.evidence.benchmark"), bundle.benchmark.status, bundle.benchmark.status)
                        evidenceMetric(appPreferences.text("tasks.observability.remediation"), "\(bundle.benchmark.summary.maxRemediationAttempts)", bundle.benchmark.summary.maxRemediationAttempts == 0 ? "passed" : "partial")
                    }

                    Text(bundle.releaseReadinessSummary)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.secondary)

                    if let errorMessage, !errorMessage.isEmpty {
                        Text(errorMessage)
                            .font(.system(size: 11))
                            .foregroundColor(Color(hex: "#ff9f0a"))
                    }

                    if let exportedURL {
                        Text(String(format: appPreferences.text("tasks.evidence.exported"), exportedURL.path))
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                            .lineLimit(2)
                    }

                    evidenceAuditSection
                    evidenceScenarioSection
                }
                .padding(16)
            }
        }
        .frame(minWidth: 720, minHeight: 560)
        .background(theme.panelBackground)
    }

    private var evidenceAuditSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(appPreferences.text("tasks.evidence.audit"))
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(theme.primaryText)

            HStack(spacing: 8) {
                evidenceMetric("Read-only", bundle.audit.readOnly ? "yes" : "no", bundle.audit.readOnly ? "passed" : "failed")
                evidenceMetric("Redacted", bundle.audit.secretsRedacted ? "yes" : "no", bundle.audit.secretsRedacted ? "passed" : "failed")
                evidenceMetric("Repair", bundle.audit.repairOrResumeTriggered ? "triggered" : "none", bundle.audit.repairOrResumeTriggered ? "failed" : "passed")
            }

            evidenceList(title: appPreferences.text("tasks.evidence.expectedFiles"), values: bundle.audit.expectedFiles)
            evidenceList(title: appPreferences.text("tasks.evidence.requiredProbes"), values: bundle.audit.requiredProbes)
        }
        .padding(14)
        .background(theme.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private var evidenceScenarioSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(appPreferences.text("tasks.evidence.benchmark"))
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(theme.primaryText)

            ForEach(bundle.benchmark.scenarios) { scenario in
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text(scenario.taskId)
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(theme.strongText)
                        Text(scenario.status)
                            .font(.system(size: 11, weight: .medium))
                            .foregroundColor(statusColor(scenario.status))
                        Spacer()
                        Text("score \(scenario.qualityScore)")
                            .font(.system(size: 11, weight: .medium))
                            .foregroundColor(.secondary)
                    }

                    evidenceList(title: appPreferences.text("tasks.evidence.producedFiles"), values: scenario.producedFiles)
                    evidenceList(title: appPreferences.text("tasks.evidence.failures"), values: scenario.failures)

                    if !scenario.checks.isEmpty {
                        LazyVGrid(columns: [GridItem(.adaptive(minimum: 160), spacing: 8)], spacing: 8) {
                            ForEach(scenario.checks.keys.sorted(), id: \.self) { key in
                                HStack(spacing: 6) {
                                    Image(systemName: scenario.checks[key] == true ? "checkmark.circle.fill" : "xmark.octagon.fill")
                                        .foregroundColor(scenario.checks[key] == true ? Color(hex: "#30d158") : Color(hex: "#FF453A"))
                                    Text(key)
                                        .font(.system(size: 10))
                                        .foregroundColor(.secondary)
                                        .lineLimit(1)
                                }
                                .padding(7)
                                .background(theme.fieldBackground)
                                .clipShape(RoundedRectangle(cornerRadius: 6))
                            }
                        }
                    }
                }
                .padding(12)
                .background(theme.fieldBackground)
                .clipShape(RoundedRectangle(cornerRadius: 8))
            }
        }
        .padding(14)
        .background(theme.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private func evidenceMetric(_ title: String, _ value: String, _ status: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title)
                .font(.system(size: 10, weight: .medium))
                .foregroundColor(.secondary)
                .lineLimit(1)
            Text(value)
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(theme.strongText)
                .lineLimit(1)
            Rectangle()
                .fill(statusColor(status))
                .frame(height: 2)
                .clipShape(RoundedRectangle(cornerRadius: 1))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(9)
        .background(theme.fieldBackground)
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    private func evidenceList(title: String, values: [String]) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(title)
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(theme.strongText)
            if values.isEmpty {
                Text("-")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            } else {
                ForEach(values.prefix(12), id: \.self) { value in
                    Text(value)
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                }
            }
        }
    }

    private func statusColor(_ status: String) -> Color {
        switch status {
        case "passed", "completed": return Color(hex: "#30d158")
        case "failed", "blocked": return Color(hex: "#FF453A")
        default: return Color(hex: "#ff9f0a")
        }
    }
}

struct BackendUnavailableBanner: View {
    let message: String?
    let onRetry: () -> Void

    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(Color(hex: "#FF9F0A"))
                .frame(width: 16, height: 16)

            VStack(alignment: .leading, spacing: 6) {
                Text(appPreferences.text("tasks.backendUnavailable.title"))
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(theme.strongText)

                Text(message?.isEmpty == false ? message! : appPreferences.text("tasks.backendUnavailable.sidebar"))
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                    .lineLimit(3)

                Button(action: onRetry) {
                    Text(appPreferences.text("tasks.backendUnavailable.retry"))
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(Color(hex: "#4D6BFE"))
                }
                .buttonStyle(.plain)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(10)
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(theme.hoverBackground)
        )
    }
}

struct TaskRowView: View {
    let task: TaskOrchestrationViewModel.TaskSummary
    let isSelected: Bool
    let onTap: () -> Void

    @State private var isHovered = false
    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    private var statusColor: Color {
        switch task.status {
        case "running": return Color(hex: "#4d6bfe")
        case "completed": return Color(hex: "#30d158")
        case "failed": return Color(hex: "#FF453A")
        case "completed_with_failures": return Color(hex: "#ff9f0a")
        case "paused": return Color(hex: "#ff9f0a")
        case "pending": return Color(hex: "#8e8e93")
        case "suspended": return Color(hex: "#8e8e93")
        default: return Color(hex: "#8e8e93")
        }
    }

    var body: some View {
        HStack(spacing: 0) {
            Rectangle()
                .fill(isSelected ? Color(hex: "#B58AE3") : Color.clear)
                .frame(width: 3)

            VStack(alignment: .leading, spacing: 4) {
                Text(task.description)
                    .font(.system(size: 12, weight: .medium))
                    .lineLimit(2)
                    .foregroundColor(theme.strongText)

                HStack(spacing: 6) {
                    Circle()
                        .fill(statusColor)
                        .frame(width: 6, height: 6)

                    Text(localizedTaskStatus(task.status, preferences: appPreferences))
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)

                    if task.totalCount > 0 {
                        Text("\(task.completedCount)/\(task.totalCount)")
                            .font(.system(size: 9))
                            .foregroundColor(.secondary.opacity(0.7))
                    }
                }
            }
            .padding(.leading, 10)
            .padding(.vertical, 8)

            Spacer()

            if task.status == "running" {
                ProgressView()
                    .controlSize(.mini)
                    .scaleEffect(0.7)
                    .padding(.trailing, 8)
            }
        }
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(backgroundColor)
                .padding(.horizontal, 8)
        )
        .contentShape(Rectangle())
        .onTapGesture(perform: onTap)
        .onHover { hovering in
            withAnimation(.easeInOut(duration: 0.1)) {
                isHovered = hovering
            }
        }
        .id(task.taskId)
    }

    private var backgroundColor: Color {
        if isSelected {
            return Color(hex: "#B58AE3").opacity(0.2)
        }
        if isHovered {
            return theme.hoverBackground
        }
        return Color.clear
    }
}

struct TaskDetailPanel: View {
    @ObservedObject var viewModel: TaskOrchestrationViewModel
    @ObservedObject var settingsVM: SettingsViewModel

    @State private var isDescriptionExpanded = false
    @State private var isHealthExpanded = false
    @State private var isObservabilityExpanded = true
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
                TaskNewTaskForm(viewModel: viewModel, settingsVM: settingsVM)
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
                VStack(spacing: 16) {
                    Image(systemName: "list.bullet.rectangle")
                        .font(.system(size: 40, weight: .light))
                        .foregroundColor(.secondary.opacity(0.4))

                    Text(appPreferences.text("tasks.none.title"))
                        .font(.system(size: 14, weight: .medium))
                        .foregroundColor(.secondary)

                    Text(appPreferences.text("tasks.none.subtitle"))
                        .font(.system(size: 12))
                        .foregroundColor(.secondary.opacity(0.6))

                    Button(action: { viewModel.enterCreateMode() }) {
                        HStack(spacing: 6) {
                            Image(systemName: "plus.circle.fill")
                            Text(appPreferences.text("tasks.new"))
                        }
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.white)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                        .background(Color(hex: "#B58AE3"))
                        .cornerRadius(8)
                    }
                    .buttonStyle(.plain)
                    .padding(.top, 8)
                }
            }
        }
    }

    private var orchestratorPluginUnavailableView: some View {
        VStack(spacing: 14) {
            Image(systemName: "puzzlepiece.extension")
                .font(.system(size: 40, weight: .light))
                .foregroundColor(Color(hex: "#B58AE3").opacity(0.78))

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
                        Button(action: { viewModel.cancelTask(task.taskId) }) {
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

    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
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

    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    private var trimmedTaskDescription: String {
        taskDescription.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var trimmedProjectDir: String {
        projectDir.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var projectDirectoryExists: Bool {
        guard !trimmedProjectDir.isEmpty else { return false }
        var isDirectory: ObjCBool = false
        return FileManager.default.fileExists(atPath: trimmedProjectDir, isDirectory: &isDirectory) && isDirectory.boolValue
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
                                .foregroundColor(Color(hex: "#B58AE3"))
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(Color(hex: "#B58AE3").opacity(0.16))
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
                                .background(selectedDeliveryTaskTypes.contains(type) ? Color(hex: "#B58AE3").opacity(0.22) : theme.fieldBackground)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 8)
                                        .stroke(selectedDeliveryTaskTypes.contains(type) ? Color(hex: "#B58AE3").opacity(0.65) : theme.divider, lineWidth: 1)
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
                        AccessibleTextField(
                            placeholder: "/path/to/project",
                            text: $projectDir,
                            textColor: NSColor.labelColor,
                            font: .systemFont(ofSize: 13)
                        )
                            .frame(height: 16)
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
                        .background(viewModel.isLoading ? Color(hex: "#B58AE3").opacity(0.5) : Color(hex: "#B58AE3"))
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
            if !availableOwnerAgents.contains(where: { $0.id == selectedOwnerAgent }) {
                selectedOwnerAgent = "auto"
            }
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
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.title = appPreferences.text("tasks.selectProjectDirectory")

        if panel.runModal() == .OK, let url = panel.url {
            projectDir = url.path
        }
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
                    .foregroundColor(Color(hex: "#B58AE3"))
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
                                .foregroundColor(Color(hex: "#B58AE3"))
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
                        .foregroundColor(Color(hex: "#B58AE3"))
                        .frame(width: 26, height: 22)
                        .background(Color(hex: "#B58AE3").opacity(0.16))
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

struct AgentIconChip: View {
    let agent: AgentOption
    let isSelected: Bool
    let onTap: () -> Void

    @Environment(\.colorScheme) private var colorScheme
    private let chipSize: CGFloat = 36
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    var body: some View {
        Button(action: onTap) {
            if agent.id == "auto" {
                Image(systemName: "wand.and.stars")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundColor(isSelected ? .white : theme.mutedText)
                    .frame(width: chipSize, height: chipSize)
                    .background(isSelected ? Color(hex: "#B58AE3").opacity(0.9) : theme.controlBackground)
                    .overlay(
                        RoundedRectangle(cornerRadius: 9)
                            .stroke(isSelected ? Color(hex: "#B58AE3") : theme.divider, lineWidth: 1)
                    )
                    .cornerRadius(9)
            } else {
                AgentIconView(name: agent.iconName, size: chipSize, isCloudLLM: agent.isCloudLLM)
                    .frame(width: chipSize, height: chipSize)
                    .overlay(
                        RoundedRectangle(cornerRadius: 9)
                            .stroke(isSelected ? Color(hex: "#B58AE3") : Color.clear, lineWidth: 1.5)
                    )
            }
        }
        .buttonStyle(.plain)
        .frame(width: chipSize, height: chipSize)
        .help(agent.name)
    }
}

struct AgentIdentityBadge: View {
    let agentId: String
    let ownerAgentId: String?
    var size: CGFloat = 22
    @EnvironmentObject private var appPreferences: AppPreferences

    private var resolvedAgentId: String {
        let normalized = agentId.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if normalized.contains("owner"), let ownerAgentId, !ownerAgentId.isEmpty {
            return AgentIDs.normalized(ownerAgentId.lowercased()) ?? ownerAgentId.lowercased()
        }
        return AgentIDs.normalized(normalized) ?? normalized
    }

    private var isAuto: Bool {
        resolvedAgentId == "auto" || resolvedAgentId.isEmpty || resolvedAgentId == "owner"
    }

    private var isCloudLLM: Bool {
        [
            "openai", "anthropic", "deepseek", "minimax", "bailian", "moonshot",
            "zhipu", "volcengine", "google", "xai", "mistral", "groq", "cohere",
            "openrouter", "together", "fireworks", "agnes"
        ].contains(resolvedAgentId)
    }

    private var iconName: String {
        "agent.\(resolvedAgentId)"
    }

    private var displayName: String {
        switch resolvedAgentId {
        case "auto": return appPreferences.text("tasks.auto")
        case "openclaw": return "OpenClaw"
        case "hermes": return "Hermes"
        case "claude": return "Claude Code"
        case "cloudcode-desktop": return "CloudCode Desktop"
        case "deepseek": return "DeepSeek"
        case "minimax": return "MiniMax"
        case "agnes": return "Agnes"
        case "owner": return appPreferences.text("tasks.owner")
        case "": return appPreferences.text("tasks.unknownAgent")
        default: return resolvedAgentId
        }
    }

    var body: some View {
        Group {
            if isAuto {
                Image(systemName: "wand.and.stars")
                    .font(.system(size: size * 0.5, weight: .semibold))
                    .foregroundColor(.white)
                    .frame(width: size, height: size)
                    .background(Color(hex: "#ff9f0a"))
                    .clipShape(RoundedRectangle(cornerRadius: size * 0.22))
            } else {
                AgentIconView(name: iconName, size: size, isCloudLLM: isCloudLLM)
                    .frame(width: size, height: size)
            }
        }
        .help(displayName)
    }
}

struct SubtaskListView: View {
    let task: TaskOrchestrationViewModel.TaskDetail
    @ObservedObject var viewModel: TaskOrchestrationViewModel
    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(String(format: appPreferences.text("tasks.subtasks"), task.subtasks.count))
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(theme.primaryText)

            VStack(spacing: 8) {
                ForEach(task.subtasks) { subtask in
                    SubtaskCard(subtask: subtask, ownerAgentId: task.ownerAgent)
                }
            }
        }
    }
}

struct DAGVisualization: View {
    let task: TaskOrchestrationViewModel.TaskDetail
    @ObservedObject var viewModel: TaskOrchestrationViewModel

    @State private var selectedSubtask: TaskOrchestrationViewModel.SubtaskDetail?
    @State private var isProgressExpanded = true
    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Button(action: { isProgressExpanded.toggle() }) {
                HStack(spacing: 6) {
                    Text(appPreferences.text("tasks.progress"))
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(theme.primaryText)

                    HStack(alignment: .bottom, spacing: 1) {
                        Rectangle()
                            .fill(Color(hex: "#FFBFBB"))
                            .frame(width: 3, height: 8)
                            .cornerRadius(1)
                        Rectangle()
                            .fill(Color(hex: "#FFE4AB"))
                            .frame(width: 3, height: 10)
                            .cornerRadius(1)
                        Rectangle()
                            .fill(Color(hex: "#A8E9B2"))
                            .frame(width: 3, height: 12)
                            .cornerRadius(1)
                    }

                    Image(systemName: isProgressExpanded ? "chevron.down" : "chevron.right")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.secondary)

                    Spacer()
                }
            }
            .buttonStyle(.plain)

            if isProgressExpanded {
                ScrollView(.horizontal, showsIndicators: false) {
                HStack(alignment: .top, spacing: 0) {
                    ForEach(Array(task.waves.enumerated()), id: \.element.waveId) { index, wave in
                        WaveColumnView(
                            wave: wave,
                            isBlocked: wave.isBlocked,
                            ownerAgentId: task.ownerAgent,
                            onSubtaskTap: { subtask in
                                selectedSubtask = subtask
                            }
                        )

                        if index < task.waves.count - 1 {
                            Image(systemName: "arrow.right")
                                .font(.system(size: 14))
                                .foregroundColor(.secondary.opacity(0.4))
                                .padding(.horizontal, 12)
                                .padding(.top, 24)
                        }
                    }
                }
                .padding(.vertical, 8)
                }
            }
        }
        .sheet(item: $selectedSubtask) { subtask in
            SubtaskDetailSheet(subtask: subtask)
        }
    }
}

struct WaveColumnView: View {
    let wave: TaskOrchestrationViewModel.WaveDetail
    let isBlocked: Bool
    let ownerAgentId: String?
    let onSubtaskTap: (TaskOrchestrationViewModel.SubtaskDetail) -> Void
    @Environment(\.colorScheme) private var colorScheme
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Text(wave.waveNumber == 0 ? "Wave 0" : "Wave \(wave.waveNumber)")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(.secondary)

                Circle()
                    .fill(statusColor)
                    .frame(width: 6, height: 6)

                Spacer()

                if wave.isRevalidating {
                    Image(systemName: "arrow.triangle.2.circlepath")
                        .font(.system(size: 10))
                        .foregroundColor(Color(hex: "#4d6bfe"))
                }

                if isBlocked {
                    Image(systemName: "lock.fill")
                        .font(.system(size: 10))
                        .foregroundColor(Color(hex: "#ff9f0a"))
                }

                if let governanceStatus = wave.governanceStatus, governanceStatus != "pending" {
                    Text(governanceStatusText(governanceStatus, blockedByWave: wave.blockedByWave))
                        .font(.system(size: 10))
                        .foregroundColor(governanceColor(governanceStatus))
                        .lineLimit(1)
                }
            }

            if let ownerDecision = wave.ownerDecision,
               let action = ownerDecision.recommendedAction,
               action != "approve" {
                HStack {
                    Spacer()
                    Text(ownerDecisionText(ownerDecision))
                        .font(.system(size: 10))
                        .foregroundColor(Color(hex: "#ff9f0a"))
                        .lineLimit(2)
                }
            }

            if !wave.subtasks.isEmpty {
                VStack(spacing: 8) {
                    ForEach(wave.subtasks) { subtask in
                        SubtaskCard(subtask: subtask, ownerAgentId: ownerAgentId)
                            .onTapGesture {
                                onSubtaskTap(subtask)
                            }
                    }
                }
                .opacity(isBlocked ? 0.5 : 1)
            }

            if let fixRounds = wave.fixRounds {
                ForEach(fixRounds) { fixRound in
                    FixRoundView(fixRound: fixRound)
                }
            }
        }
        .padding(12)
        .background(theme.subtleBackground)
        .cornerRadius(12)
    }

    private var statusColor: Color {
        if wave.isRevalidating {
            return Color(hex: "#4d6bfe")
        }
        switch wave.governanceStatus ?? wave.status {
        case "revalidating": return Color(hex: "#4d6bfe")
        case "blocked", "blocked_by_prior_wave", "needs_fix": return Color(hex: "#ff9f0a")
        case "running": return Color(hex: "#4d6bfe")
        case "completed": return Color(hex: "#30d158")
        case "failed": return Color(hex: "#FF453A")
        default: return Color(hex: "#8e8e93")
        }
    }

    private func governanceStatusText(_ status: String, blockedByWave: Int?) -> String {
        switch status {
        case "approved":
            return "Wave Gate Approved"
        case "blocked":
            if let blockedByWave {
                return "Blocked by Wave \(blockedByWave)"
            }
            return "Wave Gate Blocked"
        case "revalidating":
            return "Revalidating Downstream"
        case "needs_fix":
            return "Needs Fix"
        default:
            return status.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }

    private func governanceColor(_ status: String) -> Color {
        switch status {
        case "approved":
            return Color(hex: "#30d158")
        case "blocked", "needs_fix":
            return Color(hex: "#ff9f0a")
        case "revalidating":
            return Color(hex: "#4d6bfe")
        default:
            return .secondary
        }
    }
}

struct SubtaskCard: View {
    let subtask: TaskOrchestrationViewModel.SubtaskDetail
    let ownerAgentId: String?

    @State private var isHovered = false
    @Environment(\.colorScheme) private var colorScheme
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    private var borderColor: Color {
        switch subtask.status {
        case "running": return Color(hex: "#4d6bfe")
        case "completed": return Color(hex: "#30d158")
        case "failed": return Color(hex: "#FF453A")
        case "pending": return Color(hex: "#8e8e93")
        default: return Color(hex: "#8e8e93")
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(subtask.description)
                .font(.system(size: 11))
                .foregroundColor(theme.bodyText)
                .lineLimit(3)
                .multilineTextAlignment(.leading)

            HStack(spacing: 6) {
                AgentIdentityBadge(agentId: subtask.agentId, ownerAgentId: ownerAgentId, size: 22)

                Spacer()

                if subtask.status == "running" {
                    if let runningForSeconds = subtask.runningForSeconds, runningForSeconds >= 1 {
                        Text(formatDuration(runningForSeconds))
                            .font(.system(size: 9))
                            .foregroundColor(Color(hex: "#4d6bfe"))
                    } else {
                        ProgressView()
                            .controlSize(.mini)
                            .scaleEffect(0.6)
                    }
                } else if let duration = subtask.duration {
                    Text(String(format: "%.1fs", duration))
                        .font(.system(size: 9))
                        .foregroundColor(.secondary)
                }
            }

            if let blockedText = subtaskBlockedText {
                Text(blockedText)
                    .font(.system(size: 9))
                    .foregroundColor(Color(hex: "#ff9f0a"))
                    .lineLimit(2)
            }

            if subtask.status == "running" {
                GeometryReader { geo in
                    RoundedRectangle(cornerRadius: 2)
                        .fill(theme.controlBackground)
                        .frame(height: 4)
                        .overlay(
                            RoundedRectangle(cornerRadius: 2)
                                .fill(Color(hex: "#4d6bfe"))
                                .frame(width: geo.size.width * subtask.progress, height: 4)
                        )
                }
                .frame(height: 4)
            }
        }
        .padding(10)
        .frame(width: 200)
        .background(theme.cardBackground)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(isHovered ? borderColor.opacity(0.8) : borderColor.opacity(0.4), lineWidth: isHovered ? 2 : 1)
        )
        .cornerRadius(8)
        .onHover { hovering in
            withAnimation(.easeInOut(duration: 0.1)) {
                isHovered = hovering
            }
        }
    }

    private var subtaskBlockedText: String? {
        guard subtask.status == "pending" else { return nil }
        if !subtask.waitingOnDependencies.isEmpty {
            return "Waiting for " + subtask.waitingOnDependencies.prefix(2).joined(separator: ", ")
        }
        guard let blockedReason = subtask.blockedReason else { return nil }
        switch blockedReason {
        case "blocked_by_prior_wave":
            return "Blocked by prior wave"
        case "wave_revalidating":
            return "Wave revalidating"
        case "wave_gate_blocked":
            return "Wave gate blocked"
        default:
            return blockedReason.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }

    private func formatDuration(_ seconds: Double) -> String {
        if seconds >= 60 {
            return String(format: "%.0fm", seconds / 60)
        }
        return String(format: "%.0fs", seconds)
    }
}

struct FixRoundView: View {
    let fixRound: TaskOrchestrationViewModel.FixRoundDetail
    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: "wrench.fill")
                .font(.system(size: 10))
                .foregroundColor(Color(hex: "#ff9f0a"))

            Text(String(format: appPreferences.text("tasks.fixRound"), fixRound.roundNumber))
                .font(.system(size: 10, weight: .medium))
                .foregroundColor(theme.bodyText)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(Color(hex: "#ff9f0a").opacity(0.15))
        .cornerRadius(6)
    }
}

struct SubtaskDetailSheet: View {
    let subtask: TaskOrchestrationViewModel.SubtaskDetail

    @Environment(\.dismiss) private var dismiss
    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text(appPreferences.text("tasks.subtaskDetails"))
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(theme.primaryText)

                Spacer()

                Button(action: { dismiss() }) {
                    Image(systemName: "xmark")
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
            }

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(appPreferences.text("tasks.description"))
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(.secondary)

                        Text(subtask.description)
                            .font(.system(size: 13))
                            .foregroundColor(theme.primaryText)
                    }

                    HStack(spacing: 20) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(appPreferences.text("tasks.status"))
                                .font(.system(size: 11))
                                .foregroundColor(.secondary)

                            Text(localizedTaskStatus(subtask.status, preferences: appPreferences))
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(statusColor)
                        }

                        VStack(alignment: .leading, spacing: 4) {
                            Text(appPreferences.text("tasks.agent"))
                                .font(.system(size: 11))
                                .foregroundColor(.secondary)

                            Text(subtask.agentId)
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(theme.primaryText)
                        }

                        if let duration = subtask.duration {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(appPreferences.text("tasks.duration"))
                                    .font(.system(size: 11))
                                    .foregroundColor(.secondary)

                                Text(String(format: "%.1fs", duration))
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundColor(theme.primaryText)
                            }
                        }

                        if subtask.status == "running", let runningForSeconds = subtask.runningForSeconds {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(appPreferences.text("tasks.runningFor"))
                                    .font(.system(size: 11))
                                    .foregroundColor(.secondary)

                                Text(String(format: "%.0fs", runningForSeconds))
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundColor(Color(hex: "#4d6bfe"))
                            }
                        }
                    }

                    if !subtask.waitingOnDependencies.isEmpty || subtask.blockedReason != nil {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(appPreferences.text("tasks.waitingState"))
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(Color(hex: "#ff9f0a"))

                            if !subtask.waitingOnDependencies.isEmpty {
                                Text(String(format: appPreferences.text("tasks.waitingOn"), subtask.waitingOnDependencies.joined(separator: ", ")))
                                    .font(.system(size: 12, design: .monospaced))
                                    .foregroundColor(theme.primaryText)
                            }

                            if let blockedReason = subtask.blockedReason {
                                Text(blockedReason.replacingOccurrences(of: "_", with: " ").capitalized)
                                    .font(.system(size: 12))
                                    .foregroundColor(theme.bodyText)
                            }
                        }
                        .padding(10)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color(hex: "#ff9f0a").opacity(0.1))
                        .cornerRadius(8)
                    }

                    if let outputFile = subtask.outputFile {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(appPreferences.text("tasks.outputFile"))
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(.secondary)

                            Text(outputFile)
                                .font(.system(size: 12, design: .monospaced))
                                .foregroundColor(Color(hex: "#30d158"))
                                .padding(8)
                                .background(Color(hex: "#30d158").opacity(0.1))
                                .cornerRadius(6)
                        }
                    }

                    if let errorMessage = subtask.errorMessage {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(appPreferences.text("tasks.errorMessage"))
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(Color(hex: "#FF453A"))

                            Text(errorMessage)
                                .font(.system(size: 12, design: .monospaced))
                                .foregroundColor(theme.primaryText)
                                .padding(10)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .background(Color(hex: "#FF453A").opacity(0.1))
                                .cornerRadius(8)
                        }
                    }

                    if let fixPlan = subtask.fixPlan {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(appPreferences.text("tasks.fixPlan"))
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(Color(hex: "#ff9f0a"))

                            Text(fixPlan)
                                .font(.system(size: 12))
                                .foregroundColor(theme.primaryText)
                                .padding(10)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .background(Color(hex: "#ff9f0a").opacity(0.1))
                                .cornerRadius(8)
                        }
                    }
                }
            }
        }
        .padding(20)
        .frame(width: 500, height: 400)
        .background(theme.panelBackground)
    }

    private var statusColor: Color {
        switch subtask.status {
        case "running": return Color(hex: "#4d6bfe")
        case "completed": return Color(hex: "#30d158")
        case "failed": return Color(hex: "#FF453A")
        case "pending": return Color(hex: "#8e8e93")
        default: return Color(hex: "#8e8e93")
        }
    }
}

private func ownerDecisionText(_ decision: TaskOrchestrationViewModel.OwnerDecisionSummary) -> String {
    let action = decision.recommendedAction?.replacingOccurrences(of: "_", with: " ").capitalized ?? "Owner Decision"
    if let rootScope = decision.rootCauseScope, let rootWave = decision.rootCauseWave {
        return "\(action) · \(rootScope.replacingOccurrences(of: "_", with: " ")) W\(rootWave)"
    }
    if let rootScope = decision.rootCauseScope {
        return "\(action) · \(rootScope.replacingOccurrences(of: "_", with: " "))"
    }
    return action
}

@MainActor
private func localizedTaskStatus(_ status: String, preferences: AppPreferences) -> String {
    let key = "status.\(status)"
    let localized = preferences.text(key)
    if localized != key {
        return localized
    }
    return status
        .split(separator: "_")
        .map { $0.prefix(1).uppercased() + $0.dropFirst() }
        .joined(separator: " ")
}

struct ArtifactFileList: View {
    let artifacts: [TaskOrchestrationViewModel.Artifact]

    @State private var isArtifactsExpanded = false
    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    private var displayArtifacts: [TaskOrchestrationViewModel.Artifact] {
        var bestByPath: [String: (index: Int, artifact: TaskOrchestrationViewModel.Artifact)] = [:]

        for (index, artifact) in artifacts.enumerated() {
            let key = artifactDisplayKey(artifact)
            if let existing = bestByPath[key] {
                if shouldReplaceArtifact(existing.artifact, with: artifact) || artifactStatusRank(existing.artifact) == artifactStatusRank(artifact) {
                    bestByPath[key] = (index, artifact)
                }
            } else {
                bestByPath[key] = (index, artifact)
            }
        }

        return bestByPath.values
            .sorted { $0.index < $1.index }
            .map(\.artifact)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Button(action: { isArtifactsExpanded.toggle() }) {
                HStack(spacing: 6) {
                    Text(appPreferences.text("tasks.artifacts"))
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(theme.primaryText)

                    Text("(\(displayArtifacts.count))")
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)

                    Image(systemName: "doc.on.doc.fill")
                        .font(.system(size: 12))
                        .foregroundColor(Color(hex: "#B58AE3"))

                    Image(systemName: isArtifactsExpanded ? "chevron.down" : "chevron.right")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.secondary)

                    Spacer()
                }
            }
            .buttonStyle(.plain)

            if isArtifactsExpanded {
                VStack(spacing: 4) {
                    ForEach(displayArtifacts) { artifact in
                        ArtifactRow(artifact: artifact)
                    }
                }
            }
        }
        .animation(.easeInOut(duration: 0.2), value: isArtifactsExpanded)
    }

    private func artifactDisplayKey(_ artifact: TaskOrchestrationViewModel.Artifact) -> String {
        let path = artifact.filePath.trimmingCharacters(in: .whitespacesAndNewlines)
        if !path.isEmpty {
            return path
        }
        return artifact.fileName.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func shouldReplaceArtifact(
        _ current: TaskOrchestrationViewModel.Artifact,
        with candidate: TaskOrchestrationViewModel.Artifact
    ) -> Bool {
        artifactStatusRank(candidate) > artifactStatusRank(current)
    }

    private func artifactStatusRank(_ artifact: TaskOrchestrationViewModel.Artifact) -> Int {
        switch artifact.status?.lowercased() {
        case "accepted":
            return 5
        case "completed", "produced", "available":
            return 4
        case "pending", "running":
            return 3
        case nil:
            return 2
        case "rejected", "failed", "cancelled":
            return 1
        default:
            return 2
        }
    }
}

struct ArtifactRow: View {
    let artifact: TaskOrchestrationViewModel.Artifact

    @State private var isHovered = false
    @Environment(\.colorScheme) private var colorScheme
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    var body: some View {
        HStack(spacing: 10) {
            SVGIconView(name: getFileIconName(fileName: artifact.fileName), size: 16)

            VStack(alignment: .leading, spacing: 2) {
                Text(artifact.fileName)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(theme.strongText)

                Text(artifact.filePath)
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }

            Spacer()

            Text(artifact.fileSize)
                .font(.system(size: 10))
                .foregroundColor(.secondary)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(isHovered ? theme.hoverBackground : Color.clear)
        .cornerRadius(6)
        .contentShape(Rectangle())
        .onHover { hovering in
            withAnimation(.easeInOut(duration: 0.1)) {
                isHovered = hovering
            }
        }
        .onTapGesture {
            NSWorkspace.shared.selectFile(artifact.filePath, inFileViewerRootedAtPath: "")
        }
    }
}
