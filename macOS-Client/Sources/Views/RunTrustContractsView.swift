import SwiftUI

struct RunTrustContractsView: View {
    let task: TaskOrchestrationTaskDetail
    @ObservedObject var preferences: AppPreferences

    @StateObject private var viewModel = RunTrustContractsViewModel()
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label(preferences.text("trustContracts.title"), systemImage: "lock.doc")
                    .font(.system(size: 14, weight: .semibold))
                Spacer()
                Button {
                    Task { await viewModel.load(task: task, refresh: true) }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.plain)
                .disabled(viewModel.isLoading)
                .accessibilityLabel(preferences.text("system.refresh"))
            }

            if viewModel.isLoading {
                ProgressView()
                    .controlSize(.small)
            } else {
                policyCard
                attemptCard
                replayCard
                receiptCard

                if viewModel.errorMessage != nil {
                    Label(preferences.text("trustContracts.partial"), systemImage: "exclamationmark.circle")
                        .font(.system(size: 10))
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(14)
        .background(AcrossTheme.recessedFill(for: colorScheme))
        .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.cardCornerRadius, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AcrossTheme.Metrics.cardCornerRadius, style: .continuous)
                .stroke(AcrossTheme.separator(for: colorScheme), lineWidth: 1)
        }
        .task(id: task.taskId) {
            await viewModel.load(task: task)
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(preferences.text("trustContracts.title"))
    }

    @ViewBuilder
    private var policyCard: some View {
        if let policy = viewModel.policy {
            contractCard(
                title: preferences.text("trustContracts.policy"),
                systemImage: "person.crop.rectangle.stack",
                status: policy.approval.required ? "attention" : "passed"
            ) {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 130), spacing: 8)], spacing: 8) {
                    policyMetric(
                        preferences.text("trustContracts.role"),
                        value: policy.role.label,
                        systemImage: "person.crop.circle"
                    )
                    policyMetric(
                        preferences.text("trustContracts.model"),
                        value: [policy.modelPolicy.provider, policy.modelPolicy.model]
                            .compactMap { $0 }
                            .filter { !$0.isEmpty }
                            .joined(separator: " / ")
                            .nilIfEmpty ?? preferences.text("result.unavailable"),
                        systemImage: "cpu"
                    )
                    policyMetric(
                        preferences.text("trustContracts.budget"),
                        value: String(
                            format: preferences.text("trustContracts.budgetValue"),
                            policy.budget.maxModelCalls,
                            policy.budget.maxCandidateRepairs
                        ),
                        systemImage: "gauge.with.dots.needle.50percent"
                    )
                    policyMetric(
                        preferences.text("trustContracts.risk"),
                        value: preferences.statusText(policy.risk.profile),
                        systemImage: "shield.lefthalf.filled"
                    )
                }

                HStack(spacing: 8) {
                    Label(
                        localizedPolicy(policy.sandbox.filesystemPolicy),
                        systemImage: "folder.badge.gearshape"
                    )
                    Label(
                        localizedPolicy(policy.sandbox.networkPolicy),
                        systemImage: "network.slash"
                    )
                    Spacer()
                    Label(
                        preferences.text(policy.approval.required
                            ? "trustContracts.approvalRequired"
                            : "trustContracts.noApprovalRequired"),
                        systemImage: policy.approval.required ? "hand.raised" : "checkmark.circle"
                    )
                }
                .font(.system(size: 10, weight: .medium))
                .foregroundStyle(.secondary)
            }
        }
    }

    private var attemptCard: some View {
        contractCard(
            title: preferences.text("trustContracts.attempt"),
            systemImage: "arrow.left.arrow.right",
            status: viewModel.attemptLens == nil ? "not_run" : "ready"
        ) {
            if let lens = viewModel.attemptLens {
                AcrossAttemptLensView(lens: lens, preferences: preferences)
            } else {
                Label(preferences.text("trustContracts.attempt.none"), systemImage: "minus.circle")
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder
    private var replayCard: some View {
        if let replay = viewModel.replayPlan {
            contractCard(
                title: preferences.text("trustContracts.replay"),
                systemImage: "arrow.counterclockwise.circle",
                status: replay.status
            ) {
                HStack(spacing: 14) {
                    trustState(
                        preferences.text("trustContracts.replay.mode"),
                        value: localizedPolicy(replay.mode),
                        passed: replay.mode == "simulation"
                    )
                    trustState(
                        preferences.text("trustContracts.replay.auto"),
                        value: replay.execution.automaticExecutionAllowed
                            ? preferences.text("system.yes")
                            : preferences.text("system.no"),
                        passed: !replay.execution.automaticExecutionAllowed
                    )
                    trustState(
                        preferences.text("trustContracts.replay.sideEffects"),
                        value: replay.execution.sideEffectsRepeated
                            ? preferences.text("system.yes")
                            : preferences.text("system.no"),
                        passed: !replay.execution.sideEffectsRepeated
                    )
                    Spacer(minLength: 0)
                }
                if replay.renewedApproval.required && !replay.renewedApproval.verified {
                    Label(
                        preferences.text("trustContracts.replay.renewedApproval"),
                        systemImage: "hand.raised.fill"
                    )
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(StatusPalette.tone(for: "attention").foreground)
                }
            }
        }
    }

    private var receiptCard: some View {
        let chainStatus = viewModel.receiptChain?.chainIntegrityStatus ?? "not_run"
        return contractCard(
            title: preferences.text("trustContracts.receipts"),
            systemImage: "checkmark.seal",
            status: chainStatus
        ) {
            HStack {
                Label(
                    String(
                        format: preferences.text("trustContracts.receipts.count"),
                        viewModel.receiptChain?.total ?? 0
                    ),
                    systemImage: chainStatus == "verified" ? "link.circle.fill" : "link.badge.plus"
                )
                .font(.system(size: 10, weight: .medium))
                Spacer()
                Text(preferences.statusText(chainStatus))
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(StatusPalette.tone(for: chainStatus).foreground)
            }

            if let mark = viewModel.decisionMark(for: task) {
                AcrossDecisionMarkView(mark: mark, preferences: preferences)
            } else {
                Label(preferences.text("trustContracts.receipts.none"), systemImage: "minus.circle")
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func contractCard<Content: View>(
        title: String,
        systemImage: String,
        status: String,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label(title, systemImage: systemImage)
                    .font(.system(size: 12, weight: .semibold))
                Spacer()
                Image(systemName: StatusPalette.systemImage(for: status))
                    .foregroundStyle(StatusPalette.tone(for: status).foreground)
                    .accessibilityHidden(true)
            }
            content()
        }
        .padding(11)
        .background(AcrossTheme.panelFill(for: colorScheme))
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        .accessibilityElement(children: .contain)
        .accessibilityLabel(title)
        .accessibilityValue(preferences.statusText(status))
    }

    private func policyMetric(_ title: String, value: String, systemImage: String) -> some View {
        HStack(spacing: 8) {
            Image(systemName: systemImage)
                .foregroundStyle(AcrossTheme.accent)
                .frame(width: 18)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 1) {
                Text(title)
                    .font(.system(size: 9))
                    .foregroundStyle(.secondary)
                Text(value)
                    .font(.system(size: 11, weight: .semibold))
                    .lineLimit(1)
            }
            Spacer(minLength: 0)
        }
        .padding(8)
        .background(AcrossTheme.recessedFill(for: colorScheme))
        .clipShape(RoundedRectangle(cornerRadius: 7, style: .continuous))
        .accessibilityElement(children: .combine)
    }

    private func trustState(_ title: String, value: String, passed: Bool) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(.system(size: 9))
                .foregroundStyle(.secondary)
            Label(value, systemImage: passed ? "checkmark.circle.fill" : "exclamationmark.circle.fill")
                .font(.system(size: 10, weight: .semibold))
                .foregroundStyle(StatusPalette.tone(for: passed ? "passed" : "attention").foreground)
        }
        .accessibilityElement(children: .combine)
    }

    private func localizedPolicy(_ value: String) -> String {
        let key = "trustContracts.policyValue.\(value)"
        let localized = preferences.text(key)
        return localized == key ? value.replacingOccurrences(of: "_", with: " ") : localized
    }
}

private extension String {
    var nilIfEmpty: String? { isEmpty ? nil : self }
}
