import SwiftUI

struct AutopilotWorkbenchView: View {
    @StateObject private var viewModel = AutopilotWorkbenchViewModel()
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

                if let snapshot = viewModel.snapshot {
                    summaryGrid(snapshot)
                    actionSection(snapshot)
                    sectionsGrid(snapshot)
                } else if viewModel.isLoading {
                    loadingRow
                }
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
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                    .shadow(color: Color.black.opacity(0.16), radius: 18, x: 0, y: 8)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(bgColor)
        .task {
            await viewModel.load()
        }
    }

    private var titleRow: some View {
        HStack(alignment: .center, spacing: 14) {
            VStack(alignment: .leading, spacing: 5) {
                Text(appPreferences.text("workbench.title"))
                    .font(.system(size: 28, weight: .bold))
                    .foregroundColor(textColor)
                Text(appPreferences.text("workbench.subtitle"))
                    .font(.system(size: 13))
                    .foregroundColor(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Spacer()

            HStack(spacing: 8) {
                iconButton("arrow.clockwise", help: appPreferences.text("workbench.refresh")) {
                    Task { await viewModel.load(refresh: true) }
                }
                iconButton("checkmark.seal", help: appPreferences.text("workbench.ensure")) {
                    Task { await viewModel.ensureSelfIterationPlan() }
                }
                iconButton("timer", help: appPreferences.text("workbench.tick")) {
                    Task { await viewModel.tickTriggers() }
                }
                iconButton("play.circle", help: appPreferences.text("workbench.scheduler.start")) {
                    Task { await viewModel.startScheduler() }
                }
                iconButton("stop.circle", help: appPreferences.text("workbench.scheduler.stop")) {
                    Task { await viewModel.stopScheduler() }
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

    private func summaryGrid(_ snapshot: AutopilotWorkbenchSnapshot) -> some View {
        LazyVGrid(columns: summaryColumns, spacing: 12) {
            summaryTile(appPreferences.text("workbench.status"), value: localizedStatus(snapshot.status), systemName: statusIcon(snapshot.status), color: statusColor(snapshot.status))
            summaryTile(appPreferences.text("workbench.runs"), value: "\(snapshot.summary.completedRunCount)/\(snapshot.summary.runCount)", systemName: "checklist", color: statusColor(snapshot.summary.failedRunCount > 0 ? "attention" : "passed"))
            summaryTile(appPreferences.text("workbench.triggers"), value: "\(snapshot.summary.activeTriggerCount)/\(snapshot.summary.registeredTriggerCount)", systemName: "timer", color: statusColor(snapshot.summary.pendingTriggerCount > 0 ? "attention" : "passed"))
            summaryTile(appPreferences.text("workbench.capabilities"), value: "\(snapshot.summary.capabilityReadyCount)", systemName: "sparkles.rectangle.stack", color: statusColor(snapshot.summary.registryHealthStatus))
            summaryTile(appPreferences.text("workbench.memory"), value: "\(snapshot.summary.pendingMemoryCount)", systemName: "brain", color: statusColor(snapshot.summary.pendingMemoryCount > 0 ? "attention" : "passed"))
            summaryTile(appPreferences.text("workbench.scheduler"), value: snapshot.summary.schedulerRunning ? appPreferences.text("workbench.running") : appPreferences.text("workbench.stopped"), systemName: snapshot.summary.schedulerRunning ? "play.fill" : "stop.fill", color: statusColor(snapshot.summary.schedulerRunning ? "passed" : "attention"))
            summaryTile(appPreferences.text("workbench.ecosystem"), value: "\(snapshot.summary.ecosystemReadyRouteCount)/\(snapshot.summary.ecosystemRouteCount)", systemName: "point.3.connected.trianglepath.dotted", color: statusColor(snapshot.summary.ecosystemRouteCount == snapshot.summary.ecosystemReadyRouteCount ? "passed" : "attention"))
            summaryTile(appPreferences.text("workbench.agentPlugins"), value: "\(snapshot.summary.readyAgentPluginCount)/\(snapshot.summary.agentPluginCount)", systemName: "puzzlepiece.extension", color: statusColor(snapshot.summary.agentPluginCount == snapshot.summary.readyAgentPluginCount && snapshot.summary.agentPluginCount > 0 ? "passed" : "attention"))
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
                Text(section.title)
                    .font(.system(size: 14, weight: .bold))
                    .foregroundColor(textColor)
                    .lineLimit(1)
                Spacer()
                Text(localizedStatus(section.status))
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(statusColor(section.status))
            }

            VStack(alignment: .leading, spacing: 6) {
                ForEach(section.summary.sorted(by: { $0.key < $1.key }).prefix(5), id: \.key) { pair in
                    HStack(alignment: .top, spacing: 8) {
                        Text(displayKey(pair.key))
                            .font(.system(size: 11, weight: .medium))
                            .foregroundColor(.secondary)
                            .frame(width: 104, alignment: .leading)
                            .lineLimit(1)
                        Text(pair.value.description)
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundColor(textColor)
                            .lineLimit(2)
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
                            .lineLimit(2)
                            .frame(maxWidth: .infinity, alignment: .leading)
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
        .frame(minHeight: 190, alignment: .topLeading)
        .frame(maxWidth: .infinity, alignment: .topLeading)
        .background(cardColor)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(lineColor, lineWidth: 1))
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

    private func iconButton(_ systemName: String, help: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: systemName)
                .font(.system(size: 13, weight: .semibold))
                .frame(width: 32, height: 30)
        }
        .buttonStyle(.plain)
        .foregroundColor(textColor)
        .background(fieldColor)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .help(help)
        .disabled(viewModel.isWorking || viewModel.isLoading)
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
        case "attention", "unknown", "unavailable", "paused":
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
        case "attention", "paused":
            return "exclamationmark.triangle.fill"
        default:
            return "questionmark.circle.fill"
        }
    }

    private func localizedStatus(_ status: String) -> String {
        appPreferences.text("workbench.status.\(status)")
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
