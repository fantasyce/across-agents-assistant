import SwiftUI

struct MainPanelView: View {
    @ObservedObject var viewModel: SessionViewModel
    @Environment(\.colorScheme) var colorScheme

    var bgColor: Color { AcrossTheme.canvasFill(for: colorScheme) }
    var sidebarBgColor: Color { AcrossTheme.sidebarFill(for: colorScheme) }
    var textColor: Color { .primary }
    var accentColor: Color { AcrossTheme.accent }
    var userMsgBgColor: Color { AcrossTheme.selectedFill(for: colorScheme) }
    var userMsgTextColor: Color { .primary }
    var agentMsgTextColor: Color { .primary }

    // State for interactive buttons
    @State var selectedOperationsSurface: OperationsWorkbenchSurface = .assist
    @State var activeSettingsHubTab: SettingsHubTab? = nil
    @State var showTaskOrchestration = false
    @State var showsSelectedTaskDetails = false
    @State var showsContextDrawer = false
    @State var autopilotEvidenceTarget: AutopilotEvidenceTarget?
    @StateObject var taskOrchestrationViewModel = TaskOrchestrationViewModel()
    @StateObject var workspaceOperationsViewModel = AgentWorkspaceOperationsViewModel()
    @StateObject var qualityGateViewModel = QualityGateViewModel()
    @StateObject var memorySearchViewModel = MemorySearchViewModel()
    @StateObject var pluginLifecycleViewModel = PluginLifecycleViewModel()
    @StateObject var beginnerMissionViewModel = BeginnerMissionViewModel()
    @StateObject var speechInput = SpeechInputCoordinator()
    @StateObject var productCapabilityStore = AcrossProductCapabilityStore.shared
    @StateObject var learningProgressStore = AcrossLearningProgressStore.shared
    @StateObject var mcpPluginManager = MCPPluginManager.shared
    @ObservedObject var repositoryStore = SecurityScopedRepositoryStore.shared
    @EnvironmentObject var settingsViewModel: SettingsViewModel
    @EnvironmentObject var appPreferences: AppPreferences
    @State var showProjectTree: Bool = false
    @State var selectedSessionIds: Set<String> = []
    @State var renamingSessionId: String? = nil
    @State var renameText: String = ""
    @State var inputResignResponder = false
    @AppStorage("sidebarWidth", store: AppUserDefaults.current) var sidebarWidth: Double = 250
    @State var dragStartWidth: Double = 0
    @State var scrollAnchorId: String? = nil
    @State var mcpPollingTimer: Timer? = nil
    @State var isNewProjectMenuHovered = false
    @State var windowContentWidth: CGFloat = 1280

    var windowLayoutSize: AcrossWindowLayoutSize {
        windowContentWidth >= 1400 ? .expanded : .regular
    }

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

    var canUseBeginnerMissionInput: Bool {
        appPreferences.automaticDeliveryProtection
            && productProgress.isUnlocked(.selfIteration)
            && operationalProjectPath != nil
            && taskOrchestrationViewModel.selectedTask == nil
            && !taskOrchestrationViewModel.isLoading
    }

    var canEditWorkInput: Bool {
        canUseAgentFeatures || canUseBeginnerMissionInput
    }

    var shouldUseInputForBeginnerMission: Bool {
        canUseBeginnerMissionInput
            && taskOrchestrationViewModel.tasks.isEmpty
            && beginnerMissionViewModel.result == nil
    }

    var taskEntryDisabled: Bool {
        !canUseAgentFeatures
    }

    var operationalProjectPath: String? {
        repositoryStore.selectedPath ?? viewModel.activeProjectPath
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
            if productProgress.isUnlocked(.selfIteration) {
                if let projectName = viewModel.activeProjectName {
                    return String(format: appPreferences.text("work.placeholder.project"), projectName)
                }
                return appPreferences.text("work.placeholder.selectProject")
            }
            return appPreferences.text("chat.placeholder.noAgent")
        case .ready:
            if let projectName = viewModel.activeProjectName {
                return String(format: appPreferences.text("work.placeholder.project"), projectName)
            }
            return appPreferences.text("work.placeholder.selectProject")
        }
    }

    var canSubmitInput: Bool {
        let hasText = !viewModel.inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        return (hasText || !viewModel.attachedFiles.isEmpty)
            && viewModel.pendingApproval == nil
            && canEditWorkInput
            && !isProtectedTaskRunning
            && !beginnerMissionViewModel.isRunning
    }

    var isProtectedTaskRunning: Bool {
        guard appPreferences.automaticDeliveryProtection else { return false }
        if taskOrchestrationViewModel.isSubmittingTask { return true }
        guard let status = taskOrchestrationViewModel.selectedTask?.status else { return false }
        return !TaskOrchestrationStateReducers.isTerminalStatus(status)
    }

    var isViewingAcceptedTask: Bool {
        appPreferences.automaticDeliveryProtection
            && taskOrchestrationViewModel.selectedTask?.reviewStatus == "accepted"
    }

    var automaticDeliveryNeedsSetup: Bool {
        appPreferences.automaticDeliveryProtection
            && canUseAgentFeatures
            && taskOrchestrationViewModel.isOrchestratorPluginUnavailable
    }

    var humanReviewSnapshot: HumanReviewQueueSnapshot {
        HumanReviewQueueSnapshot(signals: humanReviewSignals)
    }

    var productProgress: AcrossProductProgressSnapshot {
        AcrossProductCapabilityRegistry.snapshot(
            plugins: productCapabilityStore.plugins,
            hasAvailableAgent: settingsViewModel.hasAnyAvailableAgents,
            learningEvents: learningProgressStore.events
        )
    }

    var taskLearningEventSignature: [String] {
        AcrossLearningProgressEngine.taskEvents(from: taskOrchestrationViewModel.tasks)
            .map(\.eventID)
            .sorted()
    }

    func recomputeTaskLearningProgress() {
        learningProgressStore.recompute(
            taskEvents: AcrossLearningProgressEngine.taskEvents(from: taskOrchestrationViewModel.tasks)
        )
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

        let pendingMemories = pluginLifecycleViewModel.memories.filter { $0.status == "pending" }
        if !pendingMemories.isEmpty {
            signals.append(
                HumanReviewSignal(
                    id: "memory-review-batch",
                    kind: .pendingMemory,
                    title: appPreferences.text("review.memory.batch.title"),
                    detail: String(
                        format: appPreferences.text("review.memory.batch.detail"),
                        pendingMemories.count
                    ),
                    status: "pending",
                    source: "Context"
                )
            )
        }

        return signals
    }

    private var panelLayout: some View {
        HStack(spacing: 0) {
            leftSidebar
            centerResizer
            centerArea
            if selectedOperationsSurface == .assist
                && !appPreferences.automaticDeliveryProtection
                && settingsViewModel.shouldShowRightSidebar
            {
                rightResizer
                rightSidebar
            }
        }
        .frame(minWidth: 1024, idealWidth: 1280, minHeight: 640, idealHeight: 800)
        .environment(\.acrossWindowLayoutSize, windowLayoutSize)
        .background(bgColor.ignoresSafeArea())
        .background {
            GeometryReader { proxy in
                Color.clear
                    .onAppear { windowContentWidth = proxy.size.width }
                    .onChange(of: proxy.size.width) { _, newWidth in
                        windowContentWidth = newWidth
                    }
            }
        }
        .overlay(alignment: .topLeading) {
            HStack(spacing: 0) {
                Color.clear
                    .frame(width: CGFloat(min(max(sidebarWidth, 220), 320)), height: 30)
                    .allowsHitTesting(false)
                WindowDragView()
                    .frame(maxWidth: .infinity)
                    .frame(height: 30)
            }
        }
        .ignoresSafeArea(.all, edges: .top)
    }

    private var synchronizedPanel: some View {
        panelLayout
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
            async let lifecycleLoad: Void = pluginLifecycleViewModel.loadForProductShell()
            taskOrchestrationViewModel.updateProjectDirectoryFilter(
                viewModel.activeProjectPath,
                reload: false
            )
            taskOrchestrationViewModel.loadTasks()
            _ = await lifecycleLoad
        }
        .onDisappear {
            mcpPollingTimer?.invalidate()
            if speechInput.state.isActive {
                speechInput.cancel(preservingDraft: viewModel.inputText)
            }
        }
        .onChange(of: settingsViewModel.visibleAgentIds) {
            syncSelectedAgentToAvailability()
        }
        .onChange(of: selectedOperationsSurface) {
            showsContextDrawer = false
            if selectedOperationsSurface != .autopilot {
                autopilotEvidenceTarget = nil
            }
            if selectedOperationsSurface != .assist, speechInput.state.isActive {
                speechInput.cancel(preservingDraft: viewModel.inputText)
            }
        }
        .onChange(of: viewModel.activeProjectPath) { _, projectPath in
            beginnerMissionViewModel.resetIfProjectChanged(to: projectPath)
            taskOrchestrationViewModel.updateProjectDirectoryFilter(projectPath)
        }
        .onChange(of: taskOrchestrationViewModel.selectedTask?.projectDir) { _, projectPath in
            guard let projectPath else { return }
            _ = viewModel.activateProject(matchingDirectory: projectPath)
        }
        .onChange(of: taskLearningEventSignature) {
            recomputeTaskLearningProgress()
        }
    }

    private var observedPanel: some View {
        synchronizedPanel
        .onChange(of: humanReviewSnapshot.totalCount) {
            if humanReviewSnapshot.totalCount == 0, selectedOperationsSurface == .humanReview {
                selectedOperationsSurface = .assist
            }
        }
        .onChange(of: productProgress.unlockedSurfaces) {
            let allowed = Set([OperationsWorkbenchSurface.assist, .humanReview] + productProgress.unlockedSurfaces)
            if !allowed.contains(selectedOperationsSurface) {
                selectedOperationsSurface = .assist
            }
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
        .onChange(of: speechInput.draftText) { _, draft in
            guard let draft, viewModel.inputText != draft else { return }
            viewModel.inputText = draft
        }
        .onChange(of: speechInput.state) { _, state in
            guard case .segmentTranscript = state else { return }
            learningProgressStore.record([
                AcrossLearningEvent(
                    kind: .voiceDraft,
                    sourceID: "session:\(viewModel.currentSessionId)"
                )
            ])
        }
        .onChange(of: viewModel.inputText) { _, draft in
            speechInput.userEditedDraft(draft)
        }
    }

    var body: some View {
        observedPanel
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
        .accessibilityHidden(activeSettingsHubTab != nil || showTaskOrchestration)
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
