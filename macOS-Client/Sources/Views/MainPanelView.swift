import SwiftUI

struct FileTreeView: View {
    let item: FileItemModel
    let depth: Int
    @ObservedObject var viewModel: SessionViewModel
    @Environment(\.colorScheme) var colorScheme

    var body: some View {
        let isSelected = item.id == viewModel.selectedFileId
        let highlightColor = colorScheme == .dark ? Color.legacyTreeSelectedDark : Color.legacyTreeSelectedLight

        HStack(spacing: 6) {
            Spacer().frame(width: CGFloat(depth * 8))

            if item.isFolder {
                Image(systemName: item.isExpanded ? "chevron.down" : "chevron.right")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                    .frame(width: 12)

                SVGIconView(name: item.isExpanded ? "icon.14.explorer.folder.open" : "icon.14.explorer.folder.closed", size: 14)
            } else {
                Spacer().frame(width: 12)

                SVGIconView(name: getFileIconName(fileName: item.name), size: 14)
            }

            Text(item.name)
                .font(.system(size: 12))
                .foregroundColor(Color.primary.opacity(0.8))
                .fixedSize(horizontal: true, vertical: false)

            Spacer()
        }
        .padding(.vertical, 4)
        .padding(.horizontal, 8)
        .background(isSelected ? highlightColor : Color.clear)
        .cornerRadius(4)
        .padding(.horizontal, 8)
        .contentShape(Rectangle())
        .onTapGesture {
            viewModel.selectedFileId = item.id
            if item.isFolder {
                withAnimation(.easeInOut(duration: 0.2)) {
                    viewModel.toggleFolderExpansion(for: item)
                }
            }
        }
        .id(item.id)
        .onDrag {
            // Provide the actual file URL for dragging.
            return NSItemProvider(object: NSURL(fileURLWithPath: item.path))
        }
    }
}

struct SVGIconView: View {
    let name: String
    var size: CGFloat = 14

    @State private var nsImage: NSImage?

    var body: some View {
        Group {
            if let img = nsImage {
                Image(nsImage: img)
                    .resizable()
                    .scaledToFit()
                    .frame(width: size, height: size)
            } else {
                Image(systemName: "doc")
                    .resizable()
                    .scaledToFit()
                    .frame(width: size, height: size)
                    .foregroundColor(.secondary)
            }
        }
        .onAppear(perform: loadImage)
    }

    private func loadImage() {
        if let url = bundledAssetURL(named: name, withExtension: "svg", subdirectory: "Assets/icons") {
            if let data = try? Data(contentsOf: url) {
                self.nsImage = NSImage(data: data)
            }
        }
    }
}

func getFileIconName(fileName: String) -> String {
    let lowerName = fileName.lowercased()

    // Check specific file names
    if lowerName == "readme.md" || lowerName == "readme" { return "icon.14.explorer.file.readme" }
    if lowerName == "package.json" { return "icon.14.explorer.npm" }
    if lowerName == "dockerfile" { return "icon.14.explorer.type.docker" }

    // Check extensions
    let ext = URL(fileURLWithPath: fileName).pathExtension.lowercased()
    switch ext {
    case "js": return "icon.14.explorer.lang.js"
    case "ts": return "icon.14.explorer.lang.ts"
    case "py": return "icon.14.explorer.lang.python"
    case "json": return "icon.14.explorer.lang.json"
    case "md": return "icon.14.explorer.type.markdown"
    case "swift": return "icon.14.explorer.type.class"
    case "cpp", "cc", "cxx": return "icon.14.explorer.lang.c++"
    case "c": return "icon.14.explorer.lang.c"
    case "h", "hpp": return "icon.14.explorer.type.h"
    case "go": return "icon.14.explorer.lang.go"
    case "rs": return "icon.14.explorer.lang.rs"
    case "html", "htm": return "icon.14.explorer.lang.html"
    case "css": return "icon.14.explorer.lang.css"
    case "vue": return "icon.14.explorer.lang.vue"
    case "txt": return "icon.14.explorer.type.txt"
    case "png", "jpg", "jpeg", "gif", "ico": return "icon.14.explorer.type.image"
    case "svg": return "icon.14.explorer.type.svg"
    case "sh", "bash", "zsh": return "icon.14.explorer.type.bash"
    case "pdf": return "icon.14.explorer.type.pdf"
    case "docx", "doc": return "icon.14.explorer.type.docx"
    case "xlsx", "xls", "csv": return "icon.14.explorer.type.xlsx"
    case "yaml", "yml": return "icon.14.explorer.lang.yaml"
    case "xml": return "icon.14.explorer.lang.xml"
    case "java": return "icon.14.explorer.lang.java"
    default: return "icon.14.explorer.file"
    }
}

struct MainPanelView: View {
    @ObservedObject var viewModel: SessionViewModel
    @Environment(\.colorScheme) var colorScheme

    // Dynamic color helpers based on color scheme
    private var bgColor: Color { colorScheme == .dark ? .legacyBgDark : .legacyBgLight }
    private var sidebarBgColor: Color { bgColor }
    private var textColor: Color { colorScheme == .dark ? .legacyTextDark : .legacyTextLight }
    private var accentColor: Color { colorScheme == .dark ? .legacyAccentDark : .legacyAccentLight }
    private var userMsgBgColor: Color { colorScheme == .dark ? .legacyUserMsgBgDark : .legacyUserMsgBgLight }
    private var userMsgTextColor: Color { colorScheme == .dark ? .white : .black }
    private var agentMsgTextColor: Color { colorScheme == .dark ? .white : .black }

    // State for interactive buttons
    @State private var isContinuousMode = false
    @State private var activeSettingsHubTab: SettingsHubTab? = nil
    @State private var showTaskOrchestration = false
    @StateObject private var taskOrchestrationViewModel = TaskOrchestrationViewModel()
    @EnvironmentObject var settingsViewModel: SettingsViewModel
    @EnvironmentObject var appPreferences: AppPreferences
    @State private var showProjectTree: Bool = false
    @State private var selectedSessionIds: Set<String> = []
    @State private var renamingSessionId: String? = nil
    @State private var renameText: String = ""
    @State private var inputResignResponder = false
    @AppStorage("sidebarWidth") private var sidebarWidth: Double = 250
    @State private var dragStartWidth: Double = 0
    @State private var scrollAnchorId: String? = nil
    @State private var mcpPollingTimer: Timer? = nil
    @State private var isNewProjectMenuHovered = false

    private var visibleLocalAgents: [AgentModel] {
        let ids = Set(settingsViewModel.availableLocalAgents.map(\.id))
        return viewModel.agents.filter { $0.type == .local && ids.contains($0.id) }
    }

    private var visibleCloudAgents: [AgentModel] {
        let ids = Set(settingsViewModel.availableCloudLLMs.map(\.id))
        return viewModel.agents.filter { $0.type == .cloudLLM && ids.contains($0.id) }
    }

    private var visibleAgentsForSelection: [AgentModel] {
        visibleLocalAgents + visibleCloudAgents
    }

    private var canUseAgentFeatures: Bool {
        settingsViewModel.availabilityBootstrapState == .ready && settingsViewModel.hasAnyAvailableAgents
    }

    private var taskEntryDisabled: Bool {
        !canUseAgentFeatures
    }

    private var currentAgentTitle: String {
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

    private var inputPlaceholder: String {
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

    private var canSubmitInput: Bool {
        let hasText = !viewModel.inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        return (hasText || !viewModel.attachedFiles.isEmpty)
            && viewModel.pendingApproval == nil
            && canUseAgentFeatures
    }

    var body: some View {
        HStack(spacing: 0) {
            leftSidebar
            centerResizer
            centerArea
            if settingsViewModel.shouldShowRightSidebar {
                rightResizer
                rightSidebar
            }
        }
        .frame(minWidth: 900, idealWidth: 1200, minHeight: 600, idealHeight: 800)
        .background(bgColor.ignoresSafeArea())
        .ignoresSafeArea(.all, edges: .top)
        .onAppear {
            AppAppearanceController.apply(appPreferences.colorSchemeMode)
            syncPreferencesToSessionViewModel()
            settingsViewModel.bootstrapFromPersistedSettings()
            loadInitialDataWhenBackendAvailable()
            mcpPollingTimer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { _ in
                viewModel.fetchMCPContexts()
            }
            syncSelectedAgentToAvailability()
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
            Group {
                if let activeSettingsHubTab {
                    SettingsHubView(
                        settingsViewModel: settingsViewModel,
                        preferences: appPreferences,
                        selectedTab: activeSettingsHubTab,
                        onClose: { self.activeSettingsHubTab = nil }
                    )
                }
                if showTaskOrchestration {
                    TaskOrchestrationView(viewModel: taskOrchestrationViewModel, settingsVM: settingsViewModel, onClose: { showTaskOrchestration = false })
                }
                if let request = viewModel.pendingApproval {
                    ZStack {
                        Color.black.opacity(0.4).ignoresSafeArea()
                        ApprovalDialogView(request: request) { decision in
                            viewModel.submitDecision(decision: decision)
                        }
                    }
                }

                if viewModel.showPermissionAlert {
                    ZStack {
                        Color.black.opacity(0.4).ignoresSafeArea()
                        VStack(spacing: 20) {
                            Image(systemName: "lock.shield.fill")
                                .font(.system(size: 40))
                                .foregroundColor(.orange)

                            Text(appPreferences.text("accessibility.title"))
                                .font(.headline)

                            Text(appPreferences.text("accessibility.message"))
                                .font(.subheadline)
                                .multilineTextAlignment(.center)
                                .padding(.horizontal)

                            HStack(spacing: 16) {
                                Button(appPreferences.text("system.cancel")) {
                                    viewModel.showPermissionAlert = false
                                    viewModel.submitDecision(decision: "reject")
                                }
                                .buttonStyle(.plain)
                                .padding(.horizontal, 20)
                                .padding(.vertical, 8)
                                .background(Color.gray.opacity(0.2))
                                .cornerRadius(8)

                                Button(appPreferences.text("system.openSystemSettings")) {
                                    viewModel.openAccessibilitySettings()
                                }
                                .buttonStyle(.plain)
                                .padding(.horizontal, 20)
                                .padding(.vertical, 8)
                                .background(Color.blue)
                                .foregroundColor(.white)
                                .cornerRadius(8)
                            }
                        }
                        .padding(30)
                        .frame(width: 350)
                        .background(VisualEffectView())
                        .cornerRadius(16)
                        .shadow(color: Color.black.opacity(0.2), radius: 20, x: 0, y: 10)
                    }
                }
            }
        )
    }

    // MARK: - Sub-views

    private var leftSidebar: some View {
        VStack(spacing: 0) {
            HStack {
                CustomTrafficLights()
                Spacer()

                if !viewModel.activeMCPContexts.isEmpty {
                    HStack(spacing: 4) {
                        ForEach(viewModel.activeMCPContexts) { context in
                            HStack(spacing: 3) {
                                Image(systemName: "externaldrive.fill")
                                    .font(.system(size: 9))
                                Text(context.name)
                                    .font(.system(size: 9))
                                if let dbPath = context.dbPath {
                                    Text("(\(URL(fileURLWithPath: dbPath).lastPathComponent))")
                                        .font(.system(size: 8))
                                        .foregroundColor(.secondary)
                                }
                            }
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color.accentColor.opacity(0.15))
                            .cornerRadius(4)
                        }
                    }
                    .padding(.leading, 8)
                }
            }
            .padding(.horizontal, 16)
            .frame(height: 56)
            .background(WindowDragView().contentShape(Rectangle()))

            Divider().opacity(0.5)

            if showProjectTree {
                projectTreeSidebar
            } else {
                projectChatSidebar
            }
        }
        .frame(width: CGFloat(sidebarWidth))
        .frame(maxHeight: .infinity)
        .background(sidebarBgColor)
    }

    private var projectChatSidebar: some View {
        VStack(spacing: 0) {
            HStack {
                Text(appPreferences.text("project.title"))
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(.secondary.opacity(0.75))
                Spacer()
                Menu {
                    Button(appPreferences.text("project.newBlank")) {
                        viewModel.createBlankProjectPrompt()
                    }
                    Button(appPreferences.text("project.useExisting")) {
                        viewModel.chooseExistingProjectFolder()
                    }
                } label: {
                    InteractiveIconLabel(
                        systemName: "folder.badge.plus",
                        help: appPreferences.text("project.new"),
                        iconSize: 13,
                        weight: .semibold,
                        frameSize: 24,
                        externalIsHovered: isNewProjectMenuHovered
                    )
                }
                .menuStyle(.borderlessButton)
                .menuIndicator(.hidden)
                .fixedSize()
                .onHover { hovering in
                    isNewProjectMenuHovered = hovering
                }
            }
            .padding(.leading, 16)
            .padding(.trailing, 6)
            .padding(.top, 12)
            .padding(.bottom, 6)

            if viewModel.projectsLoading && viewModel.projects.isEmpty {
                VStack(spacing: 8) {
                    ProgressView()
                        .controlSize(.small)
                    Text(appPreferences.text("project.loading"))
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 4) {
                        ForEach(viewModel.projects) { project in
                            ProjectSidebarRow(
                                project: project,
                                activeProjectId: viewModel.activeProjectId,
                                currentSessionId: viewModel.currentSessionId,
                                selectedSessionIds: selectedSessionIds,
                                onSelectProject: {
                                    if let firstSession = project.sessions.first {
                                        selectedSessionIds = [firstSession.session_id]
                                        viewModel.switchToSession(firstSession, in: project)
                                    } else {
                                        selectedSessionIds.removeAll()
                                        viewModel.startNewSession(in: project)
                                    }
                                },
                                onOpenTree: {
                                    viewModel.loadProjectDirectory(project)
                                    withAnimation(.easeInOut(duration: 0.2)) {
                                        showProjectTree = true
                                    }
                                },
                                onNewChat: {
                                    activeSettingsHubTab = nil
                                    showTaskOrchestration = false
                                    viewModel.startNewSession(in: project)
                                },
                                onSelectSession: { session in
                                    selectedSessionIds = [session.session_id]
                                    viewModel.switchToSession(session, in: project)
                                },
                                onDeleteSession: { session in
                                    viewModel.deleteSession(session.session_id)
                                },
                                onRenameSession: { session in
                                    renamingSessionId = session.session_id
                                    renameText = session.name ?? ""
                                },
                                onPinProject: {
                                    viewModel.setProjectPinned(project.id, pinned: !project.is_pinned)
                                },
                                onPinSession: { session in
                                    viewModel.setSessionPinned(session.session_id, pinned: !session.is_pinned)
                                }
                            )
                        }
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                }
            }
        }
    }

    private var projectTreeSidebar: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Button(action: {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        showProjectTree = false
                    }
                }) {
                    Image(systemName: "chevron.left")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(.secondary)
                        .frame(width: 36, height: 32)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .help(appPreferences.text("project.back"))

                VStack(alignment: .leading, spacing: 1) {
                    Text(viewModel.currentFileTreeRootName ?? viewModel.activeProjectName ?? "Project")
                        .font(.system(size: 12, weight: .semibold))
                        .lineLimit(1)
                    Text(viewModel.currentFileTreeRootPath ?? viewModel.activeProjectPath ?? "")
                        .font(.system(size: 9))
                        .foregroundColor(.secondary.opacity(0.65))
                        .lineLimit(1)
                }

                Spacer()

                Button(action: { withAnimation(.easeInOut(duration: 0.2)) { viewModel.collapseAllFolders() } }) {
                    Image(systemName: "arrow.up.right.and.arrow.down.left.rectangle").foregroundColor(.gray)
                }.buttonStyle(.plain).help(appPreferences.text("project.collapseAll"))

                Button(action: { withAnimation(.easeInOut(duration: 0.2)) { viewModel.refreshFileTree() } }) {
                    Image(systemName: "arrow.clockwise").foregroundColor(.gray)
                }.buttonStyle(.plain).help(appPreferences.text("project.refresh"))

                Button(action: { viewModel.toggleHiddenFiles() }) {
                    Image(systemName: viewModel.showHiddenFiles ? "eye" : "eye.slash").foregroundColor(.gray)
                }.buttonStyle(.plain).help(viewModel.showHiddenFiles ? appPreferences.text("project.hideHidden") : appPreferences.text("project.showHidden"))
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)

            Divider().opacity(0.5)

            GeometryReader { geo in
                ScrollView([.vertical, .horizontal], showsIndicators: false) {
                    LazyVStack(alignment: .leading, spacing: 0) {
                        ForEach(viewModel.flatFileTree, id: \.node.id) { element in
                            FileTreeView(item: element.node, depth: element.depth, viewModel: viewModel)
                        }
                    }
                    .scrollTargetLayout()
                    .padding(.top, 8)
                    .frame(minWidth: max(CGFloat(sidebarWidth), geo.size.width), minHeight: geo.size.height, alignment: .topLeading)
                }
                .scrollPosition(id: $scrollAnchorId)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private var centerResizer: some View {
        Rectangle()
            .fill(Color.gray.opacity(0.1))
            .frame(width: 1)
            .overlay(
                Rectangle()
                    .fill(Color.black.opacity(0.001))
                    .frame(width: 16)
                    .contentShape(Rectangle())
                    .onHover { hovering in
                        if hovering { NSCursor.resizeLeftRight.push() }
                        else { NSCursor.pop() }
                    }
                    .gesture(
                        DragGesture(coordinateSpace: .global)
                            .onChanged { value in
                                if dragStartWidth == 0 { dragStartWidth = sidebarWidth }
                                sidebarWidth = max(150, min(dragStartWidth + Double(value.translation.width), 600))
                            }
                            .onEnded { _ in
                                dragStartWidth = 0
                                NSCursor.pop()
                            }
                    )
            )
            .zIndex(100)
    }

    private var centerArea: some View {
        VStack(spacing: 0) {
            headerBar
                .zIndex(1_000)
            Divider().opacity(0.5)
                .zIndex(900)
            contentArea
                .zIndex(0)
            inputArea
                .zIndex(1_000)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(bgColor)
        .contentShape(Rectangle())
        .onTapGesture { NSApp.keyWindow?.makeFirstResponder(nil) }
    }

    private var headerBar: some View {
        HStack {
            Text(currentAgentTitle)
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(textColor)
            Spacer()
            HStack(spacing: 12) {
                InteractiveIconButton(systemName: "mic", help: appPreferences.text("toolbar.voiceInput"), iconSize: 14, frameSize: 24) {}
                InteractiveIconButton(
                    systemName: isContinuousMode ? "waveform.circle.fill" : "waveform",
                    help: isContinuousMode ? appPreferences.text("toolbar.continuous.disable") : appPreferences.text("toolbar.continuous.enable"),
                    iconSize: 14,
                    foregroundColor: isContinuousMode ? .blue : .secondary,
                    frameSize: 24
                ) {
                    isContinuousMode.toggle()
                }
                InteractiveIconButton(
                    systemName: viewModel.isMuted ? "speaker.slash.fill" : "speaker.wave.2",
                    help: viewModel.isMuted ? appPreferences.text("toolbar.unmute") : appPreferences.text("toolbar.mute"),
                    iconSize: 14,
                    foregroundColor: viewModel.isMuted ? .red : .secondary,
                    frameSize: 24
                ) {
                    viewModel.isMuted.toggle()
                }
                InteractiveIconButton(systemName: "doc.on.clipboard", help: appPreferences.text("toolbar.copyConversation"), iconSize: 13, frameSize: 24) {
                    viewModel.copyFullConversation()
                }
                InteractiveIconButton(
                    systemName: "list.bullet.rectangle",
                    help: taskEntryDisabled ? appPreferences.text("toolbar.tasks.disabled") : appPreferences.text("toolbar.tasks"),
                    iconSize: 14,
                    foregroundColor: .gray,
                    frameSize: 24,
                    isDisabled: taskEntryDisabled
                ) {
                    activeSettingsHubTab = nil
                    showTaskOrchestration = true
                }
                InteractiveIconButton(systemName: "cpu", help: appPreferences.text("toolbar.models"), iconSize: 14, foregroundColor: .gray, frameSize: 24) {
                    showTaskOrchestration = false
                    activeSettingsHubTab = .models
                }
                InteractiveIconButton(systemName: "square.grid.2x2", help: appPreferences.text("toolbar.mcp"), iconSize: 15, foregroundColor: .gray, frameSize: 24) {
                    showTaskOrchestration = false
                    activeSettingsHubTab = .mcp
                }
                InteractiveIconButton(systemName: "wrench.and.screwdriver.fill", help: appPreferences.text("toolbar.tools"), iconSize: 14, foregroundColor: .gray, frameSize: 24) {
                    showTaskOrchestration = false
                    activeSettingsHubTab = .tools
                }
                InteractiveIconButton(systemName: "gearshape", help: appPreferences.text("toolbar.settings"), iconSize: 15, foregroundColor: .gray, frameSize: 24) {
                    showTaskOrchestration = false
                    activeSettingsHubTab = activeSettingsHubTab == .settings ? nil : .settings
                }
            }
            .font(.system(size: 14))
        }
        .padding(.horizontal, 20)
        .frame(height: 56)
        .background(ZStack { bgColor; WindowDragView().contentShape(Rectangle()) })
    }

    @ViewBuilder
    private var contentArea: some View {
        switch settingsViewModel.availabilityBootstrapState {
        case .loading:
            availabilityLoadingView
        case .empty:
            onboardingView
        case .ready:
            messageList
        }
    }

    private var messageList: some View {
        ScrollView {
            ScrollViewReader { proxy in
                VStack(alignment: .leading, spacing: 16) {
                    if viewModel.hasMoreHistory {
                        HStack {
                            Spacer()
                            if viewModel.isLoadingMoreHistory {
                                ProgressView().controlSize(.small)
                                    .padding(.vertical, 4)
                            } else {
                                Button(action: { viewModel.loadMoreHistory() }) {
                                    Text(appPreferences.text("chat.loadEarlier"))
                                        .font(.system(size: 11))
                                        .foregroundColor(.accentColor)
                                }
                                .buttonStyle(.plain)
                                .padding(.vertical, 4)
                            }
                            Spacer()
                        }
                        .id("load-more")
                    }
                    ForEach(viewModel.messages) { message in
                        LegacyMessageBubble(
                            message: message, userBgColor: userMsgBgColor,
                            userTextColor: userMsgTextColor, agentTextColor: agentMsgTextColor
                        ).id(message.id)
                    }
                    if viewModel.isProcessing {
                        HStack(spacing: 6) {
                            ProgressView().controlSize(.small)
                            Text(appPreferences.text("chat.thinking")).font(.system(size: 11)).foregroundColor(.secondary)
                            Spacer()
                        }
                        .offset(x: -2).padding(.vertical, 4)
                        .id("processing")
                    }
                }
                .padding(EdgeInsets(top: 8, leading: 24, bottom: 24, trailing: 24))
                .onChange(of: viewModel.messages.count) {
                    if !viewModel.isLoadingMoreHistory {
                        if let lastId = viewModel.messages.last?.id {
                            proxy.scrollTo(lastId, anchor: .bottom)
                        }
                    }
                }
                .onChange(of: viewModel.isProcessing) {
                    if viewModel.isProcessing { proxy.scrollTo("processing", anchor: .bottom) }
                }
            }
        }
    }

    private var inputArea: some View {
        HStack(alignment: .center, spacing: 10) {
            InteractiveIconButton(
                systemName: "camera.viewfinder",
                help: appPreferences.text("screenshot.ocr"),
                iconSize: 14,
                foregroundColor: .secondary,
                frameSize: 24,
                isDisabled: !canUseAgentFeatures
            ) {
                viewModel.requestManualScreenshot()
            }

            InteractiveIconButton(
                systemName: "photo.badge.plus",
                help: appPreferences.text("screenshot.attach"),
                iconSize: 14,
                foregroundColor: .secondary,
                frameSize: 24,
                isDisabled: !canUseAgentFeatures
            ) {
                viewModel.requestScreenshotAttachment()
            }

            InteractiveIconButton(
                systemName: "plus",
                help: appPreferences.text("attachment.addFiles"),
                iconSize: 16,
                foregroundColor: .secondary,
                frameSize: 24,
                isDisabled: !canUseAgentFeatures
            ) {
                viewModel.requestFileAttachment()
            }

            VStack(alignment: .leading, spacing: 6) {
                if let notice = viewModel.transientInputNotice {
                    Text(notice)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                        .transition(.opacity)
                }
                if !viewModel.attachedFiles.isEmpty {
                    inputAttachmentShelf
                }
                HStack {
                    ZStack(alignment: .topLeading) {
                        MacEditorView(
                            text: $viewModel.inputText, attachedFiles: $viewModel.attachedFiles,
                            onSubmit: { if viewModel.pendingApproval == nil { submit() } },
                            onNavigateHistory: { up in viewModel.navigateHistory(up: up) },
                            textColor: NSColor(textColor)
                        ).disabled(viewModel.pendingApproval != nil || !canUseAgentFeatures)
                        if viewModel.inputText.isEmpty {
                            Text(inputPlaceholder)
                                .font(.system(size: 13)).foregroundColor(.secondary.opacity(0.5))
                                .padding(.leading, 4).padding(.top, 2).allowsHitTesting(false)
                        }
                    }
                    .fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(.vertical, 6).padding(.horizontal, 8)
            .background(Color.black.opacity(0.05)).cornerRadius(14)
            .frame(minHeight: 32, alignment: .center)

            if viewModel.isProcessing {
                Button(action: { viewModel.cancelGeneration() }) {
                    Image(systemName: "stop.circle.fill")
                        .font(.system(size: 14)).foregroundColor(accentColor)
                        .frame(width: 32, height: 32)
                        .background(Color.black.opacity(0.05)).cornerRadius(6)
                }.buttonStyle(.plain).help(appPreferences.text("chat.stop"))
            } else {
                Button(action: submit) {
                    Image(systemName: "paperplane.fill")
                        .font(.system(size: 14))
                        .foregroundColor(canSubmitInput ? accentColor : .secondary)
                        .frame(width: 32, height: 32)
                        .background(Color.black.opacity(0.05)).cornerRadius(6)
                }
                .buttonStyle(.plain)
                .disabled(!canSubmitInput)
            }
        }
        .padding(EdgeInsets(top: 12, leading: 24, bottom: 16, trailing: 24))
        .background(bgColor)
    }

    private var inputAttachmentShelf: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(viewModel.attachedFiles) { file in
                    InputAttachmentPreview(file: file) {
                        removeAttachedFile(file)
                    }
                }
            }
            .padding(.vertical, 2)
        }
        .frame(height: 62)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var rightResizer: some View { Divider().opacity(0.5) }

    private var rightSidebar: some View {
        HStack(spacing: 0) {
            if !visibleLocalAgents.isEmpty {
                VStack(spacing: 20) {
                    ForEach(visibleLocalAgents) { agent in
                        AgentSidebarIcon(agent: agent, isActive: agent.id == viewModel.selectedAgentId) {
                            withAnimation(.easeInOut(duration: 0.2)) { viewModel.selectedAgentId = agent.id }
                        }
                    }
                    Spacer()
                }
                .frame(width: 60).padding(.top, 24).padding(.horizontal, 8)
            }

            if !visibleLocalAgents.isEmpty && !visibleCloudAgents.isEmpty {
                Rectangle().fill(Color(NSColor.separatorColor).opacity(0.5)).frame(width: 1)
            }

            if !visibleCloudAgents.isEmpty {
                VStack(spacing: 20) {
                    ForEach(visibleCloudAgents) { agent in
                        AgentSidebarIcon(agent: agent, isActive: agent.id == viewModel.selectedAgentId) {
                            withAnimation(.easeInOut(duration: 0.2)) { viewModel.selectedAgentId = agent.id }
                        }
                    }
                    Spacer()
                }
                .frame(width: 60).padding(.top, 24).padding(.horizontal, 8)
            }
        }
        .frame(width: visibleLocalAgents.isEmpty || visibleCloudAgents.isEmpty ? 76 : 160)
        .frame(maxHeight: .infinity)
        .background(sidebarBgColor)
    }

    private var onboardingView: some View {
        VStack(spacing: 16) {
            Spacer()
            Image(systemName: "sparkles.rectangle.stack")
                .font(.system(size: 34))
                .foregroundColor(.secondary.opacity(0.8))
            Text(appPreferences.text("onboarding.noAgent"))
                .font(.system(size: 22, weight: .semibold))
                .foregroundColor(textColor)
            Text(appPreferences.text("onboarding.noAgent.help"))
                .font(.system(size: 14))
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 420)
            Button(action: { activeSettingsHubTab = .models }) {
                Text(appPreferences.text("onboarding.openModels"))
                    .font(.system(size: 14, weight: .medium))
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .background(accentColor.opacity(0.15))
                    .foregroundColor(accentColor)
                    .cornerRadius(10)
            }
            .buttonStyle(.plain)
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(.horizontal, 24)
    }

    private var availabilityLoadingView: some View {
        VStack(spacing: 14) {
            Spacer()
            ProgressView()
                .controlSize(.regular)
            Text(appPreferences.text("onboarding.checking"))
                .font(.system(size: 14))
                .foregroundColor(.secondary)
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func syncSelectedAgentToAvailability() {
        guard settingsViewModel.availabilityBootstrapState == .ready else { return }
        guard let fallback = settingsViewModel.preferredAgentId(current: viewModel.selectedAgentId) else { return }
        if viewModel.selectedAgentId != fallback {
            viewModel.selectedAgentId = fallback
        }
    }

    private func loadInitialDataWhenBackendAvailable() {
        guard settingsViewModel.availabilityBootstrapState != .loading else { return }
        viewModel.loadInitialDataIfNeeded()
    }

    private func syncPreferencesToSessionViewModel() {
        viewModel.speechPlaybackSettings = SpeechPlaybackSettings(
            autoReadReplies: appPreferences.autoReadReplies,
            voiceSource: appPreferences.voiceSource,
            chosenVoiceIdentifier: appPreferences.chosenVoiceIdentifier,
            fallbackLanguage: appPreferences.resolvedLocaleIdentifier,
            speechRate: appPreferences.speechRate,
            speechVolume: appPreferences.speechVolume
        )
        viewModel.includeActiveAppContext = appPreferences.includeActiveAppContext
        viewModel.shouldRememberSelectedAgent = appPreferences.rememberLastAgent
        viewModel.screenshotOCRPermissionTip = appPreferences.text("screenshot.permission.ocr")
        viewModel.screenshotAttachmentPermissionTip = appPreferences.text("screenshot.permission.attach")
        viewModel.screenshotClipboardPermissionTip = appPreferences.text("screenshot.permission.copy")
        viewModel.screenshotCopiedNotice = appPreferences.text("screenshot.copied")
        viewModel.screenshotCancelledNotice = appPreferences.text("screenshot.cancelled")
        viewModel.screenshotCopyFailedNotice = appPreferences.text("screenshot.copyFailed")
        if appPreferences.rememberLastAgent {
            UserDefaults.standard.set(viewModel.selectedAgentId, forKey: "lastSelectedAgentId")
        } else {
            UserDefaults.standard.removeObject(forKey: "lastSelectedAgentId")
        }
    }

    private func handleChatEnsureFailure(_ message: String) {
        viewModel.showErrorMessage(message)
    }

    private func submit() {
        guard !viewModel.isProcessing else { return }
        let text = viewModel.inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        let attachedFiles = viewModel.attachedFiles
        guard !text.isEmpty || !attachedFiles.isEmpty else { return }
        guard canUseAgentFeatures else { return }

        Task {
            if let errorMessage = await settingsViewModel.ensureChatAgentReady(agentId: viewModel.selectedAgentId) {
                await MainActor.run {
                    handleChatEnsureFailure(errorMessage)
                }
                return
            }

            await MainActor.run {
                viewModel.sendMessage(text, attachedFiles: attachedFiles)
                viewModel.inputText = ""
                viewModel.attachedFiles = []
            }
        }
    }

    private func removeAttachedFile(_ file: AttachedFile) {
        viewModel.attachedFiles.removeAll { $0.id == file.id }
    }

    private func handleSessionClick(_ session: SessionInfo) {
        let flags = NSApp.currentEvent?.modifierFlags ?? []
        if flags.contains(.command) {
            if selectedSessionIds.contains(session.session_id) {
                selectedSessionIds.remove(session.session_id)
            } else {
                selectedSessionIds.insert(session.session_id)
            }
        } else if flags.contains(.shift), let firstId = selectedSessionIds.first,
                  let firstIdx = viewModel.sessions.firstIndex(where: { $0.session_id == firstId }),
                  let clickedIdx = viewModel.sessions.firstIndex(where: { $0.session_id == session.session_id }) {
            let range = min(firstIdx, clickedIdx)...max(firstIdx, clickedIdx)
            for i in range {
                selectedSessionIds.insert(viewModel.sessions[i].session_id)
            }
        } else {
            selectedSessionIds = [session.session_id]
            viewModel.switchToSession(session.session_id)
        }
    }

}

// MARK: - Project Sidebar

struct ProjectSidebarRow: View {
    let project: ProjectInfo
    let activeProjectId: String?
    let currentSessionId: String
    let selectedSessionIds: Set<String>
    let onSelectProject: () -> Void
    let onOpenTree: () -> Void
    let onNewChat: () -> Void
    let onSelectSession: (SessionInfo) -> Void
    let onDeleteSession: (SessionInfo) -> Void
    let onRenameSession: (SessionInfo) -> Void
    let onPinProject: () -> Void
    let onPinSession: (SessionInfo) -> Void

    @State private var isHovered = false
    @EnvironmentObject private var appPreferences: AppPreferences

    private var isActive: Bool {
        project.id == activeProjectId
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 8) {
                Image(systemName: isActive ? "folder.fill" : "folder")
                    .font(.system(size: 12))
                    .foregroundColor(.secondary.opacity(0.75))
                    .frame(width: 16)

                Text(project.name)
                    .font(.system(size: 12, weight: .medium))
                    .lineLimit(1)
                    .foregroundColor(.secondary.opacity(isHovered ? 0.95 : 0.86))

                if project.is_pinned {
                    Image(systemName: "pin.fill")
                        .font(.system(size: 8, weight: .semibold))
                        .foregroundColor(.secondary.opacity(0.72))
                }

                Spacer(minLength: 4)

                HStack(spacing: 2) {
                    Button(action: onPinProject) {
                        Image(systemName: project.is_pinned ? "pin.slash" : "pin")
                            .font(.system(size: 11, weight: .semibold))
                            .frame(width: 22, height: 22)
                    }
                    .buttonStyle(.plain)
                    .help(project.is_pinned ? appPreferences.text("project.unpin") : appPreferences.text("project.pin"))

                    Button(action: onOpenTree) {
                        Image(systemName: "line.3.horizontal")
                            .font(.system(size: 11, weight: .semibold))
                            .frame(width: 22, height: 22)
                    }
                    .buttonStyle(.plain)
                    .help(appPreferences.text("project.openTree"))

                    Button(action: onNewChat) {
                        Image(systemName: "square.and.pencil")
                            .font(.system(size: 11, weight: .semibold))
                            .frame(width: 22, height: 22)
                    }
                    .buttonStyle(.plain)
                    .help(appPreferences.text("project.newChatInProject"))
                }
                .foregroundColor(.secondary)
                .opacity(isHovered ? 1 : 0)
                .allowsHitTesting(isHovered)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.leading, 10)
            .padding(.trailing, 2)
            .padding(.vertical, 7)
            .background(
                RoundedRectangle(cornerRadius: 7)
                    .fill(isHovered ? Color.white.opacity(0.05) : Color.clear)
            )
            .contentShape(Rectangle())
            .onTapGesture(perform: onSelectProject)
            .contextMenu {
                Button(project.is_pinned ? appPreferences.text("project.unpin") : appPreferences.text("project.pin"), action: onPinProject)
                Divider()
                Button(appPreferences.text("project.newChat"), action: onNewChat)
                Button(appPreferences.text("project.openTree"), action: onOpenTree)
            }
            .onHover { hovering in
                withAnimation(.easeInOut(duration: 0.12)) {
                    isHovered = hovering
                }
            }

            if isActive {
                Text(project.path)
                    .font(.system(size: 9))
                    .foregroundColor(.secondary.opacity(0.55))
                    .lineLimit(1)
                    .padding(.leading, 34)
                    .padding(.trailing, 8)
                    .padding(.bottom, 2)
            }

            if project.sessions.isEmpty {
                Text(appPreferences.text("project.noChats"))
                    .font(.system(size: 10))
                    .foregroundColor(.secondary.opacity(0.45))
                    .padding(.leading, 34)
                    .padding(.vertical, 4)
            } else {
                VStack(alignment: .leading, spacing: 1) {
                    ForEach(project.sessions) { session in
                        CompactProjectSessionRow(
                            session: session,
                            isActive: session.session_id == currentSessionId,
                            isSelected: selectedSessionIds.contains(session.session_id),
                            onSelect: { onSelectSession(session) },
                            onDelete: { onDeleteSession(session) },
                            onRename: { onRenameSession(session) },
                            onPin: { onPinSession(session) }
                        )
                    }
                }
                .padding(.leading, 14)
                .padding(.bottom, 4)
            }
        }
    }
}

struct CompactProjectSessionRow: View {
    @Environment(\.colorScheme) var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences

    let session: SessionInfo
    let isActive: Bool
    let isSelected: Bool
    let onSelect: () -> Void
    let onDelete: () -> Void
    let onRename: () -> Void
    let onPin: () -> Void

    @State private var isHovered = false

    private var titleText: String {
        if let name = session.name, !name.isEmpty {
            return name
        }
        if let preview = session.preview, !preview.isEmpty {
            return preview
        }
        return appPreferences.text("conversation.newConversation")
    }

    private var selectedBackground: Color {
        colorScheme == .dark ? Color.legacyTreeSelectedDark : Color.legacyTreeSelectedLight
    }

    private var selectedAccent: Color {
        colorScheme == .dark ? Color.legacyAccentDark : Color.legacyAccentLight
    }

    private var titleColor: Color {
        if colorScheme == .dark {
            return isActive ? Color.white.opacity(0.96) : Color.white.opacity(isHovered ? 0.86 : 0.74)
        }
        return isActive ? .primary : .secondary.opacity(isHovered ? 0.95 : 0.78)
    }

    var body: some View {
        HStack(spacing: 7) {
            Image(systemName: isActive ? "bubble.left.and.bubble.right.fill" : "bubble.left.and.bubble.right")
                .font(.system(size: 10))
                .foregroundColor(isActive ? selectedAccent : .secondary.opacity(0.55))
                .frame(width: 14)

            Text(titleText)
                .font(.system(size: 11, weight: isActive ? .medium : .regular))
                .foregroundColor(titleColor)
                .lineLimit(1)

            Spacer(minLength: 4)

            if session.is_pinned {
                Image(systemName: "pin.fill")
                    .font(.system(size: 8, weight: .semibold))
                    .foregroundColor(.secondary.opacity(0.58))
            }

            if session.message_count > 0 {
                Text("\(session.message_count)")
                    .font(.system(size: 8, weight: .semibold))
                    .foregroundColor(.secondary.opacity(0.55))
            }
        }
        .padding(.leading, 8)
        .padding(.trailing, 8)
        .padding(.vertical, 6)
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(isActive ? selectedBackground : (isSelected || isHovered ? Color.white.opacity(0.05) : Color.clear))
        )
        .contentShape(Rectangle())
        .onTapGesture(perform: onSelect)
        .onHover { hovering in
            withAnimation(.easeInOut(duration: 0.12)) {
                isHovered = hovering
            }
        }
        .contextMenu {
            Button(session.is_pinned ? appPreferences.text("conversation.unpin") : appPreferences.text("conversation.pin"), action: onPin)
            Button(appPreferences.text("conversation.rename"), action: onRename)
            Divider()
            Button(appPreferences.text("conversation.deleteSession"), action: onDelete)
        }
    }
}

// MARK: - Session Row View

struct SessionRowView: View {
    let session: SessionInfo
    let isActive: Bool
    let isSelected: Bool
    let selectedCount: Int
    let isRenaming: Bool
    @Binding var renameText: String
    let onDelete: () -> Void
    let onMultiDelete: () -> Void
    let onRenameStart: () -> Void
    let onRenameCommit: () -> Void

    @Environment(\.colorScheme) var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    @FocusState private var isFocused: Bool
    @State private var isHovered = false

    private var accent: Color {
        colorScheme == .dark ? .legacyAccentDark : .legacyAccentLight
    }

    private var titleText: String {
        if let name = session.name, !name.isEmpty {
            return name
        }
        if let preview = session.preview, !preview.isEmpty {
            return preview
        }
        return appPreferences.text("conversation.newConversation")
    }

    private var subtitle: String {
        let date = parseDate(session.updated_at)
        return formatRelativeDate(date)
    }

    var body: some View {
        HStack(spacing: 0) {
            // Left accent bar for active session
            RoundedRectangle(cornerRadius: 1)
                .fill(isActive ? accent : Color.clear)
                .frame(width: 2)
                .padding(.vertical, 6)

            HStack(spacing: 10) {
                // Session icon
                sessionIcon
                    .foregroundColor(isActive ? accent : .secondary.opacity(0.5))

                // Text content
                VStack(alignment: .leading, spacing: 2) {
                    if isRenaming {
                        TextField(appPreferences.text("conversation.sessionName"), text: $renameText)
                            .textFieldStyle(.plain)
                            .font(.system(size: 11, weight: .medium))
                            .focused($isFocused)
                            .onSubmit { onRenameCommit() }
                            .onAppear { isFocused = true }
                            .padding(.horizontal, -4)
                    } else {
                        Text(titleText)
                            .font(.system(size: 11, weight: isActive ? .medium : .regular))
                            .lineLimit(1)
                            .foregroundColor(
                                isActive
                                    ? .primary
                                    : (isHovered ? .primary.opacity(0.85) : .secondary.opacity(0.75))
                            )
                    }

                    HStack(spacing: 6) {
                        Text(subtitle)
                            .font(.system(size: 9))
                            .foregroundColor(.secondary.opacity(0.55))

                        if session.message_count > 0 {
                            Text("\(session.message_count)")
                                .font(.system(size: 8, weight: .semibold))
                                .foregroundColor(isActive ? accent : .secondary.opacity(0.6))
                                .padding(.horizontal, 5)
                                .padding(.vertical, 1)
                                .background(
                                    RoundedRectangle(cornerRadius: 3)
                                        .fill(isActive
                                            ? accent.opacity(colorScheme == .dark ? 0.2 : 0.15)
                                            : Color.secondary.opacity(0.1))
                                )
                        }
                    }
                }

                Spacer(minLength: 4)

                // Multi-select checkmark
                if isSelected && !isActive {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 12))
                        .foregroundColor(accent)
                        .transition(.scale.combined(with: .opacity))
                }
            }
            .padding(.leading, 10)
            .padding(.trailing, 10)
            .padding(.vertical, 7)
        }
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(backgroundFill)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
        )
        .contentShape(Rectangle())
        .onHover { hovering in
            withAnimation(.easeInOut(duration: 0.12)) {
                isHovered = hovering
            }
        }
        .contextMenu {
            Button(appPreferences.text("conversation.rename")) { onRenameStart() }
            Divider()
            if isSelected && selectedCount > 1 {
                Button(String(format: appPreferences.text("conversation.deleteSessions"), selectedCount)) { onMultiDelete() }
                    .foregroundColor(.red)
            } else {
                Button(appPreferences.text("conversation.deleteSession")) { onDelete() }
                    .foregroundColor(.red)
            }
        }
    }

    // MARK: - Subviews

    private var sessionIcon: some View {
        ZStack {
            if session.message_count == 0 {
                Image(systemName: "bubble.left")
                    .font(.system(size: 12))
            } else if isActive {
                Image(systemName: "bubble.left.and.bubble.right.fill")
                    .font(.system(size: 12))
            } else {
                Image(systemName: "bubble.left.and.bubble.right")
                    .font(.system(size: 12))
            }
        }
        .frame(width: 18, alignment: .center)
    }

    // MARK: - Helpers

    private var backgroundFill: Color {
        if isActive {
            return accent.opacity(colorScheme == .dark ? 0.18 : 0.10)
        }
        if isSelected {
            return accent.opacity(colorScheme == .dark ? 0.10 : 0.05)
        }
        if isHovered {
            return colorScheme == .dark
                ? Color.white.opacity(0.06)
                : Color.black.opacity(0.04)
        }
        return Color.clear
    }

    private func parseDate(_ dateString: String) -> Date {
        let fmt = DateFormatter()
        fmt.dateFormat = "yyyy-MM-dd HH:mm:ss"
        fmt.locale = Locale(identifier: "en_US_POSIX")
        fmt.timeZone = TimeZone.current
        return fmt.date(from: dateString) ?? Date()
    }

    private func formatRelativeDate(_ date: Date) -> String {
        let cal = Calendar.current
        if cal.isDateInToday(date) {
            let f = DateFormatter()
            f.dateFormat = "HH:mm"
            return f.string(from: date)
        }
        if cal.isDateInYesterday(date) {
            return appPreferences.text("conversation.yesterday")
        }
        if cal.isDate(date, equalTo: Date(), toGranularity: .weekOfYear) {
            let f = DateFormatter()
            f.dateFormat = "EEEE"
            return f.string(from: date)
        }
        let f = DateFormatter()
        f.dateFormat = "MM/dd/yy"
        return f.string(from: date)
    }
}

struct KeyEventHandler: NSViewRepresentable {
    var onKeyDown: (KeyEvent) -> Bool

    func makeNSView(context: Context) -> KeyEventView {
        let view = KeyEventView()
        view.onKeyDown = onKeyDown
        return view
    }

    func updateNSView(_ nsView: KeyEventView, context: Context) {
        nsView.onKeyDown = onKeyDown
    }
}

class KeyEventView: NSView {
    var onKeyDown: ((KeyEvent) -> Bool)?

    override var acceptsFirstResponder: Bool { true }

    override func keyDown(with event: NSEvent) {
        if event.modifierFlags.contains(.command) && event.keyCode == 13 {
            if let handler = onKeyDown {
                if handler(.close) {
                    return
                }
            }
        }
        super.keyDown(with: event)
    }

    override func performKeyEquivalent(with event: NSEvent) -> Bool {
        if event.modifierFlags.contains(.command) && event.keyCode == 13 {
            if let handler = onKeyDown {
                if handler(.close) {
                    return true
                }
            }
        }
        return super.performKeyEquivalent(with: event)
    }
}

enum KeyEvent {
    case close
}

struct LegacyMessageBubble: View {
    let message: Message
    let userBgColor: Color
    let userTextColor: Color
    let agentTextColor: Color

    @State private var isHovered = false
    @State private var isCopied = false

    var body: some View {
        HStack(alignment: .bottom) {
            if message.isUser {
                Spacer(minLength: 40)
                VStack(alignment: .trailing, spacing: 4) {
                    bubbleContent

                    // The row for the copy button always exists to prevent layout shifts
                    copyButton
                        .opacity(isHovered ? 1 : 0)
                        .offset(x: 2)
                }
            } else {
                VStack(alignment: .leading, spacing: 4) {
                    bubbleContent

                    // The row for the copy button always exists to prevent layout shifts
                    copyButton
                        .opacity(isHovered ? 1 : 0)
                        .offset(x: -2)
                }
                Spacer(minLength: 40)
            }
        }
        .contentShape(Rectangle())
        .onHover { hovering in
            withAnimation(.easeInOut(duration: 0.1)) {
                isHovered = hovering
                if !hovering {
                    // Reset copied state when mouse leaves the message bubble
                    isCopied = false
                }
            }
        }
    }

    @MainActor
    private var bubbleContent: some View {
        VStack(alignment: message.isUser ? .trailing : .leading, spacing: 6) {
            if !message.content.isEmpty {
                if message.attachedFiles.isEmpty {
                    Text(MarkdownRenderer.renderWithCodeHighlighting(message.content))
                        .textSelection(.enabled)
                        .font(.system(size: 13))
                        .lineSpacing(4)
                } else {
                    mixedContent()
                        .textSelection(.enabled)
                        .font(.system(size: 13))
                        .lineSpacing(4)
                }
            } else if !message.attachedFiles.isEmpty {
                mixedContent()
                    .textSelection(.enabled)
                    .font(.system(size: 13))
                    .lineSpacing(4)
            }
        }
        .padding(.horizontal, message.isUser ? 12 : 0)
        .padding(.vertical, message.isUser ? 8 : 4)
        .background(message.isUser ? userBgColor : Color.clear)
        .foregroundColor(message.isUser ? userTextColor : agentTextColor)
        .clipShape(
            CustomRoundedCorners(
                topLeading: message.isUser ? 12 : 0,
                topTrailing: message.isUser ? 12 : 0,
                bottomLeading: message.isUser ? 12 : 0,
                bottomTrailing: 0
            )
        )
    }

    @MainActor
    private func mixedContent() -> Text {
        let components = message.content.components(separatedBy: "\u{FFFC}")
        var result = Text("")
        var fileIndex = 0

        let textColorToUse = message.isUser ? userTextColor : agentTextColor

        for (i, component) in components.enumerated() {
            result = result + Text(component)
            if i < components.count - 1 && fileIndex < message.attachedFiles.count {
                let file = message.attachedFiles[fileIndex]

                let renderer = ImageRenderer(content: AttachmentPreviewView(file: file, textColor: textColorToUse))
                renderer.scale = NSScreen.main?.backingScaleFactor ?? 2.0
                if let image = renderer.nsImage {
                    let isImagePreview = AttachmentImageSupport.isDisplayableImage(
                        mimeType: file.mimeType,
                        fileName: file.name
                    )
                    result = result + Text(Image(nsImage: image)).baselineOffset(isImagePreview ? -58 : -3)
                } else {
                    result = result + Text(" [\(file.name)] ")
                }

                fileIndex += 1
            }
        }

        // If there are leftover files that weren't represented by \u{FFFC} (shouldn't happen normally)
        while fileIndex < message.attachedFiles.count {
            let file = message.attachedFiles[fileIndex]
            let renderer = ImageRenderer(content: AttachmentPreviewView(file: file, textColor: textColorToUse))
            renderer.scale = NSScreen.main?.backingScaleFactor ?? 2.0
            if let image = renderer.nsImage {
                let isImagePreview = AttachmentImageSupport.isDisplayableImage(
                    mimeType: file.mimeType,
                    fileName: file.name
                )
                result = result + Text(" ") + Text(Image(nsImage: image)).baselineOffset(isImagePreview ? -58 : -3)
            }
            fileIndex += 1
        }

        return result
    }

    private var copyButton: some View {
        Button(action: {
            let pasteboard = NSPasteboard.general
            pasteboard.clearContents()
            pasteboard.setString(message.content, forType: .string)
            withAnimation {
                isCopied = true
            }
        }) {
            ZStack {
                Image(systemName: "doc.on.doc")
                    .font(.system(size: 10))
                    .opacity(isCopied ? 0 : 1)

                Image(systemName: "checkmark")
                    .font(.system(size: 10, weight: .bold))
                    .opacity(isCopied ? 1 : 0)
            }
            .foregroundColor(isCopied ? .green : .secondary)
            .frame(width: 14, height: 14) // Fixed frame to prevent layout shifts
            .padding(4)
            .background(Color.black.opacity(0.1))
            .cornerRadius(4)
        }
        .buttonStyle(.plain)
    }
}

private struct InteractiveIconButton: View {
    let systemName: String
    let help: String
    var iconSize: CGFloat = 14
    var weight: Font.Weight = .regular
    var foregroundColor: Color = .secondary
    var frameSize: CGFloat = 24
    var isDisabled: Bool = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            InteractiveIconFrame(help: help, frameSize: frameSize, isDisabled: isDisabled) {
                Image(systemName: systemName)
                    .font(.system(size: iconSize, weight: weight))
                    .foregroundColor(foregroundColor)
            }
        }
        .buttonStyle(.plain)
        .disabled(isDisabled)
    }
}

private struct InteractiveIconLabel: View {
    let systemName: String
    let help: String
    var iconSize: CGFloat = 14
    var weight: Font.Weight = .regular
    var foregroundColor: Color = .secondary
    var frameSize: CGFloat = 24
    var externalIsHovered: Bool? = nil

    var body: some View {
        InteractiveIconFrame(help: help, frameSize: frameSize, externalIsHovered: externalIsHovered) {
            Image(systemName: systemName)
                .font(.system(size: iconSize, weight: weight))
                .foregroundColor(foregroundColor)
        }
    }
}

private struct InteractiveIconFrame<Content: View>: View {
    let help: String
    var frameSize: CGFloat
    var isDisabled: Bool = false
    var externalIsHovered: Bool? = nil
    @ViewBuilder let content: Content

    @Environment(\.colorScheme) private var colorScheme
    @State private var internalIsHovered = false
    @State private var showTooltip = false
    @State private var tooltipWorkItem: DispatchWorkItem?

    private var hoverBackground: Color {
        colorScheme == .dark ? Color.white.opacity(0.10) : Color.black.opacity(0.07)
    }

    private var borderColor: Color {
        colorScheme == .dark ? Color.white.opacity(0.08) : Color.black.opacity(0.05)
    }

    private var tooltipBackground: Color {
        colorScheme == .dark ? Color(hex: "2c2c2e") : Color(hex: "202124")
    }

    private var effectiveIsHovered: Bool {
        internalIsHovered || (externalIsHovered ?? false)
    }

    var body: some View {
        content
            .frame(width: frameSize, height: frameSize)
            .background(
                RoundedRectangle(cornerRadius: 7)
                    .fill(effectiveIsHovered && !isDisabled ? hoverBackground : Color.clear)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 7)
                    .stroke(effectiveIsHovered && !isDisabled ? borderColor : Color.clear, lineWidth: 1)
            )
            .opacity(isDisabled ? 0.45 : 1)
            .scaleEffect(effectiveIsHovered && !isDisabled ? 1.04 : 1.0)
            .animation(.easeInOut(duration: 0.12), value: effectiveIsHovered)
            .contentShape(RoundedRectangle(cornerRadius: 7))
            .onHover { hovering in
                internalIsHovered = hovering
            }
            .onChange(of: effectiveIsHovered) { _, hovering in
                updateTooltip(hovering)
            }
            .overlay {
                if showTooltip && !help.isEmpty && effectiveIsHovered && !isDisabled {
                    GeometryReader { proxy in
                        let frame = proxy.frame(in: .global)
                        let showBelow = shouldShowTooltipBelow(frame)
                        tooltipLabel
                            .position(
                                x: proxy.size.width / 2 + tooltipHorizontalOffset(for: frame),
                                y: showBelow ? proxy.size.height + 22 : -22
                            )
                    }
                    .frame(width: frameSize, height: frameSize)
                    .transition(.opacity.combined(with: .scale(scale: 0.96)))
                    .allowsHitTesting(false)
                    .zIndex(50)
                }
            }
            .zIndex(showTooltip ? 10_000 : (effectiveIsHovered ? 1 : 0))
    }

    private var tooltipLabel: some View {
        Text(help)
            .font(.system(size: 11, weight: .medium))
            .foregroundColor(.white)
            .lineLimit(1)
            .fixedSize(horizontal: true, vertical: false)
            .padding(.horizontal, 8)
            .padding(.vertical, 5)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(tooltipBackground)
                    .shadow(color: Color.black.opacity(0.18), radius: 8, y: 3)
            )
    }

    private func shouldShowTooltipBelow(_ frame: CGRect) -> Bool {
        frame.minY < 48
    }

    private func tooltipHorizontalOffset(for frame: CGRect) -> CGFloat {
        guard let screenFrame = NSScreen.main?.visibleFrame else { return 0 }
        let estimatedWidth = min(max(CGFloat(help.count) * 7 + 20, 72), 240)
        let margin: CGFloat = 10
        let leftOverflow = screenFrame.minX + margin - (frame.midX - estimatedWidth / 2)
        if leftOverflow > 0 {
            return leftOverflow
        }
        let rightOverflow = (frame.midX + estimatedWidth / 2) - (screenFrame.maxX - margin)
        if rightOverflow > 0 {
            return -rightOverflow
        }
        return 0
    }

    private func updateTooltip(_ hovering: Bool) {
        tooltipWorkItem?.cancel()
        tooltipWorkItem = nil

        guard hovering, !isDisabled, !help.isEmpty else {
            showTooltip = false
            return
        }

        let workItem = DispatchWorkItem {
            if effectiveIsHovered && !isDisabled {
                withAnimation(.easeInOut(duration: 0.12)) {
                    showTooltip = true
                }
            }
        }
        tooltipWorkItem = workItem
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0, execute: workItem)
    }
}

struct InputAttachmentPreview: View {
    let file: AttachedFile
    let onRemove: () -> Void
    @Environment(\.colorScheme) private var colorScheme

    private var tileBackground: Color {
        colorScheme == .dark ? Color.white.opacity(0.10) : Color.black.opacity(0.06)
    }

    private var tileBorder: Color {
        colorScheme == .dark ? Color.white.opacity(0.18) : Color.black.opacity(0.10)
    }

    var body: some View {
        ZStack(alignment: .topTrailing) {
            previewContent
                .frame(width: 76, height: 54)
                .background(tileBackground)
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(tileBorder, lineWidth: 1)
                )

            Button(action: onRemove) {
                Image(systemName: "xmark")
                    .font(.system(size: 9, weight: .bold))
                    .foregroundColor(colorScheme == .dark ? .white : .black.opacity(0.75))
                    .frame(width: 16, height: 16)
                    .background(colorScheme == .dark ? Color.black.opacity(0.55) : Color.white.opacity(0.92))
                    .clipShape(Circle())
                    .overlay(Circle().stroke(tileBorder, lineWidth: 1))
            }
            .buttonStyle(.plain)
            .offset(x: 5, y: -5)
        }
        .frame(width: 82, height: 60)
        .help(file.path)
    }

    @ViewBuilder
    private var previewContent: some View {
        if let image = AttachmentImageSupport.previewImage(
            filePath: file.path,
            mimeType: file.mimeType,
            fileName: file.name
        ) {
            Image(nsImage: image)
                .resizable()
                .scaledToFill()
                .frame(width: 76, height: 54)
                .clipped()
        } else {
            VStack(spacing: 4) {
                if file.isFolder {
                    SVGIconView(name: "icon.14.explorer.folder.closed", size: 18)
                } else {
                    SVGIconView(name: getFileIconName(fileName: file.name), size: 18)
                }
                Text(file.name)
                    .font(.system(size: 10, weight: .medium))
                    .foregroundColor(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
                    .frame(maxWidth: 64)
            }
            .padding(.horizontal, 6)
        }
    }
}

struct AttachedFileChip: View {
    let file: AttachedFile
    let onRemove: (() -> Void)?
    @State private var isHovered = false
    @Environment(\.colorScheme) var colorScheme

    var body: some View {
        HStack(spacing: 4) {
            if isHovered && onRemove != nil {
                Image(systemName: "xmark.circle.fill")
                    .foregroundColor(.secondary)
                    .font(.system(size: 12))
            } else {
                if file.isFolder {
                    SVGIconView(name: "icon.14.explorer.folder.closed", size: 12)
                } else {
                    SVGIconView(name: getFileIconName(fileName: file.name), size: 12)
                }
            }

            Text(file.name)
                .font(.system(size: 11))
                .foregroundColor(.gray)
                .lineLimit(1)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(colorScheme == .dark ? Color.white.opacity(0.1) : Color.black.opacity(0.08))
        .cornerRadius(6)
        .onHover { hovering in
            withAnimation(.easeInOut(duration: 0.1)) {
                isHovered = hovering
            }
        }
        .onTapGesture {
            if onRemove != nil {
                onRemove?()
            }
        }
        .help(file.path)
    }
}

class TrafficLightHiderView: NSView {
    private var didSetupWindow = false

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        guard let window = self.window, !didSetupWindow else { return }
        didSetupWindow = true

        window.standardWindowButton(.closeButton)?.isHidden = true
        window.standardWindowButton(.miniaturizeButton)?.isHidden = true
        window.standardWindowButton(.zoomButton)?.isHidden = true

        // SwiftUI WindowGroup auto-restores saved window frames via UserDefaults.
        // When a previously-zoomed frame is restored, the window opens visually
        // maximized but NSWindow.isZoomed returns false (frame was set directly,
        // not via zoom(_:)). This breaks the zoom toggle because calling zoom(nil)
        // saves the already-maxed frame as the "user state" and then zooms to a
        // standard state that is also maxed — toggling between identical frames.
        // Detect this and reset to default size so zoom(nil) works correctly.
        guard let screen = window.screen ?? NSScreen.main else { return }
        let screenFrame = screen.visibleFrame
        let isRestoredZoomed = window.frame.width >= screenFrame.width * 0.95
            && window.frame.height >= screenFrame.height * 0.95
        if isRestoredZoomed {
            DispatchQueue.main.async {
                let size = NSSize(width: 1200, height: 800)
                let origin = NSPoint(
                    x: screenFrame.midX - size.width / 2,
                    y: screenFrame.midY - size.height / 2
                )
                window.setFrame(NSRect(origin: origin, size: size), display: true, animate: false)
            }
        }
    }
}

struct TrafficLightHider: NSViewRepresentable {
    func makeNSView(context: Context) -> TrafficLightHiderView {
        TrafficLightHiderView()
    }

    func updateNSView(_ nsView: TrafficLightHiderView, context: Context) {}
}

class OverlayCmdWInterceptView: NSView {
    var onClose: (() -> Void)?
    private var monitor: Any?
    var isActive = false {
        didSet {
            guard isActive != oldValue else { return }
            if isActive {
                monitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
                    if event.modifierFlags.contains(.command) && event.keyCode == 13 {
                        self?.onClose?()
                        return nil
                    }
                    return event
                }
            } else if let m = monitor {
                NSEvent.removeMonitor(m)
                monitor = nil
            }
        }
    }

    override func hitTest(_ point: NSPoint) -> NSView? {
        return nil
    }

    deinit {
        if let m = monitor { NSEvent.removeMonitor(m) }
    }
}

struct OverlayCmdWInterceptor: NSViewRepresentable {
    let isActive: Bool
    let onClose: () -> Void

    func makeNSView(context: Context) -> OverlayCmdWInterceptView {
        let view = OverlayCmdWInterceptView()
        view.onClose = onClose
        return view
    }

    func updateNSView(_ nsView: OverlayCmdWInterceptView, context: Context) {
        nsView.onClose = onClose
        nsView.isActive = isActive
    }
}
