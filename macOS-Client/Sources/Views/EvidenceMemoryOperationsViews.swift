import SwiftUI

struct EvidenceOperationsView: View {
    @ObservedObject var lifecycle: PluginLifecycleViewModel
    @ObservedObject var tasks: TaskOrchestrationViewModel
    @ObservedObject var preferences: AppPreferences
    let onOpenFullEvidence: () -> Void

    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        VStack(spacing: 0) {
            commandBar
            Rectangle()
                .fill(AcrossTheme.separator(for: colorScheme))
                .frame(height: 1)

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    metrics
                    releaseEvidence
                    loopEvidence
                }
                .padding(16)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(AcrossTheme.canvasFill(for: colorScheme))
        .task {
            if lifecycle.plugins.isEmpty && !lifecycle.isLoadingPlugins {
                await lifecycle.load()
            }
            if tasks.releaseEvaluation == nil {
                tasks.loadReleaseEvaluation()
            }
        }
    }

    private var commandBar: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(preferences.text("evidence.title"))
                    .font(.system(size: 16, weight: .semibold))
                Text(preferences.text("evidence.subtitle"))
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
            }
            Spacer()
            CommandToolbarButton(
                systemName: "arrow.clockwise",
                accessibilityLabel: preferences.text("evidence.refresh"),
                help: preferences.text("evidence.refresh"),
                isDisabled: lifecycle.isLoadingPlugins || tasks.isLoadingReleaseEvaluation
            ) {
                Task { await lifecycle.load(probe: true) }
                tasks.loadReleaseEvaluation()
            }
            Button(preferences.text("evidence.openCenter"), action: onOpenFullEvidence)
                .buttonStyle(.bordered)
                .controlSize(.small)
        }
        .padding(.horizontal, 18)
        .frame(height: 58)
        .background(AcrossTheme.panelFill(for: colorScheme))
    }

    private var metrics: some View {
        let release = tasks.releaseEvaluation
        let loop = lifecycle.agentLoopEvidenceSummary
        return LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: 8)], spacing: 8) {
            MetricTile(
                title: preferences.text("evidence.metric.release"),
                value: "\(release?.releaseEvidenceCount ?? 0)",
                detail: preferences.text("evidence.metric.bundles"),
                status: release?.releaseReadiness ?? "unknown",
                systemName: "archivebox"
            )
            MetricTile(
                title: preferences.text("evidence.metric.events"),
                value: "\(loop?.eventAudit?.eventCount ?? 0)",
                detail: preferences.text("evidence.metric.audited"),
                status: loop?.status ?? "not_run",
                systemName: "timeline.selection"
            )
            MetricTile(
                title: preferences.text("evidence.metric.routes"),
                value: "\(loop?.routing?.routedActionCount ?? 0)",
                detail: preferences.text("evidence.metric.decisions"),
                status: loop?.status ?? "not_run",
                systemName: "arrow.triangle.turn.up.right.diamond"
            )
            MetricTile(
                title: preferences.text("evidence.metric.memory"),
                value: "\(lifecycle.agentLoopMemoryCandidates.count)",
                detail: preferences.text("evidence.metric.candidates"),
                status: lifecycle.agentLoopMemoryCandidates.isEmpty ? "none" : "pending",
                systemName: "memorychip"
            )
        }
    }

    @ViewBuilder
    private var releaseEvidence: some View {
        if let release = tasks.releaseEvaluation {
            EvidencePanel(
                title: preferences.text("evidence.release.title"),
                summary: release.recommendation ?? preferences.text("evidence.release.summary"),
                status: release.releaseReadiness,
                metadata: [
                    EvidenceMetadata(key: preferences.text("evidence.release.passed"), value: "\(release.passedEvidenceCount)"),
                    EvidenceMetadata(key: preferences.text("evidence.release.total"), value: "\(release.releaseEvidenceCount)"),
                    EvidenceMetadata(key: preferences.text("evidence.release.score"), value: release.averageFinalQualityScore.map(String.init) ?? "-"),
                ]
            ) {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(Array(release.recentEvaluations.prefix(5).enumerated()), id: \.element.id) { index, task in
                        TimelineRow(
                            systemName: "doc.text.magnifyingglass",
                            title: task.description,
                            detail: task.taskId,
                            status: task.qualityGate ?? task.status,
                            isLast: index == min(4, release.recentEvaluations.count - 1)
                        )
                    }
                    if release.recentEvaluations.isEmpty {
                        Text(preferences.text("evidence.release.empty"))
                            .font(.system(size: 11))
                            .foregroundStyle(.secondary)
                    }
                }
            }
        } else if let error = tasks.releaseEvaluationError {
            OperationalContentStateView(
                state: .error(error),
                title: preferences.text("evidence.release.unavailable"),
                retryTitle: preferences.text("system.retry"),
                retry: tasks.loadReleaseEvaluation
            )
            .frame(minHeight: 170)
        }
    }

    @ViewBuilder
    private var loopEvidence: some View {
        if let evidence = lifecycle.agentLoopEvidenceSummary {
            EvidencePanel(
                title: preferences.text("evidence.loop.title"),
                summary: preferences.text("evidence.loop.summary"),
                status: evidence.status,
                metadata: [
                    EvidenceMetadata(key: preferences.text("evidence.loop.id"), value: evidence.loopId),
                    EvidenceMetadata(key: preferences.text("evidence.loop.schema"), value: evidence.schemaVersion ?? "-"),
                ]
            ) {
                VStack(alignment: .leading, spacing: 8) {
                    TimelineRow(
                        systemName: "list.number",
                        title: preferences.text("evidence.loop.sequence"),
                        detail: preferences.text("evidence.loop.sequence.detail"),
                        status: evidence.eventAudit?.sequenceContiguous == true ? "passed" : "attention"
                    )
                    TimelineRow(
                        systemName: "point.3.connected.trianglepath.dotted",
                        title: preferences.text("evidence.loop.routing"),
                        detail: String(format: preferences.text("evidence.loop.routing.detail"), evidence.routing?.routedActionCount ?? 0),
                        status: evidence.status
                    )
                    TimelineRow(
                        systemName: "memorychip",
                        title: preferences.text("evidence.loop.memory"),
                        detail: String(format: preferences.text("evidence.loop.memory.detail"), lifecycle.agentLoopMemoryCandidates.count),
                        status: lifecycle.agentLoopMemoryCandidates.isEmpty ? "none" : "pending",
                        isLast: true
                    )
                }
            }
        } else {
            EvidencePanel(
                title: preferences.text("evidence.loop.title"),
                summary: preferences.text("evidence.loop.empty"),
                status: "not_run"
            ) {
                Button(preferences.text("evidence.loop.openPlugins"), action: onOpenFullEvidence)
                    .buttonStyle(.bordered)
                    .controlSize(.small)
            }
        }
    }
}

struct MemoryOperationsView: View {
    @ObservedObject var search: MemorySearchViewModel
    @ObservedObject var lifecycle: PluginLifecycleViewModel
    @ObservedObject var preferences: AppPreferences
    let activeProjectPath: String?

    @Environment(\.colorScheme) private var colorScheme
    @FocusState private var searchFocused: Bool
    @State private var pendingBulkAction: MemoryBulkAction?
    @State private var memoryPage = 0

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                pageHeader
                searchBar
                operationNotice
                if search.hasSearched || search.hasImproved || search.isSearching || search.isImproving {
                    suggestionsSection
                    retrievalSection
                }
                librarySection
            }
            .minimalPageContentFrame()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(AcrossTheme.canvasFill(for: colorScheme))
        .task {
            lifecycle.memoryStatusFilter = ""
            search.scope = .ordinary
            await lifecycle.loadMemories()
        }
        .onChange(of: allVisibleMemories.count) {
            memoryPage = MemoryPagination.clampedIndex(memoryPage, itemCount: allVisibleMemories.count)
        }
        .confirmationDialog(
            preferences.text("memory.bulk.confirmTitle"),
            isPresented: Binding(
                get: { pendingBulkAction != nil },
                set: { if !$0 { pendingBulkAction = nil } }
            ),
            titleVisibility: .visible,
            presenting: pendingBulkAction
        ) { action in
            Button(
                preferences.text(action == .approve ? "memory.bulk.approve" : "memory.bulk.archive"),
                role: action == .archive ? .destructive : nil
            ) {
                performBulkAction(action)
            }
            Button(preferences.text("system.cancel"), role: .cancel) {
                pendingBulkAction = nil
            }
        } message: { action in
            Text(String(
                format: preferences.text(
                    action == .approve ? "memory.bulk.approveConfirm" : "memory.bulk.archiveConfirm"
                ),
                pendingMemories.count
            ))
        }
    }

    private var pageHeader: some View {
        MinimalPageHeader(
            title: preferences.text("memory.title"),
            subtitle: preferences.text("memory.subtitle")
        ) {
            MinimalIconButton(
                systemName: "wand.and.stars",
                label: copy("Organize memory suggestions", "整理记忆建议"),
                isDisabled: search.isBusy
            ) {
                Task { await search.improve(projectRoot: activeProjectPath) }
            }

            MinimalIconButton(
                systemName: "arrow.clockwise",
                label: preferences.text("memory.refresh"),
                isDisabled: search.isBusy
            ) {
                Task { await refreshMemory() }
            }
        }
    }

    private var searchBar: some View {
        HStack(spacing: 10) {
            TextField(preferences.text("memory.searchPlaceholder"), text: $search.query)
                .textFieldStyle(.roundedBorder)
                .focused($searchFocused)
                .onSubmit { Task { await searchMemory() } }
                .accessibilityLabel(Text(preferences.text("memory.searchPlaceholder")))

            MinimalIconButton(
                systemName: "magnifyingglass",
                label: preferences.text("memory.search"),
                isDisabled: search.isSearching || search.query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            ) {
                Task { await searchMemory() }
            }

            if search.hasSearched {
                Text(String(format: preferences.text("memory.resultCount"), search.resultCount))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
        }
        .frame(maxWidth: 520, alignment: .leading)
    }

    private func searchMemory() async {
        search.scope = .ordinary
        await search.search(projectRoot: activeProjectPath)
    }

    private func refreshMemory() async {
        await lifecycle.loadMemories()
        if !search.query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            await searchMemory()
        }
    }

    @ViewBuilder
    private var operationNotice: some View {
        if lifecycle.isWorking,
           let status = lifecycle.memoryBatchTargetStatus,
           lifecycle.memoryBatchTotalCount > 0 {
            HStack(spacing: 8) {
                ProgressView()
                    .controlSize(.small)
                Text(String(
                    format: preferences.text(
                        status == "archived" ? "memory.bulk.archiving" : "memory.bulk.approving"
                    ),
                    lifecycle.memoryBatchCompletedCount,
                    lifecycle.memoryBatchTotalCount
                ))
                .font(.system(size: 11, weight: .medium))
                Spacer()
            }
            .padding(.horizontal, 12)
            .frame(minHeight: 34)
            .background(AcrossTheme.recessedFill(for: colorScheme))
        } else if let error = lifecycle.errorMessage ?? search.mutationErrorMessage {
            notice(icon: "exclamationmark.triangle", text: error, status: "failed")
        } else if let message = lifecycle.message ?? search.actionMessage {
            notice(icon: "checkmark.circle", text: message, status: "success")
        }
    }

    @ViewBuilder
    private var librarySection: some View {
        HStack(spacing: 8) {
            Text(copy("Your memory", "你的记忆"))
                .font(.system(size: 13, weight: .semibold))
            Spacer()
            if !pendingMemories.isEmpty {
                Button {
                    pendingBulkAction = .approve
                } label: {
                    Label(preferences.text("memory.bulk.approve"), systemImage: "checkmark.circle")
                }
                .buttonStyle(AcrossReviewActionButtonStyle(kind: .approve))
                .disabled(lifecycle.isWorking)

                Button {
                    pendingBulkAction = .archive
                } label: {
                    Label(preferences.text("memory.bulk.archive"), systemImage: "archivebox")
                }
                .buttonStyle(AcrossReviewActionButtonStyle(kind: .archive))
                .disabled(lifecycle.isWorking)
            }
            Text(String(format: preferences.text("memory.resultCount"), allVisibleMemories.count))
                .font(.system(size: 10, weight: .medium))
                .foregroundStyle(.secondary)
            if memoryPageCount > 1 {
                MinimalIconButton(
                    systemName: "chevron.left",
                    label: preferences.text("memory.previousPage"),
                    isDisabled: memoryPage == 0
                ) {
                    memoryPage = max(0, memoryPage - 1)
                }
                Text(String(
                    format: preferences.text("memory.pagination"),
                    memoryPage + 1,
                    memoryPageCount
                ))
                .font(.system(size: 10, weight: .medium))
                .foregroundStyle(.secondary)
                .monospacedDigit()
                MinimalIconButton(
                    systemName: "chevron.right",
                    label: preferences.text("memory.nextPage"),
                    isDisabled: memoryPage + 1 >= memoryPageCount
                ) {
                    memoryPage = min(memoryPageCount - 1, memoryPage + 1)
                }
            }
        }

        if lifecycle.isLoadingMemories && lifecycle.memories.isEmpty {
            sectionState(state: .loading, title: preferences.text("memory.loading"))
        } else if visibleMemories.isEmpty {
            sectionState(
                state: .empty,
                title: copy("No memory yet", "还没有记忆"),
                message: copy(
                    "Approved project context will appear here as you complete work.",
                    "完成工作后，经过确认的项目上下文会出现在这里。"
                )
            )
        } else {
            listSurface {
                ForEach(visibleMemories) { memory in
                    libraryMemoryRow(memory)
                }
            }
        }
    }

    private var visibleMemories: [AcrossMemoryEntry] {
        MemoryPagination.page(allVisibleMemories, index: memoryPage)
    }

    private var allVisibleMemories: [AcrossMemoryEntry] {
        lifecycle.memories.filter { $0.status != "archived" && $0.status != "expired" }
    }

    private var memoryPageCount: Int {
        MemoryPagination.pageCount(itemCount: allVisibleMemories.count)
    }

    private var pendingMemories: [AcrossMemoryEntry] {
        lifecycle.memories.filter { $0.status == "pending" }
    }

    private func performBulkAction(_ action: MemoryBulkAction) {
        let memories = pendingMemories
        pendingBulkAction = nil
        guard !memories.isEmpty else { return }
        Task {
            await lifecycle.updateMemories(
                memories,
                status: action == .approve ? "active" : "archived"
            )
        }
    }

    private func libraryMemoryRow(_ memory: AcrossMemoryEntry) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "memorychip")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(StatusPalette.tone(for: memory.status).foreground)
                .frame(width: 22, height: 22)
                .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: 5) {
                HStack(spacing: 7) {
                    StatusChip(
                        status: memory.status,
                        label: memory.status == "pending"
                            ? preferences.text("memory.status.pendingReview")
                            : preferences.statusText(memory.status)
                    )
                    Text(memory.scope)
                        .font(.system(size: 9, weight: .medium))
                        .foregroundStyle(.secondary)
                    if let projectName = memory.projectName {
                        Text(projectName)
                            .font(.system(size: 9, weight: .medium))
                            .foregroundStyle(.secondary)
                    }
                }
                Text(MemoryReviewTextFormatter.summary(
                    for: memory.text,
                    fallback: preferences.text("review.memory.structured")
                ))
                .font(.system(size: 12))
                .lineLimit(4)
                .textSelection(.enabled)
            }

            Spacer(minLength: 12)

            if memory.status == "pending" {
                Button {
                    Task { await lifecycle.updateMemory(memory, status: "active") }
                } label: {
                    Label(preferences.text("review.memory.approve.short"), systemImage: "checkmark")
                }
                .buttonStyle(AcrossReviewActionButtonStyle(kind: .approve))
                .disabled(lifecycle.isWorking)
            }

            Button {
                Task { await lifecycle.updateMemory(memory, status: "archived") }
            } label: {
                Image(systemName: "archivebox")
            }
            .buttonStyle(AcrossReviewActionButtonStyle(kind: .archive))
            .disabled(lifecycle.isWorking)
            .help(preferences.text("review.memory.archive"))
            .accessibilityLabel(Text(preferences.text("review.memory.archive")))
        }
        .padding(12)
        .frame(maxWidth: .infinity, minHeight: 58, alignment: .leading)
        .overlay(alignment: .bottom) {
            Rectangle()
                .fill(AcrossTheme.separator(for: colorScheme))
                .frame(height: 1)
        }
        .accessibilityElement(children: .contain)
    }

    @ViewBuilder
    private var suggestionsSection: some View {
        if search.isImproving {
            sectionState(
                state: .loading,
                title: copy("Preparing suggestions...", "正在整理建议..."),
                message: copy("Repeated memories are being grouped. Nothing will be approved automatically.", "正在归并重复记忆，不会自动批准任何内容。")
            )
        } else if let error = search.improveErrorMessage {
            sectionState(
                state: .error(error),
                title: copy("Suggestions are unavailable", "暂时无法整理建议"),
                retry: { Task { await search.improve(projectRoot: activeProjectPath) } }
            )
        } else if search.hasImproved {
            sectionHeader(
                title: copy("Suggestions for review", "待评审建议"),
                detail: search.proposals.isEmpty
                    ? copy("No new suggestions", "没有新的建议")
                    : String(format: copy("%d pending", "%d 条待评审"), search.proposals.count)
            )
            if search.proposals.isEmpty {
                sectionState(
                    state: .empty,
                    title: copy("Memory is already tidy", "记忆已整理"),
                    message: copy("No new combined memory needs review.", "当前没有需要评审的新合并记忆。")
                )
            } else {
                listSurface {
                    ForEach(search.proposals) { proposal in
                        proposalRow(proposal)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var retrievalSection: some View {
        if search.isSearching {
            sectionState(state: .loading, title: preferences.text("memory.loading"))
        } else if let error = search.errorMessage {
            sectionState(
                state: .error(error),
                title: preferences.text("memory.unavailable"),
                retry: { Task { await search.search(projectRoot: activeProjectPath) } }
            )
        } else if search.hasSearched {
            sectionHeader(
                title: copy("Best matches", "最佳匹配"),
                detail: String(format: preferences.text("memory.resultCount"), search.resultCount)
            )
            routeSummary
            if search.mergedResults.isEmpty {
                sectionState(
                    state: .empty,
                    title: preferences.text(search.scope.includesPending ? "memory.pendingEmpty" : "memory.empty")
                )
            } else {
                listSurface {
                    ForEach(search.mergedResults) { result in
                        memoryRow(result)
                    }
                }
            }
        }
    }

    private var routeSummary: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 6) { routeChips }
            VStack(alignment: .leading, spacing: 5) { routeChips }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder
    private var routeChips: some View {
        ForEach(MemoryRetrievalRoute.allCases) { route in
            let count = search.routeResults.first(where: { $0.route == route })?.resultCount
            Text(count.map { "\(routeTitle(route)) · \($0)" } ?? routeTitle(route))
                .font(.system(size: 9, weight: .medium))
                .foregroundStyle(.secondary)
                .padding(.horizontal, 7)
                .frame(height: 22)
                .background(AcrossTheme.recessedFill(for: colorScheme))
                .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.chipCornerRadius))
        }
    }

    private func proposalRow(_ proposal: MemoryDistillationProposal) -> some View {
        memoryContentRow(
            memory: proposal.memory,
            text: proposal.proposal.distilledText,
            provenance: proposal.proposal.provenance,
            contributions: [],
            rank: nil,
            canRollback: proposal.proposal.governance?.rollbackSupported == true
        )
    }

    private func memoryRow(_ result: MemoryMergedResult) -> some View {
        memoryContentRow(
            memory: result.entry,
            text: result.distilledProposal?.distilledText ?? result.entry.text,
            provenance: result.distilledProposal?.provenance,
            contributions: result.routeContributions,
            rank: result.mergedRank,
            canRollback: result.distilledProposal?.governance?.rollbackSupported == true
        )
    }

    private func memoryContentRow(
        memory: AcrossMemoryEntry,
        text: String,
        provenance: MemoryProvenance?,
        contributions: [MemoryRouteContribution],
        rank: Int?,
        canRollback: Bool
    ) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "memorychip")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(StatusPalette.tone(for: memory.status).foreground)
                .frame(width: 22, height: 22)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 5) {
                HStack(spacing: 7) {
                    if let rank {
                        Text("#\(rank)")
                            .font(.system(size: 9, weight: .semibold, design: .monospaced))
                            .foregroundStyle(.secondary)
                    }
                    StatusChip(
                        status: memory.status,
                        label: memory.status == "pending"
                            ? preferences.text("memory.status.pendingReview")
                            : preferences.statusText(memory.status)
                    )
                    Text(memory.scope)
                        .font(.system(size: 9, weight: .medium))
                        .foregroundStyle(.secondary)
                    Text(memory.type)
                        .font(.system(size: 9, weight: .medium))
                        .foregroundStyle(.secondary)
                    if let projectName = memory.projectName {
                        Text(projectName)
                            .font(.system(size: 9, weight: .medium))
                            .foregroundStyle(.secondary)
                    }
                }
                Text(text)
                    .font(.system(size: 12))
                    .foregroundStyle(.primary)
                    .lineLimit(4)
                    .textSelection(.enabled)
                if !contributions.isEmpty {
                    Text(contributions.map { routeTitle($0.route) }.joined(separator: " · "))
                        .font(.system(size: 10, weight: .medium))
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                        .accessibilityLabel(Text(copy("Matched by ", "匹配来源：") + contributions.map { routeTitle($0.route) }.joined(separator: ", ")))
                }
                if let provenance {
                    DisclosureGroup {
                        VStack(alignment: .leading, spacing: 3) {
                            ForEach(provenance.sources) { source in
                                Text("\(source.memoryId) · \(source.status ?? "-")")
                                    .font(.system(size: 9, design: .monospaced))
                                    .foregroundStyle(.secondary)
                                    .textSelection(.enabled)
                            }
                        }
                        .padding(.top, 3)
                    } label: {
                        Text(String(format: copy("Based on %d memories", "基于 %d 条原始记忆"), provenance.sourceCount))
                            .font(.system(size: 10, weight: .medium))
                    }
                }
            }
            Spacer(minLength: 12)
            CommandToolbarButton(
                systemName: "checkmark",
                accessibilityLabel: preferences.text("plugins.memory.approve"),
                help: preferences.text("plugins.memory.approve"),
                isDisabled: search.isBusy || memory.status != "pending"
            ) {
                Task {
                    await search.approve(memoryID: memory.id, projectRoot: activeProjectPath)
                    if search.mutationErrorMessage == nil {
                        AcrossLearningProgressStore.shared.record([
                            AcrossLearningEvent(kind: .memoryReviewed, sourceID: memory.id)
                        ])
                    }
                }
            }
            if canRollback {
                CommandToolbarButton(
                    systemName: "arrow.uturn.backward",
                    accessibilityLabel: copy("Restore original memories", "恢复原始记忆"),
                    help: copy("Archive this combined memory and restore its sources.", "归档这条合并记忆，并恢复其原始记忆。"),
                    isDisabled: search.isBusy
                ) {
                    Task {
                        await search.rollback(memoryID: memory.id, projectRoot: activeProjectPath)
                    }
                }
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, minHeight: 58, alignment: .leading)
        .overlay(alignment: .bottom) {
            Rectangle()
                .fill(AcrossTheme.separator(for: colorScheme))
                .frame(height: 1)
        }
        .accessibilityElement(children: .contain)
    }

    private func sectionHeader(title: String, detail: String) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title)
                .font(.system(size: 13, weight: .semibold))
            Spacer()
            Text(detail)
                .font(.system(size: 10, weight: .medium))
                .foregroundStyle(.secondary)
        }
    }

    private func sectionState(
        state: OperationalContentState,
        title: String,
        message: String? = nil,
        retry: (() -> Void)? = nil
    ) -> some View {
        OperationalContentStateView(
            state: state,
            title: title,
            message: message,
            retryTitle: retry == nil ? nil : preferences.text("system.retry"),
            retry: retry
        )
        .frame(minHeight: 150)
        .background(AcrossTheme.panelFill(for: colorScheme))
        .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.cardCornerRadius))
        .overlay(
            RoundedRectangle(cornerRadius: AcrossTheme.Metrics.cardCornerRadius)
                .stroke(AcrossTheme.separator(for: colorScheme), lineWidth: 1)
        )
    }

    private func listSurface<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        LazyVStack(spacing: 0, content: content)
            .background(AcrossTheme.panelFill(for: colorScheme))
            .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.cardCornerRadius))
            .overlay(
                RoundedRectangle(cornerRadius: AcrossTheme.Metrics.cardCornerRadius)
                    .stroke(AcrossTheme.separator(for: colorScheme), lineWidth: 1)
            )
    }

    private func notice(icon: String, text: String, status: String) -> some View {
        HStack(spacing: 8) {
            Image(systemName: icon)
                .foregroundStyle(StatusPalette.tone(for: status).foreground)
                .accessibilityHidden(true)
            Text(text)
                .font(.system(size: 11, weight: .medium))
                .textSelection(.enabled)
            Spacer()
        }
        .padding(.horizontal, 12)
        .frame(minHeight: 34)
        .background(AcrossTheme.recessedFill(for: colorScheme))
        .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.controlCornerRadius))
        .accessibilityElement(children: .combine)
    }

    private func routeTitle(_ route: MemoryRetrievalRoute) -> String {
        switch route {
        case .keyword: return copy("Words", "关键词")
        case .embedding: return copy("Meaning", "语义")
        case .evidenceGraph: return copy("Evidence", "证据")
        case .projectProfile: return copy("Project", "项目")
        case .loopRecall: return copy("Past runs", "历史迭代")
        }
    }

    private func copy(_ english: String, _ chinese: String) -> String {
        preferences.resolvedLocaleIdentifier == "zh-Hans" ? chinese : english
    }
}

enum MemoryPagination {
    static let pageSize = 8

    static func pageCount(itemCount: Int) -> Int {
        max(1, (max(0, itemCount) + pageSize - 1) / pageSize)
    }

    static func clampedIndex(_ index: Int, itemCount: Int) -> Int {
        min(max(0, index), pageCount(itemCount: itemCount) - 1)
    }

    static func page<Element>(_ items: [Element], index: Int) -> [Element] {
        let selectedIndex = clampedIndex(index, itemCount: items.count)
        let start = selectedIndex * pageSize
        let end = min(items.count, start + pageSize)
        guard start < end else { return [] }
        return Array(items[start..<end])
    }
}

private enum MemoryBulkAction {
    case approve
    case archive
}
