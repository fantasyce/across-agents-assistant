import Foundation
import Testing
@testable import AcrossAgentsAssistantClient

struct AppleMinimalUIContractTests {
    private static let expectedMainNavigation = ["工作"]

    @Test @MainActor
    func mainNavigationKeepsOneWorkDestinationAndConditionalReview() throws {
        let visibleTitles = OperationsWorkbenchSurface.primary.map {
            AppPreferences.localizedString($0.localizationKey, localeIdentifier: "zh-Hans")
        }
        #expect(visibleTitles == Self.expectedMainNavigation)

        let sidebar = try Self.source("macOS-Client/Sources/Views/OperationsWorkbenchSidebar.swift")
        let visibleBody = sidebar.components(separatedBy: "private func sectionLabel").first ?? sidebar
        #expect(visibleBody.contains("ForEach(OperationsWorkbenchSurface.primary)"))
        #expect(visibleBody.contains("if reviewCount > 0"))
        #expect(visibleBody.contains("navigationRow(.humanReview"))
        #expect(!visibleBody.contains("secondaryRow("))
    }

    @Test
    func settingsNavigationIsFlatAndCombinesRelatedCapabilities() throws {
        let settings = try Self.source("macOS-Client/Sources/Views/SettingsHubView.swift")
        let categories = try #require(
            Self.slice(settings, from: "enum SettingsHubCategory", to: "var id: String")
        )
        let categoryCases = Self.enumCaseNames(in: categories)

        #expect(categoryCases == [
            "general",
            "agents",
            "capabilities",
            "plugins",
            "mcp",
            "tools",
            "diagnostics",
        ])
        #expect(!settings.contains("case advanced"))
        #expect(!settings.contains("case workbench"))
        #expect(settings.contains("ModelSettingsView"))
        #expect(settings.contains("AgentCapabilitiesView"))
        #expect(settings.contains("PluginLifecycleView"))
        #expect(settings.contains("MCPPreferencesView"))
        #expect(!settings.contains("PluginsAndMCPSettingsView"))
        #expect(!settings.contains("PluginsAndMCPSection"))
        #expect(settings.contains("ForEach(SettingsHubCategory.allCases)"))
        #expect(settings.contains("switch selectedCategory"))
        #expect(settings.contains("settingsNavigationRow(category)"))
        #expect(settings.contains(".background(.bar)"))
        #expect(settings.contains("AcrossTheme.selectedFill(for: colorScheme)"))
        #expect(!settings.contains("List(selection:"))

        let plugins = try Self.source("macOS-Client/Sources/Views/PluginLifecycleView.swift")
        let pluginBody = try #require(
            Self.slice(plugins, from: "var body: some View", to: "private var standaloneHeader")
        )
        #expect(!pluginBody.contains("memorySection"))
        #expect(plugins.contains("plugins.action.get"))
        #expect(plugins.contains("viewModel.runAction(\"install\", for: plugin)"))
        #expect(plugins.contains("viewModel.activePluginID == plugin.pluginId"))
        #expect(plugins.contains("ProgressView()"))
        #expect(plugins.contains(".accessibilityLabel(Text(title))"))
        #expect(plugins.contains(".accessibilityLabel(Text(appPreferences.text(\"settings.refresh\")))"))
        #expect(plugins.contains(".accessibilityLabel(Text(appPreferences.text(\"plugins.loop.probe\")))"))
        #expect(!plugins.contains(".filter { !$0.installed || !$0.available }"))
    }

    @Test
    func settingsAndWorkDetailsShareTheMainPageChrome() throws {
        let settings = try Self.source("macOS-Client/Sources/Views/SettingsHubView.swift")
        let settingsHeader = try Self.source("macOS-Client/Sources/Views/MinimalSettingsComponents.swift")
        let chat = try Self.source("macOS-Client/Sources/Views/MainPanelChat.swift")
        let work = try Self.source("macOS-Client/Sources/Views/UnifiedWorkView.swift")
        let assistHeaderCondition = try #require(
            Self.slice(chat, from: "private var shouldShowAssistHeader", to: "@ViewBuilder\n    var contentArea")
        )

        #expect(settings.contains("private var windowControls"))
        #expect(!settings.contains("private var header: some View"))
        #expect(settings.contains(".background(.bar)"))
        #expect(settings.contains("WindowDragView()"))
        #expect(settings.contains(".minimalPageContentFrame()"))
        #expect(settingsHeader.contains("windowLayoutSize == .expanded ? 32 : 28"))
        #expect(!assistHeaderCondition.contains("selectedTask"))
        #expect(work.contains("MinimalPageHeader(title: headline, subtitle: subheadline)"))
        #expect(work.contains("systemName: \"chevron.left\""))
        #expect(work.contains("systemName: \"folder\""))
        #expect(work.contains("systemName: \"plus\""))

        for path in [
            "macOS-Client/Sources/Views/ModelSettingsView.swift",
            "macOS-Client/Sources/Views/PluginLifecycleView.swift",
            "macOS-Client/Sources/Views/MCPPreferencesView.swift",
            "macOS-Client/Sources/Views/AgentCapabilitiesView.swift",
            "macOS-Client/Sources/Views/ToolPermissionsView.swift",
            "macOS-Client/Sources/Views/StartupDiagnosticsView.swift",
        ] {
            #expect(try Self.source(path).contains(".minimalPageContentFrame()"))
        }
    }

    @Test
    func sidebarsUseSpacingInsteadOfHorizontalSectionRules() throws {
        let sidebar = try Self.source("macOS-Client/Sources/Views/MainPanelSidebar.swift")
        let settings = try Self.source("macOS-Client/Sources/Views/SettingsHubView.swift")
        let mainSidebar = try #require(
            Self.slice(sidebar, from: "var leftSidebar: some View", to: "private var contextDrawerLabel")
        )
        let settingsShell = try #require(
            Self.slice(settings, from: "var body: some View", to: "private var windowControls")
        )

        #expect(!mainSidebar.contains("Divider()"))
        #expect(!settingsShell.contains("Divider()"))
        #expect(mainSidebar.contains("projectChatSidebar"))
        #expect(settingsShell.contains("navigationSidebar"))
    }

    @Test
    func selectedWorkTracksTheActiveProject() throws {
        let mainPanel = try Self.source("macOS-Client/Sources/Views/MainPanelView.swift")
        let sidebar = try Self.source("macOS-Client/Sources/Views/MainPanelSidebar.swift")
        let session = try Self.source("macOS-Client/Sources/ViewModels/SessionViewModel.swift")
        let tasks = try Self.source("macOS-Client/Sources/ViewModels/TaskOrchestrationViewModel.swift")

        #expect(mainPanel.contains("onChange(of: viewModel.activeProjectPath)"))
        #expect(mainPanel.contains("onChange(of: taskOrchestrationViewModel.selectedTask?.projectDir)"))
        #expect(sidebar.contains("updateProjectDirectoryFilter(project.path)"))
        #expect(session.contains("func activateProject(matchingDirectory directory: String?)"))
        #expect(tasks.contains("func updateProjectDirectoryFilter"))
        #expect(tasks.contains("enterWorkflowPicker()"))
        #expect(tasks.contains("URLQueryItem(name: \"project_dir\""))
    }

    @Test
    func primaryOperationalPagesShareAQuietHeaderAndBoundDenseCards() throws {
        let work = try Self.source("macOS-Client/Sources/Views/MainPanelChat.swift")
        let workflows = try Self.source("macOS-Client/Sources/Views/MinimalRunsOverviewView.swift")
        let memory = try Self.source("macOS-Client/Sources/Views/EvidenceMemoryOperationsViews.swift")
        let loop = try Self.source("macOS-Client/Sources/Views/AutopilotWorkbenchView.swift")
        let growth = try Self.source("macOS-Client/Sources/Views/CapabilityProgressView.swift")

        #expect(work.contains("if shouldShowAssistHeader"))
        #expect(work.contains("taskOrchestrationViewModel.selectedTask != nil"))
        #expect(workflows.contains("MinimalPageHeader("))
        #expect(!workflows.contains("subtitle: defaultProjectPath"))
        #expect(memory.contains("MinimalPageHeader("))
        #expect(memory.contains(".minimalPageContentFrame()"))
        #expect(!memory.contains("Picker(preferences.text(\"memory.scope\")"))
        #expect(!memory.contains("private var improveBar"))
        #expect(loop.contains("MinimalPageHeader("))
        #expect(loop.contains(".minimalPageContentFrame()"))
        #expect(loop.contains("@State private var showsTechnicalEvidence = false"))
        #expect(loop.contains("DisclosureGroup(isExpanded: $showsTechnicalEvidence)"))
        #expect(loop.contains("minHeight: 220, maxHeight: 220"))
        #expect(loop.contains(".truncationMode(.tail)"))
        #expect(!loop.contains("if let endpoint = action.endpoint"))
        #expect(!loop.contains("if let endpoint = section.endpoint"))
        #expect(workflows.contains(".minimalPageContentFrame(bottomPadding: 8)"))
        #expect(growth.contains("MinimalPageHeader("))
        #expect(growth.contains(".minimalPageContentFrame()"))
    }

    @Test
    func mainWindowUsesAnIntegratedDraggableTitleBar() throws {
        let app = try Self.source("macOS-Client/Sources/AcrossAgentsAssistantApp.swift")
        let mainPanel = try Self.source("macOS-Client/Sources/Views/MainPanelView.swift")
        let sidebar = try Self.source("macOS-Client/Sources/Views/MainPanelSidebar.swift")
        let toolbar = try Self.source("macOS-Client/Sources/Views/MainPanelToolbar.swift")
        let shared = try Self.source("macOS-Client/Sources/Views/SharedUIComponents.swift")

        #expect(app.contains(".windowStyle(.hiddenTitleBar)"))
        #expect(app.contains(".fullSizeContentView"))
        #expect(mainPanel.contains("TrafficLightHider()"))
        #expect(sidebar.contains("WindowDragView()") || toolbar.contains("WindowDragView()"))
        #expect(shared.contains("accessibilityDisplayShouldReduceMotion"))
        #expect(shared.contains("preferences.reduceMotion"))
        #expect(shared.contains("animate: shouldAnimate"))
    }

    @Test
    func mainWindowAndDetailPagesShareTheIntendedGeometry() throws {
        let app = try Self.source("macOS-Client/Sources/AcrossAgentsAssistantApp.swift")
        let mainPanel = try Self.source("macOS-Client/Sources/Views/MainPanelView.swift")
        let windowSupport = try Self.source("macOS-Client/Sources/Views/MainPanelWindowSupport.swift")
        let shared = try Self.source("macOS-Client/Sources/Views/SharedUIComponents.swift")
        let workflowComponents = try Self.source("macOS-Client/Sources/Views/MinimalWorkflowComponents.swift")
        let workflows = try Self.source("macOS-Client/Sources/Views/MinimalRunsOverviewView.swift")
        let work = try Self.source("macOS-Client/Sources/Views/UnifiedWorkView.swift")
        let simpleStart = try Self.source("macOS-Client/Sources/Views/TaskWorkflowStartViews.swift")

        #expect(app.contains("contentRect: NSRect(x: 0, y: 0, width: 1280, height: 800)"))
        #expect(app.contains(".defaultSize(width: 1280, height: 800)"))
        #expect(mainPanel.contains("idealWidth: 1280, minHeight: 640, idealHeight: 800"))
        #expect(windowSupport.contains("height: min(800, screenFrame.height)"))
        #expect(windowSupport.contains("isLegacyDefaultSize"))
        #expect(windowSupport.contains("abs(window.frame.height - 820) <= 2"))
        #expect(!app.contains("height: 820"))

        #expect(shared.contains("static let topContentPadding: CGFloat = 36"))
        #expect(workflowComponents.contains("topPadding: CGFloat = SettingsHubPageLayout.topContentPadding"))
        #expect(workflowComponents.contains("if let backLabel"))
        #expect(workflows.contains("backLabel: destination == .home ? nil"))
        #expect(workflows.contains(".minimalPageContentFrame(topPadding: 12)"))
        #expect(work.contains(".minimalPageContentFrame()"))
        #expect(!work.contains(".frame(maxWidth: 760"))
        #expect(simpleStart.contains(".minimalPageContentFrame(topPadding: 12)"))
    }

    @Test
    func workComposerExposesAnAccessibleLabelAndDoesNotTrapTabFocus() throws {
        let editor = try Self.source("macOS-Client/Sources/Views/MacEditorView.swift")
        let chat = try Self.source("macOS-Client/Sources/Views/MainPanelChat.swift")

        #expect(editor.contains("textView.setAccessibilityLabel(accessibilityLabel)"))
        #expect(editor.contains("event.keyCode == 48"))
        #expect(editor.contains("window?.selectNextKeyView(self)"))
        #expect(editor.contains("window?.selectPreviousKeyView(self)"))
        #expect(chat.contains("accessibilityLabel: inputPlaceholder"))
    }

    @Test
    func primaryNavigationAndComposerControlsJoinTheKeyboardFocusChain() throws {
        let navigation = try Self.source("macOS-Client/Sources/Views/OperationsWorkbenchSidebar.swift")
        let toolbar = try Self.source("macOS-Client/Sources/Views/MainPanelToolbarControls.swift")
        let assistant = try Self.source("macOS-Client/Sources/Views/MinimalAssistantComponents.swift")
        let composer = try Self.source("macOS-Client/Sources/Views/MainPanelChat.swift")

        #expect(navigation.contains(".focusable(true)"))
        #expect(navigation.contains(".focused($focusedSurface"))
        #expect(navigation.contains(".focusEffectDisabled()"))
        #expect(!toolbar.contains(".focusable(!isDisabled)"))
        #expect(assistant.contains("action: onToggleMute\n            )\n            .focusable(true)"))
        #expect(composer.contains(".toggleStyle(.checkbox)\n                        .focusable(true)"))
    }

    @Test
    func selectionUsesFillWithoutBlueFocusBorders() throws {
        let app = try Self.source("macOS-Client/Sources/AcrossAgentsAssistantApp.swift")
        let settings = try Self.source("macOS-Client/Sources/Views/SettingsHubView.swift")
        let navigation = try Self.source("macOS-Client/Sources/Views/OperationsWorkbenchSidebar.swift")
        let design = try Self.source("macOS-Client/Sources/Views/AcrossDesignSystem.swift")
        let agents = try Self.source("macOS-Client/Sources/Views/AgentIdentityComponents.swift")
        let tasks = try Self.source("macOS-Client/Sources/Views/TaskFormViews.swift")
        let plugins = try Self.source("macOS-Client/Sources/Views/PluginLifecycleView.swift")
        let diffReview = try Self.source("macOS-Client/Sources/Views/WorkspaceDiffReviewView.swift")
        let capabilities = try Self.source("macOS-Client/Sources/Views/AgentCapabilitiesView.swift")

        #expect(app.contains(".focusEffectDisabled()"))
        #expect(settings.contains(".focusEffectDisabled()"))
        #expect(settings.contains(".focused($focusedCategory"))
        #expect(navigation.contains(".focused($focusedSurface"))
        #expect(navigation.contains("AcrossTheme.hoverFill(for: colorScheme)"))
        #expect(!design.contains("focusRing(for"))
        #expect(!agents.contains(".stroke(isSelected ? AcrossTheme.accent"))
        #expect(!tasks.contains(".stroke(selectedDeliveryTaskTypes.contains(type) ? AcrossTheme.accent"))
        #expect(!plugins.contains(".stroke(isHighlighted ? accentColor"))
        #expect(!diffReview.contains(".stroke(AcrossTheme.accent"))
        #expect(!capabilities.contains(".stroke(accentColor"))
    }

    @Test
    func systemTrafficLightsAreHidden() throws {
        let source = try Self.source("macOS-Client/Sources/Views/MainPanelWindowSupport.swift")
        for button in ["closeButton", "miniaturizeButton", "zoomButton"] {
            #expect(
                source.contains("standardWindowButton(.\(button))?.isHidden = true"),
                "System \(button) must be hidden"
            )
        }
    }

    @Test
    func memoryBatchActionsExposeProgressAndSemanticColors() throws {
        let memory = try Self.source("macOS-Client/Sources/Views/EvidenceMemoryOperationsViews.swift")
        let review = try Self.source("macOS-Client/Sources/Views/MinimalReviewInboxView.swift")
        let lifecycle = try Self.source("macOS-Client/Sources/ViewModels/PluginLifecycleViewModel.swift")

        #expect(memory.contains("memoryBatchCompletedCount"))
        #expect(memory.contains("memory.bulk.archiving"))
        #expect(memory.contains(".tint(AcrossTheme.accent)"))
        #expect(memory.contains(".tint(.red)"))
        #expect(review.contains(".tint(.red)"))
        #expect(lifecycle.contains("memoryBatchTotalCount = memories.count"))
        #expect(lifecycle.contains("memoryBatchCompletedCount = index + 1"))
        #expect(lifecycle.contains("AcrossMemoryMutationResponse.self"))
    }

    @Test
    func customTrafficLightsExposeAllThreeWindowActions() throws {
        let source = try Self.source("macOS-Client/Sources/Views/SharedUIComponents.swift")
        let customTrafficLights = try #require(
            Self.slice(source, from: "struct CustomTrafficLights", to: "struct TrafficLightButton")
        )

        #expect(Self.occurrenceCount(of: "TrafficLightButton(", in: customTrafficLights) == 3)
        #expect(customTrafficLights.contains("iconName: \"xmark\""))
        #expect(customTrafficLights.contains("iconName: \"minus\""))
        #expect(customTrafficLights.contains("iconName: \"arrow.up.left.and.arrow.down.right\""))
        #expect(customTrafficLights.contains("WindowVisibilityController.closeMainWindow()"))
        #expect(customTrafficLights.contains("keyWindow?.miniaturize(nil)"))
        #expect(customTrafficLights.contains("keyWindow?.zoom(nil)"))
    }

    @Test
    func primaryPagesRejectDecorativeLegacyVisualsAndMetricCardWalls() throws {
        let forbiddenTokens = [
            "LinearGradient(",
            "RadialGradient(",
            "AngularGradient(",
            ".legacyAccent",
            ".legacyUserMsgBg",
            "#CBA6F0",
            "#B58AE3",
            "#EBE3F5",
            "#9B82C6",
            "MetricTile(",
        ]
        let shell = try Self.source("macOS-Client/Sources/Views/OperationsWorkbenchShell.swift")
        var primaryPageFiles = [
            "macOS-Client/Sources/Views/MainPanelView.swift",
            "macOS-Client/Sources/Views/MainPanelSidebar.swift",
            "macOS-Client/Sources/Views/MainPanelSidebarRows.swift",
            "macOS-Client/Sources/Views/MainPanelToolbar.swift",
            "macOS-Client/Sources/Views/OperationsWorkbenchSidebar.swift",
            "macOS-Client/Sources/Views/OperationsWorkbenchShell.swift",
            "macOS-Client/Sources/Views/HumanReviewQueueView.swift",
            "macOS-Client/Sources/Views/MainPanelChat.swift",
            "macOS-Client/Sources/Views/UnifiedWorkView.swift",
        ]
        let viewsDirectory = Self.repositoryRoot.appendingPathComponent("macOS-Client/Sources/Views")
        let minimalFiles = try FileManager.default.contentsOfDirectory(atPath: viewsDirectory.path)
            .filter { $0.hasPrefix("Minimal") && $0.hasSuffix(".swift") }
            .map { "macOS-Client/Sources/Views/\($0)" }
        primaryPageFiles += minimalFiles
        if shell.contains("WorkspaceOperationsView(") {
            primaryPageFiles += [
                "macOS-Client/Sources/Views/WorkspaceOperationsView.swift",
                "macOS-Client/Sources/Views/WorkspaceCandidatePanes.swift",
            ]
        }
        if shell.contains("QualityGateOperationsView(") {
            primaryPageFiles += [
                "macOS-Client/Sources/Views/QualityGateOperationsView.swift",
                "macOS-Client/Sources/Views/QualityGateResultView.swift",
            ]
        }

        var violations: [String] = []
        for file in primaryPageFiles {
            let source = try Self.source(file)
            for token in forbiddenTokens where source.contains(token) {
                violations.append("\(file): \(token)")
            }
        }

        #expect(violations.isEmpty, "Forbidden main UI visuals: \(violations.joined(separator: ", "))")
    }

    @Test
    func criticalInteractionsRemainTruthfulAndSourceAware() throws {
        let sidebar = try Self.source("macOS-Client/Sources/Views/MainPanelSidebar.swift")
        let actions = try Self.source("macOS-Client/Sources/Views/MainPanelActions.swift")
        let runs = try Self.source("macOS-Client/Sources/Views/MinimalRunsOverviewView.swift")
        let mainPanel = try Self.source("macOS-Client/Sources/Views/MainPanelView.swift")
        let chat = try Self.source("macOS-Client/Sources/Views/MainPanelChat.swift")
        let message = try Self.source("macOS-Client/Sources/Views/MainPanelChatMessage.swift")
        let app = try Self.source("macOS-Client/Sources/AcrossAgentsAssistantApp.swift")
        let taskDetail = try Self.source("macOS-Client/Sources/Views/TaskDetailViews.swift")
        let releaseCenter = try Self.source("macOS-Client/Sources/Views/TaskReleaseEvidenceViews.swift")
        let taskSidebar = try Self.source("macOS-Client/Sources/Views/TaskOrchestrationSidebar.swift")
        let simpleStart = try Self.source("macOS-Client/Sources/Views/TaskWorkflowStartViews.swift")
        let qualityGate = try Self.source("macOS-Client/Sources/Views/QualityGateOperationsView.swift")
        let workspaceViewModel = try Self.source("macOS-Client/Sources/ViewModels/AgentWorkspaceOperationsViewModel.swift")
        let project = try Self.source("macOS-Client/Sources/Views/MinimalProjectWorkspaceView.swift")
        let toolbar = try Self.source("macOS-Client/Sources/Views/MainPanelToolbar.swift")
        let unifiedWork = try Self.source("macOS-Client/Sources/Views/UnifiedWorkView.swift")
        let shell = try Self.source("macOS-Client/Sources/Views/OperationsWorkbenchShell.swift")
        let loop = try Self.source("macOS-Client/Sources/Views/AutopilotWorkbenchView.swift")
        let memory = try Self.source("macOS-Client/Sources/Views/EvidenceMemoryOperationsViews.swift")
        let review = try Self.source("macOS-Client/Sources/Views/MinimalReviewInboxView.swift")
        let protectedDelivery = try #require(
            Self.slice(chat, from: "private var protectedDeliveryContent", to: "private var unifiedWorkEmptyState")
        )

        #expect(sidebar.contains("onOpenSettings: { openSettings(.settings) }"))
        #expect(sidebar.contains("selectedOperationsSurface = .assist"))
        #expect(!sidebar.contains("if selectedOperationsSurface == .assist"))
        #expect(mainPanel.contains("memory-review-batch"))
        #expect(!actions.contains("case .pendingMemory:\n            openSettings(.plugins)"))
        #expect(actions.contains("submitProtectedTask"))
        #expect(actions.contains("taskTypes: [\"functional\", \"artifact\"]"))
        #expect(actions.contains("selectedOperationsSurface = .autopilot"))
        #expect(!actions.contains("openSettings(.workbench)"))
        #expect(runs.contains("showsReleaseE2EConfirmation = true"))
        #expect(runs.contains("RunDestination"))
        #expect(runs.contains("private var runOverview"))
        #expect(!runs.contains("runCenterTabs"))
        #expect(!runs.contains("pickerStyle(.segmented)"))
        #expect(!runs.contains("private var releaseMenu"))
        #expect(!runs.contains("showsQualityGate"))
        #expect(!simpleStart.contains("accentHex"))
        #expect(!simpleStart.contains("SimpleStartWorkflowCard"))
        #expect(runs.contains("@State private var showsInspector = false"))
        #expect(qualityGate.contains("@State private var showsAdvancedOptions = false"))
        #expect(qualityGate.contains("DisclosureGroup("))
        #expect(!workspaceViewModel.contains("workspace-readiness-"))
        #expect(project.contains("workspace.repositoryRequired.title"))
        #expect(project.contains("chooseRepository"))
        #expect(!mainPanel.contains("isContinuousMode"))
        #expect(!chat.contains("isContinuousMode"))
        #expect(toolbar.contains("work.back"))
        #expect(toolbar.contains("!appPreferences.automaticDeliveryProtection"))
        #expect(unifiedWork.contains("TaskDetailPanel("))
        #expect(!protectedDelivery.contains("showTaskOrchestration = true"))
        #expect(protectedDelivery.contains("acceptTaskResult"))
        #expect(chat.contains("AutopilotEvidenceTarget("))
        #expect(chat.contains("autopilotEvidenceTarget = target"))
        #expect(chat.contains("selectedOperationsSurface = .autopilot"))
        #expect(mainPanel.contains("if selectedOperationsSurface != .autopilot"))
        #expect(mainPanel.contains("autopilotEvidenceTarget = nil"))
        #expect(shell.contains("AutopilotWorkbenchView(evidenceTarget: autopilotEvidenceTarget)"))
        #expect(loop.contains(".task(id: evidenceTarget)"))
        #expect(loop.contains("await evidenceViewModel.load(target: evidenceTarget)"))
        #expect(loop.contains("@State private var showsFocusedEvidenceDetails = false"))
        let focusedDisclosure = loop.range(of: "DisclosureGroup(isExpanded: $showsFocusedEvidenceDetails)")
        let focusedRunID = loop.range(of: "Text(target.runID)")
        #expect(focusedDisclosure != nil)
        #expect(focusedRunID != nil)
        if let focusedDisclosure, let focusedRunID {
            #expect(focusedRunID.lowerBound > focusedDisclosure.lowerBound)
        }
        #expect(!shell.contains("onOpenAutopilotDetails"))
        #expect(shell.contains("status: \"active\""))
        #expect(!memory.contains("memory.openCenter"))
        #expect(memory.contains("librarySection"))
        #expect(memory.contains("memory.bulk.approve"))
        #expect(memory.contains("memory.bulk.archive"))
        #expect(memory.contains("AcrossReviewActionButtonStyle(kind: .approve)"))
        #expect(memory.contains("AcrossReviewActionButtonStyle(kind: .archive)"))
        #expect(review.contains("review.memory.approve.short"))
        #expect(review.contains("AcrossReviewActionButtonStyle(kind: .approve)"))
        #expect(review.contains("AcrossReviewActionButtonStyle(kind: .archive)"))
        #expect(review.contains("ProgressView()"))

        let models = try Self.source("macOS-Client/Sources/Views/ModelSettingsView.swift")
        #expect(models.contains("onOpenCapabilities"))
        #expect(models.contains("showingUnconfiguredProviders.toggle()"))
        #expect(message.contains("isCopyFocused"))
        #expect(taskDetail.contains("tasks.cancelConfirmTitle"))
        #expect(releaseCenter.contains("tasks.releaseE2E.confirmTitle"))
        #expect(taskSidebar.contains("tasks.releaseE2E.confirmTitle"))
        #expect(app.contains("TrafficLightHider(resetsRestoredZoomedFrame: false)"))
    }

    @Test
    func runHistoryUsesAFloatingDrawerInsteadOfAWindowSidebar() throws {
        let runs = try Self.source("macOS-Client/Sources/Views/MinimalRunsOverviewView.swift")
        let review = try Self.source("macOS-Client/Sources/Views/MinimalReviewInboxView.swift")
        let project = try Self.source("macOS-Client/Sources/Views/MinimalProjectWorkspaceView.swift")
        let mainSidebar = try Self.source("macOS-Client/Sources/Views/MainPanelSidebar.swift")

        #expect(!runs.contains("NavigationSplitView"))
        #expect(!review.contains("NavigationSplitView"))
        #expect(review.contains("review.count.one"))
        #expect(review.contains("preferences.text(\"review.total\")"))
        #expect(!review.contains("preferences.text(\"review.count\"),\n                    value:"))
        #expect(!project.contains("NavigationSplitView"))
        #expect(project.contains("HSplitView"))
        #expect(!runs.contains(".searchable(text: $searchText, placement: .sidebar"))
        #expect(runs.contains("private var runHistoryDrawer"))
        #expect(review.contains("private var reviewInboxDrawer"))
        #expect(mainSidebar.contains("setContextDrawerVisible(!showsContextDrawer)"))
        #expect(mainSidebar.contains("CustomTrafficLights()"))
        #expect(mainSidebar.contains("Spacer()"))
        #expect(runs.contains(".onTapGesture { setRunHistoryVisible(false) }"))
        #expect(review.contains(".onTapGesture { setInboxVisible(false) }"))
        #expect(runs.contains("setRunHistoryVisible(false)"))
    }

    @Test
    func freshProfileFirstMissionConsumesTheTypedGoalWithoutAnAgent() throws {
        let main = try Self.source("macOS-Client/Sources/Views/MainPanelView.swift")
        let chat = try Self.source("macOS-Client/Sources/Views/MainPanelChat.swift")
        let actions = try Self.source("macOS-Client/Sources/Views/MainPanelActions.swift")
        let work = try Self.source("macOS-Client/Sources/Views/UnifiedWorkView.swift")

        #expect(main.contains("canUseBeginnerMissionInput"))
        #expect(main.contains("canUseAgentFeatures || canUseBeginnerMissionInput"))
        #expect(main.contains("shouldUseInputForBeginnerMission"))
        #expect(chat.contains("case .empty:"))
        #expect(chat.contains("productProgress.isUnlocked(.selfIteration)"))
        #expect(chat.contains("beginnerGoal: viewModel.inputText"))
        #expect(chat.contains("userGoal: goal"))
        #expect(actions.contains("if shouldUseInputForBeginnerMission"))
        #expect(actions.contains("if !canUseAgentFeatures"))
        #expect(actions.contains("runBeginnerMission(text)"))
        #expect(work.contains("normalizedBeginnerGoal"))
        #expect(work.contains("work.beginner.goalPrompt"))
    }

    private static var repositoryRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
    }

    private static func source(_ relativePath: String) throws -> String {
        try String(
            contentsOf: repositoryRoot.appendingPathComponent(relativePath),
            encoding: .utf8
        )
    }

    private static func slice(_ source: String, from startMarker: String, to endMarker: String) -> String? {
        guard let start = source.range(of: startMarker),
              let end = source.range(of: endMarker, range: start.upperBound..<source.endIndex)
        else {
            return nil
        }
        return String(source[start.lowerBound..<end.lowerBound])
    }

    private static func occurrenceCount(of needle: String, in haystack: String) -> Int {
        haystack.components(separatedBy: needle).count - 1
    }

    private static func enumCaseNames(in source: String) -> [String] {
        source.split(separator: "\n").flatMap { line -> [String] in
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            guard trimmed.hasPrefix("case ") else { return [] }
            return trimmed
                .dropFirst("case ".count)
                .split(separator: ",")
                .map { item in
                    item.trimmingCharacters(in: .whitespaces)
                        .split(separator: " ", maxSplits: 1)
                        .first
                        .map(String.init) ?? ""
                }
                .filter { !$0.isEmpty }
        }
    }
}
