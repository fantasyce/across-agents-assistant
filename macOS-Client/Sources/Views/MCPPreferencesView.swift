import SwiftUI
import AppKit
import UniformTypeIdentifiers

struct MCPPreferencesView: View {
    @StateObject private var manager = MCPPluginManager.shared
    @Environment(\.colorScheme) var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    @State private var importError: String?
    var onClose: (() -> Void)? = nil
    var embeddedInHub: Bool = false

    private var bgColor: Color { Color(nsColor: .windowBackgroundColor) }

    var body: some View {
        VStack(spacing: 0) {
            if !embeddedInHub {
                MinimalSettingsWindowHeader(title: appPreferences.text("mcp.title"), onClose: onClose)
            }

            ScrollView {
                VStack(alignment: .leading, spacing: MinimalSettingsMetrics.sectionSpacing) {
                    MinimalSettingsPageHeader(title: appPreferences.text("mcp.title"))

                    HStack(spacing: 12) {
                        Text(appPreferences.text("mcp.importHelp"))
                            .font(.system(size: 11))
                            .foregroundStyle(.secondary)
                        Spacer(minLength: 16)
                        Button(action: importMCPConfiguration) {
                            Label(appPreferences.text("mcp.importConfiguration"), systemImage: "square.and.arrow.down")
                        }
                        .controlSize(.small)
                        .accessibilityHint(appPreferences.text("mcp.importHelp"))
                    }

                    if let importError {
                        MinimalSettingsNotice(
                            text: importError,
                            color: .red,
                            systemImage: "exclamationmark.circle.fill"
                        )
                    }

                    VStack(spacing: 0) {
                        Divider()
                        ForEach(Array($manager.plugins.enumerated()), id: \.element.id) { index, plugin in
                            MCPCardView(plugin: plugin)
                            if index < manager.plugins.count - 1 {
                                Divider().padding(.leading, 34)
                            }
                        }
                        Divider()
                    }
                }
                .minimalPageContentFrame()
            }
            .background(bgColor)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(
            Group {
                if !embeddedInHub {
                    VisualEffectView().ignoresSafeArea()
                }
            }
        )
        .ignoresSafeArea(.all, edges: embeddedInHub ? Edge.Set() : .top)
    }

    private func importMCPConfiguration() {
        let panel = NSOpenPanel()
        panel.title = appPreferences.text("mcp.importConfiguration")
        panel.prompt = appPreferences.text("mcp.importAction")
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = true
        panel.canChooseFiles = true
        panel.allowedContentTypes = [.json]
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            _ = try manager.importPlugins(from: url)
            importError = nil
        } catch {
            importError = error.localizedDescription
        }
    }

}

struct MCPCardView: View {
    @Binding var plugin: MCPPlugin
    @Environment(\.colorScheme) var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    @State private var isExpanded = false

    private var accentColor: Color { AcrossTheme.accent }

    var body: some View {
        MinimalDisclosureRow(
            isExpanded: $isExpanded,
            accessibilityLabel: pluginDisplayName
        ) {
            HStack(spacing: 10) {
                Image(systemName: iconName(for: plugin.id))
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(accentColor)
                    .frame(width: 20)

                VStack(alignment: .leading, spacing: 2) {
                    Text(pluginDisplayName)
                        .font(.system(size: 12, weight: .medium))
                    MinimalStatusLabel(
                        text: statusText(for: plugin),
                        color: statusColor(for: plugin.status)
                    )
                }
            }
            .padding(.vertical, 10)
        } trailing: {
            Toggle("", isOn: Binding(
                get: { plugin.isEnabled },
                set: { _ in MCPPluginManager.shared.togglePlugin(id: plugin.id) }
            ))
            .labelsHidden()
            .controlSize(.small)
        } content: {
            VStack(alignment: .leading, spacing: 10) {
                Text(pluginDisplayDescription)
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)

                implementationRow

                if plugin.status == "error", let errorMsg = plugin.errorMessage {
                    MinimalSettingsNotice(
                        text: errorMsg,
                        color: .red,
                        systemImage: "exclamationmark.circle.fill"
                    )
                }

                configurationRow
            }
            .padding(.leading, 28)
            .padding(.bottom, 10)
        }
    }

    @ViewBuilder
    private var implementationRow: some View {
        if let implementationLabelKey = plugin.implementationLabelKey {
            Text(appPreferences.text(implementationLabelKey))
                .font(.system(size: 10, weight: .medium))
                .foregroundStyle(.secondary)
        }
    }

    @ViewBuilder
    private var configurationRow: some View {
        if plugin.isBuiltIn && plugin.requiresConfiguration {
            HStack(spacing: 6) {
                TextField(appPreferences.text(plugin.configurationPlaceholderKey), text: Binding(
                    get: { plugin.configurationValue ?? "" },
                    set: { newValue in
                        var newArgs = plugin.args
                        if !newArgs.isEmpty {
                            newArgs[newArgs.count - 1] = newValue
                        } else {
                            newArgs.append(newValue)
                        }
                        MCPPluginManager.shared.updatePluginArgs(id: plugin.id, args: newArgs)
                    }
                ))
                .textFieldStyle(.roundedBorder)
                .font(.system(size: 11))
                .disabled(!plugin.allowsDirectConfigurationEditing)

                if plugin.canBrowseConfiguration {
                    Button(action: openFilePicker) {
                        Image(systemName: "folder")
                    }
                    .buttonStyle(.borderless)
                    .help(appPreferences.text("system.browse"))
                }
            }
        } else if plugin.isBuiltIn {
            Text(appPreferences.text("mcp.noConfigurationRequired"))
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
        } else {
            VStack(alignment: .leading, spacing: 8) {
                Text(([plugin.command] + plugin.args).joined(separator: " "))
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                    .textSelection(.enabled)

                Toggle(
                    appPreferences.text("mcp.readOnly"),
                    isOn: Binding(
                        get: { plugin.isReadOnly },
                        set: { MCPPluginManager.shared.updateReadOnly(id: plugin.id, isReadOnly: $0) }
                    )
                )
                .controlSize(.small)
                .help(appPreferences.text("mcp.readOnlyHelp"))

                Button(role: .destructive) {
                    MCPPluginManager.shared.removeCustomPlugin(id: plugin.id)
                } label: {
                    Text(appPreferences.text("mcp.removePlugin"))
                }
                .controlSize(.small)
            }
        }
    }

    private func iconName(for id: String) -> String {
        if id == "local_kb" { return "macwindow" }
        if id == "external_rag" { return "cloud.fill" }
        if id == "sqlite" { return "externaldrive.fill" }
        if id == "filesystem" { return "folder.fill" }
        if id == "across_context" { return "memorychip.fill" }
        return "puzzlepiece.fill"
    }

    private func statusColor(for status: String) -> Color {
        switch status {
        case "connected": return .green
        case "connecting": return .yellow
        case "error": return .red
        default: return .gray
        }
    }

    private func statusText(for plugin: MCPPlugin) -> String {
        switch plugin.status {
        case "connected": return appPreferences.text("mcp.connected")
        case "connecting": return appPreferences.text("mcp.connecting")
        case "error": return appPreferences.text("mcp.failed")
        default:
            if !plugin.isEnabled {
                return appPreferences.text("mcp.disabled")
            }
            if plugin.requiresConfiguration && !plugin.isConfigurationComplete {
                return appPreferences.text("mcp.needsConfiguration")
            }
            return appPreferences.text("mcp.disconnected")
        }
    }

    private var pluginDisplayName: String {
        let key = "mcp.plugin.\(plugin.id).name"
        let localized = appPreferences.text(key)
        return localized == key ? plugin.name : localized
    }

    private var pluginDisplayDescription: String {
        let key = "mcp.plugin.\(plugin.id).description"
        let localized = appPreferences.text(key)
        return localized == key ? plugin.description : localized
    }

    private func openFilePicker() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = false

        if plugin.configurationKind == .file {
            panel.canChooseDirectories = false
            panel.canChooseFiles = true
            panel.allowedContentTypes = [.data] // Allow .db, .sqlite etc.
        } else if plugin.configurationKind == .directory {
            panel.canChooseDirectories = true
            panel.canChooseFiles = false
        }

        if panel.runModal() == .OK, let url = panel.url {
            var newArgs = plugin.args
            if !newArgs.isEmpty {
                newArgs[newArgs.count - 1] = url.path
            } else {
                newArgs.append(url.path)
            }
            MCPPluginManager.shared.updatePluginArgs(id: plugin.id, args: newArgs)
        }
    }
}
