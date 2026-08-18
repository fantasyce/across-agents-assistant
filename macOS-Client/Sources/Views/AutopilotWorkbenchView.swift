import SwiftUI

struct AutopilotWorkbenchView: View {
    @StateObject private var viewModel = AutopilotWorkbenchViewModel()
    @StateObject private var evidenceViewModel = AutopilotEvidenceViewModel()
    @StateObject private var workspaceReadiness = AgentWorkspaceReadinessViewModel()
    @State private var showsTechnicalEvidence = false
    @State private var showsFocusedEvidenceDetails = false
    @EnvironmentObject private var appPreferences: AppPreferences
    @Environment(\.colorScheme) private var colorScheme

    let evidenceTarget: AutopilotEvidenceTarget?

    init(evidenceTarget: AutopilotEvidenceTarget? = nil) {
        self.evidenceTarget = evidenceTarget
    }

    private var bgColor: Color { colorScheme == .dark ? .legacyBgDark : .legacyBgLight }
    private var cardColor: Color { colorScheme == .dark ? Color(hex: "202227") : Color(hex: "fafbfc") }
    private var fieldColor: Color { colorScheme == .dark ? Color(hex: "15171b") : Color.black.opacity(0.045) }
    private var lineColor: Color { colorScheme == .dark ? Color.white.opacity(0.10) : Color.black.opacity(0.10) }
    private var textColor: Color { colorScheme == .dark ? .legacyTextDark : .legacyTextLight }

    private let summaryColumns = [GridItem(.adaptive(minimum: 176), spacing: 18)]
    private let sectionColumns = [GridItem(.adaptive(minimum: 280), spacing: 14)]
    private let sectionCardHeight: CGFloat = 176
    private let sectionOrder = [
        "self_iteration",
        "triggers",
        "runs",
        "promotion",
        "ops",
        "capabilities",
        "memory",
        "agent_plugins",
        "agent_interop_e2e",
        "protocols",
        "plugins",
        "protocol_gateway",
        "tool_pack_registry",
        "trust_sandbox",
        "evaluation_telemetry",
        "context_packs",
        "external_agents",
        "agent_plugin_runtime",
    ]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: SettingsHubPageLayout.sectionSpacing) {
                titleRow
                feedbackRows
                focusedEvidenceSection
                agentWorkspaceReadinessSection

                if let snapshot = viewModel.snapshot {
                    summaryGrid(snapshot)
                    actionSection(snapshot)
                    technicalEvidenceSection(snapshot)
                } else if viewModel.isLoading {
                    loadingRow
                }
            }
            .minimalPageContentFrame()
        }
        .overlay {
            if viewModel.isWorking && viewModel.activeActionID == nil {
                ProgressView()
                    .controlSize(.small)
                    .padding(18)
                    .background(cardColor)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                    .shadow(color: Color.black.opacity(0.16), radius: 18, x: 0, y: 8)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(bgColor)
        .task {
            async let workbenchLoad: Void = viewModel.load()
            async let readinessLoad: Void = workspaceReadiness.load()
            _ = await (workbenchLoad, readinessLoad)
        }
        .task(id: evidenceTarget) {
            showsFocusedEvidenceDetails = false
            await evidenceViewModel.load(target: evidenceTarget)
        }
    }

    private var titleRow: some View {
        MinimalPageHeader(
            title: appPreferences.text("workbench.title"),
            subtitle: appPreferences.text("workbench.subtitle")
        ) {
            MinimalIconButton(
                systemName: "arrow.clockwise",
                label: appPreferences.text("workbench.refresh"),
                isDisabled: viewModel.isWorking || viewModel.isLoading
            ) {
                Task {
                    async let workbenchLoad: Void = viewModel.load(refresh: true)
                    async let readinessLoad: Void = workspaceReadiness.load(refresh: true)
                    _ = await (workbenchLoad, readinessLoad)
                }
            }
            MinimalIconButton(
                systemName: "play.circle.fill",
                label: appPreferences.text("workbench.selfCheck"),
                isDisabled: viewModel.isWorking || viewModel.isLoading
            ) {
                Task {
                    await viewModel.load(refresh: true)
                }
            }
            MinimalIconButton(
                systemName: "timer",
                label: appPreferences.text("workbench.tick"),
                isDisabled: viewModel.isWorking || viewModel.isLoading
            ) {
                Task {
                    await viewModel.tickTriggers(
                        successMessage: appPreferences.text("workbench.action.tick.success")
                    )
                }
            }
            MinimalIconButton(
                systemName: "play.circle",
                label: appPreferences.text("workbench.scheduler.start"),
                isDisabled: viewModel.isWorking || viewModel.isLoading || viewModel.snapshot?.summary.schedulerRunning == true
            ) {
                Task {
                    await viewModel.startScheduler(
                        successMessage: appPreferences.text("workbench.action.schedulerStarted.success")
                    )
                }
            }
            MinimalIconButton(
                systemName: "stop.circle",
                label: appPreferences.text("workbench.scheduler.stop"),
                isDisabled: viewModel.isWorking || viewModel.isLoading || viewModel.snapshot?.summary.schedulerRunning != true
            ) {
                Task {
                    await viewModel.stopScheduler(
                        successMessage: appPreferences.text("workbench.action.schedulerStopped.success")
                    )
                }
            }
            MinimalIconButton(
                systemName: "point.3.connected.trianglepath.dotted",
                label: appPreferences.text("workbench.interopE2E.run"),
                isDisabled: viewModel.isWorking || viewModel.isLoading
            ) {
                Task {
                    await viewModel.runAgentInteropE2E(
                        successMessage: appPreferences.text("workbench.action.interop.success"),
                        failureMessage: appPreferences.text("workbench.action.interop.failed")
                    )
                }
            }
        }
    }

    @ViewBuilder
    private var feedbackRows: some View {
        if let message = viewModel.message {
            banner(message, color: statusColor("passed"))
        }
        if let error = viewModel.errorMessage {
            banner(error, color: statusColor("failed"))
        }
    }

    @ViewBuilder
    private var agentWorkspaceReadinessSection: some View {
        if let snapshot = workspaceReadiness.snapshot {
            agentWorkspaceReadinessPanel(snapshot)
        } else if workspaceReadiness.isLoading {
            loadingPanel(title: appPreferences.text("workbench.workspace.loading"))
        } else if let error = workspaceReadiness.errorMessage {
            readinessErrorPanel(error)
        }
    }

    @ViewBuilder
    private var focusedEvidenceSection: some View {
        if let target = evidenceTarget {
            VStack(alignment: .leading, spacing: 10) {
                HStack(alignment: .top, spacing: 10) {
                    Image(systemName: focusedEvidenceIcon)
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(statusColor(focusedEvidenceStatus))
                        .frame(width: 22, height: 22)

                    VStack(alignment: .leading, spacing: 3) {
                        Text(appPreferences.text("work.beginner.openEvidence"))
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(textColor)
                        Text(appPreferences.text("workbench.focusedEvidence.subtitle"))
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }

                    Spacer(minLength: 12)

                    if evidenceViewModel.isLoading {
                        ProgressView()
                            .controlSize(.small)
                            .accessibilityLabel(Text(appPreferences.text("workbench.loading")))
                    }
                }

                if let error = evidenceViewModel.errorMessage {
                    Text(error)
                        .font(.system(size: 12))
                        .foregroundColor(statusColor("failed"))
                        .fixedSize(horizontal: false, vertical: true)
                } else if let evidence = evidenceViewModel.payload?.objectValue {
                    MinimalDisclosureSection(
                        title: localizedStatus(evidenceStatus(evidence)),
                        detail: appPreferences.text("workbench.focusedEvidence.subtitle"),
                        isExpanded: $showsFocusedEvidenceDetails
                    ) {
                        VStack(alignment: .leading, spacing: 7) {
                            Text(target.runID)
                                .font(.system(size: 10, design: .monospaced))
                                .foregroundColor(.secondary)
                                .lineLimit(1)
                                .truncationMode(.middle)
                                .help(target.runID)
                            Text(target.evidenceRoute)
                                .font(.system(size: 10, design: .monospaced))
                                .foregroundColor(.secondary)
                                .lineLimit(1)
                                .truncationMode(.middle)
                                .help(target.evidenceRoute)

                            ForEach(focusedEvidencePairs(evidence), id: \.key) { pair in
                                HStack(alignment: .top, spacing: 8) {
                                    Text(displayKey(pair.key))
                                        .font(.system(size: 10, weight: .medium))
                                        .foregroundColor(.secondary)
                                        .frame(width: 112, alignment: .leading)
                                        .lineLimit(1)
                                    Text(pair.value.description)
                                        .font(.system(size: 10, design: .monospaced))
                                        .foregroundColor(textColor)
                                        .lineLimit(1)
                                        .truncationMode(.middle)
                                }
                            }
                        }
                    }
                }
            }
            .padding(14)
            .background(cardColor)
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(lineColor, lineWidth: 1))
            .accessibilityElement(children: .contain)
            .accessibilityLabel(Text(appPreferences.text("work.beginner.openEvidence")))
            .accessibilityValue(Text(appPreferences.text("workbench.focusedEvidence.subtitle")))
        }
    }

    private var focusedEvidenceStatus: String {
        if evidenceViewModel.errorMessage != nil {
            return "failed"
        }
        if evidenceViewModel.isLoading {
            return "unknown"
        }
        return evidenceViewModel.payload?.objectValue.map(evidenceStatus) ?? "unknown"
    }

    private var focusedEvidenceIcon: String {
        if evidenceViewModel.isLoading {
            return "circle.dotted"
        }
        return statusIcon(focusedEvidenceStatus)
    }

    private func evidenceStatus(_ evidence: [String: AutopilotWorkbenchJSONValue]) -> String {
        switch evidence["verdict"]?.description ?? evidence["status"]?.description ?? "unknown" {
        case "verified", "completed": return "passed"
        case "needs_attention": return "attention"
        default:
            return evidence["verdict"]?.description ?? evidence["status"]?.description ?? "unknown"
        }
    }

    private func focusedEvidencePairs(
        _ evidence: [String: AutopilotWorkbenchJSONValue]
    ) -> [(key: String, value: AutopilotWorkbenchJSONValue)] {
        ["schema_version", "mission_id", "spec_id", "status", "verdict", "evidence_sha256", "result_sha256"]
            .compactMap { key in evidence[key].map { (key: key, value: $0) } }
    }

    private var loadingRow: some View {
        HStack(spacing: 10) {
            ProgressView().controlSize(.small)
            Text(appPreferences.text("workbench.loading"))
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(cardColor)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(lineColor, lineWidth: 1))
    }

    private func loadingPanel(title: String) -> some View {
        HStack(spacing: 10) {
            ProgressView().controlSize(.small)
            Text(title)
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 10)
    }

    private func readinessErrorPanel(_ error: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(statusColor("attention"))
                .frame(width: 18, height: 18)
            VStack(alignment: .leading, spacing: 3) {
                Text(appPreferences.text("workbench.workspace.title"))
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(textColor)
                Text(error)
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                    .lineLimit(2)
            }
            Spacer()
            CommandToolbarButton(
                systemName: "arrow.clockwise",
                accessibilityLabel: appPreferences.text("workbench.workspace.refresh"),
                help: appPreferences.text("workbench.workspace.refresh")
            ) {
                Task { await workspaceReadiness.load(refresh: true) }
            }
        }
        .padding(.vertical, 8)
    }

    private func agentWorkspaceReadinessPanel(_ snapshot: AgentWorkspaceReadinessSnapshot) -> some View {
        let readyAgents = snapshot.agents.filter(\.available)
        return VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .center, spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 8) {
                        Text(appPreferences.text("workbench.workspace.title"))
                            .font(.system(size: 16, weight: .bold))
                            .foregroundColor(textColor)
                        StatusChip(
                            status: snapshot.canCreateWorkspace ? "ready" : snapshot.status.rawValue,
                            label: localizedWorkspaceStatus(snapshot)
                        )
                    }
                    Text(appPreferences.text("workbench.workspace.subtitle"))
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                }

                Spacer()

                CommandToolbarButton(
                    systemName: "arrow.clockwise",
                    accessibilityLabel: appPreferences.text("workbench.workspace.refresh"),
                    help: appPreferences.text("workbench.workspace.refresh"),
                    isDisabled: workspaceReadiness.isLoading
                ) {
                    Task { await workspaceReadiness.load(refresh: true) }
                }
            }

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 138), spacing: 10)], spacing: 10) {
                workspaceMetric(
                    appPreferences.text("workbench.workspace.readyAgents"),
                    "\(readyAgents.count)",
                    readyAgents.isEmpty ? "unavailable" : "ready"
                )
                workspaceMetric(
                    appPreferences.text("workbench.workspace.isolation"),
                    snapshot.workspaceIsolation.canCreateIsolatedWorkspaces ? appPreferences.text("workbench.status.ready") : appPreferences.text("workbench.status.not_implemented"),
                    snapshot.workspaceIsolation.canCreateIsolatedWorkspaces ? "ready" : "attention"
                )
                workspaceMetric(
                    appPreferences.text("workbench.workspace.routes"),
                    "\(workspaceReadyRouteCount(snapshot))/3",
                    snapshot.routes.hasRequiredRoutes ? "ready" : "attention"
                )
                workspaceMetric(
                    appPreferences.text("workbench.workspace.strategy"),
                    snapshot.executionStrategy ?? "-",
                    "active"
                )
            }

            if !readyAgents.isEmpty {
                VStack(alignment: .leading, spacing: 7) {
                    Text(appPreferences.text("workbench.workspace.agents"))
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(textColor)

                    ForEach(readyAgents.prefix(5)) { agent in
                        HStack(spacing: 8) {
                            Image(systemName: "terminal")
                                .font(.system(size: 11, weight: .semibold))
                                .foregroundColor(agent.available ? statusColor("ready") : .secondary)
                                .frame(width: 18, height: 18)
                            Text(agent.displayName)
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(textColor)
                                .lineLimit(1)
                            Spacer()
                            StatusChip(
                                status: "ready",
                                label: appPreferences.text("workbench.status.ready")
                            )
                        }
                        .padding(.vertical, 2)
                    }
                }
            }

            if !snapshot.canCreateWorkspace {
                VStack(alignment: .leading, spacing: 6) {
                    Text(appPreferences.text("workbench.workspace.blockers"))
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(textColor)

                    ForEach(Array(snapshot.readinessIssues.prefix(5).enumerated()), id: \.offset) { _, issue in
                        HStack(alignment: .top, spacing: 7) {
                            Image(systemName: "smallcircle.filled.circle")
                                .font(.system(size: 8, weight: .bold))
                                .foregroundColor(statusColor("attention"))
                                .padding(.top, 4)
                            Text(displayKey(issue))
                                .font(.system(size: 11))
                                .foregroundColor(.secondary)
                                .lineLimit(2)
                        }
                    }
                }
            }
        }
        .padding(.vertical, 4)
    }

    private func workspaceMetric(_ title: String, _ value: String, _ status: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title)
                .font(.system(size: 10, weight: .medium))
                .foregroundColor(.secondary)
                .lineLimit(1)
            HStack(spacing: 6) {
                Circle()
                    .fill(statusColor(status))
                    .frame(width: 7, height: 7)
                Text(value)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(textColor)
                    .lineLimit(1)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 4)
    }

    private func summaryGrid(_ snapshot: AutopilotWorkbenchSnapshot) -> some View {
        LazyVGrid(columns: summaryColumns, spacing: 10) {
            summaryTile(appPreferences.text("workbench.status"), value: localizedWorkbenchStatus(snapshot), systemName: statusIcon(snapshot.status), color: statusColor(snapshot.status))
            summaryTile(appPreferences.text("workbench.runs"), value: "\(snapshot.summary.completedRunCount)/\(snapshot.summary.runCount)", systemName: "checklist", color: statusColor(snapshot.summary.failedRunCount > 0 ? "attention" : "passed"))
            summaryTile(
                appPreferences.text("workbench.triggers"),
                value: "\(snapshot.summary.activeTriggerCount)/\(snapshot.summary.registeredTriggerCount)",
                systemName: snapshot.summary.claimedTriggerCount > 0 || snapshot.summary.schedulerTickInProgress ? "arrow.triangle.2.circlepath" : "timer",
                color: statusColor(
                    snapshot.summary.claimedTriggerCount > 0 || snapshot.summary.schedulerTickInProgress
                        ? "active"
                        : snapshot.summary.pendingTriggerCount > 0 ? "attention" : "passed"
                )
            )
            summaryTile(appPreferences.text("workbench.capabilities"), value: "\(snapshot.summary.capabilityReadyCount)", systemName: "sparkles.rectangle.stack", color: statusColor(snapshot.summary.registryHealthStatus))
            summaryTile(appPreferences.text("workbench.memory"), value: "\(snapshot.summary.pendingMemoryCount)", systemName: "brain", color: statusColor(snapshot.summary.pendingMemoryCount > 0 ? "attention" : "passed"))
            summaryTile(
                appPreferences.text("workbench.scheduler"),
                value: snapshot.summary.registeredTriggerCount == 0
                    ? appPreferences.text("workbench.notConfigured")
                    : (snapshot.summary.schedulerRunning ? appPreferences.text("workbench.running") : appPreferences.text("workbench.stopped")),
                systemName: snapshot.summary.schedulerRunning ? "play.fill" : "stop.fill",
                color: statusColor(snapshot.summary.registeredTriggerCount == 0 || snapshot.summary.schedulerRunning ? "passed" : "attention")
            )
            summaryTile(appPreferences.text("workbench.ecosystem"), value: "\(snapshot.summary.ecosystemReadyRouteCount)/\(snapshot.summary.ecosystemRouteCount)", systemName: "point.3.connected.trianglepath.dotted", color: statusColor(snapshot.summary.ecosystemRouteCount == snapshot.summary.ecosystemReadyRouteCount ? "passed" : "attention"))
            summaryTile(
                appPreferences.text("workbench.agentPlugins"),
                value: snapshot.summary.agentPluginCount == 0
                    ? appPreferences.text("workbench.notConfigured")
                    : "\(snapshot.summary.readyAgentPluginCount)/\(snapshot.summary.agentPluginCount)",
                systemName: "puzzlepiece.extension",
                color: statusColor(snapshot.summary.agentPluginCount == 0 || snapshot.summary.agentPluginCount == snapshot.summary.readyAgentPluginCount ? "passed" : "attention")
            )
            summaryTile(
                appPreferences.text("workbench.interopE2E"),
                value: localizedStatus(snapshot.summary.agentInteropE2EStatus),
                systemName: "point.3.connected.trianglepath.dotted",
                color: statusColor(snapshot.summary.agentInteropE2EStatus)
            )
        }
    }

    private func actionSection(_ snapshot: AutopilotWorkbenchSnapshot) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader(appPreferences.text("workbench.actions"), subtitle: snapshot.generatedAt.map { "\(appPreferences.text("workbench.generatedAt")) \($0)" })

            if let notice = viewModel.actionNotice {
                HStack(alignment: .top, spacing: 8) {
                    if notice.status == "running" {
                        ProgressView()
                            .controlSize(.small)
                            .frame(width: 16, height: 16)
                    } else {
                        Image(systemName: statusIcon(notice.status))
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(statusColor(notice.status))
                            .frame(width: 16, height: 16)
                    }
                    Text(notice.message)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(notice.status == "failed" ? statusColor("failed") : .secondary)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 0)
                }
                .accessibilityElement(children: .combine)
            }

            if snapshot.actions.isEmpty {
                Text(appPreferences.text("workbench.noActions"))
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
            } else {
                VStack(spacing: 8) {
                    ForEach(snapshot.actions) { action in
                        HStack(alignment: .top, spacing: 10) {
                            priorityDot(action.priority)
                            VStack(alignment: .leading, spacing: 3) {
                                Text(localizedActionTitle(action))
                                    .font(.system(size: 13, weight: .semibold))
                                    .foregroundColor(textColor)
                                    .lineLimit(1)
                                Text(localizedActionReason(action))
                                    .font(.system(size: 12))
                                    .foregroundColor(.secondary)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            Spacer(minLength: 12)
                            Button {
                                run(action)
                            } label: {
                                Group {
                                    if viewModel.activeActionID == action.id {
                                        ProgressView()
                                            .controlSize(.small)
                                    } else {
                                        Image(systemName: "play.circle.fill")
                                            .font(.system(size: 18, weight: .semibold))
                                    }
                                }
                                .frame(width: 32, height: 32)
                            }
                            .buttonStyle(.plain)
                            .foregroundStyle(AcrossTheme.accent)
                            .disabled(viewModel.isWorking || viewModel.isLoading)
                            .accessibilityLabel(localizedActionTitle(action))
                            .accessibilityHint(localizedActionReason(action))
                            .help(localizedActionTitle(action))
                        }
                        .padding(11)
                        .background(fieldColor)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                    }
                }
            }
        }
    }

    private func sectionsGrid(_ snapshot: AutopilotWorkbenchSnapshot) -> some View {
        LazyVGrid(columns: sectionColumns, spacing: 14) {
            ForEach(orderedSections(snapshot), id: \.id) { section in
                sectionPanel(section)
            }
        }
    }

    private func technicalEvidenceSection(_ snapshot: AutopilotWorkbenchSnapshot) -> some View {
        MinimalDisclosureSection(
            title: appPreferences.text("workbench.sections"),
            detail: appPreferences.text("workbench.technicalEvidence.subtitle"),
            isExpanded: $showsTechnicalEvidence
        ) {
            sectionsGrid(snapshot)
        }
    }

    private func run(_ action: AutopilotWorkbenchAction) {
        Task {
            switch action.id {
            case "ensure_self_iteration_plan":
                await viewModel.ensureSelfIterationPlan(
                    successMessage: appPreferences.text("workbench.action.ensure.success"),
                    actionID: action.id,
                    runningMessage: appPreferences.text("workbench.action.running")
                )
            case "start_trigger_scheduler":
                await viewModel.startScheduler(
                    successMessage: appPreferences.text("workbench.action.schedulerStarted.success"),
                    actionID: action.id,
                    runningMessage: appPreferences.text("workbench.action.running")
                )
            case "run_queued_trigger":
                await viewModel.tickTriggers(
                    successMessage: appPreferences.text("workbench.action.tick.success"),
                    actionID: action.id,
                    runningMessage: appPreferences.text("workbench.action.running")
                )
            case "run_agent_interop_e2e":
                await viewModel.runAgentInteropE2E(
                    successMessage: appPreferences.text("workbench.action.interop.success"),
                    failureMessage: appPreferences.text("workbench.action.interop.failed"),
                    runningMessage: appPreferences.text("workbench.action.interop.running"),
                    actionID: action.id
                )
            case "advance_evaluation_telemetry", "advance_agent_plugin_runtime":
                await viewModel.checkEcosystemAction(
                    action,
                    runningMessage: appPreferences.text("workbench.action.running"),
                    successMessage: appPreferences.text("workbench.action.check.success"),
                    attentionMessage: appPreferences.text("workbench.action.check.attention"),
                    failureMessage: appPreferences.text("workbench.action.check.failed")
                )
            default:
                viewModel.reportUnsupportedAction(
                    actionID: action.id,
                    message: appPreferences.text("workbench.action.unsupported")
                )
            }
        }
    }

    private func orderedSections(_ snapshot: AutopilotWorkbenchSnapshot) -> [AutopilotWorkbenchSection] {
        let ordered = sectionOrder.compactMap { snapshot.sections[$0] }
        let extra = snapshot.sections
            .filter { !sectionOrder.contains($0.key) }
            .map(\.value)
            .sorted { $0.id < $1.id }
        return ordered + extra
    }

    private func sectionPanel(_ section: AutopilotWorkbenchSection) -> some View {
        let visibleSummary = Array(summaryPairs(for: section).prefix(3))
        let visibleItems = Array(section.items.prefix(max(0, 4 - visibleSummary.count)))
        return VStack(alignment: .leading, spacing: 11) {
            HStack(spacing: 8) {
                Image(systemName: statusIcon(section.status))
                    .font(.system(size: 12, weight: .bold))
                    .foregroundColor(statusColor(section.status))
                    .frame(width: 18, height: 18)
                Text(localizedSectionTitle(section))
                    .font(.system(size: 14, weight: .bold))
                    .foregroundColor(textColor)
                    .lineLimit(1)
                Spacer()
                Text(localizedStatus(section.status))
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(statusColor(section.status))
            }

            VStack(alignment: .leading, spacing: 6) {
                ForEach(visibleSummary, id: \.key) { pair in
                    HStack(alignment: .top, spacing: 8) {
                        Text(displayKey(pair.key))
                            .font(.system(size: 11, weight: .medium))
                            .foregroundColor(.secondary)
                            .frame(width: section.id == "agent_interop_e2e" ? 126 : 104, alignment: .leading)
                            .lineLimit(1)
                        Text(pair.value.description)
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundColor(textColor)
                            .lineLimit(1)
                            .truncationMode(.tail)
                            .help(pair.value.description)
                        Spacer(minLength: 0)
                    }
                }
            }

            if !visibleItems.isEmpty {
                Divider().opacity(0.35)
                VStack(alignment: .leading, spacing: 5) {
                    ForEach(Array(visibleItems.enumerated()), id: \.offset) { _, item in
                        Text(item.objectValue.map(compactObjectSummary) ?? item.description)
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                            .lineLimit(1)
                            .truncationMode(.tail)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .help(item.objectValue.map(compactObjectSummary) ?? item.description)
                    }
                }
            }

        }
        .padding(14)
        .frame(maxWidth: .infinity, minHeight: sectionCardHeight, maxHeight: sectionCardHeight, alignment: .topLeading)
        .clipped()
        .background(AcrossTheme.panelFill(for: colorScheme))
        .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.cardCornerRadius))
        .overlay(
            RoundedRectangle(cornerRadius: AcrossTheme.Metrics.cardCornerRadius)
                .stroke(AcrossTheme.separator(for: colorScheme), lineWidth: 1)
        )
    }

    private func summaryPairs(for section: AutopilotWorkbenchSection) -> [(key: String, value: AutopilotWorkbenchJSONValue)] {
        if section.id == "agent_interop_e2e" {
            let priority = [
                "status",
                "protocol_readiness_score",
                "frontier_interop_status",
                "remote_mcp_template_status",
                "a2a_delegation_status",
                "otel_span_count",
                "otlp_resource_span_count",
                "eval_case_count"
            ]
            let prioritized = priority.compactMap { key -> (key: String, value: AutopilotWorkbenchJSONValue)? in
                guard let value = section.summary[key] else { return nil }
                return (key, value)
            }
            let remaining = section.summary
                .filter { pair in !priority.contains(pair.key) }
                .sorted { $0.key < $1.key }
                .prefix(max(0, 7 - prioritized.count))
                .map { (key: $0.key, value: $0.value) }
            return Array((prioritized + remaining).prefix(4))
        }
        return section.summary
            .sorted { $0.key < $1.key }
            .prefix(4)
            .map { (key: $0.key, value: $0.value) }
    }

    private func sectionHeader(_ title: String, subtitle: String?) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.system(size: 16, weight: .bold))
                .foregroundColor(textColor)
            if let subtitle {
                Text(subtitle)
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
            }
        }
    }

    private func summaryTile(_ title: String, value: String, systemName: String, color: Color) -> some View {
        HStack(spacing: 10) {
            Image(systemName: systemName)
                .font(.system(size: 13, weight: .bold))
                .foregroundColor(color)
                .frame(width: 26, height: 26)
                .background(color.opacity(0.12))
                .clipShape(RoundedRectangle(cornerRadius: 7))
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(.secondary)
                    .lineLimit(1)
                Text(value)
                    .font(.system(size: 15, weight: .bold))
                    .foregroundColor(textColor)
                    .lineLimit(1)
            }
            Spacer(minLength: 0)
        }
        .padding(.vertical, 4)
        .frame(minHeight: 46)
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
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(lineColor, lineWidth: 1))
    }

    private func priorityDot(_ priority: String) -> some View {
        Circle()
            .fill(priority == "high" ? statusColor("failed") : priority == "medium" ? statusColor("attention") : statusColor("passed"))
            .frame(width: 9, height: 9)
            .padding(.top, 4)
    }

    private func statusColor(_ status: String) -> Color {
        switch status {
        case "passed", "ready":
            return Color(hex: "30d158")
        case "active":
            return Color(hex: "64d2ff")
        case "attention", "unknown", "unavailable":
            return Color(hex: "ff9f0a")
        case "paused", "not_run", "not_configured":
            return .secondary
        case "failed":
            return Color(hex: "ff453a")
        default:
            return Color(hex: "64d2ff")
        }
    }

    private func statusIcon(_ status: String) -> String {
        switch status {
        case "passed", "ready":
            return "checkmark.circle.fill"
        case "active":
            return "arrow.triangle.2.circlepath.circle.fill"
        case "failed":
            return "xmark.octagon.fill"
        case "attention":
            return "exclamationmark.triangle.fill"
        case "paused", "not_run", "not_configured":
            return "minus.circle"
        default:
            return "questionmark.circle.fill"
        }
    }

    private func localizedStatus(_ status: String) -> String {
        appPreferences.text("workbench.status.\(status)")
    }

    private func localizedActionTitle(_ action: AutopilotWorkbenchAction) -> String {
        localizedActionText(action, suffix: "title", fallback: action.title)
    }

    private func localizedSectionTitle(_ section: AutopilotWorkbenchSection) -> String {
        let key = "workbench.section.\(section.id)"
        let localized = appPreferences.text(key)
        return localized == key ? section.title : localized
    }

    private func localizedActionReason(_ action: AutopilotWorkbenchAction) -> String {
        localizedActionText(action, suffix: "reason", fallback: action.reason)
    }

    private func localizedActionText(
        _ action: AutopilotWorkbenchAction,
        suffix: String,
        fallback: String
    ) -> String {
        let key = "workbench.nextAction.\(action.id).\(suffix)"
        let localized = appPreferences.text(key)
        return localized == key ? fallback : localized
    }

    private func localizedWorkbenchStatus(_ snapshot: AutopilotWorkbenchSnapshot) -> String {
        let reasonsAreMemoryReviewOnly = !snapshot.statusReasons.isEmpty
            && snapshot.statusReasons.allSatisfy {
                $0.lowercased().contains("pending memory")
            }
        let summary = snapshot.summary
        if snapshot.status == "attention",
           reasonsAreMemoryReviewOnly,
           summary.pendingMemoryCount > 0,
           summary.failedRunCount == 0,
           summary.pendingTriggerCount == 0,
           summary.promotionReadyCount == 0,
           (summary.registeredTriggerCount == 0 || summary.schedulerRunning),
           ["active", "not_registered", "paused"].contains(summary.selfIterationStatus),
           summary.registryHealthStatus == "passed",
           ["passed", "not_run"].contains(summary.agentInteropE2EStatus) {
            return appPreferences.text("workbench.status.review")
        }
        return localizedStatus(snapshot.status)
    }

    private func localizedWorkspaceStatus(_ snapshot: AgentWorkspaceReadinessSnapshot) -> String {
        if snapshot.canCreateWorkspace {
            return appPreferences.text("workbench.workspace.ready")
        }
        return appPreferences.text("workbench.workspace.unavailable")
    }

    private func workspaceReadyRouteCount(_ snapshot: AgentWorkspaceReadinessSnapshot) -> Int {
        [snapshot.routes.events, snapshot.routes.diff, snapshot.routes.evidence]
            .filter { $0 != nil }
            .count
    }

    private func displayKey(_ key: String) -> String {
        key.replacingOccurrences(of: "_", with: " ")
    }

    private func compactObjectSummary(_ object: [String: AutopilotWorkbenchJSONValue]) -> String {
        let preferred = ["id", "trigger_id", "run_id", "spec", "spec_id", "status", "type", "priority", "title", "reason", "endpoint"]
        let parts = preferred.compactMap { key -> String? in
            guard let value = object[key] else { return nil }
            return "\(displayKey(key))=\(value.description)"
        }
        if !parts.isEmpty {
            return parts.joined(separator: "  ")
        }
        return object.sorted { $0.key < $1.key }.prefix(4).map { "\(displayKey($0.key))=\($0.value.description)" }.joined(separator: "  ")
    }
}
