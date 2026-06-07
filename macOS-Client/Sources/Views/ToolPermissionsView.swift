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

    @State private var isPresented = false
    @Environment(\.colorScheme) private var colorScheme

    private var cardColor: Color { colorScheme == .dark ? Color(hex: "20222a") : .white }
    private var lineColor: Color { colorScheme == .dark ? Color.white.opacity(0.10) : Color.black.opacity(0.10) }
    private var textColor: Color { colorScheme == .dark ? .legacyTextDark : Color(hex: "151820") }

    var body: some View {
        let chrome = ToolPermissionVisualStyle.permissionChrome(for: selectedState)

        Button {
            isPresented.toggle()
        } label: {
            HStack(spacing: 5) {
                Text(selectedState.title(localeIdentifier: localeIdentifier))
                    .font(.system(size: 10, weight: .bold))
                    .lineLimit(1)
                Image(systemName: "chevron.down")
                    .font(.system(size: 7, weight: .bold))
                    .frame(width: 7, height: 7, alignment: .center)
            }
            .foregroundColor(tint.opacity(chrome.foregroundOpacity))
            .frame(height: 24)
            .padding(.horizontal, 7)
            .background(tint.opacity(chrome.backgroundOpacity))
            .clipShape(RoundedRectangle(cornerRadius: 7))
            .overlay(
                RoundedRectangle(cornerRadius: 7)
                    .stroke(tint.opacity(chrome.borderOpacity), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .fixedSize()
        .disabled(isDisabled)
        .popover(isPresented: $isPresented, arrowEdge: .bottom) {
            VStack(alignment: .leading, spacing: 4) {
                ForEach(ToolPermissionState.allCases, id: \.rawValue) { state in
                    Button {
                        isPresented = false
                        onSelect(state)
                    } label: {
                        HStack(spacing: 8) {
                            Group {
                                if state == selectedState {
                                    Image(systemName: "checkmark")
                                        .font(.system(size: 10, weight: .bold))
                                } else {
                                    Color.clear
                                }
                            }
                            .frame(width: 12)
                            Text(state.title(localeIdentifier: localeIdentifier))
                                .font(.system(size: 12, weight: .semibold))
                            Spacer(minLength: 0)
                        }
                        .foregroundColor(state == .unavailable ? .secondary : textColor)
                        .padding(.horizontal, 10)
                        .frame(height: 30)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(6)
            .frame(width: 150)
            .background(cardColor)
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(lineColor, lineWidth: 1)
            )
        }
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

    private var bgColor: Color { colorScheme == .dark ? .legacyBgDark : .legacyBgLight }
    private var headerColor: Color { colorScheme == .dark ? .legacyBgDark : .legacyBgLight }
    private var cardColor: Color { colorScheme == .dark ? Color(hex: "20222a") : .white }
    private var softColor: Color { colorScheme == .dark ? Color.white.opacity(0.055) : Color.black.opacity(0.04) }
    private var lineColor: Color { colorScheme == .dark ? Color.white.opacity(0.09) : Color.black.opacity(0.10) }
    private var textColor: Color { colorScheme == .dark ? .legacyTextDark : .legacyTextLight }
    private var localColor: Color { colorScheme == .dark ? Color(hex: "4da3ff") : Color(hex: "0a84ff") }
    private var mcpColor: Color { colorScheme == .dark ? Color(hex: "38d88b") : Color(hex: "29a36a") }
    private var accentColor: Color { colorScheme == .dark ? Color(hex: "a58bff") : Color(hex: "8a6cff") }

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

    private let columns = Array(repeating: GridItem(.flexible(), spacing: 14), count: 3)

    var body: some View {
        VStack(spacing: 0) {
            if !embeddedInHub {
                standaloneHeader
                Divider().opacity(0.35)
            }

            ScrollView {
                VStack(alignment: .leading, spacing: SettingsHubPageLayout.sectionSpacing) {
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
                .padding(SettingsHubPageLayout.contentPadding)
                .frame(maxWidth: SettingsHubPageLayout.contentMaxWidth, alignment: .leading)
                .frame(maxWidth: .infinity)
            }
            .overlay {
                if isLoading {
                    ProgressView()
                        .controlSize(.small)
                        .padding(18)
                        .background(cardColor)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                        .shadow(color: Color.black.opacity(0.14), radius: 18, x: 0, y: 8)
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
    }

    private var standaloneHeader: some View {
        HStack {
            CustomTrafficLights(onClose: onClose)
            Spacer()
            Text(appPreferences.text("tools.title"))
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(textColor)
            Spacer()
            Spacer().frame(width: 50)
        }
        .padding(.horizontal, 16)
        .frame(height: 56)
        .background(
            ZStack {
                headerColor.opacity(colorScheme == .dark ? 0.84 : 0.96)
                WindowDragView().contentShape(Rectangle())
            }
        )
    }

    private var titleRow: some View {
        HStack(alignment: .center, spacing: 18) {
            Text(appPreferences.text("tools.title"))
                .font(.system(size: 28, weight: .bold))
                .foregroundColor(textColor)

            Spacer()

            HStack(spacing: 3) {
                ForEach(ToolPermissionFilter.allCases) { filter in
                    Button {
                        selectedFilter = filter
                    } label: {
                        Text(filter.title(preferences: appPreferences))
                            .font(.system(size: 12, weight: .bold))
                            .foregroundColor(selectedFilter == filter ? textColor : .secondary)
                            .frame(minWidth: 86, minHeight: 30)
                            .background(
                                RoundedRectangle(cornerRadius: 8)
                                    .fill(selectedFilter == filter ? cardColor : Color.clear)
                            )
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(3)
            .background(softColor)
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(lineColor, lineWidth: 1)
            )
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
        .padding(10)
        .background(cardColor)
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(lineColor, lineWidth: 1)
        )
    }

    private func toolSection(
        title: String,
        meta: String,
        scope: ToolPermissionScope,
        cards: [ToolPermissionCardModel]
    ) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline, spacing: 12) {
                HStack(spacing: 9) {
                    Circle()
                        .fill(sectionColor(for: scope))
                        .frame(width: 8, height: 8)
                    Text(title)
                        .font(.system(size: 14, weight: .bold))
                        .foregroundColor(sectionColor(for: scope))
                }
                Spacer()
                Text(meta)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(.secondary)
            }
            .padding(.horizontal, 2)

            LazyVGrid(columns: columns, spacing: 14) {
                ForEach(cards) { card in
                    permissionCard(card)
                }
            }
        }
    }

    private func permissionCard(_ card: ToolPermissionCardModel) -> some View {
        let metrics = ToolPermissionCardRhythm.metrics(localeIdentifier: appPreferences.resolvedLocaleIdentifier)
        let tint = sectionColor(for: card.scope)

        return VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .center, spacing: 10) {
                Image(systemName: iconForTool(card.id))
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(tint)
                    .frame(width: 32, height: 32)
                    .background(tint.opacity(colorScheme == .dark ? 0.16 : 0.12))
                    .clipShape(RoundedRectangle(cornerRadius: 9))

                VStack(alignment: .leading, spacing: 2) {
                    Text(localizedToolName(card.name, preferences: appPreferences))
                        .font(.system(size: 13, weight: .bold))
                        .foregroundColor(textColor)
                        .lineLimit(1)
                    Text(card.id)
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundColor(.secondary.opacity(0.78))
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
                .frame(height: metrics.titleBlockHeight, alignment: .center)

                Spacer(minLength: 8)

                permissionMenu(for: card)
            }

            Text(localizedToolDescription(card, preferences: appPreferences))
                .font(.system(size: 12))
                .foregroundColor(.secondary)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
                .frame(height: metrics.descriptionHeight, alignment: .topLeading)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.top, metrics.headerToDescriptionSpacing)

            HStack(spacing: 6) {
                Text(card.riskLevel.title(localeIdentifier: appPreferences.resolvedLocaleIdentifier))
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(tint)
                if updatingTool == card.id {
                    ProgressView()
                        .controlSize(.mini)
                        .scaleEffect(0.55)
                }
                Spacer()
            }
            .frame(height: 18)
            .padding(.top, metrics.descriptionToRiskSpacing)

            Spacer(minLength: 0)
        }
        .padding(12)
        .frame(height: metrics.cardHeight)
        .background(cardColor)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(lineColor, lineWidth: 1)
        )
    }

    private func permissionMenu(for card: ToolPermissionCardModel) -> some View {
        PermissionDropdownButton(
            selectedState: card.state,
            localeIdentifier: appPreferences.resolvedLocaleIdentifier,
            tint: permissionColor(for: card),
            isDisabled: updatingTool == card.id,
            onSelect: { state in updatePermission(card.id, to: state) }
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
