import SwiftUI

struct OperationsWorkbenchShell: View {
    @Binding var selection: OperationsWorkbenchSurface
    @ObservedObject var workspaces: AgentWorkspaceOperationsViewModel
    @ObservedObject var qualityGate: QualityGateViewModel
    @ObservedObject var memorySearch: MemorySearchViewModel
    @ObservedObject var lifecycle: PluginLifecycleViewModel
    @ObservedObject var tasks: TaskOrchestrationViewModel
    @ObservedObject var preferences: AppPreferences

    let activeProjectPath: String?
    let reviewSnapshot: HumanReviewQueueSnapshot
    let reviewIsLoading: Bool
    let reviewErrorMessage: String?
    let onOpenTaskOrchestration: () -> Void
    let onOpenPluginCenter: () -> Void
    let onRefreshReviewQueue: () -> Void
    let onOpenReviewItem: (HumanReviewSignal) -> Void

    var body: some View {
        switch selection {
        case .workspaces:
            WorkspaceOperationsView(
                operations: workspaces,
                preferences: preferences,
                activeProjectPath: activeProjectPath,
                onOpenReviewQueue: { selection = .humanReview }
            )
            .environmentObject(preferences)
        case .qualityGate:
            QualityGateOperationsView(
                operations: qualityGate,
                preferences: preferences,
                activeProjectPath: activeProjectPath,
                onOpenFullWorkflow: onOpenTaskOrchestration,
                onOpenReviewQueue: { selection = .humanReview }
            )
        case .evidence:
            EvidenceOperationsView(
                lifecycle: lifecycle,
                tasks: tasks,
                preferences: preferences,
                onOpenFullEvidence: onOpenPluginCenter
            )
        case .memory:
            MemoryOperationsView(
                search: memorySearch,
                lifecycle: lifecycle,
                preferences: preferences,
                activeProjectPath: activeProjectPath,
                onOpenFullMemory: onOpenPluginCenter
            )
        case .humanReview:
            HumanReviewQueueView(
                snapshot: reviewSnapshot,
                preferences: preferences,
                isLoading: reviewIsLoading,
                errorMessage: reviewErrorMessage,
                onRefresh: onRefreshReviewQueue,
                onOpen: onOpenReviewItem
            )
        case .assist:
            EmptyView()
        }
    }
}
