import SwiftUI

struct PluginLifecycleView: View {
    @StateObject private var viewModel = PluginLifecycleViewModel()
    @State private var showingLoopHealthDetails = false
    @EnvironmentObject private var appPreferences: AppPreferences
    @Environment(\.colorScheme) private var colorScheme

    var onClose: (() -> Void)? = nil
    var embeddedInHub: Bool = false

    private var bgColor: Color { colorScheme == .dark ? .legacyBgDark : .legacyBgLight }
    private var cardColor: Color { colorScheme == .dark ? Color(hex: "202227") : Color(hex: "fafbfc") }
    private var fieldColor: Color { colorScheme == .dark ? Color(hex: "15171b") : Color.black.opacity(0.045) }
    private var lineColor: Color { colorScheme == .dark ? Color.white.opacity(0.10) : Color.black.opacity(0.10) }
    private var textColor: Color { colorScheme == .dark ? .legacyTextDark : .legacyTextLight }
    private var accentColor: Color { colorScheme == .dark ? .legacyAccentDark : .legacyAccentLight }

    private let columns = Array(repeating: GridItem(.flexible(), spacing: 16), count: 2)

    var body: some View {
        VStack(spacing: 0) {
            if !embeddedInHub {
                standaloneHeader
                Divider().opacity(0.35)
            }

            ScrollView {
                VStack(alignment: .leading, spacing: SettingsHubPageLayout.sectionSpacing) {
                    titleRow
                    feedbackRows
                    LazyVGrid(columns: columns, spacing: 16) {
                        ForEach(viewModel.plugins) { plugin in
                            pluginCard(plugin)
                        }
                    }
                    memorySection
                }
                .padding(SettingsHubPageLayout.contentPadding)
                .frame(maxWidth: SettingsHubPageLayout.contentMaxWidth, alignment: .leading)
                .frame(maxWidth: .infinity)
            }
            .overlay {
                if viewModel.isWorking {
                    ProgressView()
                        .controlSize(.small)
                        .padding(18)
                        .background(cardColor)
                        .clipShape(RoundedRectangle(cornerRadius: 10))
                        .shadow(color: Color.black.opacity(0.16), radius: 18, x: 0, y: 8)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(bgColor)
        .background(
            Group {
                if !embeddedInHub {
                    VisualEffectView().ignoresSafeArea()
                }
            }
        )
        .ignoresSafeArea(.all, edges: embeddedInHub ? Edge.Set() : .top)
        .task {
            await viewModel.load()
        }
    }

    private var standaloneHeader: some View {
        HStack {
            CustomTrafficLights(onClose: onClose)
            Spacer()
            Text(appPreferences.text("plugins.title"))
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(textColor)
            Spacer()
            Spacer().frame(width: 50)
        }
        .padding(.horizontal, 16)
        .frame(height: 56)
        .background(
            ZStack {
                bgColor.opacity(colorScheme == .dark ? 0.84 : 0.96)
                WindowDragView().contentShape(Rectangle())
            }
        )
    }

    private var titleRow: some View {
        HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 5) {
                Text(appPreferences.text("plugins.title"))
                    .font(.system(size: 28, weight: .bold))
                    .foregroundColor(textColor)
                Text(appPreferences.text("plugins.subtitle"))
                    .font(.system(size: 13))
                    .foregroundColor(.secondary)
            }

            Spacer()

            Button {
                Task { await viewModel.load(probe: true) }
            } label: {
                Image(systemName: "arrow.clockwise")
                    .font(.system(size: 13, weight: .semibold))
                    .frame(width: 32, height: 30)
            }
            .buttonStyle(.plain)
            .foregroundColor(textColor)
            .background(fieldColor)
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .help(appPreferences.text("settings.refresh"))
        }
    }

    @ViewBuilder
    private var feedbackRows: some View {
        if let message = viewModel.message {
            banner(message, color: Color(hex: "30d158"))
        }
        if let error = viewModel.errorMessage {
            banner(error, color: Color(hex: "ff453a"))
        }
    }

    private func banner(_ text: String, color: Color) -> some View {
        HStack(spacing: 8) {
            Circle().fill(color).frame(width: 7, height: 7)
            Text(text)
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(textColor)
                .lineLimit(2)
            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 9)
        .background(color.opacity(0.10))
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(color.opacity(0.18), lineWidth: 1))
    }

    private func pluginCard(_ plugin: AcrossPluginStatus) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 10) {
                pluginIcon(for: plugin.pluginId)
                    .frame(width: 34, height: 34)
                    .background(accentColor.opacity(0.15))
                    .clipShape(RoundedRectangle(cornerRadius: 8))

                VStack(alignment: .leading, spacing: 3) {
                    Text(plugin.displayName)
                        .font(.system(size: 14, weight: .bold))
                        .foregroundColor(textColor)
                        .lineLimit(1)
                    Text(plugin.kind)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                }

                Spacer()

                statusChip(plugin)
            }

            HStack(spacing: 8) {
                metadataChip(plugin.version?.isEmpty == false ? "v\(plugin.version!)" : appPreferences.text("plugins.versionUnknown"))
                metadataChip(plugin.commandExists ? appPreferences.text("plugins.commandReady") : appPreferences.text("plugins.commandMissing"))
                metadataChip(plugin.manifestExists ? appPreferences.text("plugins.manifestReady") : appPreferences.text("plugins.manifestMissing"))
            }

            capabilityTagRow(plugin)

            pathRow(appPreferences.text("plugins.path.runtime"), plugin.paths.plugin)
            pathRow(appPreferences.text("plugins.path.data"), plugin.paths.data)
            compatibilityRow(plugin)

            HStack(spacing: 8) {
                actionButton("probe", icon: "waveform.path.ecg", title: appPreferences.text("plugins.action.probe"), plugin: plugin)
                if plugin.installed {
                    actionButton("repair", icon: "cross.case", title: appPreferences.text("plugins.action.repair"), plugin: plugin)
                    actionButton("uninstall", icon: "trash", title: appPreferences.text("plugins.action.uninstall"), plugin: plugin)
                } else {
                    actionButton("install", icon: "arrow.down.circle", title: appPreferences.text("plugins.action.install"), plugin: plugin)
                }
                if plugin.pluginId == "across-orchestrator" && plugin.available {
                    Button {
                        Task { await viewModel.runAgentLoopProbe() }
                    } label: {
                        Image(systemName: "play.circle")
                            .font(.system(size: 12, weight: .semibold))
                            .frame(width: 30, height: 28)
                    }
                    .buttonStyle(.plain)
                    .foregroundColor(textColor)
                    .background(fieldColor)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                    .help(appPreferences.text("plugins.loop.probe"))
                    .disabled(viewModel.isWorking)
                }
            }

            agentLoopProbeRow(plugin)
        }
        .padding(14)
        .frame(minHeight: 286, alignment: .topLeading)
        .frame(maxWidth: .infinity, alignment: .topLeading)
        .background(cardColor)
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(lineColor, lineWidth: 1))
    }

    @ViewBuilder
    private func capabilityTagRow(_ plugin: AcrossPluginStatus) -> some View {
        HStack(spacing: 8) {
            if plugin.supportsAgentLoopRuntime {
                metadataChip(appPreferences.text("plugins.loop.runtime"))
                if plugin.supportsAgentLoopV2 {
                    metadataChip(appPreferences.text("plugins.loop.v2"))
                }
                if plugin.supportsCheckpoints {
                    metadataChip(appPreferences.text("plugins.loop.checkpoints"))
                }
            } else {
                Color.clear.frame(height: 22)
            }
        }
        .frame(height: 22, alignment: .leading)
    }

    @ViewBuilder
    private func compatibilityRow(_ plugin: AcrossPluginStatus) -> some View {
        if let required = plugin.compatibility?.requiredHostVersion {
            pathRow(appPreferences.text("plugins.compatibility"), required)
                .frame(height: 28, alignment: .topLeading)
        } else {
            Color.clear.frame(height: 28)
        }
    }

    @ViewBuilder
    private func agentLoopProbeRow(_ plugin: AcrossPluginStatus) -> some View {
        if let probe = viewModel.agentLoopProbe {
            if plugin.pluginId == "across-orchestrator" {
                VStack(alignment: .leading, spacing: 6) {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            metadataChip(String(format: appPreferences.text("plugins.loop.status"), probe.status))
                            metadataChip(String(format: appPreferences.text("plugins.loop.steps"), probe.steps.count))
                            metadataChip(String(format: appPreferences.text("plugins.loop.checkpointCount"), probe.checkpointCount ?? 0))
                            if let health = viewModel.agentLoopHealth {
                                if let currentAction = health.currentActionType {
                                    metadataChip(String(format: appPreferences.text("plugins.loop.currentAction"), currentAction))
                                }
                                if health.pendingApproval != nil {
                                    metadataChip(appPreferences.text("plugins.loop.pendingApproval"))
                                } else if health.lease?.active == true, let remaining = health.lease?.remainingSeconds {
                                    metadataChip(String(format: appPreferences.text("plugins.loop.leaseRemaining"), Int(remaining.rounded())))
                                } else {
                                    metadataChip(appPreferences.text("plugins.loop.leaseIdle"))
                                }
                                if health.hasStaleLease {
                                    metadataChip(appPreferences.text("plugins.loop.leaseStale"))
                                }
                                if health.cancelAckPending == true {
                                    metadataChip(appPreferences.text("plugins.loop.cancelAckPending"))
                                } else if health.cancellationRequested == true {
                                    metadataChip(appPreferences.text("plugins.loop.cancelRequested"))
                                }
                                if let cancellationCategory = health.cancellationCategory {
                                    metadataChip(cancelCategorySummary(cancellationCategory))
                                }
                                if health.recentFailureCount > 0 {
                                    metadataChip(String(format: appPreferences.text("plugins.loop.failureCount"), health.recentFailureCount))
                                }
                                agentLoopHealthButton(health)
                            }
                        }
                    }
                    .frame(height: 22, alignment: .leading)

                    if !viewModel.agentLoopEvents.isEmpty {
                        agentLoopTimelineRow(viewModel.agentLoopEvents, live: viewModel.agentLoopEventsLive)
                    }
                }
            } else {
                Color.clear.frame(height: viewModel.agentLoopEvents.isEmpty ? 22 : 50)
            }
        }
    }

    private func agentLoopHealthButton(_ health: AgentLoopHealthResponse) -> some View {
        Button {
            showingLoopHealthDetails.toggle()
        } label: {
            Image(systemName: health.needsAttention ? "exclamationmark.circle" : "info.circle")
                .font(.system(size: 12, weight: .semibold))
                .frame(width: 22, height: 22)
        }
        .buttonStyle(.plain)
        .foregroundColor(health.needsAttention ? Color(hex: "ff9f0a") : .secondary)
        .background(fieldColor)
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .help(appPreferences.text("plugins.loop.healthDetails"))
        .popover(isPresented: $showingLoopHealthDetails, arrowEdge: .bottom) {
            agentLoopHealthPopover(health)
        }
    }

    private func agentLoopHealthPopover(_ health: AgentLoopHealthResponse) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(appPreferences.text("plugins.loop.healthDetails"))
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(textColor)
            Divider().opacity(0.35)
            healthDetailLine(appPreferences.text("plugins.loop.detailStatus"), health.status)
            healthDetailLine(appPreferences.text("plugins.loop.detailAction"), health.currentActionType ?? appPreferences.text("plugins.loop.none"))
            healthDetailLine(appPreferences.text("plugins.loop.detailLease"), agentLoopLeaseSummary(health.lease))
            healthDetailLine(appPreferences.text("plugins.loop.detailHeartbeat"), timestampSummary(health.lease?.heartbeatAt))
            healthDetailLine(appPreferences.text("plugins.loop.detailCancellation"), cancelCategorySummary(health.cancellationCategory))
            healthDetailLine(appPreferences.text("plugins.loop.detailFailures"), failureSummary(health))
            healthDetailLine(appPreferences.text("plugins.loop.detailExecutableActions"), actionSummary(health.executableActions ?? []))
            if let summary = viewModel.agentLoopEvidenceSummary {
                Divider().opacity(0.25)
                healthDetailLine(appPreferences.text("plugins.loop.detailAudit"), auditSummary(summary.eventAudit))
                healthDetailLine(appPreferences.text("plugins.loop.detailRouting"), routingSummary(summary.routing))
                healthDetailLine(appPreferences.text("plugins.loop.detailRecovery"), recoverySummary(summary.recovery))
                recoveryEvidenceDetailLines(summary.recovery)
                healthDetailLine(appPreferences.text("plugins.loop.detailMemory"), memoryCandidateSummary(summary.memoryCandidates))
                memoryCandidateDetailLines(summary.memoryCandidates)
            }
        }
        .padding(14)
        .frame(width: 330, alignment: .leading)
    }

    private func healthDetailLine(_ title: String, _ value: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(title)
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(.secondary)
                .frame(width: 96, alignment: .leading)
            Text(value)
                .font(.system(size: 11))
                .foregroundColor(textColor)
                .lineLimit(2)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func agentLoopLeaseSummary(_ lease: AgentLoopLeaseHealth?) -> String {
        guard let lease else { return appPreferences.text("plugins.loop.none") }
        if lease.expired == true {
            return appPreferences.text("plugins.loop.leaseStale")
        }
        if lease.active == true, let remaining = lease.remainingSeconds {
            return String(format: appPreferences.text("plugins.loop.leaseRemaining"), Int(remaining.rounded()))
        }
        if let renewals = lease.renewalCount, renewals > 0 {
            return String(format: appPreferences.text("plugins.loop.renewalCount"), renewals)
        }
        return appPreferences.text("plugins.loop.leaseIdle")
    }

    private func timestampSummary(_ timestamp: Double?) -> String {
        guard let timestamp else { return appPreferences.text("plugins.loop.none") }
        let date = Date(timeIntervalSince1970: timestamp)
        return date.formatted(date: .omitted, time: .standard)
    }

    private func failureSummary(_ health: AgentLoopHealthResponse) -> String {
        guard let failures = health.recentFailureTypes, !failures.isEmpty else {
            return appPreferences.text("plugins.loop.none")
        }
        return failures
            .sorted { $0.key < $1.key }
            .map { "\($0.key.replacingOccurrences(of: "_", with: " ")): \($0.value)" }
            .joined(separator: ", ")
    }

    private func actionSummary(_ actions: [String]) -> String {
        actions.isEmpty ? appPreferences.text("plugins.loop.none") : actions.joined(separator: ", ")
    }

    private func auditSummary(_ audit: AgentLoopEvidenceEventAudit?) -> String {
        guard let audit else { return appPreferences.text("plugins.loop.none") }
        let eventCount = audit.eventCount ?? 0
        if audit.sequenceContiguous == true,
           audit.eventIdCoverage == true,
           audit.correlationIdCoverage == true {
            return String(format: appPreferences.text("plugins.loop.auditComplete"), eventCount)
        }
        return String(format: appPreferences.text("plugins.loop.auditPartial"), eventCount)
    }

    private func routingSummary(_ routing: AgentLoopEvidenceRouting?) -> String {
        guard let routing else { return appPreferences.text("plugins.loop.none") }
        return String(
            format: appPreferences.text("plugins.loop.routingSummary"),
            routing.routedActionCount ?? 0,
            routing.capabilityHintRouteCount ?? 0
        )
    }

    private func recoverySummary(_ recovery: AgentLoopEvidenceRecovery?) -> String {
        guard let recovery else { return appPreferences.text("plugins.loop.none") }
        return String(
            format: appPreferences.text("plugins.loop.recoverySummary"),
            recovery.decisionCount ?? 0,
            recovery.appliedCount ?? 0,
            recovery.blockedCount ?? 0
        )
    }

    @ViewBuilder
    private func recoveryEvidenceDetailLines(_ recovery: AgentLoopEvidenceRecovery?) -> some View {
        if let decision = recovery?.decisions?.first {
            healthDetailLine(
                appPreferences.text("plugins.loop.detailRecoveryPolicy"),
                recoveryDecisionSummary(decision, total: recovery?.decisions?.count ?? 1)
            )
        }
        if let recoveredStep = recovery?.recoveredSteps?.first {
            healthDetailLine(
                appPreferences.text("plugins.loop.detailRecoveredStep"),
                recoveredStepSummary(recoveredStep, total: recovery?.recoveredSteps?.count ?? 1)
            )
        }
    }

    private func recoveryDecisionSummary(_ decision: AgentLoopEvidenceRecoveryDecision, total: Int) -> String {
        var parts = [String]()
        if let action = displayToken(decision.recoveryAction) {
            parts.append(action)
        }
        if let failure = displayToken(decision.failureType) {
            parts.append(failure)
        }
        if let applied = decision.applied {
            parts.append(appPreferences.text(applied ? "plugins.loop.recoveryApplied" : "plugins.loop.recoveryBlocked"))
        }
        if let attempt = recoveryAttemptSummary(decision.attempt, maxRetries: decision.maxRetries) {
            parts.append(attempt)
        }
        if total > 1 {
            parts.append(String(format: appPreferences.text("plugins.loop.recoveryMore"), total - 1))
        }
        return parts.isEmpty ? appPreferences.text("plugins.loop.none") : parts.joined(separator: ", ")
    }

    private func recoveredStepSummary(_ step: AgentLoopEvidenceRecoveredStep, total: Int) -> String {
        var parts = [String]()
        let nextAction = displayToken(step.nextAction) ?? displayToken(step.actionType)
        if let nextAction, let failure = displayToken(step.failureType) {
            parts.append(String(format: appPreferences.text("plugins.loop.recoveredAfter"), nextAction, failure))
        } else if let nextAction {
            parts.append(nextAction)
        } else if let failure = displayToken(step.failureType) {
            parts.append(failure)
        }
        if let attempt = recoveryAttemptSummary(step.attempt, maxRetries: nil) {
            parts.append(attempt)
        }
        if let nextTurn = step.nextTurn {
            parts.append(String(format: appPreferences.text("plugins.loop.recoveryTurn"), nextTurn))
        }
        if total > 1 {
            parts.append(String(format: appPreferences.text("plugins.loop.recoveryMore"), total - 1))
        }
        return parts.isEmpty ? appPreferences.text("plugins.loop.none") : parts.joined(separator: ", ")
    }

    private func recoveryAttemptSummary(_ attempt: Int?, maxRetries: Int?) -> String? {
        guard let attempt else { return nil }
        if let maxRetries {
            return String(format: appPreferences.text("plugins.loop.recoveryAttempt"), attempt, maxRetries)
        }
        return String(format: appPreferences.text("plugins.loop.recoveryAttemptSingle"), attempt)
    }

    private func memoryCandidateSummary(_ candidates: AgentLoopEvidenceMemoryCandidates?) -> String {
        guard let candidates else { return appPreferences.text("plugins.loop.none") }
        return String(format: appPreferences.text("plugins.loop.memoryCandidateSummary"), candidates.candidateCount ?? 0)
    }

    @ViewBuilder
    private func memoryCandidateDetailLines(_ candidates: AgentLoopEvidenceMemoryCandidates?) -> some View {
        if let candidate = candidates?.candidates?.first {
            healthDetailLine(
                appPreferences.text("plugins.loop.detailMemoryCandidate"),
                memoryCandidateDetailSummary(candidate, total: candidates?.candidates?.count ?? 1)
            )
        }
    }

    private func memoryCandidateDetailSummary(_ candidate: AgentLoopEvidenceMemoryCandidate, total: Int) -> String {
        var parts = [String]()
        if let provider = displayToken(candidate.provider) {
            parts.append(provider)
        }
        if let status = displayToken(candidate.memoryStatus ?? candidate.status) {
            parts.append(status)
        }
        if let turn = candidate.turn {
            parts.append(String(format: appPreferences.text("plugins.loop.memoryCandidateTurn"), turn))
        }
        if total > 1 {
            parts.append(String(format: appPreferences.text("plugins.loop.evidenceMore"), total - 1))
        }
        return parts.isEmpty ? appPreferences.text("plugins.loop.none") : parts.joined(separator: ", ")
    }

    private func cancelCategorySummary(_ category: String?) -> String {
        guard let category, !category.isEmpty else { return appPreferences.text("plugins.loop.none") }
        return category.replacingOccurrences(of: "_", with: " ")
    }

    private func displayToken(_ value: String?) -> String? {
        guard let value, !value.isEmpty else { return nil }
        return value.replacingOccurrences(of: "_", with: " ")
    }

    private func agentLoopTimelineRow(_ events: [AgentLoopEventResponse], live: Bool) -> some View {
        let recentEvents = Array(events.suffix(4))
        return ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                metadataChip(appPreferences.text("plugins.loop.events"))
                metadataChip(appPreferences.text(live ? "plugins.loop.eventsLive" : "plugins.loop.eventsSnapshot"))
                ForEach(Array(recentEvents.enumerated()), id: \.offset) { _, event in
                    agentLoopEventChip(event)
                }
            }
        }
        .frame(height: 22, alignment: .leading)
    }

    private func agentLoopEventChip(_ event: AgentLoopEventResponse) -> some View {
        let color = agentLoopEventColor(event)
        return HStack(spacing: 5) {
            Circle().fill(color).frame(width: 5, height: 5)
            if let sequenceLabel = event.sequenceLabel {
                Text(sequenceLabel)
                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                    .foregroundColor(color.opacity(0.82))
                    .lineLimit(1)
            }
            Text(event.compactLabel)
                .font(.system(size: 10, weight: .semibold))
                .foregroundColor(color)
                .lineLimit(1)
                .truncationMode(.tail)
                .frame(maxWidth: 118, alignment: .leading)
        }
        .padding(.horizontal, 7)
        .frame(height: 22)
        .background(color.opacity(0.11))
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .help(agentLoopEventAuditHelp(event))
    }

    private func agentLoopEventAuditHelp(_ event: AgentLoopEventResponse) -> String {
        var rows = [event.compactLabel]
        if let sequence = event.sequence {
            rows.append("\(appPreferences.text("plugins.loop.eventSequence")): #\(sequence)")
        }
        if let eventId = event.eventId {
            rows.append("\(appPreferences.text("plugins.loop.eventId")): \(eventId)")
        }
        if let correlationId = event.correlationId {
            rows.append("\(appPreferences.text("plugins.loop.correlationId")): \(correlationId)")
        }
        if let stepId = event.stepId {
            rows.append("\(appPreferences.text("plugins.loop.stepId")): \(stepId)")
        }
        if let actionId = event.actionId {
            rows.append("\(appPreferences.text("plugins.loop.actionId")): \(actionId)")
        }
        if let taskId = event.taskId {
            rows.append("\(appPreferences.text("plugins.loop.taskId")): \(taskId)")
        }
        if let subtaskId = event.subtaskId {
            rows.append("\(appPreferences.text("plugins.loop.subtaskId")): \(subtaskId)")
        }
        return rows.joined(separator: "\n")
    }

    private func agentLoopEventColor(_ event: AgentLoopEventResponse) -> Color {
        let type = event.type
        if type.contains("failed") || type.contains("stopped") || type.contains("cancelled") || type.contains("rejected") {
            return Color(hex: "ff453a")
        }
        if type.contains("approval") || type.contains("retry") {
            return Color(hex: "ff9f0a")
        }
        if type.contains("completed") {
            return Color(hex: "30d158")
        }
        if type.contains("heartbeat") || type.contains("started") {
            return Color(hex: "0a84ff")
        }
        return .secondary
    }

    private func statusChip(_ plugin: AcrossPluginStatus) -> some View {
        let ready = plugin.installed && plugin.available
        let color = ready ? Color(hex: "30d158") : plugin.installed ? Color(hex: "ff9f0a") : Color.secondary
        return HStack(spacing: 5) {
            Circle().fill(color).frame(width: 6, height: 6)
            Text(statusText(plugin))
                .font(.system(size: 10, weight: .bold))
                .foregroundColor(color)
                .lineLimit(1)
        }
        .padding(.horizontal, 8)
        .frame(height: 24)
        .background(color.opacity(0.11))
        .clipShape(RoundedRectangle(cornerRadius: 7))
    }

    private func metadataChip(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 10, weight: .semibold))
            .foregroundColor(.secondary)
            .lineLimit(1)
            .padding(.horizontal, 7)
            .frame(height: 22)
            .background(fieldColor)
            .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    private func pathRow(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title)
                .font(.system(size: 10, weight: .bold))
                .foregroundColor(.secondary)
            Text(value)
                .font(.system(size: 10, design: .monospaced))
                .foregroundColor(textColor.opacity(0.78))
                .lineLimit(1)
                .truncationMode(.middle)
        }
    }

    private func actionButton(_ action: String, icon: String, title: String, plugin: AcrossPluginStatus) -> some View {
        Button {
            Task { await viewModel.runAction(action, for: plugin) }
        } label: {
            Image(systemName: icon)
                .font(.system(size: 12, weight: .semibold))
                .frame(width: 30, height: 28)
        }
        .buttonStyle(.plain)
        .foregroundColor(textColor)
        .background(fieldColor)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .help(title)
        .disabled(viewModel.isWorking)
    }

    private var memorySection: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 10) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(appPreferences.text("plugins.memory.title"))
                        .font(.system(size: 18, weight: .bold))
                        .foregroundColor(textColor)
                    Text(appPreferences.text("plugins.memory.subtitle"))
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                }
                Spacer()
                Picker("", selection: $viewModel.memoryStatusFilter) {
                    Text(appPreferences.text("plugins.memory.pending")).tag("pending")
                    Text(appPreferences.text("plugins.memory.active")).tag("active")
                    Text(appPreferences.text("plugins.memory.archived")).tag("archived")
                    Text(appPreferences.text("plugins.memory.all")).tag("")
                }
                .labelsHidden()
                .frame(width: 140)
                .onChange(of: viewModel.memoryStatusFilter) {
                    Task { await viewModel.loadMemories() }
                }
                Button {
                    Task { await viewModel.loadMemories() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 12, weight: .semibold))
                        .frame(width: 30, height: 28)
                }
                .buttonStyle(.plain)
                .foregroundColor(textColor)
                .background(fieldColor)
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .help(appPreferences.text("settings.refresh"))
            }

            HStack(spacing: 10) {
                TextField(appPreferences.text("plugins.memory.placeholder"), text: $viewModel.newMemoryText)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(textColor)
                    .padding(.horizontal, 10)
                    .frame(height: 34)
                    .background(fieldColor)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                Button {
                    Task { await viewModel.rememberPendingMemory() }
                } label: {
                    Image(systemName: "plus")
                        .font(.system(size: 12, weight: .bold))
                        .frame(width: 32, height: 30)
                }
                .buttonStyle(.plain)
                .foregroundColor(textColor)
                .background(accentColor.opacity(0.18))
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .help(appPreferences.text("plugins.memory.add"))
                .disabled(viewModel.newMemoryText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }

            VStack(spacing: 10) {
                if viewModel.memories.isEmpty {
                    Text(appPreferences.text("plugins.memory.empty"))
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                        .frame(maxWidth: .infinity, minHeight: 48, alignment: .center)
                } else {
                    ForEach(viewModel.memories) { memory in
                        memoryRow(memory)
                    }
                }
            }
        }
        .padding(.top, 4)
    }

    private func memoryRow(_ memory: AcrossMemoryEntry) -> some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 5) {
                HStack(spacing: 6) {
                    metadataChip(memory.status)
                    metadataChip(memory.scope)
                    metadataChip(memory.type)
                    if let projectName = memory.projectName {
                        metadataChip(projectName)
                    }
                }
                Text(memory.text)
                    .font(.system(size: 12))
                    .foregroundColor(textColor)
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Spacer(minLength: 12)

            HStack(spacing: 6) {
                memoryAction(memory, status: "active", icon: "checkmark", title: appPreferences.text("plugins.memory.approve"))
                memoryAction(memory, status: "archived", icon: "archivebox", title: appPreferences.text("plugins.memory.archive"))
                Button {
                    Task { await viewModel.forgetMemory(memory) }
                } label: {
                    Image(systemName: "trash")
                        .font(.system(size: 11, weight: .semibold))
                        .frame(width: 28, height: 26)
                }
                .buttonStyle(.plain)
                .foregroundColor(textColor)
                .background(fieldColor)
                .clipShape(RoundedRectangle(cornerRadius: 7))
                .help(appPreferences.text("plugins.memory.forget"))
            }
        }
        .padding(12)
        .background(fieldColor.opacity(colorScheme == .dark ? 0.7 : 1.0))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private func memoryAction(_ memory: AcrossMemoryEntry, status: String, icon: String, title: String) -> some View {
        Button {
            Task { await viewModel.updateMemory(memory, status: status) }
        } label: {
            Image(systemName: icon)
                .font(.system(size: 11, weight: .semibold))
                .frame(width: 28, height: 26)
        }
        .buttonStyle(.plain)
        .foregroundColor(textColor)
        .background(fieldColor)
        .clipShape(RoundedRectangle(cornerRadius: 7))
        .help(title)
    }

    private func iconName(for id: String) -> String {
        switch id {
        case "across-context": return "memorychip.fill"
        case "across-orchestrator": return "point.3.connected.trianglepath.dotted"
        default: return "puzzlepiece"
        }
    }

    @ViewBuilder
    private func pluginIcon(for id: String) -> some View {
        switch id {
        case "across-context", "across-orchestrator":
            Image(systemName: iconName(for: id))
                .font(.system(size: 16, weight: .semibold))
                .foregroundColor(accentColor)
        default:
            BundledTemplateIcon(
                name: "ui.plugin-center",
                fallbackSystemName: "puzzlepiece",
                size: 16,
                color: accentColor
            )
        }
    }

    private func statusText(_ plugin: AcrossPluginStatus) -> String {
        if plugin.installed && plugin.available { return appPreferences.text("plugins.status.ready") }
        if plugin.installed { return appPreferences.text("plugins.status.installed") }
        return appPreferences.text("plugins.status.missing")
    }
}
