import SwiftUI
import AppKit

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
                        .foregroundColor(AcrossTheme.accent)

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
    @State private var showsReleaseE2EConfirmation = false

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

                Button(action: { showsReleaseE2EConfirmation = true }) {
                    Label(
                        viewModel.isStartingReleaseE2E ? appPreferences.text("tasks.releaseE2E.starting") : appPreferences.text("tasks.releaseE2E.run"),
                        systemImage: "checklist.checked"
                    )
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(AcrossTheme.accent)
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
        .confirmationDialog(
            appPreferences.text("tasks.releaseE2E.confirmTitle"),
            isPresented: $showsReleaseE2EConfirmation,
            titleVisibility: .visible
        ) {
            Button(appPreferences.text("tasks.releaseE2E.run")) {
                viewModel.startReleaseE2E()
            }
            Button(appPreferences.text("system.cancel"), role: .cancel) {}
        } message: {
            Text(appPreferences.text("tasks.releaseE2E.confirmMessage"))
        }
        .background(theme.panelBackground)
    }

    private func releaseCenterOverview(_ summary: ReleaseEvaluationSummary) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(appPreferences.text("tasks.releaseCenter.overview"))
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(theme.primaryText)

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 112), spacing: 8)], alignment: .leading, spacing: 8) {
                releaseCenterMetric(
                    appPreferences.text("tasks.releaseEvaluation.readiness"),
                    localizedReadiness(summary.releaseReadiness),
                    summary.releaseReadiness
                )
                releaseCenterMetric(
                    appPreferences.text("tasks.releaseCenter.evidence"),
                    "\(summary.passedEvidenceCount)/\(summary.releaseEvidenceCount)",
                    summary.releaseEvidenceCount == summary.passedEvidenceCount && summary.releaseEvidenceCount > 0 ? "passed" : "partial"
                )
                releaseCenterMetric(
                    appPreferences.text("tasks.releaseCenter.interop"),
                    localizedStatus(summary.agentInteropE2EStatus ?? "unknown"),
                    summary.agentInteropE2EStatus ?? "unknown"
                )
                releaseCenterMetric(
                    appPreferences.text("tasks.releaseEvaluation.passRate"),
                    "\(summary.passRatePercent)%",
                    summary.passRate >= 1 ? "passed" : "partial"
                )
                releaseCenterMetric(
                    appPreferences.text("tasks.releaseEvaluation.score"),
                    summary.averageFinalQualityScore.map(String.init) ?? "-",
                    (summary.averageFinalQualityScore ?? 0) >= 80 ? "passed" : "partial"
                )
                releaseCenterMetric(
                    appPreferences.text("tasks.releaseEvaluation.trend"),
                    localizedTrend(summary.qualityTrend?.direction ?? "no_data"),
                    summary.qualityTrend?.direction == "regressing" ? "failed" : "passed"
                )
                releaseCenterMetric(
                    appPreferences.text("tasks.releaseCenter.repairs"),
                    "\(summary.totalRemediationCount)",
                    summary.totalRemediationCount == 0 ? "passed" : "partial"
                )
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

    private func localizedStatus(_ status: String) -> String {
        appPreferences.text("workbench.status.\(status)")
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
