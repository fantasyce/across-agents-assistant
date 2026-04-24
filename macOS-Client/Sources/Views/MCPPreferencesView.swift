import SwiftUI
import AppKit

struct MCPPreferencesView: View {
    @StateObject private var manager = MCPPluginManager.shared
    @Environment(\.colorScheme) var colorScheme
    var onClose: (() -> Void)? = nil
    
    // Dynamic colors
    private var bgColor: Color { colorScheme == .dark ? .legacyBgDark : .legacyBgLight }
    private var textColor: Color { colorScheme == .dark ? .legacyTextDark : .legacyTextLight }
    
    var body: some View {
        VStack(spacing: 0) {
            // Custom Header
            HStack {
                CustomTrafficLights(onClose: onClose)
                
                Spacer()
                
                Text("MCP Plugins")
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
            
            // Content
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    HStack(alignment: .bottom) {
                        Text("MCP 插件管理")
                            .font(.system(size: 20, weight: .bold))
                            .foregroundColor(textColor)
                        
                        Text("通过 Model Context Protocol (MCP) 扩展 AI 助手的能力。")
                            .font(.system(size: 12))
                            .foregroundColor(.secondary)
                            .padding(.bottom, 2)
                    }
                    .padding(.bottom, 4)
                    
                    LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 16), count: 3), spacing: 16) {
                        ForEach($manager.plugins) { $plugin in
                            MCPCardView(plugin: $plugin)
                        }
                    }
                }
                .padding(24)
            }
            .background(bgColor)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(VisualEffectView().ignoresSafeArea())
        .ignoresSafeArea(.all, edges: .top)
    }
}

struct MCPCardView: View {
    @Binding var plugin: MCPPlugin
    @Environment(\.colorScheme) var colorScheme
    @State private var showingFilePicker = false
    @State private var isHoveringBrowse = false
    
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
                    Text(plugin.name)
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(textColor)
                        .lineLimit(1)
                    
                    HStack(spacing: 4) {
                        Circle()
                            .fill(statusColor(for: plugin.status))
                            .frame(width: 6, height: 6)
                        Text(statusText(for: plugin.status))
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
            
            Text(plugin.description)
                .font(.system(size: 11))
                .foregroundColor(.secondary)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
                .frame(minHeight: 28, alignment: .topLeading)
            
            if plugin.isBuiltIn {
                HStack(spacing: 6) {
                    TextField("尚未配置", text: Binding(
                        get: { plugin.args.last ?? "" },
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
                    .disabled(true)
                    
                    Button(action: openFilePicker) {
                        Text("浏览")
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
            } else {
                Text("自定义配置...")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            }
        }
        .padding(14)
        .background(sidebarBgColor)
        .cornerRadius(10)
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(Color.secondary.opacity(0.15), lineWidth: 1)
        )
    }
    
    private func iconName(for id: String) -> String {
        if id == "sqlite" { return "externaldrive.fill" }
        if id == "filesystem" { return "folder.fill" }
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
    
    private func statusText(for status: String) -> String {
        switch status {
        case "connected": return "已连接"
        case "connecting": return "连接中"
        case "error": return "失败"
        default: return "未启用"
        }
    }
    
    private func openFilePicker() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = false
        
        if plugin.id == "sqlite" {
            panel.canChooseDirectories = false
            panel.canChooseFiles = true
            panel.allowedContentTypes = [.data] // Allow .db, .sqlite etc.
        } else if plugin.id == "filesystem" {
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
