import AppKit
import SwiftUI

struct DevicesWorkersSettingsView: View {
    @EnvironmentObject private var preferences: AppPreferences
    @StateObject private var viewModel = WorkerControlViewModel()
    @State private var displayName = ""
    @State private var platform = "macos-arm64"
    @State private var listenerEnabled = false
    @State private var listenerHost = ""
    @State private var listenerPort = ""
    @State private var relayEnabled = false
    @State private var relayEndpoint = ""
    @State private var selectedNodeID: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: MinimalSettingsMetrics.sectionSpacing) {
                MinimalSettingsPageHeader(
                    title: preferences.text("workers.title"),
                    subtitle: preferences.text("workers.subtitle")
                ) {
                    Button {
                        Task { await viewModel.load() }
                    } label: {
                        Label(preferences.text("workers.refresh"), systemImage: "arrow.clockwise")
                    }
                    .disabled(viewModel.isLoading || viewModel.isMutating)
                    .accessibilityHint(preferences.text("workers.refresh.hint"))
                }

                statusContent
                pendingContent
                nodeContent
                pairingContent
                connectivityContent
            }
            .minimalPageContentFrame()
        }
        .task {
            await viewModel.load()
            synchronizeConfiguration()
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(5))
                guard !Task.isCancelled else { break }
                await viewModel.load()
            }
        }
    }

    @ViewBuilder
    private var statusContent: some View {
        if viewModel.isLoading && viewModel.snapshot == nil {
            HStack(spacing: 8) {
                ProgressView().controlSize(.small)
                Text(preferences.text("workers.loading"))
                    .foregroundStyle(.secondary)
            }
            .accessibilityElement(children: .combine)
        }
        if let error = viewModel.errorMessage {
            MinimalSettingsNotice(text: error, color: .red, systemImage: "exclamationmark.triangle.fill")
                .accessibilityLabel(Text(preferences.text("workers.error") + ": " + error))
        }
        if let message = viewModel.actionMessage {
            MinimalSettingsNotice(text: message, color: .green, systemImage: "checkmark.circle.fill")
                .accessibilityLabel(Text(message))
        }
        if let recovery = viewModel.snapshot?.recovery {
            MinimalSettingsNotice(
                text: preferences.text("workers.recovery") + " " + recovery.status,
                color: .orange,
                systemImage: "arrow.counterclockwise.circle.fill"
            )
        }
        if let listener = viewModel.snapshot?.listener,
           listener.enabled,
           listener.runtime?.status == "degraded" {
            MinimalSettingsNotice(
                text: directRuntimeDetail(listener),
                color: .orange,
                systemImage: "network.slash"
            )
            .accessibilityLabel(Text(preferences.text("workers.direct.runtime.degraded") + ": " + directRuntimeDetail(listener)))
        }
    }

    private var pendingContent: some View {
        MinimalSettingsSection(
            title: preferences.text("workers.pending.title"),
            subtitle: preferences.text("workers.pending.subtitle")
        ) {
            if let pending = viewModel.snapshot?.pending, !pending.isEmpty {
                ForEach(pending) { node in
                    pendingRow(node)
                }
            } else {
                emptyRow(preferences.text("workers.pending.empty"), systemImage: "person.badge.clock")
            }
        }
    }

    private func pendingRow(_ node: WorkerNode) -> some View {
        MinimalSettingsRow(
            title: node.displayName,
            detail: [platformText(node), shortFingerprint(node.fingerprint)].filter { !$0.isEmpty }.joined(separator: " · ")
        ) {
            Image(systemName: "desktopcomputer.trianglebadge.exclamationmark")
                .foregroundStyle(.orange)
                .accessibilityHidden(true)
        } trailing: {
            HStack(spacing: 12) {
                if let code = viewModel.verificationCode(for: node) {
                    VStack(alignment: .trailing, spacing: 2) {
                        Text(preferences.text("workers.verificationCode"))
                            .font(.system(size: 10))
                            .foregroundStyle(.secondary)
                        Text(code)
                            .font(.system(.body, design: .monospaced).weight(.semibold))
                            .accessibilityLabel(Text(preferences.text("workers.verificationCode") + " " + code))
                    }
                }
                Button(preferences.text("workers.approve")) {
                    Task { await viewModel.approve(node, verificationCode: viewModel.verificationCode(for: node) ?? "") }
                }
                .buttonStyle(.borderedProminent)
                .disabled(viewModel.isMutating || viewModel.verificationCode(for: node) == nil)
                .help(viewModel.verificationCode(for: node) == nil ? preferences.text("workers.approve.disabled") : preferences.text("workers.approve.hint"))
                Button(preferences.text("workers.reject"), role: .destructive) {
                    Task {
                        await viewModel.action("revoke", node: node)
                        await viewModel.action("remove", node: node)
                    }
                }
                .disabled(viewModel.isMutating)
            }
        }
    }

    private var nodeContent: some View {
        MinimalSettingsSection(
            title: preferences.text("workers.nodes.title"),
            subtitle: nodeSummary
        ) {
            if let nodes = viewModel.snapshot?.nodes.filter({ $0.state != "pending_approval" }), !nodes.isEmpty {
                ForEach(nodes) { node in
                    nodeRow(node)
                }
            } else {
                emptyRow(preferences.text("workers.nodes.empty"), systemImage: "desktopcomputer")
            }
        }
    }

    private func nodeRow(_ node: WorkerNode) -> some View {
        MinimalDisclosureRow(
            isExpanded: Binding(
                get: { selectedNodeID == node.id },
                set: { selectedNodeID = $0 ? node.id : nil }
            ),
            accessibilityLabel: node.displayName
        ) {
            MinimalSettingsRow(
                title: node.displayName,
                detail: [stateText(node.presentationState), platformText(node), transportText(node)].filter { !$0.isEmpty }.joined(separator: " · ")
            ) {
                Circle()
                    .fill(stateColor(node.presentationState))
                    .frame(width: 8, height: 8)
                    .accessibilityHidden(true)
            } trailing: {
                EmptyView()
            }
        } trailing: {
            Menu {
                Button(preferences.text("workers.update")) {
                    Task { await viewModel.action("update", node: node) }
                }
                .disabled(!canUpdate(node))
                if node.draining || node.state == "draining" {
                    Button(preferences.text("workers.resume")) { Task { await viewModel.action("resume", node: node) } }
                } else {
                    Button(preferences.text("workers.drain")) { Task { await viewModel.action("drain", node: node) } }
                }
                if node.state == "revoked" {
                    Button(preferences.text("workers.remove"), role: .destructive) { Task { await viewModel.action("remove", node: node) } }
                } else {
                    Button(preferences.text("workers.revoke"), role: .destructive) { Task { await viewModel.action("revoke", node: node) } }
                }
            } label: {
                Image(systemName: "ellipsis.circle")
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .disabled(viewModel.isMutating)
            .accessibilityLabel(Text(preferences.text("workers.actions") + " " + node.displayName))
        } content: {
            VStack(alignment: .leading, spacing: 8) {
                detailLine(preferences.text("workers.detail.capability"), platformText(node))
                detailLine(preferences.text("workers.detail.version"), node.capabilityManifest.workerVersion ?? "—")
                detailLine(preferences.text("workers.detail.resources"), resourceText(node))
                detailLine(preferences.text("workers.detail.executor"), node.capabilityManifest.executors?.joined(separator: ", ") ?? "—")
                detailLine(preferences.text("workers.detail.isolation"), node.capabilityManifest.isolationLevel ?? "—")
                detailLine(preferences.text("workers.detail.transport"), transportText(node))
                detailLine(preferences.text("workers.detail.job"), node.currentJob?.title ?? node.currentJob?.jobID ?? "—")
                detailLine(preferences.text("workers.detail.result"), node.recentResult?.state ?? "—")
            }
            .padding(.leading, 34)
            .padding(.bottom, 10)
        }
        .accessibilityElement(children: .contain)
    }

    private var pairingContent: some View {
        MinimalSettingsSection(
            title: preferences.text("workers.add.title"),
            subtitle: preferences.text("workers.add.subtitle")
        ) {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 12) {
                    TextField(preferences.text("workers.add.name"), text: $displayName)
                        .textFieldStyle(.roundedBorder)
                        .accessibilityLabel(Text(preferences.text("workers.add.name")))
                    Picker(preferences.text("workers.add.platform"), selection: $platform) {
                        Text("macOS Apple Silicon").tag("macos-arm64")
                        Text("macOS Intel").tag("macos-x86_64")
                        Text("Linux x86_64").tag("linux-x86_64")
                        Text("Linux arm64").tag("linux-arm64")
                    }
                    .labelsHidden()
                    .frame(width: 180)
                    Button(preferences.text("workers.add.create")) {
                        Task { await viewModel.createPairing(displayName: displayName, platform: platform) }
                    }
                    .disabled(viewModel.isMutating || !hasConnectionPath)
                    .help(hasConnectionPath ? preferences.text("workers.add.create.hint") : preferences.text("workers.add.connectionRequired"))
                }
                if let pairing = viewModel.pairing {
                    HStack(alignment: .top, spacing: 12) {
                        VStack(alignment: .leading, spacing: 5) {
                            Text(preferences.text("workers.add.code") + " " + pairing.pairingCode)
                                .font(.system(.body, design: .monospaced).weight(.semibold))
                            if let command = pairing.install?.shellCommand {
                                Text(command)
                                    .font(.system(size: 11, design: .monospaced))
                                    .textSelection(.enabled)
                                    .lineLimit(4)
                            } else if pairing.installUnavailableReason != nil {
                                Label(preferences.text("workers.add.releasePending"), systemImage: "shippingbox")
                                    .font(.system(size: 11))
                                    .foregroundStyle(.secondary)
                            }
                            Text(preferences.text("workers.add.expires"))
                                .font(.system(size: 10))
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        if let command = pairing.install?.shellCommand {
                            Button {
                                NSPasteboard.general.clearContents()
                                NSPasteboard.general.setString(command, forType: .string)
                            } label: {
                                Label(preferences.text("workers.copy"), systemImage: "doc.on.doc")
                            }
                            .accessibilityHint(preferences.text("workers.copy.hint"))
                        }
                    }
                    .padding(.vertical, 8)
                }
            }
            .padding(.vertical, MinimalSettingsMetrics.rowVerticalPadding)
        }
    }

    private var connectivityContent: some View {
        MinimalSettingsSection(
            title: preferences.text("workers.connection.title"),
            subtitle: preferences.text("workers.connection.subtitle")
        ) {
            VStack(spacing: 0) {
                MinimalSettingsRow(title: preferences.text("workers.direct"), detail: directListenerDetail) {
                    Toggle("", isOn: $listenerEnabled).labelsHidden()
                } trailing: {
                    HStack(spacing: 8) {
                        TextField(preferences.text("workers.direct.host"), text: $listenerHost)
                            .textFieldStyle(.roundedBorder)
                            .frame(width: 170)
                            .disabled(!listenerEnabled)
                            .accessibilityLabel(Text(preferences.text("workers.direct.host")))
                        TextField(preferences.text("workers.direct.port"), text: $listenerPort)
                            .textFieldStyle(.roundedBorder)
                            .frame(width: 78)
                            .disabled(!listenerEnabled)
                            .accessibilityLabel(Text(preferences.text("workers.direct.port")))
                        Button(preferences.text("workers.save")) {
                            Task { await viewModel.configureListener(enabled: listenerEnabled, bindHost: listenerHost, port: Int(listenerPort) ?? 0) }
                        }
                        .disabled(viewModel.isMutating || (listenerEnabled && (listenerHost.isEmpty || !validListenerPort)))
                    }
                }
                MinimalSettingsRow(title: preferences.text("workers.relay"), detail: preferences.text("workers.relay.help")) {
                    Toggle("", isOn: $relayEnabled).labelsHidden()
                } trailing: {
                    HStack(spacing: 8) {
                        TextField("https://relay.example", text: $relayEndpoint)
                            .textFieldStyle(.roundedBorder)
                            .frame(width: 260)
                            .disabled(!relayEnabled)
                            .accessibilityLabel(Text(preferences.text("workers.relay.endpoint")))
                        Button(preferences.text("workers.save")) {
                            Task { await viewModel.configureRelay(enabled: relayEnabled, endpoint: relayEndpoint) }
                        }
                        .disabled(viewModel.isMutating || (relayEnabled && !relayEndpoint.hasPrefix("https://")))
                    }
                }
            }
        }
    }

    private func emptyRow(_ text: String, systemImage: String) -> some View {
        HStack(spacing: 10) {
            Image(systemName: systemImage).foregroundStyle(.secondary).accessibilityHidden(true)
            Text(text).font(.system(size: 12)).foregroundStyle(.secondary)
            Spacer()
        }
        .padding(.vertical, 14)
        .accessibilityElement(children: .combine)
    }

    private func detailLine(_ label: String, _ value: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(label).foregroundStyle(.secondary).frame(width: 110, alignment: .leading)
            Text(value).textSelection(.enabled)
        }
        .font(.system(size: 11))
    }

    private var nodeSummary: String {
        guard let health = viewModel.snapshot?.health else { return preferences.text("workers.nodes.subtitle") }
        let reconnectingCount = viewModel.snapshot?.nodes.filter { $0.presentationState == "reconnecting" }.count ?? 0
        let reconnecting = reconnectingCount > 0
            ? " · \(reconnectingCount) \(preferences.text("workers.reconnecting"))"
            : ""
        return "\(health.onlineCount) \(preferences.text("workers.online"))\(reconnecting) · \(health.nodeCount) \(preferences.text("workers.total"))"
    }

    private var hasConnectionPath: Bool {
        guard let snapshot = viewModel.snapshot else { return false }
        return snapshot.listener.runtime?.status == "running" || snapshot.relay.enabled
    }

    private var validListenerPort: Bool {
        guard let port = Int(listenerPort) else { return false }
        return (1...65534).contains(port)
    }

    private var directListenerDetail: String {
        guard let listener = viewModel.snapshot?.listener, listener.enabled else {
            return preferences.text("workers.direct.help")
        }
        return directRuntimeDetail(listener)
    }

    private func directRuntimeDetail(_ listener: WorkerListenerConfiguration) -> String {
        switch listener.runtime?.status {
        case "running":
            return String(
                format: preferences.text("workers.direct.runtime.running"),
                listener.bindHost ?? "—",
                listener.port,
                listener.modelGatewayPort ?? 0
            )
        case "degraded":
            return preferences.text("workers.direct.runtime.degraded") + " " + runtimeErrorText(listener.runtime?.lastError)
        default:
            return preferences.text("workers.direct.runtime.stopped")
        }
    }

    private func runtimeErrorText(_ code: String?) -> String {
        switch code {
        case "managed_orchestrator_missing": return preferences.text("workers.direct.error.orchestrator")
        case "runtime_permission_denied": return preferences.text("workers.direct.error.permission")
        default: return preferences.text("workers.direct.error.start")
        }
    }

    private func synchronizeConfiguration() {
        guard let snapshot = viewModel.snapshot else { return }
        listenerEnabled = snapshot.listener.enabled
        listenerHost = snapshot.listener.bindHost ?? ""
        listenerPort = snapshot.listener.port > 0 ? String(snapshot.listener.port) : ""
        relayEnabled = snapshot.relay.enabled
        relayEndpoint = snapshot.relay.endpoint ?? ""
    }

    private func shortFingerprint(_ value: String) -> String {
        value.count > 12 ? String(value.prefix(12)) : value
    }

    private func platformText(_ node: WorkerNode) -> String {
        [node.capabilityManifest.os, node.capabilityManifest.osVersion, node.capabilityManifest.architecture]
            .compactMap { $0 }
            .filter { !$0.isEmpty }
            .joined(separator: " ")
    }

    private func transportText(_ node: WorkerNode) -> String {
        guard node.transport != "pending" else { return preferences.text("workers.transport.pending") }
        if let latency = node.transportQuality?.latencyMilliseconds {
            return "\(node.transport) · \(Int(latency)) ms"
        }
        return node.transport
    }

    private func resourceText(_ node: WorkerNode) -> String {
        let cpu = node.capabilityManifest.cpuCount.map { "\($0) CPU" } ?? "—"
        let memory = node.capabilityManifest.memoryBytes.map { ByteCountFormatter.string(fromByteCount: $0, countStyle: .memory) } ?? "—"
        let disk = node.capabilityManifest.diskAvailableBytes.map { ByteCountFormatter.string(fromByteCount: $0, countStyle: .file) } ?? "—"
        return "\(cpu) · \(memory) · \(disk)"
    }

    private func canUpdate(_ node: WorkerNode) -> Bool {
        guard let release = viewModel.snapshot?.release,
              release.published,
              let version = release.version,
              release.platforms.contains("\(node.capabilityManifest.os ?? "")-\(node.capabilityManifest.architecture ?? "")") else {
            return false
        }
        return version != node.capabilityManifest.workerVersion && node.state != "revoked" && node.state != "pending_approval"
    }

    private func stateText(_ value: String) -> String {
        preferences.text("workers.state.\(value)")
    }

    private func stateColor(_ value: String) -> Color {
        switch value {
        case "online_idle", "online_busy": return .green
        case "draining", "degraded", "reconnecting": return .orange
        case "revoked", "incompatible": return .red
        default: return .secondary
        }
    }
}
