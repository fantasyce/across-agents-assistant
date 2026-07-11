import SwiftUI

struct MainPanelView: View {
    @ObservedObject var viewModel: SessionViewModel
    @Environment(\.colorScheme) var colorScheme

    // Dynamic color helpers based on color scheme
    var bgColor: Color { colorScheme == .dark ? .legacyBgDark : .legacyBgLight }
    var sidebarBgColor: Color { bgColor }
    var textColor: Color { colorScheme == .dark ? .legacyTextDark : .legacyTextLight }
    var accentColor: Color { colorScheme == .dark ? .legacyAccentDark : .legacyAccentLight }
    var userMsgBgColor: Color { colorScheme == .dark ? .legacyUserMsgBgDark : .legacyUserMsgBgLight }
    var userMsgTextColor: Color { colorScheme == .dark ? .white : .black }
    var agentMsgTextColor: Color { colorScheme == .dark ? .white : .black }

    // State for interactive buttons
    @State var isContinuousMode = false
    @State var selectedOperationsSurface: OperationsWorkbenchSurface = .workspaces
    @State var activeSettingsHubTab: SettingsHubTab? = nil
    @State var showTaskOrchestration = false
    @StateObject var taskOrchestrationViewModel = TaskOrchestrationViewModel()
    @StateObject var workspaceOperationsViewModel = AgentWorkspaceOperationsViewModel()
    @StateObject var qualityGateViewModel = QualityGateViewModel()
    @StateObject var memorySearchViewModel = MemorySearchViewModel()
    @StateObject var pluginLifecycleViewModel = PluginLifecycleViewModel()
    @StateObject var mcpPluginManager = MCPPluginManager.shared
    @EnvironmentObject var settingsViewModel: SettingsViewModel
    @EnvironmentObject var appPreferences: AppPreferences
    @State var showProjectTree: Bool = false
    @State var selectedSessionIds: Set<String> = []
    @State var renamingSessionId: String? = nil
    @State var renameText: String = ""
    @State var inputResignResponder = false
    @AppStorage("sidebarWidth") var sidebarWidth: Double = 250
    @State var dragStartWidth: Double = 0
    @State var scrollAnchorId: String? = nil
    @State var mcpPollingTimer: Timer? = nil
    @State var isNewProjectMenuHovered = false

    var visibleLocalAgents: [AgentModel] {
        let ids = Set(settingsViewModel.availableLocalAgents.map(\.id))
        return viewModel.agents.filter { $0.type == .local && ids.contains($0.id) }
    }

    var visibleCloudAgents: [AgentModel] {
        let ids = Set(settingsViewModel.availableCloudLLMs.map(\.id))
        return viewModel.agents.filter { $0.type == .cloudLLM && ids.contains($0.id) }
    }

    var visibleAgentsForSelection: [AgentModel] {
        visibleLocalAgents + visibleCloudAgents
    }

    var canUseAgentFeatures: Bool {
        settingsViewModel.availabilityBootstrapState == .ready && settingsViewModel.hasAnyAvailableAgents
    }

    var taskEntryDisabled: Bool {
        !canUseAgentFeatures
    }

    var currentAgentTitle: String {
        if settingsViewModel.availabilityBootstrapState == .loading {
            return appPreferences.text("chat.checkingAgents")
        }
        if !settingsViewModel.hasAnyAvailableAgents {
            return appPreferences.text("chat.configureModel")
        }
        if let agent = visibleAgentsForSelection.first(where: { $0.id == viewModel.selectedAgentId }) {
            return agent.name
        }
        return appPreferences.text("chat.assistant")
    }

    var inputPlaceholder: String {
        switch settingsViewModel.availabilityBootstrapState {
        case .loading:
            return appPreferences.text("chat.placeholder.checking")
        case .empty:
            return appPreferences.text("chat.placeholder.noAgent")
        case .ready:
            if let projectName = viewModel.activeProjectName {
                return String(format: appPreferences.text("chat.placeholder.project"), projectName)
            }
            return appPreferences.text("chat.placeholder.selectProject")
        }
    }

    var canSubmitInput: Bool {
        let hasText = !viewModel.inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        return (hasText || !viewModel.attachedFiles.isEmpty)
            && viewModel.pendingApproval == nil
            && canUseAgentFeatures
    }

    var humanReviewSnapshot: HumanReviewQueueSnapshot {
        HumanReviewQueueSnapshot(signals: humanReviewSignals)
    }

    var humanReviewSignals: [HumanReviewSignal] {
        var signals: [HumanReviewSignal] = []

        if let request = viewModel.pendingApproval {
            signals.append(
                HumanReviewSignal(
                    id: "permission-\(request.tool_call_id ?? request.tool_name)",
                    kind: .permission,
                    title: request.tool_name,
                    detail: request.description,
                    status: request.risk_level.isEmpty ? "pending" : request.risk_level,
                    source: "Assist"
                )
            )
        }

        if viewModel.showPermissionAlert {
            signals.append(
                HumanReviewSignal(
                    id: "permission-system-accessibility",
                    kind: .permission,
                    title: appPreferences.text("accessibility.title"),
                    detail: appPreferences.text("accessibility.message"),
                    status: "pending",
                    source: "System"
                )
            )
        }

        if let approval = pluginLifecycleViewModel.agentLoopHealth?.pendingApproval {
            signals.append(
                HumanReviewSignal(
                    id: "promotion-\(approval.actionId ?? approval.stepId ?? "pending")",
                    kind: .promotion,
                    title: approval.title ?? appPreferences.text("review.promotion.default"),
                    detail: approval.actionType ?? appPreferences.text("review.promotion.detail"),
                    status: approval.approvalStatus ?? "pending",
                    source: "Agent Loop"
                )
            )
        }

        for memory in pluginLifecycleViewModel.memories where memory.status == "pending" {
            signals.append(
                HumanReviewSignal(
                    id: "memory-\(memory.id)",
                    kind: .pendingMemory,
                    title: memory.projectName ?? appPreferences.text("review.memory.default"),
                    detail: memory.text,
                    status: memory.status,
                    source: "Context"
                )
            )
        }

        signals.append(contentsOf: workspaceOperationsViewModel.reviewSignals)
        signals.append(contentsOf: qualityGateViewModel.reviewSignals)

        if let evaluation = taskOrchestrationViewModel.releaseEvaluation {
            if !["ready", "passed", "success"].contains(StatusPalette.normalized(evaluation.releaseReadiness)) {
                signals.append(
                    HumanReviewSignal(
                        id: "promotion-release-readiness",
                        kind: .promotion,
                        title: appPreferences.text("review.releasePromotion"),
                        detail: evaluation.recommendation ?? appPreferences.text("review.releasePromotion.detail"),
                        status: evaluation.releaseReadiness,
                        source: "Quality Gate"
                    )
                )
            }

            for check in evaluation.readinessChecks {
                guard let kind = humanReviewKind(forGateStatus: check.status) else { continue }
                signals.append(
                    HumanReviewSignal(
                        id: "gate-\(check.id)",
                        kind: kind,
                        title: check.label,
                        detail: check.message,
                        status: check.status,
                        source: "Release Evaluation"
                    )
                )
            }
        }

        for plugin in pluginLifecycleViewModel.plugins
            where !plugin.installed || !plugin.available || StatusPalette.tone(for: plugin.status) == .danger
        {
            signals.append(
                HumanReviewSignal(
                    id: "plugin-\(plugin.pluginId)",
                    kind: .pluginRepair,
                    title: plugin.displayName,
                    detail: appPreferences.text("review.plugin.detail"),
                    status: plugin.status,
                    source: "Plugin Lifecycle"
                )
            )
        }

        return signals
    }

    var body: some View {
        HStack(spacing: 0) {
            leftSidebar
            centerResizer
            centerArea
            if selectedOperationsSurface == .assist && settingsViewModel.shouldShowRightSidebar {
                rightResizer
                rightSidebar
            }
        }
        .frame(minWidth: 900, idealWidth: 1200, minHeight: 600, idealHeight: 800)
        .background(bgColor.ignoresSafeArea())
        .ignoresSafeArea(.all, edges: .top)
        .onAppear {
            AppAppearanceController.apply(appPreferences.colorSchemeMode)
            _ = mcpPluginManager.plugins.count
            syncPreferencesToSessionViewModel()
            settingsViewModel.bootstrapFromPersistedSettings()
            loadInitialDataWhenBackendAvailable()
            mcpPollingTimer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { _ in
                viewModel.fetchMCPContexts()
            }
            syncSelectedAgentToAvailability()
        }
        .task {
            async let lifecycleLoad: Void = pluginLifecycleViewModel.load()
            taskOrchestrationViewModel.loadReleaseEvaluation()
            _ = await lifecycleLoad
        }
        .onDisappear {
            mcpPollingTimer?.invalidate()
        }
        .onChange(of: settingsViewModel.visibleAgentIds) {
            syncSelectedAgentToAvailability()
        }
        .onChange(of: settingsViewModel.availabilityBootstrapState) {
            syncSelectedAgentToAvailability()
            loadInitialDataWhenBackendAvailable()
        }
        .onChange(of: appPreferences.languageMode) { syncPreferencesToSessionViewModel() }
        .onChange(of: appPreferences.colorSchemeMode) { AppAppearanceController.apply(appPreferences.colorSchemeMode) }
        .onChange(of: appPreferences.voiceSource) { syncPreferencesToSessionViewModel() }
        .onChange(of: appPreferences.chosenVoiceIdentifier) { syncPreferencesToSessionViewModel() }
        .onChange(of: appPreferences.speechRate) { syncPreferencesToSessionViewModel() }
        .onChange(of: appPreferences.speechVolume) { syncPreferencesToSessionViewModel() }
        .onChange(of: appPreferences.autoReadReplies) { syncPreferencesToSessionViewModel() }
        .onChange(of: appPreferences.includeActiveAppContext) { syncPreferencesToSessionViewModel() }
        .onChange(of: appPreferences.rememberLastAgent) { syncPreferencesToSessionViewModel() }
        .background(OverlayCmdWInterceptor(isActive: activeSettingsHubTab != nil || showTaskOrchestration, onClose: {
            activeSettingsHubTab = nil
            showTaskOrchestration = false
        }))
        .transaction { transaction in
            if appPreferences.reduceMotion {
                transaction.disablesAnimations = true
                transaction.animation = nil
            }
        }
        .overlay(TrafficLightHider().frame(width: 0, height: 0).allowsHitTesting(false))
        .overlay(
            MainPanelOverlayHost(
                session: viewModel,
                taskOrchestration: taskOrchestrationViewModel,
                settings: settingsViewModel,
                preferences: appPreferences,
                settingsTab: activeSettingsHubTab,
                showsTaskOrchestration: showTaskOrchestration,
                activeProjectPath: viewModel.activeProjectPath,
                onCloseSettings: { activeSettingsHubTab = nil },
                onCloseTaskOrchestration: { showTaskOrchestration = false }
            )
        )
    }
}
