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
        #expect(settings.contains("AcrossTheme.sidebarFill(for: colorScheme)"))
        #expect(settings.contains("AcrossTheme.selectedFill(for: colorScheme)"))
        #expect(!settings.contains("List(selection:"))

        let plugins = try Self.source("macOS-Client/Sources/Views/PluginLifecycleView.swift")
        let pluginBody = try #require(
            Self.slice(plugins, from: "var body: some View", to: "private var standaloneHeader")
        )
        #expect(!pluginBody.contains("memorySection"))
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
        #expect(loop.contains("minHeight: 220, maxHeight: 220"))
        #expect(loop.contains(".truncationMode(.tail)"))
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

        #expect(app.contains(".windowStyle(.hiddenTitleBar)"))
        #expect(app.contains(".fullSizeContentView"))
        #expect(mainPanel.contains("TrafficLightHider()"))
        #expect(sidebar.contains("WindowDragView()") || toolbar.contains("WindowDragView()"))
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
        #expect(shell.contains("AutopilotWorkbenchView()"))
        #expect(!shell.contains("onOpenAutopilotDetails"))
        #expect(shell.contains("status: \"active\""))
        #expect(!memory.contains("memory.openCenter"))
        #expect(memory.contains("librarySection"))
        #expect(memory.contains("memory.bulk.approve"))
        #expect(memory.contains("memory.bulk.archive"))
        #expect(review.contains("review.memory.approve.short"))
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
