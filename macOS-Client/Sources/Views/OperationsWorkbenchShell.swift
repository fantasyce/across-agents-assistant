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
    let onStartWork: () -> Void
    let onOpenPluginCenter: () -> Void
    let onOpenModels: () -> Void

    var body: some View {
        switch selection {
        case .workspaces:
            MinimalProjectWorkspaceView(
                operations: workspaces,
                preferences: preferences,
                activeProjectPath: activeProjectPath,
                onOpenReviewQueue: { selection = .qualityGate }
            )
            .environmentObject(preferences)
        case .qualityGate:
            MinimalRunsOverviewView(
                viewModel: tasks,
                preferences: preferences,
                showsRunHistory: $showsContextDrawer,
                onStartWork: onStartWork
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
                onOpenPlugins: onOpenPluginCenter,
                onStartMission: { mission in
                    switch mission {
                    case .talk:
                        selection = .assist
                    case .memory:
                        selection = .memory
                    case .loop:
                        selection = .autopilot
                    case .verifiedTask, .evidence, .review, .workflow, .repair, .compare, .release:
                        selection = .qualityGate
                    }
                }
            )
        case .assist:
            EmptyView()
        }
    }
}
