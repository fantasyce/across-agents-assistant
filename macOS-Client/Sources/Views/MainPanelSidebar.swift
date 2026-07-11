import SwiftUI

extension MainPanelView {
    var leftSidebar: some View {
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

            OperationsWorkbenchSidebar(
                selection: $selectedOperationsSurface,
                preferences: appPreferences,
                reviewCount: humanReviewSnapshot.totalCount,
                activeProjectName: viewModel.activeProjectName,
                activeProjectPath: viewModel.activeProjectPath,
                onOpenAgents: { openSettings(.models) },
                onOpenCapabilities: { openSettings(.capabilities) },
                onOpenPlugins: { openSettings(.plugins) },
                onOpenSystem: { openSettings(.diagnostics) }
            )

            if selectedOperationsSurface == .assist {
                Divider().opacity(0.5)

                if showProjectTree {
                    projectTreeSidebar
                } else {
                    projectChatSidebar
                }
            } else {
                Spacer(minLength: 0)
            }
        }
        .frame(width: CGFloat(sidebarWidth))
        .frame(maxHeight: .infinity)
        .background(sidebarBgColor)
    }

    var projectChatSidebar: some View {
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
                        iconSize: MainPanelIconMetrics.glyphSize,
                        weight: .semibold,
                        frameSize: MainPanelIconMetrics.buttonSize,
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

    var projectTreeSidebar: some View {
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

    var centerResizer: some View {
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


    var rightResizer: some View { Divider().opacity(0.5) }

    var rightSidebar: some View {
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

    var onboardingView: some View {
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

    var availabilityLoadingView: some View {
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

}

