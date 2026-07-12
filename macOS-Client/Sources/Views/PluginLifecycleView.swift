import SwiftUI

struct PluginLifecycleView: View {
    @StateObject private var viewModel = PluginLifecycleViewModel()
    @State private var showingLoopHealthDetails = false
    @State private var showingLoopEvidenceDetails = false
    @State private var expandedPluginIds: Set<String> = []
    @State private var pluginPendingUninstall: AcrossPluginStatus?
    @State private var memoryPendingForget: AcrossMemoryEntry?
    @EnvironmentObject private var appPreferences: AppPreferences
    @Environment(\.colorScheme) private var colorScheme

    var onClose: (() -> Void)? = nil
    var embeddedInHub: Bool = false

    private var bgColor: Color { Color(nsColor: .windowBackgroundColor) }
    private var cardColor: Color { Color(nsColor: .controlBackgroundColor) }
    private var fieldColor: Color { Color(nsColor: .controlBackgroundColor) }
    private var lineColor: Color { colorScheme == .dark ? Color.white.opacity(0.10) : Color.black.opacity(0.10) }
    private var textColor: Color { colorScheme == .dark ? .legacyTextDark : .legacyTextLight }
    private var accentColor: Color { AcrossTheme.accent }

    var body: some View {
        VStack(spacing: 0) {
            if !embeddedInHub {
                standaloneHeader
            }

            ScrollView {
                VStack(alignment: .leading, spacing: MinimalSettingsMetrics.sectionSpacing) {
                    titleRow
                    feedbackRows
                    VStack(spacing: 0) {
                        Divider()
                        ForEach(Array(viewModel.plugins.enumerated()), id: \.element.id) { index, plugin in
                            pluginCard(plugin)
                            if index < viewModel.plugins.count - 1 {
                                Divider().padding(.leading, 30)
                            }
                        }
                        Divider()
                    }
                }
                .padding(MinimalSettingsMetrics.contentPadding)
                .frame(maxWidth: MinimalSettingsMetrics.contentMaxWidth, alignment: .leading)
                .frame(maxWidth: .infinity)
            }
            .overlay {
                if viewModel.isWorking {
                    ProgressView()
                        .controlSize(.small)
                        .padding(18)
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
            await viewModel.loadPlugins()
            expandedPluginIds = Set(
                viewModel.plugins
                    .filter { !$0.installed || !$0.available }
                    .map(\.pluginId)
            )
        }
        .confirmationDialog(
            appPreferences.text("plugins.action.uninstallConfirmTitle"),
            isPresented: Binding(
                get: { pluginPendingUninstall != nil },
                set: { if !$0 { pluginPendingUninstall = nil } }
            ),
            titleVisibility: .visible
        ) {
            Button(appPreferences.text("plugins.action.uninstall"), role: .destructive) {
                if let plugin = pluginPendingUninstall {
                    Task { await viewModel.runAction("uninstall", for: plugin) }
                }
                pluginPendingUninstall = nil
            }
            Button(appPreferences.text("system.cancel"), role: .cancel) {
                pluginPendingUninstall = nil
            }
        } message: {
            Text(appPreferences.text("plugins.action.uninstallConfirmMessage"))
        }
        .confirmationDialog(
            appPreferences.text("plugins.memory.forgetConfirmTitle"),
            isPresented: Binding(
                get: { memoryPendingForget != nil },
                set: { if !$0 { memoryPendingForget = nil } }
            ),
            titleVisibility: .visible
        ) {
            Button(appPreferences.text("plugins.memory.forget"), role: .destructive) {
                if let memory = memoryPendingForget {
                    Task { await viewModel.forgetMemory(memory) }
                }
                memoryPendingForget = nil
            }
            Button(appPreferences.text("system.cancel"), role: .cancel) {
                memoryPendingForget = nil
            }
        } message: {
            Text(appPreferences.text("plugins.memory.forgetConfirmMessage"))
        }
    }

    private var standaloneHeader: some View {
        MinimalSettingsWindowHeader(title: appPreferences.text("plugins.title"), onClose: onClose)
    }

    private var titleRow: some View {
        MinimalSettingsPageHeader(
            title: appPreferences.text("plugins.title"),
            subtitle: appPreferences.text("plugins.subtitle")
        ) {
            Button {
                Task { await viewModel.load(probe: true) }
            } label: {
                Image(systemName: "arrow.clockwise")
                    .font(.system(size: 13, weight: .semibold))
                    .frame(width: 24, height: 24)
            }
            .buttonStyle(.borderless)
            .help(appPreferences.text("settings.refresh"))
        }
    }

    @ViewBuilder
    private var feedbackRows: some View {
        if let message = viewModel.message {
            banner(message, color: Color(nsColor: .systemGreen))
        }
        if let error = viewModel.errorMessage {
            banner(error, color: Color(nsColor: .systemRed))
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
        DisclosureGroup(isExpanded: Binding(
            get: { expandedPluginIds.contains(plugin.pluginId) },
            set: { expanded in
                if expanded {
                    expandedPluginIds.insert(plugin.pluginId)
                } else {
                    expandedPluginIds.remove(plugin.pluginId)
                }
            }
        )) {
            VStack(alignment: .leading, spacing: 12) {
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
                        agentLoopTimelineModePicker()
                        Button {
                            Task { await viewModel.runAgentLoopProbe() }
                        } label: {
                            Image(systemName: "play.circle")
                                .font(.system(size: 12, weight: .semibold))
                                .frame(width: 30, height: 28)
                        }
                        .buttonStyle(.borderless)
                        .help(appPreferences.text("plugins.loop.probe"))
                        .disabled(viewModel.isWorking)
                    }
                }

                agentLoopProbeRow(plugin)
            }
            .padding(.leading, 28)
            .padding(.bottom, 12)
        } label: {
            HStack(alignment: .center, spacing: 10) {
                pluginIcon(for: plugin.pluginId)
                    .frame(width: 24, height: 24)

                VStack(alignment: .leading, spacing: 3) {
                    Text(plugin.displayName)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(textColor)
                        .lineLimit(1)
                    Text(plugin.kind)
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                }

                Spacer()

                statusChip(plugin)
            }
            .padding(.vertical, 10)
            .contentShape(Rectangle())
        }
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
                            if let telemetry = viewModel.agentLoopTelemetry {
                                metadataChip(agentLoopTelemetryChipSummary(telemetry))
                            }
                            if let health = viewModel.agentLoopHealth {
                                if let budget = health.budget ?? viewModel.agentLoopTelemetry?.budget ?? viewModel.agentLoopEvidenceSummary?.budget {
                                    metadataChip(agentLoopBudgetChipSummary(budget))
                                }
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
                        agentLoopTimelineRow(viewModel.agentLoopEvents, source: viewModel.agentLoopTimelineSource)
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
        .foregroundColor(health.needsAttention ? Color(nsColor: .systemOrange) : .secondary)
        .background(fieldColor)
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .help(appPreferences.text("plugins.loop.healthDetails"))
        .popover(isPresented: $showingLoopHealthDetails, arrowEdge: .bottom) {
            agentLoopHealthPopover(health)
        }
    }

    private func agentLoopTimelineModePicker() -> some View {
        Picker("", selection: $viewModel.agentLoopTimelineMode) {
            Text(appPreferences.text("plugins.loop.eventsLive")).tag(AgentLoopTimelineMode.live)
            Text(appPreferences.text("plugins.loop.eventsSnapshot")).tag(AgentLoopTimelineMode.snapshot)
        }
        .pickerStyle(.segmented)
        .labelsHidden()
        .frame(width: 128, height: 28)
        .disabled(viewModel.isRunningAgentLoopProbe)
        .help(appPreferences.text("plugins.loop.timelineMode"))
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
            healthDetailLine(
                appPreferences.text("plugins.loop.detailBudget"),
                agentLoopBudgetDetailSummary(health.budget ?? viewModel.agentLoopTelemetry?.budget ?? viewModel.agentLoopEvidenceSummary?.budget)
            )
            healthDetailLine(appPreferences.text("plugins.loop.detailFailures"), failureSummary(health))
            healthDetailLine(appPreferences.text("plugins.loop.detailExecutableActions"), actionSummary(health.executableActions ?? []))
            healthDetailLine(appPreferences.text("plugins.loop.detailTelemetry"), agentLoopTelemetryDetailSummary(viewModel.agentLoopTelemetry))
            if let summary = viewModel.agentLoopEvidenceSummary {
                Divider().opacity(0.25)
                healthDetailLine(appPreferences.text("plugins.loop.detailReleaseEvidence"), hostReleaseEvidenceSummary(summary.hostReleaseEvidence))
                DisclosureGroup(isExpanded: $showingLoopEvidenceDetails) {
                    VStack(alignment: .leading, spacing: 8) {
                        hostReleaseEvidenceDetailLines(summary.hostReleaseEvidence)
                        healthDetailLine(appPreferences.text("plugins.loop.detailAudit"), auditSummary(summary.eventAudit))
                        healthDetailLine(appPreferences.text("plugins.loop.detailRouting"), routingSummary(summary.routing))
                        routingEvidenceDetailLines(summary.routing)
                        healthDetailLine(appPreferences.text("plugins.loop.detailRecovery"), recoverySummary(summary.recovery))
                        recoveryEvidenceDetailLines(summary.recovery)
                        healthDetailLine(appPreferences.text("plugins.loop.detailMemory"), memoryCandidateSummary(summary.memoryCandidates))
                        memoryCandidateDetailLines(summary.memoryCandidates)
                    }
                    .padding(.top, 4)
                } label: {
                    Text(appPreferences.text("plugins.loop.evidenceDetails"))
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(textColor)
                }
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

    private func hostReleaseEvidenceSummary(_ evidence: AgentLoopHostReleaseEvidence?) -> String {
        guard let evidence, let readiness = displayToken(evidence.readiness) else {
            return appPreferences.text("plugins.loop.none")
        }
        let riskCount = evidence.riskCount ?? evidence.risks?.count ?? 0
        if riskCount > 0 {
            return String(format: appPreferences.text("plugins.loop.releaseEvidenceWithRisks"), readiness, riskCount)
        }
        return readiness
    }

    @ViewBuilder
    private func hostReleaseEvidenceDetailLines(_ evidence: AgentLoopHostReleaseEvidence?) -> some View {
        let attentionChecks = evidence?.checks?.filter { $0.status != nil && $0.status != "passed" } ?? []
        if !attentionChecks.isEmpty {
            ForEach(Array(attentionChecks.prefix(3).enumerated()), id: \.offset) { index, check in
                healthDetailLine(
                    index == 0 ? appPreferences.text("plugins.loop.detailReleaseCheck") : "",
                    hostReleaseCheckSummary(check)
                )
            }
            if attentionChecks.count > 3 {
                healthDetailLine("", String(format: appPreferences.text("plugins.loop.recoveryMore"), attentionChecks.count - 3))
            }
        }
        let risks = evidence?.risks ?? []
        if !risks.isEmpty {
            ForEach(Array(risks.prefix(3).enumerated()), id: \.offset) { index, risk in
                healthDetailLine(
                    index == 0 ? appPreferences.text("plugins.loop.detailReleaseRisk") : "",
                    hostReleaseRiskSummary(risk)
                )
            }
            if risks.count > 3 {
                healthDetailLine("", String(format: appPreferences.text("plugins.loop.recoveryMore"), risks.count - 3))
            }
        }
        let nextActions = (evidence?.nextActions ?? []).filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        if !nextActions.isEmpty {
            ForEach(Array(nextActions.prefix(3).enumerated()), id: \.offset) { index, nextAction in
                healthDetailLine(index == 0 ? appPreferences.text("plugins.loop.detailReleaseNext") : "", nextAction)
            }
            if nextActions.count > 3 {
                healthDetailLine("", String(format: appPreferences.text("plugins.loop.recoveryMore"), nextActions.count - 3))
            }
        }
    }

    private func hostReleaseCheckSummary(_ check: AgentLoopHostReleaseCheck) -> String {
        var parts = [String]()
        if let id = displayToken(check.id) {
            parts.append(id)
        }
        if let status = displayToken(check.status) {
            parts.append(status)
        }
        if let summary = check.summary, !summary.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            parts.append(summary)
        }
        return parts.isEmpty ? appPreferences.text("plugins.loop.none") : parts.joined(separator: ", ")
    }

    private func hostReleaseRiskSummary(_ risk: AgentLoopHostReleaseRisk) -> String {
        var parts = [String]()
        if let severity = displayToken(risk.severity) {
            parts.append(severity)
        }
        if let summary = risk.summary, !summary.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            parts.append(summary)
        }
        return parts.isEmpty ? appPreferences.text("plugins.loop.none") : parts.joined(separator: ", ")
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

    @ViewBuilder
    private func routingEvidenceDetailLines(_ routing: AgentLoopEvidenceRouting?) -> some View {
        if let outcome = routing?.outcomes?.first {
            healthDetailLine(
                appPreferences.text("plugins.loop.detailRoutingOutcome"),
                routingOutcomeSummary(outcome, total: routing?.outcomes?.count ?? 1)
            )
            if let alternative = routingSelectedAlternative(outcome) {
                healthDetailLine(
                    appPreferences.text("plugins.loop.detailRoutingAlternative"),
                    routingAlternativeSummary(alternative, total: outcome.alternatives?.count ?? 1)
                )
            }
        }
    }

    private func routingOutcomeSummary(_ outcome: AgentLoopEvidenceRoutingOutcome, total: Int) -> String {
        var parts = [String]()
        if let selected = displayToken(outcome.selectedAgent) {
            parts.append(String(format: appPreferences.text("plugins.loop.routingSelected"), selected))
        }
        if let reason = outcome.reason, !reason.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            parts.append(reason)
        } else if let source = displayToken(outcome.source) {
            parts.append(source)
        }
        if let alternatives = outcome.alternatives, !alternatives.isEmpty {
            parts.append(String(format: appPreferences.text("plugins.loop.routingAlternatives"), alternatives.count))
        }
        if total > 1 {
            parts.append(String(format: appPreferences.text("plugins.loop.evidenceMore"), total - 1))
        }
        return parts.isEmpty ? appPreferences.text("plugins.loop.none") : parts.joined(separator: ", ")
    }

    private func routingSelectedAlternative(_ outcome: AgentLoopEvidenceRoutingOutcome) -> AgentLoopRoutingAlternative? {
        if let selected = outcome.alternatives?.first(where: { $0.selected == true }) {
            return selected
        }
        return outcome.alternatives?.first
    }

    private func routingAlternativeSummary(_ alternative: AgentLoopRoutingAlternative, total: Int) -> String {
        var parts = [String]()
        if let agentId = displayToken(alternative.agentId) {
            parts.append(agentId)
        }
        if alternative.selected == true {
            parts.append(appPreferences.text("plugins.loop.routingAlternativeSelected"))
        }
        if alternative.matched == true {
            parts.append(appPreferences.text("plugins.loop.routingAlternativeMatched"))
        }
        if let matchedCapability = displayToken(alternative.matchedCapability) {
            parts.append(matchedCapability)
        }
        if alternative.forbidden == true {
            parts.append(appPreferences.text("plugins.loop.routingAlternativeForbidden"))
        }
        if let count = alternative.capabilityCount {
            parts.append(String(format: appPreferences.text("plugins.loop.routingCapabilityCount"), count))
        }
        if let reason = alternative.reason, !reason.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            parts.append(reason)
        }
        if total > 1 {
            parts.append(String(format: appPreferences.text("plugins.loop.evidenceMore"), total - 1))
        }
        return parts.isEmpty ? appPreferences.text("plugins.loop.none") : parts.joined(separator: ", ")
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

    private func agentLoopBudgetChipSummary(_ budget: AgentLoopBudgetSummary) -> String {
        if let turnsLabel = budget.turnsLabel {
            return String(format: appPreferences.text("plugins.loop.budgetTurns"), turnsLabel)
        }
        if let remaining = budget.turnsRemaining {
            return String(format: appPreferences.text("plugins.loop.budgetRemaining"), remaining)
        }
        return appPreferences.text("plugins.loop.budget")
    }

    private func agentLoopBudgetDetailSummary(_ budget: AgentLoopBudgetSummary?) -> String {
        guard let budget else { return appPreferences.text("plugins.loop.none") }
        var parts = [String]()
        if let turnsLabel = budget.turnsLabel {
            parts.append(String(format: appPreferences.text("plugins.loop.budgetTurns"), turnsLabel))
        }
        if let remaining = budget.turnsRemaining {
            parts.append(String(format: appPreferences.text("plugins.loop.budgetRemaining"), remaining))
        }
        if let runtime = budget.runtimeSeconds {
            parts.append(String(format: appPreferences.text("plugins.loop.budgetRuntime"), Int(runtime.rounded())))
        }
        if let maxRuntime = budget.maxRuntimeSeconds {
            parts.append(String(format: appPreferences.text("plugins.loop.budgetRuntimeMax"), Int(maxRuntime.rounded())))
        }
        return parts.isEmpty ? appPreferences.text("plugins.loop.none") : parts.joined(separator: ", ")
    }

    private func agentLoopTelemetryChipSummary(_ telemetry: AgentLoopTelemetryResponse) -> String {
        let eventCount = telemetry.summary?.eventCount ?? 0
        let turnCount = telemetry.summary?.turnCount ?? 0
        return String(format: appPreferences.text("plugins.loop.telemetrySummary"), eventCount, turnCount)
    }

    private func agentLoopTelemetryDetailSummary(_ telemetry: AgentLoopTelemetryResponse?) -> String {
        guard let telemetry else { return appPreferences.text("plugins.loop.none") }
        var parts = [agentLoopTelemetryChipSummary(telemetry)]
        if let duration = telemetry.summary?.durationMs {
            parts.append(String(format: appPreferences.text("plugins.loop.telemetryDuration"), duration))
        }
        if let memoryCandidates = telemetry.summary?.memoryCandidateCount {
            parts.append(String(format: appPreferences.text("plugins.loop.telemetryMemoryCandidates"), memoryCandidates))
        }
        if let recoveryDecisions = telemetry.summary?.recoveryDecisionCount {
            parts.append(String(format: appPreferences.text("plugins.loop.telemetryRecoveryDecisions"), recoveryDecisions))
        }
        if let cancelCategory = telemetry.summary?.cancelCategory {
            parts.append(cancelCategorySummary(cancelCategory))
        }
        if let latestSequence = telemetry.latestSequence {
            parts.append(String(format: appPreferences.text("plugins.loop.telemetryLatestSequence"), latestSequence))
        }
        return parts.joined(separator: ", ")
    }

    private func cancelCategorySummary(_ category: String?) -> String {
        guard let category, !category.isEmpty else { return appPreferences.text("plugins.loop.none") }
        return category.replacingOccurrences(of: "_", with: " ")
    }

    private func displayToken(_ value: String?) -> String? {
        guard let value, !value.isEmpty else { return nil }
        return value.replacingOccurrences(of: "_", with: " ")
    }

    private func agentLoopTimelineRow(_ events: [AgentLoopEventResponse], source: AgentLoopTimelineSource?) -> some View {
        let recentEvents = Array(events.suffix(4))
        return ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                metadataChip(appPreferences.text("plugins.loop.events"))
                metadataChip(appPreferences.text((source ?? .snapshot).localizationKey))
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
            return Color(nsColor: .systemRed)
        }
        if type.contains("approval") || type.contains("retry") {
            return Color(nsColor: .systemOrange)
        }
        if type.contains("completed") {
            return Color(nsColor: .systemGreen)
        }
        if type.contains("heartbeat") || type.contains("started") {
            return Color(nsColor: .systemBlue)
        }
        return .secondary
    }

    private func statusChip(_ plugin: AcrossPluginStatus) -> some View {
        let ready = plugin.installed && plugin.available
        let color = ready
            ? Color(nsColor: .systemGreen)
            : plugin.installed ? Color(nsColor: .systemOrange) : Color.secondary
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
            if action == "uninstall" {
                pluginPendingUninstall = plugin
            } else {
                Task { await viewModel.runAction(action, for: plugin) }
            }
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
                if let metrics = viewModel.agentLoopMemoryMetrics {
                    metadataChip(agentLoopMemoryMetricsSummary(metrics))
                }
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

            if !viewModel.agentLoopMemoryCandidates.isEmpty {
                loopMemoryCandidateList(viewModel.agentLoopMemoryCandidates)
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

    private func loopMemoryCandidateList(_ candidates: [AgentLoopEvidenceMemoryCandidate]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Text(appPreferences.text("plugins.memory.loopCandidates"))
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(textColor)
                Spacer()
                metadataChip(String(format: appPreferences.text("plugins.memory.loopCandidateCount"), candidates.count))
            }
            ForEach(Array(candidates.enumerated()), id: \.offset) { _, candidate in
                loopMemoryCandidateRow(candidate)
            }
        }
    }

    private func agentLoopMemoryMetricsSummary(_ metrics: AgentLoopMemoryMetricsResponse) -> String {
        let total = metrics.totals?.candidateCount ?? 0
        let pending = metrics.totals?.pendingCount ?? 0
        return String(format: appPreferences.text("plugins.memory.loopMetrics"), total, pending)
    }

    private func loopMemoryCandidateRow(_ candidate: AgentLoopEvidenceMemoryCandidate) -> some View {
        HStack(alignment: .center, spacing: 10) {
            VStack(alignment: .leading, spacing: 5) {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        if let provider = displayToken(candidate.provider) {
                            metadataChip(provider)
                        }
                        metadataChip(displayToken(candidate.memoryStatus ?? candidate.status) ?? appPreferences.text("plugins.loop.none"))
                        if let turn = candidate.turn {
                            metadataChip(String(format: appPreferences.text("plugins.loop.memoryCandidateTurn"), turn))
                        }
                        if let memoryId = candidate.memoryId {
                            metadataChip(shortIdentifier(memoryId))
                        }
                    }
                }
                .frame(height: 22, alignment: .leading)
                if let stepId = candidate.stepId {
                    Text(stepId)
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
            }

            Spacer(minLength: 10)

            Button {
                Task { await viewModel.focusMemoryCandidate(candidate) }
            } label: {
                Image(systemName: "scope")
                    .font(.system(size: 11, weight: .semibold))
                    .frame(width: 28, height: 26)
            }
            .buttonStyle(.plain)
            .foregroundColor(textColor)
            .background(fieldColor)
            .clipShape(RoundedRectangle(cornerRadius: 7))
            .help(appPreferences.text("plugins.memory.focusCandidate"))
        }
        .padding(10)
        .background(fieldColor.opacity(colorScheme == .dark ? 0.48 : 0.7))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }

    private func memoryRow(_ memory: AcrossMemoryEntry) -> some View {
        let isHighlighted = viewModel.highlightedMemoryId == memory.id
        return HStack(alignment: .top, spacing: 12) {
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
                    memoryPendingForget = memory
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
        .background(isHighlighted ? accentColor.opacity(0.10) : fieldColor.opacity(colorScheme == .dark ? 0.7 : 1.0))
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(isHighlighted ? accentColor.opacity(0.7) : Color.clear, lineWidth: 1)
        )
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

    private func shortIdentifier(_ value: String) -> String {
        if value.count <= 18 {
            return value
        }
        return "\(value.prefix(10))...\(value.suffix(5))"
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
