import SwiftUI

struct WorkspaceCandidatePanes: View {
    @ObservedObject var operations: AgentWorkspaceOperationsViewModel
    @ObservedObject var preferences: AppPreferences
    @Binding var selectedPane: WorkspacePaneKind
    let onOpenReviewQueue: () -> Void

    @Environment(\.colorScheme) private var colorScheme
    @State private var reviewComment = ""
    @State private var selectedReviewAnchor: WorkspaceDiffLineAnchor?
    @State private var approvedBy = ""
    @State private var promotionConfirmed = false
    @FocusState private var focusedPane: WorkspacePaneKind?

    var body: some View {
        VStack(spacing: 0) {
            candidateBar
            Rectangle().fill(AcrossTheme.separator(for: colorScheme)).frame(height: 1)
            paneBar
            Rectangle().fill(AcrossTheme.separator(for: colorScheme)).frame(height: 1)
            paneContent
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .background(AcrossTheme.canvasFill(for: colorScheme))
        .onChange(of: operations.selectedCandidateId) {
            reviewComment = ""
            selectedReviewAnchor = nil
            approvedBy = ""
            promotionConfirmed = false
        }
    }

    private var candidateBar: some View {
        HStack(spacing: 8) {
            if let workspace = operations.workspace, !workspace.candidates.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 4) {
                        ForEach(workspace.candidates) { candidate in
                            Button {
                                operations.selectedCandidateId = candidate.candidateId
                            } label: {
                                HStack(spacing: 7) {
                                    AgentIdentityBadge(
                                        agentId: candidate.agentId,
                                        ownerAgentId: nil,
                                        size: 22,
                                        status: candidate.status
                                    )
                                    VStack(alignment: .leading, spacing: 1) {
                                        Text(candidate.agentId)
                                            .font(.system(size: 10, weight: .semibold))
                                        Text(String(format: preferences.text("workspace.attempt"), candidate.attempt))
                                            .font(.system(size: 8))
                                            .foregroundStyle(.secondary)
                                    }
                                    StatusChip(status: candidate.status, label: "")
                                        .accessibilityHidden(true)
                                }
                                .padding(.horizontal, 8)
                                .frame(height: 38)
                                .background(
                                    operations.selectedCandidateId == candidate.candidateId
                                        ? AcrossTheme.selectedFill(for: colorScheme)
                                        : Color.clear
                                )
                                .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.controlCornerRadius))
                            }
                            .buttonStyle(.plain)
                            .accessibilityLabel(Text(candidate.agentId))
                            .accessibilityValue(Text(StatusPalette.displayText(for: candidate.status)))
                            .help(candidate.candidateId)
                        }
                    }
                }
            } else {
                Text(preferences.text("workspace.noCandidates"))
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 8)
            if operations.workspace?.canCancel == true {
                Button(role: .destructive) {
                    Task { await operations.cancel() }
                } label: {
                    Label(preferences.text("workspace.cancel"), systemImage: "stop.circle")
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(operations.isPerformingAction)
                .help(preferences.text("workspace.cancelHelp"))
            }
        }
        .padding(.horizontal, 10)
        .frame(height: 50)
        .background(AcrossTheme.panelFill(for: colorScheme))
    }

    private var paneBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 3) {
                ForEach(WorkspacePaneKind.allCases) { pane in
                    Button {
                        selectedPane = pane
                    } label: {
                        HStack(spacing: 6) {
                            Image(systemName: pane.systemName)
                                .font(.system(size: 11, weight: .semibold))
                                .accessibilityHidden(true)
                            Text(preferences.text(pane.localizationKey))
                                .font(.system(size: 11, weight: .semibold))
                                .lineLimit(1)
                        }
                        .foregroundStyle(selectedPane == pane ? AcrossTheme.accent : Color.secondary)
                        .padding(.horizontal, 9)
                        .frame(height: 30)
                        .background(selectedPane == pane ? AcrossTheme.selectedFill(for: colorScheme) : Color.clear)
                        .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.controlCornerRadius))
                    }
                    .buttonStyle(.plain)
                    .focused($focusedPane, equals: pane)
                    .accessibilityLabel(Text(preferences.text(pane.localizationKey)))
                    .help(preferences.text(pane.localizationKey))
                }
            }
            .padding(.horizontal, 10)
        }
        .frame(height: 44)
        .background(AcrossTheme.panelFill(for: colorScheme))
    }

    @ViewBuilder
    private var paneContent: some View {
        if let candidate = operations.selectedCandidate {
            switch selectedPane {
            case .output: outputPane(candidate)
            case .toolCalls: toolCallsPane(candidate)
            case .changes: changesPane(candidate)
            case .providerUsage: providerPane(candidate)
            case .evidence: evidencePane(candidate)
            case .approval: approvalPane(candidate)
            }
        } else {
            OperationalContentStateView(state: .empty, title: preferences.text("workspace.noCandidateSelected"))
        }
    }

    private func outputPane(_ candidate: AgentWorkspaceCandidate) -> some View {
        let events = operations.events(for: candidate.candidateId)
        let comparison = operations.selectedComparisonCandidate?.comparison ?? candidate.comparison
        return VStack(spacing: 0) {
            HStack {
                Text(preferences.text("workspace.output.bounded"))
                    .font(.system(size: 10, weight: .medium))
                    .foregroundStyle(.secondary)
                Spacer()
                Text("\(events.count)/\(AgentWorkspaceOperationsViewModel.maximumDisplayedEvents)")
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(.secondary)
            }
            .padding(.horizontal, 12)
            .frame(height: 34)

            ScrollView {
                LazyVStack(alignment: .leading, spacing: 10) {
                    EvidencePanel(
                        title: preferences.text("workspace.output.summary"),
                        summary: preferences.text("workspace.output.notPersisted"),
                        status: candidate.status,
                        metadata: [
                            EvidenceMetadata(key: "output_bytes", value: candidate.run?.outputBytes.map(String.init) ?? "-"),
                            EvidenceMetadata(key: "output_sha256", value: candidate.run?.outputSha256 ?? "-"),
                            EvidenceMetadata(key: "transcript_persisted", value: String(candidate.run?.transcriptPersisted ?? false)),
                        ]
                    ) {
                        VStack(alignment: .leading, spacing: 6) {
                            ForEach(comparison.tests.results) { result in
                                ActionRow(
                                    systemName: StatusPalette.systemImage(for: result.status),
                                    title: String(format: preferences.text("workspace.output.validation"), result.index + 1),
                                    detail: String(
                                        format: preferences.text("workspace.output.byteCounts"),
                                        result.stdoutBytes,
                                        result.stderrBytes
                                    ),
                                    status: result.status
                                )
                            }
                            if comparison.tests.results.isEmpty {
                                Text(preferences.text("workspace.output.noValidation"))
                                    .font(.system(size: 10))
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }

                    if events.isEmpty {
                        OperationalContentStateView(
                            state: candidate.status == "running" ? .active(candidate.status) : .empty,
                            title: preferences.text("workspace.output.empty")
                        )
                        .frame(minHeight: 150)
                    } else {
                        ForEach(events) { event in
                            HStack(alignment: .top, spacing: 9) {
                                Text("#\(event.sequence)")
                                    .font(.system(size: 9, weight: .semibold, design: .monospaced))
                                    .foregroundStyle(.secondary)
                                    .frame(width: 44, alignment: .leading)
                                VStack(alignment: .leading, spacing: 3) {
                                    HStack {
                                        Text(event.type)
                                            .font(.system(size: 10, weight: .semibold, design: .monospaced))
                                        Spacer()
                                        if let timestamp = event.timestamp {
                                            Text(timestamp)
                                                .font(.system(size: 8, design: .monospaced))
                                                .foregroundStyle(.secondary)
                                        }
                                    }
                                    if !event.boundedSummary.isEmpty {
                                        Text(event.boundedSummary)
                                            .font(.system(size: 10, design: .monospaced))
                                            .foregroundStyle(.secondary)
                                            .textSelection(.enabled)
                                    }
                                }
                            }
                            .padding(9)
                            .background(AcrossTheme.panelFill(for: colorScheme))
                            .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.controlCornerRadius))
                        }
                    }
                }
                .padding(12)
            }
        }
        .accessibilityLabel(Text(preferences.text("workspace.pane.output")))
    }

    private func toolCallsPane(_ candidate: AgentWorkspaceCandidate) -> some View {
        Group {
            if let run = candidate.run, !run.toolCalls.isEmpty {
                ScrollView {
                    LazyVStack(spacing: 0) {
                        ForEach(Array(run.toolCalls.prefix(100).enumerated()), id: \.offset) { index, tool in
                            ActionRow(
                                systemName: "wrench.and.screwdriver",
                                title: tool,
                                detail: String(format: preferences.text("workspace.tool.index"), index + 1),
                                status: "observed"
                            )
                        }
                    }
                    .padding(12)
                }
            } else {
                OperationalContentStateView(
                    state: candidate.status == "running" ? .active(candidate.status) : .empty,
                    title: preferences.text("workspace.tools.empty")
                )
            }
        }
    }

    private func changesPane(_ candidate: AgentWorkspaceCandidate) -> some View {
        let comparison = operations.selectedComparisonCandidate?.comparison ?? candidate.comparison
        let diffText = operations.selectedComparisonCandidate?.diff
        let boundedDiffText = diffText.map { String($0.prefix(65_536)) }
        return ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 130), spacing: 8)], spacing: 8) {
                    MetricTile(
                        title: preferences.text("workspace.changes.files"),
                        value: "\(comparison.diff.filesChanged)",
                        detail: preferences.text("workspace.metric.files"),
                        status: comparison.diff.filesChanged > 0 ? "ready" : "not_run",
                        systemName: "doc.on.doc"
                    )
                    MetricTile(
                        title: preferences.text("workspace.changes.lines"),
                        value: "+\(comparison.diff.insertions) / -\(comparison.diff.deletions)",
                        detail: preferences.text("workspace.changes.insertionsDeletions"),
                        status: "observed",
                        systemName: "plus.forwardslash.minus"
                    )
                    MetricTile(
                        title: preferences.text("workspace.changes.tests"),
                        value: StatusPalette.displayText(for: comparison.tests.status),
                        detail: "\(comparison.tests.completedCount)/\(comparison.tests.configuredCount)",
                        status: comparison.tests.status,
                        systemName: "checkmark.shield"
                    )
                    MetricTile(
                        title: preferences.text("workspace.changes.risk"),
                        value: StatusPalette.displayText(for: comparison.risk.level),
                        detail: comparison.risk.blocking ? preferences.text("workspace.changes.blocking") : preferences.text("workspace.changes.nonBlocking"),
                        status: comparison.risk.blocking ? "blocked" : comparison.risk.level,
                        systemName: "exclamationmark.shield"
                    )
                }

                EvidencePanel(
                    title: preferences.text("workspace.changes.files"),
                    summary: String(format: preferences.text("workspace.changes.fileCount"), comparison.changedFiles.count),
                    status: comparison.changedFiles.isEmpty ? "not_run" : "ready"
                ) {
                    VStack(alignment: .leading, spacing: 5) {
                        ForEach(comparison.changedFiles, id: \.self) { path in
                            Label(path, systemImage: "doc")
                                .font(.system(size: 10, design: .monospaced))
                                .textSelection(.enabled)
                        }
                    }
                }

                if let boundedDiffText, !boundedDiffText.isEmpty {
                    EvidencePanel(
                        title: preferences.text("workspace.changes.diff"),
                        summary: preferences.text("workspace.changes.diffBounded"),
                        status: comparison.patchAvailable ? "ready" : "not_run"
                    ) {
                        VStack(alignment: .leading, spacing: 7) {
                            WorkspaceDiffReviewView(
                                files: WorkspaceUnifiedDiffParser.parse(boundedDiffText),
                                comments: operations.workspace?.lineReviewBatches
                                    .filter { $0.candidateId == candidate.candidateId }
                                    .flatMap(\.comments) ?? [],
                                canComment: candidate.canCommentAndRelaunch,
                                isSubmitting: operations.isPerformingAction,
                                selectedAnchor: $selectedReviewAnchor,
                                comment: $reviewComment,
                                preferences: preferences
                            ) {
                                Task {
                                    if let selectedReviewAnchor {
                                        await operations.lineReviewAndRelaunch(reviewComment, location: selectedReviewAnchor)
                                    }
                                    if operations.errorMessage == nil {
                                        reviewComment = ""
                                        selectedReviewAnchor = nil
                                    }
                                }
                            }
                            if (diffText?.count ?? 0) > boundedDiffText.count {
                                Label(preferences.text("workspace.output.truncated"), systemImage: "scissors")
                                    .font(.system(size: 9, weight: .medium))
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
            .padding(12)
        }
    }

    private func providerPane(_ candidate: AgentWorkspaceCandidate) -> some View {
        let operational = operations.readiness?.operationalStatus(for: candidate.agentId)
        return ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                workspaceInfoRow(preferences.text("workspace.provider.status"), candidate.status, status: candidate.status)
                workspaceInfoRow(preferences.text("workspace.provider.model"), candidate.run?.model ?? preferences.text("workspace.provider.unreported"), status: candidate.run?.model == nil ? "unavailable" : "ready")
                workspaceInfoRow(preferences.text("workspace.provider.provider"), candidate.run?.provider ?? preferences.text("workspace.provider.unreported"), status: candidate.run?.provider == nil ? "unavailable" : "ready")
                workspaceInfoRow(preferences.text("workspace.provider.inputTokens"), tokenText(candidate.run?.usage?.inputTokens), status: "observed")
                workspaceInfoRow(preferences.text("workspace.provider.outputTokens"), tokenText(candidate.run?.usage?.outputTokens), status: "observed")
                workspaceInfoRow(preferences.text("workspace.provider.totalTokens"), tokenText(candidate.run?.usage?.totalTokens), status: "observed")
                workspaceInfoRow(preferences.text("workspace.provider.outputBytes"), candidate.run?.outputBytes.map(String.init) ?? "-", status: "observed")
                workspaceInfoRow(preferences.text("workspace.provider.elapsed"), candidate.run?.elapsedSeconds.map { String(format: "%.2fs", $0) } ?? "-", status: "observed")
                workspaceInfoRow(
                    preferences.text("workspace.provider.account"),
                    operational?.account.displayName ?? operational?.account.id ?? candidate.run?.account?.displayName ?? candidate.run?.account?.id ?? preferences.text("workspace.provider.unreported"),
                    status: operational?.account.status ?? candidate.run?.account?.status ?? "unknown"
                )
                workspaceInfoRow(
                    preferences.text("workspace.provider.plan"),
                    candidate.run?.account?.plan ?? candidate.run?.account?.subscription ?? "-",
                    status: candidate.run?.account == nil ? "unavailable" : "observed"
                )
                workspaceInfoRow(
                    preferences.text("workspace.provider.rateLimit"),
                    operationalRateLimitText(operational?.rateLimit) ?? rateLimitText(candidate.run?.rateLimit),
                    status: operational?.rateLimit.status ?? candidate.run?.rateLimit?.status ?? "unknown"
                )
                workspaceInfoRow(
                    preferences.text("workspace.provider.rateReset"),
                    operational?.rateLimit.resetAt
                        ?? operational?.rateLimit.retryAfterSeconds.map { String(format: "%.0fs", $0) }
                        ?? candidate.run?.rateLimit?.resetAt
                        ?? candidate.run?.rateLimit?.retryAfterSeconds.map { String(format: "%.0fs", $0) }
                        ?? "-",
                    status: operational?.rateLimit.status ?? candidate.run?.rateLimit?.status ?? "unknown"
                )
            }
            .padding(12)
        }
    }

    private func evidencePane(_ candidate: AgentWorkspaceCandidate) -> some View {
        let comparison = operations.selectedComparisonCandidate?.comparison ?? candidate.comparison
        let evidence = operations.selectedComparisonCandidate?.evidence ?? candidate.evidence
        return ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                EvidencePanel(
                    title: preferences.text("workspace.evidence.title"),
                    summary: evidence.readyForReview ? preferences.text("workspace.evidence.ready") : preferences.text("workspace.evidence.blocked"),
                    status: evidence.readyForReview ? "ready" : "blocked",
                    metadata: [
                        EvidenceMetadata(key: "evidence_sha256", value: evidence.evidenceSha256 ?? "-"),
                        EvidenceMetadata(key: "patch_sha256", value: evidence.patchSha256 ?? comparison.patchSha256 ?? "-"),
                    ]
                ) {
                    VStack(alignment: .leading, spacing: 8) {
                        evidenceCheck(preferences.text("workspace.approval.diff"), evidence.diffValidated)
                        evidenceCheck(preferences.text("workspace.approval.tests"), evidence.testsValidated)
                        evidenceCheck(preferences.text("workspace.evidence.gate"), evidence.qualityGateValidated)
                        evidenceCheck(preferences.text("workspace.evidence.risk"), evidence.riskValidated)
                        evidenceCheck(preferences.text("workspace.approval.conflicts"), evidence.conflictsValidated)
                    }
                }

                EvidencePanel(
                    title: preferences.text("workspace.evidence.qualityGate"),
                    summary: comparison.qualityGate.prReadySummary ?? preferences.text("workspace.evidence.noGateSummary"),
                    status: comparison.qualityGate.status,
                    metadata: [
                        EvidenceMetadata(key: "verdict", value: comparison.qualityGate.gateVerdict ?? "-"),
                        EvidenceMetadata(key: "evidence_hash", value: comparison.qualityGate.evidenceHash ?? "-"),
                    ]
                ) {
                    VStack(alignment: .leading, spacing: 5) {
                        ForEach(comparison.qualityGate.findings) { finding in
                            Label(finding.summary ?? finding.id, systemImage: StatusPalette.systemImage(for: finding.state))
                                .font(.system(size: 10))
                                .foregroundStyle(StatusPalette.tone(for: finding.state).foreground)
                        }
                        ForEach(comparison.qualityGate.evidenceRoutes, id: \.self) { route in
                            Text(route)
                                .font(.system(size: 9, design: .monospaced))
                                .textSelection(.enabled)
                        }
                    }
                }

                if !evidence.blockingReasons.isEmpty {
                    EvidencePanel(
                        title: preferences.text("workspace.evidence.blockers"),
                        summary: evidence.blockingReasons.joined(separator: ", "),
                        status: "blocked"
                    ) { EmptyView() }
                }

                if let links = candidate.run?.evidenceLinks, !links.isEmpty {
                    EvidencePanel(
                        title: preferences.text("workspace.evidence.links"),
                        summary: String(format: preferences.text("workspace.evidence.linkCount"), links.count),
                        status: "ready"
                    ) {
                        VStack(alignment: .leading, spacing: 5) {
                            ForEach(Array(links.prefix(100)), id: \.self) { link in
                                Text(link)
                                    .font(.system(size: 9, design: .monospaced))
                                    .textSelection(.enabled)
                            }
                        }
                    }
                }
            }
            .padding(12)
        }
    }

    private func approvalPane(_ candidate: AgentWorkspaceCandidate) -> some View {
        let workspace = operations.workspace
        let isSelected = workspace?.selectedCandidateId == candidate.candidateId
        let canPromote = candidate.canSelect && isSelected && workspace?.promotion?.status != "promoted"
        return ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                EvidencePanel(
                    title: preferences.text("workspace.approval.title"),
                    summary: preferences.text("workspace.approval.summary"),
                    status: workspace?.promotion?.status ?? "not_run",
                    metadata: [
                        EvidenceMetadata(key: preferences.text("workspace.inspector.identity"), value: candidate.candidateId),
                        EvidenceMetadata(key: preferences.text("workspace.approval.selected"), value: isSelected ? "true" : "false"),
                    ]
                ) {
                    VStack(alignment: .leading, spacing: 8) {
                        evidenceCheck(preferences.text("workspace.approval.diff"), candidate.evidence.diffValidated)
                        evidenceCheck(preferences.text("workspace.approval.tests"), candidate.evidence.testsValidated)
                        evidenceCheck(preferences.text("workspace.evidence.gate"), candidate.evidence.qualityGateValidated)
                        evidenceCheck(preferences.text("workspace.approval.human"), workspace?.promotion?.approved == true)
                    }
                }

                if candidate.canCommentAndRelaunch {
                    VStack(alignment: .leading, spacing: 7) {
                        Text(preferences.text("workspace.comment.title"))
                            .font(.system(size: 11, weight: .semibold))
                        TextEditor(text: $reviewComment)
                            .font(.system(size: 11))
                            .scrollContentBackground(.hidden)
                            .padding(6)
                            .frame(minHeight: 76)
                            .background(AcrossTheme.recessedFill(for: colorScheme))
                            .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.controlCornerRadius))
                            .accessibilityLabel(Text(preferences.text("workspace.comment.title")))
                        Button {
                            Task {
                                await operations.commentAndRelaunch(reviewComment)
                                if operations.errorMessage == nil {
                                    reviewComment = ""
                                }
                            }
                        } label: {
                            Label(preferences.text("workspace.comment.relaunch"), systemImage: "arrow.clockwise.circle")
                        }
                        .buttonStyle(.bordered)
                        .disabled(reviewComment.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || operations.isPerformingAction)
                    }
                }

                if candidate.canSelect && !isSelected {
                    Button {
                        Task { await operations.selectCandidate() }
                    } label: {
                        Label(preferences.text("workspace.approval.select"), systemImage: "checkmark.circle")
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(operations.isPerformingAction)
                }

                if isSelected {
                    VStack(alignment: .leading, spacing: 9) {
                        Text(preferences.text("workspace.approval.confirmTitle"))
                            .font(.system(size: 11, weight: .semibold))
                        TextField(preferences.text("workspace.approval.identity"), text: $approvedBy)
                            .textFieldStyle(.roundedBorder)
                            .accessibilityLabel(Text(preferences.text("workspace.approval.identity")))
                        Toggle(preferences.text("workspace.approval.confirm"), isOn: $promotionConfirmed)
                            .toggleStyle(.checkbox)
                        Button(role: .destructive) {
                            Task {
                                await operations.promote(approvedBy: approvedBy, confirmed: promotionConfirmed)
                                if operations.errorMessage == nil { promotionConfirmed = false }
                            }
                        } label: {
                            Label(preferences.text("workspace.approval.promote"), systemImage: "arrow.up.circle.fill")
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(!canPromote || !promotionConfirmed || approvedBy.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || operations.isPerformingAction)
                        .help(preferences.text("workspace.approval.promoteHelp"))
                    }
                    .padding(12)
                    .background(AcrossTheme.panelFill(for: colorScheme))
                    .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.cardCornerRadius))
                    .overlay(
                        RoundedRectangle(cornerRadius: AcrossTheme.Metrics.cardCornerRadius)
                            .stroke(AcrossTheme.separator(for: colorScheme), lineWidth: 1)
                    )
                }

                HStack {
                    Button(preferences.text("workspace.openReviewQueue"), action: onOpenReviewQueue)
                        .buttonStyle(.bordered)
                    Spacer()
                    if workspace?.canCleanup == true {
                        Button(role: .destructive) {
                            Task { await operations.cleanup() }
                        } label: {
                            Label(preferences.text("workspace.cleanup"), systemImage: "trash")
                        }
                        .buttonStyle(.bordered)
                        .disabled(operations.isPerformingAction)
                        .help(preferences.text("workspace.cleanupHelp"))
                    }
                }
            }
            .padding(14)
        }
    }

    private func workspaceInfoRow(_ title: String, _ value: String, status: String) -> some View {
        ActionRow(
            systemName: StatusPalette.systemImage(for: status),
            title: title,
            detail: value,
            status: status
        )
    }

    private func evidenceCheck(_ title: String, _ passed: Bool) -> some View {
        HStack(spacing: 8) {
            Image(systemName: StatusPalette.systemImage(for: passed ? "passed" : "pending"))
                .foregroundStyle(StatusPalette.tone(for: passed ? "passed" : "pending").foreground)
                .accessibilityHidden(true)
            Text(title).font(.system(size: 10))
            Spacer()
            StatusChip(status: passed ? "passed" : "pending")
        }
    }

    private func tokenText(_ value: Int?) -> String {
        value.map(String.init) ?? "-"
    }

    private func rateLimitText(_ limit: AgentWorkspaceRateLimit?) -> String {
        guard let limit else { return preferences.text("workspace.provider.unreported") }
        if let remaining = limit.remaining, let maximum = limit.limit {
            return "\(remaining) / \(maximum)"
        }
        if let remaining = limit.requestsRemaining { return "\(remaining) requests" }
        if let remaining = limit.tokensRemaining { return "\(remaining) tokens" }
        return limit.status.map(StatusPalette.displayText(for:)) ?? "-"
    }

    private func operationalRateLimitText(_ limit: AgentOperationalRateLimit?) -> String? {
        guard let limit else { return nil }
        if let remaining = limit.remaining, let maximum = limit.limit {
            return "\(remaining) / \(maximum)"
        }
        return StatusPalette.displayText(for: limit.status)
    }
}
