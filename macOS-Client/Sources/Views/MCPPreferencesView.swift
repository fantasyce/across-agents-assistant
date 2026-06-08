import SwiftUI
import AppKit

struct MCPPreferencesView: View {
    @StateObject private var manager = MCPPluginManager.shared
    @Environment(\.colorScheme) var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    var onClose: (() -> Void)? = nil
    var embeddedInHub: Bool = false

    // Dynamic colors
    private var bgColor: Color { colorScheme == .dark ? .legacyBgDark : .legacyBgLight }
    private var textColor: Color { colorScheme == .dark ? .legacyTextDark : .legacyTextLight }

    var body: some View {
        VStack(spacing: 0) {
            // Custom Header
            if !embeddedInHub {
                HStack {
                    CustomTrafficLights(onClose: onClose)

                    Spacer()

                    Text(appPreferences.text("mcp.title"))
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(textColor)

                    Spacer()

                    // Balance the traffic lights width
                    Spacer().frame(width: 50)
                }
                .padding(.horizontal, 16)
                .frame(height: 56)
                .background(
                    ZStack {
                        bgColor.opacity(0.8)
                        WindowDragView()
                            .contentShape(Rectangle())
                    }
                )

                Divider().opacity(0.5)
            }

            ScrollView {
                VStack(alignment: .leading, spacing: SettingsHubPageLayout.sectionSpacing) {
                    pageTitle

                    LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 16), count: 3), spacing: 16) {
                        ForEach($manager.plugins) { $plugin in
                            MCPCardView(plugin: $plugin)
                        }
                    }
                }
                .padding(SettingsHubPageLayout.contentPadding)
                .frame(maxWidth: SettingsHubPageLayout.contentMaxWidth, alignment: .leading)
                .frame(maxWidth: .infinity)
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

    private var pageTitle: some View {
        Text(appPreferences.text("mcp.title"))
            .font(.system(size: 28, weight: .bold))
            .foregroundColor(textColor)
            .padding(.top, 2)
    }
}

struct MCPCardView: View {
    @Binding var plugin: MCPPlugin
    @Environment(\.colorScheme) var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    @State private var showingFilePicker = false
    @State private var isHoveringBrowse = false
    private let implementationRowHeight: CGFloat = 14
    private let configurationRowHeight: CGFloat = 26
    private let minimumCardHeight: CGFloat = 160

    // Dynamic colors
    private var sidebarBgColor: Color { colorScheme == .dark ? .legacySidebarDark : .legacySidebarLight }
    private var accentColor: Color { colorScheme == .dark ? .legacyAccentDark : .legacyAccentLight }
    private var textColor: Color { colorScheme == .dark ? .legacyTextDark : .legacyTextLight }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Top Row: Icon, Title, Toggle
            HStack(alignment: .top) {
                Image(systemName: iconName(for: plugin.id))
                    .font(.system(size: 16))
                    .foregroundColor(accentColor)
                    .frame(width: 32, height: 32)
                    .background(accentColor.opacity(0.15))
                    .cornerRadius(8)

                VStack(alignment: .leading, spacing: 2) {
                    Text(pluginDisplayName)
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(textColor)
                        .lineLimit(1)

                    HStack(spacing: 4) {
                        Circle()
                            .fill(statusColor(for: plugin.status))
                            .frame(width: 6, height: 6)
                        Text(statusText(for: plugin))
                            .font(.system(size: 10))
                            .foregroundColor(.secondary)
                    }
                }

                Spacer()

                Toggle("", isOn: Binding(
                    get: { plugin.isEnabled },
                    set: { _ in MCPPluginManager.shared.togglePlugin(id: plugin.id) }
                ))
                .toggleStyle(SwitchToggleStyle(tint: accentColor))
                .controlSize(.small)
            }

            Text(pluginDisplayDescription)
                .font(.system(size: 11))
                .foregroundColor(.secondary)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
                .frame(minHeight: 28, alignment: .topLeading)

            implementationRow

            if plugin.status == "error", let errorMsg = plugin.errorMessage {
                Text(errorMsg)
                    .font(.system(size: 10))
                    .foregroundColor(.red.opacity(0.8))
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
            }

            configurationRow
        }
        .padding(14)
        .frame(minHeight: minimumCardHeight, alignment: .topLeading)
        .frame(maxWidth: .infinity, alignment: .topLeading)
        .background(sidebarBgColor)
        .cornerRadius(10)
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(Color.secondary.opacity(0.15), lineWidth: 1)
        )
    }

    @ViewBuilder
    private var implementationRow: some View {
        if let implementationLabelKey = plugin.implementationLabelKey {
            Text(appPreferences.text(implementationLabelKey))
                .font(.system(size: 10, weight: .medium))
                .foregroundColor(accentColor.opacity(0.9))
                .lineLimit(1)
                .frame(height: implementationRowHeight, alignment: .leading)
        } else {
            Text(" ")
                .font(.system(size: 10, weight: .medium))
                .lineLimit(1)
                .frame(height: implementationRowHeight, alignment: .leading)
                .hidden()
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
                .textFieldStyle(.plain)
                .font(.system(size: 11))
                .foregroundColor(textColor)
                .padding(.horizontal, 6)
                .padding(.vertical, 4)
                .background(Color.black.opacity(0.05))
                .cornerRadius(4)
                .disabled(!plugin.allowsDirectConfigurationEditing)

                if plugin.canBrowseConfiguration {
                    Button(action: openFilePicker) {
                        Text(appPreferences.text("system.browse"))
                            .font(.system(size: 11))
                            .foregroundColor(textColor)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(Color.black.opacity(isHoveringBrowse ? 0.1 : 0.05))
                            .cornerRadius(4)
                    }
                    .buttonStyle(.plain)
                    .onHover { hovering in
                        withAnimation(.easeInOut(duration: 0.1)) {
                            isHoveringBrowse = hovering
                        }
                    }
                }
            }
            .frame(height: configurationRowHeight, alignment: .leading)
        } else if plugin.isBuiltIn {
            Text(appPreferences.text("mcp.noConfigurationRequired"))
                .font(.system(size: 11))
                .foregroundColor(.secondary)
                .frame(height: configurationRowHeight, alignment: .leading)
        } else {
            Text(appPreferences.text("mcp.customConfiguration"))
                .font(.system(size: 11))
                .foregroundColor(.secondary)
                .frame(height: configurationRowHeight, alignment: .leading)
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
