import SwiftUI
import AppKit

struct StartupDiagnosticsView: View {
    @ObservedObject var settingsViewModel: SettingsViewModel
    @EnvironmentObject var appPreferences: AppPreferences
    @Environment(\.colorScheme) private var colorScheme

    private var textColor: Color { colorScheme == .dark ? .legacyTextDark : .legacyTextLight }
    private var bgColor: Color { colorScheme == .dark ? .legacyBgDark : .legacyBgLight }
    private var cardColor: Color { colorScheme == .dark ? Color(hex: "202227") : Color(hex: "fafbfc") }
    private var fieldColor: Color { colorScheme == .dark ? Color(hex: "15171b") : Color.black.opacity(0.045) }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
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
            .padding(SettingsHubPageLayout.contentPadding)
            .frame(maxWidth: SettingsHubPageLayout.contentMaxWidth, alignment: .leading)
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
        HStack(alignment: .center, spacing: 16) {
            VStack(alignment: .leading, spacing: 6) {
                Text(appPreferences.text("diagnostics.title"))
                    .font(.system(size: 24, weight: .bold))
                    .foregroundColor(textColor)
                Text(appPreferences.text("diagnostics.subtitle"))
                    .font(.system(size: 13))
                    .foregroundColor(.secondary)
            }

            Spacer()

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
        .padding(.top, 2)
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
                Text(report.providerSummary)
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                if let error = settingsViewModel.startupDiagnosticsError {
                    Text(error)
                        .font(.system(size: 11))
                        .foregroundColor(.red)
                }
            }
        }
        .padding(14)
        .background(cardColor)
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(statusColor(report.status).opacity(0.28), lineWidth: 1)
        )
    }

    private func checksSection(_ report: StartupDiagnosticsReport) -> some View {
        diagnosticsSection(
            title: appPreferences.text("diagnostics.checks"),
            subtitle: appPreferences.text("diagnostics.checks.subtitle")
        ) {
            VStack(spacing: 10) {
                ForEach(report.checks) { check in
                    checkRow(check)
                }
            }
        }
    }

    private func pathsSection(_ report: StartupDiagnosticsReport) -> some View {
        diagnosticsSection(
            title: appPreferences.text("diagnostics.paths"),
            subtitle: appPreferences.text("diagnostics.paths.subtitle")
        ) {
            VStack(spacing: 10) {
                pathRow(title: "App Home", path: report.paths.appHome, canOpen: true)
                pathRow(title: "Logs", path: report.paths.logsDir, canOpen: true)
                pathRow(title: "Evidence", path: report.paths.evidenceDir, canOpen: true)
                pathRow(title: "Socket", path: report.paths.socketPath, canOpen: false)
                pathRow(title: "Database", path: report.paths.databasePath, canOpen: false)
            }
        }
    }

    private func runtimeSection(_ report: StartupDiagnosticsReport) -> some View {
        diagnosticsSection(
            title: appPreferences.text("diagnostics.runtime"),
            subtitle: appPreferences.text("diagnostics.runtime.subtitle")
        ) {
            HStack(spacing: 12) {
                metricTile(title: "PID", value: "\(report.runtime.pid)", color: .blue)
                metricTile(title: appPreferences.text("diagnostics.tasks"), value: "\(report.runtime.knownTasks)", color: .purple)
                metricTile(
                    title: appPreferences.text("diagnostics.persistence"),
                    value: appPreferences.text(report.runtime.persistenceInitialized ? "system.yes" : "system.no"),
                    color: report.runtime.persistenceInitialized ? .green : .orange
                )
                metricTile(title: appPreferences.text("diagnostics.uptime"), value: uptimeString(report.runtime.uptimeSec), color: .blue)
            }
        }
    }

    private var releaseVerificationSection: some View {
        diagnosticsSection(
            title: appPreferences.text("releaseVerification.title"),
            subtitle: appPreferences.text("releaseVerification.subtitle")
        ) {
            VStack(spacing: 10) {
                if let report = settingsViewModel.releaseVerificationReport {
                    releaseVerificationOverview(report)
                    if let latest = report.latestReleaseE2E {
                        latestReleaseE2ERow(latest)
                    } else {
                        releaseVerificationEmptyEvidence(report)
                    }
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
                    color: .purple
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
        .background(cardColor)
        .cornerRadius(8)
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
        .background(cardColor)
        .cornerRadius(8)
    }

    private func diagnosticsSection<Content: View>(
        title: String,
        subtitle: String,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.system(size: 14, weight: .bold))
                    .foregroundColor(textColor)
                Text(subtitle)
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            }
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
        .background(cardColor)
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color.secondary.opacity(0.12), lineWidth: 1)
        )
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
        .background(fieldColor)
        .cornerRadius(8)
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
            Rectangle()
                .fill(color)
                .frame(height: 3)
                .cornerRadius(2)
        }
        .padding(12)
        .frame(maxWidth: .infinity, minHeight: 76, alignment: .leading)
        .background(fieldColor)
        .cornerRadius(8)
    }

    private func statusColor(_ status: StartupDiagnosticStatus) -> Color {
        switch status {
        case .ready, .passed:
            return Color(hex: "30d158")
        case .attention, .warning:
            return Color(hex: "ff9f0a")
        case .blocked, .failed:
            return Color(hex: "ff453a")
        case .info:
            return Color(hex: "64d2ff")
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

    private func statusColorValue(_ value: String) -> Color {
        if let status = StartupDiagnosticStatus(rawValue: value) {
            return statusColor(status)
        }
        return .secondary
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
