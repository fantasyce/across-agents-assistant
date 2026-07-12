import SwiftUI

struct ProjectSidebarRow: View {
    let project: ProjectInfo
    let activeProjectId: String?
    let currentSessionId: String
    let selectedSessionIds: Set<String>
    let showsSessions: Bool
    let onSelectProject: () -> Void
    let onOpenTree: () -> Void
    let onNewChat: () -> Void
    let onSelectSession: (SessionInfo) -> Void
    let onDeleteSession: (SessionInfo) -> Void
    let onRenameSession: (SessionInfo) -> Void
    let onPinProject: () -> Void
    let onPinSession: (SessionInfo) -> Void

    @State private var isHovered = false
    @FocusState private var isFocused: Bool
    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences

    private var isActive: Bool {
        project.id == activeProjectId
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 8) {
                Image(systemName: isActive ? "folder.fill" : "folder")
                    .font(.system(size: 12))
                    .foregroundStyle(isActive || isFocused ? AcrossTheme.accent : Color.secondary.opacity(0.75))
                    .frame(width: 16)

                Text(project.name)
                    .font(.system(size: 12, weight: .medium))
                    .lineLimit(1)
                    .foregroundStyle(isActive || isFocused ? AcrossTheme.accent : Color.secondary.opacity(isHovered ? 0.95 : 0.86))

                if project.is_pinned {
                    Image(systemName: "pin.fill")
                        .font(.system(size: 8, weight: .semibold))
                        .foregroundColor(.secondary.opacity(0.72))
                }

                Spacer(minLength: 4)

                HStack(spacing: 2) {
                    Button(action: onPinProject) {
                        Image(systemName: project.is_pinned ? "pin.slash" : "pin")
                            .font(.system(size: 11, weight: .semibold))
                            .frame(width: 22, height: 22)
                    }
                    .buttonStyle(.plain)
                    .help(project.is_pinned ? appPreferences.text("project.unpin") : appPreferences.text("project.pin"))

                    Button(action: onOpenTree) {
                        Image(systemName: "line.3.horizontal")
                            .font(.system(size: 11, weight: .semibold))
                            .frame(width: 22, height: 22)
                    }
                    .buttonStyle(.plain)
                    .help(appPreferences.text("project.openTree"))

                    Button(action: onNewChat) {
                        Image(systemName: "square.and.pencil")
                            .font(.system(size: 11, weight: .semibold))
                            .frame(width: 22, height: 22)
                    }
                    .buttonStyle(.plain)
                    .help(appPreferences.text("project.newChatInProject"))
                }
                .foregroundColor(.secondary)
                .opacity(isHovered ? 1 : 0)
                .allowsHitTesting(isHovered)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.leading, 10)
            .padding(.trailing, 2)
            .padding(.vertical, 7)
            .background(
                RoundedRectangle(cornerRadius: 7)
                    .fill(
                        isActive || isFocused
                            ? AcrossTheme.selectedFill(for: colorScheme)
                            : isHovered ? AcrossTheme.hoverFill(for: colorScheme) : Color.clear
                    )
            )
            .contentShape(Rectangle())
            .onTapGesture(perform: onSelectProject)
            .focusable()
            .focused($isFocused)
            .focusEffectDisabled()
            .onKeyPress(.return) {
                onSelectProject()
                return .handled
            }
            .accessibilityElement(children: .contain)
            .accessibilityAddTraits(.isButton)
            .accessibilityAction(.default, onSelectProject)
            .contextMenu {
                Button(project.is_pinned ? appPreferences.text("project.unpin") : appPreferences.text("project.pin"), action: onPinProject)
                Divider()
                Button(appPreferences.text("project.newChat"), action: onNewChat)
                Button(appPreferences.text("project.openTree"), action: onOpenTree)
            }
            .onHover { hovering in
                withAnimation(.easeInOut(duration: 0.12)) {
                    isHovered = hovering
                }
            }

            if isActive {
                Text(project.path)
                    .font(.system(size: 9))
                    .foregroundColor(.secondary.opacity(0.55))
                    .lineLimit(1)
                    .padding(.leading, 34)
                    .padding(.trailing, 8)
                    .padding(.bottom, 2)
            }

            if showsSessions && project.sessions.isEmpty {
                Text(appPreferences.text("project.noChats"))
                    .font(.system(size: 10))
                    .foregroundColor(.secondary.opacity(0.45))
                    .padding(.leading, 34)
                    .padding(.vertical, 4)
            } else if showsSessions {
                VStack(alignment: .leading, spacing: 1) {
                    ForEach(project.sessions) { session in
                        CompactProjectSessionRow(
                            session: session,
                            isActive: session.session_id == currentSessionId,
                            isSelected: selectedSessionIds.contains(session.session_id),
                            onSelect: { onSelectSession(session) },
                            onDelete: { onDeleteSession(session) },
                            onRename: { onRenameSession(session) },
                            onPin: { onPinSession(session) }
                        )
                    }
                }
                .padding(.leading, 14)
                .padding(.bottom, 4)
            }
        }
    }
}

struct CompactProjectSessionRow: View {
    @Environment(\.colorScheme) var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences

    let session: SessionInfo
    let isActive: Bool
    let isSelected: Bool
    let onSelect: () -> Void
    let onDelete: () -> Void
    let onRename: () -> Void
    let onPin: () -> Void

    @State private var isHovered = false
    @State private var showsDeleteConfirmation = false

    private var titleText: String {
        if let name = session.name, !name.isEmpty {
            return name
        }
        if let preview = session.preview, !preview.isEmpty {
            return preview
        }
        return appPreferences.text("conversation.newConversation")
    }

    private var selectedBackground: Color {
        AcrossTheme.selectedFill(for: colorScheme)
    }

    private var selectedAccent: Color {
        AcrossTheme.accent
    }

    private var titleColor: Color {
        if colorScheme == .dark {
            return isActive ? Color.white.opacity(0.96) : Color.white.opacity(isHovered ? 0.86 : 0.74)
        }
        return isActive ? .primary : .secondary.opacity(isHovered ? 0.95 : 0.78)
    }

    var body: some View {
        HStack(spacing: 7) {
            Image(systemName: isActive ? "bubble.left.and.bubble.right.fill" : "bubble.left.and.bubble.right")
                .font(.system(size: 10))
                .foregroundColor(isActive ? selectedAccent : .secondary.opacity(0.55))
                .frame(width: 14)

            Text(titleText)
                .font(.system(size: 11, weight: isActive ? .medium : .regular))
                .foregroundColor(titleColor)
                .lineLimit(1)

            Spacer(minLength: 4)

            if session.is_pinned {
                Image(systemName: "pin.fill")
                    .font(.system(size: 8, weight: .semibold))
                    .foregroundColor(.secondary.opacity(0.58))
            }

            if session.message_count > 0 {
                Text("\(session.message_count)")
                    .font(.system(size: 8, weight: .semibold))
                    .foregroundColor(.secondary.opacity(0.55))
            }
        }
        .padding(.leading, 8)
        .padding(.trailing, 8)
        .padding(.vertical, 6)
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(
                    isActive
                        ? selectedBackground
                        : (isSelected || isHovered ? AcrossTheme.hoverFill(for: colorScheme) : Color.clear)
                )
        )
        .contentShape(Rectangle())
        .onTapGesture(perform: onSelect)
        .focusable()
        .onKeyPress(.return) {
            onSelect()
            return .handled
        }
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isButton)
        .accessibilityValue(Text(isActive ? appPreferences.text("operations.selected") : ""))
        .accessibilityAction(.default, onSelect)
        .onHover { hovering in
            withAnimation(.easeInOut(duration: 0.12)) {
                isHovered = hovering
            }
        }
        .contextMenu {
            Button(session.is_pinned ? appPreferences.text("conversation.unpin") : appPreferences.text("conversation.pin"), action: onPin)
            Button(appPreferences.text("conversation.rename"), action: onRename)
            Divider()
            Button(appPreferences.text("conversation.deleteSession"), role: .destructive) {
                showsDeleteConfirmation = true
            }
        }
        .alert(appPreferences.text("conversation.deleteConfirmTitle"), isPresented: $showsDeleteConfirmation) {
            Button(appPreferences.text("system.cancel"), role: .cancel) {}
            Button(appPreferences.text("conversation.deleteSession"), role: .destructive, action: onDelete)
        } message: {
            Text(appPreferences.text("conversation.deleteConfirmMessage"))
        }
    }
}

// MARK: - Session Row View

struct SessionRowView: View {
    let session: SessionInfo
    let isActive: Bool
    let isSelected: Bool
    let selectedCount: Int
    let isRenaming: Bool
    @Binding var renameText: String
    let onDelete: () -> Void
    let onMultiDelete: () -> Void
    let onRenameStart: () -> Void
    let onRenameCommit: () -> Void

    @Environment(\.colorScheme) var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    @FocusState private var isFocused: Bool
    @State private var isHovered = false
    @State private var showsDeleteConfirmation = false
    @State private var showsMultiDeleteConfirmation = false

    private var accent: Color {
        AcrossTheme.accent
    }

    private var titleText: String {
        if let name = session.name, !name.isEmpty {
            return name
        }
        if let preview = session.preview, !preview.isEmpty {
            return preview
        }
        return appPreferences.text("conversation.newConversation")
    }

    private var subtitle: String {
        let date = parseDate(session.updated_at)
        return formatRelativeDate(date)
    }

    var body: some View {
        HStack(spacing: 0) {
            // Left accent bar for active session
            RoundedRectangle(cornerRadius: 1)
                .fill(isActive ? accent : Color.clear)
                .frame(width: 2)
                .padding(.vertical, 6)

            HStack(spacing: 10) {
                // Session icon
                sessionIcon
                    .foregroundColor(isActive ? accent : .secondary.opacity(0.5))

                // Text content
                VStack(alignment: .leading, spacing: 2) {
                    if isRenaming {
                        TextField(appPreferences.text("conversation.sessionName"), text: $renameText)
                            .textFieldStyle(.plain)
                            .font(.system(size: 11, weight: .medium))
                            .focused($isFocused)
                            .onSubmit { onRenameCommit() }
                            .onAppear { isFocused = true }
                            .padding(.horizontal, -4)
                    } else {
                        Text(titleText)
                            .font(.system(size: 11, weight: isActive ? .medium : .regular))
                            .lineLimit(1)
                            .foregroundColor(
                                isActive
                                    ? .primary
                                    : (isHovered ? .primary.opacity(0.85) : .secondary.opacity(0.75))
                            )
                    }

                    HStack(spacing: 6) {
                        Text(subtitle)
                            .font(.system(size: 9))
                            .foregroundColor(.secondary.opacity(0.55))

                        if session.message_count > 0 {
                            Text("\(session.message_count)")
                                .font(.system(size: 8, weight: .semibold))
                                .foregroundColor(isActive ? accent : .secondary.opacity(0.6))
                                .padding(.horizontal, 5)
                                .padding(.vertical, 1)
                                .background(
                                    RoundedRectangle(cornerRadius: 3)
                                        .fill(isActive
                                            ? accent.opacity(colorScheme == .dark ? 0.2 : 0.15)
                                            : Color.secondary.opacity(0.1))
                                )
                        }
                    }
                }

                Spacer(minLength: 4)

                // Multi-select checkmark
                if isSelected && !isActive {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 12))
                        .foregroundColor(accent)
                        .transition(.scale.combined(with: .opacity))
                }
            }
            .padding(.leading, 10)
            .padding(.trailing, 10)
            .padding(.vertical, 7)
        }
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(backgroundFill)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
        )
        .contentShape(Rectangle())
        .onHover { hovering in
            withAnimation(.easeInOut(duration: 0.12)) {
                isHovered = hovering
            }
        }
        .contextMenu {
            Button(appPreferences.text("conversation.rename")) { onRenameStart() }
            Divider()
            if isSelected && selectedCount > 1 {
                Button(String(format: appPreferences.text("conversation.deleteSessions"), selectedCount), role: .destructive) {
                    showsMultiDeleteConfirmation = true
                }
            } else {
                Button(appPreferences.text("conversation.deleteSession"), role: .destructive) {
                    showsDeleteConfirmation = true
                }
            }
        }
        .alert(appPreferences.text("conversation.deleteConfirmTitle"), isPresented: $showsDeleteConfirmation) {
            Button(appPreferences.text("system.cancel"), role: .cancel) {}
            Button(appPreferences.text("conversation.deleteSession"), role: .destructive, action: onDelete)
        } message: {
            Text(appPreferences.text("conversation.deleteConfirmMessage"))
        }
        .alert(appPreferences.text("conversation.deleteMultipleConfirmTitle"), isPresented: $showsMultiDeleteConfirmation) {
            Button(appPreferences.text("system.cancel"), role: .cancel) {}
            Button(
                String(format: appPreferences.text("conversation.deleteSessions"), selectedCount),
                role: .destructive,
                action: onMultiDelete
            )
        } message: {
            Text(appPreferences.text("conversation.deleteConfirmMessage"))
        }
    }

    // MARK: - Subviews

    private var sessionIcon: some View {
        ZStack {
            if session.message_count == 0 {
                Image(systemName: "bubble.left")
                    .font(.system(size: 12))
            } else if isActive {
                Image(systemName: "bubble.left.and.bubble.right.fill")
                    .font(.system(size: 12))
            } else {
                Image(systemName: "bubble.left.and.bubble.right")
                    .font(.system(size: 12))
            }
        }
        .frame(width: 18, alignment: .center)
    }

    // MARK: - Helpers

    private var backgroundFill: Color {
        if isActive {
            return accent.opacity(colorScheme == .dark ? 0.18 : 0.10)
        }
        if isSelected {
            return accent.opacity(colorScheme == .dark ? 0.10 : 0.05)
        }
        if isHovered {
            return colorScheme == .dark
                ? Color.white.opacity(0.06)
                : Color.black.opacity(0.04)
        }
        return Color.clear
    }

    private func parseDate(_ dateString: String) -> Date {
        let fmt = DateFormatter()
        fmt.dateFormat = "yyyy-MM-dd HH:mm:ss"
        fmt.locale = Locale(identifier: "en_US_POSIX")
        fmt.timeZone = TimeZone.current
        return fmt.date(from: dateString) ?? Date()
    }

    private func formatRelativeDate(_ date: Date) -> String {
        let cal = Calendar.current
        if cal.isDateInToday(date) {
            let f = DateFormatter()
            f.dateFormat = "HH:mm"
            return f.string(from: date)
        }
        if cal.isDateInYesterday(date) {
            return appPreferences.text("conversation.yesterday")
        }
        if cal.isDate(date, equalTo: Date(), toGranularity: .weekOfYear) {
            let f = DateFormatter()
            f.dateFormat = "EEEE"
            return f.string(from: date)
        }
        let f = DateFormatter()
        f.dateFormat = "MM/dd/yy"
        return f.string(from: date)
    }
}
