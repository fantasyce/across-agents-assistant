import SwiftUI

extension MainPanelView {
    @ViewBuilder
    var centerArea: some View {
        if selectedOperationsSurface == .assist {
            assistCenterArea
        } else {
            OperationsWorkbenchShell(
                selection: $selectedOperationsSurface,
                showsContextDrawer: $showsContextDrawer,
                workspaces: workspaceOperationsViewModel,
                qualityGate: qualityGateViewModel,
                memorySearch: memorySearchViewModel,
                lifecycle: pluginLifecycleViewModel,
                tasks: taskOrchestrationViewModel,
                settings: settingsViewModel,
                preferences: appPreferences,
                autopilotEvidenceTarget: autopilotEvidenceTarget,
                activeProjectPath: operationalProjectPath,
                productProgress: productProgress,
                onStartWork: {
                    selectedOperationsSurface = .assist
                    startNewProtectedWork()
                },
                onOpenPluginCenter: { openSettings(.plugins) },
                onOpenModels: { openSettings(.models) }
            )
        }
    }

    var assistCenterArea: some View {
        VStack(spacing: 0) {
            if shouldShowAssistHeader {
                headerBar
                    .zIndex(1_000)
                Divider()
                    .zIndex(900)
            }
            contentArea
                .zIndex(0)
            if !isViewingAcceptedTask {
                inputArea
                    .zIndex(1_000)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(nsColor: .windowBackgroundColor))
        .contentShape(Rectangle())
        .onTapGesture { NSApp.keyWindow?.makeFirstResponder(nil) }
    }

    private var shouldShowAssistHeader: Bool {
        workSubmissionMode.usesDirectAgent
    }


    @ViewBuilder
    var contentArea: some View {
        switch settingsViewModel.availabilityBootstrapState {
        case .loading:
            availabilityLoadingView
        case .empty:
            if productProgress.isUnlocked(.selfIteration) {
                unifiedWorkEmptyState
            } else {
                onboardingView
            }
        case .ready:
            if workSubmissionMode.usesProtectedDelivery {
                if taskOrchestrationViewModel.selectedTask != nil || taskOrchestrationViewModel.isSubmittingTask {
                    protectedDeliveryContent
                } else {
                    unifiedWorkEmptyState
                }
            } else {
                messageList
            }
        }
    }

    private var protectedDeliveryContent: some View {
        UnifiedDeliveryView(
            task: taskOrchestrationViewModel.selectedTask,
            isLoading: taskOrchestrationViewModel.isSubmittingTask || taskOrchestrationViewModel.isLoading,
            errorMessage: taskOrchestrationViewModel.errorMessage,
            preferences: appPreferences,
            taskViewModel: taskOrchestrationViewModel,
            settingsViewModel: settingsViewModel,
            defaultProjectPath: operationalProjectPath,
            showsTechnicalDetails: $showsSelectedTaskDetails,
            onBack: returnToWorkHome,
            onChooseProject: viewModel.chooseExistingProjectFolder,
            onNewWork: startNewProtectedWork,
            onContinue: {
                let priorGoal = taskOrchestrationViewModel.selectedTask?.description ?? ""
                viewModel.inputText = String(
                    format: appPreferences.text("work.continuePrompt"),
                    priorGoal
                )
            }
        )
    }

    private var unifiedWorkEmptyState: some View {
        UnifiedWorkEmptyState(
            projectName: viewModel.activeProjectName,
            projectPath: operationalProjectPath,
            recentTasks: taskOrchestrationViewModel.tasks,
            isBeginnerMissionAvailable: productProgress.isUnlocked(.selfIteration),
            beginnerMission: beginnerMissionViewModel,
            beginnerGoal: viewModel.inputText,
            preferences: appPreferences,
            onChooseProject: viewModel.chooseExistingProjectFolder,
            onRunBeginnerMission: runBeginnerMission,
            onInstallBeginnerCapability: { openSettings(.plugins) },
            onOpenBeginnerEvidence: {
                guard let result = beginnerMissionViewModel.result,
                      let target = AutopilotEvidenceTarget(
                        runID: result.runID,
                        evidenceRoute: result.evidenceRoute
                      )
                else { return }
                learningProgressStore.record([
                    AcrossLearningEvent(
                        kind: .evidenceInspected,
                        sourceID: target.runID
                    )
                ])
                autopilotEvidenceTarget = target
                selectedOperationsSurface = .autopilot
            },
            onOpenTask: { task in
                showsSelectedTaskDetails = false
                if viewModel.activateProject(matchingDirectory: task.projectDir) {
                    taskOrchestrationViewModel.updateProjectDirectoryFilter(viewModel.activeProjectPath)
                }
                taskOrchestrationViewModel.selectTask(task.taskId)
            }
        )
    }

    func runBeginnerMission(_ userGoal: String) {
        guard let projectPath = operationalProjectPath else {
            viewModel.chooseExistingProjectFolder()
            return
        }
        guard let goal = BeginnerMissionViewModel.normalizedGoal(userGoal) else {
            viewModel.showErrorMessage(appPreferences.text("work.beginner.goalRequired"))
            return
        }
        Task {
            guard let result = await beginnerMissionViewModel.run(
                projectPath: projectPath,
                userGoal: goal
            ) else { return }
            if viewModel.inputText.trimmingCharacters(in: .whitespacesAndNewlines) == goal {
                viewModel.inputText = ""
            }
            guard result.isVerified else { return }
            learningProgressStore.record([
                AcrossLearningEvent(
                    kind: .qualityWorkflow,
                    sourceID: result.runID ?? result.resultSHA256
                )
            ])
        }
    }

    private func returnToWorkHome() {
        showsSelectedTaskDetails = false
        taskOrchestrationViewModel.enterWorkflowPicker()
        appPreferences.automaticDeliveryProtection = true
    }

    private func startNewProtectedWork() {
        returnToWorkHome()
        viewModel.inputText = ""
    }

    var messageList: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 0) {
                    if viewModel.hasMoreHistory {
                        loadEarlierControl
                            .id("load-more")
                    }

                    ForEach(viewModel.messages) { message in
                        AssistantMessageRow(
                            message: message,
                            agentName: currentAgentTitle,
                            preferences: appPreferences
                        )
                            .id(message.id)
                        Divider()
                    }

                    if viewModel.isProcessing {
                        processingRow.id("processing")
                    }
                }
                .minimalPageContentFrame(topPadding: 0, bottomPadding: 24)
            }
            .background(Color(nsColor: .windowBackgroundColor))
            .onChange(of: viewModel.messages.count) {
                if !viewModel.isLoadingMoreHistory,
                   let lastID = viewModel.messages.last?.id {
                    proxy.scrollTo(lastID, anchor: .bottom)
                }
            }
            .onChange(of: viewModel.isProcessing) {
                if viewModel.isProcessing {
                    proxy.scrollTo("processing", anchor: .bottom)
                }
            }
        }
    }

    private var loadEarlierControl: some View {
        HStack {
            Spacer()
            if viewModel.isLoadingMoreHistory {
                ProgressView()
                    .controlSize(.small)
                    .padding(.vertical, 12)
            } else {
                Button {
                    viewModel.loadMoreHistory()
                } label: {
                    Text(appPreferences.text("chat.loadEarlier"))
                        .font(.system(size: 11, weight: .medium))
                }
                .buttonStyle(.plain)
                .foregroundStyle(Color(nsColor: .controlAccentColor))
                .padding(.vertical, 12)
            }
            Spacer()
        }
    }

    private var processingRow: some View {
        HStack(alignment: .top, spacing: 18) {
            Text(currentAgentTitle)
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(.secondary)
                .lineLimit(2)
                .multilineTextAlignment(.trailing)
                .frame(width: 92, alignment: .trailing)

            HStack(spacing: 8) {
                ProgressView()
                    .controlSize(.small)
                Text(appPreferences.text("chat.thinking"))
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 18)
    }

    var inputArea: some View {
        VStack(spacing: 0) {
            VStack(alignment: .leading, spacing: 0) {
                if let notice = viewModel.transientInputNotice {
                    HStack(alignment: .top, spacing: 7) {
                        Image(systemName: "info.circle")
                            .font(.system(size: 11))
                            .foregroundStyle(.secondary)
                            .padding(.top, 1)
                        Text(notice)
                            .font(.system(size: 11))
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                    }
                    .padding(.horizontal, 12)
                    .padding(.top, 10)
                }

                if !viewModel.attachedFiles.isEmpty {
                    inputAttachmentShelf
                }

                if showsOrchestratorUpgradeHint {
                    UnifiedDeliverySetupNotice(
                        isInstalling: taskOrchestrationViewModel.isInstallingOrchestratorPlugin,
                        canInstall: taskOrchestrationViewModel.canInstallOrchestratorPlugin,
                        errorMessage: taskOrchestrationViewModel.orchestratorPluginError,
                        preferences: appPreferences,
                        onInstall: taskOrchestrationViewModel.installOrchestratorPlugin
                    )
                    .padding(.horizontal, 12)
                    .padding(.top, 10)
                }

                ZStack(alignment: .topLeading) {
                    MacEditorView(
                        text: $viewModel.inputText,
                        attachedFiles: $viewModel.attachedFiles,
                        onSubmit: { if viewModel.pendingApproval == nil { submit() } },
                        onNavigateHistory: { up in viewModel.navigateHistory(up: up) },
                        font: .systemFont(ofSize: 13),
                        textColor: .textColor,
                        accessibilityLabel: inputPlaceholder
                    )
                    .disabled(viewModel.pendingApproval != nil || !canEditWorkInput)

                    if viewModel.inputText.isEmpty {
                        Text(inputPlaceholder)
                            .font(.system(size: 13))
                            .foregroundStyle(.tertiary)
                            .lineLimit(1)
                            .truncationMode(.tail)
                            .allowsHitTesting(false)
                    }
                }
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 12)
                .padding(.top, viewModel.attachedFiles.isEmpty && viewModel.transientInputNotice == nil ? 12 : 8)
                .padding(.bottom, 10)

                Divider()
                    .padding(.horizontal, 10)

                HStack(spacing: 6) {
                    if canUseAgentFeatures {
                        MinimalAssistantAttachmentMenu(
                            screenshotOCRTitle: appPreferences.text("screenshot.ocr"),
                            screenshotAttachmentTitle: appPreferences.text("screenshot.attach"),
                            fileAttachmentTitle: appPreferences.text("attachment.addFiles"),
                            isDisabled: viewModel.pendingApproval != nil,
                            onScreenshotOCR: viewModel.requestManualScreenshot,
                            onScreenshotAttachment: viewModel.requestScreenshotAttachment,
                            onFileAttachment: viewModel.requestFileAttachment
                        )
                    }

                    if workSubmissionMode.usesDirectAgent {
                        MinimalAssistantAgentPicker(
                            agents: visibleAgentsForSelection,
                            selectedAgentID: viewModel.selectedAgentId,
                            title: currentAgentTitle,
                            isDisabled: !canUseAgentFeatures || viewModel.pendingApproval != nil,
                            onSelect: { viewModel.selectedAgentId = $0 }
                        )
                    }

                    MinimalAssistantVoiceControls(
                        speechState: speechInput.state,
                        localeIdentifier: appPreferences.resolvedLocaleIdentifier,
                        voiceInputTitle: appPreferences.text("toolbar.voiceInput"),
                        isMuted: viewModel.isMuted,
                        muteTitle: viewModel.isMuted
                            ? appPreferences.text("toolbar.unmute")
                            : appPreferences.text("toolbar.mute"),
                        isSpeechDisabled: !canEditWorkInput || viewModel.pendingApproval != nil,
                        reduceMotion: appPreferences.reduceMotion,
                        onToggleSpeechInput: toggleSpeechInput,
                        onToggleMute: { viewModel.isMuted.toggle() }
                    )

                    if canUseAgentFeatures && !taskOrchestrationViewModel.isOrchestratorPluginUnavailable {
                        Toggle(isOn: $appPreferences.automaticDeliveryProtection) {
                            Label(
                                appPreferences.text("work.automaticCheck"),
                                systemImage: "checkmark.shield"
                            )
                            .font(.system(size: 11, weight: .medium))
                        }
                        .toggleStyle(.checkbox)
                        .focusable(true)
                        .fixedSize()
                        .help(appPreferences.text("work.automaticCheck.help"))
                    }

                    Spacer(minLength: 8)

                    MinimalAssistantSendButton(
                        isProcessing: viewModel.isProcessing || taskOrchestrationViewModel.isSubmittingTask,
                        canSubmit: canSubmitInput,
                        sendTitle: appPreferences.text("chat.send"),
                        stopTitle: appPreferences.text("chat.stop"),
                        onSend: submit,
                        onStop: viewModel.cancelGeneration
                    )
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 7)
            }
            .background(Color(nsColor: .textBackgroundColor))
            .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .stroke(Color(nsColor: .separatorColor), lineWidth: 0.5)
            )
            .frame(maxWidth: windowLayoutSize == .expanded ? 860 : 720)
            .frame(maxWidth: .infinity)
            .padding(.horizontal, windowLayoutSize == .expanded ? 56 : 44)
            .padding(.top, 8)
            .padding(.bottom, 16)
        }
        .background(Color(nsColor: .windowBackgroundColor))
    }

    var inputAttachmentShelf: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(viewModel.attachedFiles) { file in
                    InputAttachmentPreview(file: file) {
                        removeAttachedFile(file)
                    }
                }
            }
            .padding(.horizontal, 12)
            .padding(.top, 10)
            .padding(.bottom, 2)
        }
        .frame(height: 66)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

}
