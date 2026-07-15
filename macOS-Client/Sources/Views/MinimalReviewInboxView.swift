import SwiftUI

struct MinimalReviewInboxView: View {
    @ObservedObject private var preferences: AppPreferences
    @Binding private var showsInbox: Bool

    private let snapshot: HumanReviewQueueSnapshot
    private let pendingMemories: [AcrossMemoryEntry]
    private let isLoading: Bool
    private let errorMessage: String?
    private let onRefresh: () -> Void
    private let onOpen: (HumanReviewSignal) -> Void
    private let onApproveMemories: ([AcrossMemoryEntry]) async -> Bool
    private let onArchiveMemories: ([AcrossMemoryEntry]) async -> Bool

    @State private var selectedItemID: String?
    @State private var filter: Filter = .all
    @State private var showsInspector = false
    @State private var processingGroupID: String?
    @State private var operationMessage: String?
    @State private var operationError: String?
    @Environment(\.colorScheme) private var colorScheme

    init(
        snapshot: HumanReviewQueueSnapshot,
        pendingMemories: [AcrossMemoryEntry],
        preferences: AppPreferences,
        showsInbox: Binding<Bool>,
        isLoading: Bool,
        errorMessage: String?,
        onRefresh: @escaping () -> Void,
        onOpen: @escaping (HumanReviewSignal) -> Void,
        onApproveMemories: @escaping ([AcrossMemoryEntry]) async -> Bool,
        onArchiveMemories: @escaping ([AcrossMemoryEntry]) async -> Bool
    ) {
        self.snapshot = snapshot
        self.pendingMemories = pendingMemories
        self.preferences = preferences
        _showsInbox = showsInbox
        self.isLoading = isLoading
        self.errorMessage = errorMessage
        self.onRefresh = onRefresh
        self.onOpen = onOpen
        self.onApproveMemories = onApproveMemories
        self.onArchiveMemories = onArchiveMemories
    }

    var body: some View {
        VStack(spacing: 0) {
            MinimalPageHeader(
                title: preferences.text("review.title"),
                subtitle: preferences.text("review.subtitle")
            ) {
                Text(
                    snapshot.totalCount == 1
                        ? preferences.text("review.count.one")
                        : String(format: preferences.text("review.count"), snapshot.totalCount)
                )
                    .font(.caption)
                    .foregroundStyle(.secondary)
                MinimalIconButton(
                    systemName: "tray.full",
                    label: preferences.text("review.title"),
                    action: { setInboxVisible(!showsInbox) }
                )
                MinimalIconButton(
                    systemName: "sidebar.right",
                    label: preferences.text("review.inspector"),
                    action: { showsInspector.toggle() }
                )
                MinimalIconButton(
                    systemName: "arrow.clockwise",
                    label: preferences.text("review.refresh"),
                    isDisabled: isLoading,
                    action: onRefresh
                )
            }
            .minimalPageContentFrame(bottomPadding: 8)

            content
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(AcrossTheme.canvasFill(for: colorScheme))
        .onAppear { selectFirstIfNeeded() }
        .onChange(of: snapshot.items.map(\.id)) {
            selectFirstIfNeeded()
        }
        .onChange(of: filter) {
            selectFirstIfNeeded(force: true)
        }
        .onExitCommand {
            if showsInbox {
                setInboxVisible(false)
            }
        }
    }

    @ViewBuilder
    private var content: some View {
        if isLoading && snapshot.items.isEmpty {
            MinimalWorkflowStateView(
                state: .loading,
                title: preferences.text("review.loading")
            )
        } else if let errorMessage, snapshot.items.isEmpty {
            MinimalWorkflowStateView(
                state: .error,
                title: preferences.text("review.unavailable"),
                detail: errorMessage,
                actionTitle: preferences.text("system.retry"),
                action: onRefresh
            )
        } else if snapshot.items.isEmpty {
            MinimalWorkflowStateView(
                state: .empty,
                title: preferences.text("review.empty"),
                detail: preferences.text("review.empty.detail")
            )
        } else {
            ZStack(alignment: .topLeading) {
                reviewDetail
                    .inspector(isPresented: $showsInspector) {
                        reviewInspector
                            .inspectorColumnWidth(min: 230, ideal: 270, max: 340)
                    }

                if showsInbox {
                    Color.black.opacity(0.001)
                        .contentShape(Rectangle())
                        .onTapGesture { setInboxVisible(false) }
                        .accessibilityHidden(true)

                    reviewInboxDrawer
                        .padding(10)
                        .transition(.move(edge: .leading).combined(with: .opacity))
                        .zIndex(1)
                }
            }
            .clipped()
        }
    }

    private var reviewInboxDrawer: some View {
        MinimalFloatingDrawer(width: 330) {
            VStack(spacing: 0) {
                HStack(spacing: 8) {
                    Text(preferences.text("review.title"))
                        .font(.subheadline.weight(.semibold))
                    Spacer()
                    Button {
                        setInboxVisible(false)
                    } label: {
                        Image(systemName: "xmark")
                            .frame(width: 28, height: 28)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .help(preferences.text("settings.close"))
                    .accessibilityLabel(Text(preferences.text("settings.close")))
                }
                .padding(.horizontal, 12)
                .frame(height: 44)

                Divider()
                inboxList
            }
        }
    }

    private var inboxList: some View {
        VStack(spacing: 0) {
            Picker("", selection: $filter) {
                Text(preferences.text("review.filter.all")).tag(Filter.all)
                Text(preferences.text("review.filter.blocking")).tag(Filter.blocking)
                Text(preferences.text("review.filter.approvals")).tag(Filter.approvals)
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .padding(10)

            Divider()

            List(selection: itemSelection) {
                ForEach(groupedItems, id: \.kind) { group in
                    Section(preferences.text(group.kind.localizationKey)) {
                        ForEach(group.items) { item in
                            reviewRow(item)
                                .tag(item.id)
                        }
                    }
                }
            }
            .listStyle(.inset)
        }
    }

    private var itemSelection: Binding<String?> {
        Binding(
            get: { selectedItemID },
            set: { itemID in
                selectedItemID = itemID
                if itemID != nil {
                    setInboxVisible(false)
                }
            }
        )
    }

    private func reviewRow(_ item: HumanReviewSignal) -> some View {
        HStack(alignment: .top, spacing: 9) {
            Image(systemName: icon(for: item.kind))
                .foregroundStyle(StatusPalette.tone(for: item.status).foreground)
                .frame(width: 16)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 3) {
                Text(item.title)
                    .lineLimit(1)
                Text(item.detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
            Spacer(minLength: 6)
            Image(systemName: StatusPalette.systemImage(for: item.status))
                .foregroundStyle(StatusPalette.tone(for: item.status).foreground)
                .accessibilityHidden(true)
        }
        .padding(.vertical, 3)
        .accessibilityElement(children: .combine)
        .accessibilityValue(Text(preferences.statusText(item.status)))
    }

    @ViewBuilder
    private var reviewDetail: some View {
        if let item = selectedItem {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    HStack(alignment: .top, spacing: 14) {
                        VStack(alignment: .leading, spacing: 5) {
                            Text(preferences.text(item.kind.localizationKey))
                                .font(.caption.weight(.medium))
                                .foregroundStyle(.secondary)
                            Label(item.title, systemImage: icon(for: item.kind))
                                .font(.system(size: 18, weight: .semibold))
                                .lineLimit(2)
                        }
                        Spacer(minLength: 16)
                        MinimalWorkflowStatusLabel(
                            status: item.status,
                            label: item.kind == .pendingMemory
                                ? preferences.text("memory.status.pendingReview")
                                : nil
                        )
                    }

                    Divider()

                    if item.kind == .pendingMemory {
                        memoryBatchDetail
                    } else {
                        Text(item.detail)
                            .font(.body)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)

                        Divider()

                        VStack(alignment: .leading, spacing: 10) {
                            MinimalSectionHeader(preferences.text("review.inspector"))
                            MinimalKeyValueRow(preferences.text("review.source"), value: localizedSource(item.source))
                            MinimalKeyValueRow(
                                preferences.text("review.type"),
                                value: preferences.text(item.kind.localizationKey)
                            )
                            MinimalKeyValueRow(
                                preferences.text("review.status"),
                                value: preferences.statusText(item.status)
                            )
                        }

                        Divider()

                        Label(
                            preferences.text("review.humanBoundary"),
                            systemImage: "hand.raised"
                        )
                        .font(.caption)
                        .foregroundStyle(.secondary)

                        Button {
                            onOpen(item)
                        } label: {
                            Label(preferences.text("review.open"), systemImage: "arrow.up.right.square")
                        }
                        .buttonStyle(.borderedProminent)
                        .keyboardShortcut(.return, modifiers: [])
                    }
                }
                .minimalPageContentFrame(topPadding: 16)
            }
        } else {
            MinimalWorkflowStateView(
                state: .empty,
                title: preferences.text("review.select")
            )
        }
    }

    private var memoryBatchDetail: some View {
        VStack(alignment: .leading, spacing: 14) {
            if let operationMessage {
                Label(operationMessage, systemImage: "checkmark.circle.fill")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(.green)
            }
            if let operationError {
                Label(operationError, systemImage: "exclamationmark.triangle.fill")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(.red)
            }

            Text(String(
                format: preferences.text("review.memory.batch.compressed"),
                pendingMemories.count,
                memoryReviewGroups.count
            ))
            .font(.body)
            .foregroundStyle(.secondary)

            ForEach(memoryReviewGroups) { group in
                memoryProposalRow(group)
                if group.id != memoryReviewGroups.last?.id {
                    Divider()
                }
            }
        }
    }

    private func memoryProposalRow(_ group: MemoryReviewGroup) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "memorychip")
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(AcrossTheme.accent)
                .frame(width: 28, height: 28)
                .background(AcrossTheme.selectedFill(for: colorScheme))
                .clipShape(RoundedRectangle(cornerRadius: 6))

            VStack(alignment: .leading, spacing: 5) {
                HStack(spacing: 8) {
                    Text(group.sourceLabel(
                        fallback: preferences.text("review.memory.global"),
                        multipleFormat: preferences.text("review.memory.sources")
                    ))
                        .font(.system(size: 13, weight: .semibold))
                        .lineLimit(1)
                    if group.memories.count > 1 {
                        Text("×\(group.memories.count)")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundStyle(AcrossTheme.accent)
                    }
                    Text(group.memories.first?.scope ?? "")
                        .font(.system(size: 10, weight: .medium))
                        .foregroundStyle(.secondary)
                }
                Text(group.summary)
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
                    .lineLimit(3)
                    .textSelection(.enabled)
            }

            Spacer(minLength: 8)

            HStack(spacing: 4) {
                if processingGroupID == group.id {
                    ProgressView()
                        .controlSize(.small)
                        .frame(width: 68, height: 28)
                } else {
                    Button {
                        performMemoryAction(group, approve: true)
                    } label: {
                        Label(preferences.text("review.memory.approve.short"), systemImage: "checkmark")
                    }
                    .buttonStyle(AcrossReviewActionButtonStyle(kind: .approve))
                    .help(preferences.text("review.memory.approve"))
                }

                Button {
                    performMemoryAction(group, approve: false)
                } label: {
                    Label(preferences.text("review.memory.archive.short"), systemImage: "archivebox")
                }
                .buttonStyle(AcrossReviewActionButtonStyle(kind: .archive))
                .disabled(processingGroupID != nil)
                .help(preferences.text("review.memory.archive"))
            }
        }
        .padding(.vertical, 6)
    }

    private func performMemoryAction(_ group: MemoryReviewGroup, approve: Bool) {
        guard processingGroupID == nil else { return }
        processingGroupID = group.id
        operationMessage = nil
        operationError = nil
        Task {
            let succeeded = approve
                ? await onApproveMemories(group.memories)
                : await onArchiveMemories(group.memories)
            await MainActor.run {
                processingGroupID = nil
                if succeeded {
                    operationMessage = String(
                        format: preferences.text(
                            approve ? "review.memory.approve.success" : "review.memory.archive.success"
                        ),
                        group.memories.count
                    )
                } else {
                    operationError = preferences.text("review.memory.action.failed")
                }
            }
        }
    }

    private var memoryReviewGroups: [MemoryReviewGroup] {
        var groups: [MemoryReviewGroup] = []
        var indexBySummary: [String: Int] = [:]

        for memory in pendingMemories {
            let summary = MemoryReviewTextFormatter.summary(
                for: memory.text,
                fallback: preferences.text("review.memory.structured")
            )
            let key = summary.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            if let index = indexBySummary[key] {
                groups[index].memories.append(memory)
            } else {
                indexBySummary[key] = groups.count
                groups.append(MemoryReviewGroup(id: memory.id, summary: summary, memories: [memory]))
            }
        }
        return groups
    }

    @ViewBuilder
    private var reviewInspector: some View {
        Form {
            Section(preferences.text("review.title")) {
                MinimalKeyValueRow(
                    preferences.text("review.count"),
                    value: "\(snapshot.totalCount)"
                )
                MinimalKeyValueRow(preferences.text("review.blocking"), value: "\(snapshot.blockingCount)")
            }

            if let item = selectedItem {
                Section(preferences.text(item.kind.localizationKey)) {
                    MinimalKeyValueRow(preferences.text("review.id"), value: item.id, monospaced: true)
                    MinimalKeyValueRow(preferences.text("review.source"), value: localizedSource(item.source))
                    MinimalKeyValueRow(
                        preferences.text("review.status"),
                        value: preferences.statusText(item.status)
                    )
                }
            }
        }
        .formStyle(.grouped)
    }

    private var selectedItem: HumanReviewSignal? {
        filteredItems.first { $0.id == selectedItemID }
    }

    private var filteredItems: [HumanReviewSignal] {
        switch filter {
        case .all:
            return snapshot.items
        case .blocking:
            return snapshot.items.filter(isBlocking)
        case .approvals:
            return snapshot.items.filter { [.promotion, .permission, .manualGate].contains($0.kind) }
        }
    }

    private var groupedItems: [(kind: HumanReviewKind, items: [HumanReviewSignal])] {
        HumanReviewKind.allCases.compactMap { kind in
            let items = filteredItems.filter { $0.kind == kind }
            return items.isEmpty ? nil : (kind, items)
        }
    }

    private func selectFirstIfNeeded(force: Bool = false) {
        if force || selectedItem == nil {
            selectedItemID = filteredItems.first?.id
        }
    }

    private func setInboxVisible(_ isVisible: Bool) {
        withAnimation(preferences.reduceMotion ? nil : .easeOut(duration: 0.18)) {
            showsInbox = isVisible
        }
    }

    private func isBlocking(_ item: HumanReviewSignal) -> Bool {
        if item.kind == .blockingGate { return true }
        let status = item.status
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .replacingOccurrences(of: "-", with: "_")
        return ["blocked", "error", "failed", "invalid", "missing", "timeout"]
            .contains(status)
    }

    private func icon(for kind: HumanReviewKind) -> String {
        switch kind {
        case .promotion: return "arrow.up.forward.square"
        case .pendingMemory: return "memorychip"
        case .blockingGate: return "xmark.octagon"
        case .manualGate: return "hand.raised"
        case .skippedGate: return "forward.end"
        case .permission: return "lock.shield"
        case .pluginRepair: return "wrench.and.screwdriver"
        }
    }

    private func localizedSource(_ source: String) -> String {
        let key: String
        switch source {
        case "Assist": key = "review.source.assist"
        case "System": key = "review.source.system"
        case "Agent Loop": key = "review.source.agentLoop"
        case "Context": key = "review.source.context"
        case "Workspace Readiness": key = "review.source.workspaceReadiness"
        case "Agent Workspace": key = "review.source.agentWorkspace"
        case "Quality Gate": key = "review.source.qualityGate"
        case "Release Evaluation": key = "review.source.releaseEvaluation"
        case "Plugin Lifecycle": key = "review.source.pluginLifecycle"
        default: return source
        }
        return preferences.text(key)
    }

    private enum Filter: Hashable {
        case all
        case blocking
        case approvals
    }
}

private struct MemoryReviewGroup: Identifiable {
    let id: String
    let summary: String
    var memories: [AcrossMemoryEntry]

    func sourceLabel(fallback: String, multipleFormat: String) -> String {
        let projects = Array(Set(memories.compactMap(\.projectName))).sorted()
        if projects.count == 1 {
            return projects[0]
        }
        if projects.count > 1 {
            return String(format: multipleFormat, projects.count)
        }
        return fallback
    }
}
