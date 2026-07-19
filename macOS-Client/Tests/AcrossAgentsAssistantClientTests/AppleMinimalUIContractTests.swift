import Foundation
import Testing
@testable import AcrossAgentsAssistantClient

struct AppleMinimalUIContractTests {
    private static let expectedMainNavigation = ["工作"]

    @Test
    func providerConfigurationStatusesAreLocalized() {
        #expect(AppPreferences.localizedString("status.not_configured", localeIdentifier: "en") == "Not configured")
        #expect(AppPreferences.localizedString("status.not_configured", localeIdentifier: "zh-Hans") == "未配置")
    }

    @Test @MainActor
    func mainNavigationKeepsOneWorkDestinationAndRoutesAttentionToOwners() throws {
        let visibleTitles = OperationsWorkbenchSurface.primary.map {
            AppPreferences.localizedString($0.localizationKey, localeIdentifier: "zh-Hans")
        }
        #expect(visibleTitles == Self.expectedMainNavigation)

        let sidebar = try Self.source("macOS-Client/Sources/Views/OperationsWorkbenchSidebar.swift")
        let visibleBody = sidebar.components(separatedBy: "private func sectionLabel").first ?? sidebar
        #expect(visibleBody.contains("ForEach(OperationsWorkbenchSurface.primary)"))
        #expect(visibleBody.contains("attentionSurfaces.contains(surface)"))
        #expect(visibleBody.contains("Circle()"))
        #expect(!visibleBody.contains("reviewCount"))
        #expect(!visibleBody.contains("navigationRow(.humanReview"))
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
            "workers",
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
            Self.slice(sidebar, from: "var leftSidebar: some View", to: "var projectChatSidebar")
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
    func projectSelectionPreservesTheCurrentOperationalSurface() throws {
        let sidebar = try Self.source("macOS-Client/Sources/Views/MainPanelSidebar.swift")
        let projectSelection = try #require(
            Self.slice(sidebar, from: "onSelectProject: {", to: "onOpenTree: {")
        )
        let newChat = try #require(
            Self.slice(sidebar, from: "onNewChat: {", to: "onSelectSession: {")
        )

        #expect(projectSelection.contains("updateProjectDirectoryFilter(project.path)"))
        #expect(!projectSelection.contains("selectedOperationsSurface = .assist"))
        #expect(newChat.contains("selectedOperationsSurface = .assist"))
    }

    @Test
    func settingsInteractionsUseIndependentScrollingAndSinglePurposeControls() throws {
        let capabilities = try Self.source("macOS-Client/Sources/Views/AgentCapabilitiesView.swift")
        let capabilityBody = try #require(
            Self.slice(capabilities, from: "var body: some View", to: "private var standaloneHeader")
        )
        #expect(capabilityBody.contains("ScrollViewReader"))
        #expect(capabilityBody.contains(".frame(width: 246)"))
        #expect(capabilityBody.contains(".onChange(of: selectedAgentId)"))
        #expect(capabilityBody.contains("proxy.scrollTo(profileScrollTopID, anchor: .top)"))

        let permissions = try Self.source("macOS-Client/Sources/Views/ToolPermissionsView.swift")
        let permissionDropdown = try #require(
            Self.slice(permissions, from: "private struct PermissionDropdownButton", to: "struct ToolPermissionsView")
        )
        #expect(permissionDropdown.contains("Menu {"))
        #expect(!permissionDropdown.contains("Image(systemName: \"chevron.down\")"))

        let diagnostics = try Self.source("macOS-Client/Sources/Views/StartupDiagnosticsView.swift")
        #expect(diagnostics.contains("@State private var showingChecks = false"))
        #expect(diagnostics.contains("isExpanded: $showingChecks"))
        #expect(diagnostics.contains("VStack(spacing: 12)"))
    }

    @Test
    func loopNextActionsRunOnlyFromAPlayButton() throws {
        let loop = try Self.source("macOS-Client/Sources/Views/AutopilotWorkbenchView.swift")
        let actions = try #require(
            Self.slice(loop, from: "private func actionSection", to: "private func sectionsGrid")
        )

        #expect(actions.contains("Image(systemName: \"play.circle.fill\")"))
        #expect(!actions.contains("Image(systemName: \"arrow.right\")"))
        #expect(!actions.contains(".contentShape(Rectangle())"))
        #expect(actions.contains(".accessibilityHint(localizedActionReason(action))"))
    }

    @Test
    func growthResultsAndDiagnosticsKeepActionsExplicitAndCompact() throws {
        let growth = try Self.source("macOS-Client/Sources/Views/CapabilityProgressView.swift")
        let challenge = try #require(
            Self.slice(growth, from: "private struct CapabilityPathView", to: "private struct CapabilityComponentTile")
        )
        #expect(challenge.contains("Image(systemName: \"play.circle.fill\")"))
        #expect(!challenge.contains("Image(systemName: \"arrow.right\")"))
        #expect(challenge.contains("Button {\n                        start(mission)"))
        #expect(!challenge.contains(".contentShape(Rectangle())"))

        let results = try Self.source("macOS-Client/Sources/Views/AcrossVisualResultViews.swift")
        let overview = try #require(
            Self.slice(results, from: "struct AcrossVisualResultOverview", to: "struct AcrossTrustCompassView")
        )
        let verdictHeader = try #require(
            Self.slice(overview, from: "private var verdictHeader", to: "private var actionRow")
        )
        #expect(overview.contains("if !hasActions"))
        #expect(verdictHeader.contains("Spacer(minLength: 16)"))
        #expect(verdictHeader.contains("if hasActions {\n                actionRow"))

        let diagnostics = try Self.source("macOS-Client/Sources/Views/StartupDiagnosticsView.swift")
        let header = try #require(
            Self.slice(diagnostics, from: "private var header", to: "private func overview")
        )
        #expect(header.contains(".controlSize(.small)"))
        #expect(!header.contains(".padding(.horizontal"))
        #expect(!header.contains(".padding(.vertical"))
    }

    @Test
    func primaryOperationalPagesShareAQuietHeaderAndBoundDenseCards() throws {
        let work = try Self.source("macOS-Client/Sources/Views/MainPanelChat.swift")
        let workflows = try Self.source("macOS-Client/Sources/Views/MinimalRunsOverviewView.swift")
        let memory = try Self.source("macOS-Client/Sources/Views/EvidenceMemoryOperationsViews.swift")
        let loop = try Self.source("macOS-Client/Sources/Views/AutopilotWorkbenchView.swift")
        let growth = try Self.source("macOS-Client/Sources/Views/CapabilityProgressView.swift")
        let shared = try Self.source("macOS-Client/Sources/Views/MinimalWorkflowComponents.swift")

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
        #expect(loop.contains("title: appPreferences.text(\"workbench.sections\")"))
        #expect(loop.contains("isExpanded: $showsTechnicalEvidence"))
        #expect(!loop.contains("sectionHeader(appPreferences.text(\"workbench.sections\")"))
        #expect(!loop.contains("DisclosureGroup(isExpanded: $showsTechnicalEvidence)"))
        #expect(!loop.contains("minHeight: 220, maxHeight: 220"))
        #expect(shared.contains("struct MinimalDisclosureSection"))
        #expect(shared.contains("isExpanded.toggle()"))
        #expect(shared.contains("isExpanded ? \"chevron.down\" : \"chevron.right\""))
        #expect(shared.contains(".contentShape(Rectangle())"))
        #expect(loop.contains(".truncationMode(.tail)"))
        #expect(!loop.contains("if let endpoint = action.endpoint"))
        #expect(!loop.contains("if let endpoint = section.endpoint"))
        #expect(loop.contains("label: appPreferences.text(\"workbench.selfCheck\")"))
        let workspaceReadiness = try #require(
            Self.slice(loop, from: "private func agentWorkspaceReadinessPanel", to: "private func summaryGrid")
        )
        #expect(!workspaceReadiness.contains("AcrossTheme.panelFill"))
        #expect(!workspaceReadiness.contains("AcrossTheme.recessedFill"))
        let operationalCards = try #require(
            Self.slice(loop, from: "private func sectionPanel", to: "private func summaryPairs")
        )
        #expect(operationalCards.contains("AcrossTheme.panelFill"))
        #expect(workflows.contains(".minimalPageContentFrame(bottomPadding: 8)"))
        #expect(workflows.contains("Text(conciseTaskTitle(task.description))"))
        #expect(growth.contains("onStartMission: (AcrossLearningMissionKind) -> Void"))
        #expect(growth.contains("Array(repeating: GridItem(.flexible(minimum: 148), spacing: 12), count: 4)"))
        #expect(growth.contains("private struct CapabilityComponentTile"))
        #expect(!growth.contains("private func missionNode"))
        #expect(!growth.contains("Text(preferences.text(\"growth.path.title\"))"))
        #expect(!growth.contains("subtitle: preferences.text(progress.levelKey)"))
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
        #expect(navigation.contains("focusedSurface = surface"))
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
        let lifecycle = try Self.source("macOS-Client/Sources/ViewModels/PluginLifecycleViewModel.swift")
        let designSystem = try Self.source("macOS-Client/Sources/Views/AcrossDesignSystem.swift")

        #expect(memory.contains("memoryBatchCompletedCount"))
        #expect(memory.contains("memory.bulk.archiving"))
        #expect(memory.contains("AcrossReviewActionButtonStyle(kind: .approve)"))
        #expect(memory.contains("AcrossReviewActionButtonStyle(kind: .archive)"))
        #expect(designSystem.contains("case .approve:\n            return AcrossTheme.accent"))
        #expect(designSystem.contains("case .archive:\n            return Color(nsColor: .systemRed)"))
        #expect(lifecycle.contains("memoryBatchTotalCount = memories.count"))
        #expect(lifecycle.contains("memoryBatchCompletedCount = index + 1"))
        #expect(lifecycle.contains("AcrossMemoryMutationResponse.self"))
    }

    @Test
    func productShellPublishesFastReviewCountsAndUsesExpandedWindowSpace() throws {
        let lifecycle = try Self.source("macOS-Client/Sources/ViewModels/PluginLifecycleViewModel.swift")
        let main = try Self.source("macOS-Client/Sources/Views/MainPanelView.swift")

        #expect(lifecycle.contains("var pendingMemoryCount: Int"))
        #expect(lifecycle.contains("agentLoopMemoryMetrics?.totals?.pendingCount ?? 0"))
        #expect(lifecycle.contains("let memoryMetricsTask = Task"))
        #expect(lifecycle.contains("await loadMemories(refreshMetrics: false)"))
        #expect(main.contains("windowContentWidth >= 1220"))
        #expect(main.contains("pluginLifecycleViewModel.pendingMemoryCount"))
    }

    @Test
    func taskResultsKeepOnlyTheDecisionSurfaceVisibleByDefault() throws {
        let runs = try Self.source("macOS-Client/Sources/Views/MinimalRunsOverviewView.swift")
        let visualResults = try Self.source("macOS-Client/Sources/Views/AcrossVisualResultViews.swift")
        let evidence = try Self.source("macOS-Client/Sources/Views/TaskReleaseEvidenceViews.swift")
        let artifacts = try Self.source("macOS-Client/Sources/Views/TaskArtifactViews.swift")
        let detail = try Self.source("macOS-Client/Sources/Views/TaskDetailViews.swift")
        let work = try Self.source("macOS-Client/Sources/Views/UnifiedWorkView.swift")

        #expect(runs.contains("@State private var showsTaskDescription = false"))
        #expect(runs.contains("@State private var showsWaveDetails = false"))
        #expect(runs.contains("@State private var showsArtifactDetails = false"))
        #expect(runs.contains("MinimalDisclosureSection("))
        #expect(!runs.contains("DisclosureGroup(isExpanded: $showsTaskDescription)"))
        #expect(!runs.contains("DisclosureGroup(isExpanded: $showsWaveDetails)"))
        #expect(!runs.contains("DisclosureGroup(isExpanded: $showsArtifactDetails)"))
        #expect(runs.contains("Array(artifacts.prefix(8))"))
        #expect(visualResults.contains("viewModel.acceptTaskResult(task.taskId)"))
        #expect(runs.contains("AcrossTaskResultOverview("))
        #expect(work.contains("AcrossTaskResultOverview("))
        #expect(work.contains("showsResultOverview: false"))
        #expect(detail.contains("if showsResultOverview"))
        #expect(!runs.contains("runHeader(task)"))
        let resultOverview = try #require(
            Self.slice(visualResults, from: "struct AcrossVisualResultOverview", to: "struct AcrossTrustCompassView")
        )
        #expect(!resultOverview.contains("DisclosureGroup"))
        #expect(!resultOverview.contains("AcrossEvidenceRouteView"))
        #expect(resultOverview.contains("result.review.awaiting"))
        #expect(!visualResults.contains("AcrossTheme.recessedFill"))
        #expect(evidence.contains("@State private var showsDecisionBasis = false"))
        #expect(evidence.contains("@State private var showsVerificationScope = false"))
        #expect(evidence.contains("@State private var showsResultDetails = false"))
        #expect(evidence.contains("isExpanded: $showsDecisionBasis"))
        #expect(evidence.contains("isExpanded: $showsVerificationScope"))
        #expect(evidence.contains("isExpanded: $showsResultDetails"))
        #expect(!evidence.contains("DisclosureGroup(isExpanded: $showsDecisionBasis)"))
        #expect(evidence.contains("AcrossTrustCompassView("))
        #expect(!evidence.contains("AcrossEvidenceRouteView("))
        #expect(!evidence.contains("AcrossLoopTrailView("))
        #expect(artifacts.contains("artifact.filePath.hasPrefix(\"/api/workers/artifacts/\")"))
        #expect(artifacts.contains("TaskArtifactPreviewSheet"))
        #expect(detail.contains("viewModel.previewArtifact($0)"))
        #expect(detail.contains("$viewModel.selectedArtifactPreview"))
        #expect(!evidence.contains("AcrossDecisionMarkView("))
        #expect(!evidence.contains("Text(bundle.releaseReadinessSummary)"))
    }

    @Test
    func workerRowsKeepNativeChildAccessibilityInsteadOfRepeatingTheRowLabel() throws {
        let workers = try Self.source("macOS-Client/Sources/Views/DevicesWorkersSettingsView.swift")

        #expect(workers.contains(".accessibilityElement(children: .contain)"))
        #expect(!workers.contains(".accessibilityLabel(Text(node.displayName + \", \" + stateText(node.state)))"))
        #expect(workers.contains("Task.sleep(for: .seconds(5))"))
        #expect(!workers.contains(".onChange(of: viewModel.snapshot)"))
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
        let qualityGate = try Self.source("macOS-Client/Sources/Views/QualityGateOperationsView.swift")
        let workspaceViewModel = try Self.source("macOS-Client/Sources/ViewModels/AgentWorkspaceOperationsViewModel.swift")
        let project = try Self.source("macOS-Client/Sources/Views/MinimalProjectWorkspaceView.swift")
        let toolbar = try Self.source("macOS-Client/Sources/Views/MainPanelToolbar.swift")
        let unifiedWork = try Self.source("macOS-Client/Sources/Views/UnifiedWorkView.swift")
        let shell = try Self.source("macOS-Client/Sources/Views/OperationsWorkbenchShell.swift")
        let loop = try Self.source("macOS-Client/Sources/Views/AutopilotWorkbenchView.swift")
        let memory = try Self.source("macOS-Client/Sources/Views/EvidenceMemoryOperationsViews.swift")
        let protectedDelivery = try #require(
            Self.slice(chat, from: "private var protectedDeliveryContent", to: "private var unifiedWorkEmptyState")
        )

        #expect(sidebar.contains("onOpenSettings: { openSettings(.settings) }"))
        #expect(sidebar.contains("selectedOperationsSurface = .assist"))
        #expect(!sidebar.contains("if selectedOperationsSurface == .assist"))
        #expect(mainPanel.contains("memory-review-batch"))
        #expect(mainPanel.contains("qualityGateViewModel.reviewSignals"))
        #expect(mainPanel.contains("workspaceOperationsViewModel.reviewSignals"))
        #expect(!actions.contains("openHumanReviewItem"))
        #expect(actions.contains("submitProtectedTask"))
        #expect(actions.contains("workSubmissionMode.usesProtectedDelivery"))
        #expect(actions.contains("submitDirectAgentWork"))
        #expect(!actions.contains("work.setupRequired"))
        #expect(mainPanel.contains("&& !canUseAgentFeatures"))
        #expect(actions.contains("taskTypes: [\"functional\", \"artifact\"]"))
        #expect(!actions.contains("openSettings(.workbench)"))
        #expect(runs.contains("RunDestination"))
        #expect(runs.contains("private var runOverview"))
        #expect(runs.contains("ForEach(filteredTasks)"))
        #expect(!runs.contains("viewModel.tasks.prefix(6)"))
        #expect(!runs.contains("runCenterTabs"))
        #expect(!runs.contains("pickerStyle(.segmented)"))
        #expect(!runs.contains("private var releaseMenu"))
        #expect(!runs.contains("showsQualityGate"))
        #expect(runs.contains("onStartWork()"))
        #expect(!runs.contains("SimpleStartWorkflowView"))
        #expect(!runs.contains("TaskNewTaskForm("))
        #expect(!runs.contains("runActionRow("))
        #expect(!runs.contains("destination = .quality"))
        #expect(!runs.contains("destination = .release"))
        #expect(runs.contains("@State private var showsInspector = false"))
        #expect(qualityGate.contains("@State private var showsAdvancedOptions = false"))
        #expect(qualityGate.contains("MinimalDisclosureSection("))
        #expect(!qualityGate.contains("DisclosureGroup("))
        #expect(!workspaceViewModel.contains("workspace-readiness-"))
        #expect(project.contains("workspace.repositoryRequired.title"))
        #expect(project.contains("chooseRepository"))
        #expect(!mainPanel.contains("isContinuousMode"))
        #expect(!chat.contains("isContinuousMode"))
        #expect(toolbar.contains("work.back"))
        #expect(toolbar.contains("!appPreferences.automaticDeliveryProtection"))
        #expect(unifiedWork.contains("TaskDetailPanel("))
        #expect(!protectedDelivery.contains("showTaskOrchestration = true"))
        #expect(unifiedWork.contains("AcrossTaskResultOverview("))
        #expect(chat.contains("AutopilotEvidenceTarget("))
        #expect(chat.contains("autopilotEvidenceTarget = target"))
        #expect(chat.contains("selectedOperationsSurface = .autopilot"))
        #expect(mainPanel.contains("if selectedOperationsSurface != .autopilot"))
        #expect(mainPanel.contains("autopilotEvidenceTarget = nil"))
        #expect(shell.contains("AutopilotWorkbenchView(evidenceTarget: autopilotEvidenceTarget)"))
        #expect(loop.contains(".task(id: evidenceTarget)"))
        #expect(loop.contains("await evidenceViewModel.load(target: evidenceTarget)"))
        #expect(loop.contains("@State private var showsFocusedEvidenceDetails = false"))
        let focusedDisclosure = loop.range(of: "isExpanded: $showsFocusedEvidenceDetails")
        let focusedRunID = loop.range(of: "Text(target.runID)")
        #expect(focusedDisclosure != nil)
        #expect(focusedRunID != nil)
        if let focusedDisclosure, let focusedRunID {
            #expect(focusedRunID.lowerBound > focusedDisclosure.lowerBound)
        }
        #expect(!shell.contains("onOpenAutopilotDetails"))
        #expect(memory.contains("status: \"active\""))
        #expect(!memory.contains("memory.openCenter"))
        #expect(memory.contains("librarySection"))
        #expect(memory.contains("memory.bulk.approve"))
        #expect(memory.contains("memory.bulk.archive"))
        #expect(memory.contains("AcrossReviewActionButtonStyle(kind: .approve)"))
        #expect(memory.contains("AcrossReviewActionButtonStyle(kind: .archive)"))
        let models = try Self.source("macOS-Client/Sources/Views/ModelSettingsView.swift")
        #expect(models.contains("onOpenCapabilities"))
        #expect(models.contains("unconfiguredLocalAgents"))
        #expect(models.contains("showingUnconfiguredLocalAgents.toggle()"))
        #expect(models.contains("showingUnconfiguredProviders.toggle()"))
        let capabilities = try Self.source("macOS-Client/Sources/Views/AgentCapabilitiesView.swift")
        #expect(capabilities.contains("settingsViewModel.availableLocalAgents.map"))
        #expect(capabilities.contains("settingsViewModel.availableCloudLLMs.map"))
        #expect(!capabilities.contains("settingsViewModel.localAgents.map"))
        #expect(!capabilities.contains("settingsViewModel.cloudLLMs.map"))
        #expect(message.contains("isCopyFocused"))
        #expect(taskDetail.contains("tasks.cancelConfirmTitle"))
        #expect(taskDetail.contains("if task.remoteExecution != nil"))
        #expect(taskDetail.contains("if task.remoteExecution == nil,"))
        #expect(releaseCenter.contains("tasks.releaseE2E.confirmTitle"))
        #expect(taskSidebar.contains("tasks.releaseE2E.confirmTitle"))
        #expect(app.contains("TrafficLightHider(resetsRestoredZoomedFrame: false)"))
    }

    @Test
    func runHistoryUsesAFloatingDrawerInsteadOfAWindowSidebar() throws {
        let runs = try Self.source("macOS-Client/Sources/Views/MinimalRunsOverviewView.swift")
        let project = try Self.source("macOS-Client/Sources/Views/MinimalProjectWorkspaceView.swift")
        let mainSidebar = try Self.source("macOS-Client/Sources/Views/MainPanelSidebar.swift")

        #expect(!runs.contains("NavigationSplitView"))
        #expect(!project.contains("NavigationSplitView"))
        #expect(project.contains("HSplitView"))
        #expect(!runs.contains(".searchable(text: $searchText, placement: .sidebar"))
        #expect(runs.contains("private var runHistoryDrawer"))
        #expect(!mainSidebar.contains("contextDrawerLabel"))
        #expect(mainSidebar.contains("CustomTrafficLights()"))
        #expect(mainSidebar.contains("Spacer()"))
        #expect(runs.contains(".onTapGesture { setRunHistoryVisible(false) }"))
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
