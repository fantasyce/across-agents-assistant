import SwiftUI
import AppKit

struct StartupDiagnosticsView: View {
    @ObservedObject var settingsViewModel: SettingsViewModel
    @EnvironmentObject var appPreferences: AppPreferences
    @Environment(\.colorScheme) private var colorScheme
    @State private var showingPassedChecks = false
    @State private var showingPaths = false
    @State private var showingRuntime = false
    @State private var showingReleaseDetails = false

    private var textColor: Color { .primary }
    private var bgColor: Color { Color(nsColor: .windowBackgroundColor) }
    private var cardColor: Color { Color(nsColor: .controlBackgroundColor) }
    private var fieldColor: Color { Color(nsColor: .controlBackgroundColor) }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: MinimalSettingsMetrics.sectionSpacing) {
                header

                if let report = settingsViewModel.startupDiagnostics {
                    overview(report)
                    checksSection(report)
                    pathsSection(report)
                    runtimeSection(report)
                } else if settingsViewModel.isLoadingStartupDiagnostics {
                    loadingState
                } else {
                    emptyState
                }

                releaseVerificationSection
            }
            .padding(MinimalSettingsMetrics.contentPadding)
            .frame(maxWidth: MinimalSettingsMetrics.contentMaxWidth, alignment: .leading)
            .frame(maxWidth: .infinity)
        }
        .background(bgColor)
        .task {
            if settingsViewModel.startupDiagnostics == nil {
                await settingsViewModel.refreshStartupDiagnostics()
            }
        }
    }

    private var header: some View {
        MinimalSettingsPageHeader(
            title: appPreferences.text("diagnostics.title"),
            subtitle: appPreferences.text("diagnostics.subtitle")
        ) {
            HStack(spacing: 8) {
                Button {
                    Task { await settingsViewModel.runReleaseVerification() }
                } label: {
                    HStack(spacing: 7) {
                        if settingsViewModel.isRunningReleaseVerification {
                            ProgressView()
                                .scaleEffect(0.6)
                                .frame(width: 12, height: 12)
                        } else {
                            Image(systemName: "checkmark.seal.fill")
                                .font(.system(size: 12, weight: .semibold))
                        }
                        Text(appPreferences.text(settingsViewModel.isRunningReleaseVerification ? "releaseVerification.running" : "releaseVerification.run"))
                            .font(.system(size: 12, weight: .semibold))
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                }
                .buttonStyle(.borderedProminent)
                .disabled(settingsViewModel.isRunningReleaseVerification)

                Button {
                    Task { await settingsViewModel.refreshStartupDiagnostics() }
                } label: {
                    HStack(spacing: 7) {
                        if settingsViewModel.isLoadingStartupDiagnostics {
                            ProgressView()
                                .scaleEffect(0.6)
                                .frame(width: 12, height: 12)
                        } else {
                            Image(systemName: "arrow.clockwise")
                                .font(.system(size: 12, weight: .semibold))
                        }
                        Text(appPreferences.text("settings.refresh"))
                            .font(.system(size: 12, weight: .semibold))
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                }
                .buttonStyle(.bordered)
                .disabled(settingsViewModel.isLoadingStartupDiagnostics)
            }
        }
    }

    private func overview(_ report: StartupDiagnosticsReport) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 12) {
                statusTile(
                    title: appPreferences.text("diagnostics.status"),
                    value: localizedStatus(report.status),
                    status: report.status
                )
                metricTile(title: appPreferences.text("diagnostics.passed"), value: "\(report.summary.passed)", color: .green)
                metricTile(title: appPreferences.text("diagnostics.warnings"), value: "\(report.summary.warnings)", color: .orange)
                metricTile(title: appPreferences.text("diagnostics.failed"), value: "\(report.summary.failed)", color: .red)
            }

            VStack(alignment: .leading, spacing: 6) {
                Text(localizedHeadline(report))
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(textColor)
                Text(localizedProviderSummary(report))
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                if let error = settingsViewModel.startupDiagnosticsError {
                    Text(error)
                        .font(.system(size: 11))
                        .foregroundColor(.red)
                }
            }
        }
        .padding(.vertical, 4)
    }

    private func checksSection(_ report: StartupDiagnosticsReport) -> some View {
        let attentionChecks = report.checks.filter { !isNormal($0.status) }
        let normalChecks = report.checks.filter { isNormal($0.status) }
        return diagnosticsSection(
            title: appPreferences.text("diagnostics.checks"),
            subtitle: appPreferences.text("diagnostics.checks.subtitle")
        ) {
            VStack(spacing: 0) {
                ForEach(attentionChecks) { check in
                    checkRow(check)
                }

                if !normalChecks.isEmpty {
                    DisclosureGroup(isExpanded: $showingPassedChecks) {
                        VStack(spacing: 0) {
                            ForEach(normalChecks) { check in
                                checkRow(check)
                            }
                        }
                    } label: {
                        HStack {
                            Label(appPreferences.text("diagnostics.passed"), systemImage: "checkmark.circle")
                            Spacer()
                            Text("\(normalChecks.count)")
                                .foregroundStyle(.secondary)
                        }
                        .font(.system(size: 12, weight: .medium))
                        .padding(.vertical, 10)
                    }
                }
            }
        }
    }

    private func pathsSection(_ report: StartupDiagnosticsReport) -> some View {
        diagnosticsSection(
            title: appPreferences.text("diagnostics.paths"),
            subtitle: appPreferences.text("diagnostics.paths.subtitle")
        ) {
            DisclosureGroup(isExpanded: $showingPaths) {
                VStack(spacing: 0) {
                    pathRow(title: "App Home", path: report.paths.appHome, canOpen: true)
                    pathRow(title: "Logs", path: report.paths.logsDir, canOpen: true)
                    pathRow(title: "Evidence", path: report.paths.evidenceDir, canOpen: true)
                    pathRow(title: "Socket", path: report.paths.socketPath, canOpen: false)
                    pathRow(title: "Database", path: report.paths.databasePath, canOpen: false)
                }
            } label: {
                Label(appPreferences.text("diagnostics.paths"), systemImage: "folder")
                    .font(.system(size: 12, weight: .medium))
                    .padding(.vertical, 10)
            }
        }
    }

    private func runtimeSection(_ report: StartupDiagnosticsReport) -> some View {
        diagnosticsSection(
            title: appPreferences.text("diagnostics.runtime"),
            subtitle: appPreferences.text("diagnostics.runtime.subtitle")
        ) {
            DisclosureGroup(isExpanded: $showingRuntime) {
                HStack(spacing: 12) {
                    metricTile(title: "PID", value: "\(report.runtime.pid)", color: .blue)
                    metricTile(title: appPreferences.text("diagnostics.tasks"), value: "\(report.runtime.knownTasks)", color: .blue)
                    metricTile(
                        title: appPreferences.text("diagnostics.persistence"),
                        value: appPreferences.text(report.runtime.persistenceInitialized ? "system.yes" : "system.no"),
                        color: report.runtime.persistenceInitialized ? .green : .orange
                    )
                    metricTile(title: appPreferences.text("diagnostics.uptime"), value: uptimeString(report.runtime.uptimeSec), color: .blue)
                }
                .padding(.bottom, 10)
            } label: {
                Label(appPreferences.text("diagnostics.runtime"), systemImage: "waveform.path.ecg")
                    .font(.system(size: 12, weight: .medium))
                    .padding(.vertical, 10)
            }
        }
    }

    private var releaseVerificationSection: some View {
        diagnosticsSection(
            title: appPreferences.text("releaseVerification.title"),
            subtitle: appPreferences.text("releaseVerification.subtitle")
        ) {
            DisclosureGroup(isExpanded: $showingReleaseDetails) {
                VStack(spacing: 10) {
                if let report = settingsViewModel.releaseVerificationReport {
                    releaseVerificationOverview(report)
                    if let latest = report.latestReleaseE2E {
                        latestReleaseE2ERow(latest)
                    } else {
                        releaseVerificationEmptyEvidence(report)
                    }
                    preReleaseGateSection(report)
                    releaseReportFiles(report)
                    if !report.remediations.isEmpty {
                        releaseRemediations(report.remediations)
                    }
                } else {
                    releaseVerificationEmptyState
                }

                if let error = settingsViewModel.releaseVerificationError {
                    Text(error)
                        .font(.system(size: 11))
                        .foregroundColor(.red)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                }
                .padding(.bottom, 10)
            } label: {
                HStack {
                    Label(appPreferences.text("releaseVerification.latest"), systemImage: "checkmark.seal")
                    Spacer()
                    if let report = settingsViewModel.releaseVerificationReport {
                        MinimalStatusLabel(
                            text: localizedStatus(report.status),
                            color: statusColor(report.status)
                        )
                    }
                }
                .font(.system(size: 12, weight: .medium))
                .padding(.vertical, 10)
            }
        }
    }

    private func releaseVerificationOverview(_ report: ReleaseVerificationReport) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 12) {
                statusTile(
                    title: appPreferences.text("diagnostics.status"),
                    value: localizedStatus(report.status),
                    status: report.status
                )
                metricTile(
                    title: appPreferences.text("releaseVerification.score"),
                    value: report.latestReleaseE2E?.summary.qualityScore.map(String.init) ?? "-",
                    color: .green
                )
                metricTile(
                    title: appPreferences.text("releaseVerification.repairs"),
                    value: "\(report.latestReleaseE2E?.summary.remediationAttempts ?? 0)",
                    color: .blue
                )
                metricTile(
                    title: appPreferences.text("diagnostics.tasks"),
                    value: "\(report.releaseEvaluation.evaluatedTaskCount)",
                    color: .blue
                )
            }

            Text(report.readyHeadline)
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(textColor)
        }
        .padding(14)
        .background(cardColor)
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(statusColor(report.status).opacity(0.28), lineWidth: 1)
        )
    }

    private func latestReleaseE2ERow(_ latest: ReleaseVerificationLatestE2E) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline) {
                Text(appPreferences.text("releaseVerification.latest"))
                    .font(.system(size: 12, weight: .bold))
                    .foregroundColor(textColor)
                Spacer()
                Text(localizedStatusValue(latest.benchmark.status))
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(statusColorValue(latest.benchmark.status))
            }

            Text(latest.compactDescription)
                .font(.system(size: 11))
                .foregroundColor(.secondary)
                .lineLimit(2)

            HStack(spacing: 10) {
                releaseMetaPill(title: appPreferences.text("releaseVerification.task"), value: latest.taskId)
                releaseMetaPill(title: appPreferences.text("releaseVerification.benchmark"), value: latest.benchmark.status)
            }

            if let projectDir = latest.projectDir, !projectDir.isEmpty {
                reportFileRow(title: "Project", path: projectDir, systemImage: "folder")
            }
        }
        .padding(12)
        .background(cardColor)
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color.secondary.opacity(0.12), lineWidth: 1)
        )
    }

    @ViewBuilder
    private func preReleaseGateSection(_ report: ReleaseVerificationReport) -> some View {
        let gates = report.preReleaseGates ?? []
        if !gates.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                HStack(alignment: .firstTextBaseline) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(appPreferences.text("releaseVerification.preReleaseGates"))
                            .font(.system(size: 12, weight: .bold))
                            .foregroundColor(textColor)
                        Text(report.gateHeadline)
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                    }
                    Spacer()
                    Text(
                        String(
                            format: appPreferences.text("releaseVerification.gateSummary"),
                            report.gateSummary.passed,
                            report.gateSummary.configured,
                            report.gateSummary.manualRequired,
                            report.gateSummary.missing
                        )
                    )
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(gateSummaryColor(report.gateSummary))
                        .lineLimit(1)
                }

                if !report.preReleaseGateMissingPaths.isEmpty {
                    missingGatePaths(report.preReleaseGateMissingPaths)
                }
                if !report.preReleaseGateParseErrors.isEmpty {
                    gateParseErrors(report.preReleaseGateParseErrors)
                }

                ForEach(gates) { gate in
                    preReleaseGateRow(gate)
                }
            }
            .padding(12)
            .background(cardColor)
            .cornerRadius(8)
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(Color.secondary.opacity(0.12), lineWidth: 1)
            )
        }
    }

    private func preReleaseGateRow(_ gate: ReleaseVerificationPreReleaseGate) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: gateIconName(gate.status))
                .font(.system(size: 12, weight: .bold))
                .foregroundColor(gateStatusColor(gate.status))
                .frame(width: 22, height: 22)
                .background(gateStatusColor(gate.status).opacity(0.14))
                .cornerRadius(7)

            VStack(alignment: .leading, spacing: 5) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(gate.label)
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(textColor)
                    Text(localizedGateStatus(gate.status))
                        .font(.system(size: 9, weight: .bold))
                        .foregroundColor(gateStatusColor(gate.status))
                    Spacer(minLength: 0)
                    Text(gate.source.replacingOccurrences(of: "_", with: " "))
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                }
                if !gate.detail.isEmpty {
                    Text(gate.detail)
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if !gate.command.isEmpty {
                    Text(gate.command)
                        .font(.system(size: 9, design: .monospaced))
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                        .truncationMode(.middle)
                }
                if let evidence = gate.evidence {
                    Text(gateEvidenceSummary(evidence))
                        .font(.system(size: 10))
                        .foregroundColor(gateStatusColor(evidence.status))
                        .fixedSize(horizontal: false, vertical: true)
                    if let runURL = evidence.runURL ?? evidence.workflowRunURL, !runURL.isEmpty {
                        Text(runURL)
                            .font(.system(size: 9, design: .monospaced))
                            .foregroundColor(.secondary)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }
                }
            }
        }
        .padding(10)
        .background(fieldColor)
        .cornerRadius(8)
    }

    private func missingGatePaths(_ paths: [String]) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(appPreferences.text("releaseVerification.missingGatePaths"))
                .font(.system(size: 10, weight: .bold))
                .foregroundColor(Color(nsColor: .systemRed))
            ForEach(paths.prefix(5), id: \.self) { path in
                Text(path)
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundColor(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            if paths.count > 5 {
                Text(String(format: appPreferences.text("releaseVerification.morePaths"), paths.count - 5))
                    .font(.system(size: 9))
                    .foregroundColor(.secondary)
            }
        }
        .padding(10)
        .background(fieldColor)
        .cornerRadius(8)
    }

    private func gateParseErrors(_ errors: [ReleaseVerificationPreReleaseGateParseError]) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(appPreferences.text("releaseVerification.gateParseErrors"))
                .font(.system(size: 10, weight: .bold))
                .foregroundColor(Color(nsColor: .systemOrange))
            ForEach(errors.prefix(4)) { error in
                Text("\(error.evidencePath): \(error.errorType)")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundColor(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
                if !error.message.isEmpty {
                    Text(error.message)
                        .font(.system(size: 9))
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                }
            }
            if errors.count > 4 {
                Text(String(format: appPreferences.text("releaseVerification.morePaths"), errors.count - 4))
                    .font(.system(size: 9))
                    .foregroundColor(.secondary)
            }
        }
        .padding(10)
        .background(fieldColor)
        .cornerRadius(8)
    }

    private func gateEvidenceSummary(_ evidence: ReleaseVerificationPreReleaseGateEvidence) -> String {
        var parts = [appPreferences.text("releaseVerification.gateEvidence"), localizedGateStatus(evidence.status)]
        if let tier = evidence.tier, !tier.isEmpty {
            parts.append(tier)
        }
        if let completedAt = evidence.completedAt, !completedAt.isEmpty {
            parts.append(completedAt)
        }
        if let duration = evidence.durationSeconds {
            parts.append("\(duration)s")
        }
        return parts.joined(separator: " · ")
    }

    private func releaseVerificationEmptyEvidence(_ report: ReleaseVerificationReport) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundColor(statusColor(report.status))
                .frame(width: 22, height: 22)
            VStack(alignment: .leading, spacing: 4) {
                Text(appPreferences.text("releaseVerification.latest"))
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(textColor)
                Text(report.primaryRemediation ?? appPreferences.text("releaseVerification.empty"))
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
        }
        .padding(12)
        .background(cardColor)
        .cornerRadius(8)
    }

    private var releaseVerificationEmptyState: some View {
        HStack(spacing: 10) {
            Image(systemName: "doc.badge.gearshape")
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(.secondary)
            Text(appPreferences.text("releaseVerification.empty"))
                .font(.system(size: 12))
                .foregroundColor(.secondary)
            Spacer(minLength: 0)
        }
        .padding(14)
        .background(cardColor)
        .cornerRadius(8)
    }

    private func releaseReportFiles(_ report: ReleaseVerificationReport) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(appPreferences.text("releaseVerification.reportFiles"))
                .font(.system(size: 12, weight: .bold))
                .foregroundColor(textColor)
            reportFileRow(
                title: appPreferences.text("releaseVerification.markdown"),
                path: report.reportFiles.markdownPath,
                systemImage: "doc.text.magnifyingglass"
            )
            reportFileRow(
                title: appPreferences.text("releaseVerification.json"),
                path: report.reportFiles.jsonPath,
                systemImage: "curlybraces.square"
            )
        }
        .padding(12)
        .background(cardColor)
        .cornerRadius(8)
    }

    private func releaseRemediations(_ remediations: [String]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(appPreferences.text("releaseVerification.remediation"))
                .font(.system(size: 12, weight: .bold))
                .foregroundColor(textColor)
            ForEach(Array(remediations.enumerated()), id: \.offset) { _, remediation in
                Text(remediation)
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .padding(12)
        .background(cardColor)
        .cornerRadius(8)
    }

    private func releaseMetaPill(title: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title)
                .font(.system(size: 9, weight: .bold))
                .foregroundColor(.secondary)
            Text(value)
                .font(.system(size: 10, design: .monospaced))
                .foregroundColor(textColor)
                .lineLimit(1)
                .truncationMode(.middle)
        }
        .padding(.horizontal, 9)
        .padding(.vertical, 7)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(fieldColor)
        .cornerRadius(7)
    }

    private func reportFileRow(title: String, path: String, systemImage: String) -> some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(textColor)
                Text(path.isEmpty ? "-" : path)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundColor(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            Spacer()
            if !path.isEmpty {
                Button {
                    NSWorkspace.shared.open(URL(fileURLWithPath: path))
                } label: {
                    Image(systemName: systemImage)
                        .font(.system(size: 12, weight: .semibold))
                        .frame(width: 28, height: 28)
                }
                .buttonStyle(.borderless)
                .help(appPreferences.text("releaseVerification.openReport"))
            }
        }
        .padding(12)
        .background(fieldColor)
        .cornerRadius(8)
    }

    private var loadingState: some View {
        HStack(spacing: 12) {
            ProgressView()
            Text(appPreferences.text("diagnostics.loading"))
                .font(.system(size: 13))
                .foregroundColor(.secondary)
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var emptyState: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(appPreferences.text("diagnostics.empty"))
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(textColor)
            if let error = settingsViewModel.startupDiagnosticsError {
                Text(error)
                    .font(.system(size: 12))
                    .foregroundColor(.red)
            }
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func diagnosticsSection<Content: View>(
        title: String,
        subtitle: String,
        @ViewBuilder content: @escaping () -> Content
    ) -> some View {
        MinimalSettingsSection(title: title, subtitle: subtitle) {
            content()
        }
    }

    private func checkRow(_ check: StartupDiagnosticsCheck) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: iconName(check.status))
                .font(.system(size: 13, weight: .bold))
                .foregroundColor(statusColor(check.status))
                .frame(width: 22, height: 22)
                .background(statusColor(check.status).opacity(0.14))
                .cornerRadius(7)

            VStack(alignment: .leading, spacing: 5) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(check.title)
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(textColor)
                    Text(localizedStatus(check.status))
                        .font(.system(size: 10, weight: .bold))
                        .foregroundColor(statusColor(check.status))
                }
                Text(check.detail)
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                if let remediation = check.remediation, !remediation.isEmpty {
                    Text(remediation)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(statusColor(check.status))
                        .fixedSize(horizontal: false, vertical: true)
                }
                if !check.metadataString.isEmpty {
                    Text(check.metadataString)
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                }
            }

            Spacer(minLength: 0)
        }
        .padding(12)
        .overlay(alignment: .bottom) { Divider() }
    }

    private func pathRow(title: String, path: String, canOpen: Bool) -> some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(textColor)
                Text(path)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundColor(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            Spacer()
            if canOpen {
                Button {
                    NSWorkspace.shared.open(URL(fileURLWithPath: path))
                } label: {
                    Image(systemName: "folder")
                        .font(.system(size: 12, weight: .semibold))
                        .frame(width: 28, height: 28)
                }
                .buttonStyle(.borderless)
                .help(appPreferences.text("diagnostics.openPath"))
            }
        }
        .padding(12)
        .overlay(alignment: .bottom) { Divider() }
    }

    private func statusTile(title: String, value: String, status: StartupDiagnosticStatus) -> some View {
        metricTile(title: title, value: value, color: statusColor(status))
    }

    private func metricTile(title: String, value: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.system(size: 10, weight: .semibold))
                .foregroundColor(.secondary)
                .lineLimit(1)
            Text(value)
                .font(.system(size: 17, weight: .bold))
                .foregroundColor(textColor)
                .lineLimit(1)
                .minimumScaleFactor(0.78)
            Circle()
                .fill(color)
                .frame(width: 6, height: 6)
                .accessibilityHidden(true)
        }
        .padding(.vertical, 10)
        .frame(maxWidth: .infinity, minHeight: 68, alignment: .leading)
    }

    private func isNormal(_ status: StartupDiagnosticStatus) -> Bool {
        status == .ready || status == .passed
    }

    private func statusColor(_ status: StartupDiagnosticStatus) -> Color {
        switch status {
        case .ready, .passed:
            return Color(nsColor: .systemGreen)
        case .attention, .warning:
            return Color(nsColor: .systemOrange)
        case .blocked, .failed:
            return Color(nsColor: .systemRed)
        case .info:
            return Color(nsColor: .systemTeal)
        }
    }

    private func iconName(_ status: StartupDiagnosticStatus) -> String {
        switch status {
        case .ready, .passed:
            return "checkmark.circle.fill"
        case .attention, .warning:
            return "exclamationmark.triangle.fill"
        case .blocked, .failed:
            return "xmark.octagon.fill"
        case .info:
            return "info.circle.fill"
        }
    }

    private func localizedStatus(_ status: StartupDiagnosticStatus) -> String {
        appPreferences.text("diagnostics.status.\(status.rawValue)")
    }

    private func localizedStatusValue(_ value: String) -> String {
        if let status = StartupDiagnosticStatus(rawValue: value) {
            return localizedStatus(status)
        }
        return value
    }

    private func localizedProviderSummary(_ report: StartupDiagnosticsReport) -> String {
        [
            ("deepseek", "DeepSeek"),
            ("minimax", "MiniMax"),
            ("agnes", "Agnes"),
        ]
        .map { id, title in
            "\(title): \(appPreferences.statusText(report.keys.providers[id] ?? "unknown"))"
        }
        .joined(separator: " · ")
    }

    private func statusColorValue(_ value: String) -> Color {
        if let status = StartupDiagnosticStatus(rawValue: value) {
            return statusColor(status)
        }
        return .secondary
    }

    private func gateStatusColor(_ value: String) -> Color {
        switch value {
        case "configured", "passed":
            return Color(nsColor: .systemGreen)
        case "manual_required", "attention", "warning":
            return Color(nsColor: .systemOrange)
        case "missing", "failed", "blocked":
            return Color(nsColor: .systemRed)
        default:
            return .secondary
        }
    }

    private func gateSummaryColor(_ summary: ReleaseVerificationPreReleaseGateSummary) -> Color {
        if summary.requiredFailed > 0 || summary.failed > 0 || summary.requiredMissing > 0 || summary.missing > 0 {
            return Color(nsColor: .systemRed)
        }
        if summary.requiredManual > 0 || summary.manualRequired > 0 {
            return Color(nsColor: .systemOrange)
        }
        return Color(nsColor: .systemGreen)
    }

    private func gateIconName(_ value: String) -> String {
        switch value {
        case "configured", "passed":
            return "checkmark.circle.fill"
        case "manual_required", "attention", "warning":
            return "clock.badge.exclamationmark.fill"
        case "missing", "failed", "blocked":
            return "xmark.octagon.fill"
        default:
            return "info.circle.fill"
        }
    }

    private func localizedGateStatus(_ value: String) -> String {
        let key = "releaseVerification.gateStatus.\(value)"
        let localized = appPreferences.text(key)
        if localized != key {
            return localized
        }
        return value.replacingOccurrences(of: "_", with: " ")
    }

    private func localizedHeadline(_ report: StartupDiagnosticsReport) -> String {
        var parts = [
            localizedStatus(report.status),
            String(format: appPreferences.text("diagnostics.headline.passed"), report.summary.passed)
        ]
        if report.summary.warnings > 0 {
            parts.append(String(format: appPreferences.text("diagnostics.headline.warnings"), report.summary.warnings))
        }
        if report.summary.failed > 0 {
            parts.append(String(format: appPreferences.text("diagnostics.headline.failed"), report.summary.failed))
        }
        return parts.joined(separator: " · ")
    }

    private func uptimeString(_ seconds: Double) -> String {
        if seconds < 60 {
            return "\(Int(seconds))s"
        }
        let minutes = Int(seconds / 60)
        if minutes < 60 {
            return "\(minutes)m"
        }
        return "\(minutes / 60)h"
    }
}
