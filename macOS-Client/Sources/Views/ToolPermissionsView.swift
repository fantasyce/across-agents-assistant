import SwiftUI
import AppKit

struct PermissionInfo: Codable, Identifiable {
    var id: String { tool_name }
    let tool_name: String
    let permission_type: String
    let granted_at: String
    let granted_by: String?
}

private struct ToolSchemaInfo: Decodable {
    let name: String
    let description: String?
    let risk_level: String?

    func catalogSchema() -> ToolPermissionSchema {
        ToolPermissionSchema(
            name: name,
            description: description ?? "",
            riskLevel: risk_level ?? "unknown"
        )
    }
}

private struct PermissionUpdateRequest: Encodable {
    let permission_type: String
}

private struct PendingToolPermissionChange {
    let toolID: String
    let state: ToolPermissionState
}

private enum ToolPermissionFilter: CaseIterable, Identifiable {
    case all
    case local
    case mcp

    var id: String {
        switch self {
        case .all: return "all"
        case .local: return "local"
        case .mcp: return "mcp"
        }
    }

    @MainActor
    func title(preferences: AppPreferences) -> String {
        switch self {
        case .all: return preferences.text("tools.filter.all")
        case .local: return preferences.text("tools.filter.local")
        case .mcp: return preferences.text("tools.filter.mcp")
        }
    }
}

@MainActor
func localizedToolName(_ name: String, preferences: AppPreferences) -> String {
    let exactKey = "tool.name.\(name)"
    let exact = preferences.text(exactKey)
    if exact != exactKey { return exact }
    if name.hasPrefix("sqlite__") { return preferences.text("tool.category.sqlite") }
    if name.hasPrefix("filesystem__") { return preferences.text("tool.category.filesystem") }
    if name.hasPrefix("local_kb__") { return preferences.text("tool.category.local_kb") }
    if name.hasPrefix("external_rag__") { return preferences.text("mcp.plugin.external_rag.name") }
    if name.hasPrefix("across_context__") { return preferences.text("tool.category.across_context") }
    if name.contains("directory") || name.contains("list_dir") { return preferences.text("tool.name.list_directory") }
    if name.contains("search_files") || name.contains("find_file") { return preferences.text("tool.name.search_files") }
    if name.contains("read_file") || name.contains("get_file") { return preferences.text("tool.name.read_file") }
    if name.contains("write_file") || name.contains("create_file") { return preferences.text("tool.name.write_file") }
    if name.contains("delete_file") || name.contains("remove_file") { return preferences.text("tool.name.filesystem__delete_file") }
    if name.contains("email") || name.contains("mail") { return preferences.text("tool.category.email") }
    if name.contains("browser") || name.contains("url") { return preferences.text("tool.category.browser") }
    if name.contains("screenshot") || name.contains("ocr") || name.contains("image_text") { return preferences.text("tool.name.take_screenshot_and_ocr") }
    if name.contains("finder") { return preferences.text("tool.category.finder") }
    if name.contains("xcode") { return preferences.text("tool.category.xcode") }
    if name.contains("dark_mode") || name.contains("theme") { return preferences.text("tool.category.appearance") }
    if name.contains("volume") || name.contains("audio") { return preferences.text("tool.category.audio") }
    if name.contains("note") { return preferences.text("tool.category.note") }
    return name
}

@MainActor
private func localizedToolDescription(_ card: ToolPermissionCardModel, preferences: AppPreferences) -> String {
    let exactKey = "tool.description.\(card.id)"
    let exact = preferences.text(exactKey)
    return exact == exactKey ? card.description : exact
}

private func iconForTool(_ name: String) -> String {
    if name.hasPrefix("sqlite__") { return "cylinder.split.1x2.fill" }
    if name.hasPrefix("filesystem__") { return "folder.fill" }
    if name.hasPrefix("local_kb__") { return "book.closed.fill" }
    if name.hasPrefix("external_rag__") { return "cloud.fill" }
    if name.hasPrefix("across_context__") { return "memorychip.fill" }
    if name == "create_email_draft" { return "envelope.fill" }
    if name == "create_note_draft" { return "note.text" }
    if name == "get_finder_context" { return "finder" }
    if name == "get_xcode_context" { return "hammer.fill" }
    if name == "get_active_browser_url" { return "safari.fill" }
    if name == "read_image_text" || name == "take_screenshot_and_ocr" { return "camera.viewfinder" }
    if name == "toggle_system_dark_mode" { return "circle.lefthalf.filled" }
    if name == "set_system_volume" { return "speaker.wave.2.fill" }
    if name == "read_file" { return "doc.text.fill" }
    if name == "write_file" { return "square.and.pencil" }
    if name == "edit_file" { return "pencil.line" }
    if name == "grep" { return "magnifyingglass.circle.fill" }
    if name == "search_files" { return "folder.badge.questionmark" }
    if name == "list_directory" { return "folder.fill.badge.gearshape" }
    return "wrench.and.screwdriver.fill"
}

private struct PermissionDropdownButton: View {
    let selectedState: ToolPermissionState
    let localeIdentifier: String
    let tint: Color
    let isDisabled: Bool
    let onSelect: (ToolPermissionState) -> Void

    var body: some View {
        Menu {
            ForEach(ToolPermissionState.allCases, id: \.rawValue) { state in
                Button {
                    onSelect(state)
                } label: {
                    if state == selectedState {
                        Label(state.title(localeIdentifier: localeIdentifier), systemImage: "checkmark")
                    } else {
                        Text(state.title(localeIdentifier: localeIdentifier))
                    }
                }
            }
        } label: {
            Text(selectedState.title(localeIdentifier: localeIdentifier))
                .font(.system(size: 11, weight: .medium))
                .lineLimit(1)
                .foregroundStyle(tint)
        }
        .menuStyle(.borderlessButton)
        .fixedSize()
        .disabled(isDisabled)
    }
}

struct ToolPermissionsView: View {
    @Environment(\.colorScheme) var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    @StateObject private var mcpManager = MCPPluginManager.shared

    var onClose: (() -> Void)? = nil
    var embeddedInHub: Bool = false

    @State private var fetchedSchemas: [ToolPermissionSchema] = []
    @State private var permissionTypesByTool: [String: String] = [:]
    @State private var isLoading = true
    @State private var errorMessage: String? = nil
    @State private var updatingTool: String? = nil
    @State private var selectedFilter: ToolPermissionFilter = .all
    @State private var pendingPermissionChange: PendingToolPermissionChange?

    private var bgColor: Color { Color(nsColor: .windowBackgroundColor) }
    private var localColor: Color { Color(nsColor: .systemBlue) }
    private var mcpColor: Color { Color(nsColor: .systemGreen) }
    private var accentColor: Color { AcrossTheme.accent }

    private var cards: [ToolPermissionCardModel] {
        ToolPermissionCatalog.makeCards(
            schemas: fetchedSchemas,
            permissionTypes: permissionTypesByTool,
            enabledMCPServerIds: Set(mcpManager.plugins.filter(\.isEnabled).map(\.id))
        )
    }

    private var localCards: [ToolPermissionCardModel] {
        cards.filter { $0.scope == .local }
    }

    private var mcpCards: [ToolPermissionCardModel] {
        cards.filter { $0.scope == .mcp }
    }

    private var filteredLocalCards: [ToolPermissionCardModel] {
        selectedFilter == .mcp ? [] : localCards
    }

    private var filteredMCPCards: [ToolPermissionCardModel] {
        selectedFilter == .local ? [] : mcpCards
    }

    var body: some View {
        VStack(spacing: 0) {
            if !embeddedInHub {
                MinimalSettingsWindowHeader(title: appPreferences.text("tools.title"), onClose: onClose)
            }

            ScrollView {
                VStack(alignment: .leading, spacing: MinimalSettingsMetrics.sectionSpacing) {
                    titleRow

                    if let errorMessage {
                        warningBanner(errorMessage)
                    }

                    if !filteredLocalCards.isEmpty {
                        toolSection(
                            title: appPreferences.text("tools.local.section"),
                            meta: String(format: appPreferences.text("tools.local.meta"), localCards.count),
                            scope: .local,
                            cards: filteredLocalCards
                        )
                    }

                    if !filteredMCPCards.isEmpty {
                        toolSection(
                            title: appPreferences.text("tools.mcp.section"),
                            meta: String(format: appPreferences.text("tools.mcp.meta"), mcpCards.count),
                            scope: .mcp,
                            cards: filteredMCPCards
                        )
                    }
                }
                .minimalPageContentFrame()
            }
            .overlay {
                if isLoading {
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
            _ = mcpManager.plugins
            await loadToolData()
        }
        .onChange(of: mcpManager.plugins) {
            Task { await loadToolData() }
        }
        .confirmationDialog(
            appPreferences.text("tools.permission.confirmTitle"),
            isPresented: Binding(
                get: { pendingPermissionChange != nil },
                set: { if !$0 { pendingPermissionChange = nil } }
            ),
            titleVisibility: .visible
        ) {
            Button(appPreferences.text("tools.permission.alwaysAllow")) {
                if let change = pendingPermissionChange {
                    updatePermission(change.toolID, to: change.state)
                }
                pendingPermissionChange = nil
            }
            Button(appPreferences.text("system.cancel"), role: .cancel) {
                pendingPermissionChange = nil
            }
        } message: {
            Text(appPreferences.text("tools.permission.confirmMessage"))
        }
    }

    private var titleRow: some View {
        MinimalSettingsPageHeader(title: appPreferences.text("tools.title")) {
            Picker("", selection: $selectedFilter) {
                ForEach(ToolPermissionFilter.allCases) { filter in
                    Text(filter.title(preferences: appPreferences)).tag(filter)
                }
            }
            .labelsHidden()
            .pickerStyle(.segmented)
            .frame(width: 280)
        }
    }

    private func warningBanner(_ message: String) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundColor(.orange)
            Text(message)
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(.secondary)
            Spacer()
            Button(appPreferences.text("system.retry")) {
                Task { await loadToolData() }
            }
            .buttonStyle(.plain)
            .font(.system(size: 12, weight: .semibold))
            .foregroundColor(accentColor)
        }
        .padding(.vertical, 8)
    }

    private func toolSection(
        title: String,
        meta: String,
        scope: ToolPermissionScope,
        cards: [ToolPermissionCardModel]
    ) -> some View {
        MinimalSettingsSection(title: title, subtitle: meta) {
            VStack(spacing: 0) {
                ForEach(Array(cards.enumerated()), id: \.element.id) { index, card in
                    permissionCard(card)
                    if index < cards.count - 1 {
                        Divider().padding(.leading, 34)
                    }
                }
            }
        }
    }

    private func permissionCard(_ card: ToolPermissionCardModel) -> some View {
        let tint = sectionColor(for: card.scope)

        return MinimalSettingsRow(
            title: localizedToolName(card.name, preferences: appPreferences),
            detail: localizedToolDescription(card, preferences: appPreferences),
            leading: {
                Image(systemName: iconForTool(card.id))
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(tint)
            },
            trailing: {
                HStack(spacing: 10) {
                    Text(card.riskLevel.title(localeIdentifier: appPreferences.resolvedLocaleIdentifier))
                        .font(.system(size: 10))
                        .foregroundStyle(.secondary)
                    if updatingTool == card.id {
                        ProgressView().controlSize(.mini)
                    }
                    permissionMenu(for: card)
                }
            }
        )
    }

    private func permissionMenu(for card: ToolPermissionCardModel) -> some View {
        PermissionDropdownButton(
            selectedState: card.state,
            localeIdentifier: appPreferences.resolvedLocaleIdentifier,
            tint: permissionColor(for: card),
            isDisabled: updatingTool == card.id,
            onSelect: { state in
                if state == .alwaysAllow && card.state != .alwaysAllow {
                    pendingPermissionChange = PendingToolPermissionChange(toolID: card.id, state: state)
                } else {
                    updatePermission(card.id, to: state)
                }
            }
        )
    }

    private func sectionColor(for scope: ToolPermissionScope) -> Color {
        scope == .local ? localColor : mcpColor
    }

    private func permissionColor(for card: ToolPermissionCardModel) -> Color {
        if card.state == .unavailable {
            return .secondary
        }
        return sectionColor(for: card.scope)
    }

    private func loadToolData() async {
        isLoading = true
        errorMessage = nil

        do {
            async let fetchedToolSchemas = fetchToolSchemas()
            async let fetchedPermissions = fetchPermissions()
            fetchedSchemas = try await fetchedToolSchemas
            permissionTypesByTool = Dictionary(
                uniqueKeysWithValues: try await fetchedPermissions.map { ($0.tool_name, $0.permission_type) }
            )
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }

    private func fetchToolSchemas() async throws -> [ToolPermissionSchema] {
        guard let url = URL(string: "http://backend/api/tools") else { return [] }
        let (data, _) = try await URLSession.shared.data(from: url)
        let decoded = try JSONDecoder().decode([ToolSchemaInfo].self, from: data)
        return decoded.map { $0.catalogSchema() }
    }

    private func fetchPermissions() async throws -> [PermissionInfo] {
        guard let url = URL(string: "http://backend/api/permissions") else { return [] }
        let (data, _) = try await URLSession.shared.data(from: url)
        return try JSONDecoder().decode([PermissionInfo].self, from: data)
    }

    private func updatePermission(_ toolName: String, to state: ToolPermissionState) {
        let previous = permissionTypesByTool[toolName]
        permissionTypesByTool[toolName] = state.rawValue
        updatingTool = toolName

        Task {
            do {
                try await persistPermission(toolName, state: state)
                if state == .askEveryTime {
                    permissionTypesByTool.removeValue(forKey: toolName)
                }
            } catch {
                if let previous {
                    permissionTypesByTool[toolName] = previous
                } else {
                    permissionTypesByTool.removeValue(forKey: toolName)
                }
                errorMessage = String(format: appPreferences.text("tools.updateFailed"), error.localizedDescription)
            }
            updatingTool = nil
        }
    }

    private func persistPermission(_ toolName: String, state: ToolPermissionState) async throws {
        guard let encodedName = toolName.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed),
              let url = URL(string: "http://backend/api/permissions/\(encodedName)") else {
            return
        }

        var request = URLRequest(url: url)
        request.httpMethod = "PUT"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(PermissionUpdateRequest(permission_type: state.rawValue))

        let (_, response) = try await URLSession.shared.data(for: request)
        if let httpResponse = response as? HTTPURLResponse,
           !(200...299).contains(httpResponse.statusCode) {
            throw URLError(.badServerResponse)
        }
    }
}
