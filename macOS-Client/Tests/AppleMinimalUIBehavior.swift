import Foundation

private let repositoryRoot = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)

private func source(_ relativePath: String) -> String {
    let url = repositoryRoot.appendingPathComponent(relativePath)
    guard let contents = try? String(contentsOf: url, encoding: .utf8) else {
        fatalError("Unable to read \(relativePath)")
    }
    return contents
}

private func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() {
        fatalError(message)
    }
}

private func slice(_ source: String, from startMarker: String, to endMarker: String) -> String {
    guard let start = source.range(of: startMarker),
          let end = source.range(of: endMarker, range: start.upperBound..<source.endIndex)
    else {
        fatalError("Missing source markers: \(startMarker) ... \(endMarker)")
    }
    return String(source[start.lowerBound..<end.lowerBound])
}

private func bracketedList(in source: String, after marker: String) -> String {
    guard let markerRange = source.range(of: marker),
          let assignment = source[markerRange.upperBound...].firstIndex(of: "="),
          let open = source[assignment...].firstIndex(of: "[")
    else {
        fatalError("Missing list after \(marker)")
    }

    var depth = 0
    var index = open
    while index < source.endIndex {
        switch source[index] {
        case "[": depth += 1
        case "]":
            depth -= 1
            if depth == 0 {
                return String(source[open...index])
            }
        default: break
        }
        index = source.index(after: index)
    }
    fatalError("Unterminated list after \(marker)")
}

private func caseReferences(in source: String) -> [String] {
    let expression = try! NSRegularExpression(pattern: #"\.([A-Za-z][A-Za-z0-9_]*)"#)
    let range = NSRange(source.startIndex..., in: source)
    return expression.matches(in: source, range: range).compactMap { match in
        guard let range = Range(match.range(at: 1), in: source) else { return nil }
        return String(source[range])
    }
}

private func occurrenceCount(of needle: String, in haystack: String) -> Int {
    haystack.components(separatedBy: needle).count - 1
}

private func checkNavigationShape() {
    let model = source("macOS-Client/Sources/Models/OperationsWorkbenchModels.swift")
    let primary = bracketedList(in: model, after: "static let primary")
    let primaryCases = caseReferences(in: primary)
    check(
        primaryCases == ["assist"],
        "Main navigation must contain only the Work destination"
    )

    let preferences = source("macOS-Client/Sources/Models/AppPreferences.swift")
    let expectedChineseTitles = [
        "operations.reviewQueue": "待你确认",
        "operations.assist": "工作",
    ]
    for (key, title) in expectedChineseTitles {
        check(
            preferences.contains("\"\(key)\": \"\(title)\""),
            "Missing Chinese main navigation title: \(title)"
        )
    }

    let sidebar = source("macOS-Client/Sources/Views/OperationsWorkbenchSidebar.swift")
    let visibleBody = sidebar.components(separatedBy: "private func sectionLabel").first ?? sidebar
    check(visibleBody.contains("ForEach(OperationsWorkbenchSurface.primary)"), "Main navigation must render the Work destination")
    check(visibleBody.contains("if reviewCount > 0"), "Review must remain hidden when there is nothing to decide")
    check(visibleBody.contains("navigationRow(.humanReview"), "Review must appear when a decision is waiting")
    check(!visibleBody.contains("secondaryRow("), "Management links must not expand the main navigation")
    check(sidebar.contains(".focused($focusedSurface"), "Keyboard focus must remain tracked without a system outline")
    check(sidebar.contains(".focusEffectDisabled()"), "Main navigation must suppress blue system focus borders")

    let settings = source("macOS-Client/Sources/Views/SettingsHubView.swift")
    let settingsCategories = slice(settings, from: "enum SettingsHubCategory", to: "var id: String")
    let settingsCases = settingsCategories.split(separator: "\n").filter {
        $0.trimmingCharacters(in: .whitespaces).hasPrefix("case ")
    }
    check(settingsCases.count == 7, "Settings navigation must expose seven clear flat destinations")
    check(settings.contains("case plugins"), "Settings must expose Plugin Center directly")
    check(settings.contains("case mcp"), "Settings must expose MCP directly")
    check(!settings.contains("case pluginsAndConnections"), "Plugin Center and MCP must not share one destination")
    check(!settings.contains("case advanced"), "Settings must not hide all product capabilities behind Advanced")
    check(!settings.contains("case workbench"), "Settings must not duplicate Loop Engineering")
    check(settings.contains("case agents"), "Agent and model settings must have a direct destination")
    check(settings.contains("case capabilities"), "Capabilities must have a direct destination")
    check(settings.contains("PluginLifecycleView"), "Plugin Center must render directly")
    check(settings.contains("MCPPreferencesView"), "MCP settings must render directly")
    check(settings.contains("ForEach(SettingsHubCategory.allCases)"), "Settings must render the flat navigation")
    check(settings.contains("switch selectedCategory"), "Settings content must follow the visible category selection")
    check(settings.contains("private var windowControls"), "Settings must integrate controls into the sidebar")
    check(!settings.contains("private var header: some View"), "Settings must not restore a visible title bar")
    check(settings.contains(".background(.bar)"), "Settings sidebar must share the main sidebar material")
    check(settings.contains(".minimalPageContentFrame()"), "Settings content must share the primary page geometry")
    check(settings.contains("WindowDragView()"), "Settings must retain a hidden drag region")
    check(settings.contains(".focused($focusedCategory"), "Settings focus must remain visible through its background state")
    check(settings.contains(".focusEffectDisabled()"), "Settings must suppress blue system focus borders")
    let settingsShell = slice(settings, from: "var body: some View", to: "private var windowControls")
    check(!settingsShell.contains("Divider()"), "Settings sidebar must not be split by a top rule")

    let app = source("macOS-Client/Sources/AcrossAgentsAssistantApp.swift")
    let design = source("macOS-Client/Sources/Views/AcrossDesignSystem.swift")
    let agentIdentity = source("macOS-Client/Sources/Views/AgentIdentityComponents.swift")
    let taskForm = source("macOS-Client/Sources/Views/TaskFormViews.swift")
    let pluginSource = source("macOS-Client/Sources/Views/PluginLifecycleView.swift")
    let diffReview = source("macOS-Client/Sources/Views/WorkspaceDiffReviewView.swift")
    let capabilities = source("macOS-Client/Sources/Views/AgentCapabilitiesView.swift")
    check(app.contains(".focusEffectDisabled()"), "The main app must suppress inherited system focus borders")
    check(!design.contains("focusRing(for"), "The design system must not render a blue focus outline")
    check(!agentIdentity.contains(".stroke(isSelected ? AcrossTheme.accent"), "Agent selection must use fill or icon feedback, not a blue border")
    check(!taskForm.contains(".stroke(selectedDeliveryTaskTypes.contains(type) ? AcrossTheme.accent"), "Task selection must use a blue fill without a blue border")
    check(!pluginSource.contains(".stroke(isHighlighted ? accentColor"), "Highlighted memories must use fill without a blue border")
    check(!diffReview.contains(".stroke(AcrossTheme.accent"), "Focused diff comments must use fill without a blue border")
    check(!capabilities.contains(".stroke(accentColor"), "Capability actions must not use blue borders")

    let settingsHeader = source("macOS-Client/Sources/Views/MinimalSettingsComponents.swift")
    check(settingsHeader.contains("windowLayoutSize == .expanded ? 32 : 28"), "Settings titles must share primary page typography")

    for path in [
        "macOS-Client/Sources/Views/ModelSettingsView.swift",
        "macOS-Client/Sources/Views/PluginLifecycleView.swift",
        "macOS-Client/Sources/Views/MCPPreferencesView.swift",
        "macOS-Client/Sources/Views/AgentCapabilitiesView.swift",
        "macOS-Client/Sources/Views/ToolPermissionsView.swift",
        "macOS-Client/Sources/Views/StartupDiagnosticsView.swift",
    ] {
        check(source(path).contains(".minimalPageContentFrame()"), "Every settings destination must share primary page geometry")
    }

    let plugins = source("macOS-Client/Sources/Views/PluginLifecycleView.swift")
    let pluginBody = slice(plugins, from: "var body: some View", to: "private var standaloneHeader")
    check(!pluginBody.contains("memorySection"), "Plugin settings must not duplicate shared memory review")
    check(
        plugins.contains(".accessibilityLabel(Text(title))"),
        "Plugin icon-only lifecycle actions must expose their localized names"
    )
    check(
        plugins.contains(".accessibilityLabel(Text(appPreferences.text(\"settings.refresh\")))"),
        "Plugin refresh actions must expose a localized accessible name"
    )
    check(
        plugins.contains(".accessibilityLabel(Text(appPreferences.text(\"plugins.loop.probe\")))"),
        "Plugin Agent Loop probe must expose a localized accessible name"
    )
}

private func checkWindowChrome() {
    let app = source("macOS-Client/Sources/AcrossAgentsAssistantApp.swift")
    check(app.contains(".windowStyle(.hiddenTitleBar)"), "Main window must use hiddenTitleBar")
    check(app.contains(".fullSizeContentView"), "Main window must use fullSizeContentView")

    let support = source("macOS-Client/Sources/Views/MainPanelWindowSupport.swift")
    for button in ["closeButton", "miniaturizeButton", "zoomButton"] {
        check(
            support.contains("standardWindowButton(.\(button))?.isHidden = true"),
            "System \(button) must be hidden"
        )
    }

    let mainPanel = source("macOS-Client/Sources/Views/MainPanelView.swift")
    check(mainPanel.contains("TrafficLightHider()"), "Main panel must install the system traffic-light hider")

    let draggableChrome = source("macOS-Client/Sources/Views/MainPanelSidebar.swift")
        + source("macOS-Client/Sources/Views/MainPanelToolbar.swift")
    check(draggableChrome.contains("WindowDragView()"), "Integrated title bar must retain a drag region")
    let sharedUI = source("macOS-Client/Sources/Views/SharedUIComponents.swift")
    check(
        sharedUI.contains("accessibilityDisplayShouldReduceMotion")
            && sharedUI.contains("preferences.reduceMotion")
            && sharedUI.contains("animate: shouldAnimate"),
        "Double-click full-size transitions must honor both system and in-app Reduce Motion"
    )
    let mainSidebar = slice(
        source("macOS-Client/Sources/Views/MainPanelSidebar.swift"),
        from: "var leftSidebar: some View",
        to: "private var contextDrawerLabel"
    )
    check(!mainSidebar.contains("Divider()"), "Main sidebar must use spacing instead of horizontal section rules")
}

private func checkCustomTrafficLights() {
    let sharedUI = source("macOS-Client/Sources/Views/SharedUIComponents.swift")
    let trafficLights = slice(sharedUI, from: "struct CustomTrafficLights", to: "struct TrafficLightButton")

    check(occurrenceCount(of: "TrafficLightButton(", in: trafficLights) == 3, "CustomTrafficLights must draw exactly three buttons")
    check(trafficLights.contains("iconName: \"xmark\""), "Close traffic light is missing")
    check(trafficLights.contains("iconName: \"minus\""), "Minimize traffic light is missing")
    check(trafficLights.contains("iconName: \"arrow.up.left.and.arrow.down.right\""), "Zoom traffic light is missing")
    check(trafficLights.contains("WindowVisibilityController.closeMainWindow()"), "Close action is missing")
    check(trafficLights.contains("keyWindow?.miniaturize(nil)"), "Minimize action is missing")
    check(trafficLights.contains("keyWindow?.zoom(nil)"), "Zoom action is missing")
}

private func checkPrimaryPageVisualLanguage() {
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
    let shell = source("macOS-Client/Sources/Views/OperationsWorkbenchShell.swift")
    var files = [
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
    let viewsDirectory = repositoryRoot.appendingPathComponent("macOS-Client/Sources/Views")
    let minimalFiles = (try? FileManager.default.contentsOfDirectory(atPath: viewsDirectory.path)) ?? []
    files += minimalFiles
        .filter { $0.hasPrefix("Minimal") && $0.hasSuffix(".swift") }
        .map { "macOS-Client/Sources/Views/\($0)" }
    if shell.contains("WorkspaceOperationsView(") {
        files += [
            "macOS-Client/Sources/Views/WorkspaceOperationsView.swift",
            "macOS-Client/Sources/Views/WorkspaceCandidatePanes.swift",
        ]
    }
    if shell.contains("QualityGateOperationsView(") {
        files += [
            "macOS-Client/Sources/Views/QualityGateOperationsView.swift",
            "macOS-Client/Sources/Views/QualityGateResultView.swift",
        ]
    }

    var violations: [String] = []
    for file in files {
        let contents = source(file)
        for token in forbiddenTokens where contents.contains(token) {
            violations.append("\(file): \(token)")
        }
    }
    check(violations.isEmpty, "Forbidden main UI visuals: \(violations.joined(separator: ", "))")
}

private func checkCriticalInteractionContracts() {
    let sidebar = source("macOS-Client/Sources/Views/MainPanelSidebar.swift")
    check(sidebar.contains("onOpenSettings: { openSettings(.settings) }"), "Settings must open the simple General page")
    check(sidebar.contains("selectedOperationsSurface = .assist"), "Session selection must reveal Work")

    let actions = source("macOS-Client/Sources/Views/MainPanelActions.swift")
    check(actions.contains("submitProtectedTask"), "Work must support protected delivery")
    check(actions.contains("taskTypes: [\"functional\", \"artifact\"]"), "Protected delivery must check behavior and artifacts")
    check(actions.contains("selectedOperationsSurface = .autopilot"), "Agent Loop review items must route to Loop Engineering")
    check(!actions.contains("openSettings(.workbench)"), "Loop Engineering must not reopen a duplicate Settings workbench")

    let runs = source("macOS-Client/Sources/Views/MinimalRunsOverviewView.swift")
    let minimalControls = source("macOS-Client/Sources/Views/MinimalWorkflowComponents.swift")
    let loopWorkbench = source("macOS-Client/Sources/Views/AutopilotWorkbenchView.swift")
    let memory = source("macOS-Client/Sources/Views/EvidenceMemoryOperationsViews.swift")
    let simpleStart = source("macOS-Client/Sources/Views/TaskWorkflowStartViews.swift")
    let qualityGate = source("macOS-Client/Sources/Views/QualityGateOperationsView.swift")
    let workspaceViewModel = source("macOS-Client/Sources/ViewModels/AgentWorkspaceOperationsViewModel.swift")
    let projectSetup = source("macOS-Client/Sources/Views/MinimalProjectWorkspaceView.swift")
    check(runs.contains("showsReleaseE2EConfirmation = true"), "Complex E2E must require confirmation")
    check(runs.contains("tasks.releaseE2E.confirmMessage"), "Complex E2E must explain cost and duration")
    check(runs.contains("RunDestination"), "Runs must use hierarchical destinations")
    check(runs.contains("private var runOverview"), "Runs must start from one workflow-oriented overview")
    check(minimalControls.contains(".frame(width: 32, height: 30)"), "Primary page icon buttons must use one stable size")
    check(minimalControls.contains("Task.sleep(nanoseconds: 800_000_000)"), "Primary page tooltips must appear within one second")
    check(minimalControls.contains(".onHover(perform: updateTooltip)"), "Primary page icon buttons must expose fast hover help")
    check(!minimalControls.contains(".help(label)"), "Primary page icon buttons must not also show the slower native tooltip")
    check(loopWorkbench.contains("MinimalIconButton("), "Loop Engineering must use the shared header icon buttons")
    check(!loopWorkbench.contains("private func iconButton("), "Loop Engineering must not keep a separate toolbar style")
    check(loopWorkbench.contains("@State private var showsTechnicalEvidence = false"), "Loop Engineering technical evidence must start collapsed")
    check(loopWorkbench.contains("DisclosureGroup(isExpanded: $showsTechnicalEvidence)"), "Loop Engineering raw diagnostics must use progressive disclosure")
    check(!loopWorkbench.contains("if let endpoint = action.endpoint"), "Loop Engineering actions must not expose internal endpoints")
    check(!loopWorkbench.contains("if let endpoint = section.endpoint"), "Loop Engineering sections must not expose internal endpoints")
    check(memory.contains("systemName: \"wand.and.stars\""), "Memory suggestions must use an icon command")
    check(runs.contains("systemName: \"plus\""), "New Workflow must use the shared icon command")
    check(!runs.contains("runCenterTabs"), "Runs must not expose module tabs")
    check(!runs.contains("pickerStyle(.segmented)"), "Runs must not present Tasks, Quality, and Release as segmented modules")
    check(!runs.contains("private var releaseMenu"), "Runs must not restore the legacy checkmark dropdown")
    check(!runs.contains("showsQualityGate"), "Quality must not open as a separate sheet")
    check(!simpleStart.contains("accentHex"), "Workflow choices must not use colored category accents")
    check(!simpleStart.contains("SimpleStartWorkflowCard"), "Workflow choices must remain a compact list")
    check(runs.contains("@State private var showsInspector = false"), "Run inspector must start closed")
    check(qualityGate.contains("@State private var showsAdvancedOptions = false"), "Quality advanced options must start collapsed")
    check(qualityGate.contains("DisclosureGroup("), "Quality advanced options must remain progressively disclosed")
    check(!workspaceViewModel.contains("workspace-readiness-"), "Repository setup errors must not become review items")
    check(projectSetup.contains("workspace.repositoryRequired.title"), "Project setup must explain the repository requirement")
    check(projectSetup.contains("chooseRepository"), "Project setup must provide an immediate repository action")
    let taskDetail = source("macOS-Client/Sources/Views/TaskDetailViews.swift")
    let releaseCenter = source("macOS-Client/Sources/Views/TaskReleaseEvidenceViews.swift")
    let taskSidebar = source("macOS-Client/Sources/Views/TaskOrchestrationSidebar.swift")
    check(taskDetail.contains("tasks.cancelConfirmTitle"), "Detailed task cancellation must require confirmation")
    check(releaseCenter.contains("tasks.releaseE2E.confirmTitle"), "Release Center E2E must require confirmation")
    check(taskSidebar.contains("tasks.releaseE2E.confirmTitle"), "Task sidebar E2E must require confirmation")

    let mainPanel = source("macOS-Client/Sources/Views/MainPanelView.swift")
    let chat = source("macOS-Client/Sources/Views/MainPanelChat.swift")
    let shell = source("macOS-Client/Sources/Views/OperationsWorkbenchShell.swift")
    let toolbar = source("macOS-Client/Sources/Views/MainPanelToolbar.swift")
    let unifiedWork = source("macOS-Client/Sources/Views/UnifiedWorkView.swift")
    let protectedDelivery = slice(chat, from: "private var protectedDeliveryContent", to: "private var unifiedWorkEmptyState")
    check(!mainPanel.contains("isContinuousMode"), "Assistant must not expose a state-only continuous mode")
    check(!chat.contains("isContinuousMode"), "Assistant must not expose a state-only continuous mode")
    check(toolbar.contains("work.back"), "Completed work must provide an explicit back action")
    check(toolbar.contains("!appPreferences.automaticDeliveryProtection"), "Direct conversations must provide a return to Work")
    let assistHeaderCondition = slice(chat, from: "private var shouldShowAssistHeader", to: "@ViewBuilder\n    var contentArea")
    check(!assistHeaderCondition.contains("selectedTask"), "Protected work details must not restore the legacy title bar")
    check(unifiedWork.contains("MinimalPageHeader(title: headline, subtitle: subheadline)"), "Work details must use the shared page header")
    check(unifiedWork.contains("systemName: \"chevron.left\""), "Work details must expose Back as an icon action")
    check(unifiedWork.contains("systemName: \"folder\""), "Work details must expose Workspace as an icon action")
    check(unifiedWork.contains("systemName: \"plus\""), "Work details must expose New Work as an icon action")
    check(unifiedWork.contains("TaskDetailPanel("), "Technical details must be embedded for the selected task")
    check(!protectedDelivery.contains("showTaskOrchestration = true"), "Technical details must not open the all-workflows overlay")
    check(protectedDelivery.contains("acceptTaskResult"), "Accepting a result must persist through the task API")
    check(chat.contains("AutopilotEvidenceTarget("), "Open evidence must bind the beginner run and evidence route")
    check(chat.contains("autopilotEvidenceTarget = target"), "Open evidence must preserve its run-specific target")
    check(mainPanel.contains("if selectedOperationsSurface != .autopilot"), "Leaving Loop Engineering must clear stale evidence routing")
    check(mainPanel.contains("autopilotEvidenceTarget = nil"), "A later Loop Engineering visit must not inherit an old beginner run")
    check(shell.contains("AutopilotWorkbenchView(evidenceTarget: autopilotEvidenceTarget)"), "Loop Engineering must receive the selected evidence target")
    check(loopWorkbench.contains(".task(id: evidenceTarget)"), "Loop Engineering must load evidence when the selected run changes")
    check(loopWorkbench.contains("@State private var showsFocusedEvidenceDetails = false"), "Focused technical evidence must start collapsed")
    if let disclosure = loopWorkbench.range(of: "DisclosureGroup(isExpanded: $showsFocusedEvidenceDetails)"),
       let runID = loopWorkbench.range(of: "Text(target.runID)") {
        check(runID.lowerBound > disclosure.lowerBound, "Raw run identifiers must stay behind focused technical evidence disclosure")
    } else {
        check(false, "Focused evidence must keep a collapsed technical details section")
    }
    check(!protectedDelivery.contains("onContinue: {\n                let priorGoal = taskOrchestrationViewModel.selectedTask?.description ?? \"\"\n                showsSelectedTaskDetails = false"), "Continue editing must stay on the current result")

    let models = source("macOS-Client/Sources/Views/ModelSettingsView.swift")
    check(models.contains("onOpenCapabilities"), "Each Agent must provide a direct capabilities action")
    check(models.contains("showingUnconfiguredProviders.toggle()"), "Unconfigured providers must have an explicit expansion action")
    let message = source("macOS-Client/Sources/Views/MainPanelChatMessage.swift")
    check(message.contains("isCopyFocused"), "Keyboard-focused copy action must remain visible")

    let app = source("macOS-Client/Sources/AcrossAgentsAssistantApp.swift")
    check(
        app.contains("TrafficLightHider(resetsRestoredZoomedFrame: false)"),
        "Settings must not reuse main-window frame recovery"
    )

    let session = source("macOS-Client/Sources/ViewModels/SessionViewModel.swift")
    let tasks = source("macOS-Client/Sources/ViewModels/TaskOrchestrationViewModel.swift")
    let mainSidebar = source("macOS-Client/Sources/Views/MainPanelSidebar.swift")
    check(mainPanel.contains("onChange(of: viewModel.activeProjectPath)"), "Project changes must refresh work scope")
    check(mainPanel.contains("onChange(of: taskOrchestrationViewModel.selectedTask?.projectDir)"), "Selected work must activate its owning project")
    check(mainSidebar.contains("updateProjectDirectoryFilter(project.path)"), "Sidebar project selection must exit stale work details")
    check(session.contains("func activateProject(matchingDirectory directory: String?)"), "Sessions must support project activation from work ownership")
    check(tasks.contains("URLQueryItem(name: \"project_dir\""), "Recent work must request the active project only")

    let review = source("macOS-Client/Sources/Views/MinimalReviewInboxView.swift")
    let project = source("macOS-Client/Sources/Views/MinimalProjectWorkspaceView.swift")
    check(!runs.contains("NavigationSplitView"), "Run history must not install a system window sidebar")
    check(!review.contains("NavigationSplitView"), "Review inbox must not install a system window sidebar")
    check(review.contains("review.count.one"), "Review count must use a grammatical singular label")
    check(!project.contains("NavigationSplitView"), "Project workspace must not install a system window sidebar")
    check(project.contains("HSplitView"), "Project workspace must retain its fixed operational panes")
    check(runs.contains("private var runHistoryDrawer"), "Run history must use the floating drawer")
    check(review.contains("private var reviewInboxDrawer"), "Review inbox must use the floating drawer")
    check(runs.contains(".onTapGesture { setRunHistoryVisible(false) }"), "Floating run history must close when clicking outside")

    let mainSidebarSource = source("macOS-Client/Sources/Views/MainPanelSidebar.swift")
    check(mainSidebarSource.contains("setContextDrawerVisible(!showsContextDrawer)"), "Context drawer toggle must live in the main sidebar chrome")
}

@main
struct AppleMinimalUIBehavior {
    static func main() {
        checkNavigationShape()
        checkWindowChrome()
        checkCustomTrafficLights()
        checkPrimaryPageVisualLanguage()
        checkCriticalInteractionContracts()
        print("AppleMinimalUIBehavior passed")
    }
}
