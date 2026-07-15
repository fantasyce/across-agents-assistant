import SwiftUI

struct OperationsWorkbenchShell: View {
    @Binding var selection: OperationsWorkbenchSurface
    @Binding var showsContextDrawer: Bool
    @ObservedObject var workspaces: AgentWorkspaceOperationsViewModel
    @ObservedObject var qualityGate: QualityGateViewModel
    @ObservedObject var memorySearch: MemorySearchViewModel
    @ObservedObject var lifecycle: PluginLifecycleViewModel
    @ObservedObject var tasks: TaskOrchestrationViewModel
    @ObservedObject var settings: SettingsViewModel
    @ObservedObject var preferences: AppPreferences

    let autopilotEvidenceTarget: AutopilotEvidenceTarget?
    let activeProjectPath: String?
    let productProgress: AcrossProductProgressSnapshot
    let reviewSnapshot: HumanReviewQueueSnapshot
    let reviewIsLoading: Bool
    let reviewErrorMessage: String?
    let onOpenTaskOrchestration: () -> Void
    let onOpenPluginCenter: () -> Void
    let onOpenModels: () -> Void
    let onRefreshReviewQueue: () -> Void
    let onOpenReviewItem: (HumanReviewSignal) -> Void

    var body: some View {
        switch selection {
        case .workspaces:
            MinimalProjectWorkspaceView(
                operations: workspaces,
                preferences: preferences,
                activeProjectPath: activeProjectPath,
                onOpenReviewQueue: { selection = .humanReview }
            )
            .environmentObject(preferences)
        case .qualityGate:
            MinimalRunsOverviewView(
                viewModel: tasks,
                qualityGate: qualityGate,
                settingsViewModel: settings,
                preferences: preferences,
                showsRunHistory: $showsContextDrawer,
                defaultProjectPath: activeProjectPath,
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
                activeProjectPath: activeProjectPath
            )
        case .autopilot:
            AutopilotWorkbenchView(evidenceTarget: autopilotEvidenceTarget)
                .environmentObject(preferences)
        case .achievements:
            CapabilityProgressView(
                progress: productProgress,
                preferences: preferences,
                onOpenModels: onOpenModels,
                onOpenPlugins: onOpenPluginCenter
            )
        case .humanReview:
            MinimalReviewInboxView(
                snapshot: reviewSnapshot,
                pendingMemories: lifecycle.memories.filter { $0.status == "pending" },
                preferences: preferences,
                showsInbox: $showsContextDrawer,
                isLoading: reviewIsLoading,
                errorMessage: reviewErrorMessage,
                onRefresh: onRefreshReviewQueue,
                onOpen: onOpenReviewItem,
                onApproveMemories: { memories in
                    await lifecycle.updateMemories(memories, status: "active")
                },
                onArchiveMemories: { memories in
                    await lifecycle.updateMemories(memories, status: "archived")
                }
            )
        case .assist:
            EmptyView()
        }
    }
}
