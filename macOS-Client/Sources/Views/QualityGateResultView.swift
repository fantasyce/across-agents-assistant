import SwiftUI

struct QualityGateResultView: View {
    let result: QualityGateResult
    @ObservedObject var preferences: AppPreferences

    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                summary
                findings
                gitBinding
                checks
                receipt
                ci
                repairPlan
                draftPR
                githubRemote
                githubReview
            }
            .padding(14)
        }
        .background(AcrossTheme.canvasFill(for: colorScheme))
    }

    private var summary: some View {
        VStack(alignment: .leading, spacing: 10) {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 145), spacing: 8)], spacing: 8) {
                MetricTile(
                    title: preferences.text("gate.metric.readiness"),
                    value: StatusPalette.displayText(for: result.gateVerdict),
                    detail: result.status ?? preferences.text("gate.metric.release"),
                    status: result.gateVerdict,
                    systemName: "checkmark.shield"
                )
                MetricTile(
                    title: preferences.text("gate.result.findings"),
                    value: "\(result.findings.count)",
                    detail: preferences.text("gate.result.normalized"),
                    status: result.isBlocked ? "blocked" : "ready",
                    systemName: "list.bullet.clipboard"
                )
                MetricTile(
                    title: preferences.text("gate.result.ci"),
                    value: StatusPalette.displayText(for: result.ci?.status),
                    detail: result.ci?.mode ?? "-",
                    status: result.ci?.status ?? "unavailable",
                    systemName: "network"
                )
                MetricTile(
                    title: preferences.text("gate.result.repairs"),
                    value: "\(result.repairPlan?.actions.count ?? 0)",
                    detail: result.repairPlan?.status ?? "not_needed",
                    status: result.repairPlan?.status ?? "not_run",
                    systemName: "wrench.and.screwdriver"
                )
            }
            EvidencePanel(
                title: preferences.text("gate.result.summary"),
                summary: result.prReadySummary ?? result.gateVerdict,
                status: result.gateVerdict,
                metadata: [
                    EvidenceMetadata(key: "repository", value: result.repository?.displayText ?? "-"),
                    EvidenceMetadata(key: "base", value: result.baseRef ?? "-"),
                    EvidenceMetadata(key: "head", value: result.headRef ?? "-"),
                    EvidenceMetadata(key: "evidence_hash", value: result.evidenceHash ?? "-"),
                ]
            ) { EmptyView() }
        }
    }

    @ViewBuilder
    private var findings: some View {
        gateSection(preferences.text("gate.result.findings"), status: result.isBlocked ? "blocked" : "ready") {
            if result.findings.isEmpty {
                Text(preferences.text("gate.result.noFindings"))
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
            } else {
                ForEach(result.findings) { finding in
                    ActionRow(
                        systemName: StatusPalette.systemImage(for: finding.state),
                        title: finding.summary ?? finding.id,
                        detail: [finding.sourceGate, finding.suggestedAction].compactMap { $0 }.joined(separator: " · "),
                        status: finding.state
                    )
                }
            }
        }
    }

    @ViewBuilder
    private var gitBinding: some View {
        if let binding = result.gitBinding {
            gateSection(preferences.text("gate.result.gitBinding"), status: binding.baseIsAncestor == false ? "blocked" : "ready") {
                resultRow("base_sha", binding.baseSha ?? "-")
                resultRow("head_sha", binding.headSha ?? "-")
                resultRow("current_head_sha", binding.currentHeadSha ?? "-")
                resultRow("branch", binding.branch ?? "-")
                resultRow("expected_branch", binding.expectedBranch ?? "-")
                resultRow("expected_commit", binding.expectedCommit ?? "-")
                resultRow("base_is_ancestor", binding.baseIsAncestor.map(String.init) ?? "-")
                resultRow("dirty_paths", binding.dirtyPaths.joined(separator: ", ").nilIfEmpty ?? "-")
            }
        }
    }

    @ViewBuilder
    private var checks: some View {
        if let checks = result.checks {
            gateSection(preferences.text("gate.result.checks"), status: result.gateVerdict) {
                ForEach(checks.commands) { check in checkRow(check, prefix: "command") }
                ForEach(checks.tools) { check in checkRow(check, prefix: "tool") }
                ForEach(checks.policies.keys.sorted(), id: \.self) { key in
                    resultRow("policy.\(key)", checks.policies[key]?.displayText ?? "-")
                }
                if checks.commands.isEmpty && checks.tools.isEmpty && checks.policies.isEmpty {
                    Text(preferences.text("gate.result.noChecks"))
                        .font(.system(size: 10))
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    @ViewBuilder
    private var receipt: some View {
        if let receipt = result.pushReceipt {
            gateSection(preferences.text("gate.result.receipt"), status: receipt.gateVerdict ?? result.gateVerdict) {
                resultRow("schema_version", receipt.schemaVersion ?? "-")
                resultRow("gate_verdict", receipt.gateVerdict ?? "-")
                resultRow("evidence_hash", receipt.evidenceHash ?? "-")
                resultRow("pr_ready_summary", receipt.prReadySummary ?? "-")
            }
        }
    }

    @ViewBuilder
    private var ci: some View {
        if let ci = result.ci {
            gateSection(preferences.text("gate.result.ciTaxonomy"), status: ci.status) {
                if let watcher = ci.watcher {
                    resultRow("watcher.mode", watcher.mode)
                    resultRow("watcher.status", watcher.status)
                    resultRow("watcher.max_wait_seconds", String(watcher.maximumWaitSeconds))
                    resultRow("watcher.deterministic_snapshot", String(watcher.deterministicSnapshot))
                    if let polls = watcher.polls { resultRow("watcher.polls", String(polls)) }
                    if let heartbeatRefresh = watcher.heartbeatRefresh {
                        resultRow("watcher.heartbeat_refresh", String(heartbeatRefresh))
                    }
                    if let idle = watcher.idleTimeoutMilliseconds {
                        resultRow("watcher.idle_timeout", duration(milliseconds: idle))
                    }
                    if let maxWall = watcher.maxWallTimeoutMilliseconds {
                        resultRow("watcher.max_wall_timeout", duration(milliseconds: maxWall))
                    }
                    if let elapsed = watcher.elapsedMilliseconds {
                        resultRow("watcher.elapsed", duration(milliseconds: elapsed))
                    }
                    if let lastHeartbeat = watcher.lastHeartbeatAt {
                        resultRow("watcher.last_heartbeat", lastHeartbeat)
                    }
                }
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 5) {
                        ForEach(ci.taxonomy, id: \.self) { item in
                            StatusChip(status: item, label: "\(item) \(ci.counts[item] ?? 0)")
                        }
                    }
                }
                ForEach(ci.checks) { check in
                    ActionRow(
                        systemName: StatusPalette.systemImage(for: check.status),
                        title: check.name,
                        detail: [
                            check.category,
                            check.conclusion,
                            check.required.map { preferences.text($0 ? "gate.result.required" : "gate.result.optional") },
                        ]
                            .compactMap { $0 }
                            .joined(separator: " · "),
                        status: check.status
                    )
                    if let summary = check.failureSummary {
                        Text(summary)
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundStyle(.secondary)
                            .textSelection(.enabled)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var githubRemote: some View {
        if let remote = result.githubRemote {
            gateSection(
                localized("GitHub remote delivery", "GitHub 远程交付"),
                status: remote.status
            ) {
                HStack(spacing: 6) {
                    StatusChip(status: remote.status)
                    if remote.recoverable {
                        Label(localized("Recoverable", "可恢复"), systemImage: "arrow.clockwise.circle")
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    if let pullRequest = remote.pullRequest,
                       let value = pullRequest.url,
                       let url = URL(string: value) {
                        Link(destination: url) {
                            Label(
                                pullRequest.number.map { "PR #\($0)" } ?? "PR",
                                systemImage: "arrow.up.right.square"
                            )
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                        .accessibilityLabel(Text(localized("Open GitHub draft pull request", "打开 GitHub 草稿 PR")))
                    }
                }

                if let authorization = remote.authorization {
                    resultRow("authorization", authorization.allowed ? "approved" : "denied")
                    resultRow("repository", authorization.repository ?? "-")
                    resultRow("push_ref", authorization.pushRef ?? "-")
                    resultRow("approval_verified", String(authorization.approvalTokenVerified))
                    resultRow("credential_available", String(authorization.credentialPresent))
                    resultRow("secret_material_included", String(authorization.secretMaterialIncluded))
                }

                if let push = remote.branchPush {
                    ActionRow(
                        systemName: StatusPalette.systemImage(for: push.status),
                        title: localized("Feature branch push", "功能分支推送"),
                        detail: [push.targetRef, push.remoteSHA].compactMap { $0 }.joined(separator: " · "),
                        status: push.status ?? "unknown"
                    )
                }

                if let pullRequest = remote.pullRequest {
                    ActionRow(
                        systemName: "arrow.triangle.pull",
                        title: pullRequest.number.map { "Draft PR #\($0)" } ?? "Draft PR",
                        detail: [pullRequest.baseRef, pullRequest.headRef].compactMap { $0 }.joined(separator: " ← "),
                        status: pullRequest.draft ? "draft" : (pullRequest.state ?? "unknown")
                    )
                }

                if let watch = remote.ciWatch {
                    remoteCIWatch(watch)
                }

                ForEach(remote.operations) { operation in
                    ActionRow(
                        systemName: StatusPalette.systemImage(for: operation.status),
                        title: operation.id,
                        detail: operationDetail(operation),
                        status: operation.status
                    )
                }

                if remote.verificationMode == "commit_status_fallback" {
                    Label(
                        localized(
                            "GitHub Check Run was unavailable; verification was published as a commit status.",
                            "GitHub Check Run 不可用，验证结果已回退发布为提交状态。"
                        ),
                        systemImage: "arrow.triangle.2.circlepath"
                    )
                    .font(.system(size: 10))
                    .foregroundStyle(StatusPalette.tone(for: "attention").foreground)
                    .fixedSize(horizontal: false, vertical: true)
                }

                if remote.remoteStateRequiresReconciliation {
                    Label(
                        localized(
                            "A remote response was lost. Retry the same branch to reconcile idempotently before taking another action.",
                            "远程响应曾丢失。请使用同一分支重试，以幂等方式核对状态后再执行其他操作。"
                        ),
                        systemImage: "exclamationmark.arrow.triangle.2.circlepath"
                    )
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(StatusPalette.tone(for: "attention").foreground)
                    .fixedSize(horizontal: false, vertical: true)
                } else if remote.status == "failed", remote.recoverable {
                    Label(
                        localized(
                            "Retry with the same branch. Existing push, draft PR, check, and comment state will be reused or reconciled.",
                            "请使用同一分支重试；既有推送、草稿 PR、检查和评论状态会被复用或核对。"
                        ),
                        systemImage: "arrow.clockwise.circle"
                    )
                    .font(.system(size: 10, weight: .semibold))
                    .fixedSize(horizontal: false, vertical: true)
                }

                ForEach(Array(remote.errors.enumerated()), id: \.offset) { _, error in
                    Label(error, systemImage: "exclamationmark.triangle")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundStyle(StatusPalette.tone(for: "blocked").foreground)
                        .textSelection(.enabled)
                        .fixedSize(horizontal: false, vertical: true)
                }

                resultRow("mutation_performed", String(remote.mutationPerformed))
                resultRow("secret_material_persisted", String(remote.secretMaterialPersisted))
                resultRow("audit_hash", remote.auditHash ?? "-")
            }
        }
    }

    private func remoteCIWatch(_ watch: QualityGateRemoteCIWatch) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            ActionRow(
                systemName: StatusPalette.systemImage(for: watch.status),
                title: localized("GitHub CI watcher", "GitHub CI 监视"),
                detail: String(format: localized("%d polls · %d heartbeats", "%d 次轮询 · %d 次心跳"), watch.polls, watch.heartbeats.count),
                status: watch.status
            )
            if let watcher = watch.snapshot?.watcher {
                HStack(spacing: 5) {
                    StatusChip(
                        status: watcher.heartbeatRefresh == true ? "active" : watcher.status,
                        label: watcher.heartbeatRefresh == true
                            ? localized("Heartbeat refresh", "心跳刷新")
                            : StatusPalette.displayText(for: watcher.status)
                    )
                    if let idle = watcher.idleTimeoutMilliseconds {
                        StatusChip(status: "idle", label: "idle \(duration(milliseconds: idle))")
                    }
                    if let maxWall = watcher.maxWallTimeoutMilliseconds {
                        StatusChip(status: "bounded", label: "max \(duration(milliseconds: maxWall))")
                    }
                }
                .accessibilityElement(children: .combine)
            }
            if let latest = watch.heartbeats.last {
                resultRow(
                    "latest_heartbeat",
                    "#\(latest.sequence) · checks \(latest.checkCount) · pending \(latest.pendingCount) · \(latest.observedAt ?? "-")"
                )
            }
            ForEach(watch.failureSummaries) { failure in
                ActionRow(
                    systemName: "xmark.octagon",
                    title: failure.name,
                    detail: failure.summary ?? failure.logSHA256 ?? "-",
                    status: "failed"
                )
            }
        }
    }

    private func operationDetail(_ operation: QualityGateRemoteOperation) -> String {
        var details: [String] = []
        if let mode = operation.verificationMode { details.append(mode) }
        if operation.resumed { details.append(localized("resumed", "已恢复")) }
        if let attempts = operation.attempts { details.append("attempts \(attempts)") }
        if let recovery = operation.recovery { details.append(recovery) }
        return details.joined(separator: " · ")
    }

    private func duration(milliseconds: Int) -> String {
        let seconds = max(0, milliseconds / 1_000)
        let hours = seconds / 3_600
        let minutes = (seconds % 3_600) / 60
        let remaining = seconds % 60
        if hours > 0 { return String(format: "%dh %02dm", hours, minutes) }
        if minutes > 0 { return String(format: "%dm %02ds", minutes, remaining) }
        return "\(remaining)s"
    }

    private func localized(_ english: String, _ simplifiedChinese: String) -> String {
        preferences.resolvedLocaleIdentifier == "zh-Hans" ? simplifiedChinese : english
    }

    @ViewBuilder
    private var repairPlan: some View {
        if let repair = result.repairPlan {
            gateSection(preferences.text("gate.result.repairPlan"), status: repair.status) {
                resultRow("rounds", "\(repair.currentRound)/\(repair.maxRounds)")
                resultRow("max_actions", "\(repair.maxActions)")
                resultRow("mutation_performed", String(repair.mutationPerformed))
                ForEach(repair.actions) { action in
                    ActionRow(
                        systemName: "wrench.and.screwdriver",
                        title: action.suggestedAction ?? action.id,
                        detail: "\(action.category) · \(action.execution)",
                        status: action.execution == "planned_only" ? "manual_required" : action.execution
                    )
                }
            }
        }
    }

    @ViewBuilder
    private var draftPR: some View {
        if let draft = result.draftPR {
            gateSection(preferences.text("gate.result.draftPR"), status: draft.status) {
                resultRow("requested", String(draft.requested))
                resultRow("ready", String(draft.ready))
                resultRow("mutation_performed", String(draft.mutationPerformed))
                resultRow("remote_mutation_allowed", String(draft.remoteMutationAllowed))
                resultRow("title", draft.title ?? "-")
                resultRow("blocking_reasons", draft.blockingReasons.joined(separator: ", ").nilIfEmpty ?? "-")
            }
        }
    }

    @ViewBuilder
    private var githubReview: some View {
        if let review = result.githubReview {
            gateSection(preferences.text("gate.result.githubReview"), status: review.checkRun?.conclusion ?? "ready") {
                resultRow("schema_version", review.schemaVersion ?? "-")
                resultRow("mutation_performed", String(review.mutationPerformed))
                resultRow("remote_mutation_allowed", String(review.remoteMutationAllowed))
                resultRow("check_run.conclusion", review.checkRun?.conclusion ?? "-")
                resultRow("check_run.head_sha", review.checkRun?.headSha ?? "-")
                if let title = review.checkRun?.output?.title {
                    Text(title)
                        .font(.system(size: 11, weight: .semibold))
                }
                if let markdown = review.checkRun?.output?.text ?? review.prComment?.body {
                    Text(.init(markdown))
                        .font(.system(size: 10))
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(10)
                        .background(AcrossTheme.recessedFill(for: colorScheme))
                        .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.controlCornerRadius))
                        .accessibilityLabel(Text(preferences.text("gate.result.githubReviewRendered")))
                }
            }
        }
    }

    private func gateSection<Content: View>(
        _ title: String,
        status: String,
        @ViewBuilder content: @escaping () -> Content
    ) -> some View {
        EvidencePanel(title: title, summary: StatusPalette.displayText(for: status), status: status) {
            VStack(alignment: .leading, spacing: 7) { content() }
        }
    }

    private func resultRow(_ key: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(key)
                .font(.system(size: 9, weight: .semibold, design: .monospaced))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.system(size: 10, design: .monospaced))
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func checkRow(_ check: QualityGateCheck, prefix: String) -> some View {
        ActionRow(
            systemName: StatusPalette.systemImage(for: check.status),
            title: "\(prefix).\(check.id)",
            detail: check.reason ?? check.argv.joined(separator: " "),
            status: check.status
        )
    }
}

private extension String {
    var nilIfEmpty: String? { isEmpty ? nil : self }
}
