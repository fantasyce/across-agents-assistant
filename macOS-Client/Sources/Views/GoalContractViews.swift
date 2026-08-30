import SwiftUI

struct GoalContractSummaryView: View {
    @ObservedObject var viewModel: TaskOrchestrationViewModel
    let taskId: String

    @EnvironmentObject private var appPreferences: AppPreferences
    @State private var showsScope = false
    @State private var showsCoverage = true
    @State private var showsDecisions = true
    @State private var showsInvalidations = false
    @State private var selectedOperationIndexes: Set<Int> = []
    @State private var pendingDecision: PendingGoalDecision?
    @State private var pendingRevalidation = false
    @State private var pendingCriterionReview: PendingCriterionReview?

    private let acceptAllAccessibilityLabel = "Accept all changes"
    private let acceptSelectedAccessibilityLabel = "Accept selected changes"
    private let rejectAccessibilityLabel = "Reject changes"
    private let revalidateAccessibilityLabel = "Revalidate stale evidence"
    private let replacementAttemptAccessibilityLabel = "Create replacement Attempt"

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            switch viewModel.goalTaskState {
            case .loading:
                stateLine(icon: "arrow.triangle.2.circlepath", text: appPreferences.text("tasks.goal.loading")) {
                    ProgressView().controlSize(.small)
                }
            case .legacyEmpty:
                stateLine(icon: "clock.arrow.circlepath", text: appPreferences.text("tasks.goal.legacy"))
            case .error(let message):
                stateLine(icon: "exclamationmark.triangle", text: message)
            case .active:
                if let envelope = viewModel.selectedGoalContract {
                    contractContent(envelope)
                }
            case .stale:
                if let envelope = viewModel.selectedGoalContract {
                    contractContent(envelope)
                }
            case .decisionRequired:
                if let envelope = viewModel.selectedGoalContract {
                    contractContent(envelope)
                }
            case .completed:
                if let envelope = viewModel.selectedGoalContract {
                    contractContent(envelope)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .confirmationDialog(
            appPreferences.text("tasks.goal.confirmDecision"),
            isPresented: Binding(
                get: { pendingDecision != nil },
                set: { if !$0 { pendingDecision = nil } }
            ),
            titleVisibility: .visible
        ) {
            Button(appPreferences.text("tasks.goal.confirmDecision")) { submitPendingDecision() }
            Button(appPreferences.text("tasks.goal.cancel"), role: .cancel) { pendingDecision = nil }
        }
        .confirmationDialog(
            revalidationConfirmationTitle,
            isPresented: $pendingRevalidation,
            titleVisibility: .visible
        ) {
            Button(revalidationActionTitle) { submitRevalidation() }
            Button(appPreferences.text("tasks.goal.cancel"), role: .cancel) { pendingRevalidation = false }
        }
        .confirmationDialog(
            appPreferences.text("tasks.goal.confirmCriterionReview"),
            isPresented: Binding(
                get: { pendingCriterionReview != nil },
                set: { if !$0 { pendingCriterionReview = nil } }
            ),
            titleVisibility: .visible
        ) {
            Button(appPreferences.text("tasks.goal.confirmCriterionReview")) { submitCriterionReview() }
            Button(appPreferences.text("tasks.goal.cancel"), role: .cancel) { pendingCriterionReview = nil }
        }
    }

    @ViewBuilder
    private func stateLine<Trailing: View>(
        icon: String,
        text: String,
        @ViewBuilder trailing: () -> Trailing = { EmptyView() }
    ) -> some View {
        HStack(alignment: .center, spacing: 9) {
            Image(systemName: icon)
                .foregroundStyle(.secondary)
                .accessibilityHidden(true)
            Text(text)
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
            Spacer(minLength: 8)
            trailing()
        }
        .accessibilityElement(children: .combine)
    }

    private func contractContent(_ envelope: GoalContractEnvelope) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 16) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(appPreferences.text("tasks.goal.outcome"))
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(.secondary)
                    Text(envelope.contract.successOutcome)
                        .font(.system(size: 14, weight: .semibold))
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 12)
                summaryValue(appPreferences.text("tasks.goal.criteria"), "\(satisfiedCount(envelope))/\(envelope.projection.criterionCoverage.count)")
                summaryValue(appPreferences.text("tasks.goal.revision"), "r\(envelope.contract.revision)")
            }

            HStack(spacing: 8) {
                MinimalWorkflowStatusLabel(
                    status: statusName,
                    label: appPreferences.statusText(envelope.projection.displayState.rawValue)
                )
                Text("\(appPreferences.text("tasks.goal.blocker")): \(primaryBlocker(envelope))")
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                Spacer(minLength: 8)
                if envelope.needsReplacementAttempt,
                   envelope.availableAction("revalidate")?.enabled == true {
                    Button(appPreferences.text("tasks.goal.repairAttempt")) {
                        pendingRevalidation = true
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                    .accessibilityLabel(replacementAttemptAccessibilityLabel)
                }
            }

            if case .completed = viewModel.goalTaskState {
                Label(appPreferences.text("tasks.goal.completed"), systemImage: "checkmark.circle.fill")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(StatusPalette.tone(for: "success").foreground)
            }

            MinimalDisclosureSection(
                title: appPreferences.text("tasks.goal.scope"),
                detail: "\(envelope.contract.scope.includes.count) / \(envelope.contract.scope.excludes.count)",
                isExpanded: $showsScope
            ) {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(envelope.contract.scope.includes, id: \.self) { value in
                        Label(value, systemImage: "plus")
                    }
                    ForEach(envelope.contract.scope.excludes, id: \.self) { value in
                        Label(value, systemImage: "minus")
                    }
                }
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
            }

            MinimalDisclosureSection(
                title: appPreferences.text("tasks.goal.coverage"),
                detail: "\(satisfiedCount(envelope))/\(envelope.projection.criterionCoverage.count)",
                isExpanded: $showsCoverage
            ) {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(envelope.projection.criterionCoverage) { coverage in
                        criterionRow(coverage, contract: envelope.contract)
                        if coverage.id != envelope.projection.criterionCoverage.last?.id { Divider() }
                    }
                }
            }

            MinimalDisclosureSection(
                title: appPreferences.text("tasks.goal.decisions"),
                detail: "\(envelope.pendingProposals.count)",
                isExpanded: $showsDecisions
            ) {
                if envelope.pendingProposals.isEmpty {
                    Text(appPreferences.text("tasks.goal.emptyDecisions"))
                        .font(.system(size: 11))
                        .foregroundStyle(.secondary)
                } else {
                    VStack(alignment: .leading, spacing: 12) {
                        ForEach(envelope.pendingProposals) { proposal in
                            proposalView(proposal, revision: envelope.contract.revision)
                        }
                    }
                }
            }

            MinimalDisclosureSection(
                title: appPreferences.text("tasks.goal.invalidations"),
                detail: "\(envelope.invalidations.count)",
                isExpanded: $showsInvalidations
            ) {
                VStack(alignment: .leading, spacing: 8) {
                    if envelope.invalidations.isEmpty {
                        Text(appPreferences.text("tasks.goal.emptyInvalidations"))
                            .font(.system(size: 11))
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(envelope.invalidations) { invalidation in
                            VStack(alignment: .leading, spacing: 3) {
                                Text(invalidation.reason).font(.system(size: 11, weight: .medium))
                                Text(invalidation.criterionIds.joined(separator: ", "))
                                    .font(.system(size: 10))
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                    if !envelope.needsReplacementAttempt,
                       envelope.availableAction("revalidate")?.enabled == true {
                        Button(appPreferences.text("tasks.goal.revalidate")) { pendingRevalidation = true }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                            .accessibilityLabel(revalidateAccessibilityLabel)
                    }
                }
            }
        }
    }

    private func summaryValue(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title).font(.system(size: 10, weight: .semibold)).foregroundStyle(.secondary)
            Text(value).font(.system(size: 12, weight: .semibold))
        }
    }

    private func criterionRow(_ coverage: GoalCriterionCoverage, contract: GoalContract) -> some View {
        let criterion = contract.acceptanceCriteria.first { $0.criterionId == coverage.criterionId }
        return HStack(alignment: .top, spacing: 9) {
            Image(systemName: coverage.satisfied ? "checkmark.circle.fill" : "circle.dashed")
                .foregroundStyle(StatusPalette.tone(for: coverage.satisfied ? "success" : coverage.evidenceState.rawValue).foreground)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 3) {
                Text(criterion?.description ?? coverage.criterionId).font(.system(size: 11, weight: .medium))
                Text("\(appPreferences.statusText(coverage.evidenceState.rawValue)) · \(appPreferences.statusText(coverage.reviewState.rawValue))")
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
            }
            .accessibilityElement(children: .combine)
            Spacer(minLength: 8)
            if let criterion, criterion.reviewPolicy != "automatic", coverage.evidenceState.rawValue == "verified" {
                HStack(spacing: 6) {
                    Button(appPreferences.text("tasks.goal.reviewReject"), role: .destructive) {
                        pendingCriterionReview = PendingCriterionReview(
                            criterionId: coverage.criterionId,
                            decision: "rejected",
                            revision: contract.revision
                        )
                    }
                    .accessibilityLabel("Reject criterion review")
                    Button(
                        appPreferences.text(
                            coverage.reviewState.rawValue == "rejected"
                                ? "tasks.goal.reviewPassAfterFix"
                                : "tasks.goal.reviewPass"
                        )
                    ) {
                        pendingCriterionReview = PendingCriterionReview(
                            criterionId: coverage.criterionId,
                            decision: "passed",
                            revision: contract.revision
                        )
                    }
                    .accessibilityLabel("Pass criterion review")
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            }
        }
        .padding(.vertical, 7)
        .accessibilityElement(children: .contain)
    }

    private func proposalView(_ proposal: GoalChangeProposal, revision: Int) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(proposal.reason).font(.system(size: 11, weight: .semibold))
            Text("\(proposal.proposedBy) · r\(proposal.baseGoalRevision)")
                .font(.system(size: 10))
                .foregroundStyle(.secondary)
            ForEach(Array(proposal.operations.enumerated()), id: \.offset) { index, operation in
                Toggle(isOn: operationSelection(index)) {
                    Text("\(operation.op.uppercased()) \(operation.path)")
                        .font(.system(size: 10))
                }
                .toggleStyle(.checkbox)
                .accessibilityLabel("Select change \(index + 1): \(operation.path)")
            }
            HStack(spacing: 8) {
                Button(appPreferences.text("tasks.goal.acceptAll")) {
                    pendingDecision = PendingGoalDecision(
                        proposalId: proposal.proposalId,
                        decision: "accepted",
                        operationIndexes: [],
                        revision: revision
                    )
                }
                .accessibilityLabel(acceptAllAccessibilityLabel)

                Button(appPreferences.text("tasks.goal.acceptSelected")) {
                    pendingDecision = PendingGoalDecision(
                        proposalId: proposal.proposalId,
                        decision: "partially_accepted",
                        operationIndexes: selectedOperationIndexes.sorted(),
                        revision: revision
                    )
                }
                .disabled(selectedOperationIndexes.isEmpty || selectedOperationIndexes.count == proposal.operations.count)
                .accessibilityLabel(acceptSelectedAccessibilityLabel)

                Button(appPreferences.text("tasks.goal.reject"), role: .destructive) {
                    pendingDecision = PendingGoalDecision(
                        proposalId: proposal.proposalId,
                        decision: "rejected",
                        operationIndexes: [],
                        revision: revision
                    )
                }
                .accessibilityLabel(rejectAccessibilityLabel)
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
        }
    }

    private func operationSelection(_ index: Int) -> Binding<Bool> {
        Binding(
            get: { selectedOperationIndexes.contains(index) },
            set: { selected in
                if selected { selectedOperationIndexes.insert(index) }
                else { selectedOperationIndexes.remove(index) }
            }
        )
    }

    private func submitPendingDecision() {
        guard let decision = pendingDecision else { return }
        viewModel.decideGoalProposal(
            taskId: taskId,
            proposalId: decision.proposalId,
            decision: decision.decision,
            expectedRevision: decision.revision,
            operationIndexes: decision.operationIndexes,
            idempotencyKey: UUID().uuidString
        )
        pendingDecision = nil
        selectedOperationIndexes = []
    }

    private func submitRevalidation() {
        guard let envelope = viewModel.selectedGoalContract else { return }
        let criterionIds = envelope.revalidationCriterionIds
        guard !criterionIds.isEmpty else { return }
        viewModel.requestGoalRevalidation(
            taskId: taskId,
            expectedRevision: envelope.contract.revision,
            criterionIds: criterionIds,
            reason: envelope.needsReplacementAttempt
                ? "User requested a replacement Attempt after rejecting the current result"
                : "User requested revalidation of stale criterion evidence",
            idempotencyKey: UUID().uuidString
        )
        pendingRevalidation = false
    }

    private func submitCriterionReview() {
        guard let review = pendingCriterionReview else { return }
        viewModel.reviewGoalCriterion(
            taskId: taskId,
            expectedRevision: review.revision,
            criterionId: review.criterionId,
            decision: review.decision,
            reason: review.decision == "passed"
                ? "Human reviewer confirmed the corrected criterion now passes."
                : "Human reviewer rejected the criterion and requested a fix.",
            idempotencyKey: UUID().uuidString
        )
        pendingCriterionReview = nil
    }

    private var revalidationActionTitle: String {
        appPreferences.text(
            viewModel.selectedGoalContract?.needsReplacementAttempt == true
                ? "tasks.goal.repairAttempt"
                : "tasks.goal.revalidate"
        )
    }

    private var revalidationConfirmationTitle: String {
        appPreferences.text(
            viewModel.selectedGoalContract?.needsReplacementAttempt == true
                ? "tasks.goal.confirmRepairAttempt"
                : "tasks.goal.confirmRevalidation"
        )
    }

    private func satisfiedCount(_ envelope: GoalContractEnvelope) -> Int {
        envelope.projection.criterionCoverage.filter(\.satisfied).count
    }

    private func primaryBlocker(_ envelope: GoalContractEnvelope) -> String {
        guard let reason = envelope.projection.reasonCodes.first?.rawValue else {
            return appPreferences.statusText(envelope.projection.displayState.rawValue)
        }
        return appPreferences.statusText(reason)
    }

    private var statusName: String {
        switch viewModel.goalTaskState {
        case .completed: "success"
        case .stale, .decisionRequired: "attention"
        case .error: "failed"
        default: "active"
        }
    }
}

private struct PendingGoalDecision {
    let proposalId: String
    let decision: String
    let operationIndexes: [Int]
    let revision: Int
}

private struct PendingCriterionReview {
    let criterionId: String
    let decision: String
    let revision: Int
}
