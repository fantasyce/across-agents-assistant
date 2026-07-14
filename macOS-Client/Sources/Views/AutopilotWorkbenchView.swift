import SwiftUI

struct AutopilotWorkbenchView: View {
    @StateObject private var viewModel = AutopilotWorkbenchViewModel()
    @StateObject private var workspaceReadiness = AgentWorkspaceReadinessViewModel()
    @EnvironmentObject private var appPreferences: AppPreferences
    @Environment(\.colorScheme) private var colorScheme

    private var bgColor: Color { colorScheme == .dark ? .legacyBgDark : .legacyBgLight }
    private var cardColor: Color { colorScheme == .dark ? Color(hex: "202227") : Color(hex: "fafbfc") }
    private var fieldColor: Color { colorScheme == .dark ? Color(hex: "15171b") : Color.black.opacity(0.045) }
    private var lineColor: Color { colorScheme == .dark ? Color.white.opacity(0.10) : Color.black.opacity(0.10) }
    private var textColor: Color { colorScheme == .dark ? .legacyTextDark : .legacyTextLight }

    private let summaryColumns = [GridItem(.adaptive(minimum: 148), spacing: 12)]
    private let sectionColumns = [GridItem(.adaptive(minimum: 280), spacing: 14)]
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
                agentWorkspaceReadinessSection

                if let snapshot = viewModel.snapshot {
                    summaryGrid(snapshot)
                    actionSection(snapshot)
                    sectionsGrid(snapshot)
                } else if viewModel.isLoading {
                    loadingRow
                }
            }
            .minimalPageContentFrame()
        }
        .overlay {
            if viewModel.isWorking {
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
                systemName: "checkmark.seal",
                label: appPreferences.text("workbench.ensure"),
                isDisabled: viewModel.isWorking || viewModel.isLoading
            ) {
                Task {
                    await viewModel.ensureSelfIterationPlan(
                        successMessage: appPreferences.text("workbench.action.ensure.success")
                    )
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
        .padding(14)
        .background(AcrossTheme.recessedFill(for: colorScheme))
        .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.cardCornerRadius))
        .overlay(
            RoundedRectangle(cornerRadius: AcrossTheme.Metrics.cardCornerRadius)
                .stroke(AcrossTheme.separator(for: colorScheme), lineWidth: 1)
        )
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
        .padding(14)
        .background(AcrossTheme.recessedFill(for: colorScheme))
        .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.cardCornerRadius))
        .overlay(
            RoundedRectangle(cornerRadius: AcrossTheme.Metrics.cardCornerRadius)
                .stroke(AcrossTheme.separator(for: colorScheme), lineWidth: 1)
        )
    }

    private func agentWorkspaceReadinessPanel(_ snapshot: AgentWorkspaceReadinessSnapshot) -> some View {
        VStack(alignment: .leading, spacing: 12) {
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
                    "\(snapshot.readyAgentIds.count)/\(snapshot.agents.count)",
                    snapshot.readyAgentIds.isEmpty ? "unavailable" : "ready"
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

            if !snapshot.agents.isEmpty {
                VStack(alignment: .leading, spacing: 7) {
                    Text(appPreferences.text("workbench.workspace.agents"))
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(textColor)

                    ForEach(snapshot.agents.prefix(5)) { agent in
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
                            if let reason = agent.reason, !reason.isEmpty {
                                Text(reason)
                                    .font(.system(size: 10))
                                    .foregroundColor(.secondary)
                                    .lineLimit(1)
                            }
                            StatusChip(
                                status: agent.available ? "ready" : "not_installed",
                                label: agent.available
                                    ? appPreferences.text("workbench.status.ready")
                                    : appPreferences.text("workbench.agent.optionalNotInstalled")
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
        .padding(14)
        .background(AcrossTheme.panelFill(for: colorScheme))
        .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.cardCornerRadius))
        .overlay(
            RoundedRectangle(cornerRadius: AcrossTheme.Metrics.cardCornerRadius)
                .stroke(AcrossTheme.separator(for: colorScheme), lineWidth: 1)
        )
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
        .padding(10)
        .background(AcrossTheme.recessedFill(for: colorScheme))
        .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.controlCornerRadius))
    }

    private func summaryGrid(_ snapshot: AutopilotWorkbenchSnapshot) -> some View {
        LazyVGrid(columns: summaryColumns, spacing: 12) {
            summaryTile(appPreferences.text("workbench.status"), value: localizedWorkbenchStatus(snapshot), systemName: statusIcon(snapshot.status), color: statusColor(snapshot.status))
            summaryTile(appPreferences.text("workbench.runs"), value: "\(snapshot.summary.completedRunCount)/\(snapshot.summary.runCount)", systemName: "checklist", color: statusColor(snapshot.summary.failedRunCount > 0 ? "attention" : "passed"))
            summaryTile(appPreferences.text("workbench.triggers"), value: "\(snapshot.summary.activeTriggerCount)/\(snapshot.summary.registeredTriggerCount)", systemName: "timer", color: statusColor(snapshot.summary.pendingTriggerCount > 0 ? "attention" : "passed"))
            summaryTile(appPreferences.text("workbench.capabilities"), value: "\(snapshot.summary.capabilityReadyCount)", systemName: "sparkles.rectangle.stack", color: statusColor(snapshot.summary.registryHealthStatus))
            summaryTile(appPreferences.text("workbench.memory"), value: "\(snapshot.summary.pendingMemoryCount)", systemName: "brain", color: statusColor(snapshot.summary.pendingMemoryCount > 0 ? "attention" : "passed"))
            summaryTile(appPreferences.text("workbench.scheduler"), value: snapshot.summary.schedulerRunning ? appPreferences.text("workbench.running") : appPreferences.text("workbench.stopped"), systemName: snapshot.summary.schedulerRunning ? "play.fill" : "stop.fill", color: statusColor(snapshot.summary.schedulerRunning ? "passed" : "attention"))
            summaryTile(appPreferences.text("workbench.ecosystem"), value: "\(snapshot.summary.ecosystemReadyRouteCount)/\(snapshot.summary.ecosystemRouteCount)", systemName: "point.3.connected.trianglepath.dotted", color: statusColor(snapshot.summary.ecosystemRouteCount == snapshot.summary.ecosystemReadyRouteCount ? "passed" : "attention"))
            summaryTile(appPreferences.text("workbench.agentPlugins"), value: "\(snapshot.summary.readyAgentPluginCount)/\(snapshot.summary.agentPluginCount)", systemName: "puzzlepiece.extension", color: statusColor(snapshot.summary.agentPluginCount == snapshot.summary.readyAgentPluginCount && snapshot.summary.agentPluginCount > 0 ? "passed" : "attention"))
            summaryTile(appPreferences.text("workbench.interopE2E"), value: localizedStatus(snapshot.summary.agentInteropE2EStatus), systemName: "point.3.connected.trianglepath.dotted", color: statusColor(snapshot.summary.agentInteropE2EStatus))
        }
    }

    private func actionSection(_ snapshot: AutopilotWorkbenchSnapshot) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader(appPreferences.text("workbench.actions"), subtitle: snapshot.generatedAt.map { "\(appPreferences.text("workbench.generatedAt")) \($0)" })

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
                                Text(action.title)
                                    .font(.system(size: 13, weight: .semibold))
                                    .foregroundColor(textColor)
                                    .lineLimit(1)
                                Text(action.reason)
                                    .font(.system(size: 12))
                                    .foregroundColor(.secondary)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            Spacer()
                            if let endpoint = action.endpoint {
                                Text(endpoint)
                                    .font(.system(size: 10, weight: .medium, design: .monospaced))
                                    .foregroundColor(.secondary)
                                    .lineLimit(1)
                                    .truncationMode(.middle)
                                    .frame(maxWidth: 220, alignment: .trailing)
                            }
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
        VStack(alignment: .leading, spacing: 14) {
            sectionHeader(appPreferences.text("workbench.sections"), subtitle: nil)

            LazyVGrid(columns: sectionColumns, spacing: 14) {
                ForEach(orderedSections(snapshot), id: \.id) { section in
                    sectionPanel(section)
                }
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
        VStack(alignment: .leading, spacing: 11) {
            HStack(spacing: 8) {
                Image(systemName: statusIcon(section.status))
                    .font(.system(size: 12, weight: .bold))
                    .foregroundColor(statusColor(section.status))
                    .frame(width: 18, height: 18)
                Text(
                    section.id == "self_iteration"
                        ? appPreferences.text("workbench.section.loopEngineering")
                        : section.title
                )
                    .font(.system(size: 14, weight: .bold))
                    .foregroundColor(textColor)
                    .lineLimit(1)
                Spacer()
                Text(localizedStatus(section.status))
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(statusColor(section.status))
            }

            VStack(alignment: .leading, spacing: 6) {
                ForEach(summaryPairs(for: section), id: \.key) { pair in
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

            if !section.items.isEmpty {
                Divider().opacity(0.35)
                VStack(alignment: .leading, spacing: 5) {
                    ForEach(Array(section.items.prefix(3).enumerated()), id: \.offset) { _, item in
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

            if let endpoint = section.endpoint {
                Text(endpoint)
                    .font(.system(size: 10, weight: .medium, design: .monospaced))
                    .foregroundColor(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, minHeight: 220, maxHeight: 220, alignment: .topLeading)
        .clipped()
        .background(cardColor)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(lineColor, lineWidth: 1))
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
        .padding(12)
        .frame(minHeight: 58)
        .background(cardColor)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(lineColor, lineWidth: 1))
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

    private func priorityDot(_ priority: String) -> some View {
        Circle()
            .fill(priority == "high" ? statusColor("failed") : priority == "medium" ? statusColor("attention") : statusColor("passed"))
            .frame(width: 9, height: 9)
            .padding(.top, 4)
    }

    private func statusColor(_ status: String) -> Color {
        switch status {
        case "passed", "ready", "active":
            return Color(hex: "30d158")
        case "attention", "unknown", "unavailable", "paused", "not_run":
            return Color(hex: "ff9f0a")
        case "failed":
            return Color(hex: "ff453a")
        default:
            return Color(hex: "64d2ff")
        }
    }

    private func statusIcon(_ status: String) -> String {
        switch status {
        case "passed", "ready", "active":
            return "checkmark.circle.fill"
        case "failed":
            return "xmark.octagon.fill"
        case "attention", "paused", "not_run":
            return "exclamationmark.triangle.fill"
        default:
            return "questionmark.circle.fill"
        }
    }

    private func localizedStatus(_ status: String) -> String {
        appPreferences.text("workbench.status.\(status)")
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
           summary.schedulerRunning,
           summary.selfIterationStatus == "active",
           summary.registryHealthStatus == "passed",
           summary.agentInteropE2EStatus == "passed" {
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
